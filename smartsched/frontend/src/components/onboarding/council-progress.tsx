"use client";
/**
 * Council progress as a files table (phase19-intake R7): one row per file with its route (Doğrudan / YZ), the
 * council route name, status and a compact phase line (intake → structure → extract → rules) instead of one card
 * per file. E-mail attachments (`parent`) sit indented under their e-mail. Cross-file steps follow as one line.
 */
import { CheckCircle2, CircleDashed, MinusCircle, XCircle } from "lucide-react";
import { BusyGlyph } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { CROSS_AGENTS, FILE_AGENTS, type CouncilFile, type CouncilJob, type CouncilStep } from "@/lib/api/council";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { useOnboardingCopy } from "./copy";
import { MethodBadge, type ReadMethod } from "./method-badge";

/** How the file was read (T-R1-23): with the AI off nothing is labelled AI; a file nothing could be read from says so. */
function readMethod(job: CouncilJob, f: CouncilFile): ReadMethod | null {
  if (!f.route_kind) return null;
  if (f.route === "vision" || f.route === "ai-off") return job.ai_mode === "llm" ? "ai" : "unread";
  if (f.route_kind !== "ai" || job.ai_mode !== "llm") return "direct";
  return "ai";
}

/** The intake step's read notes (encoding and delimiter of a CSV, hidden sheets, no text layer) for the file row. */
function readNotes(f: CouncilFile): string[] {
  const intake = [...f.steps].reverse().find((s) => s.agent === "intake");
  return (intake?.message ?? "").split("\n").filter((l) => l && l !== f.message);
}

const ICON = { DONE: CheckCircle2, SKIPPED: MinusCircle, FAILED: XCircle } as const;

function StepChip({ agent, step }: { agent: string; step: CouncilStep | undefined }) {
  const { t, n } = useI18n();
  const c = useOnboardingCopy();
  const status = step?.status ?? "PENDING";
  const Icon = step && step.status !== "RUNNING" ? ICON[step.status] : null;
  const detail = [step ? (c.status[step.status] ?? step.status) : t("onboarding.pending"), step?.duration_ms != null ? `${n(step.duration_ms)} ms` : null, step && step.input_tokens + step.output_tokens > 0 ? t("onboarding.tokens", { count: step.input_tokens + step.output_tokens }) : null, step?.message ?? null]
    .filter(Boolean)
    .join(" · ");
  return (
    <li
      className={cn("inline-flex items-center gap-1 type-footnote", status === "FAILED" ? "text-status-infeasible-fg" : status === "DONE" ? "text-label-1" : "text-label-2")}
      data-testid={`step-${agent}`}
      data-status={status}
      title={detail}
    >
      {status === "RUNNING" ? <BusyGlyph className="size-3.5" /> : Icon ? <Icon aria-hidden className="size-3.5 stroke-[1.75]" /> : <CircleDashed aria-hidden className="size-3.5 stroke-[1.75]" />}
      <span>{c.agent[agent] ?? agent}</span>
      <span className="sr-only">: {detail}</span>
    </li>
  );
}

function latest(steps: CouncilStep[], agent: string): CouncilStep | undefined {
  return [...steps].reverse().find((s) => s.agent === agent);
}

/** Files in table order: each e-mail followed by its attachments. */
function ordered(files: CouncilFile[]): { f: CouncilFile; depth: number }[] {
  const children = new Map<number, CouncilFile[]>();
  for (const f of files) if (f.parent != null) children.set(f.parent, [...(children.get(f.parent) ?? []), f]);
  const out: { f: CouncilFile; depth: number }[] = [];
  const walk = (f: CouncilFile, depth: number) => {
    out.push({ f, depth });
    for (const c of children.get(f.index) ?? []) walk(c, depth + 1);
  };
  for (const f of files) if (f.parent == null || !files.some((x) => x.index === f.parent)) walk(f, 0);
  return out;
}

