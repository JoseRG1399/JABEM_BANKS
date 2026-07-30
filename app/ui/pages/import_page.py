"""Pantalla de importación de archivos bancarios (BBVA TXT, Mifel CSV).

La importación real corre en un ``QThread`` (``ImportWorker``) para no
congelar la interfaz; ningún widget se toca desde el hilo de trabajo, solo
se emiten señales que el hilo principal conecta a sus propios métodos.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.database.session import Database
from app.parsers.base_parser import decode_bytes
from app.parsers.parser_factory import UnsupportedParserError, get_parser_for_bank
from app.repositories.bank_repository import BankRepository
from app.ui.dialogs.import_result_dialog import ImportResultDialog
from app.ui.workers.import_worker import ImportWorker


class _DropArea(QFrame):
    file_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setAcceptDrops(True)
        self.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel("Arrastra un archivo TXT o CSV aquí, o usa el botón de abajo.")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.file_dropped.emit(urls[0].toLocalFile())

    def set_file_name(self, name: str) -> None:
        self._label.setText(name)


class ImportPage(QWidget):
    import_completed = Signal()

    def __init__(self, config: Config, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._database = database
        self._selected_file: Path | None = None
        self._worker: ImportWorker | None = None
        self._build_ui()
        self._populate_banks()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)

        title = QLabel("Importar movimientos")
        title.setObjectName("appTitle")
        outer.addWidget(title)

        selectors_row = QHBoxLayout()
        selectors_row.addWidget(QLabel("Banco:"))
        self._bank_combo = QComboBox()
        self._bank_combo.currentIndexChanged.connect(self._on_bank_changed)
        selectors_row.addWidget(self._bank_combo)

        selectors_row.addWidget(QLabel("Cuenta:"))
        self._account_combo = QComboBox()
        self._account_combo.currentIndexChanged.connect(self._update_actions_enabled)
        selectors_row.addWidget(self._account_combo)
        selectors_row.addStretch()
        outer.addLayout(selectors_row)

        self._drop_area = _DropArea()
        self._drop_area.file_dropped.connect(self._set_selected_file)
        outer.addWidget(self._drop_area)

        pick_row = QHBoxLayout()
        pick_button = QPushButton("Seleccionar archivo…")
        pick_button.clicked.connect(self._pick_file)
        pick_row.addWidget(pick_button)

        self._file_type_label = QLabel("")
        self._file_type_label.setObjectName("cardLabel")
        pick_row.addWidget(self._file_type_label)
        pick_row.addStretch()
        outer.addLayout(pick_row)

        outer.addWidget(QLabel("Vista previa (primeras líneas del archivo)"))
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(160)
        self._preview.setFont(_monospace_font())
        outer.addWidget(self._preview)

        actions_row = QHBoxLayout()
        self._validate_button = QPushButton("Validar archivo")
        self._validate_button.clicked.connect(self._validate_file)
        actions_row.addWidget(self._validate_button)

        self._import_button = QPushButton("Importar movimientos")
        self._import_button.setObjectName("primaryButton")
        self._import_button.clicked.connect(self._start_import)
        actions_row.addWidget(self._import_button)
        actions_row.addStretch()
        outer.addLayout(actions_row)

        self._validation_label = QLabel("")
        self._validation_label.setWordWrap(True)
        outer.addWidget(self._validation_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setRange(0, 0)  # indeterminado: no hay progreso por fila
        outer.addWidget(self._progress_bar)

        outer.addStretch()

        self._update_actions_enabled()

    # ------------------------------------------------------------------
    def _populate_banks(self) -> None:
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            self._bank_combo.clear()
            for bank in bank_repo.list_all():
                self._bank_combo.addItem(bank.name, bank.id)
        self._on_bank_changed()

    def _on_bank_changed(self) -> None:
        bank_id = self._bank_combo.currentData()
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            self._account_combo.clear()
            if bank_id is not None:
                for account in bank_repo.list_accounts(bank_id=bank_id):
                    self._account_combo.addItem(account.alias, account.id)
        self._update_actions_enabled()

    def _pick_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de movimientos", "", "Archivos soportados (*.txt *.csv)"
        )
        if file_name:
            self._set_selected_file(file_name)

    def _set_selected_file(self, file_name: str) -> None:
        path = Path(file_name)
        self._selected_file = path
        self._drop_area.set_file_name(path.name)
        self._file_type_label.setText(f"Extensión detectada: {path.suffix.upper() or 'desconocida'}")
        self._validation_label.setText("")
        self._load_preview(path)
        self._update_actions_enabled()

    def _load_preview(self, path: Path) -> None:
        try:
            text = decode_bytes(path.read_bytes())
        except OSError as exc:
            self._preview.setPlainText(f"No se pudo leer el archivo: {exc}")
            return
        lines = text.splitlines()[:15]
        self._preview.setPlainText("\n".join(lines))

    def _update_actions_enabled(self) -> None:
        has_file = self._selected_file is not None
        has_account = self._account_combo.currentData() is not None
        is_busy = self._worker is not None
        self._validate_button.setEnabled(has_file and not is_busy)
        self._import_button.setEnabled(has_file and has_account and not is_busy)

    def _current_bank_code(self) -> str | None:
        bank_id = self._bank_combo.currentData()
        if bank_id is None:
            return None
        with self._database.session_scope() as session:
            bank_repo = BankRepository(session)
            for bank_row in bank_repo.list_all():
                if bank_row.id == bank_id:
                    return bank_row.code
        return None

    def _validate_file(self) -> None:
        if self._selected_file is None:
            return
        bank_code = self._current_bank_code()
        if bank_code is None:
            QMessageBox.warning(self, "Banco requerido", "Selecciona un banco antes de validar.")
            return
        try:
            parser = get_parser_for_bank(bank_code)
            outcome = parser.parse(self._selected_file)
        except UnsupportedParserError as exc:
            QMessageBox.critical(self, "Archivo no soportado", str(exc))
            return

        object_name = "statusSuccess" if not outcome.errors else "statusWarning"
        self._validation_label.setText(
            f"Filas leídas: {outcome.total_rows_seen}  |  "
            f"Filas válidas: {len(outcome.rows)}  |  "
            f"Filas inválidas: {len(outcome.errors)}"
        )
        self._validation_label.setObjectName(object_name)
        self._validation_label.style().unpolish(self._validation_label)
        self._validation_label.style().polish(self._validation_label)

    def _start_import(self) -> None:
        if self._selected_file is None or self._worker is not None:
            return
        account_id = self._account_combo.currentData()
        if account_id is None:
            QMessageBox.warning(self, "Cuenta requerida", "Selecciona una cuenta antes de importar.")
            return

        self._progress_bar.setVisible(True)
        self._worker = ImportWorker(self._config, self._selected_file, account_id)
        self._update_actions_enabled()

        self._worker.finished_ok.connect(self._on_import_finished)
        self._worker.failed.connect(self._on_import_failed)
        self._worker.finished.connect(self._on_worker_thread_finished)
        self._worker.start()

    def _on_import_finished(self, result) -> None:
        dialog = ImportResultDialog(result, parent=self)
        dialog.exec()
        self._clear_form()
        self.import_completed.emit()

    def _on_import_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Error al importar", message)

    def _on_worker_thread_finished(self) -> None:
        self._progress_bar.setVisible(False)
        self._worker = None
        self._update_actions_enabled()

    def _clear_form(self) -> None:
        self._selected_file = None
        self._bank_combo.setCurrentIndex(-1)
        self._account_combo.clear()
        self._drop_area.set_file_name("Arrastra un archivo TXT o CSV aquí, o usa el botón de abajo.")
        self._file_type_label.clear()
        self._preview.clear()
        self._validation_label.clear()
        self._validation_label.setObjectName("")
        self._update_actions_enabled()


def _monospace_font() -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font
