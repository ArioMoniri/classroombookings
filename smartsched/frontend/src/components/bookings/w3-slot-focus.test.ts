/** R3-S-05 (W3-SLOT): after cancelling from a My bookings row, focus goes to the next row (or the previous one, or the
 *  list heading), never to <body>, even when the cancelled row leaves the list after the refetch. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { focusAfter } from "./focus-after";
import { rowFocusAfterRemoval, rowIndexOf } from "./my-bookings-model";

function list(ids: number[]) {
  document.body.innerHTML = `<h2 id="mine-list" tabindex="-1" data-focus-fallback>Liste</h2><ul data-testid="booking-list">${ids
    .map((id) => `<li data-booking-ids="${id}"><button data-row-open>${id}</button></li>`)
    .join("")}</ul>`;
}

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("rowFocusAfterRemoval", () => {
  it("finds the row of a booking (any of its period ids)", () => {
    document.body.innerHTML = `<ul data-testid="booking-list"><li data-booking-ids="1,2"></li><li data-booking-ids="7"></li></ul>`;
    expect(rowIndexOf(2)).toBe(0);
    expect(rowIndexOf(7)).toBe(1);
    expect(rowIndexOf(99)).toBe(-1);
  });

  it("focuses the row that takes the cancelled row's place once it is gone", async () => {
    vi.useFakeTimers();
    list([10, 11, 12]);
    focusAfter(rowFocusAfterRemoval(rowIndexOf(11)), 10, 2000);
    await vi.advanceTimersByTimeAsync(20);
    // the refetch drops row 11
    document.querySelector('[data-booking-ids="11"]')!.remove();
    await vi.advanceTimersByTimeAsync(400);
    expect(document.activeElement?.textContent).toBe("12");
  });

  it("the last row falls back to the previous row, an emptied list to the heading", async () => {
    vi.useFakeTimers();
    list([10]);
    focusAfter(rowFocusAfterRemoval(rowIndexOf(10)), 10, 2000);
    await vi.advanceTimersByTimeAsync(20);
    document.querySelector('[data-booking-ids="10"]')!.remove();
    await vi.advanceTimersByTimeAsync(400);
    expect(document.activeElement?.id).toBe("mine-list");
    expect(document.activeElement).not.toBe(document.body);
  });
});
