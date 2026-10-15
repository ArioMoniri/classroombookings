import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { I18nProvider } from "@/lib/i18n/provider";
import { TimetableNoAccess } from "./no-access";
import { calendarFlags } from "./use-calendar-data";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const base = { hydrated: true, runsPending: false, runsError: null, requestedError: null, indexError: null, indexPending: false, runId: null };

describe("calendarFlags (U-02: a 403 is not 'no timetable')", () => {
  it("no usable run for a planner → noRun", () => {
    expect(calendarFlags(base)).toMatchObject({ noRun: true, forbidden: false });
  });
  it("403 on /runs → forbidden, never the planner empty state", () => {
    const f = calendarFlags({ ...base, runsError: new HttpError(403, "Forbidden") });
    expect(f).toMatchObject({ noRun: false, forbidden: true, loading: false });
  });
  it("403 on a deep-linked run or on its index → forbidden", () => {
    expect(calendarFlags({ ...base, requestedError: new HttpError(403, "x"), runId: 5 }).forbidden).toBe(true);
    expect(calendarFlags({ ...base, indexError: new HttpError(403, "x"), runId: 5 }).forbidden).toBe(true);
  });
  it("another /runs failure is an error with retry, not 'no timetable'", () => {
    const f = calendarFlags({ ...base, runsError: new HttpError(500, "boom") });
    expect(f).toMatchObject({ noRun: false, forbidden: false, error: true });
  });
  it("still loading before hydration / while runs load", () => {
    expect(calendarFlags({ ...base, hydrated: false }).noRun).toBe(false);
    expect(calendarFlags({ ...base, runsPending: true })).toMatchObject({ noRun: false, loading: true });
  });
});

describe("TimetableNoAccess", () => {
  it("explains the missing access and offers bookings, with no planner actions", () => {
    render(
      <I18nProvider initialLocale="tr">
        <TimetableNoAccess />
      </I18nProvider>,
    );
    expect(screen.getByRole("heading", { name: "Planlama takvimine erişiminiz yok" })).toBeInTheDocument();
    expect(screen.queryByText("Bu dönem için henüz bir program yok.")).toBeNull();
    expect(screen.queryByRole("button", { name: /Program oluştur|Excel'den içe aktar/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Rezervasyonlara git" })).toHaveAttribute("href", "/bookings");
  });
});

describe("pickRun (UX fix: remember term, run and week per user)", () => {
  const r = (id: number, kind: "COURSE" | "EXAM" = "COURSE") => ({ id, kind }) as never;
  const usable = [r(9), r(7), r(5, "EXAM")];
  it("a deep link wins; then the run this user last opened (if still usable in the term); then the default", async () => {
    const { pickRun } = await import("./use-calendar-data");
    expect(pickRun({ requested: 3, remembered: 7, runs: usable, term: undefined })).toBe(3);
    expect(pickRun({ requested: null, remembered: 7, runs: usable, term: undefined })).toBe(7);
    expect(pickRun({ requested: null, remembered: 42, runs: usable, term: undefined })).toBe(9);
    expect(pickRun({ requested: null, remembered: undefined, runs: [], term: undefined })).toBeNull();
  });
});
