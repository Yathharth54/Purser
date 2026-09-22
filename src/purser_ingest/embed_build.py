from __future__ import annotations

from pathlib import Path

import numpy as np

from purser_core.embed import Embedder
from purser_core.models import Page

_BATCH = 64


def build_vectors(pages: list[Page], out_path: Path, embedder: Embedder | None = None) -> None:
    """One vector per page. Row index is pdf_page - 1."""
    embedder = embedder or Embedder()
    ordered = sorted(pages, key=lambda p: p.pdf_page)

    chunks: list[np.ndarray] = []
    for i in range(0, len(ordered), _BATCH):
        batch = [p.text for p in ordered[i : i + _BATCH]]
        chunks.append(embedder.encode(batch))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.vstack(chunks).astype(np.float32))
