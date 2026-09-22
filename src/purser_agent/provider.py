from __future__ import annotations

import os

DEFAULT_MODEL = "openai:gpt-4o"


def resolve_model() -> str:
    """The only place a model string is read. Swapping providers is one env var."""
    return os.environ.get("PURSER_MODEL", DEFAULT_MODEL)
