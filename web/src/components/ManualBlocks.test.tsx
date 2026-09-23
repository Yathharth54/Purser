import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ManualBlocks } from "./ManualBlocks";
import type { Block } from "../api/types";

/**
 * Fixtures below are real `Block`s read off the live API
 * (`GET /api/section/4.2` and `/api/section/4.4`), not invented shapes --
 * see task-10-report.md for how they were pulled. `TABLE_4_2B` in
 * particular is the exact table rendered in the mockup's own "Manual" demo
 * section.
 */

const HEADING: Block = { kind: "heading", level: 1, text: "2. CREW RESPONSIBILTIES" };
const SUBHEADING: Block = { kind: "subheading", level: 0, text: "SECTION 4.4" };
const PARA: Block = { kind: "para", level: 0, text: "Suspected burning smell in the cabin" };
const BULLET: Block = {
  kind: "bullet",
  level: 0,
  text: "If possible - move passengers away from the affected area.",
};
const NOTE: Block = { kind: "note", level: 0, text: "Note: Kindly refer to PART THREE for details" };
const CAPTION: Block = { kind: "caption", level: 0, text: "Table 4.2B" };

// pdf page 552, §4.2 -- a real two-column safety table. Leading spaces and
// embedded newlines are the only thing pairing a command to the cabin crew
// action it requires; collapsing or trimming this text destroys that
// mapping. See ManualBlocks.tsx / Block's doc comment.
const TABLE_4_2B_TEXT =
  "          MID AIR SMOKE FILLED CABIN               CABIN CREW ACTIONS\n" +
  "         COMMANDS (WHEN CREW ARE\n" +
  "            SEATED FOR LANDING )\n" +
  "                   STAY LOW                  For smoke during approach: Cabin\n" +
  "        COVER YOUR NOSE AND MOUTH            crew must use their scarves to\n" +
  "                                             protect themselves against toxic\n" +
  "               BREATHE SHALLOW\n" +
  "                                             gasses and fumes whilst remaining\n" +
  "        Note: to be alternated with brace    in their brace positions\n" +
  "         commands (if required) prior to\n" +
  "                     impact";
const TABLE: Block = { kind: "table", level: 0, text: TABLE_4_2B_TEXT };

// pdf page 594, §4.4 -- the nine-step ditching procedure, one nesting level
// under its own intro paragraph.
const BULLET_LV1: Block = { kind: "bullet", level: 1, text: "Step 1: Crew communication and co-ordination" };

// pdf page 646, §4.4 -- the deepest real bullet nesting found in the
// corpus (level 7), inside the ABP briefing procedure.
const BULLET_LV7: Block = { kind: "bullet", level: 7, text: "will create barrier with other ABPs to avoid" };

function extractTag(html: string, className: string): { tag: string; inner: string } | null {
  const re = new RegExp(`<(\\w+)[^>]*class="${className}"[^>]*>([\\s\\S]*?)</\\1>`);
  const m = re.exec(html);
  if (!m) return null;
  return { tag: m[1]!, inner: m[2]! };
}

describe("ManualBlocks", () => {
  it("renders each kind to its own distinct element/class -- the seven kinds never collapse into each other", () => {
    const html = renderToStaticMarkup(
      <ManualBlocks blocks={[HEADING, SUBHEADING, PARA, BULLET, NOTE, CAPTION, TABLE]} />,
    );

    const heading = extractTag(html, "m-h");
    const subheading = extractTag(html, "m-sh");
    const para = extractTag(html, "m-p");
    const bullet = extractTag(html, "m-li");
    const note = extractTag(html, "m-note");
    const caption = extractTag(html, "m-cap");
    const table = extractTag(html, "m-tbl");

    expect(heading?.tag).toBe("h4");
    expect(subheading?.tag).toBe("h5");
    expect(para?.tag).toBe("p");
    expect(bullet?.tag).toBe("div");
    expect(note?.tag).toBe("div");
    expect(caption?.tag).toBe("div");
    expect(table?.tag).toBe("div");

    // Every class is present exactly once (one block of each kind was
    // given, so a collapse into a shared class would show up as a class
    // that's missing here or a leftover class matching more than one kind).
    for (const cls of ["m-h", "m-sh", "m-p", "m-li", "m-note", "m-cap", "m-tbl"]) {
      expect(html).toContain(`class="${cls}"`);
    }

    expect(heading?.inner).toContain("CREW RESPONSIBILTIES");
    expect(subheading?.inner).toContain("SECTION 4.4");
    expect(para?.inner).toContain("Suspected burning smell");
    expect(bullet?.inner).toContain("move passengers away");
    expect(note?.inner).toContain("Kindly refer to PART THREE");
    expect(caption?.inner).toContain("Table 4.2B");
  });

  it("preserves a table's whitespace byte-for-byte -- no collapsing, trimming, or reflow", () => {
    const html = renderToStaticMarkup(<ManualBlocks blocks={[TABLE]} />);
    const pre = /<pre>([\s\S]*?)<\/pre>/.exec(html);
    expect(pre).not.toBeNull();
    // Exact equality, not `.toContain` -- a table's column gaps ARE the
    // condition->action mapping the safety procedure depends on. This
    // fixture has no HTML-special characters, so the extracted text is
    // directly comparable to the source string with no entity-decoding
    // needed.
    expect(pre![1]).toBe(TABLE_4_2B_TEXT);
  });

  it("reaches the DOM with the bullet's nesting level, at a shallow and a deep level", () => {
    const html = renderToStaticMarkup(<ManualBlocks blocks={[BULLET_LV1, BULLET_LV7]} />);
    const styleAttrs = [...html.matchAll(/<div class="m-li" style="([^"]*)"/g)].map((m) => m[1]);
    expect(styleAttrs).toHaveLength(2);
    expect(styleAttrs[0]).toContain("--lv:1");
    expect(styleAttrs[1]).toContain("--lv:7");
  });

  it("substitutes PUA glyphs so they never survive into rendered output as raw codepoints", () => {
    const known: Block = { kind: "bullet", level: 0, text: "Captain  leaves the cockpit last" };
    // A PUA codepoint the manual doesn't specifically map is still swept by
    // the general PUA range and given the fallback glyph, not a tofu box.
    const unmapped: Block = { kind: "bullet", level: 0, text: "Item  marker" };

    const html = renderToStaticMarkup(<ManualBlocks blocks={[known, unmapped]} />);

    expect(html).not.toContain("");
    expect(html).not.toContain("");
    expect(html).toContain("▸"); // "▸" -- the known U+F0D8 substitution
    expect(html).toContain("•"); // "•" -- the fallback for an unmapped PUA glyph
  });

  it("renders an empty blocks array without throwing", () => {
    expect(() => renderToStaticMarkup(<ManualBlocks blocks={[]} />)).not.toThrow();
    expect(renderToStaticMarkup(<ManualBlocks blocks={[]} />)).toBe('<div class="manual-blocks"></div>');
  });
});
