from datetime import date
from pathlib import Path

import pytest

from purser_agent.schemas import CiteRef
from purser_api.citations import resolve, resolve_all
from purser_core.corpus import Corpus

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def corpus():
    return Corpus("data")


def test_resolved_citation_carries_her_coordinates(corpus):
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=15))
    assert str(cite.part) == "PART FOUR"
    assert cite.section == "4.4"
    assert cite.section_title == "Evacuations"
    assert cite.page_in_section == 34
    assert cite.pdf_page == 600
    # A quote stamped with the wrong revision/effective date is a superseded
    # procedure shown as current -- the exact failure this project exists to
    # prevent, so these are asserted explicitly rather than left implicit.
    assert cite.revision == "Issue IX Revision 00"
    assert cite.effective == date(2023, 5, 18)
    assert cite.label == "PART FOUR §4.4 p.34"


def test_partial_range_is_exact(corpus):
    """Pins the half-open slice. An off-by-one here truncates a procedure step
    with no visible symptom. (This is the test that goes red under a
    `line_to + 1` mutation -- see the task report's mutation-check transcript.)
    """
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=12, line_to=15))
    assert cite.text == "\n".join(page.lines[12:15])


def test_out_of_range_lines_are_clamped_not_raised(corpus):
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=99999))
    assert cite is not None and cite.text


def test_line_from_at_end_of_page_is_dropped_not_an_empty_quote(corpus):
    """`line_from == len(page.lines)` clamps `lo == hi` exactly. A model can
    emit this (e.g. an off-by-one in its own coordinates). If the emptiness
    check were ever loosened from `lo >= hi` to `lo > hi`, this would slip
    through as a citation with `text=""` -- an empty quote card -- instead
    of being dropped.
    """
    page = corpus.page(600)
    n = len(page.lines)
    assert resolve(corpus, CiteRef(pdf_page=600, line_from=n, line_to=n + 5)) is None


def test_out_of_bounds_line_range_on_a_real_page_is_dropped_from_resolve_all(corpus):
    """Page 1 is a real, existing page -- the bad part of this ref is the line
    range (line 500 is far past its length), not the page number."""
    assert resolve_all(corpus, [CiteRef(pdf_page=1, line_from=500, line_to=501)]) == []


def test_unknown_page_returns_none(corpus, monkeypatch):
    """The genuine unknown-page case: `Corpus.page()` raises `KeyError`."""

    def _raise(pdf_page: int):
        raise KeyError(pdf_page)

    monkeypatch.setattr(corpus, "page", _raise)
    assert resolve(corpus, CiteRef(pdf_page=1, line_from=0, line_to=1)) is None


def test_resolve_all_drops_bad_refs_and_keeps_good_ones(corpus):
    refs = [
        CiteRef(pdf_page=600, line_from=0, line_to=15),
        CiteRef(pdf_page=1, line_from=900, line_to=901),
    ]
    assert len(resolve_all(corpus, refs)) == 1


def test_resolve_all_of_no_refs_is_a_clean_empty_list(corpus):
    """A `not_in_manual=True` / zero-ref `Answer` is a normal result, not an
    error -- the API must render it without complaint."""
    assert resolve_all(corpus, []) == []


def test_leading_and_trailing_furniture_is_trimmed_from_a_citation(corpus):
    """Task 3 stops the model citing furniture. This stops it mattering when it does.

    A model asked for a whole page will still sometimes emit line_from=0. The
    quote card then opens with 'InterGlobe Aviation Limited / NOT A CONTROLLED
    COPY' instead of the procedure, which reads as though the manual says
    nothing useful.
    """
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=len(page.lines)))
    assert cite is not None
    assert "InterGlobe" not in cite.text.splitlines()[0]
    assert "NOT A CONTROLLED COPY" not in cite.text.splitlines()[0]
    assert "Page 1 of" not in cite.text.splitlines()[-1]
    assert "life raft" in cite.text


def test_interior_furniture_is_left_alone(corpus):
    """Trim the edges only.

    Removing an interior line would make the quote a non-contiguous fabrication
    -- text that appears nowhere on the page in that order. Edges are safe; the
    middle is not ours to edit.
    """
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=len(page.lines)))
    assert cite is not None
    assert cite.text in "\n".join(page.lines)


def test_a_citation_of_pure_furniture_resolves_to_none(corpus):
    assert resolve(corpus, CiteRef(pdf_page=314, line_from=0, line_to=20)) is None
