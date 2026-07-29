"""Pantalla de reglas de clasificación (sección 15.7 de la especificación)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import MatchType
from app.database.session import Database
from app.repositories.rule_repository import RuleRepository
from app.ui.dialogs.rule_dialog import RuleDialog

COLUMNS = ["Nombre", "Patrón", "Tipo", "Banco / Cuenta", "Categoría", "Sucursal", "Prioridad", "Estado"]

MATCH_TYPE_LABELS = {
    MatchType.CONTAINS.value: "Contiene",
    MatchType.STARTS_WITH.value: "Empieza con",
    MatchType.ENDS_WITH.value: "Termina con",
    MatchType.EXACT.value: "Igual a",
    MatchType.REGEX.value: "Expresión regular",
}


class RulesPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database = database
        self._row_rule_ids: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Reglas de clasificación")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch()

        new_button = QPushButton("Nueva regla")
        new_button.setObjectName("primaryButton")
        new_button.clicked.connect(self._on_new_rule)
        header.addWidget(new_button)
        outer.addLayout(header)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        outer.addWidget(self._table, stretch=1)

        actions_row = QHBoxLayout()
        self._toggle_button = QPushButton("Activar / Desactivar seleccionada")
        self._toggle_button.setEnabled(False)
        self._toggle_button.clicked.connect(self._on_toggle_active)
        actions_row.addWidget(self._toggle_button)
        actions_row.addStretch()
        outer.addLayout(actions_row)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)

    def refresh(self) -> None:
        with self._database.session_scope() as session:
            rule_repo = RuleRepository(session)
            rules = rule_repo.list_all()

            self._table.setRowCount(len(rules))
            self._row_rule_ids = []
            for row_index, rule in enumerate(rules):
                self._row_rule_ids.append(rule.id)
                account_label = rule.bank_account.alias if rule.bank_account else "Todas"
                category_label = rule.category.name if rule.category else "—"
                branch_label = rule.branch.name if rule.branch else "—"
                values = [
                    rule.name,
                    rule.pattern,
                    MATCH_TYPE_LABELS.get(rule.match_type, rule.match_type),
                    account_label,
                    category_label,
                    branch_label,
                    str(rule.priority),
                    "Activa" if rule.active else "Inactiva",
                ]
                for col_index, value in enumerate(values):
                    self._table.setItem(row_index, col_index, QTableWidgetItem(value))

        self._on_selection_changed()

    def _selected_rule_id(self) -> int | None:
        rows = {index.row() for index in self._table.selectedIndexes()}
        if not rows:
            return None
        row = next(iter(rows))
        if row >= len(self._row_rule_ids):
            return None
        return self._row_rule_ids[row]

    def _on_selection_changed(self) -> None:
        self._toggle_button.setEnabled(self._selected_rule_id() is not None)

    def _on_new_rule(self) -> None:
        dialog = RuleDialog(self._database, rule_id=None, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if row >= len(self._row_rule_ids):
            return
        dialog = RuleDialog(self._database, rule_id=self._row_rule_ids[row], parent=self)
        if dialog.exec():
            self.refresh()

    def _on_toggle_active(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            return
        with self._database.session_scope() as session:
            rule_repo = RuleRepository(session)
            rule = rule_repo.get_by_id(rule_id)
            if rule is None:
                return
            rule.active = not rule.active
            new_state = "activada" if rule.active else "desactivada"

        QMessageBox.information(self, "Regla actualizada", f"La regla fue {new_state}.")
        self.refresh()
