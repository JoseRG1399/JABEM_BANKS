"""Normaliza un ``ParsedMovement`` (salida de un parser) a los campos
canónicos que se persistirán en la tabla ``movements``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.schemas.parsed_movement import ParsedMovement
from app.utils.hashes import compute_movement_hash
from app.utils.money import money_to_cents
from app.utils.text import normalize_text


@dataclass
class NormalizedMovement:
    row_number: int
    movement_date: dt.date
    description_original: str
    reference_original: str | None
    normalized_text: str
    external_folio: str | None
    charge_cents: int
    payment_cents: int
    balance_cents: int | None
    base_movement_hash: str


def normalize_movement(parsed: ParsedMovement, bank_account_id: int) -> NormalizedMovement:
    normalized_text = normalize_text(parsed.description_original)
    normalized_reference = (
        normalize_text(parsed.reference_original) if parsed.reference_original else ""
    )
    charge_cents = money_to_cents(parsed.charge)
    payment_cents = money_to_cents(parsed.payment)
    balance_cents = money_to_cents(parsed.balance) if parsed.balance is not None else None

    base_hash = compute_movement_hash(
        bank_account_id=bank_account_id,
        movement_date=parsed.movement_date,
        normalized_concept=normalized_text,
        normalized_reference=normalized_reference,
        external_folio=parsed.external_folio or "",
        charge_cents=charge_cents,
        payment_cents=payment_cents,
        balance_cents=balance_cents,
    )

    return NormalizedMovement(
        row_number=parsed.row_number,
        movement_date=parsed.movement_date,
        description_original=parsed.description_original,
        reference_original=parsed.reference_original,
        normalized_text=normalized_text,
        external_folio=parsed.external_folio,
        charge_cents=charge_cents,
        payment_cents=payment_cents,
        balance_cents=balance_cents,
        base_movement_hash=base_hash,
    )
