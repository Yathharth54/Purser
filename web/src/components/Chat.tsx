import { useEffect, useRef, useState, type ReactNode } from "react";
import { fetchThread, fetchThreads, streamChat } from "../api/client";
import type { Citation, ThreadMessage, ThreadSummary, ToolEvent } from "../api/types";
import { ChatHistory } from "./ChatHistory";
import { CitationChip } from "./CitationChip";
import { AnswerMarkdown } from "../lib/answerMarkdown";

interface Turn {
  role: "user" | "assistant";
  body: string;
  citations: Citation[];
  /** True once a `citations` event (even an empty one) or `done`/`error` has
   *  settled this turn -- gates whether "Not from the manual." can show. */
  settled: boolean;
  /** Transient retrieval progress, replaced in place -- never appended. */
  toolStatus: string | null;
  errorText: string | null;
  /** Wall-clock time the turn was created, formatted once at creation.
   *  Approximate (not the moment the answer actually finished streaming),
   *  which is exactly what every other chat surface shows too. */
  time: string;
}

interface Props {
  onOpenCitation: (c: Citation) => void;
  /** The chats panel is opened from the app header, which has no view of
   *  the thread -- Chat owns what switching or starting a chat means. */
  chatsOpen: boolean;
  onCloseChats: () => void;
  /** Open a section of the manual in the Manual tab (the home shortcuts). */
  onOpenSection: (section: string) => void;
}

// Home shortcuts: the emergency chapters, straight into the manual.
const SECTIONS: { section: string; label: string; icon: ReactNode }[] = [
  {
    section: "4.4",
    label: "Evacuations",
    icon: (
      <>
        <path d="M13 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5" />
        <path d="M4 12h10" />
        <path d="m10 8 4 4-4 4" />
      </>
    ),
  },
  {
    section: "4.2",
    label: "Smoke / fumes",
    icon: <path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.2 9.1 4.5 4.5 0 0 0 7 18Z" />,
  },
  {
    section: "4.3",
    label: "Decompression",
    icon: (
      <>
        <path d="M12 3v5" />
        <path d="M7 12c0-2.2 2.2-4 5-4s5 1.8 5 4v2a5 5 0 0 1-10 0z" />
        <path d="M9 21h6" />
      </>
    ),
  },
  {
    section: "4.1",
    label: "Fire fighting",
    icon: <path d="M12 3c1 3 4 5 4 9a4 4 0 0 1-8 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 0-8Z" />,
  },
];

