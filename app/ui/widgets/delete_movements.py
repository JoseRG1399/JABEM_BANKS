"""Eliminación confirmada de movimientos, compartida por las pantallas de
Movimientos y Sin clasificar."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from app.database.session import Database
from app.repositories.movement_repository import MovementRepository


def confirm_and_delete_movements(
    parent: QWidget, database: Database, movement_ids: list[int]
) -> int | None:
    """Pide confirmación y elimina. Devuelve cuántos se eliminaron, o None si se canceló."""
    if not movement_ids:
        return None
    answer = QMessageBox.question(
        parent,
        "Confirmar eliminación",
        f"¿Eliminar {len(movement_ids)} movimiento(s) seleccionado(s)?\n\n"
        "Esta acción no se puede deshacer. Si vuelves a importar el archivo "
        "original, el movimiento podrá cargarse otra vez.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return None
    with database.session_scope() as session:
        deleted = MovementRepository(session).delete_by_ids(movement_ids)
    QMessageBox.information(parent, "Eliminación completa", f"Se eliminaron {deleted} movimiento(s).")
    return deleted
