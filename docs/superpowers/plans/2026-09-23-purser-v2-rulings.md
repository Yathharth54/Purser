# Purser v2 — decisions taken during execution

Every judgement call made while executing `2026-09-23-purser-v2.md` without stopping to
ask, with what it costs if it was wrong. Preserved here because the scratch workspace
these were recorded in is deleted once the branch is finished, and a decision that dies
with its notes was a decision made in secret.

Branch: `feat/purser-v2` (31 commits from `489d5cb`).

---

Ruling: work on a branch in the primary checkout, not a git worktree — every

Task 1: Ruling: the reviewer's Important finding is REAL but its diagnosis is
  WRONG, and the correct fix differs from the one it proposed. Controller-verified
  against data/manual.sqlite:
    InterGlobe 1,217 | ifly.SEP 1,228 | NOT A CONTROLLED COPY 1,226
    SEP MANUAL 1,223 | Issue..Revision 1,200 | Page N of M 1,200 | Effective 1,222
    Page-of-M matching WITHOUT Effective:  0
    Effective matching WITHOUT Page-of-M: 22   <-- the plan's "x22"
  So `22` is not a dropped digit (reviewer claimed "off by 55x"). It is the exact
  MARGINAL contribution of the `Effective` alternative — the 22 footer lines of the
  form "GOTC 1 of 2 ... Effective 18 May 2023" that `Page N of M` does not catch.
  The comment is misleading because it prints a marginal count in a column of raw
  counts, not because the figure is wrong.
  Consequence both the implementer and the reviewer got backwards: they concluded
  `Page N of M` is load-bearing and `Effective` is rare. It is the other way round —
  `Page N of M` has ZERO unique hits on this corpus and is pure insurance, while
  `Effective` is the only pattern catching those 22 lines. A future maintainer
  trusting the current comment would delete the wrong alternative.
  Decision: correct the comment to give total AND marginal per pattern and say which
  is which; correct InterGlobe 1,229 -> 1,217; state that `Page N of M` has no unique
  hits today and is kept deliberately. Also correct the same two figures in the plan's
  own measurement table, which is where the error originated.
  Cost if wrong: a comment and a doc table are inaccurate; zero runtime effect —
  the aggregate invariant test (6,100 / 24,276) passes either way and is the real gate.

