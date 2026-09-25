import { describe, expect, it, vi } from "vitest";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const { fetchThreads } = vi.hoisted(() => ({ fetchThreads: vi.fn() }));
vi.mock("../api/client", () => ({ fetchThreads }));
const { ChatHistory } = await import("./ChatHistory");

describe("ChatHistory", () => {
  it("lists her chats, most recent first, and opens the one she taps", async () => {
    fetchThreads.mockResolvedValue([
      { id: "b", title: "brace position", updated_at: "2026-09-25T10:00:00+00:00" },
      { id: "a", title: "slide raft detach", updated_at: "2026-09-24T09:00:00+00:00" },
    ]);
    const onSelect = vi.fn();
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<ChatHistory currentId="a" onSelect={onSelect} onClose={() => {}} />);
    });
    const rows = r!.root.findAllByProps({ className: "hist-row" }).concat(
      r!.root.findAllByProps({ className: "hist-row on" }),
    );
    expect(rows).toHaveLength(2);
    const text = JSON.stringify(r!.toJSON());
    expect(text.indexOf("brace position")).toBeLessThan(text.indexOf("slide raft detach"));
    await act(async () => rows.find((x) => x.props.className === "hist-row")!.props.onClick());
    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("says so when there are no chats yet", async () => {
    fetchThreads.mockResolvedValue([]);
    let r: ReactTestRenderer;
    await act(async () => {
      r = create(<ChatHistory currentId={null} onSelect={() => {}} onClose={() => {}} />);
    });
    expect(JSON.stringify(r!.toJSON())).toContain("No chats yet");
  });
});
