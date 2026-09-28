"""The agent and the MCP server describe the tools with the same words."""

from __future__ import annotations

import subprocess
import sys

from purser_agent import tooling


def test_tooling_imports_nothing_heavy():
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; import purser_agent.tooling; print('pydantic_ai' in sys.modules)"],
        capture_output=True, text=True, check=True, env={"PYTHONPATH": "src"},
    )
    assert out.stdout.strip() == "False"


def test_agent_tools_use_the_shared_descriptions(monkeypatch):
    # No index or key needed: `tools` is only read when a tool runs, and
    # pydantic-ai's built-in "test" model needs no credentials.
    import purser_agent.lookup as lookup

    monkeypatch.setattr(lookup, "require_credentials", lambda: None)
    monkeypatch.setattr(lookup, "resolve_model", lambda: "test")
    agent = lookup.build_agent(tools=None)  # tools unused at construction
    tools = agent._function_toolset.tools
    expected = {
        "search": tooling.SEARCH,
        "toc": tooling.TOC,
        "read_section": tooling.READ_SECTION,
        "read_page": tooling.READ_PAGE,
        "lookup_term": tooling.LOOKUP_TERM,
    }
    for name, text in expected.items():
        assert tools[name].tool_def.description == text, name


def test_max_read_pages_is_shared():
    from purser_agent.lookup import MAX_READ_PAGES

    assert MAX_READ_PAGES == tooling.MAX_READ_PAGES == 6
