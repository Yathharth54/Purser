<p align="center">
  <img src="docs/banner.png" alt="Purser Agent" width="100%">
</p>

<h1 align="center">Purser</h1>

<p align="center">
  <b>Cited retrieval over a 1,226-page safety manual.</b><br>
  The model finds the page. The manual supplies the words.
</p>

<p align="center">
  <code>hybrid BM25 + dense retrieval</code> · <code>RRF fusion</code> · <code>tool-calling agent</code> ·
  <code>citations by construction</code> · <code>FastAPI + SSE</code> · <code>React PWA</code>
</p>

---

## The problem

My friend Diya is a flight attendant. Her Airbus A320/321 *Safety and Emergency
Procedures Manual* runs to **1,226 pages**.

General-purpose chatbots fail her twice over. The PDF is too big to upload whole, and
when one does answer there is no way to tell a sentence lifted from the manual from a
plausible sentence the model made up. For the brace commands on a ditching, "sounds
right" is a failure, not a partial success.

The job wasn't a smarter model. It was **retrieval that lands on the right section, and
an architecture where the source text can't be paraphrased**.

## How Purser answers

```
question
   │
   ▼
LookupAgent (pydantic-ai, tool calling)
   │  search(query)          ── BM25 over SQLite FTS5 ─┐
   │                         ── bge-small embeddings ──┴─▶ Reciprocal Rank Fusion
   │  toc(part)              ── the manual's own Part → Section tree
   │  read_section(§, pages) ── whole sections, page by page, in order
   │  read_page(n)           ── one page, line-numbered
   │  lookup_term(term)      ── glossary mined from the manual
   ▼
Answer { body, citations: [CiteRef(pdf_page, line_from, line_to)] }
   │                              ▲ coordinates only: no quote field exists
   ▼
citations.resolve()  ── splices the verbatim text out of the index
   │
   ▼
SSE stream (thread · tool · delta · citations · done)  ──▶  PWA
```

### What made it work

**The manual's structure is the index.** Every page prints a footer with its Part,
Section and page-in-section. Ingest parses that footer with no LLM and no network, so
each of the 1,226 pages is addressed as `PART FOUR §4.4 p.34`, and the contents tree
falls out of the document itself. A reissue with the same footer grammar needs no code
changes.

**Hybrid retrieval with rank fusion.** Two independent lanes:

- **Lexical:** SQLite FTS5 with BM25, for acronyms and jargon a crew member types
  exactly: `PBE`, `ELT`, `slide raft`, `L2`.
- **Semantic:** `BAAI/bge-small-en-v1.5` embeddings via fastembed (ONNX, CPU, no
  PyTorch), for how people actually ask: *"what do I do if the cabin fills with
  smoke"*.

BM25 scores and cosine similarity aren't on comparable scales, so they are merged with
**Reciprocal Rank Fusion** (`k = 60`), which uses rank alone. There's no normalisation
constant to tune, and the lanes stay independent.

**Sections, not snippets.** Procedures run across page breaks, so the agent reads whole
sections in page order (capped at 6 pages per read) rather than stitching 300-token
chunks back together. The reader carries state across pages too: a table that starts on
page 28 is still a table on page 31, even with no caption of its own.

**Citations are correct by construction.** The agent's output schema is
`CiteRef(pdf_page, line_from, line_to)`. It has **no `quote` field**, so the model has
nowhere to write one. The API splices the cited lines byte for byte from the index, and
the app shows the manual's own words beside the answer. Tap a citation and it opens the
rendered PDF page. The source always wins.

**An eval gate, not vibes.** `tests/eval/` holds 40 real crew questions with their
expected sections:

| metric | score |
| --- | --- |
| recall@8 | **100%** (40/40) |
| top-3 | 85% (34/40) |
| MRR | 0.748 |

The gate runs with the ordinary test suite, so a retrieval regression fails `pytest`
rather than surfacing mid-flight.

## The manual, readable

`pdftotext -layout` output is a wall of monospace. Purser's parser (`purser_core.blocks`)
recovers the document underneath and renders it as one:

- **Headings nest** into collapsible sections, in title case, with the manual's own
  numbers hung in a column (abbreviations, Roman numerals and aircraft codes kept as
  printed).
- **Two-column safety tables stay verbatim.** Their column gaps are what pair a command
  with its action, so they are never reflowed.
- **Notes, Cautions and Warnings** get escalating treatments.
- **Printed contents pages** turn into tappable *In this section* cards that jump to the
  page, with no dot leaders left.
