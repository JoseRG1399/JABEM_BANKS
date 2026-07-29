"""Ventana principal: arma el sidebar y el área de contenido con las páginas."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from app.config import Config
from app.database.session import Database
from app.ui.pages.branches_page import BranchesPage
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.import_page import ImportPage
from app.ui.pages.movements_page import MovementsPage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.rules_page import RulesPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.unclassified_page import UnclassifiedPage
from app.ui.widgets.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, config: Config, database: Database) -> None:
        super().__init__()
        self._config = config
        self._database = database

        self.setWindowTitle(config.settings.app_name)
        self.setMinimumSize(1366, 768)

        central = QWidget()
        central.setObjectName("contentArea")
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar(config.settings.app_name)
        layout.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        self._pages: dict[str, QWidget] = {}
        self._register_page("dashboard", DashboardPage(database))
        self._register_page("import", ImportPage(config, database))
        self._register_page("movements", MovementsPage(database, config=config))
        self._register_page("unclassified", UnclassifiedPage(database, config=config))
        self._register_page("branches", BranchesPage(database))
        self._register_page("rules", RulesPage(database))
        self._register_page("reports", ReportsPage(config, database))
        self._register_page("settings", SettingsPage(config, database))

        self._sidebar.navigate.connect(self._on_navigate)
        self._stack.setCurrentWidget(self._pages["dashboard"])

        import_page = self._pages["import"]
        import_page.import_completed.connect(self._on_import_completed)

    def _register_page(self, key: str, widget: QWidget) -> None:
        self._pages[key] = widget
        self._stack.addWidget(widget)

    def _on_navigate(self, key: str) -> None:
        self._show_page(key)

    def navigate_to(self, key: str) -> None:
        self._sidebar.set_active(key)
        self._show_page(key)

    def _show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh()

    def _on_import_completed(self) -> None:
        self._pages["dashboard"].refresh()
        self._pages["movements"].refresh()
        self._pages["unclassified"].refresh()
