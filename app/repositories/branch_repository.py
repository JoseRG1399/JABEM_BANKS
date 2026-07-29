"""Acceso a datos de sucursales e identificadores de sucursal."""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models import BankAccount, Branch, BranchIdentifier


class BranchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, branch_id: int) -> Branch | None:
        return self.session.get(Branch, branch_id)

    def get_by_number(self, branch_number: str) -> Branch | None:
        return self.session.query(Branch).filter_by(branch_number=branch_number).one_or_none()

    def list_all(self, active_only: bool = True) -> list[Branch]:
        query = self.session.query(Branch)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(Branch.branch_number).all()

    def add(self, branch: Branch) -> Branch:
        self.session.add(branch)
        return branch

    def get_identifier_by_id(self, identifier_id: int) -> BranchIdentifier | None:
        return self.session.get(BranchIdentifier, identifier_id)

    def list_active_identifiers(self) -> list[BranchIdentifier]:
        return (
            self.session.query(BranchIdentifier)
            .filter_by(active=True)
            .order_by(BranchIdentifier.priority)
            .all()
        )

    def list_identifiers_for_branch(self, branch_id: int) -> list[BranchIdentifier]:
        return (
            self.session.query(BranchIdentifier)
            .filter_by(branch_id=branch_id)
            .order_by(BranchIdentifier.priority)
            .all()
        )

    def list_all_identifiers(self) -> list[BranchIdentifier]:
        """Todos los identificadores (activos e inactivos), para la tabla de
        la pantalla de Sucursales. Carga sucursal y cuenta/banco de forma
        anticipada para poder usarlos después de cerrar la sesión."""
        return (
            self.session.query(BranchIdentifier)
            .join(Branch, BranchIdentifier.branch_id == Branch.id)
            .options(
                joinedload(BranchIdentifier.branch),
                joinedload(BranchIdentifier.bank_account).joinedload(BankAccount.bank),
            )
            .order_by(Branch.branch_number, BranchIdentifier.priority)
            .all()
        )

    def find_identifier(
        self, identifier: str, bank_account_id: int, exclude_id: int | None = None
    ) -> BranchIdentifier | None:
        """Busca un identificador duplicado (mismo texto + misma cuenta bancaria)."""
        query = self.session.query(BranchIdentifier).filter_by(
            identifier=identifier, bank_account_id=bank_account_id
        )
        if exclude_id is not None:
            query = query.filter(BranchIdentifier.id != exclude_id)
        return query.first()

    def add_identifier(self, identifier: BranchIdentifier) -> BranchIdentifier:
        self.session.add(identifier)
        return identifier
