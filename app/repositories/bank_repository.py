"""Acceso a datos de bancos y cuentas bancarias."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Bank, BankAccount


class BankRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_code(self, code: str) -> Bank | None:
        return self.session.query(Bank).filter_by(code=code).one_or_none()

    def list_all(self, active_only: bool = True) -> list[Bank]:
        query = self.session.query(Bank)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(Bank.name).all()

    def add(self, bank: Bank) -> Bank:
        self.session.add(bank)
        return bank

    def get_account_by_id(self, account_id: int) -> BankAccount | None:
        return self.session.get(BankAccount, account_id)

    def get_account_by_alias(self, alias: str) -> BankAccount | None:
        return self.session.query(BankAccount).filter_by(alias=alias).one_or_none()

    def list_accounts(
        self, bank_id: int | None = None, active_only: bool = True
    ) -> list[BankAccount]:
        query = self.session.query(BankAccount)
        if bank_id is not None:
            query = query.filter_by(bank_id=bank_id)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(BankAccount.alias).all()

    def add_account(self, account: BankAccount) -> BankAccount:
        self.session.add(account)
        return account
