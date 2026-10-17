// Flow-loop round 2, lane A (T-R2-01, R2-A-02 / R2-S-06): the document-level keyboard clearance. Mounted once in the
// app shell, it scrolls a focused page-level field clear of any sticky or fixed bar (the /profile save bar, the
// /find-room search capsule, the tab bar) when the on-screen keyboard shrinks the viewport.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KeyboardClearance, stickyBarsOf } from "@/components/ui/keyboard-clearance";

const rect = (top: number, bottom: number, left = 0, right = 390) => ({ top, bottom, left, right, width: right - left, height: bottom - top, x: left, y: top, toJSON: () => ({}) }) as DOMRect;

describe("T-R2-01: document keyboard clearance", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("scrolls the window by the overlap of a focused field with a sticky bottom bar and a fixed tab bar", () => {
    const { container } = render(
      <div>
        <main>
          <input aria-label="Yeni parola" />
          <div data-testid="save" style={{ position: "sticky" }}>
            <button type="button">Kaydet</button>
          </div>
        </main>
        <div data-testid="tabs" style={{ position: "fixed" }}>
          <nav aria-label="Sekmeler" />
        </div>
        <KeyboardClearance scope="document" />
      </div>,
    );
    const field = container.querySelector("input")!;
    const save = container.querySelector("[data-testid=save]")!;
    const tabs = container.querySelector("[data-testid=tabs]")!;
    // keyboard open: viewport 508 px; the field sits under the save bar (420–480), the tab bar is at 440–508
    vi.spyOn(field, "getBoundingClientRect").mockReturnValue(rect(430, 474));
    vi.spyOn(save, "getBoundingClientRect").mockReturnValue(rect(420, 480));
    vi.spyOn(tabs, "getBoundingClientRect").mockReturnValue(rect(440, 508));
    field.scrollIntoView = vi.fn();
    const scrollBy = vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
    expect(stickyBarsOf(document.body, field).map((b) => b.getAttribute("data-testid"))).toEqual(["save", "tabs"]);
    field.focus();
    fireEvent.focusIn(field);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(field.scrollIntoView).toHaveBeenCalledWith({ block: "nearest", inline: "nearest" });
    // the save bar is the higher bar: field.bottom (474) + 8 − save.top (420) = 62
    expect(scrollBy).toHaveBeenCalledWith({ top: 62, behavior: "instant" });
  });

  it("leaves fields inside a popup to the popup's own clearance", () => {
    const { container } = render(
      <div>
        <div data-slot="sheet-content">
          <input aria-label="Not" />
        </div>
        <KeyboardClearance scope="document" />
      </div>,
    );
    const field = container.querySelector("input")!;
    field.scrollIntoView = vi.fn();
    field.focus();
    fireEvent.focusIn(field);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(field.scrollIntoView).not.toHaveBeenCalled();
  });

  it("is mounted once in the app shell for the document scroller", () => {
    expect(readFileSync(join(process.cwd(), "src/components/shell/app-shell.tsx"), "utf8")).toContain('<KeyboardClearance scope="document" />');
  });
});
