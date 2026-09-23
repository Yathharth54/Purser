<p align="center">
  <img src="docs/banner.png" alt="Purser Agent" width="100%">
</p>

# Purser

A cited retrieval agent over the Airbus A320/321 Safety and Emergency Procedures
Manual (`ifly.SEP`, Issue IX Rev 04). It finds the page; your eyes stay the authority.

Design spec: [`docs/superpowers/specs/2026-09-22-purser-design.md`](docs/superpowers/specs/2026-09-22-purser-design.md)

## Design

Built for a working flight attendant reading one-handed in a dim cabin, so the two
themes are not a light/dark toggle so much as two reading conditions: **day** (a warm
ivory ground, for a briefing room) and **cabin** (navy, for a dark aircraft). Tokens live
in `web/src/styles/tokens.css`.

**Palette** — a warm night sky with a single narrow gold accent:

| Token | Value | Use |
| --- | --- | --- |
| `--navy-900` / `--navy-860` / `--navy-820` | `#090f21` / `#0c1426` / `#111a33` | cabin ground, chrome, raised surfaces |
| `--sky-top` / `--sky-mid` / `--dawn` | `#0c1f3a` / `#1a3053` / `#fccc8a` | the brand artwork's gradient (icons, banner) |
| `--ivory` | `#f6efe3` | day ground / cabin text |
| `--gold` / `--gold-ink` | `#dcc08c` / `#7a5f21` | the one accent — see the tripwire below |

**The gold tripwire.** Gold marks the manual and the one primary action only: the
citation label, the manual's edge, the active tab, focus rings and the send control —
nowhere else. `--gold-ink` exists because raw `--gold` fails contrast on ivory; it is
gold's day-mode voice, not a second colour. If gold ever lands on a secondary button or
a background wash, the system has collapsed into a generic dark theme with an accent
colour — that regression is called out explicitly in the token file's own header comment.

**Three typefaces, three jobs:**

| Typeface | Role | Why |
| --- | --- | --- |
| **Cormorant Garamond** | Display — headings, the wordmark | A book serif. The manual is a document, not a dashboard, and this says so before a word is read. |
| **Atkinson Hyperlegible** | UI — body text, chat, controls | Designed by the Braille Institute for legibility at speed and in poor conditions — exactly the dim-cabin, one-handed reading this app is built for. |
| **IBM Plex Mono** | Citation text, tables | Manual quotes and two-column tables are rendered verbatim; monospace is what preserves a table's columns as the information they are, and signals "this is the source, not prose." |

**Regenerating the icons and banner.** Both are derived from the AI-generated brand
artwork committed in `assets/` and must be rebuilt from that source rather than
hand-edited:

```sh
python scripts/make_icons.py          # crops the logomark -> web/public/icons/*.png
python scripts/make_readme_banner.py  # crops + widens the hero -> docs/banner.png
```

`make_icons.py` cuts the logomark out of the hero art with padding tuned to survive
Android's circular maskable-icon crop, and additionally renders a full-bleed
`maskable-512.png`. `make_readme_banner.py` crops the 16:9 hero to a 5:1 banner strip and
paints out the subtitle band — the source artwork's subtitle reads "A CITED RETRIEVAL
AGENT **OVEN** THE AIRBUS A320/321" (a typo in the generated image, not a repo typo), so
it is removed by reconstructing the sky gradient behind it rather than shipped on the
front page of this README.

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
cp .env.example .env          # add the key for your provider
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
cp .env.example .env         # add the key for your provider
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
| `OPENAI_API_KEY` | required when `PURSER_MODEL` names `openai:` |
| `OPENROUTER_API_KEY` | required when `PURSER_MODEL` names `openrouter:` |
| `PURSER_MODEL` | defaults to `openai:gpt-4o`; see *Choosing a model* below |
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

**Use the `purser ingest` console script above, not `python -m purser_ingest.cli`.** The
latter is a silent no-op — `cli.py` has no `if __name__ == "__main__"` guard, so the
module runs its imports, prints nothing, and exits 0 without ingesting anything. It looks
like it worked; it did not.


## Choosing a model

`PURSER_MODEL` is the only place a model is named, and it is handed to
pydantic-ai verbatim — it infers the provider from the prefix. Nothing else in
the codebase knows which provider is in use.

```bash
PURSER_MODEL=openai:gpt-4o                           # default
PURSER_MODEL=openrouter:anthropic/claude-sonnet-4.5  # via OpenRouter
PURSER_MODEL=openrouter:openai/gpt-4o                # same model, OpenRouter billing
```

OpenRouter needs no client of its own: it is the same OpenAI-compatible surface
behind one account, and `pydantic-ai` ships the provider. Set
`OPENROUTER_API_KEY` instead of `OPENAI_API_KEY` and restart — the other may
stay empty.

If the key for the configured provider is missing, the app raises at agent
construction naming the variable it wants, rather than surfacing a 401 from
three layers down while she is waiting on an answer.

**One caveat.** The agent uses tool calling and a structured output type
(`Answer`, which carries `CiteRef` coordinates). Not every model OpenRouter
fronts supports function calling well enough for that. If citations stop
resolving after a model swap, suspect the model before the code — and check
`tests/eval/` still reports `recall@8` at its baseline.

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
