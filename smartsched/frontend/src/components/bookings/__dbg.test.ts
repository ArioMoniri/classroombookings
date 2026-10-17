import { it, expect, vi } from "vitest";
import { focusAfter } from "./focus-after";
import { rowFocusAfterRemoval, rowIndexOf } from "./my-bookings-model";
it("dbg", async () => {
  vi.useFakeTimers();
  document.body.innerHTML = `<h2 id="mine-list" tabindex="-1">L</h2><ul data-testid="booking-list"><li data-booking-ids="10"><button data-row-open>10</button></li><li data-booking-ids="11"><button data-row-open>11</button></li><li data-booking-ids="12"><button data-row-open>12</button></li></ul>`;
  const i = rowIndexOf(11);
  const sels = rowFocusAfterRemoval(i);
  focusAfter(sels, 10, 2000);
  await vi.advanceTimersByTimeAsync(20);
  const a1 = document.activeElement?.textContent;
  document.querySelector('[data-booking-ids="11"]')!.remove();
  await vi.advanceTimersByTimeAsync(400);
  expect([i, sels, a1, document.activeElement?.textContent]).toEqual([]);
});
