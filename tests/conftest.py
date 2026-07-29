from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Config
from app.database.migrator import ensure_database_ready
from app.database.session import Database
from app.utils.dates import DISPLAY_FORMAT, set_display_format


@pytest.fixture(autouse=True)
def _reset_global_date_format():
    """``app.utils.dates`` mantiene el formato de fecha activo como estado
    global mutable (para que Configuración pueda cambiarlo en caliente).
    Se restaura después de cada prueba para evitar contaminación entre
    pruebas de toda la suite."""
    yield
    set_display_format(DISPLAY_FORMAT)


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    return Config(base_dir=tmp_path / "analizador_bancario_test")


@pytest.fixture()
def database(config: Config) -> Database:
    db = Database(config=config)
    ensure_database_ready(db)
    yield db
    db.dispose()


@pytest.fixture()
def db_session(database: Database):
    with database.session_scope() as session:
        yield session
