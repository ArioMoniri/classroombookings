"use client";

import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, FileUp, PlayCircle, XOctagon } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { trPercent } from "@/components/common/tr-suffix";
import { isImportBoard, partialCounts, runStatusBadge } from "@/components/runs/runs-list";
import { useActiveTerm, useTermKindLabel } from "@/components/shell/term-switcher";
import { useRememberedTermWeek, weekOfTerm } from "@/components/shell/workspace";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { GlassPanel } from "@/components/ui/glass-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useMeetings, useRuns, useWeeks } from "@/lib/api/hooks";
import type { DashboardSummary, ScheduleRun } from "@/lib/api/schemas";
import { useDashboardWeek } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, formatDate, periodRangeLabel } from "@/lib/time";
import { BuildingBars, PeriodArea } from "./dashboard-charts";
import { KpiNumber } from "./kpi-number";
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

const DONE = new Set<ScheduleRun["status"]>(["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "INFEASIBLE", "TIMEOUT"]);

/** The plan the planner works on: the newest finished solver run of the term (imports are boards, not plans). */
function latestPlan(runs: ScheduleRun[] | undefined): ScheduleRun | undefined {
  return runs?.find((r) => DONE.has(r.status) && !isImportBoard(r) && r.kind === "COURSE") ?? runs?.find((r) => DONE.has(r.status) && !isImportBoard(r));
}

function HeroStatus({ plan }: { plan: ScheduleRun | undefined }) {
  const { t, n } = useI18n();
  if (!plan) {
    return (
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 type-title-3 text-label-2">
        {t("glass.dashboard.noPlan")}
        <Link href="/generate" className="text-[14px] font-medium text-tint-text hover:underline">
          {t("glass.dashboard.makePlan")}
        </Link>
      </p>
    );
  }
  const partial = partialCounts(plan);
  const unplaced = partial ? partial.total - partial.placed : 0;
  const complete = !partial && (plan.status === "FEASIBLE" || plan.status === "OPTIMAL");
  const Icon = complete ? CheckCircle2 : partial ? AlertTriangle : XOctagon;
  const tone = complete ? "text-status-feasible-fg" : partial ? "text-status-warning-fg" : "text-status-infeasible-fg";
  const text = complete ? t("glass.dashboard.allPlaced", { id: plan.id }) : partial ? t("glass.dashboard.needRoom", { n: n(unplaced), id: plan.id }) : t("glass.dashboard.noTimetable", { id: plan.id });
  return (
    <p className="flex items-start gap-2 type-title-3">
      <Icon className={`mt-0.5 size-5 shrink-0 stroke-[2] ${tone}`} aria-hidden />
      <span className="min-w-0 text-label-1">
        {text}{" "}
        <Link href={`/runs/${plan.id}`} className="text-[14px] font-medium whitespace-nowrap text-tint-text hover:underline">
          {partial || !complete ? t("glass.dashboard.openReport") : t("glass.dashboard.openRun")}
        </Link>
      </span>
    </p>
  );
}

function QuietNumbers({ d }: { d: DashboardSummary }) {
  const { t, locale, n } = useI18n();
  const fmt = (v: number) => new Intl.NumberFormat(locale).format(v);
  const items = [
    { label: t("glass.dashboard.toReview"), value: d.requests_needs_review, href: "/requests?status=NEEDS_REVIEW", hint: t("glass.dashboard.ofRequests", { n: n(d.requests_total) }) },
    { label: t("dashboard.sections"), value: d.sections_total, href: "/requests" },
    { label: t("glass.dashboard.bookable"), value: d.rooms_bookable, href: "/rooms", hint: t("glass.dashboard.ofRooms", { n: n(d.rooms_total) }) },
    { label: t("glass.dashboard.conflicts"), value: d.conflicts, href: "/timetable" },
  ];
  return (
    <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 pt-5 hairline-t sm:grid-cols-4">
      {items.map((i) => (
        <div key={i.label} className="min-w-0">
          <dt className="text-[12px] text-label-3">{i.label}</dt>
          <dd>
            <Link href={i.href} className="rounded-md text-[22px] leading-7 font-semibold tracking-[-0.017em] text-label-1 outline-none hover:text-tint-text focus-visible:outline-2 focus-visible:outline-(--focus)">
              <KpiNumber value={i.value} format={fmt} />
            </Link>
            {i.hint ? <span className="block text-[12px] text-label-3">{i.hint}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function DashboardView() {
  const { t, locale, n } = useI18n();
  const { term, isLoading: termsLoading } = useActiveTerm();
  const kindLabel = useTermKindLabel();
  const weeks = useWeeks(term?.id);
  const [remembered, rememberWeek] = useRememberedTermWeek(term?.id);
  const lastWeek = term?.week_count ?? 1;
  const week = Math.min(lastWeek, Math.max(1, remembered ?? (term ? (weekOfTerm(term) ?? 1) : 1)));
  const dash = useDashboardWeek(term?.id, term ? week : undefined);
  const runs = useRuns(term ? { term_id: term.id } : undefined);
  const pending = useMeetings(term ? { status: "NEEDS_REVIEW", term_id: term.id, page_size: 6 } : { status: "NEEDS_REVIEW", page_size: 6 });
  const d = dash.data;
  const plan = latestPlan(runs.data);
  const weekRow = weeks.data?.find((w) => w.index === week);
  const weekDates = weekRow ? `${formatDate(weekRow.start_date, locale, { day: "numeric", month: "short" })}` : "";
  const pct = d ? Math.round(d.utilisation * 100) : 0;
  // Turkish writes the sign first (%44), English after (44%): read it from Intl, not from a guess
  const pctParts = useMemo(() => (trPercent(0.5, locale).startsWith("%") ? { prefix: "%", suffix: undefined } : { prefix: undefined, suffix: "%" }), [locale]);
  const recent = (runs.data ?? []).slice(0, 6);

  if (!termsLoading && !term) {
    return (
      <div data-testid="dashboard">
        <PageHeader title={t("dashboard.title")} />
        <EmptyState title={t("glass.dashboard.emptyTitle")} description={t("glass.dashboard.emptyBody")} animation="file-to-rules" animationLabel={t("glass.dashboard.emptyTitle")} actions={<Button nativeButton={false} render={<Link href="/import" />}>{t("dashboard.import")}</Button>} />
      </div>
    );
  }

  return (
    <div data-testid="dashboard">
      <PageHeader
        title={t("dashboard.title")}
        subtitle={term ? `${term.name} · ${kindLabel(term.kind)}` : undefined}
        actions={
          <>
            <Button variant="outline" nativeButton={false} render={<Link href="/import" />}>
              <FileUp /> {t("dashboard.import")}
            </Button>
            <Button nativeButton={false} render={<Link href="/generate" />}>
              <PlayCircle /> {t("dashboard.generate")}
            </Button>
          </>
        }
      />

      {/* One hero insight (A2): this week's room use and what still needs a room. */}
      <GlassPanel material="regular" radius="2xl" className="p-5 sm:p-6" render={<section aria-labelledby="hero-title" data-testid="dashboard-hero" />}>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,440px)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[13px] text-label-2">
                {t("glass.dashboard.thisWeek", { week })}
                {weekDates ? <span className="text-label-3"> · {t("glass.dashboard.weekFrom", { date: weekDates })}</span> : null}
              </p>
              <div className="ml-auto flex items-center gap-0.5 sm:ml-0" role="group" aria-label={t("glass.dashboard.weekPicker")}>
                <Button variant="ghost" size="icon-sm" aria-label={t("glass.dashboard.prevWeek")} disabled={week <= 1} onClick={() => rememberWeek(week - 1)}>
                  <ChevronLeft />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label={t("glass.dashboard.nextWeek")} disabled={week >= lastWeek} onClick={() => rememberWeek(week + 1)}>
                  <ChevronRight />
                </Button>
              </div>
            </div>
            <h2 id="hero-title" className="mt-2 type-title-1 text-label-1 sm:type-large-title">
              {d ? (
                <>
                  {t("glass.dashboard.roomUse")}{" "}
                  <KpiNumber value={pct} prefix={pctParts.prefix} suffix={pctParts.suffix} className="align-baseline" />
                </>
              ) : (
                <Skeleton className="h-10 w-72" />
              )}
            </h2>
            <div className="mt-2">{runs.data ? <HeroStatus plan={plan} /> : <Skeleton className="h-6 w-80" />}</div>
            {d ? <QuietNumbers d={d} /> : <Skeleton className="mt-6 h-16" />}
          </div>
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-label-1">{t("glass.dashboard.byPeriod")}</p>
            <p className="text-[12px] text-label-3">{t("glass.dashboard.byPeriodHint")}</p>
            {d ? <PeriodArea data={d} className="mt-2 h-[180px]" /> : <Skeleton className="mt-2 h-[180px]" />}
          </div>
        </div>
      </GlassPanel>

      <div className="mt-6 grid gap-4 lg:grid-cols-3 lg:gap-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("dashboard.byBuilding")}</CardTitle>
            <CardDescription>{t("glass.dashboard.heatHint", { week })}</CardDescription>
          </CardHeader>
          <CardContent>{d ? <UtilisationHeatmap data={d} week={week} /> : <Skeleton className="h-40" />}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("glass.dashboard.buildings")}</CardTitle>
            <CardDescription>{t("glass.dashboard.buildingsHint")}</CardDescription>
          </CardHeader>
          <CardContent>{d ? <BuildingBars data={d} className="h-[200px]" /> : <Skeleton className="h-[200px]" />}</CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("dashboard.lastRuns")}</CardTitle>
            <CardAction>
              <Link href="/runs" className="text-[13px] font-medium text-tint-text hover:underline">
                {t("dashboard.viewAll")}
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            {runs.data && recent.length === 0 ? <p className="text-[13px] text-label-2">{t("glass.shell.noRuns")}</p> : null}
            <ul>
              {recent.map((r) => (
                <li key={r.id} className="[&:not(:last-child)]:hairline-b">
                  <Link href={`/runs/${r.id}`} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 outline-none hover:bg-fill-3 focus-visible:bg-fill-3">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-label-1">{isImportBoard(r) ? t("glass.dashboard.importedBoard", { id: r.id }) : t("glass.shell.runTitle", { id: r.id, term: r.term_code })}</span>
                      <span className="block truncate text-[12px] text-label-3">
                        {t(r.kind === "COURSE" ? "glass.dashboard.kindCourse" : "glass.dashboard.kindExam")} · {r.horizon_params.weeks.length ? t("glass.dashboard.weeksN", { list: r.horizon_params.weeks.join(", ") }) : t("glass.dashboard.wholeTerm")} · {relative(r.created_at, locale)}
                      </span>
                    </span>
                    <StatusBadge variant="plain" {...runStatusBadge(r, t)} />
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              {t("glass.dashboard.toReview")} <span className="font-normal text-label-3 tabular-nums">{pending.data ? n(pending.data.total) : ""}</span>
            </CardTitle>
            <CardAction>
              <Link href="/requests?status=NEEDS_REVIEW" className="text-[13px] font-medium text-tint-text hover:underline">
                {t("dashboard.viewAll")}
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            {pending.data?.items.length === 0 ? <p className="text-[13px] text-label-2">{t("glass.dashboard.nothingToReview")}</p> : null}
            <ul>
              {pending.data?.items.map((m) => (
                <li key={m.id} className="[&:not(:last-child)]:hairline-b">
                  <Link href={`/requests?kind=meetings&id=${m.id}`} className="-mx-2 flex min-w-0 flex-col rounded-lg px-2 py-2 outline-none hover:bg-fill-3 focus-visible:bg-fill-3">
                    <span className="text-[13px] font-medium text-label-1">
                      {m.course_code}
                      {m.day && m.start_period && m.end_period ? <span className="font-normal text-label-2"> · {dayName(m.day, locale, "short")} {periodRangeLabel(m.start_period, m.end_period)}</span> : null}
                    </span>
                    <span className="truncate text-[12px] text-label-3">{m.program_name}</span>
                  </Link>
                </li>
              )) ?? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="my-1 h-9" />)}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
