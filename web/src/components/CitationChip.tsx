// The manual arrives as paper, not another chat bubble: this is the "paper
// extract" from the approved mockup (see docs/design/purser-v2-mockup.html,
// the `.paper` block) -- highest elevation in the app, gold-edged, a dashed
// rule under its label because it reads as a page torn out of something.
//
// `citation.blocks` is rendered via <ManualBlocks> (Task 10) for a document
// read, not a second line-by-line renderer. `citation.text` -- the
// byte-exact verbatim splice that is this whole architecture's audit trail
// -- is never touched here, never trimmed, and stays available unmodified
// for the page drawer (PageDrawer.tsx) to show as the authoritative quote.
// If `text` and `blocks` ever disagree about the words, `text` is the one
// that's right; `blocks` is only how this card draws it.
//
// (Filename kept as earlier tasks named it; the component itself is the
// paper card per the binding design plan, not the brief's original small
// chip sketch.)
import type { Citation } from "../api/types";
import { ManualBlocks } from "./ManualBlocks";

interface Props {
  citation: Citation;
  onOpen: (c: Citation) => void;
}

export function CitationChip({ citation, onOpen }: Props) {
  return (
    <button
      type="button"
      className="paper"
      onClick={() => onOpen(citation)}
      aria-label={`Open ${citation.label} in the manual`}
    >
      <div className="paper-head">
        {/* citation.label is the manual's own nomenclature (e.g. "PART FOUR
            §4.4 p.46"), reproduced verbatim -- never restyled or re-cased. */}
        <span className="paper-label">{citation.label}</span>
        <span className="paper-open" aria-hidden="true">
          ⤢
        </span>
      </div>
      <div className="paper-body">
        <ManualBlocks blocks={citation.blocks} />
      </div>
      {/* The revision stamp is safety-critical, not metadata: a superseded
          procedure shown as current is the failure this whole design
          exists to prevent. */}
      <p className="paper-rev">{citation.revision ?? "Revision not stated"}</p>
    </button>
  );
}
