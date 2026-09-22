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
_MIN_TERM = 2  # drops NATO-phonetic single letters ("P – Papa"); useless for retrieval
_MAX_CONTINUATION_LINES = 6  # cap so a bad match can't swallow the rest of the page

# Footnote markers ("NOTE1:", "NOTE2:") happen to match the TERM: pattern but are
# not glossary terms.
_NOTE_MARKER = re.compile(r"^NOTE\s*\d*$", re.I)

# Recurring header/footer/masthead text. A prose definition must never absorb
# this even if it falls inside the continuation-merge window.
_PAGE_FURNITURE = re.compile(
    r"Issue\s+[IVX]+\s+Revision\s+\d+"
    r"|Effective\s+\d{1,2}\s+\w+\s+\d{4}"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|SAFETY AND EMERGENCY PROCEDURES MANUAL"
    r"|InterGlobe Aviation Limited"
    r"|ifly\.SEP"
    r"|NOT A CONTROLLED COPY",
    re.I,
)


def _split_columns(line: str) -> list[str]:
    """The abbreviations table is two columns separated by runs of 3+ spaces."""
    return [c.strip() for c in re.split(r"\s{3,}", line.strip()) if c.strip()]


def _is_abbr_row(stripped: str) -> bool:
    """True if this physical line is (part of) the two-column abbreviation table."""
    return any(_ABBR.match(chunk) for chunk in _split_columns(stripped))


def _valid_term(term: str) -> bool:
    if len(term) < _MIN_TERM:
        return False
    if _NOTE_MARKER.match(term):
        return False
    return True


def _record(entries: dict[str, GlossaryEntry], term: str, defn: str, pdf_page: int) -> None:
    if len(defn) >= _MIN_DEFN and _valid_term(term):
        entries.setdefault(term, GlossaryEntry(term=term, definition=defn, pdf_page=pdf_page))


def mine_glossary(pages: list[Page]) -> list[GlossaryEntry]:
    entries: dict[str, GlossaryEntry] = {}

    for page in pages:
        if page.section not in _GLOSSARY_SECTIONS:
            continue

        lines = page.lines
        n = len(lines)
        i = 0
        while i < n:
            stripped = lines[i].strip()
            i += 1
            if not stripped:
                continue

            # Prose definitions wrap across several physical lines in the source.
            # Merge continuation lines until a blank line, a new TERM:, an
            # abbreviation-table row, page furniture, or the cap -- whichever
            # comes first. The two-column table below is genuinely single-line
            # and must never be merged this way.
            if m := _PROSE.match(stripped):
                term = m.group("term").strip()
                parts = [m.group("defn").strip()]

                consumed = 0
                while i < n and consumed < _MAX_CONTINUATION_LINES:
                    nxt = lines[i].strip()
                    if not nxt or _PROSE.match(nxt) or _is_abbr_row(nxt) or _PAGE_FURNITURE.search(nxt):
                        break
                    parts.append(nxt)
                    consumed += 1
                    i += 1

                defn = re.sub(r"\s+", " ", " ".join(parts)).strip()
                _record(entries, term, defn, page.pdf_page)
                continue

            # Abbreviation table: try each column independently. Single-line only.
            for chunk in _split_columns(stripped):
                if m := _ABBR.match(chunk):
                    _record(entries, m.group("term").strip(), m.group("defn").strip(), page.pdf_page)

    return list(entries.values())
