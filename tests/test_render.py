"""Page images are rendered on demand from the PDF, in-process (pypdfium2).

No poppler binary: Vercel's runtime can't install system packages, and a
pip-installed renderer works the same on this Mac, in Docker and on Vercel.
"""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from purser_ingest.render import render_page


@pytest.fixture
def var_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PURSER_VAR_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def pdf(tmp_path) -> Path:
    """A real 3-page PDF; page 2 is landscape, so page numbering is checkable."""
    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.new_page(792, 612)
    doc.new_page(612, 792)
    path = tmp_path / "tiny.pdf"
    doc.save(path)
    return path


def test_renders_the_requested_page_to_webp(var_dir, pdf):
    out = render_page(pdf, 2, dpi=72)
    assert out == var_dir / "pagecache" / "p0002.webp"
    with Image.open(out) as im:
        assert im.format == "WEBP"
        assert im.size == (792, 612)  # page 2, the landscape one, at 72 dpi


def test_resolution_follows_dpi(var_dir, pdf):
    with Image.open(render_page(pdf, 1, dpi=144)) as im:
        assert im.size == (1224, 1584)


def test_a_rendered_page_is_served_from_the_cache(var_dir, pdf, monkeypatch):
    first = render_page(pdf, 3, dpi=72)
    opened = []
    monkeypatch.setattr(pdfium, "PdfDocument", lambda *a, **k: opened.append(a) or None)
    assert render_page(pdf, 3, dpi=72) == first
    assert opened == []


def test_a_page_beyond_the_document_raises(var_dir, pdf):
    with pytest.raises((IndexError, ValueError)):
        render_page(pdf, 9, dpi=72)


def test_rendering_needs_no_poppler_binary(var_dir, pdf, monkeypatch):
    """Vercel's runtime has no pdftoppm; rendering must not shell out at all."""
    monkeypatch.setenv("PATH", "")
    with Image.open(render_page(pdf, 1, dpi=72)) as im:
        assert im.size == (612, 792)
