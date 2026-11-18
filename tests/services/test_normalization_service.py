import datetime as dt
from decimal import Decimal

from app.schemas.parsed_movement import ParsedMovement
from app.services.normalization_service import build_vat_split, normalize_movement


def test_build_vat_split_produces_base_and_vat_with_correct_amounts():
    parsed = ParsedMovement(
        row_number=22,
        movement_date=dt.date(2026, 9, 7),
        description_original="Domic/6066887",
        reference_original=None,
        external_folio="S15071133",
        charge=Decimal("68.44"),
        payment=None,
        balance=Decimal("154986.88"),
        raw_line="",
    )
    nm = normalize_movement(parsed, bank_account_id=1)

    base, vat = build_vat_split(nm, bank_account_id=1)

    assert base.charge_cents == 5900
    assert base.payment_cents == 0
    assert base.description_original == "Domic/6066887"
    assert base.external_folio == "S15071133"
    assert base.balance_cents == nm.balance_cents

    assert vat.charge_cents == 944
    assert vat.payment_cents == 0
    assert vat.description_original == "IVA Domic/6066887"
    assert vat.normalized_text == "IVA DOMIC 6066887"
    assert vat.external_folio == "S15071133"
    assert vat.balance_cents == nm.balance_cents

    assert base.base_movement_hash != vat.base_movement_hash
    assert base.base_movement_hash != nm.base_movement_hash


def test_build_vat_split_hash_differs_from_a_different_original_charge():
    parsed_a = ParsedMovement(
        row_number=1,
        movement_date=dt.date(2026, 9, 7),
        description_original="Domic/6066887",
        reference_original=None,
        external_folio="S1",
        charge=Decimal("68.44"),
        payment=None,
        balance=None,
        raw_line="",
    )
    parsed_b = ParsedMovement(
        row_number=1,
        movement_date=dt.date(2026, 9, 7),
        description_original="Domic/6066887",
        reference_original=None,
        external_folio="S1",
        charge=Decimal("116.00"),
        payment=None,
        balance=None,
        raw_line="",
    )
    nm_a = normalize_movement(parsed_a, bank_account_id=1)
    nm_b = normalize_movement(parsed_b, bank_account_id=1)

    _, vat_a = build_vat_split(nm_a, bank_account_id=1)
    _, vat_b = build_vat_split(nm_b, bank_account_id=1)

    assert vat_a.base_movement_hash != vat_b.base_movement_hash
