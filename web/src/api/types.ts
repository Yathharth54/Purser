/**
 * Types for the Purser API, per
 * .superpowers/sdd/2026-09-22-purser/api-contract.md (authoritative over the
 * task-17 brief, which predates the built backend).
 */

/**
 * One structural unit of manual text, recovered from the text layer (Task
 * 6/7's parser).
 *
 * `text` is verbatim for every kind EXCEPT `para`, `bullet`, `step` and `note`,
 * where lines the PDF hard-wrapped are rejoined with a single space --
 * that restores the sentence the author wrote. `table` keeps its own
 * newlines and leading spaces, because its columns ARE the information --
 * never reflow it. `bullet`'s glyph has already been stripped server-side;
 * `step` is a numbered procedure step and keeps its number in `text`.
 * `level` is a heading's depth from its numbering ("1.6" is 2), or a
 * bullet's/step's nesting from its indent.
 *
 * Render every block's `text` through `displayManualText()`
 * (`web/src/lib/manualText.ts`) so PUA glyphs the source PDF's symbol
 * fonts left behind don't show up as tofu boxes.
 */
export interface Block {
  kind:
    | "heading"
    | "subheading"
    | "para"
    | "bullet"
    | "step"
    | "note"
    | "caption"
    | "table";
  level: number;
  text: string;
}

/**
 * A cited block of manual text.
 *
 * `text` is verbatim manual text spliced server-side, with leading
 * whitespace that carries meaning in procedure tables (column alignment
 * from `pdftotext -layout`). NEVER trim, normalise, or otherwise mutate it
 * -- render it as-is in a monospace face inside `white-space: pre-wrap`.
 *
 * `label` is prebuilt (e.g. "PART FOUR §4.4 p.46") -- render it, don't
 * rebuild it client-side.
 *
 * `blocks` is the SAME text, already parsed into `Block`s, for the nicer
 * default render via `<ManualBlocks>`. `text` stays the source of truth --
 * if the two ever disagree about the words, `text` is right. A resolved
 * citation's `blocks` is never empty.
 */
export interface Citation {
  pdf_page: number;
  part: string;
  section: string | null;
  section_title: string | null;
  page_in_section: number;
  revision: string | null;
  effective: string; // ISO date
  text: string;
  blocks: Block[];
  label: string;
}

export interface TocNode {
  part: string;
  section: string | null;
  title: string | null;
  pdf_page_from: number;
  pdf_page_to: number;
  pages: number;
}

/**
 * GET /api/section/{section} element -- one page of the manual, shaped for
 * a person reading it rather than for the agent (the agent's own citable
 * view of a page, numbered_lines and all, is server-side only -- nothing
 * on this client needs it).
 *
 * `empty` is true for the ~8 pages of the manual that carry no text after
 * de-chroming -- `blocks` is `[]` for those, and they're still returned in
 * position (not skipped), so page numbers stay aligned with the paper
 * manual a reader is cross-checking.
 */
export interface ReadingPage {
  pdf_page: number;
  page_in_section: number;
  section_total: number;
  section: string | null;
  section_title: string | null;
  revision: string | null;
  effective: string; // ISO date
  blocks: Block[];
  empty: boolean;
}

/** Names emitted on the `tool` SSE event -- one retrieval call each. */
export type ToolName = "search" | "toc" | "read_section" | "read_page" | "lookup_term";

/**
 * Retrieval progress, additive to the brief. Emitted once per tool call the
 * agent makes while answering. Render as transient progress ("reading 4.4
 * Evacuations"), replaced in place -- not appended to the transcript.
 */
export interface ToolEvent {
  name: ToolName;
  args: Record<string, unknown>;
}

/** GET /api/threads element. Threads are ordered most-recently-active first. */
export interface ThreadSummary {
  id: string;
  title: string | null;
  updated_at: string;
}

/** GET /api/threads/{id} element. */
export interface ThreadMessage {
  role: string;
  body: string;
  citations: Citation[];
}
