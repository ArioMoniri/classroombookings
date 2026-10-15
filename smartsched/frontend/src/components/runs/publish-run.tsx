"use client";

/**
 * Publish a finished run as the term's timetable (admin persona M-03: `POST /runs/{id}/activate` had no button).
 * The confirmation names what changes — the scope (weeks or the whole term), the run it replaces, a partial
 * run's missing classes and the report's exceptions — and the backend's publish guard decides: a 409 lists its
 * reasons, shown verbatim, and the dialog stays open.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyButton } from "@/components/ui/busy-label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { weekRanges } from "@/components/timetable/model/run-label";
import { HttpError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { qk } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { partialCounts } from "./runs-list";
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

export function PublishRunButton({ run, published, exceptions = [] }: { run: ScheduleRun; /** the term's published run of this kind, if another one */ published: number | null; exceptions?: VerdictException[] }) {
  const { t, n } = useI18n();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [refusals, setRefusals] = useState<string[]>([]);
  const publish = useMutation({
    mutationFn: () => api.runs.activate(run.id),
    onSuccess: () => {
      setOpen(false);
      toast.success(t("runs.publish.done", { id: run.id }));
    },
    onError: (e) => setRefusals(publishRefusals(e)),
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
  return (
    <>
      <Button size="sm" onClick={() => { setRefusals([]); setOpen(true); }} data-testid="run-publish">
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
            <BusyButton busy={publish.isPending} busyLabel={t("runs.publish.publishing")} onClick={() => publish.mutate()} data-testid="publish-confirm">
              {t("runs.publish.confirm")}
            </BusyButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
