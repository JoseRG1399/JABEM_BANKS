"""Pantalla de consulta de movimientos: filtros, tabla paginada, totales,
detalle y exportación a Excel del resultado filtrado."""
from __future__ import annotations

import datetime as dt
import html as html_lib
from pathlib import Path

from PySide6.QtGui import QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from app.models import ImportedFile
from app.repositories.bank_repository import BankRepository
from app.repositories.branch_repository import BranchRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.imported_file_repository import ImportedFileRepository
from app.repositories.movement_repository import MovementFilter, MovementRepository
from app.services import export_service
from app.ui.dialogs.classify_movement_dialog import ClassifyMovementDialog
from app.ui.dialogs.movement_detail_dialog import MovementDetailDialog
from app.ui.widgets.delete_movements import confirm_and_delete_movements
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

MOVEMENTS_PRINT_STYLE = """
<style>
    body { font-family: Arial, sans-serif; font-size: 11pt; color: #000000; }
    h1 { font-size: 14pt; margin-top: 0; margin-bottom: 4px; }
    .filters { font-size: 9pt; color: #333333; margin-bottom: 8px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid #000000; padding: 3px 5px; text-align: right; font-size: 8pt; }
    th { background-color: #dddddd; text-align: center; font-weight: bold; }
    td.label { text-align: left; }
</style>
"""

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

        title = QLabel("Reporte de movimientos")
        title.setObjectName("appTitle")
        outer.addWidget(title)

        self._filter_bar = FilterBar()
        self._filter_bar.search_requested.connect(self._on_search)
        self._filter_bar.clear_requested.connect(self._on_clear_filters)

        self._date_from = QDateEdit(calendarPopup=True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(dt.date.today())
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

        selection_row = QHBoxLayout()
        self._selection_label = QLabel("0 movimiento(s) seleccionado(s)")
        self._selection_label.setObjectName("cardLabel")
        selection_row.addWidget(self._selection_label)
        selection_row.addStretch()

        self._reclassify_button = QPushButton("Reclasificar seleccionados")
        self._reclassify_button.setObjectName("primaryButton")
        self._reclassify_button.setEnabled(False)
        self._reclassify_button.clicked.connect(self._on_reclassify_selected)
        selection_row.addWidget(self._reclassify_button)

        self._delete_button = QPushButton("Eliminar seleccionados")
        self._delete_button.setObjectName("dangerButton")
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self._on_delete_selected)
        selection_row.addWidget(self._delete_button)

        print_button = QPushButton("Imprimir")
        print_button.setObjectName("infoButton")
        print_button.clicked.connect(self._on_print)
        selection_row.addWidget(print_button)

        export_button = QPushButton("Exportar Excel")
        export_button.setObjectName("successButton")
        export_button.clicked.connect(self._on_export)
        selection_row.addWidget(export_button)
        outer.addLayout(selection_row)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        outer.addWidget(self._table, stretch=1)

        footer = QHBoxLayout()
        self._totals_label = QLabel("")
        self._totals_label.setObjectName("cardLabel")
        footer.addWidget(self._totals_label)
        footer.addStretch()
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

    def _filter_conflict(self, filters: MovementFilter) -> str | None:
        """Devuelve el motivo si la combinación de filtros no puede dar resultados."""
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            return "La fecha inicial no puede ser posterior a la fecha final."

        low, high = filters.min_amount_cents, filters.max_amount_cents
        if low is not None and high is not None and low > high:
            return "El importe mínimo no puede ser mayor que el importe máximo."

        category_label = self._category_combo.currentText()
        if filters.category_id is not None:
            is_unclassified_category = category_label == "No clasificado"
            if filters.classification_status in ("CLASSIFIED", "MANUAL") and is_unclassified_category:
                return (
                    "La categoría «No clasificado» no puede combinarse con el estado "
                    "Clasificado o Manual."
                )
            if filters.classification_status == "UNCLASSIFIED" and not is_unclassified_category:
                return (
                    "El estado «No clasificado» solo puede combinarse con la categoría "
                    "«No clasificado»."
                )

        if filters.imported_file_id is not None and (
            filters.bank_account_id is not None or filters.bank_id is not None
        ):
            with self._database.session_scope() as session:
                imported_file = session.get(ImportedFile, filters.imported_file_id)
                account = imported_file.bank_account if imported_file else None
                if account is not None:
                    if filters.bank_account_id is not None and account.id != filters.bank_account_id:
                        return "El archivo importado seleccionado pertenece a otra cuenta."
                    if filters.bank_id is not None and account.bank_id != filters.bank_id:
                        return "El archivo importado seleccionado pertenece a otro banco."
        return None

    def _validated_filters(self) -> MovementFilter | None:
        filters = self._current_filters()
        conflict = self._filter_conflict(filters)
        if conflict:
            QMessageBox.warning(self, "Filtros incompatibles", conflict)
            return None
        return filters

    def _on_search(self) -> None:
        if self._validated_filters() is None:
            return
        self._current_page = 1
        self._pagination.reset()
        self._load_page()

    def _on_clear_filters(self) -> None:
        self._date_from.setDate(dt.date.today())
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

        self._on_selection_changed()

    # ------------------------------------------------------------------
    # Reclasificación (incluye movimientos ya clasificados, a diferencia de
    # la pantalla "Sin clasificar" que solo trabaja con los pendientes)
    # ------------------------------------------------------------------
    def _selected_movement_ids(self) -> list[int]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        return [self._row_movement_ids[row] for row in sorted(rows) if row < len(self._row_movement_ids)]

    def _on_selection_changed(self) -> None:
        count = len(self._selected_movement_ids())
        self._selection_label.setText(f"{count} movimiento(s) seleccionado(s)")
        self._reclassify_button.setEnabled(count > 0)
        self._delete_button.setEnabled(count > 0)

    def _on_delete_selected(self) -> None:
        movement_ids = self._selected_movement_ids()
        if not movement_ids:
            return
        if confirm_and_delete_movements(self, self._database, movement_ids) is not None:
            self._load_page()

    def _on_reclassify_selected(self) -> None:
        movement_ids = self._selected_movement_ids()
        if not movement_ids:
            return
        dialog = ClassifyMovementDialog(self._database, movement_ids, parent=self)
        if dialog.exec():
            self._load_page()

    def _on_export(self) -> None:
        filters = self._validated_filters()
        if filters is None:
            return
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

    def _on_print(self) -> None:
        filters = self._validated_filters()
        if filters is None:
            return
        with self._database.session_scope() as session:
            movements = MovementRepository(session).list_all_filtered(filters)
            if not movements:
                QMessageBox.warning(self, "Sin datos", "No hay movimientos para imprimir con estos filtros.")
                return

            header_html = "".join(f"<th>{html_lib.escape(col)}</th>" for col in COLUMNS)
            money_cols = {6, 7, 8}
            rows_html = []
            total_charge = total_payment = 0
            for movement in movements:
                total_charge += movement.charge_cents or 0
                total_payment += movement.payment_cents or 0
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
                cells = "".join(
                    ("<td>" if i in money_cols else '<td class="label">')
                    + html_lib.escape(v)
                    + "</td>"
                    for i, v in enumerate(values)
                )
                rows_html.append(f"<tr>{cells}</tr>")
            count = len(movements)

        printed_at = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        period = (
            f"Del {format_date_for_display(filters.date_from)} "
            f"al {format_date_for_display(filters.date_to)}"
        )
        body = (
            "<h1>Reporte de movimientos</h1>"
            f'<div class="filters">{html_lib.escape(period)} &middot; {count} movimiento(s) &middot; '
            f"Cargo total: {html_lib.escape(format_currency(total_charge))} &middot; "
            f"Abono total: {html_lib.escape(format_currency(total_payment))}</div>"
            f'<div class="filters">Impreso el {printed_at}</div>'
            f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
        )

        document = QTextDocument()
        document.setHtml(MOVEMENTS_PRINT_STYLE + body)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Vista previa de impresión — Reporte de movimientos")
        preview.paintRequested.connect(document.print_)
        preview.exec()

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
