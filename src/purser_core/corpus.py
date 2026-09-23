from __future__ import annotations

import json
import sqlite3
from functools import cached_property
from pathlib import Path

import numpy as np

from purser_core.models import GlossaryEntry, Page, TocNode

_COLUMNS = (
    "pdf_page, part, section, section_title, page_in_section, "
    "section_total, effective, revision, lines, chrome, text"
)


def _row_to_page(row: sqlite3.Row) -> Page:
    data = dict(row)
    data["lines"] = json.loads(data["lines"])
    data["chrome"] = json.loads(data["chrome"])
    return Page(**data)


class Corpus:
    """Read-only access to the built manual index. No network, no web framework."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.dir = Path(data_dir)
        self._con = sqlite3.connect(self.dir / "manual.sqlite", check_same_thread=False)
        self._con.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        return self._con

    @cached_property
    def vectors(self) -> np.ndarray:
        return np.load(self.dir / "vectors.npy")

    @cached_property
    def toc(self) -> list[TocNode]:
        return [TocNode(**n) for n in json.loads((self.dir / "toc.json").read_text())]

    @cached_property
    def glossary(self) -> list[GlossaryEntry]:
        return [GlossaryEntry(**g) for g in json.loads((self.dir / "glossary.json").read_text())]

    def page(self, pdf_page: int) -> Page:
        row = self._con.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE pdf_page = ?", (pdf_page,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no such page: {pdf_page}")
        return _row_to_page(row)

    def pages_in_section(self, section: str) -> list[Page]:
        rows = self._con.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE section = ? ORDER BY page_in_section",
            (section,),
        ).fetchall()
        return [_row_to_page(r) for r in rows]
