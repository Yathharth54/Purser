from __future__ import annotations

import re

from purser_core.models import GlossaryEntry, Page

# Only these sections define vocabulary. Section 3.1 is mostly prose despite its
# name ("Common Terminology") but carries a handful of TERM: lines.
_GLOSSARY_SECTIONS = {"1.2", "3.1"}

# "ABP – Able Bodied Passenger"  (en-dash, em-dash or hyphen)
_ABBR = re.compile(r"^(?P<term>[A-Z][A-Za-z0-9/\.\-]{0,11})\s*[–—-]\s+(?P<defn>\S.*)$")

# "TIME ZONE: Is a region of the earth..."
_PROSE = re.compile(r"^(?P<term>[A-Z][A-Z0-9 /\-\.\(\)&]{2,44}?)\s*:\s+(?P<defn>\S.*)$")

_MIN_DEFN = 3


def _split_columns(line: str) -> list[str]:
    """The abbreviations table is two columns separated by runs of 3+ spaces."""
    return [c.strip() for c in re.split(r"\s{3,}", line.strip()) if c.strip()]


def mine_glossary(pages: list[Page]) -> list[GlossaryEntry]:
    entries: dict[str, GlossaryEntry] = {}

    for page in pages:
        if page.section not in _GLOSSARY_SECTIONS:
            continue

        for line in page.lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Prose definitions occupy the whole line.
            if m := _PROSE.match(stripped):
                term = m.group("term").strip()
                defn = m.group("defn").strip()
                if len(defn) >= _MIN_DEFN:
                    entries.setdefault(term, GlossaryEntry(
                        term=term, definition=defn, pdf_page=page.pdf_page))
                continue

            # Abbreviation table: try each column independently.
            for chunk in _split_columns(stripped):
                if m := _ABBR.match(chunk):
                    term = m.group("term").strip()
                    defn = m.group("defn").strip()
                    if len(defn) >= _MIN_DEFN:
                        entries.setdefault(term, GlossaryEntry(
                            term=term, definition=defn, pdf_page=page.pdf_page))

    return list(entries.values())
