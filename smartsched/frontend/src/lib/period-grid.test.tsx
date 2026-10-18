/**
 * RF-16 / RF-16b: the period grid comes from `GET /period-grid` at app start (components/shell/period-grid-gate.tsx) and
 * replaces the fixed `@/lib/time` defaults at runtime. Everything that shows a clock time reads the live grid at
 * call time (no module-level values computed from PERIODS), so an admin-edited P1 = 08:00 shows on the timetable,
 * classes and find-room models without a rebuild. RF-16b: nothing waits for it; pages render at once with the device's
 * cached grid or the defaults, a different answer is applied in place (version store) and an error keeps what shows.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyPeriodGrid, DEFAULT_PERIODS, PERIODS, periodGridVersion, periodRangeLabel, resetPeriodGrid, snapToPeriod, usePeriodGridVersion } from "@/lib/time";
import * as periods from "@/components/timetable/model/periods";
import { dayEndMin, dayStartMin, periodAtMinute, periodStartMin, rowTable } from "@/components/timetable/model/geometry";
import { checkMove, spanText } from "@/components/timetable/model/check";
import { buildModel, eventsOf } from "@/components/timetable/model/index-model";
import { TimeGrid, type GridColumn } from "@/components/timetable/time-grid";
import { DayTimeline } from "@/components/timetable/day-timeline";
import { I18nProvider } from "@/lib/i18n/provider";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { parseTimeWindow } from "@/components/classes/classes-model";
import { clockDefaults, emptyForm, regridForm } from "@/components/findroom/find-room-model";
import { PERIOD_GRID_CACHE_KEY, PeriodGridGate } from "@/components/shell/period-grid-gate";

/** The default grid with P1 moved to 08:00–08:40 by an admin (RF-09 editor). */
const edited = DEFAULT_PERIODS.map((p) => (p.index === 1 ? { index: 1, start: "08:00", end: "08:40" } : { ...p }));

