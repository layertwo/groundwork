"""Tests for crypto service."""

from backend.services.crypto import decrypt_token, encrypt_token


class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "test-token-value"
        ciphertext = encrypt_token(plaintext)
        assert ciphertext != plaintext
        assert decrypt_token(ciphertext) == plaintext

    def test_decrypt_invalid_returns_none(self):
        assert decrypt_token("not-a-valid-fernet-token") is None

    def test_decrypt_tampered_returns_none(self):
        ciphertext = encrypt_token("original")
        tampered = ciphertext[:-5] + "XXXXX"
        assert decrypt_token(tampered) is None
