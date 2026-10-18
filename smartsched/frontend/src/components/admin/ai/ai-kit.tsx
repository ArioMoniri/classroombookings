"use client";
/**
 * Small shared pieces of Yönetim › Yapay zekâ: the meter (ratio against a limit, the word always next to the fill),
 * a stat tile, a status word with a dot, the AI transparency notice, and label helpers for features / reasons /
 * outcomes (docs/design/v3/ai-admin.md §5, §11).
 */
import { Info } from "lucide-react";
import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { compactTokens, fullNumber, meterFill, outcomeOf, pctText, reasonOf, type MeterState } from "./ai-model";

export function useAiLabels() {
  const { t } = useI18n();
  return {
    feature: (f: string) => (f === "voice_stt" ? t("voice.admin.feature") : t((["rules", "chat", "intake", "vision", "explain", "booking_nl", "guard", "test"].includes(f) ? `aiAdmin.feature.${f}` : "aiAdmin.feature.other") as MessageKey)),
    reason: (code: string | null | undefined) => t(`aiAdmin.reason.${reasonOf(code)}` as MessageKey),
    outcome: (o: string) => t(`aiAdmin.outcome.${outcomeOf(o)}` as MessageKey),
    state: (s: MeterState) => t(`aiAdmin.state.${s}` as MessageKey),
  };
}

/** Tokens as "2,41 Mn" with the full number for assistive tech and the tooltip. */
export function Tokens({ n }: { n: number }) {
  const { locale } = useI18n();
  return (
    <span title={fullNumber(n, locale)} aria-label={fullNumber(n, locale)} className="tabular-nums">
      {compactTokens(n, locale)}
    </span>
  );
}

export function Meter({ pct, state, label, testId, className }: { pct: number | null; state: MeterState; label: ReactNode; testId?: string; className?: string }) {
  const { locale } = useI18n();
  const words = useAiLabels();
  const width = Math.max(0, Math.min(100, pct ?? 0));
  return (
    <div className={cn("flex flex-col gap-1.5", className)} data-testid={testId} data-state={state}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="type-callout text-label-1">{label}</span>
        <span className="type-footnote font-medium text-label-2">
          {pct != null ? `${pctText(pct, locale)} · ` : ""}
          {words.state(state)}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-fill-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? 0} aria-valuetext={`${pctText(pct, locale)} ${words.state(state)}`}>
        <div className="h-full rounded-full transition-transform duration-(--dur-fast) motion-reduce:transition-none" style={{ width: `${width}%`, background: meterFill(state) }} />
      </div>
    </div>
  );
}

export function StatTile({ label, value, note, testId }: { label: ReactNode; value: ReactNode; note?: ReactNode; testId?: string }) {
  return (
    <Card className="gap-1 px-4 py-3" data-testid={testId}>
      <p className="type-footnote text-label-2">{label}</p>
      <p className="type-title-2 font-semibold text-label-1 tabular-nums">{value}</p>
      {note ? <p className="type-caption text-label-3">{note}</p> : null}
    </Card>
  );
}

const DOT: Record<string, string> = {
  ok: "bg-status-feasible-fg",
  untested: "bg-label-3",
  noKey: "bg-label-3",
  disabled: "bg-label-4",
  error: "bg-status-infeasible-fg",
  warning: "bg-status-warning-fg",
};

export function StatusWord({ tone, children, testId }: { tone: keyof typeof DOT | string; children: ReactNode; testId?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 type-footnote font-medium text-label-1" data-testid={testId} data-tone={tone}>
      <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone] ?? "bg-label-3")} />
      {children}
    </span>
  );
}

/** R-AI-10: the transparency notice on every AI screen. */
export function AiNotice({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <p className={cn("flex items-start gap-2 type-footnote text-label-2", className)} data-testid="ai-notice">
      <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <span>{t("aiAdmin.notice")}</span>
    </p>
  );
}
