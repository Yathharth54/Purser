import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { fetchThreads } = vi.hoisted(() => ({ fetchThreads: vi.fn() }));
vi.mock("../api/client", () => ({ fetchThreads }));
const { ChatHistory } = await import("./ChatHistory");

const keys: Record<string, (e: { key: string }) => void> = {};

// Local-time ISO strings relative to now, so the day groups don't depend on
// when (or in which time zone) the suite runs.
function daysBack(n: number, hour = 10): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(hour, 4, 0, 0);
  return d.toISOString();
}

const THREADS = [
  { id: "a", title: "Smoke from the aft lavatory", updated_at: daysBack(0) },
  { id: "b", title: "Oxygen masks dropped", updated_at: daysBack(0, 8) },
  { id: "c", title: "Passenger collapsed", updated_at: daysBack(1) },
  { id: "d", title: "Galley oven smoke on climb", updated_at: daysBack(3) },
  { id: "e", title: "Brace position", updated_at: daysBack(20) },
];

type Props = Partial<React.ComponentProps<typeof ChatHistory>>;

async function render(props: Props = {}): Promise<ReactTestRenderer> {
  let r: ReactTestRenderer;
  await act(async () => {
    r = create(
      <ChatHistory
        open
        currentId="a"
        busy={false}
        onSelect={() => {}}
        onNew={() => {}}
        onClose={() => {}}
        {...props}
      />,
      { createNodeMock: () => ({ focus() {} }) },
    );
  });
  return r!;
}

const text = (r: ReactTestRenderer) => JSON.stringify(r.toJSON());
const rows = (r: ReactTestRenderer) =>
  r.root.findAll((n) => n.type === "button" && String(n.props.className).startsWith("chats-row"));
const labels = (r: ReactTestRenderer) =>
  r.root.findAll((n) => n.props.className === "chats-group-label").map((n) => n.props.children);

describe("ChatHistory", () => {
  beforeEach(() => {
    fetchThreads.mockReset().mockResolvedValue(THREADS);
    vi.stubGlobal("window", {
      ...globalThis.window,
      addEventListener: (t: string, f: (e: { key: string }) => void) => (keys[t] = f),
      removeEventListener: () => {},
    });
    vi.stubGlobal("document", { activeElement: null });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("groups her chats by day, most recent first", async () => {
    const r = await render();
    expect(labels(r)).toEqual(["Today", "Yesterday", "This week", "Earlier"]);
    const t = text(r);
    expect(t.indexOf("Smoke from the aft")).toBeLessThan(t.indexOf("Oxygen masks"));
    expect(t.indexOf("Oxygen masks")).toBeLessThan(t.indexOf("Brace position"));
  });

  it("marks the chat she is in and opens the one she taps", async () => {
    const onSelect = vi.fn();
    const r = await render({ onSelect });
    const current = rows(r).find((b) => b.props["aria-current"] === "true")!;
    expect(current.props.className).toBe("chats-row on");
    expect(text(r)).toContain(" · open now");
    await act(async () => rows(r).find((b) => b.props.className === "chats-row")!.props.onClick());
    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("filters by title as she types and highlights the match", async () => {
    const r = await render();
    const input = r.root.findByProps({ type: "search" });
    await act(async () => input.props.onChange({ target: { value: "SMOKE" } }));
    expect(rows(r)).toHaveLength(2);
    expect(labels(r)).toEqual(["2 chats match"]);
    const marks = r.root.findAllByType("mark").map((m) => m.props.children);
    expect(marks).toEqual(["Smoke", "smoke"]);
    expect(text(r)).toContain("Searching chat titles.");
  });

  it("says when nothing matches, and clears back to the full list", async () => {
    const r = await render();
    await act(async () => r.root.findByProps({ type: "search" }).props.onChange({ target: { value: "ditching" } }));
    expect(rows(r)).toHaveLength(0);
    expect(text(r)).toContain("No chat titles match");
    await act(async () => r.root.findByProps({ "aria-label": "Clear search" }).props.onClick());
    expect(rows(r)).toHaveLength(5);
  });

  it("starts a new chat, but not while an answer is still coming in", async () => {
    const onNew = vi.fn();
    const r = await render({ onNew });
    await act(async () => r.root.findByProps({ className: "chats-new" }).props.onClick());
    expect(onNew).toHaveBeenCalled();
    await act(async () => r.update(
      <ChatHistory open currentId="a" busy onSelect={() => {}} onNew={onNew} onClose={() => {}} />,
    ));
    expect(r.root.findByProps({ className: "chats-new" }).props.disabled).toBe(true);
    expect(rows(r).every((b) => b.props.disabled)).toBe(true);
  });

  it("closes on Escape and on a tap outside", async () => {
    const onClose = vi.fn();
    const r = await render({ onClose });
    act(() => keys.keydown!({ key: "Escape" }));
    await act(async () => r.root.findByProps({ className: "chats-backdrop" }).props.onClick());
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("fetches afresh each time it opens, and not while closed", async () => {
    const r = await render({ open: false });
    expect(fetchThreads).not.toHaveBeenCalled();
    expect(r.root.findAllByProps({ className: "chats-backdrop" })).toHaveLength(0);
    await act(async () => r.update(
      <ChatHistory open currentId="a" busy={false} onSelect={() => {}} onNew={() => {}} onClose={() => {}} />,
    ));
    expect(fetchThreads).toHaveBeenCalledTimes(1);
  });

  it("says so when there are no chats yet", async () => {
    fetchThreads.mockResolvedValue([]);
    expect(text(await render())).toContain("No chats yet");
  });
});
