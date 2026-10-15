"use client";

/**
 * Publish a finished run as the term's timetable (admin persona M-03: `POST /runs/{id}/activate` had no button).
 * The confirmation names what changes — the scope (weeks or the whole term), the run it replaces, a partial
 * run's missing classes and the report's exceptions — and the backend's publish guard decides: a 409 lists its
 * reasons, shown verbatim, and the dialog stays open.
 * 2026-10-15 contract: a 409 `scope_reduction` (the run covers fewer weeks than the published one) shows the
 * weeks that would leave the published timetable and needs an explicit confirm that resends
 * `confirm_scope_reduction: true`; a partial run needs a ticked confirmation that names the unplaced classes.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { BusyButton } from "@/components/ui/busy-label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { weekRanges } from "@/components/timetable/model/run-label";
import { HttpError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { qk } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { partialCounts } from "./runs-list";
import { sectionOf } from "./diagnosis-format";
import type { VerdictException } from "./run-truth";

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

export function PublishRunButton({ run, published, exceptions = [] }: { run: ScheduleRun; /** the term's published run of this kind, if another one */ published: number | null; exceptions?: VerdictException[] }) {
  const { t, n, locale } = useI18n();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [refusals, setRefusals] = useState<string[]>([]);
  const [reduction, setReduction] = useState<ReturnType<typeof scopeReductionOf>>(null);
  const [partialOk, setPartialOk] = useState(false);
  const tr = locale === "tr";
  const publish = useMutation({
    mutationFn: (confirmScopeReduction: boolean) => api.runs.activate(run.id, { confirmScopeReduction }),
    onSuccess: () => {
      setOpen(false);
      setReduction(null);
      toast.success(t("runs.publish.done", { id: run.id }));
    },
    onError: (e) => {
      const r = scopeReductionOf(e);
      if (r) {
        setReduction(r);
        setRefusals([]);
      } else setRefusals(publishRefusals(e));
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
  const blockedByPartial = Boolean(partial) && !partialOk;
  return (
    <>
      <Button size="sm" onClick={() => { setRefusals([]); setReduction(null); setPartialOk(false); setOpen(true); }} data-testid="run-publish">
        <Upload aria-hidden /> {t("runs.publish.button")}
      </Button>
      <Dialog open={open} onOpenChange={(o) => !publish.isPending && setOpen(o)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("runs.publish.title", { id: run.id })}</DialogTitle>
            <DialogDescription>{weeks.length ? t("runs.publish.scopeWeeks", { weeks: weekRanges(weeks), term: run.term_code }) : t("runs.publish.scopeTerm", { term: run.term_code })}</DialogDescription>
          </DialogHeader>
          <ul className="list-disc space-y-1 pl-5 type-callout text-label-1">
            <li>{published !== null ? t("runs.publish.replaces", { id: published }) : t("runs.publish.first")}</li>
            {weeks.length ? <li>{t("runs.publish.weeksOnly")}</li> : null}
            {partial ? <li className="text-status-warning-fg">{t("runs.publish.partial", { placed: n(partial.placed), total: n(partial.total), missing: n(partial.total - partial.placed) })}</li> : null}
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
              <label className="flex items-center gap-2 type-callout text-label-1">
                <Checkbox checked={partialOk} onCheckedChange={(v) => setPartialOk(Boolean(v))} data-testid="publish-partial-ack" />
                {tr ? "Eksik derslerle yayımlamayı onaylıyorum" : "I confirm publishing without these classes"}
              </label>
            </div>
          ) : null}
          {reduction ? (
            <div role="alert" className="grid gap-1 rounded-xl bg-status-warning px-3 py-2 type-callout text-status-warning-fg" data-testid="publish-scope-reduction">
              <p className="font-medium">
                {tr
                  ? `Bu çalıştırma daha az hafta kapsıyor: ${weekRanges(reduction.weeksLost)}. haftalar${reduction.activeId ? ` (#${reduction.activeId})` : ""} yayından kalkacak.`
                  : `This run covers fewer weeks: weeks ${weekRanges(reduction.weeksLost)}${reduction.activeId ? ` of #${reduction.activeId}` : ""} will leave the published timetable.`}
              </p>
              {reduction.message ? <p className="type-footnote text-label-1">{reduction.message}</p> : null}
            </div>
          ) : null}
          {refusals.length ? (
            <div role="alert" className="rounded-xl bg-status-infeasible px-3 py-2 type-callout text-status-infeasible-fg">
              <p className="font-medium">{t("runs.publish.refused")}</p>
              <ul className="mt-1 list-disc pl-5">
                {refusals.map((x) => <li key={x}>{x}</li>)}
              </ul>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={publish.isPending}>{t("common.cancel")}</Button>
            {reduction ? (
              <BusyButton busy={publish.isPending} busyLabel={t("runs.publish.publishing")} disabled={blockedByPartial} onClick={() => publish.mutate(true)} data-testid="publish-confirm-reduction">
                {tr ? "Haftaları kaldırarak yayımla" : "Publish and remove those weeks"}
              </BusyButton>
            ) : (
              <BusyButton busy={publish.isPending} busyLabel={t("runs.publish.publishing")} disabled={blockedByPartial} onClick={() => publish.mutate(false)} data-testid="publish-confirm">
                {t("runs.publish.confirm")}
              </BusyButton>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
