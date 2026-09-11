"""Datos iniciales (seed) de catálogos: bancos, cuentas, sucursales,
identificadores, categorías y reglas de clasificación especiales.

La función principal ``seed_catalogs`` es idempotente: ejecutarla varias
veces no duplica registros, ya que cada entidad se busca por su clave
natural (código, alias, número de sucursal, etc.) antes de insertarla.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.constants import CATEGORY_DISPLAY_NAMES, CategoryCode, IdentifierType, MatchType
from app.models import (
    Bank,
    BankAccount,
    Branch,
    BranchIdentifier,
    ClassificationRule,
    MovementCategory,
)

# ---------------------------------------------------------------------------
# Bancos y cuentas
# ---------------------------------------------------------------------------

BANKS = [
    {"code": "BBVA", "name": "BBVA"},
    {"code": "MIFEL", "name": "Mifel"},
]

BANK_ACCOUNTS = [
    {"alias": "BBVA", "bank_code": "BBVA", "account_name": "BBVA"},
    {"alias": "MIFEL", "bank_code": "MIFEL", "account_name": "Mifel"},
    {"alias": "MIFEL2", "bank_code": "MIFEL", "account_name": "Mifel 2"},
]

# ---------------------------------------------------------------------------
# Sucursales (sección 8.3)
# ---------------------------------------------------------------------------

BRANCHES = [
    {"branch_number": "01", "name": "ALFREDO"},
    {"branch_number": "02", "name": "COLON"},
    {"branch_number": "03", "name": "LERMA"},
    {"branch_number": "04", "name": "TECNOLOGICO"},
    {"branch_number": "05", "name": "ACROPOLIS"},
    {"branch_number": "06", "name": "ADOLFO"},
    {"branch_number": "07", "name": "AERO"},
    {"branch_number": "08", "name": "CARRANZA"},
    {"branch_number": "09", "name": "METEPEC"},
    {"branch_number": "10", "name": "MEXI"},
    {"branch_number": "11", "name": "P SUAREZ"},
    {"branch_number": "12", "name": "TORRES"},
    {"branch_number": "13", "name": "SANTIN"},
    {"branch_number": "14", "name": "XONA"},
    {"branch_number": "15", "name": "FABELA"},
    {"branch_number": "16", "name": "MODERNA"},
    {"branch_number": "17", "name": "CALIMAYA"},
    {"branch_number": "18", "name": "DEPORTIVA"},
    {"branch_number": "19", "name": "OCOYOACAC"},
    {"branch_number": "20", "name": "FOGÓN OCOYOACAC"},
    {"branch_number": "21", "name": "FOGÓN TORRES"},
]

# ---------------------------------------------------------------------------
# Identificadores de sucursal (sección 8.4)
# ---------------------------------------------------------------------------

BRANCH_IDENTIFIERS = [
    {"identifier": "3515", "branch_number": "01", "bank_account_alias": "BBVA"},
    {"identifier": "3518", "branch_number": "02", "bank_account_alias": "BBVA"},
    {"identifier": "4912", "branch_number": "03", "bank_account_alias": "BBVA"},
    {"identifier": "3520", "branch_number": "04", "bank_account_alias": "BBVA"},
    {"identifier": "4798", "branch_number": "05", "bank_account_alias": "MIFEL"},
    {"identifier": "6650", "branch_number": "06", "bank_account_alias": "MIFEL"},
    {"identifier": "6421", "branch_number": "07", "bank_account_alias": "MIFEL"},
    {"identifier": "4219", "branch_number": "08", "bank_account_alias": "MIFEL"},
    {"identifier": "6262", "branch_number": "09", "bank_account_alias": "MIFEL"},
    {"identifier": "6805", "branch_number": "10", "bank_account_alias": "MIFEL"},
    {"identifier": "4062", "branch_number": "11", "bank_account_alias": "MIFEL"},
    {"identifier": "4061", "branch_number": "12", "bank_account_alias": "MIFEL"},
    {"identifier": "0613", "branch_number": "13", "bank_account_alias": "BBVA"},
    {"identifier": "5534", "branch_number": "14", "bank_account_alias": "MIFEL"},
    {"identifier": "0841", "branch_number": "15", "bank_account_alias": "MIFEL"},
    {"identifier": "9688", "branch_number": "16", "bank_account_alias": "MIFEL"},
    {"identifier": "0214", "branch_number": "17", "bank_account_alias": "MIFEL"},
    {"identifier": "1789", "branch_number": "18", "bank_account_alias": "MIFEL"},
    {"identifier": "4102", "branch_number": "19", "bank_account_alias": "BBVA"},
    {"identifier": "3629", "branch_number": "20", "bank_account_alias": "BBVA"},
    {"identifier": "3628", "branch_number": "21", "bank_account_alias": "BBVA"},
]

# ---------------------------------------------------------------------------
# Categorías (sección 8.5)
# ---------------------------------------------------------------------------

CATEGORIES = [
    {"code": code.value, "name": name, "report_order": order}
    for order, (code, name) in enumerate(CATEGORY_DISPLAY_NAMES.items())
]

# ---------------------------------------------------------------------------
# Reglas de clasificación especiales (sección 8.6)
# ---------------------------------------------------------------------------

CLASSIFICATION_RULES = [
    {
        "name": "Uber",
        "category_code": CategoryCode.UBER.value,
        "bank_account_alias": "MIFEL2",
        "pattern": "UBER",
        "match_type": MatchType.CONTAINS.value,
        "priority": 10,
    },
    {
        "name": "Clip",
        "category_code": CategoryCode.CLIP.value,
        "bank_account_alias": "MIFEL2",
        "pattern": "CLIP",
        "match_type": MatchType.CONTAINS.value,
        "priority": 10,
    },
    {
        "name": "IVA comisión",
        "category_code": CategoryCode.COMMISSION_VAT.value,
        "bank_account_alias": "BBVA",
        "pattern": r"(?=.*\bIVA\b)(?=.*\bCOMISION\b)",
        "match_type": MatchType.REGEX.value,
        # Debe evaluarse antes que la regla "Comisión" (prioridad menor = primero).
        "priority": 15,
    },
    {
        "name": "Comisión",
        "category_code": CategoryCode.COMMISSION.value,
        "bank_account_alias": "BBVA",
        "pattern": "COMISION",
        "match_type": MatchType.CONTAINS.value,
        "priority": 30,
    },
    {
        "name": "Traspaso",
        "category_code": CategoryCode.TRANSFER.value,
        "bank_account_alias": "BBVA",
        "pattern": "TRASP",
        "match_type": MatchType.CONTAINS.value,
        "priority": 10,
    },
    {
        "name": "Transferencia errónea",
        "category_code": CategoryCode.ERRONEOUS_TRANSFER.value,
        "bank_account_alias": "BBVA",
        "pattern": "TRANSFERENCIA ERRONEA",
        "match_type": MatchType.CONTAINS.value,
        "priority": 10,
    },
    {
        "name": "Devolución de IVA (SAT)",
        "category_code": CategoryCode.VAT_REFUND.value,
        "bank_account_alias": "BBVA",
        "pattern": r"(?=.*\bSAT\b)(?=.*\bDEVOLUCION\b)(?=.*\bIVA\b)",
        "match_type": MatchType.REGEX.value,
        "priority": 10,
    },
    {
        "name": "Gastos tarjeta débito",
        "category_code": CategoryCode.CARD_EXPENSES.value,
        "bank_account_alias": "BBVA",
        "pattern": r"(?=.*\bGTOS\b)(?=.*\bTARJ\b)(?=.*\bDEBITO\b)",
        "match_type": MatchType.REGEX.value,
        "priority": 10,
    },
]


@dataclass
class SeedResult:
    banks_created: int = 0
    accounts_created: int = 0
    branches_created: int = 0
    identifiers_created: int = 0
    categories_created: int = 0
    rules_created: int = 0

    @property
    def total_created(self) -> int:
        return (
            self.banks_created
            + self.accounts_created
            + self.branches_created
            + self.identifiers_created
            + self.categories_created
            + self.rules_created
        )


def seed_catalogs(session: Session) -> SeedResult:
    result = SeedResult()

    banks_by_code: dict[str, Bank] = {b.code: b for b in session.query(Bank).all()}
    for data in BANKS:
        if data["code"] in banks_by_code:
            continue
        bank = Bank(code=data["code"], name=data["name"])
        session.add(bank)
        session.flush()
        banks_by_code[bank.code] = bank
        result.banks_created += 1

    accounts_by_alias: dict[str, BankAccount] = {
        a.alias: a for a in session.query(BankAccount).all()
    }
    for data in BANK_ACCOUNTS:
        if data["alias"] in accounts_by_alias:
            continue
        account = BankAccount(
            alias=data["alias"],
            account_name=data["account_name"],
            bank_id=banks_by_code[data["bank_code"]].id,
        )
        session.add(account)
        session.flush()
        accounts_by_alias[account.alias] = account
        result.accounts_created += 1

    branches_by_number: dict[str, Branch] = {
        b.branch_number: b for b in session.query(Branch).all()
    }
    for data in BRANCHES:
        if data["branch_number"] in branches_by_number:
            continue
        branch = Branch(branch_number=data["branch_number"], name=data["name"])
        session.add(branch)
        session.flush()
        branches_by_number[branch.branch_number] = branch
        result.branches_created += 1

    existing_identifiers: set[tuple[str, int, int]] = {
        (bi.identifier, bi.branch_id, bi.bank_account_id)
        for bi in session.query(BranchIdentifier).all()
    }
    for data in BRANCH_IDENTIFIERS:
        branch = branches_by_number[data["branch_number"]]
        account = accounts_by_alias[data["bank_account_alias"]]
        key = (data["identifier"], branch.id, account.id)
        if key in existing_identifiers:
            continue
        identifier = BranchIdentifier(
            identifier=data["identifier"],
            branch_id=branch.id,
            bank_account_id=account.id,
            identifier_type=IdentifierType.TERMINAL_SUFFIX.value,
            priority=100,
        )
        session.add(identifier)
        existing_identifiers.add(key)
        result.identifiers_created += 1

    categories_by_code: dict[str, MovementCategory] = {
        c.code: c for c in session.query(MovementCategory).all()
    }
    for data in CATEGORIES:
        if data["code"] in categories_by_code:
            continue
        category = MovementCategory(
            code=data["code"], name=data["name"], report_order=data["report_order"]
        )
        session.add(category)
        session.flush()
        categories_by_code[category.code] = category
        result.categories_created += 1

    existing_rule_names = {r.name for r in session.query(ClassificationRule).all()}
    for data in CLASSIFICATION_RULES:
        if data["name"] in existing_rule_names:
            continue
        rule = ClassificationRule(
            name=data["name"],
            category_id=categories_by_code[data["category_code"]].id,
            bank_account_id=accounts_by_alias[data["bank_account_alias"]].id,
            pattern=data["pattern"],
            match_type=data["match_type"],
            priority=data["priority"],
        )
        session.add(rule)
        existing_rule_names.add(rule.name)
        result.rules_created += 1

    session.commit()
    return result
