"""Acceso a datos de archivos importados."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ImportedFile


class ImportedFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_hash(self, file_hash: str) -> ImportedFile | None:
        return self.session.query(ImportedFile).filter_by(file_hash=file_hash).one_or_none()

    def get_by_id(self, imported_file_id: int) -> ImportedFile | None:
        return self.session.get(ImportedFile, imported_file_id)

    def add(self, imported_file: ImportedFile) -> ImportedFile:
        self.session.add(imported_file)
        return imported_file

    def list_all(self) -> list[ImportedFile]:
        return self.session.query(ImportedFile).order_by(ImportedFile.imported_at.desc()).all()

    def list_recent(self, limit: int = 5) -> list[ImportedFile]:
        return (
            self.session.query(ImportedFile)
            .order_by(ImportedFile.imported_at.desc())
            .limit(limit)
            .all()
        )

    def count_all(self) -> int:
        return self.session.query(func.count(ImportedFile.id)).scalar() or 0
