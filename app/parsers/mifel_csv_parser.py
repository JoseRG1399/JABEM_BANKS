"""Parser para archivos CSV de movimientos Mifel.

La tabla de movimientos puede no comenzar en la primera fila (el archivo
suele traer líneas informativas antes). El parser busca dinámicamente la
fila de encabezado y lee todos los campos como texto para no perder ceros a
la izquierda en folios y referencias.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from app.constants import FileType
from app.parsers.base_parser import BaseParser, decode_bytes
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


def _normalize_header_cell(cell: str) -> str:
    return strip_accents(cell).strip().upper()


def _find_header_row(lines: list[str]) -> int | None:
    for idx, line in enumerate(lines):
        upper = _normalize_header_cell(line)
        if all(keyword in upper for keyword in _HEADER_REQUIRED_KEYWORDS):
            return idx
    return None


def _map_columns(header_cells: list[str]) -> dict[str, int]:
    normalized = [_normalize_header_cell(cell) for cell in header_cells]
    mapping: dict[str, int] = {}
    for field_name, aliases in _COLUMN_ALIASES.items():
        for idx, cell in enumerate(normalized):
            if any(cell.startswith(alias) for alias in aliases):
                mapping[field_name] = idx
                break
    return mapping


def _get_cell(row: list[str], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index]


def _clean_reference(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped in ("", "-"):
        return None
    return stripped


class MifelCsvParser(BaseParser):
    file_type = FileType.CSV

    def parse(self, file_path: Path) -> ParseOutcome:
        text = decode_bytes(file_path.read_bytes())
        lines = text.splitlines()

        header_idx = _find_header_row(lines)
        rows: list[ParsedMovement] = []
        errors: list[ParseError] = []

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

        csv_text = "\n".join(lines[header_idx:])
        reader = csv.reader(io.StringIO(csv_text))
        header_cells = next(reader)
        columns = _map_columns(header_cells)

        required = ("date", "charge", "payment", "balance")
        missing = [name for name in required if name not in columns]
        if missing:
            errors.append(
                ParseError(
                    row_number=header_idx + 1,
                    raw_content=",".join(header_cells),
                    reason=f"Encabezado incompleto, faltan columnas: {', '.join(missing)}.",
                )
            )
            return ParseOutcome(rows=rows, errors=errors, total_rows_seen=0)

        for offset, raw_row in enumerate(reader, start=1):
            row_number = header_idx + 1 + offset
            if not raw_row or all(not cell.strip() for cell in raw_row):
                continue

            date_cell = _get_cell(raw_row, columns.get("date"))
            try:
                movement_date = parse_date(date_cell)
                if movement_date is None:
                    raise ValueError("La fecha está vacía.")
            except ValueError as exc:
                errors.append(
                    ParseError(row_number=row_number, raw_content=",".join(raw_row), reason=str(exc))
                )
                continue

            description = _get_cell(raw_row, columns.get("description")) or ""
            folio = _get_cell(raw_row, columns.get("folio"))
            reference = _get_cell(raw_row, columns.get("reference"))

            try:
                charge = parse_money(_get_cell(raw_row, columns.get("charge")))
                payment = parse_money(_get_cell(raw_row, columns.get("payment")))
                balance = parse_money(_get_cell(raw_row, columns.get("balance")))
            except ValueError as exc:
                errors.append(
                    ParseError(row_number=row_number, raw_content=",".join(raw_row), reason=str(exc))
                )
                continue

            rows.append(
                ParsedMovement(
                    row_number=row_number,
                    movement_date=movement_date,
                    description_original=description.strip(),
                    reference_original=_clean_reference(reference),
                    external_folio=_clean_reference(folio),
                    charge=charge,
                    payment=payment,
                    balance=balance,
                    raw_line=",".join(raw_row),
                )
            )

        total_rows_seen = len(rows) + len(errors)
        return ParseOutcome(rows=rows, errors=errors, total_rows_seen=total_rows_seen)
