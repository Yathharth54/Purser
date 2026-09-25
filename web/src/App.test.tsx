import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { fetchSession } = vi.hoisted(() => ({ fetchSession: vi.fn() }));
vi.mock("./api/client", () => ({ fetchSession, login: vi.fn(), LOCKED_EVENT: "purser:locked" }));
vi.mock("./components/Chat", () => ({ Chat: () => <p>CHAT</p> }));
vi.mock("./components/TocBrowser", () => ({ TocBrowser: () => <p>TOC</p> }));
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
});
