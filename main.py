"""Punto de entrada de Analizador Bancario.

Prepara la base de datos, configura logging, aplica la configuración
guardada (formato de fecha, tema), crea un respaldo automático si
corresponde según la frecuencia configurada, y lanza la ventana principal
de PySide6. Los errores no controlados se registran en el log y se
muestran al usuario como un mensaje simple, nunca como una traza completa
(sección 19).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import get_config
from app.database.migrator import ensure_database_ready
from app.database.seed import seed_catalogs
from app.database.session import get_database
from app.services import backup_service
from app.ui.dialogs.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.theme import build_stylesheet
from app.utils.dates import set_display_format
from app.utils.logging import configure_logging, get_logger


def _application_icon() -> QIcon:
    if getattr(sys, "frozen", False):
        icon_path = Path(sys._MEIPASS) / "public" / "images" / "Logo.ico"
    else:
        icon_path = Path(__file__).resolve().parent / "public" / "images" / "Logo.ico"
    return QIcon(str(icon_path))


def _install_exception_hook() -> None:
    logger = get_logger("main")

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error(
            "Excepción no controlada:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )
        QMessageBox.critical(
            None,
            "Error inesperado",
            "Ocurrió un error inesperado. Se registró el detalle en el archivo de "
            "log para su revisión.",
        )

    sys.excepthook = handle_exception


def main() -> None:
    config = get_config()
    logger = configure_logging(config.paths.logs_dir)
    _install_exception_hook()
    logger.info("Iniciando %s", config.settings.app_name)

    set_display_format(config.settings.date_format)

    database = get_database()
    ensure_database_ready(database)
    with database.session_scope() as session:
        seed_catalogs(session)

    try:
        if backup_service.needs_scheduled_backup(config):
            backup_path = backup_service.create_backup(config)
            logger.info("Respaldo automático creado: %s", backup_path)
    except OSError as exc:
        logger.warning("No se pudo crear el respaldo automático: %s", exc)

    app = QApplication(sys.argv)
    app.setWindowIcon(_application_icon())
    app.setStyleSheet(build_stylesheet(config.settings.theme))

    login_dialog = LoginDialog(config)
    if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
        logger.info("Acceso cancelado")
        return

    window = MainWindow(config, database)
    window.show()

    exit_code = app.exec()
    logger.info("Cerrando %s", config.settings.app_name)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
