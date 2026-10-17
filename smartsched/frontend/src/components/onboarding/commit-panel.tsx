"use client";
/**
 * Fark → Kaydet (phase19-intake I8, 2026-10-15 contract): "Farkı göster" runs POST commit {dry_run: true} — the
 * same writer in a rolled-back transaction — and lists create / update / unchanged / conflict per entity plus the
 * conflicting rows. A planner's correction that the file changed is kept or replaced by `on_conflict`
 * (keep | take), and the real commit sends the same choice. The term group and term fields stay editable.
 *
 * T-R1-24: "Yaz" never writes on the first press. It opens a confirm with the dry run's counts ("2026-BAHAR
 * dönemine 1.527 yeni talep yazılacak", per record type in Turkish) and says the commit cannot be undone; the
 * result is a Turkish summary (no raw keys) whose rule count is every constraint the commit wrote.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { BusyButton, BusyGlyph } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { councilApi, type BaselineTarget, type CommitDryRun, type CommitIn, type CommitOut, type CouncilJob } from "@/lib/api/council";
import { problemText } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";
import { BaselinePreview, BaselineResult, BaselineTargetPicker, hasScheduleMap, targetReady } from "./baseline-summary";
import { useOnboardingCopy } from "./copy";
import { PlanTermFields } from "./review-panel";

export function CommitPanel({ job, blocking, busy, result, onCommit }: { job: CouncilJob; blocking: number; busy: boolean; result: CommitOut | null; onCommit: (body: CommitIn) => void }) {
  const { t, n, locale } = useI18n();
  const c = useOnboardingCopy();
  const groups = job.plan?.groups ?? [];
  const [group, setGroup] = useState(0);
  const g = groups[group];
  const [term, setTerm] = useState(() => ({ code: g?.code ?? "", name: g?.name ?? "", weekCount: g?.week_count ?? 14 }));
  const [includeRules, setIncludeRules] = useState(true);
  const [onConflict, setOnConflict] = useState<"keep" | "take">("keep");
  const [baseline, setBaseline] = useState<BaselineTarget>({ mode: "auto" });
  const [diff, setDiff] = useState<CommitDryRun | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const names = new Map(job.files.map((f) => [f.index, f.filename]));
  const globalFiles = job.plan?.global_files ?? [];

  const pick = (i: number) => {
    setGroup(i);
    setDiff(null);
    if (baseline.mode === "run") setBaseline({ mode: "auto" }); // a run of another term
    const ng = groups[i];
    if (ng) setTerm({ code: ng.code, name: ng.name, weekCount: ng.week_count });
  };
  const body = (): CommitIn => ({
    ...(groups.length ? { group } : { files: job.files.map((f) => f.index) }),
    term: { code: term.code.trim(), name: term.name.trim() || term.code.trim(), week_count: term.weekCount },
    include_rules: includeRules,
    on_conflict: onConflict,
    // auto (the term's baseline run) is the backend default: sent only for a schedule map
    ...(hasScheduleMap(job) ? { baseline } : {}),
  });
  const runDiff = async (): Promise<CommitDryRun | null> => {
    setDiffBusy(true);
    setDiffError(null);
    try {
      const d = await councilApi.dryRun(job.id, body());
      setDiff(d);
      return d;
    } catch (e) {
      setDiffError(problemText(e, locale) ?? (e instanceof Error ? e.message : String(e)));
      return null;
    } finally {
      setDiffBusy(false);
    }
  };
  // Yaz: the dry run's counts first (run it now when Fark was not shown), then a confirm, then the commit
  const askWrite = async () => {
    if (diff || (await runDiff())) setConfirming(true);
  };
  const label = (entity: string) => c.entity[entity] ?? entity.replace(/_/g, " ");
  const changed = (counts: Record<string, { create: number; update: number }> | null | undefined) =>
    Object.entries(counts ?? {}).filter(([, v]) => v.create || v.update);
  const disabled = busy || blocking > 0 || !term.code.trim() || !targetReady(baseline);

  return (
    <Card data-testid="onboarding-commit">
      <CardHeader>
        <CardTitle>{t("onboarding.commit")}</CardTitle>
        <p className="type-callout text-label-2">{t("onboarding.commitHint")}</p>
      </CardHeader>
      <CardContent className="grid max-w-3xl gap-4 type-callout">
        {groups.length ? (
          <fieldset className="grid min-w-0 gap-1.5">
            <legend className="mb-1 type-footnote font-semibold text-label-2">{t("onboarding.group")}</legend>
            {groups.map((gr, i) => (
              <label key={gr.key} className="flex items-start gap-2">
                <input type="radio" name="term-group" className="mt-1 accent-(--accent)" checked={group === i} onChange={() => pick(i)} />
                <span className="min-w-0">
                  <span className="font-medium text-label-1">{gr.code}</span> · {c.termKind[gr.kind] ?? gr.kind} · {t("onboarding.weeks", { count: gr.week_count })}
                  <span className="block truncate type-footnote text-label-2">{[...gr.files, ...globalFiles].map((f) => names.get(f)).join(", ")}</span>
                </span>
              </label>
            ))}
          </fieldset>
        ) : (
          <p className="type-footnote text-label-2">{t("onboarding.noGroups")}</p>
        )}
        <PlanTermFields value={term} onChange={(v) => { if (v.code !== term.code && baseline.mode === "run") setBaseline({ mode: "auto" }); setTerm(v); setDiff(null); }} />
        <label className="flex items-center gap-2 text-label-1">
          <Checkbox checked={includeRules} onCheckedChange={(v) => { setIncludeRules(Boolean(v)); setDiff(null); }} />
          {t("onboarding.includeRules")}
        </label>
        <div className="grid gap-1.5">
          <span className="type-footnote font-semibold text-label-2" id={`onc-${job.id}`}>{c.onConflict}</span>
          <SegmentedControl
            size="sm"
            semantics="radiogroup"
            aria-labelledby={`onc-${job.id}`}
            value={onConflict}
            onValueChange={(v) => { setOnConflict(v); setDiff(null); }}
            options={[{ value: "keep", label: c.keep }, { value: "take", label: c.take }]}
          />
        </div>
        {/* where the schedule map goes (P19-I5): the term's baseline run, another run of the term, or nowhere */}
        {!result ? <BaselineTargetPicker job={job} termCode={term.code} value={baseline} onChange={(v) => { setBaseline(v); setDiff(null); }} /> : null}
        {blocking ? <p className="type-footnote text-status-infeasible-fg">{t("onboarding.blockingBeforeCommit", { count: blocking })}</p> : null}
        {/* Fark: the dry run says which run the map goes to and what it would write */}
        {!result ? <BaselinePreview job={job} termCode={term.code} baseline={diff?.result.baseline_run} diffDone={!!diff} /> : null}

        {/* ④ Fark */}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" disabled={disabled || diffBusy} onClick={() => void runDiff()} data-testid="onboarding-diff-button">
            {diffBusy ? <BusyGlyph /> : null}
            {c.diff}
          </Button>
          {/* ⑤ Kaydet */}
          <BusyButton busy={busy || diffBusy} busyLabel={diffBusy ? c.commitPreparing : t("onboarding.commitButton")} data-testid="onboarding-commit-button" disabled={disabled || diffBusy} onClick={() => void askWrite()}>
            {t("onboarding.commitButton")}
          </BusyButton>
        </div>
        {diffError ? <p role="alert" className="type-callout text-status-infeasible-fg">{diffError}</p> : null}
        {diff ? (
          <section aria-labelledby={`diff-${job.id}`} className="grid gap-2 rounded-lg bg-fill-3 p-3 edge-hairline" data-testid="onboarding-diff">
            <h3 id={`diff-${job.id}`} className="type-headline text-label-1">{c.diffTitle}</h3>
            <p className="type-footnote text-label-2">{c.diffHint}</p>
            <div className="overflow-x-auto">
              <table className="w-full type-callout">
                <thead>
                  <tr className="text-left type-footnote text-label-2 edge-hairline-b">
                    <th scope="col" className="py-1.5 pr-2 font-semibold">{c.diffCols.entity}</th>
                    {(["create", "update", "unchanged", "conflict"] as const).map((k) => (
                      <th key={k} scope="col" className="px-2 py-1.5 text-right font-semibold">{c.diffCols[k]}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(diff.counts).map(([entity, v]) => (
                    <tr key={entity} className="edge-hairline-b">
                      <th scope="row" className="py-1.5 pr-2 text-left font-normal text-label-1" data-entity={entity}>{label(entity)}</th>
                      <td className="px-2 text-right">{n(v.create)}</td>
                      <td className="px-2 text-right">{n(v.update)}</td>
                      <td className="px-2 text-right">{n(v.unchanged)}</td>
                      <td className={v.conflict ? "px-2 text-right font-semibold text-status-warning-fg" : "px-2 text-right"}>{n(v.conflict)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {diff.conflicts_total ? (
              <details>
                <summary className="cursor-pointer type-callout font-medium text-status-warning-fg">{c.conflictRows(diff.conflicts_total)}</summary>
                <ul className="mt-1 grid gap-1 type-footnote">
                  {diff.rows
                    .filter((r) => r.change === "conflict")
                    .slice(0, 50)
                    .map((r, i) => (
                      <li key={i} className="text-label-1">
                        <span className="font-medium">{String(r.key ?? r.id ?? "")}</span>{" "}
                        <span className="text-label-2">
                          {(Array.isArray(r.conflicts) ? (r.conflicts as Record<string, unknown>[]) : [])
                            .map((x) => `${String(x.field)}: ${String(x.planner)} ↔ ${String(x.file)}`)
                            .join("; ")}
                        </span>
                      </li>
                    ))}
                </ul>
              </details>
            ) : null}
          </section>
        ) : null}
        {result ? (
          <div className="rounded-lg p-3 edge-hairline" data-testid="onboarding-result" role="status">
            <p className="font-medium text-label-1">{t("onboarding.committed", { code: result.term_code })}</p>
            {changed(result.changes).length ? (
              <ul className="type-footnote text-label-2">
                {changed(result.changes).map(([entity, v]) => (
                  <li key={entity} data-entity={entity}>{c.resultLine(label(entity), n(v.create), n(v.update))}</li>
                ))}
              </ul>
            ) : Object.keys(result.general).some((k) => k in c.entity) ? (
              // an answer without `changes` (older backends): the writer's own per-entity counts
              <ul className="type-footnote text-label-2">
                {Object.entries(result.general)
                  .filter(([k]) => k in c.entity)
                  .map(([k, v]) => (
                    <li key={k} data-entity={k}>{`${label(k)}: ${n(v)}`}</li>
                  ))}
              </ul>
            ) : (
              <p className="type-footnote text-label-2">{t("onboarding.fastOnly")}</p>
            )}
            {[
              result.general.merges_applied ? c.merges(n(result.general.merges_applied)) : null,
              result.general.duplicates_skipped ? c.duplicatesSkipped(n(result.general.duplicates_skipped)) : null,
              result.general.rows_rejected ? c.rowsRejected(n(result.general.rows_rejected)) : null,
              result.general.rows_edited ? c.rowsEdited(n(result.general.rows_edited)) : null,
            ]
              .filter(Boolean)
              .map((line) => (
                <p key={line} className="type-footnote text-label-2">{line}</p>
              ))}
            <p className="type-footnote text-label-2" data-testid="onboarding-result-rules">{t("onboarding.rulesCreated", { count: result.constraints_total ?? result.constraints_created.length })}</p>
          </div>
        ) : null}
        <Dialog open={confirming} onOpenChange={(o) => !busy && setConfirming(o)}>
          <DialogContent className="sm:max-w-md" data-testid="onboarding-commit-confirm">
            <DialogHeader>
              <DialogTitle>{c.commitConfirmTitle(term.code.trim())}</DialogTitle>
              <DialogDescription>{c.commitConfirmLead(term.code.trim(), n(diff?.counts.meeting_requests?.create ?? 0))}</DialogDescription>
            </DialogHeader>
            <ul className="grid gap-1 type-callout" data-testid="onboarding-commit-confirm-counts">
              {changed(diff?.counts).map(([entity, v]) => (
                <li key={entity} className="flex justify-between gap-3" data-entity={entity}>
                  <span className="text-label-1">{label(entity)}</span>
                  <span className="text-label-2 tnum">{c.commitConfirmCounts(n(v.create), n(v.update))}</span>
                </li>
              ))}
            </ul>
            <p className="type-footnote font-medium text-status-warning-fg" data-testid="onboarding-commit-irreversible">{c.commitIrreversible}</p>
            <DialogFooter>
              <Button variant="outline" disabled={busy} onClick={() => setConfirming(false)}>{c.cancel}</Button>
              <BusyButton
                busy={busy}
                busyLabel={c.commitWrite}
                data-testid="onboarding-commit-confirm-button"
                onClick={() => {
                  setConfirming(false);
                  onCommit(body());
                }}
              >
                {c.commitWrite}
              </BusyButton>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        {result?.baseline_run ? <BaselineResult baseline={result.baseline_run} /> : null}
      </CardContent>
    </Card>
  );
}
