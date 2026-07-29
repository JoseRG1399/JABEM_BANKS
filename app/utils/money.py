"""Utilidades para el manejo seguro de importes monetarios.

Los importes se parsean como ``Decimal`` y se persisten como enteros en
centavos para evitar los errores de precisión propios de ``float``.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_MONEY_CLEAN_RE = re.compile(r"[^0-9.,\-]")
_EMPTY_TOKENS = {"", "-", "--", "n/a", "na"}


def parse_money(raw: str | float | int | Decimal | None) -> Decimal | None:
    """Convierte un valor crudo (texto u otro) a ``Decimal``.

    Soporta:
        "$3,953.00", "3,953.00", "3953.00", "-", "", None
    Devuelve ``None`` cuando el valor representa "sin importe" (vacío o "-").
    """
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))

    text = str(raw).strip()
    if text.lower() in _EMPTY_TOKENS:
        return None

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    cleaned = _MONEY_CLEAN_RE.sub("", text).replace(",", "")
    if cleaned in ("", "-", "."):
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Importe inválido: {raw!r}") from exc

    return -value if negative else value


def money_to_cents(value: Decimal | str | float | int | None) -> int:
    """Convierte un importe a centavos enteros. Un valor vacío equivale a 0."""
    decimal_value = value if isinstance(value, Decimal) else parse_money(value)
    if decimal_value is None:
        return 0
    cents = (decimal_value * 100).to_integral_value(rounding="ROUND_HALF_UP")
    return int(cents)


def cents_to_decimal(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


def format_currency(cents: int, currency_symbol: str = "$") -> str:
    """Formatea centavos como moneda legible: 395300 -> '$3,953.00'."""
    value = cents_to_decimal(cents)
    negative = value < 0
    formatted = f"{abs(value):,.2f}"
    sign = "-" if negative else ""
    return f"{sign}{currency_symbol}{formatted}"
