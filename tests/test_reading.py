"""The manual as a person reads it.

numbered_lines is the AGENT's view: every content line, prefixed with the
coordinate it would cite. Rendering that to a human produced a screen of
'0|  1|  2|' with letterhead between the paragraphs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from purser_core.corpus import Corpus
from purser_core.reading import reading_pages

pytestmark = pytest.mark.skipif(
    not Path("data/manual.sqlite").is_file(), reason="needs the built index"
)


@pytest.fixture
def corpus():
    return Corpus("data")


def test_section_reads_as_pages_in_order(corpus):
    pages = reading_pages(corpus, "4.2")
    assert len(pages) == 8
    assert [p.page_in_section for p in pages] == list(range(1, 9))


def test_every_page_of_a_long_section_is_returned(corpus):
    """Section 4.4 is 80 pages. The old UI showed 4 of them, then 40 lines."""
    assert len(reading_pages(corpus, "4.4")) == 80


def test_no_coordinates_and_no_furniture_reach_the_reader(corpus):
    for p in reading_pages(corpus, "4.2"):
        for b in p.blocks:
            assert "InterGlobe" not in b.text
            assert "NOT A CONTROLLED COPY" not in b.text
            assert "SAFETY AND EMERGENCY PROCEDURES MANUAL" not in b.text


def test_the_eight_empty_pages_are_marked_not_dropped(corpus):
    """Skipping a blank page would renumber the section against the paper
    manual she is cross-checking.

    None of the corpus's 8 zero-content pages fall in 4.2 or 4.4: 5 have no
    section at all (section=None, unreachable through `reading_pages` at
    all) and the other 3 sit in 3.5 (two) and 3.13 (one). A check against
    4.2/4.4 alone can only ever see `empty=False`, so it can never actually
    observe the branch it's named for -- it would pass identically if
    `empty` were hardcoded `False`. Use 3.13, the smallest section that has
    one of the real empty pages (pdf_page 484, page_in_section 8 of 12).
    """
    pages = reading_pages(corpus, "3.13")
    assert len(pages) == 12
    for p in pages:
        assert p.empty == (not p.blocks)
    # The universal check above must actually exercise both branches, not
    # just the (vacuously true) False one.
    assert any(p.empty for p in pages)


def test_an_empty_page_does_not_disturb_the_numbering_around_it(corpus):
    """The reason an empty page is kept rather than skipped: dropping it
    would shift every later page's `page_in_section` (and thus its label on
    screen) out of sync with the printed manual. Pin that the page right
    after the empty one keeps ITS correct number and content, not a
    number one lower than it should be."""
    pages = reading_pages(corpus, "3.13")
    empty = next(p for p in pages if p.empty)
    assert empty.pdf_page == 484
    assert empty.page_in_section == 8
    assert empty.blocks == []

    after = next(p for p in pages if p.page_in_section == 9)
    assert after.pdf_page == 485
    assert not after.empty
    assert after.blocks


# --- sections and tables flow across page breaks -------------------------------


def _page(pages, pdf_page):
    [p] = [p for p in pages if p.pdf_page == pdf_page]
    return p


def test_a_heading_keeps_owning_its_content_across_a_page_break(corpus):
    """pdf 299 opens '1.6 3 POINT BRIEFING' at its foot; the top of pdf 300 is still
    that briefing, so it is nested under it and the page says so."""
    p300 = _page(reading_pages(corpus, "3.5"), 300)
    assert p300.continues[-1] == "1.6         3 POINT BRIEFING"
    assert p300.blocks[0].kind != "heading"
    assert p300.blocks[0].depth == len(p300.continues)


def test_every_page_opens_at_the_depth_of_the_headings_it_continues(corpus):
    for section in ("4.2", "3.5", "4.4"):
        for p in reading_pages(corpus, section):
            if p.blocks and p.blocks[0].kind != "heading":
                assert p.blocks[0].depth == len(p.continues), (section, p.pdf_page)


def test_the_first_page_of_a_section_continues_nothing(corpus):
    assert reading_pages(corpus, "4.2")[0].continues == []


def test_a_table_continuing_from_the_previous_page_is_a_table_in_the_reader(corpus):
    """pdf 597 continues Table 4.4F (land vs ditching briefing) with no caption of
    its own; its two columns used to interleave top to bottom."""
    p597 = _page(reading_pages(corpus, "4.4"), 597)
    [first, *_] = [b for b in p597.blocks if b.kind == "table"]
    assert "To ABP1: You will inflate your life jacket" in first.text


def test_prose_after_a_page_that_ended_in_a_table_stays_prose(corpus):
    p182 = _page(reading_pages(corpus, "2.2"), 182)
    assert "table" not in [b.kind for b in p182.blocks]


def test_reading_a_section_twice_gives_the_same_pages(corpus):
    assert reading_pages(corpus, "3.5") == reading_pages(corpus, "3.5")


def test_no_reader_page_carries_an_empty_table(corpus):
    p759 = _page(reading_pages(corpus, "6.1"), 759)
    assert p759.blocks[0].kind == "heading"
    assert all(b.text for b in p759.blocks if b.kind == "table")
