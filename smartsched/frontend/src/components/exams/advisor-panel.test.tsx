/** AS-17 exam advisor: the AS-12 cards and ranked moves with an edit link (advice only), the load-derived fallback. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { adaptiveApi, type ExamForecast } from "@/lib/api/adaptive";
import { HttpError } from "@/lib/api/client";
import { I18nProvider } from "@/lib/i18n/provider";
import { examAdvice } from "./advisor-model";
import { ExamAdvisorView } from "./advisor-panel";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("term=4") }));
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 2, name: "Bahar" }, terms: [{ id: 2, name: "Bahar", kind: "REGULAR", is_active: true }, { id: 4, name: "Final", kind: "FINAL", is_active: true }], isLoading: false }) }));
vi.mock("@/components/charts/chart-card", () => ({ ChartCard: ({ summary }: { summary: string }) => <p data-testid="chart-card">{summary}</p> }));

const forecast: ExamForecast = {
  method: "requests", confidence: "high",
  days: [{ date: "2026-06-01", label: { tr: "1 Haziran 2026 Pazartesi", en: "Monday 01 June 2026" }, exams: 9, seats: 900 }, { date: "2026-06-02", exams: 3, seats: 200 }],
  peak_day: "2026-06-01", peak_label: { tr: "1 Haziran 2026 Pazartesi", en: "Monday" }, peak_exams: 9, weekday_mean: 3.2, peak_to_mean: 2.8,
  slots: [{ date: "2026-06-01", period: 3, exams: 4, seats: 520, exam_capacity: 480, seat_pct: 108, invigilators: 12, pool: 9, invigilators_short: 3 }],
};

function mount() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr"><ExamAdvisorView /></I18nProvider>
    </QueryClientProvider>,
  );
}

describe("examAdvice (fallback)", () => {
  it("cards the peak day, a slot over the exam seats and invigilators short", () => {
    const kinds = examAdvice(forecast, "tr").map((a) => a.kind);
    expect(kinds).toEqual(["peak_day", "seats", "invigilators"]);
    expect(examAdvice({ ...forecast, peak_to_mean: 1.1, slots: [] }, "tr")).toEqual([]);
  });
});

describe("ExamAdvisorView", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the advisor's cards and ranked moves with a link to edit the exam request (term from the URL)", async () => {
    const exams = vi.spyOn(adaptiveApi, "exams").mockResolvedValue(forecast);
    vi.spyOn(adaptiveApi, "examAdvice").mockResolvedValue({
      confidence: "high", basis: { tr: "Hiçbir şey otomatik değişmez.", en: "Nothing changes automatically." },
      cards: [{ kind: "cohort_day", date: "2026-06-01", text: { tr: "Tıp 1. sınıf: 1 Haziran'da 3 sınav; en çok 2", en: "x" }, request_ids: [11], suggestion_ranks: [1] }],
      suggestions: [{ rank: 1, exam_id: 3, request_ids: [11], label: "TIP101", from: { date: "2026-06-01" }, to: { date: "2026-06-03" }, kind: "date", text: { tr: "TIP101 sınavını 3 Haziran'a al: kohort çakışması −1", en: "y" } }],
    });
    mount();
    const card = await screen.findByTestId("advisor-card");
    expect(card).toHaveTextContent("3 sınav; en çok 2");
    expect(card).toHaveTextContent("Önerilen taşıma: #1");
    const move = screen.getByTestId("advisor-move");
    expect(move).toHaveTextContent("#1TIP101 sınavını 3 Haziran'a al");
    expect(within(move).getByTestId("advisor-edit")).toHaveAttribute("href", "/requests?kind=exams&id=11&term=4");
    expect(exams).toHaveBeenCalledWith(4);
  });

  it("falls back to the load cards while the advisor route is missing (404)", async () => {
    vi.spyOn(adaptiveApi, "exams").mockResolvedValue(forecast);
    vi.spyOn(adaptiveApi, "examAdvice").mockRejectedValue(new HttpError(404, "Not Found"));
    mount();
    const cards = await screen.findAllByTestId("advisor-card");
    expect(cards.map((c) => c.getAttribute("data-kind"))).toEqual(["peak_day", "seats", "invigilators"]);
    expect(cards[1]).toHaveTextContent("520 öğrenci, sınav salonlarında 480 koltuk (%108).");
  });

  it("an install without dated exams reads the needs sentence", async () => {
    vi.spyOn(adaptiveApi, "exams").mockResolvedValue({ ...forecast, confidence: "none", days: [], slots: [], needs: { tr: "Tarihli sınav listesi gerekli", en: "x" } });
    vi.spyOn(adaptiveApi, "examAdvice").mockRejectedValue(new HttpError(404, "Not Found"));
    mount();
    expect(await screen.findByTestId("advisor-needs")).toHaveTextContent("Tarihli sınav listesi gerekli");
  });
});
