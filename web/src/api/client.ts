import type {
  Citation,
  ReadingPage,
  ThreadMessage,
  ThreadSummary,
  TocNode,
  ToolEvent,
} from "./types";

/**
 * Typed client for the Purser API, per
 * .superpowers/sdd/2026-09-22-purser/api-contract.md (authoritative over the
 * task-17 brief). Base path is "/api" -- same-origin in production (FastAPI
 * serves web/dist), proxied by Vite in dev (see vite.config.ts).
 */

export interface StreamHandlers {
  onThread: (threadId: string) => void;
  /** Retrieval progress. Additive to the brief -- render as transient
   *  progress, replaced in place, not appended to the transcript. */
  onTool: (event: ToolEvent) => void;
  /** Currently fires once with the whole answer body (not token-by-token),
   *  but the name is kept stable for when streaming is reintroduced --
   *  always append what you're given, never replace. */
  onDelta: (text: string) => void;
  /** A bare JSON list, per the contract -- not `{ citations: [...] }`. An
   *  empty list is normal (general conversation), not an error. */
  onCitations: (citations: Citation[]) => void;
  onError: (detail: string) => void;
  onDone: () => void;
}

interface ParsedSSERecord {
  event: string;
  data: string;
}

/**
 * Split an accumulated SSE buffer into complete, blank-line-delimited
 * records plus whatever partial record is left at the end.
 *
 * This backend emits CRLF line endings ("\r\n"), so a delimiter is
 * "\r\n\r\n" -- a literal `buffer.split("\n\n")` never matches that (there
 * is no "\n\n" substring inside "\r\n\r\n") and silently drops every event.
 * Normalising line endings first, on the whole accumulated buffer -- not
 * per network chunk -- also makes this correct when a chunk boundary lands
 * in the middle of a record or even mid-delimiter: incomplete text always
 * stays in `rest` for the next call rather than being parsed early.
 */
export function splitSSERecords(buffer: string): { records: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  return { records: parts, rest };
}

/** Parse one SSE record's `event:`/`data:` lines. Multiple `data:` lines are
 *  joined with "\n", per the SSE spec. Returns null for a record with no
 *  `data:` line (e.g. a stray blank chunk). */
export function parseSSERecord(record: string): ParsedSSERecord | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of record.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/**
 * POST /api/chat and read the SSE stream. Uses `fetch` + a `ReadableStream`
 * reader rather than `EventSource`, which cannot issue a POST.
 *
 * The stream always ends in a `done` or `error` event. If the response body
 * closes without either -- a dropped connection, a proxy timeout, a server
 * crash mid-answer -- that is a failure and is surfaced via `onError`; it
 * never resolves silently. A flight attendant reading a half-delivered
 * procedure with no error indicator is exactly what this guards against.
 */
export async function streamChat(
  message: string,
  threadId: string | null,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let settled = false;
  const fail = (detail: string): void => {
    if (settled) return;
    settled = true;
    handlers.onError(detail);
  };
  const succeed = (): void => {
    if (settled) return;
    settled = true;
    handlers.onDone();
  };

  let res: Response;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: threadId }),
      signal,
    });
  } catch (err) {
    fail(`Request failed: ${err instanceof Error ? err.message : String(err)}`);
    return;
  }

  if (res.status === 401) announceLocked();
  if (!res.ok || !res.body) {
    let detail = `Request failed (${res.status})`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Response wasn't JSON; keep the generic message.
    }
    fail(detail);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handleRecord = (record: string): void => {
    if (settled || record.trim().length === 0) return;
    const parsed = parseSSERecord(record);
    if (!parsed) return;

    let payload: unknown;
    try {
      payload = JSON.parse(parsed.data);
    } catch {
      fail(`Malformed "${parsed.event}" event from server`);
      return;
    }

    switch (parsed.event) {
      case "thread":
        handlers.onThread((payload as { thread_id: string }).thread_id);
        break;
      case "tool":
        handlers.onTool(payload as ToolEvent);
        break;
      case "delta":
        handlers.onDelta((payload as { text: string }).text);
        break;
      case "citations":
        // Bare list -- see the contract note above.
        handlers.onCitations(payload as Citation[]);
        break;
      case "error":
        fail((payload as { detail: string }).detail);
        break;
      case "done":
        succeed();
        break;
      default:
        // Forward-compatible: an event name we don't know yet is ignored
        // rather than failing the whole stream.
        break;
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { records, rest } = splitSSERecords(buffer);
      buffer = rest;
      for (const record of records) {
        handleRecord(record);
        if (settled) break;
      }
      if (settled) break;
    }
  } catch (err) {
    fail(`Stream read failed: ${err instanceof Error ? err.message : String(err)}`);
    return;
  }

  if (settled) return;

  // The body closed without a `done`/`error` event having been seen yet.
  // Flush the decoder and try the leftover buffer as one last record, in
  // case the final event wasn't followed by a trailing blank line.
  buffer += decoder.decode();
  const { records, rest } = splitSSERecords(buffer);
  for (const record of [...records, rest]) {
    handleRecord(record);
    if (settled) break;
  }

  if (!settled) {
    fail("Connection closed before the response finished (no done/error event received)");
  }
}

/**
 * Fired on `window` whenever the server answers 401: the passcode cookie is
 * missing, expired, or was invalidated by a passcode change. App listens and
 * shows the passcode screen again, from wherever she was.
 */
export const LOCKED_EVENT = "purser:locked";

function announceLocked(): void {
  window.dispatchEvent(new Event(LOCKED_EVENT));
}

export interface SessionState {
  authenticated: boolean;
  required: boolean;
}

export const fetchSession = (): Promise<SessionState> => getJSON<SessionState>("/api/session");

/** True if the passcode was accepted; the server then sets the session cookie. */
export async function login(passcode: string): Promise<boolean> {
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passcode }),
  });
  return res.ok;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (res.status === 401) announceLocked();
  if (!res.ok) {
    let detail = `${path} failed (${res.status})`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // Not JSON; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const fetchToc = (): Promise<TocNode[]> => getJSON<TocNode[]>("/api/toc");

/**
 * GET /api/section/{section} -- every `ReadingPage` in the section, in
 * order, no bounds. Task 7 moved this endpoint's response shape to
 * `ReadingPage[]` (whole pages, parsed into `blocks`) and the endpoint
 * itself already returns the entire section with no server-side cap; this
 * client used to also accept `pageFrom`/`pageTo` and the one caller
 * (`TocBrowser`) used them to request only the first few pages, which was
 * the actual bug (see that component). Nothing needs a partial read
 * client-side, so this stays a single-argument call -- no page-bound
 * parameters exist here to be silently reintroduced as a cap.
 */
export const fetchSection = (section: string): Promise<ReadingPage[]> =>
  getJSON<ReadingPage[]>(`/api/section/${encodeURIComponent(section)}`);

/** Not fetched here -- returns the same-origin/proxied URL for an <img src>. */
export const pageImageUrl = (pdfPage: number): string => `/api/page/${pdfPage}/image`;

export const fetchThreads = (): Promise<ThreadSummary[]> => getJSON<ThreadSummary[]>("/api/threads");

/** Delete a chat for good. One that is already gone counts as deleted. */
export async function deleteThread(threadId: string): Promise<void> {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  if (res.status === 401) announceLocked();
  if (!res.ok && res.status !== 404) throw new Error(`Couldn't delete this chat (${res.status})`);
}

export const fetchThread = (threadId: string): Promise<ThreadMessage[]> =>
  getJSON<ThreadMessage[]>(`/api/threads/${encodeURIComponent(threadId)}`);
