"""The manual as a person reads it: whole pages, structured, in order.

This is the reading-side counterpart to `PurserTools.read_section` (which
serves numbered lines to the agent). Nothing here is spliced or sliced --
each page is parsed whole, so `page.chrome` is passed to `parse_blocks`
unmodified: it already indexes `page.lines` 1:1. Rebasing only matters where
a *slice* of a page's lines is handed to `parse_blocks` (see
`purser_api.citations.resolve`), which does not apply here.

A section is read as ONE document split across pages, not as unrelated
pages: a table begun on page N may continue on page N+1 with no caption of
its own, and a heading on page N still owns the top of page N+1. That state
is carried here, by walking the section in order -- `parse_blocks` itself
stays a pure per-page function.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Protocol

from purser_core.blocks import opens_with_a_row, parse_blocks, table_state_after
from purser_core.corpus import Corpus
from purser_core.models import Page, ReadingPage
from purser_core.outline import HeadingStack, annotate_depth


class _HasPageInSection(Protocol):
    page_in_section: int


def clamp_by_page_in_section[P: _HasPageInSection](
    pages: list[P], page_from: int, page_to: int | None
) -> list[P]:
    """Keep only the pages whose `page_in_section` falls within [page_from, page_to].

    Shared by `PurserTools.read_section` (the agent's view, `Page` rows) and
    `GET /api/section/{section}` (the reader's view, `ReadingPage` rows) so
    the two never drift apart on this.

    Bounds are clamped against the actual `page_in_section` range of `pages`,
    not against `len(pages)`. Five sections (1.1, 2.1, 3.1, 4.1, 6.1) open at
    page_in_section 3 rather than 1 (each Part has a 2-page lead-in), so
    `len(pages)` undercounts a section's true last page by 2 for those
    sections -- using it here would silently drop the section's last two
    pages whenever `page_to` is left at its default or set beyond the
    section's end.

    `page_from` is clamped to at least 1 defensively: `PurserTools` has no
    request-validation layer of its own, unlike the FastAPI route (which
    already rejects a non-positive `page_from`/`page_to` with 422 via
    `Query(ge=1)` before this is ever called).
    """
    if not pages:
        return []
    last = max(p.page_in_section for p in pages)
    lo = max(1, page_from)
    hi = min(last, page_to) if page_to is not None else last
    return [p for p in pages if lo <= p.page_in_section <= hi]


@dataclass(frozen=True)
class PageStart:
    """What is still open at the top of a page, carried from the pages before it.

    There is no table edge here: a carried table's left edge is re-derived
    from the new page's own rows, since page N's indentation says nothing
    reliable about page N+1's.
    """

    in_table: bool = False
    stack: tuple[tuple[int, str], ...] = ()


# Per corpus, per section. The corpus is read-only at runtime, so a section's
# page starts never change; only these small records are cached, never the
# (mutable) blocks handed out to callers.
_STARTS: weakref.WeakKeyDictionary[Corpus, dict[str, dict[int, PageStart]]] = (
    weakref.WeakKeyDictionary()
)


def _walk(pages: list[Page]) -> dict[int, PageStart]:
    starts: dict[int, PageStart] = {}
    in_table, stack = False, ()
    for page in pages:
        # Carry a table only when this page agrees it opens with a row: "the
        # previous page ended in a table" alone is wrong whenever a table ran
        # to the foot of its page and prose follows overleaf (pdf 181 -> 182).
        carry = in_table and opens_with_a_row(page.lines, page.chrome)
        starts[page.pdf_page] = PageStart(carry, stack)
        blocks = parse_blocks(page.lines, page.chrome, start_in_table=carry)
        stack = tuple(annotate_depth(blocks, list(stack)))
        in_table, _ = table_state_after(page.lines, page.chrome, start_in_table=carry)
    return starts


def page_starts(corpus: Corpus, section: str) -> dict[int, PageStart]:
    """The carried state at the top of every page of `section`, by pdf_page."""
    by_section = _STARTS.setdefault(corpus, {})
    if section not in by_section:
        by_section[section] = _walk(corpus.pages_in_section(section))
    return by_section[section]


def page_start(corpus: Corpus, page: Page) -> PageStart:
    """The carried state at the top of `page`; a page outside any section starts clean."""
    if page.section is None:
        return PageStart()
    return page_starts(corpus, page.section).get(page.pdf_page, PageStart())


def reading_pages(corpus: Corpus, section: str) -> list[ReadingPage]:
    out: list[ReadingPage] = []
    starts = page_starts(corpus, section)
    for page in corpus.pages_in_section(section):
        start = starts[page.pdf_page]
        blocks = parse_blocks(page.lines, page.chrome, start_in_table=start.in_table)
        stack: HeadingStack = list(start.stack)
        annotate_depth(blocks, stack)
        out.append(
            ReadingPage(
                pdf_page=page.pdf_page,
                page_in_section=page.page_in_section,
                section_total=page.section_total,
                section=page.section,
                section_title=page.section_title,
                revision=page.revision,
                effective=page.effective,
                blocks=blocks,
                empty=not blocks,
                continues=[text for _, text in stack],
            )
        )
    return out
