import datetime as dt
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from app.parsers.mifel_xlsx_parser import MifelXlsxParser

# Encabezado real de un estado de cuenta Mifel exportado a Excel (mismas
# columnas que se ven en la captura reportada por el usuario), incluyendo
# columnas que el importador no usa (RFC, IVA, Cheque) y que debe ignorar.
SCREENSHOT_HEADER = [
    "Fecha",
    "Descripción",
    "Folio",
    "Referencia",
    "Cargo (MXN)",
    "Abono (MXN)",
    "Saldo total (MXN)",
    "RFC",
    "IVA(MXN)",
    "Cheque",
]


def _write_xlsx(tmp_path: Path, name: str, rows: list[list]) -> Path:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(row)
    path = tmp_path / name
    workbook.save(path)
    return path


@pytest.fixture()
def sample_file(tmp_path) -> Path:
    return _write_xlsx(
        tmp_path,
        "mifel_sample.xlsx",
        [
            SCREENSHOT_HEADER,
            [
                dt.date(2026, 9, 8),
                "o5pv996jd ganancias clip",
                "S15647974",
                "-",
                171.53,
                None,
                182366.97,
                "ND",
                0,
                "No aplica",
            ],
            [
                dt.date(2026, 9, 7),
                "Ubrpagosmexico",
                "S15481765",
                "-",
                None,
                409.58,
                182195.44,
                "ND",
                0,
                "No aplica",
            ],
        ],
    )


def test_parses_valid_xlsx_with_screenshot_headers(sample_file):
    outcome = MifelXlsxParser().parse(sample_file)

    assert len(outcome.errors) == 0
    assert len(outcome.rows) == 2

    first = outcome.rows[0]
    assert first.movement_date == dt.date(2026, 9, 8)
    assert first.description_original == "o5pv996jd ganancias clip"
    assert first.external_folio == "S15647974"
    assert first.reference_original is None  # "-" se interpreta como "sin referencia"
    assert first.charge == Decimal("171.53")
    assert first.payment is None
    assert first.balance == Decimal("182366.97")


def test_row_with_only_payment(sample_file):
    outcome = MifelXlsxParser().parse(sample_file)
    second = outcome.rows[1]
    assert second.charge is None
    assert second.payment == Decimal("409.58")


def test_extra_columns_rfc_iva_cheque_are_ignored(sample_file):
    # Si el parser rompiera por columnas de más, ni siquiera llegaríamos a
    # tener filas: basta con que las dos filas de arriba se hayan leído bien.
    outcome = MifelXlsxParser().parse(sample_file)
    assert len(outcome.rows) == 2


def test_blank_rows_are_skipped(tmp_path):
    path = _write_xlsx(
        tmp_path,
        "mifel_with_blank_row.xlsx",
        [
            SCREENSHOT_HEADER,
            [dt.date(2026, 9, 8), "Movimiento", "F1", "-", 100.0, None, 900.0, "ND", 0, "No aplica"],
            [None] * len(SCREENSHOT_HEADER),
        ],
    )
    outcome = MifelXlsxParser().parse(path)
    assert len(outcome.rows) == 1
    assert len(outcome.errors) == 0


def test_missing_header_reports_file_level_error(tmp_path):
    # Este es exactamente el caso reportado: un archivo cuyo encabezado no
    # coincide con lo esperado (o que no es realmente el tipo de archivo que
    # el parser sabe leer) debía reportarse como "0 filas" sin explicación.
    path = _write_xlsx(
        tmp_path,
        "sin_encabezado.xlsx",
        [["A", "B", "C"], [1, 2, 3]],
    )
    outcome = MifelXlsxParser().parse(path)

    assert outcome.rows == []
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 0
    assert "encabezado" in outcome.errors[0].reason.lower()


def test_invalid_date_row_is_reported_and_others_still_parsed(tmp_path):
    path = _write_xlsx(
        tmp_path,
        "mifel_invalid_row.xlsx",
        [
            SCREENSHOT_HEADER,
            [None, "Sin fecha", "F1", "-", 50.0, None, 500.0, "ND", 0, "No aplica"],
            [dt.date(2026, 9, 9), "Con fecha", "F2", "-", None, 75.0, 575.0, "ND", 0, "No aplica"],
        ],
    )
    outcome = MifelXlsxParser().parse(path)

    assert len(outcome.rows) == 1
    assert len(outcome.errors) == 1
    assert "fecha" in outcome.errors[0].reason.lower()
