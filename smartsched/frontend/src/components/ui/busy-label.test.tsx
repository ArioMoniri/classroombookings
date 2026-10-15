import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BUSY_DELAY_MS, BusyButton } from "./busy-label";

function Harness({ busy, onClick }: { busy: boolean; onClick?: () => void }) {
  return (
    <BusyButton busy={busy} busyLabel="Running…" onClick={onClick}>
      Start
    </BusyButton>
  );
}

describe("BusyButton (motion audit T1: busy state that is not motion-only)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    delete document.documentElement.dataset.motion;
  });

  it("idle: plain label, no aria-busy, enabled", () => {
    render(<Harness busy={false} />);
    const b = screen.getByRole("button", { name: "Start" });
    expect(b).not.toHaveAttribute("aria-busy");
    expect(b).not.toHaveAttribute("aria-disabled");
  });

  it("busy: aria-busy at once, the gerund label after 150 ms (no flicker on fast requests)", () => {
    render(<Harness busy />);
    const b = screen.getByRole("button");
    expect(b).toHaveAttribute("aria-busy", "true");
    expect(b).toHaveAccessibleName("Start");
    act(() => vi.advanceTimersByTime(BUSY_DELAY_MS + 1));
    expect(b).toHaveAccessibleName("Running…");
    expect(b.querySelector("[data-busy-glyph=spin]")).not.toBeNull();
  });

  it("busy keeps focus: aria-disabled instead of disabled, and clicks are ignored", async () => {
    vi.useRealTimers();
    const onClick = vi.fn();
    const { rerender } = render(<Harness busy={false} onClick={onClick} />);
    const b = screen.getByRole("button");
    b.focus();
    rerender(<Harness busy onClick={onClick} />);
    expect(b).not.toBeDisabled(); // a disabled focused button is blurred by Chromium
    expect(b).toHaveAttribute("aria-disabled", "true");
    expect(document.activeElement).toBe(b);
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("reduced motion (in-app switch): a static glyph, never a spinner", () => {
    document.documentElement.dataset.motion = "reduced";
    render(<Harness busy />);
    act(() => vi.advanceTimersByTime(BUSY_DELAY_MS + 1));
    const b = screen.getByRole("button");
    expect(b.querySelector("[data-busy-glyph=static]")).not.toBeNull();
    expect(b.querySelector(".animate-spin")).toBeNull();
    expect(b).toHaveAccessibleName("Running…");
  });

  it("returns to the idle label when the work ends", () => {
    const { rerender } = render(<Harness busy />);
    act(() => vi.advanceTimersByTime(BUSY_DELAY_MS + 1));
    rerender(<Harness busy={false} />);
    expect(screen.getByRole("button")).toHaveAccessibleName("Start");
    rerender(<Harness busy />);
    expect(screen.getByRole("button")).toHaveAccessibleName("Start"); // the delay restarts
  });
});
