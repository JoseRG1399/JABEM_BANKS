"""Autenticación local basada en contraseñas derivadas con PBKDF2."""
from __future__ import annotations

import hashlib
import hmac
import secrets

PASSWORD_HASH_ITERATIONS = 600_000
MASTER_PASSWORD = "Josh"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Devuelve el hash PBKDF2 y la sal usados para una contraseña."""
    password_salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("ascii"),
        PASSWORD_HASH_ITERATIONS,
    )
    return password_hash.hex(), password_salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    calculated_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(calculated_hash, password_hash)


def verify_master_password(password: str) -> bool:
    return hmac.compare_digest(password, MASTER_PASSWORD)