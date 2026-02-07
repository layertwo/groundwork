"""Tests for job service helper functions."""

from backend.services.jobs import _sanitize_error


class TestSanitizeError:
    def test_account_creation_failed_passes_through(self):
        exc = RuntimeError("Account creation failed: EMAIL_ALREADY_EXISTS")
        assert _sanitize_error(exc) == "Account creation failed: EMAIL_ALREADY_EXISTS"

    def test_account_creation_timed_out_passes_through(self):
        exc = RuntimeError("Account creation timed out")
        assert _sanitize_error(exc) == "Account creation timed out"

    def test_generic_error_is_sanitized(self):
        exc = RuntimeError("boto3 credential error: secret key leaked")
        assert _sanitize_error(exc) == "Operation failed — see server logs for details"
