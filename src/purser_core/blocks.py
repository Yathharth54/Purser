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
_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+)*)\.\s+\S")
_NOTE = re.compile(r"^(Note|Caution|Warning|NOTE|CAUTION|WARNING)\s*[:\-]\s*\S")
_TABLE_CAP = re.compile(r"^Table\s+[\d.]+\s*[A-Z]?\s*$", re.IGNORECASE)


def parse_blocks(lines: list[str], chrome: list[int]) -> list[Block]:
    skip = set(chrome)
    body = [(i, s) for i, s in enumerate(lines) if i not in skip]

    widths = sorted(len(s.rstrip()) for _, s in body if s.strip())
    # 70th percentile, not the max: one wide table row would otherwise set the
    # bar so high that no prose line ever counts as wrapped.
    full = max(0, (widths[int(len(widths) * 0.70)] - 4) if widths else 0)

    out: list[Block] = []
    open_indent: list[int | None] = []  # parallel to out; None once a block is closed
    prev_len = 0
    in_table = False
    table: list[str] = []
    table_indent: int | None = None  # indent of the table's first row

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

        head = _NUM_HEAD.match(stripped)
        if head and indent <= 2:
            close_table()
            add("heading", stripped, None, head.group(1).count(".") + 1)
            prev_len = len(raw.rstrip())
            continue

        if in_table:
            # A table ends when a line's indent falls more than 2 columns below
            # the indent of the table's own first row. A stricter (< table_indent)
            # test would sever a real table at a wrapped header cell that sits a
            # column or two left of the first row (pdf_page 552); a looser one
            # (e.g. triggering on a bullet glyph or "Note:") would sever a real
            # table that legitimately carries either inside a cell (pdf_page 130,
            # pdf_page 552). Indent-drop past the tolerance is what a genuinely
            # new, page-margin block looks like; nothing narrower is safe.
            if table_indent is None or indent >= table_indent - 2:
                if table_indent is None:
                    table_indent = indent
                table.append(raw.rstrip())
                continue
            close_table()
            # fall through: reprocess this line through normal classification

        if stripped[0] in BULLET_GLYPHS:
            add("bullet", stripped[1:].strip(), indent, max(0, indent // 5 - 1))
            prev_len = len(raw.rstrip())
            continue

        if _NOTE.match(stripped):
            add("note", stripped, indent)
            prev_len = len(raw.rstrip())
            continue

        if out and open_indent[-1] is not None and prev_len >= full:
            prev_ind = open_indent[-1]
            if out[-1].kind in ("bullet", "para", "note") and indent >= prev_ind:
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
