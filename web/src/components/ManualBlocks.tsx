import { useState, type CSSProperties, type ReactNode } from "react";
import type { Block } from "../api/types";
import { splitHeading, titleCase } from "../lib/headingCase";
import { displayManualText } from "../lib/manualText";

interface Props {
  blocks: Block[];
  /** Collapsing (the section reader only). A heading's id is
   * `${idPrefix}-${index}`; when `onToggle` is absent, headings are static. */
  idPrefix?: string;
  collapsed?: ReadonlySet<string>;
  onToggle?: (id: string) => void;
  /** Indices of blocks a collapsed heading hides -- possibly a heading on an
   * earlier page, which is why the caller computes this, not this component. */
  hidden?: ReadonlySet<number>;
  /** Contents entries become links to their page (the section reader only);
   *  without this they are a plain list, as in a citation card. */
  onJumpToPage?: (pageInSection: number) => void;
}

/**
 * Renders parsed manual `Block`s as a document, instead of the line-by-line
 * monospace dump that made the manual unreadable before Tasks 6/7 (parsing)
 * and this task (rendering) existed.
 *
 * One component, used both for a short range inside the citation "paper"
 * card (Task 11) and for whole pages in sequence in the section reader
 * (Task 12) -- it owns no outer card chrome, margin-collapsing assumptions,
 * or ambient text color of its own, so either caller can drop it in
 * without forking it. A caller that wants the manual's own paper voice
 * (`--paper-ink`) sets that as the `color` on its own wrapper; a caller
 * that renders on the app's normal background gets `--text` for free from
 * `body`.
 *
 * Sections: the blocks arrive flat, each with the `depth` of the headings
 * enclosing it. A heading at depth d opens a `.m-sec` whose body holds the
 * following blocks deeper than d, so a section reads as one unit. When a
 * page opens inside sections begun on an earlier page (first block deeper
 * than 0), matching `.m-sec-cont` wrappers keep their rules running across
 * the page break.
 *
 * Every block's `text` is verbatim from the server except where the parser
 * already rejoined a hard-wrapped line (see `Block` in api/types.ts). It is
 * passed through `displayManualText()` here -- and only here -- so PUA
 * glyphs the source PDF's embedded symbol fonts left behind render as the
 * bullet/square they were meant to be, not a tofu box. See
 * web/src/lib/manualText.ts's header for why this must never move upstream.
 */
export function ManualBlocks({ blocks, idPrefix = "", collapsed, onToggle, hidden, onJumpToPage }: Props) {
  interface Open {
    depth: number;
    heading: ReactNode | null; // null: continues a section begun on an earlier page
    children: ReactNode[];
    key: string;
  }
  const root: Open = { depth: -1, heading: null, children: [], key: "root" };
  const stack: Open[] = [root];
  const top = () => stack[stack.length - 1]!;

  // Close every open section at depth >= d, attaching each to its parent.
  function closeTo(d: number) {
    while (stack.length > 1 && top().depth >= d) {
      const s = stack.pop()!;
      top().children.push(
        <div key={s.key} className={s.heading ? "m-sec" : "m-sec m-sec-cont"} data-depth={s.depth}>
          {s.heading}
          <div className="m-sec-body">{s.children}</div>
        </div>,
      );
    }
  }
  // Open continuation sections until the innermost open one is at depth d - 1.
  function openTo(d: number, i: number) {
    while (top().depth < d - 1) {
      stack.push({ depth: top().depth + 1, heading: null, children: [], key: `cont-${i}-${top().depth}` });
    }
  }

  // Consecutive contents entries share one card; the array is filled in place
  // until something else is drawn, before React ever renders the card.
  let tocRun: Block[] | null = null;

  const list = blocks ?? [];
  list.forEach((block, i) => {
    if (hidden?.has(i)) return;
    // The card's own title replaces the manual's "TABLE OF CONTENTS" label.
    if (block.kind === "subheading" && list[i + 1]?.kind === "toc" && /contents/i.test(block.text)) return;
    const depth = block.depth ?? 0;
    closeTo(depth);
    openTo(depth, i);
    if (block.kind === "toc") {
      if (!tocRun) {
        tocRun = [];
        top().children.push(<TocCard key={`toc-${i}`} entries={tocRun} onJump={onJumpToPage} />);
      }
      tocRun.push(block);
      return;
    }
    tocRun = null;
    if (block.kind === "heading") {
      const id = `${idPrefix}-${i}`;
      const toggle = onToggle ? { expanded: !collapsed?.has(id), onClick: () => onToggle(id) } : null;
      stack.push({ depth, heading: <Heading block={block} toggle={toggle} />, children: [], key: `h-${i}` });
    } else {
      top().children.push(<ManualBlock key={i} block={block} />);
    }
  });
  closeTo(0);

  return <div className="manual-blocks">{root.children}</div>;
}

