# Handoff — make the manual read like a document

> **Status (2026-09-23): all three issues shipped on `feat/manual-structure`.**
> The fixes as written below were **unsafe** and were changed before shipping:
> issue 1's running minimum causes table runaways unless a heading closes a table
> first (pdf 299, 366), and issue 2's carry must be *confirmed* by the next page
> opening with a row, or it spreads those runaways across pages (56 pages, prose
> pdf 182 among them). Issue 3's thin structure was mostly the heading regex. See
> "Manual structure" in `docs/superpowers/plans/2026-09-23-purser-v2-rulings.md`
> for every decision and what it costs if wrong. The text below is kept as the
> original diagnosis.

Three separate problems, in the order I'd fix them. Each is independently
shippable. The first has a validated fix with numbers; the second has an
approach and a known complication; the third is the one the repository owner
actually cares most about and is the least specified.

Written after merging `feat/purser-v2` (32 commits, now on `main` at `2ce21ad`).

---

## Read this first — the invariants you must not break

These are load-bearing. Violating one produces text that still *reads* like
plausible manual prose, which is what makes it the worst available failure.

1. **`CiteRef` line indices are never renumbered.** `line_from` inclusive,
   `line_to` **exclusive**, both indices into the full, unfiltered
   `Page.lines`. Page furniture is stored as *metadata* (a list of line
   indices on `Page.chrome`), never by rewriting or renumbering lines.
   Any change that shifts an index silently invalidates every citation
   already stored in `var/app.sqlite`.
2. **`CiteRef` has no `quote` field, ever.** `src/purser_api/citations.py` is
   the only code in the system that produces quote text, and `Citation.text`
   is a **byte-exact splice** of `Page.lines`. `Citation.blocks` is *only how
   it is drawn*. If the two ever disagree about the words, `text` is the truth.
3. **`purser_core` must not import** `fastapi`, `pydantic_ai`, `openai`,
   `httpx`, `sqlmodel`, `starlette`. Enforced by `tests/test_boundaries.py`,
   which globs `purser_core/**/*.py`, so a new module is covered automatically.
4. **`parse_blocks(lines, chrome)` is per-page and pure**, and `chrome` holds
   indices **into the `lines` list you pass it**. `resolve()` calls it on a
   *slice* and rebases: `[c - lo for c in page.chrome if lo <= c < hi]`.
   Any cross-page state must live in the *caller*, not in `parse_blocks`.
5. The SSE stream uses **CRLF** — `\r\n\r\n`, not `\n\n`.
6. Commits carry the repository owner as sole author. **No `Co-Authored-By:`
   trailers, no "Generated with Claude Code" footers, no AI-attribution line
   of any kind.**

## Where things live

| | |
|---|---|
| `src/purser_ingest/chrome.py` | the six page-furniture patterns → line indices |
| `src/purser_core/blocks.py` | **the parser you will be changing** |
| `src/purser_core/reading.py` | `reading_pages(corpus, section)` — walks a section in page order |
| `src/purser_api/citations.py` | `resolve()` — the byte-exact splice, plus `Citation.blocks` |
| `web/src/components/ManualBlocks.tsx` | the single renderer, used by BOTH readers |
| `web/src/components/TocBrowser.tsx` | the section reader |
| `web/src/components/CitationChip.tsx` | the citation paper card |
| `docs/design/purser-v2-mockup.html` | **the approved design. Where prose and mockup disagree on appearance, the mockup wins.** |

Verify with `.venv/bin/python -m pytest -q` (expect **242 passed** with OpenAI
credits; the only failures without them are 4 in `tests/test_agent.py` hitting
`429 credit_balance_exhausted`), `.venv/bin/ruff check`,
`.venv/bin/ruff format --check`, and in `web/`: `npx tsc --noEmit`,
`npm run build`, `npx vitest run` (16 tests).

## The guard pages

Every table change must be measured against these. They were each established
by a previous bug and they constrain the rule from different directions.

| page | what it guards | expected non-blank table lines |
|---|---|---|
| **594** | a table must not swallow the rest of the page | 2 |
| **130** | a page-level `Note:` at indent 0 must close the table | 11 |
| **552** | a wrapped header cell 1 column left of the first row must NOT close it | 11 |
| **631** | a caption with an aircraft suffix (`Table 4.4Y (A-320)`) must open its table | 20 |
| **613** | a centred header row must not truncate the body | 17 → **18 after issue 1** |
| **57** | a PUA bullet glyph + padding must not read as a column gap | 7 |
| **299** | a subsection heading (`1.6 3 POINT BRIEFING`) must close the table above it | 16 |
| **366** | a gap-less `Note:` at the table edge, then `3. ADVISORY…`, must close it | 15 |
| **596** | a body row with an empty right cell must not close the table | 11 |
| **597** | a caption-less continuation page is a table in the reader (carried) | 0 per page, 52 in the reader |
| **182** | prose after a page that ended in a table must stay prose | 0 |

