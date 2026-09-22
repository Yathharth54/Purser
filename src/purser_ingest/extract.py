from __future__ import annotations

import subprocess
from pathlib import Path


def extract_pages(pdf: Path) -> list[str]:
    """Run pdftotext -layout and split on form feed. One string per physical page."""
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", errors="replace")
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()  # pdftotext emits a trailing empty page
    return pages
