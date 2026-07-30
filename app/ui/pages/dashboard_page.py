"""Página de inicio: métricas generales, gráficas y accesos rápidos."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtCharts import (
        QBarCategoryAxis,
        QBarSeries,
        QBarSet,
        QChart,
        QChartView,
        QPieSeries,
        QValueAxis,
    )

    QTCHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - entorno sin el módulo QtCharts
    QTCHARTS_AVAILABLE = False

from app.database.session import Database
from app.repositories.imported_file_repository import ImportedFileRepository
from app.repositories.movement_repository import MovementRepository
from app.ui.widgets.metric_card import MetricCard
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency

QUICK_RANGES: dict[str, int | None] = {
    "Este mes": 30,
    "Últimos 90 días": 90,
    "Todo": None,
}


class DashboardPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database = database
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Inicio")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("Periodo:"))
        self._range_combo = QComboBox()
        self._range_combo.addItems(list(QUICK_RANGES.keys()))
        self._range_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self._range_combo)
        outer.addLayout(header)

        cards_row = QHBoxLayout()
        self._card_total_movements = MetricCard("Movimientos totales")
        self._card_total_files = MetricCard("Archivos importados")
        self._card_unclassified = MetricCard("Movimientos sin clasificar")
        self._card_charges = MetricCard("Cargos del periodo")
        self._card_payments = MetricCard("Abonos del periodo")
        for card in (
            self._card_total_movements,
            self._card_total_files,
            self._card_unclassified,
            self._card_charges,
            self._card_payments,
        ):
            cards_row.addWidget(card)
        outer.addLayout(cards_row)

        quick_access = QPushButton("Ver movimientos sin clasificar →")
        quick_access.clicked.connect(self._go_to_unclassified)
        outer.addWidget(quick_access, alignment=Qt.AlignmentFlag.AlignLeft)

        charts_row = QHBoxLayout()
        self._cash_flow_chart_layout = QVBoxLayout()
        self._cash_flow_chart_layout.addWidget(QLabel("Cargos vs abonos por día"))
        charts_row.addLayout(self._cash_flow_chart_layout, 2)

        self._distribution_chart_layout = QVBoxLayout()
        self._distribution_chart_layout.addWidget(QLabel("Distribución por cuenta"))
        charts_row.addLayout(self._distribution_chart_layout, 1)
        outer.addLayout(charts_row, stretch=1)

        outer.addWidget(QLabel("Últimas importaciones"))
        self._recent_imports_list = QListWidget()
        self._recent_imports_list.setMaximumHeight(140)
        outer.addWidget(self._recent_imports_list)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _go_to_unclassified(self) -> None:
        window = self.window()
        if hasattr(window, "navigate_to"):
            window.navigate_to("unclassified")

    def refresh(self) -> None:
        days = QUICK_RANGES[self._range_combo.currentText()]
        date_from = dt.date.today() - dt.timedelta(days=days) if days else None

        with self._database.session_scope() as session:
            movement_repo = MovementRepository(session)
            file_repo = ImportedFileRepository(session)

            self._card_total_movements.set_value(str(movement_repo.count_all()))
            self._card_total_files.set_value(str(file_repo.count_all()))
            self._card_unclassified.set_value(str(movement_repo.count_unclassified()))

            charge_cents, payment_cents = movement_repo.sum_totals_for_period(date_from, None)
            self._card_charges.set_value(format_currency(charge_cents))
            self._card_payments.set_value(format_currency(payment_cents))

            self._recent_imports_list.clear()
            for imported_file in file_repo.list_recent(5):
                text = (
                    f"{imported_file.original_name} — "
                    f"{format_date_for_display(imported_file.imported_at.date())} — "
                    f"{imported_file.inserted_rows} nuevos"
                )
                self._recent_imports_list.addItem(QListWidgetItem(text))

            self._render_cash_flow_chart(
                movement_repo.sum_charges_and_payments_by_day(date_from, None)
            )
            self._render_distribution_chart(movement_repo.sum_by_account(date_from, None))

    def _render_cash_flow_chart(self, data: list[tuple[dt.date, int, int]]) -> None:
        _clear_layout(self._cash_flow_chart_layout, keep_first=True)
        if not QTCHARTS_AVAILABLE or not data:
            self._cash_flow_chart_layout.addWidget(QLabel("Sin datos suficientes para graficar."))
            return

        charges = QBarSet("Cargos")
        payments = QBarSet("Abonos")
        categories: list[str] = []
        for day, charge_cents, payment_cents in data:
            charges.append(charge_cents / 100)
            payments.append(payment_cents / 100)
            categories.append(day.strftime("%d/%m"))

        series = QBarSeries()
        series.append(charges)
        series.append(payments)

        chart = QChart()
        chart.addSeries(series)
        chart.legend().setVisible(True)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart_view = QChartView(chart)
        chart_view.setMinimumHeight(220)
        self._cash_flow_chart_layout.addWidget(chart_view)

    def _render_distribution_chart(self, data: list[tuple[str, int]]) -> None:
        _clear_layout(self._distribution_chart_layout, keep_first=True)
        non_zero_data = [(label, cents) for label, cents in data if cents]
        if not QTCHARTS_AVAILABLE or not non_zero_data:
            self._distribution_chart_layout.addWidget(
                QLabel("Sin datos suficientes para graficar.")
            )
            return

        series = QPieSeries()
        for label, cents in non_zero_data:
            series.append(label, cents / 100)

        chart = QChart()
        chart.addSeries(series)
        chart.legend().setVisible(True)

        chart_view = QChartView(chart)
        chart_view.setMinimumHeight(220)
        self._distribution_chart_layout.addWidget(chart_view)


def _clear_layout(layout, keep_first: bool = False) -> None:
    start_index = 1 if keep_first else 0
    while layout.count() > start_index:
        item = layout.takeAt(start_index)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
