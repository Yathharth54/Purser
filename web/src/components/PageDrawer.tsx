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

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The trust anchor. Tapping a citation slides this up from the bottom to
 * show the actual manual page image -- the manual itself, not a rendering
 * of it. This is the one orchestrated motion in the app (the other being
 * the segmented control's thumb), and both respect prefers-reduced-motion
 * through the global rule in styles.css.
 *
 * A real bottom sheet, not a styled div: it traps and restores focus,
 * closes on Escape or a backdrop tap, and locks background scroll while
 * open. The drawer stays mounted (off-screen) so the slide has something
 * to transition from; `citation` toggles a class rather than mount/unmount.
 */
export function PageDrawer({ citation, onClose }: Props) {
  const [rendered, setRendered] = useState<Citation | null>(null);
  const [image, setImage] = useState<ImageState>({ status: "loading" });
  const sheetRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const open = citation !== null;

  useEffect(() => {
    if (citation) setRendered(citation);
  }, [citation]);

  // Focus management, part 1: snapshot whatever had focus (the citation she
  // just tapped) the instant the sheet starts opening, and hand it back
  // when the sheet closes, rather than dropping focus to <body>.
  useEffect(() => {
    if (open) {
      previouslyFocused.current = document.activeElement as HTMLElement | null;
    } else if (previouslyFocused.current) {
      previouslyFocused.current.focus();
      previouslyFocused.current = null;
    }
  }, [open]);

  // Focus management, part 2: move focus to the close affordance -- the
  // dismiss control should be the very next stop for a keyboard/switch
  // user. This is a separate effect keyed on `rendered` (not just `open`)
  // because the header/close button only mount once `rendered` catches up
  // to `citation` a tick later; keying this on `open` alone would call
  // .focus() on a ref that's still null.
  useEffect(() => {
    if (open && rendered) closeRef.current?.focus();
  }, [open, rendered]);

  // Scroll lock: a bottom sheet over content she can still drag is a leak,
  // especially one-handed where a stray thumb movement scrolls the page
  // behind it.
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  // Focus trap: a modal surface never lets Tab walk a keyboard user out
  // into the (scroll-locked, visually obscured) app behind it.
  function trapTab(e: React.KeyboardEvent<HTMLElement>) {
    if (e.key !== "Tab" || !open || !sheetRef.current) return;
    const focusables = sheetRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

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
          setImage({ status: "error", detail: `Couldn't load the page image (${res.status}).` });
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
        ref={sheetRef}
        className={`drawer${open ? " drawer--open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
        aria-label={rendered?.label ?? "Manual page"}
        onKeyDown={trapTab}
      >
        <div className="drawer-grab" aria-hidden="true" />
        {rendered && (
          <>
            <header className="drawer-head">
              <div className="drawer-heading">
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

            <div className="drawer-body">
              {/* See web/src/lib/manualText.ts -- render-time-only PUA glyph
                  substitution, never applied to `rendered.text` itself. This
                  is the byte-exact verbatim quote; the image below is the
                  page it was cut from. */}
              <pre className="drawer-quote">{displayManualText(rendered.text)}</pre>

              <div className="drawer-image">
                {image.status === "loading" && (
                  <div className="think">
                    <i className="crescent" aria-hidden="true" />
                    Loading the manual page…
                  </div>
                )}
                {image.status === "unavailable" && (
                  <p className="drawer-note">
                    Page images aren't available on this server. Read the excerpt above instead --
                    it's the verbatim manual text.
                  </p>
                )}
                {image.status === "error" && (
                  <p className="drawer-note">
                    {image.detail} Read the excerpt above instead -- it's the verbatim manual text.
                  </p>
                )}
                {image.status === "ready" && (
                  <div className="drawer-page-frame">
                    <img
                      className="drawer-page"
                      src={image.url}
                      alt={`Manual page ${rendered.pdf_page}`}
                      loading="lazy"
                    />
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
}
