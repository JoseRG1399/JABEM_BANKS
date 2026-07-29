"""Control de paginación reutilizable."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
DEFAULT_PAGE_SIZE_INDEX = 1  # 50


class Pagination(QWidget):
    page_changed = Signal(int)
    page_size_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None, default_page_size: int | None = None) -> None:
        super().__init__(parent)
        self._page = 1
        self._total_pages = 1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._prev_button = QPushButton("‹ Anterior")
        self._prev_button.clicked.connect(self._go_previous)
        layout.addWidget(self._prev_button)

        self._status_label = QLabel("Página 1 de 1")
        layout.addWidget(self._status_label)

        self._next_button = QPushButton("Siguiente ›")
        self._next_button.clicked.connect(self._go_next)
        layout.addWidget(self._next_button)

        layout.addStretch()

        layout.addWidget(QLabel("Filas por página:"))
        self._page_size_combo = QComboBox()
        for size in PAGE_SIZE_OPTIONS:
            self._page_size_combo.addItem(str(size), size)
        initial_index = DEFAULT_PAGE_SIZE_INDEX
        if default_page_size is not None:
            closest = min(PAGE_SIZE_OPTIONS, key=lambda size: abs(size - default_page_size))
            initial_index = PAGE_SIZE_OPTIONS.index(closest)
        self._page_size_combo.setCurrentIndex(initial_index)
        self._page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        layout.addWidget(self._page_size_combo)

        self._update_controls()

    def current_page_size(self) -> int:
        return self._page_size_combo.currentData()

    def set_total(self, total_items: int) -> None:
        page_size = self.current_page_size()
        self._total_pages = max(1, (total_items + page_size - 1) // page_size)
        self._page = min(self._page, self._total_pages)
        self._update_controls()

    def reset(self) -> None:
        self._page = 1
        self._update_controls()

    def _go_previous(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._update_controls()
            self.page_changed.emit(self._page)

    def _go_next(self) -> None:
        if self._page < self._total_pages:
            self._page += 1
            self._update_controls()
            self.page_changed.emit(self._page)

    def _on_page_size_changed(self) -> None:
        self._page = 1
        self.page_size_changed.emit(self.current_page_size())

    def _update_controls(self) -> None:
        self._status_label.setText(f"Página {self._page} de {self._total_pages}")
        self._prev_button.setEnabled(self._page > 1)
        self._next_button.setEnabled(self._page < self._total_pages)