- **Word's `o` sub-bullets nest**, hyphenated line breaks rejoin (`take-off`, not
  `take- off`), and sentences split mid-line are made whole.

All of it is display-side. `Block.text` stays as printed, and citation text is still
spliced verbatim.

## Built for the cabin

A PWA for reading one-handed in a dark aircraft:

- **Two themes as reading conditions,** not a light/dark toggle: **day** (warm ivory, for
  a briefing room) and **cabin** (navy, for a darkened aircraft), following the phone's
  setting on first run.
- **Atkinson Hyperlegible** for UI and body text, designed by the Braille Institute for
  legibility at speed and in poor conditions. **Cormorant Garamond** for display, because
  the manual is a document, not a dashboard. **IBM Plex Mono** for citations and tables,
  where columns are information.
- **Ask doubles as home.** *What do you need?*, with the question box front and centre,
  one-tap shortcuts into Evacuations, Smoke/fumes, Decompression and Fire fighting, and
  recent chats.
- **Chats persist** (Postgres on Vercel, SQLite locally), with a slide-in panel grouped by
  day, title search, and delete. The newest question stays pinned in view while its
  answer streams in below.
- **44 px touch targets**, full keyboard and screen-reader support (roving-tabindex tabs,
  focus-trapped drawers), and `prefers-reduced-motion` respected throughout.

**The gold tripwire.** Gold (`--gold`, and `--gold-ink` on ivory, where raw gold fails
contrast) marks the manual and the one primary action only: citation labels, the
manual's edge, the active tab, focus rings, the send button. If it ever shows up on a
secondary button or a background wash, the system has collapsed into a generic dark theme
with an accent colour. Tokens live in `web/src/styles/tokens.css`.

## Privacy and access

- **Private by default.** One shared passcode (`PURSER_PASSCODE`) gates every `/api`
  route, including the manual, chats, page images and the OpenAPI docs. The session is an
  HttpOnly, SameSite=Lax cookie holding an **HMAC keyed by the passcode**, never the
  passcode itself, so rotating it signs out every device.
- **Brute-force resistant.** Each wrong guess costs a second, and 10 failures in 15
  minutes pause logins across all instances.
- **The manual is not in this repo.** It is a controlled document. Bring your own copy.
- **Analytics are page views only:** Vercel Web Analytics, no cookies, never question
  text.

## Stack

| Layer | Package | Tech |
| --- | --- | --- |
| L0 ingest | `purser_ingest` | pdftotext layout parsing, footer grammar, glossary miner, FTS5 + vector index build |
| L1–2 core | `purser_core` | BM25, dense search, RRF, block parser, reading order. **Imports nothing from the web stack** |
| L3 agent | `purser_agent` | pydantic-ai, provider-agnostic, five tools, structured `Answer` |
| L4 API | `purser_api` | FastAPI, SSE streaming, SQLModel (Postgres / SQLite), pypdfium2 page renders, passcode gate |
| L5 web | `web/` | React 18, Vite, TypeScript, PWA manifest and icons |

```
purser_ingest  ──writes──▶  data/          PDF → index, once per revision
purser_core    ──reads───▶  data/          hybrid search + tree navigation
purser_agent   ──uses────▶  purser_core    one agent, five tools
purser_api     ──uses────▶  agent + core   streaming, sessions, citations
web            ──HTTP────▶  purser_api     React PWA
```

`tests/test_boundaries.py` fails the build if `purser_core` ever imports FastAPI,
pydantic-ai or an HTTP client. That boundary is what keeps a future MCP server a thin
adapter.

## Quick start

```sh
uv sync --extra dev
cp .env.example .env                      # add your provider key
uv run purser ingest "docs/<manual>.pdf" --out data/
uv run pytest                             # includes the retrieval eval gate
```

Then run the API and the web app side by side:

```sh
uv run uvicorn purser_api.main:app --port 8000
cd web && npm install && npm run dev      # proxies /api to 127.0.0.1:8000
```

The manual PDF goes in `docs/` (gitignored) before ingest.

## Configuration

Everything is environment-driven. See [`.env.example`](.env.example).

| Variable | Purpose |
| --- | --- |
| `PURSER_MODEL` | `provider:model`, default `openai:gpt-4o`. See *Choosing a model* |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | the key for whichever provider `PURSER_MODEL` names |
| `PURSER_PASSCODE` | turns on the passcode gate; empty means open (local dev) |
| `DATABASE_URL` | Postgres for chats (Neon on Vercel); unset means SQLite in `PURSER_VAR_DIR` |
| `PURSER_MAX_THREADS` | chats kept before the least recently used are pruned (default 100) |
| `PURSER_DATA_DIR` / `PURSER_VAR_DIR` | the committed index / runtime state |
| `PURSER_PDF_PATH` | the manual, for page images. **Keep it quoted**: the filename has spaces |
| `PURSER_PORT` | Docker host port (default 8000) |
| `FASTEMBED_CACHE_PATH`, `HF_HUB_OFFLINE` | set by the Docker image and the Vercel build so the embedding model is baked in and never downloaded at runtime |

