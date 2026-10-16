"use client";
/**
 * Settings › Çözücü › "Sığmayan dersler" for the active term: the term's relaxation policy, the settings key
 * `term.<id>.relaxation_policy` (`PUT /settings {extra}`; administrators, backend `app/api/v1/settings.py`).
 *
 * `GET /settings` does not list dotted keys, so the stored value cannot be read back. What the card shows instead is
 * what the term's newest run recorded (`stats.relaxation_policy`): when that run took the term setting (`source:
 * term`) or found none (`default`), the stored value at the time is known and preselected; otherwise the card says it
 * cannot tell. A value saved here is shown as saved for the rest of the session.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { request } from "@/lib/api/client";
import { useRuns } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PolicyPicker, runPolicy, type Policy } from "./relaxation";

export const termPolicyKey = (termId: number) => `term.${termId}.relaxation_policy`;

/** The newest finished run that says what the term setting was: `{policy, run}` (default = lock_first) or null. */
export function inferTermPolicy(runs: ScheduleRun[] | undefined): { policy: Policy; run: number; fromDefault: boolean } | null {
  for (const r of [...(runs ?? [])].sort((a, b) => b.id - a.id)) {
    const p = runPolicy(r);
    if (!p) continue;
    if (p.source === "term") return { policy: p.policy, run: r.id, fromDefault: false };
    if (p.source === "default") return { policy: "lock_first", run: r.id, fromDefault: true };
  }
  return null;
}

export function RelaxationTermCard() {
  const { term } = useActiveTerm();
  return term ? <TermPolicy key={term.id} termId={term.id} termCode={term.code} /> : null;
}

function TermPolicy({ termId, termCode }: { termId: number; termCode: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const runs = useRuns({ term_id: termId, limit: 100 });
  const savedKey = ["relax-term-saved", termId] as const;
  const saved = qc.getQueryData<Policy>(savedKey);
  const inferred = inferTermPolicy(runs.data);
  const [value, setValue] = useState<Policy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = value ?? saved ?? inferred?.policy ?? null;

  const save = async () => {
    if (!shown) return;
    setBusy(true);
    setError(null);
    try {
      await request("/settings", { method: "PUT", body: { extra: { [termPolicyKey(termId)]: shown } }, silent: true });
      qc.setQueryData(savedKey, shown);
      setValue(null);
      toast.success(t("relax.term.saved", { term: termCode }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card data-testid="relax-term-card">
      <CardHeader>
        <CardTitle>{t("relax.term.title", { term: termCode })}</CardTitle>
        <CardDescription>{t("relax.term.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <PolicyPicker id="relax-term" value={shown} onChange={(v) => v !== "term" && setValue(v)} withTerm={false} disabled={busy} />
        <p className="type-footnote text-label-2" data-testid="relax-term-known">
          {saved && !value
            ? t("relax.term.savedNow")
            : inferred
              ? inferred.fromDefault
                ? t("relax.term.fromDefault", { id: inferred.run })
                : t("relax.term.fromRun", { id: inferred.run })
              : runs.isLoading
                ? t("busy.loading")
                : t("relax.term.unknown")}
        </p>
        {error ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {error}
          </p>
        ) : null}
        <div>
          <Button size="sm" onClick={() => void save()} disabled={!shown || busy || (!value && !!saved)} aria-busy={busy || undefined} data-testid="relax-term-save">
            <BusyLabel busy={busy} label={t("busy.saving")}>{t("relax.term.save")}</BusyLabel>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
