from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.movement import Movement


class MovementClassificationHistory(Base):
    """Historial de reclasificaciones manuales, con fines de auditoría."""

    __tablename__ = "movement_classification_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("movements.id"), nullable=False)
    previous_branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    new_branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    previous_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("movement_categories.id"), nullable=True
    )
    new_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("movement_categories.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    create_rule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    movement: Mapped["Movement"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"MovementClassificationHistory(id={self.id}, movement_id={self.movement_id})"
