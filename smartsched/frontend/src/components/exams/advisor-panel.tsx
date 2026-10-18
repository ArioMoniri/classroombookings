"use client";
/**
 * AS-17 `/exams/advisor` "Sınav yükü ve öneriler" (docs/research/2026-10-17-adaptive-scheduling.md §3.5): the exams
 * per day (ChartCard, the table twin and CSV included), advice cards for the peak day, slots whose seats exceed the
 * exam rooms and invigilators short, and the exam-slot holds (the room-periods the `slots` mode frees for bookings).
 * Advice only: nothing here moves an exam.
 */
import { CalendarClock, Users, Armchair, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { LazyBarChart } from "@/components/charts/chart-lazy";
import { singleConfig } from "@/components/charts/chart-tokens";
import { PageHeader } from "@/components/common/page-header";
import { ConfidenceNote } from "@/components/analytics/forecast-bits";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useExamForecast } from "@/lib/api/adaptive";
import { useI18n } from "@/lib/i18n/provider";
import { examAdvice, type AdviceKind } from "./advisor-model";

const ICON: Record<AdviceKind, typeof CalendarClock> = { peak_day: CalendarClock, seats: Armchair, invigilators: Users };
const SERIES = ["exams"] as const;
type DayRow = { date: string; exams: number; seats: number };

export function ExamAdvisorView() {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const params = useSearchParams();
  const { term, terms } = useActiveTerm();
  const fromUrl = Number(params.get("term")) || null;
  // the Final / make-up term is the one with exams: the active term otherwise
  const fallback = terms.find((x) => x.kind === "FINAL" && x.is_active)?.id ?? term?.id ?? null;
  const [picked, setPicked] = useState<number | null>(fromUrl);
  const termId = picked ?? fallback;
  const q = useExamForecast(termId);
  const d = q.data;
  const advice = useMemo(() => (d ? examAdvice(d, lang) : []), [d, lang]);
  const rows = useMemo<DayRow[]>(() => (d?.days ?? []).map((x) => ({ date: x.date, exams: x.exams, seats: x.seats })), [d]);
  const columns = useMemo<ChartColumn<DayRow>[]>(() => [{ key: "date", label: t("adaptive.exams.col.date"), kind: "date" }, { key: "exams", label: t("adaptive.exams.col.exams"), kind: "number" }, { key: "seats", label: t("adaptive.exams.col.seats"), kind: "number" }], [t]);
  const config = useMemo(() => singleConfig("exams", t("adaptive.exams.col.exams")), [t]);
  const dayLabel = (date: string) => d?.days.find((x) => x.date === date)?.label?.[lang] ?? date;
  const holds = d?.holds;

  return (
    <div className="flex min-w-0 flex-col gap-5" data-testid="exam-advisor">
      <PageHeader title={t("adaptive.exams.title")} subtitle={t("adaptive.exams.subtitle")} />
      <label className="flex max-w-xs flex-col gap-1">
        <span className="type-footnote font-medium text-label-2">{t("adaptive.peaks.term")}</span>
        <NativeSelect value={termId ?? ""} onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)} data-testid="advisor-term">
          {terms.map((x) => (
            <option key={x.id} value={x.id}>{x.name}</option>
          ))}
        </NativeSelect>
      </label>
      {termId === null ? (
        <p className="type-callout text-label-2">{t("analytics.noTerm")}</p>
      ) : q.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : q.isError ? (
        <p role="alert" className="type-callout text-label-2">{t("adaptive.loadError")}</p>
      ) : !d || d.confidence === "none" || d.days.length === 0 ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5" data-testid="advisor-needs">
          <p className="type-callout text-label-1">{d?.needs?.[lang] || t("adaptive.exams.empty")}</p>
        </div>
      ) : (
        <>
          <ConfidenceNote confidence={d.confidence} basis={d.basis?.[lang]} needs={d.needs?.[lang]} />
          <section aria-labelledby="adv-cards" className="flex flex-col gap-2">
            <h2 id="adv-cards" className="type-title-3 text-label-1">{t("adaptive.exams.adviceTitle")}</h2>
            <p className="type-footnote text-label-2">{t("adaptive.exams.adviceHint")}</p>
            {advice.length === 0 ? (
              <p className="type-callout text-label-1" data-testid="advisor-calm">{t("adaptive.exams.calm")}</p>
            ) : (
              <ul className="grid gap-2 md:grid-cols-2" data-testid="advisor-cards">
                {advice.map((a, i) => {
                  const Icon = ICON[a.kind];
                  return (
                    <li key={`${a.kind}-${a.date}-${a.period ?? 0}-${i}`}>
                      <Card className="flex flex-row items-start gap-3 p-4" data-testid="advisor-card" data-kind={a.kind}>
                        <Icon className="mt-0.5 size-5 shrink-0 text-label-2" aria-hidden />
                        <div className="min-w-0">
                          <p className="type-callout font-semibold text-label-1">{t(`adaptive.exams.card.${a.kind}.title`, { day: dayLabel(a.date), period: a.period ?? "" })}</p>
                          <p className="type-footnote text-label-2">{t(`adaptive.exams.card.${a.kind}.body`, { ...a.vars, day: dayLabel(a.date) })}</p>
                        </div>
                      </Card>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          <ChartCard<DayRow>
            id="exam-days"
            title={t("adaptive.exams.chartTitle")}
            hint={t("adaptive.exams.chartHint")}
            summary={d.peak_day ? t("adaptive.exams.chartSummary", { day: d.peak_label?.[lang] ?? d.peak_day, n: n(d.peak_exams ?? 0), mean: n(Math.round((d.weekday_mean ?? 0) * 10) / 10) }) : ""}
            state={rows.length ? "ready" : "empty"}
            columns={columns}
            rows={rows}
            series={1}
            height={200}
          >
            {(ctx) => <LazyBarChart {...ctx} data={rows} config={config} xKey="date" series={SERIES} />}
          </ChartCard>
          {holds && (holds.held_room_periods ?? 0) + (holds.freed_room_periods ?? 0) > 0 ? (
            <Card className="flex flex-row flex-wrap items-center justify-between gap-3 p-4" data-testid="advisor-holds">
              <p className="min-w-0 type-callout text-label-1">{t("adaptive.exams.holds", { held: n(holds.held_room_periods ?? 0), freed: n(holds.freed_room_periods ?? 0), buffer: n(holds.buffer_periods ?? 0) })}</p>
              <Button size="sm" variant="ghost" nativeButton={false} render={<Link href="/settings?tab=booking-rules" />}>
                {t("adaptive.exams.holdsLink")} <ArrowRight aria-hidden />
              </Button>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}
