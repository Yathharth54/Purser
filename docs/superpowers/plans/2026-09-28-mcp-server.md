# Purser MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Purser's five manual-reading tools plus `ask` as an MCP server at `/mcp` on the existing Vercel app, for Claude Code and Claude Desktop.

**Architecture:** A new `purser_mcp` package holds two files. `server.py` builds an `MCPServer` whose tools delegate to the existing `purser_api.deps` singletons. `http.py` is an ASGI endpoint that checks a bearer token, allows only POST, and builds the MCP app and its session manager lazily on the first request, so PWA cold starts never import the SDK. Tool descriptions move into a small `purser_agent.tooling` module so the agent and the MCP server share them without the MCP side importing pydantic-ai.

**Tech Stack:** Python 3.13, FastAPI/Starlette, `mcp` 2.2 (`mcp.server.mcpserver.MCPServer`, stateless Streamable HTTP, JSON responses), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-28-mcp-server-design.md`

## Global Constraints

- `mcp` is the 2.x SDK: `from mcp.server.mcpserver import MCPServer`. There is no `mcp.server.fastmcp`; do not copy v1 examples.
- Declare `"mcp>=2.2,<3"` in `pyproject.toml` `dependencies`. The lock already contains `mcp` 2.2.0, so `uv lock` must not change its version.
- Env var: `PURSER_MCP_TOKEN`. Unset or blank means every `/mcp` request returns 404.
- Auth header: `Authorization: Bearer <token>`, compared with `hmac.compare_digest`.
- Transport: `streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))`.
- Tool names, exactly: `search`, `toc`, `read_section`, `read_page`, `lookup_term`, `ask`.
- Page cap: `MAX_READ_PAGES = 6` for `read_section` and `read_page`.
- `purser_core` must not import `mcp`.
- Importing `purser_api.main` must not import `mcp.server`.
- Ruff line length 100. Run `uv run ruff check src tests` before each commit.
- Commits carry the user's name only, with **no** `Co-Authored-By` trailer (user preference). Branch: `feat/mcp-server`.

## Review Focus

1. **`GET /mcp`**, which some clients send to open an SSE stream. In stateless mode the SDK holds it open indefinitely (seen in a probe), so a Vercel function would stay busy for 300 s. Expected: an immediate 405. Test in Task 3.
2. **`/mcp` with no trailing slash.** A Starlette `mount` answers 307 (seen in a probe), and some clients won't re-POST. Expected: 200 on `/mcp` exactly. Test in Task 3.
3. **A warm instance on a new event loop,** such as a second `TestClient` or a runtime that swaps loops. The session manager's task group is tied to the old loop and fails with "Task group is not initialized" (seen in a probe). Expected: the endpoint rebuilds. Test in Task 3.
4. **A token pasted with a trailing newline** (`echo tok | vercel env add` stores `tok\n`). Expected: the stored token is stripped before comparing, so the right header still works. Test in Task 3.
5. **An unknown section or an out-of-range page** (`read_section("99.9")`, `read_page(5000)`). Core returns `[]`, which leaves Claude guessing. Expected: a tool error that says what went wrong and points to `toc`. Test in Task 2.

---

## File Structure

| file | status | responsibility |
|---|---|---|
| `src/purser_agent/tooling.py` | create | Tool descriptions + `MAX_READ_PAGES`, with no imports, shared by the agent and MCP |
| `src/purser_agent/lookup.py` | modify | Uses `tooling` descriptions and `MAX_READ_PAGES` (re-exported) |
| `src/purser_mcp/__init__.py` | create | Package docstring |
| `src/purser_mcp/server.py` | create | `build_server() -> MCPServer`: six tools and server instructions |
| `src/purser_mcp/http.py` | create | `McpEndpoint` ASGI app: token gate, POST-only, lazy and loop-aware startup |
| `src/purser_api/main.py` | modify | Registers `Route("/mcp", McpEndpoint())` before the `/` static mount |
| `pyproject.toml` | modify | `mcp>=2.2,<3` dependency |
| `tests/conftest.py` | modify | Pops `PURSER_MCP_TOKEN` |
| `tests/test_boundaries.py` | modify | Adds `mcp` to `FORBIDDEN` |
| `tests/test_tooling.py` | create | Agent descriptions match `tooling` |
| `tests/test_mcp_server.py` | create | In-process tool tests |
| `tests/test_mcp_http.py` | create | HTTP, auth and lifecycle tests |
| `tests/test_cold_start.py` | modify | App import does not load `mcp.server` |
| `.env.example`, `README.md` | modify | Document `PURSER_MCP_TOKEN` and `claude mcp add` |

---

### Task 1: Shared tool descriptions

Pulls the agent's tool docstrings and page cap into a dependency-free module, so the MCP server can reuse them without importing pydantic-ai (about 0.3 s, and the reason `deps.py` defers the agent).

**Files:**
- Create: `src/purser_agent/tooling.py`
- Modify: `src/purser_agent/lookup.py:12-15` (MAX_READ_PAGES) and the five `@agent.tool` functions (lines ~46-114)
- Test: `tests/test_tooling.py`

**Interfaces:**
- Produces: `purser_agent.tooling.MAX_READ_PAGES: int = 6`, and `SEARCH`, `TOC`, `READ_SECTION`, `READ_PAGE`, `LOOKUP_TERM`, `ASK: str`. `purser_agent.lookup.MAX_READ_PAGES` still importable (re-export).

- [ ] **Step 1: Write the failing test**

`tests/test_tooling.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_tooling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'purser_agent.tooling'`

- [ ] **Step 3: Create `src/purser_agent/tooling.py`**

Move the five docstrings verbatim out of `lookup.py`:

```python
"""The tool surface the agent and the MCP server share: the page cap and the
words each tool is described with.

Deliberately imports nothing. `purser_mcp` reads these without loading
pydantic-ai, and a description changed here changes it for both surfaces.
"""

