"use client";
/**
 * "Bu çalıştırmayı koruyarak yeniden çöz": a new solve whose parent is this run (`POST /runs` with `parent_run_id` and
 * `params.stability`), so classes stay where this run has them unless a rule or a clash moves them. For the term's
 * baseline import run (schedule map, P19-I5) this is the re-solve that keeps the published board. The dialog also
 * carries the run's relaxation policy (relaxation.tsx). Opens by itself on `/runs/{id}?resolve=1` (the onboarding
 * Kaydet step links there).
 */
import { RefreshCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ResponsiveDialog } from "@/components/approvals/responsive-dialog";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateRun } from "@/lib/api/hooks";
import type { RunCreate, ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { isBaselineRun } from "@/lib/api/council";
import { PolicyPicker, policyParams, type PolicyChoice } from "./relaxation";

/** The `POST /runs` body of a re-solve that keeps `r` (same term, kind and horizon; `r` is the parent). */
export function resolveBody(r: Pick<ScheduleRun, "id" | "term_id" | "kind" | "horizon" | "horizon_params">, choice: PolicyChoice, label: string): RunCreate {
  const weeks = r.horizon_params.weeks;
  return {
    term_id: r.term_id,
    kind: r.kind,
    horizon: r.horizon,
    ...(weeks.length ? { horizon_params: { weeks } } : {}),
    parent_run_id: r.id,
    params: { stability: true, ...policyParams(choice) },
    ...(label.trim() ? { label: label.trim() } : {}),
  };
}

export function ResolveRunButton({ run, autoOpen = false }: { run: ScheduleRun; autoOpen?: boolean }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const create = useCreateRun();
  // `/runs/{id}?resolve=1` (the onboarding Kaydet link) opens the dialog with the page
  const [open, setOpen] = useState(autoOpen);
  const [choice, setChoice] = useState<PolicyChoice>("term");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const baseline = isBaselineRun(run);

  const start = () => {
    setError(null);
    create.mutate(resolveBody(run, choice, label), {
      onSuccess: (res) => {
        setOpen(false);
        toast.success(t("resolveRun.started", { id: res.run_id }));
        router.push(`/runs/${res.run_id}`);
      },
      onError: (e) => setError(e instanceof Error ? e.message : String(e)),
    });
  };
  const title = baseline ? t("resolveRun.titleBaseline") : t("resolveRun.title");
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} data-testid="resolve-run-open">
        <RefreshCcw aria-hidden />
        {baseline ? t("resolveRun.openBaseline") : t("resolveRun.open")}
      </Button>
      <ResponsiveDialog
        open={open}
        onOpenChange={(o) => !create.isPending && setOpen(o)}
        title={title}
        description={t(baseline ? "resolveRun.leadBaseline" : "resolveRun.lead", { id: run.id })}
        testId="resolve-run"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={create.isPending}>
              {t("crbs.common.cancel")}
            </Button>
            <Button onClick={start} disabled={create.isPending} aria-busy={create.isPending || undefined} data-testid="resolve-run-start">
              <BusyLabel busy={create.isPending} label={t("busy.working")}>{t("resolveRun.start")}</BusyLabel>
            </Button>
          </>
        }
      >
        <PolicyPicker id="resolve-relax" value={choice} onChange={setChoice} />
        <div className="grid gap-1.5">
          <Label htmlFor="resolve-label">{t("resolveRun.label")}</Label>
          <Input id="resolve-label" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={255} placeholder={t("resolveRun.labelPlaceholder", { id: run.id })} lang={locale} />
        </div>
        {error ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {error}
          </p>
        ) : null}
      </ResponsiveDialog>
    </>
  );
}
