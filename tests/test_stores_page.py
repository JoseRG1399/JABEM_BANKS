from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.services.store_report_service import parse_transfer_payments, parse_uber_sales
from app.ui.pages.stores_page import StoresPage, transfers_report_html, uber_report_html

UBER_PAYLOAD = {
    "data": [
        {
            "_id": "Torres",
            "total": "100.00",
            "detalleVentas": [
                {"inventarioProductosNombre": "Pan <b>", "inventarioCantidad": 2,
                 "inventarioProductosPrecio": "50.00", "total": "100.00"}
            ],
        },
        {
            "_id": "Aeropuerto",
            "total": "540.00",
            "detalleVentas": [
                {"inventarioProductosNombre": "Pastel", "inventarioCantidad": 1,
                 "inventarioProductosPrecio": "540.00", "total": "540.00"}
            ],
        },
    ]
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_uber_tree_collapse_expand_and_click_toggle(qapp, config):
    page = StoresPage(config)
    page._render_uber(parse_uber_sales(UBER_PAYLOAD))
    tree = page._uber_tree
    first = tree.topLevelItem(0)

    assert tree.topLevelItemCount() == 2
    assert not first.isExpanded() and first.text(0).startswith("▶ ")

    page._on_uber_item_clicked(first, 0)
    assert first.isExpanded() and first.text(0).startswith("▼ ")
    page._on_uber_item_clicked(first, 0)
    assert not first.isExpanded()

    page._expand_all()
    assert all(tree.topLevelItem(i).isExpanded() for i in range(2))
    page._collapse_all()
    assert not any(tree.topLevelItem(i).isExpanded() for i in range(2))


def test_uber_print_html_has_all_details_and_escapes():
    html = uber_report_html(parse_uber_sales(UBER_PAYLOAD))
    assert "Pastel" in html and "Pan &lt;b&gt;" in html
    assert "$640.00" in html


def test_transfers_print_html():
    report = parse_transfer_payments(
        {"ventas": [{"ventasSucursal": "Torres", "ventasTicket": 5, "ventasTotal": 82,
                     "ventasMetodoPago": [{"transferencia": 82}],
                     "createdAt": "2026-11-13T18:13:56.000Z"}]}
    )
    html = transfers_report_html(report)
    assert "Torres" in html and "$82.00" in html and "Resumen por sucursal" in html


def test_print_preview_opens_maximized(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextDocument

    from app.ui.widgets.print_preview import create_print_preview

    preview = create_print_preview(None, QTextDocument(), "Prueba")
    assert preview.windowState() & Qt.WindowState.WindowMaximized
    assert "Prueba" in preview.windowTitle()
