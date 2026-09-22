from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from purser_agent.lookup import PurserDeps, build_agent
from purser_core.tools import PurserTools


@lru_cache(maxsize=1)
def get_tools() -> PurserTools:
    return PurserTools(os.environ.get("PURSER_DATA_DIR", "data"))


@lru_cache(maxsize=1)
def get_agent():
    return build_agent(get_tools())


def get_deps() -> PurserDeps:
    return PurserDeps(tools=get_tools())


def get_pdf_path() -> Path:
    return Path(os.environ["PURSER_PDF_PATH"])
