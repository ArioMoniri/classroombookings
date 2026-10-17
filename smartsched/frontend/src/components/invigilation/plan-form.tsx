"use client";
/**
 * The run form of an invigilation plan: the rules a planner usually sets are visible with their defaults
 * (students per invigilator 40, at least 1 per room, at most 3 duties a day, own exam "prefer", the exam
 * instructors as the pool); the solver knobs (rest between duties, time budget, seed, objective weights) sit in a
 * collapsed "Gelişmiş" part. A re-run starts from the parent plan's parameters and keeps its locked duties.
 * Only the values that differ from the defaults are sent (`changedParams`).
 */
import { ChevronDown, RotateCcw } from "lucide-react";
import { useId, useState } from "react";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { errorText } from "@/lib/api/analytics";
import { changedParams, PLAN_DEFAULTS, paramsFrom, useCreatePlan, useRerunPlan, WEIGHT_KEYS, type InstructorPool, type OwnExam, type PlanBrief, type WeightKey } from "@/lib/api/invigilation";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

type Values = typeof PLAN_DEFAULTS;
type NumKey = "students_per_invigilator" | "min_per_room" | "max_per_day" | "min_rest" | "time_limit_s" | "seed";
const BOUNDS: Record<NumKey | "max_per_room", [number, number]> = {
  students_per_invigilator: [1, 1000],
  min_per_room: [0, 20],
  max_per_room: [1, 50],
  max_per_day: [1, 12],
  min_rest: [0, 6],
  time_limit_s: [1, 600],
  seed: [0, 2 ** 31 - 1],
};

export function validateParams(v: Values): Partial<Record<NumKey | "max_per_room" | WeightKey, true>> {
  const bad: Partial<Record<NumKey | "max_per_room" | WeightKey, true>> = {};
  for (const k of Object.keys(BOUNDS) as (NumKey | "max_per_room")[]) {
    const x = v[k];
    if (k === "max_per_room" && x === null) continue;
    const [lo, hi] = BOUNDS[k];
    if (typeof x !== "number" || !Number.isFinite(x) || x < lo || x > hi || (k !== "time_limit_s" && !Number.isInteger(x))) bad[k] = true;
  }
  if (v.max_per_room !== null && v.max_per_room < v.min_per_room) bad.max_per_room = true;
  for (const k of WEIGHT_KEYS) if (!Number.isInteger(v.weights[k]) || v.weights[k] < 0 || v.weights[k] > 1000) bad[k] = true;
  return bad;
}

