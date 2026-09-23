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
# "Note:", "Note 1:", "Note -", "Note —", "Note. —". The punctuation is what
# separates a label from "Note the FAPs..." (a verb). The body is optional: a
# bare "Note:" on its own line takes the next line as its body.
_NOTE = re.compile(r"^(Note|Caution|Warning|NOTE|CAUTION|WARNING)(\s*\d+)?\s*[:\-—.]")
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


def wrap_width(lines: list[str], chrome: list[int]) -> int:
    """The width a line must reach to count as hard-wrapped, measured per page.

    70th percentile, not the max: one wide table row would otherwise set the
    bar so high that no prose line ever counts as wrapped.
    No floor at 0: `prev_len` starts at 0 and `prev_len >= full` is
    unconditionally true whenever `full <= 0`, so a floor here bought no
    protection -- a narrow page over-joining unrelated lines is a real, open
    risk, not one this function was actually closing.
    """
    skip = set(chrome)
    widths = sorted(len(s.rstrip()) for i, s in enumerate(lines) if i not in skip and s.strip())
    return (widths[int(len(widths) * 0.70)] - 4) if widths else 0


def _looks_like_row(raw: str) -> bool:
    stripped = raw.strip()
    return _ROW_GAP.search(raw.rstrip()) is not None and stripped[0] not in BULLET_GLYPHS


def opens_with_a_row(lines: list[str], chrome: list[int]) -> bool:
    """Whether a page's first content line is shaped like a table row.

    The confirmation half of carrying a table across a page break: "the
    previous page ended inside a table" is often wrong (a table that ran to
    the foot of its page, then prose overleaf -- pdf 181 -> 182), so a page
    only starts inside a table when its own first line agrees.
    """
    skip = set(chrome)
    for i, raw in enumerate(lines):
        if i not in skip and (stripped := raw.strip()):
            # A heading whose number is padded ("2.         EXTERIOR
            # DESCRIPTION", pdf 759) has a column-sized gap too, but a
            # heading or a caption can never continue a table.
            numbered = _numbered(stripped)
            if (numbered and numbered[0] == "heading") or _TABLE_CAP.match(stripped):
                return False
            return _looks_like_row(raw)
    return False


