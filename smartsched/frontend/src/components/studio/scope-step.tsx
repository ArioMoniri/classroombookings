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
import { Segmented } from "./segmented";
import { useStudio } from "./studio-context";
import type { Horizon } from "./studio-reducer";

function relDays(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-days, "day");
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
  const toggleWeek = (i: number) => {
    if (local.horizon === "MONTH") return setScope("MONTH", undefined, i);
    const next = chosen.includes(i) ? chosen.filter((x) => x !== i) : [...chosen, i].sort((a, b) => a - b);
    setScope("WEEK", next);
  };

  const noTerm = terms.length === 0;
  const nothing = !classesLoading && classes !== undefined && classes.length === 0;
  const noExamWeeks = kind === "EXAM" && termWeeks.length > 0 && !termWeeks.some((w) => w.kind === "EXAM");
  const holidays = summary.holidayWeeks.length;

  if (noTerm)
    return (
      <div className="rounded-lg border p-6 text-center text-sm" data-testid="scope-step">
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
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="grid gap-1.5">
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
        <div className="grid gap-1.5">
          <span id="scope-kind" className="text-sm font-medium">
            {t("studio.scope.kind")}
          </span>
          <Segmented labelledBy="scope-kind" value={kind} onChange={onKind} testId="scope-kind" options={[{ value: "COURSE", label: t("studio.kind.COURSE"), testId: "kind-COURSE" }, { value: "EXAM", label: t("studio.kind.EXAM"), testId: "kind-EXAM" }]} />
        </div>
        <div className="grid gap-1.5">
          <span id="scope-horizon" className="text-sm font-medium">
            {t("studio.scope.horizon")}
          </span>
          {kind === "EXAM" ? (
            <Segmented labelledBy="scope-horizon" value={local.horizon === "TERM" ? "TERM" : "WEEK"} onChange={(h) => setScope(h as Horizon, h === "WEEK" ? (chosen.length ? chosen : selectable.slice(0, 1).map((w) => w.index)) : undefined)} options={[{ value: "WEEK", label: t("studio.horizon.EXAM_WEEKS") }, { value: "TERM", label: t("studio.horizon.EXAM") }]} />
          ) : (
            <Segmented
              labelledBy="scope-horizon"
              value={local.horizon}
              onChange={(h) => setScope(h, h === "WEEK" ? (chosen.length ? chosen : selectable.slice(0, 1).map((w) => w.index)) : undefined)}
              testId="scope-horizon"
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
                    <button
                      key={w.id}
                      type="button"
                      aria-pressed={on}
                      disabled={holiday}
                      title={holiday ? t("studio.scope.holiday", { label: w.label }) : w.label}
                      aria-label={`W${w.index} ${formatDate(w.start_date, locale)}${holiday ? `, ${t("studio.scope.holiday", { label: w.label })}` : ""}`}
                      onClick={() => toggleWeek(w.index)}
                      className={cn("flex min-w-14 flex-col items-center rounded-md border px-2 py-1 text-xs pointer-coarse:min-h-11 disabled:cursor-not-allowed disabled:opacity-50", on ? "border-primary bg-primary-tint text-primary" : "hover:bg-muted", holiday && "hatch-preoccupied")}
                      data-testid={`week-${w.index}`}
                    >
                      <span className="font-mono font-semibold">W{w.index}</span>
                      <span className="text-[10px] text-muted-foreground">{formatDate(w.start_date, locale)}</span>
                    </button>
                  );
                })}
            </div>
          )}
          {local.horizon === "WEEK" && chosen.length === 0 ? <p className="text-xs text-status-warning-fg">{t("studio.scope.pickWeeks")}</p> : null}
        </div>
      ) : null}

      {nothing ? (
        <div className="rounded-lg border p-4 text-sm" data-testid="scope-empty">
          <p>{t("studio.scope.nothingToPlan")}</p>
          <Button className="mt-3" render={<Link href={kind === "EXAM" ? "/import?source=exam" : "/import?source=planning"} />}>
            {t("studio.scope.importCta")}
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border bg-muted/40 p-4">
          <p className="text-base" aria-live="polite" data-testid="scope-sentence">
            {classesLoading && !classes ? t("studio.scope.counting") : t("studio.scope.sentence", { n: n(summary.classesIn), rooms: n(summary.rooms), weeks: n(summary.weeks.length) })}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">{t("studio.scope.line2", { out: n(summary.classesOut), pinned: n(summary.pinned), holidays: n(holidays) })}</p>
          {summaryData?.last_good_run ? (
            <p className="mt-2 text-sm">
              <Link href={`/runs/${summaryData.last_good_run.id}`} className="text-primary underline-offset-2 hover:underline">
                {t("studio.scope.lastRun", { id: summaryData.last_good_run.id, when: relDays(summaryData.last_good_run.finished_at, locale) })}
              </Link>
              {summaryData.last_good_run.hard_score === 100 ? <span className="text-muted-foreground"> · {t("studio.scope.allRulesMet")}</span> : null}
            </p>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">{t("studio.scope.noRun")}</p>
          )}
        </div>
      )}
    </div>
  );
}
