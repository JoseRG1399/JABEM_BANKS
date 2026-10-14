"""Pantalla de reportes (sección 15.8 de la especificación)."""
from __future__ import annotations

import datetime as dt
import html as html_lib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.database.session import Database
from app.repositories.bank_repository import BankRepository
from app.repositories.branch_repository import BranchRepository
from app.repositories.category_repository import CategoryRepository
from app.schemas.report_filter import ReportFilter
from app.services import export_service, report_service
from app.services.report_service import (
    BankCommissionReport,
    BranchDayPivotReport,
    BranchPivotRow,
    ConsolidatedReport,
    ReportRow,
    ReportValueType,
)
from app.ui.widgets.multi_select_combo import MultiSelectComboBox
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency

REPORT_TYPES = [
    ("Flujo diario", "day"),
    ("Resumen por banco (actividad operativa)", "bank"),
    ("Resumen por cuenta bancaria", "account"),
    ("Resumen por sucursal", "branch"),
    ("Resumen por categoría de movimiento", "category"),
    ("Pendientes de clasificar", "unclassified"),
    ("Gasto en comisiones e IVA", "commissions"),
    ("Peso de comisiones por banco", "bank_commissions"),
    ("Conciliación de depósitos por día y sucursal", "consolidated"),
    ("Detalle del periodo por sucursal", "branch_day_pivot"),
]

PIVOT_TOTAL_LABEL = "Total general"

BANK_COMMISSION_COLUMNS = ["Banco", "Comisiones", "IVA comisiones", "Total", "Peso %"]

VALUE_TYPE_OPTIONS = [
    ("Abono", ReportValueType.PAYMENT),
    ("Cargo", ReportValueType.CHARGE),
    ("Movimiento neto", ReportValueType.NET),
]

UNCLASSIFIED_COLUMNS = ["Fecha", "Banco", "Cuenta", "Concepto / Referencia", "Cargo", "Abono", "Archivo"]

MOVEMENT_DETAIL_COLUMNS = [
    "Fecha",
    "Banco",
    "Cuenta",
    "Concepto / Referencia",
    "Cargo",
    "Abono",
    "Categoría",
    "Archivo",
]

REPORT_PRINT_STYLE = """
<style>
    body { font-family: Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 0; }
    h1 {
        font-size: 14pt;
        margin-top: 0;
        margin-bottom: 4px;
        margin-left: 0;
        margin-right: 0;
    }
    .filters {
        font-size: 9pt;
        color: #333333;
        margin-top: 0;
        margin-bottom: 12px;
    }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td {
        border: 1px solid #000000;
        padding: 4px 8px;
        text-align: right;
        font-size: 9pt;
    }
    th {
        background-color: #dddddd;
        text-align: center;
        font-weight: bold;
    }
    td.label { text-align: left; }
    td.indent { padding-left: 20px; }
    tr.total td { font-weight: bold; background-color: #eeeeee; }
</style>
"""