class _Parser:
    """One pass over one page's lines. The state lives here, not in globals,
    so a caller can start it mid-table and read where it ended -- but it is
    still fed a single page: any state crossing a page boundary is carried by
    the CALLER, through `start_in_table` / `table_indent`."""

    def __init__(self, full: int, in_table: bool, table_indent: int | None) -> None:
        self.full = full
        self.out: list[Block] = []
        self.open_indent: list[int | None] = []  # parallel to out; None once closed
        self.prev_len = 0
        self.in_table = in_table
        self.table: list[str] = []
        # The table's left edge: the lowest row indent so far.
        self.table_indent = table_indent if in_table else None
        self.pending_note = False  # the last block is a bare "Note:" awaiting its body

    def close_table(self) -> None:
        table = self.table
        while table and not table[0].strip():
            table.pop(0)
        while table and not table[-1].strip():
            table.pop()
        # Trim first, then test: a carried table closed before any row
        # arrived holds only blank lines, and must leave no empty block.
        if table:
            self.out.append(Block(kind="table", text="\n".join(table)))
            self.open_indent.append(None)
        self.in_table, self.table, self.table_indent = False, [], None

    def add(self, kind: str, text: str, indent: int | None, level: int = 0) -> None:
        self.out.append(Block(kind=kind, level=level, text=text))
        self.open_indent.append(indent)

    def feed(self, raw: str) -> None:
        out = self.out
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())

        if not stripped:
            if self.in_table:
                self.table.append("")
            self.prev_len = 0  # a blank line always ends a wrapped run
            return

        awaiting_body, self.pending_note = self.pending_note, False

        if _TABLE_CAP.match(stripped):
            self.close_table()
            self.add("caption", stripped, None)
            self.in_table = True
            self.prev_len = 0
            return

        numbered = _numbered(stripped)
        if numbered and numbered[0] == "heading":
            # At any indent, and even inside a table: a heading is the one
            # thing a table can never contain, so it is also the table's
            # most reliable terminator.
            self.close_table()
            self.add("heading", stripped, None, numbered[1])
            self.prev_len = len(raw.rstrip())
            return

        if self.in_table:
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
            looks_like_row = _looks_like_row(raw)
            table_indent = self.table_indent
            # A note label at the table's left edge with no column gap beside it
            # is a note ABOUT the table, not a cell in it (pdf_page 366). A note
            # set inside a column (pdf_pages 289, 814, 1144: well right of the
            # edge) or with its neighbouring cell's text beside it stays a row.
            # Known miss: pdf_page 622 has an in-cell note in the LEFT column
            # with its right cell empty -- indistinguishable, so it exits.
            note_exit = (
                not looks_like_row
                and _NOTE.match(stripped) is not None
                and (table_indent is None or indent <= table_indent + 2)
            )
            if not note_exit and (
                table_indent is None or indent >= table_indent - 2 or looks_like_row
            ):
                if table_indent is None:
                    self.table_indent = indent
                elif looks_like_row:
                    # The body, not the first row, defines the table's left
                    # edge: the first row is often a centred header (pdf_page
                    # 596), and a body row whose right cell is empty has no
                    # column gap left to vouch for it. Only a line that looks
                    # like a row may lower the edge. This is safe only because
                    # a heading closes a table before this test is reached --
                    # once the edge reaches column 0-2 the indent test can no
                    # longer fail.
                    self.table_indent = min(table_indent, indent)
                self.table.append(raw.rstrip())
                return
            self.close_table()
            # fall through: reprocess this line through normal classification

        # A bare "Note:" takes this line as its body -- unless the line is a
        # list item or another note, which the label introduces instead.
        if (
            awaiting_body
            and stripped[0] not in BULLET_GLYPHS
            and not numbered
            and not _NOTE.match(stripped)
        ):
            out[-1].text = f"{out[-1].text} {stripped}"
            self.prev_len = len(raw.rstrip())
            return

        if stripped[0] in BULLET_GLYPHS:
            self.add("bullet", stripped[1:].strip(), indent, max(0, indent // 5 - 1))
            self.prev_len = len(raw.rstrip())
            return

        if numbered:
            self.add("step", stripped, indent, max(0, indent // 5 - 1))
            self.prev_len = len(raw.rstrip())
            return

        note = _NOTE.match(stripped)
        if note:
            self.add("note", stripped, indent)
            self.pending_note = not stripped[note.end() :].strip()
            self.prev_len = len(raw.rstrip())
            return

        if out and self.open_indent[-1] is not None and self.prev_len >= self.full:
            prev_ind = self.open_indent[-1]
            if out[-1].kind in ("bullet", "step", "para", "note") and indent >= prev_ind:
                out[-1].text = f"{out[-1].text} {stripped}".strip()
                self.prev_len = len(raw.rstrip())
                return

        if stripped.isupper() and len(stripped) < 62:
            self.add("subheading", stripped, indent)
        else:
            self.add("para", stripped, indent)
        self.prev_len = len(raw.rstrip())


def _run(
    lines: list[str],
    chrome: list[int],
    start_in_table: bool,
    table_indent: int | None,
    full: int | None,
) -> _Parser:
    skip = set(chrome)
    parser = _Parser(
        wrap_width(lines, chrome) if full is None else full, start_in_table, table_indent
    )
    for i, raw in enumerate(lines):
        if i not in skip:
            parser.feed(raw)
    return parser


def parse_blocks(
    lines: list[str],
    chrome: list[int],
    *,
    start_in_table: bool = False,
    table_indent: int | None = None,
    full: int | None = None,
) -> list[Block]:
    """Parse one page (or a slice of one) into blocks. Pure.

    `chrome` indexes into `lines` as passed. The keywords carry state a caller
    knows and this function cannot: that the page opens inside a table begun
    earlier (`start_in_table`, with that table's left edge if known), and the
    page-level wrap width when `lines` is only a slice (`full`). Their
    defaults reproduce a standalone single-page parse.
    """
    parser = _run(lines, chrome, start_in_table, table_indent, full)
    parser.close_table()
    return parser.out


def table_state_after(
    lines: list[str],
    chrome: list[int],
    *,
    start_in_table: bool = False,
    table_indent: int | None = None,
    full: int | None = None,
) -> tuple[bool, int | None]:
    """Whether a table is still open after the last of `lines`, and its left edge."""
    parser = _run(lines, chrome, start_in_table, table_indent, full)
    return parser.in_table, parser.table_indent
