from __future__ import annotations

import os

DEFAULT_MODEL = "openai:gpt-4o"

# Which environment variable carries the credential for each provider prefix.
#
# pydantic-ai infers the provider from the string's prefix and reads the key
# itself, so this mapping exists only so we can fail with a sentence that names
# the missing variable instead of surfacing a 401 from three layers down. Add a
# row here when adding a provider; the rest of the codebase needs no change.
_KEY_VAR = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def resolve_model() -> str:
    """The only place a model string is read. Swapping providers is one env var.

    `PURSER_MODEL` is passed to pydantic-ai verbatim, so anything it can infer
    works:

        openai:gpt-4o                             (default)
        openrouter:anthropic/claude-sonnet-4.5
        openrouter:openai/gpt-4o

    OpenRouter is the same OpenAI-compatible surface behind one account, which
    is why it needs no client of its own here.
    """
    return os.environ.get("PURSER_MODEL", DEFAULT_MODEL)


def key_var(model: str | None = None) -> str | None:
    """The env var holding the credential for `model`, or None if unrecognised.

    Unrecognised is not an error: pydantic-ai supports providers this project
    has never been configured for, and refusing to start on one would be worse
    than letting it try.
    """
    prefix = (model or resolve_model()).split(":", 1)[0]
    return _KEY_VAR.get(prefix)


def credentials_present(model: str | None = None) -> bool:
    """Whether the key for the configured provider is set and non-empty.

    Tests use this to skip live calls, so it must not raise on a provider we do
    not know about -- an unknown provider is assumed configured.
    """
    var = key_var(model)
    return True if var is None else bool(os.environ.get(var, "").strip())


def require_credentials(model: str | None = None) -> None:
    """Raise with a sentence that names the missing variable.

    Called at agent construction so the failure lands where someone can act on
    it, rather than as an opaque 401 mid-stream while she is waiting for an
    answer in a cabin.
    """
    resolved = model or resolve_model()
    if credentials_present(resolved):
        return
    var = key_var(resolved)
    raise RuntimeError(
        f"PURSER_MODEL is {resolved!r} but {var} is not set. "
        f"Put {var} in .env, or point PURSER_MODEL at a provider you have a key for."
    )
