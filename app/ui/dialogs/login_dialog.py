"""Diálogo de creación y validación del acceso local a la aplicación."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.services.authentication_service import hash_password, verify_master_password, verify_password

MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_SECONDS = 60


class _ForgotPasswordLabel(QLabel):
    activated = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.activated.emit()
        event.accept()


class LoginDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._is_first_access = not config.settings.login_password_hash
        self.setWindowTitle("Crear acceso" if self._is_first_access else "Iniciar sesión")
        self.setMinimumWidth(360)
        self._lockout_remaining = 0
        self._lockout_timer = QTimer(self)
        self._lockout_timer.setInterval(1000)
        self._lockout_timer.timeout.connect(self._on_lockout_tick)
        self._build_ui()
        if not self._is_first_access:
            self._apply_persisted_lockout()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        description = (
            "Crea las credenciales locales para proteger el acceso a la aplicación."
            if self._is_first_access
            else "Ingresa tus credenciales para continuar."
        )
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)

        form = QFormLayout()
        self._username_edit = QLineEdit()
        self._username_edit.setText(self._config.settings.login_username)
        self._username_edit.setPlaceholderText("Usuario")
        self._username_edit.setReadOnly(not self._is_first_access)
        form.addRow("Usuario:", self._username_edit)

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Contraseña")
        self._password_edit.returnPressed.connect(self._on_submit)
        form.addRow("Contraseña:", self._password_edit)

        self._confirmation_edit: QLineEdit | None = None
        if self._is_first_access:
            self._confirmation_edit = QLineEdit()
            self._confirmation_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirmation_edit.setPlaceholderText("Repite la contraseña")
            self._confirmation_edit.returnPressed.connect(self._on_submit)
            form.addRow("Confirmar:", self._confirmation_edit)
        layout.addLayout(form)

        if not self._is_first_access:
            self._lockout_label = QLabel("")
            self._lockout_label.setObjectName("statusWarning")
            self._lockout_label.setWordWrap(True)
            layout.addWidget(self._lockout_label)

            self._forgot_password_label = _ForgotPasswordLabel(
                "¿Olvidaste tu contraseña? Haz doble clic aquí para restablecerla."
            )
            self._forgot_password_label.setObjectName("cardLabel")
            self._forgot_password_label.setWordWrap(True)
            self._forgot_password_label.activated.connect(self._reset_password)
            layout.addWidget(self._forgot_password_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        self._submit_button = QPushButton("Crear acceso" if self._is_first_access else "Ingresar")
        self._submit_button.setObjectName("primaryButton")
        self._submit_button.clicked.connect(self._on_submit)
        buttons.addWidget(self._submit_button)
        layout.addLayout(buttons)

    def _on_submit(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        if self._is_first_access:
            self._create_access(username, password)
            return

        if self._remaining_lockout_seconds() > 0:
            return

        if verify_password(
            password,
            self._config.settings.login_password_hash,
            self._config.settings.login_password_salt,
        ):
            self._config.settings.login_failed_attempts = 0
            self._config.settings.login_lockout_until = ""
            self._config.save_settings()
            self.accept()
            return

        self._password_edit.clear()
        self._register_failed_attempt()

    def _register_failed_attempt(self) -> None:
        self._config.settings.login_failed_attempts += 1
        attempts = self._config.settings.login_failed_attempts

        if attempts >= MAX_LOGIN_ATTEMPTS:
            lockout_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=LOCKOUT_SECONDS)
            self._config.settings.login_lockout_until = lockout_until.isoformat()
            self._config.settings.login_failed_attempts = 0
            self._config.save_settings()
            QMessageBox.warning(
                self,
                "Demasiados intentos",
                f"Superaste el número máximo de intentos ({MAX_LOGIN_ATTEMPTS}). "
                f"Espera {LOCKOUT_SECONDS} segundos antes de volver a intentar.",
            )
            self._begin_lockout(LOCKOUT_SECONDS)
            return

        self._config.save_settings()
        remaining_attempts = MAX_LOGIN_ATTEMPTS - attempts
        QMessageBox.warning(
            self,
            "Credenciales inválidas",
            f"La contraseña no es correcta. Te queda(n) {remaining_attempts} "
            "intento(s) antes del bloqueo temporal.",
        )

    # ------------------------------------------------------------------
    # Bloqueo temporal tras exceder los intentos permitidos
    # ------------------------------------------------------------------
    def _remaining_lockout_seconds(self) -> int:
        raw = self._config.settings.login_lockout_until
        if not raw:
            return 0
        try:
            lockout_until = dt.datetime.fromisoformat(raw)
        except ValueError:
            return 0
        remaining = (lockout_until - dt.datetime.now(dt.timezone.utc)).total_seconds()
        return max(0, round(remaining))

    def _apply_persisted_lockout(self) -> None:
        remaining = self._remaining_lockout_seconds()
        if remaining > 0:
            self._begin_lockout(remaining)

    def _begin_lockout(self, seconds: int) -> None:
        self._lockout_remaining = seconds
        self._password_edit.setEnabled(False)
        self._submit_button.setEnabled(False)
        self._update_lockout_label()
        self._lockout_timer.start()

    def _update_lockout_label(self) -> None:
        self._lockout_label.setText(
            "Demasiados intentos fallidos. Intenta de nuevo en "
            f"{self._lockout_remaining} segundo(s)."
        )

    def _on_lockout_tick(self) -> None:
        self._lockout_remaining -= 1
        if self._lockout_remaining <= 0:
            self._end_lockout()
            return
        self._update_lockout_label()

    def _end_lockout(self) -> None:
        self._lockout_timer.stop()
        self._lockout_label.clear()
        self._password_edit.setEnabled(True)
        self._submit_button.setEnabled(True)
        self._config.settings.login_failed_attempts = 0
        self._config.settings.login_lockout_until = ""
        self._config.save_settings()
        self._password_edit.setFocus()

    def _create_access(self, username: str, password: str) -> None:
        if not username:
            QMessageBox.warning(self, "Usuario requerido", "Indica un nombre de usuario.")
            return
        if len(password) < 8:
            QMessageBox.warning(
                self, "Contraseña insegura", "La contraseña debe tener al menos 8 caracteres."
            )
            return
        if self._confirmation_edit is None or password != self._confirmation_edit.text():
            self._password_edit.clear()
            if self._confirmation_edit is not None:
                self._confirmation_edit.clear()
            QMessageBox.warning(self, "Contraseñas distintas", "Las contraseñas no coinciden.")
            return

        password_hash, password_salt = hash_password(password)
        self._config.settings.login_username = username
        self._save_password(password_hash, password_salt)
        self.accept()

    def _reset_password(self) -> None:
        master_password, accepted = QInputDialog.getText(
            self,
            "Restablecer contraseña",
            "Clave maestra:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        if not verify_master_password(master_password):
            QMessageBox.warning(self, "Clave inválida", "La clave maestra no es correcta.")
            return

        new_password, accepted = QInputDialog.getText(
            self,
            "Restablecer contraseña",
            "Nueva contraseña:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        if len(new_password) < 8:
            QMessageBox.warning(
                self, "Contraseña insegura", "La contraseña debe tener al menos 8 caracteres."
            )
            return

        confirmation, accepted = QInputDialog.getText(
            self,
            "Restablecer contraseña",
            "Confirmar nueva contraseña:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return
        if new_password != confirmation:
            QMessageBox.warning(self, "Contraseñas distintas", "Las contraseñas no coinciden.")
            return

        password_hash, password_salt = hash_password(new_password)
        self._save_password(password_hash, password_salt)
        self._password_edit.clear()
        self._password_edit.setFocus()
        QMessageBox.information(
            self, "Contraseña restablecida", "La contraseña se actualizó correctamente."
        )

    def _save_password(self, password_hash: str, password_salt: str) -> None:
        self._config.settings.login_password_hash = password_hash
        self._config.settings.login_password_salt = password_salt
        self._config.settings.login_failed_attempts = 0
        self._config.settings.login_lockout_until = ""
        self._config.save_settings()
        if self._lockout_timer.isActive():
            self._lockout_timer.stop()
            self._lockout_label.clear()
            self._password_edit.setEnabled(True)
            self._submit_button.setEnabled(True)