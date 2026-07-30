"""Diálogo de creación y validación del acceso local a la aplicación."""
from __future__ import annotations

from PySide6.QtCore import Signal
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
        self._build_ui()

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

        submit_button = QPushButton("Crear acceso" if self._is_first_access else "Ingresar")
        submit_button.setObjectName("primaryButton")
        submit_button.clicked.connect(self._on_submit)
        buttons.addWidget(submit_button)
        layout.addLayout(buttons)

    def _on_submit(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        if self._is_first_access:
            self._create_access(username, password)
            return
        if verify_password(
            password,
            self._config.settings.login_password_hash,
            self._config.settings.login_password_salt,
        ):
            self.accept()
            return
        self._password_edit.clear()
        QMessageBox.warning(self, "Credenciales inválidas", "La contraseña no es correcta.")

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
        self._config.save_settings()