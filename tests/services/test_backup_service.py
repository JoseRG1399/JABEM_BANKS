import time

import pytest

from app.database.migrator import ensure_database_ready
from app.database.seed import seed_catalogs
from app.database.session import Database
from app.models import Bank
from app.services import backup_service


def test_create_backup_creates_file(config, database):
    backup_path = backup_service.create_backup(config)
    assert backup_path.exists()
    assert backup_path.parent == database.config.paths.backups_dir
    assert backup_path.name.startswith("backup_")


def test_create_backup_repeated_calls_never_overwrite(config, database):
    # Llamadas consecutivas suelen caer dentro del mismo segundo, lo que
    # ejercita directamente la lógica de sufijo incremental sin necesidad
    # de simular el reloj.
    paths = [backup_service.create_backup(config) for _ in range(3)]

    for path in paths:
        assert path.exists()
    assert len(set(paths)) == 3


def test_backup_contains_real_data(config, database, db_session):
    seed_catalogs(db_session)
    db_session.commit()

    backup_path = backup_service.create_backup(config)
    assert backup_service.validate_backup_integrity(backup_path)

    import sqlite3

    conn = sqlite3.connect(str(backup_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_validate_backup_integrity_rejects_invalid_file(tmp_path):
    fake_file = tmp_path / "not_a_db.db"
    fake_file.write_text("esto no es una base de datos sqlite", encoding="utf-8")
    assert backup_service.validate_backup_integrity(fake_file) is False


def test_validate_backup_integrity_rejects_missing_file(tmp_path):
    missing = tmp_path / "no_existe.db"
    assert backup_service.validate_backup_integrity(missing) is False


def test_list_backups_orders_newest_first(config, database):
    first = backup_service.create_backup(config)
    time.sleep(0.05)
    second = backup_service.create_backup(config)

    backups = backup_service.list_backups(config)
    assert len(backups) == 2
    assert backups[0].path in (first, second)
    assert backups[0].created_at >= backups[1].created_at


def test_needs_scheduled_backup_true_when_no_backups(config):
    assert backup_service.needs_scheduled_backup(config) is True


def test_needs_scheduled_backup_false_right_after_backup(config, database):
    backup_service.create_backup(config)
    config.settings.backup_frequency_days = 1
    assert backup_service.needs_scheduled_backup(config) is False


def test_restore_backup_replaces_current_database(config, tmp_path):
    database = Database(config=config)
    ensure_database_ready(database)
    with database.session_scope() as session:
        seed_catalogs(session)

    backup_path = backup_service.create_backup(config)

    # Modificamos la base actual después del respaldo.
    with database.session_scope() as session:
        session.add(Bank(code="TESTBANK", name="Banco de prueba"))

    with database.session_scope() as session:
        assert session.query(Bank).filter_by(code="TESTBANK").one_or_none() is not None

    backup_service.restore_backup(config, database, backup_path)

    with database.session_scope() as session:
        assert session.query(Bank).filter_by(code="TESTBANK").one_or_none() is None
        assert session.query(Bank).count() == 2

    database.dispose()


def test_restore_backup_rejects_corrupt_file(config, database, tmp_path):
    fake_backup = tmp_path / "corrupt.db"
    fake_backup.write_text("no es una base de datos", encoding="utf-8")

    with pytest.raises(ValueError):
        backup_service.restore_backup(config, database, fake_backup)
