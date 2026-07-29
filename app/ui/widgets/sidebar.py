"""Barra lateral de navegación fija."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QPushButton, QVBoxLayout, QWidget

from app.config import APP_VERSION
from app.ui.theme import SIDEBAR_WIDTH

NAV_ITEMS = [
    ("dashboard", "Inicio"),
    ("import", "Importar"),
    ("movements", "Movimientos"),
    ("unclassified", "Sin clasificar"),
    ("branches", "Sucursales"),
    ("rules", "Reglas"),
    ("reports", "Reportes"),
    ("settings", "Configuración"),
]


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, app_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(4)

        title = QLabel(app_name)
        title.setObjectName("appTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        version = QLabel(f"Versión {APP_VERSION}")
        version.setObjectName("appVersion")
        layout.addWidget(version)
        layout.addSpacing(16)

        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for key, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setProperty("active", "false")
            button.clicked.connect(lambda _checked=False, item_key=key: self._on_clicked(item_key))
            layout.addWidget(button)
            self._group.addButton(button)
            self._buttons[key] = button

        layout.addStretch()

        self.set_active("dashboard")

    def _on_clicked(self, key: str) -> None:
        self.set_active(key)
        self.navigate.emit(key)

    def set_active(self, key: str) -> None:
        for item_key, button in self._buttons.items():
            is_active = item_key == key
            button.setChecked(is_active)
            button.setProperty("active", "true" if is_active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
