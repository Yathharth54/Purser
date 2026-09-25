import { useEffect, useRef, useState } from "react";
import { fetchThreads } from "../api/client";
import type { ThreadSummary } from "../api/types";

interface Props {
  open: boolean;
  currentId: string | null;
  /** While an answer streams, switching or starting a chat would land it in
   *  the wrong one -- the panel still opens, but those actions wait. */
  busy: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Whole local days between `iso` and today: 0 today, 1 yesterday. */
function daysAgo(iso: string, now: Date): number {
  return Math.round((startOfDay(now) - startOfDay(new Date(iso))) / DAY_MS);
}

function groupLabel(days: number): string {
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "This week";
  return "Earlier";
}

/** "10:04" for today and yesterday (the group already says which), "24 Sep"
 *  for anything older -- in her local time. */
function when(iso: string, now: Date): string {
  const d = new Date(iso);
  return daysAgo(iso, now) <= 1
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })
    : d.toLocaleDateString([], { day: "numeric", month: "short" });
}

/** The title with every case-insensitive hit on `query` wrapped in <mark>. */
function highlight(title: string, query: string): React.ReactNode {
  if (!query) return title;
  const lower = title.toLowerCase();
  const q = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (let hit = lower.indexOf(q); hit !== -1; hit = lower.indexOf(q, at)) {
    if (hit > at) parts.push(title.slice(at, hit));
    parts.push(<mark key={hit}>{title.slice(hit, hit + q.length)}</mark>);
    at = hit + q.length;
  }
  if (at < title.length) parts.push(title.slice(at));
  return parts;
}

/**
 * Her past chats in a panel that slides in from the left, most recently used
 * first (the server keeps the last 100), grouped by day and searchable by
 * title. Tapping one reopens it in place, ready to continue.
 *
 * A real modal like the page drawer: it stays mounted so the slide has
 * something to transition from, traps and restores focus, and closes on
 * Escape or a tap on the dimmed chat behind it. The list is fetched afresh
 * each time it opens, so a chat she just asked in is already at the top.
 */
export function ChatHistory({ open, currentId, busy, onSelect, onNew, onClose }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    setQuery("");
    void fetchThreads()
      .then((t) => !cancelled && setThreads(t))
      .catch((err: unknown) => !cancelled && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Hand focus to the close button on open, and back to whatever opened the
  // panel (the header's chats button) on close.
  useEffect(() => {
    if (open) {
      previouslyFocused.current = document.activeElement as HTMLElement | null;
      closeRef.current?.focus();
    } else if (previouslyFocused.current) {
      previouslyFocused.current.focus();
      previouslyFocused.current = null;
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  function trapTab(e: React.KeyboardEvent<HTMLElement>) {
    if (e.key !== "Tab" || !panelRef.current) return;
    const focusables = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
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

  const now = new Date();
  const q = query.trim();
  const shown = threads?.filter((t) => (t.title || "Untitled chat").toLowerCase().includes(q.toLowerCase())) ?? [];
  const groups: { label: string; items: ThreadSummary[] }[] = [];
  if (q) {
    if (shown.length > 0) {
      groups.push({ label: shown.length === 1 ? "1 chat matches" : `${shown.length} chats match`, items: shown });
    }
  } else {
    for (const t of shown) {
      const label = groupLabel(daysAgo(t.updated_at, now));
      const last = groups[groups.length - 1];
      if (last?.label === label) last.items.push(t);
      else groups.push({ label, items: [t] });
    }
  }

  return (
    <>
      {open && <div className="chats-backdrop" onClick={onClose} aria-hidden="true" />}
      <nav
        ref={panelRef}
        className={open ? "chats chats--open" : "chats"}
        role="dialog"
        aria-modal="true"
        aria-label="Your chats"
        aria-hidden={!open}
        onKeyDown={trapTab}
      >
        <div className="chats-head">
          <h2 className="chats-title">Chats</h2>
          <button
            type="button"
            ref={closeRef}
            className="chats-close"
            onClick={onClose}
            aria-label="Close chats"
            tabIndex={open ? 0 : -1}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        <div className="chats-tools">
          <button type="button" className="chats-new" onClick={onNew} disabled={busy} tabIndex={open ? 0 : -1}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
            New chat
          </button>
          <label className="chats-search">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your chats"
              aria-label="Search your chats"
              enterKeyHint="search"
              tabIndex={open ? 0 : -1}
            />
            {query && (
              <button type="button" className="chats-clear" onClick={() => setQuery("")} aria-label="Clear search">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            )}
          </label>
        </div>

        <div className="chats-body">
          {error && <p className="turn-error">Couldn't load your chats: {error}</p>}
          {!error && threads === null && <p className="chats-note">Loading…</p>}
          {!error && threads?.length === 0 && <p className="chats-note">No chats yet. Ask something to start one.</p>}
          {!error && q && threads && threads.length > 0 && shown.length === 0 && (
            <p className="chats-note">No chat titles match “{q}”.</p>
          )}
          {groups.map((g) => (
            <section key={g.label} className="chats-group" aria-label={g.label}>
              <h3 className="chats-group-label">{g.label}</h3>
              <ul className="chats-list">
                {g.items.map((t) => {
                  const current = t.id === currentId;
                  return (
                    <li key={t.id}>
                      <button
                        type="button"
                        className={current ? "chats-row on" : "chats-row"}
                        aria-current={current ? "true" : undefined}
                        onClick={() => onSelect(t.id)}
                        disabled={busy}
                        tabIndex={open ? 0 : -1}
                      >
                        <span className="chats-row-dot" aria-hidden="true" />
                        <span className="chats-row-text">
                          <span className="chats-row-title">{highlight(t.title || "Untitled chat", q)}</span>
                          <span className="chats-row-when">
                            {q && daysAgo(t.updated_at, now) <= 1
                              ? `${groupLabel(daysAgo(t.updated_at, now))} ${when(t.updated_at, now)}`
                              : when(t.updated_at, now)}
                            {current && " · open now"}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>

        <p className="chats-foot">{q ? "Searching chat titles." : "Your last 100 chats are kept."}</p>
      </nav>
    </>
  );
}
