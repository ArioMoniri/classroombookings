/** T-R1-12: focus lands on the booked cell even when the grid replaces the cell after the first attempt. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cellSelector, focusAfter } from "./focus-after";

const slot = { date: "2026-02-19", period_id: 3, room_id: 7 };
function cell(): HTMLButtonElement {
  const b = document.createElement("button");
  b.dataset.slotKey = `${slot.date}|${slot.period_id}|${slot.room_id}`;
  b.textContent = "A 102";
  return b;
}

describe("focusAfter", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = "";
  });
  afterEach(() => vi.useRealTimers());

  it("waits for the target instead of a fixed delay: a re-keyed cell gets the focus back", () => {
    const grid = document.createElement("div");
    document.body.append(grid);
    grid.append(cell());
    focusAfter([cellSelector(slot)]);
    vi.advanceTimersByTime(330);
    expect(document.activeElement?.getAttribute("data-slot-key")).toBe("2026-02-19|3|7");
    // the grid re-renders after the request: the focused cell is replaced, focus drops to <body>
    grid.replaceChildren(cell());
    expect(document.activeElement).toBe(document.body);
    vi.advanceTimersByTime(100);
    expect(document.activeElement?.getAttribute("data-slot-key")).toBe("2026-02-19|3|7");
    expect(document.activeElement?.isConnected).toBe(true);
  });

  it("moves from the fallback to the cell once the cell appears", () => {
    const main = document.createElement("main");
    main.id = "main";
    main.tabIndex = -1;
    document.body.append(main);
    focusAfter([cellSelector(slot)]);
    vi.advanceTimersByTime(330);
    expect(document.activeElement).toBe(main);
    main.append(cell());
    vi.advanceTimersByTime(100);
    expect(document.activeElement?.getAttribute("data-slot-key")).toBe("2026-02-19|3|7");
  });

  it("stops watching when the user presses a key", () => {
    const b = cell();
    document.body.append(b);
    focusAfter([cellSelector(slot)]);
    vi.advanceTimersByTime(330);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
    b.blur();
    vi.advanceTimersByTime(200);
    expect(document.activeElement).toBe(document.body);
  });
});
