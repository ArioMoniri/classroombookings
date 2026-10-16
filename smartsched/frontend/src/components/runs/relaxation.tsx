"use client";
/**
 * Relaxation policy (backend `app/services/run_params.py`, `app/solver/policy.py`; owner decision 2026-10-15): who
 * gives way when not every class fits.
 *
 * - `lock_first` (default): locked rows first, then coordinator priority, then the most classes.
 * - `most_classes_first`: the most classes first, then coordinator priority, then locked rows.
 *
 * Per run: `POST /runs {params: {relaxation_policy}}` or studio generate (unset = the term's setting). Per term:
 * `GET/PUT /terms/{id}/relaxation-policy` (the settings key `term.<id>.relaxation_policy`, administrators). A finished run records what it
 * used in `stats.relaxation_policy {policy, source: run | term | default | invalid_setting}`.
 */
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";

export const POLICIES = ["lock_first", "most_classes_first"] as const;
export type Policy = (typeof POLICIES)[number];
/** the run form's choice: a policy, or "term" (send nothing; the term setting or the default decides) */
export type PolicyChoice = Policy | "term";
export type PolicySource = "run" | "term" | "default" | "invalid_setting";

export function isPolicy(v: unknown): v is Policy {
  return v === "lock_first" || v === "most_classes_first";
}

/** What a finished run used (`stats.relaxation_policy`), or null for runs before 2026-10-15 / imported runs. */
export function runPolicy(r: Pick<ScheduleRun, "stats_detail">): { policy: Policy; source: PolicySource } | null {
  const raw = r.stats_detail?.relaxation_policy;
  if (!raw || typeof raw !== "object") return null;
  const { policy, source } = raw as { policy?: unknown; source?: unknown };
  if (!isPolicy(policy)) return null;
  const src: PolicySource = source === "run" || source === "term" || source === "invalid_setting" ? source : "default";
  return { policy, source: src };
}

/** `params` of `POST /runs` for a choice: "term" sends nothing, so the term setting stays in charge. */
export function policyParams(choice: PolicyChoice): { relaxation_policy?: Policy } {
  return choice === "term" ? {} : { relaxation_policy: choice };
}

export function PolicyPicker({ id, value, onChange, withTerm = true, disabled }: { id: string; value: PolicyChoice | Policy | null; onChange: (v: PolicyChoice) => void; withTerm?: boolean; disabled?: boolean }) {
  const { t } = useI18n();
  const options = [
    ...(withTerm ? [{ value: "term" as const, label: t("relax.choice.term") }] : []),
    { value: "lock_first" as const, label: t("relax.choice.lock_first") },
    { value: "most_classes_first" as const, label: t("relax.choice.most_classes_first") },
  ].map((o) => ({ ...o, disabled, testId: `relax-${o.value}` }));
  return (
    <div className="grid gap-1.5">
      <span id={`${id}-label`} className="type-footnote font-semibold text-label-2">
        {t("relax.label")}
      </span>
      <SegmentedControl size="sm" semantics="radiogroup" aria-labelledby={`${id}-label`} aria-describedby={`${id}-desc`} value={value} onValueChange={onChange} options={options} data-testid={id} />
      <p id={`${id}-desc`} className="type-footnote text-label-2" data-testid={`${id}-desc`}>
        {value === null ? t("relax.unknown") : t(`relax.desc.${value}`)}
      </p>
    </div>
  );
}

/** One line for the run report: "Sığmayan dersler: önce kilitli satırlar (dönem ayarı)". */
export function RunPolicyLine({ r }: { r: Pick<ScheduleRun, "stats_detail"> }) {
  const { t } = useI18n();
  const p = runPolicy(r);
  if (!p) return null;
  return (
    <p className="type-footnote text-label-2" data-testid="run-relaxation-policy" data-policy={p.policy} data-source={p.source}>
      {t("relax.used", { policy: t(`relax.short.${p.policy}`), source: t(`relax.source.${p.source}`) })}
    </p>
  );
}