### Choosing a model

`PURSER_MODEL` is the only place a model is named. It is handed to pydantic-ai verbatim,
which infers the provider from the prefix, and nothing else in the codebase knows which
provider is in use.

```sh
PURSER_MODEL=openai:gpt-4o                           # default
PURSER_MODEL=openrouter:anthropic/claude-sonnet-4.5  # via OpenRouter
PURSER_MODEL=openrouter:openai/gpt-4o                # same model, OpenRouter billing
```

A missing key fails at agent construction with the variable it wants, not as a 401 three
layers down. **Caveat:** the agent relies on tool calling plus a structured output type.
If citations stop resolving after a model swap, suspect the model before the code, and
check that `tests/eval/` still reports `recall@8` at its baseline.

## Deploying

### Vercel (production)

The repo is linked to a Vercel project. **A push to `main` is a production deploy.**
`scripts/vercel_build.py` builds the PWA and bakes the embedding model into the function
bundle. The Python API runs on Fluid Compute. Chats need `DATABASE_URL` pointing at
Postgres, because the function filesystem doesn't persist. Set `PURSER_PASSCODE`, the
model variables and `HF_HUB_OFFLINE=1` in the **Production** environment. Preview-only
variables are a classic way to ship a site that answers nothing.

### Docker (self-hosted)

One container serves the API and the PWA together.

```sh
cp .env.example .env          # add your key
docker compose up -d --build  # then open http://localhost:8000
PURSER_PORT=8010 docker compose up -d   # if 8000 is taken
```

Before you build, the manual PDF must be in `docs/`: it is copied into the image so page
images can be rasterised on demand. Without it, `/api/page/{n}/image` returns 503.

- **Chats live in the `purser-var` volume**, with the page-render cache.
  `docker compose down` keeps it; `down -v` destroys every chat.
- **`docker stop` exits 143, not 0.** uvicorn re-raises the SIGTERM after a graceful
  shutdown, which is the Unix convention, not a fault. A **137** (SIGKILL after the grace
  period) is the real problem.

## Rebuilding the index

`data/` is committed (~10 MB) and only needs regenerating when the manual is reissued:

```sh
uv run purser ingest "docs/<the new manual>.pdf" --out data/
uv run pytest tests/eval/          # prove retrieval before trusting it
```

**Use the `purser ingest` console script, not `python -m purser_ingest.cli`.** The
latter is a silent no-op: `cli.py` has no `__main__` guard, so it imports, prints
nothing, exits 0 and ingests nothing.

## Testing

```sh
uv run pytest                 # ~350 tests: parser guard pages, API, auth, citations, eval gate
uv run ruff check && uv run ruff format --check
cd web && npx vitest run && npm run build
```

The parser suite pins **guard pages**, real pages that each broke an earlier version of
the table and structure rules (594, 130, 552, 631, 613, 57, 299, 366, 596, 597, 182). Any
change to `blocks.py` is measured against all of them.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/purser_ingest/` | the only code that touches the PDF |
| `src/purser_core/` | retrieval and document structure: no FastAPI, no LLM, no network |
| `src/purser_agent/` | the LookupAgent, its prompt and LLM-facing schemas |
| `src/purser_api/` | FastAPI app: chat, manual, citations, auth, database |
| `web/` | the React PWA |
| `data/` | the committed index: pages, FTS5, vectors, contents tree, glossary |
| `tests/eval/` | 40 real questions: the retrieval accuracy gate |
| `docs/` | design spec, plans, handoff notes |
| `assets/` | source brand artwork |

### Brand assets

The icons and this banner are derived from the artwork in `assets/`. Rebuild them rather
than hand-editing:

```sh
python scripts/make_icons.py          # logomark → web/public/icons/*.png (incl. maskable)
python scripts/make_readme_banner.py  # hero → docs/banner.png
```

The banner script also paints out the source artwork's subtitle, which reads "A CITED
RETRIEVAL AGENT **OVEN** THE AIRBUS…": a typo in the generated image, not in this repo.

---

<p align="center">
  <i>For a document like this, you don't need a smarter model.<br>
  You need better retrieval and a rule that the source always wins.</i>
</p>
