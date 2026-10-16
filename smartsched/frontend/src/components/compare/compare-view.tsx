"use client";
/**
 * Senaryo karşılaştırma (`/runs/compare?a=&b=[&week=][&tab=]`): two stored runs of one term and kind side by side
 * (backend `GET /analytics/compare`; services/scenario_compare.py). A is the baseline ("before"), B the scenario
 * ("after"); every delta is B − A. Sections: the headline, the metrics with a better / worse word and glyph
 * (never colour alone), class changes (moved / only in A / only in B, change type, search), instructor load,
 * room utilisation and the rule-by-rule soft penalties. Each section downloads as CSV (`format=csv&part=`).
 */
import { ArrowDownRight, ArrowRight, ArrowUpRight, CheckCircle2, Download, Lock, Minus, XOctagon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";
import { FadePanel } from "@/components/analytics/fade-panel";
import { signed } from "@/components/analytics/heat-scale";
import { PageHeader } from "@/components/common/page-header";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, StatusDot, type DataColumn } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import {
  csvHref,
  errorText,
  isExamRow,
  pairOf,
  useCompare,
  useRunOptions,
  type ChangeKind,
  type CompareData,
  type ComparePart,
  type CourseInstructorRow,
  type ExamInstructorRow,
  type Metric,
  type Place,
  type RoomDelta,
  type RuleRow,
  type RunBrief,
} from "@/lib/api/analytics";
import { useMe, useTerms } from "@/lib/api/hooks";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { CHANGE_KINDS, CLASS_FILTERS, classRows, metricValue, verdict, type ClassFilter, type ClassRow, type Verdict } from "./compare-model";
import { RunPairPicker } from "./run-pair-picker";
import { useRunText } from "./run-text";

type Tab = "classes" | "instructors" | "rooms" | "rules";
const TABS: readonly Tab[] = ["classes", "instructors", "rooms", "rules"];
const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

export function CompareView() {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const a = num(params.get("a"));
  const b = num(params.get("b"));
  const week = num(params.get("week"));
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "classes";
  const runs = useRunOptions();
  const q = useCompare(a, b, week);
  const terms = useTerms();
  const data = q.data;
  const term = terms.data?.find((x) => x.id === data?.term_id);

  const setParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="compare-page">
      <PageHeader title={t("compare.title")} subtitle={data ? pairOf(data.definitions.delta, lang) : t("compare.subtitle")} />
      <section aria-label={t("compare.picker.title")} className="rounded-xl bg-card p-4 edge-hairline">
        <RunPairPicker runs={runs.data} a={a} b={b} loading={runs.isLoading} onApply={(na, nb) => setParams({ a: String(na), b: String(nb), week: null })} />
        {runs.data && runs.data.length < 2 ? <p className="mt-2 type-footnote text-label-2">{t("compare.picker.needTwo")}</p> : null}
      </section>

      {a === null || b === null ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5" data-testid="compare-empty">
          <p className="type-headline">{t("compare.empty.title")}</p>
          <p className="mt-1 type-callout text-label-2">{t("compare.empty.body")}</p>
        </div>
      ) : a === b ? (
        <Alert tone="warning">{t("compare.sameRun")}</Alert>
      ) : q.isError ? (
        <Alert tone="error" data-testid="compare-error" action={<Button size="sm" variant="ghost" onClick={() => void q.refetch()}>{t("common.retry")}</Button>}>
          {errorText(q.error, lang)}
        </Alert>
      ) : !data ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label={t("compare.loading")}>
          <Skeleton className="h-16 w-full" />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-72 w-full" />
        </div>
      ) : (
        <FadePanel panelKey={`${data.a.id}-${data.b.id}-${week ?? "all"}`} className="flex min-w-0 flex-col gap-4">
          <Summary data={data} />
          <div className="flex flex-wrap items-end gap-3">
            {term && term.week_count > 1 && (data.a.horizon === "TERM" || data.b.horizon === "TERM" || week !== null) ? (
              <label className="flex flex-col gap-1">
                <span className="type-footnote font-medium text-label-2">{t("compare.week")}</span>
                <NativeSelect size="sm" className="w-44" value={week ?? ""} onChange={(e) => setParams({ week: e.target.value || null })} data-testid="compare-week">
                  <option value="">{t("compare.allWeeks")}</option>
                  {Array.from({ length: term.week_count }, (_, i) => i + 1).map((w) => (
                    <option key={w} value={w}>{t("compare.weekN", { n: w })}</option>
                  ))}
                </NativeSelect>
              </label>
            ) : null}
            <CsvLink a={data.a.id} b={data.b.id} week={week} part="metrics" label={t("compare.csv.metrics")} />
          </div>
          <Metrics metrics={data.metrics} />
          <SegmentedControl
            aria-label={t("compare.sections")}
            options={TABS.map((x) => ({ value: x, label: t(`compare.tab.${x}`), controls: `compare-panel-${x}`, testId: `compare-tab-${x}` }))}
            value={tab}
            onValueChange={(v) => setParams({ tab: v === "classes" ? null : v })}
            className="self-start"
          />
          <FadePanel panelKey={tab} data-testid={`compare-panel-${tab}`}>
            <div id={`compare-panel-${tab}`} role="tabpanel" aria-label={t(`compare.tab.${tab}`)}>
              {tab === "classes" ? <ClassesSection data={data} week={week} /> : tab === "instructors" ? <InstructorsSection data={data} week={week} /> : tab === "rooms" ? <RoomsSection data={data} week={week} /> : <RulesSection data={data} week={week} />}
            </div>
          </FadePanel>
        </FadePanel>
      )}
    </div>
  );
}

