from pathlib import Path

import pytest

from app.constants import ImportedFileStatus
from app.database.seed import seed_catalogs
from app.models import BankAccount, Movement
from app.services.import_service import DuplicateFileError, import_file

DATE_W = 12
CONCEPT_W = 60
CARGO_W = 11
ABONO_W = 11
SALDO_W = 12


def _row(date: str, concept: str, cargo: str = "", abono: str = "", saldo: str = "") -> str:
    return (
        date.ljust(DATE_W)
        + concept.ljust(CONCEPT_W)
        + cargo.rjust(CARGO_W)
        + abono.rjust(ABONO_W)
        + saldo.rjust(SALDO_W)
    )


def _header() -> str:
    return (
        "Día".ljust(DATE_W)
        + "Concepto / Referencia".ljust(CONCEPT_W)
        + "Cargo".rjust(CARGO_W)
        + "Abono".rjust(ABONO_W)
        + "Saldo".rjust(SALDO_W)
    )


def _write_txt(tmp_path: Path, name: str, rows: list[str]) -> Path:
    path = tmp_path / name
    path.write_text("\n".join([_header(), *rows]) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def bbva_account(db_session) -> BankAccount:
    seed_catalogs(db_session)
    return db_session.query(BankAccount).filter_by(alias="BBVA").one()


def test_import_new_file_inserts_and_classifies_movements(tmp_path, db_session, bbva_account):
    file_path = _write_txt(
        tmp_path,
        "extracto1.txt",
        [
            _row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04"),
            _row(
                "01-07-2026",
                "VENTAS DEBITO/149064102 TERMINALES PUNTO DE VENTA",
                "",
                "3,953.00",
                "467,440.04",
            ),
        ],
    )

    result = import_file(db_session, file_path, bbva_account)

    assert result.status == ImportedFileStatus.SUCCESS
    assert result.inserted_rows == 2
    assert result.duplicate_rows == 0
    assert result.invalid_rows == 0

    movements = db_session.query(Movement).order_by(Movement.id).all()
    assert len(movements) == 2
    assert movements[0].classification_status == "CLASSIFIED"
    assert movements[0].classification_method == "SPECIAL_RULE"
    assert movements[1].classification_method == "BRANCH_IDENTIFIER"
    assert movements[1].branch_id is not None


def test_reimporting_same_file_raises_duplicate_file_error(tmp_path, db_session, bbva_account):
    file_path = _write_txt(
        tmp_path,
        "extracto2.txt",
        [_row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04")],
    )

    import_file(db_session, file_path, bbva_account)

    with pytest.raises(DuplicateFileError):
        import_file(db_session, file_path, bbva_account)


def test_two_identical_movements_in_same_file_are_both_kept(tmp_path, db_session, bbva_account):
    file_path = _write_txt(
        tmp_path,
        "extracto3.txt",
        [
            _row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04"),
            _row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04"),
        ],
    )

    result = import_file(db_session, file_path, bbva_account)

    assert result.inserted_rows == 2
    assert result.duplicate_rows == 0

    movements = db_session.query(Movement).order_by(Movement.occurrence_number).all()
    assert [m.occurrence_number for m in movements] == [1, 2]
    assert movements[0].movement_hash == movements[1].movement_hash


def test_subsequent_file_with_extra_occurrence_inserts_only_the_new_one(
    tmp_path, db_session, bbva_account
):
    file_a = _write_txt(
        tmp_path,
        "extracto4a.txt",
        [_row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04")],
    )
    result_a = import_file(db_session, file_a, bbva_account)
    assert result_a.inserted_rows == 1
    assert result_a.duplicate_rows == 0

    file_b = _write_txt(
        tmp_path,
        "extracto4b.txt",
        [
            _row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04"),
            _row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04"),
        ],
    )
    result_b = import_file(db_session, file_b, bbva_account)

    assert result_b.inserted_rows == 1
    assert result_b.duplicate_rows == 1

    all_movements = db_session.query(Movement).order_by(Movement.occurrence_number).all()
    assert len(all_movements) == 2
    assert [m.occurrence_number for m in all_movements] == [1, 2]


def test_invalid_rows_do_not_block_valid_rows_and_are_reported(tmp_path, db_session, bbva_account):
    lines = [
        _header(),
        "FECHA-MALA   CONCEPTO SIN FECHA VALIDA                                 14.22               467,336.94",
        _row("01-07-2026", "COMISION MANEJO DE CUENTA", "150.00", "", "467,290.04"),
    ]
    file_path = tmp_path / "extracto5.txt"
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = import_file(db_session, file_path, bbva_account)

    assert result.status == ImportedFileStatus.PARTIAL
    assert result.inserted_rows == 1
    assert result.invalid_rows == 1
    assert len(result.row_errors) == 1
