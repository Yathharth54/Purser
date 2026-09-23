import { describe, expect, it, vi } from "vitest";
import { parseSSERecord, splitSSERecords, streamChat } from "./client";
import type { StreamHandlers } from "./client";
import type { Citation } from "./types";

describe("splitSSERecords", () => {
  it("splits complete CRLF-delimited records and keeps a trailing partial one", () => {
    const buffer = 'event: thread\r\ndata: {"thread_id":"abc"}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n';
    const { records, rest } = splitSSERecords(buffer);
    expect(records).toEqual(['event: thread\ndata: {"thread_id":"abc"}', "event: done\ndata: {}"]);
    expect(rest).toBe("");
  });

  it("keeps an incomplete trailing record in `rest`", () => {
    const { records, rest } = splitSSERecords('event: delta\r\ndata: {"text":"hel');
    expect(records).toEqual([]);
    expect(rest).toBe('event: delta\ndata: {"text":"hel');
  });

  it("recovers a record whose delimiter is split across two network chunks", () => {
    // "\r\n\r\n" split right down the middle -- the exact case a naive
    // per-chunk `chunk.split("\n\n")` loses, because "\r\n\r\n" contains no
    // literal "\n\n" substring at all.
    const chunk1 = 'event: citations\r\ndata: [{"pdf_page":1}]\r\n\r';
    const chunk2 = '\nevent: done\r\ndata: {}\r\n\r\n';

    let buffer = "";
    const seen: string[] = [];

    buffer += chunk1;
    let split = splitSSERecords(buffer);
    seen.push(...split.records);
    buffer = split.rest;

    buffer += chunk2;
    split = splitSSERecords(buffer);
    seen.push(...split.records);
    buffer = split.rest;

    expect(seen).toEqual(['event: citations\ndata: [{"pdf_page":1}]', "event: done\ndata: {}"]);
    expect(buffer).toBe("");
  });

  it("recovers a record split mid-data across two chunks", () => {
    const chunk1 = 'event: delta\r\ndata: {"te';
    const chunk2 = 'xt":"hello"}\r\n\r\n';

    let buffer = chunk1;
    let split = splitSSERecords(buffer);
    expect(split.records).toEqual([]); // nothing complete yet
    buffer = split.rest + chunk2;
    split = splitSSERecords(buffer);
    expect(split.records).toEqual(['event: delta\ndata: {"text":"hello"}']);
  });
});

describe("parseSSERecord", () => {
  it("parses event and data lines", () => {
    expect(parseSSERecord('event: tool\ndata: {"name":"search"}')).toEqual({
      event: "tool",
      data: '{"name":"search"}',
    });
  });

  it("defaults to a message event and joins multiple data lines", () => {
    expect(parseSSERecord("data: a\ndata: b")).toEqual({ event: "message", data: "a\nb" });
  });

  it("returns null for a record with no data line", () => {
    expect(parseSSERecord("event: ping")).toBeNull();
  });
});

function fakeHandlers(): StreamHandlers & {
  calls: { thread: string[]; tool: unknown[]; delta: string[]; citations: Citation[][]; error: string[]; done: number };
} {
  const calls = { thread: [] as string[], tool: [] as unknown[], delta: [] as string[], citations: [] as Citation[][], error: [] as string[], done: 0 };
  return {
    calls,
    onThread: (id) => calls.thread.push(id),
    onTool: (e) => calls.tool.push(e),
    onDelta: (t) => calls.delta.push(t),
    onCitations: (c) => calls.citations.push(c),
    onError: (d) => calls.error.push(d),
    onDone: () => {
      calls.done += 1;
    },
  };
}

function streamResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
  return new Response(body, { status, headers: { "content-type": "text/event-stream" } });
}

describe("streamChat", () => {
  it("delivers thread/tool/delta/citations/done even when a record's delimiter is split across chunks", async () => {
    const chunk1 =
      'event: thread\r\ndata: {"thread_id":"t1"}\r\n\r\n' +
      'event: tool\r\ndata: {"name":"search","args":{"query":"ditching"}}\r\n\r\n' +
      'event: delta\r\ndata: {"text":"answer body"}\r\n\r' /* split delimiter here */;
    const chunk2 =
      '\nevent: citations\r\ndata: [{"pdf_page":594,"part":"PART FOUR","section":"4.4","section_title":"Evacuations","page_in_section":28,"revision":null,"effective":"2023-05-18","text":"  leading space matters","label":"PART FOUR §4.4 p.28"}]\r\n\r\n' +
      "event: done\r\ndata: {}\r\n\r\n";

    vi.stubGlobal("fetch", vi.fn(async () => streamResponse([chunk1, chunk2])));

    const h = fakeHandlers();
    await streamChat("What is the ditching procedure?", null, h);

    expect(h.calls.thread).toEqual(["t1"]);
    expect(h.calls.tool).toEqual([{ name: "search", args: { query: "ditching" } }]);
    expect(h.calls.delta).toEqual(["answer body"]);
    expect(h.calls.citations).toHaveLength(1);
    expect(h.calls.citations[0]?.[0]?.text).toBe("  leading space matters");
    expect(h.calls.done).toBe(1);
    expect(h.calls.error).toEqual([]);

    vi.unstubAllGlobals();
  });

  it("surfaces an error when the stream closes without a done or error event", async () => {
    const chunk = 'event: thread\r\ndata: {"thread_id":"t1"}\r\n\r\nevent: tool\r\ndata: {"name":"search","args":{}}\r\n\r\n';
    vi.stubGlobal("fetch", vi.fn(async () => streamResponse([chunk])));

    const h = fakeHandlers();
    await streamChat("hi", null, h);

    expect(h.calls.done).toBe(0);
    expect(h.calls.error).toHaveLength(1);
    expect(h.calls.error[0]).toMatch(/no done\/error event/i);

    vi.unstubAllGlobals();
  });

  it("surfaces a non-OK response's detail without calling onDone", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "thread not found" }), { status: 404 })),
    );

    const h = fakeHandlers();
    await streamChat("hi", "unknown-thread", h);

    expect(h.calls.error).toEqual(["thread not found"]);
    expect(h.calls.done).toBe(0);

    vi.unstubAllGlobals();
  });
});
