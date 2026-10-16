/** Schedule map → baseline import run in the onboarding Fark / Kaydet steps: which run the map goes to (the term's
 * existing baseline run or a new one), the commit's counts and the links to the run and to a re-solve keeping it. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { CouncilJob } from "@/lib/api/council";

const TERM = { id: 1, code: "2026-BAHAR", name: "Bahar 2026", kind: "REGULAR", start_date: "2026-02-16", end_date: "2026-06-05", week_count: 14, is_active: true };
const run = (id: number, params: Record<string, unknown>) => ({
  id, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "TERM", horizon_params: {}, status: "FEASIBLE", label: null, params,
  objective_value: null, soft_score: 100, hard_score: 100, stats: {}, diagnosis: [], parent_run_id: null, prompt_text: null,
  created_at: "2026-10-16T08:00:00", finished_at: "2026-10-16T08:00:10", is_active: false,
});
const db = vi.hoisted(() => ({ runs: [] as unknown[], calls: [] as string[] }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { query?: Record<string, unknown>; schema?: { parse: (v: unknown) => unknown } } = {}) => {
    db.calls.push(`${path}?${new URLSearchParams(Object.entries(opts.query ?? {}).map(([k, v]) => [k, String(v)])).toString()}`);
    const raw = path === "/terms" ? [TERM] : path === "/runs" ? db.runs : null;
    if (raw === null) throw new Error(`unexpected ${path}`);
    return opts.schema ? opts.schema.parse(raw) : raw;
  },
}));

import { BaselinePreview, BaselineResult, baselineFor, hasScheduleMap } from "./baseline-summary";

const job = (records: Record<string, number>) => ({ id: 7, status: "READY", files: [], summary: { records } }) as unknown as CouncilJob;

function wrap(ui: React.ReactNode, locale: "tr" | "en" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("helpers", () => {
  it("knows a schedule map by its booking records", () => {
    expect(hasScheduleMap(job({ booking: 10134 }))).toBe(true);
    expect(hasScheduleMap(job({ meeting: 1524, room: 54 }))).toBe(false);
  });
  it("finds the term's baseline run by params.source, never the board import or a solver run", () => {
    const runs = [run(2, {}), run(4, { source: "COUNCIL_BASELINE" }), run(3, { source: "something-else" })].map((r) => ({ ...r, params: { time_limit_s: 60, seed: 0, workers: 8, stability: true, weights: {}, ...r.params } }));
    expect(baselineFor(runs as never, "2026-BAHAR")?.id).toBe(4);
    expect(baselineFor(runs as never, "2026-GUZ")).toBeUndefined();
  });
});

describe("BaselinePreview", () => {
  it("says nothing for a file without a schedule map", () => {
    const { container } = wrap(<BaselinePreview job={job({ meeting: 1524 })} termCode="2026-BAHAR" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the term's existing baseline run and links it", async () => {
    db.runs = [run(4, { source: "COUNCIL_BASELINE", sources: [{ sha256: "ab", file: "bahar_derslikler_takvimi_2026.xlsx", job: 2 }] }), run(1, {})];
    wrap(<BaselinePreview job={job({ booking: 10134 })} termCode="2026-BAHAR" />);
    const box = await screen.findByTestId("onboarding-baseline-preview");
    await vi.waitFor(() => expect(box).toHaveAttribute("data-state", "existing"));
    expect(box).toHaveTextContent("goes into the baseline run of 2026-BAHAR (#4)");
    expect(screen.getByTestId("onboarding-baseline-existing")).toHaveAttribute("href", "/runs/4");
    expect(db.calls.some((c) => c.startsWith("/runs?") && c.includes("term_id=1"))).toBe(true);
  });

  it("says a new baseline run is made for a term without one (or a new term)", async () => {
    db.runs = [run(1, {})];
    wrap(<BaselinePreview job={job({ booking: 3 })} termCode="2027-YAZ" />, "tr");
    const box = await screen.findByTestId("onboarding-baseline-preview");
    await vi.waitFor(() => expect(box).toHaveAttribute("data-state", "new"));
    expect(box).toHaveTextContent("2027-YAZ dönemi için açılacak yeni temel çalıştırmaya");
  });
});

describe("BaselineResult", () => {
  it("shows the commit's counts, what was skipped and the links", () => {
    wrap(<BaselineResult baseline={{ run_id: 4, run_created: true, created: 8954, updated: 0, unchanged: 0, linked: 8630, unlinked: 324, clipped_outside_term: 12, linked_by_start: 8410 }} />);
    const box = screen.getByTestId("onboarding-baseline-result");
    expect(box).toHaveTextContent("Baseline run #4 created");
    expect(box).toHaveTextContent("8,954");
    expect(box).toHaveTextContent("324");
    expect(screen.getByTestId("onboarding-baseline-skipped")).toHaveTextContent("12 entries fell outside the term's dates");
    expect(screen.getByTestId("onboarding-baseline-open")).toHaveAttribute("href", "/runs/4");
    expect(screen.getByTestId("onboarding-baseline-resolve")).toHaveAttribute("href", "/runs/4?resolve=1");
  });
});
