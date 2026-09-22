"""Retrieval accuracy gate. No model in the loop — this measures L2 alone."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from purser_core.models import PartName, SectionHit
from purser_core.tools import PurserTools

QUESTIONS = yaml.safe_load(Path("tests/eval/questions.yaml").read_text())
TOP_N = 3
TARGET = 0.90

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


def _hit_sections(tools: PurserTools, query: str, n: int) -> list[str]:
    """The top n sections `search` returns, as comparison keys, rank order.

    search() now groups by section itself, so this is a direct read of its
    result — no page-level dedup step needed here any more.
    """
    return [_key(hit) for hit in tools.search(query, k=n)]


@pytest.mark.parametrize("case", QUESTIONS, ids=lambda c: c["q"][:48])
def test_question_finds_an_acceptable_section(tools, case):
    found = _hit_sections(tools, case["q"], TOP_N)
    assert set(found) & set(case["sections"]), (
        f"{case['q']!r}\n  expected one of {case['sections']}\n  got {found}"
    )


def test_overall_accuracy_meets_target(tools):
    passed = sum(
        bool(set(_hit_sections(tools, c["q"], TOP_N)) & set(c["sections"])) for c in QUESTIONS
    )
    rate = passed / len(QUESTIONS)
    assert rate >= TARGET, f"top-{TOP_N} accuracy {rate:.0%} below target {TARGET:.0%}"