from __future__ import annotations

# The most pages one read hands the model. An uncapped read_section returned
# whole sections (4.4 is 80 pages) and every later turn re-sent them: one
# ditching question measured 454k input tokens over 16 model calls.
MAX_READ_PAGES = 6

SEARCH = """Find candidate sections of the manual for a topic.

Returns up to `k` sections, best-scored first, each with the pages inside
it that matched (`hit_pages`) and a `snippet` from the best of them. This
NARROWS the search space -- it does not tell you which candidate is
correct. The right section is first only ~62% of the time and can be
anywhere in the returned list. Read every candidate's section_title and
snippet and judge which one actually answers the question before opening
it with read_section/read_page."""

TOC = "List the manual's Parts and Sections, optionally within one Part."

READ_SECTION = """Read verbatim numbered lines from a section, e.g. section='4.4'.

Returns at most 6 pages per call, starting at `page_from` (a
page_in_section number). Each page carries `section_total`; to read
further, call again with a later `page_from`. Start where search found
the topic -- its `hit_page_numbers` are page_in_section values -- rather
than at page 1 of a long section.

Only for search/toc hits with a real section string. If a search hit's
`section` is None (unsectioned Parts Seven-Ten, Annexures, or a Part's
2-page lead-in), use read_page with its hit_pages instead -- there is no
section string to pass here."""

READ_PAGE = """Read one PDF page plus optional neighbouring pages (up to 2 each side).

Use this for unsectioned search hits (section=None) with the hit's
hit_pages values, or whenever you want a specific page plus its
immediate neighbours without pulling a whole section."""

LOOKUP_TERM = """The manual's own definition of an acronym or term of art.

Prefer this over search for "what does X stand for" / "what is X"
questions about an acronym or defined term -- it is a single hop and
returns the manual's own defining wording, whereas search tends to
surface pages that merely use the term rather than define it."""

