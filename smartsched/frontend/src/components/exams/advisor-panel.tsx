"use client";
/**
 * AS-17 `/exams/advisor` "Sınav yükü ve öneriler" (docs/research/2026-10-17-adaptive-scheduling.md §3.5): the exams
 * per day (ChartCard, the table twin and CSV included), advice cards for the peak day, slots whose seats exceed the
 * exam rooms and invigilators short, and the exam-slot holds (the room-periods the `slots` mode frees for bookings).
 * Nothing moves by itself: a planner accepts one ranked move with "Uygula" (AS20-F04; the toast's "Geri al" undoes
 * it). AS20-F05: the peak day leads; at most 5 cards and 10 moves show until "Tümünü göster".
 */
import { CalendarClock, Users, Armchair, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { LazyBarChart } from "@/components/charts/chart-lazy";
import { singleConfig } from "@/components/charts/chart-tokens";
import { PageHeader } from "@/components/common/page-header";
import { ConfidenceNote, NoTerms } from "@/components/analytics/forecast-bits";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { apiText } from "@/lib/api/seasons";
import { useApplyAdvice, useExamAdvice, useExamForecast, type AdviceApplyIn, type AdviceCard, type AdviceMove } from "@/lib/api/adaptive";
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
  const server = useExamAdvice(termId);
  // the AS-12 advisor answers cards + ranked moves; until its route is deployed the load gives the cards
  const fromServer = server.data && server.data.confidence !== "none" ? server.data : null;
  const advice = useMemo(() => (d ? examAdvice(d, lang) : []), [d, lang]);
  const rows = useMemo<DayRow[]>(() => (d?.days ?? []).map((x) => ({ date: x.date, exams: x.exams, seats: x.seats })), [d]);
  const columns = useMemo<ChartColumn<DayRow>[]>(() => [{ key: "date", label: t("adaptive.exams.col.date"), kind: "date" }, { key: "exams", label: t("adaptive.exams.col.exams"), kind: "number" }, { key: "seats", label: t("adaptive.exams.col.seats"), kind: "number" }], [t]);
  const config = useMemo(() => singleConfig("exams", t("adaptive.exams.col.exams")), [t]);
  const dayLabel = (date: string) => d?.days.find((x) => x.date === date)?.label?.[lang] ?? date;
  const holds = d?.holds;

  return (
    <div className="flex min-w-0 flex-col gap-5" data-testid="exam-advisor">
      <PageHeader title={t("adaptive.exams.title")} subtitle={t("adaptive.exams.subtitle")} />
      {terms.length === 0 ? (
        <NoTerms />
      ) : (
        <label className="flex max-w-xs flex-col gap-1">
          <span className="type-footnote font-medium text-label-2">{t("adaptive.peaks.term")}</span>
          <NativeSelect value={termId ?? ""} onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)} data-testid="advisor-term">
            {terms.map((x) => (
              <option key={x.id} value={x.id}>{x.name}</option>
            ))}
          </NativeSelect>
        </label>
      )}
      {terms.length === 0 ? null : termId === null ? (
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
            {fromServer ? (
              <ServerAdvice cards={fromServer.cards} moves={fromServer.suggestions} termId={termId} basis={fromServer.basis?.[lang]} />
            ) : advice.length === 0 ? (
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

/** AS20-F05: the order the cards are read in (the peak day is the page's one message) */
const CARD_ORDER = ["peak_day", "seats", "cohort_day", "clash", "back_to_back", "front_load"];
const CARDS_SHOWN = 5;
const MOVES_SHOWN = 10;
const cardRank = (kind: string) => {
  const i = CARD_ORDER.indexOf(kind);
  return i < 0 ? CARD_ORDER.length : i;
};

/** the AS-12 advisor's own cards and its ranked moves: "Uygula" moves the exam (undo in the toast), the link edits it */
function ServerAdvice({ cards, moves, termId, basis }: { cards: AdviceCard[]; moves: AdviceMove[]; termId: number | null; basis?: string }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [allCards, setAllCards] = useState(false);
  const [allMoves, setAllMoves] = useState(false);
  const apply = useApplyAdvice();
  const sorted = useMemo(() => cards.map((c, i) => ({ c, i })).sort((a, b) => cardRank(a.c.kind) - cardRank(b.c.kind) || a.i - b.i).map((x) => x.c), [cards]);
  const edit = (ids: number[]) => `/requests?kind=exams${ids[0] ? `&id=${ids[0]}` : ""}${termId ? `&term=${termId}` : ""}`;
  const run = (body: AdviceApplyIn, undo: boolean) =>
    apply.mutate(body, {
      onSuccess: (out) => {
        if (undo) {
          toast.success(t("adaptive.exams.undone"));
          return;
        }
        toast.success((lang === "tr" ? out.message_tr : out.message_en) || t("adaptive.exams.applied"), {
          action: { label: t("common.undo"), onClick: () => run(out.undo, true) },
        });
      },
      onError: (e) => toast.error(apiText(e, locale)),
    });
  const accept = (m: AdviceMove) => {
    if (termId === null || !m.request_ids.length || m.to.start === undefined) return;
    run({ term_id: termId, request_ids: m.request_ids, date: m.to.date, start_period: m.to.start }, false);
  };
  if (!cards.length && !moves.length) return <p className="type-callout text-label-1" data-testid="advisor-calm">{t("adaptive.exams.calm")}</p>;
  const shownCards = allCards ? sorted : sorted.slice(0, CARDS_SHOWN);
  const shownMoves = allMoves ? moves : moves.slice(0, MOVES_SHOWN);
  return (
    <div className="flex flex-col gap-3">
      {sorted.length ? (
        <ul className="grid gap-2 md:grid-cols-2" data-testid="advisor-cards">
          {shownCards.map((c, i) => (
            <li key={`${c.kind}-${c.date ?? ""}-${i}`} className={i === 0 && c.kind === "peak_day" ? "md:col-span-2" : undefined}>
              <Card className="flex flex-row items-start gap-3 p-4" data-testid="advisor-card" data-kind={c.kind}>
                <CalendarClock className="mt-0.5 size-5 shrink-0 text-label-2" aria-hidden />
                <div className="min-w-0">
                  <p className={i === 0 && c.kind === "peak_day" ? "type-headline text-label-1" : "type-callout text-label-1"}>{c.text[lang] || c.text.tr}</p>
                  {c.suggestion_ranks.length ? <p className="type-footnote text-label-2">{t("adaptive.exams.seeMoves", { list: c.suggestion_ranks.map((r) => `#${r}`).join(", ") })}</p> : null}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
      {sorted.length > CARDS_SHOWN && !allCards ? (
        <Button size="sm" variant="secondary" className="self-start" onClick={() => setAllCards(true)} data-testid="advisor-cards-all">{t("adaptive.showAll", { n: sorted.length })}</Button>
      ) : null}
      {moves.length ? (
        <section aria-labelledby="adv-moves" className="flex flex-col gap-2">
          <h3 id="adv-moves" className="type-headline text-label-1">{t("adaptive.exams.movesTitle")}</h3>
          {basis ? <p className="type-footnote text-label-2">{basis}</p> : null}
          <ol className="flex flex-col" data-testid="advisor-moves">
            {shownMoves.map((m) => (
              <li key={m.rank} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-2 type-callout" data-testid="advisor-move">
                <span className="font-semibold tabular-nums text-label-2">#{m.rank}</span>
                <span className="min-w-0 flex-1 text-label-1">{m.text[lang] || m.text.tr}</span>
                <span className="flex gap-2">
                  {m.to.start !== undefined && m.request_ids.length ? (
                    <Button size="sm" onClick={() => accept(m)} disabled={apply.isPending} data-testid="advisor-apply">
                      {t("adaptive.exams.apply")}
                    </Button>
                  ) : null}
                  <Button size="sm" variant="ghost" nativeButton={false} render={<Link href={edit(m.request_ids)} />} data-testid="advisor-edit">
                    {t("adaptive.exams.editRequest")}
                  </Button>
                </span>
              </li>
            ))}
          </ol>
          {moves.length > MOVES_SHOWN && !allMoves ? (
            <Button size="sm" variant="secondary" className="self-start" onClick={() => setAllMoves(true)} data-testid="advisor-moves-all">{t("adaptive.showAll", { n: moves.length })}</Button>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
