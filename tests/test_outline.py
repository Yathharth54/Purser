"""A heading owns what follows it until a heading of equal or higher rank.

The reader and the citation card both render nesting from `Block.depth`, so the
grouping is computed here, once, over the flat block list -- `Block` itself
stays a flat, serialisable record.
"""

from __future__ import annotations

from purser_core.models import Block
from purser_core.outline import annotate_depth


def h(level: int, text: str) -> Block:
    return Block(kind="heading", level=level, text=text)


def p(text: str) -> Block:
    return Block(kind="para", text=text)


def depths(blocks: list[Block]) -> list[tuple[str, int]]:
    return [(b.text, b.depth) for b in blocks]


def test_content_before_any_heading_is_at_depth_zero():
    blocks = [p("intro")]
    assert annotate_depth(blocks, []) == []
    assert depths(blocks) == [("intro", 0)]


def test_a_heading_owns_the_blocks_after_it():
    blocks = [h(1, "1. GENERAL"), p("a"), h(2, "1.1 SMOKE"), p("b")]
    stack = annotate_depth(blocks, [])
    assert depths(blocks) == [("1. GENERAL", 0), ("a", 1), ("1.1 SMOKE", 1), ("b", 2)]
    assert stack == [(1, "1. GENERAL"), (2, "1.1 SMOKE")]


def test_a_heading_of_equal_or_higher_rank_closes_the_open_sections():
    blocks = [h(1, "1. A"), h(2, "1.1 B"), p("x"), h(2, "1.2 C"), p("y"), h(1, "2. D"), p("z")]
    annotate_depth(blocks, [])
    assert depths(blocks) == [
        ("1. A", 0),
        ("1.1 B", 1),
        ("x", 2),
        ("1.2 C", 1),
        ("y", 2),
        ("2. D", 0),
        ("z", 1),
    ]


def test_a_skipped_level_nests_one_step_not_two():
    blocks = [h(1, "1. A"), h(3, "1.1.1 B"), p("x")]
    annotate_depth(blocks, [])
    assert depths(blocks) == [("1. A", 0), ("1.1.1 B", 1), ("x", 2)]


def test_a_subheading_does_not_open_a_section():
    blocks = [h(1, "1. A"), Block(kind="subheading", text="EVACUATION"), p("x")]
    annotate_depth(blocks, [])
    assert depths(blocks) == [("1. A", 0), ("EVACUATION", 1), ("x", 1)]


def test_the_open_stack_carries_onto_the_next_page_without_being_mutated():
    page1 = [h(1, "1. A"), h(2, "1.6 B")]
    carried = annotate_depth(page1, [])
    page2 = [p("continued"), h(2, "1.7 C"), p("y")]
    after = annotate_depth(page2, carried)
    assert depths(page2) == [("continued", 2), ("1.7 C", 1), ("y", 2)]
    assert carried == [(1, "1. A"), (2, "1.6 B")]
    assert after == [(1, "1. A"), (2, "1.7 C")]