ASK = """Ask Purser's own agent a crew question and get a cited answer.

Purser searches and reads the manual itself, then returns a short `body`
plus `citations` whose `text` is spliced byte for byte from the manual --
never written by a model. Use it for a one-call answer; use the reading
tools instead to explore. `not_in_manual` is true when the manual does
not cover the question. Slower (it runs a model) and costs an LLM call."""
```

- [ ] **Step 4: Point `lookup.py` at it**

In `src/purser_agent/lookup.py`:
- Replace the `MAX_READ_PAGES = 6` block and its comment with `from purser_agent.tooling import MAX_READ_PAGES  # noqa: F401  (re-exported)`, placed with the other imports, plus `from purser_agent import tooling`.
- On each of the five tools, change the decorator to pass the description and delete the function's docstring. For example:

```python
    @agent.tool(description=tooling.SEARCH)
    def search(ctx: RunContext[PurserDeps], query: str, k: int = 8) -> list[SectionHit]:
        return ctx.deps.tools.search(query, k=k)
```

Do the same for `toc` (`tooling.TOC`), `read_section` (`tooling.READ_SECTION`), `read_page` (`tooling.READ_PAGE`) and `lookup_term` (`tooling.LOOKUP_TERM`). Leave the bodies unchanged.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_tooling.py tests/test_agent.py -v`
Expected: `test_tooling.py` 3 passed. `test_agent.py`: non-live tests pass and live ones pass or skip as before.

`Agent("test")` and `tools[name].tool_def.description` were both checked against pydantic-ai 2.47.0. If the assertion fails, the decorator isn't passing `description=`; fix the decorator, don't loosen the assertion.

- [ ] **Step 6: Commit**

```bash
uv run ruff check src tests
git add src/purser_agent/tooling.py src/purser_agent/lookup.py tests/test_tooling.py
git commit -m "refactor(agent): tool descriptions and page cap in a shared, import-free module"
```

---

### Task 2: The MCP server and its six tools

**Files:**
- Create: `src/purser_mcp/__init__.py`, `src/purser_mcp/server.py`
- Modify: `pyproject.toml` (dependencies), `tests/test_boundaries.py` (FORBIDDEN)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `purser_agent.tooling.*` (Task 1); `purser_api.deps.get_tools() -> PurserTools`, `get_agent()`, `get_deps() -> PurserDeps`, `get_corpus() -> Corpus`; `purser_api.citations.resolve_all(corpus, refs) -> list[Citation]`.
- Produces: `purser_mcp.server.build_server() -> MCPServer` (new instance each call; Task 3 relies on that); `purser_mcp.server.AskResult(body: str, not_in_manual: bool, citations: list[Citation])`; `purser_mcp.server.INSTRUCTIONS: str`.

- [ ] **Step 1: Add the dependency and the boundary**

In `pyproject.toml` `dependencies`, after `"vercel>=0.11",`, add `"mcp>=2.2,<3",`. Then run `uv lock`. Expected: `mcp` stays at 2.2.0 (`git diff uv.lock` shows only the root package's dependency list).

In `tests/test_boundaries.py`, add `"mcp"` to `FORBIDDEN`.

- [ ] **Step 2: Write the failing tests**

`tests/test_mcp_server.py`:

```python
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
```

pytest-asyncio runs in strict mode here (no `asyncio_mode` in `pyproject.toml`). That's why every test in this file is `async` under the module-level `pytestmark`.

- [ ] **Step 3: Run them and watch them fail**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'purser_mcp'`

- [ ] **Step 4: Implement**

`src/purser_mcp/__init__.py`:

```python
"""Purser as an MCP server: the manual's reading tools for Claude Code and Desktop."""
```

`src/purser_mcp/server.py`:

