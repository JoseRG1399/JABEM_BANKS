"""Diálogo de solo lectura con el detalle completo de un movimiento."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.models import Movement
from app.utils.dates import format_date_for_display
from app.utils.money import format_currency

STATUS_LABELS = {
    "CLASSIFIED": "Clasificado",
    "UNCLASSIFIED": "No clasificado",
    "MANUAL": "Manual",
}

METHOD_LABELS = {
    "SPECIAL_RULE": "Regla especial",
    "BRANCH_IDENTIFIER": "Identificador de sucursal",
    "MANUAL": "Manual",
    "NONE": "Ninguno",
}


class MovementDetailDialog(QDialog):
    def __init__(self, movement: Movement, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detalle del movimiento")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(form.labelAlignment())

        bank_name = movement.bank_account.bank.name if movement.bank_account else "—"
        account_alias = movement.bank_account.alias if movement.bank_account else "—"
        branch_name = movement.branch.name if movement.branch else "—"
        category_name = movement.category.name if movement.category else "—"
        file_name = movement.imported_file.original_name if movement.imported_file else "—"
        balance_text = (
            format_currency(movement.balance_cents) if movement.balance_cents is not None else "—"
        )

        fields = [
            ("Fecha", format_date_for_display(movement.movement_date)),
            ("Banco", bank_name),
            ("Cuenta", account_alias),
            ("Sucursal", branch_name),
            ("Categoría", category_name),
            ("Concepto original", movement.description_original),
            ("Referencia original", movement.reference_original or "—"),
            ("Concepto normalizado", movement.normalized_text),
            ("Folio externo", movement.external_folio or "—"),
            ("Cargo", format_currency(movement.charge_cents)),
            ("Abono", format_currency(movement.payment_cents)),
            ("Saldo", balance_text),
            (
                "Estado de clasificación",
                STATUS_LABELS.get(movement.classification_status, movement.classification_status),
            ),
            (
                "Método de clasificación",
                METHOD_LABELS.get(movement.classification_method, movement.classification_method),
            ),
            ("Identificador detectado", movement.matched_identifier or "—"),
            ("Archivo de origen", file_name),
            ("Fila de origen", str(movement.source_row_number)),
        ]
        for label_text, value in fields:
            value_label = QLabel(str(value))
            value_label.setWordWrap(True)
            form.addRow(QLabel(label_text + ":"), value_label)

        layout.addLayout(form)

        close_button = QPushButton("Cerrar")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
