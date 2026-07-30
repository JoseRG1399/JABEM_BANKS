"""Pruebas de humo de la interfaz: instancian las páginas reales contra una
base de datos real y ejecutan su ``refresh()``. No hay forma de tomar
capturas de una app de escritorio en este entorno, así que esto es lo más
cercano a "verificar que la UI no truena" de forma automatizada.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datetime as dt

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.database.seed import seed_catalogs
from app.models import BankAccount, Branch, ClassificationRule, ImportedFile, Movement
from app.ui.dialogs.branch_dialog import BranchDialog
from app.ui.dialogs.classify_movement_dialog import ClassifyMovementDialog
from app.ui.dialogs.rule_dialog import RuleDialog
from app.ui.main_window import MainWindow
from app.ui.pages.import_page import ImportPage
from app.ui.pages.reports_page import REPORT_TYPES, ReportsPage
from app.ui.pages.settings_page import SettingsPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def no_blocking_dialogs(monkeypatch):
    """Los QMessageBox.exec() bloquean esperando clic del usuario; en un
    entorno offscreen sin interacción eso colgaría la prueba para siempre.
    Se neutralizan para poder ejercitar el código que hay detrás de ellos.
    """
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )


@pytest.fixture()
def seeded_database(database):
    with database.session_scope() as session:
        seed_catalogs(session)
        bbva = session.query(BankAccount).filter_by(alias="BBVA").one()

        imported_file = ImportedFile(
            bank_account_id=bbva.id,
            original_name="extracto.txt",
            stored_name="extracto.txt",
            original_path="C:/tmp/extracto.txt",
            file_type="TXT",
            file_hash="hash-smoke-test",
            file_size=10,
        )
        session.add(imported_file)
        session.flush()

        session.add(
            Movement(
                bank_account_id=bbva.id,
                imported_file_id=imported_file.id,
                movement_date=dt.date(2026, 7, 1),
                description_original="MOVIMIENTO DE PRUEBA",
                normalized_text="MOVIMIENTO DE PRUEBA",
                charge_cents=1000,
                payment_cents=0,
                movement_hash="hash-smoke-movement",
                occurrence_number=1,
                classification_status="UNCLASSIFIED",
                classification_method="NONE",
                source_row_number=1,
            )
        )
    return database


def test_main_window_builds_and_navigates_all_pages(qapp, config, seeded_database):
    window = MainWindow(config, seeded_database)
    try:
        for key in [
            "dashboard",
            "import",
            "movements",
            "unclassified",
            "branches",
            "rules",
            "reports",
            "settings",
        ]:
            window.navigate_to(key)
    finally:
        window.close()
        window.deleteLater()


def test_import_page_clear_form_resets_all_controls(qapp, config, seeded_database, tmp_path):
    page = ImportPage(config, seeded_database)
    try:
        file_path = tmp_path / "movimientos.txt"
        file_path.write_text("contenido de prueba", encoding="utf-8")
        page._set_selected_file(str(file_path))

        assert page._selected_file == file_path
        assert page._bank_combo.currentData() is not None
        assert page._account_combo.currentData() is not None

        page._clear_form()

        assert page._selected_file is None
        assert page._bank_combo.currentIndex() == -1
        assert page._account_combo.count() == 0
        assert page._file_type_label.text() == ""
        assert page._preview.toPlainText() == ""
        assert page._validation_label.text() == ""
        assert not page._validate_button.isEnabled()
        assert not page._import_button.isEnabled()
    finally:
        page.close()
        page.deleteLater()


def test_classify_movement_dialog_builds(qapp, config, seeded_database):
    with seeded_database.session_scope() as session:
        movement_id = session.query(Movement).filter_by(movement_hash="hash-smoke-movement").one().id

    dialog = ClassifyMovementDialog(seeded_database, [movement_id])
    try:
        assert dialog.windowTitle()
    finally:
        dialog.close()
        dialog.deleteLater()


def test_branch_dialog_builds_for_new_and_existing_branch(qapp, config, seeded_database):
    with seeded_database.session_scope() as session:
        branch_id = session.query(Branch).filter_by(branch_number="01").one().id

    new_dialog = BranchDialog(seeded_database, branch_id=None)
    try:
        assert new_dialog.windowTitle() == "Nueva sucursal"
    finally:
        new_dialog.close()
        new_dialog.deleteLater()

    edit_dialog = BranchDialog(seeded_database, branch_id=branch_id)
    try:
        assert edit_dialog.windowTitle() == "Editar sucursal"
    finally:
        edit_dialog.close()
        edit_dialog.deleteLater()


def test_rule_dialog_builds_for_new_and_existing_rule(qapp, config, seeded_database):
    with seeded_database.session_scope() as session:
        rule = session.query(ClassificationRule).first()
        rule_id = rule.id if rule else None

    new_dialog = RuleDialog(seeded_database, rule_id=None)
    try:
        assert new_dialog.windowTitle() == "Nueva regla"
    finally:
        new_dialog.close()
        new_dialog.deleteLater()

    assert rule_id is not None
    edit_dialog = RuleDialog(seeded_database, rule_id=rule_id)
    try:
        assert edit_dialog.windowTitle() == "Editar regla"
    finally:
        edit_dialog.close()
        edit_dialog.deleteLater()


def test_reports_page_generates_every_report_type(qapp, config, seeded_database, tmp_path):
    page = ReportsPage(config, seeded_database)
    try:
        for _label, key in REPORT_TYPES:
            index = page._type_combo.findData(key)
            page._type_combo.setCurrentIndex(index)
            page._on_generate()

            export_path = tmp_path / f"{key}.xlsx"
            if key == "consolidated" and page._current_consolidated is not None:
                from app.services import export_service

                export_service.export_consolidated_report_to_excel(
                    page._current_consolidated, "Abono", page._current_filters(), export_path
                )
                assert export_path.exists()
            elif key not in ("unclassified",) and page._current_rows:
                from app.services import export_service

                export_service.export_simple_report_to_excel(
                    page._current_title, page._current_rows, page._current_filters(), export_path
                )
                assert export_path.exists()
    finally:
        page.close()
        page.deleteLater()


def test_settings_page_save_general_and_aliases(qapp, config, seeded_database, no_blocking_dialogs):
    page = SettingsPage(config, seeded_database)
    try:
        page._company_edit.setText("Empresa de prueba")
        page._rows_per_page_spin.setValue(75)
        page._on_save_general()

        assert config.settings.company_name == "Empresa de prueba"
        assert config.settings.rows_per_page == 75

        page._on_save_aliases()
        page.refresh()
    finally:
        page.close()
        page.deleteLater()


def test_settings_page_create_and_list_backup(qapp, config, seeded_database, no_blocking_dialogs):
    page = SettingsPage(config, seeded_database)
    try:
        page._on_create_backup()
        assert len(page._backups) >= 1
    finally:
        page.close()
        page.deleteLater()