```python
"""The MCP surface: Purser's five reading tools plus `ask`.

A thin adapter. Every tool delegates to the singletons the PWA's API already
uses (purser_api.deps), so the two surfaces can never disagree about the
manual. Imported only on the first /mcp request -- see purser_mcp.http.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from purser_agent import tooling
from purser_api.citations import resolve_all
from purser_api.deps import get_agent, get_corpus, get_deps, get_tools
from purser_api.schemas import Citation
from purser_core.models import GlossaryEntry, PageText, PartName, SectionHit, TocNode

LAST_PAGE = 1226

INSTRUCTIONS = """Purser reads the Airbus A320/321 Safety and Emergency Procedures
Manual. Every page is addressed as PART, section and page, e.g. PART FOUR §4.4 p.34.

When you answer from these tools, quote the manual's lines verbatim and cite each
quote by its coordinates. Never paraphrase a procedure, a command or a drill: crew
act on the exact words. If the tools do not turn up the answer, say plainly that
the manual does not cover it rather than filling the gap.

Start with `search` (or `lookup_term` for an acronym), then read the candidate
with `read_section` or `read_page`. `ask` returns Purser's own cited answer in one
call."""

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


class AskResult(BaseModel):
    """Purser's answer. `citations[].text` is spliced from the index, never model-written."""

    body: str
    not_in_manual: bool
    citations: list[Citation]


def build_server() -> MCPServer:
    """A fresh server. purser_mcp.http builds a new one whenever its event loop changes."""
    server = MCPServer("purser", instructions=INSTRUCTIONS)

    @server.tool(description=tooling.SEARCH, annotations=_READ_ONLY)
    def search(query: str, k: int = 8) -> list[SectionHit]:
        return get_tools().search(query, k=k)

    @server.tool(description=tooling.TOC, annotations=_READ_ONLY)
    def toc(part: PartName | None = None) -> list[TocNode]:
        return get_tools().toc(part=part)

    @server.tool(description=tooling.READ_SECTION, annotations=_READ_ONLY)
    def read_section(section: str, page_from: int = 1, page_to: int | None = None) -> list[PageText]:
        pages = get_tools().read_section(
            section, page_from=page_from, page_to=page_to, max_pages=tooling.MAX_READ_PAGES
        )
        if not pages:
            raise ToolError(
                f"No pages for section {section!r} in that range. "
                "Call toc for the manual's section numbers, or read_page for unsectioned pages."
            )
        return pages

    @server.tool(description=tooling.READ_PAGE, annotations=_READ_ONLY)
    def read_page(pdf_page: int, before: int = 0, after: int = 0) -> list[PageText]:
        if not 1 <= pdf_page <= LAST_PAGE:
            raise ToolError(f"pdf_page must be between 1 and {LAST_PAGE}, got {pdf_page}.")
        return get_tools().read_page(
            pdf_page, before=before, after=after, max_pages=tooling.MAX_READ_PAGES
        )

    @server.tool(description=tooling.LOOKUP_TERM, annotations=_READ_ONLY)
    def lookup_term(term: str) -> GlossaryEntry | None:
        return get_tools().lookup_term(term)

    @server.tool(description=tooling.ASK)
    async def ask(question: str) -> AskResult:
        try:
            result = await get_agent().run(question, deps=get_deps())
        except Exception as exc:  # a missing key, a provider outage, a bad model reply
            raise ToolError(f"Purser could not answer: {exc}") from exc
        answer = result.output
        citations = resolve_all(get_corpus(), answer.refs)
        # `blocks` only draws a quote in the PWA; `text` is the quote itself.
        return AskResult(
            body=answer.body,
            not_in_manual=answer.not_in_manual,
            citations=[c.model_copy(update={"blocks": []}) for c in citations],
        )

    return server
```

Note that `get_agent` is looked up as a module global inside `ask` at call time, which is what lets the test's `monkeypatch.setattr("purser_mcp.server.get_agent", ...)` work. Keep `from purser_api.deps import get_agent` at module level; don't bind it inside `build_server`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_mcp_server.py tests/test_boundaries.py -v`
Expected: all pass (index-dependent ones skip if `data/manual.sqlite` is missing, but it is present in this repo).

- [ ] **Step 6: Live check of `ask` (only if a key is configured)**

Run:
```bash
uv run python -c "
import asyncio; from mcp import Client; from purser_mcp.server import build_server
async def m():
    async with Client(build_server()) as c:
        r = await c.call_tool('ask', {'question': 'What are the brace commands?'})
        print(r.is_error, r.structured_content['body'][:200], len(r.structured_content['citations']))
