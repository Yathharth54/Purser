# Purser — Design Spec

**Date:** 2026-09-22
**Status:** Approved for planning
**Source document:** `docs/Airbus SEP Manual Issue IX Rev 04 Effective 08th Oct 2025 2.pdf`
(InterGlobe Aviation / IndiGo, `ifly.SEP`, Issue IX Rev 04, effective 08 Oct 2025, 1,226 pages)

---

## 1. Problem

A working A320/321 cabin crew member needs answers from a 1,226-page Safety and
Emergency Procedures manual. Today that means scrolling a PDF on a phone. General
purpose LLM apps cannot help: the document is too large to paste, and a model that
paraphrases a safety procedure is worse than no answer at all.

Purser is a chat agent over that manual. It answers in her own vocabulary, quotes the
manual verbatim, and cites the exact Part, Section and page — the same coordinates she
would use to find it in the paper copy.

## 2. Users and scope

**User:** one flight attendant. Not a product, not multi-tenant, no accounts.

**In scope**

- Fast lookup during duty: "what's the PA for a ditching?"
- Topic explanation for recurrent training prep: "explain oxygen administration"
- Stateful conversation — follow-ups resolve against prior turns
- Verbatim citation with a tappable image of the real manual page

**Out of scope for v1** — see §14 for the full list with reasons.
Quizzes, accounts, revision diffing, multi-manual support, offline search, voice input.

## 3. Principles

These are load-bearing. Every design decision below traces to one of them.

1. **The model finds; it does not decide.** Every factual claim resolves to verbatim
   manual text. The model never adjudicates correctness of a procedure.
2. **Quotes are correct by construction, not by validation.** The model emits page and
   line coordinates. The backend splices the text. There is no code path in which a
   model-authored sentence is presented as manual text.
3. **Structure is parsed, never inferred.** Every page of this manual stamps its own
   coordinates in its footer. No LLM participates in ingest.
4. **Shrink the model's job.** Retrieval is deterministic code; citation resolution is a
   slice; routing is a UI tab. What remains is small enough for a cheap model.
5. **The retrieval core knows nothing about the web.** It is a plain Python package so
   that a second consumer (an MCP server) costs a day, not a fork.

## 4. Architecture

Six layers, dependencies pointing one way only.

```
purser_ingest  ──writes──▶  data/
purser_core    ──reads───▶  data/          numpy, sqlite3, onnxruntime
purser_agent   ──uses────▶  purser_core    + pydantic_ai
purser_api     ──uses────▶  agent + core   + fastapi, sqlmodel
web            ──HTTP────▶  purser_api
```

| Layer | Package | Responsibility |
| --- | --- | --- |
| L0 | `purser_ingest` | PDF → index. CLI, run once per manual revision. |
| L1 | `data/` | The index: two committed files plus two JSON. |
| L2 | `purser_core` | Hybrid search, tree navigation, verbatim page reads. |
| L3 | `purser_agent` | One Pydantic AI agent, five tools, typed output. |
| L4 | `purser_api` | FastAPI. Streaming, session state, citation splicing. |
| L5 | `web` | React PWA. |

**Deployment:** one container, one process. FastAPI serves the built React bundle.
No database server. One external API call (the LLM).

## 5. Document model

The manual's own structure, parsed from page footers.

```python
class PartName(StrEnum):
    ONE = "PART ONE"
    TWO = "PART TWO"
    THREE = "PART THREE"
    FOUR = "PART FOUR"
    FIVE = "PART FIVE"
    SIX = "PART SIX"
    SEVEN = "PART SEVEN"
    EIGHT = "PART EIGHT"
    NINE = "PART NINE"
    TEN = "PART TEN"
    ANNEX = "Annexures"
    FRONT = "Front Matter"


class Page(BaseModel):
    pdf_page: int  # 1..1226, the physical page — used to render images
    part: PartName
    section: str | None  # "4.4"; None for Parts Seven-Ten, Annexures, front
    section_title: str | None  # "Evacuations"
    page_in_section: int  # 34   <- what she flips to
    section_total: int  # 80
    effective: date
    revision: str | None  # "Issue IX Revision 00", from the page header
    lines: list[str]  # verbatim, 0-indexed, the citation substrate
    text: str  # lines joined, for FTS5 and embedding
```

`page_in_section` and `pdf_page` are both kept deliberately: the first is what she
reads in a citation, the second is what the renderer needs. They are not interchangeable
and conflating them would produce citations that look right and point wrong.

### Verified structure

