"""Reportes de consulta de información de las tiendas (API externa).

Las funciones ``parse_*`` son puras: reciben el JSON de la API y devuelven
dataclasses con importes en centavos, listas para mostrarse o exportarse.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from app.utils.money import money_to_cents

# México no usa horario de verano desde 2022: UTC-6 fijo.
LOCAL_TZ = dt.timezone(dt.timedelta(hours=-6))
_MIN_DATETIME = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------------------
# Ventas Uber por sucursal con detalle
# ---------------------------------------------------------------------------
@dataclass
class UberProductLine:
    product: str
    quantity: int
    unit_price_cents: int
    total_cents: int


@dataclass
class UberBranchSales:
    branch: str
    total_cents: int
    lines: list[UberProductLine] = field(default_factory=list)


@dataclass
class UberSalesReport:
    branches: list[UberBranchSales] = field(default_factory=list)
    total_cents: int = 0


def parse_uber_sales(payload: dict[str, Any]) -> UberSalesReport:
    branches: list[UberBranchSales] = []
    for item in payload.get("data") or []:
        lines = [
            UberProductLine(
                product=str(line.get("inventarioProductosNombre") or ""),
                quantity=int(line.get("inventarioCantidad") or 0),
                unit_price_cents=money_to_cents(line.get("inventarioProductosPrecio")),
                total_cents=money_to_cents(line.get("total")),
            )
            for line in item.get("detalleVentas") or []
        ]
        branches.append(
            UberBranchSales(
                branch=str(item.get("_id") or "Sin sucursal"),
                total_cents=money_to_cents(item.get("total")),
                lines=sorted(lines, key=lambda line: line.product.casefold()),
            )
        )
    branches.sort(key=lambda b: b.branch.casefold())
    # El total general se recalcula: no se depende de que la API lo envíe bien.
    return UberSalesReport(branches=branches, total_cents=sum(b.total_cents for b in branches))


# ---------------------------------------------------------------------------
# Pagos por transferencia
# ---------------------------------------------------------------------------
@dataclass
class TransferSale:
    kind: str  # "Venta" (ticket) o "Nota" (abono a un pedido)
    branch: str
    ticket: str
    shift: str
    responsible: str
    created_at: dt.datetime | None
    transfer_cents: int
    total_cents: int
    products: list[str] = field(default_factory=list)
    customer: str = ""


@dataclass
class TransferBranchSummary:
    branch: str
    sales_count: int
    transfer_cents: int


@dataclass
class TransferPaymentsReport:
    sales: list[TransferSale] = field(default_factory=list)

    @property
    def total_transfer_cents(self) -> int:
        return sum(s.transfer_cents for s in self.sales)

    def summary_by_branch(self) -> list[TransferBranchSummary]:
        grouped: dict[str, TransferBranchSummary] = {}
        for sale in self.sales:
            row = grouped.setdefault(sale.branch, TransferBranchSummary(sale.branch, 0, 0))
            row.sales_count += 1
            row.transfer_cents += sale.transfer_cents
        return sorted(grouped.values(), key=lambda r: r.branch.casefold())


def _parse_created_at(raw: Any) -> dt.datetime | None:
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(LOCAL_TZ)


def parse_transfer_payments(payload: dict[str, Any]) -> TransferPaymentsReport:
    sales: list[TransferSale] = []
    for item in payload.get("ventas") or []:
        transfer_cents = sum(
            money_to_cents(method.get("transferencia"))
            for method in item.get("ventasMetodoPago") or []
        )
        products = [
            f"{product.get('cantidad', '')} x {product.get('producto', '')}".strip()
            for product in item.get("ventasListaProductos") or []
        ]
        sales.append(
            TransferSale(
                kind="Venta",
                branch=str(item.get("ventasSucursal") or "Sin sucursal"),
                ticket=str(item.get("ventasTicket") or ""),
                shift=str(item.get("ventasTurno") or ""),
                responsible=str(item.get("ventasResponsable") or ""),
                created_at=_parse_created_at(item.get("createdAt")),
                transfer_cents=transfer_cents,
                total_cents=money_to_cents(item.get("ventasTotal")),
                products=products,
            )
        )
    sales.extend(_parse_note_transfers(payload.get("notas") or []))
    sales.sort(key=lambda s: (s.created_at or _MIN_DATETIME, s.ticket))
    return TransferPaymentsReport(sales=sales)


def _parse_note_transfers(notes: list[dict[str, Any]]) -> list[TransferSale]:
    """Cada abono por transferencia de una nota (pedido) es una entrada de
    dinero al banco, con la fecha del abono. No se incluyen los datos
    fiscales ni el teléfono del cliente."""
    result: list[TransferSale] = []
    for note in notes:
        products = [
            " ".join(
                part
                for part in (
                    f"{product.get('cantidad', '')} x {str(product.get('producto', '')).strip()}",
                    f"({product.get('medida')})" if product.get("medida") else "",
                )
                if part
            )
            for product in note.get("pedidosListadoProductos") or []
        ]
        for payment in note.get("pedidosACuenta") or []:
            if "transferencia" not in str(payment.get("metodoPago") or "").casefold():
                continue
            result.append(
                TransferSale(
                    kind="Nota",
                    branch=str(note.get("pedidosSucursal") or "Sin sucursal"),
                    ticket=str(note.get("pedidosNoNota") or ""),
                    shift=str(payment.get("turno") or ""),
                    responsible=str(payment.get("responsable") or note.get("pedidosResponsable") or ""),
                    created_at=_parse_created_at(payment.get("fechaAbono")),
                    transfer_cents=money_to_cents(payment.get("monto")),
                    total_cents=money_to_cents(note.get("pedidosCostoTotal")),
                    products=products,
                    customer=str(note.get("pedidosNombreCliente") or "").strip(),
                )
            )
    return result
