"""Recover the manual's structure from its text layer.

`pdftotext -layout` preserves position, so headings, bullet nesting, notes and
two-column tables are all still present as indentation and glyphs -- they are
simply invisible if you render the lines one at a time in a monospace font.

The one judgement call is rejoining wrapped lines. A line is treated as the
continuation of the block above it only when the line above RAN TO THE COLUMN
LIMIT, measured per page. That is what distinguishes a hard-wrapped sentence
from a short standalone line, and without it the parser swallows the next
heading every time.
"""

from __future__ import annotations

import re

from purser_core.models import Block

# The manual's bullets are symbol-font glyphs in the Unicode private use area.
BULLET_GLYPHS = "•"
# A numbered line: "3.", "1.6", "1.2.", "1.46.4" then a title. Written so that
# no two quantifiers compete for the same digits -- `(?:\d+\.?)*` would
# backtrack exponentially on a long digit run.
_NUMBERED = re.compile(r"^(\d+\.(?:\d+\.)*\d*)\s+(\S.*)$")
# Table-of-contents rows: dot leaders, or a trailing page range like "3-76".
_TOC_ROW = re.compile(r"\.{5,}|\s\d+-\d+\s*$")
_NOTE = re.compile(r"^(Note|Caution|Warning|NOTE|CAUTION|WARNING)\s*[:\-]\s*\S")
_TABLE_CAP = re.compile(r"^Table\s+[\d.]+\s?[A-Z]{0,2}\d?\b.{0,40}$", re.IGNORECASE)
# A line "looks like a table row" when it has an internal multi-space column
# gap and does not open with a bullet glyph -- see the indent-drop comment
# below for why both halves of that test matter.
_ROW_GAP = re.compile(r"\S {3,}\S")


def _numbered(stripped: str) -> tuple[str, int] | None:
    """Classify a numbered line as ("heading", level) or ("step", 0).

    The manual numbers two different things the same way. A heading's title is
    set in capitals ("1.6  3 POINT BRIEFING"); a procedure step is a sentence
    ("6. Latch the lavatory and mark it inoperative."). Measured across the
    corpus, the capitals test separates them cleanly, where the old test --
    a trailing dot at indent <= 2 -- missed ~630 subsection headings (no
    trailing dot, or indented) and promoted ~200 steps to headings.
    Level comes from the number's depth: "3." is 1, "1.6" is 2, "1.46.4" is 3.
    """
    m = _NUMBERED.match(stripped)
    if not m or _TOC_ROW.search(stripped):
        return None
    letters = [ch for ch in m.group(2) if ch.isalpha()]
    if len(letters) >= 3 and sum(ch.isupper() for ch in letters) / len(letters) > 0.8:
        return "heading", m.group(1).rstrip(".").count(".") + 1
    return "step", 0


def parse_blocks(lines: list[str], chrome: list[int]) -> list[Block]:
    skip = set(chrome)
    body = [(i, s) for i, s in enumerate(lines) if i not in skip]

    widths = sorted(len(s.rstrip()) for _, s in body if s.strip())
    # 70th percentile, not the max: one wide table row would otherwise set the
    # bar so high that no prose line ever counts as wrapped.
    # No floor at 0: `prev_len` starts at 0 and `prev_len >= full` below is
    # unconditionally true whenever `full <= 0`, so a floor here bought no
    # protection -- a narrow page over-joining unrelated lines is a real,
    # open risk, not one this line was actually closing.
    full = (widths[int(len(widths) * 0.70)] - 4) if widths else 0

    out: list[Block] = []
    open_indent: list[int | None] = []  # parallel to out; None once a block is closed
    prev_len = 0
    in_table = False
    table: list[str] = []
    table_indent: int | None = None  # the table's left edge: the lowest row indent so far

    def close_table() -> None:
        nonlocal in_table, table, table_indent
        if table:
            while table and not table[0].strip():
                table.pop(0)
            while table and not table[-1].strip():
                table.pop()
            out.append(Block(kind="table", text="\n".join(table)))
            open_indent.append(None)
        in_table, table, table_indent = False, [], None

    def add(kind: str, text: str, indent: int | None, level: int = 0) -> None:
        out.append(Block(kind=kind, level=level, text=text))
        open_indent.append(indent)

    for _, raw in body:
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())

        if not stripped:
            if in_table:
                table.append("")
            prev_len = 0  # a blank line always ends a wrapped run
            continue

        if _TABLE_CAP.match(stripped):
            close_table()
            add("caption", stripped, None)
            in_table = True
            prev_len = 0
            continue

        numbered = _numbered(stripped)
        if numbered and numbered[0] == "heading":
            # At any indent, and even inside a table: a heading is the one
            # thing a table can never contain, so it is also the table's
            # most reliable terminator.
            close_table()
            add("heading", stripped, None, numbered[1])
            prev_len = len(raw.rstrip())
            continue

        if in_table:
            # A table ends when a line's indent falls more than 2 columns below
            # the table's left edge -- UNLESS that line still looks like a
            # table row. The first row is not always representative
            # of the table's left edge: a centred header label (pdf_page 613,
            # "A-320          A-321") can sit far to the right of the body rows
            # it labels, and indent-drop alone would close the table right after
            # the header. A line with an internal multi-space column gap is a
            # row regardless of indent; a line-initial bullet glyph is excluded
            # from that test because a glyph followed by its padding reads as a
            # column gap too (pdf_page 57), and would otherwise be wrongly
            # absorbed into the table it precedes. An in-cell glyph (pdf_page
            # 130) sits mid-row, not at indent-drop, so it is unaffected.
            looks_like_row = _ROW_GAP.search(raw.rstrip()) is not None and (
                stripped[0] not in BULLET_GLYPHS
            )
            if table_indent is None or indent >= table_indent - 2 or looks_like_row:
                if table_indent is None:
                    table_indent = indent
                elif looks_like_row:
                    # The body, not the first row, defines the table's left
                    # edge: the first row is often a centred header (pdf_page
                    # 596), and a body row whose right cell is empty has no
                    # column gap left to vouch for it. Only a line that looks
                    # like a row may lower the edge. This is safe only because
                    # a heading closes a table before this test is reached --
                    # once the edge reaches column 0-2 the indent test can no
                    # longer fail.
                    table_indent = min(table_indent, indent)
                table.append(raw.rstrip())
                continue
            close_table()
            # fall through: reprocess this line through normal classification

        if stripped[0] in BULLET_GLYPHS:
            add("bullet", stripped[1:].strip(), indent, max(0, indent // 5 - 1))
            prev_len = len(raw.rstrip())
            continue

        if numbered:
            add("step", stripped, indent, max(0, indent // 5 - 1))
            prev_len = len(raw.rstrip())
            continue

        if _NOTE.match(stripped):
            add("note", stripped, indent)
            prev_len = len(raw.rstrip())
            continue

        if out and open_indent[-1] is not None and prev_len >= full:
            prev_ind = open_indent[-1]
            if out[-1].kind in ("bullet", "step", "para", "note") and indent >= prev_ind:
                out[-1].text = f"{out[-1].text} {stripped}".strip()
                prev_len = len(raw.rstrip())
                continue

        if stripped.isupper() and len(stripped) < 62:
            add("subheading", stripped, indent)
        else:
            add("para", stripped, indent)
        prev_len = len(raw.rstrip())

    close_table()
    return out
