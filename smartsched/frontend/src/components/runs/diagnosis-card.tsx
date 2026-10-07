"use client";

import { AlertTriangle, Loader2, MessageSquare, XOctagon } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Diagnosis } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export function DiagnosisCard({ d, onApply, applying, onChat }: { d: Diagnosis; onApply: (suggestionId: string) => void; applying: boolean; onChat: () => void }) {
  const { t } = useI18n();
  const hard = d.severity === "critical" || d.severity === "high";
  const [choice, setChoice] = useState(d.suggestions[0]?.id ?? "");
  const Icon = hard ? XOctagon : AlertTriangle;
  return (
    <article className={cn("rounded-xl border bg-card", hard ? "border-status-infeasible-border" : "border-status-warning-border")} aria-labelledby={`diag-${d.id}`} data-testid="diagnosis-card">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", hard ? "bg-status-infeasible text-status-infeasible-fg" : "bg-status-warning text-status-warning-fg")}><Icon className="size-3.5" aria-hidden />{hard ? t("runs.hard") : t("runs.soft")} · {t(`runs.severity.${d.severity}`)}</span>
        {d.constraint_kinds.map((k) => <Badge key={k} variant="outline" className="font-mono text-[10px]">{k}</Badge>)}
        <span className="ml-auto flex gap-1">{d.event_labels.map((l) => <Badge key={l} variant="secondary" className="font-mono">{l}</Badge>)}</span>
      </div>
      <p id={`diag-${d.id}`} className="px-4 py-3 text-sm">{d.message}</p>
      {d.suggestions.length ? (
        <div className="border-t px-4 py-3">
          <p className="mb-2 text-xs font-medium uppercase text-muted-foreground">{t("runs.suggestions")}</p>
          <div role="radiogroup" aria-label={t("runs.suggestions")} className="space-y-1.5">
            {d.suggestions.map((s) => (
              <label key={s.id} className={cn("flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm", choice === s.id && "border-primary bg-primary-tint")}>
                <input type="radio" name={`diag-${d.id}`} value={s.id} checked={choice === s.id} onChange={() => setChoice(s.id)} className="accent-primary" />
                <span className="flex-1">{s.text}</span>
                <Badge variant="outline" className="font-mono text-[10px]">{s.action}</Badge>
              </label>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => onApply(choice)} disabled={!choice || applying} aria-label={`${t("runs.applyFix")}: ${d.suggestions.find((s) => s.id === choice)?.text ?? ""}`} data-testid="apply-fix">{applying ? <Loader2 className="animate-spin" /> : null} {t("runs.applyFix")}</Button>
            <Button size="sm" variant="ghost" onClick={onChat}><MessageSquare /> {t("chat.title")}</Button>
          </div>
        </div>
      ) : null}
    </article>
  );
}
