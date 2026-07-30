import datetime as dt

import pytest

from app.database.seed import seed_catalogs
from app.models import BankAccount, Branch, ImportedFile, Movement, MovementCategory
from app.repositories.movement_repository import MovementFilter, MovementRepository


@pytest.fixture()
def catalogs(db_session):
    seed_catalogs(db_session)
    bbva = db_session.query(BankAccount).filter_by(alias="BBVA").one()
    mifel = db_session.query(BankAccount).filter_by(alias="MIFEL").one()
    branch_alfredo = db_session.query(Branch).filter_by(branch_number="01").one()
    commission_category = db_session.query(MovementCategory).filter_by(code="COMMISSION").one()
    unclassified_category = (
        db_session.query(MovementCategory).filter_by(code="UNCLASSIFIED").one()
    )

    imported_file = ImportedFile(
        bank_account_id=bbva.id,
        original_name="extracto.txt",
        stored_name="extracto.txt",
        original_path="C:/tmp/extracto.txt",
        file_type="TXT",
        file_hash="hash-file-1",
        file_size=10,
    )
    db_session.add(imported_file)
    db_session.flush()

    def make_movement(**overrides):
        defaults = dict(
            bank_account_id=bbva.id,
            branch_id=None,
            category_id=unclassified_category.id,
            imported_file_id=imported_file.id,
            movement_date=dt.date(2026, 7, 1),
            description_original="MOVIMIENTO",
            normalized_text="MOVIMIENTO",
            charge_cents=0,
            payment_cents=0,
            balance_cents=None,
            movement_hash="hash-unico",
            occurrence_number=1,
            classification_status="UNCLASSIFIED",
            classification_method="NONE",
            source_row_number=1,
        )
        defaults.update(overrides)
        return Movement(**defaults)

    movements = [
        make_movement(
            movement_date=dt.date(2026, 7, 1),
            description_original="COMISION MANEJO DE CUENTA",
            normalized_text="COMISION MANEJO DE CUENTA",
            charge_cents=15000,
            movement_hash="hash-1",
            classification_status="CLASSIFIED",
            classification_method="SPECIAL_RULE",
            category_id=commission_category.id,
        ),
        make_movement(
            movement_date=dt.date(2026, 7, 2),
            description_original="VENTAS DEBITO TERMINALES",
            normalized_text="VENTAS DEBITO TERMINALES",
            payment_cents=395300,
            movement_hash="hash-2",
            branch_id=branch_alfredo.id,
            classification_status="CLASSIFIED",
            classification_method="BRANCH_IDENTIFIER",
        ),
        make_movement(
            bank_account_id=mifel.id,
            movement_date=dt.date(2026, 7, 3),
            description_original="MOVIMIENTO DESCONOCIDO",
            normalized_text="MOVIMIENTO DESCONOCIDO",
            charge_cents=5000,
            movement_hash="hash-3",
        ),
    ]
    db_session.add_all(movements)
    db_session.flush()

    return {
        "bbva": bbva,
        "mifel": mifel,
        "branch_alfredo": branch_alfredo,
        "commission_category": commission_category,
        "imported_file": imported_file,
    }


def test_query_paginated_without_filters_returns_all(db_session, catalogs):
    repo = MovementRepository(db_session)
    result = repo.query_paginated(MovementFilter(), page=1, page_size=50)

    assert result.total_items == 3
    assert len(result.items) == 3


def test_query_paginated_filters_by_bank_account(db_session, catalogs):
    repo = MovementRepository(db_session)
    filters = MovementFilter(bank_account_id=catalogs["bbva"].id)
    result = repo.query_paginated(filters, page=1, page_size=50)

    assert result.total_items == 2
    assert all(m.bank_account_id == catalogs["bbva"].id for m in result.items)


def test_query_paginated_filters_by_classification_status(db_session, catalogs):
    repo = MovementRepository(db_session)
    filters = MovementFilter(classification_status="UNCLASSIFIED")
    result = repo.query_paginated(filters, page=1, page_size=50)

    assert result.total_items == 1
    assert result.items[0].description_original == "MOVIMIENTO DESCONOCIDO"


def test_query_paginated_filters_by_movement_type(db_session, catalogs):
    repo = MovementRepository(db_session)
    charge_result = repo.query_paginated(
        MovementFilter(movement_type="CARGO"), page=1, page_size=50
    )
    payment_result = repo.query_paginated(
        MovementFilter(movement_type="ABONO"), page=1, page_size=50
    )

    assert charge_result.total_items == 2
    assert payment_result.total_items == 1


def test_query_paginated_filters_by_free_text(db_session, catalogs):
    repo = MovementRepository(db_session)
    result = repo.query_paginated(MovementFilter(free_text="ventas"), page=1, page_size=50)

    assert result.total_items == 1
    assert "VENTAS" in result.items[0].normalized_text


def test_query_paginated_filters_by_amount_range(db_session, catalogs):
    repo = MovementRepository(db_session)
    filters = MovementFilter(min_amount_cents=100000, max_amount_cents=500000)
    result = repo.query_paginated(filters, page=1, page_size=50)

    assert result.total_items == 1
    assert result.items[0].payment_cents == 395300


def test_query_paginated_filters_by_date_range(db_session, catalogs):
    repo = MovementRepository(db_session)
    filters = MovementFilter(date_from=dt.date(2026, 7, 2), date_to=dt.date(2026, 7, 2))
    result = repo.query_paginated(filters, page=1, page_size=50)

    assert result.total_items == 1
    assert result.items[0].movement_date == dt.date(2026, 7, 2)


def test_query_paginated_totals_reflect_full_filtered_set_not_just_page(db_session, catalogs):
    repo = MovementRepository(db_session)
    result = repo.query_paginated(MovementFilter(), page=1, page_size=1)

    assert len(result.items) == 1
    assert result.total_items == 3
    assert result.total_charge_cents == 20000
    assert result.total_payment_cents == 395300


def test_query_paginated_pagination_and_sorting(db_session, catalogs):
    repo = MovementRepository(db_session)
    page_1 = repo.query_paginated(
        MovementFilter(), page=1, page_size=1, sort_column="movement_date", sort_desc=True
    )
    page_2 = repo.query_paginated(
        MovementFilter(), page=2, page_size=1, sort_column="movement_date", sort_desc=True
    )

    assert page_1.items[0].movement_date == dt.date(2026, 7, 3)
    assert page_2.items[0].movement_date == dt.date(2026, 7, 2)


def test_count_all_and_count_unclassified(db_session, catalogs):
    repo = MovementRepository(db_session)
    assert repo.count_all() == 3
    assert repo.count_unclassified() == 1


def test_sum_totals_for_period(db_session, catalogs):
    repo = MovementRepository(db_session)
    charge_total, payment_total = repo.sum_totals_for_period(None, None)
    assert charge_total == 20000
    assert payment_total == 395300


def test_sum_charges_and_payments_by_day(db_session, catalogs):
    repo = MovementRepository(db_session)

    totals = repo.sum_charges_and_payments_by_day(None, None)

    assert totals == [
        (dt.date(2026, 7, 1), 15000, 0),
        (dt.date(2026, 7, 2), 0, 395300),
        (dt.date(2026, 7, 3), 5000, 0),
    ]


def test_sum_by_account(db_session, catalogs):
    repo = MovementRepository(db_session)
    totals = dict(repo.sum_by_account(None, None))
    assert totals["BBVA"] == 395300
    assert totals["MIFEL"] == 0
