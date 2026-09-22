from __future__ import annotations

import os
from pathlib import Path

import pytest

from purser_agent.lookup import PurserDeps, build_agent
from purser_agent.prompts import SYSTEM_PROMPT
from purser_core.tools import PurserTools

needs_live = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or not Path("data/manual.sqlite").is_file(),
    reason="needs OPENAI_API_KEY and a built index",
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
async def test_declines_when_the_manual_does_not_cover_it(agent_and_deps):
    agent, deps = agent_and_deps
    result = await agent.run("what is the capital of Portugal?", deps=deps)
    assert result.output.not_in_manual or not result.output.refs
