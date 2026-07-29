from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ClassificationMethod, ClassificationStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank_account import BankAccount
    from app.models.branch import Branch
    from app.models.imported_file import ImportedFile
    from app.models.movement_category import MovementCategory


class Movement(TimestampMixin, Base):
    __tablename__ = "movements"
    __table_args__ = (
        UniqueConstraint("movement_hash", "occurrence_number", name="uq_movement_hash_occurrence"),
        Index("ix_movements_date", "movement_date"),
        Index("ix_movements_account", "bank_account_id"),
        Index("ix_movements_branch", "branch_id"),
        Index("ix_movements_category", "category_id"),
        Index("ix_movements_classification_status", "classification_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=False
    )
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("movement_categories.id"), nullable=True
    )
    imported_file_id: Mapped[int] = mapped_column(
        ForeignKey("imported_files.id"), nullable=False
    )

    movement_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    description_original: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_original: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_text: Mapped[str] = mapped_column(String(500), nullable=False)
    external_folio: Mapped[str | None] = mapped_column(String(100), nullable=True)

    charge_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    movement_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurrence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    classification_status: Mapped[ClassificationStatus] = mapped_column(
        String(15), nullable=False, default=ClassificationStatus.UNCLASSIFIED
    )
    classification_method: Mapped[ClassificationMethod] = mapped_column(
        String(20), nullable=False, default=ClassificationMethod.NONE
    )
    matched_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    bank_account: Mapped["BankAccount"] = relationship()
    branch: Mapped["Branch | None"] = relationship()
    category: Mapped["MovementCategory | None"] = relationship()
    imported_file: Mapped["ImportedFile"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Movement(id={self.id}, date={self.movement_date}, "
            f"hash={self.movement_hash[:8]}..., occurrence={self.occurrence_number})"
        )
