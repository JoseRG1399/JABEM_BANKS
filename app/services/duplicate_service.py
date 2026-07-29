"""Detección de archivos y movimientos duplicados (sección 12 de la especificación).

- Un archivo duplicado se detecta por el hash SHA-256 del archivo completo.
- Un movimiento duplicado se detecta por ``movement_hash``. Como puede haber
  dos movimientos legítimamente idénticos dentro de un mismo archivo (o entre
  archivos), se numeran las apariciones (``occurrence_number``) y solo se
  insertan las apariciones nuevas respecto de lo que ya existe en la base.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass

from app.repositories.imported_file_repository import ImportedFileRepository
from app.repositories.movement_repository import MovementRepository
from app.services.normalization_service import NormalizedMovement


@dataclass
class FileDuplicateInfo:
    is_duplicate: bool
    previous_file_name: str | None = None
    previous_imported_at: dt.datetime | None = None


def check_file_duplicate(
    imported_file_repo: ImportedFileRepository, file_hash: str
) -> FileDuplicateInfo:
    existing = imported_file_repo.get_by_hash(file_hash)
    if existing is None:
        return FileDuplicateInfo(is_duplicate=False)
    return FileDuplicateInfo(
        is_duplicate=True,
        previous_file_name=existing.original_name,
        previous_imported_at=existing.imported_at,
    )


@dataclass
class OccurrenceAssignment:
    normalized: NormalizedMovement
    occurrence_number: int
    is_new: bool


def assign_occurrence_numbers(
    movement_repo: MovementRepository,
    normalized_movements: list[NormalizedMovement],
) -> list[OccurrenceAssignment]:
    """Calcula el ``occurrence_number`` de cada movimiento normalizado y si
    corresponde a una aparición nueva (a insertar) o ya existente (duplicada).
    """
    hash_counts_in_file: Counter[str] = Counter()
    existing_counts = movement_repo.count_existing_occurrences(
        {nm.base_movement_hash for nm in normalized_movements}
    )

    assignments: list[OccurrenceAssignment] = []
    for nm in normalized_movements:
        hash_counts_in_file[nm.base_movement_hash] += 1
        occurrence_number = hash_counts_in_file[nm.base_movement_hash]
        already_in_db = existing_counts.get(nm.base_movement_hash, 0)
        is_new = occurrence_number > already_in_db
        assignments.append(
            OccurrenceAssignment(
                normalized=nm, occurrence_number=occurrence_number, is_new=is_new
            )
        )
    return assignments