asyncio.run(m())"
```
Expected: `False`, a short body, and at least 1 citation. If there's no key, it prints a ToolError naming the missing variable. Record which one happened in the task report.

- [ ] **Step 7: Commit**

```bash
uv run ruff check src tests
git add pyproject.toml uv.lock src/purser_mcp tests/test_mcp_server.py tests/test_boundaries.py
git commit -m "feat(mcp): MCP server with Purser's five reading tools and ask"
```

---

### Task 3: `/mcp` endpoint: token gate, POST only, lazy start

**Files:**
- Create: `src/purser_mcp/http.py`
- Modify: `src/purser_api/main.py` (register the route before the static mount), `tests/conftest.py` (pop `PURSER_MCP_TOKEN`), `tests/test_cold_start.py`, `.env.example`, `README.md`
- Test: `tests/test_mcp_http.py`

**Interfaces:**
- Consumes: `purser_mcp.server.build_server() -> MCPServer` (Task 2).
- Produces: `purser_mcp.http.McpEndpoint` (an ASGI callable) and `purser_mcp.http.TOKEN_VAR = "PURSER_MCP_TOKEN"`.

Why it looks like this (all three were seen in probes against mcp 2.2.0):
- It's a `Route`, not a `mount`: `app.mount("/mcp", ...)` answers `POST /mcp` with a 307 to `/mcp/`.
- `session_manager.run()` has to be entered. A mounted or routed sub-app's lifespan never runs under FastAPI, so the endpoint runs it in a background task and waits until it's ready.
- The loop check exists because the task group belongs to the loop that started it. On a different loop the SDK raises "Task group is not initialized", so the endpoint rebuilds. `run()` can only be called once per manager, which is why it rebuilds instead of restarting.

- [ ] **Step 1: Write the failing tests**

`tests/test_mcp_http.py`:

```python
"""/mcp over HTTP: off unless a token is set, closed without it, POST only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "s3cret-token"
H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "test", "version": "0"}},
}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


def _client():
    from purser_api.main import app

    return TestClient(app, follow_redirects=False)


def _auth(token: str = TOKEN) -> dict:
    return {**H, "Authorization": f"Bearer {token}"}


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("PURSER_MCP_TOKEN", TOKEN)


def test_it_is_off_when_no_token_is_set(monkeypatch):
    monkeypatch.delenv("PURSER_MCP_TOKEN", raising=False)
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 404


def test_a_blank_token_counts_as_unset(monkeypatch):
    monkeypatch.setenv("PURSER_MCP_TOKEN", "   ")
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth("")).status_code == 404


@pytest.mark.parametrize("headers", [H, _auth("wrong"), {**H, "Authorization": TOKEN}])
def test_it_is_closed_without_the_right_token(token, headers):
    with _client() as c:
        r = c.post("/mcp", json=LIST, headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_the_right_token_lists_the_tools(token):
    with _client() as c:
        assert c.post("/mcp", json=INIT, headers=_auth()).status_code == 200
        r = c.post("/mcp", json=LIST, headers=_auth())
    assert r.status_code == 200  # on /mcp exactly, no 307 (Review Focus 2)
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"search", "toc", "read_section", "read_page", "lookup_term", "ask"}


def test_the_scheme_is_case_insensitive(token):
    with _client() as c:
        r = c.post("/mcp", json=LIST, headers={**H, "Authorization": f"bearer {TOKEN}"})
    assert r.status_code == 200


def test_a_token_stored_with_a_trailing_newline_still_works(monkeypatch):  # Review Focus 4
    monkeypatch.setenv("PURSER_MCP_TOKEN", TOKEN + "\n")
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 200


@pytest.mark.parametrize("method", ["get", "delete"])
def test_only_post_is_served(token, method):  # Review Focus 1: GET would hang
    with _client() as c:
        r = c.request(method.upper(), "/mcp", headers=_auth())
    assert r.status_code == 405
    assert r.headers["allow"] == "POST"


def test_it_survives_a_new_event_loop(token):  # Review Focus 3
    for _ in range(2):  # each TestClient runs its own loop
        with _client() as c:
            assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 200


def test_the_passcode_gate_does_not_apply_to_mcp(token, monkeypatch):
    monkeypatch.setenv("PURSER_PASSCODE", "tulip-42")
    with _client() as c:
        assert c.post("/mcp", json=LIST, headers=_auth()).status_code == 200
```

Append to `tests/test_cold_start.py`:

```python
def test_importing_the_app_does_not_load_the_mcp_sdk():
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import purser_api.main; print('mcp.server' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": "src"},
    )
    assert out.stdout.strip() == "False"
```

In `tests/conftest.py`, add `"PURSER_MCP_TOKEN"` to the tuple of popped variables.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_mcp_http.py tests/test_cold_start.py -v`
Expected: `test_mcp_http.py` fails with 404 or 405 from the static mount or no route. The new cold-start test passes already, which is fine because it guards against a regression in Step 3.

- [ ] **Step 3: Implement `src/purser_mcp/http.py`**

```python
"""/mcp: the MCP server over stateless Streamable HTTP, behind a bearer token.

