"""Estructuras intermedias producidas por los parsers, antes de persistir."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ParsedMovement:
    row_number: int
    movement_date: dt.date
    description_original: str
    reference_original: str | None
    external_folio: str | None
    charge: Decimal | None
    payment: Decimal | None
    balance: Decimal | None
    raw_line: str = ""


@dataclass
class ParseError:
    row_number: int
    raw_content: str
    reason: str


@dataclass
class ParseOutcome:
    rows: list[ParsedMovement] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    total_rows_seen: int = 0