37 numbered sections across Parts One–Six (pages 29–988), then Parts Seven–Ten
(989–1196) and Annexures (1197–1226) which carry no section numbers.

Largest sections: §3.5 Passenger Handling (104 pp), §5.1 Emergency Equipment (102 pp),
§6.1 Physical Description (86 pp), §4.4 Evacuations (80 pp).

## 6. L0 — Ingest

CLI: `purser ingest docs/<manual>.pdf --out data/`

### 6.1 Text extraction

`pdftotext -layout` over the whole PDF, split on form feed. **Verified:** the manual has
a complete text layer — only 3 of 1,226 pages are image-only, median 2,015 characters
per page. No OCR is required.

### 6.2 Footer grammar — four patterns

**This is verified against the real document: 1,222 of 1,226 pages match.**

```python
SEC   = r'(?P<part>PART\s+[A-Z]+)\s+Section\s+(?P<section>[\d.]+)\s+'
        r'Page\s+(?P<p>\d+)\s+of\s+(?P<t>\d+)\s+Effective\s*(?P<eff>.+?)\s*$'   # 952 pp
PART  = r'(?P<part>PART\s+[A-Z]+)\s+'
        r'Page\s+(?P<p>\d+)\s+of\s+(?P<t>\d+)\s+Effective\s*(?P<eff>.+?)\s*$'   # 218 pp
ANNEX = r'(?P<part>Annexures?)\s+'
        r'Page\s+(?P<p>\d+)\s+of\s+(?P<t>\d+)\s+Effective\s*(?P<eff>.+?)\s*$'   #  30 pp
FRONT = r'^\s*(?P<code>GOTC|GTOC|ROR|DL|LEP|HIS|LOC|FDW|ACK|ISP)\s+'
        r'(?P<p>\d+)\s+of\s+(?P<t>\d+)\s+Effective\s*(?P<eff>.+?)\s*$'          #  22 pp
```

Patterns are tried in that order; first match wins. The last footer occurrence on a
page is authoritative (headers can repeat mid-page on sparse pages).

**Two findings that must not be lost:**

- `Effective\s*` — not `\s+`. 53 pages in §6.7 print `Effective18 May 2023` with no
  space. Requiring whitespace silently drops an entire 60-page section on exits.
- Front matter footers omit the word `Page` entirely (`LOC 2 of 4 Effective ...`).

**Pages 1–4 carry no footer** (cover, two blanks, the DGCA approval letter). They are
assigned `PartName.FRONT` with `section_title="Manual Administration"` explicitly.

### 6.3 Structural assertion

`test_structure.py` asserts **every one of the 1,226 pages resolves to a coordinate**,
and that within each section `page_in_section` is a **contiguous run with no gaps or
duplicates, ending exactly at `section_total`**.

**Corrected 2026-09-22.** An earlier draft asserted the run starts at 1. It does not,
for five sections, and the difference is a property of the manual rather than a parse
bug. Parts One, Two, Three, Four and Six each open with a 2-page title/contents lead-in
whose footer carries no Section token (`PART ONE   Page 1 of 76`). Those two pages share
the following section's counter, so the section itself starts at 3:

| Section | Run | Declared total | Lead-in pages (PDF) |
| --- | --- | --- | --- |
| §1.1 | 3..76 | 76 | 27–28 |
| §2.1 | 3..30 | 30 | 141–142 |
| §3.1 | 3..28 | 28 | 195–196 |
| §4.1 | 3..24 | 24 | 523–524 |
| §6.1 | 3..88 | 88 | 749–750 |

The lead-in pages stay `section=None`. Folding them into the following section would
produce a tidier 1..N invariant, but only by **inferring** that a Part-only block belongs
to the section after it — which violates principle 3 (§3) and puts a heuristic in the one
code path where a mistake yields a citation pointing at the wrong page. They remain
searchable and readable via `read_page`; they are simply not returned by `read_section`.

This is the most important test in the project. A silent footer-parse failure does not
crash anything — it produces a citation that points at the wrong page, which is the
worst defect this application can ship.

### 6.4 Section titles and revision

Taken from the page header line, which carries
`<Section Title>    Issue IX    Revision NN`. Title is the text before `Issue`;
revision is the whole trailing token. First non-empty title seen in a section wins.

**A title may wrap across the revision line** and the parser must reassemble it.
`pdftotext -layout` interleaves the wrapped remainder *after* the revision token:

```
  'Rapid and slow decompression (Pressurization'
  '                       Issue IX   Revision 00'
  'Problems)'                                      <- belongs to the title
```

