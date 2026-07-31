"""Diálogo de reclasificación manual (sección 14 de la especificación).

Permite asignar sucursal/categoría a uno o varios movimientos, con la
opción de crear una regla para futuros movimientos, probarla antes de
guardar y confirmar antes de aplicarla retroactivamente a movimientos ya
existentes que coincidan con el patrón.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.constants import ClassificationStatus, MatchType
from app.database.session import Database
from app.models import Movement
from app.repositories.bank_repository import BankRepository
from app.repositories.branch_repository import BranchRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.movement_repository import MovementRepository
from app.services.classification_service import (
    ReclassifyRequest,
    count_matching_movements,
    reclassify_movements,
)

MATCH_TYPE_LABELS = [
    ("Contiene", MatchType.CONTAINS.value),
    ("Empieza con", MatchType.STARTS_WITH.value),
    ("Termina con", MatchType.ENDS_WITH.value),
    ("Igual a", MatchType.EXACT.value),
    ("Expresión regular", MatchType.REGEX.value),
]


class ClassifyMovementDialog(QDialog):
    def __init__(
        self, database: Database, movement_ids: list[int], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._database = database
        self._movement_ids = movement_ids
        self._already_classified_count = 0
        self.setWindowTitle("Reclasificar movimiento(s)")
        self.setMinimumWidth(480)

        self._build_ui()
        self._load_data()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._summary_label = QLabel(f"{len(self._movement_ids)} movimiento(s) seleccionado(s).")
        self._summary_label.setObjectName("cardLabel")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        self._preview_list = QListWidget()
        self._preview_list.setMaximumHeight(90)
        layout.addWidget(self._preview_list)

        form = QFormLayout()
        self._branch_combo = QComboBox()
        form.addRow("Sucursal:", self._branch_combo)

        self._category_combo = QComboBox()
        form.addRow("Categoría:", self._category_combo)

        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("Opcional")
        form.addRow("Nota:", self._note_edit)
        layout.addLayout(form)

        self._create_rule_checkbox = QCheckBox("Crear una regla para futuros movimientos")
        self._create_rule_checkbox.toggled.connect(self._on_toggle_create_rule)
        layout.addWidget(self._create_rule_checkbox)

        self._rule_form_container = QWidget()
        rule_form = QFormLayout(self._rule_form_container)

        self._rule_name_edit = QLineEdit()
        rule_form.addRow("Nombre de la regla:", self._rule_name_edit)

        self._rule_pattern_edit = QLineEdit()
        rule_form.addRow("Patrón:", self._rule_pattern_edit)

        self._rule_match_type_combo = QComboBox()
        for label, value in MATCH_TYPE_LABELS:
            self._rule_match_type_combo.addItem(label, value)
        rule_form.addRow("Tipo de coincidencia:", self._rule_match_type_combo)

        self._rule_case_sensitive_checkbox = QCheckBox("Distinguir mayúsculas/minúsculas")
        rule_form.addRow("", self._rule_case_sensitive_checkbox)

        self._rule_account_combo = QComboBox()
        rule_form.addRow("Aplicar solo a la cuenta:", self._rule_account_combo)

        self._rule_priority_spin = QSpinBox()
        self._rule_priority_spin.setRange(1, 9999)
        self._rule_priority_spin.setValue(100)
        rule_form.addRow("Prioridad:", self._rule_priority_spin)

        test_row = QHBoxLayout()
        self._test_button = QPushButton("Probar regla")
        self._test_button.clicked.connect(self._on_test_rule)
        self._test_result_label = QLabel("")
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._test_result_label)
        rule_form.addRow(test_row)

        layout.addWidget(self._rule_form_container)
        self._rule_form_container.setVisible(False)

        buttons_row = QFormLayout()
        self._save_button = QPushButton("Guardar")
        self._save_button.setObjectName("primaryButton")
        self._save_button.clicked.connect(self._on_save)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons_row.addRow(cancel_button, self._save_button)
        layout.addLayout(buttons_row)

    def _on_toggle_create_rule(self, checked: bool) -> None:
        self._rule_form_container.setVisible(checked)

    # ------------------------------------------------------------------
    def _load_data(self) -> None:
        with self._database.session_scope() as session:
            movement_repo = MovementRepository(session)
            branch_repo = BranchRepository(session)
            category_repo = CategoryRepository(session)
            bank_repo = BankRepository(session)

            self._branch_combo.addItem("Sin sucursal", None)
            for branch in branch_repo.list_all():
                self._branch_combo.addItem(branch.name, branch.id)

            for category in category_repo.list_all():
                self._category_combo.addItem(category.name, category.id)

            self._rule_account_combo.addItem("Todas las cuentas", None)
            for account in bank_repo.list_accounts():
                self._rule_account_combo.addItem(account.alias, account.id)

            first_bank_account_id: int | None = None
            for movement_id in self._movement_ids:
                movement: Movement | None = movement_repo.get_by_id(movement_id)
                if movement is None:
                    continue
                if movement.classification_status != ClassificationStatus.UNCLASSIFIED.value:
                    self._already_classified_count += 1
                if first_bank_account_id is None:
                    first_bank_account_id = movement.bank_account_id
                self._preview_list.addItem(
                    f"{movement.description_original} "
                    f"({movement.movement_date.strftime('%d/%m/%Y')})"
                )
                if not self._rule_pattern_edit.text():
                    self._rule_pattern_edit.setText(movement.normalized_text.split(" ")[0])

            if first_bank_account_id is not None:
                index = self._rule_account_combo.findData(first_bank_account_id)
                if index >= 0:
                    self._rule_account_combo.setCurrentIndex(index)

        if self._already_classified_count:
            self._summary_label.setText(
                f"{len(self._movement_ids)} movimiento(s) seleccionado(s) — "
                f"{self._already_classified_count} ya tienen una clasificación asignada. "
                "Guardar sobrescribirá su sucursal/categoría actual."
            )
            self._summary_label.setObjectName("statusWarning")
            self._summary_label.style().unpolish(self._summary_label)
            self._summary_label.style().polish(self._summary_label)

    # ------------------------------------------------------------------
    def _on_test_rule(self) -> None:
        pattern = self._rule_pattern_edit.text().strip()
        if not pattern:
            QMessageBox.warning(self, "Patrón requerido", "Escribe un patrón para probar.")
            return
        match_type = self._rule_match_type_combo.currentData()
        case_sensitive = self._rule_case_sensitive_checkbox.isChecked()
        bank_account_id = self._rule_account_combo.currentData()

        with self._database.session_scope() as session:
            try:
                count = count_matching_movements(
                    session, pattern, match_type, case_sensitive, bank_account_id
                )
            except Exception as exc:  # noqa: BLE001 - patrón regex inválido, por ejemplo
                QMessageBox.critical(self, "Patrón inválido", str(exc))
                return

        self._test_result_label.setText(f"{count} movimiento(s) existentes coincidirían.")

    def _on_save(self) -> None:
        create_rule = self._create_rule_checkbox.isChecked()
        rule_pattern = self._rule_pattern_edit.text().strip()

        if create_rule and not rule_pattern:
            QMessageBox.warning(
                self, "Patrón requerido", "Escribe un patrón para la nueva regla."
            )
            return

        if self._already_classified_count:
            answer = QMessageBox.question(
                self,
                "Confirmar reclasificación",
                f"{self._already_classified_count} de los {len(self._movement_ids)} "
                "movimiento(s) seleccionados ya tienen una sucursal/categoría asignada. "
                "Esta acción sobrescribirá su clasificación actual y no se puede deshacer "
                "automáticamente. ¿Deseas continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        request = ReclassifyRequest(
            movement_ids=self._movement_ids,
            branch_id=self._branch_combo.currentData(),
            category_id=self._category_combo.currentData(),
            note=self._note_edit.text().strip() or None,
            create_rule=create_rule,
            rule_name=self._rule_name_edit.text().strip() or None,
            rule_pattern=rule_pattern or None,
            rule_match_type=self._rule_match_type_combo.currentData(),
            rule_case_sensitive=self._rule_case_sensitive_checkbox.isChecked(),
            rule_bank_account_id=self._rule_account_combo.currentData(),
            rule_priority=self._rule_priority_spin.value(),
        )

        if create_rule:
            with self._database.session_scope() as session:
                preview_count = count_matching_movements(
                    session,
                    request.rule_pattern,
                    request.rule_match_type,
                    request.rule_case_sensitive,
                    request.rule_bank_account_id,
                )
            remaining = max(preview_count - len(self._movement_ids), 0)
            if remaining > 0:
                answer = QMessageBox.question(
                    self,
                    "Confirmar reclasificación retroactiva",
                    f"La nueva regla también coincide con aproximadamente {remaining} "
                    "movimiento(s) ya existentes. ¿Deseas reclasificarlos también?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

        with self._database.session_scope() as session:
            result = reclassify_movements(session, request)

        QMessageBox.information(
            self,
            "Reclasificación completada",
            f"Se actualizaron {len(result.updated_movement_ids)} movimiento(s) seleccionado(s)"
            + (
                f" y {result.retroactive_count} movimiento(s) adicionales por la nueva regla."
                if result.retroactive_count
                else "."
            ),
        )
        self.accept()
