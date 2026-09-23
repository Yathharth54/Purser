import type { CSSProperties } from "react";
import type { Block } from "../api/types";
import { displayManualText } from "../lib/manualText";

interface Props {
  blocks: Block[];
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
 * Every block's `text` is verbatim from the server except where the parser
 * already rejoined a hard-wrapped line (see `Block` in api/types.ts). It is
 * passed through `displayManualText()` here -- and only here -- so PUA
 * glyphs the source PDF's embedded symbol fonts left behind render as the
 * bullet/square they were meant to be, not a tofu box. See
 * web/src/lib/manualText.ts's header for why this must never move upstream.
 */
export function ManualBlocks({ blocks }: Props) {
  return (
    <div className="manual-blocks">
      {(blocks ?? []).map((block, i) => (
        <ManualBlock key={i} block={block} />
      ))}
    </div>
  );
}

function ManualBlock({ block }: { block: Block }) {
  const text = displayManualText(block.text);

  switch (block.kind) {
    case "heading":
      return <h4 className="m-h">{text}</h4>;

    case "subheading":
      return <h5 className="m-sh">{text}</h5>;

    case "para":
      return <p className="m-p">{text}</p>;

    case "step":
      return <p className="m-p m-step">{text}</p>;

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

    case "note":
      return <div className="m-note">{text}</div>;

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
