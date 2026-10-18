/**
 * AS-16 forecast and peaks: calibrated ranges carry "düşük güven" while confidence is low, `requests` counts show no
 * range, an empty install shows the needs sentence (never a blank chart), and the what-if sends its scope and links
 * the draft run.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { adaptiveApi, type DemandForecast, type Peaks } from "@/lib/api/adaptive";
import { catalogApi } from "@/lib/api/catalog-admin";
import { I18nProvider } from "@/lib/i18n/provider";
import { ForecastView, shortfallText } from "./forecast-view";
import { parsePct } from "./forecast-whatif";
import { PeaksView } from "./peaks-view";

vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 2, name: "2026 Bahar" }, terms: [{ id: 2, name: "2026 Bahar" }], isLoading: false }) }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, can: () => true }) }));
vi.mock("@/components/charts/chart-card", () => ({ ChartCard: ({ title, summary }: { title: string; summary: string }) => <figure data-testid="chart-card"><figcaption>{title}</figcaption><p>{summary}</p></figure> }));

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

const demand = (over: Partial<DemandForecast>): DemandForecast => ({ term_id: 2, term_code: "2026-BAHAR", group_by: "building", method: "seasonal_naive", confidence: "low", cells: [], ...over });

describe("ForecastView", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the calibrated range with düşük güven for a low cell and no range for computed requests", async () => {
    vi.spyOn(adaptiveApi, "demand").mockResolvedValue(
      demand({
        needs: { tr: "Düşük güven: aralık bu kurumun geçmişiyle henüz kalibre edilmedi", en: "Low confidence" },
        cells: [
          { key: "A", label: { tr: "A Blok", en: "Block A" }, value: 120, lo80: 100, hi80: 140, method: "seasonal_naive", confidence: "low" },
          { key: "B", label: { tr: "B Blok", en: "Block B" }, value: 40, lo80: 40, hi80: 40, method: "requests", confidence: "high" },
        ],
      }),
    );
    vi.spyOn(adaptiveApi, "shortfall").mockResolvedValue({ method: "requests", confidence: "high", no_fit: 0, cells: [{ day: 3, period: 4, group: "PC", demand: 6, supply: 4, shortfall: 2, competing: [] }] });
    wrap(<ForecastView />);
    const cells = await screen.findAllByTestId("forecast-cell");
    expect(cells[0]).toHaveTextContent("A Blok");
    expect(cells[0]).toHaveTextContent("%80 aralık 100–140");
    expect(within(cells[0]!).getByTestId("low-confidence")).toHaveTextContent("düşük güven");
    expect(within(cells[1]!).queryByTestId("range-text")).toBeNull();
    expect(within(cells[1]!).queryByTestId("low-confidence")).toBeNull();
    expect(screen.getByTestId("confidence-note")).toHaveTextContent("Düşük güven: aralık");
    expect(await screen.findByTestId("shortfall-list")).toHaveTextContent("Çarşamba 4. ders · PC: 6 talep, 4 uygun oda (2 eksik)");
  });

  it("an empty install reads the needs sentence", async () => {
    vi.spyOn(adaptiveApi, "demand").mockResolvedValue(demand({ confidence: "none", method: "none", needs: { tr: "Henüz yayımlanmış bir dönem yok", en: "No published term" } }));
    vi.spyOn(adaptiveApi, "shortfall").mockResolvedValue({ method: "none", confidence: "none", no_fit: 0, cells: [], needs: { tr: "Planlama listesi yok", en: "No list" } });
    wrap(<ForecastView />);
    expect(await screen.findByTestId("forecast-needs")).toHaveTextContent("Henüz yayımlanmış bir dönem yok");
    expect(screen.queryByTestId("forecast-cells")).toBeNull();
  });

  it("the what-if sends a faculty scope, moves focus to the answer and links the draft run", async () => {
    vi.spyOn(adaptiveApi, "demand").mockResolvedValue(demand({ confidence: "none" }));
    vi.spyOn(adaptiveApi, "shortfall").mockResolvedValue({ method: "none", confidence: "none", no_fit: 0, cells: [] });
    vi.spyOn(catalogApi, "faculties").mockResolvedValue({ items: [{ id: 1, name: "Tıp Fakültesi" }], total: 1 } as never);
    const whatIf = vi.spyOn(adaptiveApi, "whatIf").mockResolvedValue({
      scenario: { label: { tr: "Senaryo: Tıp Fakültesi +20 %", en: "Scenario" } }, method: "requests", confidence: "high",
      today: { classes: 300, no_fit: 2, shortfall_cells: 1, shortfall_total: 10 }, what_if: { classes: 300, no_fit: 7, shortfall_cells: 3, shortfall_total: 40 },
      delta: { no_fit: 5, shortfall_total: 30 }, run_id: 77,
    });
    wrap(<ForecastView />);
    fireEvent.change(await screen.findByTestId("wi-pct"), { target: { value: "+20" } });
    fireEvent.click(screen.getByTestId("wi-scope-faculty"));
    await waitFor(() => expect(screen.getByTestId("wi-value")).toHaveTextContent("Tıp Fakültesi"));
    fireEvent.change(screen.getByTestId("wi-value"), { target: { value: "Tıp Fakültesi" } });
    fireEvent.click(screen.getByTestId("wi-solve"));
    await act(async () => { fireEvent.click(screen.getByTestId("wi-submit")); });
    await waitFor(() => expect(whatIf).toHaveBeenCalledWith({ term_id: 2, enrolment_pct: 20, scope: "faculty", scope_value: "Tıp Fakültesi", solve: true }));
    const out = await screen.findByTestId("wi-result");
    expect(out).toHaveTextContent("Senaryoda 5 ders daha odasız kalıyor.");
    expect(within(out).getByTestId("wi-run")).toHaveAttribute("href", "/runs/77");
    await waitFor(() => expect(document.activeElement).toBe(out));
  });

  it("refuses a faculty scope without a faculty before calling the server", async () => {
    vi.spyOn(adaptiveApi, "demand").mockResolvedValue(demand({ confidence: "none" }));
    vi.spyOn(adaptiveApi, "shortfall").mockResolvedValue({ method: "none", confidence: "none", no_fit: 0, cells: [] });
    vi.spyOn(catalogApi, "programs").mockResolvedValue({ items: [], total: 0 } as never);
    const whatIf = vi.spyOn(adaptiveApi, "whatIf");
    wrap(<ForecastView />);
    fireEvent.click(await screen.findByTestId("wi-scope-program"));
    fireEvent.click(screen.getByTestId("wi-submit"));
    expect(await screen.findByTestId("wi-error")).toHaveTextContent("Fakülte ya da programı seçin.");
    expect(whatIf).not.toHaveBeenCalled();
  });
});

describe("PeaksView", () => {
  afterEach(() => vi.restoreAllMocks());
  const peaks = (over: Partial<Peaks>): Peaks => ({ term_id: 2, term_code: "2026-BAHAR", period_kind: "LECTURE", group_by: "building", threshold_pct: 85, weeks: [], rooms: 40, cells: [], peaks: [], period_profile: [], method: "shrunk_weekly_mean", confidence: "medium", ...over });

  it("names the busiest hour and lists peaks with their ranges in text", async () => {
    const c = { day: 3, period: 4, group: "A", value: 92, lo80: 85, hi80: 97, n_weeks: 12, rooms: 20, peak: true, label: { tr: "Çarşamba 4. ders", en: "Wednesday period 4" } };
    vi.spyOn(adaptiveApi, "peaks").mockResolvedValue(peaks({ cells: [c], peaks: [c], period_profile: [{ period: 4, value: 80 }, { period: 5, value: 60 }, { period: 6, value: 40 }] }));
    wrap(<PeaksView />);
    expect(await screen.findByTestId("peaks-summary")).toHaveTextContent("En yoğun saat Çarşamba 4. ders (A, odaların %92'si dolu)");
    const row = screen.getByTestId("peak-row");
    expect(row).toHaveTextContent("%80 aralık %85–%97");
    expect(within(row).queryByTestId("low-confidence")).toBeNull();
    expect(screen.getByTestId("peaks-csv")).toHaveAttribute("href", expect.stringContaining("format=csv"));
  });

  it("an empty install shows the needs text, never a blank chart", async () => {
    vi.spyOn(adaptiveApi, "peaks").mockResolvedValue(peaks({ confidence: "none", needs: { tr: "Yayımlanmış program gerekiyor", en: "Needs a published timetable" } }));
    wrap(<PeaksView />);
    expect(await screen.findByTestId("peaks-needs")).toHaveTextContent("Yayımlanmış program gerekiyor");
    expect(screen.queryByTestId("chart-card")).toBeNull();
  });
});

describe("helpers", () => {
  it("parses what-if percentages inside the backend's bounds", () => {
    expect(parsePct("+12")).toBe(12);
    expect(parsePct("-5")).toBe(-5);
    expect(parsePct("12,5")).toBe(13);
    expect(parsePct("250")).toBeNull();
    expect(parsePct("abc")).toBeNull();
  });
  it("words a shortfall cell for 'tüm odalar'", () => {
    const t = (k: string, v?: Record<string, string | number>) => (k === "adaptive.shortfall.all" ? "tüm odalar" : `${v?.day} ${v?.period} ${v?.group} ${v?.short}`);
    expect(shortfallText({ day: 1, period: 2, group: "*", demand: 3, supply: 1, shortfall: 2, competing: [] }, ["Pazartesi"], t)).toBe("Pazartesi 2 tüm odalar 2");
  });
});
