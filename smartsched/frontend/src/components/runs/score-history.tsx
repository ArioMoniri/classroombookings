"use client";
/**
 * /runs › "Çalıştırmalara göre yumuşak puan" (CH-08, docs/design/v3/charts.md §4 row 12): this term's finished
 * course runs in the order they finished, as a line with a dot per run (EvilCharts ECharts line, lazy). The active
 * (published) run is labelled on the axis. Nothing renders with fewer than 3 finished runs. A tap or click on a dot,
 * or ←/→ then Enter, opens that run; the table twin lists the same runs. CH12-F02 (FIX-G): on touch the first tap
 * on a dot only previews it (the chart's tooltip) and the second tap on the same dot opens it, so a scroll that
 * starts on the chart never opens a run; mouse clicks and Enter open at once. Original work.
 */
import { useRouter } from "next/navigation";
import { useMemo, useRef } from "react";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { useChartFormat } from "@/components/charts/chart-format";
import { LazyLineChart } from "@/components/charts/chart-lazy";
import { singleConfig } from "@/components/charts/chart-tokens";
import { Card } from "@/components/ui/card";
import { COARSE_POINTER, useMediaQuery } from "@/components/ui/use-media-query";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { MIN_RUNS, scoreHistory, scoreSummary, type ScorePoint } from "./score-history-model";

export function ScoreHistory({ runs, userId }: { runs: readonly ScheduleRun[] | undefined; userId?: number | null }) {
  const { t } = useI18n();
  const f = useChartFormat();
  const router = useRouter();
  const coarse = useMediaQuery(COARSE_POINTER);
  /** the pointer of the press that led to the select ("touch" arms a dot first); a key press clears it */
  const pointer = useRef<string | null>(null);
  const armed = useRef<number | null>(null);
  const points = useMemo(() => scoreHistory(runs), [runs]);
  const config = useMemo(() => singleConfig("soft", t("charts.runs.score")), [t]);
  const active = points.find((p) => p.active)?.label;
  const xTick = useMemo(() => (s: string) => (s === active ? t("charts.runs.activeTick", { run: s }) : s), [active, t]);
  if (points.length < MIN_RUNS) return null;

  const columns: ChartColumn<ScorePoint>[] = [
    { key: "label", label: t("charts.runs.run"), format: (v, r) => (r.active ? t("charts.runs.activeTick", { run: String(v) }) : String(v)) },
    { key: "finished", label: t("charts.runs.finished"), kind: "date" },
    { key: "soft", label: t("charts.runs.score"), kind: "number" },
  ];

  return (
    <Card
      className="mb-4 px-4 py-4"
      data-testid="runs-score-history"
      onPointerDownCapture={(e) => {
        pointer.current = e.pointerType;
      }}
      onKeyDownCapture={() => {
        pointer.current = null;
      }}
    >
      <ChartCard<ScorePoint>
        id="runs-soft-score"
        title={t("charts.runs.title")}
        hint={t("charts.runs.hint")}
        summary={scoreSummary(points, t, f)}
        state="ready"
        columns={columns}
        rows={points}
        series={1}
        minPoints={MIN_RUNS}
        userId={userId}
        range={{ from: points[0]!.finished.slice(0, 10), to: points.at(-1)!.finished.slice(0, 10) }}
        onSelect={(i) => {
          const p = points[i];
          if (!p) return;
          if (pointer.current === "touch" && armed.current !== i) {
            armed.current = i;
            return;
          }
          armed.current = null;
          router.push(`/runs/${p.id}`);
        }}
        selectHint={t(coarse ? "charts.runs.openTouch" : "charts.runs.open")}
      >
        {(c) => <LazyLineChart {...c} xTickFormatter={xTick} data={points} config={config} xKey="label" series={["soft"]} dots />}
      </ChartCard>
    </Card>
  );
}
