from __future__ import annotations

import re

from purser_core.models import GlossaryEntry, Page

# Only these sections define vocabulary. Section 3.1 is mostly prose despite its
# name ("Common Terminology") but carries a handful of TERM: lines.
_GLOSSARY_SECTIONS = {"1.2", "3.1"}

# "ABP – Able Bodied Passenger"  (en-dash, em-dash or hyphen)
_ABBR = re.compile(r"^(?P<term>[A-Z][A-Za-z0-9/\.\-]{0,11})\s*[–—-]\s+(?P<defn>\S.*)$")

# A malformed abbreviation attempt: term characters running directly into a hyphen
# with no surrounding space ("FAP-Flight Attendant Panel"), so _ABBR's required
# `\s+` after the dash never matches. This must not be swallowed as a continuation
# of the previous entry in its column -- it is neither a valid entry nor prose.
_ABBR_LIKE_BUT_MALFORMED = re.compile(r"^[A-Z][A-Za-z0-9/\.]{0,10}-\S")

# Right column of the two-column abbreviation table starts well past this offset;
# the left column starts near the line's indentation. Used to route a continuation
# line (no "-" separator) to the same column as the entry it continues.
_RIGHT_COLUMN_INDENT = 20

# "TIME ZONE: Is a region of the earth..."
_PROSE = re.compile(r"^(?P<term>[A-Z][A-Z0-9 /\-\.\(\)&]{2,44}?)\s*:\s+(?P<defn>\S.*)$")

_MIN_DEFN = 3
_MIN_TERM = 2  # drops NATO-phonetic single letters ("P – Papa"); useless for retrieval
_MAX_CONTINUATION_LINES = 6  # cap so a bad match can't swallow the rest of the page

# Footnote markers ("NOTE1:", "NOTE2:") happen to match the TERM: pattern but are
# not glossary terms.
_NOTE_MARKER = re.compile(r"^NOTE\s*\d*$", re.IGNORECASE)

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
    re.IGNORECASE,
)


def _split_columns(line: str) -> list[str]:
    """The abbreviations table is two columns separated by runs of 3+ spaces."""
    return [c.strip() for c in re.split(r"\s{3,}", line.strip()) if c.strip()]


def _is_abbr_row(stripped: str) -> bool:
    """True if this physical line is (part of) the two-column abbreviation table."""
    return any(_ABBR.match(chunk) for chunk in _split_columns(stripped))


def _column_cells(raw_line: str) -> list[tuple[int, str]]:
    """Split a two-column table line into (column_index, text) cells.

    Column index (0 left, 1 right) is each cell's own character offset in the
    RAW (unstripped) line, not its position in the split -- a physical line can
    carry content in only one column when the other cell's entry continues from
    a previous row (see e.g. real page 121: "ACARS" wraps in the right column
    while the left column is blank on that line, then swaps on the next line).
    """
    cells: list[tuple[int, str]] = []
    offset = 0
    for piece in re.split(r"(\s{3,})", raw_line):
        text = piece.strip()
        if text:
            col = 0 if offset < _RIGHT_COLUMN_INDENT else 1
            cells.append((col, text))
        offset += len(piece)
    return cells


def _valid_term(term: str) -> bool:
    if len(term) < _MIN_TERM:
        return False
    return not _NOTE_MARKER.match(term)


def _record(entries: dict[str, GlossaryEntry], term: str, defn: str, pdf_page: int) -> None:
    if len(defn) >= _MIN_DEFN and _valid_term(term):
        entries.setdefault(term, GlossaryEntry(term=term, definition=defn, pdf_page=pdf_page))


def _flush_open_entry(
    open_entries: dict[int, tuple[str, list[str]]],
    col: int,
    entries: dict[str, GlossaryEntry],
    pdf_page: int,
) -> None:
    """Finalise and record the entry open in `col`, if any."""
    if col in open_entries:
        term, parts = open_entries.pop(col)
        defn = re.sub(r"\s+", " ", " ".join(parts)).strip()
        _record(entries, term, defn, pdf_page)


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
                    is_furniture = _is_abbr_row(nxt) or _PAGE_FURNITURE.search(nxt)
                    if not nxt or _PROSE.match(nxt) or is_furniture:
                        break
                    parts.append(nxt)
                    consumed += 1
                    i += 1

                defn = re.sub(r"\s+", " ", " ".join(parts)).strip()
                _record(entries, term, defn, page.pdf_page)
                continue

            # Two-column abbreviation table. Each column wraps independently: a
            # continuation line has no "-" separator in that column and belongs
            # to whichever entry is currently open in that SAME column. Consume
            # the whole contiguous table block (both columns) in one pass rather
            # than one physical line at a time, since a continuation for one
            # column can appear on a row where the other column starts a new
            # entry (or is blank).
            if _is_abbr_row(stripped):
                open_entries: dict[int, tuple[str, list[str]]] = {}

                j = i - 1  # re-examine the row already consumed above
                while j < n:
                    row = lines[j]
                    row_stripped = row.strip()
                    if not row_stripped or _PAGE_FURNITURE.search(row_stripped):
                        break
                    row_cells = _column_cells(row)
                    if not row_cells:
                        break
                    matched_any = False
                    for col, text in row_cells:
                        if m := _ABBR.match(text):
                            _flush_open_entry(open_entries, col, entries, page.pdf_page)
                            open_entries[col] = (m.group("term").strip(), [m.group("defn").strip()])
                            matched_any = True
                        elif _ABBR_LIKE_BUT_MALFORMED.match(text):
                            # Not a valid entry and not prose either -- close out
                            # whatever was open in this column rather than
                            # silently absorbing it as a continuation.
                            _flush_open_entry(open_entries, col, entries, page.pdf_page)
                            matched_any = True
                        elif col in open_entries:
                            open_entries[col][1].append(text)
                            matched_any = True
                    if not matched_any:
                        break
                    j += 1

                for col in list(open_entries):
                    _flush_open_entry(open_entries, col, entries, page.pdf_page)
                i = j
                continue

    return list(entries.values())
