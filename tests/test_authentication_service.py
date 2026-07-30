from app.services.authentication_service import hash_password, verify_master_password, verify_password


def test_password_hash_can_be_verified():
    password_hash, salt = hash_password("contraseña-segura")

    assert verify_password("contraseña-segura", password_hash, salt)


def test_password_hash_rejects_another_password():
    password_hash, salt = hash_password("contraseña-segura")

    assert not verify_password("contraseña-incorrecta", password_hash, salt)


def test_password_hash_uses_a_unique_salt():
    first_hash, first_salt = hash_password("contraseña-segura")
    second_hash, second_salt = hash_password("contraseña-segura")

    assert first_salt != second_salt
    assert first_hash != second_hash


def test_master_password_is_required_for_password_recovery():
    assert verify_master_password("Josh")
    assert not verify_master_password("josh")