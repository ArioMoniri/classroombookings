import { fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ChartApi } from "@/components/charts/chart-form-types";
import { ScheduleRun } from "@/lib/api/schemas";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/components/charts/chart-lazy", () => ({
  LazyLineChart: (p: { data: { label: string }[]; dots?: boolean; xTickFormatter: (s: string) => string; onReady: (a: ChartApi) => void }) => {
    useEffect(() => p.onReady({ getDataURL: () => null, dispatchAction: () => undefined, showTip: () => undefined, hideTip: () => undefined, indexAt: () => 0 }), [p]);
    return <div data-testid="line" data-dots={String(!!p.dots)} data-ticks={p.data.map((r) => p.xTickFormatter(r.label)).join("|")} />;
  },
}));

import { ScoreHistory } from "./score-history";

const run = (id: number, soft: number, finished: string, over: Record<string, unknown> = {}) =>
  ScheduleRun.parse({ id, term_id: 1, term_code: "B", kind: "COURSE", horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", params: {}, objective_value: null, soft_score: soft, hard_score: 100, stats: { solver: "cp-sat" }, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: finished, finished_at: finished, ...over });
const runs = [run(12, 81, "2026-10-14T09:00:00Z", { is_active: true }), run(15, 88, "2026-10-16T09:00:00Z"), run(9, 70, "2026-10-12T09:00:00Z"), run(16, 0, "2026-10-17T09:00:00Z", { status: "CANCELLED" })];

describe("CH-08 soft score history on /runs", { timeout: 20_000 }, () => {
  it("a line with dots in finish order; the active run is labelled; cancelled runs are left out", () => {
    render(<ScoreHistory runs={runs} />);
    const fig = screen.getByRole("figure", { name: "Çalıştırmalara göre yumuşak puan" });
    expect(fig).toHaveAccessibleDescription(/Etkin çalıştırma #12: 81\. Son çalıştırma #15: 88; en yüksek #15 \(88\)\./);
    const line = within(fig).getByTestId("line");
    expect(line).toHaveAttribute("data-dots", "true");
    expect(line).toHaveAttribute("data-ticks", "#9|#12 etkin|#15");
    expect(within(within(fig).getByRole("table")).getAllByRole("row")).toHaveLength(4);
  });

  it("renders nothing with fewer than 3 finished runs", () => {
    const { container } = render(<ScoreHistory runs={runs.slice(0, 2)} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("←/→ then Enter opens that run; a tap on a dot opens it too; the hint says so", () => {
    push.mockClear();
    render(<ScoreHistory runs={runs} />);
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    fireEvent.keyDown(group, { key: "ArrowRight" });
    fireEvent.keyDown(group, { key: "ArrowRight" });
    fireEvent.keyDown(group, { key: "Enter" });
    expect(push).toHaveBeenLastCalledWith("/runs/12");
    fireEvent.click(group, { clientX: 10, clientY: 10 });
    expect(push).toHaveBeenLastCalledWith("/runs/9");
    expect(screen.getByTestId("chart-select-hint-runs-soft-score")).toHaveTextContent(/Enter/);
  });
});
