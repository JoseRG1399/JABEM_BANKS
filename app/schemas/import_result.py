"""Resultado consolidado de una importación de archivo, listo para mostrarse
en la UI (Fase 4) y para exportar los errores de fila a CSV.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.constants import ImportedFileStatus
from app.schemas.parsed_movement import ParseError


@dataclass
class ImportResult:
    imported_file_id: int
    original_file_name: str
    bank_name: str
    account_alias: str
    total_rows: int
    inserted_rows: int
    duplicate_rows: int
    invalid_rows: int
    unclassified_rows: int
    status: ImportedFileStatus
    row_errors: list[ParseError] = field(default_factory=list)

    @property
    def has_row_errors(self) -> bool:
        return bool(self.row_errors)
