/** W3-SLOT: the booking grid follows the administrator's slot display (labels, density, blocks, hidden periods). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Grid, GridSlot } from "@/lib/api/crbs";
import { I18nProvider } from "@/lib/i18n/provider";
import { BookingGrid } from "./booking-grid";
import { dateFormatter } from "./date-format";
import { applySlotDisplay, DEFAULT_SLOT_DISPLAY, type SlotDisplay } from "./slot-display";

const D = "2026-02-17";
const periods = [
  { id: 1, name: "P1", time_start: "08:30", time_end: "09:20", start_period: 1, end_period: 1, days: [1, 2, 3, 4, 5] },
  { id: 2, name: "P2", time_start: "09:30", time_end: "10:20", start_period: 2, end_period: 2, days: [1, 2, 3, 4, 5] },
  { id: 17, name: "P17", time_start: "21:10", time_end: "22:00", start_period: 17, end_period: 17, days: [1, 2, 3, 4, 5] },
];
const free = (p: number): GridSlot => ({ date: D, period_id: p, room_id: 1, status: "available", allow_single: true, allow_recur: false });
const grid: Grid = {
  display: "day",
  term: { id: 1, code: "2026-BAHAR", name: "Bahar 2026", start: "2026-02-02", end: "2026-06-12" },
  date: D,
  dates: [{ date: D, weekday: 2, open: true }],
  periods,
  rooms: [{ id: 1, name: "A 101", code: "A101", capacity: 58 }],
  slots: [free(1), free(2), free(17)],
  nav: {},
  limits: {},
  problems: [],
};

function renderWith(sd: Partial<SlotDisplay>) {
  const display = { ...DEFAULT_SLOT_DISPLAY, ...sd };
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <BookingGrid grid={applySlotDisplay(grid, display)} columns="periods" fmt={dateFormatter(undefined, "tr")} multi={false} selected={new Set()} onActivate={() => undefined} slotDisplay={display} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}
const headers = () => [...document.querySelectorAll("thead th")].slice(1).map((th) => th.textContent);
const cell = (p: number) => document.querySelector<HTMLButtonElement>(`button[data-slot-key="${D}|${p}|1"]`);

describe("BookingGrid × slot display", () => {
  it("default: name and time in the header, 44 px rows", () => {
    renderWith({});
    expect(headers()).toEqual(["P108:30–09:20", "P209:30–10:20", "P1721:10–22:00"]);
    expect(cell(1)!.className).toContain("h-11");
  });

  it("time labels: the header is the time, and the time is spoken once", () => {
    renderWith({ label: "time" });
    expect(headers()[0]).toBe("08:30–09:20");
    const label = cell(1)!.getAttribute("aria-label")!;
    expect(label.match(/08:30–09:20/g)).toHaveLength(1);
  });

  it("name labels still speak the time", () => {
    renderWith({ label: "name" });
    expect(headers()[0]).toBe("P1");
    expect(cell(1)!.getAttribute("aria-label")).toContain("08:30–09:20");
  });

  it("hidden evening period is gone from header and cells", () => {
    renderWith({ day_end: "18:00" });
    expect(headers()).toHaveLength(2);
    expect(cell(17)).toBeNull();
  });

  it("compact density: 32 px rows with a fine pointer, 44 px on touch", () => {
    renderWith({ density: "compact" });
    expect(cell(1)!.className).toMatch(/\bh-8\b/);
    expect(cell(1)!.className).toContain("pointer-coarse:h-11");
  });

  it("blocks: tick strip per period and hairlines inside the cell, column as wide as its blocks", () => {
    renderWith({ unit: "blocks", block_minutes: 15 });
    expect(document.querySelectorAll('[data-testid="block-ticks"]')[0]!.children).toHaveLength(4);
    expect(cell(1)!.querySelector("[data-blocks]")?.getAttribute("data-blocks")).toBe("4");
    const col = document.querySelectorAll("colgroup col")[1] as HTMLElement;
    expect(col.style.width).toBe("136px");
  });
});
