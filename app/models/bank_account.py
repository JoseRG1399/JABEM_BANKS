from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank import Bank


class BankAccount(TimestampMixin, Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    alias: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="MXN", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bank: Mapped["Bank"] = relationship(back_populates="accounts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"BankAccount(id={self.id}, alias={self.alias!r})"
