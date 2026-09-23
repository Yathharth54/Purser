// Per the design plan, a citation is not a small chip pill -- it is a ruled
// block rendered inline with the assistant's answer: the manual's own label,
// the verbatim spliced text (mono, pre-wrap, whitespace intact), and the
// revision stamp, all behind a single 3px --halo rule. Tapping anywhere on
// the block opens the real page image in the PageDrawer. This is the one
// place --halo is allowed to appear -- never on a button, link, heading, or
// focus ring.
//
// (Filename kept as the task-17/18 interface names it; the component itself
// supersedes the brief's small-button sketch per the binding design plan.)
import type { Citation } from "../api/types";
import { displayManualText } from "../lib/manualText";

interface Props {
  citation: Citation;
  onOpen: (c: Citation) => void;
}

export function CitationChip({ citation, onOpen }: Props) {
  return (
    <button
      type="button"
      className="citation"
      onClick={() => onOpen(citation)}
      aria-label={`Open ${citation.label} in the manual`}
    >
      {/* citation.label is the manual's own nomenclature (e.g. "PART FOUR
          §4.4 p.46"), reproduced verbatim -- never restyled or re-cased. */}
      <p className="citation-label">{citation.label}</p>
      {/* citation.text is verbatim, server-spliced manual text. Its leading
          whitespace is load-bearing (procedure-table column alignment from
          `pdftotext -layout`) -- never trim, normalise, or collapse it.
          displayManualText() only substitutes unrenderable PUA glyphs
          (tofu boxes) for their intended bullet marks at render time --
          see web/src/lib/manualText.ts. It never touches `citation.text`
          itself. */}
      <pre className="citation-text">{displayManualText(citation.text)}</pre>
      <p className="citation-revision">{citation.revision ?? "Revision not stated"}</p>
    </button>
  );
}
