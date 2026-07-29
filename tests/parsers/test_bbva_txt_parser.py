import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.parsers.bbva_txt_parser import BbvaTxtParser

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_parses_valid_file_with_charge_and_payment_rows():
    outcome = BbvaTxtParser().parse(FIXTURES / "bbva_sample.txt")

    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 5

    first = outcome.rows[0]
    assert first.movement_date == dt.date(2026, 7, 1)
    assert "IVA TASA DE DESC DEBITO" in first.description_original
    assert first.charge == Decimal("14.22")
    assert first.payment is None
    assert first.balance == Decimal("467336.94")


def test_parses_row_with_only_payment():
    outcome = BbvaTxtParser().parse(FIXTURES / "bbva_sample.txt")
    payment_row = outcome.rows[2]

    assert payment_row.charge is None
    assert payment_row.payment == Decimal("3953.00")
    assert payment_row.balance == Decimal("467440.04")


def test_parses_row_with_saldo():
    outcome = BbvaTxtParser().parse(FIXTURES / "bbva_sample.txt")
    assert all(row.balance is not None for row in outcome.rows)


def test_variable_spacing_and_invalid_row_does_not_stop_import():
    outcome = BbvaTxtParser().parse(FIXTURES / "bbva_variable_spacing.txt")

    assert len(outcome.rows) == 2
    assert len(outcome.errors) == 1
    assert outcome.errors[0].reason
    assert "FILA INVALIDA" in outcome.errors[0].raw_content


def test_invalid_date_row_is_reported_and_others_still_parsed():
    outcome = BbvaTxtParser().parse(FIXTURES / "bbva_invalid_row.txt")

    assert len(outcome.rows) == 1
    assert len(outcome.errors) == 1
    assert "fecha" in outcome.errors[0].reason.lower()


def test_missing_header_reports_file_level_error(tmp_path):
    bad_file = tmp_path / "no_header.txt"
    bad_file.write_text("01-07-2026  ALGO SIN ENCABEZADO   14.22   100.00\n", encoding="utf-8")

    outcome = BbvaTxtParser().parse(bad_file)

    assert outcome.rows == []
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 0
