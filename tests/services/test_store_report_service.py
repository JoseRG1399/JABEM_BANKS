from __future__ import annotations

from app.services.store_report_service import parse_uber_sales, parse_transfer_payments


def test_parse_uber_sales():
    report = parse_uber_sales(
        {
            "data": [
                {
                    "_id": "Torres",
                    "total": "100.50",
                    "detalleVentas": [
                        {
                            "inventarioProductosNombre": "Pan",
                            "inventarioCantidad": 3,
                            "inventarioProductosPrecio": "20.00",
                            "total": "60.00",
                        }
                    ],
                },
                {
                    "_id": "Aeropuerto",
                    "total": "540.00",
                    "detalleVentas": [
                        {
                            "inventarioProductosNombre": "Tres leches fresa G",
                            "inventarioCantidad": 1,
                            "inventarioProductosPrecio": "540.00",
                            "total": "540.00",
                        }
                    ],
                },
            ],
            "totalGeneral": "640.50",
        }
    )
    assert [b.branch for b in report.branches] == ["Aeropuerto", "Torres"]
    assert report.total_cents == 64050
    assert report.branches[1].lines[0].quantity == 3
    assert report.branches[1].lines[0].unit_price_cents == 2000


def test_parse_uber_sales_empty():
    report = parse_uber_sales({"data": []})
    assert report.branches == [] and report.total_cents == 0


def _sale(branch, ticket, transfer, total, created):
    return {
        "ventasSucursal": branch,
        "ventasTurno": "1",
        "ventasResponsable": "ANA",
        "ventasTicket": ticket,
        "ventasTotal": total,
        "ventasMetodoPago": [{"efectivo": 0, "transferencia": transfer}],
        "ventasListaProductos": [{"cantidad": "2", "producto": "Elote"}],
        "createdAt": created,
    }


def test_parse_transfer_payments_summary_and_local_time():
    report = parse_transfer_payments(
        {
            "ventas": [
                _sale("Torres", 2, 82, 82, "2026-11-13T18:13:56.000Z"),
                _sale("Xonacatlán", 1, 540, 540, "2026-11-13T18:03:17.000Z"),
                _sale("Torres", 3, 18.5, 20, "2026-11-13T19:00:00.000Z"),
            ],
            "notas": [],
        }
    )
    assert [s.ticket for s in report.sales] == ["1", "2", "3"]
    # 18:03Z -> 12:03 hora de México (UTC-6)
    assert report.sales[0].created_at.strftime("%H:%M") == "12:03"
    assert report.sales[0].products == ["2 x Elote"]
    assert report.total_transfer_cents == 54000 + 8200 + 1850

    summary = {row.branch: row for row in report.summary_by_branch()}
    assert summary["Torres"].sales_count == 2
    assert summary["Torres"].transfer_cents == 10050


def test_parse_transfer_payments_tolerates_bad_data():
    report = parse_transfer_payments({"ventas": [{"createdAt": "no-es-fecha"}]})
    assert report.sales[0].created_at is None
    assert report.sales[0].transfer_cents == 0
    assert report.sales[0].branch == "Sin sucursal"


def test_parse_transfer_payments_includes_note_transfer_abonos_only():
    report = parse_transfer_payments(
        {
            "ventas": [],
            "notas": [
                {
                    "pedidosSucursal": "Tecnológico",
                    "pedidosNoNota": 687,
                    "pedidosNombreCliente": "oscar",
                    "pedidosCostoTotal": 6292,
                    "pedidosListadoProductos": [
                        {"cantidad": 1, "producto": "Supremo ", "medida": "60 x 40 cm"}
                    ],
                    "pedidosACuenta": [
                        {
                            "fechaAbono": "2026-11-12T11:59:06.000Z",
                            "monto": 6000,
                            "responsable": "IRENE",
                            "metodoPago": "Transferencia",
                            "turno": "1",
                        },
                        {
                            "fechaAbono": "2026-11-11T15:00:00.000Z",
                            "monto": 292,
                            "metodoPago": "Efectivo",
                        },
                    ],
                    "datosFiscales": {"datosCFRFC": "NO-DEBE-USARSE"},
                }
            ],
        }
    )
    assert len(report.sales) == 1
    sale = report.sales[0]
    assert sale.kind == "Nota"
    assert sale.ticket == "687" and sale.customer == "oscar"
    assert sale.transfer_cents == 600000
    assert sale.total_cents == 629200
    assert sale.created_at.strftime("%d/%m %H:%M") == "12/11 05:59"
    assert sale.products == ["1 x Supremo (60 x 40 cm)"]
    assert report.total_transfer_cents == 600000
