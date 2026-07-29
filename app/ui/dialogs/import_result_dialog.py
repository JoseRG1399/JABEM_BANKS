"""Diálogo de resumen tras una importación (sección 15.4 de la especificación)."""
from __future__ import annotations

import csv

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.schemas.import_result import ImportResult
from app.utils.text import sanitize_for_spreadsheet

_STATUS_INFO = {
    "SUCCESS": ("Importación completada correctamente.", "statusSuccess"),
    "PARTIAL": ("Importación completada con filas inválidas.", "statusWarning"),
    "FAILED": ("La importación falló: no se pudo insertar ningún movimiento.", "statusError"),
}


class ImportResultDialog(QDialog):
    def __init__(self, result: ImportResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resumen de importación")
        self.setMinimumWidth(440)
        self._result = result

        layout = QVBoxLayout(self)

        message, object_name = _STATUS_INFO.get(result.status.value, ("", ""))
        if message:
            status_label = QLabel(message)
            status_label.setObjectName(object_name)
            layout.addWidget(status_label)

        summary_rows = [
            ("Archivo", result.original_file_name),
            ("Banco", result.bank_name),
            ("Cuenta", result.account_alias),
            ("Filas leídas", str(result.total_rows)),
            ("Movimientos nuevos", str(result.inserted_rows)),
            ("Movimientos repetidos", str(result.duplicate_rows)),
            ("Filas inválidas", str(result.invalid_rows)),
            ("Sin clasificar", str(result.unclassified_rows)),
        ]
        for caption, value in summary_rows:
            row = QHBoxLayout()
            label = QLabel(caption + ":")
            label.setObjectName("cardLabel")
            row.addWidget(label)
            row.addStretch()
            row.addWidget(QLabel(value))
            layout.addLayout(row)

        if result.row_errors:
            layout.addWidget(QLabel(f"Errores de fila ({len(result.row_errors)}):"))
            error_list = QListWidget()
            for error in result.row_errors[:100]:
                error_list.addItem(QListWidgetItem(f"Fila {error.row_number}: {error.reason}"))
            layout.addWidget(error_list)

            export_button = QPushButton("Exportar errores a CSV")
            export_button.clicked.connect(self._export_errors)
            layout.addWidget(export_button)

        close_button = QPushButton("Cerrar")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def _export_errors(self) -> None:
        default_name = f"errores_{self._result.original_file_name}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar errores", default_name, "CSV (*.csv)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(["fila", "contenido", "motivo"])
                for error in self._result.row_errors:
                    writer.writerow(
                        [
                            error.row_number,
                            sanitize_for_spreadsheet(error.raw_content),
                            sanitize_for_spreadsheet(error.reason),
                        ]
                    )
            QMessageBox.information(
                self, "Exportación completa", "Los errores se exportaron correctamente."
            )
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar", f"No se pudo exportar el archivo: {exc}")
