import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import type { ReadingPage, TocNode } from "../api/types";

/**
 * `TocBrowser` is the component whose old preview requested
 * `Math.min(4, …)` pages and then rendered `.slice(0, 40)` of the result --
 * for an 80-page section that showed roughly one page and called it done.
 * `fetchSection` was changed to take a single `section` argument with no
 * page-bound parameters, so a cap can no longer be *passed*, but nothing
 * pinned that signature or proved every page returned actually reaches the
 * DOM. This test does both.
 *
 * `ManualBlocks.test.tsx` uses `renderToStaticMarkup` and avoids jsdom, but
 * that only works for a purely presentational component: React's server
 * renderer never runs `useEffect`, and `TocBrowser`'s fetch happens inside
 * one. `react-test-renderer` (already a peer-matched 18.3.1, added here) is
 * the lighter-weight alternative built for exactly this -- it renders off
 * the real DOM but still runs effects under `act()`, without adding jsdom.
 */

const { fetchToc, fetchSection } = vi.hoisted(() => ({
  fetchToc: vi.fn(),
  fetchSection: vi.fn(),
}));

vi.mock("../api/client", () => ({ fetchToc, fetchSection }));

const { TocBrowser } = await import("./TocBrowser");

const NODE: TocNode = {
  part: "PART FOUR",
  section: "4.4",
  title: "Emergency Evacuation",
  pdf_page_from: 590,
  pdf_page_to: 669,
  pages: 80,
};

function page(n: number, total: number): ReadingPage {
  return {
    pdf_page: 589 + n,
    page_in_section: n,
    section_total: total,
    section: "4.4",
    section_title: "Emergency Evacuation",
    revision: "REV 40",
    effective: "2024-01-01",
    blocks: [{ kind: "para", level: 0, text: `Page ${n} body text` }],
    empty: false,
  };
}

describe("TocBrowser", () => {
  beforeEach(() => {
    fetchToc.mockReset();
    fetchSection.mockReset();
  });

  it("calls fetchSection with a single argument and renders every page a section returns", async () => {
    fetchToc.mockResolvedValue([NODE]);
    // Small stand-in for the real 80-page §4.4 -- large enough that a
    // reintroduced 4-page or 40-line cap would fail this.
    const totalPages = 6;
    fetchSection.mockResolvedValue(
      Array.from({ length: totalPages }, (_, i) => page(i + 1, totalPages)),
    );

    let renderer: ReactTestRenderer;
    await act(async () => {
      renderer = create(<TocBrowser />);
    });
    await act(async () => {}); // flush fetchToc().then(setNodes)

    const openButton = renderer!.root.findByProps({ className: "toc-open" });
    await act(async () => {
      openButton.props.onClick();
    });
    await act(async () => {}); // flush fetchSection().then(setSection)

    expect(fetchSection).toHaveBeenCalledTimes(1);
    expect(fetchSection.mock.calls[0]).toEqual(["4.4"]);
    expect(fetchSection.mock.calls[0]).toHaveLength(1);

    const pageEls = renderer!.root.findAllByType("section");
    expect(pageEls).toHaveLength(totalPages);

    const rendered = JSON.stringify(renderer!.toJSON());
    for (let n = 1; n <= totalPages; n++) {
      expect(rendered).toContain(`"aria-label":"Page ${n} of ${totalPages}"`);
      expect(rendered).toContain(`Page ${n} body text`);
    }
  });
  it("marks a page that opens inside a section, and collapses that section across the page break", async () => {
    fetchToc.mockResolvedValue([NODE]);
    const base = page(1, 3);
    fetchSection.mockResolvedValue([
      {
        ...base,
        blocks: [
          { kind: "heading", level: 1, depth: 0, text: "1. GENERAL" },
          { kind: "para", level: 0, depth: 1, text: "p1 body" },
        ],
      },
      {
        ...page(2, 3),
        continues: ["1. GENERAL"],
        blocks: [{ kind: "para", level: 0, depth: 1, text: "p2 body" }],
      },
      {
        ...page(3, 3),
        blocks: [
          { kind: "heading", level: 1, depth: 0, text: "2. CREW" },
          { kind: "para", level: 0, depth: 1, text: "p3 body" },
        ],
      },
    ]);

    let renderer: ReactTestRenderer;
    await act(async () => {
      renderer = create(<TocBrowser />);
    });
    await act(async () => {});
    await act(async () => {
      renderer!.root.findByProps({ className: "toc-open" }).props.onClick();
    });
    await act(async () => {});

    const text = () => JSON.stringify(renderer!.toJSON());
    expect(text()).toContain("1 General · continued");
    expect(text()).toContain("p2 body");

    const [general] = renderer!.root.findAllByProps({ className: "m-h-toggle" });
    await act(async () => {
      general!.props.onClick();
    });

    expect(general!.props["aria-expanded"]).toBe(false);
    expect(text()).not.toContain("p1 body");
    expect(text()).not.toContain("p2 body");
    expect(text()).toContain("p3 body");
    const sections = renderer!.root.findAllByType("section");
    expect(sections).toHaveLength(3);
    expect(sections.map((s) => Boolean(s.props.hidden))).toEqual([false, true, false]);
  });

  it("jumps to the page a contents entry names, reopening a collapsed heading that hides it", async () => {
    fetchToc.mockResolvedValue([NODE]);
    fetchSection.mockResolvedValue([
      {
        ...page(1, 3),
        blocks: [
          { kind: "toc", level: 1, depth: 0, text: "CREW", number: "2", page: 3 },
          { kind: "heading", level: 1, depth: 0, text: "1. GENERAL" },
          { kind: "para", level: 0, depth: 1, text: "p1 body" },
        ],
      },
      { ...page(2, 3), continues: ["1. GENERAL"], blocks: [{ kind: "para", level: 0, depth: 1, text: "p2" }] },
      { ...page(3, 3), continues: ["1. GENERAL"], blocks: [{ kind: "para", level: 0, depth: 1, text: "p3" }] },
    ]);
    const scrolled: string[] = [];
    vi.stubGlobal("document", {
      getElementById: (id: string) => ({ scrollIntoView: () => scrolled.push(id) }),
    });
    vi.stubGlobal("window", { ...globalThis.window, matchMedia: () => ({ matches: true }) });

    let renderer: ReactTestRenderer;
    await act(async () => {
      renderer = create(<TocBrowser />);
    });
    await act(async () => {});
    await act(async () => renderer!.root.findByProps({ className: "toc-open" }).props.onClick());
    await act(async () => {});
    // Collapse "1. GENERAL": pages 2 and 3 are hidden under it.
    await act(async () => renderer!.root.findByProps({ className: "m-h-toggle" }).props.onClick());
    expect(JSON.stringify(renderer!.toJSON())).not.toContain("p3");

    await act(async () => renderer!.root.findByProps({ className: "m-toc-row" }).props.onClick());
    expect(scrolled).toEqual(["manual-page-592"]); // page 3 of the section
    expect(JSON.stringify(renderer!.toJSON())).toContain("p3");
    vi.unstubAllGlobals();
  });
});
