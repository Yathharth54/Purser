<p align="center">
  <img src="docs/banner.png" alt="Purser Agent" width="100%">
</p>

# Purser

A cited retrieval agent over the Airbus A320/321 Safety and Emergency Procedures
Manual (`ifly.SEP`, Issue IX Rev 04). It finds the page; your eyes stay the authority.

Design spec: [`docs/superpowers/specs/2026-09-22-purser-design.md`](docs/superpowers/specs/2026-09-22-purser-design.md)

## Layers

```
purser_ingest  ──writes──▶  data/                       PDF → index, once per revision
purser_core    ──reads───▶  data/                       hybrid search + tree navigation
purser_agent   ──uses────▶  purser_core                 one agent, five tools
purser_api     ──uses────▶  agent + core                streaming, sessions, citations
web            ──HTTP────▶  purser_api                  React PWA
```

`purser_core` imports nothing from the web stack. `tests/test_boundaries.py` enforces
that, which is what keeps a future MCP adapter cheap.

## Setup

```sh
uv sync --extra dev
cp .env.example .env          # add OPENAI_API_KEY
purser ingest "docs/<manual>.pdf" --out data/
pytest
```

The manual PDF is **not** in this repo — it is a controlled document. Place your own
copy in `docs/` (gitignored) before running ingest.

## Running it with Docker

This is how it is meant to be run. One container serves the API and the PWA together.

**Before you build, two things must be in place:**

1. **The manual PDF in `docs/`.** It is gitignored and copied into the image at build
   time, because page images are rasterised on demand at request time. Without it,
   `/api/page/{n}/image` returns 503.
2. **`.env` with your key.** `OPENAI_API_KEY` is read from the environment and is never
   baked into the image.

```sh
cp .env.example .env         # add OPENAI_API_KEY
docker compose up -d --build
```

Then open <http://localhost:8000>. If something already holds port 8000:

```sh
PURSER_PORT=8010 docker compose up -d
```

**`.env` values.** `PURSER_PDF_PATH` must stay quoted — the manual's filename contains
spaces, and an unquoted copy of it breaks any shell that sources the file.

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | required |
| `PURSER_MODEL` | defaults to `openai:gpt-4o` |
| `PURSER_PORT` | host port, defaults to 8000 |
| `PURSER_PDF_PATH` | set inside the container by compose; only needed locally for dev |

**Her conversation threads live in the `purser-var` volume**, along with the rendered page
cache. Do not prune it. `docker compose down` keeps it; `docker compose down -v` destroys
it and every thread she has.

**On shutdown:** `docker stop` exits **143**, not 0. uvicorn re-raises the captured
SIGTERM after shutting down gracefully, which is the Unix convention, not a fault. Judge
health by the container healthcheck or by `Application shutdown complete` in the logs.
A **137** means it was SIGKILLed after the grace period — that one is a real problem.

### Rebuilding the index

`data/` is committed and only needs regenerating when the manual is reissued:

```sh
uv sync --extra dev
uv run purser ingest "docs/<the new manual>.pdf" --out data/
uv run pytest tests/eval/          # confirm retrieval accuracy before trusting it
docker compose up -d --build
```

Ingest is pure parsing — no LLM, no network. Structure comes from the footer every page
prints for itself, so a reissue with the same footer grammar needs no code change.

## Layout

| Path | Contents |
| --- | --- |
| `src/purser_ingest/` | L0 — the only code that touches the PDF |
| `src/purser_core/` | L1+L2 — the boundary. No FastAPI, no Pydantic AI, no network |
| `src/purser_agent/` | L3 — LookupAgent, LLM-facing schemas |
| `src/purser_api/` | L4 — FastAPI, citation splicing, app.sqlite |
| `web/` | L5 — React PWA |
| `data/` | committed index (~10 MB) |
| `var/` | runtime state — needs a persistent volume in production |
| `tests/eval/` | ~40 real questions, the retrieval accuracy gate |
