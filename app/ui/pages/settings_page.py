"""Pantalla de configuración (sección 17) y gestión de respaldos (sección 18)."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.database.session import Database
from app.repositories.bank_repository import BankRepository
from app.services import backup_service
from app.ui.theme import build_stylesheet
from app.utils.dates import set_display_format

DATE_FORMAT_OPTIONS = [
    ("31/12/2026 (día/mes/año)", "%d/%m/%Y"),
    ("2026-12-31 (ISO)", "%Y-%m-%d"),
    ("31-12-2026", "%d-%m-%Y"),
]

THEME_OPTIONS = [("Claro", "light"), ("Oscuro", "dark")]
TABLE_ROW_HEIGHT = 36
MAX_VISIBLE_TABLE_ROWS = 6


class SettingsPage(QWidget):
    def __init__(self, config: Config, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._database = database
        self._account_alias_edits: dict[int, QLineEdit] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Configuración")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        layout.addWidget(self._build_general_group())
        layout.addWidget(self._build_accounts_group())
        layout.addWidget(self._build_backups_group())
        layout.addWidget(self._build_logs_group())
        layout.addStretch()

    # ------------------------------------------------------------------
    def _build_general_group(self) -> QGroupBox:
        group = QGroupBox("General")
        form = QFormLayout(group)

        self._company_edit = QLineEdit(self._config.settings.company_name)
        form.addRow("Nombre de la empresa:", self._company_edit)

        self._app_name_edit = QLineEdit(self._config.settings.app_name)
        form.addRow("Nombre de la aplicación:", self._app_name_edit)

        self._export_folder_edit, export_row = self._build_folder_row(self._config.settings.export_folder)
        form.addRow("Carpeta de exportaciones:", export_row)

        self._backup_folder_edit, backup_row = self._build_folder_row(self._config.settings.backup_folder)
        form.addRow("Carpeta de respaldos:", backup_row)

        self._date_format_combo = QComboBox()
        for label, value in DATE_FORMAT_OPTIONS:
            self._date_format_combo.addItem(label, value)
        index = self._date_format_combo.findData(self._config.settings.date_format)
        self._date_format_combo.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Formato de fecha:", self._date_format_combo)

        self._rows_per_page_spin = QSpinBox()
        self._rows_per_page_spin.setRange(10, 1000)
        self._rows_per_page_spin.setValue(self._config.settings.rows_per_page)
        form.addRow("Filas por página:", self._rows_per_page_spin)

        self._backup_frequency_spin = QSpinBox()
        self._backup_frequency_spin.setRange(0, 365)
        self._backup_frequency_spin.setValue(self._config.settings.backup_frequency_days)
        self._backup_frequency_spin.setSuffix(" día(s)")
        form.addRow("Frecuencia de respaldo:", self._backup_frequency_spin)

        self._currency_edit = QLineEdit(self._config.settings.currency)
        form.addRow("Moneda:", self._currency_edit)

        self._theme_combo = QComboBox()
        for label, value in THEME_OPTIONS:
            self._theme_combo.addItem(label, value)
        theme_index = self._theme_combo.findData(self._config.settings.theme)
        self._theme_combo.setCurrentIndex(theme_index if theme_index >= 0 else 0)
        form.addRow("Tema:", self._theme_combo)

        save_button = QPushButton("Guardar configuración")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._on_save_general)
        form.addRow("", save_button)

        return group

    def _build_folder_row(self, initial_value: str) -> tuple[QLineEdit, QWidget]:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(initial_value)
        row_layout.addWidget(edit)
        browse_button = QPushButton("Examinar…")
        browse_button.clicked.connect(lambda: self._browse_folder(edit))
        row_layout.addWidget(browse_button)
        return edit, row_widget

    def _browse_folder(self, target_edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", target_edit.text())
        if folder:
            target_edit.setText(folder)

    def _on_save_general(self) -> None:
        settings = self._config.settings
        settings.company_name = self._company_edit.text().strip()
        settings.app_name = self._app_name_edit.text().strip() or settings.app_name
        settings.export_folder = self._export_folder_edit.text().strip()
        settings.backup_folder = self._backup_folder_edit.text().strip()
        settings.date_format = self._date_format_combo.currentData()
        settings.rows_per_page = self._rows_per_page_spin.value()
        settings.backup_frequency_days = self._backup_frequency_spin.value()
        settings.currency = self._currency_edit.text().strip() or settings.currency
        settings.theme = self._theme_combo.currentData()

        self._config.save_settings()
        set_display_format(settings.date_format)

        instance = QApplication.instance()
        if instance is not None:
            instance.setStyleSheet(build_stylesheet(settings.theme))

        window = self.window()
        if hasattr(window, "setWindowTitle"):
            window.setWindowTitle(settings.app_name)

        QMessageBox.information(self, "Configuración guardada", "Los cambios se guardaron correctamente.")

    # ------------------------------------------------------------------
    def _build_accounts_group(self) -> QGroupBox:
        group = QGroupBox("Cuentas y alias")
        layout = QVBoxLayout(group)

        self._accounts_table = QTableWidget(0, 3)
        self._accounts_table.setHorizontalHeaderLabels(["Banco", "Cuenta", "Alias"])
        self._configure_content_table(self._accounts_table)
        layout.addWidget(self._accounts_table)

        self._populate_accounts_table()

        save_aliases_button = QPushButton("Guardar alias")
        save_aliases_button.clicked.connect(self._on_save_aliases)
        layout.addWidget(save_aliases_button)

        return group

    def _populate_accounts_table(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            accounts = bank_repo.list_accounts(active_only=False)

            self._accounts_table.setRowCount(len(accounts))
            self._account_alias_edits = {}
            for row_index, account in enumerate(accounts):
                self._accounts_table.setItem(row_index, 0, QTableWidgetItem(account.bank.name))
                self._accounts_table.setItem(row_index, 1, QTableWidgetItem(account.account_name))

                alias_edit = QLineEdit(account.alias)
                self._accounts_table.setCellWidget(row_index, 2, alias_edit)
                self._account_alias_edits[account.id] = alias_edit
            self._fit_table_to_content(self._accounts_table)

    def _on_save_aliases(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            aliases_seen: set[str] = set()
            for edit in self._account_alias_edits.values():
                new_alias = edit.text().strip()
                if not new_alias:
                    QMessageBox.warning(self, "Alias requerido", "Ningún alias puede quedar vacío.")
                    return
                if new_alias in aliases_seen:
                    QMessageBox.warning(
                        self, "Alias duplicado", f"El alias '{new_alias}' está repetido."
                    )
                    return
                aliases_seen.add(new_alias)

            for account_id, edit in self._account_alias_edits.items():
                account = bank_repo.get_account_by_id(account_id)
                if account is not None:
                    account.alias = edit.text().strip()

        QMessageBox.information(self, "Alias guardados", "Los alias de cuentas se actualizaron.")

    # ------------------------------------------------------------------
    def _build_backups_group(self) -> QGroupBox:
        group = QGroupBox("Respaldos")
        layout = QVBoxLayout(group)

        actions_row = QHBoxLayout()
        backup_button = QPushButton("Crear respaldo ahora")
        backup_button.setObjectName("primaryButton")
        backup_button.clicked.connect(self._on_create_backup)
        actions_row.addWidget(backup_button)

        open_folder_button = QPushButton("Abrir carpeta de respaldos")
        open_folder_button.clicked.connect(self._on_open_backups_folder)
        actions_row.addWidget(open_folder_button)
        actions_row.addStretch()
        layout.addLayout(actions_row)

        self._backups_table = QTableWidget(0, 3)
        self._backups_table.setHorizontalHeaderLabels(["Fecha", "Tamaño", "Archivo"])
        self._backups_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._backups_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._configure_content_table(self._backups_table)
        layout.addWidget(self._backups_table)

        restore_button = QPushButton("Restaurar respaldo seleccionado")
        restore_button.clicked.connect(self._on_restore_backup)
        layout.addWidget(restore_button)

        self._populate_backups_table()
        return group

    def _populate_backups_table(self) -> None:
        self._backups = backup_service.list_backups(self._config)
        self._backups_table.setRowCount(len(self._backups))
        for row_index, backup in enumerate(self._backups):
            size_kb = backup.size_bytes / 1024
            self._backups_table.setItem(
                row_index, 0, QTableWidgetItem(backup.created_at.strftime("%d/%m/%Y %H:%M:%S"))
            )
            self._backups_table.setItem(row_index, 1, QTableWidgetItem(f"{size_kb:,.1f} KB"))
            self._backups_table.setItem(row_index, 2, QTableWidgetItem(backup.path.name))
        self._fit_table_to_content(self._backups_table)

    def _configure_content_table(self, table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

    def _fit_table_to_content(self, table: QTableWidget) -> None:
        visible_rows = min(max(table.rowCount(), 2), MAX_VISIBLE_TABLE_ROWS)
        header_height = table.horizontalHeader().sizeHint().height()
        table.setFixedHeight(header_height + visible_rows * TABLE_ROW_HEIGHT + 2 * table.frameWidth())

    def _on_create_backup(self) -> None:
        try:
            backup_path = backup_service.create_backup(self._config)
        except OSError as exc:
            QMessageBox.critical(self, "Error al respaldar", f"No se pudo crear el respaldo: {exc}")
            return
        self._populate_backups_table()
        QMessageBox.information(self, "Respaldo creado", f"Se creó el respaldo: {backup_path.name}")

    def _on_open_backups_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._config.paths.backups_dir)))

    def _on_restore_backup(self) -> None:
        selected_rows = {index.row() for index in self._backups_table.selectedIndexes()}
        if not selected_rows:
            QMessageBox.warning(self, "Selecciona un respaldo", "Elige un respaldo de la lista.")
            return
        backup = self._backups[next(iter(selected_rows))]

        answer = QMessageBox.question(
            self,
            "Confirmar restauración",
            f"Esto reemplazará la base de datos actual con el respaldo del "
            f"{backup.created_at.strftime('%d/%m/%Y %H:%M:%S')}.\n\n"
            "Se creará automáticamente un respaldo de seguridad del estado actual "
            "antes de restaurar. ¿Deseas continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            backup_service.restore_backup(self._config, self._database, backup.path)
        except ValueError as exc:
            QMessageBox.critical(self, "Respaldo inválido", str(exc))
            return

        self._populate_backups_table()
        QMessageBox.information(
            self,
            "Restauración completa",
            "La base de datos fue restaurada. Reinicia la aplicación para asegurar "
            "que todas las pantallas reflejen los datos restaurados.",
        )

    # ------------------------------------------------------------------
    def _build_logs_group(self) -> QGroupBox:
        group = QGroupBox("Registro de actividad (logs)")
        layout = QHBoxLayout(group)

        open_logs_button = QPushButton("Abrir carpeta de logs")
        open_logs_button.clicked.connect(self._on_open_logs_folder)
        layout.addWidget(open_logs_button)
        layout.addStretch()

        return group

    def _on_open_logs_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._config.paths.logs_dir)))

    def refresh(self) -> None:
        self._populate_accounts_table()
        self._populate_backups_table()
