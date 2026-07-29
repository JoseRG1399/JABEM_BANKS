"""Fábrica que selecciona el parser adecuado según el banco.

Agregar soporte para un banco nuevo no requiere modificar los parsers
existentes: basta con registrar la clase correspondiente aquí (o mediante
``register_parser``) sin tocar el resto del código.
"""
from __future__ import annotations

from pathlib import Path

from app.constants import FileType
from app.parsers.base_parser import BaseParser
from app.parsers.bbva_txt_parser import BbvaTxtParser
from app.parsers.mifel_csv_parser import MifelCsvParser

_PARSERS_BY_BANK_CODE: dict[str, type[BaseParser]] = {
    "BBVA": BbvaTxtParser,
    "MIFEL": MifelCsvParser,
}

_EXTENSION_TO_FILE_TYPE: dict[str, FileType] = {
    ".txt": FileType.TXT,
    ".csv": FileType.CSV,
}


class UnsupportedParserError(Exception):
    pass


def detect_file_type(file_path: Path) -> FileType:
    extension = file_path.suffix.lower()
    if extension not in _EXTENSION_TO_FILE_TYPE:
        raise UnsupportedParserError(f"Extensión de archivo no soportada: {extension}")
    return _EXTENSION_TO_FILE_TYPE[extension]


def get_parser_for_bank(bank_code: str) -> BaseParser:
    parser_cls = _PARSERS_BY_BANK_CODE.get(bank_code.upper())
    if parser_cls is None:
        raise UnsupportedParserError(
            f"No existe un parser configurado para el banco: {bank_code}"
        )
    return parser_cls()


def register_parser(bank_code: str, parser_cls: type[BaseParser]) -> None:
    _PARSERS_BY_BANK_CODE[bank_code.upper()] = parser_cls
