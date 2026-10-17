/**
 * Round-3 lane E (R3-M-05, R1-S-26, R2-S-08): on a phone the timetable filters are a full-width bottom sheet with
 * 44 px rows and a 16 px search, and they filter the agenda (the search left 170 chips on the day list).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { fixtureIndex } from "@/test/fixtures/calendar-index";
import { CalendarSidebar, type CalendarSidebarProps } from "./calendar-sidebar";
import { EMPTY_FILTERS, eventFilter } from "./model/filters";
import { buildModel, eventsOf } from "./model/index-model";

const model = buildModel(fixtureIndex());
const labels = (keep: ReturnType<typeof eventFilter>) => [...new Set(eventsOf(model, 3).filter(keep).map((e) => e.a.label))].sort();

describe("eventFilter: one predicate for the board and the phone agenda", () => {
  it("no filter keeps everything; a course query keeps its chips; a room query keeps the room's chips", () => {
    expect(labels(eventFilter(model, EMPTY_FILTERS))).toEqual(["BME 419 §1", "CSE 225 §1", "ENG 102 §1"]);
    expect(labels(eventFilter(model, { ...EMPTY_FILTERS, query: "bme" }))).toEqual(["BME 419 §1"]);
    expect(labels(eventFilter(model, { ...EMPTY_FILTERS, query: "A 101" }))).toEqual(["ENG 102 §1"]);
    expect(labels(eventFilter(model, { ...EMPTY_FILTERS, buildings: ["C"] }))).toEqual([]);
    expect(labels(eventFilter(model, { ...EMPTY_FILTERS, tags: ["PC"] }))).toEqual(["CSE 225 §1"]);
  });
});

describe("CalendarSidebar compact (phone sheet)", () => {
  const props = {
    model,
    term: { id: 1, name: "Bahar 2026" } as never,
    runs: [model.index.run as never],
    runId: 42,
    onRun: () => undefined,
    week: 3,
    day: 3,
    onPickDate: () => undefined,
    heat: new Map(),
    todayIso: "2026-03-18",
    filters: EMPTY_FILTERS,
    onFilters: () => undefined,
    counts: { conflicts: 1, warnings: 0, locked: 1, slots: new Map([[1, 3]]) },
    compare: null,
    onCompare: () => undefined,
    ghosts: false,
    onGhosts: () => undefined,
  };
  it("drops the mini month, gives the search 16 px / 44 px and every chip and row a 44 px height", () => {
    render(
      <I18nProvider initialLocale="tr">
        <CalendarSidebar {...(props as unknown as CalendarSidebarProps)} compact />
      </I18nProvider>,
    );
    const aside = screen.getByTestId("calendar-sidebar");
    expect(aside).toHaveAttribute("data-compact", "true");
    expect(aside.querySelector('[role="grid"]')).toBeNull(); // no mini month (the day strip and the week swipe do that)
    const search = screen.getByTestId("calendar-search");
    expect(search).toHaveClass("text-base", "min-h-11");
    // the chips (a ui primitive) take the 44 px height from the sheet's descendant rule; jsdom has no layout, so the
    // stack e2e measures them (MOBILE M-02)
    expect(aside.className).toContain("[&_[data-slot=chip]>button]:min-h-11");
    expect(aside.querySelectorAll('[data-slot="chip"] > button').length).toBeGreaterThan(0);
    const rows = [...aside.querySelectorAll<HTMLElement>("button[aria-pressed]")].filter((b) => !b.closest('[data-slot="chip"]'));
    expect(rows.length).toBeGreaterThan(0); // the faculty rows
    for (const row of rows) expect(row).toHaveClass("min-h-11");
  });
  it("the desktop sidebar keeps its mini month and compact sizes off", () => {
    render(
      <I18nProvider initialLocale="tr">
        <CalendarSidebar {...(props as unknown as CalendarSidebarProps)} />
      </I18nProvider>,
    );
    const aside = screen.getByTestId("calendar-sidebar");
    expect(aside).not.toHaveAttribute("data-compact");
    expect(aside.querySelector('[role="grid"]')).not.toBeNull();
    expect(screen.getByTestId("calendar-search")).not.toHaveClass("min-h-11");
  });
});
