"use client";
/**
 * Denetim kaydı › "Günlük olaylar" (CH-10, docs/design/v3/charts.md §4 row 15): events per day over the last 30 days
 * above the list (EvilCharts ECharts bar, lazy). A tap or click on a column, or ←/→ then Enter, filters the list to
 * that day (the date fields of the filter form show it, so the filter stays keyboard reachable and undoable with
 * "Sıfırla"). Phones keep the first event high on the screen: the chart sits behind one 44 px "Günlük olayları
 * göster" button. Data: `GET /audit/stats/daily` (lib/api/stats.ts); while that route is missing the card says so
 * ("veri yok"), never invented numbers. Original work.
 */
import { BarChart3 } from "lucide-react";
import { useMemo, useState } from "react";
import { ChartCard, type ChartState } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { useChartFormat } from "@/components/charts/chart-format";
import { LazyBarChart } from "@/components/charts/chart-lazy";
import { singleConfig } from "@/components/charts/chart-tokens";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { serverMessage } from "@/lib/api/error-text";
import { isMissingRoute, useDailyAuditStats } from "@/lib/api/stats";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { auditDailySummary, dailyRows, type DayRow } from "./audit-daily-model";

const DAYS = 30;

/** `open` given: the phone toggle lives with the page's title actions (audit-view.tsx), so the first event still starts
 *  high on a phone (T-R1-32); otherwise the chart brings its own toggle. */
export function AuditDaily({ onDay, userId, open: openProp }: { onDay: (day: string) => void; userId?: number | null; open?: boolean }) {
  const { t, locale } = useI18n();
  const f = useChartFormat();
  const q = useDailyAuditStats(DAYS);
  const [openSelf, setOpen] = useState(false);
  const open = openProp ?? openSelf;
  const [live, setLive] = useState("");
  const missing = q.isError && isMissingRoute(q.error);
  const rows = useMemo(() => (q.data ? dailyRows(q.data) : []), [q.data]);
  const config = useMemo(() => singleConfig("events", t("charts.audit.events")), [t]);
  const total = rows.reduce((s, r) => s + r.events, 0);
  const state: ChartState = q.isLoading ? "loading" : missing ? "empty" : q.isError ? "error" : total ? "ready" : "empty";
  const today = q.data?.to;
  const columns: ChartColumn<DayRow>[] = [
    { key: "day", label: t("charts.audit.day"), kind: "date" },
    { key: "events", label: t("charts.audit.events"), kind: "number" },
  ];

  return (
    <div className={cn("flex flex-col gap-2", openProp !== undefined && !open && "max-sm:hidden")} data-testid="audit-daily">
      {openProp === undefined ? (
        <Button variant="outline" className="self-start sm:hidden pointer-coarse:h-11" aria-expanded={open} aria-controls="audit-daily-card" onClick={() => setOpen((v) => !v)} data-testid="audit-daily-toggle">
          <BarChart3 aria-hidden />
          {open ? t("charts.audit.hide") : t("charts.audit.show")}
        </Button>
      ) : null}
      <Card id="audit-daily-card" className={cn("px-4 py-4", !open && "max-sm:hidden")}>
        <ChartCard<DayRow>
          id="audit-daily"
          title={t("charts.audit.title")}
          hint={t("charts.audit.hint")}
          summary={auditDailySummary(rows, t, f)}
          state={state}
          empty={{ reason: missing ? t("charts.audit.missing") : t("charts.audit.empty") }}
          error={q.isError && !missing ? (serverMessage(q.error, locale) ?? undefined) : undefined}
          onRetry={() => void q.refetch()}
          columns={columns}
          rows={rows}
          series={1}
          partial={!!today && rows.at(-1)?.day === today}
          range={rows.length ? { from: rows[0]!.day, to: rows.at(-1)!.day } : undefined}
          unit={t("charts.audit.events").toLocaleLowerCase(locale)}
          userId={userId}
          onSelect={(i) => {
            const r = rows[i];
            if (!r) return;
            onDay(r.day);
            setLive(t("charts.audit.filtered", { day: f.dayLong(r.day) }));
          }}
          selectHint={t("charts.audit.pick")}
        >
          {(c) => <LazyBarChart {...c} data={rows} config={config} xKey="day" series={["events"]} />}
        </ChartCard>
      </Card>
      <div aria-live="polite" className="sr-only" data-testid="audit-daily-live">
        {live}
      </div>
    </div>
  );
}
