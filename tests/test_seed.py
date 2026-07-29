from __future__ import annotations

from app.database.seed import seed_catalogs
from app.models import Bank, BankAccount, Branch, BranchIdentifier, ClassificationRule, MovementCategory


def test_seed_catalogs_creates_expected_records(db_session):
    result = seed_catalogs(db_session)

    assert result.banks_created == 2
    assert result.accounts_created == 3
    assert result.branches_created == 21
    assert result.identifiers_created == 21
    assert result.categories_created == 10
    assert result.rules_created == 8

    assert db_session.query(Bank).count() == 2
    assert db_session.query(BankAccount).count() == 3
    assert db_session.query(Branch).count() == 21
    assert db_session.query(BranchIdentifier).count() == 21
    assert db_session.query(MovementCategory).count() == 10
    assert db_session.query(ClassificationRule).count() == 8


def test_seed_catalogs_is_idempotent(db_session):
    seed_catalogs(db_session)
    second_result = seed_catalogs(db_session)

    assert second_result.total_created == 0
    assert db_session.query(Bank).count() == 2
    assert db_session.query(BankAccount).count() == 3
    assert db_session.query(Branch).count() == 21
    assert db_session.query(BranchIdentifier).count() == 21
    assert db_session.query(MovementCategory).count() == 10
    assert db_session.query(ClassificationRule).count() == 8


def test_mifel2_account_has_no_branch_identifiers(db_session):
    seed_catalogs(db_session)
    mifel2 = db_session.query(BankAccount).filter_by(alias="MIFEL2").one()
    identifiers = (
        db_session.query(BranchIdentifier).filter_by(bank_account_id=mifel2.id).count()
    )
    assert identifiers == 0
