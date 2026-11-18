import datetime as dt

import pytest

from app.constants import CategoryCode, MatchType
from app.database.seed import seed_catalogs
from app.models import (
    BankAccount,
    Branch,
    ClassificationRule,
    ImportedFile,
    Movement,
    MovementCategory,
    MovementClassificationHistory,
)
from app.services.classification_service import (
    ReclassifyRequest,
    apply_rule_to_matching_movements,
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
    m4 = make_movement("Domic/6066887", "hash-u4")
    m4.charge_cents = 6844  # $68.44 = $59.00 base + $9.44 de IVA (16%)
    m5 = make_movement("Domic/1234567", "hash-u5")
    m5.charge_cents = 11600  # $116.00 = $100.00 base + $16.00 de IVA (16%)
    db_session.add_all([m1, m2, m3, m4, m5])
    db_session.flush()

    return {
        "bbva": bbva,
        "branch_alfredo": branch_alfredo,
        "unclassified_category": unclassified_category,
        "m1": m1,
        "m2": m2,
        "m3": m3,
        "m4": m4,
        "m5": m5,
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


def test_reclassify_inverts_charge_to_negative_payment_for_selected_movements(db_session, catalogs):
    # m3 llega como cargo (charge_cents=1000, payment_cents=0), pero es una
    # devolución que debe descontarse del abono en vez de sumarse al cargo.
    request = ReclassifyRequest(
        movement_ids=[catalogs["m3"].id],
        branch_id=None,
        category_id=catalogs["unclassified_category"].id,
        invert_to_negative_payment=True,
        create_rule=False,
    )
    reclassify_movements(db_session, request)

    updated = db_session.get(Movement, catalogs["m3"].id)
    assert updated.charge_cents == 0
    assert updated.payment_cents == -1000

    # Los no seleccionados no se tocan.
    untouched = db_session.get(Movement, catalogs["m1"].id)
    assert untouched.charge_cents == 1000
    assert untouched.payment_cents == 0


def test_reclassify_with_rule_inverts_retroactive_matches_too(db_session, catalogs):
    request = ReclassifyRequest(
        movement_ids=[catalogs["m1"].id],
        branch_id=None,
        category_id=catalogs["unclassified_category"].id,
        invert_to_negative_payment=True,
        create_rule=True,
        rule_name="Uber",
        rule_pattern="UBER",
        rule_match_type=MatchType.CONTAINS.value,
        rule_case_sensitive=False,
        rule_bank_account_id=catalogs["bbva"].id,
        rule_priority=10,
    )
    result = reclassify_movements(db_session, request)
    assert result.retroactive_count == 1

    m1 = db_session.get(Movement, catalogs["m1"].id)
    m2 = db_session.get(Movement, catalogs["m2"].id)
    for movement in (m1, m2):
        assert movement.charge_cents == 0
        assert movement.payment_cents == -1000

    created_rule = db_session.get(ClassificationRule, result.created_rule_id)
    assert created_rule.invert_to_negative_payment is True

    # m3 no coincide con el patrón y conserva su cargo original.
    m3 = db_session.get(Movement, catalogs["m3"].id)
    assert m3.charge_cents == 1000
    assert m3.payment_cents == 0


def test_apply_rule_to_matching_movements_inverts_and_skips_excluded(db_session, catalogs):
    rule = ClassificationRule(
        name="Uber",
        category_id=catalogs["unclassified_category"].id,
        pattern="UBER",
        match_type=MatchType.CONTAINS.value,
        priority=10,
        invert_to_negative_payment=True,
    )
    db_session.add(rule)
    db_session.flush()

    updated_count = apply_rule_to_matching_movements(
        db_session, rule, exclude_movement_ids={catalogs["m1"].id}
    )
    # Solo m2 coincide con "UBER" y no fue excluido.
    assert updated_count == 1

    m1 = db_session.get(Movement, catalogs["m1"].id)
    m2 = db_session.get(Movement, catalogs["m2"].id)
    assert m1.charge_cents == 1000  # excluido explícitamente, sin cambios
    assert m2.charge_cents == 0
    assert m2.payment_cents == -1000


def _vat_counterpart(session, movement_id: int) -> Movement:
    return session.query(Movement).filter_by(split_from_movement_id=movement_id).one()


def test_reclassify_splits_selected_movement_into_base_and_vat(db_session, catalogs):
    m4 = catalogs["m4"]
    request = ReclassifyRequest(
        movement_ids=[m4.id],
        branch_id=catalogs["branch_alfredo"].id,
        category_id=catalogs["unclassified_category"].id,
        split_vat_from_charge=True,
        create_rule=False,
    )
    result = reclassify_movements(db_session, request)
    assert result.updated_movement_ids == [m4.id]

    base = db_session.get(Movement, m4.id)
    assert base.charge_cents == 5900
    assert base.branch_id == catalogs["branch_alfredo"].id
    assert base.category_id == catalogs["unclassified_category"].id
    assert base.classification_status == "MANUAL"

    vat = _vat_counterpart(db_session, base.id)
    assert vat.description_original == "IVA Domic/6066887"
    assert vat.charge_cents == 944
    assert vat.payment_cents == 0
    assert vat.branch_id == catalogs["branch_alfredo"].id
    assert vat.category.code == CategoryCode.DIRECT_DEBIT_VAT.value
    assert vat.split_from_movement_id == base.id

    # m5 no fue seleccionado y no debe verse afectado.
    m5 = db_session.get(Movement, catalogs["m5"].id)
    assert m5.charge_cents == 11600


def test_reclassify_with_rule_splits_retroactive_matches_too(db_session, catalogs):
    request = ReclassifyRequest(
        movement_ids=[catalogs["m4"].id],
        branch_id=None,
        category_id=catalogs["unclassified_category"].id,
        split_vat_from_charge=True,
        create_rule=True,
        rule_name="Domiciliaciones",
        rule_pattern="DOMIC",
        rule_match_type=MatchType.CONTAINS.value,
        rule_case_sensitive=False,
        rule_bank_account_id=catalogs["bbva"].id,
        rule_priority=10,
    )
    result = reclassify_movements(db_session, request)
    assert result.retroactive_count == 1  # m5 coincide con "DOMIC" y no fue seleccionado

    created_rule = db_session.get(ClassificationRule, result.created_rule_id)
    assert created_rule.split_vat_from_charge is True

    base4 = db_session.get(Movement, catalogs["m4"].id)
    assert base4.charge_cents == 5900
    vat4 = _vat_counterpart(db_session, base4.id)
    assert vat4.charge_cents == 944

    base5 = db_session.get(Movement, catalogs["m5"].id)
    assert base5.charge_cents == 10000
    vat5 = _vat_counterpart(db_session, base5.id)
    assert vat5.charge_cents == 1600
    assert vat5.description_original == "IVA Domic/1234567"

    # m1/m2/m3 no coinciden con "DOMIC" y no deben verse afectados.
    m3 = db_session.get(Movement, catalogs["m3"].id)
    assert m3.charge_cents == 1000


def test_apply_rule_to_matching_movements_split_is_idempotent(db_session, catalogs):
    rule = ClassificationRule(
        name="Domiciliaciones",
        category_id=catalogs["unclassified_category"].id,
        pattern="DOMIC",
        match_type=MatchType.CONTAINS.value,
        priority=10,
        split_vat_from_charge=True,
    )
    db_session.add(rule)
    db_session.flush()

    first_count = apply_rule_to_matching_movements(db_session, rule)
    assert first_count == 2  # m4 y m5

    # Volver a aplicar la misma regla no debe partir de nuevo ni el
    # movimiento base (ya dividido) ni el de IVA generado (que también
    # coincide textualmente con "DOMIC").
    second_count = apply_rule_to_matching_movements(db_session, rule)
    assert second_count == 0

    base4 = db_session.get(Movement, catalogs["m4"].id)
    assert base4.charge_cents == 5900
    vat_rows = db_session.query(Movement).filter_by(split_from_movement_id=base4.id).all()
    assert len(vat_rows) == 1
    assert vat_rows[0].charge_cents == 944
