/** Reservation panel grid: visible free state, reason glyphs, department colours, Shift-click spans. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Grid, GridSlot } from "@/lib/api/crbs";
import { I18nProvider } from "@/lib/i18n/provider";
import { BookingGrid, pickKind } from "./booking-grid";
import { dateFormatter } from "./date-format";

const D = "2026-02-17";
const periods = [1, 2, 3].map((n) => ({ id: n, name: `P${n}`, time_start: `0${7 + n}:30`, time_end: `0${8 + n}:20`, start_period: n, end_period: n, days: [1, 2, 3, 4, 5] }));
const free = (p: number): GridSlot => ({ date: D, period_id: p, room_id: 1, status: "available", allow_single: true, allow_recur: false });
const booking = (p: number, dept: number, canCancel = false): GridSlot => ({
  date: D,
  period_id: p,
  room_id: 2,
  status: "booked",
  reason: "single",
  booking: { id: 50 + p, type: "single", status: "BOOKED", date: D, weekday: 2, period_id: p, start_period: p, end_period: p, room_id: 2, room_name: "A 102", user_name: "Ayşe Yılmaz", department_id: dept, department_name: dept === 5 ? "Psikoloji" : "Hukuk", notes: "Tez savunması, jüri toplantısı", user_hidden: false, notes_hidden: false, is_owner: false, can_cancel: canCancel },
});
const grid: Grid = {
  display: "day",
  term: { id: 1, code: "2026-BAHAR", name: "Bahar 2026", start: "2026-02-02", end: "2026-06-12" },
  date: D,
  dates: [{ date: D, weekday: 2, open: true }],
  periods,
  rooms: [
    { id: 1, name: "A 101", code: "A101", capacity: 58, owner: "Selin Aydın" },
    { id: 2, name: "A 102", code: "A102", capacity: 96 },
  ],
  slots: [free(1), free(2), free(3), booking(1, 5, true), booking(2, 7), { date: D, period_id: 3, room_id: 2, status: "unavailable", reason: "limit" }],
  nav: {},
  limits: {},
  problems: [],
};

function renderGrid(props: Partial<Parameters<typeof BookingGrid>[0]> = {}) {
  const onActivate = vi.fn();
  const onSpan = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="en">
        <BookingGrid grid={grid} columns="periods" fmt={dateFormatter(undefined, "en")} multi={false} selected={new Set()} onActivate={onActivate} onSpan={onSpan} onRoomInfo={() => undefined} {...props} />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { onActivate, onSpan };
}
const cellOf = (p: number, room: number) => document.querySelector<HTMLButtonElement>(`button[data-slot-key="${D}|${p}|${room}"]`)!;

describe("BookingGrid reservation affordances", () => {
  it("free cells say Free at rest and Reserve in their accessible name", () => {
    renderGrid();
    const c = cellOf(1, 1);
    expect(c.textContent).toContain("Free");
    expect(c.textContent).toContain("Reserve");
    expect(c.getAttribute("aria-label")).toMatch(/free, Reserve/);
  });

  it("one click activates; Shift-click from it selects a span of consecutive free periods", () => {
    const { onActivate, onSpan } = renderGrid();
    fireEvent.click(cellOf(1, 1));
    expect(onActivate).toHaveBeenCalledTimes(1);
    fireEvent.click(cellOf(3, 1), { shiftKey: true });
    expect(onSpan).toHaveBeenCalledTimes(1);
    expect((onSpan.mock.calls[0]![0] as GridSlot[]).map((s) => s.period_id)).toEqual([1, 2, 3]);
  });

  it("unavailable reasons get their own glyph and say why", () => {
    renderGrid();
    const c = cellOf(3, 2);
    expect(c.querySelector('[data-reason-icon="limit"]')).not.toBeNull();
    expect(c.getAttribute("aria-label")).toMatch(/booking limit/i);
  });

  it("the room owner is under the room name", () => {
    renderGrid();
    expect(screen.getByTestId("room-info-A101").textContent).toContain("Selin Aydın");
  });

  it("a chosen department mutes the others and keeps its own colour", () => {
    renderGrid({ department: 5 });
    expect(cellOf(1, 2).dataset.muted).toBeUndefined();
    expect(cellOf(1, 2).style.boxShadow).toContain("var(--cat-5)");
    expect(cellOf(2, 2).dataset.muted).toBe("true");
    expect(cellOf(2, 2).getAttribute("aria-label")).toContain("Hukuk");
  });

  it("multi-select picks free cells to book and cancellable bookings to cancel", () => {
    expect(pickKind(free(1))).toBe("book");
    expect(pickKind(booking(1, 5, true))).toBe("cancel");
    expect(pickKind(booking(2, 7))).toBeNull();
  });
});
