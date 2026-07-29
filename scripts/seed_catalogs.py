"""Carga los catálogos iniciales (bancos, cuentas, sucursales, identificadores,
categorías y reglas) en la base de datos. Es seguro ejecutarlo varias veces.

Uso:
    python scripts/seed_catalogs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.migrator import ensure_database_ready
from app.database.seed import seed_catalogs
from app.database.session import get_database


def main() -> None:
    database = get_database()
    ensure_database_ready(database)
    with database.session_scope() as session:
        result = seed_catalogs(session)

    print("Catálogos cargados:")
    print(f"  Bancos nuevos:          {result.banks_created}")
    print(f"  Cuentas nuevas:         {result.accounts_created}")
    print(f"  Sucursales nuevas:      {result.branches_created}")
    print(f"  Identificadores nuevos: {result.identifiers_created}")
    print(f"  Categorías nuevas:      {result.categories_created}")
    print(f"  Reglas nuevas:          {result.rules_created}")
    if result.total_created == 0:
        print("Todos los catálogos ya estaban cargados; no se creó nada nuevo.")


if __name__ == "__main__":
    main()
