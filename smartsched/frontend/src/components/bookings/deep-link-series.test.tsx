/** RF-11 deep links: `?series=<id>` without `?booking=` opens the series' earliest booking that the page has loaded
 *  (the row of /my-bookings, the cell of /bookings), then tidies the address; `?booking=` still wins. */
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deepLinkedSeriesId, firstOfSeries } from "./deep-link-model";

const nav = vi.hoisted(() => ({ query: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.query),
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/my-bookings",
}));

import { useDeepLinkedBooking } from "./deep-link";

// a real recurring booking as /bookings/mine returns it (series 8: Perşembe 09:00, D-204)
const rows = [
  { id: 415, series_id: 8, date: "2026-03-05", status: "BOOKED" },
  { id: 412, series_id: 8, date: "2026-02-19", status: "CANCELLED" },
  { id: 413, series_id: 8, date: "2026-02-26", status: "BOOKED" },
  { id: 390, series_id: null, date: "2026-02-18", status: "BOOKED" },
  { id: 420, series_id: 9, date: "2026-02-17", status: "BOOKED" },
];

describe("series deep links", () => {
  beforeEach(() => {
    nav.replace.mockReset();
  });

  it("reads a positive series id only", () => {
    expect(deepLinkedSeriesId(new URLSearchParams("series=8"))).toBe(8);
    expect(deepLinkedSeriesId(new URLSearchParams("series=0"))).toBeNull();
    expect(deepLinkedSeriesId(new URLSearchParams("series=8x"))).toBeNull();
    expect(deepLinkedSeriesId(new URLSearchParams(""))).toBeNull();
  });

  it("picks the series' earliest active booking, else its earliest one", () => {
    expect(firstOfSeries(rows, 8)).toBe(413);
    expect(firstOfSeries([rows[1]], 8)).toBe(412);
    expect(firstOfSeries(rows, 77)).toBeNull();
  });

  it("opens the series' booking once the rows are there, then drops series from the address", () => {
    nav.query = "series=8&tab=upcoming";
    const open = vi.fn();
    const { rerender } = renderHook(({ list }: { list: typeof rows | undefined }) => useDeepLinkedBooking(open, list), {
      initialProps: { list: undefined as typeof rows | undefined },
    });
    expect(open).not.toHaveBeenCalled();
    expect(nav.replace).not.toHaveBeenCalled();
    rerender({ list: rows });
    expect(open).toHaveBeenCalledExactlyOnceWith(413);
    expect(nav.replace).toHaveBeenCalledWith("/my-bookings?tab=upcoming", { scroll: false });
  });

  it("a series that is not on the page opens nothing but still tidies the address", () => {
    nav.query = "series=77";
    const open = vi.fn();
    renderHook(() => useDeepLinkedBooking(open, rows));
    expect(open).not.toHaveBeenCalled();
    expect(nav.replace).toHaveBeenCalledWith("/my-bookings", { scroll: false });
  });

  it("?booking= wins over ?series= and needs no rows", () => {
    nav.query = "series=8&booking=415";
    const open = vi.fn();
    renderHook(() => useDeepLinkedBooking(open));
    expect(open).toHaveBeenCalledExactlyOnceWith(415);
  });
});
