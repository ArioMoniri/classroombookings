/**
 * Round-1 R1-M-05: the timetable banner reads the run's truth through the real run adapter (the structured stats
 * live in `stats_detail`; `stats` keeps only flat numbers) and names the broken rule with the forced move's reason.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { BrokenRulesBanner } from "./broken-banner";

const raw = {
  id: 7, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, status: "FEASIBLE_PARTIAL",
  params: {}, objective_value: null, soft_score: 80, hard_score: 99, is_active: true, diagnosis: [], parent_run_id: null, prompt_text: null,
  created_at: "2026-10-16T10:00:00Z", finished_at: "2026-10-16T10:01:00Z", label: null,
  stats: {
    placed: 682, events_total: 716,
    truth: {
      verdict: "broken", placed: 682, total: 716, unplaced: 34, hard_score: 99, broken_count: 1, exceptions: [], exceptions_total: 0,
      broken: [{ rule: "room_double_booking", message: "C201 week 3 day 1 P2: HEM 242, MAT 112 §1", request_ids: [518, 738], explained: true, reason: "Bölüm başkanı onayı, tek seferlik", by_name: "Administrator", at: null }],
      headline: { tr: "682/716 ders yerleşti · 1 kesin kural bozuk (1 gerekçeli zorunlu taşıma)", en: "x" },
    },
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("broken-rule banner (R1-M-05)", () => {
  it("names the published run's broken rule and the reason", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(raw), { status: 200, headers: { "Content-Type": "application/json" } })));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <BrokenRulesBanner runId={7} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const banner = await screen.findByTestId("run-broken-banner");
    expect(banner).toHaveTextContent("Yayımdaki program 1 kesin kuralı bozuyor (katı puan 99)");
    expect(banner).toHaveTextContent("derslik çakışması");
    expect(banner).toHaveTextContent("Bölüm başkanı onayı, tek seferlik");
  });
});
