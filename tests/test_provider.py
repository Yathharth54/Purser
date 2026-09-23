"""The provider indirection: one env var swaps the whole backend.

These pin the mapping rather than the model, because the model string is the
one value this project deliberately never hardcodes outside `provider.py`.
"""

from __future__ import annotations

import pytest

from purser_agent.provider import (
    DEFAULT_MODEL,
    credentials_present,
    key_var,
    require_credentials,
    resolve_model,
)


def test_the_default_is_openai_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("PURSER_MODEL", raising=False)
    assert resolve_model() == DEFAULT_MODEL


def test_purser_model_is_passed_through_verbatim(monkeypatch):
    """No parsing, no rewriting -- pydantic-ai infers the provider itself."""
    monkeypatch.setenv("PURSER_MODEL", "openrouter:anthropic/claude-sonnet-4.5")
    assert resolve_model() == "openrouter:anthropic/claude-sonnet-4.5"


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("openai:gpt-4o", "OPENAI_API_KEY"),
        ("openrouter:anthropic/claude-sonnet-4.5", "OPENROUTER_API_KEY"),
        ("openrouter:openai/gpt-4o", "OPENROUTER_API_KEY"),
        # A provider we have never configured. Not an error -- pydantic-ai
        # supports many, and refusing to start on one would be worse.
        ("anthropic:claude-3-5-sonnet", None),
    ],
)
def test_each_provider_maps_to_its_own_key_variable(model, expected):
    assert key_var(model) == expected


def test_a_missing_key_names_the_variable_that_is_missing(monkeypatch):
    """The whole point of this check: an actionable sentence, not a 401."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        require_credentials("openrouter:openai/gpt-4o")


def test_an_empty_key_counts_as_missing(monkeypatch):
    """`OPENROUTER_API_KEY=` in a .env is the commonest way to get this wrong."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    assert credentials_present("openrouter:openai/gpt-4o") is False
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        require_credentials("openrouter:openai/gpt-4o")


def test_an_unknown_provider_is_assumed_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert credentials_present("anthropic:claude-3-5-sonnet") is True
    require_credentials("anthropic:claude-3-5-sonnet")  # must not raise
