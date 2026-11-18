"""Clasificación de movimientos (sección 13 de la especificación).

Orden de evaluación obligatorio:
    1. Reglas especiales (por prioridad, filtradas por cuenta si aplica).
    2. Identificador de sucursal (restringido a la cuenta bancaria).
    3. No clasificado.

Las reglas y los identificadores se cargan una sola vez en memoria por
importación (``ClassificationEngine``) para evitar consultas repetidas por
cada movimiento, requisito de rendimiento de la sección 20.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.constants import CategoryCode, ClassificationMethod, ClassificationStatus, IdentifierType, MatchType
from app.models import (
    BranchIdentifier,
    ClassificationRule,
    Movement,
    MovementCategory,
    MovementClassificationHistory,
)
from app.utils.hashes import compute_movement_hash
from app.utils.money import invert_charge_to_negative_payment, split_charge_into_base_and_vat
from app.utils.text import extract_digit_blocks, normalize_text


@dataclass
class ClassificationResult:
    status: ClassificationStatus
    method: ClassificationMethod
    category_id: int | None
    branch_id: int | None
    matched_identifier: str | None
    invert_to_negative_payment: bool = False
    split_vat_from_charge: bool = False


def _text_matches_rule(normalized_text: str, rule: ClassificationRule) -> bool:
    haystack = normalized_text if rule.case_sensitive else normalized_text.upper()
    needle = rule.pattern if rule.case_sensitive else rule.pattern.upper()

    if rule.match_type == MatchType.CONTAINS:
        return needle in haystack
    if rule.match_type == MatchType.STARTS_WITH:
        return haystack.startswith(needle)
    if rule.match_type == MatchType.ENDS_WITH:
        return haystack.endswith(needle)
    if rule.match_type == MatchType.EXACT:
        return haystack == needle
    if rule.match_type == MatchType.REGEX:
        flags = 0 if rule.case_sensitive else re.IGNORECASE
        return re.search(rule.pattern, normalized_text, flags) is not None
    raise ValueError(f"Tipo de coincidencia no soportado: {rule.match_type}")


def _rule_applies_to_account(rule: ClassificationRule, bank_account_id: int) -> bool:
    return rule.bank_account_id is None or rule.bank_account_id == bank_account_id


def _identifier_matches(
    identifier: BranchIdentifier, normalized_text: str, digit_blocks: list[str]
) -> bool:
    if identifier.identifier_type == IdentifierType.TERMINAL_SUFFIX:
        suffix = identifier.identifier
        return any(block.endswith(suffix) for block in digit_blocks)
    if identifier.identifier_type == IdentifierType.REFERENCE:
        return identifier.identifier in digit_blocks
    if identifier.identifier_type == IdentifierType.CONTAINS:
        return identifier.identifier.upper() in normalized_text
    if identifier.identifier_type == IdentifierType.EXACT:
        return normalized_text == identifier.identifier.upper()
    if identifier.identifier_type == IdentifierType.REGEX:
        pattern = identifier.regex_pattern or identifier.identifier
        return re.search(pattern, normalized_text) is not None
    raise ValueError(f"Tipo de identificador no soportado: {identifier.identifier_type}")


class ClassificationEngine:
    def __init__(
        self,
        rules: list[ClassificationRule],
        branch_identifiers: list[BranchIdentifier],
        branch_category_id: int,
        unclassified_category_id: int,
    ) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority)
        self._identifiers_by_account: dict[int, list[BranchIdentifier]] = {}
        for identifier in branch_identifiers:
            self._identifiers_by_account.setdefault(identifier.bank_account_id, []).append(
                identifier
            )
        for identifiers in self._identifiers_by_account.values():
            identifiers.sort(key=lambda i: i.priority)
        self._branch_category_id = branch_category_id
        self._unclassified_category_id = unclassified_category_id

    def classify(self, normalized_text: str, bank_account_id: int) -> ClassificationResult:
        for rule in self._rules:
            if not _rule_applies_to_account(rule, bank_account_id):
                continue
            if _text_matches_rule(normalized_text, rule):
                return ClassificationResult(
                    status=ClassificationStatus.CLASSIFIED,
                    method=ClassificationMethod.SPECIAL_RULE,
                    category_id=rule.category_id,
                    branch_id=rule.branch_id,
                    matched_identifier=rule.pattern,
                    invert_to_negative_payment=rule.invert_to_negative_payment,
                    split_vat_from_charge=rule.split_vat_from_charge,
                )

        identifier = self._match_branch_identifier(normalized_text, bank_account_id)
        if identifier is not None:
            return ClassificationResult(
                status=ClassificationStatus.CLASSIFIED,
                method=ClassificationMethod.BRANCH_IDENTIFIER,
                category_id=self._branch_category_id,
                branch_id=identifier.branch_id,
                matched_identifier=identifier.identifier,
            )

        return ClassificationResult(
            status=ClassificationStatus.UNCLASSIFIED,
            method=ClassificationMethod.NONE,
            category_id=self._unclassified_category_id,
            branch_id=None,
            matched_identifier=None,
        )

    def _match_branch_identifier(
        self, normalized_text: str, bank_account_id: int
    ) -> BranchIdentifier | None:
        identifiers = self._identifiers_by_account.get(bank_account_id, [])
        if not identifiers:
            return None

        digit_blocks = extract_digit_blocks(normalized_text)
        for identifier in identifiers:
            if _identifier_matches(identifier, normalized_text, digit_blocks):
                return identifier
        return None


# ---------------------------------------------------------------------------
# Funciones auxiliares expuestas para "probar" reglas e identificadores desde
# la UI (pantallas de Sucursales y Reglas, sección 15.6 y 15.7).
# ---------------------------------------------------------------------------
def rule_matches_text(
    pattern: str, match_type: str, case_sensitive: bool, normalized_text: str
) -> bool:
    """Prueba si un patrón candidato coincidiría con un texto ya normalizado."""
    candidate = ClassificationRule(
        pattern=pattern, match_type=match_type, case_sensitive=case_sensitive
    )
    return _text_matches_rule(normalized_text, candidate)


def identifier_matches_text(
    identifier: str,
    identifier_type: str,
    normalized_text: str,
    regex_pattern: str | None = None,
) -> bool:
    """Prueba si un identificador candidato coincidiría con un texto normalizado."""
    candidate = BranchIdentifier(
        identifier=identifier, identifier_type=identifier_type, regex_pattern=regex_pattern
    )
    digit_blocks = extract_digit_blocks(normalized_text)
    return _identifier_matches(candidate, normalized_text, digit_blocks)


def count_matching_movements(
    session: Session,
    pattern: str,
    match_type: str,
    case_sensitive: bool,
    bank_account_id: int | None = None,
) -> int:
    """Cuenta cuántos movimientos existentes coincidirían con una regla candidata
    (sección 14, punto 7: "Mostrar cuántos movimientos existentes coincidirían").
    """
    candidate = ClassificationRule(
        pattern=pattern, match_type=match_type, case_sensitive=case_sensitive
    )
    query = session.query(Movement.normalized_text)
    if bank_account_id:
        query = query.filter(Movement.bank_account_id == bank_account_id)

    count = 0
    for (normalized_text,) in query.yield_per(1000):
        if _text_matches_rule(normalized_text, candidate):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Reclasificación manual (sección 14 de la especificación)
# ---------------------------------------------------------------------------
@dataclass
class ReclassifyRequest:
    movement_ids: list[int] = field(default_factory=list)
    branch_id: int | None = None
    category_id: int | None = None
    note: str | None = None
    invert_to_negative_payment: bool = False
    split_vat_from_charge: bool = False
    create_rule: bool = False
    rule_name: str | None = None
    rule_pattern: str | None = None
    rule_match_type: str | None = None
    rule_case_sensitive: bool = False
    rule_bank_account_id: int | None = None
    rule_priority: int = 100


@dataclass
class ReclassifyResult:
    updated_movement_ids: list[int] = field(default_factory=list)
    created_rule_id: int | None = None
    retroactive_count: int = 0


def get_direct_debit_vat_category_id(session: Session) -> int:
    category = (
        session.query(MovementCategory)
        .filter_by(code=CategoryCode.DIRECT_DEBIT_VAT.value)
        .one_or_none()
    )
    if category is None:
        raise RuntimeError(
            "La categoría 'IVA domiciliación' no está cargada. Ejecuta seed_catalogs primero."
        )
    return category.id


def _split_movement_into_base_and_vat(
    session: Session,
    movement: Movement,
    *,
    branch_id: int | None,
    category_id: int | None,
    vat_category_id: int,
    matched_identifier: str | None,
    classification_status: str,
    classification_method: str,
    reason: str,
) -> Movement | None:
    """Convierte ``movement`` en la parte "base" de un cargo con IVA (p. ej.
    una domiciliación) y crea un segundo movimiento con la parte de IVA,
    enlazado mediante ``split_from_movement``. No hace nada si el movimiento
    no tiene cargo que dividir.

    El IVA se calcula con :func:`split_charge_into_base_and_vat` (16% ya
    incluido en el total). El hash del movimiento de IVA se deriva de su
    propia descripción e importe, así que un archivo reimportado lo
    reconoce como duplicado igual que a cualquier otro movimiento.
    """
    if not movement.charge_cents:
        return None

    base_cents, vat_cents = split_charge_into_base_and_vat(movement.charge_cents)

    previous_branch_id = movement.branch_id
    previous_category_id = movement.category_id

    movement.charge_cents = base_cents
    movement.branch_id = branch_id
    movement.category_id = category_id
    movement.classification_status = classification_status
    movement.classification_method = classification_method
    movement.matched_identifier = matched_identifier

    vat_description = f"IVA {movement.description_original}"
    vat_normalized_text = normalize_text(vat_description)
    vat_normalized_reference = (
        normalize_text(movement.reference_original) if movement.reference_original else ""
    )
    vat_hash = compute_movement_hash(
        bank_account_id=movement.bank_account_id,
        movement_date=movement.movement_date,
        normalized_concept=vat_normalized_text,
        normalized_reference=vat_normalized_reference,
        external_folio=movement.external_folio or "",
        charge_cents=vat_cents,
        payment_cents=0,
        balance_cents=movement.balance_cents,
    )
    # Numera la aparición por si, en un caso extremo, ya existiera otro
    # movimiento con el mismo hash (misma cuenta/fecha/concepto/importe).
    existing_with_hash = session.query(Movement).filter_by(movement_hash=vat_hash).count()

    vat_movement = Movement(
        bank_account_id=movement.bank_account_id,
        branch_id=branch_id,
        category_id=vat_category_id,
        imported_file_id=movement.imported_file_id,
        movement_date=movement.movement_date,
        description_original=vat_description,
        reference_original=movement.reference_original,
        normalized_text=vat_normalized_text,
        external_folio=movement.external_folio,
        charge_cents=vat_cents,
        payment_cents=0,
        balance_cents=movement.balance_cents,
        movement_hash=vat_hash,
        occurrence_number=existing_with_hash + 1,
        classification_status=classification_status,
        classification_method=classification_method,
        matched_identifier=matched_identifier,
        source_row_number=movement.source_row_number,
        split_from_movement=movement,
    )
    session.add(vat_movement)

    session.add(
        MovementClassificationHistory(
            movement_id=movement.id,
            previous_branch_id=previous_branch_id,
            new_branch_id=branch_id,
            previous_category_id=previous_category_id,
            new_category_id=category_id,
            reason=reason,
            create_rule=True,
        )
    )
    # Sin este flush, una segunda llamada dentro de la misma sesión (sin un
    # commit de por medio) no vería el movimiento de IVA recién creado al
    # comprobar si algo ya se dividió, y lo volvería a partir.
    session.flush()
    return vat_movement


def apply_rule_to_matching_movements(
    session: Session,
    rule: ClassificationRule,
    exclude_movement_ids: set[int] | None = None,
) -> int:
    """Aplica una regla ya guardada (categoría, sucursal y, si corresponde,
    la conversión de cargo a abono negativo o la división de cargo con IVA)
    a todos los movimientos existentes que coincidan con su patrón. Devuelve
    cuántos se actualizaron.

    Se usa tanto al crear una regla desde la reclasificación manual como al
    aplicar retroactivamente una regla creada en la pantalla de Reglas.
    """
    query = session.query(Movement)
    if exclude_movement_ids:
        query = query.filter(~Movement.id.in_(exclude_movement_ids))
    if rule.bank_account_id:
        query = query.filter(Movement.bank_account_id == rule.bank_account_id)

    vat_category_id: int | None = None
    updated_count = 0
    for movement in query.all():
        if not _text_matches_rule(movement.normalized_text, rule):
            continue

        if rule.split_vat_from_charge:
            # Ni un movimiento ya dividido (es el IVA de otro) ni uno que ya
            # tiene su contraparte de IVA se vuelven a partir.
            if movement.split_from_movement_id is not None:
                continue
            already_split = (
                session.query(Movement.id)
                .filter_by(split_from_movement_id=movement.id)
                .first()
                is not None
            )
            if already_split or not movement.charge_cents:
                continue
            if vat_category_id is None:
                vat_category_id = get_direct_debit_vat_category_id(session)
            _split_movement_into_base_and_vat(
                session,
                movement,
                branch_id=rule.branch_id,
                category_id=rule.category_id,
                vat_category_id=vat_category_id,
                matched_identifier=rule.pattern,
                classification_status=ClassificationStatus.CLASSIFIED.value,
                classification_method=ClassificationMethod.SPECIAL_RULE.value,
                reason="Reclasificación retroactiva por nueva regla (división de IVA).",
            )
            updated_count += 1
            continue

        previous_branch_id = movement.branch_id
        previous_category_id = movement.category_id
        movement.branch_id = rule.branch_id
        movement.category_id = rule.category_id
        movement.classification_status = ClassificationStatus.CLASSIFIED.value
        movement.classification_method = ClassificationMethod.SPECIAL_RULE.value
        movement.matched_identifier = rule.pattern
        if rule.invert_to_negative_payment:
            movement.charge_cents, movement.payment_cents = invert_charge_to_negative_payment(
                movement.charge_cents, movement.payment_cents
            )

        session.add(
            MovementClassificationHistory(
                movement_id=movement.id,
                previous_branch_id=previous_branch_id,
                new_branch_id=rule.branch_id,
                previous_category_id=previous_category_id,
                new_category_id=rule.category_id,
                reason="Reclasificación retroactiva por nueva regla.",
                create_rule=True,
            )
        )
        updated_count += 1

    return updated_count


def reclassify_movements(session: Session, request: ReclassifyRequest) -> ReclassifyResult:
    """Aplica una nueva sucursal/categoría a los movimientos seleccionados y,
    opcionalmente, crea una regla y la aplica retroactivamente a todos los
    movimientos existentes que coincidan con ella.
    """
    updated_ids: list[int] = []
    vat_category_id: int | None = None
    for movement_id in request.movement_ids:
        movement = session.get(Movement, movement_id)
        if movement is None:
            continue

        if (
            request.split_vat_from_charge
            and movement.charge_cents
            and movement.split_from_movement_id is None
        ):
            if vat_category_id is None:
                vat_category_id = get_direct_debit_vat_category_id(session)
            _split_movement_into_base_and_vat(
                session,
                movement,
                branch_id=request.branch_id,
                category_id=request.category_id,
                vat_category_id=vat_category_id,
                matched_identifier=None,
                classification_status=ClassificationStatus.MANUAL.value,
                classification_method=ClassificationMethod.MANUAL.value,
                reason=request.note or "División manual de cargo con IVA.",
            )
            updated_ids.append(movement.id)
            continue

        previous_branch_id = movement.branch_id
        previous_category_id = movement.category_id

        movement.branch_id = request.branch_id
        movement.category_id = request.category_id
        movement.classification_status = ClassificationStatus.MANUAL.value
        movement.classification_method = ClassificationMethod.MANUAL.value
        movement.matched_identifier = None
        if request.invert_to_negative_payment:
            movement.charge_cents, movement.payment_cents = invert_charge_to_negative_payment(
                movement.charge_cents, movement.payment_cents
            )

        session.add(
            MovementClassificationHistory(
                movement_id=movement.id,
                previous_branch_id=previous_branch_id,
                new_branch_id=request.branch_id,
                previous_category_id=previous_category_id,
                new_category_id=request.category_id,
                reason=request.note,
                create_rule=request.create_rule,
            )
        )
        updated_ids.append(movement.id)

    created_rule_id: int | None = None
    retroactive_count = 0

    if request.create_rule:
        rule = ClassificationRule(
            name=request.rule_name or "Regla creada desde reclasificación",
            category_id=request.category_id,
            bank_account_id=request.rule_bank_account_id,
            branch_id=request.branch_id,
            pattern=request.rule_pattern,
            match_type=request.rule_match_type,
            priority=request.rule_priority,
            case_sensitive=request.rule_case_sensitive,
            invert_to_negative_payment=request.invert_to_negative_payment,
            split_vat_from_charge=request.split_vat_from_charge,
        )
        session.add(rule)
        session.flush()
        created_rule_id = rule.id

        retroactive_count = apply_rule_to_matching_movements(
            session, rule, exclude_movement_ids=set(updated_ids)
        )

    session.flush()

    return ReclassifyResult(
        updated_movement_ids=updated_ids,
        created_rule_id=created_rule_id,
        retroactive_count=retroactive_count,
    )
