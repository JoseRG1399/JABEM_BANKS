"""Parser para archivos XLSX de movimientos BBVA.

Espera la misma estructura que el TXT (Dia, Concepto / Referencia, Cargo,
Abono[, Saldo]) pero como hoja de cálculo: cada importe se lee directamente
de la celda de su columna según el encabezado, en vez de inferirse por la
posición del texto como en ``BbvaTxtParser``. Esto evita que Cargo/Abono se
pierdan cuando el TXT no alinea las columnas de forma exacta. La columna
Saldo es opcional y, si existe, no se usa para la importación.
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

_REQUIRED_FIELDS = ("date", "description", "charge", "payment")

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("DIA", "FECHA"),
    "description": ("CONCEPTO",),
    "charge": ("CARGO",),
    "payment": ("ABONO",),
}


def _normalize_header_cell(value: object) -> str:
    if value is None:
        return ""
    return strip_accents(str(value)).strip().upper()


def _find_header_row(rows: list[tuple]) -> int | None:
    for idx, row in enumerate(rows):
        normalized_cells = [_normalize_header_cell(cell) for cell in row]
        has_date = any(cell.startswith(("DIA", "FECHA")) for cell in normalized_cells)
        has_concepto = any(cell.startswith("CONCEPTO") for cell in normalized_cells)
        has_cargo = any(cell.startswith("CARGO") for cell in normalized_cells)
        has_abono = any(cell.startswith("ABONO") for cell in normalized_cells)
        if has_date and has_concepto and has_cargo and has_abono:
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


class BbvaXlsxParser(BaseParser):
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
                        "Dia/Concepto/Cargo/Abono."
                    ),
                )
            )
            return ParseOutcome(rows=rows, errors=errors, total_rows_seen=0)

        columns = _map_columns(raw_rows[header_idx])
        missing = [name for name in _REQUIRED_FIELDS if name not in columns]
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
            if not description:
                errors.append(
                    ParseError(
                        row_number=row_number,
                        raw_content=str(raw_row),
                        reason="La fila no contiene concepto/referencia.",
                    )
                )
                continue

            try:
                charge = parse_money(_get_cell(raw_row, columns.get("charge")))
                payment = parse_money(_get_cell(raw_row, columns.get("payment")))
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
                    reference_original=None,
                    external_folio=None,
                    charge=charge,
                    payment=payment,
                    balance=None,
                    raw_line=str(raw_row),
                )
            )

        total_rows_seen = len(rows) + len(errors)
        return ParseOutcome(rows=rows, errors=errors, total_rows_seen=total_rows_seen)
