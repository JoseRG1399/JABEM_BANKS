import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.parsers.bbva_xlsx_parser import BbvaXlsxParser

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_parses_valid_xlsx_with_charge_and_payment_rows():
    outcome = BbvaXlsxParser().parse(FIXTURES / "bbva_sample.xlsx")

    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 5

    first = outcome.rows[0]
    assert first.movement_date == dt.date(2026, 7, 1)
    assert "IVA TASA DE DESC DEBITO" in first.description_original
    assert first.charge == Decimal("14.22")
    assert first.payment is None


def test_parses_row_with_only_payment():
    outcome = BbvaXlsxParser().parse(FIXTURES / "bbva_sample.xlsx")
    payment_row = outcome.rows[2]

    assert payment_row.charge is None
    assert payment_row.payment == Decimal("3953.00")


def test_saldo_column_is_ignored_when_present():
    outcome = BbvaXlsxParser().parse(FIXTURES / "bbva_sample.xlsx")
    assert all(row.balance is None for row in outcome.rows)


def test_parses_file_without_saldo_column():
    outcome = BbvaXlsxParser().parse(FIXTURES / "bbva_sample_no_saldo.xlsx")

    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 2
    assert outcome.rows[0].charge == Decimal("14.22")
    assert outcome.rows[1].payment == Decimal("3953.00")


def test_invalid_date_row_is_reported_and_others_still_parsed():
    outcome = BbvaXlsxParser().parse(FIXTURES / "bbva_invalid_row.xlsx")

    assert len(outcome.rows) == 1
    assert len(outcome.errors) == 1
    assert "fecha" in outcome.errors[0].reason.lower()


def test_missing_header_reports_file_level_error():
    outcome = BbvaXlsxParser().parse(FIXTURES / "bbva_no_header.xlsx")

    assert outcome.rows == []
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 0
