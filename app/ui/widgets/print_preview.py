"""Vista previa de impresión común a todas las pantallas."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import QWidget


def create_print_preview(
    parent: QWidget, document: QTextDocument, title: str
) -> QPrintPreviewDialog:
    """Diálogo de vista previa en horizontal que se abre maximizado (ocupa
    toda la pantalla, respetando la barra de tareas)."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    preview = QPrintPreviewDialog(printer, parent)
    # El diálogo NO toma posesión del QPrinter: si se destruye al salir de esta
    # función, el diálogo queda con un puntero colgante y la app se cierra.
    preview._printer = printer  # type: ignore[attr-defined]
    preview._document = document  # type: ignore[attr-defined]
    preview.setWindowTitle(f"Vista previa de impresión — {title}")
    preview.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    preview.setWindowState(Qt.WindowState.WindowMaximized)
    preview.paintRequested.connect(document.print_)
    return preview


def show_print_preview(parent: QWidget, document: QTextDocument, title: str) -> None:
    create_print_preview(parent, document, title).exec()
