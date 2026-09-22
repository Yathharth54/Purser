from __future__ import annotations

import re
from typing import TYPE_CHECKING

from purser_core.models import GlossaryEntry

if TYPE_CHECKING:
    from purser_core.corpus import Corpus

_WORD = re.compile(r"[A-Za-z0-9/]+")

# Above this length a glossary "definition" is prose explanation, not a
# canonical term worth injecting into a search query — see expand_query.
_MAX_DEFINITION_LEN = 80
_MAX_EXPANSIONS = 3
_MAX_REVERSE_EXPANSIONS = 3


def _index(corpus: Corpus) -> dict[str, GlossaryEntry]:
    """Lowercase term -> entry lookup, built once per corpus and cached on it.

    Cached as a private attribute on the Corpus instance the caller already
    holds, rather than in a module-level cache keyed by path or id() and
    rather than constructing a second Corpus: either of those would open a
    second SQLite connection to the same database just to re-read a list the
    caller already has in memory.
    """
    cached: dict[str, GlossaryEntry] | None = getattr(corpus, "_glossary_index", None)
    if cached is None:
        cached = {e.term.lower(): e for e in corpus.glossary}
        corpus._glossary_index = cached
    return cached


def find_term(corpus: Corpus, term: str) -> GlossaryEntry | None:
    return _index(corpus).get(term.strip().lower())


def _reverse_index(corpus: Corpus) -> dict[str, str]:
    """Bigram (from a short glossary DEFINITION) -> that entry's TERM.

    Cached on the Corpus instance for the same reason `_index` is (see its
    docstring). Restricted to short (<= 80 char) definitions — the
    abbreviation-table entries — for the same reason `expand_query`'s forward
    match is: long prose definitions are explanations, not vocabulary worth
    matching against.

    Keyed by bigram, not single word, so a query is only matched by two
    consecutive words that also appear consecutively in a definition — see
    `_reverse_matches`.
    """
    cached: dict[str, str] | None = getattr(corpus, "_glossary_reverse_index", None)
    if cached is None:
        cached = {}
        for entry in corpus.glossary:
            if len(entry.definition) > _MAX_DEFINITION_LEN:
                continue
            words = [w.lower() for w in _WORD.findall(entry.definition)]
            for a, b in zip(words, words[1:], strict=False):
                cached.setdefault(f"{a} {b}", entry.term)
        corpus._glossary_reverse_index = cached
    return cached


def _reverse_matches(corpus: Corpus, query: str) -> list[str]:
    """TERMs whose short definition shares a bigram with the query.

    Single-word matching would fire on any common word a definition happens
    to contain ("cabin", "flight", "crew") and flood every query; requiring
    two consecutive words to line up is specific enough to fire only on the
    phrase a definition actually names.
    """
    index = _reverse_index(corpus)
    words = [w.lower() for w in _WORD.findall(query)]
    matches: list[str] = []
    for a, b in zip(words, words[1:], strict=False):
        term = index.get(f"{a} {b}")
        if term:
            matches.append(term)
    return list(dict.fromkeys(matches))[:_MAX_REVERSE_EXPANSIONS]


def expand_query(corpus: Corpus, query: str) -> str:
    """Append short, manual-canonical expansions for glossary terms in the query.

    The manual defines its own vocabulary, so most of the gap between her words
    and the document's words is closed here rather than by the embedding model.

    Only short abbreviation-style definitions are injected (<= 80 characters).
    The value of expansion is mapping her word onto the manual's canonical
    term — "smoke hood" -> "Protective Breathing Equipment" — which is what
    the abbreviation table gives. Long prose definitions (glossary entries run
    up to 582 characters) are explanations that belong to `find_term`'s
    caller, not to search: appending one would drown a six-word question.

    This also runs the reverse direction: "cabin defect" never matches a
    glossary TERM (the forward loop only matches query tokens against terms),
    but it does match a bigram inside CDLB's definition, "Cabin Defect Log
    Book" — the manual's own name for this. That match injects the TERM
    (CDLB), not the definition, so the lexical lane can find the page that
    actually uses that abbreviation. See `_reverse_matches`.

    Forward and reverse expansions share one budget: at most 3 total, in the
    order matched (forward first, then reverse).
    """
    table = _index(corpus)
    additions: list[str] = []

    for token in _WORD.findall(query):
        entry = table.get(token.lower())
        if entry and len(entry.definition) <= _MAX_DEFINITION_LEN:
            additions.append(entry.definition)

    # Multi-word terms: check the whole lowered query for each known term.
    lowered = query.lower()
    for key, entry in table.items():
        if " " in key and key in lowered and len(entry.definition) <= _MAX_DEFINITION_LEN:
            additions.append(entry.definition)

    additions.extend(_reverse_matches(corpus, query))

    if not additions:
        return query

    deduped = list(dict.fromkeys(additions))[:_MAX_EXPANSIONS]
    return f"{query} {' '.join(deduped)}"
