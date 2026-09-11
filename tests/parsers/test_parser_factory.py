from pathlib import Path

import pytest

from app.parsers.bbva_txt_parser import BbvaTxtParser
from app.parsers.bbva_xlsx_parser import BbvaXlsxParser
from app.parsers.mifel_csv_parser import MifelCsvParser
from app.parsers.mifel_xlsx_parser import MifelXlsxParser
from app.parsers.parser_factory import UnsupportedParserError, get_parser_for_bank


@pytest.mark.parametrize(
    "bank_code,file_name,expected_cls",
    [
        ("BBVA", "extracto.txt", BbvaTxtParser),
        ("BBVA", "extracto.xlsx", BbvaXlsxParser),
        ("MIFEL", "extracto.csv", MifelCsvParser),
        # Antes de agregar MifelXlsxParser, un .xlsx de Mifel caía aquí
        # también y se intentaba leer como CSV (texto plano), lo que
        # reportaba "no se encontró encabezado" sin más explicación.
        ("MIFEL", "extracto.xlsx", MifelXlsxParser),
        ("mifel", "extracto.xlsx", MifelXlsxParser),  # sin distinguir mayúsculas
    ],
)
def test_get_parser_for_bank_routes_by_bank_and_extension(bank_code, file_name, expected_cls):
    parser = get_parser_for_bank(bank_code, Path(file_name))
    assert isinstance(parser, expected_cls)


def test_get_parser_for_bank_without_file_path_uses_bank_default():
    assert isinstance(get_parser_for_bank("MIFEL"), MifelCsvParser)


def test_get_parser_for_bank_unknown_bank_raises():
    with pytest.raises(UnsupportedParserError):
        get_parser_for_bank("SANTANDER", Path("extracto.csv"))


def test_get_parser_for_bank_unsupported_extension_raises():
    with pytest.raises(UnsupportedParserError):
        get_parser_for_bank("MIFEL", Path("extracto.pdf"))
