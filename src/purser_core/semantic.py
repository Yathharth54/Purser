from __future__ import annotations

import numpy as np

from purser_core.corpus import Corpus
from purser_core.embed import Embedder


def semantic_search(
    corpus: Corpus, embedder: Embedder, query: str, k: int = 20
) -> list[tuple[int, float]]:
    """Brute-force cosine over 1,226 normalised vectors. Sub-millisecond."""
    q = embedder.encode([query])[0]
    scores = corpus.vectors @ q  # both L2-normalised, so dot == cosine
    top = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
    top = top[np.argsort(-scores[top])]
    return [(int(i) + 1, float(scores[i])) for i in top]
