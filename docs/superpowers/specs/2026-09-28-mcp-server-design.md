# Purser MCP server: design

**Date:** 2026-09-28
**Status:** approved in conversation, pending written review

## Goal

A fun build: expose Purser's manual retrieval as an MCP server, so Claude Code and
Claude Desktop can search and read the SEP manual and cite it. Diya keeps using the
PWA, and the MCP server is for us. Sending manual text to Claude is cleared with the
officials.

**Success:** from Claude Code, `claude mcp add` against the production URL, one real
crew question answered with `PART … § … p.…` labels drawn from the tool results.

## Non-goals

OAuth, claude.ai/mobile custom connectors, a secret-URL token, MCP resources and
prompts. All can come later, and none is needed for Claude Code or Desktop.

## Architecture

```
Claude Code ──HTTP + Bearer──▶ /mcp  (same Vercel function as the PWA API)
                                 │
                        purser_mcp.server  (MCPServer, stateless, JSON responses)
                                 │
              purser_api.deps: get_tools() / get_agent()   ← existing singletons
                                 │
                 purser_core.PurserTools  /  LookupAgent + citations.resolve_all
```

- New package `src/purser_mcp/`. It depends on `purser_core`, `purser_agent` and
  `purser_api` (for `deps` and `citations`). Nothing depends on it except the mount in
  `purser_api.main`.
- SDK: `mcp` 2.x, already in `uv.lock` through `pydantic-ai-slim[mcp]` (0 bytes
  added). It is declared explicitly in `pyproject.toml`. In 2.x the class is
  `mcp.server.mcpserver.MCPServer` (FastMCP was renamed).
- Transport: `streamable_http_app(stateless_http=True, json_response=True)`, which
  holds no session state between requests and so suits serverless.

## Tools

| tool | wraps | notes |
|---|---|---|
| `search(query, k=8)` | `PurserTools.search` | section hits, best first |
| `toc(part=None)` | `PurserTools.toc` | |
| `read_section(section, page_from=1, page_to=None)` | `PurserTools.read_section` | `max_pages=MAX_READ_PAGES` (6) |
| `read_page(pdf_page, before=0, after=0)` | `PurserTools.read_page` | `max_pages=MAX_READ_PAGES` |
| `lookup_term(term)` | `PurserTools.lookup_term` | |
| `ask(question)` | `get_agent().run` + `resolve_all` | returns `body`, `not_in_manual`, verbatim `citations` |

- Descriptions reuse the agent's tool docstrings (`purser_agent/lookup.py`), so both
  surfaces explain the tools the same way.
- The five raw tools are marked `readOnlyHint`. Pydantic return types give structured
  output automatically.
- `ask` is the only tool that spends the LLM key. An agent failure comes back as a tool
  error, not a 500.
- Server `instructions`: quote the manual's lines verbatim and cite them by their
  `PART … § … p.…` coordinates, never paraphrase a procedure, and say plainly when the
  manual does not cover something.
- The verbatim-citation guarantee is **a convention the client model is asked to
  follow**, not enforced as in the PWA. `ask` keeps the PWA's guarantee, because its
  citations come from `resolve_all`.

## Auth

- `/mcp` sits outside the `/api/` passcode gate and has its own check, in its own ASGI
  wrapper:
  - `PURSER_MCP_TOKEN` unset: every `/mcp` request returns 404, so the server is off
    by default.
  - Set, with a header other than `Authorization: Bearer <token>`: 401, compared with
    `hmac.compare_digest`.
- Rejection happens before the SDK is imported or any work is done.
- DNS-rebinding protection is turned off (`TransportSecuritySettings(enable_dns_rebinding_protection=False)`).
  The SDK's default for `host=127.0.0.1` would reject the production Host header, and
  the bearer token is the actual gate.

## Cold start

`import mcp.server` costs about 0.29 s against a 0.46 s app import today. The wrapper
imports and builds the MCP app on the **first `/mcp` request**, so PWA cold starts are
unchanged.

The SDK's session manager needs `session_manager.run()` held open, and a mounted
sub-app's lifespan does not run under FastAPI. The wrapper therefore starts
`run()` in a background task on first use, holds it open for the life of the process,
and waits for it to be ready before serving. It does not depend on whether Vercel runs
ASGI lifespan.

The `/mcp` mount is registered **before** the `/` StaticFiles mount, which would
otherwise swallow it.

## Testing

- Tool tests run the in-process `mcp.Client(server)` against `data/`, and skip if the
  index is not built (the same pattern as `test_tools.py`). They cover list_tools
  (six names) and one call each for `search`, `toc`, `read_section`, `read_page` and
  `lookup_term`.
- `ask` gets a live test gated like `test_agent.py`'s `needs_live`.
- HTTP tests use `TestClient`: 404 when unset, 401 for a missing or wrong token, 200 on
  `initialize` and `tools/list` with the right token, and two sequential requests to
  prove the lazy session manager survives.
- A boundary test: `purser_core` must not import `mcp`, which is added to `FORBIDDEN`.
- A cold-start test checks that importing `purser_api.main` does not import `mcp.server`.
- Production: set `PURSER_MCP_TOKEN` on Vercel, deploy, `claude mcp add`, and ask one
  real question end to end.
