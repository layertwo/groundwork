"""Tests for account schema validation."""

import pytest
from pydantic import ValidationError

from backend.schemas.account import AccountUpdate


class TestAccountUpdateAliasValidation:
    def test_valid_alias(self):
        body = AccountUpdate(alias="my-prod-account")
        assert body.alias == "my-prod-account"

    def test_alias_min_length(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="ab")

    def test_alias_max_length(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="a" * 64)

    def test_alias_no_uppercase(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="MyAlias")

    def test_alias_no_special_chars(self):
        with pytest.raises(ValidationError):
            AccountUpdate(alias="my_alias!")

    def test_alias_empty_string_allowed(self):
        """Empty string means 'delete the alias'."""
        body = AccountUpdate(alias="")
        assert body.alias == ""


class TestAccountUpdateColorValidation:
    def test_valid_color(self):
        body = AccountUpdate(color="red")
        assert body.color == "red"

    def test_valid_camelcase_color(self):
        body = AccountUpdate(color="darkBlue")
        assert body.color == "darkBlue"

    def test_invalid_color(self):
        with pytest.raises(ValidationError):
            AccountUpdate(color="magenta")

    def test_none_color_clears(self):
        body = AccountUpdate(color="none")
        assert body.color == "none"

    def test_empty_string_clears(self):
        body = AccountUpdate(color="")
        assert body.color == ""
