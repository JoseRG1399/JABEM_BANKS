"""Fábrica de sesiones de SQLAlchemy y contexto de acceso a la base de datos."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Config, get_config
from app.database.connection import create_app_engine


class Database:
    """Punto único de acceso al engine y a las sesiones de la aplicación."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.engine: Engine = create_app_engine(self.config)
        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Contexto que garantiza commit/rollback y cierre limpio de la sesión."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def new_session(self) -> Session:
        """Crea una sesión sin ciclo de vida gestionado; el llamador debe cerrarla."""
        return self._session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


_database_instance: Database | None = None


def get_database() -> Database:
    global _database_instance
    if _database_instance is None:
        _database_instance = Database()
    return _database_instance


def reset_database_instance() -> None:
    """Utilizado en pruebas para forzar la recreación de la instancia global."""
    global _database_instance
    if _database_instance is not None:
        _database_instance.dispose()
    _database_instance = None
