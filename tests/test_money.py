from decimal import Decimal

import pytest

from app.utils.money import cents_to_decimal, format_currency, money_to_cents, parse_money


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$3,953.00", Decimal("3953.00")),
        ("3,953.00", Decimal("3953.00")),
        ("3953.00", Decimal("3953.00")),
        ("14.22", Decimal("14.22")),
        ("-", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


def test_parse_money_invalid_raises():
    with pytest.raises(ValueError):
        parse_money("no-es-un-numero")


@pytest.mark.parametrize(
    "raw,expected_cents",
    [
        ("$3,953.00", 395300),
        ("14.22", 1422),
        ("-", 0),
        ("", 0),
        (None, 0),
    ],
)
def test_money_to_cents(raw, expected_cents):
    assert money_to_cents(raw) == expected_cents


def test_cents_to_decimal_roundtrip():
    assert cents_to_decimal(395300) == Decimal("3953.00")


def test_format_currency():
    assert format_currency(395300) == "$3,953.00"
    assert format_currency(0) == "$0.00"
    assert format_currency(-150) == "-$1.50"
