"""Consulta de información de las tiendas mediante la API externa."""
from __future__ import annotations

import datetime as dt
import html as html_lib

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
from app.integrations.store_api import StoreApiClient, resolve_api_host
from app.services import store_report_service as svc
from app.ui.widgets.loading_overlay import LoadingOverlay
from app.ui.workers.store_api_worker import StoreApiWorker
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency

REPORT_UBER = "uber"
REPORT_TRANSFERS = "transfers"
REPORT_TYPES = [
    ("Ventas Uber por sucursal (con detalle)", REPORT_UBER),
    ("Pagos por transferencia", REPORT_TRANSFERS),
]

TRANSFER_COLUMNS = [
    "Fecha y hora",
    "Tipo",
    "Sucursal",
    "Ticket / Nota",
    "Cliente",
    "Turno",
    "Responsable",
    "Productos",
    "Transferencia",
    "Total venta / nota",
]
UBER_COLUMNS = ["Sucursal / Producto", "Cantidad", "Precio", "Total"]

COLLAPSED_MARK = "▶ "
EXPANDED_MARK = "▼ "

PRINT_STYLE = """
<style>
    body { font-family: Arial, sans-serif; font-size: 11pt; color: #000000; }
    h1 { font-size: 14pt; margin: 0 0 4px 0; }
    h2 { font-size: 11pt; margin: 14px 0 2px 0; }
    .filters { font-size: 9pt; color: #333333; margin-bottom: 8px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid #000000; padding: 4px 8px; font-size: 9pt; text-align: left; }
    th { background-color: #dddddd; text-align: center; font-weight: bold; }
    td.num { text-align: right; }
    tr.branch td { font-weight: bold; background-color: #eeeeee; }
    tr.total td { font-weight: bold; background-color: #dddddd; }
</style>
"""


def _esc(value: object) -> str:
    return html_lib.escape(str(value))


def _header_html(title: str, date_from: dt.date, date_to: dt.date) -> str:
    printed_at = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return (
        f"<h1>{_esc(title)}</h1>"
        f'<div class="filters">Del {_esc(format_date_for_display(date_from))} '
        f"al {_esc(format_date_for_display(date_to))}</div>"
        f'<div class="filters">Impreso el {printed_at}</div>'
    )


def uber_report_html(report: svc.UberSalesReport) -> str:
    """Impresión del reporte Uber: siempre con todo el detalle por sucursal,
    sin importar qué sucursales estén colapsadas en pantalla."""
    rows = []
    for branch in report.branches:
        rows.append(
            f'<tr class="branch"><td>{_esc(branch.branch)}</td><td></td><td></td>'
            f'<td class="num">{_esc(format_currency(branch.total_cents))}</td></tr>'
        )
        for line in branch.lines:
            rows.append(
                f"<tr><td>&nbsp;&nbsp;&nbsp;{_esc(line.product)}</td>"
                f'<td class="num">{line.quantity}</td>'
                f'<td class="num">{_esc(format_currency(line.unit_price_cents))}</td>'
                f'<td class="num">{_esc(format_currency(line.total_cents))}</td></tr>'
            )
    rows.append(
        '<tr class="total"><td>Total general</td><td></td><td></td>'
        f'<td class="num">{_esc(format_currency(report.total_cents))}</td></tr>'
    )
    head = "".join(f"<th>{_esc(c)}</th>" for c in UBER_COLUMNS)
    return f"<table><tr>{head}</tr>{''.join(rows)}</table>"


def transfers_report_html(report: svc.TransferPaymentsReport) -> str:
    head = "".join(f"<th>{_esc(c)}</th>" for c in TRANSFER_COLUMNS)
    rows = []
    for sale in report.sales:
        created = sale.created_at.strftime("%d/%m/%Y %H:%M") if sale.created_at else ""
        cells = [
            created,
            sale.kind,
            sale.branch,
            sale.ticket,
            sale.customer,
            sale.shift,
            sale.responsible,
            ", ".join(sale.products),
        ]
        body = "".join(f"<td>{_esc(c)}</td>" for c in cells)
        body += f'<td class="num">{_esc(format_currency(sale.transfer_cents))}</td>'
        body += f'<td class="num">{_esc(format_currency(sale.total_cents))}</td>'
        rows.append(f"<tr>{body}</tr>")
    rows.append(
        f'<tr class="total"><td colspan="8">Total transferencias</td>'
        f'<td class="num">{_esc(format_currency(report.total_transfer_cents))}</td><td></td></tr>'
    )

    summary_rows = "".join(
        f"<tr><td>{_esc(r.branch)}</td>"
        f'<td class="num">{r.sales_count}</td>'
        f'<td class="num">{_esc(format_currency(r.transfer_cents))}</td></tr>'
        for r in report.summary_by_branch()
    )
    return (
        f"<table><tr>{head}</tr>{''.join(rows)}</table>"
        "<h2>Resumen por sucursal</h2>"
        "<table><tr><th>Sucursal</th><th>Ventas</th><th>Transferencia</th></tr>"
        f"{summary_rows}</table>"
    )


