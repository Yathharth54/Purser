import { describe, expect, it, vi } from "vitest";
import { act, create } from "react-test-renderer";
import type { Citation } from "../api/types";

vi.mock("../api/client", () => ({
  pageImageUrl: (n: number) => `/api/page/${n}/image`,
  LOCKED_EVENT: "purser:locked",
}));
const { PageDrawer } = await import("./PageDrawer");

const CITE = { pdf_page: 597, label: "PART FOUR §4.4 p.31", text: "x", blocks: [] } as unknown as Citation;

describe("PageDrawer", () => {
  it("returns to the passcode screen when the page image is refused", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    const dispatch = vi.fn();
    vi.stubGlobal("window", { ...globalThis.window, dispatchEvent: dispatch, addEventListener() {}, removeEventListener() {} });
    vi.stubGlobal("document", { ...globalThis.document, activeElement: null, body: { style: {} }, addEventListener() {}, removeEventListener() {} });
    await act(async () => {
      create(<PageDrawer citation={CITE} onClose={() => {}} />, { createNodeMock: () => ({ focus() {} }) });
    });
    await act(async () => {});
    expect(dispatch.mock.calls.some(([e]) => (e as Event).type === "purser:locked")).toBe(true);
    vi.unstubAllGlobals();
  });
});
