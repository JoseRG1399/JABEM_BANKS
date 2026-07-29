"""Acceso a datos de categorías de movimiento."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import MovementCategory


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, category_id: int) -> MovementCategory | None:
        return self.session.get(MovementCategory, category_id)

    def get_by_code(self, code: str) -> MovementCategory | None:
        return self.session.query(MovementCategory).filter_by(code=code).one_or_none()

    def list_all(self, active_only: bool = True) -> list[MovementCategory]:
        query = self.session.query(MovementCategory)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(MovementCategory.report_order).all()
