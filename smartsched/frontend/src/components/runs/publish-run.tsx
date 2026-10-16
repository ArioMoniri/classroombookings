"use client";

/**
 * Publish a finished run as the term's timetable (admin persona M-03: `POST /runs/{id}/activate` had no button).
 * The confirmation names what changes — the scope (weeks or the whole term), the run it replaces, a partial
 * run's missing classes and the report's exceptions — and the backend's publish guard decides: a 409 lists its
 * reasons, shown verbatim, and the dialog stays open.
 * 2026-10-15 contract: a 409 `scope_reduction` (the run covers fewer weeks than the published one) shows the
 * weeks that would leave the published timetable and needs an explicit confirm that resends
 * `confirm_scope_reduction: true`; a partial run needs a ticked confirmation that names the unplaced classes.
 * Round-1 R1-M-02 / R1-S-01: a week run that replaces a published run shows the scope tick before the first try
 * (and after a 409 `scope_reduction`); a run whose only hard-rule breaks are forced moves lists them with their
 * reasons and needs its own tick (`confirm_forced_breaks`); the request is silent, so a 409 is never the global
 * "someone else changed it" toast.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { BusyButton } from "@/components/ui/busy-label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { HttpError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { qk } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { weekList } from "@/lib/i18n/turkish";
import { partialCounts } from "./runs-list";
import { sectionOf } from "./diagnosis-format";
import { isStaleConflict, refusalBody, serverMessage } from "@/lib/api/error-text";
import { BROKEN_RULE_TR, type RunTruth, type VerdictException } from "./run-truth";

const rec = (v: unknown): Record<string, unknown> | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);

/** The guard's reasons: `{detail: {message, issues: [...]}}` (FastAPI wraps the dict), or a plain detail string. */
export function publishRefusals(e: unknown): string[] {
  if (!(e instanceof HttpError)) return [e instanceof Error ? e.message : String(e)];
  const d = rec(e.detail);
  const inner = rec(d?.detail) ?? d;
  const issues = Array.isArray(inner?.issues) ? inner.issues.map(String).filter(Boolean) : [];
  if (issues.length) return issues;
  if (typeof inner?.message === "string") return [inner.message];
  if (typeof d?.detail === "string") return [d.detail];
  if (typeof e.detail === "string") return [e.detail];
  return [e.message];
}

/** 409 `scope_reduction` payload (FastAPI wraps the dict in `detail`). */
export function scopeReductionOf(e: unknown): { weeksLost: number[]; activeId: number | null; message: string } | null {
  if (!(e instanceof HttpError)) return null;
  const d = rec(e.detail);
  const inner = rec(d?.detail) ?? d;
  if (inner?.code !== "scope_reduction") return null;
  const lost = Array.isArray(inner.weeks_lost) ? inner.weeks_lost.map(Number).filter(Number.isFinite) : [];
  const active = rec(inner.active);
  return { weeksLost: lost, activeId: typeof active?.run_id === "number" ? active.run_id : null, message: String(inner.message_tr ?? inner.message ?? "") };
}

/** 409 `forced_breaks`: the hard rules the run breaks through forced moves with a reason (round-1 R1-S-01). */
export function forcedBreaksOf(e: unknown): { breaks: { rule: string; message: string; reason: string | null }[]; message: string } | null {
  const b = refusalBody(e);
  if (b?.code !== "forced_breaks") return null;
  const list = Array.isArray(b.breaks) ? b.breaks.filter((x): x is Record<string, unknown> => !!x && typeof x === "object") : [];
  return {
    breaks: list.map((x) => ({ rule: String(x.rule ?? ""), message: String(x.message ?? ""), reason: typeof x.reason === "string" ? x.reason : null })),
    message: String(b.message_tr ?? b.message ?? ""),
  };
}

