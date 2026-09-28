"""The MCP tools, called in-process through the SDK's own client."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client

from purser_mcp.server import build_server

needs_index = pytest.mark.skipif(
    not Path("data/manual.sqlite").is_file(), reason="index not built"
)
pytestmark = pytest.mark.asyncio


async def _call(name: str, args: dict):
    async with Client(build_server()) as c:
        return await c.call_tool(name, args)


async def test_it_lists_exactly_the_six_tools():
    async with Client(build_server()) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {"search", "toc", "read_section", "read_page", "lookup_term", "ask"}
    for name in ("search", "toc", "read_section", "read_page", "lookup_term"):
        assert tools[name].annotations.read_only_hint is True, name
    assert tools["search"].description.startswith("Find candidate sections")


async def test_instructions_ask_for_verbatim_quotes():
    s = build_server()
    assert "verbatim" in s.instructions and "paraphrase" in s.instructions


@needs_index
async def test_search_returns_section_hits():
    r = await _call("search", {"query": "ditching", "k": 3})
    assert not r.is_error
    hits = r.structured_content["result"]
    assert 1 <= len(hits) <= 3
    assert all(1 <= p <= 1226 for h in hits for p in h["hit_pages"])


@needs_index
async def test_toc_lists_parts():
    r = await _call("toc", {})
    assert not r.is_error
    assert r.structured_content["result"][0]["part"] == "Front Matter"


@needs_index
async def test_read_section_is_capped_at_six_pages():
    r = await _call("read_section", {"section": "4.4"})
    assert not r.is_error
    assert len(r.structured_content["result"]) == 6


@needs_index
async def test_read_page_returns_the_page():
    r = await _call("read_page", {"pdf_page": 600})
    assert not r.is_error
    assert r.structured_content["result"][0]["pdf_page"] == 600


@needs_index
async def test_lookup_term_finds_a_known_acronym():
    r = await _call("lookup_term", {"term": "PBE"})
    assert not r.is_error
    assert r.structured_content["result"] is not None


@needs_index
async def test_unknown_section_is_a_helpful_error():  # Review Focus 5
    r = await _call("read_section", {"section": "99.9"})
    assert r.is_error
    assert "99.9" in r.content[0].text and "toc" in r.content[0].text


@needs_index
async def test_out_of_range_page_is_a_helpful_error():  # Review Focus 5
    r = await _call("read_page", {"pdf_page": 5000})
    assert r.is_error
    assert "1226" in r.content[0].text


async def test_ask_reports_a_broken_agent_as_a_tool_error(monkeypatch):
    def broken():
        raise RuntimeError("PURSER_MODEL is 'openai:gpt-4o' but OPENAI_API_KEY is not set.")

    monkeypatch.setattr("purser_mcp.server.get_agent", broken)
    r = await _call("ask", {"question": "brace commands?"})
    assert r.is_error
    assert "OPENAI_API_KEY" in r.content[0].text
