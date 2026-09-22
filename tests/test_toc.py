from datetime import date

import pytest

from purser_core.models import Page, PartName
from purser_ingest.toc_build import build_toc


def _page(pdf_page, part, section, title, pis, total):
    return Page(
        pdf_page=pdf_page,
        part=part,
        section=section,
        section_title=title,
        page_in_section=pis,
        section_total=total,
        effective=date(2023, 5, 18),
        revision="Issue IX Revision 00",
        lines=["x"],
        text="x",
    )


def test_groups_contiguous_pages_into_one_node():
    pages = [
        _page(1, PartName.FOUR, "4.4", "Evacuations", 1, 2),
        _page(2, PartName.FOUR, "4.4", "Evacuations", 2, 2),
        _page(3, PartName.FIVE, "5.1", "Emergency Equipment", 1, 1),
    ]
    toc = build_toc(pages)
    assert len(toc) == 2
    assert toc[0].section == "4.4"
    assert toc[0].pdf_page_from == 1
    assert toc[0].pdf_page_to == 2
    assert toc[0].pages == 2
    assert toc[1].title == "Emergency Equipment"


def test_unsectioned_parts_become_one_node():
    pages = [_page(i, PartName.SEVEN, None, "First Aid", i, 3) for i in (1, 2, 3)]
    toc = build_toc(pages)
    assert len(toc) == 1
    assert toc[0].section is None
    assert toc[0].pages == 3


def test_sorts_by_pdf_page_before_grouping():
    """Out-of-order input must not desync the page range from the page count."""
    pages = [
        _page(1, PartName.FOUR, "4.4", "Evacuations", 1, 3),
        _page(3, PartName.FOUR, "4.4", "Evacuations", 3, 3),
        _page(2, PartName.FOUR, "4.4", "Evacuations", 2, 3),
    ]
    toc = build_toc(pages)
    assert len(toc) == 1
    assert toc[0].pdf_page_from == 1
    assert toc[0].pdf_page_to == 3
    assert toc[0].pages == 3


def test_repeated_section_key_across_a_gap_raises():
    """A section that reappears in a second, non-contiguous block of pages must
    fail loudly rather than silently produce two nodes for the same key."""
    pages = [
        _page(1, PartName.FOUR, "4.4", "Evacuations", 1, 1),
        _page(2, PartName.FIVE, "5.1", "Emergency Equipment", 1, 1),
        _page(3, PartName.FOUR, "4.4", "Evacuations", 1, 1),
    ]
    with pytest.raises(ValueError):
        build_toc(pages)
