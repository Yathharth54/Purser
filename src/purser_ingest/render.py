from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _cache_dir() -> Path:
    d = Path(os.environ.get("PURSER_VAR_DIR", "var")) / "pagecache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_page(pdf: Path, pdf_page: int, dpi: int = 150) -> Path:
    """Render one page to WebP, cached on disk.

    Pages are rendered on demand rather than pre-rendered: all 1,226 would be
    roughly 200 MB of dead weight in the image. Rendering shells out to
    `pdftoppm` (poppler-utils) against the live PDF, so both the PDF (at
    `PURSER_PDF_PATH`) and poppler must be present in the running process,
    not just at build time.
    """
    out = _cache_dir() / f"p{pdf_page:04d}.webp"
    if out.is_file():
        return out

    stem = out.with_suffix("")
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(pdf_page),
            "-l",
            str(pdf_page),
            "-r",
            str(dpi),
            "-png",
            "-singlefile",
            str(pdf),
            str(stem),
        ],
        check=True,
        capture_output=True,
    )
    png = stem.with_suffix(".png")

    from PIL import Image

    with Image.open(png) as im:
        im.save(out, "WEBP", quality=80, method=4)
    png.unlink(missing_ok=True)
    return out
