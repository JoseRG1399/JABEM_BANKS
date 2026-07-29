import datetime as dt

from app.utils.hashes import compute_bytes_hash, compute_file_hash, compute_movement_hash


def test_compute_file_hash_is_deterministic(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("contenido de prueba", encoding="utf-8")

    first = compute_file_hash(file_path)
    second = compute_file_hash(file_path)

    assert first == second
    assert len(first) == 64


def test_compute_file_hash_differs_for_different_content(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("contenido A", encoding="utf-8")
    file_b.write_text("contenido B", encoding="utf-8")

    assert compute_file_hash(file_a) != compute_file_hash(file_b)


def test_compute_bytes_hash_matches_file_hash(tmp_path):
    file_path = tmp_path / "sample.txt"
    data = b"mismo contenido"
    file_path.write_bytes(data)

    assert compute_file_hash(file_path) == compute_bytes_hash(data)


def _movement_kwargs(**overrides):
    base = dict(
        bank_account_id=1,
        movement_date=dt.date(2026, 7, 1),
        normalized_concept="VENTAS DEBITO 149064102 TERMINALES",
        normalized_reference="",
        external_folio="",
        charge_cents=0,
        payment_cents=395300,
        balance_cents=46744004,
    )
    base.update(overrides)
    return base


def test_compute_movement_hash_is_deterministic():
    first = compute_movement_hash(**_movement_kwargs())
    second = compute_movement_hash(**_movement_kwargs())
    assert first == second


def test_compute_movement_hash_changes_with_amount():
    first = compute_movement_hash(**_movement_kwargs())
    second = compute_movement_hash(**_movement_kwargs(payment_cents=100000))
    assert first != second


def test_compute_movement_hash_ignores_none_vs_empty_string_consistently():
    with_none = compute_movement_hash(**_movement_kwargs(external_folio=None))
    with_empty = compute_movement_hash(**_movement_kwargs(external_folio=""))
    assert with_none == with_empty
