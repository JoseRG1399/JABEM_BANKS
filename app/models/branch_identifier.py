from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import IdentifierType
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank_account import BankAccount
    from app.models.branch import Branch


class BranchIdentifier(TimestampMixin, Base):
    __tablename__ = "branch_identifiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    bank_account_id: Mapped[int] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    identifier_type: Mapped[IdentifierType] = mapped_column(
        String(20), nullable=False, default=IdentifierType.TERMINAL_SUFFIX
    )
    regex_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    branch: Mapped["Branch"] = relationship(back_populates="identifiers")
    bank_account: Mapped["BankAccount"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"BranchIdentifier(id={self.id}, identifier={self.identifier!r}, "
            f"type={self.identifier_type!r})"
        )
