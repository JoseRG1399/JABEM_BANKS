"""Pantalla de sucursales e identificadores (sección 15.6 de la especificación)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import IdentifierType
from app.database.session import Database
from app.repositories.branch_repository import BranchRepository
from app.ui.dialogs.branch_dialog import BranchDialog

COLUMNS = ["Número", "Sucursal", "Banco", "Cuenta", "Identificador", "Tipo", "Prioridad", "Estado"]

IDENTIFIER_TYPE_LABELS = {
    IdentifierType.TERMINAL_SUFFIX.value: "Terminación",
    IdentifierType.REFERENCE.value: "Referencia exacta",
    IdentifierType.CONTAINS.value: "Contiene",
    IdentifierType.EXACT.value: "Igual a",
    IdentifierType.REGEX.value: "Expresión regular",
}


class BranchesPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database = database
        self._row_branch_ids: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Sucursales")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch()

        new_button = QPushButton("Nueva sucursal")
        new_button.setObjectName("primaryButton")
        new_button.clicked.connect(self._on_new_branch)
        header.addWidget(new_button)
        outer.addLayout(header)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Sucursal:"))
        self._branch_filter_combo = QComboBox()
        self._branch_filter_combo.currentIndexChanged.connect(self._load_table)
        filter_row.addWidget(self._branch_filter_combo)

        self._edit_button = QPushButton("Editar sucursal seleccionada")
        self._edit_button.clicked.connect(self._on_edit_selected_branch)
        filter_row.addWidget(self._edit_button)
        filter_row.addStretch()
        outer.addLayout(filter_row)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        outer.addWidget(self._table, stretch=1)

    def refresh(self) -> None:
        self._populate_branch_filter()
        self._load_table()

    def _populate_branch_filter(self) -> None:
        current = self._branch_filter_combo.currentData()
        with self._database.session_scope() as session:
            branch_repo = BranchRepository(session)
            branches = branch_repo.list_all(active_only=False)

        self._branch_filter_combo.blockSignals(True)
        self._branch_filter_combo.clear()
        self._branch_filter_combo.addItem("Todas", None)
        for branch in branches:
            self._branch_filter_combo.addItem(f"{branch.branch_number}. {branch.name}", branch.id)
        index = self._branch_filter_combo.findData(current)
        self._branch_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self._branch_filter_combo.blockSignals(False)

    def _load_table(self) -> None:
        selected_branch_id = self._branch_filter_combo.currentData()
        with self._database.session_scope() as session:
            branch_repo = BranchRepository(session)
            identifiers = branch_repo.list_all_identifiers()

        if selected_branch_id is not None:
            identifiers = [i for i in identifiers if i.branch_id == selected_branch_id]

        self._table.setRowCount(len(identifiers))
        self._row_branch_ids = []
        for row_index, identifier in enumerate(identifiers):
            branch = identifier.branch
            account = identifier.bank_account
            self._row_branch_ids.append(branch.id)
            values = [
                branch.branch_number,
                branch.name,
                account.bank.name if account else "",
                account.alias if account else "",
                identifier.identifier,
                IDENTIFIER_TYPE_LABELS.get(identifier.identifier_type, identifier.identifier_type),
                str(identifier.priority),
                "Activo" if identifier.active else "Inactivo",
            ]
            for col_index, value in enumerate(values):
                self._table.setItem(row_index, col_index, QTableWidgetItem(value))

    def _on_new_branch(self) -> None:
        dialog = BranchDialog(self._database, branch_id=None, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_edit_selected_branch(self) -> None:
        branch_id = self._branch_filter_combo.currentData()
        if branch_id is None:
            return
        dialog = BranchDialog(self._database, branch_id=branch_id, parent=self)
        if dialog.exec():
            self.refresh()

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if row >= len(self._row_branch_ids):
            return
        branch_id = self._row_branch_ids[row]
        dialog = BranchDialog(self._database, branch_id=branch_id, parent=self)
        if dialog.exec():
            self.refresh()
