import datetime as dt

from app.models import Bank, BankAccount, ImportedFile, Movement
from app.repositories.imported_file_repository import ImportedFileRepository
from app.repositories.movement_repository import MovementRepository
from app.services.duplicate_service import assign_occurrence_numbers, check_file_duplicate
from app.services.normalization_service import NormalizedMovement


def _seed_bank_account(db_session) -> BankAccount:
    bank = Bank(code="BBVA", name="BBVA")
    db_session.add(bank)
    db_session.flush()
    account = BankAccount(bank_id=bank.id, account_name="BBVA", alias="BBVA")
    db_session.add(account)
    db_session.flush()
    return account


def test_check_file_duplicate_detects_existing_hash(db_session):
    account = _seed_bank_account(db_session)
    imported_file = ImportedFile(
        bank_account_id=account.id,
        original_name="archivo.txt",
        stored_name="archivo.txt",
        original_path="C:/tmp/archivo.txt",
        file_type="TXT",
        file_hash="abc123",
        file_size=10,
    )
    db_session.add(imported_file)
    db_session.flush()

    repo = ImportedFileRepository(db_session)
    result = check_file_duplicate(repo, "abc123")

    assert result.is_duplicate is True
    assert result.previous_file_name == "archivo.txt"
    assert result.previous_imported_at is not None


def test_check_file_duplicate_returns_false_for_new_hash(db_session):
    repo = ImportedFileRepository(db_session)
    result = check_file_duplicate(repo, "hash-nuevo")
    assert result.is_duplicate is False


def _normalized(hash_value: str, row_number: int = 1) -> NormalizedMovement:
    return NormalizedMovement(
        row_number=row_number,
        movement_date=dt.date(2026, 7, 1),
        description_original="CONCEPTO",
        reference_original=None,
        normalized_text="CONCEPTO",
        external_folio=None,
        charge_cents=1000,
        payment_cents=0,
        balance_cents=100000,
        base_movement_hash=hash_value,
    )


def test_two_identical_movements_in_same_file_get_separate_occurrences(db_session):
    repo = MovementRepository(db_session)
    movements = [_normalized("hash-x", 1), _normalized("hash-x", 2)]

    assignments = assign_occurrence_numbers(repo, movements)

    assert [a.occurrence_number for a in assignments] == [1, 2]
    assert all(a.is_new for a in assignments)


def test_subsequent_file_with_extra_occurrence_only_inserts_the_new_one(db_session):
    account = _seed_bank_account(db_session)
    imported_file = ImportedFile(
        bank_account_id=account.id,
        original_name="a.txt",
        stored_name="a.txt",
        original_path="C:/tmp/a.txt",
        file_type="TXT",
        file_hash="hash-file-a",
        file_size=10,
    )
    db_session.add(imported_file)
    db_session.flush()

    existing = Movement(
        bank_account_id=account.id,
        imported_file_id=imported_file.id,
        movement_date=dt.date(2026, 7, 1),
        description_original="CONCEPTO",
        normalized_text="CONCEPTO",
        charge_cents=1000,
        payment_cents=0,
        movement_hash="hash-x",
        occurrence_number=1,
        classification_status="UNCLASSIFIED",
        classification_method="NONE",
        source_row_number=1,
    )
    db_session.add(existing)
    db_session.flush()

    repo = MovementRepository(db_session)
    movements = [_normalized("hash-x", 1), _normalized("hash-x", 2)]
    assignments = assign_occurrence_numbers(repo, movements)

    assert assignments[0].occurrence_number == 1
    assert assignments[0].is_new is False
    assert assignments[1].occurrence_number == 2
    assert assignments[1].is_new is True
