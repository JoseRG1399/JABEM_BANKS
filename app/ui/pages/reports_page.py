"""Pantalla de reportes (sección 15.8 de la especificación)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
from app.services.report_service import ConsolidatedReport, ReportRow, ReportValueType
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency

REPORT_TYPES = [
    ("Totales por día", "day"),
    ("Totales por banco", "bank"),
    ("Totales por cuenta", "account"),
    ("Totales por sucursal", "branch"),
    ("Totales por categoría", "category"),
    ("Movimientos sin clasificar", "unclassified"),
    ("Comisiones e IVA", "commissions"),
    ("Tabla consolidada (fecha / sucursal / cuenta)", "consolidated"),
]

VALUE_TYPE_OPTIONS = [
    ("Abono", ReportValueType.PAYMENT),
    ("Cargo", ReportValueType.CHARGE),
    ("Movimiento neto", ReportValueType.NET),
]

UNCLASSIFIED_COLUMNS = ["Fecha", "Banco", "Cuenta", "Concepto / Referencia", "Cargo", "Abono", "Archivo"]


class ReportsPage(QWidget):
    def __init__(self, config: Config, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._database = database
        self._current_rows: list[ReportRow] = []
        self._current_unclassified: list = []
        self._current_consolidated: ConsolidatedReport | None = None
        self._current_title = ""
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
        self._date_from.setDate(dt.date(2000, 1, 1))
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
        self._branch_combo = QComboBox()
        filters_row.addWidget(self._branch_combo)

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
            self._fill_combo(
                self._branch_combo, [(b.name, b.id) for b in branch_repo.list_all()]
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
        self._value_type_combo.setVisible(key == "consolidated")
        if key == "unclassified":
            self._results_stack.setCurrentWidget(self._unclassified_table)
        elif key == "consolidated":
            self._results_stack.setCurrentWidget(self._tree)
        else:
            self._results_stack.setCurrentWidget(self._simple_table)

    def _current_filters(self) -> ReportFilter:
        return ReportFilter(
            date_from=self._date_from.date().toPython(),
            date_to=self._date_to.date().toPython(),
            bank_id=self._bank_combo.currentData(),
            bank_account_id=self._account_combo.currentData(),
            branch_id=self._branch_combo.currentData(),
            category_id=self._category_combo.currentData(),
        )

    # ------------------------------------------------------------------
    def _on_generate(self) -> None:
        key = self._current_report_key()
        filters = self._current_filters()
        self._current_title = next(lbl for lbl, k in REPORT_TYPES if k == key)

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
            elif key == "unclassified":
                movements = report_service.unclassified_movements(session, filters)
                self._render_unclassified_table(movements)
            elif key == "consolidated":
                value_type = self._value_type_combo.currentData()
                self._current_consolidated = report_service.consolidated_by_date_branch_account(
                    session, filters, value_type
                )
                self._render_consolidated_tree()

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

    def _render_unclassified_table(self, movements: list) -> None:
        self._current_unclassified = movements
        self._unclassified_table.setRowCount(len(movements))
        for row_index, movement in enumerate(movements):
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
                self._unclassified_table.setItem(row_index, col_index, QTableWidgetItem(value))
        self._totals_label.setText(f"{len(movements)} movimiento(s) sin clasificar.")

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
