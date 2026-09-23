"""The manual as a person reads it: whole pages, structured, in order.

This is the reading-side counterpart to `PurserTools.read_section` (which
serves numbered lines to the agent). Nothing here is spliced or sliced --
each page is parsed whole, so `page.chrome` is passed to `parse_blocks`
unmodified: it already indexes `page.lines` 1:1. Rebasing only matters where
a *slice* of a page's lines is handed to `parse_blocks` (see
`purser_api.citations.resolve`), which does not apply here.
"""

from __future__ import annotations

from purser_core.blocks import parse_blocks
from purser_core.corpus import Corpus
from purser_core.models import ReadingPage


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
