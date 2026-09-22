from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from purser_core.models import Page

_SCHEMA = """
DROP TABLE IF EXISTS pages;
DROP TABLE IF EXISTS pages_fts;

CREATE TABLE pages (
    pdf_page        INTEGER PRIMARY KEY,
    part            TEXT NOT NULL,
    section         TEXT,
    section_title   TEXT,
    page_in_section INTEGER NOT NULL,
    section_total   INTEGER NOT NULL,
    effective       TEXT NOT NULL,
    revision        TEXT,
    lines           TEXT NOT NULL,   -- JSON array, 0-indexed
    text            TEXT NOT NULL
);

CREATE INDEX idx_pages_section ON pages(part, section, page_in_section);

CREATE VIRTUAL TABLE pages_fts USING fts5(
    text,
    pdf_page UNINDEXED,
    tokenize = 'porter unicode61'
);
"""


def build_index(pages: list[Page], db_path: Path) -> None:
    """Write pages and the FTS5 index. Destructive and idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_SCHEMA)
        con.executemany(
            "INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    p.pdf_page, str(p.part), p.section, p.section_title,
                    p.page_in_section, p.section_total, p.effective.isoformat(),
                    p.revision, json.dumps(p.lines), p.text,
                )
                for p in pages
            ],
        )
        con.executemany(
            "INSERT INTO pages_fts (text, pdf_page) VALUES (?,?)",
            [(p.text, p.pdf_page) for p in pages],
        )
        con.commit()
    finally:
        con.close()
