"use client";

import { FileUp, MessageSquare, PlayCircle, Table2 } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { ScoreRing } from "@/components/runs/score-ring";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard, useMeetings } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, periodRangeLabel } from "@/lib/time";
import { StatTile } from "./stat-tile";
import { UtilisationHeatmap } from "./utilisation-heatmap";

function relative(iso: string, locale: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const mins = Math.round(diff / 60_000);
  if (Math.abs(mins) < 60) return rtf.format(-mins, "minute");
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 48) return rtf.format(-hours, "hour");
  return rtf.format(-Math.round(hours / 24), "day");
}

export function DashboardView() {
  const { t, locale, n } = useI18n();
  const { term } = useActiveTerm();
  const dash = useDashboard(term?.id);
  const pending = useMeetings({ status: "NEEDS_REVIEW", page_size: 6 });
  const d = dash.data;
  const lastRun = d?.last_runs[0];

  return (
    <div data-testid="dashboard">
      <PageHeader
        title={t("dashboard.title")}
        subtitle={d ? t("dashboard.subtitle", { term: d.term.name, week: d.current_week, weeks: d.term.week_count }) : undefined}
        actions={
          <>
            <Button variant="outline" nativeButton={false} render={<Link href="/import" />}><FileUp /> {t("dashboard.import")}</Button>
            <Button nativeButton={false} render={<Link href="/generate" />}><PlayCircle /> {t("dashboard.generate")}</Button>
          </>
        }
      />
      {lastRun && lastRun.status === "INFEASIBLE" ? (
        <Link href={`/runs/${lastRun.id}`} className="mb-4 flex items-center justify-between rounded-lg border border-status-warning-border bg-status-warning px-4 py-2 text-sm text-status-warning-fg">
          <span>Run #{lastRun.id} · {t("runs.status.INFEASIBLE")} ({lastRun.hard_score}/100)</span>
          <span className="font-medium">{t("runs.report")} →</span>
        </Link>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {d ? (
          <>
            <StatTile label={t("dashboard.utilisation")} value={d.utilisation * 100} format={(v) => `${Math.round(v)}%`} delta={{ value: 3, goodDirection: "up", label: "+3 pt" }} href="/timetable?zoom=week" footnote={`${t("common.week")} ${d.current_week}`} />
            <StatTile label={t("dashboard.needsReview")} value={d.requests_needs_review} delta={{ value: -2, goodDirection: "down", label: "−2" }} href="/requests?status=NEEDS_REVIEW" footnote={`${n(d.requests_total)} ${t("requests.title").toLocaleLowerCase(locale)}`} tone={d.requests_needs_review > 0 ? "warning" : "default"} />
            <StatTile label={t("dashboard.sections")} value={d.sections_total} href="/requests" footnote={`${d.rooms_bookable} ${t("dashboard.rooms").toLocaleLowerCase(locale)}`} />
            <StatTile
              label={t("dashboard.lastRuns")}
              value={lastRun ? `${lastRun.hard_score ?? "—"}/100` : "—"}
              href={lastRun ? `/runs/${lastRun.id}` : "/generate"}
              footnote={lastRun ? `#${lastRun.id} · soft ${lastRun.soft_score ?? "—"} · ${relative(lastRun.created_at, locale)}` : t("dashboard.empty")}
              tone={lastRun?.status === "INFEASIBLE" ? "infeasible" : lastRun?.hard_score === 100 ? "feasible" : "default"}
            />
          </>
        ) : (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[140px] rounded-xl" />)
        )}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3 lg:gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("dashboard.byBuilding")}</CardTitle>
          </CardHeader>
          <CardContent>{d ? <UtilisationHeatmap data={d} week={d.current_week} /> : <Skeleton className="h-40" />}</CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>{t("dashboard.pending")}</CardTitle>
            <Link href="/requests?status=NEEDS_REVIEW" className="text-xs text-primary hover:underline">{t("dashboard.viewAll")}</Link>
          </CardHeader>
          <CardContent className="space-y-1">
            {pending.data?.items.length === 0 ? <p className="text-sm text-muted-foreground">{t("common.noData")}</p> : null}
            {pending.data?.items.map((m) => (
              <Link key={m.id} href={`/requests?kind=meetings&id=${m.id}`} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                <span className="min-w-0">
                  <span className="font-mono font-medium">{m.course_code}</span>
                  <span className="block truncate text-xs text-muted-foreground">{m.program_name}{m.day && m.start_period && m.end_period ? ` · ${dayName(m.day, locale, "short")} ${periodRangeLabel(m.start_period, m.end_period)}` : ""}</span>
                </span>
                <StatusBadge kind="warning" label={t("requests.status.NEEDS_REVIEW")} />
              </Link>
            )) ?? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-9" />)}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>{t("dashboard.lastRuns")}</CardTitle>
            <Link href="/runs" className="text-xs text-primary hover:underline">{t("dashboard.viewAll")}</Link>
          </CardHeader>
          <CardContent>
            <div className="mb-3 flex gap-1" aria-hidden>
              {d?.last_runs.slice().reverse().map((r) => (
                <span key={r.id} title={`#${r.id}`} className={`h-1.5 flex-1 rounded-full ${r.status === "INFEASIBLE" ? "bg-status-infeasible-border" : r.status === "FEASIBLE" || r.status === "OPTIMAL" ? "bg-status-feasible-border" : "bg-border-strong"}`} />
              ))}
            </div>
            <ul className="divide-y">
              {d?.last_runs.map((r) => (
                <li key={r.id}>
                  <Link href={`/runs/${r.id}`} className="flex items-center gap-3 py-2 text-sm hover:bg-accent/50">
                    <span className="font-mono">#{r.id}</span>
                    <span className="min-w-0 flex-1 truncate">{r.term_code} · {t(`generate.${r.horizon === "WEEK" ? "week" : r.horizon === "MONTH" ? "month" : "wholeTerm"}`)}{r.horizon_params.weeks.length ? ` W${r.horizon_params.weeks[0]}${r.horizon_params.weeks.length > 1 ? `–${r.horizon_params.weeks.at(-1)}` : ""}` : ""}</span>
                    <ScoreRing size="sm" value={r.hard_score} label={t("runs.hard")} />
                    <span className="hidden w-12 text-right tabular-nums text-muted-foreground sm:inline">{r.soft_score ?? "—"}</span>
                    <span className="hidden w-24 text-right text-xs text-muted-foreground md:inline">{relative(r.created_at, locale)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("common.actions")}</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-2">
            <Button variant="outline" className="h-12 justify-start" nativeButton={false} render={<Link href="/import" />}><FileUp /> {t("nav.import")}</Button>
            <Button variant="outline" className="h-12 justify-start" nativeButton={false} render={<Link href="/generate" />}><PlayCircle /> {t("nav.generate")}</Button>
            <Button variant="outline" className="h-12 justify-start" nativeButton={false} render={<Link href="/timetable" />}><Table2 /> {t("nav.timetable")}</Button>
            <Button variant="outline" className="h-12 justify-start" nativeButton={false} render={<Link href={lastRun ? `/runs/${lastRun.id}?tab=chat` : "/runs"} />}><MessageSquare /> {t("chat.title")}</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
