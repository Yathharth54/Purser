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