---

# Issue 1 — tables close at the first row with an empty second column

**Status: shipped — but only together with the heading rule (see banner).**

## What happens

`blocks.py` tracks `table_indent` from the **first** row after a caption. That
row is usually a *centred header*. The body sits further left. So the first
body row whose right-hand cell happens to be empty fails the indent test, has
no column gap, looks like prose — and closes the table mid-table.

Concretely, pdf **596** (`Table 4.4F`):

```
  30 ind=41  Table 4.4F                                     <- caption
  32 ind=9   Escape slide equipped      Slide raft equipped <- first row, table_indent = 9
  33 ind=0   To ABP 1: In case ...      To ABP 1: In case … <- body, kept (has a gap)
  ...
  42 ind=0   automatically, I will push it with force to    <- right cell empty, NO gap
                                                               -> 0 < 9-2, closes the table
```

Everything from line 42 on becomes `para`, including the rest of the table
spilling onto the next page.

## The fix

Track the **running minimum** of row indents, so the *body* defines the
table's left edge rather than the header. Only update it from lines that
actually look like rows.

```python
if indent >= table_indent - 2 or looks_like_row:
    table.append(raw.rstrip())
    if looks_like_row:
        table_indent = min(table_indent, indent)
    continue
```

## Measured

```
                  table lines   pages changed   guards
today                   1,946         —         all hold
running-minimum         2,480        41         all hold, 613 improves 17 -> 18
```

**+534 lines** returned to tables. The single change on 613 is
`"thrown either from the R2 or the L2"` — the continuation of *"The life raft
will be…"* in the row above, left cell continuing with the right cell empty.
That is a recovery; update the guard to 18.

Add a regression test on pdf 596 asserting line 42's text lands in the `table`
block. Make it fail against the current code first.

---

# Issue 2 — caption-less table continuation pages

**Status: shipped with a confirmed carry, in the reader and in citations.**

## What happens

`parse_blocks` opens a table only when it sees a `Table X.Y` caption. A table
spanning pages 28–31 has its caption on page 28, so pages 29–31 never open one
and their two columns interleave top-to-bottom.

pdf **597** captures **zero** table lines, before or after issue 1's fix. What
the reader sees:

```
detach the slide by pulling a white
To ABP1: You will inflate your life jacket,     <- right column, injected
handle at the centre of the girt bar            <- left column resumes mid-sentence
```

Left column is the *land* evacuation briefing; right is *ditching*. On this
page that is slide-vs-slide-raft — different procedures.

Issue 1's fix only moves the interleaved-page count from **285 → 275**.

## What I already ruled out — do not redo this

**Shape-based detection (column gutter) does not separate.** I measured the
strongest mid-page whitespace gutter shared across lines, as a ratio of body
lines:

```
real tables:  1082 100%   1086 100%   631 59%   473 57%   613 43%   646 24%   597 13%   552 12%   632 0%   634 0%
prose      :    12  74%    551  34%  1000 22%    594  8%   600  0%   100  0%   700  0%
```

Page 12 is prose and outranks most real tables. Pages 632 and 634 are genuine
tables scoring zero. No threshold separates them; any value both misses real
tables and wraps real prose in monospace.

**A "patience" counter (close only after K consecutive non-row lines) leaks.**
At K=2 it recovers ~500 lines but breaks two guards: 594 goes 2 → 3 and 130
goes 11 → 12. It re-introduces the runaway bug it was meant to avoid.

## The approach that is sound

**Continuation-carry.** Use the caption you already found instead of guessing:
if the previous page ended inside a table, the next page starts inside one.

- Add an optional parameter to `parse_blocks`, e.g.
  `parse_blocks(lines, chrome, *, start_in_table: bool = False)`. It must
  default to `False` so the citation slice path is unchanged until you
  deliberately change it (invariant 4).
- `reading_pages(corpus, section)` walks pages in order and already has the
  sequence. Thread the state: parse page *N*, note whether its last block is a
  `table`, pass that as `start_in_table` for page *N+1*.
- A caption or a top-level numbered heading on page *N+1* must still close it.
- Do issue 1 **first** — more pages will genuinely end inside a table
  afterwards, which is what makes the carry effective.

