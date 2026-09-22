from __future__ import annotations

import re

from purser_core.corpus import Corpus

_TOKEN = re.compile(r"[A-Za-z0-9/]+")


def _to_fts_query(query: str) -> str:
    """Quote every token so user punctuation can never be FTS5 syntax.

    'what is a "slide-raft"?' -> '"what" OR "is" OR "a" OR "slide" OR "raft"'
    """
    tokens = _TOKEN.findall(query)
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else '""'


def lexical_search(corpus: Corpus, query: str, k: int = 20) -> list[tuple[int, float]]:
    """BM25 over page text. Carries acronyms and terms of art."""
    fts = _to_fts_query(query)
    if fts == '""':
        return []
    rows = corpus.connection.execute(
        "SELECT pdf_page, bm25(pages_fts) AS score FROM pages_fts "
        "WHERE pages_fts MATCH ? ORDER BY score LIMIT ?",
        (fts, k),
    ).fetchall()
    # bm25() returns lower-is-better; negate so higher is better everywhere.
    return [(int(r["pdf_page"]), -float(r["score"])) for r in rows]
