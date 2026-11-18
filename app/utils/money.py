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


DIRECT_DEBIT_VAT_RATE = Decimal("0.16")


def split_charge_into_base_and_vat(total_cents: int) -> tuple[int, int]:
    """Separa un cargo que ya incluye IVA (16%) en su base y su IVA.

    Se usa para domiciliaciones que el banco reporta como un solo cargo que
    en realidad junta un importe base y su IVA (p. ej. $68.44 = $59.00 de
    base + $9.44 de IVA).

    Devuelve ``(base_cents, vat_cents)``. El IVA se calcula como el residuo
    (``total_cents - base_cents``) en vez de redondear ambos por separado,
    para garantizar que ``base_cents + vat_cents == total_cents`` siempre,
    sin perder ni agregar centavos por redondeo.
    """
    if not total_cents:
        return 0, 0
    base_cents = int(
        (Decimal(total_cents) / (Decimal("1") + DIRECT_DEBIT_VAT_RATE)).to_integral_value(
            rounding="ROUND_HALF_UP"
        )
    )
    vat_cents = total_cents - base_cents
    return base_cents, vat_cents


def invert_charge_to_negative_payment(charge_cents: int, payment_cents: int) -> tuple[int, int]:
    """Convierte un cargo en un abono negativo neto (para movimientos como
    "Dev. deb nac ..." que en realidad son devoluciones y deben descontarse
    del total de abonos en vez de sumarse a los cargos).

    Devuelve ``(charge_cents, payment_cents)`` ya ajustados: el cargo pasa a
    cero y el abono absorbe la diferencia (``payment_cents - charge_cents``).
    Si no hay cargo, los valores se devuelven sin cambios.
    """
    if not charge_cents:
        return charge_cents, payment_cents
    return 0, payment_cents - charge_cents


def format_currency(cents: int, currency_symbol: str = "$") -> str:
    """Formatea centavos como moneda legible: 395300 -> '$3,953.00'."""
    value = cents_to_decimal(cents)
    negative = value < 0
    formatted = f"{abs(value):,.2f}"
    sign = "-" if negative else ""
    return f"{sign}{currency_symbol}{formatted}"
