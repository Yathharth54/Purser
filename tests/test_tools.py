import re
from pathlib import Path

import pytest

from purser_core.tools import PurserTools

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def tools():
    return PurserTools("data")


def test_search_returns_hits_with_tree_coordinates(tools):
    hits = tools.search("ditching", k=5)
    assert hits
    h = hits[0]
    assert h.part and h.page_in_section >= 1 and h.snippet


def test_search_snippet_is_short_not_a_whole_page(tools):
    """search() is a locator. Reading is a separate, explicit act."""
    for hit in tools.search("evacuation", k=5):
        assert len(hit.snippet) <= 400


def test_read_section_returns_numbered_lines_in_order(tools):
    pages = tools.read_section("4.4", page_from=30, page_to=32)
    assert [p.page_in_section for p in pages] == [30, 31, 32]
    assert pages[0].numbered_lines[0].startswith("0|")


def test_read_section_clamps_out_of_range_requests(tools):
    pages = tools.read_section("4.4", page_from=78, page_to=999)
    assert pages[-1].page_in_section == 80


def test_read_section_default_range_covers_a_lead_in_offset_section(tools):
    """Section 1.1 opens at page_in_section 3 (Part One has a 2-page lead-in) and
    has 74 rows in the database, but its true last page is page_in_section 76 —
    len(pages) (74) is NOT the upper clamp bound, max(page_in_section) (76) is.

    A read_section that clamped against len(pages) instead of the section's
    actual page_in_section range would silently drop pages 75 and 76 from the
    default (whole-section) read. This pins that down against the real index.
    """
    pages = tools.read_section("1.1")
    assert [p.page_in_section for p in pages][0] == 3
    assert [p.page_in_section for p in pages][-1] == 76
    assert len(pages) == 74


def test_read_section_clamps_high_end_of_lead_in_offset_section(tools):
    """Requesting far beyond the end of an offset section must clamp to that
    section's real last page (76), not to its row count (74)."""
    pages = tools.read_section("1.1", page_from=1, page_to=999)
    assert pages[-1].page_in_section == 76


def test_read_page_includes_neighbours(tools):
    pages = tools.read_page(600, before=1, after=1)
    assert [p.pdf_page for p in pages] == [599, 600, 601]


def test_read_page_skips_out_of_range_neighbours_silently(tools):
    """Page 1 has no page 0; asking for a neighbour before it must not raise."""
    pages = tools.read_page(1, before=5, after=0)
    assert [p.pdf_page for p in pages] == [1]


def test_toc_lists_every_numbered_section(tools):
    assert len([n for n in tools.toc() if n.section]) == 37


def test_toc_filters_by_part(tools):
    """Filtering by Part keeps every node of that Part, including the
    section=None lead-in: Part Four opens with an unsectioned 2-page lead-in
    (pdf_page_from 523) before its four numbered sections begin. Those pages
    are real content, so they belong in "what Part Four contains" — dropping
    them would be inferring a section boundary the manual's own footers don't
    give us, which this project never does.
    """
    from purser_core.models import PartName

    nodes = tools.toc(part=PartName.FOUR)
    assert all(n.part is PartName.FOUR for n in nodes)
    assert {n.section for n in nodes} == {None, "4.1", "4.2", "4.3", "4.4"}

    lead_ins = [n for n in nodes if n.section is None]
    assert len(lead_ins) == 1
    assert lead_ins[0].pdf_page_from == 523


def test_lookup_term_returns_the_manuals_own_definition(tools):
    entry = tools.lookup_term("PAX")
    assert entry is not None and entry.definition == "Passenger"


def test_lookup_term_unknown_returns_none(tools):
    assert tools.lookup_term("zzzz") is None


# --- The one thing that matters most in this task ---
#
# numbered_lines is the substrate for every citation the finished app will ever
# show. The number printed before "|" in each entry MUST equal that line's
# index in Page.lines (0-based), because a later layer slices
# Page.lines[line_from:line_to] using numbers an agent read off numbered_lines.
# A silent off-by-one here shifts every quote in the whole application by one
# line while still looking completely plausible.


def test_numbered_lines_index_matches_page_lines_index_exactly(tools):
    pdf_page = 600
    page = tools.corpus.page(pdf_page)
    (page_text,) = tools.read_page(pdf_page)

    assert len(page_text.numbered_lines) == len(page.lines)

    for entry, expected_text in zip(page_text.numbered_lines, page.lines, strict=True):
        match = re.match(r"^(\d+)\| (.*)$", entry, re.DOTALL)
        assert match, f"malformed numbered_line entry: {entry!r}"
        line_no, text = int(match.group(1)), match.group(2)
        assert text == expected_text
        assert page.lines[line_no] == expected_text, (
            f"numbered_lines index {line_no} does not address the same text in "
            f"Page.lines (expected index {page.lines.index(expected_text)})"
        )

    # And directly: the printed number must equal the enumerate() index, start=0.
    printed_numbers = [int(re.match(r"(\d+)\|", e).group(1)) for e in page_text.numbered_lines]
    assert printed_numbers == list(range(len(page.lines)))
