"""Retrieval accuracy gate. No model in the loop — this measures L2 alone."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from purser_core.tools import PurserTools

QUESTIONS = yaml.safe_load(Path("tests/eval/questions.yaml").read_text())
TOP_N = 3
TARGET = 0.90

pytestmark = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def tools():
    return PurserTools("data")


def _hit_sections(tools: PurserTools, query: str, n: int) -> list[str]:
    """Distinct sections in rank order, capped at n."""
    seen: list[str] = []
    for hit in tools.search(query, k=12):
        key = hit.section or str(hit.part).split()[-1].lower()
        if key not in seen:
            seen.append(key)
        if len(seen) == n:
            break
    return seen


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
