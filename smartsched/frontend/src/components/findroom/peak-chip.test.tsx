/** AS-17 "Yoğun saat" on /find-room: a Wednesday P4 search is a peak; the nearest calmer span is named. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { adaptiveApi, type PeakCell } from "@/lib/api/adaptive";
import { I18nProvider } from "@/lib/i18n/provider";
import { PeakChip } from "./peak-chip";

const cell = (period: number, peak: boolean): PeakCell => ({ day: 3, period, group: "*", value: peak ? 93 : 50, lo80: 40, hi80: 97, n_weeks: 12, rooms: 80, peak, label: { tr: `Çarşamba ${period}. ders`, en: "x" } });
const peaks = (confidence: "medium" | "none") => ({ term_id: 2, term_code: "B", period_kind: "LECTURE", group_by: "campus", threshold_pct: 85, weeks: [], rooms: 80, cells: [1, 2, 3, 4, 5, 6].map((p) => cell(p, p === 4)), peaks: [], period_profile: [], method: "shrunk_weekly_mean", confidence });

function mount(slot: { date: string; start_period: number; end_period: number }) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr"><PeakChip termId={2} slot={slot} /></I18nProvider>
    </QueryClientProvider>,
  );
}

describe("PeakChip", () => {
  afterEach(() => vi.restoreAllMocks());

  it("marks a Wednesday P4 search and offers P3", async () => {
    const spy = vi.spyOn(adaptiveApi, "campusPeaks").mockResolvedValue(peaks("medium"));
    mount({ date: "2026-10-21", start_period: 4, end_period: 4 });
    const chip = await screen.findByTestId("fr-peak");
    expect(chip).toHaveTextContent("Yoğun saat");
    expect(chip).toHaveTextContent("odaların genellikle %93'si dolu");
    expect(screen.getByTestId("fr-peak-alt")).toHaveTextContent("Daha sakin: Çarşamba 3. ders.");
    expect(spy).toHaveBeenCalledWith(2);
  });

  it("stays silent off peak and without history", async () => {
    vi.spyOn(adaptiveApi, "campusPeaks").mockResolvedValue(peaks("medium"));
    mount({ date: "2026-10-21", start_period: 2, end_period: 2 });
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("fr-peak")).toBeNull();
  });
});
