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
# One row of a section's printed contents page: an optional number, the
# title, dot leaders, and the page it points at. Leaders run in ASCII dots or
# ellipsis characters; the page is missing when it wrapped to its own line.
_TOC_ENTRY = re.compile(r"^(?:(\d+(?:\.\d+)*\.?)\s+)?(\S.*?)\s*[.…]{3,}[\s.…]*(\d{1,3})?$")
# Inside a contents run, a row whose leaders were lost: "3.15 TITLE 58".
_TOC_NO_LEADER = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+(\S.*?)\s+(\d{1,3})$")
_TOC_HEAD = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+(\S.*)$")
# A Word sub-bullet: a literal "o" and its padding, one level under a bullet.
_SUB_BULLET = re.compile(r"^o\s{2,}(\S.*)$")
# Where a wrapped para may take a lowercase line even though the line above
# stopped short of the column limit: its sentence plainly had not ended.
_OPEN_SENTENCE = re.compile(r"[A-Za-z,(]$")
# ...but never a lettered item, which starts lowercase and is a new line: "a)", "(ii)".
_LETTERED = re.compile(r"^\(?[a-z]{1,4}[).]\s")


def is_contents_page(lines: list[str], chrome: list[int]) -> bool:
    """Whether a page carries a printed contents list: a numbered leadered row,
    or two leadered rows that end in a page number. Checklists use dot leaders
    too ("PBE ........ DON", pdf 1164), but are never numbered and end in a
    word, not a page. A one-entry list (pdf 173) is still numbered."""
    skip = set(chrome)
    rows = 0
    for i, raw in enumerate(lines):
        if i in skip or not (m := _TOC_ENTRY.match(raw.strip())):
            continue
        if m.group(1):
            return True
        if m.group(3):
            rows += 1
            if rows >= 2:
                return True
    return False


def _toc_level(number: str | None) -> int:
    return number.rstrip(".").count(".") + 1 if number else 1


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

    def __init__(
        self, full: int, in_table: bool, table_indent: int | None, contents: bool = False
    ) -> None:
        self.full = full
        self.out: list[Block] = []
        self.open_indent: list[int | None] = []  # parallel to out; None once closed
        self.prev_len = 0
        self.in_table = in_table
        self.table: list[str] = []
        # The table's left edge: the lowest row indent so far.
        self.table_indent = table_indent if in_table else None
        self.pending_note = False  # the last block is a bare "Note:" awaiting its body
        # A contents page starts inside a contents run, so a wrapped entry
        # at the very top of the page is still read as one.
        self.contents = contents
        self.in_toc = contents
        # A numbered contents row still waiting for its leaders and page on
        # the next line; (raw line, block index) so it can be undone if the
        # run ends first and it was a real heading after all.
        self.toc_head: tuple[str, int] | None = None
        self.bullet_level = 0  # level of the last glyph bullet, for "o" sub-bullets

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

    def add_toc(self, number: str | None, title: str, page: str | None) -> None:
        self.out.append(
            Block(
                kind="toc",
                level=_toc_level(number),
                text=" ".join(title.split()),
                number=number.rstrip(".") if number else None,
                page=int(page) if page else None,
            )
        )
        self.open_indent.append(None)

    def feed_toc(self, stripped: str) -> bool:
        """Take `stripped` as part of a contents run, or end the run. Pure
        routing: True when the line was consumed."""
        entry = _TOC_ENTRY.match(stripped)
        if entry:
            number, title, page = entry.groups()
            head, self.toc_head = self.toc_head, None
            if head and number is None:
                # The second half of a wrapped entry: its leaders and page.
                last = self.out[head[1]]
                last.text = f"{last.text} {' '.join(title.split())}"
                last.page = int(page) if page else None
            else:
                self.add_toc(number, title, page)
            self.in_toc = True
            return True
        if not self.in_toc:
            return False
        last = self.out[-1] if self.out and self.out[-1].kind == "toc" else None
        if last and last.page is None and stripped.isdigit() and len(stripped) <= 3:
            last.page = int(stripped)  # the page number wrapped to its own line
            self.toc_head = None
            return True
        if not_leadered := _TOC_NO_LEADER.match(stripped):
            self.toc_head = None
            self.add_toc(*not_leadered.groups())
            return True
        if head := _TOC_HEAD.match(stripped):
            self.toc_head = None
            self.add_toc(head.group(1), head.group(2), None)
            self.toc_head = (stripped, len(self.out) - 1)
            return True
        self.end_toc()
        return False

    def end_toc(self) -> None:
        """Close a contents run. A numbered line that never got its leaders
        was not a contents row but a heading or step on a mixed page: put it
        back as the block it would have been."""
        self.in_toc = False
        if self.toc_head:
            stripped, i = self.toc_head
            self.toc_head = None
            numbered = _numbered(stripped)
            kind, level = numbered or ("para", 0)
            self.out[i] = Block(kind=kind, level=level, text=stripped)
            self.open_indent[i] = None

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

        if self.contents and not self.in_table and self.feed_toc(stripped):
            self.prev_len = 0
            return

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
        sub = _SUB_BULLET.match(stripped)
        if (
            awaiting_body
            and stripped[0] not in BULLET_GLYPHS
            and not sub
            and not numbered
            and not _NOTE.match(stripped)
        ):
            out[-1].text = f"{out[-1].text} {stripped}"
            self.prev_len = len(raw.rstrip())
            return

        if stripped[0] in BULLET_GLYPHS:
            self.bullet_level = max(0, indent // 5 - 1)
            self.add("bullet", stripped[1:].strip(), indent, self.bullet_level)
            self.prev_len = len(raw.rstrip())
            return

        if sub:
            # The marker is a letter, so it is dropped like a glyph and the
            # renderer draws the sub-bullet's own marker.
            self.add("bullet", sub.group(1).strip(), indent, self.bullet_level + 1)
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

        if out and self.open_indent[-1] is not None:
            prev_ind = self.open_indent[-1]
            prev = out[-1]
            wrapped = self.prev_len >= self.full or (
                # A para that stopped mid-sentence ("... (crew to point at")
                # continues on a lowercase line, whatever its length.
                prev.kind == "para"
                and self.prev_len > 0
                and stripped[0].islower()
                and not _LETTERED.match(stripped)
                and _OPEN_SENTENCE.search(prev.text) is not None
            )
            if wrapped and prev.kind in ("bullet", "step", "para", "note") and indent >= prev_ind:
                # A word hyphenated across the break ("take-" / "off") is
                # rejoined whole, not as "take- off".
                glue = "" if prev.text[-2:-1].isalpha() and prev.text.endswith("-") else " "
                prev.text = f"{prev.text}{glue}{stripped}".strip()
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
        wrap_width(lines, chrome) if full is None else full,
        start_in_table,
        table_indent,
        is_contents_page(lines, chrome),
    )
    for i, raw in enumerate(lines):
        if i not in skip:
            parser.feed(raw)
    parser.end_toc()
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
