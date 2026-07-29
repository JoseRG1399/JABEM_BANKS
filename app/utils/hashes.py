"""Cálculo de hashes usados para la detección de archivos y movimientos duplicados."""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def compute_file_hash(path: Path) -> str:
    """SHA-256 del contenido completo de un archivo."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_movement_hash(
    *,
    bank_account_id: int,
    movement_date: dt.date,
    normalized_concept: str,
    normalized_reference: str,
    external_folio: str,
    charge_cents: int,
    payment_cents: int,
    balance_cents: int | None,
) -> str:
    """SHA-256 determinista a partir de los campos que identifican un movimiento.

    No incluye ``occurrence_number``: ese contador se aplica por separado para
    distinguir movimientos legítimamente idénticos dentro de un mismo archivo.
    """
    parts = [
        str(bank_account_id),
        movement_date.isoformat(),
        normalized_concept,
        normalized_reference or "",
        external_folio or "",
        str(charge_cents),
        str(payment_cents),
        "" if balance_cents is None else str(balance_cents),
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
