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
    r = create(<Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={() => {}} />, { createNodeMock: () => ({ scrollTo() {} }) });
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
    await act(async () => r.root.findByProps({ className: "chats-new" }).props.onClick());
    expect(store["purser-thread"]).toBeUndefined();
    expect(JSON.stringify(r.toJSON())).not.toContain("brace position");
  });

  it("closes the chats panel once she picks a chat", async () => {
    fetchThread.mockResolvedValue([]);
    const onCloseChats = vi.fn();
    const r = await render();
    await act(async () =>
      r.update(<Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={onCloseChats} />),
    );
    await act(async () => r.root.findByProps({ className: "chats-new" }).props.onClick());
    expect(onCloseChats).toHaveBeenCalled();
  });

  it("keeps the saved chat when the network, not the server, failed", async () => {
    store["purser-thread"] = "t1";
    fetchThread.mockRejectedValue(new Error("Failed to fetch"));
    await render();
    expect(store["purser-thread"]).toBe("t1");
  });

  it("blocks asking until the reopened chat has loaded", async () => {
    store["purser-thread"] = "t1";
    let finish: (v: unknown) => void = () => {};
    fetchThread.mockReturnValue(new Promise((res) => (finish = res)));
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={() => {}} />, { createNodeMock: () => ({ scrollTo() {} }) });
    });
    expect(r!.root.findByProps({ id: "purser-input" }).props.disabled).toBe(true);
    await act(async () => finish([]));
    expect(r!.root.findByProps({ id: "purser-input" }).props.disabled).toBe(false);
  });

  it("won't switch chats while an answer is still coming in", async () => {
    streamChat.mockReturnValue(new Promise(() => {}));
    const r = await render();
    await act(async () => r.root.findByProps({ id: "purser-input" }).props.onChange({ target: { value: "brace" } }));
    await act(async () => r.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    expect(r.root.findByProps({ className: "chats-new" }).props.disabled).toBe(true);
  });
});
