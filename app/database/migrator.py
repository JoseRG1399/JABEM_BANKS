"""Aplicación de migraciones Alembic (o creación directa del esquema como respaldo)."""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect as sa_inspect

from app.database.session import Database

# Revisión de la primerísima migración ("esquema inicial"). Las instalaciones
# empaquetadas anteriores a que el ejecutable incluyera Alembic (ver
# ``scripts/build_executable.py``) crearon su base de datos directamente con
# ``Base.metadata.create_all`` y nunca quedaron versionadas. Si Alembic
# intentara correr "upgrade head" sobre esa base tal cual, reintentaría crear
# las tablas que ya existen y fallaría. Por eso, antes de actualizar, se
# detecta ese caso y se "estampa" esta revisión sin volver a ejecutarla.
INITIAL_SCHEMA_REVISION = "6b49f74b1b35"


def _project_root() -> Path:
    """Carpeta donde buscar ``alembic.ini`` y las migraciones.

    En un ejecutable empaquetado (PyInstaller), el código no vive en rutas
    de archivo normales: los datos agregados con ``--add-data`` se
    extraen a ``sys._MEIPASS`` en tiempo de ejecución. En modo desarrollo
    se usa la raíz del repositorio, relativa a este archivo.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _project_root()
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "app" / "database" / "migrations"


def get_alembic_config(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(MIGRATIONS_PATH))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _needs_baseline_stamp(database: Database) -> bool:
    """True si la base ya tiene tablas (creadas por una versión anterior con
    ``Base.metadata.create_all``) pero Alembic nunca la ha versionado."""
    inspector = sa_inspect(database.engine)
    existing_tables = set(inspector.get_table_names())
    if "alembic_version" in existing_tables:
        return False
    # "banks" es una tabla del esquema inicial: si existe, la base ya fue
    # creada antes, aunque sin quedar registrada en Alembic.
    return "banks" in existing_tables


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
        if _needs_baseline_stamp(database):
            command.stamp(cfg, INITIAL_SCHEMA_REVISION)
        command.upgrade(cfg, "head")
    else:
        Base.metadata.create_all(database.engine)
