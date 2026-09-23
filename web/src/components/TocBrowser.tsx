import { useEffect, useState } from "react";
import { fetchSection, fetchToc } from "../api/client";
import type { PageText, TocNode } from "../api/types";
import { displayManualText } from "../lib/manualText";

export function TocBrowser() {
  const [nodes, setNodes] = useState<TocNode[]>([]);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [pages, setPages] = useState<PageText[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    void fetchToc()
      .then(setNodes)
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const node = openIndex === null ? null : nodes[openIndex];
    if (!node?.section) {
      setPages([]);
      return;
    }
    void fetchSection(node.section, 1, Math.min(4, node.pdf_page_to - node.pdf_page_from + 1)).then(setPages);
  }, [openIndex, nodes]);

  if (loadError) {
    return <p className="turn-error toc-error">Couldn't load the manual index: {loadError}</p>;
  }

  return (
    <div className="toc">
      {nodes.map((n, i) => {
        const open = openIndex === i;
        return (
          <div key={`${n.part}-${n.section ?? i}`} className="toc-row">
            <button
              type="button"
              className="toc-open"
              aria-expanded={open}
              onClick={() => setOpenIndex(open ? null : i)}
            >
              <span className="toc-id">{n.section ?? n.part}</span>
              <span className="toc-title">{n.title ?? n.part}</span>
              <span className="toc-pages">{n.pages} pp</span>
            </button>
            {open && (
              // See web/src/lib/manualText.ts -- render-time-only PUA glyph
              // substitution, never applied to the underlying PageText.
              <pre className="toc-preview">
                {pages.length > 0
                  ? displayManualText(pages.flatMap((p) => p.numbered_lines).slice(0, 40).join("\n"))
                  : "Loading…"}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