function Heading({
  block,
  toggle,
}: {
  block: Block;
  toggle: { expanded: boolean; onClick: () => void } | null;
}) {
  // The number hangs in its own column; the title is recased for display only.
  const { number, title } = splitHeading(displayManualText(block.text));
  const label = (
    <>
      {number && <span className="m-h-num">{number}</span>}
      <span className="m-h-title">{title}</span>
    </>
  );
  const content = toggle ? (
    <button type="button" className="m-h-toggle" aria-expanded={toggle.expanded} onClick={toggle.onClick}>
      {label}
      <i aria-hidden="true" />
    </button>
  ) : (
    <span className="m-h-row">{label}</span>
  );
  // Level from the manual's own numbering: "1." is 1, "1.6" is 2, "1.46.4" is 3.
  if (block.level >= 3) return <h5 className="m-h m-h3">{content}</h5>;
  if (block.level === 2) return <h4 className="m-h m-h2">{content}</h4>;
  return <h3 className="m-h">{content}</h3>;
}

// The label is part of the verbatim text ("CAUTION: ..."), so tone is read
// from it rather than carried as a separate field that could disagree.
function noteTone(text: string): string {
  if (/^warning\b/i.test(text)) return "m-note m-note-warning";
  if (/^caution\b/i.test(text)) return "m-note m-note-caution";
  return "m-note";
}

const STEP_NUMBER = /^(\d+(?:\.\d+)*\.?)\s+([\s\S]*)$/;

// A short line that only introduces what follows ("Seating:", "Handling
// Procedure:"): a lead-in label, not a paragraph. Capitalised, a few words,
// ending in the colon.
const LEAD_IN = /^[A-Z][^.:;]{0,44}:$/;

/** Text with the manual's fill-in blanks ("Mera naam ______ hai") drawn as a
 *  blank line to fill, rather than a run of underscores. */
function withBlanks(text: string): ReactNode {
  const parts = text.split(/_{3,}/);
  if (parts.length === 1) return text;
  return parts.flatMap((part, i) =>
    i === 0 ? [part] : [<span key={i} className="m-blank" role="img" aria-label="blank to fill in" />, part],
  );
}

function TocCard({ entries, onJump }: { entries: Block[]; onJump?: (page: number) => void }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="m-toc">
      <button type="button" className="m-toc-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="m-toc-title">In this section</span>
        <span className="m-toc-count">
          {entries.length} {entries.length === 1 ? "topic" : "topics"}
        </span>
        <i aria-hidden="true" />
      </button>
      {open && (
        <ul className="m-toc-list">
          {entries.map((e, i) => {
            const style = { "--lv": Math.max(0, e.level - 1) } as CSSProperties;
            const inner = (
              <>
                <span className="m-toc-num">{e.number ?? ""}</span>
                <span className="m-toc-text">{titleCase(displayManualText(e.text))}</span>
                {e.page != null && <span className="m-toc-page">p. {e.page}</span>}
              </>
            );
            return (
              <li key={i} style={style}>
                {onJump && e.page != null ? (
                  <button type="button" className="m-toc-row" onClick={() => onJump(e.page!)}>
                    {inner}
                    <i aria-hidden="true" />
                  </button>
                ) : (
                  <div className="m-toc-row">{inner}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ManualBlock({ block }: { block: Block }) {
  const text = displayManualText(block.text);

  switch (block.kind) {
    case "heading":
      // Headings are drawn by <Heading> as the head of their section.
      return <Heading block={block} toggle={null} />;

    case "subheading":
      return <h5 className="m-sh">{text}</h5>;

    case "para":
      if (LEAD_IN.test(text) && text.split(/\s+/).length <= 6) return <p className="m-label">{text}</p>;
      return <p className="m-p">{withBlanks(text)}</p>;

    case "bullet": {
      // The parser has already stripped the bullet glyph from `text` --
      // the marker below is drawn by this renderer, not the manual's own
      // (often inconsistent, sometimes PUA-glyph) character.
      const style = { "--lv": block.level } as CSSProperties;
      return (
        <div className={block.level > 0 ? "m-li m-li-sub" : "m-li"} style={style}>
          <i aria-hidden="true" />
          <span>{withBlanks(text)}</span>
        </div>
      );
    }

    case "step": {
      // The number stays the manual's own; it is only hung in its own column.
      const style = { "--lv": block.level } as CSSProperties;
      const m = STEP_NUMBER.exec(text);
      return (
        <div className="m-step" style={style}>
          <b>{m ? m[1] : ""}</b>
          <span>{withBlanks(m ? m[2]! : text)}</span>
        </div>
      );
    }

    case "note":
      return <div className={noteTone(text)}>{withBlanks(text)}</div>;

    case "caption":
      return <div className="m-cap">{text}</div>;

    case "toc":
      // Drawn by <ManualBlocks> as rows of a <TocCard>.
      return null;

    case "table":
      // Verbatim, monospace, never reflowed: a two-column safety table's
      // column gaps are the only thing pairing a condition to the action
      // it requires. `overflow-x: auto` (in styles.css) lets a wide table
      // scroll horizontally on a 360px phone instead of clipping or
      // collapsing its whitespace.
      return (
        <div className="m-tbl">
          <pre>{text}</pre>
        </div>
      );

    default: {
      // Exhaustiveness check: Block.kind is a closed union, so this branch
      // is unreachable for valid data. If the API ever adds a kind this
      // component doesn't know about yet, fail loudly in dev rather than
      // silently dropping content a reader needed.
      const exhaustive: never = block.kind;
      console.warn(`ManualBlocks: unknown block kind ${String(exhaustive)}`);
      return null;
    }
  }
}
