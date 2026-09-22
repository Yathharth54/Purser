from datetime import date

import numpy as np
import pytest

from purser_core.embed import Embedder
from purser_core.models import Page, PartName
from purser_ingest.embed_build import build_vectors


@pytest.fixture(scope="module")
def embedder():
    return Embedder()


def test_encode_shape_and_normalisation(embedder):
    vecs = embedder.encode(["brace for impact", "life raft deployment"])
    assert vecs.shape == (2, 384)
    assert vecs.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-5)


def test_related_text_scores_higher_than_unrelated(embedder):
    v = embedder.encode(["protective breathing equipment", "smoke hood", "meal service"])
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])


def test_build_vectors_row_order_matches_pdf_page(tmp_path, embedder):
    # pdf_page -> text, deliberately out of order so a missing sort in
    # build_vectors would misalign rows and this test would catch it.
    text_by_pdf_page = {1: "fire extinguisher", 2: "life raft", 3: "oxygen mask"}
    pages = [
        Page(pdf_page=n, part=PartName.FOUR, section="4.4", section_title="Evacuations",
             page_in_section=n, section_total=3, effective=date(2023, 5, 18),
             revision=None, lines=[text_by_pdf_page[n]], text=text_by_pdf_page[n])
        for n in [3, 1, 2]
    ]
    out = tmp_path / "vectors.npy"
    build_vectors(pages, out, embedder=embedder)
    arr = np.load(out)
    assert arr.shape == (3, 384)
    assert arr.dtype == np.float32
    for n, text in text_by_pdf_page.items():
        np.testing.assert_allclose(arr[n - 1], embedder.encode([text])[0], atol=1e-5)
