"""Crea (o actualiza) la base de datos SQLite de la aplicación.

Uso:
    python scripts/initialize_database.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from app.database.migrator import ensure_database_ready
from app.database.session import get_database


def main() -> None:
    config = get_config()
    database = get_database()
    ensure_database_ready(database)
    print(f"Base de datos lista en: {config.paths.database_file}")


if __name__ == "__main__":
    main()
