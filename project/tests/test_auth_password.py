from auth.password import PasswordManager


def test_passwords_use_argon2id_and_never_store_plaintext():
    manager = PasswordManager()
    password = "correct-horse-battery-staple"

    password_hash = manager.hash(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert manager.verify(password_hash, password) is True
    assert manager.verify(password_hash, "wrong-password") is False
