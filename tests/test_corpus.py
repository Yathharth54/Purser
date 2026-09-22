import pytest

from purser_core.corpus import Corpus

pytestmark = pytest.mark.skipif(
    not (__import__("pathlib").Path("data/manual.sqlite").is_file()),
    reason="index not built — run `purser ingest` first",
)


@pytest.fixture(scope="module")
def corpus():
    return Corpus("data")


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


def test_vectors_align_with_pdf_page(corpus):
    assert corpus.vectors.shape == (1226, 384)


def test_unknown_page_raises(corpus):
    with pytest.raises(KeyError):
        corpus.page(99999)
