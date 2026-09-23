import { useEffect, useRef, useState } from "react";
import { pageImageUrl } from "../api/client";
import type { Citation } from "../api/types";
import { displayManualText } from "../lib/manualText";

interface Props {
  citation: Citation | null;
  onClose: () => void;
}

type ImageState =
  | { status: "loading" }
  | { status: "ready"; url: string }
  | { status: "unavailable" } // 503: no PDF / no poppler on this deployment
  | { status: "error"; detail: string };

/**
 * The trust anchor. Tapping a citation slides this up from the bottom to
 * show the actual manual page image -- the manual itself, not a rendering
 * of it. This is the one orchestrated motion in the app.
 *
 * The drawer stays mounted (off-screen) so the slide has something to
 * transition from; `citation` toggles a class rather than mount/unmount.
 */
export function PageDrawer({ citation, onClose }: Props) {
  const [rendered, setRendered] = useState<Citation | null>(null);
  const [image, setImage] = useState<ImageState>({ status: "loading" });
  const closeRef = useRef<HTMLButtonElement>(null);
  const open = citation !== null;

  useEffect(() => {
    if (citation) setRendered(citation);
  }, [citation]);

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  useEffect(() => {
    if (!citation) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setImage({ status: "loading" });

    fetch(pageImageUrl(citation.pdf_page))
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 503) {
          setImage({ status: "unavailable" });
          return;
        }
        if (!res.ok) {
          setImage({ status: "error", detail: `Page image failed to load (${res.status}).` });
          return;
        }
        const blob = await res.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setImage({ status: "ready", url: objectUrl });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setImage({
          status: "error",
          detail: `Couldn't load the page image: ${err instanceof Error ? err.message : String(err)}`,
        });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [citation]);

  return (
    <>
      {open && <div className="drawer-backdrop" onClick={onClose} role="presentation" />}
      <aside
        className={`drawer${open ? " drawer--open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
        aria-label={rendered?.label ?? "Manual page"}
      >
        {rendered && (
          <>
            <header className="drawer-head">
              <div>
                <p className="drawer-label">{rendered.label}</p>
                <p className="drawer-sub">{rendered.section_title ?? rendered.part}</p>
                <p className="drawer-sub drawer-revision">{rendered.revision ?? "Revision not stated"}</p>
              </div>
              <button
                ref={closeRef}
                type="button"
                className="drawer-close"
                onClick={onClose}
                aria-label="Close"
                tabIndex={open ? 0 : -1}
              >
                &times;
              </button>
            </header>

            {/* See web/src/lib/manualText.ts -- render-time-only PUA glyph
                substitution, never applied to `rendered.text` itself. */}
            <pre className="drawer-text">{displayManualText(rendered.text)}</pre>

            <div className="drawer-image">
              {image.status === "loading" && <p className="drawer-note">Loading the manual page…</p>}
              {image.status === "unavailable" && (
                <p className="drawer-note">
                  This deployment doesn't have the manual PDF available, so the page image can't be shown.
                </p>
              )}
              {image.status === "error" && <p className="drawer-note">{image.detail}</p>}
              {image.status === "ready" && (
                <img
                  className="drawer-page"
                  src={image.url}
                  alt={`Manual page ${rendered.pdf_page}`}
                  loading="lazy"
                />
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
