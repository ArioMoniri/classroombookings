/**
 * FIX-F (2026-10-18): round-4 AS-20 / CH-12 findings (docs/testing/round4/2026-10-18-as20.md, -ch12.md).
 *
 * - AS20-F03 the find-room peak chip reads the campus peaks every signed-in person may read;
 * - AS20-F04 an advisor move is applied with one tap ("Uygula") and undone from the toast; /classes honours ?term=;
 * - AS20-F05 the advisor leads with the peak day: at most 5 cards and 10 moves, the rest behind "Tümünü göster";
 * - AS20-F11 / F12 the revert toast tells "already current" from a real revert; the Turkish needs no suffix;
 * - AS20-F14 an install with no term reads the needs sentence with a link to /import, not "Önce bir dönem seçin.";
 * - CH12-F03 the peaks period-profile chart has its summary sentence even when no hour is a peak.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ForecastView } from "@/components/analytics/forecast-view";
import { PeaksView } from "@/components/analytics/peaks-view";
import { ExamAdvisorView } from "@/components/exams/advisor-panel";
import { PeakChip } from "@/components/findroom/peak-chip";
import { LearningVersions } from "@/components/learning/learning-versions";
import { adaptiveApi, type AdviceCard, type AdviceMove, type ExamForecast, type PeakCell, type Peaks } from "@/lib/api/adaptive";
import { learningVersionsApi, type LearningVersion } from "@/lib/api/learning-versions";
import { translate } from "@/lib/i18n";
import { I18nProvider } from "@/lib/i18n/provider";

const terms = vi.hoisted(() => ({ list: [] as { id: number; name: string; kind?: string; is_active?: boolean }[] }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("term=4"), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: terms.list[0], terms: terms.list, isLoading: false }) }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, can: () => true }) }));
vi.mock("@/components/charts/chart-card", () => ({ ChartCard: ({ summary }: { summary: string }) => <p data-testid="chart-card">{summary}</p> }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() } }));

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

const src = (p: string) => readFileSync(join(__dirname, "..", p), "utf8");

const forecast: ExamForecast = {
  method: "requests", confidence: "high",
  days: [{ date: "2026-06-03", label: { tr: "3 Haziran 2026 Çarşamba", en: "x" }, exams: 126, seats: 9000 }],
  peak_day: "2026-06-03", peak_label: { tr: "3 Haziran 2026 Çarşamba", en: "x" }, peak_exams: 126, weekday_mean: 67.5, peak_to_mean: 1.87, slots: [],
};
const card = (kind: string, i: number): AdviceCard => ({ kind, date: "2026-06-03", text: { tr: `${kind} kartı ${i}`, en: "x" }, request_ids: [], suggestion_ranks: [] });
const move = (rank: number): AdviceMove => ({ rank, exam_id: 270 + rank, request_ids: [270 + rank], label: `PRO${rank}`, from: { date: "2026-06-03", start: 3, end: 4 }, to: { date: "2026-06-01", start: 5, end: 6 }, kind: "date", text: { tr: `PRO${rank} sınavını 1 Haziran'a al`, en: "x" } });

describe("AS20-F05 · the advisor leads with the peak day", () => {
  beforeEach(() => { terms.list = [{ id: 2, name: "Güz", kind: "REGULAR", is_active: true }, { id: 4, name: "Final 2026", kind: "FINAL", is_active: true }]; });
  afterEach(() => vi.restoreAllMocks());

  it("sorts the cards by kind (peak day first), shows 5 cards and 10 moves, the rest behind Tümünü göster", async () => {
    vi.spyOn(adaptiveApi, "exams").mockResolvedValue(forecast);
    const cards = [card("clash", 1), card("back_to_back", 2), card("clash", 3), card("cohort_day", 4), card("peak_day", 5), card("seats", 6), card("clash", 7), card("back_to_back", 8)];
    vi.spyOn(adaptiveApi, "examAdvice").mockResolvedValue({ confidence: "high", cards, suggestions: Array.from({ length: 12 }, (_, i) => move(i + 1)) });
    wrap(<ExamAdvisorView />);
    const shown = await screen.findAllByTestId("advisor-card");
    expect(shown.map((c) => c.getAttribute("data-kind"))).toEqual(["peak_day", "seats", "cohort_day", "clash", "clash"]);
    expect(screen.getAllByTestId("advisor-move")).toHaveLength(10);
    fireEvent.click(screen.getByTestId("advisor-cards-all"));
    expect(screen.getAllByTestId("advisor-card")).toHaveLength(8);
    fireEvent.click(screen.getByTestId("advisor-moves-all"));
    expect(screen.getAllByTestId("advisor-move")).toHaveLength(12);
  });
});

describe("AS20-F04 · Uygula moves the exam, the toast undoes it", () => {
  beforeEach(() => { terms.list = [{ id: 4, name: "Final 2026", kind: "FINAL", is_active: true }]; });
  afterEach(() => vi.restoreAllMocks());

  it("applies the move with its date and start, then the toast's Geri al sends the undo body", async () => {
    vi.spyOn(adaptiveApi, "exams").mockResolvedValue(forecast);
    vi.spyOn(adaptiveApi, "examAdvice").mockResolvedValue({ confidence: "high", cards: [card("peak_day", 1)], suggestions: [move(2)] });
    const undo = { term_id: 4, request_ids: [272], date: "2026-06-03", start_period: 3 };
    const apply = vi.spyOn(adaptiveApi, "applyAdvice").mockResolvedValue({ applied: [272], undo, message_tr: "PRO2 1 Haziran 2026 Pazartesi gününe taşındı.", message_en: "x" });
    wrap(<ExamAdvisorView />);
    const row = await screen.findByTestId("advisor-move");
    const btn = within(row).getByTestId("advisor-apply");
    expect(btn).toHaveTextContent("Uygula");
    await act(async () => { fireEvent.click(btn); });
    await waitFor(() => expect(apply).toHaveBeenCalledWith({ term_id: 4, request_ids: [272], date: "2026-06-01", start_period: 5 }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const [msg, opts] = vi.mocked(toast.success).mock.calls.at(-1)! as [string, { action: { label: string; onClick: () => void } }];
    expect(msg).toBe("PRO2 1 Haziran 2026 Pazartesi gününe taşındı.");
    expect(opts.action.label).toBe("Geri al");
    await act(async () => { opts.action.onClick(); });
    await waitFor(() => expect(apply).toHaveBeenLastCalledWith(undo));
  });

  it("/classes reads the term of the link (the advisor's Final term, not the sidebar's)", () => {
    expect(src("components/classes/classes-page.tsx")).toContain('useTermContext(Number(params.get("term")) || null)');
  });
});

describe("AS20-F14 · no term yet", () => {
  beforeEach(() => { terms.list = []; });
  afterEach(() => vi.restoreAllMocks());

  it("the advisor and the forecast read the needs sentence with a link to İçe aktar", async () => {
    wrap(<ExamAdvisorView />);
    const needs = await screen.findByTestId("adaptive-no-terms");
    expect(needs).toHaveTextContent("Henüz dönem yok");
    expect(within(needs).getByText("İçe aktar").closest("a")).toHaveAttribute("href", "/import");
    expect(screen.queryByTestId("advisor-term")).toBeNull();
    expect(screen.queryByText("Önce bir dönem seçin.")).toBeNull();
  });

  it("the forecast too", async () => {
    wrap(<ForecastView />);
    expect(await screen.findByTestId("adaptive-no-terms")).toHaveTextContent("Henüz dönem yok");
    expect(screen.queryByTestId("forecast-term")).toBeNull();
  });
});

describe("AS20-F03 · the find-room chip reads the campus peaks", () => {
  afterEach(() => vi.restoreAllMocks());
  const cell = (period: number, peak: boolean): PeakCell => ({ day: 3, period, group: "*", value: peak ? 92 : 40, lo80: 30, hi80: 95, n_weeks: 2, rooms: 80, peak, label: { tr: "x", en: "x" } });

  it("asks GET /analytics/peaks/campus (an academician has no planning.view)", async () => {
    const campus = vi.spyOn(adaptiveApi, "campusPeaks").mockResolvedValue({ term_id: 2, term_code: "G", period_kind: "LECTURE", group_by: "campus", threshold_pct: 85, weeks: [1, 2], rooms: 80, cells: [1, 2, 3, 4, 5].map((p) => cell(p, p === 4)), peaks: [], period_profile: [], method: "shrunk_weekly_mean", confidence: "low" });
    const planner = vi.spyOn(adaptiveApi, "peaks");
    wrap(<PeakChip termId={2} slot={{ date: "2026-10-21", start_period: 4, end_period: 4 }} />);
    expect(await screen.findByTestId("fr-peak")).toHaveTextContent("Yoğun saat");
    expect(campus).toHaveBeenCalledWith(2);
    expect(planner).not.toHaveBeenCalled();
  });
});

describe("AS20-F11 / F12 · learning revert", () => {
  const v = (id: number, number: number): LearningVersion => ({ id, number, trigger: "manual", trigger_label: { tr: "Elle", en: "x" }, created_at: "2026-10-18T06:00:00", observations: 1, priors: 1, suggestible: 1, checksum: "", diff: { new: [], dropped: [], changed: [], counts: { new: 0, dropped: 0, changed: 0 } }, restored_from: null });
  beforeEach(() => {
    vi.spyOn(learningVersionsApi, "settings").mockResolvedValue({ nightly_refresh: false });
    vi.spyOn(learningVersionsApi, "versions").mockResolvedValue({ versions: [v(12, 3), v(11, 2)], pinned_version_id: null, nightly_refresh: false });
    // a slow refetch elsewhere on the page (calibration over a big term, a busy SQLite) must not hold the toast back
    // (the 1440 run: no toast and a stale list 4 s after the revert)
    vi.spyOn(learningVersionsApi, "calibration").mockReturnValue(new Promise(() => {}));
  });
  afterEach(() => vi.restoreAllMocks());

  it("says 'already current' only when the server wrote no new version", async () => {
    vi.spyOn(learningVersionsApi, "revert").mockResolvedValue({ identical: true, unchanged: true, version: v(12, 3) });
    wrap(<LearningVersions termId={2} />);
    const rows = await screen.findAllByTestId("version-row");
    fireEvent.click(within(rows[1]!).getByTestId("version-revert"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("2. sürüme dönülsün mü?");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Bu sürüme dön" })); });
    await waitFor(() => expect(toast.success).toHaveBeenLastCalledWith("2. sürüm zaten geçerli olanla aynı; yeni sürüm yazılmadı."));
  });

  it("a real revert (identical snapshot, new version) says it reverted", async () => {
    vi.spyOn(learningVersionsApi, "revert").mockResolvedValue({ identical: true, unchanged: false, version: v(13, 4) });
    wrap(<LearningVersions termId={2} />);
    const rows = await screen.findAllByTestId("version-row");
    fireEvent.click(within(rows[1]!).getByTestId("version-revert"));
    const dialog = await screen.findByRole("alertdialog");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Bu sürüme dön" })); });
    await waitFor(() => expect(toast.success).toHaveBeenLastCalledWith("2. sürüme dönüldü."));
  });

  it("the Turkish strings need no suffix harmony", () => {
    expect(translate("tr", "adaptive.learning.revertTitle", { n: 2 })).toBe("2. sürüme dönülsün mü?");
    expect(translate("tr", "adaptive.learning.reverted", { n: 6 })).toBe("6. sürüme dönüldü.");
  });
});

describe("CH12-F03 · the peaks profile chart always has its summary", () => {
  beforeEach(() => { terms.list = [{ id: 2, name: "Güz" }]; });
  afterEach(() => vi.restoreAllMocks());

  it("names the busiest period even when no hour passes the threshold", async () => {
    const peaks: Peaks = { term_id: 2, term_code: "G", period_kind: "LECTURE", group_by: "building", threshold_pct: 85, weeks: [1, 2], rooms: 80, cells: [{ day: 1, period: 4, group: "A", value: 62, lo80: 50, hi80: 70, n_weeks: 2, rooms: 20, peak: false, label: { tr: "Pazartesi 4. ders", en: "x" } }], peaks: [], period_profile: [{ period: 3, value: 40 }, { period: 4, value: 62 }, { period: 5, value: 50 }], method: "shrunk_weekly_mean", confidence: "low" };
    vi.spyOn(adaptiveApi, "peaks").mockResolvedValue(peaks);
    wrap(<PeaksView />);
    await waitFor(() => expect(screen.getByTestId("chart-card")).toHaveTextContent("Gün içinde en yoğun saat 4. ders."));
  });
});

describe("AS20-F10 · the focus stays on the button that started the work", () => {
  it("Öğrenmeyi yenile and Düzenlemelerden ağırlık öner are not disabled while busy (a disabled button drops focus to <body>)", () => {
    const lv = src("components/learning/learning-versions.tsx");
    expect(lv).toContain('disabled={termId === null} aria-busy={act.refresh.isPending || undefined} data-testid="learning-refresh"');
    expect(lv).toContain("if (termId === null || act.refresh.isPending) return;");
    const sp = src("components/seasons/season-profiles.tsx");
    expect(sp).toContain('disabled={termId === null} aria-busy={act.propose.isPending || undefined} data-testid="profile-propose"');
    expect(sp).toContain("if (termId === null || act.propose.isPending) return;");
  });
});

describe("AS20-F07 · a scenario run says so on its own page", () => {
  it("keeps params.scenario and shows the Senaryo badge with the run's label", async () => {
    const { RunParams } = await import("@/lib/api/schemas");
    const { RunScenarioLine } = await import("@/components/runs/run-profile");
    const params = RunParams.parse({ scenario: { enrolment_pct: 10, scope: "all" } });
    expect(params.scenario).toEqual({ enrolment_pct: 10, scope: "all" });
    const view = wrap(<RunScenarioLine r={{ label: "Senaryo: +10 % kontenjan", params }} />);
    expect(screen.getByTestId("run-scenario")).toHaveTextContent("Senaryo taslağı");
    expect(screen.getByTestId("run-scenario")).toHaveTextContent("Senaryo: +10 % kontenjan");
    view.unmount();
    wrap(<RunScenarioLine r={{ label: "Bahar 3. hafta", params: RunParams.parse({}) }} />);
    expect(screen.queryByTestId("run-scenario")).toBeNull();
  });
});

describe("CH12-F06 · print shows the page, not the app chrome", () => {
  it("hides the sidebar, both top bars and the tab bar in print", () => {
    const css = src("app/globals.css");
    const block = css.slice(css.indexOf("/* CH12-F06"));
    expect(block).toContain("@media print");
    for (const sel of ["[data-app-shell] > aside", "[data-app-shell] > div > header", '[data-slot="tab-bar"]']) expect(block).toContain(sel);
  });
});

describe("CH12-F05 · 44 px hit areas around the charts on phones", () => {
  it("the dashboard KPI numbers, the runs table links and the profile's inline links grow on touch", () => {
    const cases: [string, string][] = [
      ["components/dashboard/dashboard-view.tsx", 'className={cn("relative rounded-md type-kpi'],
      ["components/runs/runs-list.tsx", 'className={cn("relative truncate font-medium text-label-1'],
      ["components/notifications/preferences-panel.tsx", 'href="/profile#channels" className={cn("relative'],
      ["components/settings/calendar-connections.tsx", 'href="/profile#privacy" className={cn("relative'],
      ["components/privacy/calendar-consent.tsx", 'href={refusal.href} className={cn("relative'],
      ["components/privacy/calendar-consent.tsx", 'href={GRANT_PATH} className={cn("relative'],
    ];
    for (const [file, needle] of cases) {
      const line = src(file).split("\n").find((l) => l.includes(needle));
      expect(line, `${file}: ${needle}`).toBeDefined();
      expect(line).toContain("coarseHitArea");
    }
  });
});
