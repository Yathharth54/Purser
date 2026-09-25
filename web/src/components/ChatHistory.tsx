import { useEffect, useState } from "react";
import { fetchThreads } from "../api/client";
import type { ThreadSummary } from "../api/types";

interface Props {
  currentId: string | null;
  onSelect: (id: string) => void;
  onClose: () => void;
}

/** "10:04" for today, "24 Sep" for anything older -- in her local time. */
function when(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })
    : d.toLocaleDateString([], { day: "numeric", month: "short" });
}

/**
 * Her past chats, most recently used first (the server keeps the last 100).
 * Tapping one reopens it in place, ready to continue.
 */
export function ChatHistory({ currentId, onSelect, onClose }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchThreads()
      .then(setThreads)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <section className="hist" aria-label="Your chats">
      <div className="hist-head">
        <h2 className="hist-title">Your chats</h2>
        <button type="button" className="bar-btn" onClick={onClose}>
          Close
        </button>
      </div>
      {error && <p className="turn-error">Couldn't load your chats: {error}</p>}
      {!error && threads === null && <p className="hist-note">Loading…</p>}
      {threads?.length === 0 && <p className="hist-note">No chats yet. Ask something to start one.</p>}
      {threads && threads.length > 0 && (
        <ul className="hist-list">
          {threads.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                className={t.id === currentId ? "hist-row on" : "hist-row"}
                aria-current={t.id === currentId ? "true" : undefined}
                onClick={() => onSelect(t.id)}
              >
                <span className="hist-row-title">{t.title || "Untitled chat"}</span>
                <span className="hist-row-when">{when(t.updated_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
