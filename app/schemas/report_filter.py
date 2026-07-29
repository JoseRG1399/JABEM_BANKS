"""Filtros compartidos por los reportes (sección 15.8 de la especificación)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass
class ReportFilter:
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    bank_id: int | None = None
    bank_account_id: int | None = None
    branch_id: int | None = None
    category_id: int | None = None