/** "10:04" today, "Yest." yesterday, "22 Sep" before that. */
function recentWhen(iso: string): string {
  const d = new Date(iso);
  const days = Math.round(
    (new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86_400_000,
  );
  if (days <= 0) return formatClock(d);
  if (days === 1) return "Yest.";
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

// The chat she is in survives a refresh: its id is kept on the device and
// reopened on load. Storage can be unavailable (private mode) -- then a
// refresh simply starts a fresh chat, as before.
const THREAD_KEY = "purser-thread";

function storedThread(): string | null {
  try {
    return localStorage.getItem(THREAD_KEY);
  } catch {
    return null;
  }
}

function storeThread(id: string | null): void {
  try {
    if (id) localStorage.setItem(THREAD_KEY, id);
    else localStorage.removeItem(THREAD_KEY);
  } catch {
    // Ignore -- only affects reopening after a refresh.
  }
}

function toTurn(m: ThreadMessage): Turn {
  return {
    role: m.role === "user" ? "user" : "assistant",
    body: m.body,
    citations: m.citations,
    settled: true,
    toolStatus: null,
    errorText: null,
    time: formatClock(new Date(m.created_at)),
  };
}

function formatClock(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** Best-effort human label for a `tool` event. Args are a loosely-typed
 *  bag (`Record<string, unknown>`) so this reads defensively. */
function describeTool(event: ToolEvent): string {
  const args = event.args ?? {};
  const str = (key: string): string | undefined => {
    const v = args[key];
    return typeof v === "string" || typeof v === "number" ? String(v) : undefined;
  };
  switch (event.name) {
    case "search": {
      const q = str("query");
      return q ? `Searching “${q}”` : "Searching the manual";
    }
    case "toc":
      return "Checking the manual index";
    case "read_section": {
      const section = str("section");
      const title = str("section_title") ?? str("title");
      if (section && title) return `Reading ${section} ${title}`;
      if (section) return `Reading ${section}`;
      return "Reading a section";
    }
    case "read_page": {
      const page = str("pdf_page") ?? str("page");
      return page ? `Reading page ${page}` : "Reading a page";
    }
    case "lookup_term": {
      const term = str("term");
      return term ? `Looking up “${term}”` : "Looking up a term";
    }
    default:
      return "Consulting the manual";
  }
}

/** Maps the client's raw error strings to the design plan's copy where the
 *  failure mode matches; otherwise surfaces the server-provided detail
 *  as-is. Either way, a stream that ends without done/error is always a
 *  visible failure, never a silently "complete"-looking answer. */
function friendlyError(detail: string): string {
  if (detail.startsWith("Request failed:") || detail.startsWith("Stream read failed:")) {
    return "Couldn't reach the manual. Check your connection and ask again.";
  }
  if (detail.includes("no done/error event")) {
    return "The connection dropped before the answer finished. Ask again.";
  }
  return `Couldn't answer: ${detail}`;
}

export function Chat({ onOpenCitation, chatsOpen, onCloseChats, onOpenSection }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // True while the chat she was in before a refresh is being reopened: asking
  // now would start a new chat that the reopened one then replaces on screen.
  const [restoring, setRestoring] = useState(() => storedThread() !== null);
  const threadId = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const questionRef = useRef<HTMLElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // What the next render should do with the scroll position: "question" puts
  // the question she just asked at the top and leaves it there while the
  // answer streams in below; "end" shows the end of a chat she reopened.
  // Anything else -- every streamed word -- leaves her scroll where it is.
  const scrollIntent = useRef<"question" | "end" | null>(null);
  const pinned = useRef(false);
  // Her last few chats, for the home view. Fetched whenever home shows.
  const [recent, setRecent] = useState<ThreadSummary[]>([]);
  const home = turns.length === 0;

  useEffect(() => {
    if (!home || restoring) return;
    let cancelled = false;
    void fetchThreads()
      .then((t) => !cancelled && setRecent(t.slice(0, 3)))
      .catch(() => !cancelled && setRecent([]));
    return () => {
      cancelled = true;
    };
  }, [home, restoring]);

  useEffect(() => {
    const box = scrollRef.current;
    const spacer = spacerRef.current;
    if (!box || !spacer) return;
    const intent = scrollIntent.current;
    scrollIntent.current = null;
    if (intent === "end") {
      pinned.current = false;
      spacer.style.height = "0px";
      box.scrollTo({ top: box.scrollHeight });
      return;
    }
    const q = questionRef.current;
    if (!pinned.current || !q) return;
    // Room below the question for it to reach the top even while the answer
    // is still short; it shrinks to nothing as the answer grows.
    const boxTop = box.getBoundingClientRect().top;
    const qTop = q.getBoundingClientRect().top - boxTop + box.scrollTop;
    const below = box.scrollHeight - spacer.offsetHeight - qTop;
    spacer.style.height = `${Math.max(0, box.clientHeight - below)}px`;
    if (intent === "question") {
      const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      box.scrollTo({ top: Math.max(0, qTop - 12), behavior: reduce ? "auto" : "smooth" });
    }
  }, [turns]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function openThread(id: string) {
    // Never while an answer is streaming: it would land in the other chat.
    if (busy) return;
    try {
      const messages = await fetchThread(id);
      threadId.current = id;
      storeThread(id);
      scrollIntent.current = "end";
      setTurns(messages.map(toTurn));
    } catch (err) {
      // Forget it only if the server says it's gone (pruned: the last 100 are
      // kept) -- not on flaky cabin wifi, where a retry would find it again.
      if (err instanceof Error && err.message.includes("no such thread")) {
        if (threadId.current === id) threadId.current = null;
        storeThread(null);
      }
    }
    onCloseChats();
  }

  function newChat() {
    if (busy) return;
    threadId.current = null;
    storeThread(null);
    scrollIntent.current = "end";
    setTurns([]);
    onCloseChats();
  }

  // A chat deleted from the panel: if it is the one on screen, clear it
  // without closing the panel she is still working in.
  function chatDeleted(id: string) {
    if (threadId.current !== id) return;
    threadId.current = null;
    storeThread(null);
    scrollIntent.current = "end";
    setTurns([]);
  }

  useEffect(() => {
    const id = storedThread();
    if (id) void openThread(id).finally(() => setRestoring(false));
    // Runs once on mount: reopen the chat she was in before a refresh.
  }, []);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy || restoring) return;

    setInput("");
    setBusy(true);
    scrollIntent.current = "question";
    pinned.current = true;
    setTurns((t) => [
      ...t,
      {
        role: "user",
        body: trimmed,
        citations: [],
        settled: true,
        toolStatus: null,
        errorText: null,
        time: formatClock(new Date()),
      },
      {
        role: "assistant",
        body: "",
        citations: [],
        settled: false,
        toolStatus: null,
        errorText: null,
        time: formatClock(new Date()),
      },
    ]);

    const patchLast = (fn: (t: Turn) => Turn) =>
      setTurns((all) => all.map((t, i) => (i === all.length - 1 ? fn(t) : t)));

    const controller = new AbortController();
    abortRef.current = controller;

    await streamChat(
      trimmed,
      threadId.current,
      {
        onThread: (id) => {
          threadId.current = id;
          storeThread(id);
        },
        onTool: (event) => patchLast((t) => ({ ...t, toolStatus: describeTool(event) })),
        onDelta: (text) => patchLast((t) => ({ ...t, body: t.body + text, toolStatus: null })),
        onCitations: (citations) => patchLast((t) => ({ ...t, citations, settled: true, toolStatus: null })),
        onError: (detail) =>
          patchLast((t) => ({ ...t, errorText: friendlyError(detail), settled: true, toolStatus: null })),
        onDone: () => patchLast((t) => ({ ...t, settled: true, toolStatus: null })),
      },
      controller.signal,
    );
    setBusy(false);
  }

  const lastQuestion = turns.map((t) => t.role).lastIndexOf("user");

  // One question box: in the middle of the home view, then at the foot of
  // the conversation once one has begun.
  function composer(className: string) {
    return (
      <form
        className={className}
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input
          id="purser-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a procedure"
          aria-label="Ask about a procedure"
          disabled={busy || restoring}
          autoComplete="off"
          enterKeyHint="send"
        />
        <button type="submit" className="send" disabled={busy || !input.trim()} aria-label="Send">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
            <path d="M12 4 L12 20 M12 4 L6 10 M12 4 L18 10" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    );
  }

  return (
    <div className="chat">
      <ChatHistory
        open={chatsOpen}
        currentId={threadId.current}
        busy={busy}
        onSelect={(id) => void openThread(id)}
        onNew={newChat}
        onDeleted={chatDeleted}
        onClose={onCloseChats}
      />

      <div className="turns" ref={scrollRef}>
        {home && (
          <div className="home">
            <img className="home-mark" src="/icons/icon-180.png" alt="" width={52} height={52} />
            <h2 className="home-head">What do you need?</h2>
            <p className="home-sub">Answered from the manual, cited to the page.</p>
            {composer("composer composer-home")}
            <div className="home-sections" aria-label="Open the manual at">
              {SECTIONS.map((s) => (
                <button
                  key={s.section}
                  type="button"
                  className="home-section"
                  onClick={() => onOpenSection(s.section)}
                  aria-label={`${s.label}, section ${s.section}`}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    {s.icon}
                  </svg>
                  {s.label}
                </button>
              ))}
            </div>
            {recent.length > 0 && (
              <section className="home-recent" aria-label="Recent chats">
                <h3 className="home-label">Recent</h3>
                <ul>
                  {recent.map((t) => (
                    <li key={t.id}>
                      <button type="button" className="home-recent-row" onClick={() => void openThread(t.id)} disabled={restoring}>
                        <span className="home-recent-title">{t.title || "Untitled chat"}</span>
                        <span className="home-recent-when">{recentWhen(t.updated_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}

        {turns.map((turn, i) => {
          if (turn.role === "user") {
            return (
              <article key={i} className="me" ref={i === lastQuestion ? questionRef : undefined}>
                {turn.body}
              </article>
            );
          }

          // Assistant turn: the thinking chip, the answer bubble, its
          // citations and the timestamp are one visual unit beside the
          // avatar -- never four floating fragments (see the mockup).
          const thinking = !turn.body && !turn.settled;
          const showStamp = !thinking;

          return (
            <article key={i} className="turn">
              <span className="avatar" aria-hidden="true">
                <img src="/icons/icon-32.png" alt="" width={25} height={25} />
              </span>
              <div className="stack">
                {thinking && (
                  <div className="think">
                    <i className="crescent" aria-hidden="true" />
                    <span>{turn.toolStatus ?? "Thinking…"}</span>
                  </div>
                )}

                {turn.body && (
                  <div className="bot">
                    <AnswerMarkdown text={turn.body} />
                  </div>
                )}

                {turn.citations.length > 0 && (
                  <div className="citations">
                    {turn.citations.map((c, j) => (
                      <CitationChip key={j} citation={c} onOpen={onOpenCitation} />
                    ))}
                  </div>
                )}

                {turn.settled && turn.citations.length === 0 && !turn.errorText && (
                  <p className="uncited">Not from the manual.</p>
                )}

                {turn.errorText && <p className="turn-error">{turn.errorText}</p>}

                {showStamp && <span className="stamp">{turn.time}</span>}
              </div>
            </article>
          );
        })}
        <div ref={spacerRef} className="turns-spacer" aria-hidden="true" />
      </div>

      {!home && composer("composer")}
    </div>
  );
}
