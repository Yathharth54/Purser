import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CitationChip } from "./CitationChip";
import type { Citation } from "../api/types";

const CITE: Citation = {
  pdf_page: 300,
  part: "PART THREE",
  section: "3.5",
  section_title: "Passenger Handling",
  page_in_section: 16,
  revision: "Issue IX Revision 03",
  effective: "2024-01-01",
  text: "Where: The distance of (no. of rows) the nearest exit",
  blocks: [{ kind: "para", level: 0, depth: 0, text: "Where: The distance of (no. of rows) the nearest exit" }],
  label: "PART THREE §3.5 p.16",
  context: "1.6         3 POINT BRIEFING",
};

describe("CitationChip", () => {
  it("names the section a quote sits in, in the header and never in the quote body", () => {
    const html = renderToStaticMarkup(<CitationChip citation={CITE} onOpen={() => {}} />);
    const head = /<div class="paper-head">([\s\S]*?)<\/div>/.exec(html)![1]!;
    const body = /<div class="paper-body">([\s\S]*?)<p class="paper-rev">/.exec(html)![1]!;
    expect(head).toContain('<span class="paper-ctx">1.6         3 POINT BRIEFING</span>');
    expect(body).not.toContain("3 POINT BRIEFING");
  });

  it("shows no section line when the quote sits outside any section", () => {
    const html = renderToStaticMarkup(<CitationChip citation={{ ...CITE, context: null }} onOpen={() => {}} />);
    expect(html).not.toContain("paper-ctx");
  });
});
