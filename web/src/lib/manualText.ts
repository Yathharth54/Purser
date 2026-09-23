/**
 * Display-time-only glyph substitution for verbatim manual text.
 *
 * `pdftotext -layout` carries over Wingdings/symbol-font bullet glyphs from
 * the source PDF as Private Use Area (PUA, U+E000-U+F8FF) codepoints --
 * there is no font on a phone or a laptop that maps U+F0D8 or U+F0A7 to
 * anything, so they render as a "tofu" missing-glyph box. Measured across
 * the corpus: 4,341 PUA codepoints over 619 of 1,226 pages (U+F0D8 x4326,
 * a Wingdings right-pointing bullet, and U+F0A7 x15, a filled square),
 * landing hardest in numbered step lists in the emergency procedures --
 * exactly where illegibility hurts most.
 *
 * This is applied ONLY here, at render time, in the client. It must never
 * move into ingest or into the server-side citation splice: the backend's
 * verbatim-text guarantee (`Citation.text` byte-exact from the manual) is
 * the whole point of the coordinate-only citation architecture, and this
 * function does not touch it -- `citation.text` in memory and over the
 * wire stays exactly what the server sent.
 *
 * Why this is faithfulness, not alteration: a tofu box is not a more
 * faithful reproduction of a bullet than a bullet is -- it is an
 * unrenderable glyph carrying no information. The source PDF's *intent*
 * at that codepoint was a bullet glyph; rendering it as one recovers that
 * intent for a reader, where rendering the box recovers nothing. Do not
 * "fix" tofu boxes by trimming or filtering this text upstream -- the
 * fix belongs here, in the renderer, and only here.
 */

/** Codepoints the manual is known to use, mapped to their intended glyph. */
const KNOWN_PUA_GLYPHS: Record<number, string> = {
  0xf0d8: "▸", // Wingdings right-pointing bullet (step-list marker)
  0xf0a7: "▪", // Wingdings filled square
};

/** Any other PUA codepoint we haven't specifically identified still needs
 *  *something* other than a box -- a plain bullet is a reasonable general
 *  default for a symbol-font glyph substituted into body text. */
const FALLBACK_PUA_GLYPH = "•";

// Both the primary PUA block used by the manual's embedded symbol fonts
// and the two supplementary PUA planes, swept generally rather than
// hardcoding only the two codepoints above.
const PUA_RANGES: Array<[number, number]> = [
  [0xe000, 0xf8ff],
  [0xf0000, 0xffffd],
  [0x100000, 0x10fffd],
];

function isPrivateUse(codepoint: number): boolean {
  return PUA_RANGES.some(([start, end]) => codepoint >= start && codepoint <= end);
}

/**
 * Render-time substitution for a verbatim manual text string. Returns a new
 * string; never mutates or is applied to the `Citation`/`PageText` objects
 * themselves, so the underlying data stays byte-exact for anything else
 * that touches it (copy, future export, etc.) -- only what's painted to
 * the screen is affected.
 */
export function displayManualText(text: string): string {
  let out = "";
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp in KNOWN_PUA_GLYPHS) {
      out += KNOWN_PUA_GLYPHS[cp];
    } else if (isPrivateUse(cp)) {
      out += FALLBACK_PUA_GLYPH;
    } else {
      out += ch;
    }
  }
  return out;
}
