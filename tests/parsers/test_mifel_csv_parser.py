import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.parsers.mifel_csv_parser import MifelCsvParser

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_parses_valid_csv_with_leading_informational_lines():
    outcome = MifelCsvParser().parse(FIXTURES / "mifel_sample.csv")

    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 3

    first = outcome.rows[0]
    assert first.movement_date == dt.date(2026, 7, 1)
    assert first.description_original == "Iva al 16.00%"
    assert first.charge == Decimal("0.30")
    assert first.payment is None
    assert first.balance == Decimal("756758.65")
    assert first.external_folio == "SMG573604"
    assert first.reference_original is None


def test_reference_with_leading_zero_is_preserved():
    outcome = MifelCsvParser().parse(FIXTURES / "mifel_sample.csv")
    second = outcome.rows[1]
    assert second.reference_original == "0613"


def test_row_with_only_payment():
    outcome = MifelCsvParser().parse(FIXTURES / "mifel_sample.csv")
    third = outcome.rows[2]
    assert third.charge is None
    assert third.payment == Decimal("5000.00")


def test_utf8_bom_encoding():
    outcome = MifelCsvParser().parse(FIXTURES / "mifel_utf8_bom.csv")
    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 2
    assert outcome.rows[0].description_original == "Iva al 16.00%"


def test_cp1252_encoding():
    outcome = MifelCsvParser().parse(FIXTURES / "mifel_cp1252.csv")
    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 2
    assert outcome.rows[1].description_original == "Comisión por manejo de cuenta"


def test_invalid_row_does_not_stop_import():
    outcome = MifelCsvParser().parse(FIXTURES / "mifel_invalid_row.csv")

    assert len(outcome.rows) == 2
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 3


def test_missing_header_reports_file_level_error(tmp_path):
    bad_file = tmp_path / "no_header.csv"
    bad_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

    outcome = MifelCsvParser().parse(bad_file)

    assert outcome.rows == []
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 0
