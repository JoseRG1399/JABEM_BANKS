from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import FileType, ImportedFileStatus
from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.bank_account import BankAccount


class ImportedFile(Base):
    __tablename__ = "imported_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[FileType] = mapped_column(String(10), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unclassified_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ImportedFileStatus] = mapped_column(
        String(15), nullable=False, default=ImportedFileStatus.PROCESSING
    )
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    bank_account: Mapped["BankAccount"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"ImportedFile(id={self.id}, original_name={self.original_name!r})"
