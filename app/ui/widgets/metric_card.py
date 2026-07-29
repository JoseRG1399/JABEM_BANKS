"""Tarjeta de métrica reutilizable para el dashboard."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("cardValue")
        layout.addWidget(self._value_label)

        caption = QLabel(label)
        caption.setObjectName("cardLabel")
        caption.setWordWrap(True)
        layout.addWidget(caption)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)
