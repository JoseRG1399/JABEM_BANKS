"""Pruebas del bloqueo temporal por intentos fallidos en el login
(3 intentos y 60 segundos de espera)."""
from __future__ import annotations

import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.config import Config
from app.services.authentication_service import hash_password
from app.ui.dialogs.login_dialog import LOCKOUT_SECONDS, MAX_LOGIN_ATTEMPTS, LoginDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def no_blocking_dialogs(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))


@pytest.fixture()
def config_with_password(config: Config) -> Config:
    password_hash, password_salt = hash_password("correcta123")
    config.settings.login_username = "admin"
    config.settings.login_password_hash = password_hash
    config.settings.login_password_salt = password_salt
    config.save_settings()
    return config


def _submit_wrong_password(dialog: LoginDialog) -> None:
    dialog._password_edit.setText("incorrecta")
    dialog._on_submit()


def test_login_succeeds_with_correct_password(qapp, no_blocking_dialogs, config_with_password):
    dialog = LoginDialog(config_with_password)
    dialog._password_edit.setText("correcta123")
    dialog._on_submit()

    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.deleteLater()


def test_wrong_password_does_not_lock_before_max_attempts(
    qapp, no_blocking_dialogs, config_with_password
):
    dialog = LoginDialog(config_with_password)

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        _submit_wrong_password(dialog)

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._password_edit.isEnabled()
    assert dialog._submit_button.isEnabled()
    assert config_with_password.settings.login_lockout_until == ""
    dialog.deleteLater()


def test_third_wrong_attempt_locks_out_for_one_minute(
    qapp, no_blocking_dialogs, config_with_password
):
    dialog = LoginDialog(config_with_password)

    for _ in range(MAX_LOGIN_ATTEMPTS):
        _submit_wrong_password(dialog)

    assert not dialog._password_edit.isEnabled()
    assert not dialog._submit_button.isEnabled()
    assert dialog._lockout_label.text()
    assert config_with_password.settings.login_lockout_until != ""

    lockout_until = dt.datetime.fromisoformat(config_with_password.settings.login_lockout_until)
    remaining = (lockout_until - dt.datetime.now(dt.timezone.utc)).total_seconds()
    assert 0 < remaining <= LOCKOUT_SECONDS

    dialog.deleteLater()


def test_correct_password_is_ignored_while_locked_out(
    qapp, no_blocking_dialogs, config_with_password
):
    dialog = LoginDialog(config_with_password)
    for _ in range(MAX_LOGIN_ATTEMPTS):
        _submit_wrong_password(dialog)

    dialog._password_edit.setText("correcta123")
    dialog._on_submit()

    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.deleteLater()


def test_lockout_persists_across_new_dialog_instances(
    qapp, no_blocking_dialogs, config_with_password
):
    """Simula reabrir la app: el bloqueo no debe reiniciarse solo por crear
    un nuevo diálogo con la misma configuración persistida."""
    first_dialog = LoginDialog(config_with_password)
    for _ in range(MAX_LOGIN_ATTEMPTS):
        _submit_wrong_password(first_dialog)
    first_dialog.deleteLater()

    second_dialog = LoginDialog(config_with_password)
    assert not second_dialog._password_edit.isEnabled()
    assert not second_dialog._submit_button.isEnabled()
    assert second_dialog._lockout_label.text()
    second_dialog.deleteLater()


def test_expired_lockout_does_not_block_new_dialog(qapp, no_blocking_dialogs, config_with_password):
    expired = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    config_with_password.settings.login_lockout_until = expired.isoformat()
    config_with_password.save_settings()

    dialog = LoginDialog(config_with_password)
    assert dialog._password_edit.isEnabled()
    assert dialog._submit_button.isEnabled()
    dialog.deleteLater()
