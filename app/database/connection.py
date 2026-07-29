"""Creación del engine de SQLAlchemy con configuración adecuada para SQLite local."""
from __future__ import annotations

from sqlalchemy import Engine, event
from sqlalchemy import create_engine

from app.config import Config


def _enable_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def create_app_engine(config: Config) -> Engine:
    engine = create_engine(
        config.database_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_sqlite_pragmas)
    return engine
