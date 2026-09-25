import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchSession, fetchToc, LOCKED_EVENT, login } from "./client";

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("passcode client", () => {
  it("reports whether this device is unlocked", async () => {
    vi.stubGlobal("fetch", respond(200, { authenticated: false, required: true }));
    expect(await fetchSession()).toEqual({ authenticated: false, required: true });
  });

  it("returns true for the right passcode and false for a wrong one", async () => {
    vi.stubGlobal("fetch", respond(200, { ok: true }));
    expect(await login("tulip-42")).toBe(true);
    vi.stubGlobal("fetch", respond(401, { detail: "wrong passcode" }));
    expect(await login("nope")).toBe(false);
  });

  it("announces a lock when any request comes back 401", async () => {
    vi.stubGlobal("fetch", respond(401, { detail: "passcode required" }));
    const dispatch = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: dispatch });
    await expect(fetchToc()).rejects.toThrow();
    expect(dispatch).toHaveBeenCalledTimes(1);
    expect((dispatch.mock.calls[0]![0] as Event).type).toBe(LOCKED_EVENT);
  });
});
