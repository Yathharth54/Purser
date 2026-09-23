import numpy as np
import pytest

from purser_core.corpus import Corpus
from purser_core.embed import Embedder

pytestmark = pytest.mark.skipif(
    not (__import__("pathlib").Path("data/manual.sqlite").is_file()),
    reason="index not built — run `purser ingest` first",
)


@pytest.fixture(scope="module")
def corpus():
    return Corpus("data")


@pytest.fixture(scope="module")
def embedder():
    return Embedder()


def test_page_returns_full_record(corpus):
    page = corpus.page(600)
    assert page.pdf_page == 600
    assert page.section == "4.4"
    assert page.section_title == "Evacuations"
    assert page.page_in_section == 34
    assert isinstance(page.lines, list)


def test_pages_in_section_are_ordered(corpus):
    pages = corpus.pages_in_section("4.4")
    assert len(pages) == 80
    assert [p.page_in_section for p in pages] == list(range(1, 81))


def test_vectors_align_with_pdf_page(corpus, embedder):
    """vectors.npy row i must correspond to pdf_page i+1, exactly.

    A shape check alone would pass unchanged if the whole array were rolled
    by one row -- every semantic hit would then cite the wrong page while
    this test stayed green. Instead: embed a known page's OWN text and
    confirm that vector row is the single best match for it. Three
    well-separated pages so a shift of any size, not just by one, is caught.
    """
    assert corpus.vectors.shape == (1226, 384)

    for pdf_page in (121, 600, 900):
        page = corpus.page(pdf_page)
        q = embedder.encode([page.text])[0]
        scores = corpus.vectors @ q
        best_row = int(np.argmax(scores))
        assert best_row + 1 == pdf_page, (
            f"page {pdf_page}'s own text best-matches vector row {best_row} "
            f"(pdf_page {best_row + 1}), not its own row -- vectors.npy is "
            "misaligned with pdf_page"
        )


def test_unknown_page_raises(corpus):
    with pytest.raises(KeyError):
        corpus.page(99999)


def test_page_carries_its_chrome_indices(corpus):
    page = corpus.page(600)
    assert page.chrome, "page 600 prints letterhead; chrome must not be empty"
    assert all(0 <= i < len(page.lines) for i in page.chrome)
    for i in page.chrome:
        assert page.lines[i].strip(), "a blank line is never chrome"


def test_content_lines_keeps_ORIGINAL_indices(corpus):
    """The index is the citation coordinate. It must survive filtering.

    If content_lines() renumbered from zero, every CiteRef the agent emits would
    point at the wrong line -- and the failure would be silent, because the text
    spliced out would still look like plausible manual prose.
    """
    page = corpus.page(600)
    pairs = page.content_lines()
    assert len(pairs) == 31
    for i, text in pairs:
        assert page.lines[i] == text
        assert i not in page.chrome