export function PlanFormDialog({ open, mode, onOpenChange, examRunId, parent, onStarted }: { open: boolean; mode: "new" | "rerun"; onOpenChange: (v: boolean) => void; examRunId: number; parent: PlanBrief | null; onStarted: (planId: number) => void }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const id = useId();
  const rerun = mode === "rerun" && parent !== null;
  const start = () => (rerun ? paramsFrom(parent.params) : paramsFrom(null));
  const [v, setV] = useState<Values>(start);
  const [label, setLabel] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [tried, setTried] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // reset when the dialog opens for another mode or parent (state adjusted during render, no effect)
  const sig = `${open}|${mode}|${parent?.id ?? 0}`;
  const [seen, setSeen] = useState(sig);
  if (seen !== sig) {
    setSeen(sig);
    if (open) {
      setV(start());
      setLabel("");
      setTried(false);
      setError(null);
    }
  }
  const create = useCreatePlan();
  const rerunM = useRerunPlan();
  const busy = create.isPending || rerunM.isPending;
  const bad = validateParams(v);
  const invalid = Object.keys(bad).length > 0;

  const num = (k: NumKey, value: string) => setV((s) => ({ ...s, [k]: value === "" ? Number.NaN : Number(value) }));
  const field = (k: NumKey | "max_per_room", labelKey: Parameters<typeof t>[0], hintKey: Parameters<typeof t>[0], opts: { step?: string; placeholder?: string } = {}) => {
    const value = v[k];
    const err = tried && bad[k];
    return (
      <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-${k}`}>
        <span className="type-footnote font-medium text-label-1">{t(labelKey)}</span>
        <Input
          id={`${id}-${k}`}
          type="number"
          inputMode={opts.step ? "decimal" : "numeric"}
          step={opts.step ?? "1"}
          min={BOUNDS[k][0]}
          max={BOUNDS[k][1]}
          placeholder={opts.placeholder}
          value={value === null || Number.isNaN(value) ? "" : String(value)}
          aria-invalid={err || undefined}
          aria-describedby={`${id}-${k}-hint`}
          onChange={(e) => (k === "max_per_room" ? setV((s) => ({ ...s, max_per_room: e.target.value === "" ? null : Number(e.target.value) })) : num(k, e.target.value))}
          data-testid={`invig-param-${k}`}
        />
        <span id={`${id}-${k}-hint`} className={cn("type-caption", err ? "text-status-infeasible-fg" : "text-label-2")}>
          {err ? t("invigilation.form.range", { lo: BOUNDS[k][0], hi: BOUNDS[k][1] }) : t(hintKey)}
        </span>
      </label>
    );
  };

  const submit = async () => {
    setTried(true);
    setError(null);
    if (invalid) return;
    const params = changedParams(v);
    try {
      const res = rerun ? await rerunM.mutateAsync({ id: parent.id, label: label.trim() || undefined, params }) : await create.mutateAsync({ exam_run_id: examRunId, label: label.trim() || undefined, params });
      onOpenChange(false);
      onStarted(res.plan_id);
    } catch (e) {
      setError(errorText(e, lang));
    }
  };

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title={rerun ? t("invigilation.form.rerunTitle", { id: parent.id }) : t("invigilation.form.title")}
      description={rerun ? t("invigilation.form.rerunBody") : t("invigilation.form.body")}
      className="sm:max-w-2xl"
      testId="invig-form"
      footer={
        <>
          <Button variant="ghost" className="max-md:h-11" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <BusyButton busy={busy} busyLabel={t("invigilation.form.starting")} className="max-md:h-11" onClick={() => void submit()} data-testid="invig-form-submit">
            {rerun ? t("invigilation.form.rerun") : t("invigilation.form.run")}
          </BusyButton>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        noValidate
      >
        <label className="flex flex-col gap-1" htmlFor={`${id}-label`}>
          <span className="type-footnote font-medium text-label-1">{t("invigilation.form.label")}</span>
          <Input id={`${id}-label`} maxLength={255} value={label} placeholder={t("invigilation.form.labelPlaceholder")} onChange={(e) => setLabel(e.target.value)} data-testid="invig-param-label" />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          {field("students_per_invigilator", "invigilation.form.students", "invigilation.form.studentsHint")}
          {field("max_per_day", "invigilation.form.maxPerDay", "invigilation.form.maxPerDayHint")}
          {field("min_per_room", "invigilation.form.minPerRoom", "invigilation.form.minPerRoomHint")}
          {field("max_per_room", "invigilation.form.maxPerRoom", "invigilation.form.maxPerRoomHint", { placeholder: t("invigilation.form.noLimit") })}
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="type-footnote font-medium text-label-1" id={`${id}-own`}>{t("invigilation.form.ownExam")}</span>
          <SegmentedControl<OwnExam>
            semantics="radiogroup"
            aria-labelledby={`${id}-own`}
            options={(["prefer", "allow", "forbid"] as const).map((o) => ({ value: o, label: t(`invigilation.own.${o}`), testId: `invig-own-${o}` }))}
            value={v.own_exam}
            onValueChange={(o) => setV((s) => ({ ...s, own_exam: o }))}
            fill
          />
          <span className="type-caption text-label-2">{t(`invigilation.ownHint.${v.own_exam}`)}</span>
        </div>
        <label className="flex flex-col gap-1" htmlFor={`${id}-pool`}>
          <span className="type-footnote font-medium text-label-1">{t("invigilation.form.pool")}</span>
          <NativeSelect id={`${id}-pool`} value={v.instructor_pool} onChange={(e) => setV((s) => ({ ...s, instructor_pool: e.target.value as InstructorPool }))} data-testid="invig-param-pool">
            {(["exam_instructors", "all", "none"] as const).map((o) => (
              <option key={o} value={o}>{t(`invigilation.poolOpt.${o}`)}</option>
            ))}
          </NativeSelect>
          <span className="type-caption text-label-2">{t("invigilation.form.poolHint")}</span>
        </label>
        <div className="flex flex-col gap-3 rounded-xl bg-fill-3 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="ghost" size="sm" className="max-md:h-11" aria-expanded={advanced} aria-controls={`${id}-adv`} onClick={() => setAdvanced((a) => !a)} data-testid="invig-advanced">
              <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast)", advanced && "rotate-180")} />
              {t("invigilation.form.advanced")}
            </Button>
            <Button variant="ghost" size="sm" className="max-md:h-11" onClick={() => setV(paramsFrom(null))} data-testid="invig-defaults">
              <RotateCcw aria-hidden />
              {t("invigilation.form.defaults")}
            </Button>
          </div>
          {advanced ? (
            <div id={`${id}-adv`} className="flex flex-col gap-3">
              <div className="grid gap-3 sm:grid-cols-3">
                {field("min_rest", "invigilation.form.minRest", "invigilation.form.minRestHint")}
                {field("time_limit_s", "invigilation.form.timeLimit", "invigilation.form.timeLimitHint", { step: "1" })}
                {field("seed", "invigilation.form.seed", "invigilation.form.seedHint")}
              </div>
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-1 type-footnote font-medium text-label-1">{t("invigilation.form.weights")}</legend>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                  {WEIGHT_KEYS.map((k) => (
                    <label key={k} className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-w-${k}`}>
                      <span className="truncate type-caption text-label-1" title={t(`invigilation.weight.${k}`)}>{t(`invigilation.weight.${k}`)}</span>
                      <Input
                        id={`${id}-w-${k}`}
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={1000}
                        fieldSize="sm"
                        value={Number.isNaN(v.weights[k]) ? "" : String(v.weights[k])}
                        aria-invalid={(tried && bad[k]) || undefined}
                        onChange={(e) => setV((s) => ({ ...s, weights: { ...s.weights, [k]: e.target.value === "" ? Number.NaN : Number(e.target.value) } }))}
                        data-testid={`invig-weight-${k}`}
                      />
                    </label>
                  ))}
                </div>
                <span className="type-caption text-label-2">{t("invigilation.form.weightsHint")}</span>
              </fieldset>
            </div>
          ) : (
            <p className="type-caption text-label-2">
              {t("invigilation.form.advancedSummary", { rest: v.min_rest, limit: v.time_limit_s, seed: v.seed })}
            </p>
          )}
        </div>
        {tried && invalid ? <Alert tone="error">{t("invigilation.form.fix")}</Alert> : null}
        {error ? <Alert tone="error" data-testid="invig-form-error">{error}</Alert> : null}
      </form>
    </ResponsiveDialog>
  );
}
