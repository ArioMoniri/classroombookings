/** Schedule map → baseline import run in the onboarding Fark / Kaydet steps: where the map goes (from the dry run's
 * `result.baseline_run`: the existing baseline run, a new one, a chosen run or nowhere), the target picker (auto /
 * another run / skip), the commit's counts and the links to the run and to a re-solve keeping it. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { BaselineRunResult, type BaselineTarget, type CouncilJob } from "@/lib/api/council";

const TERM = { id: 1, code: "2026-BAHAR", name: "Bahar 2026", kind: "REGULAR", start_date: "2026-02-16", end_date: "2026-06-05", week_count: 14, is_active: true };
const run = (id: number, params: Record<string, unknown>, extra: Record<string, unknown> = {}) => ({
  id, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "TERM", horizon_params: {}, status: "FEASIBLE", label: null, params,
  objective_value: null, soft_score: 100, hard_score: 100, stats: {}, diagnosis: [], parent_run_id: null, prompt_text: null,
  created_at: "2026-10-16T08:00:00", finished_at: "2026-10-16T08:00:10", is_active: false, ...extra,
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

import { BaselinePreview, BaselineResult, BaselineTargetPicker, hasScheduleMap, targetReady, targetRuns } from "./baseline-summary";

const job = (records: Record<string, number>) => ({ id: 7, status: "READY", files: [], summary: { records } }) as unknown as CouncilJob;
const base = (v: Record<string, unknown>) => BaselineRunResult.parse({ run_created: false, created: 0, updated: 0, unchanged: 0, linked: 0, unlinked: 0, ...v });

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
  it("offers finished, inactive COURSE runs of the term as targets, never the baseline run itself", () => {
    const withParams = (r: ReturnType<typeof run>) => ({ ...r, params: { time_limit_s: 60, seed: 0, workers: 8, stability: true, weights: {}, ...r.params } });
    const runs = [run(2, {}), run(4, { source: "COUNCIL_BASELINE" }), run(5, {}, { is_active: true }), run(6, {}, { status: "RUNNING" }), run(7, {}, { kind: "EXAM" }), run(8, {})].map(withParams);
    expect(targetRuns(runs as never, "2026-BAHAR").map((r) => r.id)).toEqual([8, 2]);
    expect(targetRuns(runs as never, "2026-GUZ")).toEqual([]);
    expect(targetReady({ mode: "run", run_id: 0 })).toBe(false);
    expect(targetReady({ mode: "skip" })).toBe(true);
  });
});

describe("BaselinePreview (Fark)", () => {
  it("says nothing for a file without a schedule map", () => {
    const { container } = wrap(<BaselinePreview job={job({ meeting: 1524 })} termCode="2026-BAHAR" baseline={null} diffDone />);
    expect(container).toBeEmptyDOMElement();
  });
  it("asks for the diff first, then names the existing baseline run with the dry run's counts", () => {
    const { rerender } = wrap(<BaselinePreview job={job({ booking: 10134 })} termCode="2026-BAHAR" baseline={undefined} diffDone={false} />);
    expect(screen.getByTestId("onboarding-baseline-preview")).toHaveAttribute("data-state", "pending");
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="en">
          <BaselinePreview job={job({ booking: 10134 })} termCode="2026-BAHAR" baseline={base({ run_id: 4, unchanged: 8954, linked: 8630, unlinked: 324 })} diffDone />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const box = screen.getByTestId("onboarding-baseline-preview");
    expect(box).toHaveAttribute("data-state", "existing");
    expect(box).toHaveTextContent("goes into the baseline run of 2026-BAHAR (#4)");
    expect(box).toHaveTextContent("8,954");
    expect(screen.getByTestId("onboarding-baseline-existing")).toHaveAttribute("href", "/runs/4");
    expect(db.calls.filter((c) => c.startsWith("/runs"))).toEqual([]); // read from the dry run, not inferred from the runs list
  });
  it("tells a new run, a chosen run and a skipped map apart (TR)", () => {
    const { unmount } = wrap(<BaselinePreview job={job({ booking: 3 })} termCode="2027-YAZ" baseline={base({ run_id: null, run_created: true, created: 3 })} diffDone />, "tr");
    expect(screen.getByTestId("onboarding-baseline-preview")).toHaveAttribute("data-state", "new");
    expect(screen.getByTestId("onboarding-baseline-preview")).toHaveTextContent("2027-YAZ dönemi için açılacak yeni temel çalıştırmaya");
    expect(screen.queryByTestId("onboarding-baseline-existing")).not.toBeInTheDocument();
    unmount();
    const r2 = wrap(<BaselinePreview job={job({ booking: 3 })} termCode="2026-BAHAR" baseline={base({ run_id: 9, mode: "run", created: 3 })} diffDone />, "tr");
    expect(screen.getByTestId("onboarding-baseline-preview")).toHaveTextContent("2026-BAHAR döneminin #9 numaralı çalıştırmasına yazılacak");
    r2.unmount();
    wrap(<BaselinePreview job={job({ booking: 3 })} termCode="2026-BAHAR" baseline={base({ run_id: null, mode: "skip", skipped: true, entries: 12 })} diffDone />, "tr");
    expect(screen.getByTestId("onboarding-baseline-preview")).toHaveAttribute("data-state", "skip");
    expect(screen.getByTestId("onboarding-baseline-preview")).toHaveTextContent("Program haritası yazılmayacak (12 ders girişi atlanır).");
  });
});

function Picker({ initial = { mode: "auto" } as BaselineTarget, termCode = "2026-BAHAR", spy }: { initial?: BaselineTarget; termCode?: string; spy: (v: BaselineTarget) => void }) {
  const [v, setV] = useState<BaselineTarget>(initial);
  return <BaselineTargetPicker job={job({ booking: 10 })} termCode={termCode} value={v} onChange={(x) => { setV(x); spy(x); }} />;
}

describe("BaselineTargetPicker (Kaydet)", () => {
  it("switches between the baseline run, another run of the term and not writing the map", async () => {
    const user = userEvent.setup();
    db.runs = [run(4, { source: "COUNCIL_BASELINE" }), run(11, {}, { label: "Plan A" }), run(12, {}, { is_active: true })];
    const spy = vi.fn();
    wrap(<Picker spy={spy} />);
    expect(screen.getByRole("radiogroup", { name: "Where the schedule map goes" })).toBeInTheDocument();
    await user.click(await screen.findByRole("radio", { name: "Another run" }));
    const select = await screen.findByTestId("baseline-target-run");
    expect(select).toHaveTextContent("#11 · Plan A · FEASIBLE");
    expect(select).not.toHaveTextContent("#12");
    expect(spy).toHaveBeenLastCalledWith({ mode: "run", run_id: 11 });
    await user.click(screen.getByRole("radio", { name: "Do not write" }));
    expect(spy).toHaveBeenLastCalledWith({ mode: "skip" });
    expect(screen.getByTestId("onboarding-baseline-target")).toHaveTextContent("Requests and rooms are written; the schedule map goes into no run.");
  });
  it("cannot target another run of a term that does not exist yet", async () => {
    wrap(<Picker termCode="2030-YAZ" spy={vi.fn()} />, "tr");
    const other = await screen.findByRole("radio", { name: "Başka çalıştırma" });
    await vi.waitFor(() => expect(other).toBeDisabled());
  });
});

describe("BaselineResult", () => {
  it("shows the commit's counts, what was skipped and the links", () => {
    wrap(<BaselineResult baseline={base({ run_id: 4, run_created: true, created: 8954, linked: 8630, unlinked: 324, clipped_outside_term: 12, linked_by_start: 8410 })} />);
    const box = screen.getByTestId("onboarding-baseline-result");
    expect(box).toHaveTextContent("Baseline run #4 created");
    expect(box).toHaveTextContent("8,954");
    expect(box).toHaveTextContent("324");
    expect(screen.getByTestId("onboarding-baseline-skipped")).toHaveTextContent("12 entries fell outside the term's dates");
    expect(screen.getByTestId("onboarding-baseline-open")).toHaveAttribute("href", "/runs/4");
    expect(screen.getByTestId("onboarding-baseline-resolve")).toHaveAttribute("href", "/runs/4?resolve=1");
  });
  it("names a chosen run and a skipped map", () => {
    const { unmount } = wrap(<BaselineResult baseline={base({ run_id: 9, mode: "run", created: 5 })} />);
    expect(screen.getByTestId("onboarding-baseline-result")).toHaveTextContent("Schedule map written into run #9");
    unmount();
    wrap(<BaselineResult baseline={base({ run_id: null, mode: "skip", skipped: true, entries: 40 })} />);
    expect(screen.getByTestId("onboarding-baseline-result")).toHaveTextContent("Schedule map not written");
    expect(screen.queryByTestId("onboarding-baseline-open")).not.toBeInTheDocument();
  });
});
