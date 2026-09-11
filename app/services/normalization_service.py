"""Normaliza un ``ParsedMovement`` (salida de un parser) a los campos
canónicos que se persistirán en la tabla ``movements``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from app.schemas.parsed_movement import ParsedMovement
from app.utils.hashes import compute_movement_hash
from app.utils.money import money_to_cents, split_charge_into_base_and_vat
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


def build_vat_split(
    nm: NormalizedMovement, bank_account_id: int
) -> tuple[NormalizedMovement, NormalizedMovement]:
    """Divide un movimiento normalizado que junta cargo base + IVA (p. ej.
    una domiciliación) en dos movimientos independientes: ``(base, vat)``.

    Cada uno lleva su propio hash, recalculado a partir de su descripción e
    importe, para que un archivo reimportado los reconozca como duplicados
    igual que a cualquier otro movimiento (sección 12).
    """
    base_cents, vat_cents = split_charge_into_base_and_vat(nm.charge_cents)
    normalized_reference = normalize_text(nm.reference_original) if nm.reference_original else ""

    base = replace(
        nm,
        charge_cents=base_cents,
        base_movement_hash=compute_movement_hash(
            bank_account_id=bank_account_id,
            movement_date=nm.movement_date,
            normalized_concept=nm.normalized_text,
            normalized_reference=normalized_reference,
            external_folio=nm.external_folio or "",
            charge_cents=base_cents,
            payment_cents=nm.payment_cents,
            balance_cents=nm.balance_cents,
        ),
    )

    vat_description = f"IVA {nm.description_original}"
    vat_normalized_text = normalize_text(vat_description)
    vat = NormalizedMovement(
        row_number=nm.row_number,
        movement_date=nm.movement_date,
        description_original=vat_description,
        reference_original=nm.reference_original,
        normalized_text=vat_normalized_text,
        external_folio=nm.external_folio,
        charge_cents=vat_cents,
        payment_cents=0,
        balance_cents=nm.balance_cents,
        base_movement_hash=compute_movement_hash(
            bank_account_id=bank_account_id,
            movement_date=nm.movement_date,
            normalized_concept=vat_normalized_text,
            normalized_reference=normalized_reference,
            external_folio=nm.external_folio or "",
            charge_cents=vat_cents,
            payment_cents=0,
            balance_cents=nm.balance_cents,
        ),
    )
    return base, vat
