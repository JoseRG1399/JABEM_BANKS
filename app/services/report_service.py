"""Cálculo de reportes (sección 15.8 de la especificación).

Todas las consultas usan agregación SQL (``GROUP BY`` / ``SUM``) en vez de
traer movimientos a memoria y sumarlos en Python, tal como pide la
sección 20 ("Generar reportes con consultas SQL agregadas antes de usar
pandas cuando sea posible").
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.constants import CategoryCode
from app.models import Bank, BankAccount, Branch, Movement, MovementCategory
from app.schemas.report_filter import ReportFilter


class ReportValueType(str, Enum):
    PAYMENT = "PAYMENT"
    CHARGE = "CHARGE"
    NET = "NET"


@dataclass
class ReportRow:
    label: str
    charge_cents: int = 0
    payment_cents: int = 0

    @property
    def net_cents(self) -> int:
        return self.payment_cents - self.charge_cents


def _apply_common_filters(query: Query, filters: ReportFilter, joined_account: bool = False) -> Query:
    if filters.date_from:
        query = query.filter(Movement.movement_date >= filters.date_from)
    if filters.date_to:
        query = query.filter(Movement.movement_date <= filters.date_to)
    if filters.bank_account_id:
        query = query.filter(Movement.bank_account_id == filters.bank_account_id)
    if filters.bank_id and not joined_account:
        query = query.join(BankAccount, Movement.bank_account_id == BankAccount.id).filter(
            BankAccount.bank_id == filters.bank_id
        )
    elif filters.bank_id and joined_account:
        query = query.filter(BankAccount.bank_id == filters.bank_id)
    if filters.branch_id:
        query = query.filter(Movement.branch_id == filters.branch_id)
    if filters.category_id:
        query = query.filter(Movement.category_id == filters.category_id)
    return query


def _sums() -> tuple:
    return (
        func.coalesce(func.sum(Movement.charge_cents), 0),
        func.coalesce(func.sum(Movement.payment_cents), 0),
    )


# ---------------------------------------------------------------------------
# 1. Totales por día
# ---------------------------------------------------------------------------
def totals_by_day(session: Session, filters: ReportFilter) -> list[ReportRow]:
    charge_sum, payment_sum = _sums()
    query = session.query(Movement.movement_date, charge_sum, payment_sum)
    query = _apply_common_filters(query, filters)
    rows = query.group_by(Movement.movement_date).order_by(Movement.movement_date).all()
    return [
        ReportRow(label=day.strftime("%d/%m/%Y"), charge_cents=int(charge), payment_cents=int(payment))
        for day, charge, payment in rows
    ]


# ---------------------------------------------------------------------------
# 2. Totales por banco
# ---------------------------------------------------------------------------
def totals_by_bank(session: Session, filters: ReportFilter) -> list[ReportRow]:
    charge_sum, payment_sum = _sums()
    query = (
        session.query(Bank.name, charge_sum, payment_sum)
        .join(BankAccount, BankAccount.bank_id == Bank.id)
        .join(Movement, Movement.bank_account_id == BankAccount.id)
    )
    query = _apply_common_filters(query, filters, joined_account=True)
    rows = query.group_by(Bank.name).order_by(Bank.name).all()
    return [
        ReportRow(label=name, charge_cents=int(charge), payment_cents=int(payment))
        for name, charge, payment in rows
    ]


# ---------------------------------------------------------------------------
# 3. Totales por cuenta
# ---------------------------------------------------------------------------
def totals_by_account(session: Session, filters: ReportFilter) -> list[ReportRow]:
    charge_sum, payment_sum = _sums()
    query = session.query(BankAccount.alias, charge_sum, payment_sum).join(
        Movement, Movement.bank_account_id == BankAccount.id
    )
    query = _apply_common_filters(query, filters, joined_account=True)
    rows = query.group_by(BankAccount.alias).order_by(BankAccount.alias).all()
    return [
        ReportRow(label=alias, charge_cents=int(charge), payment_cents=int(payment))
        for alias, charge, payment in rows
    ]


# ---------------------------------------------------------------------------
# 4. Totales por sucursal
# ---------------------------------------------------------------------------
def totals_by_branch(session: Session, filters: ReportFilter) -> list[ReportRow]:
    charge_sum, payment_sum = _sums()
    query = session.query(
        Branch.branch_number, Branch.name, charge_sum, payment_sum
    ).join(Movement, Movement.branch_id == Branch.id)
    query = _apply_common_filters(query, filters)
    rows = (
        query.group_by(Branch.branch_number, Branch.name)
        .order_by(Branch.branch_number)
        .all()
    )
    return [
        ReportRow(label=f"{number}. {name}", charge_cents=int(charge), payment_cents=int(payment))
        for number, name, charge, payment in rows
    ]


# ---------------------------------------------------------------------------
# 5. Totales por categoría
# ---------------------------------------------------------------------------
def totals_by_category(session: Session, filters: ReportFilter) -> list[ReportRow]:
    charge_sum, payment_sum = _sums()
    query = session.query(
        MovementCategory.report_order, MovementCategory.name, charge_sum, payment_sum
    ).join(Movement, Movement.category_id == MovementCategory.id)
    query = _apply_common_filters(query, filters)
    rows = (
        query.group_by(MovementCategory.report_order, MovementCategory.name)
        .order_by(MovementCategory.report_order)
        .all()
    )
    return [
        ReportRow(label=name, charge_cents=int(charge), payment_cents=int(payment))
        for _order, name, charge, payment in rows
    ]


# ---------------------------------------------------------------------------
# 6. Movimientos sin clasificar
# ---------------------------------------------------------------------------
def unclassified_movements(session: Session, filters: ReportFilter) -> list[Movement]:
    from sqlalchemy.orm import joinedload

    query = session.query(Movement).filter(Movement.classification_status == "UNCLASSIFIED")
    query = _apply_common_filters(query, filters)
    return (
        query.options(
            joinedload(Movement.bank_account).joinedload(BankAccount.bank),
            joinedload(Movement.imported_file),
        )
        .order_by(Movement.movement_date.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# 7. Comisiones e IVA
# ---------------------------------------------------------------------------
def commissions_and_vat(session: Session, filters: ReportFilter) -> list[ReportRow]:
    charge_sum, payment_sum = _sums()
    query = (
        session.query(MovementCategory.name, charge_sum, payment_sum)
        .join(Movement, Movement.category_id == MovementCategory.id)
        .filter(
            MovementCategory.code.in_(
                [CategoryCode.COMMISSION.value, CategoryCode.COMMISSION_VAT.value]
            )
        )
    )
    query = _apply_common_filters(query, filters)
    rows = query.group_by(MovementCategory.name).order_by(MovementCategory.name).all()
    return [
        ReportRow(label=name, charge_cents=int(charge), payment_cents=int(payment))
        for name, charge, payment in rows
    ]


# ---------------------------------------------------------------------------
# 8. Tabla consolidada por fecha, sucursal y banco (cuenta)
# ---------------------------------------------------------------------------
@dataclass
class ConsolidatedBranchRow:
    branch_label: str
    values_by_account: dict[str, int] = field(default_factory=dict)

    @property
    def total_cents(self) -> int:
        return sum(self.values_by_account.values())


@dataclass
class ConsolidatedDayGroup:
    day: dt.date
    branch_rows: list[ConsolidatedBranchRow] = field(default_factory=list)

    @property
    def values_by_account(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for branch_row in self.branch_rows:
            for account_alias, value in branch_row.values_by_account.items():
                totals[account_alias] = totals.get(account_alias, 0) + value
        return totals

    @property
    def total_cents(self) -> int:
        return sum(row.total_cents for row in self.branch_rows)


@dataclass
class ConsolidatedReport:
    account_aliases: list[str] = field(default_factory=list)
    day_groups: list[ConsolidatedDayGroup] = field(default_factory=list)

    @property
    def grand_totals_by_account(self) -> dict[str, int]:
        totals: dict[str, int] = {alias: 0 for alias in self.account_aliases}
        for day_group in self.day_groups:
            for alias, value in day_group.values_by_account.items():
                totals[alias] = totals.get(alias, 0) + value
        return totals

    @property
    def grand_total_cents(self) -> int:
        return sum(day_group.total_cents for day_group in self.day_groups)


def _value_column(value_type: ReportValueType):
    if value_type == ReportValueType.CHARGE:
        return func.coalesce(func.sum(Movement.charge_cents), 0)
    if value_type == ReportValueType.NET:
        return func.coalesce(func.sum(Movement.payment_cents - Movement.charge_cents), 0)
    return func.coalesce(func.sum(Movement.payment_cents), 0)


def consolidated_by_date_branch_account(
    session: Session,
    filters: ReportFilter,
    value_type: ReportValueType = ReportValueType.PAYMENT,
) -> ConsolidatedReport:
    """Reporte tipo tabla dinámica: solo incluye movimientos con sucursal
    identificada (es el reporte de conciliación de depósitos por sucursal).
    """
    value_column = _value_column(value_type)

    query = (
        session.query(
            Movement.movement_date,
            Branch.branch_number,
            Branch.name,
            BankAccount.alias,
            value_column,
        )
        .join(Branch, Movement.branch_id == Branch.id)
        .join(BankAccount, Movement.bank_account_id == BankAccount.id)
    )
    query = _apply_common_filters(query, filters, joined_account=True)
    rows = (
        query.group_by(Movement.movement_date, Branch.branch_number, Branch.name, BankAccount.alias)
        .order_by(Movement.movement_date, Branch.branch_number)
        .all()
    )

    account_aliases: list[str] = []
    days: dict[dt.date, dict[str, ConsolidatedBranchRow]] = {}

    for movement_date, branch_number, branch_name, account_alias, value in rows:
        if account_alias not in account_aliases:
            account_aliases.append(account_alias)

        branch_label = f"{branch_number}. {branch_name}"
        day_branches = days.setdefault(movement_date, {})
        branch_row = day_branches.setdefault(
            branch_label, ConsolidatedBranchRow(branch_label=branch_label)
        )
        branch_row.values_by_account[account_alias] = (
            branch_row.values_by_account.get(account_alias, 0) + int(value)
        )

    account_aliases.sort()

    day_groups = [
        ConsolidatedDayGroup(
            day=day,
            branch_rows=sorted(branches.values(), key=lambda r: r.branch_label),
        )
        for day, branches in sorted(days.items())
    ]

    return ConsolidatedReport(account_aliases=account_aliases, day_groups=day_groups)
