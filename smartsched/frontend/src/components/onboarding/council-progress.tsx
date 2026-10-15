"use client";

import { CheckCircle2, CircleDashed, Loader2, MinusCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CROSS_AGENTS, FILE_AGENTS, type CouncilJob, type CouncilStep } from "@/lib/api/council";
import { useI18n } from "@/lib/i18n/provider";

const ICON = { DONE: CheckCircle2, SKIPPED: MinusCircle, FAILED: XCircle, RUNNING: Loader2 } as const;

function StepRow({ agent, step }: { agent: string; step: CouncilStep | undefined }) {
  const { t, n } = useI18n();
  const Icon = step ? ICON[step.status] : CircleDashed;
  return (
    <li className="flex gap-2 py-1 text-sm" data-testid={`step-${agent}`} data-status={step?.status ?? "PENDING"}>
      <Icon className={step?.status === "RUNNING" ? "mt-0.5 size-4 shrink-0 animate-spin" : "mt-0.5 size-4 shrink-0"} aria-hidden />
      <div className="min-w-0">
        <span className="font-medium">{agent}</span>
        <span className="ml-2 text-xs text-muted-foreground">{step ? step.status : t("onboarding.pending")}</span>
        {step?.duration_ms != null ? <span className="ml-2 text-xs text-muted-foreground">{n(step.duration_ms)} ms</span> : null}
        {step && step.input_tokens + step.output_tokens > 0 ? (
          <span className="ml-2 text-xs text-muted-foreground">
            {t("onboarding.tokens", { count: step.input_tokens + step.output_tokens })} · ${step.cost_usd.toFixed(4)}
          </span>
        ) : null}
        {step?.message ? <p className="whitespace-pre-line text-xs text-muted-foreground">{step.message}</p> : null}
      </div>
    </li>
  );
}

function latest(steps: CouncilStep[], agent: string): CouncilStep | undefined {
  return [...steps].reverse().find((s) => s.agent === agent);
}

export function CouncilProgress({ job }: { job: CouncilJob }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3" data-testid="onboarding-progress">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="outline">{job.status}</Badge>
        <Badge variant="secondary">{job.ai_mode === "llm" ? t("onboarding.aiLlm") : t("onboarding.aiHeuristic")}</Badge>
        {job.phase ? <span className="text-muted-foreground">{job.phase}</span> : null}
      </div>
      <Progress value={job.progress} aria-label={t("onboarding.progress")} />
      <div className="grid gap-3 lg:grid-cols-2">
        {job.files.map((f) => (
          <Card key={f.index} data-testid={`file-${f.index}`}>
            <CardHeader className="pb-1">
              <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                <span className="truncate">{f.filename}</span>
                {f.route ? <Badge variant="outline">{f.route}</Badge> : null}
                {f.language && f.language !== "und" ? <Badge variant="ghost">{f.language}</Badge> : null}
              </CardTitle>
              {Object.keys(f.counts).length ? (
                <p className="text-xs text-muted-foreground">
                  {Object.entries(f.counts)
                    .map(([k, v]) => `${v} ${k}`)
                    .join(" · ")}
                </p>
              ) : null}
              {f.message ? <p className="text-xs text-muted-foreground">{f.message}</p> : null}
            </CardHeader>
            <CardContent>
              <ul>
                {FILE_AGENTS.map((a) => (a === "rules" && !f.rule_texts && !latest(f.steps, a) ? null : <StepRow key={a} agent={a} step={latest(f.steps, a)} />))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader className="pb-1">
          <CardTitle className="text-sm">{t("onboarding.crossFiles")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul>
            {CROSS_AGENTS.map((a) => (
              <StepRow key={a} agent={a} step={latest(job.cross_steps, a)} />
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
