import { useEffect, useMemo, useRef, useState } from "react";
import { fetchSection, fetchToc } from "../api/client";
import type { ReadingPage, TocNode } from "../api/types";
import { ManualBlocks } from "./ManualBlocks";
import { splitHeading } from "../lib/headingCase";

/** The heading a page opens inside, cased like the heading itself. */
function continuedLabel(heading: string): string {
  const { number, title } = splitHeading(heading);
  return number ? `${number} ${title}` : title;
}

type SectionState =
  | { status: "loading" }
  | { status: "ready"; pages: ReadingPage[] }
  | { status: "error"; detail: string };

/**
 * Which blocks a collapsed heading hides, walking the whole section in order.
 *
 * A section flows across page breaks, so a heading collapsed on page 5 also
 * hides the top of page 6 -- this has to be computed over all pages at once,
 * not per page. A collapsed heading at depth d hides every following block
 * deeper than d, until the first block at depth d or shallower.
 */
function hiddenBlocks(
  pages: ReadingPage[],
  collapsed: ReadonlySet<string>,
): { byPage: Map<number, Set<number>>; hiddenPages: Set<number> } {
  const byPage = new Map<number, Set<number>>();
  const hiddenPages = new Set<number>();
  let hideDeeperThan: number | null = null;
  for (const page of pages) {
    const hidden = new Set<number>();
    if (page.blocks.length === 0 && hideDeeperThan !== null) hiddenPages.add(page.pdf_page);
    page.blocks.forEach((block, i) => {
      const depth = block.depth ?? 0;
      if (hideDeeperThan !== null) {
        if (depth > hideDeeperThan) {
          hidden.add(i);
          return;
        }
        hideDeeperThan = null;
      }
      if (block.kind === "heading" && collapsed.has(`${page.pdf_page}-${i}`)) hideDeeperThan = depth;
    });
    if (page.blocks.length > 0 && hidden.size === page.blocks.length) hiddenPages.add(page.pdf_page);
    byPage.set(page.pdf_page, hidden);
  }
  return { byPage, hiddenPages };
}

/**
 * The manual's contents list and section reader.
 *
 * This replaces a "preview" that requested `Math.min(4, …)` pages from the
 * API and then rendered `.slice(0, 40)` of the resulting lines -- for a
 * section like §4.4 (80 pages) that showed roughly one page and called it
 * done. The API was never the bug: `fetchSection` now takes no page bounds
 * and returns every `ReadingPage` in the section, and every one of them is
 * rendered. See client.ts's `fetchSection` for the removed parameters.
 *
 * 80 pages of a section is rendered as one continuous scroll, not paginated
 * or virtualised: each `ReadingPage` is `<ManualBlocks>` over already-parsed
 * blocks (no images, no heavy markup), so a full section is a few thousand
 * plain DOM nodes at most -- well within what a mobile browser handles, and
 * it keeps the page rail's scroll-progress readout and native find-in-page
 * both trivially correct. Pagination would need its own "jump to page N"
 * affordance to satisfy "the reader must be able to reach the last page";
 * a single scroll already does that for free.
 *
 * The section reads as one document: headings nest (see ManualBlocks), a
 * page that opens inside a section begun earlier says so, and any heading
 * can be collapsed -- including across page breaks (see `hiddenBlocks`). A
 * page whose every block is collapsed away hides its page marker too.
 */
