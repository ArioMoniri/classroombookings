/**
 * RF-04 (audit 2026-10-17 A4, blocker): on a phone, /timetable › Ay showed ‹ › month arrows that did nothing.
 * Root cause: mobile-calendar.tsx passed `onMonth={() => undefined}` and derived the month from the selected
 * date, so the month could never change. The phone calendar now keeps its own month, as calendar-view does.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { fixtureIndex } from "@/test/fixtures/calendar-index";
import { MobileCalendar, type MobileCalendarProps } from "./mobile-calendar";
import { dateOf } from "./model/dates";
import { buildModel } from "./model/index-model";

const model = buildModel(fixtureIndex());
const week = 3;
const dates = [1, 2, 3, 4, 5, 6, 7].map((d) => dateOf(model.index.weeks, week, d));

function renderPhone(over: Partial<MobileCalendarProps> = {}) {
  const props: MobileCalendarProps = {
    model,
    week,
    day: 3,
    dates,
    onDay: vi.fn(),
    onWeek: vi.fn(),
    heat: new Map(),
    now: { minutes: 600, iso: "2026-02-18" },
    selection: new Set(),
    onSelect: vi.fn(),
    subject: null,
    onSubject: vi.fn(),
    runId: 42,
    termId: 1,
    actions: {} as MobileCalendarProps["actions"],
    readOnly: true,
    lens: "month",
    onLens: vi.fn(),
    ...over,
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <MobileCalendar {...props} />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { props, view, qc };
}

const title = () => screen.getByTestId("month-heat").querySelector("h2")?.textContent ?? "";

describe("RF-04: phone month arrows", () => {
  it("starts on the selected day's month, then ‹ › change the month", async () => {
    renderPhone();
    expect(dates[2]).toBe("2026-02-18");
    expect(title()).toMatch(/şubat 2026/i);
    await userEvent.click(screen.getByRole("button", { name: "Sonraki" }));
    expect(title()).toMatch(/mart 2026/i);
    await userEvent.click(screen.getByRole("button", { name: "Sonraki" }));
    expect(title()).toMatch(/nisan 2026/i);
    await userEvent.click(screen.getByRole("button", { name: "Önceki" }));
    await userEvent.click(screen.getByRole("button", { name: "Önceki" }));
    await userEvent.click(screen.getByRole("button", { name: "Önceki" }));
    expect(title()).toMatch(/ocak 2026/i);
  });

  it("the arrows are 44 px touch targets on a coarse pointer", () => {
    renderPhone();
    for (const name of ["Önceki", "Sonraki"]) expect(screen.getByRole("button", { name }).className).toContain("pointer-coarse:size-11");
  });

  it("leaving Ay and coming back starts again from the selected day's month", async () => {
    const { props, view, qc } = renderPhone();
    await userEvent.click(screen.getByRole("button", { name: "Sonraki" }));
    expect(title()).toMatch(/mart 2026/i);
    const rerender = (lens: MobileCalendarProps["lens"]) =>
      view.rerender(
        <QueryClientProvider client={qc}>
          <I18nProvider initialLocale="tr">
            <MobileCalendar {...props} lens={lens} />
          </I18nProvider>
        </QueryClientProvider>,
      );
    rerender("agenda");
    rerender("month");
    expect(title()).toMatch(/şubat 2026/i);
  });

  it("shows the unplaced counts it is given (the phone passed an empty map)", async () => {
    const heat = new Map([["3:3", { week: 3, day: 3, occupied: 1, blocked: 0, capacity: 10, occupancy: 0.1, conflicts: 0, changes: 0, byBuilding: {} }]]);
    renderPhone({ heat, unplacedByDay: new Map([["3:3", 4]]) });
    await userEvent.click(screen.getByRole("tab", { name: "Yerleşmeyen" }));
    const cell = screen.getAllByRole("gridcell").find((c) => c.getAttribute("aria-label")?.startsWith("18 Şubat"));
    expect(cell?.querySelector(".type-title-2")?.textContent).toBe("4");
  });
});
