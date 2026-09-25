from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from purser_core.corpus import Corpus
from purser_core.tools import PurserTools

if TYPE_CHECKING:
    from purser_agent.lookup import PurserDeps

# The agent package pulls in pydantic_ai (and through it MCP clients): over
# half the app's import time. It is imported only when a chat actually runs,
# so a cold start for the passcode check or the manual doesn't pay for it.


@lru_cache(maxsize=1)
def get_tools() -> PurserTools:
    return PurserTools(os.environ.get("PURSER_DATA_DIR", "data"))


def get_corpus() -> Corpus:
    """The reading endpoints need the raw corpus, not the agent's tool surface."""
    return get_tools().corpus


@lru_cache(maxsize=1)
def get_agent():
    from purser_agent.lookup import build_agent

    return build_agent(get_tools())


def get_deps() -> PurserDeps:
    from purser_agent.lookup import PurserDeps

    return PurserDeps(tools=get_tools())


def get_pdf_path() -> Path:
    return Path(os.environ["PURSER_PDF_PATH"])
