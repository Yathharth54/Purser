from pathlib import Path

import numpy as np
import pytest

from purser_core.corpus import Corpus
from purser_core.embed import Embedder
from purser_core.lexical import lexical_search
from purser_core.semantic import semantic_search

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def corpus():
    return Corpus("data")


@pytest.fixture(scope="module")
def embedder():
    return Embedder()


def test_lexical_finds_acronym_exactly(corpus):
    hits = lexical_search(corpus, "PBE", k=10)
    assert hits, "no hits for PBE"
    sections = {corpus.page(p).section for p, _ in hits}
    assert "5.1" in sections  # Emergency Equipment


def test_lexical_tolerates_fts_special_characters(corpus):
    """A bare quote or hyphen must not raise an FTS5 syntax error."""
    assert isinstance(lexical_search(corpus, 'what is a "slide-raft"?', k=5), list)


def test_lexical_returns_ranked_descending(corpus):
    hits = lexical_search(corpus, "evacuation commands", k=10)
    scores = [s for _, s in hits]
    assert scores == sorted(scores, reverse=True)


def test_semantic_bridges_her_words_to_the_manuals(corpus, embedder):
    """'smoke hood' never appears; the manual says Protective Breathing Equipment."""
    hits = semantic_search(corpus, embedder, "smoke hood", k=20)
    sections = {corpus.page(p).section for p, _ in hits}
    assert "5.1" in sections


def test_semantic_returns_k_results(corpus, embedder):
    assert len(semantic_search(corpus, embedder, "life raft", k=7)) == 7


class _FakeEmbedder:
    """Returns a fixed, caller-chosen vector regardless of query text."""

    def __init__(self, vector: np.ndarray) -> None:
        self._vector = vector

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.array([self._vector], dtype=np.float32)


class _FakeCorpus:
    """Duck-typed stand-in: semantic_search only needs `.vectors`."""

    def __init__(self, vectors: np.ndarray) -> None:
        self.vectors = vectors


def test_semantic_search_maps_vector_row_to_pdf_page_exactly():
    """Row index 2 in the vectors array must come back as pdf_page 3 (row + 1).

    This pins the row->page mapping down precisely, independent of section
    boundaries. A set-membership check against real manual sections is too
    weak here: sections span many contiguous pages, so an off-by-one in this
    mapping can shift every hit by one page without the target section ever
    leaving the result set. Getting this backwards is the worst defect this
    project can ship — citations would confidently point at the wrong page.
    """
    vectors = np.eye(5, dtype=np.float32)  # row i is a one-hot unit vector
    corpus = _FakeCorpus(vectors)
    embedder = _FakeEmbedder(vectors[2])  # exact match for row 2 only

    hits = semantic_search(corpus, embedder, "irrelevant query text", k=1)

    assert hits == [(3, 1.0)]  # row 2 -> pdf_page 3, cosine similarity 1.0