Task 2: Ruling: the plan's rebuild command `.venv/bin/python -m purser_ingest.cli
  ingest ...` is a SILENT NO-OP and is a genuine plan defect, not implementer error.
  Controller-verified: src/purser_ingest/cli.py has no `if __name__ == "__main__"`
  guard, so `python -m purser_ingest.cli --help` imports the module, prints nothing
  and exits 0 — indistinguishable from success. The packaged console script
  `purser = "purser_ingest.cli:app"` (pyproject.toml:30) is the real entrypoint, and
  README.md:30/85 already documents it correctly. Decided: correct the plan's two
  occurrences to `.venv/bin/purser ingest` (done; task-5-brief.md regenerated) and do
  NOT add a `__main__` guard — a second supported invocation of the same CLI buys
  nothing and the README already names the right one. The implementer independently
  reached the same workaround.
  Cost if wrong: none to runtime; if a future reader prefers `-m`, they add two lines.

Task 2: Ruling: the transient `TypeError` (None pdf_page from bm25) in
  test_aviation_question_not_covered_by_manual_is_declined is PRE-EXISTING and not
  caused by this diff — it is the known flaky live-LLM pydantic_ai tool-call fault,
  already guarded, carried over from before this plan. Passed in isolation, on replay
  against the rebuilt index, and on a clean full-suite rerun (215/215). Not a blocker.
  Cost if wrong: a real regression hides behind a known flake — mitigated because
  Task 14 re-runs the whole suite end to end against a rebuilt container.

Task 3: Ruling: the Important finding (stale wire-format docs) is REAL and the fix direction
  is to update the DOCS, not the code. Controller-verified the format genuinely changed:
    before a554ea3  tools.py:75  f"{i}| {ln}"      (separator space)
    after  c3da985  tools.py:77  f"{i}|{text}"     (no space)
  and two places still describe the old shape: src/purser_agent/prompts.py (HOW TO CITE
  block, 'formatted "12| text"') and src/purser_core/models.py:76 (field comment
  '"12| CABIN CREW SHALL..."'). prompts.py is what the live model is told, so the drift is
  in exactly the domain this task changed — line-number citation format.
  Chose docs-follow-code over restoring the space because the brief mandates f"{i}|{text}"
  and because manual lines carry semantically meaningful leading indentation (Task 6's block
  parser keys off indent level); a separator space prepends a phantom column to every line.
  Cost if wrong: the prompt's worked example reads one character off from the wire format —
  cosmetic, and the model reads the real strings regardless.

Task 4: Ruling: keep the orphaned working-tree changes and re-dispatch a fresh
  implementer to verify, complete and commit them, rather than discarding and starting
  clean. Why: the implementation is nine lines and visibly matches the brief's Step 3
  prose (edge-only walk, contiguous slice, None when the window closes); discarding it
  buys nothing because the final diff is reviewed either way. The cost is that genuine
  TDD RED evidence cannot be produced by an implementer who inherits working code, so
  the re-dispatch requires it be RECONSTRUCTED by reverting the implementation, watching
  the tests fail, and restoring -- and the report must state the work was inherited.
  Cost if wrong: an inherited line escapes first-principles scrutiny; mitigated by the
  mutation check, the call-site audit and the task review all still running.

Task 4: Ruling: concern 3 is a REAL PLAN DEFECT. The brief/plan mandate
  `assert "escape slides" in cite.text` for pdf_page 600. Controller-verified against
  data/manual.sqlite: "escape slide" does NOT appear on page 600; "life raft" does;
  "ditching" and "slide" do not appear either. Page 600 is a life-raft procedure. The
  implementer's substitution of "life raft" is correct and stands. The plan text is wrong
  and must be corrected so a later re-run of this brief does not reintroduce a test that
  fails for a reason unrelated to the code under test.
  Cost if wrong: none — the assertion's job is to prove real content survived the trim,
  and "life raft" does that on this page.

Task 4: Ruling: concern 2 is a REAL PLAN DEFECT, and the fix is better than the one the
  implementer applied. Controller-verified: pdf_page 600 has chrome at [0,5,6,9,45]; the
  edge-trimmed window is 12..43; there is NO chrome and NO blank line strictly inside it.
  So the plan's mandated Step 5 mutation ("also remove interior chrome") genuinely cannot
  turn test_interior_furniture_is_left_alone red on that page — the mutation is a no-op
  and the mandated check is toothless.
  BUT the premise is not impossible, only mis-paged: 40 pages DO carry chrome strictly
  inside their trimmed window — e.g. pdf 15 (window 0..46, interior chrome at [5,6]),
  pdf 9 (window 8..37, interior chrome at [16,19,22,25,28,31]). Decided: move
  test_interior_furniture_is_left_alone onto such a page so the mandated mutation becomes
  a real guard, and keep the implementer's substitute mutation as an additional check.
  Cost if wrong: the test exercises a different page than the plan named; the property
  asserted (contiguity) is identical and is now actually falsifiable.

Task 4: Ruling: all 3 Important findings are REAL and enter the fix loop. Controller
  re-verified the new one directly:
    page 600 trailing chrome [45] = '   PART FOUR Section 4.4   Page 34 of 80   Effective 18 May 2023'
    "Page 1 of" appears NOWHERE on page 600.
    With the trailing (hi) trim DISABLED, the text still ends on that footer line and
    `"Page 1 of" not in last_line` STILL PASSES, as does `"life raft" in text`.
  So the entire trailing-edge walk currently has no test that would fail if it were
  deleted. Same root cause as the "escape slides" defect — a brief literal authored
  against a different page — but this one fails SILENTLY rather than loudly.
  Cost if wrong: none; these are strictly-stronger assertions over the same behaviour.

Task 5: Ruling: `Page.chrome` is populated ONLY on the SQLite read path, so the ingest-time
  in-memory Page objects carry `chrome == []` and Task 5's `content_lines()` change is a
  silent no-op. Controller-verified:
    - `chrome_line_indices` is called in exactly ONE place: index_build.py:57, inline in the
      INSERT (`json.dumps(chrome_line_indices(p.lines))`). It is never assigned onto a Page.
    - corpus.py:21 (`data["chrome"] = json.loads(...)`) is the only thing that ever sets it.
    - cli.py::ingest passes the SAME `pages` list from assemble() to both build_index() and
      build_vectors(); assemble() constructs Page without chrome, so it defaults to [].
  The implementer proved the consequence empirically: the rebuilt vectors.npy was BYTE-FOR-BYTE
  identical to the committed blob, and on pdf_page 1 (real chrome [0,2,8]) embedding page.text
  vs content_lines()-with-empty-chrome gave bit-identical vectors, while applying the REAL
  chrome gave cosine 0.7957 against the original. Large, real difference — never exercised.
  Decided: EXPAND TASK 5's SCOPE to populate `Page.chrome` at construction in
  src/purser_ingest/assemble.py, so it is an invariant of a constructed Page rather than
  something only a DB round-trip provides, and have index_build.py write `p.chrome` instead of
  recomputing it. Then run Steps 3-6 for real.
  Why this and not a fix inside build_vectors: computing chrome in two places invites the two
  copies to drift, and the property "a Page knows its own furniture" should not depend on which
  side of a serialization boundary the object came from. Blast radius is limited — every other
  consumer (tools.py, citations.py, and Tasks 6/7) reads Pages from the corpus, where chrome was
  already correct, so this changes only the ingest-time path.
  Note: the committed data/manual.sqlite is NOT wrong — index_build computed chrome directly at
  write time, so the stored column has always been correct. Only the in-memory object was empty.
  Cost if wrong: assemble.py is on every ingest path; a mistake there corrupts the chrome column
  for the whole corpus. Mitigated by the existing corpus-wide invariant test (6,100 / 24,276),
  which would go red immediately, plus the task review.

Task 5: Ruling: the gate wording has a hole — it names branches for recall@8 <95% and
  ==100%, but the measurement landed at 97.5%, which neither covers. The implementer
  resolved it as REVERT and that is correct on both the letter (the keep branch requires
  100%) and the spirit (MRR regressed too). Decided: the resolution stands, and the plan's
  gate text is corrected to "recall@8 < 100% -> revert" so a re-run has no gap.
  Cost if wrong: none — no branch of any reading authorized keeping this.

Task 5: CONTROLLER CORRECTION — the reviewer caught an error in MY OWN framing and is right.
  I told it tests/test_chrome.py::test_corpus_wide_counts_match_the_measurement was the canary
  proving the two chrome computations agreed. It is not. Verified: that test does
  `select pdf_page, lines from pages` and recomputes `chrome_line_indices(lines)` fresh — it
  never reads the persisted `chrome` column, so it would pass identically in the pre-fix
  broken state. The actual agreement evidence was the implementer's ad hoc row-by-row script
  (1226/1226, 6,100 indices, 0 mismatches), plus the structural argument that
  chrome_line_indices is pure and both call sites received the identical `lines` object.

Task 5: Ruling: corrected the plan's gate wording from "recall@8 below 95%" to "below 100%".
  The original left 95-99.9% uncovered and the real measurement landed at 97.5%, squarely in
  the gap. No branch of any reading authorized keeping, so the action taken was right; this
  only closes the hole for a re-run. Cost if wrong: none.

Ruling: proceed through Tasks 6-13, none of which need a model call (parser, API shape,
  frontend). Treat the 4 live-LLM failures as a known environmental failure and re-baseline
  the pass count on the offline suite. Task 14's live step is deferred, not skipped, and
  will be surfaced to the user at the finish.
  Cost if wrong: a genuine agent regression hides behind the credit failures — mitigated
  because those 4 tests are the only ones that call a model, and Task 14 re-runs them.

Task 6: Ruling: concern 1 is ANOTHER PLAN DEFECT of the same class as Task 4's "escape
  slides" literal, and the implementer's fix is correct. The brief's
  test_no_content_is_lost_anywhere_in_the_corpus builds its probe as
  `" ".join(line.split()[:3])`. When a bullet glyph stands alone as a token, the glyph
  becomes word #1 of the probe — but the parser strips it from bullet text by design
  (test_a_wrapped_bullet_is_rejoined_into_one_sentence asserts exactly that), so the probe
  can never match. It failed on pages 552 and 600 for that reason, not because content was
  lost; the implementer confirmed the prose is present verbatim in every case.
  Shipped fix: `words = [w for w in line.split() if w.strip(BULLET_GLYPHS)]` — filters
  glyph-only tokens before building the probe. Verified this does NOT weaken the assertion:
  it still requires the first three REAL words of every content line to appear in the
  output; it only stops counting a glyph as a word. blocks.py, the 70th-percentile
  threshold and every regex were left untouched.
  Cost if wrong: the no-content-lost guard would miss a parser that dropped a bullet glyph
  and nothing else — which is the intended behaviour anyway.

Task 6: Ruling: the table-runaway finding is REAL, serious, and a PLAN DEFECT inherited
  from the brief's own Step 4 code. Controller reproduced it directly:
    pdf 594 -> 2 blocks total: [caption, table(25 rows)]
  Only rows 14-15 are a genuine table ("SIGNAL FOR BRACE | COMMANDS"). Lines 16-38 —
  the whole "Planned Emergency (Ditching)" narrative and its nine-step procedure — are
  swallowed into the table block, rendered monospace and unreflowed. That is precisely
  the "reads like a scanned document" failure Task 6 exists to remove, reproduced inside
  a table block, on one of the four pages the brief itself cites as validating the parser.
  Cause: once in_table, the ONLY terminators are a fresh `Table X.Y` caption or a
  _NUM_HEAD match at indent <= 2. Everything else is appended verbatim to end of page.

Task 6: CONTROLLER CORRECTION — my own fix #2 is INERT and I was wrong to call it insurance.
  I ruled that flooring `full` at 0 closed the over-joining risk. It does not. The
  re-reviewer showed `prev_len` is never negative (always len(...) or reset to 0), so
  `prev_len >= full` is vacuously true for ANY full <= 0, floored or not — and proved it by
  diffing floored vs unfloored output across all 1,226 pages: 0 differences. It also
  measured that the raw unfloored `full` is non-negative on every page in the corpus today,
  so the trigger never fires either.
  Decision: KEEP the floor (harmless, and it documents the intent) but record that the
  over-joining gap is NOT closed. A real fix needs a positive minimum width, which is a
  design change with genuine risk and no observed trigger — not something to slip into a
  fix round. Carrying it to the final review instead.
  Cost of leaving it: if a future corpus has a page of very short lines, every line there
  joins into one fabricated paragraph. No page in this manual does.

Task 7: Ruling: Important #1 is REAL and is a PLAN DEFECT — the FOURTH of this exact class
  in this plan (after "escape slides", "Page 1 of", and the bullet-glyph probe). My brief
  specifies test_the_eight_empty_pages_are_marked_not_dropped against section "4.2".
  Controller-verified where the 8 zero-block pages actually live:
      pdf 314 -> 3.5      pdf 338 -> 3.5      pdf 484 -> 3.13
      pdf 1179, 1181, 1182, 1185, 1188 -> section None (in NO section at all)
  None are in 4.2 or 4.4 — the only two sections any test in this diff exercises. So the
  test compares False == False on every page and would pass identically with `empty`
  hardcoded to False. The implementation IS correct (verified: 3.5 returns 104 pages with
  empty=True on 314 and 338; 3.13 flags 484) — this is purely a vacuous test.
  Decided: add a directed test against 3.5 or 3.13 asserting at least one empty is True AND
  that page_in_section sequencing is preserved around it, and fix the section in the plan.
  Cost if wrong: none; strictly a stronger assertion over behaviour already shown correct.
  NOTE also worth recording: 5 of the 8 empty pages carry section=None, so they can never
  appear in a section reader at all. Only 3 are reachable through reading_pages().

Task 7: Ruling: Important #2 is REAL. The bounds-clamping logic in
  src/purser_api/routers/manual.py:166-169 is a verbatim copy of PurserTools.read_section
  (src/purser_core/tools.py:139-146), down to the comment explaining the subtle "five
  sections open at page_in_section 3, not 1" invariant. That clamp IS the mechanism the
  80-page requirement depends on, so a fix applied to one copy and not the other silently
  reintroduces exactly the capped-section bug this task exists to remove. Decided: extract
  one shared helper in purser_core and call it from both. Cost if wrong: one more small
  function; the drift risk it removes is the specific bug class already burned us once.

Task 8: Ruling: concern 1 (old token names dangle until Task 9) is EXPECTED sequencing,
  not a defect. tokens.css is a mandated full rewrite; --ink, --halo, --caution,
  --font-ui, --font-mono and --text-body-* are still referenced by the placeholder
  App.tsx/styles.css/Chat/PageDrawer/TocBrowser/CitationChip, which Task 9 rewrites.
  The app is visually broken between Task 8 and Task 9 — acceptable inside a branch that
  is never merged mid-phase. Cost if wrong: none, provided Task 9 lands; Task 14's
  end-to-end browser verification is the backstop that would catch it if it did not.

Task 8: Ruling: the `--inset` divergence is REAL. Verified every inset shadow in the
  mockup is either rgba(0,0,0,...) or rgba(255,255,255,...) — there is no warm/brown tint
  anywhere, in EITHER theme. The shipped day value `inset 0 1px 3px rgba(60,48,26,.18)`
  is synthesized. The mockup's day recessed shadows are rgba(0,0,0,.18)/.2/.22. Fix to a
  black-based value. This matters because --inset is what Tasks 9-12 will use on the
  composer field, the day chip, the segmented track and manual tables — four real surfaces
  that would all render warmer and lower-contrast than the approved design.
  Cost if wrong: a slightly different recessed shadow; trivially reversible.

Task 8: Ruling: the dropped global reset is REAL and foundational. Verified
  `grep -rn box-sizing web/src web/index.html` returns NOTHING, while the mockup carries
  `*,*::before,*::after{box-sizing:border-box}` and `body{margin:0}`. The old tokens.css
  had both and the rewrite dropped them with no replacement. Every later task is written
  against the mockup and will assume border-box math; content-box silently diverges on
  every element with padding and a set width. Restore both in tokens.css.
  Cost if wrong: none — border-box is what the mockup and all five consumers assume.

Task 8: Ruling: the cascade collision is REAL and is a LIVE BUG on this commit, not a
  hypothesis. web/src/styles.css:17-28 still declares its own :root and
  :root[data-theme="cabin"] blocks redefining --bg and --rule. styles.css loads AFTER
  tokens.css (main.tsx imports tokens, then App.tsx pulls styles.css), equal specificity,
  so the stale block WINS. And its cabin value is `--bg: var(--ink)` where --ink no longer
  exists, so --bg is invalid and body background falls back to transparent instead of navy.
  --fg: var(--ink) and --surface: var(--deck) are equally dead.
  Task 8 CANNOT fix this — styles.css is Task 9's file. Decided: carry it into Task 9's
  dispatch as an explicit requirement to DELETE that block rather than layer on top of it.
  Cost if wrong: the shadowing survives Task 9 and the cabin theme stays broken — which
  Task 14's browser verification would catch, but late.

Task 8: Ruling: OVERRIDING the mockup on one accessibility point. Day-mode --dim on
  --sunken measures 4.36:1, below the 4.5:1 AA floor for normal text, and --sunken is the
  surface --dim text actually sits on (.daychip, .think, .field are all sunken+dim, all
  <=14.5px). The value is inherited byte-for-byte from the mockup, so it is not the
  implementer's doing. I am ruling the floor wins here: "visually accessible" is a stated
  quality requirement, this is a safety manual read on a phone, and clearing 4.5:1 needs
  only a small darkening of --dim that preserves the design intent. The mockup governs
  appearance, not accessibility minimums.
  Cost if wrong: day-mode secondary text is a shade darker than the mockup. Visible only
  side by side, and in the direction of legibility.

Task 9: Ruling: concern 1 — my brief says the chrome should sit "above scrolling content so
  it blurs underneath", implying a sticky overlay. The mockup does NOT do that. Verified:
  its `.bar` is `position:relative; z-index:6; background:var(--chrome)` with
  `backdrop-filter:blur(20px)`, sitting as a non-overlapping flex sibling around the scroll
  area. The implementer followed the mockup and flagged the discrepancy rather than
  silently picking one — exactly right. The tie-break stands: the mockup is what the owner
  approved after rejecting two attempts, and restructuring Chat.tsx's scroll container into
  an overlay architecture is both outside this task's ownership and a deviation from the
  signed-off design. Accepted as shipped; my brief's prose was aspirational.
  Cost if wrong: the frost reads as a solid bar rather than a blur over moving content — a
  refinement available later without touching the token system or the component tree.

Task 9: Ruling: the Important is REAL. The segmented control ships role="tablist"/role="tab"
  with correct aria-selected/aria-controls/aria-labelledby, but WITHOUT the interaction
  model those roles promise: no roving tabindex and no arrow-key handler (grep for
  tabIndex/onKeyDown/ArrowLeft/ArrowRight in App.tsx returns zero hits). So Tab produces two
  separate stops instead of one, and a screen-reader user who hears "tab, 1 of 2" and
  reaches for the arrow keys gets nothing. That is precisely the "focusable but not correct"
  gap, and it matters here because this is operated one-handed by a working crew member.
  Contained fix: tabIndex + onKeyDown on the two existing buttons. Cost if wrong: none.

Task 10: Ruling: concern 2 (extending types.ts with Citation.blocks and ReadingPage beyond
  the brief's literal Step 1) is CORRECT and approved. api-contract.md already specifies
  both, and neither Task 11 nor Task 12 lists types.ts in its file scope — leaving it stale
  would have blocked them both. Exactly the right scope call to make and to disclose.

Task 10: Ruling: fix it now rather than defer. Controller validated the replacement against
  the corpus before dispatching, the same way the table-runaway rule was validated:
      ^Table\s+[\d.]+\s?[A-Z]{0,2}\d?\b.{0,40}$   (case-insensitive)
      tail cap 30 -> +21 gained, 0 false positives
      tail cap 40 -> +22 gained, 0 false positives   <- CHOSEN
      tail cap 50 -> +27 gained, 0 false positives
  Chose 40, the conservative option that still captures every consequential miss. The tail
  cap is what rejects a SENTENCE about a table — pdf 254's
  'Table 3.4C shows the crew responsible for checking the forward and aft galleys' has a
  68-character tail and is excluded at every cap tested. Being conservative here is
  deliberate: a false caption OPENS a spurious table, which is the runaway bug class Task 6
  already had to fix once.
  Cost if wrong: a line that merely mentions a table becomes a caption and opens a table
  block, swallowing following prose in monospace — visible immediately, and bounded by the
  indent-drop terminator Task 6 already added.

Task 10: Ruling: Important #1 (zero tests on the centrepiece component) is REAL and I am
  fixing it despite the reviewer not blocking on it. The brief only asked for live-API
  verification, so this is my omission, not the implementer's. But ManualBlocks is consumed
  by BOTH Task 11 and Task 12, and the two properties most likely to regress silently —
  table whitespace preservation and the bullet --lv nesting mechanism — are exactly the
  kind a render test pins cheaply. vitest is already wired (10/10 on client.test.ts).
  Cost if wrong: a few minutes of test-writing on a component that is the plan's whole point.

Task 10: Ruling: Important #2 (visual claims resting on a screenshot tool that renders every
  capture DOUBLED) — no action against Task 10. The reviewer closed the gap by a different
  route (direct mockup-CSS diffing) and found no defect. But the tool limitation is real and
  CARRIES INTO TASK 14, which must judge appearance for real. Recorded there.

Task 11: Ruling: the added `Turn.time` timestamp is ACCEPTED. The brief's Step 2 names the
  timestamp as part of the one grouped visual unit and the mockup renders one, so a field
  was required; it was disclosed explicitly rather than slipped in. Cost if wrong: one
  additive field.

Task 12: Ruling: concern 2 (rendering `revision` verbatim from the API, "Issue IX Revision
  00", rather than the mockup's demo string "Issue IX Rev 00") — APPROVED as shipped. The
  mockup wins on APPEARANCE; it does not get to overrule real data. Its demo text is a
  placeholder, and PageDrawer already renders the field verbatim. Cost if wrong: four
  characters of label text.

Task 12: Ruling: concern 3 (making the 11 part-transition contents rows non-interactive
  instead of clickable-but-stuck-on-"Loading…") — APPROVED. Those nodes carry no section id,
  so a tap could never resolve; a row that looks tappable and then hangs is a worse bug than
  the one the brief named. In scope, disclosed, correct.

Task 13: Ruling: concern 1 (the mockup has no drawer section at all) — ACCEPTED. Controller
  confirms there was no mockup-vs-brief conflict to resolve, only an absent reference, so
  building from the brief plus the established token language is correct.

Task 14: PARKED — Ruling: caption-less table continuation pages are a REAL and MATERIAL
  readability gap, but they are a SCOPE GAP, not a defect in what was specified, and I am
  not fixing them at the finish line.
  Controller investigated the two pages Task 14 flagged (§4.4 p.31 = pdf 597, p.80 = pdf 646)
  and found a NEW class, distinct from the three parser defects already fixed: NEITHER PAGE
  CARRIES A `Table X.Y` CAPTION AT ALL. They are continuation pages of a table whose caption
  sat on an earlier page. parse_blocks is per-page by contract — Task 7 calls it on SLICES —
  so it has no cross-page state and can never open a table there.
  Measured scope: 251 pages have a run of >=4 consecutive column-gap lines yet produce no
  table block; 229 of those carry no caption at all. That is 19% of the corpus. Longest runs
  reach 27 consecutive rows (pdf 1082, 634, 1086, 632).
  Why not fix now: closing it needs caption-LESS table detection — a brand-new heuristic, not
  an adjustment to an existing one — with real false-positive risk across 1,226 pages. The
  plan's parser spec keys tables off captions by design. Slipping a new detection heuristic
  into the final fix wave, which gets exactly one scoped re-review, is precisely the
  under-reviewed change that causes regressions. Nothing is lost or wrong today: the text is
  verbatim-correct, it simply reads as interleaved columns on those pages.
  Cost of parking: some multi-page tables stay hard to read. This is the single largest
  remaining readability item and is being surfaced to the user as the first follow-up.

Ruling: ACCEPTED the new devDependency (react-test-renderer + its types, both ^18.3.1).
  The dispatch suggested renderToStaticMarkup to avoid adding jsdom, and the implementer
  correctly reported that it CANNOT work: React's server renderer never runs effects, so it
  can never exercise TocBrowser's useEffect-driven fetchSection call — the exact thing B4
  exists to pin. react-test-renderer runs effects under act() without a browser DOM, matches
  the project's React 18.3 exactly, and is dev-only. Stopping to report the mismatch instead
  of writing a test that silently asserted nothing was the right instinct.
  Cost if wrong: react-test-renderer is deprecated in React 19, so a future React upgrade
  will need this one test moved to @testing-library/react. Dev-only, one file.

Ruling: C1's line numbers were off by 5 (834/880 vs actual 839/885) because B1's
  overflow-wrap insertions landed earlier in the same file. Selectors and content matched
  exactly, so applying was correct — this is the expected consequence of batching edits to
  one file, not a mismatch worth stopping for.

---

# Manual structure (feat/manual-structure) — decisions taken during execution

Plan: headings, tables across pages, sections in the reader. Every rule below
was measured against all 1,226 pages before it was adopted.

Ruling: headings are numbered lines whose title is >80% capitals, at ANY indent;
  lower-case numbered lines are a new `step` kind. The old test (trailing dot,
  indent <= 2) missed ~630 subsection headings and promoted ~200 steps to
  headings. Headings 444 -> 851.
  Cost if wrong: a numbered line in capitals inside a table closes the table.
  None of the guard pages do this; watch for it in new corpora.

Ruling: the handoff's running-minimum table edge (issue 1) ships ONLY together
  with the heading rule. Alone it produced runaways no guard page caught: once a
  table's body reaches column 0-2 the indent test can never fail again (pdf 299
  swallowed '1.6 3 POINT BRIEFING'; pdf 366 swallowed a Note and '3. ADVISORY').
  A heading now closes a table first. Table lines 1,946 -> 2,397 per page.

Ruling: a gap-less Note/Caution/Warning label at the table's left edge (indent <=
  edge + 2) closes the table. Restricted to the edge after eyeballing all 18
  affected pages: notes set inside a column (289, 814, 1144) sit well right of
  the edge and the table continues after them.
  Known miss: pdf 622's in-cell note sits in the LEFT column at the edge with an
  empty right cell -- indistinguishable, so the rest of that table interleaves.

Ruling: a table is carried onto the next page only when (a) the previous page in
  the section ended inside one AND (b) the new page's first content line is itself
  a row. Blind carry turned 56 pages -- prose pdf 182 among them -- into monospace.
  Confirmed carry: pdf 597 0 -> 52 table lines; 14 pages become all-table in the
  reader, each eyeballed as a genuine continuation.

Ruling: section structure is a flat `Block.depth` computed in purser_core, not a
  nested model. It carries across page breaks (with `ReadingPage.continues`) and
  serialises unchanged. Citations parse their slice with the carried table state,
  its left edge and the PAGE's wrap width, so a card draws the same structure the
  reader does; depth is rebased so the quote's shallowest block sits at 0, and the
  enclosing section is a display-only `Citation.context`. `Citation.text` is
  untouched.

Ruling: the reader flows sections across pages (page markers stay), steps heading
  size by level, hangs nested sections off a hairline rule, escalates Caution and
  Warning with their own AA tokens, and makes every heading collapsible --
  including across page breaks. Owner's choices, 2026-09-23. No outline this round.

Open (pre-existing, not introduced here): a wrapped line joins the block above
  only when that line reached the page's 70th-percentile width. Several notes miss
  by 1-7 characters (pdf 811 WARNING: 76 vs 77; 242, 414, 1033), so their second
  line renders as a separate paragraph outside the note. Fixing it changes joining
  corpus-wide and needs its own measurement pass.
