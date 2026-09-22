from __future__ import annotations

from itertools import groupby

from purser_core.models import Page, TocNode


def build_toc(pages: list[Page]) -> list[TocNode]:
    """Group pages into one node per (part, section), in document order."""
    nodes: list[TocNode] = []
    for (part, section), group in groupby(pages, key=lambda p: (p.part, p.section)):
        block = list(group)
        title = next((p.section_title for p in block if p.section_title), None)
        nodes.append(
            TocNode(
                part=part,
                section=section,
                title=title,
                pdf_page_from=block[0].pdf_page,
                pdf_page_to=block[-1].pdf_page,
                pages=len(block),
            )
        )
    return nodes
