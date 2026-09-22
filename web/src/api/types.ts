/**
 * Types for the Purser API, per
 * .superpowers/sdd/2026-09-22-purser/api-contract.md (authoritative over the
 * task-17 brief, which predates the built backend).
 */

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

export interface PageText {
  pdf_page: number;
  part: string;
  section: string | null;
  section_title: string | null;
  page_in_section: number;
  numbered_lines: string[];
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