Two of the 37 sections wrap this way — §4.3 *Rapid and slow decompression
(Pressurization Problems)* and §3.9 *Fuelling with Passengers On Board and or While
Disembarking/Embarking*. A regex whose whitespace class spans newlines silently keeps
only the fragment adjacent to the revision token, producing a truncated title on every
citation into those sections.

**Amended 2026-09-22 — the List of Chapters fallback is struck.** An earlier draft
required falling back to the titles on pages 17–20 when a header title is blank. All 37
numbered sections resolve a title from their own header, so the fallback has no consumer.
Removed under YAGNI rather than left as an unimplemented requirement.

### 6.5 Glossary mining

**Verified against the document.** §1.2 *Aviation Terminology* (pp. 103–122) carries
three distinct structures, and they need three parsers:

| Structure | Where | Shape | Yield |
| --- | --- | --- | --- |
| Prose definitions | §1.2, and scattered in §3.1 | `TERM: definition` at line start | ~90 |
| ~~NATO phonetic alphabet~~ | ~~pp. 119–120~~ | ~~`X – X-ray`~~ | **excluded** |
| §1.8 Aviation Abbreviations | p. 121 | **two-column** `ABBR – Expansion` | 46 |

**Amended 2026-09-22 — the phonetic alphabet is deliberately excluded.** Its entries are
single characters, and `expand_query` lowercases and matches per token: a query containing
the token `s` or `x` would inject "Sierra" or "X-ray" into the search. Terms shorter than
two characters are rejected, as are `NOTE\d*` footnote markers. Expected yield is therefore
**131 entries**, not ~162 — that difference is intended, not a regression.

The abbreviations table is the highest-value of the three — it is where `ABP`, `CIDS`,
`EPSU`, `LRBL`, `PAX` and `PA` are defined, which is exactly the vocabulary the lexical
lane needs. It is two columns split on runs of 3+ spaces, and some entries wrap onto the
following line (`CIDS – Cabin Inter- Communication Data` / `System`).

Note: §3.1 *Common Terminology* is **not** a glossary despite its name — it is mostly
prose on physiology and psychoactive substances, with a few `TERM:` lines mixed in.
An earlier draft of this spec assumed otherwise.

All three feed `data/glossary.json` as `{term, definition, aliases[], pdf_page}`.

Used for query expansion (§8.2) and by the `lookup_term` tool. Every glossary entry
keeps its source page so a definition is citable like anything else.

### 6.6 Page images

Rendered on demand by `pdftoppm -r 150 -png -f N -l N`, converted to WebP, cached
under `var/pagecache/`. Not pre-rendered: all 1,226 pages would be roughly 200 MB of
dead weight in the image.

**Consequence:** the PDF must be present at runtime. It is copied into the container at
build time and is **not committed to git** — it is a controlled document.

### 6.7 Embedding build

`bge-small-en-v1.5` via `onnxruntime`, 384 dimensions, one vector per page.
Output `data/vectors.npy`, float32, shape `(1226, 384)`, L2-normalised, row order
matching `pdf_page - 1`. Size ≈ 1.8 MB.

## 7. L1 — Index

Committed to git under `data/`. Total ≈ 10 MB.

| File | Contents |
| --- | --- |
| `manual.sqlite` | `pages` table (the `Page` model, `lines` as JSON) + `pages_fts` FTS5 virtual table over `text` |
| `vectors.npy` | `(1226, 384)` float32, L2-normalised |
| `toc.json` | Part → Section → page-range tree |
| `glossary.json` | Mined terms |

Committing the index means deploy needs neither the PDF nor an ingest run — except for
page-image rendering, which is why the PDF ships in the image anyway.

## 8. L2 — Retrieval core

Plain Python. **Imports nothing from FastAPI, Pydantic AI, or the network.** Enforced by
`test_boundaries.py`.

### 8.1 Hybrid search

Two independent retrievers over the same page records, fused by Reciprocal Rank Fusion:

```
score(page) = Σ  1 / (k + rank_lane(page))      k = 60
```

- **Lane A — lexical.** SQLite FTS5 BM25. Carries acronyms and terms of art
  (PBE, ELT, CIDS, ABP, Type III) which embeddings mangle.
- **Lane B — semantic.** Cosine over `vectors.npy`, brute force in NumPy. 1,226 × 384
  floats; no vector database, no index structure, sub-millisecond.

