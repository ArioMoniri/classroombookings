"use client";

import Link from "next/link";
import { toast } from "sonner";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useStudio } from "./studio-context";
import type { Horizon } from "./studio-reducer";
import { BareButton } from "@/components/shell/bare-button";

function relDays(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-days, "day");
}

/** Week chip selection: a plain click replaces, ⌘/Ctrl/⇧ toggles one week (usability M10). */
export function nextWeeks(chosen: number[], i: number, additive: boolean): number[] {
  if (!additive) return [i];
  return chosen.includes(i) ? chosen.filter((x) => x !== i) : [...chosen, i].sort((a, b) => a - b);
}

export function ScopeStep({ onKind }: { onKind: (k: "COURSE" | "EXAM") => void }) {
  const { t, n, locale } = useI18n();
  const { terms } = useActiveTerm();
  const setTermId = useUiStore((s) => s.setTermId);
  const { termId, kind, local, dispatch, store, termWeeks, summary, summaryData, classes, classesLoading } = useStudio();
  const isAdmin = useStudio().isAdmin;

  const lecture = termWeeks.filter((w) => w.kind !== "EXAM" || kind === "EXAM");
  const selectable = kind === "EXAM" ? termWeeks.filter((w) => w.kind === "EXAM") : lecture;
  const chosen = local.horizon_params.weeks ?? [];

  const setScope = (horizon: Horizon, weeks?: number[], start?: number) => {
    const before = { horizon: local.horizon, horizon_params: local.horizon_params };
    const hp = horizon === "TERM" ? {} : horizon === "MONTH" ? { start_week: start ?? chosen[0] ?? selectable[0]?.index ?? 1 } : { weeks: weeks ?? chosen };
    dispatch({ type: "setScope", horizon, horizon_params: hp });
    store.getState().record({ label: t("studio.history.scope"), undo: () => dispatch({ type: "setScope", ...before }), redo: () => dispatch({ type: "setScope", horizon, horizon_params: hp }) });
  };
  /** Plain click/Enter **replaces** the selection (usability M10: W1 stayed selected and W3 was added);
   *  ⌘/Ctrl/⇧ + click adds or removes one week, like selecting files in Finder or Explorer. */
  const pickWeek = (i: number, additive: boolean) => {
    if (local.horizon === "MONTH") return setScope("MONTH", undefined, i);
    if (!additive && chosen.length === 1 && chosen[0] === i) return;
    setScope("WEEK", nextWeeks(chosen, i, additive));
  };

  const noTerm = terms.length === 0;
  const nothing = !classesLoading && classes !== undefined && classes.length === 0;
  const noExamWeeks = kind === "EXAM" && termWeeks.length > 0 && !termWeeks.some((w) => w.kind === "EXAM");
  const holidays = summary.holidayWeeks.length;

  if (noTerm)
    return (
      <div className="rounded-2xl bg-fill-3 p-6 text-sm" data-testid="scope-step">
        <p>{t("studio.scope.noTerm")}</p>
        {isAdmin ? (
          <Button className="mt-3" render={<Link href="/settings" />}>
            {t("studio.scope.createTerm")}
          </Button>
        ) : null}
      </div>
    );

  return (
    <div className="space-y-5" data-testid="scope-step">
      {/* fields at their natural widths that wrap as whole fields: three equal columns squeezed the horizon control
          into its select fallback at 1440 (each control keeps one row and one height, review §3 Generate) */}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-4">
        <div className="grid min-w-48 max-w-full gap-1.5">
          <Label htmlFor="scope-term">{t("studio.scope.term")}</Label>
          <NativeSelect
            id="scope-term"
            value={String(termId)}
            onChange={(e) => {
              const id = Number(e.target.value);
              setTermId(id);
              toast(t("nav.switched", { term: terms.find((x) => x.id === id)?.name ?? "" }));
            }}
          >
            {terms.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        {/* 200 % text (mobile-b phase 2): min-w-0 / max-w-full let the segment fall back to its select instead of
            pushing the page sideways (the label row measured 391–477 px at 390) */}
        <div className="grid min-w-0 max-w-full grid-cols-[minmax(0,1fr)] gap-1.5">
          <span id="scope-kind" className="text-sm font-medium">
            {t("studio.scope.kind")}
          </span>
          <SegmentedControl semantics="radiogroup" aria-labelledby="scope-kind" value={kind} onValueChange={onKind} data-testid="scope-kind" options={[{ value: "COURSE", label: t("studio.kind.COURSE"), testId: "kind-COURSE" }, { value: "EXAM", label: t("studio.kind.EXAM"), testId: "kind-EXAM" }]} />
        </div>
        <div className="grid min-w-0 max-w-full grid-cols-[minmax(0,1fr)] gap-1.5">
          <span id="scope-horizon" className="text-sm font-medium">
            {t("studio.scope.horizon")}
          </span>
          {kind === "EXAM" ? (
            <SegmentedControl semantics="radiogroup" aria-labelledby="scope-horizon" value={local.horizon === "TERM" ? "TERM" : "WEEK"} onValueChange={(h) => setScope(h as Horizon, h === "WEEK" ? (chosen.length ? chosen : selectable.slice(0, 1).map((w) => w.index)) : undefined)} options={[{ value: "WEEK", label: t("studio.horizon.EXAM_WEEKS") }, { value: "TERM", label: t("studio.horizon.EXAM") }]} />
          ) : (
            <SegmentedControl semantics="radiogroup"
              aria-labelledby="scope-horizon"
              value={local.horizon}
              onValueChange={(h) => setScope(h, h === "WEEK" ? (chosen.length ? chosen : selectable.slice(0, 1).map((w) => w.index)) : undefined)}
              data-testid="scope-horizon"
              options={[
                { value: "WEEK", label: t("studio.horizon.WEEK"), testId: "horizon-WEEK" },
                { value: "MONTH", label: t("studio.horizon.MONTH"), testId: "horizon-MONTH" },
                { value: "TERM", label: t("studio.horizon.TERM"), testId: "horizon-TERM" },
              ]}
            />
          )}
        </div>
      </div>

      {noExamWeeks ? <p className="rounded-md bg-status-warning px-3 py-2 text-sm text-status-warning-fg">{t("studio.scope.examNoWeeks")}</p> : null}

      {local.horizon !== "TERM" ? (
        <div className="space-y-1.5">
          <p className="text-sm font-medium" id="scope-weeks">
            {local.horizon === "MONTH" ? t("studio.scope.monthFrom") : t("studio.scope.weeks")}
          </p>
          {termWeeks.length === 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {Array.from({ length: 14 }, (_, i) => (
                <Skeleton key={i} className="h-11 w-14" />
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5" role="group" aria-labelledby="scope-weeks">
              {termWeeks
                .filter((w) => (kind === "EXAM" ? w.kind === "EXAM" : w.kind !== "EXAM"))
                .map((w) => {
                  const holiday = w.kind === "HOLIDAY";
                  const on = summary.weeks.includes(w.index);
                  return (
                    <BareButton
                      key={w.id}
                      aria-pressed={on}
                      disabled={holiday}
                      title={holiday ? t("studio.scope.holiday", { label: w.label }) : w.label}
                      aria-label={`${t("glass.studio.weekN", { n: w.index })} ${formatDate(w.start_date, locale)}${holiday ? `, ${t("studio.scope.holiday", { label: w.label })}` : ""}`}
                      onClick={(e) => pickWeek(w.index, e.metaKey || e.ctrlKey || e.shiftKey)}
                      className={cn(
                        "flex min-w-14 flex-col items-center rounded-xl px-2.5 py-1.5 type-footnote transition-[background-color,color,transform] duration-(--dur-fast) ease-(--spring-snappy) active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-(--focus) pointer-coarse:min-h-11 disabled:cursor-not-allowed disabled:opacity-50",
                        on ? "bg-tint-soft text-tint-text edge-tint" : "bg-fill-3 text-label-1 edge-hairline hover:bg-fill-2",
                        holiday && "hatch-preoccupied",
                      )}
                      data-testid={`week-${w.index}`}
                    >
                      <span className="font-semibold tabular-nums">{t("glass.studio.weekShort", { n: w.index })}</span>
                      <span className={cn("type-caption", on ? "text-tint-text" : "text-label-3")}>{formatDate(w.start_date, locale, { day: "numeric", month: "short" })}</span>
                    </BareButton>
                  );
                })}
            </div>
          )}
          {local.horizon === "WEEK" ? <p className="type-footnote text-label-3">{t("glass.studio.weekHint")}</p> : null}
          {local.horizon === "WEEK" && chosen.length === 0 ? <p className="text-xs text-status-warning-fg">{t("studio.scope.pickWeeks")}</p> : null}
        </div>
      ) : null}

      {nothing ? (
        <div className="rounded-xl bg-fill-3 p-4 type-callout edge-hairline" data-testid="scope-empty">
          <p>{t("studio.scope.nothingToPlan")}</p>
          <Button className="mt-3" render={<Link href={kind === "EXAM" ? "/import?source=exam" : "/import?source=planning"} />}>
            {t("studio.scope.importCta")}
          </Button>
        </div>
      ) : (
        <div className="rounded-xl bg-fill-3 p-4 edge-hairline">
          {/* one loading signal, no zero counts while counting (review 2026-10-15 §2 "Loading states") */}
          <p className="type-body text-label-1" aria-live="polite" data-testid="scope-sentence">
            {/* the selected term's summary is not in yet (a term switch): count, never "0 derslikte" (round-1 R1-S-21) */}
            {(classesLoading && !classes) || summary.rooms === null ? t("studio.scope.counting") : t("studio.scope.sentence", { n: summary.classesIn, rooms: summary.rooms, weeks: summary.weekCount })}
          </p>
          {(classesLoading && !classes) || summary.rooms === null ? (
            <Skeleton className="mt-1.5 h-3.5 w-2/3 rounded-sm" />
          ) : (
            <p className="mt-1 type-callout text-label-2">{t("studio.scope.line2", { out: n(summary.classesOut), pinned: n(summary.pinned), holidays })}</p>
          )}
          {summary.rooms !== null && local.horizon === "TERM" && summary.datedWeeks < summary.weekCount ? (
            // Güz has 14 weeks but only 2 dated week rows: say so instead of "2 hafta" (round-1 R1-S-22)
            <p className="mt-1 type-footnote text-label-2" data-testid="scope-term-weeks">{t("studio.scope.termWeeks", { total: n(summary.weekCount), dated: n(summary.datedWeeks) })}</p>
          ) : null}
          {summaryData?.last_good_run ? (
            <p className="mt-2 text-sm">
              <Link href={`/runs/${summaryData.last_good_run.id}`} className="text-tint-text underline-offset-2 hover:underline">
                {t("studio.scope.lastRun", { id: summaryData.last_good_run.id, when: relDays(summaryData.last_good_run.finished_at, locale) })}
              </Link>
              {summaryData.last_good_run.status === "FEASIBLE_PARTIAL" ? (
                <span className="text-status-warning-fg"> · {t("glass.studio.lastPartial")}</span>
              ) : summaryData.last_good_run.hard_score === 100 ? (
                <span className="text-label-2"> · {t("studio.scope.allRulesMet")}</span>
              ) : null}
            </p>
          ) : (
            <p className="mt-2 text-sm text-label-2">{t("studio.scope.noRun")}</p>
          )}
        </div>
      )}
    </div>
  );
}
