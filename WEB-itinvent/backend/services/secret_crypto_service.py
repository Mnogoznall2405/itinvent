"""
Encryption helpers for sensitive per-user credentials.
"""
from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache


class SecretCryptoError(RuntimeError):
    """Raised when crypto operations cannot be performed."""


def _as_fernet_key(raw_key: str) -> bytes:
    """
    Accept either:
    - canonical Fernet key (urlsafe base64, 32-byte payload)
    - arbitrary passphrase (derived via SHA-256 to Fernet key)
    """
    value = str(raw_key or "").strip()
    if not value:
        raise SecretCryptoError("MAIL_CREDENTIALS_KEY is not configured")

    try:
        decoded = base64.urlsafe_b64decode(value.encode("utf-8"))
        if len(decoded) == 32:
            return value.encode("utf-8")
    except Exception:
        pass

    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _build_fernet():
    try:
        from cryptography.fernet import Fernet
    except Exception as exc:  # pragma: no cover
        raise SecretCryptoError("cryptography package is not installed") from exc

    raw = os.getenv("MAIL_CREDENTIALS_KEY", "")
    key = _as_fernet_key(raw)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str:
    plain = str(value or "")
    if not plain:
        return ""
    token = _build_fernet().encrypt(plain.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(token: str | None) -> str:
    encoded = str(token or "").strip()
    if not encoded:
        return ""
    try:
        plain = _build_fernet().decrypt(encoded.encode("utf-8"))
    except Exception as exc:
        raise SecretCryptoError("Failed to decrypt secret value") from exc
    return plain.decode("utf-8")

