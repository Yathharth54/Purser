from __future__ import annotations

import re
from pathlib import Path

import pytest

from purser_agent.lookup import PurserDeps, build_agent
from purser_agent.prompts import SYSTEM_PROMPT
from purser_agent.provider import credentials_present
from purser_core.tools import PurserTools

needs_live = pytest.mark.skipif(
    not credentials_present() or not Path("data/manual.sqlite").is_file(),
    reason="needs a key for the configured PURSER_MODEL and a built index",
)


@pytest.fixture(scope="module")
def agent_and_deps():
    tools = PurserTools("data")
    return build_agent(tools), PurserDeps(tools=tools)


def test_agent_registers_exactly_the_five_expected_tools(agent_and_deps):
    agent, _ = agent_and_deps
    names = set(agent._function_toolset.tools.keys())
    assert names == {"search", "toc", "read_section", "read_page", "lookup_term"}


def test_system_prompt_states_the_half_open_line_range_rule_with_worked_example():
    # Guards against a fix round silently dropping the off-by-one rule: the
    # exact worked example (lines 12-17 => line_from=12, line_to=18) must be
    # present, not just some vague mention of "line" or "range".
    assert "line_from=12" in SYSTEM_PROMPT
    assert "line_to=18" in SYSTEM_PROMPT
    assert "EXCLUSIVE" in SYSTEM_PROMPT


def test_system_prompt_warns_against_trusting_the_first_search_result():
    # Guards Correction 1: the agent must not assume search's first hit is
    # correct -- it is only right 62% of the time on the eval set.
    assert "62%" in SYSTEM_PROMPT
    assert "Do NOT assume the first" in SYSTEM_PROMPT
    assert "section=None" in SYSTEM_PROMPT  # unsectioned hits -> use read_page instead


def test_system_prompt_distinguishes_general_knowledge_from_aviation_fact():
    # Guards the corrected rule: conversational ability is a real product
    # requirement, so general-knowledge questions ("capital of Portugal")
    # must be answered naturally -- the risk is narrower than "never use
    # world knowledge." It is specifically aviation/safety/procedural/
    # equipment/regulatory questions ("max takeoff weight of the A321") that
    # must come from the manual with citations or be declined, because those
    # are the answers she cannot tell apart from verified manual content and
    # might act on. Pin the concrete example of each class so this doesn't
    # regress into a vague "be careful" that the model can rationalize past.
    assert "GENERAL CONVERSATION / GENERAL KNOWLEDGE" in SYSTEM_PROMPT
    assert "what is the capital of Portugal?" in SYSTEM_PROMPT
    assert "AVIATION / SAFETY / PROCEDURAL / EQUIPMENT / REGULATORY" in SYSTEM_PROMPT
    assert "what is the maximum takeoff" in SYSTEM_PROMPT
    assert "weight of the A321?" in SYSTEM_PROMPT


@needs_live
@pytest.mark.asyncio(loop_scope="module")
async def test_answers_a_real_question_with_valid_citations(agent_and_deps):
    agent, deps = agent_and_deps
    result = await agent.run("what does ABP stand for?", deps=deps)
    assert result.output.refs, "answered without citing"
    assert not result.output.not_in_manual
    for ref in result.output.refs:
        assert 1 <= ref.pdf_page <= 1226
        assert ref.line_to > ref.line_from


@needs_live
@pytest.mark.asyncio(loop_scope="module")
async def test_cited_pages_are_in_range(agent_and_deps):
    agent, deps = agent_and_deps
    result = await agent.run("what are the evacuation commands?", deps=deps)
    assert result.output.refs
    for ref in result.output.refs:
        assert 1 <= ref.pdf_page <= 1226
        assert ref.line_to > ref.line_from


@needs_live
@pytest.mark.asyncio(loop_scope="module")
async def test_general_knowledge_question_is_answered_naturally(agent_and_deps):
    # Corrected rule: general conversation/general-knowledge questions are
    # NOT a decline case. Conversational ability is a real product
    # requirement -- the agent should answer this like any chat assistant,
    # while still marking it as not sourced from the manual.
    agent, deps = agent_and_deps
    result = await agent.run("what is the capital of Portugal?", deps=deps)
    assert result.output.not_in_manual
    assert not result.output.refs
    assert result.output.body.strip()  # answered, did not stonewall
    assert "lisbon" in result.output.body.lower()


@needs_live
@pytest.mark.asyncio(loop_scope="module")
async def test_aviation_question_not_covered_by_manual_is_declined(agent_and_deps):
    # This IS the decline case: an aviation fact (real max takeoff weight
    # figures exist for the A321) that is plausibly in the model's training
    # data but genuinely absent from a cabin safety/emergency procedures
    # manual. The body must not supply the figure from parametric knowledge
    # -- she cannot tell that apart from verified manual content.
    agent, deps = agent_and_deps
    result = await agent.run("what is the maximum takeoff weight of the A321?", deps=deps)
    assert result.output.not_in_manual
    assert not result.output.refs
    # No weight figure (e.g. "93,500 kg", "97000 kg", "205,000 lb") leaked
    # into the body: no run of 4+ digits, the shape any real MTOW figure has.
    assert not re.search(r"\d{4,}", result.output.body)


def test_the_agent_reads_sections_and_neighbours_in_bounded_windows(monkeypatch):
    """The cap only helps if the agent's own tools apply it."""
    from types import SimpleNamespace

    from purser_agent.lookup import MAX_READ_PAGES

    monkeypatch.setenv("PURSER_MODEL", "openrouter:deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-used")
    tools = PurserTools("data")
    fns = build_agent(tools)._function_toolset.tools
    ctx = SimpleNamespace(deps=PurserDeps(tools=tools))
    assert len(fns["read_section"].function(ctx, section="4.4")) == MAX_READ_PAGES
    assert len(fns["read_page"].function(ctx, pdf_page=600, before=20, after=20)) <= MAX_READ_PAGES
