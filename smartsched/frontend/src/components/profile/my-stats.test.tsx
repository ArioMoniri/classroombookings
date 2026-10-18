import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";

const state = vi.hoisted(() => ({
  dash: { totals: { active: 3, session: 12, all: 40 }, limits: { max_active_bookings: 5 } } as unknown,
  requests: [{ id: 1, status: "PENDING", group_id: null }, { id: 2, status: "PENDING", group_id: 7 }, { id: 3, status: "PENDING", group_id: 7 }, { id: 4, status: "APPROVED", group_id: null }],
  prefs: { linked: true, instructor_id: 41 } as unknown,
  load: { linked: true, instructor_id: 41, term_id: 3, run_id: 12, days: [{ day: 1, periods: 4, minutes: 200 }, { day: 3, periods: 6, minutes: 300 }], total_periods: 10 } as unknown,
  loadError: null as unknown,
}));
vi.mock("@/lib/api/crbs", async (orig) => ({ ...(await orig<typeof import("@/lib/api/crbs")>()), useBookingDashboard: () => ({ data: state.dash, isLoading: false, isError: false }) }));
vi.mock("@/lib/api/wave1", async (orig) => ({ ...(await orig<typeof import("@/lib/api/wave1")>()), useMyRequests: () => ({ data: state.requests }) }));
vi.mock("@/lib/api/teacher-preferences", async (orig) => ({ ...(await orig<typeof import("@/lib/api/teacher-preferences")>()), useMyPreferences: () => ({ data: state.prefs }) }));
vi.mock("@/lib/api/stats", async (orig) => ({ ...(await orig<typeof import("@/lib/api/stats")>()), useMyLoad: () => ({ data: state.loadError ? undefined : state.load, error: state.loadError, isError: !!state.loadError, isLoading: false, refetch: vi.fn() }) }));
// the network rule (charts.md §10): these routes never load the chart engine
vi.mock("@/components/charts/chart-lazy", () => {
  throw new Error("chart-lazy must not be imported on /profile or /my-bookings");
});

import { MyLoad } from "./my-load";
import { MyStats } from "./my-stats";

beforeEach(() => {
  state.prefs = { linked: true, instructor_id: 41 };
  state.loadError = null;
});

describe("CH-11 Özetim tiles", { timeout: 20_000 }, () => {
  it("three numbers: active, this term, open requests (a multi-period request counts once)", () => {
    render(<MyStats />);
    expect(within(screen.getByTestId("my-stat-active")).getByText("3")).toBeInTheDocument();
    expect(within(screen.getByTestId("my-stat-term")).getByText("12")).toBeInTheDocument();
    expect(within(screen.getByTestId("my-stat-open")).getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Özetim" })).toBeInTheDocument();
  });

  it("the quota sentence and how many are left", () => {
    render(<MyStats />);
    expect(screen.getByTestId("my-stats-quota")).toHaveTextContent("3 / 5 aktif rezervasyon hakkı kullanıldı · 2 rezervasyon daha yapabilirsiniz");
  });
});

describe("CH-11 Haftalık ders yüküm", { timeout: 20_000 }, () => {
  it("weekday rows as 44 px links to that day of the timetable; 0 reads 'ders yok'", () => {
    render(<MyLoad />);
    const list = screen.getByRole("list", { name: "Gün başına ders saati" });
    const links = within(list).getAllByRole("link");
    expect(links).toHaveLength(5);
    expect(links[0]).toHaveAttribute("href", "/timetable?lens=day&day=1&subject=instructor%3A41&run=12");
    expect(links[0]).toHaveAccessibleName("Pazartesi: 4 ders saati. Takvimde o günü aç");
    expect(links[1]).toHaveAccessibleName("Salı: ders yok. Takvimde o günü aç");
    expect(links[0]!.className).toMatch(/pointer-coarse:min-h-11/);
    expect(screen.getByTestId("my-load-total")).toHaveTextContent("Haftada toplam 10 ders saati.");
  });

  it("not linked to an instructor record: nothing", () => {
    state.prefs = { linked: false, instructor_id: null };
    const { container } = render(<MyLoad />);
    expect(container).toBeEmptyDOMElement();
  });

  it("route missing: an honest sentence, no bars", () => {
    state.loadError = new HttpError(404, "Not Found", "Not Found");
    render(<MyLoad />);
    expect(screen.getByText("Ders yükü verisi sunucuda henüz hazır değil.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("nothing published for the term: says so", () => {
    state.load = { linked: true, instructor_id: 41, term_id: 3, run_id: null, days: [], total_periods: 0 };
    render(<MyLoad />);
    expect(screen.getByText("Bu dönem için yayımlanmış program yok.")).toBeInTheDocument();
  });
});
