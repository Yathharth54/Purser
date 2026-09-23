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