export function PublishRunButton({ run, published, exceptions = [], truth = null }: { run: ScheduleRun; /** the term's published run of this kind, if another one */ published: number | null; exceptions?: VerdictException[]; truth?: RunTruth | null }) {
  const { t, n, locale } = useI18n();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [refusals, setRefusals] = useState<string[]>([]);
  const [reduction, setReduction] = useState<ReturnType<typeof scopeReductionOf>>(null);
  const [forcedRefusal, setForcedRefusal] = useState<ReturnType<typeof forcedBreaksOf>>(null);
  const [partialOk, setPartialOk] = useState(false);
  const [scopeOk, setScopeOk] = useState(false);
  const [forcedOk, setForcedOk] = useState(false);
  const tr = locale === "tr";
  const publish = useMutation({
    mutationFn: (o: { scope: boolean; forced: boolean }) => api.runs.activate(run.id, { confirmScopeReduction: o.scope, confirmForcedBreaks: o.forced }),
    onSuccess: () => {
      setOpen(false);
      setReduction(null);
      setForcedRefusal(null);
      toast.success(t("runs.publish.done", { id: run.id }));
    },
    onError: (e) => {
      // round-1 R1-M-02: each 409 in its own words; the scope and the forced breaks get their own confirm
      const r = scopeReductionOf(e);
      const f = forcedBreaksOf(e);
      if (r) {
        setReduction(r);
        setScopeOk(false);
        setRefusals([]);
      } else if (f) {
        setForcedRefusal(f);
        setForcedOk(false);
        setRefusals([]);
      } else {
        const said = serverMessage(e, locale);
        setRefusals(isStaleConflict(e) ? [t("glass.errors.conflict")] : publishRefusals(e).length ? publishRefusals(e) : said ? [said] : []);
      }
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["runs"] });
      void qc.invalidateQueries({ queryKey: qk.run(run.id) });
    },
  });
  if (run.is_active) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-status-feasible px-2.5 py-1 type-footnote font-medium text-status-feasible-fg" data-testid="run-published">
        <BadgeCheck className="size-3.5" aria-hidden /> {t("runs.publish.published")}
      </span>
    );
  }
  const partial = partialCounts(run);
  const weeks = run.horizon === "WEEK" && run.horizon_params.weeks.length ? run.horizon_params.weeks : [];
  const unplaced = partial ? [...new Set(run.diagnosis.filter((d) => sectionOf(d) === "unplaced").flatMap((d) => d.event_labels))] : [];
  // a week run replacing a published run: the weeks outside it leave the published timetable - an explicit tick
  const needsScope = (weeks.length > 0 && published !== null) || reduction !== null;
  const forcedList = forcedRefusal?.breaks ?? (truth?.broken ?? []).filter((b) => b.explained).map((b) => ({ rule: b.rule, message: b.message, reason: b.reason }));
  const needsForced = forcedList.length > 0;
  const blocked = (Boolean(partial) && !partialOk) || (needsScope && !scopeOk) || (needsForced && !forcedOk);
  return (
    <>
      <Button
        size="sm"
        onClick={() => {
          setRefusals([]);
          setReduction(null);
          setForcedRefusal(null);
          setPartialOk(false);
          setScopeOk(false);
          setForcedOk(false);
          setOpen(true);
        }}
        data-testid="run-publish"
      >
        <Upload aria-hidden /> {t("runs.publish.button")}
      </Button>
      <Dialog open={open} onOpenChange={(o) => !publish.isPending && setOpen(o)}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("runs.publish.title", { id: run.id })}</DialogTitle>
            <DialogDescription>{weeks.length ? t("runs.publish.scopeWeeks", { weeks: weekList(weeks, tr ? "tr" : "en"), term: run.term_code }) : t("runs.publish.scopeTerm", { term: run.term_code })}</DialogDescription>
          </DialogHeader>
          <ul className="list-disc space-y-1 pl-5 type-callout text-label-1">
            <li>{published !== null ? t("runs.publish.replaces", { id: published }) : t("runs.publish.first")}</li>
            {partial ? <li className="text-status-warning-fg">{t("runs.publish.partial", { placed: n(partial.placed), total: n(partial.total), missing: n(partial.total - partial.placed) })}</li> : null}
            {truth?.verdict === "exceptions"
              ? truth.exceptions.map((e) => (
                  <li key={e.cause} className="text-status-warning-fg">
                    {tr ? e.label.tr : e.label.en} · {n(e.classes)} {tr ? "ders" : "classes"}
                  </li>
                ))
              : null}
            {exceptions.map((e) => (
              <li key={e.key} className="text-status-warning-fg">{t(`glass.report.exc.${e.key}`, { n: n(e.n), rules: (e.rules ?? []).join(", ") })}</li>
            ))}
          </ul>
          {partial ? (
            <div className="grid gap-2 rounded-xl bg-status-warning px-3 py-2" data-testid="publish-partial">
              <p className="type-callout font-medium text-status-warning-fg">
                {tr ? `Yerleşmeyen ${n(partial.total - partial.placed)} ders yayımlanan programda olmayacak:` : `${n(partial.total - partial.placed)} unplaced classes will not be in the published timetable:`}
              </p>
              {unplaced.length ? (
                <ul className="max-h-32 overflow-y-auto pl-4 type-footnote text-label-1 [list-style:disc]">
                  {unplaced.slice(0, 30).map((u) => <li key={u}>{u}</li>)}
                  {unplaced.length > 30 ? <li className="text-label-2">{tr ? `ve ${unplaced.length - 30} ders daha` : `and ${unplaced.length - 30} more`}</li> : null}
                </ul>
              ) : null}
              <label className="flex min-h-11 items-center gap-2 type-callout text-label-1 pointer-fine:min-h-0">
                <Checkbox checked={partialOk} onCheckedChange={(v) => setPartialOk(Boolean(v))} data-testid="publish-partial-ack" />
                {tr ? "Eksik derslerle yayımlamayı onaylıyorum" : "I confirm publishing without these classes"}
              </label>
            </div>
          ) : null}
          {needsScope ? (
            <div role={reduction ? "alert" : undefined} className="grid gap-1.5 rounded-xl bg-status-warning px-3 py-2 type-callout text-status-warning-fg" data-testid="publish-scope-reduction">
              <p className="font-medium">
                {reduction
                  ? tr
                    ? `Bu çalıştırma daha az hafta kapsıyor: ${weekList(reduction.weeksLost, "tr")}${reduction.activeId ? ` (#${reduction.activeId})` : ""} yayından kalkacak.`
                    : `This run covers fewer weeks: ${weekList(reduction.weeksLost, "en")}${reduction.activeId ? ` of #${reduction.activeId}` : ""} will leave the published timetable.`
                  : t("runs.publish.weeksOnly")}
              </p>
              {reduction?.message ? <p className="type-footnote text-label-1">{reduction.message}</p> : null}
              <label className="flex min-h-11 items-center gap-2 text-label-1 pointer-fine:min-h-0">
                <Checkbox checked={scopeOk} onCheckedChange={(v) => setScopeOk(Boolean(v))} data-testid="publish-scope-ack" />
                {tr
                  ? `Evet, ${weeks.length ? weekList(weeks, "tr") + " dışındaki haftalar" : "bu haftalar"}${published !== null ? ` #${published} programından` : ""} yayından kalksın`
                  : `Yes, remove the ${weeks.length ? `weeks outside ${weekList(weeks, "en")}` : "other weeks"}${published !== null ? ` of #${published}` : ""} from the published timetable`}
              </label>
            </div>
          ) : null}
          {needsForced ? (
            <div role={forcedRefusal ? "alert" : undefined} className="grid gap-1.5 rounded-xl bg-status-infeasible px-3 py-2 type-callout text-status-infeasible-fg" data-testid="publish-forced-breaks">
              <p className="font-medium">{tr ? `Bu program ${n(forcedList.length)} kesin kuralı gerekçeli zorunlu taşımalarla bozuyor:` : `This timetable breaks ${n(forcedList.length)} hard rule(s) through forced moves with a reason:`}</p>
              <ul className="list-disc pl-5 type-footnote text-label-1">
                {forcedList.slice(0, 10).map((b, i) => (
                  <li key={`${b.rule}-${i}`}>
                    {(tr ? BROKEN_RULE_TR[b.rule] : null) ?? b.rule}: {b.message}
                    {b.reason ? ` · “${b.reason}”` : ""}
                  </li>
                ))}
              </ul>
              <label className="flex min-h-11 items-center gap-2 text-label-1 pointer-fine:min-h-0">
                <Checkbox checked={forcedOk} onCheckedChange={(v) => setForcedOk(Boolean(v))} data-testid="publish-forced-ack" />
                {tr ? "Bu kural ihlallerini gördüm; gerekçeleriyle yayımla" : "I have seen these breaks; publish with their reasons"}
              </label>
            </div>
          ) : null}
          {refusals.length ? (
            <div role="alert" className="rounded-xl bg-status-infeasible px-3 py-2 type-callout text-status-infeasible-fg" data-testid="publish-refused">
              <p className="font-medium">{t("runs.publish.refused")}</p>
              <ul className="mt-1 list-disc pl-5">
                {refusals.map((x) => <li key={x}>{x}</li>)}
              </ul>
            </div>
          ) : null}
          {/* phones: "Yayınla" stays in reach while the sheet scrolls (MOBILE.md M-05, round-1 R1-S-16) */}
          <DialogFooter className="max-sm:sticky max-sm:bottom-0 max-sm:z-10">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={publish.isPending}>{t("common.cancel")}</Button>
            <BusyButton
              busy={publish.isPending}
              busyLabel={t("runs.publish.publishing")}
              disabled={blocked}
              onClick={() => publish.mutate({ scope: needsScope && scopeOk, forced: needsForced && forcedOk })}
              data-testid={reduction ? "publish-confirm-reduction" : "publish-confirm"}
            >
              {reduction ? (tr ? "Haftaları kaldırarak yayımla" : "Publish and remove those weeks") : t("runs.publish.confirm")}
            </BusyButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