export function CouncilProgress({ job }: { job: CouncilJob }) {
  const { t, n } = useI18n();
  const c = useOnboardingCopy();
  const failed = job.files.filter((f) => f.status === "FAILED").length;
  const done = job.files.filter((f) => f.status === "DONE" || f.status === "READY" || f.status === "REVIEW").length;
  return (
    <Card className="gap-3 p-4" data-testid="onboarding-progress">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 type-callout">
        <span className="font-semibold text-label-1" data-status={job.status}>{c.status[job.status] ?? job.status}</span>
        <span className="text-label-2">{job.ai_mode === "llm" ? t("onboarding.aiLlm") : t("onboarding.aiHeuristic")}</span>
        {job.phase ? <span className="text-label-2">· {job.phase}</span> : null}
        <span className="ml-auto text-label-2 tnum">{c.summary(done, failed)}</span>
      </div>
      <Progress value={job.progress} aria-label={t("onboarding.progress")}>
        <ProgressTrack>
          <ProgressIndicator />
        </ProgressTrack>
      </Progress>
      <div className="overflow-x-auto">
        <table className="w-full type-callout">
          <thead>
            <tr className="text-left type-footnote text-label-2 edge-hairline-b">
              <th scope="col" className="py-2 pr-2 font-semibold">{c.colName}</th>
              <th scope="col" className="px-2 py-2 font-semibold">{c.colRoute}</th>
              <th scope="col" className="px-2 py-2 font-semibold">{c.colStatus}</th>
              <th scope="col" className="px-2 py-2 font-semibold">{c.colPhase}</th>
            </tr>
          </thead>
          <tbody>
            {ordered(job.files).map(({ f, depth }) => (
              <tr key={f.index} className="align-top edge-hairline-b" data-testid={`file-${f.index}`} data-parent={f.parent ?? undefined}>
                <td className="max-w-0 py-2 pr-2" style={{ paddingLeft: depth * 20 }}>
                  <span className="flex min-w-0 items-baseline gap-1.5">
                    {depth ? <span aria-hidden className="text-label-3">↳</span> : null}
                    <span className="truncate text-label-1">{f.filename}</span>
                    {depth ? <span className="shrink-0 type-caption text-label-2">{c.attachment}</span> : null}
                  </span>
                  {Object.keys(f.counts).length ? (
                    <span className="block truncate type-footnote text-label-2 tnum">
                      {Object.entries(f.counts)
                        .map(([k, v]) => `${n(v)} ${c.record[k] ?? k}`)
                        .join(" · ")}
                    </span>
                  ) : null}
                  {f.message ? <span className="block type-footnote text-label-2">{f.message}</span> : null}
                  {readNotes(f).map((line) => (
                    <span key={line} className="block type-footnote text-label-2" data-testid="file-read-note">{line}</span>
                  ))}
                </td>
                <td className="px-2 py-2">
                  <span className="flex flex-wrap items-center gap-1.5">
                    {readMethod(job, f) ? <MethodBadge method={readMethod(job, f) ?? "direct"} /> : null}
                    {f.route && f.route !== "ai-off" ? <span className="type-footnote text-label-2" data-route={f.route}>{c.route(f.route)}</span> : null}
                    {f.language && f.language !== "und" ? <span className="type-footnote text-label-2">· {f.language}</span> : null}
                  </span>
                </td>
                <td className={cn("px-2 py-2 type-footnote", f.status === "FAILED" ? "text-status-infeasible-fg" : "text-label-1")} data-status={f.status}>{c.status[f.status] ?? f.status}</td>
                <td className="px-2 py-2">
                  <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label={c.colPhase}>
                    {FILE_AGENTS.map((a) => (a === "rules" && !f.rule_texts && !latest(f.steps, a) ? null : <StepChip key={a} agent={a} step={latest(f.steps, a)} />))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="type-footnote font-semibold text-label-2">{t("onboarding.crossFiles")}</span>
        <ul className="flex flex-wrap gap-x-3 gap-y-1">
          {CROSS_AGENTS.map((a) => (
            <StepChip key={a} agent={a} step={latest(job.cross_steps, a)} />
          ))}
        </ul>
      </div>
    </Card>
  );
}
