"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CommitIn, CommitOut, CouncilJob } from "@/lib/api/council";
import { useI18n } from "@/lib/i18n/provider";
import { PlanTermFields } from "./review-panel";

/** Commit one planner term group (or every file) into a term; the planner's proposal is editable. */
export function CommitPanel({ job, blocking, busy, result, onCommit }: { job: CouncilJob; blocking: number; busy: boolean; result: CommitOut | null; onCommit: (body: CommitIn) => void }) {
  const { t } = useI18n();
  const groups = job.plan?.groups ?? [];
  const [group, setGroup] = useState(0);
  const g = groups[group];
  const [term, setTerm] = useState(() => ({ code: g?.code ?? "", name: g?.name ?? "", weekCount: g?.week_count ?? 14 }));
  const [includeRules, setIncludeRules] = useState(true);
  const names = new Map(job.files.map((f) => [f.index, f.filename]));
  const globalFiles = job.plan?.global_files ?? [];

  const pick = (i: number) => {
    setGroup(i);
    const ng = groups[i];
    if (ng) setTerm({ code: ng.code, name: ng.name, weekCount: ng.week_count });
  };

  return (
    <Card data-testid="onboarding-commit">
      <CardHeader>
        <CardTitle>{t("onboarding.commit")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("onboarding.commitHint")}</p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {groups.length ? (
          <fieldset className="space-y-1">
            <legend className="text-xs font-medium">{t("onboarding.group")}</legend>
            {groups.map((gr, i) => (
              <label key={gr.key} className="flex items-start gap-2">
                <input type="radio" name="term-group" checked={group === i} onChange={() => pick(i)} />
                <span>
                  <span className="font-medium">{gr.code}</span> · {gr.kind} · {t("onboarding.weeks", { count: gr.week_count })}
                  <span className="block text-xs text-muted-foreground">{[...gr.files, ...globalFiles].map((f) => names.get(f)).join(", ")}</span>
                </span>
              </label>
            ))}
          </fieldset>
        ) : (
          <p className="text-xs text-muted-foreground">{t("onboarding.noGroups")}</p>
        )}
        <PlanTermFields value={term} onChange={setTerm} />
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={includeRules} onChange={(e) => setIncludeRules(e.target.checked)} />
          {t("onboarding.includeRules")}
        </label>
        {blocking ? <p className="text-xs text-destructive">{t("onboarding.blockingBeforeCommit", { count: blocking })}</p> : null}
        <Button
          data-testid="onboarding-commit-button"
          disabled={busy || blocking > 0 || !term.code.trim()}
          onClick={() =>
            onCommit({
              ...(groups.length ? { group } : { files: job.files.map((f) => f.index) }),
              term: { code: term.code.trim(), name: term.name.trim() || term.code.trim(), week_count: term.weekCount },
              include_rules: includeRules,
            })
          }
        >
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t("onboarding.commitButton")}
        </Button>
        {result ? (
          <div className="rounded-lg border p-3" data-testid="onboarding-result" role="status">
            <p className="font-medium">{t("onboarding.committed", { code: result.term_code })}</p>
            <p className="text-xs text-muted-foreground">
              {Object.entries(result.general)
                .map(([k, v]) => `${k}: ${v}`)
                .join(" · ") || t("onboarding.fastOnly")}
            </p>
            <p className="text-xs text-muted-foreground">{t("onboarding.rulesCreated", { count: result.constraints_created.length })}</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
