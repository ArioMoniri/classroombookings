"use client";

import { Loader2, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import type { MessageKey } from "@/lib/i18n";
import { useSettingsPeek } from "@/lib/api/studio-hooks";
import { useI18n } from "@/lib/i18n/provider";
import { useEstimateText } from "./check-step";
import { RunCard, RunHistory } from "./run-cards";
import { compactRange } from "./rule-sentence";
import { useStudio, useStudioStore } from "./studio-context";
import { useGenerate } from "./use-generate";

const WEIGHT_KINDS = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;

/** The plain-language "What will happen" paragraph (TR/EN), built from the live summary. */
export function useHumanSummary(): string {
  const { t, n } = useI18n();
  const { summary } = useStudio();
  const est = useEstimateText();
  const parts = [
    t("studio.summary.h.place", { n: n(summary.classesIn), rooms: n(summary.rooms), weeks: compactRange(summary.weeks) || "—" }),
    t("studio.summary.h.rules", { must: n(summary.must), try: n(summary.tryTo) }),
    summary.pinned ? t("studio.summary.h.pinned", { n: n(summary.pinned) }) : "",
    summary.classesOut ? t("studio.summary.h.out", { n: n(summary.classesOut) }) : "",
    summary.stability && summary.lastGoodRunId ? t("studio.summary.h.stable", { id: summary.lastGoodRunId }) : "",
    summary.estimate ? t("studio.summary.h.time", { words: est(summary.estimate) }) : "",
  ];
  return parts.filter(Boolean).join(" ");
}

export function GenerateButton({ className, size = "lg", testId = "studio-generate" }: { className?: string; size?: "lg" | "default" | "sm"; testId?: string }) {
  const { t } = useI18n();
  const { generate, busy } = useGenerate();
  const active = useStudioStore((s) => s.activeRun);
  return (
    <Button size={size} className={className} onClick={() => void generate()} disabled={busy} data-testid={testId} aria-keyshortcuts="Meta+Enter Control+Enter">
      {busy ? <Loader2 className="animate-spin" aria-hidden /> : <PlayCircle aria-hidden />}
      {busy ? t("studio.run.preparing") : active ? t("studio.run.again") : t("studio.run.generate")}
    </Button>
  );
}

export function KeepSmallToggle() {
  const { t } = useI18n();
  const { summary, local, dispatch } = useStudio();
  if (!summary.lastGoodRunId) return null;
  const on = local.params.stability !== false;
  return (
    <label className="flex items-start gap-2.5 text-sm">
      <Switch checked={on} onCheckedChange={(v) => dispatch({ type: "setParams", params: { stability: v } })} className="mt-0.5" data-testid="keep-small" />
      <span>
        {t("studio.run.keepSmall", { id: summary.lastGoodRunId })}
        <span className="block text-xs text-label-2">{t("studio.run.keepSmallHelp")}</span>
      </span>
    </label>
  );
}

export function GenerateStep() {
  const { t } = useI18n();
  const { local, dispatch, advanced } = useStudio();
  const settings = useSettingsPeek();
  const human = useHumanSummary();
  const active = useStudioStore((s) => s.activeRun);
  const weights = local.params.weights ?? settings.data?.default_weights ?? {};
  return (
    <div className="space-y-5" data-testid="generate-step">
      {active ? <RunCard /> : null}
      <section className="space-y-4 rounded-xl border bg-card p-4" aria-labelledby="before-title">
        <h3 id="before-title" className="text-base font-semibold">
          {t("studio.run.before")}
        </h3>
        <p className="text-sm" data-testid="human-summary">
          {human}
        </p>
        <KeepSmallToggle />
        <div className="grid max-w-md gap-1.5">
          <Label htmlFor="run-label">{t("studio.run.label")}</Label>
          <Input id="run-label" value={(local.params.label as string | undefined) ?? ""} onChange={(e) => dispatch({ type: "setParams", params: { label: e.target.value } })} placeholder={t("studio.run.labelPlaceholder")} />
        </div>
        {advanced ? (
          <div className="space-y-4 rounded-lg border border-dashed p-3" data-testid="advanced-solver">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1">
                <Label htmlFor="tl">{t("studio.run.timeLimit")}</Label>
                <Input id="tl" type="number" min={10} max={3600} value={local.params.time_limit_s ?? settings.data?.solver_default_time_limit ?? 120} onChange={(e) => dispatch({ type: "setParams", params: { time_limit_s: Number(e.target.value) } })} />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="seed">{t("generate.seed")}</Label>
                <Input id="seed" type="number" value={local.params.seed ?? settings.data?.solver_default_seed ?? 0} onChange={(e) => dispatch({ type: "setParams", params: { seed: Number(e.target.value) } })} />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="workers">{t("settings.workers")}</Label>
                <Input id="workers" type="number" min={1} max={32} value={local.params.workers ?? settings.data?.solver_default_workers ?? 8} onChange={(e) => dispatch({ type: "setParams", params: { workers: Number(e.target.value) } })} />
              </div>
            </div>
            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
              {WEIGHT_KINDS.map((k) => (
                <div key={k} className="grid gap-1">
                  <div className="flex items-center justify-between text-sm">
                    <span id={`w-${k}`}>{t(`generate.weight.${k}` as MessageKey)}</span>
                    <span className="font-mono text-xs tabular-nums">{weights[k] ?? 0}</span>
                  </div>
                  <Slider min={0} max={10} step={1} value={[weights[k] ?? 0]} aria-labelledby={`w-${k}`} onValueChange={(v) => dispatch({ type: "setParams", params: { weights: { ...weights, [k]: Array.isArray(v) ? (v[0] ?? 0) : Number(v) } } })} />
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <GenerateButton />
      </section>
      {advanced ? <RunHistory /> : null}
    </div>
  );
}