export function TocBrowser() {
  const [nodes, setNodes] = useState<TocNode[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [openNode, setOpenNode] = useState<TocNode | null>(null);
  const [section, setSection] = useState<SectionState>({ status: "loading" });
  const [progress, setProgress] = useState(0);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const docRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    void fetchToc()
      .then(setNodes)
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    if (!openNode?.section) return;
    const section = openNode.section;
    let cancelled = false;
    setSection({ status: "loading" });
    void fetchSection(section)
      .then((pages) => {
        if (!cancelled) setSection({ status: "ready", pages });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSection({ status: "error", detail: err instanceof Error ? err.message : String(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [openNode]);

  useEffect(() => {
    if (!openNode) return;
    setCollapsed(new Set());
    setProgress(0);
    docRef.current?.scrollTo(0, 0);
    backRef.current?.focus();
  }, [openNode]);

  const [jumpTo, setJumpTo] = useState<number | null>(null);

  const visibility = useMemo(
    () => (section.status === "ready" ? hiddenBlocks(section.pages, collapsed) : null),
    [section, collapsed],
  );

  function toggle(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // A contents entry names a page of this section. Scroll to it -- or to the
  // next page that exists, for an entry pointing at a blank page -- opening
  // any collapsed heading that hides it first.
  function jumpToPage(pageInSection: number) {
    if (section.status !== "ready") return;
    const target = section.pages.find((p) => p.page_in_section >= pageInSection);
    if (!target) return;
    if (visibility?.hiddenPages.has(target.pdf_page)) setCollapsed(new Set());
    setJumpTo(target.pdf_page);
  }

  // Scroll once the page is rendered and shown -- after any collapse above
  // has been undone, which a scroll in the click handler would run ahead of.
  useEffect(() => {
    if (jumpTo === null) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    document
      .getElementById(`manual-page-${jumpTo}`)
      ?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
    setJumpTo(null);
  }, [jumpTo, visibility]);

  function handleScroll() {
    const el = docRef.current;
    if (!el) return;
    const max = el.scrollHeight - el.clientHeight;
    setProgress(max > 0 ? Math.min(1, Math.max(0, el.scrollTop / max)) : 1);
  }

  if (loadError) {
    return <p className="turn-error toc-error">Couldn't load the manual index: {loadError}</p>;
  }

  if (openNode) {
    // While the pages are loading, the header's page count/revision fall
    // back to what the contents list already knew, so it never flashes
    // empty.
    const firstPage = section.status === "ready" ? section.pages[0] : undefined;
    const totalPages = firstPage?.section_total ?? openNode.pages;
    const revision = firstPage?.revision ?? null;

    return (
      <div className="reader">
        <header className="reader-head">
          <button ref={backRef} type="button" className="reader-back" onClick={() => setOpenNode(null)}>
            &lsaquo; {openNode.part}
          </button>
          <h3 className="reader-title">{openNode.title ?? openNode.section}</h3>
          <p className="reader-meta">
            <span>&sect;{openNode.section}</span>
            <span aria-hidden="true">&middot;</span>
            <span>{totalPages} pages</span>
            {revision && (
              <>
                <span aria-hidden="true">&middot;</span>
                <span>{revision}</span>
              </>
            )}
          </p>
          <div
            className="reader-rail"
            role="progressbar"
            aria-label="Reading progress"
            aria-valuenow={Math.round(progress * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <i style={{ width: `${progress * 100}%` }} />
          </div>
        </header>

        <div className="reader-doc" ref={docRef} onScroll={handleScroll}>
          {section.status === "loading" && <p className="reader-note">Loading…</p>}
          {section.status === "error" && (
            <p className="turn-error reader-note">Couldn't load this section: {section.detail}</p>
          )}
          {section.status === "ready" &&
            section.pages.map((page) => {
              const hidden = visibility?.byPage.get(page.pdf_page);
              const firstShown = page.blocks.find((_, i) => !hidden?.has(i));
              const opensInside = page.continues?.length && firstShown && firstShown.kind !== "heading";
              return (
                <section
                  key={page.pdf_page}
                  id={`manual-page-${page.pdf_page}`}
                  aria-label={`Page ${page.page_in_section} of ${page.section_total}`}
                  hidden={visibility?.hiddenPages.has(page.pdf_page)}
                >
                  <div className="reader-pb">
                    <span>
                      PAGE {page.page_in_section} OF {page.section_total}
                    </span>
                    <i aria-hidden="true" />
                  </div>
                  {opensInside ? (
                    <p className="m-cont">{`${continuedLabel(page.continues![page.continues!.length - 1]!)} · continued`}</p>
                  ) : null}
                  {page.empty ? (
                    <p className="reader-blank">No text on this page.</p>
                  ) : (
                    <ManualBlocks
                      blocks={page.blocks}
                      idPrefix={String(page.pdf_page)}
                      collapsed={collapsed}
                      onToggle={toggle}
                      hidden={hidden}
                      onJumpToPage={jumpToPage}
                    />
                  )}
                </section>
              );
            })}
        </div>
      </div>
    );
  }

  return (
    <div className="toc">
      {nodes.map((n, i) => {
        const key = `${n.part}-${n.section ?? i}`;
        if (!n.section) {
          // Part-level dividers and unsectioned front matter have no
          // section id to read through GET /api/section/{section}, so they
          // aren't openable -- shown for context, not as a dead button that
          // would otherwise sit forever on "Loading…".
          return (
            <div key={key} className="toc-row toc-row-static">
              <span className="toc-id">{n.part}</span>
              <span className="toc-title">{n.title ?? n.part}</span>
              <span className="toc-pages">{n.pages} pp</span>
            </div>
          );
        }
        return (
          <div key={key} className="toc-row">
            <button type="button" className="toc-open" onClick={() => setOpenNode(n)}>
              <span className="toc-id">{n.section}</span>
              <span className="toc-title">{n.title ?? n.part}</span>
              <span className="toc-pages">{n.pages} pp</span>
              <span className="toc-chevron" aria-hidden="true">
                &rsaquo;
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
