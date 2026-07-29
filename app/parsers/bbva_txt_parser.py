"""Parser para archivos TXT de movimientos BBVA.

El archivo no se separa con un ``split()`` simple: el encabezado se usa para
localizar dinámicamente las columnas de Cargo, Abono y Saldo, y cada fila se
interpreta primero extrayendo la fecha al inicio y luego los importes,
clasificándolos según la columna a la que están más próximos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.constants import FileType
from app.parsers.base_parser import BaseParser, decode_bytes
from app.schemas.parsed_movement import ParseError, ParsedMovement, ParseOutcome
from app.utils.dates import parse_date
from app.utils.money import parse_money

_DATE_START_RE = re.compile(r"^(?P<date>\d{2}[-/]\d{2}[-/]\d{4})\s+(?P<rest>.*)$")
_MONEY_TOKEN_RE = re.compile(r"-?\$?\d{1,3}(?:,\d{3})*\.\d{2}")


@dataclass
class _ColumnLayout:
    charge_start: int
    payment_start: int
    balance_start: int

    def classify(self, token_start: int) -> str:
        distances = {
            "charge": abs(token_start - self.charge_start),
            "payment": abs(token_start - self.payment_start),
            "balance": abs(token_start - self.balance_start),
        }
        return min(distances, key=distances.get)


def _find_header_layout(lines: list[str]) -> tuple[int, _ColumnLayout] | None:
    for idx, line in enumerate(lines):
        upper = line.upper()
        if "CARGO" in upper and "ABONO" in upper and "SALDO" in upper:
            charge_start = upper.find("CARGO")
            payment_start = upper.find("ABONO")
            balance_start = upper.find("SALDO")
            if -1 in (charge_start, payment_start, balance_start):
                continue
            return idx, _ColumnLayout(charge_start, payment_start, balance_start)
    return None


class BbvaTxtParser(BaseParser):
    file_type = FileType.TXT

    def parse(self, file_path: Path) -> ParseOutcome:
        text = decode_bytes(file_path.read_bytes())
        lines = text.splitlines()

        header = _find_header_layout(lines)
        rows: list[ParsedMovement] = []
        errors: list[ParseError] = []

        if header is None:
            errors.append(
                ParseError(
                    row_number=0,
                    raw_content="",
                    reason=(
                        "No se encontró una fila de encabezado con columnas "
                        "Cargo/Abono/Saldo."
                    ),
                )
            )
            return ParseOutcome(rows=rows, errors=errors, total_rows_seen=0)

        header_idx, layout = header

        for row_number, line in enumerate(lines[header_idx + 1 :], start=header_idx + 2):
            stripped = line.strip()
            if not stripped:
                continue

            match = _DATE_START_RE.match(stripped)
            if not match:
                errors.append(
                    ParseError(
                        row_number=row_number,
                        raw_content=line,
                        reason="No se pudo identificar la fecha al inicio de la fila.",
                    )
                )
                continue

            try:
                movement_date = parse_date(match.group("date"))
            except ValueError as exc:
                errors.append(
                    ParseError(row_number=row_number, raw_content=line, reason=str(exc))
                )
                continue

            rest = match.group("rest")
            money_matches = list(_MONEY_TOKEN_RE.finditer(rest))

            if not money_matches:
                errors.append(
                    ParseError(
                        row_number=row_number,
                        raw_content=line,
                        reason="No se encontraron importes (cargo/abono/saldo) en la fila.",
                    )
                )
                continue

            offset = match.start("rest")
            charge = payment = balance = None
            concept_end = money_matches[0].start()

            for token_match in money_matches:
                column = layout.classify(token_match.start() + offset)
                value = parse_money(token_match.group())
                if column == "charge":
                    charge = value
                elif column == "payment":
                    payment = value
                else:
                    balance = value

            concept = rest[:concept_end].strip()
            if not concept:
                errors.append(
                    ParseError(
                        row_number=row_number,
                        raw_content=line,
                        reason="La fila no contiene concepto/referencia.",
                    )
                )
                continue

            rows.append(
                ParsedMovement(
                    row_number=row_number,
                    movement_date=movement_date,
                    description_original=concept,
                    reference_original=None,
                    external_folio=None,
                    charge=charge,
                    payment=payment,
                    balance=balance,
                    raw_line=line,
                )
            )

        total_rows_seen = len(rows) + len(errors)
        return ParseOutcome(rows=rows, errors=errors, total_rows_seen=total_rows_seen)
