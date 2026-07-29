"""Modelos SQLAlchemy. Importar este módulo garantiza que todos los modelos
queden registrados en Base.metadata (necesario para create_all y Alembic).
"""
from app.models.base import Base
from app.models.bank import Bank
from app.models.bank_account import BankAccount
from app.models.branch import Branch
from app.models.branch_identifier import BranchIdentifier
from app.models.movement_category import MovementCategory
from app.models.classification_rule import ClassificationRule
from app.models.imported_file import ImportedFile
from app.models.movement import Movement
from app.models.movement_classification_history import MovementClassificationHistory

__all__ = [
    "Base",
    "Bank",
    "BankAccount",
    "Branch",
    "BranchIdentifier",
    "MovementCategory",
    "ClassificationRule",
    "ImportedFile",
    "Movement",
    "MovementClassificationHistory",
]
