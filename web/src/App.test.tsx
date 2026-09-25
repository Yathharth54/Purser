import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { fetchSession } = vi.hoisted(() => ({ fetchSession: vi.fn() }));
vi.mock("./api/client", () => ({ fetchSession, login: vi.fn(), LOCKED_EVENT: "purser:locked" }));
vi.mock("./components/Chat", () => ({
  Chat: ({ chatsOpen, onOpenSection }: { chatsOpen: boolean; onOpenSection: (s: string) => void }) => (
    <p className="chat-mock" onClick={() => onOpenSection("4.4")}>
      {chatsOpen ? "CHAT+PANEL" : "CHAT"}
    </p>
  ),
}));
vi.mock("./components/TocBrowser", () => ({
  TocBrowser: ({ openSection }: { openSection: string | null }) => <p>{`TOC:${openSection ?? "none"}`}</p>,
}));
vi.mock("./components/PageDrawer", () => ({ PageDrawer: () => null }));
const listeners: Record<string, () => void> = {};
vi.stubGlobal("window", {
  ...globalThis.window,
  localStorage: { getItem: () => null, setItem: () => {} },
  matchMedia: () => ({ matches: false }),
  addEventListener: (t: string, f: () => void) => (listeners[t] = f),
  removeEventListener: () => {},
});
vi.stubGlobal("document", { documentElement: { dataset: {} } });
const { default: App } = await import("./App");

async function render(): Promise<ReactTestRenderer> {
  let r: ReactTestRenderer;
  await act(async () => {
    r = create(<App />);
  });
  await act(async () => {});
  return r!;
}

describe("App passcode gate", () => {
  beforeEach(() => fetchSession.mockReset());

  it("shows only the passcode screen while locked", async () => {
    fetchSession.mockResolvedValue({ authenticated: false, required: true });
    const text = JSON.stringify((await render()).toJSON());
    expect(text).toContain("Enter passcode");
    expect(text).not.toContain("CHAT");
  });

  it("shows the app once unlocked", async () => {
    fetchSession.mockResolvedValue({ authenticated: true, required: true });
    const text = JSON.stringify((await render()).toJSON());
    expect(text).toContain("CHAT");
    expect(text).not.toContain("Enter passcode");
  });

  it("returns to the passcode screen when a request is refused", async () => {
    fetchSession.mockResolvedValue({ authenticated: true, required: true });
    const r = await render();
    await act(async () => listeners["purser:locked"]!());
    expect(JSON.stringify(r.toJSON())).toContain("Enter passcode");
  });
  it("says it's opening while the server wakes up, instead of a blank page", async () => {
    let wake: (v: unknown) => void = () => {};
    fetchSession.mockReturnValue(new Promise((res) => (wake = res)));
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<App />);
    });
    const text = JSON.stringify(r!.toJSON());
    expect(text).toContain("Opening the manual");
    expect(text).not.toContain("CHAT");
    await act(async () => wake({ authenticated: true, required: true }));
    act(() => r!.unmount());
  });

  it("opens her chats from the header, switching back to Ask from Manual", async () => {
    fetchSession.mockResolvedValue({ authenticated: true, required: true });
    const r = await render();
    await act(async () => r.root.findByProps({ id: "tab-manual" }).props.onClick());
    const chats = r.root.findByProps({ "aria-label": "Your chats" });
    expect(chats.props["aria-expanded"]).toBe(false);
    await act(async () => chats.props.onClick());
    expect(r.root.findByProps({ id: "tab-chat" }).props["aria-selected"]).toBe(true);
    expect(r.root.findByProps({ "aria-label": "Your chats" }).props["aria-expanded"]).toBe(true);
    expect(JSON.stringify(r.toJSON())).toContain("CHAT+PANEL");
  });

  it("has no chats button behind the passcode screen", async () => {
    fetchSession.mockResolvedValue({ authenticated: false, required: true });
    const r = await render();
    expect(r.root.findAllByProps({ "aria-label": "Your chats" })).toHaveLength(0);
  });

  it("opens a manual section asked for from the home screen", async () => {
    fetchSession.mockResolvedValue({ authenticated: true, required: true });
    const r = await render();
    await act(async () => r.root.findByProps({ className: "chat-mock" }).props.onClick());
    expect(r.root.findByProps({ id: "tab-manual" }).props["aria-selected"]).toBe(true);
    expect(JSON.stringify(r.toJSON())).toContain("TOC:4.4");
  });

  it("shows the passcode screen as a cover, with no app header above it", async () => {
    fetchSession.mockResolvedValue({ authenticated: false, required: true });
    const r = await render();
    expect(r.root.findAllByProps({ className: "app-head" })).toHaveLength(0);
    expect(JSON.stringify(r.toJSON())).toContain("Safety and Emergency Procedures Manual");
  });
});
