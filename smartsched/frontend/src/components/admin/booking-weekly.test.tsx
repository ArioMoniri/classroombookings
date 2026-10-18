import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import type { WeeklyBookingStats } from "@/lib/api/stats";

vi.mock("@/components/charts/chart-lazy", () => ({
  LazyBarChart: (p: { data: unknown[]; series: readonly string[]; stackType?: string; partialLast: boolean; xTickFormatter: (s: string) => string }) => (
    <div data-testid="bar" data-series={p.series.join(",")} data-stack={p.stackType ?? "default"} data-partial={String(p.partialLast)} data-ticks={(p.data as { week: string }[]).map((r) => p.xTickFormatter(r.week)).join("|")} />
  ),
}));

const state = vi.hoisted(() => ({ can: true, stats: null as unknown, error: null as unknown, ctxLoading: false, sessions: [{ id: 3, name: "2026 Bahar", is_current: true }] as { id: number; name: string; is_current: boolean }[] }));
vi.mock("@/lib/permissions", async (orig) => ({ ...(await orig<typeof import("@/lib/permissions")>()), usePermissions: () => ({ can: (p: string) => state.can && p === "system.export_bookings", loading: false, perms: [] }) }));
vi.mock("@/lib/api/crbs", async (orig) => ({ ...(await orig<typeof import("@/lib/api/crbs")>()), useBookingContext: () => ({ data: { sessions: state.sessions }, isLoading: state.ctxLoading, isSuccess: !state.ctxLoading }) }));
vi.mock("@/lib/api/stats", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/stats")>()),
  useWeeklyBookingStats: () => ({ data: state.stats ?? undefined, error: state.error, isError: !!state.error, isLoading: false, refetch: vi.fn() }),
}));

import { BookingWeekly } from "./booking-weekly";

const wk = (n: number, bookings: number, over: Partial<WeeklyBookingStats["weeks"][number]> = {}) => ({ week: n, start: `2026-03-0${n}`, end: `2026-03-0${n + 4}`, exam: false, partial: false, bookings, requests: { approved: n, rejected: 1, pending: 0 }, ...over });

beforeEach(() => {
  state.can = true;
  state.error = null;
  state.ctxLoading = false;
  state.sessions = [{ id: 3, name: "2026 Bahar", is_current: true }];
  state.stats = { term_id: 3, from: "2026-03-01", to: "2026-06-01", today: "2026-03-04", weeks: [wk(1, 120), wk(2, 210, { exam: true }), wk(3, 40, { partial: true })] };
});

describe("CH-07 Bu dönem charts on /admin", { timeout: 20_000 }, () => {
  it("bookings per week: one series, the current week hatched, exam weeks direct-labelled and in the table", () => {
    render(<BookingWeekly />);
    const fig = screen.getByRole("figure", { name: "Haftalık rezervasyonlar" });
    expect(fig).toHaveAccessibleDescription(/Bu dönem 370 rezervasyon; en yoğun hafta 2\. hafta \(210\)\. Bu hafta henüz bitmedi\./);
    const bar = within(fig).getByTestId("bar");
    expect(bar).toHaveAttribute("data-series", "bookings");
    expect(bar).toHaveAttribute("data-partial", "true");
    expect(bar).toHaveAttribute("data-ticks", "1. hf|2. hf\nSınav haftası|3. hf");
    const heads = within(within(fig).getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Hafta", "Hafta başı", "Rezervasyon", "Sınav haftası"]);
  });

  it("request outcomes: stacked approved / rejected / pending with a legend", () => {
    render(<BookingWeekly />);
    const fig = screen.getByRole("figure", { name: "Haftalık talep sonuçları" });
    expect(fig).toHaveAccessibleDescription(/Bu dönem 9 talep: 6 onaylandı, 3 reddedildi, 0 bekliyor\./);
    expect(within(fig).getByTestId("bar")).toHaveAttribute("data-stack", "stacked");
    expect(screen.getByTestId("chart-legend-requests-weekly")).toHaveTextContent("OnaylandıReddedildiBekliyor");
  });

  it("route missing on this server: one honest 'veri yok' card, no plot, no numbers", () => {
    state.stats = null;
    state.error = new HttpError(404, "Not Found", "Not Found");
    render(<BookingWeekly />);
    expect(screen.getAllByRole("figure")).toHaveLength(1);
    expect(screen.getByText("Henüz gösterilecek veri yok")).toBeInTheDocument();
    expect(screen.getByText(/Haftalık sayımlar sunucuda henüz hazır değil/)).toBeInTheDocument();
    expect(screen.queryByTestId("bar")).toBeNull();
  });

  it("a real refusal is an error with the server's words, not an empty chart", () => {
    state.stats = null;
    state.error = new HttpError(403, "Bu işlem için yetkiniz yok.", { code: "forbidden", message: "Forbidden", message_tr: "Bu işlem için yetkiniz yok." });
    render(<BookingWeekly />);
    expect(screen.getAllByText("Grafik yüklenemedi").length).toBeGreaterThan(0);
  });

  it("no current term: the empty reason says so", () => {
    state.sessions = [];
    state.stats = null;
    render(<BookingWeekly />);
    expect(screen.getByText("Geçerli bir dönem yok.")).toBeInTheDocument();
  });

  it("people who may not export all bookings see nothing", () => {
    state.can = false;
    const { container } = render(<BookingWeekly />);
    expect(container).toBeEmptyDOMElement();
  });
});
