"""Pantalla de consulta de movimientos: filtros, tabla paginada, totales,
detalle y exportación a Excel del resultado filtrado."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.constants import ClassificationStatus
from app.database.session import Database
from app.repositories.bank_repository import BankRepository
from app.repositories.branch_repository import BranchRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.imported_file_repository import ImportedFileRepository
from app.repositories.movement_repository import MovementFilter, MovementRepository
from app.services import export_service
from app.ui.dialogs.movement_detail_dialog import MovementDetailDialog
from app.ui.widgets.filter_bar import FilterBar
from app.ui.widgets.pagination import Pagination
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency, parse_money

COLUMNS = [
    "Fecha",
    "Banco",
    "Cuenta",
    "Sucursal",
    "Categoría",
    "Concepto / Referencia",
    "Cargo",
    "Abono",
    "Saldo",
    "Clasificación",
    "Archivo",
]

STATUS_LABELS = {
    "CLASSIFIED": "Clasificado",
    "UNCLASSIFIED": "No clasificado",
    "MANUAL": "Manual",
}


class MovementsPage(QWidget):
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
    # Construcción de la interfaz
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Movimientos")
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

        self._bank_combo = QComboBox()
        self._bank_combo.currentIndexChanged.connect(self._on_bank_changed)
        self._filter_bar.add_field("Banco", self._bank_combo)

        self._account_combo = QComboBox()
        self._filter_bar.add_field("Cuenta", self._account_combo)

        self._branch_combo = QComboBox()
        self._filter_bar.add_field("Sucursal", self._branch_combo)

        self._category_combo = QComboBox()
        self._filter_bar.add_field("Categoría", self._category_combo)

        self._type_combo = QComboBox()
        self._type_combo.addItem("Todos", None)
        self._type_combo.addItem("Cargo", "CARGO")
        self._type_combo.addItem("Abono", "ABONO")
        self._filter_bar.add_field("Cargo / Abono", self._type_combo)

        self._status_combo = QComboBox()
        self._status_combo.addItem("Todos", None)
        for status in ClassificationStatus:
            self._status_combo.addItem(STATUS_LABELS.get(status.value, status.value), status.value)
        self._filter_bar.add_field("Estado", self._status_combo)

        self._file_combo = QComboBox()
        self._filter_bar.add_field("Archivo importado", self._file_combo)

        self._text_edit = QLineEdit()
        self._text_edit.setPlaceholderText("Buscar en concepto…")
        self._filter_bar.add_field("Texto libre", self._text_edit)

        self._min_amount_edit = QLineEdit()
        self._min_amount_edit.setPlaceholderText("0.00")
        self._filter_bar.add_field("Importe mínimo", self._min_amount_edit)

        self._max_amount_edit = QLineEdit()
        self._max_amount_edit.setPlaceholderText("0.00")
        self._filter_bar.add_field("Importe máximo", self._max_amount_edit)

        outer.addWidget(self._filter_bar)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        outer.addWidget(self._table, stretch=1)

        footer = QHBoxLayout()
        self._totals_label = QLabel("")
        self._totals_label.setObjectName("cardLabel")
        footer.addWidget(self._totals_label)
        footer.addStretch()

        export_button = QPushButton("Exportar Excel")
        export_button.clicked.connect(self._on_export)
        footer.addWidget(export_button)
        outer.addLayout(footer)

        default_page_size = self._config.settings.rows_per_page if self._config else None
        self._pagination = Pagination(default_page_size=default_page_size)
        self._pagination.page_changed.connect(self._on_page_changed)
        self._pagination.page_size_changed.connect(self._on_page_size_changed)
        outer.addWidget(self._pagination)

        self._sort_column = "movement_date"
        self._sort_desc = True

    # ------------------------------------------------------------------
    # Carga de catálogos para los filtros
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._populate_lookup_combos()
        self._current_page = 1
        self._pagination.reset()
        self._load_page()

    def _fill_combo(self, combo: QComboBox, items: list[tuple[str, int]]) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todos", None)
        for label, value in items:
            combo.addItem(label, value)
        combo.blockSignals(False)

    def _populate_lookup_combos(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            branch_repo = BranchRepository(session)
            category_repo = CategoryRepository(session)
            file_repo = ImportedFileRepository(session)

            self._fill_combo(self._bank_combo, [(b.name, b.id) for b in bank_repo.list_all()])
            self._fill_account_combo(bank_repo, bank_id=None)
            self._fill_combo(self._branch_combo, [(b.name, b.id) for b in branch_repo.list_all()])
            self._fill_combo(
                self._category_combo, [(c.name, c.id) for c in category_repo.list_all()]
            )

            self._file_combo.blockSignals(True)
            self._file_combo.clear()
            self._file_combo.addItem("Todos", None)
            for imported_file in file_repo.list_all():
                label = (
                    f"{imported_file.original_name} "
                    f"({format_date_for_display(imported_file.imported_at.date())})"
                )
                self._file_combo.addItem(label, imported_file.id)
            self._file_combo.blockSignals(False)

    def _fill_account_combo(self, bank_repo: BankRepository, bank_id: int | None) -> None:
        accounts = bank_repo.list_accounts(bank_id=bank_id)
        self._fill_combo(self._account_combo, [(a.alias, a.id) for a in accounts])

    def _on_bank_changed(self) -> None:
        bank_id = self._bank_combo.currentData()
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            self._fill_account_combo(bank_repo, bank_id=bank_id)

    # ------------------------------------------------------------------
    # Filtros y acciones
    # ------------------------------------------------------------------
    def _current_filters(self) -> MovementFilter:
        min_amount = self._read_amount(self._min_amount_edit, "mínimo")
        max_amount = self._read_amount(self._max_amount_edit, "máximo")

        return MovementFilter(
            date_from=self._date_from.date().toPython(),
            date_to=self._date_to.date().toPython(),
            bank_id=self._bank_combo.currentData(),
            bank_account_id=self._account_combo.currentData(),
            branch_id=self._branch_combo.currentData(),
            category_id=self._category_combo.currentData(),
            classification_status=self._status_combo.currentData(),
            movement_type=self._type_combo.currentData(),
            free_text=self._text_edit.text().strip() or None,
            min_amount_cents=min_amount,
            max_amount_cents=max_amount,
            imported_file_id=self._file_combo.currentData(),
        )

    def _read_amount(self, field: QLineEdit, label: str) -> int | None:
        text = field.text().strip()
        if not text:
            return None
        try:
            value = parse_money(text)
        except ValueError:
            QMessageBox.warning(self, "Importe inválido", f"El importe {label} no es válido.")
            return None
        if value is None:
            return None
        return int(value * 100)

    def _on_search(self) -> None:
        self._current_page = 1
        self._pagination.reset()
        self._load_page()

    def _on_clear_filters(self) -> None:
        self._date_from.setDate(dt.date(2000, 1, 1))
        self._date_to.setDate(dt.date.today())
        self._bank_combo.setCurrentIndex(0)
        self._account_combo.setCurrentIndex(0)
        self._branch_combo.setCurrentIndex(0)
        self._category_combo.setCurrentIndex(0)
        self._type_combo.setCurrentIndex(0)
        self._status_combo.setCurrentIndex(0)
        self._file_combo.setCurrentIndex(0)
        self._text_edit.clear()
        self._min_amount_edit.clear()
        self._max_amount_edit.clear()
        self._on_search()

    def _on_page_changed(self, page: int) -> None:
        self._current_page = page
        self._load_page()

    def _on_page_size_changed(self, _page_size: int) -> None:
        self._current_page = 1
        self._load_page()

    def _on_header_clicked(self, section: int) -> None:
        sortable_columns = {
            0: "movement_date",
            6: "charge_cents",
            7: "payment_cents",
            8: "balance_cents",
        }
        column = sortable_columns.get(section)
        if column is None:
            return
        if self._sort_column == column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_column = column
            self._sort_desc = True
        self._load_page()

    # ------------------------------------------------------------------
    # Carga de la tabla
    # ------------------------------------------------------------------
    def _load_page(self) -> None:
        filters = self._current_filters()
        page_size = self._pagination.current_page_size()

        with self._database.session_scope() as session:
            repo = MovementRepository(session)
            result = repo.query_paginated(
                filters,
                self._current_page,
                page_size,
                sort_column=self._sort_column,
                sort_desc=self._sort_desc,
            )

            self._table.setRowCount(len(result.items))
            self._row_movement_ids = []
            for row_index, movement in enumerate(result.items):
                self._row_movement_ids.append(movement.id)
                values = [
                    format_date_for_display(movement.movement_date),
                    movement.bank_account.bank.name if movement.bank_account else "",
                    movement.bank_account.alias if movement.bank_account else "",
                    movement.branch.name if movement.branch else "—",
                    movement.category.name if movement.category else "—",
                    movement.description_original,
                    format_currency(movement.charge_cents) if movement.charge_cents else "",
                    format_currency(movement.payment_cents) if movement.payment_cents else "",
                    (
                        format_currency(movement.balance_cents)
                        if movement.balance_cents is not None
                        else "—"
                    ),
                    STATUS_LABELS.get(movement.classification_status, movement.classification_status),
                    movement.imported_file.original_name if movement.imported_file else "",
                ]
                for col_index, value in enumerate(values):
                    self._table.setItem(row_index, col_index, QTableWidgetItem(value))

            self._pagination.set_total(result.total_items)
            self._totals_label.setText(
                f"Resultados: {result.total_items}  |  "
                f"Cargo total: {format_currency(result.total_charge_cents)}  |  "
                f"Abono total: {format_currency(result.total_payment_cents)}"
            )

    def _on_export(self) -> None:
        filters = self._current_filters()
        with self._database.session_scope() as session:
            repo = MovementRepository(session)
            movements = repo.list_all_filtered(filters)

            if not movements:
                QMessageBox.warning(self, "Sin datos", "No hay movimientos para exportar con estos filtros.")
                return

            default_name = export_service.build_safe_filename(
                "movimientos", filters.date_from, filters.date_to
            )
            default_dir = str(self._config.paths.exports_dir) if self._config else ""
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Exportar movimientos", str(Path(default_dir) / default_name), "Excel (*.xlsx)"
            )
            if not file_path:
                return
            if not file_path.endswith(".xlsx"):
                file_path += ".xlsx"

            try:
                export_service.export_movements_to_excel(movements, filters, Path(file_path))
            except OSError as exc:
                QMessageBox.critical(self, "Error al exportar", f"No se pudo exportar el archivo: {exc}")
                return

        QMessageBox.information(self, "Exportación completa", "Los movimientos se exportaron correctamente.")

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if row >= len(self._row_movement_ids):
            return
        movement_id = self._row_movement_ids[row]
        with self._database.session_scope() as session:
            repo = MovementRepository(session)
            movement = repo.get_by_id(movement_id)
            if movement is None:
                return
            dialog = MovementDetailDialog(movement, parent=self)
            dialog.exec()
