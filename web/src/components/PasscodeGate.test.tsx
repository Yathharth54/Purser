import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { login } = vi.hoisted(() => ({ login: vi.fn() }));
vi.mock("../api/client", () => ({ login }));
const { PasscodeGate } = await import("./PasscodeGate");

async function submit(renderer: ReactTestRenderer, value: string) {
  const input = renderer.root.findByType("input");
  await act(async () => input.props.onChange({ target: { value } }));
  const form = renderer.root.findByType("form");
  await act(async () => form.props.onSubmit({ preventDefault() {} }));
}

describe("PasscodeGate", () => {
  beforeEach(() => login.mockReset());

  it("unlocks on the right passcode", async () => {
    login.mockResolvedValue(true);
    const onUnlock = vi.fn();
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<PasscodeGate onUnlock={onUnlock} />);
    });
    await submit(r!, "tulip-42");
    expect(login).toHaveBeenCalledWith("tulip-42");
    expect(onUnlock).toHaveBeenCalledTimes(1);
  });

  it("says so, and stays locked, on a wrong passcode", async () => {
    login.mockResolvedValue(false);
    const onUnlock = vi.fn();
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<PasscodeGate onUnlock={onUnlock} />);
    });
    await submit(r!, "nope");
    expect(onUnlock).not.toHaveBeenCalled();
    expect(JSON.stringify(r!.toJSON())).toContain("That passcode didn't work");
  });

  it("uses a password field, so the passcode is never shown on screen", async () => {
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<PasscodeGate onUnlock={() => {}} />);
    });
    expect(r!.root.findByType("input").props.type).toBe("password");
  });
});
