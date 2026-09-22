from __future__ import annotations

from itertools import groupby

from purser_core.models import Page, PartName, TocNode


def build_toc(pages: list[Page]) -> list[TocNode]:
    """Group pages into one node per (part, section), in pdf_page order.

    `itertools.groupby` only groups CONSECUTIVE runs -- it does not sort. Without
    an explicit sort first, out-of-order input silently produces a node whose
    `pp a-b` range disagrees with its own `pages` count, and a section that
    reappears later (also out of order) produces two nodes sharing one section
    key, with lookups resolving to whichever is found first.
    """
    ordered = sorted(pages, key=lambda p: p.pdf_page)

    nodes: list[TocNode] = []
    seen_keys: set[tuple] = set()
    for (part, section), group in groupby(ordered, key=lambda p: (p.part, p.section)):
        key = (part, section)
        if key in seen_keys:
            raise ValueError(
                f"section {key} appears in more than one non-contiguous block of pages "
                "-- a duplicate or out-of-order footer, not a valid TOC"
            )
        seen_keys.add(key)

        block = list(group)
        title = next((p.section_title for p in block if p.section_title), None)
        if part is PartName.ANNEX:
            # On these pages the revision line's `pre` is empty, so header
            # reassembly splices the masthead line above onto "Annexures"
            # below, producing "SAFETY AND EMERGENCY PROCEDURES MANUAL
            # Annexures" -- that's not this section's title, it's the page
            # masthead run together with what the page actually says. This is
            # narrowly scoped to the Annexures node; masthead-as-title on
            # other unsectioned parts is a separate, pre-existing defect.
            title = "Annexures"
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
