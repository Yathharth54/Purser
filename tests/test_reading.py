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
    manual she is cross-checking."""
    pages = reading_pages(corpus, "4.2")
    for p in pages:
        assert p.empty == (not p.blocks)
