"""Respaldo y restauración de la base de datos (sección 18 de la especificación).

Los respaldos se crean con la API de respaldo en línea de ``sqlite3`` (no
una simple copia de archivo), para que funcionen de forma segura incluso
con el modo WAL activo y conexiones abiertas en la aplicación.
"""
from __future__ import annotations

import datetime as dt
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.config import Config
from app.database.session import Database

BACKUP_PREFIX = "backup_"
BACKUP_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


@dataclass
class BackupInfo:
    path: Path
    created_at: dt.datetime
    size_bytes: int


def _backups_dir(config: Config) -> Path:
    backups_dir = Path(config.settings.backup_folder)
    backups_dir.mkdir(parents=True, exist_ok=True)
    return backups_dir


def create_backup(config: Config) -> Path:
    """Copia la base de datos actual a la carpeta de respaldos, con nombre
    con fecha y hora. Nunca sobrescribe un respaldo previo (el nombre
    incluye segundos, y si por alguna razón coincidiera, se agrega un
    sufijo incremental)."""
    backups_dir = _backups_dir(config)
    timestamp = dt.datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    backup_path = backups_dir / f"{BACKUP_PREFIX}{timestamp}.db"

    suffix = 1
    while backup_path.exists():
        backup_path = backups_dir / f"{BACKUP_PREFIX}{timestamp}_{suffix}.db"
        suffix += 1

    source_conn = sqlite3.connect(str(config.paths.database_file))
    try:
        dest_conn = sqlite3.connect(str(backup_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    return backup_path


def list_backups(config: Config) -> list[BackupInfo]:
    backups_dir = _backups_dir(config)
    backups = []
    for file_path in backups_dir.glob(f"{BACKUP_PREFIX}*.db"):
        stat = file_path.stat()
        backups.append(
            BackupInfo(
                path=file_path,
                created_at=dt.datetime.fromtimestamp(stat.st_mtime),
                size_bytes=stat.st_size,
            )
        )
    backups.sort(key=lambda b: b.created_at, reverse=True)
    return backups


def validate_backup_integrity(backup_path: Path) -> bool:
    """Ejecuta PRAGMA integrity_check sobre el archivo de respaldo."""
    if not backup_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(backup_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(result) and result[0] == "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def needs_scheduled_backup(config: Config) -> bool:
    """Determina si corresponde crear un respaldo automático según la
    frecuencia configurada (sección 17: "Frecuencia de respaldo")."""
    backups = list_backups(config)
    if not backups:
        return True
    last_backup = backups[0]
    elapsed = dt.datetime.now() - last_backup.created_at
    return elapsed.days >= config.settings.backup_frequency_days


def restore_backup(config: Config, database: Database, backup_path: Path) -> None:
    """Restaura un respaldo sobre la base de datos activa.

    El llamador es responsable de confirmar la acción con el usuario antes
    de invocar esta función. Antes de sobrescribir se valida la integridad
    del respaldo y se crea, además, un respaldo de seguridad del estado
    actual (por si el usuario se arrepiente).
    """
    if not validate_backup_integrity(backup_path):
        raise ValueError(
            "El archivo de respaldo está dañado o no es una base de datos válida."
        )

    create_backup(config)

    # Libera las conexiones activas antes de sobrescribir el archivo, para
    # evitar bloqueos de archivo en Windows.
    database.dispose()

    db_file = config.paths.database_file
    shutil.copy2(backup_path, db_file)

    for suffix in ("-wal", "-shm"):
        stale_file = db_file.with_name(db_file.name + suffix)
        if stale_file.exists():
            stale_file.unlink()
