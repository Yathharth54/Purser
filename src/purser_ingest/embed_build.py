from __future__ import annotations

from pathlib import Path

import numpy as np

from purser_core.embed import Embedder
from purser_core.models import Page

_BATCH = 64


def build_vectors(pages: list[Page], out_path: Path, embedder: Embedder | None = None) -> None:
    """One vector per page. Row index is pdf_page - 1.

    That invariant holds only if the input covers exactly {1..N} with no gap and
    no duplicate -- sorted() guarantees order, not positional identity. Feeding
    e.g. pages [1, 2, 5] would otherwise write a (3, 384) array with no error,
    where row 2 (read by any consumer as page 3) actually holds page 5's vector.
    """
    embedder = embedder or Embedder()
    ordered = sorted(pages, key=lambda p: p.pdf_page)

    expected = list(range(1, len(ordered) + 1))
    actual = [p.pdf_page for p in ordered]
    if actual != expected:
        pairs = enumerate(zip(expected, actual, strict=True))
        bad = next(i for i, (want, got) in pairs if want != got)
        raise ValueError(
            f"pdf_page sequence has a gap or duplicate at row {bad}: "
            f"expected pdf_page {expected[bad]}, got {actual[bad]} "
            "(row index must equal pdf_page - 1 for every row)"
        )

    chunks: list[np.ndarray] = []
    for i in range(0, len(ordered), _BATCH):
        batch = [p.text for p in ordered[i : i + _BATCH]]
        chunks.append(embedder.encode(batch))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, np.vstack(chunks).astype(np.float32))
