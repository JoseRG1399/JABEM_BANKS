from app.constants import ClassificationMethod, ClassificationStatus, IdentifierType, MatchType
from app.models import BranchIdentifier, ClassificationRule
from app.services.classification_service import ClassificationEngine
from app.utils.text import normalize_text

BRANCH_CATEGORY_ID = 1
UNCLASSIFIED_CATEGORY_ID = 2
COMMISSION_CATEGORY_ID = 3
COMMISSION_VAT_CATEGORY_ID = 4

BBVA_ACCOUNT_ID = 10
MIFEL2_ACCOUNT_ID = 20


def _rule(**overrides) -> ClassificationRule:
    defaults = dict(
        name="regla",
        category_id=COMMISSION_CATEGORY_ID,
        bank_account_id=BBVA_ACCOUNT_ID,
        branch_id=None,
        pattern="COMISION",
        match_type=MatchType.CONTAINS.value,
        priority=100,
        case_sensitive=False,
        active=True,
    )
    defaults.update(overrides)
    return ClassificationRule(**defaults)


def _identifier(**overrides) -> BranchIdentifier:
    defaults = dict(
        branch_id=19,
        bank_account_id=BBVA_ACCOUNT_ID,
        identifier="4102",
        identifier_type=IdentifierType.TERMINAL_SUFFIX.value,
        regex_pattern=None,
        priority=100,
        active=True,
    )
    defaults.update(overrides)
    return BranchIdentifier(**defaults)


def _engine(rules=None, identifiers=None) -> ClassificationEngine:
    return ClassificationEngine(
        rules=rules or [],
        branch_identifiers=identifiers or [],
        branch_category_id=BRANCH_CATEGORY_ID,
        unclassified_category_id=UNCLASSIFIED_CATEGORY_ID,
    )


def test_special_rule_classifies_movement():
    engine = _engine(rules=[_rule(pattern="COMISION", category_id=COMMISSION_CATEGORY_ID)])
    text = normalize_text("COMISION MANEJO DE CUENTA")

    result = engine.classify(text, BBVA_ACCOUNT_ID)

    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.method == ClassificationMethod.SPECIAL_RULE
    assert result.category_id == COMMISSION_CATEGORY_ID


def test_iva_comision_has_priority_over_plain_comision():
    rules = [
        _rule(
            name="IVA comisión",
            pattern=r"(?=.*\bIVA\b)(?=.*\bCOMISION\b)",
            match_type=MatchType.REGEX.value,
            category_id=COMMISSION_VAT_CATEGORY_ID,
            priority=15,
        ),
        _rule(name="Comisión", pattern="COMISION", category_id=COMMISSION_CATEGORY_ID, priority=30),
    ]
    engine = _engine(rules=rules)

    text = normalize_text("IVA TASA DE DESC COMISION MANEJO DE CUENTA")
    result = engine.classify(text, BBVA_ACCOUNT_ID)

    assert result.category_id == COMMISSION_VAT_CATEGORY_ID


def test_plain_comision_without_iva_uses_commission_rule():
    rules = [
        _rule(
            name="IVA comisión",
            pattern=r"(?=.*\bIVA\b)(?=.*\bCOMISION\b)",
            match_type=MatchType.REGEX.value,
            category_id=COMMISSION_VAT_CATEGORY_ID,
            priority=15,
        ),
        _rule(name="Comisión", pattern="COMISION", category_id=COMMISSION_CATEGORY_ID, priority=30),
    ]
    engine = _engine(rules=rules)

    text = normalize_text("COMISION MANEJO DE CUENTA")
    result = engine.classify(text, BBVA_ACCOUNT_ID)

    assert result.category_id == COMMISSION_CATEGORY_ID


def test_branch_identifier_classifies_by_terminal_suffix():
    engine = _engine(identifiers=[_identifier(identifier="4102", branch_id=19)])
    text = normalize_text("VENTAS DEBITO/149064102 TERMINALES PUNTO DE VENTA")

    result = engine.classify(text, BBVA_ACCOUNT_ID)

    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.method == ClassificationMethod.BRANCH_IDENTIFIER
    assert result.branch_id == 19
    assert result.category_id == BRANCH_CATEGORY_ID
    assert result.matched_identifier == "4102"


def test_branch_identifier_does_not_match_arbitrary_four_digits():
    engine = _engine(identifiers=[_identifier(identifier="4102", branch_id=19)])
    text = normalize_text("VENTAS DEBITO/149069999 TERMINALES PUNTO DE VENTA")

    result = engine.classify(text, BBVA_ACCOUNT_ID)

    assert result.status == ClassificationStatus.UNCLASSIFIED


def test_branch_identifier_is_limited_to_its_bank_account():
    engine = _engine(
        identifiers=[_identifier(identifier="4102", branch_id=19, bank_account_id=BBVA_ACCOUNT_ID)]
    )
    text = normalize_text("VENTAS DEBITO/149064102 TERMINALES PUNTO DE VENTA")

    result = engine.classify(text, MIFEL2_ACCOUNT_ID)

    assert result.status == ClassificationStatus.UNCLASSIFIED
    assert result.branch_id is None


def test_unmatched_movement_is_unclassified():
    engine = _engine()
    text = normalize_text("MOVIMIENTO DESCONOCIDO SIN PATRON")

    result = engine.classify(text, BBVA_ACCOUNT_ID)

    assert result.status == ClassificationStatus.UNCLASSIFIED
    assert result.method == ClassificationMethod.NONE
    assert result.category_id == UNCLASSIFIED_CATEGORY_ID
