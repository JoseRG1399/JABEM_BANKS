"""Normalización de texto para conceptos y referencias bancarias."""
from __future__ import annotations

import re
import unicodedata

_SYMBOLS_RE = re.compile(r"[^A-Z0-9\s]")
_MULTISPACE_RE = re.compile(r"\s+")
_DIGIT_BLOCK_RE = re.compile(r"\d+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(text: str | None) -> str:
    """Normaliza un texto para comparación y clasificación.

    - Convierte a mayúsculas.
    - Elimina acentos.
    - Sustituye signos de puntuación por espacios (preserva letras y números).
    - Reduce espacios repetidos a uno solo.
    - Recorta espacios al inicio/fin.
    """
    if not text:
        return ""
    upper = strip_accents(text).upper()
    without_symbols = _SYMBOLS_RE.sub(" ", upper)
    collapsed = _MULTISPACE_RE.sub(" ", without_symbols)
    return collapsed.strip()


def normalize_compact(text: str | None) -> str:
    """Variante sin espacios, útil para búsquedas de terminación."""
    return normalize_text(text).replace(" ", "")


def extract_digit_blocks(text: str | None) -> list[str]:
    """Devuelve todas las secuencias numéricas contenidas en el texto."""
    if not text:
        return []
    return _DIGIT_BLOCK_RE.findall(text)


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


def sanitize_for_spreadsheet(value: str) -> str:
    """Evita inyección de fórmulas al exportar a Excel/CSV.

    Antepone un apóstrofo cuando el valor comienza con un carácter que Excel
    interpretaría como el inicio de una fórmula (=, +, -, @).
    """
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return f"'{value}"
    return value
