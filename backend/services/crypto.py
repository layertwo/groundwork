"""Symmetric encryption for token storage using Fernet.

Derives a Fernet key from the session_secret via PBKDF2 so the secret
can be any arbitrary string rather than a base64-encoded 32-byte key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings

_KEY = base64.urlsafe_b64encode(
    hashlib.pbkdf2_hmac("sha256", settings.session_secret.encode(), b"gw-token-enc", 100_000)
)
_fernet = Fernet(_KEY)


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str | None:
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return None