RRF is chosen over score normalisation because BM25 and cosine are not on comparable
scales and any normalisation constant would be a tuned magic number.

### 8.2 Query expansion

Before either lane, expand the query using `glossary.json`: a matched term contributes
its canonical form and aliases. "smoke hood" reaches Lane A as "PBE" and "Protective
Breathing Equipment" too.

This is what lets a small local embedding model carry the semantic lane — most of the
vocabulary gap in this document is terminology the document itself defines.

### 8.3 Public interface

```python
def search(query: str, k: int = 8) -> list[SearchHit]     # coordinates + snippet only
def toc(part: PartName | None = None) -> list[TocNode]
def read_section(section: str, page_from: int = 1, page_to: int | None = None) -> list[PageText]
def read_page(pdf_page: int, before: int = 0, after: int = 0) -> list[PageText]
def lookup_term(term: str) -> GlossaryEntry | None
def page(pdf_page: int) -> Page                            # used by citation resolution
```

`search` returns snippets, never full pages. Reading is a separate, explicit act — that
separation is what makes the agent read a neighbourhood in order rather than assemble an
answer from disconnected fragments.

## 9. L3 — Agent

**One agent.** Routing between modes is a UI concern; there is no router agent.

```python
LookupAgent = Agent(
    model=os.environ["PURSER_MODEL"],  # "openai:gpt-4o" for v1
    output_type=Answer,
    deps_type=PurserDeps,
    tools=[search, toc, read_section, read_page, lookup_term],
)
```

### 9.1 Output type — the safety contract

```python
class CiteRef(BaseModel):
    pdf_page: int
    line_from: int  # 0-indexed, inclusive
    line_to: int  # 0-indexed, EXCLUSIVE — a Python half-open slice
    # deliberately NO quote field.


class Answer(BaseModel):
    body: str  # framing in her language
    refs: list[CiteRef]
    not_in_manual: bool = False
```

The model cannot emit quote text because the schema has nowhere to put it.
Paraphrasing a procedure is not a mistake it can make — it is a field it does not have.

A model validator rejects an `Answer` with a non-empty `body`, no `refs`, and
`not_in_manual` false. This is a backstop; the schema shape is the mechanism.

`not_in_manual` is the honest exit: when retrieval does not cover the question, say so
and name the section worth reading rather than improvise.

### 9.2 Behaviour

- Concise. She is often reading this standing up. Lead with the answer.
- Quote-first: the framing exists to orient her around the manual's text, never to
  replace it.
- Stateful: prior turns are in context, so "and what about the overwing exit?" resolves
  without repetition.
- Never answers from parametric knowledge. If it did not read it, it does not say it.

### 9.3 Injected, not tool-called

Anything the backend already knows is passed via `deps` — never made a tool call.
For v1 that is the current thread's history and the manual's revision identity.

## 10. L4 — API

FastAPI. Thin: streaming, session persistence, and citation resolution.

| Endpoint | Purpose |
| --- | --- |
| `POST /chat` | SSE stream. Body `{thread_id, message}`. Emits token deltas then a final `citations` event. |
| `GET /threads` / `GET /threads/{id}` | Conversation list and history. |
| `GET /toc` | The parsed tree, for the browser surface. |
| `GET /section/{section}` | Verbatim section text for reading. |
| `GET /page/{pdf_page}/image` | Rendered WebP, cached. |

### 10.1 Citation resolution — the splice

```python
def resolve(ref: CiteRef) -> Citation:
    pg = corpus.page(ref.pdf_page)
    return Citation(
        part=pg.part,
        section=pg.section,
        section_title=pg.section_title,
        page_in_section=pg.page_in_section,
        pdf_page=pg.pdf_page,
        revision=pg.revision,
        effective=pg.effective,
        text="\n".join(pg.lines[ref.line_from : ref.line_to]),
    )
```

Two schema modules exist on purpose: `purser_agent/schemas.py` is what the model may
emit; `purser_api/schemas.py` is what the client receives. `citations.py` is the only
bridge. Keeping them apart is how the contract stays structural rather than becoming a
convention someone erodes in three months.

`line_from`/`line_to` are a half-open slice over `Page.lines`, matching Python semantics
exactly. The prompt states this explicitly, and `test_citations.py` asserts that a ref of
`(0, len(lines))` reproduces the page byte-for-byte. An off-by-one here would truncate a
procedure step without any visible symptom, so it is pinned by a test rather than by
convention.

Out-of-range or nonexistent refs are dropped with a logged warning rather than raising —
a malformed ref should cost one citation, not the whole answer.

