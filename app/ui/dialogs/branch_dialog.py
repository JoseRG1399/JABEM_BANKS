"""Diálogo de creación/edición de sucursal y sus identificadores
(sección 15.6 de la especificación)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import IdentifierType
from app.database.session import Database
from app.models import Branch, BranchIdentifier
from app.repositories.bank_repository import BankRepository
from app.repositories.branch_repository import BranchRepository
from app.services.classification_service import identifier_matches_text
from app.utils.text import normalize_text

IDENTIFIER_TYPE_LABELS = [
    ("Terminación", IdentifierType.TERMINAL_SUFFIX.value),
    ("Referencia exacta", IdentifierType.REFERENCE.value),
    ("Contiene", IdentifierType.CONTAINS.value),
    ("Igual a", IdentifierType.EXACT.value),
    ("Expresión regular", IdentifierType.REGEX.value),
]

IDENTIFIER_COLUMNS = ["Identificador", "Tipo", "Cuenta", "Prioridad", "Activo"]


class BranchDialog(QDialog):
    def __init__(
        self, database: Database, branch_id: int | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._branch_id = branch_id
        self._accounts: list[tuple[str, int]] = []
        self.setWindowTitle("Editar sucursal" if branch_id else "Nueva sucursal")
        self.setMinimumWidth(560)

        self._build_ui()
        self._load_accounts()
        if branch_id is not None:
            self._load_branch(branch_id)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._number_edit = QLineEdit()
        form.addRow("Número:", self._number_edit)

        self._name_edit = QLineEdit()
        form.addRow("Nombre:", self._name_edit)

        self._active_checkbox = QCheckBox("Activa")
        self._active_checkbox.setChecked(True)
        form.addRow("", self._active_checkbox)
        layout.addLayout(form)

        layout.addWidget(QLabel("Identificadores"))
        self._identifiers_table = QTableWidget(0, len(IDENTIFIER_COLUMNS))
        self._identifiers_table.setHorizontalHeaderLabels(IDENTIFIER_COLUMNS)
        self._identifiers_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._identifiers_table)

        add_identifier_button = QPushButton("Agregar identificador")
        add_identifier_button.clicked.connect(lambda: self._add_identifier_row())
        layout.addWidget(add_identifier_button)

        layout.addWidget(QLabel("Probar identificador contra un texto de ejemplo"))
        test_row = QHBoxLayout()
        self._test_text_edit = QLineEdit()
        self._test_text_edit.setPlaceholderText("VENTAS DEBITO/149064102 TERMINALES PUNTO DE VENTA")
        test_row.addWidget(self._test_text_edit)
        test_button = QPushButton("Probar")
        test_button.clicked.connect(self._on_test_identifiers)
        test_row.addWidget(test_button)
        layout.addLayout(test_row)

        self._test_result_label = QLabel("")
        self._test_result_label.setWordWrap(True)
        layout.addWidget(self._test_result_label)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons_row.addWidget(cancel_button)

        save_button = QPushButton("Guardar")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._on_save)
        buttons_row.addWidget(save_button)
        layout.addLayout(buttons_row)

    # ------------------------------------------------------------------
    def _load_accounts(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            self._accounts = [(a.alias, a.id) for a in bank_repo.list_accounts()]

    def _load_branch(self, branch_id: int) -> None:
        with self._database.session_scope() as session:
            branch_repo = BranchRepository(session)
            branch = branch_repo.get_by_id(branch_id)
            if branch is None:
                return
            self._number_edit.setText(branch.branch_number)
            self._name_edit.setText(branch.name)
            self._active_checkbox.setChecked(branch.active)

            for identifier in branch_repo.list_identifiers_for_branch(branch_id):
                self._add_identifier_row(
                    identifier_id=identifier.id,
                    identifier_text=identifier.identifier,
                    identifier_type=identifier.identifier_type,
                    bank_account_id=identifier.bank_account_id,
                    priority=identifier.priority,
                    active=identifier.active,
                )

    # ------------------------------------------------------------------
    def _add_identifier_row(
        self,
        identifier_id: int | None = None,
        identifier_text: str = "",
        identifier_type: str = IdentifierType.TERMINAL_SUFFIX.value,
        bank_account_id: int | None = None,
        priority: int = 100,
        active: bool = True,
    ) -> None:
        row = self._identifiers_table.rowCount()
        self._identifiers_table.insertRow(row)

        identifier_item = QTableWidgetItem(identifier_text)
        identifier_item.setData(Qt.ItemDataRole.UserRole, identifier_id)
        self._identifiers_table.setItem(row, 0, identifier_item)

        type_combo = QComboBox()
        for label, value in IDENTIFIER_TYPE_LABELS:
            type_combo.addItem(label, value)
        index = type_combo.findData(identifier_type)
        type_combo.setCurrentIndex(index if index >= 0 else 0)
        self._identifiers_table.setCellWidget(row, 1, type_combo)

        account_combo = QComboBox()
        for alias, account_id in self._accounts:
            account_combo.addItem(alias, account_id)
        if bank_account_id is not None:
            account_index = account_combo.findData(bank_account_id)
            if account_index >= 0:
                account_combo.setCurrentIndex(account_index)
        self._identifiers_table.setCellWidget(row, 2, account_combo)

        priority_spin = QSpinBox()
        priority_spin.setRange(1, 9999)
        priority_spin.setValue(priority)
        self._identifiers_table.setCellWidget(row, 3, priority_spin)

        active_item = QTableWidgetItem()
        active_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        active_item.setCheckState(Qt.CheckState.Checked if active else Qt.CheckState.Unchecked)
        self._identifiers_table.setItem(row, 4, active_item)

    def _read_identifier_rows(self) -> list[dict]:
        rows = []
        for row in range(self._identifiers_table.rowCount()):
            identifier_item = self._identifiers_table.item(row, 0)
            active_item = self._identifiers_table.item(row, 4)
            type_combo: QComboBox = self._identifiers_table.cellWidget(row, 1)
            account_combo: QComboBox = self._identifiers_table.cellWidget(row, 2)
            priority_spin: QSpinBox = self._identifiers_table.cellWidget(row, 3)

            rows.append(
                {
                    "id": identifier_item.data(Qt.ItemDataRole.UserRole),
                    "identifier": identifier_item.text().strip(),
                    "identifier_type": type_combo.currentData(),
                    "bank_account_id": account_combo.currentData(),
                    "priority": priority_spin.value(),
                    "active": active_item.checkState() == Qt.CheckState.Checked,
                }
            )
        return rows

    def _on_test_identifiers(self) -> None:
        sample = self._test_text_edit.text()
        if not sample.strip():
            return
        normalized = normalize_text(sample)

        matches = []
        for row_data in self._read_identifier_rows():
            if not row_data["identifier"] or not row_data["active"]:
                continue
            if identifier_matches_text(
                row_data["identifier"], row_data["identifier_type"], normalized
            ):
                matches.append(row_data["identifier"])

        if matches:
            self._test_result_label.setText(
                f"Coincide con: {', '.join(matches)}"
            )
            self._test_result_label.setObjectName("statusSuccess")
        else:
            self._test_result_label.setText("Sin coincidencias.")
            self._test_result_label.setObjectName("statusWarning")
        self._test_result_label.style().unpolish(self._test_result_label)
        self._test_result_label.style().polish(self._test_result_label)

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        number = self._number_edit.text().strip()
        name = self._name_edit.text().strip()
        if not number or not name:
            QMessageBox.warning(self, "Datos incompletos", "Número y nombre son obligatorios.")
            return

        identifier_rows = self._read_identifier_rows()
        for row_data in identifier_rows:
            if not row_data["identifier"]:
                QMessageBox.warning(
                    self, "Identificador incompleto", "Todos los identificadores requieren texto."
                )
                return
            if row_data["bank_account_id"] is None:
                QMessageBox.warning(
                    self,
                    "Cuenta requerida",
                    "Todos los identificadores deben asociarse a una cuenta bancaria.",
                )
                return

        # Detectar duplicados dentro de la misma tabla (mismo identificador + cuenta).
        seen: set[tuple[str, int]] = set()
        for row_data in identifier_rows:
            key = (row_data["identifier"], row_data["bank_account_id"])
            if key in seen:
                QMessageBox.warning(
                    self,
                    "Identificador duplicado",
                    f"El identificador '{row_data['identifier']}' está repetido para la misma cuenta.",
                )
                return
            seen.add(key)

        with self._database.session_scope() as session:
            branch_repo = BranchRepository(session)

            existing_by_number = branch_repo.get_by_number(number)
            if existing_by_number is not None and existing_by_number.id != self._branch_id:
                QMessageBox.warning(
                    self, "Número duplicado", f"Ya existe una sucursal con el número '{number}'."
                )
                return

            for row_data in identifier_rows:
                duplicate = branch_repo.find_identifier(
                    row_data["identifier"],
                    row_data["bank_account_id"],
                    exclude_id=row_data["id"],
                )
                if duplicate is not None:
                    QMessageBox.warning(
                        self,
                        "Identificador duplicado",
                        f"El identificador '{row_data['identifier']}' ya está asignado a otra "
                        "sucursal para esa cuenta bancaria.",
                    )
                    return

            if self._branch_id is None:
                branch = Branch(branch_number=number, name=name, active=self._active_checkbox.isChecked())
                branch_repo.add(branch)
                session.flush()
            else:
                branch = branch_repo.get_by_id(self._branch_id)
                branch.branch_number = number
                branch.name = name
                branch.active = self._active_checkbox.isChecked()

            for row_data in identifier_rows:
                if row_data["id"] is not None:
                    identifier = branch_repo.get_identifier_by_id(row_data["id"])
                    if identifier is None:
                        continue
                    identifier.identifier = row_data["identifier"]
                    identifier.identifier_type = row_data["identifier_type"]
                    identifier.bank_account_id = row_data["bank_account_id"]
                    identifier.priority = row_data["priority"]
                    identifier.active = row_data["active"]
                else:
                    new_identifier = BranchIdentifier(
                        branch_id=branch.id,
                        identifier=row_data["identifier"],
                        identifier_type=row_data["identifier_type"],
                        bank_account_id=row_data["bank_account_id"],
                        priority=row_data["priority"],
                        active=row_data["active"],
                    )
                    branch_repo.add_identifier(new_identifier)

        self.accept()
