from pathlib import Path

import pytest

from purser_agent.schemas import CiteRef
from purser_api.citations import resolve, resolve_all
from purser_core.corpus import Corpus

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def corpus():
    return Corpus("data")


def test_full_page_range_reproduces_the_page_byte_for_byte(corpus):
    """Pins the half-open slice. An off-by-one here truncates a procedure step
    with no visible symptom."""
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=len(page.lines)))
    assert cite.text == "\n".join(page.lines)


def test_resolved_citation_carries_her_coordinates(corpus):
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=3))
    assert str(cite.part) == "PART FOUR"
    assert cite.section == "4.4"
    assert cite.section_title == "Evacuations"
    assert cite.page_in_section == 34
    assert cite.pdf_page == 600


def test_partial_range_is_exact(corpus):
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=2, line_to=5))
    assert cite.text == "\n".join(page.lines[2:5])


def test_out_of_range_lines_are_clamped_not_raised(corpus):
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=99999))
    assert cite is not None and cite.text


def test_unknown_page_returns_none_rather_than_killing_the_answer(corpus):
    assert resolve(corpus, CiteRef(pdf_page=1226, line_from=0, line_to=1)) is not None
    assert resolve_all(corpus, [CiteRef(pdf_page=1, line_from=500, line_to=501)]) == []


def test_resolve_all_drops_bad_refs_and_keeps_good_ones(corpus):
    refs = [
        CiteRef(pdf_page=600, line_from=0, line_to=2),
        CiteRef(pdf_page=1, line_from=900, line_to=901),
    ]
    assert len(resolve_all(corpus, refs)) == 1
