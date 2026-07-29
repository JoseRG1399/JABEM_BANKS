"""Barra de filtros reutilizable con distribución adaptable y acciones."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


MIN_FIELD_WIDTH = 150
MAX_FIELDS_PER_ROW = 6


class FilterBar(QWidget):
    search_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self._fields_layout = QGridLayout()
        self._fields_layout.setSpacing(12)
        outer.addLayout(self._fields_layout)
        self._fields: list[QWidget] = []

        buttons_row = QHBoxLayout()
        search_button = QPushButton("Buscar")
        search_button.setObjectName("primaryButton")
        search_button.clicked.connect(self.search_requested.emit)
        buttons_row.addWidget(search_button)

        clear_button = QPushButton("Limpiar filtros")
        clear_button.clicked.connect(self.clear_requested.emit)
        buttons_row.addWidget(clear_button)

        buttons_row.addStretch()
        outer.addLayout(buttons_row)

    def add_field(self, label_text: str, widget: QWidget) -> None:
        column = QWidget()
        column.setMinimumWidth(MIN_FIELD_WIDTH)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("cardLabel")
        column_layout.addWidget(label)
        column_layout.addWidget(widget)
        self._fields.append(column)
        self._reflow_fields()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow_fields()

    def _reflow_fields(self) -> None:
        if not self._fields:
            return

        spacing = self._fields_layout.horizontalSpacing()
        available_width = max(1, self.contentsRect().width())
        columns = max(1, (available_width + spacing) // (MIN_FIELD_WIDTH + spacing))
        columns = min(columns, MAX_FIELDS_PER_ROW, len(self._fields))

        for field in self._fields:
            self._fields_layout.removeWidget(field)

        for index, field in enumerate(self._fields):
            row, column = divmod(index, columns)
            self._fields_layout.addWidget(field, row, column)

        for column in range(MAX_FIELDS_PER_ROW):
            self._fields_layout.setColumnStretch(column, 1 if column < columns else 0)
