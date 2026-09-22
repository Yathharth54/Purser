from __future__ import annotations

from collections import defaultdict

RRF_K = 60


def rrf(*lanes: list[tuple[int, float]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion.

    Chosen over score normalisation because BM25 and cosine are not on comparable
    scales — any normalising constant would be a tuned magic number. RRF uses only
    rank, so the lanes stay independent.
    """
    scores: dict[int, float] = defaultdict(float)
    for lane in lanes:
        for rank, (pdf_page, _score) in enumerate(lane, start=1):
            scores[pdf_page] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])
