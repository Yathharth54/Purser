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


def expand_query(corpus: Corpus, query: str) -> str:
    """Append short, manual-canonical expansions for glossary terms in the query.

    The manual defines its own vocabulary, so most of the gap between her words
    and the document's words is closed here rather than by the embedding model.

    Only short abbreviation-style definitions are injected (<= 80 characters).
    The value of expansion is mapping her word onto the manual's canonical
    term — "smoke hood" -> "Protective Breathing Equipment" — which is what
    the abbreviation table gives. Long prose definitions (glossary entries run
    up to 582 characters) are explanations that belong to `find_term`'s
    caller, not to search: appending one would drown a six-word question. At
    most 3 expansions are injected, in the order matched.
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

    if not additions:
        return query

    deduped = list(dict.fromkeys(additions))[:_MAX_EXPANSIONS]
    return f"{query} {' '.join(deduped)}"
