from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str, *, salt: str | None = None) -> str:
    normalized_salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        normalized_salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"{normalized_salt}${derived}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected = password_hash.split("$", maxsplit=1)
    except ValueError:
        return False
    candidate = hash_password(password, salt=salt).split("$", maxsplit=1)[1]
    return hmac.compare_digest(candidate, expected)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