## The citation complication — the owner wants this fixed too

`resolve()` parses a **slice of a single page** and has no sequence context,
so a citation landing on page 597 will still interleave even after the section
reader is fixed.

`resolve()` does have `corpus`, so it can look back. But this is the function
that produces the audit trail, so:

- **`Citation.text` must stay byte-exact.** Only `Citation.blocks` may change.
- There is an existing test pinning this —
  `test_full_page_range_is_byte_exact_after_trimming` — keep it green.
- The rebasing test
  `test_chrome_is_rebased_onto_the_trimmed_slice_not_passed_page_absolute`
  demonstrates the bug and the fix on one fixture; do not let it rot.

---

# Issue 3 — the reader is a flat block stream, not a document

**Status: shipped — nested sections, steps, note severity, collapsible headings.**

> *"i dont like how in manual the text is so random and dumped, it should be in
> good section just like doc but cleanly in our app. sure cites should hve the
> same too."*

## What is wrong

`ReadingPage.blocks` is a **flat list**. The renderer walks it top to bottom
and styles each block by `kind`. Nothing groups content under the heading that
owns it, so a section reads as a stream of fragments rather than a document.

Corpus-wide the structure is also very thin:

```
para 6,925 | bullet 4,596 | subheading 1,363 | heading 444
note 207 | caption 197 | table 196
```

**444 headings across 1,226 pages** — about one per three pages. Most real
structure is landing in `subheading` (a flat all-caps test) or `para`.

A real page, §4.2 p.5 (pdf 551), as the reader receives it:

```
heading    L1  1. GENERAL
para       L0  Smoke is the result of combustion, is a byproduct of burning...
caption    L0  Table 4.2A
table      L0  Scenario | Suggested Verbiage
caption    L0  Table 4.2 A1
table      L0  Odor Type | Suspected Reason
para       L0  Note 1: Do not use any subjective words like think, feel etc.
para       L0  Note 2: The procedures in this chapter are applicable for A-320/321
```

Two concrete defects visible in that one page:

**(a) Notes are misclassified as paragraphs.** `_NOTE` is
`^(Note|Caution|Warning|NOTE|CAUTION|WARNING)\s*[:\-]\s*\S` — the `[:\-]` is
**required** and must be followed by a non-empty body. So:
- `Note 1: …` fails, because `1` is not `:` or `-`
- a bare `Note:` on its own line, with its body on the next line, fails the
  trailing `\S` — **33 such lines** across the corpus (pdf 152, 260, 345, 476,
  487, 541 `Caution:`, 588, 787 …)

These carry safety emphasis and are currently rendering as ordinary prose.

**(b) There is no hierarchy.** `1. GENERAL` does not own the paragraphs and
tables beneath it. Nothing nests.

## Suggested direction — confirm with the owner before building

1. **Fix the note classification** — numbered notes and standalone labels
   (a standalone `Note:` should adopt the following line as its body).
2. **Add a grouping layer** over the flat block list: a heading owns
   subsequent blocks until a heading of equal or higher level. Put it in
   `purser_core` (a pure function over `list[Block]`) so **both** readers get
   it, and so `Block` itself stays a flat serialisable record.
3. **Render the hierarchy** in `ManualBlocks.tsx` — indentation, spacing, and
   rules that make a section visually a unit. Check `purser-v2-mockup.html`
   first; its formatted-manual section is the approved look and **wins over
   any description of it**.
4. **Apply it to the citation card too** — same component, so this follows if
   the grouping lives in the data rather than the renderer.

Open questions for the owner: should sections be collapsible? Should the
reader show a per-section outline? Neither is specified.

---

## Working notes

- Measure before proposing. Every fix above was found by running a scratch
  script against `data/manual.sqlite` (1,226 pages), not by reading code.
  Three parser defects in this project were found by *downstream consumers*
  and none by the parser's own tests — a corpus sweep counts blocks, a
  renderer shows them.
- `curl` is blocked by a hook. Drive HTTP from Python with `httpx`.
- `resize_window` does not work in this sandbox. Verify phone width by serving
  the production build (`vite preview`) and rendering it in a same-origin
  iframe at true CSS pixel width, confirming via `iframe.contentWindow.innerWidth`.
- The screenshot tool has been observed rendering captures doubled
  side-by-side. If that happens, say so and verify structurally.
- Prior decisions, with what each costs if wrong, are in
  `docs/superpowers/plans/2026-09-23-purser-v2-rulings.md`.
