"""Pruebas de punta a punta del módulo Tiendas: servidor HTTP local real,
hilo de consulta, render y flujo de impresión (con la vista previa abierta)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datetime as dt
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.pages import stores_page
from app.ui.pages.stores_page import REPORT_TRANSFERS, REPORT_UBER, StoresPage
from app.ui.widgets.print_preview import show_print_preview

UBER_RESPONSE = {
    "data": [
        {"_id": "Torres", "total": "100.00", "detalleVentas": [
            {"inventarioProductosNombre": "Pan", "inventarioCantidad": 2,
             "inventarioProductosPrecio": "50.00", "total": "100.00"}]},
        {"_id": "Aeropuerto", "total": "540.00", "detalleVentas": [
            {"inventarioProductosNombre": "Pastel", "inventarioCantidad": 1,
             "inventarioProductosPrecio": "540.00", "total": "540.00"}]},
    ],
    "totalGeneral": "640.00",
}
TRANSFERS_RESPONSE = {
    "ventas": [{"ventasSucursal": "Torres", "ventasTicket": 9, "ventasTotal": 82,
                "ventasMetodoPago": [{"transferencia": 82}],
                "createdAt": "2026-11-13T18:13:56.000Z"}],
    "notas": [{"pedidosSucursal": "Tecnológico", "pedidosNoNota": 687, "pedidosCostoTotal": 6292,
               "pedidosACuenta": [{"fechaAbono": "2026-11-12T11:59:06.000Z", "monto": 6292,
                                   "metodoPago": "Transferencia"}]}],
}


class _Handler(BaseHTTPRequestHandler):
    requests: list[tuple[str, dict]] = []
    fail = False

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((self.path, body))
        if type(self).fail:
            self.send_response(500)
            self.end_headers()
            return
        routes = {
            "/getVentasDeDIDIByFechasConDetalleDeVentas": UBER_RESPONSE,
            "/manageInfoOfTransferenciaPayments": TRANSFERS_RESPONSE,
        }
        payload = routes.get(self.path)
        self.send_response(200 if payload is not None else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    _Handler.requests = []
    _Handler.fail = False
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def page(qapp, config, server):
    config.settings.store_api_host = server
    page = StoresPage(config)
    page._date_from.setDate(dt.date(2026, 11, 1))
    page._date_to.setDate(dt.date(2026, 11, 13))
    return page


def _wait_for_query(qapp, page, timeout=10):
    deadline = time.time() + timeout
    while not page._query_button.isEnabled() or page._worker is None or page._worker.isRunning():
        qapp.processEvents()
        assert time.time() < deadline, "la consulta no terminó"
        time.sleep(0.01)
    qapp.processEvents()


def _close_preview_soon(qapp, seen: list):
    def close():
        for widget in qapp.topLevelWidgets():
            if isinstance(widget, QPrintPreviewDialog) and widget.isVisible():
                seen.append(widget)
                widget.close()
    QTimer.singleShot(400, close)


def _select(page, key):
    page._type_combo.setCurrentIndex(page._type_combo.findData(key))


def test_uber_query_render_and_print(qapp, page, server):
    _select(page, REPORT_UBER)
    page._on_query()
    _wait_for_query(qapp, page)

    path, body = _Handler.requests[-1]
    assert path == "/getVentasDeDIDIByFechasConDetalleDeVentas"
    assert body == {"startDate": "2026-11-01T00:00:00.229Z", "endDate": "2026-11-13T23:59:59.229Z"}

    tree = page._uber_tree
    assert [tree.topLevelItem(i).text(0)[2:] for i in range(2)] == ["Aeropuerto", "Torres"]
    assert "$640.00" in page._totals_label.text()
    assert not tree.topLevelItem(0).isExpanded()

    seen: list = []
    _close_preview_soon(qapp, seen)
    page._on_print()
    assert len(seen) == 1, "la vista previa de impresión no llegó a abrirse"
    assert seen[0].isMaximized() or seen[0].windowState()


def test_transfers_query_render_and_print(qapp, page):
    _select(page, REPORT_TRANSFERS)
    page._on_query()
    _wait_for_query(qapp, page)

    assert page._transfer_table.rowCount() == 2
    kinds = {page._transfer_table.item(r, 1).text() for r in range(2)}
    assert kinds == {"Venta", "Nota"}
    assert page._transfer_summary.rowCount() == 2
    assert "$6,374.00" in page._totals_label.text()

    seen: list = []
    _close_preview_soon(qapp, seen)
    page._on_print()
    assert len(seen) == 1


def test_print_without_query_warns(qapp, page, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))
    page._on_print()
    assert warnings == ["Sin datos"]


def test_print_after_switching_report_type_requires_new_query(qapp, page, monkeypatch):
    _select(page, REPORT_UBER)
    page._on_query()
    _wait_for_query(qapp, page)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))
    _select(page, REPORT_TRANSFERS)
    page._on_print()
    assert warnings == ["Sin datos"]


def test_server_error_is_reported_and_ui_recovers(qapp, page, monkeypatch):
    _Handler.fail = True
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    page._on_query()
    _wait_for_query(qapp, page)
    assert warnings and "500" in warnings[0]
    assert page._query_button.isEnabled()


def test_missing_host_is_reported(qapp, config, monkeypatch):
    monkeypatch.delenv("NEXT_PUBLIC_API_HOST", raising=False)
    config.settings.store_api_host = ""
    page = StoresPage(config)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    page._on_query()
    _wait_for_query(qapp, page)
    assert warnings and "no está configurada" in warnings[0]


def test_invalid_date_range_does_not_query(qapp, page, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))
    page._date_from.setDate(dt.date(2026, 11, 20))
    page._on_query()
    assert warnings == ["Fechas inválidas"]
    assert _Handler.requests == []


def test_print_preview_helper_does_not_crash_when_executed(qapp):
    """Regresión: el QPrinter debe sobrevivir a la función que crea el diálogo."""
    seen: list = []
    _close_preview_soon(qapp, seen)
    document = QTextDocument()
    document.setHtml("<h1>Prueba</h1>")
    show_print_preview(None, document, "Prueba")
    assert len(seen) == 1
