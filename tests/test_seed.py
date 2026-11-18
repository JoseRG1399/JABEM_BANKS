from __future__ import annotations

from app.database.seed import seed_catalogs
from app.models import Bank, BankAccount, Branch, BranchIdentifier, ClassificationRule, MovementCategory


def test_seed_catalogs_creates_expected_records(db_session):
    result = seed_catalogs(db_session)

    assert result.banks_created == 2
    assert result.accounts_created == 3
    assert result.branches_created == 21
    assert result.identifiers_created == 21
    assert result.categories_created == 14
    assert result.rules_created == 14

    assert db_session.query(Bank).count() == 2
    assert db_session.query(BankAccount).count() == 3
    assert db_session.query(Branch).count() == 21
    assert db_session.query(BranchIdentifier).count() == 21
    assert db_session.query(MovementCategory).count() == 14
    assert db_session.query(ClassificationRule).count() == 14


def test_seed_catalogs_is_idempotent(db_session):
    seed_catalogs(db_session)
    second_result = seed_catalogs(db_session)

    assert second_result.total_created == 0
    assert db_session.query(Bank).count() == 2
    assert db_session.query(BankAccount).count() == 3
    assert db_session.query(Branch).count() == 21
    assert db_session.query(BranchIdentifier).count() == 21
    assert db_session.query(MovementCategory).count() == 14
    assert db_session.query(ClassificationRule).count() == 14


def test_mifel2_account_has_no_branch_identifiers(db_session):
    seed_catalogs(db_session)
    mifel2 = db_session.query(BankAccount).filter_by(alias="MIFEL2").one()
    identifiers = (
        db_session.query(BranchIdentifier).filter_by(bank_account_id=mifel2.id).count()
    )
    assert identifiers == 0


def test_bonification_rules_classify_without_branch(db_session):
    from app.constants import CategoryCode
    from app.services.classification_service import ClassificationEngine
    from app.utils.text import normalize_text

    seed_catalogs(db_session)
    categories = {c.code: c.id for c in db_session.query(MovementCategory).all()}
    bbva = db_session.query(BankAccount).filter_by(alias="BBVA").one()
    engine = ClassificationEngine(
        rules=db_session.query(ClassificationRule).all(),
        branch_identifiers=db_session.query(BranchIdentifier).all(),
        branch_category_id=categories[CategoryCode.BRANCH.value],
        unclassified_category_id=categories[CategoryCode.UNCLASSIFIED.value],
    )

    cases = {
        "BONIFICACION DCC BBVA/140004893518ABO 140004893518": CategoryCode.BONIFICATION,
        "IVA BONIFICACION DCC BBVA/140004893518ABO 140004893518": CategoryCode.BONIFICATION_VAT,
    }
    for text, expected in cases.items():
        result = engine.classify(normalize_text(text), bbva.id)
        assert result.category_id == categories[expected.value]
        assert result.branch_id is None


def test_stripe_rule_classifies_mifel2_without_branch(db_session):
    from app.constants import CategoryCode
    from app.services.classification_service import ClassificationEngine
    from app.utils.text import normalize_text

    seed_catalogs(db_session)
    categories = {c.code: c.id for c in db_session.query(MovementCategory).all()}
    mifel2 = db_session.query(BankAccount).filter_by(alias="MIFEL2").one()
    engine = ClassificationEngine(
        rules=db_session.query(ClassificationRule).all(),
        branch_identifiers=db_session.query(BranchIdentifier).all(),
        branch_category_id=categories[CategoryCode.BRANCH.value],
        unclassified_category_id=categories[CategoryCode.UNCLASSIFIED.value],
    )

    result = engine.classify(normalize_text("Stripe"), mifel2.id)
    assert result.category_id == categories[CategoryCode.STRIPE.value]
    assert result.branch_id is None
