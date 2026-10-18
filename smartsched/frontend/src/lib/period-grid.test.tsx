/**
 * RF-16: the period grid comes from `GET /period-grid` at app start (components/shell/period-grid-gate.tsx) and
 * replaces the fixed `@/lib/time` defaults at runtime. Everything that shows a clock time reads the live grid at
 * call time (no module-level values computed from PERIODS), so an admin-edited P1 = 08:00 shows on the timetable,
 * classes and find-room models without a rebuild. While loading or on an error the defaults stay.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyPeriodGrid, DEFAULT_PERIODS, PERIODS, periodGridVersion, periodRangeLabel, resetPeriodGrid, snapToPeriod } from "@/lib/time";
import * as periods from "@/components/timetable/model/periods";
import { dayEndMin, dayStartMin, periodAtMinute, periodStartMin, rowTable } from "@/components/timetable/model/geometry";
import { checkMove, spanText } from "@/components/timetable/model/check";
import { buildModel } from "@/components/timetable/model/index-model";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { parseTimeWindow } from "@/components/classes/classes-model";
import { emptyForm } from "@/components/findroom/find-room-model";
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
  /** a "screen that shows times": it reads the grid while rendering */
  function Times() {
    return <p data-testid="p1">{periodRangeLabel(1, 1)}</p>;
  }
  return render(
    <QueryClientProvider client={client}>
      <PeriodGridGate>
        <Times />
      </PeriodGridGate>
    </QueryClientProvider>,
  );
}

describe("PeriodGridGate (app shell)", () => {
  it("holds the first screen until GET /period-grid answers, then shows the edited times", async () => {
    let release: (r: Response) => void = () => undefined;
    const fetchMock = stubGrid(() => new Promise<Response>((r) => (release = r)));
    renderGate();
    expect(screen.queryByTestId("p1")).toBeNull();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    release(gridBody(edited));
    expect(await screen.findByTestId("p1")).toHaveTextContent("08:00–08:40");
    expect(JSON.parse(window.localStorage.getItem(PERIOD_GRID_CACHE_KEY) ?? "[]")[0]).toMatchObject({ start: "08:00", end: "08:40" });
  });

  it("falls back to the defaults on an error", async () => {
    stubGrid(async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500, headers: { "Content-Type": "application/json" } }));
    renderGate();
    expect(await screen.findByTestId("p1")).toHaveTextContent("08:30–09:10");
  });

  it("starts with the grid this device saw last, without waiting", async () => {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, JSON.stringify(edited));
    stubGrid(() => new Promise<Response>(() => undefined));
    renderGate();
    expect(await screen.findByTestId("p1")).toHaveTextContent("08:00–08:40");
  });
});
