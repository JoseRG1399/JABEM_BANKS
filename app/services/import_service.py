"""Orquesta la importación completa de un archivo bancario:

1. Verifica que el archivo no se haya importado antes (hash SHA-256).
2. Lo interpreta con el parser correspondiente al banco de la cuenta.
3. Normaliza cada fila y calcula su hash de movimiento.
4. Determina qué apariciones son nuevas y cuáles ya existen (duplicados).
5. Clasifica cada movimiento nuevo (reglas especiales, luego sucursal).
6. Inserta todo por lotes.

Toda la función opera sobre la sesión recibida sin hacer commit: el
llamador controla la transacción, de modo que la importación completa de un
archivo es atómica.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy.orm import Session

from app.constants import ImportedFileStatus
from app.models import BankAccount, ImportedFile, Movement
from app.parsers.parser_factory import get_parser_for_bank
from app.repositories.branch_repository import BranchRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.imported_file_repository import ImportedFileRepository
from app.repositories.movement_repository import MovementRepository
from app.repositories.rule_repository import RuleRepository
from app.schemas.import_result import ImportResult
from app.schemas.parsed_movement import ParseOutcome
from app.services.classification_service import ClassificationEngine
from app.services.duplicate_service import assign_occurrence_numbers, check_file_duplicate
from app.services.normalization_service import normalize_movement
from app.utils.hashes import compute_file_hash


class DuplicateFileError(Exception):
    """Se lanza cuando el archivo (por su hash SHA-256) ya fue importado antes."""

    def __init__(self, previous_file_name: str, previous_imported_at: dt.datetime) -> None:
        self.previous_file_name = previous_file_name
        self.previous_imported_at = previous_imported_at
        super().__init__(
            f"El archivo ya fue importado previamente el {previous_imported_at:%d/%m/%Y %H:%M} "
            f"como '{previous_file_name}'."
        )


def import_file(
    session: Session,
    file_path: Path,
    bank_account: BankAccount,
    original_name: str | None = None,
) -> ImportResult:
    imported_file_repo = ImportedFileRepository(session)
    movement_repo = MovementRepository(session)
    rule_repo = RuleRepository(session)
    branch_repo = BranchRepository(session)

    file_hash = compute_file_hash(file_path)
    duplicate_info = check_file_duplicate(imported_file_repo, file_hash)
    if duplicate_info.is_duplicate:
        raise DuplicateFileError(
            previous_file_name=duplicate_info.previous_file_name,
            previous_imported_at=duplicate_info.previous_imported_at,
        )

    display_name = original_name or file_path.name
    parser = get_parser_for_bank(bank_account.bank.code, file_path)
    parse_outcome = parser.parse(file_path)

    imported_file = ImportedFile(
        bank_account_id=bank_account.id,
        original_name=display_name,
        stored_name=file_path.name,
        original_path=str(file_path),
        file_type=parser.file_type.value,
        file_hash=file_hash,
        file_size=file_path.stat().st_size,
        total_rows=parse_outcome.total_rows_seen,
        invalid_rows=len(parse_outcome.errors),
        status=ImportedFileStatus.PROCESSING.value,
    )
    imported_file_repo.add(imported_file)
    session.flush()

    normalized_movements = [
        normalize_movement(row, bank_account.id) for row in parse_outcome.rows
    ]
    assignments = assign_occurrence_numbers(movement_repo, normalized_movements)

    engine = _build_classification_engine(session, rule_repo, branch_repo)

    new_movements: list[Movement] = []
    duplicate_count = 0
    unclassified_count = 0

    for assignment in assignments:
        if not assignment.is_new:
            duplicate_count += 1
            continue

        nm = assignment.normalized
        result = engine.classify(nm.normalized_text, bank_account.id)
        if result.status.value == "UNCLASSIFIED":
            unclassified_count += 1

        new_movements.append(
            Movement(
                bank_account_id=bank_account.id,
                branch_id=result.branch_id,
                category_id=result.category_id,
                imported_file_id=imported_file.id,
                movement_date=nm.movement_date,
                description_original=nm.description_original,
                reference_original=nm.reference_original,
                normalized_text=nm.normalized_text,
                external_folio=nm.external_folio,
                charge_cents=nm.charge_cents,
                payment_cents=nm.payment_cents,
                balance_cents=nm.balance_cents,
                movement_hash=nm.base_movement_hash,
                occurrence_number=assignment.occurrence_number,
                classification_status=result.status.value,
                classification_method=result.method.value,
                matched_identifier=result.matched_identifier,
                source_row_number=nm.row_number,
            )
        )

    movement_repo.add_all(new_movements)

    imported_file.inserted_rows = len(new_movements)
    imported_file.duplicate_rows = duplicate_count
    imported_file.unclassified_rows = unclassified_count
    imported_file.status = _resolve_status(parse_outcome, new_movements).value

    session.flush()

    return ImportResult(
        imported_file_id=imported_file.id,
        original_file_name=display_name,
        bank_name=bank_account.bank.name,
        account_alias=bank_account.alias,
        total_rows=imported_file.total_rows,
        inserted_rows=imported_file.inserted_rows,
        duplicate_rows=imported_file.duplicate_rows,
        invalid_rows=imported_file.invalid_rows,
        unclassified_rows=imported_file.unclassified_rows,
        status=ImportedFileStatus(imported_file.status),
        row_errors=list(parse_outcome.errors),
    )


def _resolve_status(
    parse_outcome: ParseOutcome, new_movements: list[Movement]
) -> ImportedFileStatus:
    if parse_outcome.errors and not new_movements:
        return ImportedFileStatus.FAILED
    if parse_outcome.errors:
        return ImportedFileStatus.PARTIAL
    return ImportedFileStatus.SUCCESS


def _build_classification_engine(
    session: Session, rule_repo: RuleRepository, branch_repo: BranchRepository
) -> ClassificationEngine:
    category_repo = CategoryRepository(session)
    rules = rule_repo.list_active()
    identifiers = branch_repo.list_active_identifiers()
    branch_category = category_repo.get_by_code("BRANCH")
    unclassified_category = category_repo.get_by_code("UNCLASSIFIED")
    if branch_category is None or unclassified_category is None:
        raise RuntimeError(
            "Los catálogos de categorías no están cargados. Ejecuta seed_catalogs primero."
        )
    return ClassificationEngine(
        rules=rules,
        branch_identifiers=identifiers,
        branch_category_id=branch_category.id,
        unclassified_category_id=unclassified_category.id,
    )
