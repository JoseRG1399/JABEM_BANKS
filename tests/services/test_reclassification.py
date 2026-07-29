import datetime as dt

import pytest

from app.constants import MatchType
from app.database.seed import seed_catalogs
from app.models import (
    BankAccount,
    Branch,
    ImportedFile,
    Movement,
    MovementCategory,
    MovementClassificationHistory,
)
from app.services.classification_service import (
    ReclassifyRequest,
    count_matching_movements,
    identifier_matches_text,
    reclassify_movements,
    rule_matches_text,
)
from app.utils.text import normalize_text


@pytest.fixture()
def catalogs(db_session):
    seed_catalogs(db_session)
    bbva = db_session.query(BankAccount).filter_by(alias="BBVA").one()
    branch_alfredo = db_session.query(Branch).filter_by(branch_number="01").one()
    unclassified_category = (
        db_session.query(MovementCategory).filter_by(code="UNCLASSIFIED").one()
    )

    imported_file = ImportedFile(
        bank_account_id=bbva.id,
        original_name="extracto.txt",
        stored_name="extracto.txt",
        original_path="C:/tmp/extracto.txt",
        file_type="TXT",
        file_hash="hash-file-reclass",
        file_size=10,
    )
    db_session.add(imported_file)
    db_session.flush()

    def make_movement(description: str, movement_hash: str) -> Movement:
        return Movement(
            bank_account_id=bbva.id,
            branch_id=None,
            category_id=unclassified_category.id,
            imported_file_id=imported_file.id,
            movement_date=dt.date(2026, 7, 1),
            description_original=description,
            normalized_text=normalize_text(description),
            charge_cents=1000,
            payment_cents=0,
            movement_hash=movement_hash,
            occurrence_number=1,
            classification_status="UNCLASSIFIED",
            classification_method="NONE",
            source_row_number=1,
        )

    m1 = make_movement("UBER TRIP 12345", "hash-u1")
    m2 = make_movement("PAGO UBER EATS", "hash-u2")
    m3 = make_movement("COMPRA SUPERMERCADO", "hash-u3")
    db_session.add_all([m1, m2, m3])
    db_session.flush()

    return {
        "bbva": bbva,
        "branch_alfredo": branch_alfredo,
        "unclassified_category": unclassified_category,
        "m1": m1,
        "m2": m2,
        "m3": m3,
    }


def test_rule_matches_text():
    assert rule_matches_text("UBER", MatchType.CONTAINS.value, False, "PAGO UBER EATS") is True
    assert rule_matches_text("UBER", MatchType.CONTAINS.value, False, "COMPRA SUPERMERCADO") is False


def test_identifier_matches_text():
    assert identifier_matches_text("4102", "TERMINAL_SUFFIX", "VENTAS 149064102 TERMINALES") is True
    assert identifier_matches_text("4102", "TERMINAL_SUFFIX", "VENTAS 149069999 TERMINALES") is False


def test_count_matching_movements(db_session, catalogs):
    count = count_matching_movements(
        db_session, pattern="UBER", match_type=MatchType.CONTAINS.value, case_sensitive=False
    )
    assert count == 2

    scoped_count = count_matching_movements(
        db_session,
        pattern="UBER",
        match_type=MatchType.CONTAINS.value,
        case_sensitive=False,
        bank_account_id=catalogs["bbva"].id,
    )
    assert scoped_count == 2


def test_reclassify_applies_only_to_selected_movement_without_rule(db_session, catalogs):
    request = ReclassifyRequest(
        movement_ids=[catalogs["m3"].id],
        branch_id=catalogs["branch_alfredo"].id,
        category_id=catalogs["unclassified_category"].id,
        note="Clasificado manualmente por el usuario.",
        create_rule=False,
    )
    result = reclassify_movements(db_session, request)

    assert result.updated_movement_ids == [catalogs["m3"].id]
    assert result.created_rule_id is None
    assert result.retroactive_count == 0

    updated = db_session.get(Movement, catalogs["m3"].id)
    assert updated.branch_id == catalogs["branch_alfredo"].id
    assert updated.classification_status == "MANUAL"
    assert updated.classification_method == "MANUAL"

    history = (
        db_session.query(MovementClassificationHistory)
        .filter_by(movement_id=catalogs["m3"].id)
        .one()
    )
    assert history.previous_branch_id is None
    assert history.new_branch_id == catalogs["branch_alfredo"].id
    assert history.reason == "Clasificado manualmente por el usuario."
    assert history.create_rule is False

    # Los otros movimientos no seleccionados no deben verse afectados.
    untouched = db_session.get(Movement, catalogs["m1"].id)
    assert untouched.classification_status == "UNCLASSIFIED"


def test_reclassify_with_rule_applies_retroactively(db_session, catalogs):
    request = ReclassifyRequest(
        movement_ids=[catalogs["m1"].id],
        branch_id=None,
        category_id=catalogs["unclassified_category"].id,
        note=None,
        create_rule=True,
        rule_name="Uber",
        rule_pattern="UBER",
        rule_match_type=MatchType.CONTAINS.value,
        rule_case_sensitive=False,
        rule_bank_account_id=catalogs["bbva"].id,
        rule_priority=10,
    )
    result = reclassify_movements(db_session, request)

    assert result.updated_movement_ids == [catalogs["m1"].id]
    assert result.created_rule_id is not None
    # m2 también contiene "UBER" pero no fue seleccionado explícitamente:
    # debe reclasificarse retroactivamente gracias a la nueva regla.
    assert result.retroactive_count == 1

    m2 = db_session.get(Movement, catalogs["m2"].id)
    assert m2.classification_status == "CLASSIFIED"
    assert m2.classification_method == "SPECIAL_RULE"
    assert m2.matched_identifier == "UBER"

    # m3 no contiene "UBER" y no debe verse afectado.
    m3 = db_session.get(Movement, catalogs["m3"].id)
    assert m3.classification_status == "UNCLASSIFIED"

    history_for_m2 = (
        db_session.query(MovementClassificationHistory).filter_by(movement_id=m2.id).one()
    )
    assert history_for_m2.create_rule is True
