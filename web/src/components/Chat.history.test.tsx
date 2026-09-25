import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { fetchThread, streamChat } = vi.hoisted(() => ({ fetchThread: vi.fn(), streamChat: vi.fn() }));
const { fetchThreads } = vi.hoisted(() => ({ fetchThreads: vi.fn() }));
vi.mock("../api/client", () => ({ fetchThread, streamChat, fetchThreads }));
const store: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store[k] ?? null,
  setItem: (k: string, v: string) => (store[k] = v),
  removeItem: (k: string) => delete store[k],
});
const { Chat } = await import("./Chat");

/** Stand-ins for the DOM nodes Chat measures. The conversation box records
 *  where it was asked to scroll; the newest question sits 300px down it. */
const scrolls: { top: number }[] = [];
function nodeMock(el: { type: unknown; props: { className?: string } }) {
  const base = { style: {} as Record<string, string>, offsetHeight: 0, scrollTop: 0 };
  if (el.props.className === "turns") {
    return {
      ...base,
      clientHeight: 600,
      scrollHeight: 900,
      getBoundingClientRect: () => ({ top: 100 }),
      scrollTo: (o: { top: number }) => scrolls.push(o),
    };
  }
  if (el.props.className === "me") return { ...base, getBoundingClientRect: () => ({ top: 400 }) };
  return { ...base, focus() {}, scrollTo() {} };
}

async function render(): Promise<ReactTestRenderer> {
  let r: ReactTestRenderer;
  await act(async () => {
    r = create(<Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={() => {}} onOpenSection={() => {}} />, { createNodeMock: nodeMock });
  });
  await act(async () => {});
  return r!;
}

describe("Chat keeps her place", () => {
  beforeEach(() => {
    for (const k of Object.keys(store)) delete store[k];
    fetchThread.mockReset();
    fetchThreads.mockReset().mockResolvedValue([]);
    scrolls.length = 0;
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
      r.update(<Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={onCloseChats} onOpenSection={() => {}} />),
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
      r = create(<Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={() => {}} onOpenSection={() => {}} />, { createNodeMock: nodeMock });
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

  it("keeps her question in view instead of following the answer down", async () => {
    let stream: { onDelta: (t: string) => void } | null = null;
    streamChat.mockImplementation((_m: string, _t: unknown, handlers: typeof stream) => {
      stream = handlers;
      return new Promise(() => {});
    });
    const r = await render();
    scrolls.length = 0;
    await act(async () => r.root.findByProps({ id: "purser-input" }).props.onChange({ target: { value: "brace" } }));
    await act(async () => r.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    // Question 300px down the box: brought to the top, less a 12px margin.
    expect(scrolls).toEqual([{ top: 288, behavior: "smooth" }]);
    await act(async () => stream!.onDelta("Heads down, "));
    await act(async () => stream!.onDelta("stay down."));
    expect(scrolls).toHaveLength(1); // streamed words never move her
  });

  it("shows the end of a chat she reopens", async () => {
    store["purser-thread"] = "t1";
    fetchThread.mockResolvedValue([
      { role: "user", body: "brace position", citations: [], created_at: "2026-09-25T10:00:00+00:00" },
    ]);
    await render();
    expect(scrolls).toEqual([{ top: 900 }]);
  });

  it("clears the screen when the open chat is deleted from the panel", async () => {
    store["purser-thread"] = "t1";
    fetchThread.mockResolvedValue([
      { role: "user", body: "brace position", citations: [], created_at: "2026-09-25T10:00:00+00:00" },
    ]);
    const r = await render();
    const history = r.root.findByProps({ onNew: r.root.findByProps({ className: "chats-new" }).props.onClick });
    await act(async () => history.props.onDeleted("other"));
    expect(JSON.stringify(r.toJSON())).toContain("brace position");
    await act(async () => history.props.onDeleted("t1"));
    expect(JSON.stringify(r.toJSON())).not.toContain("brace position");
    expect(store["purser-thread"]).toBeUndefined();
  });

  it("opens on a home view: the question box, the emergency chapters and her last chats", async () => {
    fetchThreads.mockResolvedValue([
      { id: "a", title: "Smoke from the aft lavatory", updated_at: new Date().toISOString() },
      { id: "b", title: "Oxygen masks dropped", updated_at: new Date().toISOString() },
      { id: "c", title: "Passenger collapsed", updated_at: new Date().toISOString() },
      { id: "d", title: "Fourth, not shown", updated_at: new Date().toISOString() },
    ]);
    fetchThread.mockResolvedValue([
      { role: "user", body: "smoke?", citations: [], created_at: "2026-09-25T10:00:00+00:00" },
    ]);
    const onOpenSection = vi.fn();
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(
        <Chat onOpenCitation={() => {}} chatsOpen={false} onCloseChats={() => {}} onOpenSection={onOpenSection} />,
        { createNodeMock: nodeMock },
      );
    });
    await act(async () => {});
    const text = JSON.stringify(r!.toJSON());
    expect(text).toContain("What do you need?");
    expect(r!.root.findByType("form").props.className).toBe("composer composer-home");
    expect(r!.root.findAllByProps({ className: "home-recent-row" })).toHaveLength(3);
    expect(text).not.toContain("Fourth, not shown");

    await act(async () => r!.root.findByProps({ "aria-label": "Evacuations, section 4.4" }).props.onClick());
    expect(onOpenSection).toHaveBeenCalledWith("4.4");

    await act(async () => r!.root.findAllByProps({ className: "home-recent-row" })[0]!.props.onClick());
    expect(fetchThread).toHaveBeenCalledWith("a");
    // A chat on screen: no home view, and the question box back at the foot.
    expect(JSON.stringify(r!.toJSON())).not.toContain("What do you need?");
    expect(r!.root.findByType("form").props.className).toBe("composer");
  });
});