afterEach(() => {
  resetPeriodGrid();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("runtime period grid (lib/time)", () => {
  it("applies an edited grid in place and resets to the defaults", () => {
    const before = periodGridVersion();
    expect(applyPeriodGrid(edited)).toBe(true);
    expect(PERIODS[0]).toEqual({ index: 1, start: "08:00", end: "08:40" });
    expect(periodGridVersion()).toBeGreaterThan(before);
    expect(periodRangeLabel(1, 2)).toBe("08:00–10:00");
    expect(snapToPeriod("08:00")).toEqual({ index: 1, exact: true });
    resetPeriodGrid();
    expect(PERIODS[0]).toEqual({ index: 1, start: "08:30", end: "09:10" });
  });

  it("ignores a grid that is not 18 readable periods (defaults stay)", () => {
    expect(applyPeriodGrid(edited.slice(0, 17))).toBe(false);
    expect(applyPeriodGrid(edited.map((p, i) => (i === 3 ? { ...p, start: "sabah" } : p)))).toBe(false);
    expect(applyPeriodGrid(edited.map((p, i) => (i === 3 ? { ...p, start: "12:00", end: "11:00" } : p)))).toBe(false);
    expect(applyPeriodGrid(null)).toBe(false);
    expect(PERIODS[0].start).toBe("08:30");
  });

  it("reads the Turkish dotted form the editor accepts", () => {
    expect(applyPeriodGrid(edited.map((p, i) => (i === 0 ? { ...p, start: "8.00", end: "08.40" } : p)))).toBe(true);
    expect(PERIODS[0]).toEqual({ index: 1, start: "08:00", end: "08:40" });
  });
});

describe("P1 = 08:00 reaches the models", () => {
  it("timetable: period facts, geometry and the move check", () => {
    applyPeriodGrid(edited);
    expect([periods.dayStart(), periods.dayEnd()]).toEqual(["08:00", "22:50"]);
    expect(periods.transitionPeriod()).toBe(12);
    expect([periods.lastDaytimePeriod(), periods.firstEveningPeriod()]).toEqual([11, 13]);
    expect(dayStartMin()).toBe(8 * 60);
    expect(dayEndMin()).toBe(22 * 60 + 50);
    expect(periodStartMin(1)).toBe(480);
    expect(periodAtMinute(8 * 60 + 5)).toBe(1);
    expect(rowTable(40).heights[11]).toBe(24);
    expect(spanText(1, 2)).toBe("08:00–10:00");
    const model = buildModel(fixtureIndex([assignment({ id: 501, label: "XYZ 101 §1", day: 3, sp: 1, ep: 2, rooms: [4], weeks: [1] })]));
    const ev = model.eventByAid.get(501)?.[0];
    if (!ev) throw new Error("fixture");
    expect(checkMove(model, ev, { room: 4, day: 3, sp: 17, ep: 19 }).hard[0].text.tr).toBe("Ders saati 08:00–22:50 aralığının dışına taşıyor");
  });

  it("classes: the time filter reads the edited times", () => {
    expect(parseTimeWindow("08:00-08:40")).toBeNull(); // defaults: no period ends by 08:40
    applyPeriodGrid(edited);
    expect(parseTimeWindow("08:00-08:40")).toEqual({ from: 1, to: 1 });
  });

  it("find-room: the form's default window starts at P1", () => {
    expect(emptyForm("2026-10-19").windowStart).toBe("08:30");
    applyPeriodGrid(edited);
    expect(emptyForm("2026-10-19").windowStart).toBe("08:00");
  });

  it("the defaults come back with the grid reset", () => {
    applyPeriodGrid(edited);
    resetPeriodGrid();
    expect(periods.dayStart()).toBe("08:30");
    expect(dayStartMin()).toBe(510);
  });
});

function stubGrid(response: () => Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (new URL(url, "http://localhost").pathname === "/api/v1/period-grid") return response();
    return new Response(JSON.stringify({ detail: "not here" }), { status: 404, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const gridBody = (rows: readonly { index: number; start: string; end: string }[]) =>
  new Response(JSON.stringify({ source: "setting", count: 18, periods: rows, default: DEFAULT_PERIODS }), { status: 200, headers: { "Content-Type": "application/json" } });

function renderGate() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  /** a "screen that shows times": it reads the grid while rendering and subscribes to its version */
  function Times() {
    const version = usePeriodGridVersion();
    return (
      <p data-testid="p1" data-version={version}>
        {periodRangeLabel(1, 1)}
      </p>
    );
  }
  /** a screen without times: it must stay mounted (focus, typed text) when the grid changes */
  function Field() {
    return <input aria-label="search" data-testid="field" defaultValue="" />;
  }
  return render(
    <QueryClientProvider client={client}>
      <PeriodGridGate>
        <Field />
        <Times />
      </PeriodGridGate>
    </QueryClientProvider>,
  );
}

const status500 = async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500, headers: { "Content-Type": "application/json" } });

describe("PeriodGridGate (app shell, RF-16b: never blocks)", () => {
  it("renders at once with the defaults (no skeleton), then a late grid updates the subscribed screen in place", async () => {
    let release: (r: Response) => void = () => undefined;
    const fetchMock = stubGrid(() => new Promise<Response>((r) => (release = r)));
    renderGate();
    expect(screen.queryByTestId("period-grid-wait")).toBeNull();
    expect(screen.getByTestId("p1")).toHaveTextContent("08:30–09:10");
    const field = screen.getByTestId("field") as HTMLInputElement;
    field.focus();
    fireEvent.change(field, { target: { value: "B204" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => release(gridBody(edited)));
    await waitFor(() => expect(screen.getByTestId("p1")).toHaveTextContent("08:00–08:40"));
    // the timetable model reads the late grid
    expect(periods.dayStart()).toBe("08:00");
    expect(dayStartMin()).toBe(480);
    expect(spanText(1, 2)).toBe("08:00–10:00");
    // same node, focus and typed text kept (no remount)
    expect(screen.getByTestId("field")).toBe(field);
    expect(document.activeElement).toBe(field);
    expect(field.value).toBe("B204");
    expect(JSON.parse(window.localStorage.getItem(PERIOD_GRID_CACHE_KEY) ?? "[]")[0]).toMatchObject({ start: "08:00", end: "08:40" });
  });

  it("an error keeps the defaults", async () => {
    const fetchMock = stubGrid(status500);
    renderGate();
    expect(screen.getByTestId("p1")).toHaveTextContent("08:30–09:10");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => undefined);
    expect(screen.getByTestId("p1")).toHaveTextContent("08:30–09:10");
    expect(window.localStorage.getItem(PERIOD_GRID_CACHE_KEY)).toBeNull();
  });

  it("reads the device's cached grid at start (first render after mount), and an error keeps it", async () => {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, JSON.stringify(edited));
    const fetchMock = stubGrid(status500);
    renderGate();
    expect(screen.getByTestId("p1")).toHaveTextContent("08:00–08:40");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => undefined);
    expect(screen.getByTestId("p1")).toHaveTextContent("08:00–08:40");
  });

  it("refreshes the cache on every load: the server's defaults replace a stale cached grid", async () => {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, JSON.stringify(edited));
    stubGrid(async () => gridBody(DEFAULT_PERIODS));
    renderGate();
    expect(screen.getByTestId("p1")).toHaveTextContent("08:00–08:40");
    await waitFor(() => expect(screen.getByTestId("p1")).toHaveTextContent("08:30–09:10"));
    expect(JSON.parse(window.localStorage.getItem(PERIOD_GRID_CACHE_KEY) ?? "[]")[0]).toMatchObject({ start: "08:30", end: "09:10" });
  });

  it("the same grid again does not re-render the screens (version unchanged)", async () => {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, JSON.stringify(edited));
    const fetchMock = stubGrid(async () => gridBody(edited));
    renderGate();
    const version = screen.getByTestId("p1").getAttribute("data-version");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(window.localStorage.getItem(PERIOD_GRID_CACHE_KEY)).toContain("08:00"));
    await act(async () => undefined);
    expect(screen.getByTestId("p1").getAttribute("data-version")).toBe(version);
  });

  it("an unreadable cache is ignored (defaults stay)", () => {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, "{not json");
    stubGrid(() => new Promise<Response>(() => undefined));
    renderGate();
    expect(screen.getByTestId("p1")).toHaveTextContent("08:30–09:10");
  });
});

