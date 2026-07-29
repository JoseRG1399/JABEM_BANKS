"""Worker en segundo plano para ejecutar una importación sin congelar la UI.

Crea su propia instancia de ``Database`` (y por lo tanto su propio engine y
conexión) en vez de reutilizar la del hilo principal, ya que las sesiones de
SQLAlchemy no deben compartirse entre hilos.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.config import Config


class ImportWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        config: Config,
        file_path: Path,
        bank_account_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._file_path = file_path
        self._bank_account_id = bank_account_id

    def run(self) -> None:  # noqa: D102 (override de QThread)
        from app.database.session import Database
        from app.repositories.bank_repository import BankRepository
        from app.services.import_service import DuplicateFileError, import_file

        database = Database(config=self._config)
        try:
            with database.session_scope() as session:
                bank_repo = BankRepository(session)
                bank_account = bank_repo.get_account_by_id(self._bank_account_id)
                if bank_account is None:
                    raise ValueError("La cuenta bancaria seleccionada ya no existe.")
                result = import_file(session, self._file_path, bank_account)
            self.finished_ok.emit(result)
        except DuplicateFileError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - un error de importación no debe tumbar la app
            self.failed.emit(f"No se pudo importar el archivo: {exc}")
        finally:
            database.dispose()
