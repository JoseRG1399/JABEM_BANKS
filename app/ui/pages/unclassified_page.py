"""Pantalla de movimientos sin clasificar: permite seleccionar uno o varios
y reclasificarlos manualmente (sección 14 de la especificación)."""
from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.database.session import Database
from app.repositories.bank_repository import BankRepository
from app.repositories.movement_repository import MovementFilter, MovementRepository
from app.ui.dialogs.classify_movement_dialog import ClassifyMovementDialog
from app.ui.widgets.filter_bar import FilterBar
from app.ui.widgets.pagination import Pagination
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency

COLUMNS = ["Fecha", "Banco", "Cuenta", "Concepto / Referencia", "Cargo", "Abono", "Archivo"]


class UnclassifiedPage(QWidget):
    def __init__(
        self, database: Database, config: Config | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._config = config
        self._current_page = 1
        self._row_movement_ids: list[int] = []
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Movimientos sin clasificar")
        title.setObjectName("appTitle")
        outer.addWidget(title)

        self._filter_bar = FilterBar()
        self._filter_bar.search_requested.connect(self._on_search)
        self._filter_bar.clear_requested.connect(self._on_clear_filters)

        self._date_from = QDateEdit(calendarPopup=True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(dt.date(2000, 1, 1))
        self._filter_bar.add_field("Fecha inicial", self._date_from)

        self._date_to = QDateEdit(calendarPopup=True)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setDate(dt.date.today())
        self._filter_bar.add_field("Fecha final", self._date_to)

        self._account_combo = QComboBox()
        self._filter_bar.add_field("Cuenta", self._account_combo)

        self._text_edit = QLineEdit()
        self._text_edit.setPlaceholderText("Buscar en concepto…")
        self._filter_bar.add_field("Texto libre", self._text_edit)

        outer.addWidget(self._filter_bar)

        actions_row = QHBoxLayout()
        self._selection_label = QLabel("0 movimiento(s) seleccionado(s)")
        self._selection_label.setObjectName("cardLabel")
        actions_row.addWidget(self._selection_label)
        actions_row.addStretch()

        self._reclassify_button = QPushButton("Reclasificar seleccionados")
        self._reclassify_button.setObjectName("primaryButton")
        self._reclassify_button.setEnabled(False)
        self._reclassify_button.clicked.connect(self._on_reclassify_selected)
        actions_row.addWidget(self._reclassify_button)
        outer.addLayout(actions_row)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        outer.addWidget(self._table, stretch=1)

        default_page_size = self._config.settings.rows_per_page if self._config else None
        self._pagination = Pagination(default_page_size=default_page_size)
        self._pagination.page_changed.connect(self._on_page_changed)
        self._pagination.page_size_changed.connect(self._on_page_size_changed)
        outer.addWidget(self._pagination)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._populate_lookup_combos()
        self._current_page = 1
        self._pagination.reset()
        self._load_page()

    def _populate_lookup_combos(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            self._account_combo.blockSignals(True)
            self._account_combo.clear()
            self._account_combo.addItem("Todas", None)
            for account in bank_repo.list_accounts():
                self._account_combo.addItem(account.alias, account.id)
            self._account_combo.blockSignals(False)

    def _current_filters(self) -> MovementFilter:
        return MovementFilter(
            date_from=self._date_from.date().toPython(),
            date_to=self._date_to.date().toPython(),
            bank_account_id=self._account_combo.currentData(),
            classification_status="UNCLASSIFIED",
            free_text=self._text_edit.text().strip() or None,
        )

    def _on_search(self) -> None:
        self._current_page = 1
        self._pagination.reset()
        self._load_page()

    def _on_clear_filters(self) -> None:
        self._date_from.setDate(dt.date(2000, 1, 1))
        self._date_to.setDate(dt.date.today())
        self._account_combo.setCurrentIndex(0)
        self._text_edit.clear()
        self._on_search()

    def _on_page_changed(self, page: int) -> None:
        self._current_page = page
        self._load_page()

    def _on_page_size_changed(self, _page_size: int) -> None:
        self._current_page = 1
        self._load_page()

    # ------------------------------------------------------------------
    def _load_page(self) -> None:
        filters = self._current_filters()
        page_size = self._pagination.current_page_size()

        with self._database.session_scope() as session:
            repo = MovementRepository(session)
            result = repo.query_paginated(filters, self._current_page, page_size)

            self._table.setRowCount(len(result.items))
            self._row_movement_ids = []
            for row_index, movement in enumerate(result.items):
                self._row_movement_ids.append(movement.id)
                values = [
                    format_date_for_display(movement.movement_date),
                    movement.bank_account.bank.name if movement.bank_account else "",
                    movement.bank_account.alias if movement.bank_account else "",
                    movement.description_original,
                    format_currency(movement.charge_cents) if movement.charge_cents else "",
                    format_currency(movement.payment_cents) if movement.payment_cents else "",
                    movement.imported_file.original_name if movement.imported_file else "",
                ]
                for col_index, value in enumerate(values):
                    self._table.setItem(row_index, col_index, QTableWidgetItem(value))

            self._pagination.set_total(result.total_items)

        self._on_selection_changed()

    def _selected_movement_ids(self) -> list[int]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        return [self._row_movement_ids[row] for row in sorted(rows) if row < len(self._row_movement_ids)]

    def _on_selection_changed(self) -> None:
        count = len(self._selected_movement_ids())
        self._selection_label.setText(f"{count} movimiento(s) seleccionado(s)")
        self._reclassify_button.setEnabled(count > 0)

    def _on_reclassify_selected(self) -> None:
        movement_ids = self._selected_movement_ids()
        if not movement_ids:
            return
        dialog = ClassifyMovementDialog(self._database, movement_ids, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if row >= len(self._row_movement_ids):
            return
        movement_id = self._row_movement_ids[row]
        dialog = ClassifyMovementDialog(self._database, [movement_id], parent=self)
        if dialog.exec():
            self.refresh()
