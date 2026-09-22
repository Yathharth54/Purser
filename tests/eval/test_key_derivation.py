"""Unit tests for the eval harness's comparison-key derivation.

No index or embedding model required — SectionHit objects are built directly
so this runs fast and is never skipped by the index-availability gate that
guards the full eval in test_eval.py.
"""

from __future__ import annotations

from purser_core.models import PartName, SectionHit
from tests.eval.test_eval import _key


def _hit(part: PartName, section: str | None) -> SectionHit:
    return SectionHit(
        part=part,
        section=section,
        section_title=None,
        score=1.0,
        hit_pages=[1],
        hit_page_numbers=[1],
        snippet="",
    )


def test_real_section_key_is_unchanged():
    assert _key(_hit(PartName.FOUR, "4.4")) == "4.4"


def test_part_seven_falls_back_to_digit():
    assert _key(_hit(PartName.SEVEN, None)) == "7"


def test_part_nine_falls_back_to_digit():
    assert _key(_hit(PartName.NINE, None)) == "9"


def test_part_ten_falls_back_to_two_digit_ordinal():
    assert _key(_hit(PartName.TEN, None)) == "10"


def test_annexures_fallback_does_not_collide():
    # "annex" not in {"1".."10"} is entailed by this equality -- no
    # separate assertion needed.
    assert _key(_hit(PartName.ANNEX, None)) == "annex"


def test_front_matter_fallback_does_not_collide():
    # "front" not in {"1".."10"} is entailed by this equality -- no
    # separate assertion needed.
    assert _key(_hit(PartName.FRONT, None)) == "front"
