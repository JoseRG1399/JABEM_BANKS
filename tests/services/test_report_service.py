import datetime as dt

import pytest

from app.database.seed import seed_catalogs
from app.models import BankAccount, Branch, ImportedFile, Movement, MovementCategory
from app.schemas.report_filter import ReportFilter
from app.services import report_service
from app.services.report_service import ReportValueType


@pytest.fixture()
def scenario(db_session):
    seed_catalogs(db_session)
    bbva = db_session.query(BankAccount).filter_by(alias="BBVA").one()
    mifel = db_session.query(BankAccount).filter_by(alias="MIFEL").one()
    branch_alfredo = db_session.query(Branch).filter_by(branch_number="01").one()
    branch_colon = db_session.query(Branch).filter_by(branch_number="02").one()
    commission_category = db_session.query(MovementCategory).filter_by(code="COMMISSION").one()
    commission_vat_category = (
        db_session.query(MovementCategory).filter_by(code="COMMISSION_VAT").one()
    )
    branch_category = db_session.query(MovementCategory).filter_by(code="BRANCH").one()
    unclassified_category = (
        db_session.query(MovementCategory).filter_by(code="UNCLASSIFIED").one()
    )

    imported_file = ImportedFile(
        bank_account_id=bbva.id,
        original_name="extracto.txt",
        stored_name="extracto.txt",
        original_path="C:/tmp/extracto.txt",
        file_type="TXT",
        file_hash="hash-report-test",
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
            movement_hash="hash",
            occurrence_number=1,
            classification_status="UNCLASSIFIED",
            classification_method="NONE",
            source_row_number=1,
        )
        defaults.update(overrides)
        return Movement(**defaults)

    movements = [
        # 01/07: sucursal Alfredo (BBVA), sucursal Colon (MIFEL)
        make_movement(
            movement_date=dt.date(2026, 7, 1),
            bank_account_id=bbva.id,
            branch_id=branch_alfredo.id,
            category_id=branch_category.id,
            payment_cents=100000,
            movement_hash="h1",
            classification_status="CLASSIFIED",
        ),
        make_movement(
            movement_date=dt.date(2026, 7, 1),
            bank_account_id=mifel.id,
            branch_id=branch_colon.id,
            category_id=branch_category.id,
            payment_cents=50000,
            movement_hash="h2",
            classification_status="CLASSIFIED",
        ),
        # 02/07: sucursal Alfredo otra vez (BBVA)
        make_movement(
            movement_date=dt.date(2026, 7, 2),
            bank_account_id=bbva.id,
            branch_id=branch_alfredo.id,
            category_id=branch_category.id,
            payment_cents=20000,
            movement_hash="h3",
            classification_status="CLASSIFIED",
        ),
        # comisiones e IVA (BBVA, sin sucursal)
        make_movement(
            movement_date=dt.date(2026, 7, 1),
            bank_account_id=bbva.id,
            category_id=commission_category.id,
            charge_cents=15000,
            movement_hash="h4",
            classification_status="CLASSIFIED",
        ),
        make_movement(
            movement_date=dt.date(2026, 7, 1),
            bank_account_id=bbva.id,
            category_id=commission_vat_category.id,
            charge_cents=2400,
            movement_hash="h5",
            classification_status="CLASSIFIED",
        ),
        # sin clasificar
        make_movement(
            movement_date=dt.date(2026, 7, 3),
            bank_account_id=mifel.id,
            charge_cents=5000,
            movement_hash="h6",
            classification_status="UNCLASSIFIED",
        ),
    ]
    db_session.add_all(movements)
    db_session.flush()

    return {
        "bbva": bbva,
        "mifel": mifel,
        "branch_alfredo": branch_alfredo,
        "branch_colon": branch_colon,
    }


def test_totals_by_day(db_session, scenario):
    rows = report_service.totals_by_day(db_session, ReportFilter())
    totals = {row.label: row.payment_cents for row in rows}
    assert totals["01/07/2026"] == 150000
    assert totals["02/07/2026"] == 20000


def test_totals_by_bank(db_session, scenario):
    rows = report_service.totals_by_bank(db_session, ReportFilter())
    totals = {row.label: row.payment_cents for row in rows}
    assert totals["BBVA"] == 120000
    assert totals["Mifel"] == 50000


def test_totals_by_account(db_session, scenario):
    rows = report_service.totals_by_account(db_session, ReportFilter())
    totals = {row.label: row.payment_cents for row in rows}
    assert totals["BBVA"] == 120000
    assert totals["MIFEL"] == 50000


def test_totals_by_branch(db_session, scenario):
    rows = report_service.totals_by_branch(db_session, ReportFilter())
    totals = {row.label: row.payment_cents for row in rows}
    assert totals["01. ALFREDO"] == 120000
    assert totals["02. COLON"] == 50000


def test_totals_by_category(db_session, scenario):
    rows = report_service.totals_by_category(db_session, ReportFilter())
    by_label = {row.label: row for row in rows}
    assert by_label["Sucursal"].payment_cents == 170000
    assert by_label["Comisiones"].charge_cents == 15000
    assert by_label["IVA comisiones"].charge_cents == 2400


def test_unclassified_movements(db_session, scenario):
    movements = report_service.unclassified_movements(db_session, ReportFilter())
    assert len(movements) == 1
    assert movements[0].movement_hash == "h6"


def test_commissions_and_vat(db_session, scenario):
    rows = report_service.commissions_and_vat(db_session, ReportFilter())
    totals = {row.label: row.charge_cents for row in rows}
    assert totals["Comisiones"] == 15000
    assert totals["IVA comisiones"] == 2400
    assert len(rows) == 2


def test_report_filters_by_date_range(db_session, scenario):
    filters = ReportFilter(date_from=dt.date(2026, 7, 2), date_to=dt.date(2026, 7, 2))
    rows = report_service.totals_by_day(db_session, filters)
    assert len(rows) == 1
    assert rows[0].label == "02/07/2026"


def test_consolidated_report_structure(db_session, scenario):
    report = report_service.consolidated_by_date_branch_account(db_session, ReportFilter())

    assert set(report.account_aliases) == {"BBVA", "MIFEL"}
    assert len(report.day_groups) == 2

    day1 = next(g for g in report.day_groups if g.day == dt.date(2026, 7, 1))
    assert day1.total_cents == 150000
    assert day1.values_by_account["BBVA"] == 100000
    assert day1.values_by_account["MIFEL"] == 50000
    assert len(day1.branch_rows) == 2

    day2 = next(g for g in report.day_groups if g.day == dt.date(2026, 7, 2))
    assert day2.total_cents == 20000

    assert report.grand_total_cents == 170000
    assert report.grand_totals_by_account["BBVA"] == 120000
    assert report.grand_totals_by_account["MIFEL"] == 50000


def test_consolidated_report_value_type_charge(db_session, scenario):
    report = report_service.consolidated_by_date_branch_account(
        db_session, ReportFilter(), value_type=ReportValueType.CHARGE
    )
    # Los movimientos de sucursal en el escenario son todos abonos; en modo
    # cargo el total consolidado debe ser cero.
    assert report.grand_total_cents == 0


def test_consolidated_report_excludes_movements_without_branch(db_session, scenario):
    report = report_service.consolidated_by_date_branch_account(db_session, ReportFilter())
    total_branch_rows = sum(len(g.branch_rows) for g in report.day_groups)
    # Solo 3 movimientos del escenario tienen sucursal asignada.
    assert total_branch_rows == 3
