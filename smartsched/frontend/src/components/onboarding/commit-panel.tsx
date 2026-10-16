"use client";
/**
 * Fark → Kaydet (phase19-intake I8, 2026-10-15 contract): "Farkı göster" runs POST commit {dry_run: true} — the
 * same writer in a rolled-back transaction — and lists create / update / unchanged / conflict per entity plus the
 * conflicting rows. A planner's correction that the file changed is kept or replaced by `on_conflict`
 * (keep | take), and the real commit sends the same choice. The term group and term fields stay editable.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { BusyButton, BusyGlyph } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { councilApi, type BaselineTarget, type CommitDryRun, type CommitIn, type CommitOut, type CouncilJob } from "@/lib/api/council";
import { useI18n } from "@/lib/i18n/provider";
import { BaselinePreview, BaselineResult, BaselineTargetPicker, hasScheduleMap, targetReady } from "./baseline-summary";
import { useOnboardingCopy } from "./copy";
import { PlanTermFields } from "./review-panel";

export function CommitPanel({ job, blocking, busy, result, onCommit }: { job: CouncilJob; blocking: number; busy: boolean; result: CommitOut | null; onCommit: (body: CommitIn) => void }) {
  const { t, n } = useI18n();
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
  const runDiff = async () => {
    setDiffBusy(true);
    setDiffError(null);
    try {
      setDiff(await councilApi.dryRun(job.id, body()));
    } catch (e) {
      setDiffError(e instanceof Error ? e.message : String(e));
    } finally {
      setDiffBusy(false);
    }
  };
  const disabled = busy || blocking > 0 || !term.code.trim() || !targetReady(baseline);

  return (
    <Card data-testid="onboarding-commit">
      <CardHeader>
        <CardTitle>{t("onboarding.commit")}</CardTitle>
        <p className="type-callout text-label-2">{t("onboarding.commitHint")}</p>
      </CardHeader>
      <CardContent className="grid max-w-3xl gap-4 type-callout">
        {groups.length ? (
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 type-footnote font-semibold text-label-2">{t("onboarding.group")}</legend>
            {groups.map((gr, i) => (
              <label key={gr.key} className="flex items-start gap-2">
                <input type="radio" name="term-group" className="mt-1 accent-(--accent)" checked={group === i} onChange={() => pick(i)} />
                <span className="min-w-0">
                  <span className="font-medium text-label-1">{gr.code}</span> · {gr.kind} · {t("onboarding.weeks", { count: gr.week_count })}
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
          <BusyButton busy={busy} busyLabel={t("onboarding.commitButton")} data-testid="onboarding-commit-button" disabled={disabled} onClick={() => onCommit(body())}>
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
                      <th scope="row" className="py-1.5 pr-2 text-left font-normal text-label-1">{entity}</th>
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
            <p className="type-footnote text-label-2">
              {Object.entries(result.general)
                .map(([k, v]) => `${k}: ${v}`)
                .join(" · ") || t("onboarding.fastOnly")}
            </p>
            <p className="type-footnote text-label-2">{t("onboarding.rulesCreated", { count: result.constraints_created.length })}</p>
          </div>
        ) : null}
        {result?.baseline_run ? <BaselineResult baseline={result.baseline_run} /> : null}
      </CardContent>
    </Card>
  );
}