describe("find-room: the untouched default clock fields follow a late grid", () => {
  it("moves the defaults, keeps what the person typed", () => {
    const before = clockDefaults();
    const form = { ...emptyForm("2026-10-19"), end: "13:00" };
    applyPeriodGrid(edited.map((p) => (p.index === 3 ? { index: 3, start: "10:00", end: "10:40" } : p)));
    const next = regridForm(form, before, clockDefaults());
    expect(next.windowStart).toBe("08:00");
    expect(next.start).toBe("10:00");
    expect(next.end).toBe("13:00");
    expect(regridForm(next, clockDefaults(), clockDefaults())).toBe(next);
  });
});

describe("the timetable views follow a late grid in place (memoised views subscribe)", () => {
  const model = buildModel(fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 1, sp: 1, ep: 2, rooms: [3] })]));
  const handlers = () => ({ onOpen: vi.fn(), onCreate: vi.fn(), onSelect: vi.fn(), onMove: vi.fn(), onAnnounce: vi.fn() });

  it("TimeGrid: the gutter times change, the focused chip keeps focus", () => {
    const columns: GridColumn[] = model.rooms.map((r) => ({ key: `r${r.id}`, room: r.id, day: 1, label: r.name, ariaLabel: r.name }));
    const colIndex = new Map(columns.map((c, i) => [c.room, i]));
    const { container } = render(
      <I18nProvider initialLocale="en">
        <TimeGrid model={model} mask={model.allMask} columns={columns} colW={160} rowH={32} events={eventsOf(model, 1, 1)} colOf={(e) => colIndex.get(e.room) ?? -1} blocks={[]} blockCol={() => -1} bookings={[]} bookingCol={() => -1} selection={new Set()} onSelectMany={vi.fn()} onResize={vi.fn()} gridLabel="Monday" headerH={40} line2={() => ""} ariaFor={(e) => e.a.label} {...handlers()} />
      </I18nProvider>,
    );
    expect(container.querySelector('[title^="P1 ·"]')?.getAttribute("title")).toBe("P1 · 08:30–09:10");
    const chip = screen.getByRole("button", { name: "MAT 101 §2" });
    chip.focus();
    act(() => void applyPeriodGrid(edited));
    expect(container.querySelector('[title^="P1 ·"]')?.getAttribute("title")).toBe("P1 · 08:00–08:40");
    expect(document.activeElement).toBe(chip);
  });

  it("DayTimeline: the period header reads the late grid", () => {
    render(
      <I18nProvider initialLocale="en">
        <DayTimeline model={model} rooms={model.rooms} day={1} mask={model.allMask} pxPerMin={2} events={eventsOf(model, 1, 1)} blocks={[]} bookings={[]} nowMin={null} isToday={false} selection={new Set()} ariaFor={(e) => e.a.label} label="Monday" {...handlers()} />
      </I18nProvider>,
    );
    const p1 = () => screen.getAllByRole("columnheader").find((h) => h.getAttribute("title") === "P1");
    expect(p1()).toHaveTextContent("08:30");
    act(() => void applyPeriodGrid(edited));
    expect(p1()).toHaveTextContent("08:00");
  });
});