Off unless PURSER_MCP_TOKEN is set (404). Closed without `Authorization:
Bearer <token>` (401). POST only: in stateless mode a GET opens a stream that
never ends, which on Vercel is a function held for its full 300 s (405).

The SDK is imported, and its app built, on the first authorised request, so a
PWA cold start never pays for it. The SDK's session manager must be running
(`session_manager.run()`), and a sub-app's lifespan never runs under FastAPI,
so it runs in a background task for the life of the event loop -- and is
rebuilt if the loop changes, since its task group belongs to the old one.
"""

from __future__ import annotations

import asyncio
import hmac
import os

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN_VAR = "PURSER_MCP_TOKEN"


def _token() -> str:
    # Stripped: `echo tok | vercel env add` stores the trailing newline.
    return os.environ.get(TOKEN_VAR, "").strip()


def _presented(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"authorization":
            scheme, _, credential = value.decode("latin-1").partition(" ")
            return credential.strip() if scheme.lower() == "bearer" else ""
    return ""


class McpEndpoint:
    def __init__(self) -> None:
        self._app: ASGIApp | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None
        self._task: asyncio.Task | None = None  # held so the loop does not drop it

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = _token()
        if not token:
            return await Response(status_code=404)(scope, receive, send)
        if not hmac.compare_digest(_presented(scope).encode(), token.encode()):
            return await Response(
                status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )(scope, receive, send)
        if scope["method"] != "POST":
            return await Response(status_code=405, headers={"Allow": "POST"})(
                scope, receive, send
            )
        app = await self._ready()
        await app(scope, receive, send)

    async def _ready(self) -> ASGIApp:
        loop = asyncio.get_running_loop()
        if self._app is not None and self._loop is loop:
            return self._app
        if self._lock is None or self._loop is not loop:
            self._lock, self._loop, self._app = asyncio.Lock(), loop, None
        async with self._lock:
            if self._app is None:
                self._app = await self._start()
        return self._app

    async def _start(self) -> ASGIApp:
        from mcp.server.transport_security import TransportSecuritySettings

        from purser_mcp.server import build_server

        server = build_server()
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
            # The SDK's default (host 127.0.0.1) rejects any real Host header.
            # The bearer token above is the gate.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        ready = asyncio.Event()

        async def hold() -> None:
            async with server.session_manager.run():
                ready.set()
                await asyncio.Event().wait()

        self._task = asyncio.create_task(hold())
        await ready.wait()
        return app
```

`asyncio.Lock` isn't created in `__init__` because it would bind to whichever loop is running at import time. The lock is recreated per loop in `_ready`.

- [ ] **Step 4: Register the route in `src/purser_api/main.py`**

Add the import `from starlette.routing import Route` and `from purser_mcp.http import McpEndpoint`. `purser_mcp.http` imports only the stdlib and Starlette, which keeps the cold-start test green. Then, after `app.include_router(chat.router)` and **before** the `if _DIST.is_dir():` static mount:

```python
# MCP for Claude Code/Desktop (see purser_mcp.http). A Route, not a mount: a
# mount answers POST /mcp with a 307, and it must come before the "/" static
# mount, which would otherwise swallow it. Outside /api, so the passcode gate
# does not apply -- it has its own bearer token.
app.router.routes.append(Route("/mcp", McpEndpoint()))
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_mcp_http.py tests/test_cold_start.py tests/test_auth.py tests/test_api.py -v`
Expected: all pass.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: everything passes, including the retrieval eval gate. Live tests pass or skip as before.

- [ ] **Step 7: Docs**

In `.env.example`, after the `PURSER_PASSCODE=` block:

```sh
# MCP server at /mcp, for Claude Code and Claude Desktop. Unset: /mcp answers
# 404. Set: requests need `Authorization: Bearer <this>`. Generate one with
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
PURSER_MCP_TOKEN=
```

In `README.md`, add a row to the Configuration table after `PURSER_PASSCODE`:

```markdown
| `PURSER_MCP_TOKEN` | turns on the MCP server at `/mcp`; clients send it as a bearer token |
```

Then add a section just before `## Quick start`:

````markdown
## Purser in Claude (MCP)

The same five tools the agent uses, plus `ask` for Purser's own cited answer,
served at `/mcp` for Claude Code and Claude Desktop. Set `PURSER_MCP_TOKEN`, then:

```sh
claude mcp add --transport http purser https://<your-app>/mcp \
  --header "Authorization: Bearer $PURSER_MCP_TOKEN"
```

Claude calls the tools on its own when a question needs the manual. Unlike the
PWA, quoting verbatim is an instruction to the client model, not a guarantee;
`ask` keeps the guarantee, because its citations are spliced from the index.
````

- [ ] **Step 8: Commit**

```bash
uv run ruff check src tests
git add src/purser_mcp/http.py src/purser_api/main.py tests/test_mcp_http.py \
  tests/test_cold_start.py tests/conftest.py .env.example README.md
git commit -m "feat(mcp): serve the MCP server at /mcp behind a bearer token"
```

---

### Task 4: Local end to end, then production

This needs the human partner for the production steps: setting a Vercel env var and deploying are outward-facing actions. Stop and ask before each one.

- [ ] **Step 1: Local end to end with a real client**

```bash
export PURSER_MCP_TOKEN=$(uv run python -c "import secrets; print(secrets.token_urlsafe(32))")
uv run uvicorn purser_api.main:app --port 8000   # in the background
claude mcp add --transport http purser-local http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer $PURSER_MCP_TOKEN"
claude mcp list    # expect: purser-local ... ✓ Connected
```

Expected: `purser-local` shows as connected. If it shows failed, capture the uvicorn log for the `/mcp` requests (method + status) before changing anything.

Then `claude mcp remove purser-local` and stop uvicorn.

- [ ] **Step 2 (ask first): Set the token on Vercel production**

Give the human partner the generated token and the command, and let them run it or approve it:

```bash
vercel env add PURSER_MCP_TOKEN production
```

- [ ] **Step 3 (ask first): Merge and deploy**

Follow the repo's existing flow (`Merge feat/...` commits on `main`, deployed by Vercel). Use superpowers:finishing-a-development-branch.

- [ ] **Step 4: Production end to end (user memory: ask one real question, not just status checks)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<app>/mcp          # 401
curl -s -o /dev/null -w "%{http_code}\n" https://<app>/api/session           # 200, PWA unaffected
claude mcp add --transport http purser https://<app>/mcp \
  --header "Authorization: Bearer <token>"
```

In a fresh Claude Code session, ask: *"Using purser, what are the brace commands for a planned ditching? Quote the manual."* Expected: the tool calls show `search`, then `read_section` or `read_page`, and the answer quotes the manual with `PART … § … p.…` labels. Also call `ask` once. Report the question, the tools called, and one cited label.
