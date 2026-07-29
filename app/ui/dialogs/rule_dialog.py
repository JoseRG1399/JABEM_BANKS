"""Diálogo de creación/edición de reglas de clasificación
(sección 15.7 de la especificación)."""
from __future__ import annotations

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
    QVBoxLayout,
    QWidget,
)

from app.constants import MatchType
from app.database.session import Database
from app.models import ClassificationRule
from app.repositories.bank_repository import BankRepository
from app.repositories.branch_repository import BranchRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.rule_repository import RuleRepository
from app.services.classification_service import count_matching_movements, rule_matches_text
from app.utils.text import normalize_text

MATCH_TYPE_LABELS = [
    ("Contiene", MatchType.CONTAINS.value),
    ("Empieza con", MatchType.STARTS_WITH.value),
    ("Termina con", MatchType.ENDS_WITH.value),
    ("Igual a", MatchType.EXACT.value),
    ("Expresión regular", MatchType.REGEX.value),
]


class RuleDialog(QDialog):
    def __init__(
        self, database: Database, rule_id: int | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._rule_id = rule_id
        self.setWindowTitle("Editar regla" if rule_id else "Nueva regla")
        self.setMinimumWidth(480)

        self._build_ui()
        self._load_lookups()
        if rule_id is not None:
            self._load_rule(rule_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit()
        form.addRow("Nombre:", self._name_edit)

        self._pattern_edit = QLineEdit()
        form.addRow("Patrón:", self._pattern_edit)

        self._match_type_combo = QComboBox()
        for label, value in MATCH_TYPE_LABELS:
            self._match_type_combo.addItem(label, value)
        form.addRow("Tipo de coincidencia:", self._match_type_combo)

        self._case_sensitive_checkbox = QCheckBox("Distinguir mayúsculas/minúsculas")
        form.addRow("", self._case_sensitive_checkbox)

        self._account_combo = QComboBox()
        form.addRow("Cuenta bancaria:", self._account_combo)

        self._category_combo = QComboBox()
        form.addRow("Categoría:", self._category_combo)

        self._branch_combo = QComboBox()
        form.addRow("Sucursal:", self._branch_combo)

        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(1, 9999)
        self._priority_spin.setValue(100)
        form.addRow("Prioridad:", self._priority_spin)

        self._active_checkbox = QCheckBox("Activa")
        self._active_checkbox.setChecked(True)
        form.addRow("", self._active_checkbox)

        layout.addLayout(form)

        layout.addWidget(QLabel("Probar regla"))
        test_row = QHBoxLayout()
        self._test_text_edit = QLineEdit()
        self._test_text_edit.setPlaceholderText("Texto de ejemplo del concepto…")
        test_row.addWidget(self._test_text_edit)
        test_button = QPushButton("Probar")
        test_button.clicked.connect(self._on_test_pattern)
        test_row.addWidget(test_button)
        layout.addLayout(test_row)

        count_row = QHBoxLayout()
        count_button = QPushButton("Contar coincidencias en movimientos existentes")
        count_button.clicked.connect(self._on_count_matches)
        count_row.addWidget(count_button)
        layout.addLayout(count_row)

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
    def _load_lookups(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            category_repo = CategoryRepository(session)
            branch_repo = BranchRepository(session)

            self._account_combo.addItem("Todas las cuentas", None)
            for account in bank_repo.list_accounts():
                self._account_combo.addItem(account.alias, account.id)

            for category in category_repo.list_all():
                self._category_combo.addItem(category.name, category.id)

            self._branch_combo.addItem("Ninguna", None)
            for branch in branch_repo.list_all():
                self._branch_combo.addItem(branch.name, branch.id)

    def _load_rule(self, rule_id: int) -> None:
        with self._database.session_scope() as session:
            rule_repo = RuleRepository(session)
            rule = rule_repo.get_by_id(rule_id)
            if rule is None:
                return
            self._name_edit.setText(rule.name)
            self._pattern_edit.setText(rule.pattern)
            index = self._match_type_combo.findData(rule.match_type)
            self._match_type_combo.setCurrentIndex(index if index >= 0 else 0)
            self._case_sensitive_checkbox.setChecked(rule.case_sensitive)

            account_index = self._account_combo.findData(rule.bank_account_id)
            self._account_combo.setCurrentIndex(account_index if account_index >= 0 else 0)

            category_index = self._category_combo.findData(rule.category_id)
            self._category_combo.setCurrentIndex(category_index if category_index >= 0 else 0)

            branch_index = self._branch_combo.findData(rule.branch_id)
            self._branch_combo.setCurrentIndex(branch_index if branch_index >= 0 else 0)

            self._priority_spin.setValue(rule.priority)
            self._active_checkbox.setChecked(rule.active)

    # ------------------------------------------------------------------
    def _on_test_pattern(self) -> None:
        pattern = self._pattern_edit.text().strip()
        sample = self._test_text_edit.text()
        if not pattern or not sample.strip():
            QMessageBox.warning(self, "Datos incompletos", "Escribe un patrón y un texto de ejemplo.")
            return
        try:
            matches = rule_matches_text(
                pattern,
                self._match_type_combo.currentData(),
                self._case_sensitive_checkbox.isChecked(),
                normalize_text(sample),
            )
        except Exception as exc:  # noqa: BLE001 - regex inválida, por ejemplo
            QMessageBox.critical(self, "Patrón inválido", str(exc))
            return

        if matches:
            self._test_result_label.setText("El patrón coincide con el texto de ejemplo.")
            self._test_result_label.setObjectName("statusSuccess")
        else:
            self._test_result_label.setText("El patrón no coincide con el texto de ejemplo.")
            self._test_result_label.setObjectName("statusWarning")
        self._test_result_label.style().unpolish(self._test_result_label)
        self._test_result_label.style().polish(self._test_result_label)

    def _on_count_matches(self) -> None:
        pattern = self._pattern_edit.text().strip()
        if not pattern:
            QMessageBox.warning(self, "Patrón requerido", "Escribe un patrón para contarlo.")
            return
        with self._database.session_scope() as session:
            try:
                count = count_matching_movements(
                    session,
                    pattern,
                    self._match_type_combo.currentData(),
                    self._case_sensitive_checkbox.isChecked(),
                    self._account_combo.currentData(),
                )
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Patrón inválido", str(exc))
                return
        self._test_result_label.setText(f"{count} movimiento(s) existentes coincidirían.")

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        pattern = self._pattern_edit.text().strip()
        if not name or not pattern:
            QMessageBox.warning(self, "Datos incompletos", "Nombre y patrón son obligatorios.")
            return
        if self._category_combo.currentData() is None:
            QMessageBox.warning(self, "Categoría requerida", "Selecciona una categoría.")
            return

        with self._database.session_scope() as session:
            rule_repo = RuleRepository(session)

            if self._rule_id is None:
                rule = ClassificationRule(
                    name=name,
                    category_id=self._category_combo.currentData(),
                    bank_account_id=self._account_combo.currentData(),
                    branch_id=self._branch_combo.currentData(),
                    pattern=pattern,
                    match_type=self._match_type_combo.currentData(),
                    priority=self._priority_spin.value(),
                    case_sensitive=self._case_sensitive_checkbox.isChecked(),
                    active=self._active_checkbox.isChecked(),
                )
                rule_repo.add(rule)
            else:
                rule = rule_repo.get_by_id(self._rule_id)
                if rule is None:
                    return
                rule.name = name
                rule.category_id = self._category_combo.currentData()
                rule.bank_account_id = self._account_combo.currentData()
                rule.branch_id = self._branch_combo.currentData()
                rule.pattern = pattern
                rule.match_type = self._match_type_combo.currentData()
                rule.priority = self._priority_spin.value()
                rule.case_sensitive = self._case_sensitive_checkbox.isChecked()
                rule.active = self._active_checkbox.isChecked()

        self.accept()
