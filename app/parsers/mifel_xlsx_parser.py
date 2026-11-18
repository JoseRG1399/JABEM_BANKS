"""Parser para archivos XLSX de movimientos Mifel.

Espera la misma estructura que el CSV (Fecha, Descripción/Concepto, Folio,
Referencia, Cargo, Abono, Saldo) pero como hoja de cálculo: cada importe se
lee directamente de la celda de su columna según el encabezado, en vez de
interpretarse como texto delimitado por comas. Las columnas adicionales que
trae el estado de cuenta (RFC, IVA, Cheque) se ignoran: no forman parte de
los datos que necesita la importación.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from app.constants import FileType
from app.parsers.base_parser import BaseParser
from app.schemas.parsed_movement import ParseError, ParsedMovement, ParseOutcome
from app.utils.dates import parse_date
from app.utils.money import parse_money
from app.utils.text import strip_accents

_HEADER_REQUIRED_KEYWORDS = ("FECHA", "CARGO", "ABONO", "SALDO")

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("FECHA",),
    "description": ("DESCRIPCION", "CONCEPTO"),
    "folio": ("FOLIO",),
    "reference": ("REFERENCIA",),
    "charge": ("CARGO",),
    "payment": ("ABONO",),
    "balance": ("SALDO",),
}


def _normalize_header_cell(value: object) -> str:
    if value is None:
        return ""
    return strip_accents(str(value)).strip().upper()


def _find_header_row(rows: list[tuple]) -> int | None:
    for idx, row in enumerate(rows):
        normalized_cells = [_normalize_header_cell(cell) for cell in row]
        has_all_keywords = all(
            any(cell.startswith(keyword) for cell in normalized_cells)
            for keyword in _HEADER_REQUIRED_KEYWORDS
        )
        if has_all_keywords:
            return idx
    return None


def _map_columns(header_row: tuple) -> dict[str, int]:
    normalized = [_normalize_header_cell(cell) for cell in header_row]
    mapping: dict[str, int] = {}
    for field_name, aliases in _COLUMN_ALIASES.items():
        for idx, cell in enumerate(normalized):
            if any(cell.startswith(alias) for alias in aliases):
                mapping[field_name] = idx
                break
    return mapping


def _get_cell(row: tuple, index: int | None) -> object:
    if index is None or index >= len(row):
        return None
    return row[index]


def _is_blank_row(row: tuple) -> bool:
    return all(cell is None or (isinstance(cell, str) and not cell.strip()) for cell in row)


def _clean_reference(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    if stripped in ("", "-"):
        return None
    return stripped


class MifelXlsxParser(BaseParser):
    file_type = FileType.XLSX

    def parse(self, file_path: Path) -> ParseOutcome:
        rows: list[ParsedMovement] = []
        errors: list[ParseError] = []

        workbook = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        try:
            worksheet = workbook.active
            raw_rows = list(worksheet.iter_rows(values_only=True))
        finally:
            workbook.close()

        header_idx = _find_header_row(raw_rows)
        if header_idx is None:
            errors.append(
                ParseError(
                    row_number=0,
                    raw_content="",
                    reason=(
                        "No se encontró una fila de encabezado con columnas "
                        "Fecha/Cargo/Abono/Saldo."
                    ),
                )
            )
            return ParseOutcome(rows=rows, errors=errors, total_rows_seen=0)

        columns = _map_columns(raw_rows[header_idx])
        required = ("date", "charge", "payment", "balance")
        missing = [name for name in required if name not in columns]
        if missing:
            errors.append(
                ParseError(
                    row_number=header_idx + 1,
                    raw_content=str(raw_rows[header_idx]),
                    reason=f"Encabezado incompleto, faltan columnas: {', '.join(missing)}.",
                )
            )
            return ParseOutcome(rows=rows, errors=errors, total_rows_seen=0)

        for offset, raw_row in enumerate(raw_rows[header_idx + 1 :], start=1):
            row_number = header_idx + 1 + offset
            if not raw_row or _is_blank_row(raw_row):
                continue

            date_cell = _get_cell(raw_row, columns.get("date"))
            try:
                movement_date = parse_date(date_cell)
                if movement_date is None:
                    raise ValueError("La fecha está vacía.")
            except ValueError as exc:
                errors.append(
                    ParseError(row_number=row_number, raw_content=str(raw_row), reason=str(exc))
                )
                continue

            description_cell = _get_cell(raw_row, columns.get("description"))
            description = str(description_cell).strip() if description_cell is not None else ""

            folio = _clean_reference(_get_cell(raw_row, columns.get("folio")))
            reference = _clean_reference(_get_cell(raw_row, columns.get("reference")))

            try:
                charge = parse_money(_get_cell(raw_row, columns.get("charge")))
                payment = parse_money(_get_cell(raw_row, columns.get("payment")))
                balance = parse_money(_get_cell(raw_row, columns.get("balance")))
            except ValueError as exc:
                errors.append(
                    ParseError(row_number=row_number, raw_content=str(raw_row), reason=str(exc))
                )
                continue

            rows.append(
                ParsedMovement(
                    row_number=row_number,
                    movement_date=movement_date,
                    description_original=description,
                    reference_original=reference,
                    external_folio=folio,
                    charge=charge,
                    payment=payment,
                    balance=balance,
                    raw_line=str(raw_row),
                )
            )

        total_rows_seen = len(rows) + len(errors)
        return ParseOutcome(rows=rows, errors=errors, total_rows_seen=total_rows_seen)