class StoresPage(QWidget):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._worker: StoreApiWorker | None = None
        self._current_report: object | None = None
        self._current_title = ""
        self._current_period: tuple[dt.date, dt.date] | None = None
        self._pending_title = ""
        self._pending_period: tuple[dt.date, dt.date] | None = None
        self._build_ui()
        self._on_report_type_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Tiendas")
        title.setObjectName("appTitle")
        outer.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(QLabel("Consulta:"))
        self._type_combo = QComboBox()
        for label, key in REPORT_TYPES:
            self._type_combo.addItem(label, key)
        self._type_combo.currentIndexChanged.connect(self._on_report_type_changed)
        row.addWidget(self._type_combo)

        row.addWidget(QLabel("Desde:"))
        self._date_from = QDateEdit(calendarPopup=True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(dt.date.today())
        row.addWidget(self._date_from)

        row.addWidget(QLabel("Hasta:"))
        self._date_to = QDateEdit(calendarPopup=True)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setDate(dt.date.today())
        row.addWidget(self._date_to)

        self._query_button = QPushButton("Consultar")
        self._query_button.setObjectName("primaryButton")
        self._query_button.clicked.connect(self._on_query)
        row.addWidget(self._query_button)

        self._print_button = QPushButton("Imprimir")
        self._print_button.setObjectName("infoButton")
        self._print_button.clicked.connect(self._on_print)
        row.addWidget(self._print_button)

        self._collapse_button = QPushButton("Colapsar todo")
        self._collapse_button.clicked.connect(self._collapse_all)
        row.addWidget(self._collapse_button)

        self._expand_button = QPushButton("Expandir todo")
        self._expand_button.clicked.connect(self._expand_all)
        row.addWidget(self._expand_button)
        row.addStretch()
        outer.addLayout(row)

        self._stack = QStackedWidget()

        self._uber_tree = QTreeWidget()
        self._uber_tree.setColumnCount(len(UBER_COLUMNS))
        self._uber_tree.setHeaderLabels(UBER_COLUMNS)
        self._uber_tree.setColumnWidth(0, 360)
        # El clic en la fila de la sucursal despliega/colapsa su detalle; el
        # indicador del sistema se reemplaza por ▶/▼ para no alternar dos veces.
        self._uber_tree.setRootIsDecorated(False)
        self._uber_tree.setExpandsOnDoubleClick(False)
        self._uber_tree.itemClicked.connect(self._on_uber_item_clicked)
        self._uber_tree.itemExpanded.connect(lambda item: self._set_mark(item, True))
        self._uber_tree.itemCollapsed.connect(lambda item: self._set_mark(item, False))
        self._stack.addWidget(self._uber_tree)

        self._transfers_page = QWidget()
        transfers_layout = QVBoxLayout(self._transfers_page)
        transfers_layout.setContentsMargins(0, 0, 0, 0)
        self._transfer_table = QTableWidget(0, len(TRANSFER_COLUMNS))
        self._transfer_table.setHorizontalHeaderLabels(TRANSFER_COLUMNS)
        self._transfer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._transfer_table.horizontalHeader().setStretchLastSection(True)
        transfers_layout.addWidget(self._transfer_table, stretch=3)
        transfers_layout.addWidget(QLabel("Resumen por sucursal"))
        self._transfer_summary = QTableWidget(0, 3)
        self._transfer_summary.setHorizontalHeaderLabels(["Sucursal", "Ventas", "Transferencia"])
        self._transfer_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._transfer_summary.horizontalHeader().setStretchLastSection(True)
        transfers_layout.addWidget(self._transfer_summary, stretch=1)
        self._stack.addWidget(self._transfers_page)

        outer.addWidget(self._stack, stretch=1)

        self._totals_label = QLabel("")
        self._totals_label.setObjectName("cardLabel")
        outer.addWidget(self._totals_label)

        self._overlay = LoadingOverlay("Consultando la API…", self)

    # ------------------------------------------------------------------
    def _on_report_type_changed(self) -> None:
        is_uber = self._type_combo.currentData() == REPORT_UBER
        self._stack.setCurrentWidget(self._uber_tree if is_uber else self._transfers_page)
        self._collapse_button.setVisible(is_uber)
        self._expand_button.setVisible(is_uber)
        self._totals_label.setText("")

    def _on_query(self) -> None:
        date_from = self._date_from.date().toPython()
        date_to = self._date_to.date().toPython()
        if date_from > date_to:
            QMessageBox.warning(self, "Fechas inválidas", "La fecha inicial no puede ser posterior a la final.")
            return

        host = resolve_api_host(self._config.settings.store_api_host)
        if self._type_combo.currentData() == REPORT_UBER:
            fetch, parse = StoreApiClient.get_uber_sales, svc.parse_uber_sales
        else:
            fetch, parse = StoreApiClient.get_transfer_payments, svc.parse_transfer_payments
        self._pending_title = self._type_combo.currentText()
        self._pending_period = (date_from, date_to)

        self._query_button.setEnabled(False)
        self._overlay.show_overlay()
        self._worker = StoreApiWorker(host, fetch, parse, date_from, date_to, self)
        self._worker.finished_ok.connect(self._on_result)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _finish_query(self) -> None:
        self._overlay.hide_overlay()
        self._query_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self._finish_query()
        QMessageBox.warning(self, "No se pudo consultar la API", message)

    def _on_result(self, report: object) -> None:
        self._finish_query()
        self._current_report = report
        self._current_title = self._pending_title
        self._current_period = self._pending_period
        if isinstance(report, svc.UberSalesReport):
            self._render_uber(report)
        else:
            self._render_transfers(report)

    # ------------------------------------------------------------------
    def _on_print(self) -> None:
        report = self._current_report
        expected = (
            svc.UberSalesReport
            if self._type_combo.currentData() == REPORT_UBER
            else svc.TransferPaymentsReport
        )
        if not isinstance(report, expected) or self._current_period is None:
            QMessageBox.warning(self, "Sin datos", "Consulta la información antes de imprimirla.")
            return

        body = (
            uber_report_html(report)
            if isinstance(report, svc.UberSalesReport)
            else transfers_report_html(report)
        )
        date_from, date_to = self._current_period
        document = QTextDocument()
        document.setHtml(PRINT_STYLE + _header_html(self._current_title, date_from, date_to) + body)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(f"Vista previa de impresión — {self._current_title}")
        preview.paintRequested.connect(document.print_)
        preview.exec()

    # ------------------------------------------------------------------
    @staticmethod
    def _set_mark(item: QTreeWidgetItem, expanded: bool) -> None:
        text = item.text(0)
        for mark in (COLLAPSED_MARK, EXPANDED_MARK):
            if text.startswith(mark):
                text = text[len(mark):]
                break
        item.setText(0, (EXPANDED_MARK if expanded else COLLAPSED_MARK) + text)

    def _on_uber_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.childCount():
            item.setExpanded(not item.isExpanded())

    def _collapse_all(self) -> None:
        self._uber_tree.collapseAll()

    def _expand_all(self) -> None:
        self._uber_tree.expandAll()

    # ------------------------------------------------------------------
    def _render_uber(self, report: svc.UberSalesReport) -> None:
        self._uber_tree.clear()
        for branch in report.branches:
            parent = QTreeWidgetItem(
                [COLLAPSED_MARK + branch.branch, "", "", format_currency(branch.total_cents)]
            )
            font = parent.font(0)
            font.setBold(True)
            for column in range(len(UBER_COLUMNS)):
                parent.setFont(column, font)
            for line in branch.lines:
                parent.addChild(
                    QTreeWidgetItem(
                        [
                            line.product,
                            str(line.quantity),
                            format_currency(line.unit_price_cents),
                            format_currency(line.total_cents),
                        ]
                    )
                )
            for column in (1, 2, 3):
                parent.setTextAlignment(column, Qt.AlignmentFlag.AlignRight)
            self._uber_tree.addTopLevelItem(parent)
        # Por defecto se ve el resumen por sucursal; clic en una para ver su detalle.
        self._uber_tree.collapseAll()
        self._totals_label.setText(
            f"Total general Uber: {format_currency(report.total_cents)}"
            if report.branches
            else "Sin ventas de Uber en el periodo."
        )

    def _render_transfers(self, report: svc.TransferPaymentsReport) -> None:
        table = self._transfer_table
        table.setRowCount(len(report.sales))
        for row, sale in enumerate(report.sales):
            created = sale.created_at.strftime("%d/%m/%Y %H:%M") if sale.created_at else ""
            values = [
                created,
                sale.kind,
                sale.branch,
                sale.ticket,
                sale.customer,
                sale.shift,
                sale.responsible,
                ", ".join(sale.products),
                format_currency(sale.transfer_cents),
                format_currency(sale.total_cents),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= len(values) - 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, column, item)

        summary = report.summary_by_branch()
        self._transfer_summary.setRowCount(len(summary))
        for row, entry in enumerate(summary):
            self._transfer_summary.setItem(row, 0, QTableWidgetItem(entry.branch))
            self._transfer_summary.setItem(row, 1, QTableWidgetItem(str(entry.sales_count)))
            amount = QTableWidgetItem(format_currency(entry.transfer_cents))
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._transfer_summary.setItem(row, 2, amount)

        self._totals_label.setText(
            f"{len(report.sales)} pago(s) por transferencia (ventas y abonos de notas) · "
            f"Total: {format_currency(report.total_transfer_cents)}"
            if report.sales
            else "Sin pagos por transferencia en el periodo."
        )
