from datetime import date
from pathlib import Path

import pytest

from purser_agent.schemas import CiteRef
from purser_api.citations import resolve, resolve_all
from purser_core.blocks import parse_blocks
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
    # Page 600's real footer is "...Page 34 of 80...Effective 18 May 2023" --
    # asserted against that literal, not a made-up one, so a regression that
    # stops trimming the trailing edge actually fails this test.
    assert "Page 34 of 80" not in cite.text.splitlines()[-1]
    assert "life raft" in cite.text


def test_full_page_range_is_byte_exact_after_trimming(corpus):
    """Restates the byte-exact splice guarantee this task's trim requires.

    `Citation.text` being an exact splice of `Page.lines` is the one property
    the whole coordinate-only citation design exists to provide. It has to be
    pinned with exact equality on a page where the trim actually moves `lo`
    and `hi` -- not just checked with `in`/substring assertions -- or a bug
    that mangles the surviving window (drops a line, duplicates one, reorders
    one) could still pass.
    """
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=0, line_to=len(page.lines)))
    assert cite is not None
    assert cite.text == "\n".join(page.lines[12:43])


def test_interior_furniture_is_left_alone(corpus):
    """Trim the edges only.

    Removing an interior line would make the quote a non-contiguous fabrication
    -- text that appears nowhere on the page in that order. Edges are safe; the
    middle is not ours to edit.

    Page 15, not 600: page 600's chrome ([0, 5, 6, 9, 45]) all falls on the
    edge of its citable window -- the trimmed window is 12:43, which contains
    no chrome and no blank line, so a mutation that also stripped interior
    chrome would have nothing to strip and this test would pass for the wrong
    reason. Page 15's chrome ([5, 6, 48]) survives inside its trimmed window
    (0:46), so this actually exercises the "interior is untouched" guarantee.
    """
    page = corpus.page(15)
    cite = resolve(corpus, CiteRef(pdf_page=15, line_from=0, line_to=len(page.lines)))
    assert cite is not None
    assert cite.text in "\n".join(page.lines)


def test_a_citation_of_pure_furniture_resolves_to_none(corpus):
    assert resolve(corpus, CiteRef(pdf_page=314, line_from=0, line_to=20)) is None


def test_citation_carries_both_verbatim_text_and_parsed_blocks(corpus):
    """`text` stays the auditable splice; `blocks` is only how it is drawn.

    If these ever disagree about the words, the splice is the truth -- `text` is
    the guarantee the whole coordinate-only design exists to provide.
    """
    cite = resolve(corpus, CiteRef(pdf_page=552, line_from=12, line_to=23))
    assert cite is not None
    assert cite.text  # unchanged, byte-exact
    assert cite.blocks
    words = " ".join(" ".join(b.text.split()) for b in cite.blocks)
    assert "CREW RESPONSIBILTIES" in words


def test_a_resolved_citations_blocks_are_never_empty(corpus):
    """Can a citation's trimmed range parse to zero blocks? No: `resolve()`'s
    own trim loop only stops once `lo` (and, symmetrically, `hi - 1`) is
    neither chrome nor blank -- so the first line of the window handed to
    `parse_blocks` is always real content, which always yields at least one
    block. A pure-furniture range does not reach here at all: it returns
    `None` before `Citation` is ever built (see
    `test_a_citation_of_pure_furniture_resolves_to_none`). Pinned here on a
    single-line window, the tightest case there is."""
    page = corpus.page(600)
    cite = resolve(corpus, CiteRef(pdf_page=600, line_from=12, line_to=13))
    assert cite is not None
    assert cite.text == page.lines[12]
    assert cite.blocks  # never empty for a resolved citation


def test_chrome_is_rebased_onto_the_trimmed_slice_not_passed_page_absolute(corpus):
    """`parse_blocks(lines, chrome)` treats `chrome` as indices INTO the list
    it is handed. `resolve()` hands it a SLICE (`page.lines[lo:hi]`), so
    `page.chrome` -- which is page-absolute -- must be rebased by subtracting
    `lo`, or interior furniture is mis-skipped against the wrong lines.

    Page 9's chrome is `[0, 5, 6, 16, 19, 22, 25, 28, 31, 41]`; the trimmed
    citation window for the whole page is `8:37` (verified below against the
    real splice), so entries `16, 19, 22, 25, 28, 31` are interior to it.
    Passed unrebased against the 29-line SLICE, those same absolute numbers
    land on different, real content: local index 22 is absolute 30
    ('Aircraft Electronic Copy in the Electronic Flight'); local index 28 is
    absolute 36 ('A downloadable copy from the intranet portal...'). An
    unrebased call silently drops both real sentences and, going the other
    way, fails to skip the actual furniture (the 'ifly.SEP0000x' control-copy
    numbers), which leaks into the rendered blocks instead. A test that only
    checked "blocks is non-empty" would pass under either behaviour; this one
    pins the actual words, which only come out right when rebased.
    """
    page = corpus.page(9)
    cite = resolve(corpus, CiteRef(pdf_page=9, line_from=0, line_to=len(page.lines)))
    assert cite is not None
    assert cite.text == "\n".join(page.lines[8:37])  # the trim this test assumes

    words = " ".join(" ".join(b.text.split()) for b in cite.blocks)
    assert "Aircraft Electronic Copy" in words
    assert "downloadable copy" in words
    assert "ifly.SEP" not in words

    # Prove the fixture actually exercises the bug, rather than merely
    # asserting the fix: the SAME chrome list, passed unrebased against the
    # SAME slice, gets the words wrong in exactly the predicted way.
    lo, hi = 8, 37
    unrebased = parse_blocks(page.lines[lo:hi], [c for c in page.chrome if lo <= c < hi])
    unrebased_words = " ".join(" ".join(b.text.split()) for b in unrebased)
    assert "Aircraft Electronic Copy" not in unrebased_words
    assert "downloadable copy" not in unrebased_words
    assert "ifly.SEP" in unrebased_words
