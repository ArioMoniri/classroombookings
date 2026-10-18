// E2EA2-F03 (FIX-K): focus never falls to <body> after a period-grid save or reset, or a week kind change.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PERIODS } from "@/lib/time";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
const TERM = { id: 2, code: "2026-BAHAR", name: "2025-2026 Bahar", kind: "REGULAR", start_date: "2026-02-16", end_date: "2026-06-05", week_count: 14, is_active: true };
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: TERM, terms: [TERM], isLoading: false }) }));

import { PeriodGridEditor } from "./period-grid-editor";
import { TermWeeksEditor } from "./term-weeks-editor";

const GRID = (source = "default", first = "08:30") => ({
  source,
  count: 18,
  periods: PERIODS.map((p) => ({ index: p.index, start: p.index === 1 ? first : p.start, end: p.end, label: `${p.start}-${p.end}` })),
  default: PERIODS.map((p) => ({ index: p.index, start: p.start, end: p.end })),
});
const W = (index: number, kind = "LECTURE", edited = false) => ({ id: index, term_id: 2, index, start_date: null, kind, label: null, edited });
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let routes: Record<string, (b: unknown) => Response | Promise<Response>>;
beforeEach(() => {
  routes = {
    "GET /api/v1/period-grid": () => res(200, GRID()),
    "PUT /api/v1/period-grid": () => res(200, { ...GRID("setting", "08:40"), booking_periods_updated: 0 }),
    "DELETE /api/v1/period-grid": () => res(200, { ...GRID(), booking_periods_updated: 0 }),
    "GET /api/v1/terms/2/weeks": () => res(200, [W(1), W(2)]),
    "PATCH /api/v1/terms/2/weeks/2": (b) => res(200, { ...W(2), kind: (b as { kind: string }).kind, edited: true }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      return routes[key]?.(body) ?? res(404, {});
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

describe("focus after admin actions (E2EA2-F03)", () => {
  it("period grid Kaydet keeps focus on Kaydet after the form starts again from the server's answer", async () => {
    wrap(<PeriodGridEditor />);
    fireEvent.change(await screen.findByLabelText("P1 başlangıç"), { target: { value: "08.40" } });
    const save = screen.getByTestId("period-grid-save");
    save.focus();
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByLabelText("P1 başlangıç")).toHaveValue("08:40"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("period-grid-save")));
  });

  it("Varsayılana dön moves focus to the P1 start field", async () => {
    routes["GET /api/v1/period-grid"] = () => res(200, GRID("setting", "08:40"));
    wrap(<PeriodGridEditor />);
    await screen.findByLabelText("P1 başlangıç");
    fireEvent.click(screen.getByTestId("period-grid-advanced"));
    fireEvent.click(screen.getByTestId("period-grid-reset"));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Varsayılana dön" }));
    await waitFor(() => expect(screen.getByLabelText("P1 başlangıç")).toHaveValue("08:30"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("P1 başlangıç")));
  });

  it("a week kind select stays enabled (aria-disabled) while it saves, so focus stays on it", async () => {
    let release: () => void = () => undefined;
    routes["PATCH /api/v1/terms/2/weeks/2"] = (b) => new Promise((r) => (release = () => r(res(200, { ...W(2), kind: (b as { kind: string }).kind, edited: true }))));
    wrap(<TermWeeksEditor />);
    const select = await screen.findByLabelText("2. hafta türü");
    select.focus();
    fireEvent.change(select, { target: { value: "HOLIDAY" } });
    await waitFor(() => expect(screen.getByLabelText("2. hafta türü")).toHaveAttribute("aria-disabled", "true"));
    expect(screen.getByLabelText("2. hafta türü")).not.toBeDisabled();
    release();
    await waitFor(() => expect(screen.getByLabelText("2. hafta türü")).not.toHaveAttribute("aria-disabled"));
    expect(document.activeElement).toBe(screen.getByLabelText("2. hafta türü"));
  });
});