function CsvLink({ a, b, week, part, label }: { a: number; b: number; week: number | null; part: ComparePart; label: string }) {
  return (
    <Button variant="outline" size="sm" nativeButton={false} render={<a href={csvHref.compare(a, b, part, week)} download />} data-testid={`compare-csv-${part}`}>
      <Download aria-hidden />
      {label}
    </Button>
  );
}

/* ------------------------------------------------------------------ summary */

function Summary({ data }: { data: CompareData }) {
  const { locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  return (
    <section aria-labelledby="compare-headline" className="flex flex-col gap-3">
      <p id="compare-headline" className="type-title-3 text-label-1" data-testid="compare-headline">
        {pairOf(data.headline, lang)}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <RunCard side="a" run={data.a} />
        <RunCard side="b" run={data.b} />
      </div>
    </section>
  );
}

function RunCard({ side, run }: { side: "a" | "b"; run: RunBrief }) {
  const { t, n } = useI18n();
  const runText = useRunText();
  const tone = run.status === "OPTIMAL" || run.status === "FEASIBLE" ? "feasible" : run.status === "FEASIBLE_PARTIAL" ? "warning" : "infeasible";
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-xl bg-card p-3 edge-hairline" data-testid={`compare-run-${side}`}>
      <span className="type-caption font-semibold tracking-wide text-label-2 uppercase">{t(side === "a" ? "compare.sideA" : "compare.sideB")}</span>
      <Link href={`/runs/${run.id}`} className="truncate type-headline text-label-1 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)">
        {runText({ ...run, label: run.label })}
      </Link>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 type-footnote text-label-2">
        <StatusDot tone={tone}>{t(`runs.status.${run.status}` as MessageKey)}</StatusDot>
        <span className="tnum">{t("compare.hardSoft", { hard: run.hard_score === null ? "—" : n(run.hard_score), soft: run.soft_score === null ? "—" : n(run.soft_score) })}</span>
        {run.horizon_params.weeks?.length ? <span>{t("compare.weeksList", { list: run.horizon_params.weeks.join(", ") })}</span> : <span>{t("compare.wholeTerm")}</span>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ metrics */

export function VerdictTag({ v, delta, locale }: { v: Verdict; delta: number | null; locale: string }) {
  const { t } = useI18n();
  const Icon = v === "better" ? CheckCircle2 : v === "worse" ? XOctagon : Minus;
  const Dir = delta === null || delta === 0 ? null : delta > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 type-footnote font-medium",
        v === "better" ? "text-status-feasible-fg" : v === "worse" ? "text-status-infeasible-fg" : "text-label-2",
      )}
      data-verdict={v}
    >
      {v === "better" || v === "worse" ? <Icon aria-hidden className="size-3.5" /> : null}
      {Dir ? <Dir aria-hidden className="size-3.5" /> : null}
      {delta !== null ? <span className="tnum">{signed(delta, locale)}</span> : null}
      <span>{t(`compare.verdict.${v}`)}</span>
    </span>
  );
}

