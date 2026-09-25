from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

# PDFium is not thread-safe -- not even across different documents -- and the
# image endpoint runs in FastAPI's threadpool. Two citations opened together
# used to fail with "Data format error" (or worse, crash the process). Renders
# are fast (~0.3 s), so one at a time costs nothing noticeable.
_PDFIUM = threading.Lock()


def _cache_dir() -> Path:
    d = Path(os.environ.get("PURSER_VAR_DIR", "var")) / "pagecache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_page(pdf: Path, pdf_page: int, dpi: int = 150) -> Path:
    """Render one page (1-based) to WebP, cached on disk.

    Pages are rendered on demand rather than pre-rendered: all 1,226 would be
    roughly 200 MB of dead weight. Rendering runs in-process with pypdfium2
    -- no poppler binary -- because Vercel's runtime cannot install system
    packages; the same code runs locally, in Docker and on Vercel. The PDF
    must be present at `PURSER_PDF_PATH` in the running process.
    """
    out = _cache_dir() / f"p{pdf_page:04d}.webp"
    if out.is_file():
        return out

    import pypdfium2 as pdfium

    with _PDFIUM:
        if out.is_file():  # rendered by another request while this one waited
            return out
        doc = pdfium.PdfDocument(pdf)
        try:
            if not 1 <= pdf_page <= len(doc):
                raise IndexError(f"page {pdf_page} is outside 1..{len(doc)}")
            image = doc[pdf_page - 1].render(scale=dpi / 72).to_pil()
        finally:
            doc.close()

    # Write-then-rename, so a half-written file is never served from the cache;
    # a unique temp name, so two writers of one page never clobber each other.
    tmp = out.with_suffix(f".{uuid.uuid4().hex}.tmp")
    image.save(tmp, "WEBP", quality=80, method=4)
    tmp.replace(out)
    return out