class ReportsPage(QWidget):
    def __init__(self, config: Config, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._database = database
        self._current_rows: list[ReportRow] = []
        self._current_unclassified: list = []
        self._current_consolidated: ConsolidatedReport | None = None
        self._current_pivot: BranchDayPivotReport | None = None
        self._current_bank_commissions: BankCommissionReport | None = None
        self._current_title = ""
        self._current_filters_snapshot: ReportFilter | None = None
        self._build_ui()
        self._populate_lookup_combos()
        self._on_report_type_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Reportes")
        title.setObjectName("appTitle")
        outer.addWidget(title)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Tipo de reporte:"))
        self._type_combo = QComboBox()
        for label, key in REPORT_TYPES:
            self._type_combo.addItem(label, key)
        self._type_combo.currentIndexChanged.connect(self._on_report_type_changed)
        type_row.addWidget(self._type_combo)

        self._value_type_combo = QComboBox()
        for label, value in VALUE_TYPE_OPTIONS:
            self._value_type_combo.addItem(label, value)
        type_row.addWidget(QLabel("Valor:"))
        type_row.addWidget(self._value_type_combo)
        type_row.addStretch()
        outer.addLayout(type_row)

        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel("Desde:"))
        self._date_from = QDateEdit(calendarPopup=True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(dt.date.today())
        filters_row.addWidget(self._date_from)

        filters_row.addWidget(QLabel("Hasta:"))
        self._date_to = QDateEdit(calendarPopup=True)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setDate(dt.date.today())
        filters_row.addWidget(self._date_to)

        filters_row.addWidget(QLabel("Banco:"))
        self._bank_combo = QComboBox()
        filters_row.addWidget(self._bank_combo)

        filters_row.addWidget(QLabel("Cuenta:"))
        self._account_combo = QComboBox()
        filters_row.addWidget(self._account_combo)

        filters_row.addWidget(QLabel("Sucursal:"))
        self._branch_filter = MultiSelectComboBox(placeholder="Todas")
        self._branch_filter.setMinimumWidth(160)
        filters_row.addWidget(self._branch_filter)

        filters_row.addWidget(QLabel("Categoría:"))
        self._category_combo = QComboBox()
        filters_row.addWidget(self._category_combo)
        outer.addLayout(filters_row)

        actions_row = QHBoxLayout()
        generate_button = QPushButton("Generar")
        generate_button.setObjectName("primaryButton")
        generate_button.clicked.connect(self._on_generate)
        actions_row.addWidget(generate_button)

        export_button = QPushButton("Exportar a Excel")
        export_button.clicked.connect(self._on_export)
        actions_row.addWidget(export_button)

        print_button = QPushButton("Imprimir")
        print_button.clicked.connect(self._on_print)
        actions_row.addWidget(print_button)
        actions_row.addStretch()
        outer.addLayout(actions_row)

        self._results_stack = QStackedWidget()

        self._simple_table = QTableWidget(0, 4)
        self._simple_table.setHorizontalHeaderLabels(["Concepto", "Cargo", "Abono", "Neto"])
        self._simple_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._simple_table.horizontalHeader().setStretchLastSection(True)
        self._results_stack.addWidget(self._simple_table)

        self._unclassified_table = QTableWidget(0, len(UNCLASSIFIED_COLUMNS))
        self._unclassified_table.setHorizontalHeaderLabels(UNCLASSIFIED_COLUMNS)
        self._unclassified_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._unclassified_table.horizontalHeader().setStretchLastSection(True)
        self._results_stack.addWidget(self._unclassified_table)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Día / Sucursal", "Total"])
        self._results_stack.addWidget(self._tree)

        self._pivot_table = QTableWidget(0, 0)
        self._pivot_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pivot_table.horizontalHeader().setStretchLastSection(True)
        self._pivot_table.cellDoubleClicked.connect(self._on_pivot_cell_double_clicked)
        self._results_stack.addWidget(self._pivot_table)

        self._bank_commissions_table = QTableWidget(0, len(BANK_COMMISSION_COLUMNS))
        self._bank_commissions_table.setHorizontalHeaderLabels(BANK_COMMISSION_COLUMNS)
        self._bank_commissions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bank_commissions_table.horizontalHeader().setStretchLastSection(True)
        self._results_stack.addWidget(self._bank_commissions_table)

        outer.addWidget(self._results_stack, stretch=1)

        self._totals_label = QLabel("")
        self._totals_label.setObjectName("cardLabel")
        outer.addWidget(self._totals_label)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._populate_lookup_combos()

    def _populate_lookup_combos(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            branch_repo = BranchRepository(session)
            category_repo = CategoryRepository(session)

            self._fill_combo(self._bank_combo, [(b.name, b.id) for b in bank_repo.list_all()])
            self._fill_combo(
                self._account_combo, [(a.alias, a.id) for a in bank_repo.list_accounts()]
            )
            self._branch_filter.set_items(
                [(f"{b.branch_number}. {b.name}", b.id) for b in branch_repo.list_all()]
            )
            self._fill_combo(
                self._category_combo, [(c.name, c.id) for c in category_repo.list_all()]
            )

    def _fill_combo(self, combo: QComboBox, items: list[tuple[str, int]]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todos", None)
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _current_report_key(self) -> str:
        return self._type_combo.currentData()

    def _on_report_type_changed(self) -> None:
        key = self._current_report_key()
        self._value_type_combo.setVisible(key in ("consolidated", "branch_day_pivot"))
        if key == "unclassified":
            self._results_stack.setCurrentWidget(self._unclassified_table)
        elif key == "consolidated":
            self._results_stack.setCurrentWidget(self._tree)
        elif key == "branch_day_pivot":
            self._results_stack.setCurrentWidget(self._pivot_table)
        elif key == "bank_commissions":
            self._results_stack.setCurrentWidget(self._bank_commissions_table)
        else:
            self._results_stack.setCurrentWidget(self._simple_table)

    def _current_filters(self) -> ReportFilter:
        return ReportFilter(
            date_from=self._date_from.date().toPython(),
            date_to=self._date_to.date().toPython(),
            bank_id=self._bank_combo.currentData(),
            bank_account_id=self._account_combo.currentData(),
            branch_ids=self._branch_filter.checked_values() or None,
            category_id=self._category_combo.currentData(),
        )

    # ------------------------------------------------------------------
    def _on_generate(self) -> None:
        key = self._current_report_key()
        filters = self._current_filters()
        self._current_title = next(lbl for lbl, k in REPORT_TYPES if k == key)
        self._current_filters_snapshot = filters

        with self._database.session_scope() as session:
            if key == "day":
                self._current_rows = report_service.totals_by_day(session, filters)
                self._render_simple_table()
            elif key == "bank":
                self._current_rows = report_service.totals_by_bank(session, filters)
                self._render_simple_table()
            elif key == "account":
                self._current_rows = report_service.totals_by_account(session, filters)
                self._render_simple_table()
            elif key == "branch":
                self._current_rows = report_service.totals_by_branch(session, filters)
                self._render_simple_table()
            elif key == "category":
                self._current_rows = report_service.totals_by_category(session, filters)
                self._render_simple_table()
            elif key == "commissions":
                self._current_rows = report_service.commissions_and_vat(session, filters)
                self._render_simple_table()
            elif key == "bank_commissions":
                self._current_bank_commissions = report_service.commissions_weighted_by_bank(
                    session, filters
                )
                self._render_bank_commissions_table()
            elif key == "unclassified":
                movements = report_service.unclassified_movements(session, filters)
                self._render_unclassified_table(movements)
            elif key == "consolidated":
                value_type = self._value_type_combo.currentData()
                self._current_consolidated = report_service.consolidated_by_date_branch_account(
                    session, filters, value_type
                )
                self._render_consolidated_tree()
            elif key == "branch_day_pivot":
                value_type = self._value_type_combo.currentData()
                self._current_pivot = report_service.branch_day_pivot(session, filters, value_type)
                self._render_branch_day_pivot()

    def _render_simple_table(self) -> None:
        rows = self._current_rows
        self._simple_table.setRowCount(len(rows))
        total_charge = total_payment = 0
        for row_index, row in enumerate(rows):
            values = [
                row.label,
                format_currency(row.charge_cents),
                format_currency(row.payment_cents),
                format_currency(row.net_cents),
            ]
            for col_index, value in enumerate(values):
                self._simple_table.setItem(row_index, col_index, QTableWidgetItem(value))
            total_charge += row.charge_cents
            total_payment += row.payment_cents

        self._totals_label.setText(
            f"Cargo total: {format_currency(total_charge)}  |  "
            f"Abono total: {format_currency(total_payment)}  |  "
            f"Neto: {format_currency(total_payment - total_charge)}"
        )

    @staticmethod
    def _bank_commission_row_values(bank_row) -> list[str]:
        return [
            bank_row.bank_name,
            format_currency(bank_row.commission_cents),
            format_currency(bank_row.vat_cents),
            format_currency(bank_row.total_cents),
            f"{bank_row.weight * 100:.2f}%",
        ]

    def _render_bank_commissions_table(self) -> None:
        report = self._current_bank_commissions
        table = self._bank_commissions_table
        table.clearContents()
        if report is None:
            table.setRowCount(0)
            return

        bold_font = QFont()
        bold_font.setBold(True)
        table.setRowCount(len(report.rows) + 1)
        for row_index, bank_row in enumerate(report.rows):
            for col_index, value in enumerate(self._bank_commission_row_values(bank_row)):
                table.setItem(row_index, col_index, QTableWidgetItem(value))

        total_values = [
            PIVOT_TOTAL_LABEL,
            format_currency(report.commission_cents),
            format_currency(report.vat_cents),
            format_currency(report.total_cents),
            "100.00%" if report.total_cents else "0.00%",
        ]
        for col_index, value in enumerate(total_values):
            item = QTableWidgetItem(value)
            item.setFont(bold_font)
            table.setItem(len(report.rows), col_index, item)

        table.resizeColumnsToContents()
        self._totals_label.setText(
            f"Comisiones: {format_currency(report.commission_cents)}  |  "
            f"IVA: {format_currency(report.vat_cents)}  |  "
            f"Total: {format_currency(report.total_cents)}"
        )

    def _render_unclassified_table(self, movements: list) -> None:
        self._current_unclassified = movements
        self._unclassified_table.setRowCount(len(movements))
        for row_index, movement in enumerate(movements):
            values = self._unclassified_row_values(movement)
            for col_index, value in enumerate(values):
                self._unclassified_table.setItem(row_index, col_index, QTableWidgetItem(value))
        self._totals_label.setText(f"{len(movements)} movimiento(s) sin clasificar.")

    @staticmethod
    def _unclassified_row_values(movement) -> list[str]:
        return [
            format_date_for_display(movement.movement_date),
            movement.bank_account.bank.name if movement.bank_account else "",
            movement.bank_account.alias if movement.bank_account else "",
            movement.description_original,
            format_currency(movement.charge_cents) if movement.charge_cents else "",
            format_currency(movement.payment_cents) if movement.payment_cents else "",
            movement.imported_file.original_name if movement.imported_file else "",
        ]

    def _render_consolidated_tree(self) -> None:
        report = self._current_consolidated
        self._tree.clear()
        if report is None:
            return

        headers = ["Día / Sucursal", *report.account_aliases, "Total"]
        self._tree.setColumnCount(len(headers))
        self._tree.setHeaderLabels(headers)

        for day_group in report.day_groups:
            day_totals = day_group.values_by_account
            day_values = [format_currency(day_totals.get(alias, 0)) for alias in report.account_aliases]
            day_item = QTreeWidgetItem(
                [format_date_for_display(day_group.day), *day_values, format_currency(day_group.total_cents)]
            )
            self._tree.addTopLevelItem(day_item)

            for branch_row in day_group.branch_rows:
                branch_values = [
                    format_currency(branch_row.values_by_account.get(alias, 0))
                    if branch_row.values_by_account.get(alias)
                    else ""
                    for alias in report.account_aliases
                ]
                branch_item = QTreeWidgetItem(
                    [branch_row.branch_label, *branch_values, format_currency(branch_row.total_cents)]
                )
                day_item.addChild(branch_item)

        for column_index in range(self._tree.columnCount()):
            self._tree.resizeColumnToContents(column_index)

        grand_totals = report.grand_totals_by_account
        totals_text = "  |  ".join(
            f"{alias}: {format_currency(grand_totals.get(alias, 0))}" for alias in report.account_aliases
        )
        self._totals_label.setText(f"Total general: {format_currency(report.grand_total_cents)}  |  {totals_text}")

    def _render_branch_day_pivot(self) -> None:
        report = self._current_pivot
        self._pivot_table.clear()
        if report is None:
            self._pivot_table.setRowCount(0)
            self._pivot_table.setColumnCount(0)
            return

        bold_font = QFont()
        bold_font.setBold(True)

        headers = ["Sucursal", *[format_date_for_display(day) for day in report.days], PIVOT_TOTAL_LABEL]
        total_column = len(headers) - 1
        self._pivot_table.setColumnCount(len(headers))
        self._pivot_table.setHorizontalHeaderLabels(headers)
        self._pivot_table.setRowCount(len(report.branch_rows) + 1)

        for row_index, branch_row in enumerate(report.branch_rows):
            self._pivot_table.setItem(row_index, 0, QTableWidgetItem(branch_row.branch_label))
            for col_index, day in enumerate(report.days, start=1):
                value = branch_row.values_by_day.get(day)
                text = format_currency(value) if value else ""
                self._pivot_table.setItem(row_index, col_index, QTableWidgetItem(text))
            total_item = QTableWidgetItem(format_currency(branch_row.total_cents))
            total_item.setFont(bold_font)
            self._pivot_table.setItem(row_index, total_column, total_item)

        totals_row = len(report.branch_rows)
        totals_by_day = report.totals_by_day
        totals_label_item = QTableWidgetItem(PIVOT_TOTAL_LABEL)
        totals_label_item.setFont(bold_font)
        self._pivot_table.setItem(totals_row, 0, totals_label_item)
        for col_index, day in enumerate(report.days, start=1):
            day_total_item = QTableWidgetItem(format_currency(totals_by_day.get(day, 0)))
            day_total_item.setFont(bold_font)
            self._pivot_table.setItem(totals_row, col_index, day_total_item)
        grand_total_item = QTableWidgetItem(format_currency(report.grand_total_cents))
        grand_total_item.setFont(bold_font)
        self._pivot_table.setItem(totals_row, total_column, grand_total_item)

        self._pivot_table.resizeColumnsToContents()
        self._totals_label.setText(f"Total general: {format_currency(report.grand_total_cents)}")

    def _on_pivot_cell_double_clicked(self, row: int, column: int) -> None:
        report = self._current_pivot
        if report is None or row >= len(report.branch_rows):
            return
        total_column = self._pivot_table.columnCount() - 1
        if column <= 0 or column >= total_column:
            return

        branch_row = report.branch_rows[row]
        day = report.days[column - 1]
        if not branch_row.values_by_day.get(day):
            return
        self._show_pivot_cell_detail(branch_row, day)

    def _show_pivot_cell_detail(self, branch_row: BranchPivotRow, day: dt.date) -> None:
        filters = self._current_filters_snapshot or self._current_filters()
        with self._database.session_scope() as session:
            movements = report_service.movements_for_branch_day(
                session, filters, branch_row.branch_id, day
            )
            rows_data = [self._movement_detail_values(m) for m in movements]

        dialog = QDialog(self)
        dialog.setWindowTitle(
            f"Movimientos — {branch_row.branch_label} — {format_date_for_display(day)}"
        )
        dialog.resize(950, 500)
        layout = QVBoxLayout(dialog)

        total = branch_row.values_by_day.get(day, 0)
        summary = QLabel(f"{len(rows_data)} movimiento(s) — Total: {format_currency(total)}")
        layout.addWidget(summary)

        columns = MOVEMENT_DETAIL_COLUMNS
        table = QTableWidget(len(rows_data), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        for row_index, values in enumerate(rows_data):
            for col_index, value in enumerate(values):
                table.setItem(row_index, col_index, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        layout.addWidget(table)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        dialog.exec()

    @staticmethod
    def _movement_detail_values(movement) -> list[str]:
        return [
            format_date_for_display(movement.movement_date),
            movement.bank_account.bank.name if movement.bank_account else "",
            movement.bank_account.alias if movement.bank_account else "",
            movement.description_original,
            format_currency(movement.charge_cents) if movement.charge_cents else "",
            format_currency(movement.payment_cents) if movement.payment_cents else "",
            movement.category.name if movement.category else "",
            movement.imported_file.original_name if movement.imported_file else "",
        ]

    # ------------------------------------------------------------------
    def _on_export(self) -> None:
        key = self._current_report_key()
        filters = self._current_filters()

        if key == "consolidated" and self._current_consolidated is not None:
            default_name = export_service.build_safe_filename(
                "reporte_sucursales", filters.date_from, filters.date_to
            )
            self._save_and_export(
                default_name,
                lambda path: export_service.export_consolidated_report_to_excel(
                    self._current_consolidated,
                    self._value_type_combo.currentText(),
                    filters,
                    path,
                ),
            )
        elif key == "branch_day_pivot" and self._current_pivot is not None:
            default_name = export_service.build_safe_filename(
                "reporte_sucursales_dia", filters.date_from, filters.date_to
            )
            self._save_and_export(
                default_name,
                lambda path: export_service.export_branch_day_pivot_to_excel(
                    self._current_pivot,
                    self._value_type_combo.currentText(),
                    filters,
                    path,
                ),
            )
        elif key == "bank_commissions" and self._current_bank_commissions is not None:
            default_name = export_service.build_safe_filename(
                "comisiones_por_banco", filters.date_from, filters.date_to
            )
            self._save_and_export(
                default_name,
                lambda path: export_service.export_bank_commissions_to_excel(
                    self._current_bank_commissions, filters, path
                ),
            )
        elif key == "unclassified":
            QMessageBox.information(
                self,
                "Exportar",
                "Usa la exportación de la pantalla 'Movimientos' filtrando por "
                "estado 'No clasificado' para obtener el detalle completo.",
            )
        elif self._current_rows:
            default_name = export_service.build_safe_filename(
                self._current_title, filters.date_from, filters.date_to
            )
            self._save_and_export(
                default_name,
                lambda path: export_service.export_simple_report_to_excel(
                    self._current_title, self._current_rows, filters, path
                ),
            )
        else:
            QMessageBox.warning(self, "Sin datos", "Genera el reporte antes de exportarlo.")

    def _save_and_export(self, default_name: str, export_fn) -> None:
        default_path = str(self._config.paths.exports_dir / default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar reporte", default_path, "Excel (*.xlsx)"
        )
        if not file_path:
            return
        if not file_path.endswith(".xlsx"):
            file_path += ".xlsx"
        try:
            export_fn(Path(file_path))
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar", f"No se pudo exportar el archivo: {exc}")
            return
        QMessageBox.information(self, "Exportación completa", "El reporte se exportó correctamente.")

    # ------------------------------------------------------------------
    def _on_print(self) -> None:
        body_html = self._build_report_body_html()
        if body_html is None:
            QMessageBox.warning(self, "Sin datos", "Genera el reporte antes de imprimirlo.")
            return

        document = QTextDocument()
        document.setHtml(REPORT_PRINT_STYLE + self._report_header_html() + body_html)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(f"Vista previa de impresión — {self._current_title}")
        preview.paintRequested.connect(document.print_)
        preview.exec()

    def _report_header_html(self) -> str:
        title = html_lib.escape(self._current_title or "Reporte")
        filters_line = self._filters_summary_html()
        return f'<h1>{title}</h1><div class="filters">{filters_line}</div>'

    def _filters_summary_html(self) -> str:
        filters = self._current_filters_snapshot
        if filters is None:
            return ""
        parts = [
            f"Del {format_date_for_display(filters.date_from)} al {format_date_for_display(filters.date_to)}"
        ]
        bank_label = self._combo_label_for_value(self._bank_combo, filters.bank_id)
        if bank_label:
            parts.append(f"Banco: {bank_label}")
        account_label = self._combo_label_for_value(self._account_combo, filters.bank_account_id)
        if account_label:
            parts.append(f"Cuenta: {account_label}")
        if filters.branch_ids:
            branch_labels = self._branch_filter.checked_labels()
            if branch_labels:
                parts.append(f"Sucursales: {', '.join(branch_labels)}")
        category_label = self._combo_label_for_value(self._category_combo, filters.category_id)
        if category_label:
            parts.append(f"Categoría: {category_label}")
        return " &middot; ".join(html_lib.escape(part) for part in parts)

    @staticmethod
    def _combo_label_for_value(combo: QComboBox, value) -> str | None:
        if value is None:
            return None
        index = combo.findData(value)
        return combo.itemText(index) if index >= 0 else None

    def _build_report_body_html(self) -> str | None:
        key = self._current_report_key()
        if key == "unclassified":
            if not self._current_unclassified:
                return None
            return self._unclassified_report_html()
        if key == "consolidated":
            if self._current_consolidated is None:
                return None
            return self._consolidated_report_html()
        if key == "branch_day_pivot":
            if self._current_pivot is None:
                return None
            return self._branch_day_pivot_html()
        if key == "bank_commissions":
            if self._current_bank_commissions is None:
                return None
            return self._bank_commissions_html()
        if not self._current_rows:
            return None
        return self._simple_report_html()

    def _bank_commissions_html(self) -> str:
        report = self._current_bank_commissions
        header_html = "".join(f"<th>{html_lib.escape(col)}</th>" for col in BANK_COMMISSION_COLUMNS)
        rows_html = []
        for bank_row in report.rows:
            values = self._bank_commission_row_values(bank_row)
            cells = f'<td class="label">{html_lib.escape(values[0])}</td>' + "".join(
                f"<td>{html_lib.escape(value)}</td>" for value in values[1:]
            )
            rows_html.append(f"<tr>{cells}</tr>")
        rows_html.append(
            '<tr class="total">'
            f'<td class="label">{html_lib.escape(PIVOT_TOTAL_LABEL)}</td>'
            f"<td>{html_lib.escape(format_currency(report.commission_cents))}</td>"
            f"<td>{html_lib.escape(format_currency(report.vat_cents))}</td>"
            f"<td>{html_lib.escape(format_currency(report.total_cents))}</td>"
            f"<td>{'100.00%' if report.total_cents else '0.00%'}</td>"
            "</tr>"
        )
        return (
            f"<table><thead><tr>{header_html}</tr></thead><tbody>"
            + "".join(rows_html)
            + "</tbody></table>"
        )

    def _simple_report_html(self) -> str:
        rows_html = []
        total_charge = total_payment = 0
        for row in self._current_rows:
            rows_html.append(
                "<tr>"
                f'<td class="label">{html_lib.escape(row.label)}</td>'
                f"<td>{html_lib.escape(format_currency(row.charge_cents))}</td>"
                f"<td>{html_lib.escape(format_currency(row.payment_cents))}</td>"
                f"<td>{html_lib.escape(format_currency(row.net_cents))}</td>"
                "</tr>"
            )
            total_charge += row.charge_cents
            total_payment += row.payment_cents

        rows_html.append(
            '<tr class="total">'
            '<td class="label">Total</td>'
            f"<td>{html_lib.escape(format_currency(total_charge))}</td>"
            f"<td>{html_lib.escape(format_currency(total_payment))}</td>"
            f"<td>{html_lib.escape(format_currency(total_payment - total_charge))}</td>"
            "</tr>"
        )
        return (
            "<table><thead><tr>"
            "<th>Concepto</th><th>Cargo</th><th>Abono</th><th>Neto</th>"
            "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
        )

    def _unclassified_report_html(self) -> str:
        header_html = "".join(f"<th>{html_lib.escape(col)}</th>" for col in UNCLASSIFIED_COLUMNS)
        rows_html = []
        for movement in self._current_unclassified:
            values = self._unclassified_row_values(movement)
            cells = "".join(f"<td>{html_lib.escape(value)}</td>" for value in values)
            rows_html.append(f"<tr>{cells}</tr>")
        return (
            f"<table><thead><tr>{header_html}</tr></thead><tbody>"
            + "".join(rows_html)
            + "</tbody></table>"
        )

    def _consolidated_report_html(self) -> str:
        report = self._current_consolidated
        headers_html = "<th>Día / Sucursal</th>" + "".join(
            f"<th>{html_lib.escape(alias)}</th>" for alias in report.account_aliases
        ) + "<th>Total</th>"

        rows_html = []
        for day_group in report.day_groups:
            day_totals = day_group.values_by_account
            day_values_html = "".join(
                f"<td>{html_lib.escape(format_currency(day_totals.get(alias, 0)))}</td>"
                for alias in report.account_aliases
            )
            rows_html.append(
                '<tr class="total">'
                f"<td class=\"label\">{html_lib.escape(format_date_for_display(day_group.day))}</td>"
                f"{day_values_html}"
                f"<td>{html_lib.escape(format_currency(day_group.total_cents))}</td>"
                "</tr>"
            )
            for branch_row in day_group.branch_rows:
                branch_values_html = "".join(
                    f"<td>{html_lib.escape(format_currency(branch_row.values_by_account.get(alias, 0)))}</td>"
                    if branch_row.values_by_account.get(alias)
                    else "<td></td>"
                    for alias in report.account_aliases
                )
                rows_html.append(
                    "<tr>"
                    f'<td class="label indent">{html_lib.escape(branch_row.branch_label)}</td>'
                    f"{branch_values_html}"
                    f"<td>{html_lib.escape(format_currency(branch_row.total_cents))}</td>"
                    "</tr>"
                )

        grand_totals = report.grand_totals_by_account
        grand_totals_html = "".join(
            f"<td>{html_lib.escape(format_currency(grand_totals.get(alias, 0)))}</td>"
            for alias in report.account_aliases
        )
        rows_html.append(
            '<tr class="total">'
            '<td class="label">Total general</td>'
            f"{grand_totals_html}"
            f"<td>{html_lib.escape(format_currency(report.grand_total_cents))}</td>"
            "</tr>"
        )
        return (
            f"<table><thead><tr>{headers_html}</tr></thead><tbody>"
            + "".join(rows_html)
            + "</tbody></table>"
        )

    def _branch_day_pivot_html(self) -> str:
        report = self._current_pivot
        headers_html = (
            "<th>Sucursal</th>"
            + "".join(f"<th>{html_lib.escape(format_date_for_display(day))}</th>" for day in report.days)
            + f"<th>{html_lib.escape(PIVOT_TOTAL_LABEL)}</th>"
        )

        rows_html = []
        for branch_row in report.branch_rows:
            day_cells_html = "".join(
                f"<td>{html_lib.escape(format_currency(branch_row.values_by_day.get(day, 0)))}</td>"
                if branch_row.values_by_day.get(day)
                else "<td></td>"
                for day in report.days
            )
            rows_html.append(
                "<tr>"
                f'<td class="label">{html_lib.escape(branch_row.branch_label)}</td>'
                f"{day_cells_html}"
                f"<td>{html_lib.escape(format_currency(branch_row.total_cents))}</td>"
                "</tr>"
            )

        totals_by_day = report.totals_by_day
        totals_row_html = "".join(
            f"<td>{html_lib.escape(format_currency(totals_by_day.get(day, 0)))}</td>" for day in report.days
        )
        rows_html.append(
            '<tr class="total">'
            f'<td class="label">{html_lib.escape(PIVOT_TOTAL_LABEL)}</td>'
            f"{totals_row_html}"
            f"<td>{html_lib.escape(format_currency(report.grand_total_cents))}</td>"
            "</tr>"
        )
        return (
            f"<table><thead><tr>{headers_html}</tr></thead><tbody>"
            + "".join(rows_html)
            + "</tbody></table>"
        )