function Metrics({ metrics }: { metrics: Metric[] }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  return (
    <section aria-label={t("compare.metrics")}>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {metrics.map((m) => {
          const v = verdict(m);
          return (
            <li key={m.key} className="flex min-w-0 flex-col gap-1 rounded-xl bg-card p-3 edge-hairline" data-testid="compare-metric" data-key={m.key} data-verdict={v}>
              <span className="truncate type-footnote text-label-2" title={pairOf(m.label, lang)}>{pairOf(m.label, lang)}</span>
              <span className="flex items-baseline gap-1.5">
                <span className="type-callout text-label-2 tnum" aria-label={`A ${metricValue(m.key, m.a, locale)}`}>{metricValue(m.key, m.a, locale)}</span>
                <ArrowRight aria-hidden className="size-3.5 self-center text-label-3" />
                <span className="type-title-3 text-label-1 tnum" aria-label={`B ${metricValue(m.key, m.b, locale)}`}>{metricValue(m.key, m.b, locale)}</span>
              </span>
              <VerdictTag v={v} delta={m.delta} locale={locale} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------ classes */

function PlaceCell({ p, emphasise }: { p: Place | null; emphasise?: "time" | "room" | "both" | null }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  if (!p) return <span className="type-footnote text-label-3">{t("compare.notPlaced")}</span>;
  return (
    <span className="flex min-w-0 flex-col leading-tight">
      <span className={cn("truncate", (emphasise === "time" || emphasise === "both") && "font-semibold")}>{pairOf(p.when, lang)}</span>
      <span className={cn("truncate type-footnote text-label-2", (emphasise === "room" || emphasise === "both") && "font-semibold text-label-1")}>
        {p.rooms.join(", ") || "—"}
        {p.locked ? <Lock aria-label={t("compare.locked")} className="ml-1 inline size-3 align-[-1px]" /> : null}
      </span>
    </span>
  );
}

const emphasisOf = (c: ChangeKind | undefined) => (c === "time" ? "time" : c === "room" ? "room" : c === "time_room" ? "both" : null);

function ClassesSection({ data, week }: { data: CompareData; week: number | null }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const me = useMe();
  const [filter, setFilter] = useState<ClassFilter>(data.classes.counts.moved ? "moved" : data.classes.counts.only_in_a ? "only_in_a" : data.classes.counts.only_in_b ? "only_in_b" : "moved");
  const [change, setChange] = useState<ChangeKind | "all">("all");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => classRows(data, filter, change, query), [data, filter, change, query]);
  const c = data.classes.counts;
  const noun = data.kind === "EXAM" ? "exam" : "class";
  const columns = useMemo<DataColumn<ClassRow>[]>(
    () => [
      { id: "label", header: t(`compare.col.${noun}`), pin: "left", priority: 1, grow: 2, minSize: 120, maxSize: 420, text: (r) => r.label, sortValue: (r) => r.label, cell: (r) => <span className="truncate font-medium" title={r.label}>{r.label}</span> },
      {
        id: "change",
        header: t("compare.col.change"),
        priority: 2,
        minSize: 110,
        text: (r) => (r.change_text ? pairOf(r.change_text, lang) : t(`compare.bucket.${r.bucket}`)),
        sortValue: (r) => r.change ?? r.bucket,
        cell: (r) => <Badge tone={r.bucket === "moved" ? "tint" : r.bucket === "only_in_a" ? "warning" : "feasible"}>{r.change_text ? pairOf(r.change_text, lang) : t(`compare.bucket.${r.bucket}`)}</Badge>,
        extra: 16,
      },
      { id: "a", header: t("compare.col.a"), priority: 2, grow: 1, minSize: 150, text: (r) => (r.a ? `${pairOf(r.a.when, lang)} ${r.a.rooms.join(", ")}` : t("compare.notPlaced")), sortValue: (r) => (r.a ? r.a.day * 100 + r.a.start_period : 9999), cell: (r) => <PlaceCell p={r.a} emphasise={emphasisOf(r.change)} /> },
      { id: "b", header: t("compare.col.b"), priority: 2, grow: 1, minSize: 150, text: (r) => (r.b ? `${pairOf(r.b.when, lang)} ${r.b.rooms.join(", ")}` : t("compare.notPlaced")), sortValue: (r) => (r.b ? r.b.day * 100 + r.b.start_period : 9999), cell: (r) => <PlaceCell p={r.b} emphasise={emphasisOf(r.change)} /> },
      ...(data.kind === "EXAM"
        ? [{ id: "enrol", header: t("compare.col.enrolment"), align: "end" as const, priority: 4 as const, text: (r: ClassRow) => String(r.enrolment ?? "—"), sortValue: (r: ClassRow) => r.enrolment ?? -1, cell: (r: ClassRow) => <span className="tnum">{r.enrolment ?? "—"}</span> }]
        : []),
    ],
    [t, lang, noun, data.kind],
  );
  return (
    <section className="flex flex-col gap-3" aria-label={t("compare.tab.classes")}>
      <p className="type-footnote text-label-2">
        {t("compare.classes.summary", { unchanged: n(c.unchanged), neither: n(c.unplaced_in_both), total: n(data.requests_in_scope) })} {pairOf(data.definitions.moved, lang)}
      </p>
      {data.classes.truncated ? <Alert tone="warning">{t("compare.truncated", { n: 2000 })}</Alert> : null}
      <DataTable
        tableId="compare-classes"
        userId={me.data?.id}
        label={t("compare.tab.classes")}
        columns={columns}
        rows={rows}
        getRowId={(r) => `${r.bucket}-${r.request_id}`}
        rowProps={(r) => ({ "data-testid": "compare-class-row", "data-bucket": r.bucket })}
        defaultSort={[{ id: "label", desc: false }]}
        maxHeight="min(70dvh, 40rem)"
        toolbar={
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <SegmentedControl
              size="sm"
              semantics="radiogroup"
              aria-label={t("compare.classes.filter")}
              options={CLASS_FILTERS.map((f) => ({ value: f, label: `${t(`compare.filter.${f}`)} ${n(c[f])}`, text: `${t(`compare.filter.${f}`)} ${n(c[f])}`, testId: `compare-filter-${f}` }))}
              value={filter}
              onValueChange={setFilter}
            />
            {filter === "moved" ? (
              <NativeSelect size="sm" className="w-48" aria-label={t("compare.classes.changeType")} value={change} onChange={(e) => setChange(e.target.value as ChangeKind | "all")} data-testid="compare-change">
                <option value="all">{t("compare.change.all")}</option>
                {CHANGE_KINDS.filter((k) => (c.by_change[k] ?? 0) > 0).map((k) => (
                  <option key={k} value={k}>{`${t(`compare.change.${k}`)} (${n(c.by_change[k] ?? 0)})`}</option>
                ))}
              </NativeSelect>
            ) : null}
            <Input fieldSize="sm" className="w-48" type="search" placeholder={t("compare.classes.search")} aria-label={t("compare.classes.search")} value={query} onChange={(e) => setQuery(e.target.value)} data-testid="compare-search" />
            <CsvLink a={data.a.id} b={data.b.id} week={week} part="classes" label={t("compare.csv.classes")} />
          </div>
        }
        empty={<p className="px-3 py-6 type-callout text-label-2">{query ? t("compare.classes.noMatch") : t(`compare.classes.none.${filter}`)}</p>}
      />
    </section>
  );
}

/* ------------------------------------------------------------------ instructors */

function DeltaNum({ v, lowerIsBetter = true }: { v: number; lowerIsBetter?: boolean }) {
  const { locale, t } = useI18n();
  if (v === 0) return <span className="tnum text-label-2">0</span>;
  const good = lowerIsBetter ? v < 0 : v > 0;
  return (
    <span className={cn("inline-flex items-center gap-0.5 tnum", good ? "text-status-feasible-fg" : "text-status-infeasible-fg")} title={t(good ? "compare.verdict.better" : "compare.verdict.worse")}>
      {v > 0 ? <ArrowUpRight aria-hidden className="size-3" /> : <ArrowDownRight aria-hidden className="size-3" />}
      {signed(v, locale)}
      <span className="sr-only">{t(good ? "compare.verdict.better" : "compare.verdict.worse")}</span>
    </span>
  );
}

function InstructorsSection({ data, week }: { data: CompareData; week: number | null }) {
  const { t, n } = useI18n();
  const me = useMe();
  const exam = data.kind === "EXAM";
  const agg = data.instructors;
  const courseCols = useMemo<DataColumn<CourseInstructorRow>[]>(
    () => [
      { id: "name", header: t("compare.col.instructor"), pin: "left", priority: 1, grow: 2, minSize: 140, text: (r) => r.name, sortValue: (r) => r.name, cell: (r) => <span className="truncate font-medium">{r.name}</span> },
      { id: "loadA", header: t("compare.col.loadA"), align: "end", priority: 2, text: (r) => String(r.a.periods_per_week), sortValue: (r) => r.a.periods_per_week, cell: (r) => <span className="tnum">{n(r.a.periods_per_week)}</span> },
      { id: "loadB", header: t("compare.col.loadB"), align: "end", priority: 2, text: (r) => String(r.b.periods_per_week), sortValue: (r) => r.b.periods_per_week, cell: (r) => <span className="tnum">{n(r.b.periods_per_week)}</span> },
      { id: "dLoad", header: t("compare.col.dLoad"), align: "end", priority: 3, text: (r) => String(r.delta.periods_per_week), extra: 14, sortValue: (r) => r.delta.periods_per_week, cell: (r) => <DeltaNum v={r.delta.periods_per_week} lowerIsBetter={false} /> },
      { id: "gapsA", header: t("compare.col.gapsA"), align: "end", priority: 3, text: (r) => String(r.a.gaps_per_week), sortValue: (r) => r.a.gaps_per_week, cell: (r) => <span className="tnum">{n(r.a.gaps_per_week)}</span> },
      { id: "gapsB", header: t("compare.col.gapsB"), align: "end", priority: 3, text: (r) => String(r.b.gaps_per_week), sortValue: (r) => r.b.gaps_per_week, cell: (r) => <span className="tnum">{n(r.b.gaps_per_week)}</span> },
      { id: "dGaps", header: t("compare.col.dGaps"), align: "end", priority: 2, text: (r) => String(r.delta.gaps_per_week), extra: 14, sortValue: (r) => r.delta.gaps_per_week, cell: (r) => <DeltaNum v={r.delta.gaps_per_week} /> },
      { id: "days", header: t("compare.col.days"), align: "end", priority: 4, text: (r) => `${r.a.days_per_week} → ${r.b.days_per_week}`, sortValue: (r) => r.delta.days_per_week, cell: (r) => <span className="tnum">{`${n(r.a.days_per_week)} → ${n(r.b.days_per_week)}`}</span> },
    ],
    [t, n],
  );
  const examCols = useMemo<DataColumn<ExamInstructorRow>[]>(
    () => [
      { id: "name", header: t("compare.col.instructor"), pin: "left", priority: 1, grow: 2, minSize: 140, text: (r) => r.name, sortValue: (r) => r.name, cell: (r) => <span className="truncate font-medium">{r.name}</span> },
      { id: "examsA", header: t("compare.col.examsA"), align: "end", priority: 2, text: (r) => String(r.a.exams), sortValue: (r) => r.a.exams, cell: (r) => <span className="tnum">{n(r.a.exams)}</span> },
      { id: "examsB", header: t("compare.col.examsB"), align: "end", priority: 2, text: (r) => String(r.b.exams), sortValue: (r) => r.b.exams, cell: (r) => <span className="tnum">{n(r.b.exams)}</span> },
      { id: "dayA", header: t("compare.col.maxDayA"), align: "end", priority: 3, text: (r) => String(r.a.max_per_day), sortValue: (r) => r.a.max_per_day, cell: (r) => <span className="tnum">{n(r.a.max_per_day)}</span> },
      { id: "dayB", header: t("compare.col.maxDayB"), align: "end", priority: 2, text: (r) => String(r.b.max_per_day), extra: 14, sortValue: (r) => r.b.max_per_day - r.a.max_per_day, cell: (r) => <span className="inline-flex items-center gap-1"><span className="tnum">{n(r.b.max_per_day)}</span><DeltaNum v={r.b.max_per_day - r.a.max_per_day} /></span> },
    ],
    [t, n],
  );
  const stat = (key: string): ReactNode => {
    const va = agg.a[key];
    const vb = agg.b[key];
    if (va === undefined && vb === undefined) return null;
    return (
      <li key={key} className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-card p-3 edge-hairline">
        <span className="truncate type-footnote text-label-2">{t(`compare.ins.${key}` as MessageKey)}</span>
        <span className="flex items-baseline gap-1.5 tnum">
          <span className="type-callout text-label-2">{va === undefined ? "—" : n(va)}</span>
          <ArrowRight aria-hidden className="size-3.5 self-center text-label-3" />
          <span className="type-title-3">{vb === undefined ? "—" : n(vb)}</span>
        </span>
      </li>
    );
  };
  const keys = exam ? ["instructors", "with_two_or_more_a_day"] : ["gaps_per_week_total", "instructors_with_gaps", "periods_per_week_max", "instructors"];
  return (
    <section className="flex flex-col gap-3" aria-label={t("compare.tab.instructors")}>
      <ul className="grid grid-cols-2 gap-2 md:grid-cols-4">{keys.map(stat)}</ul>
      <p className="type-footnote text-label-2">{t("compare.ins.changed", { n: n(agg.changed) })}</p>
      {exam ? (
        <DataTable
          tableId="compare-instructors-exam"
          userId={me.data?.id}
          label={t("compare.tab.instructors")}
          columns={examCols}
          rows={agg.rows.filter(isExamRow)}
          getRowId={(r) => r.key}
          defaultSort={[{ id: "dayB", desc: true }]}
          maxHeight="min(70dvh, 40rem)"
          toolbar={<CsvLink a={data.a.id} b={data.b.id} week={week} part="instructors" label={t("compare.csv.instructors")} />}
          empty={<p className="px-3 py-6 type-callout text-label-2">{t("compare.ins.none")}</p>}
        />
      ) : (
        <DataTable
          tableId="compare-instructors"
          userId={me.data?.id}
          label={t("compare.tab.instructors")}
          columns={courseCols}
          rows={agg.rows.filter((r): r is CourseInstructorRow => !isExamRow(r))}
          getRowId={(r) => String(r.instructor_id)}
          defaultSort={[{ id: "dGaps", desc: false }]}
          maxHeight="min(70dvh, 40rem)"
          rowProps={() => ({ "data-testid": "compare-instructor-row" })}
          toolbar={<CsvLink a={data.a.id} b={data.b.id} week={week} part="instructors" label={t("compare.csv.instructors")} />}
          empty={<p className="px-3 py-6 type-callout text-label-2">{t("compare.ins.none")}</p>}
        />
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ rooms */

function pctFmt(v: number, locale: string) {
  const f = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(v);
  return locale.startsWith("tr") ? `%${f}` : `${f}%`;
}

function RoomsSection({ data, week }: { data: CompareData; week: number | null }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const me = useMe();
  const r = data.rooms;
  const buildingCols = useMemo<DataColumn<CompareData["rooms"]["by_building"][number]>[]>(
    () => [
      { id: "building", header: t("compare.col.building"), pin: "left", priority: 1, grow: 1, text: (x) => x.building, sortValue: (x) => x.building, cell: (x) => <span className="font-medium">{x.building}</span> },
      { id: "a", header: t("compare.col.pctA"), align: "end", priority: 1, text: (x) => pctFmt(x.a.pct, locale), sortValue: (x) => x.a.pct, cell: (x) => <span className="tnum">{pctFmt(x.a.pct, locale)}</span> },
      { id: "b", header: t("compare.col.pctB"), align: "end", priority: 1, text: (x) => pctFmt(x.b.pct, locale), sortValue: (x) => x.b.pct, cell: (x) => <span className="tnum">{pctFmt(x.b.pct, locale)}</span> },
      { id: "d", header: t("compare.col.dPts"), align: "end", priority: 2, text: (x) => signed(x.b.pct - x.a.pct, locale), sortValue: (x) => x.b.pct - x.a.pct, cell: (x) => <span className="tnum">{signed(Math.round((x.b.pct - x.a.pct) * 10) / 10, locale)}</span> },
      { id: "occ", header: t("compare.col.occupied"), align: "end", priority: 3, text: (x) => `${x.a.occupied} → ${x.b.occupied}`, sortValue: (x) => x.b.occupied - x.a.occupied, cell: (x) => <span className="tnum">{`${n(x.a.occupied)} → ${n(x.b.occupied)}`}</span> },
      { id: "cap", header: t("compare.col.capacity"), align: "end", priority: 4, text: (x) => String(x.a.capacity), cell: (x) => <span className="tnum">{n(x.a.capacity)}</span> },
    ],
    [t, n, locale],
  );
  const roomCols = useMemo<DataColumn<RoomDelta>[]>(
    () => [
      {
        id: "code",
        header: t("compare.col.room"),
        pin: "left",
        priority: 1,
        minSize: 90,
        text: (x) => x.code,
        sortValue: (x) => x.code,
        cell: (x) => (
          <Link href={`/rooms/${x.room_id}`} className="font-medium hover:underline focus-visible:outline-2 focus-visible:outline-(--focus)" onClick={(e) => e.stopPropagation()}>
            {x.code}
          </Link>
        ),
      },
      { id: "building", header: t("compare.col.building"), priority: 4, text: (x) => x.building ?? "—", sortValue: (x) => x.building ?? "", cell: (x) => x.building ?? "—" },
      { id: "a", header: t("compare.col.pctA"), align: "end", priority: 2, text: (x) => `${pctFmt(x.a.pct, locale)} (${x.a.occupied})`, sortValue: (x) => x.a.pct, cell: (x) => <span className="tnum">{`${pctFmt(x.a.pct, locale)} · ${n(x.a.occupied)}`}</span> },
      { id: "b", header: t("compare.col.pctB"), align: "end", priority: 2, text: (x) => `${pctFmt(x.b.pct, locale)} (${x.b.occupied})`, sortValue: (x) => x.b.pct, cell: (x) => <span className="tnum">{`${pctFmt(x.b.pct, locale)} · ${n(x.b.occupied)}`}</span> },
      { id: "d", header: t("compare.col.dPts"), align: "end", priority: 1, text: (x) => signed(x.delta.pct, locale), sortValue: (x) => x.delta.pct, cell: (x) => <span className="tnum font-medium">{signed(x.delta.pct, locale)}</span> },
    ],
    [t, n, locale],
  );
  return (
    <section className="flex flex-col gap-3" aria-label={t("compare.tab.rooms")}>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="type-headline tnum" data-testid="compare-rooms-total">
          {t("compare.rooms.total", { a: pctFmt(r.a.pct, locale), b: pctFmt(r.b.pct, locale) })}
        </p>
        <p className="type-footnote text-label-2">
          {t("compare.rooms.weeks", { list: r.weeks.join(", ") })} · {pairOf(data.definitions.rooms, lang)}
        </p>
      </div>
      <DataTable tableId="compare-buildings" userId={me.data?.id} label={t("compare.rooms.byBuilding")} columns={buildingCols} rows={r.by_building} getRowId={(x) => x.building} defaultSort={[{ id: "building", desc: false }]} narrow="scroll" />
      <h3 className="mt-2 type-title-3">{t("compare.rooms.changed", { n: n(r.changed.length) })}</h3>
      <DataTable
        tableId="compare-rooms"
        userId={me.data?.id}
        label={t("compare.rooms.changedLabel")}
        columns={roomCols}
        rows={r.changed}
        getRowId={(x) => String(x.room_id)}
        defaultSort={[{ id: "d", desc: false }]}
        maxHeight="min(60dvh, 32rem)"
        rowProps={() => ({ "data-testid": "compare-room-row" })}
        toolbar={<CsvLink a={data.a.id} b={data.b.id} week={week} part="rooms" label={t("compare.csv.rooms")} />}
        empty={<p className="px-3 py-6 type-callout text-label-2">{t("compare.rooms.none")}</p>}
      />
    </section>
  );
}

/* ------------------------------------------------------------------ rules */

function RulesSection({ data, week }: { data: CompareData; week: number | null }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const me = useMe();
  const cols = useMemo<DataColumn<RuleRow>[]>(
    () => [
      { id: "rule", header: t("compare.col.rule"), pin: "left", priority: 1, grow: 2, minSize: 140, text: (r) => pairOf(r.label, lang), sortValue: (r) => pairOf(r.label, lang), cell: (r) => <span className="truncate font-medium" title={r.rule}>{pairOf(r.label, lang)}</span> },
      { id: "a", header: t("compare.col.penaltyA"), align: "end", priority: 2, text: (r) => String(r.a), sortValue: (r) => r.a, cell: (r) => <span className="tnum">{n(r.a)}</span> },
      { id: "b", header: t("compare.col.penaltyB"), align: "end", priority: 2, text: (r) => String(r.b), sortValue: (r) => r.b, cell: (r) => <span className="tnum">{n(r.b)}</span> },
      {
        id: "verdict",
        header: t("compare.col.verdict"),
        priority: 1,
        minSize: 130,
        text: (r) => `${signed(r.delta, locale)} ${t("compare.verdict.better")}`,
        extra: 30,
        sortValue: (r) => r.delta,
        cell: (r) => <VerdictTag v={r.better === "same" ? "same" : r.better === "b" ? "better" : "worse"} delta={r.delta} locale={locale} />,
      },
    ],
    [t, n, locale, lang],
  );
  const diagKeys = [...new Set([...Object.keys(data.diagnoses.a), ...Object.keys(data.diagnoses.b)])].sort();
  return (
    <section className="flex flex-col gap-3" aria-label={t("compare.tab.rules")}>
      <p className="type-footnote text-label-2">{t("compare.rules.lead")}</p>
      <DataTable
        tableId="compare-rules"
        userId={me.data?.id}
        label={t("compare.tab.rules")}
        columns={cols}
        rows={data.rules}
        getRowId={(r) => r.rule}
        defaultSort={[{ id: "verdict", desc: false }]}
        rowProps={() => ({ "data-testid": "compare-rule-row" })}
        toolbar={<CsvLink a={data.a.id} b={data.b.id} week={week} part="rules" label={t("compare.csv.rules")} />}
        empty={<p className="px-3 py-6 type-callout text-label-2">{t("compare.rules.none")}</p>}
      />
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl bg-card p-3 edge-hairline">
          <h3 className="type-headline">{t("compare.rules.waived")}</h3>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 type-callout">
            <dt className="text-label-2">A</dt>
            <dd>{data.waived_rules.a.length ? data.waived_rules.a.join(", ") : t("compare.rules.noneWaived")}</dd>
            <dt className="text-label-2">B</dt>
            <dd>{data.waived_rules.b.length ? data.waived_rules.b.join(", ") : t("compare.rules.noneWaived")}</dd>
          </dl>
        </div>
        <div className="rounded-xl bg-card p-3 edge-hairline">
          <h3 className="type-headline">{t("compare.rules.diagnoses")}</h3>
          {diagKeys.length ? (
            <table className="mt-1 w-full type-callout">
              <thead>
                <tr className="text-left type-footnote text-label-2">
                  <th className="py-1 font-medium">{t("compare.rules.code")}</th>
                  <th className="py-1 text-right font-medium">A</th>
                  <th className="py-1 text-right font-medium">B</th>
                </tr>
              </thead>
              <tbody>
                {diagKeys.map((k) => (
                  <tr key={k} className="edge-hairline-t">
                    <td className="py-1 font-mono type-footnote">{k}</td>
                    <td className="py-1 text-right">{n(data.diagnoses.a[k] ?? 0)}</td>
                    <td className="py-1 text-right">{n(data.diagnoses.b[k] ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mt-1 type-callout text-label-2">{t("compare.rules.noDiagnoses")}</p>
          )}
        </div>
      </div>
    </section>
  );
}
