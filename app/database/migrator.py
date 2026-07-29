"""Aplicación de migraciones Alembic (o creación directa del esquema como respaldo)."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from app.database.session import Database

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "app" / "database" / "migrations"


def get_alembic_config(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(MIGRATIONS_PATH))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def ensure_database_ready(database: Database) -> None:
    """Garantiza que el esquema de la base de datos exista y esté actualizado.

    En entornos de desarrollo, con el repositorio completo disponible, aplica
    las migraciones de Alembic. Si ``alembic.ini`` no está disponible (por
    ejemplo, en un ejecutable empaquetado sin los archivos de migración),
    recurre a crear el esquema directamente desde los modelos.
    """
    from app.models import Base

    if ALEMBIC_INI_PATH.exists() and MIGRATIONS_PATH.exists():
        cfg = get_alembic_config(database.config.database_url)
        command.upgrade(cfg, "head")
    else:
        Base.metadata.create_all(database.engine)
