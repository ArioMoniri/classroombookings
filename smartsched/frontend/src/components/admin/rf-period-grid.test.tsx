// RF-09 (rf-f-2026-10-18): /admin/schedules "Ders saatleri": exactly 18 rows of two time inputs, Turkish input
// (08.30) sent as typed, the backend's Turkish refusal at the period it names, "Varsayılana dön" behind "Gelişmiş"
// with a confirm (DELETE /period-grid).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PERIODS } from "@/lib/time";
import { I18nProvider } from "@/lib/i18n/provider";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), toasts) }));

import { PeriodGridEditor } from "./period-grid-editor";

const GRID = (source = "default", first = "08:30") => ({
  source,
  count: 18,
  periods: PERIODS.map((p) => ({ index: p.index, start: p.index === 1 ? first : p.start, end: p.end, label: `${p.start}-${p.end}` })),
  default: PERIODS.map((p) => ({ index: p.index, start: p.start, end: p.end })),
});
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: { key: string; body: unknown }[];
let routes: Record<string, (b: unknown) => Response>;
beforeEach(() => {
  calls = [];
  Object.values(toasts).forEach((f) => f.mockReset());
  routes = {
    "GET /api/v1/period-grid": () => res(200, GRID()),
    "PUT /api/v1/period-grid": () => res(200, { ...GRID("setting", "08:40"), booking_periods_updated: 1 }),
    "DELETE /api/v1/period-grid": () => res(200, { ...GRID(), booking_periods_updated: 1 }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ key, body });
      return routes[key]?.(body) ?? res(404, {});
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <PeriodGridEditor />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("Ders saatleri (period grid)", () => {
  it("shows exactly 18 periods with start and end inputs", async () => {
    wrap();
    const rows = await screen.findAllByTestId(/^grid-row-\d+$/);
    expect(rows).toHaveLength(18);
    expect(screen.getByLabelText("P1 başlangıç")).toHaveValue("08:30");
    expect(screen.getByLabelText("P18 bitiş")).toHaveValue("22:50");
    expect(screen.getByTestId("period-grid")).toHaveTextContent("Varsayılan saatler");
  });

  it("saves the 18 periods as typed (08.40 is read by the server)", async () => {
    wrap();
    fireEvent.change(await screen.findByLabelText("P1 başlangıç"), { target: { value: "08.40" } });
    fireEvent.click(screen.getByTestId("period-grid-save"));
    await waitFor(() => expect(calls.some((c) => c.key === "PUT /api/v1/period-grid")).toBe(true));
    const body = calls.find((c) => c.key === "PUT /api/v1/period-grid")!.body as { periods: { start: string; end: string }[] };
    expect(body.periods).toHaveLength(18);
    expect(body.periods[0]).toEqual({ start: "08.40", end: "09:10" });
    await waitFor(() => expect(toasts.success).toHaveBeenCalled());
    expect(await screen.findByLabelText("P1 başlangıç")).toHaveValue("08:40");
  });

  it("shows the server's Turkish refusal at the period it names", async () => {
    routes["PUT /api/v1/period-grid"] = () => res(422, { detail: { code: "period_grid_order", message: "P3 starts at 09:00 before P2 ends at 10:00", message_en: "P3 starts at 09:00 before P2 ends at 10:00", message_tr: "P3 (09:00), P2 bitmeden (10:00) başlıyor; saatler sırayla ve çakışmadan gelmeli." } });
    wrap();
    fireEvent.change(await screen.findByLabelText("P3 başlangıç"), { target: { value: "09.00" } });
    fireEvent.click(screen.getByTestId("period-grid-save"));
    const row = screen.getByTestId("grid-row-3");
    expect(await within(row).findByRole("alert")).toHaveTextContent("P2 bitmeden (10:00) başlıyor");
    expect(screen.getByLabelText("P3 başlangıç")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("P1 başlangıç")).not.toHaveAttribute("aria-invalid");
  });

  it("puts a time refusal on the field whose value it quotes", async () => {
    routes["PUT /api/v1/period-grid"] = () => res(422, { detail: { code: "period_grid_time", message: "P2: cannot read the time 'sabah' (e.g. 08:30)", message_en: "x", message_tr: "P2: 'sabah' saati okunamadı (örnek: 08:30)." } });
    wrap();
    fireEvent.change(await screen.findByLabelText("P2 bitiş"), { target: { value: "sabah" } });
    fireEvent.click(screen.getByTestId("period-grid-save"));
    expect(await within(screen.getByTestId("grid-row-2")).findByRole("alert")).toHaveTextContent("'sabah' saati okunamadı");
    expect(screen.getByLabelText("P2 bitiş")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("P2 başlangıç")).not.toHaveAttribute("aria-invalid");
  });

  it("'Varsayılana dön' is under 'Gelişmiş' and asks first", async () => {
    routes["GET /api/v1/period-grid"] = () => res(200, GRID("setting", "08:40"));
    wrap();
    await screen.findByLabelText("P1 başlangıç");
    expect(screen.queryByTestId("period-grid-reset")).toBeNull();
    fireEvent.click(screen.getByTestId("period-grid-advanced"));
    fireEvent.click(screen.getByTestId("period-grid-reset"));
    const dialog = await screen.findByRole("alertdialog");
    expect(calls.some((c) => c.key === "DELETE /api/v1/period-grid")).toBe(false);
    fireEvent.click(within(dialog).getByRole("button", { name: "Varsayılana dön" }));
    await waitFor(() => expect(calls.some((c) => c.key === "DELETE /api/v1/period-grid")).toBe(true));
    await waitFor(() => expect(screen.getByLabelText("P1 başlangıç")).toHaveValue("08:30"));
  });
});
