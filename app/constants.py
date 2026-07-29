"""Constantes y enumeraciones de dominio compartidas por toda la aplicación."""
from __future__ import annotations

import enum


class IdentifierType(str, enum.Enum):
    TERMINAL_SUFFIX = "TERMINAL_SUFFIX"
    REFERENCE = "REFERENCE"
    CONTAINS = "CONTAINS"
    REGEX = "REGEX"
    EXACT = "EXACT"


class MatchType(str, enum.Enum):
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    EXACT = "EXACT"
    REGEX = "REGEX"


class ImportedFileStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class FileType(str, enum.Enum):
    TXT = "TXT"
    CSV = "CSV"


class ClassificationStatus(str, enum.Enum):
    CLASSIFIED = "CLASSIFIED"
    UNCLASSIFIED = "UNCLASSIFIED"
    MANUAL = "MANUAL"


class ClassificationMethod(str, enum.Enum):
    SPECIAL_RULE = "SPECIAL_RULE"
    BRANCH_IDENTIFIER = "BRANCH_IDENTIFIER"
    MANUAL = "MANUAL"
    NONE = "NONE"


# Códigos de categorías iniciales (sección 8.5 de la especificación)
class CategoryCode(str, enum.Enum):
    BRANCH = "BRANCH"
    UBER = "UBER"
    CLIP = "CLIP"
    COMMISSION = "COMMISSION"
    COMMISSION_VAT = "COMMISSION_VAT"
    TRANSFER = "TRANSFER"
    ERRONEOUS_TRANSFER = "ERRONEOUS_TRANSFER"
    VAT_REFUND = "VAT_REFUND"
    CARD_EXPENSES = "CARD_EXPENSES"
    UNCLASSIFIED = "UNCLASSIFIED"


CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    CategoryCode.BRANCH: "Sucursal",
    CategoryCode.UBER: "Uber",
    CategoryCode.CLIP: "Clip",
    CategoryCode.COMMISSION: "Comisiones",
    CategoryCode.COMMISSION_VAT: "IVA comisiones",
    CategoryCode.TRANSFER: "Traspaso",
    CategoryCode.ERRONEOUS_TRANSFER: "Transferencia errónea",
    CategoryCode.VAT_REFUND: "Devolución de IVA",
    CategoryCode.CARD_EXPENSES: "Gastos tarjeta débito",
    CategoryCode.UNCLASSIFIED: "No clasificado",
}
