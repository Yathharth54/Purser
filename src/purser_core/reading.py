"""The manual as a person reads it: whole pages, structured, in order.

This is the reading-side counterpart to `PurserTools.read_section` (which
serves numbered lines to the agent). Nothing here is spliced or sliced --
each page is parsed whole, so `page.chrome` is passed to `parse_blocks`
unmodified: it already indexes `page.lines` 1:1. Rebasing only matters where
a *slice* of a page's lines is handed to `parse_blocks` (see
`purser_api.citations.resolve`), which does not apply here.
"""

from __future__ import annotations

from typing import Protocol

from purser_core.blocks import parse_blocks
from purser_core.corpus import Corpus
from purser_core.models import ReadingPage


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


def reading_pages(corpus: Corpus, section: str) -> list[ReadingPage]:
    out: list[ReadingPage] = []
    for page in corpus.pages_in_section(section):
        blocks = parse_blocks(page.lines, page.chrome)
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
            )
        )
    return out
