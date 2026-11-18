from decimal import Decimal

import pytest

from app.utils.money import (
    cents_to_decimal,
    format_currency,
    invert_charge_to_negative_payment,
    money_to_cents,
    parse_money,
    split_charge_into_base_and_vat,
)


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


def test_invert_charge_to_negative_payment_moves_charge_into_negative_payment():
    # Caso típico: "Dev. deb nac..." llega como cargo puro.
    assert invert_charge_to_negative_payment(6400, 0) == (0, -6400)


def test_invert_charge_to_negative_payment_nets_against_existing_payment():
    assert invert_charge_to_negative_payment(500, 2000) == (0, 1500)


def test_invert_charge_to_negative_payment_leaves_pure_payments_unchanged():
    assert invert_charge_to_negative_payment(0, 5000) == (0, 5000)


def test_split_charge_into_base_and_vat_matches_domiciliacion_example():
    # $68.44 = $59.00 base + $9.44 de IVA (16%), el caso reportado.
    assert split_charge_into_base_and_vat(6844) == (5900, 944)


@pytest.mark.parametrize("total_cents", [1, 7, 100, 6844, 999999, 1234567])
def test_split_charge_into_base_and_vat_always_sums_to_total(total_cents):
    base_cents, vat_cents = split_charge_into_base_and_vat(total_cents)
    assert base_cents + vat_cents == total_cents
    assert base_cents >= 0
    assert vat_cents >= 0


def test_split_charge_into_base_and_vat_of_zero_is_zero():
    assert split_charge_into_base_and_vat(0) == (0, 0)
