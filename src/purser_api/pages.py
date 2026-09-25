"""Page images from the private Blob store, for a deployment without the PDF.

The manual PDF is never deployed (it is kept out of git and the bundle), so
on Vercel page images are rendered ahead of time by `scripts/upload_pages.py`
and kept in a private Blob store, one WebP per page at `pages/p0001.webp`.

Pages, not the PDF, on purpose: the 49 MB PDF would be re-downloaded on every
cold start and eat the Hobby plan's 10 GB of Blob transfer in about 200 cold
starts, where a page is ~77 KB and fetched only when she opens a citation.
Each fetched page is kept in the instance's page cache, so a warm instance
reads a page from Blob once.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

BLOB_PREFIX = "pages"


def blob_path(pdf_page: int) -> str:
    return f"{BLOB_PREFIX}/p{pdf_page:04d}.webp"


def configured() -> bool:
    """Whether a Blob store is connected (Vercel sets this when it is)."""
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


class PageNotStored(LookupError):
    """The store has no image for this page: the upload was never run, or ran
    against a different manual."""


def _cache_path(pdf_page: int) -> Path:
    # The same directory and name the local renderer uses, so a page is cached
    # once however it was obtained.
    d = Path(os.environ.get("PURSER_VAR_DIR", "var")) / "pagecache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"p{pdf_page:04d}.webp"


def fetch_page(pdf_page: int) -> Path:
    """The page's WebP on local disk, fetched from Blob on first use."""
    out = _cache_path(pdf_page)
    if out.is_file():
        return out

    from vercel.blob import BlobNotFoundError, get

    try:
        result = get(blob_path(pdf_page), access="private")
    except BlobNotFoundError as exc:
        raise PageNotStored(blob_path(pdf_page)) from exc

    # Write-then-rename, as the renderer does: never serve a half-written file.
    tmp = out.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(result.content)
    tmp.replace(out)
    return out
