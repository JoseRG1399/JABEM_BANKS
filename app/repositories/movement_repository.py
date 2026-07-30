"""Acceso a datos de movimientos: duplicados, consultas paginadas y agregados
para el dashboard. Todas las consultas usan filtros e índices en vez de
cargar la tabla completa en memoria (requisito de rendimiento, sección 20).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Query, Session, joinedload

from app.models import BankAccount, Movement


class MovementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Inserción y duplicados
    # ------------------------------------------------------------------
    def add_all(self, movements: list[Movement]) -> None:
        if movements:
            self.session.add_all(movements)

    def count_existing_occurrences(self, hashes: set[str]) -> dict[str, int]:
        """Para cada hash dado, cuántas ocurrencias ya existen en la base de datos."""
        if not hashes:
            return {}
        rows = (
            self.session.query(Movement.movement_hash, func.count(Movement.id))
            .filter(Movement.movement_hash.in_(hashes))
            .group_by(Movement.movement_hash)
            .all()
        )
        return {movement_hash: count for movement_hash, count in rows}

    def get_by_id(self, movement_id: int) -> Movement | None:
        return self.session.get(Movement, movement_id)

    # ------------------------------------------------------------------
    # Agregados para el dashboard
    # ------------------------------------------------------------------
    def count_all(self) -> int:
        return self.session.query(func.count(Movement.id)).scalar() or 0

    def count_unclassified(self) -> int:
        return (
            self.session.query(func.count(Movement.id))
            .filter_by(classification_status="UNCLASSIFIED")
            .scalar()
            or 0
        )

    def sum_totals_for_period(
        self, date_from: dt.date | None, date_to: dt.date | None
    ) -> tuple[int, int]:
        query = self.session.query(
            func.coalesce(func.sum(Movement.charge_cents), 0),
            func.coalesce(func.sum(Movement.payment_cents), 0),
        )
        if date_from:
            query = query.filter(Movement.movement_date >= date_from)
        if date_to:
            query = query.filter(Movement.movement_date <= date_to)
        charge_total, payment_total = query.one()
        return int(charge_total), int(payment_total)

    def sum_payments_by_day(
        self, date_from: dt.date | None, date_to: dt.date | None
    ) -> list[tuple[dt.date, int]]:
        query = self.session.query(
            Movement.movement_date, func.coalesce(func.sum(Movement.payment_cents), 0)
        )
        if date_from:
            query = query.filter(Movement.movement_date >= date_from)
        if date_to:
            query = query.filter(Movement.movement_date <= date_to)
        rows = query.group_by(Movement.movement_date).order_by(Movement.movement_date).all()
        return [(day, int(total)) for day, total in rows]

    def sum_charges_and_payments_by_day(
        self, date_from: dt.date | None, date_to: dt.date | None
    ) -> list[tuple[dt.date, int, int]]:
        query = self.session.query(
            Movement.movement_date,
            func.coalesce(func.sum(Movement.charge_cents), 0),
            func.coalesce(func.sum(Movement.payment_cents), 0),
        )
        if date_from:
            query = query.filter(Movement.movement_date >= date_from)
        if date_to:
            query = query.filter(Movement.movement_date <= date_to)
        rows = query.group_by(Movement.movement_date).order_by(Movement.movement_date).all()
        return [(day, int(charges), int(payments)) for day, charges, payments in rows]

    def sum_by_account(
        self, date_from: dt.date | None, date_to: dt.date | None
    ) -> list[tuple[str, int]]:
        query = self.session.query(
            BankAccount.alias, func.coalesce(func.sum(Movement.payment_cents), 0)
        ).join(BankAccount, Movement.bank_account_id == BankAccount.id)
        if date_from:
            query = query.filter(Movement.movement_date >= date_from)
        if date_to:
            query = query.filter(Movement.movement_date <= date_to)
        rows = query.group_by(BankAccount.alias).all()
        return [(alias, int(total)) for alias, total in rows]

    # ------------------------------------------------------------------
    # Consulta paginada con filtros (pantalla de movimientos)
    # ------------------------------------------------------------------
    def query_paginated(
        self,
        filters: "MovementFilter",
        page: int,
        page_size: int,
        sort_column: str = "movement_date",
        sort_desc: bool = True,
    ) -> "PagedResult":
        base_query = self._apply_filters(self.session.query(Movement), filters)

        total_items = base_query.order_by(None).count()

        charge_total, payment_total = self._apply_filters(
            self.session.query(
                func.coalesce(func.sum(Movement.charge_cents), 0),
                func.coalesce(func.sum(Movement.payment_cents), 0),
            ),
            filters,
        ).one()

        sort_map = {
            "movement_date": Movement.movement_date,
            "charge_cents": Movement.charge_cents,
            "payment_cents": Movement.payment_cents,
            "balance_cents": Movement.balance_cents,
        }
        sort_field = sort_map.get(sort_column, Movement.movement_date)
        order_clause = sort_field.desc() if sort_desc else sort_field.asc()

        items = (
            base_query.options(
                joinedload(Movement.bank_account).joinedload(BankAccount.bank),
                joinedload(Movement.branch),
                joinedload(Movement.category),
                joinedload(Movement.imported_file),
            )
            .order_by(order_clause, Movement.id.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
            .all()
        )

        return PagedResult(
            items=items,
            total_items=int(total_items),
            total_charge_cents=int(charge_total or 0),
            total_payment_cents=int(payment_total or 0),
        )

    def list_all_filtered(self, filters: "MovementFilter") -> list[Movement]:
        """Todos los movimientos que cumplen el filtro, sin paginar. Se usa
        para exportar a Excel el resultado filtrado completo, no solo la
        página visible."""
        query = self._apply_filters(self.session.query(Movement), filters)
        return (
            query.options(
                joinedload(Movement.bank_account).joinedload(BankAccount.bank),
                joinedload(Movement.branch),
                joinedload(Movement.category),
                joinedload(Movement.imported_file),
            )
            .order_by(Movement.movement_date.desc(), Movement.id.desc())
            .all()
        )

    def _apply_filters(self, query: Query, filters: "MovementFilter") -> Query:
        if filters.date_from:
            query = query.filter(Movement.movement_date >= filters.date_from)
        if filters.date_to:
            query = query.filter(Movement.movement_date <= filters.date_to)
        if filters.bank_account_id:
            query = query.filter(Movement.bank_account_id == filters.bank_account_id)
        if filters.bank_id:
            query = query.join(
                BankAccount, Movement.bank_account_id == BankAccount.id
            ).filter(BankAccount.bank_id == filters.bank_id)
        if filters.branch_id:
            query = query.filter(Movement.branch_id == filters.branch_id)
        if filters.category_id:
            query = query.filter(Movement.category_id == filters.category_id)
        if filters.classification_status:
            query = query.filter(Movement.classification_status == filters.classification_status)
        if filters.movement_type == "CARGO":
            query = query.filter(Movement.charge_cents > 0)
        elif filters.movement_type == "ABONO":
            query = query.filter(Movement.payment_cents > 0)
        if filters.free_text:
            pattern = f"%{filters.free_text.upper()}%"
            query = query.filter(Movement.normalized_text.like(pattern))
        if filters.min_amount_cents is not None or filters.max_amount_cents is not None:
            amount_expr = func.max(Movement.charge_cents, Movement.payment_cents)
            if filters.min_amount_cents is not None:
                query = query.filter(amount_expr >= filters.min_amount_cents)
            if filters.max_amount_cents is not None:
                query = query.filter(amount_expr <= filters.max_amount_cents)
        if filters.imported_file_id:
            query = query.filter(Movement.imported_file_id == filters.imported_file_id)
        return query


@dataclass
class MovementFilter:
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    bank_id: int | None = None
    bank_account_id: int | None = None
    branch_id: int | None = None
    category_id: int | None = None
    classification_status: str | None = None
    movement_type: str | None = None  # "CARGO" | "ABONO" | None
    free_text: str | None = None
    min_amount_cents: int | None = None
    max_amount_cents: int | None = None
    imported_file_id: int | None = None


@dataclass
class PagedResult:
    items: list[Movement] = field(default_factory=list)
    total_items: int = 0
    total_charge_cents: int = 0
    total_payment_cents: int = 0
