import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api/client";
import type { Citation, ToolEvent } from "../api/types";
import { CitationChip } from "./CitationChip";

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
}

// Per the approved mockup's empty state (four chips, this exact wording and
// order) -- not the plan's earlier three-chip sketch.
const STARTERS = ["Ditching drill", "Slide raft detach", "Infant restraint", "Smoke in the cabin"];

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

export function Chat({ onOpenCitation }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const threadId = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;

    setInput("");
    setBusy(true);
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

  return (
    <div className="chat">
      <div className="turns" ref={scrollRef}>
        {turns.length === 0 && (
          <div className="empty">
            <h2 className="empty-head">Ask about a procedure</h2>
            <p className="empty-sub">
              Search the Safety and Emergency Procedures Manual, cited to the page.
            </p>
            <div className="starters">
              {STARTERS.map((s) => (
                <button key={s} type="button" className="starter" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => {
          if (turn.role === "user") {
            return (
              <div key={i} className="me">
                {turn.body}
              </div>
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

                {turn.body && <div className="bot">{turn.body}</div>}

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
      </div>

      <form
        className="composer"
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
          disabled={busy}
          autoComplete="off"
          enterKeyHint="send"
        />
        <button type="submit" className="send" disabled={busy || !input.trim()} aria-label="Send">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
            <path d="M12 4 L12 20 M12 4 L6 10 M12 4 L18 10" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </div>
  );
}
