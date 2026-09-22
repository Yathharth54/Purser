"""Retrieval accuracy gate. No model in the loop — this measures L2 alone.

`search(query, k=8)` narrows; it does not choose. It returns up to 8
SectionHit rows, best-first, for the agent to open with
`read_section`/`read_page` before citing anything (spec §8.3, §8.4). The gate
here is split into two metrics that are BOTH always reported, so no one
reading a run sees only the flattering number:

  PRIMARY   -- recall@8 (hard gate, >= 95%): does the correct section appear
              anywhere among the up-to-8 rows `search` returns? This is
              `search`'s actual contract. A miss here means `search` failed
              at the one job it promises to do.

  SECONDARY -- rank quality (still asserted, but softer):
              * top-3 rate (>= 80%): correct section within the first 3
                rows. `search` never promised this, but a real ranking
                regression should still be catchable somewhere, so this
                floor has genuine teeth (currently 85%).
              * MRR (mean reciprocal rank) over the returned rows: reported
                every run, never gated. It is the continuous signal -- while
                recall@8 is pinned at a ceiling (see caveat below) and top-3
                is coarse, MRR can move in either direction in response to a
                real change in ranking quality, which is what makes a
                regression visible at all.

CAVEAT -- read this before trusting the 100%: recall@8 is currently 100%
against the 40 questions in tests/eval/questions.yaml, and those 40 questions
were invented by the developer while building this retrieval pipeline, NOT
collected from the end user. A hand-built set authored by the implementer
tends to ask the questions the implementation already handles well, so 100%
here means "the developer's own guesses are covered," not "retrieval is
solved." The primary metric is saturated with zero headroom left to detect a
regression -- that is exactly why the MRR figure exists alongside it. This
questions.yaml must be replaced with the real user's questions (spec §16.2)
before recall@8 is allowed to mean anything about the product. Do not read a
future 100% here as a finished retrieval system until that swap has happened.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from purser_core.models import PartName, SectionHit
from purser_core.tools import PurserTools

QUESTIONS = yaml.safe_load(Path("tests/eval/questions.yaml").read_text())

K = 8  # search()'s actual candidate window -- its real contract (spec §8.3, §8.4)
TOP_N = 3  # secondary rank-quality window; NOT part of search()'s contract

RECALL_TARGET = 0.95  # PRIMARY gate: correct section anywhere in the k=8 candidates
TOP_N_TARGET = 0.80  # SECONDARY soft floor on rank quality, given real teeth today

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")

# questions.yaml identifies unsectioned Parts by their ordinal digit (e.g. "7"
# for PART SEVEN, since that Part has no section numbers of its own). Hits from
# pages in such a Part carry section=None, so the fallback key must translate
# the Part name back into the same digit string the questions file uses.
# Annexures and Front Matter have no ordinal; they map to keys chosen so they
# can never collide with a real section key ("1.1") or a Part digit ("7").
PART_FALLBACK_KEY: dict[PartName, str] = {
    PartName.ONE: "1",
    PartName.TWO: "2",
    PartName.THREE: "3",
    PartName.FOUR: "4",
    PartName.FIVE: "5",
    PartName.SIX: "6",
    PartName.SEVEN: "7",
    PartName.EIGHT: "8",
    PartName.NINE: "9",
    PartName.TEN: "10",
    PartName.ANNEX: "annex",
    PartName.FRONT: "front",
}


def _key(hit: SectionHit) -> str:
    """Comparison key for a hit: its section, or its Part's fallback key."""
    return hit.section or PART_FALLBACK_KEY[hit.part]


@pytest.fixture(scope="module")
def tools():
    return PurserTools("data")


def _hit_sections(tools: PurserTools, query: str, k: int = K) -> list[str]:
    """The keys of the up-to-k sections `search` returns, best-first.

    search() now groups by section itself, so this is a direct read of its
    result -- no page-level dedup step needed here any more.
    """
    return [_key(hit) for hit in tools.search(query, k=k)]


def _rank(found: list[str], acceptable: set[str]) -> int | None:
    """1-based rank of the first acceptable section in `found`, or None if absent."""
    for i, key in enumerate(found, start=1):
        if key in acceptable:
            return i
    return None


@pytest.mark.parametrize("case", QUESTIONS, ids=lambda c: c["q"][:48])
def test_question_in_candidate_set(tools, case):
    """PRIMARY gate, per question: is the correct section anywhere in search(q, k=8)?

    This is what `search` actually promises -- a k=8 candidate window, not a
    top-3 ranking -- so this is the assertion that should fail on a real
    regression in `search`'s recall.
    """
    found = _hit_sections(tools, case["q"])
    acceptable = set(case["sections"])
    rank = _rank(found, acceptable)
    where = (
        f"at rank {rank} of {len(found)}" if rank is not None else "absent from the candidate set"
    )
    assert rank is not None, (
        f"{case['q']!r}\n  expected one of {acceptable}\n  got {found}\n  ({where})"
    )


def test_recall_and_rank_quality(tools):
    """Headline metrics for the whole 40-question set, always reported together.

    recall@8 (PRIMARY, >= 95%) and top-3 (SECONDARY floor, >= 80%) are gated.
    MRR is reported every run and never gated -- see module docstring for why.
    """
    n = len(QUESTIONS)
    in_k = 0
    in_top_n = 0
    reciprocal_rank_sum = 0.0

    for case in QUESTIONS:
        found = _hit_sections(tools, case["q"])
        acceptable = set(case["sections"])
        rank = _rank(found, acceptable)
        if rank is not None:
            in_k += 1
            reciprocal_rank_sum += 1.0 / rank
            if rank <= TOP_N:
                in_top_n += 1

    recall_at_k = in_k / n
    top_n_rate = in_top_n / n
    mrr = reciprocal_rank_sum / n

    summary = (
        f"recall@{K} {recall_at_k:.1%} ({in_k}/{n}) | "
        f"top-{TOP_N} {top_n_rate:.1%} ({in_top_n}/{n}) | "
        f"MRR {mrr:.3f}"
    )
    # Printed unconditionally -- pass or fail -- so nobody reading a run sees
    # only the flattering number. (Run pytest with -s, or read the assertion
    # message below, to see it when the gates pass.)
    print(f"\n{summary}")

    assert recall_at_k >= RECALL_TARGET, (
        f"{summary}\n"
        f"recall@{K} {recall_at_k:.1%} is below the PRIMARY gate of {RECALL_TARGET:.0%} -- "
        f"search(q, k={K}) is failing to surface the correct section at all, "
        "not just ranking it low"
    )
    assert top_n_rate >= TOP_N_TARGET, (
        f"{summary}\n"
        f"top-{TOP_N} rate {top_n_rate:.1%} is below the SECONDARY floor of {TOP_N_TARGET:.0%}"
    )
