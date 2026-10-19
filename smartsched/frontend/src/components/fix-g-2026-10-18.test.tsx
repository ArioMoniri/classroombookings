/**
 * FIX-G (2026-10-18): round-4 AS-20 / CH-12 minors (docs/testing/round4/2026-10-18-as20.md, -ch12.md).
 *
 * - AS20-F14 the peaks tab of an install with no term reads "Henüz dönem yok" + İçe aktar, with no controls;
 * - AS20-F15 the forecast lists "Bina belirtilmemiş" last with one line saying what it is, and says once that no
 *   row has a range instead of a dash per row;
 * - CH12-F04 the ops inbox's plain line per error class;
 * - CH12-F10 a kiosk 404 with a ?date= names the window and offers today.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { plainErrorKey } from "@/components/admin/ops/ops-error-plain";
import { ForecastView } from "@/components/analytics/forecast-view";
import { PeaksView } from "@/components/analytics/peaks-view";
import { PublicNotFound } from "@/components/public-schedule/kiosk";
import { adaptiveApi, type DemandForecast } from "@/lib/api/adaptive";
import { I18nProvider } from "@/lib/i18n/provider";

const terms = vi.hoisted(() => ({ list: [] as { id: number; name: string }[] }));
vi.mock("next/navigation", () => ({ usePathname: () => "/public/rooms/C304", useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: terms.list[0], terms: terms.list, isLoading: false }) }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, can: () => false }) }));
vi.mock("@/components/charts/chart-card", () => ({ ChartCard: ({ summary }: { summary: string }) => <p data-testid="chart-card">{summary}</p> }));
vi.mock("@/components/shell/locale-toggle", () => ({ LocaleToggle: () => null }));

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("AS20-F14 · peaks tab with no term", () => {
  beforeEach(() => { terms.list = []; });
  afterEach(() => vi.restoreAllMocks());

  it("shows the needs block with İçe aktar and none of the controls", async () => {
    const peaks = vi.spyOn(adaptiveApi, "peaks");
    wrap(<PeaksView />);
    const block = await screen.findByTestId("adaptive-no-terms");
    expect(block).toHaveTextContent("Henüz dönem yok");
    expect(within(block).getByText("İçe aktar").closest("a")).toHaveAttribute("href", "/import");
    expect(screen.queryByTestId("peaks-term")).toBeNull();
    expect(screen.queryByTestId("peaks-group")).toBeNull();
    expect(screen.queryByTestId("peaks-csv")).toBeNull();
    expect(peaks).not.toHaveBeenCalled();
  });
});

describe("AS20-F15 · forecast rows", () => {
  beforeEach(() => { terms.list = [{ id: 2, name: "Güz 2026-27" }]; });
  afterEach(() => vi.restoreAllMocks());

  const cell = (key: string, label: string, value: number) => ({ key, label: { tr: label, en: label }, value, lo80: null, hi80: null, method: "requests", confidence: "high" as const });
  const demand: DemandForecast = {
    term_id: 2, term_code: "2026-GUZ", group_by: "building", method: "requests", confidence: "high",
    cells: [cell("*", "Bina belirtilmemiş", 1334), cell("A", "A blok", 82), cell("B", "B blok", 76)],
  };

  it("puts Bina belirtilmemiş last with its line, and says once that no row has a range", async () => {
    vi.spyOn(adaptiveApi, "demand").mockResolvedValue(demand);
    vi.spyOn(adaptiveApi, "shortfall").mockResolvedValue({ confidence: "none", cells: [] } as never);
    wrap(<ForecastView />);
    const list = await screen.findByTestId("forecast-cells");
    const rows = within(list).getAllByTestId("forecast-cell");
    expect(rows.map((r) => r.textContent?.slice(0, 6))).toEqual(["A blok", "B blok", "Bina b"]);
    expect(within(rows[2]!).getByTestId("forecast-unnamed-hint")).toHaveTextContent("Planlama listesinde bina yazılmamış talepler");
    expect(list).not.toHaveTextContent("—");
    expect(screen.getByTestId("forecast-no-ranges")).toHaveTextContent("Aralık yok: bu dönemin kendi talepleri sayıldı");
  });
});

describe("CH12-F04 · plain line per error class", () => {
  it("maps the database and network classes, and leaves the rest alone", () => {
    expect(plainErrorKey("OperationalError", "(sqlite3.OperationalError) database is locked [SQL: UPDATE …]")).toBe("dbLocked");
    expect(plainErrorKey("sqlalchemy.exc.OperationalError", "connection refused")).toBe("db");
    expect(plainErrorKey("http_503", "GET /api/v1/bookings/dates → 503")).toBe("server");
    expect(plainErrorKey("PendingRollbackError", "This Session's transaction has been rolled back")).toBe("rollback");
    expect(plainErrorKey("IntegrityError", "UNIQUE constraint failed")).toBe("integrity");
    expect(plainErrorKey("TypeError", "Cannot read properties of undefined")).toBeNull();
  });
});

describe("CH12-F10 · kiosk 404 with a date", () => {
  it("names the window and offers today; without a date it stays the one sentence", () => {
    const { unmount } = wrap(<PublicNotFound date="2026-09-23" />);
    expect(screen.getByTestId("public-not-found-date")).toHaveTextContent("son 7 gün ile önümüzdeki 120 günü");
    expect(screen.getByTestId("public-not-found-today")).toHaveAttribute("href", "/public/rooms/C304");
    unmount();
    wrap(<PublicNotFound />);
    expect(screen.queryByTestId("public-not-found-date")).toBeNull();
  });
});
