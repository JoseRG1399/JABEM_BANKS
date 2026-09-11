"""Combo con casillas de verificación para filtrar por varios elementos a la vez.

Se usa en la pantalla de Reportes para poder elegir un subconjunto de
sucursales (en vez de una sola, o todas) sin tener que abrir el desplegable
una vez por cada clic.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QWidget


class MultiSelectComboBox(QComboBox):
    """QComboBox cuyos ítems tienen casilla de verificación.

    Ningún ítem marcado equivale a "sin filtro" (se incluye todo); marcar
    uno o varios limita el resultado a esos elementos.
    """

    selection_changed = Signal()

    def __init__(self, placeholder: str = "Todas", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder

        self._item_model = QStandardItemModel(self)
        self.setModel(self._item_model)
        self._item_model.itemChanged.connect(self._on_item_changed)

        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self.view().viewport().installEventFilter(self)

        self._update_text()

    # ------------------------------------------------------------------
    def set_items(self, items: list[tuple[str, object]]) -> None:
        """Reemplaza los ítems mostrados, conservando la selección previa
        cuando el mismo valor sigue presente (p. ej. al refrescar catálogos)."""
        previous = set(self.checked_values())
        self._item_model.blockSignals(True)
        self._item_model.clear()
        for label, value in items:
            item = QStandardItem(label)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(value, Qt.ItemDataRole.UserRole)
            item.setCheckState(Qt.CheckState.Checked if value in previous else Qt.CheckState.Unchecked)
            self._item_model.appendRow(item)
        self._item_model.blockSignals(False)
        self._update_text()

    def checked_values(self) -> list:
        values = []
        for row in range(self._item_model.rowCount()):
            item = self._item_model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                values.append(item.data(Qt.ItemDataRole.UserRole))
        return values

    def set_checked_values(self, values: list) -> None:
        wanted = set(values)
        self._item_model.blockSignals(True)
        for row in range(self._item_model.rowCount()):
            item = self._item_model.item(row)
            item.setCheckState(
                Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in wanted else Qt.CheckState.Unchecked
            )
        self._item_model.blockSignals(False)
        self._update_text()

    def clear_selection(self) -> None:
        self.set_checked_values([])

    # ------------------------------------------------------------------
    def eventFilter(self, source, event) -> bool:  # noqa: N802 (nombre impuesto por Qt)
        if source is self.view().viewport() and event.type() == event.Type.MouseButtonRelease:
            index = self.view().indexAt(event.position().toPoint())
            if index.isValid():
                item = self._item_model.itemFromIndex(index)
                item.setCheckState(
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
            return True  # evita que el popup se cierre al marcar/desmarcar
        return super().eventFilter(source, event)

    def _on_item_changed(self, _item: QStandardItem) -> None:
        self._update_text()
        self.selection_changed.emit()

    def _update_text(self) -> None:
        checked_labels = [
            self._item_model.item(row).text()
            for row in range(self._item_model.rowCount())
            if self._item_model.item(row).checkState() == Qt.CheckState.Checked
        ]
        if not checked_labels:
            text = self._placeholder
        elif len(checked_labels) == 1:
            text = checked_labels[0]
        else:
            text = f"{len(checked_labels)} seleccionadas"
        self.lineEdit().setText(text)
