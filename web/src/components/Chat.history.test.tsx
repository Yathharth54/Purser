import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { fetchThread, streamChat } = vi.hoisted(() => ({ fetchThread: vi.fn(), streamChat: vi.fn() }));
vi.mock("../api/client", () => ({ fetchThread, streamChat, fetchThreads: vi.fn().mockResolvedValue([]) }));
const store: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store[k] ?? null,
  setItem: (k: string, v: string) => (store[k] = v),
  removeItem: (k: string) => delete store[k],
});
const { Chat } = await import("./Chat");

async function render(): Promise<ReactTestRenderer> {
  let r: ReactTestRenderer;
  await act(async () => {
    r = create(<Chat onOpenCitation={() => {}} />, { createNodeMock: () => ({ scrollTo() {} }) });
  });
  await act(async () => {});
  return r!;
}

describe("Chat keeps her place", () => {
  beforeEach(() => {
    for (const k of Object.keys(store)) delete store[k];
    fetchThread.mockReset();
  });

  it("reopens the chat she was in after a refresh", async () => {
    store["purser-thread"] = "t1";
    fetchThread.mockResolvedValue([
      { role: "user", body: "brace position", citations: [], created_at: "2026-09-25T10:00:00+00:00" },
      { role: "assistant", body: "Heads down", citations: [], created_at: "2026-09-25T10:00:05+00:00" },
    ]);
    const text = JSON.stringify((await render()).toJSON());
    expect(fetchThread).toHaveBeenCalledWith("t1");
    expect(text).toContain("brace position");
    expect(text).toContain("Heads down");
  });

  it("forgets a stored chat that no longer exists", async () => {
    store["purser-thread"] = "gone";
    fetchThread.mockRejectedValue(new Error("no such thread"));
    const text = JSON.stringify((await render()).toJSON());
    expect(store["purser-thread"]).toBeUndefined();
    expect(text).toContain("Ask about a procedure");
  });

  it("starts a fresh chat on New", async () => {
    store["purser-thread"] = "t1";
    fetchThread.mockResolvedValue([
      { role: "user", body: "brace position", citations: [], created_at: "2026-09-25T10:00:00+00:00" },
    ]);
    const r = await render();
    await act(async () => r.root.findByProps({ className: "bar-btn new" }).props.onClick());
    expect(store["purser-thread"]).toBeUndefined();
    expect(JSON.stringify(r.toJSON())).not.toContain("brace position");
  });
});
