"""Overlay semitransparente con indicador de carga para operaciones largas."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    def __init__(self, message: str = "Procesando…", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(15, 20, 30, 140);")
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel(message)
        self._label.setStyleSheet("color: white; font-size: 12pt; font-weight: 600;")
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_message(self, message: str) -> None:
        self._label.setText(message)

    def show_overlay(self, message: str | None = None) -> None:
        if message:
            self.set_message(message)
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.setVisible(True)

    def hide_overlay(self) -> None:
        self.setVisible(False)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (override Qt)
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        super().resizeEvent(event)
