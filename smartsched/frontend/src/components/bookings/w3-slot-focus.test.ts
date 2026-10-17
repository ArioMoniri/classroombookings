/** R3-S-05 (W3-SLOT): after cancelling from a My bookings row, focus goes to the next row (or the previous one, or the
 *  list heading), never to <body>, once the cancelled row has left the list. */
import { afterEach, describe, expect, it } from "vitest";
import { focusRowAfterRemoval, rowIndexOf } from "./my-bookings-model";

function list(ids: number[]) {
  document.body.innerHTML = `<h2 id="mine-list" tabindex="-1">Liste</h2><ul data-testid="booking-list">${ids
    .map((id) => `<li data-booking-ids="${id}"><button data-row-open>${id}</button></li>`)
    .join("")}</ul>`;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("focus after a cancelled row", () => {
  it("finds the row of a booking (any of its period ids)", () => {
    document.body.innerHTML = `<ul data-testid="booking-list"><li data-booking-ids="1,2"></li><li data-booking-ids="7"></li></ul>`;
    expect(rowIndexOf(2)).toBe(0);
    expect(rowIndexOf(7)).toBe(1);
    expect(rowIndexOf(99)).toBe(-1);
  });

  it("the row that takes the cancelled row's place", () => {
    list([10, 11, 12]);
    const i = rowIndexOf(11);
    document.querySelector('[data-booking-ids="11"]')!.remove();
    expect(focusRowAfterRemoval(i)?.textContent).toBe("12");
    expect(document.activeElement?.textContent).toBe("12");
  });

  it("the last row falls back to the previous row, an emptied list to the heading", () => {
    list([10, 11]);
    const i = rowIndexOf(11);
    document.querySelector('[data-booking-ids="11"]')!.remove();
    expect(focusRowAfterRemoval(i)?.textContent).toBe("10");
    list([10]);
    document.querySelector('[data-booking-ids="10"]')!.remove();
    focusRowAfterRemoval(0);
    expect(document.activeElement?.id).toBe("mine-list");
    expect(document.activeElement).not.toBe(document.body);
  });
});