## 11. L5 — Web

React 18 + Vite + TypeScript, built as an installable PWA. Types generated from the
OpenAPI schema so the Pydantic models remain the single source of truth.

**Surfaces**

- **Chat** — streaming answers, thread history, phone-first.
- **Citation chip** — `[PART FOUR §4.4 p.34]` inline. Tapping opens a drawer with the
  verbatim text *and the rendered manual page image*. This is the trust anchor: the
  model is a finder, her eyes remain the authority.
- **TOC browser** — the tree, for when she'd rather navigate than ask.

`manifest.webmanifest` with `display: standalone` so Add to Home Screen gives a
full-screen app with its own icon. No App Store, no developer account, no review.

## 12. Persistence

| Store | Mutability | Location |
| --- | --- | --- |
| `data/manual.sqlite`, `vectors.npy`, `toc.json`, `glossary.json` | immutable | committed to git, baked into the image |
| `var/app.sqlite` | mutable | persistent volume |
| `var/pagecache/` | derived cache | volume; safe to lose |

`app.sqlite` holds `threads`, `messages`, `citations`. SQLModel for tables, Alembic for
migrations.

**Known operational hazard:** most free hosting tiers have ephemeral disks. Without a
mounted volume `app.sqlite` is destroyed on redeploy and her conversation history is
lost. The manual index is unaffected (it is in the image). Mitigation: a mounted volume,
or Litestream replication to object storage.

## 13. Testing

| Test | Gate |
| --- | --- |
| `test_structure.py` | All 1,226 pages resolve to a coordinate; `page_in_section` is contiguous within every section. |
| `test_boundaries.py` | `purser_core` imports neither `fastapi` nor `pydantic_ai`. |
| `test_search.py` | Known queries return known sections; glossary expansion fires. |
| `test_citations.py` | Spliced text is byte-identical to the source page lines. |
| `tests/eval/` | ~40 real questions with known-correct sections. |

**The eval set is written before the agent exists**, against `purser_core.search`
directly. Retrieval quality must be demonstrable without a model in the loop — otherwise
a retrieval regression and a model regression are indistinguishable.

It is also the instrument for the later model swap: run the same 40 questions against
`gpt-4o` and a free-tier model and measure the difference rather than guessing at it.

Target: correct section in top-3 for ≥ 90% of eval questions. The eval set must be
written with the user — questions she would actually ask, in her words, not ours.

## 14. Non-goals for v1

| Cut | Reason |
| --- | --- |
| Quizzes / flashcards | She did not ask for them. "Explain this topic" already serves recurrent prep through the lookup agent. |
| Auth and accounts | One user. A private URL is the access control. |
| Native iOS app | $99/yr, review queue, 90-day TestFlight expiry — and App Store review would reasonably ask who owns this manual. The PWA path stays open to it later. |
| Revision diffing | Needs a previous revision PDF. `effective` and `revision` are already on every page record, so the door is open. |
| Multi-manual support | The footer grammar is specific to this manual's conventions. Generalising before a second manual exists is guessing. |
| Offline search | A service worker could cache the TOC and section text for a no-signal read-only mode. Genuinely useful; not v1. |
| Cross-section reasoning | Not a requested use case. Supported by the architecture as a prompt change. |
| Vector database | 1,226 × 384 floats is 1.8 MB. A database here is infrastructure carried for nothing. |
| LangChain / LlamaIndex | At this scale a framework adds indirection and removes debuggability from the one layer that must be correct. |
| Router agent | The UI already knows the mode. A router adds latency and a failure mode to re-decide a settled question. |
| Grading her answers | Deliberate: no model adjudicates whether her understanding of a safety procedure is correct. |

## 15. Model and provider

v1 runs on `openai:gpt-4o` via `PURSER_MODEL`. Correctness of the system comes first;
the provider swap is a one-variable change by construction and is measured with the eval
set, not assumed.

Accepted: free tiers of some providers may train on submitted content. The manual is a
controlled document rather than a secret one, and this was an explicit user decision.

## 16. Open questions

1. **Hosting.** Needs a persistent volume and must not hibernate — at her usage rate a
   sleeping instance would be hit on nearly every question. Provider not yet chosen.
2. **Eval question set.** Must be authored with the user before the agent is built.
   The plan ships a provisional 40 to unblock implementation; they are placeholders for
   her real questions, not a substitute.

*Resolved 2026-09-22:* glossary parse fidelity — see §6.5. Three structures, all
verified against the document.
