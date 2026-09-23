import type { CSSProperties, ReactNode } from "react";
import type { Block } from "../api/types";
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
export function ManualBlocks({ blocks, idPrefix = "", collapsed, onToggle, hidden }: Props) {
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

  (blocks ?? []).forEach((block, i) => {
    if (hidden?.has(i)) return;
    const depth = block.depth ?? 0;
    closeTo(depth);
    openTo(depth, i);
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
  const text = displayManualText(block.text);
  const content = toggle ? (
    <button type="button" className="m-h-toggle" aria-expanded={toggle.expanded} onClick={toggle.onClick}>
      <span>{text}</span>
      <i aria-hidden="true" />
    </button>
  ) : (
    text
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

function ManualBlock({ block }: { block: Block }) {
  const text = displayManualText(block.text);

  switch (block.kind) {
    case "heading":
      // Headings are drawn by <Heading> as the head of their section.
      return <Heading block={block} toggle={null} />;

    case "subheading":
      return <h5 className="m-sh">{text}</h5>;

    case "para":
      return <p className="m-p">{text}</p>;

    case "bullet": {
      // The parser has already stripped the bullet glyph from `text` --
      // the marker below is drawn by this renderer, not the manual's own
      // (often inconsistent, sometimes PUA-glyph) character.
      const style = { "--lv": block.level } as CSSProperties;
      return (
        <div className="m-li" style={style}>
          <i aria-hidden="true" />
          <span>{text}</span>
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
          <span>{m ? m[2] : text}</span>
        </div>
      );
    }

    case "note":
      return <div className={noteTone(text)}>{text}</div>;

    case "caption":
      return <div className="m-cap">{text}</div>;

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
