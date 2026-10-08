"use client";

import { AlertTriangle, ChevronRight, Info, Loader2, MessageSquare, XOctagon } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import type { Diagnosis } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { formatSuggestion, plannerText, type ReportSection } from "./diagnosis-format";

const ICON = { unplaced: XOctagon, rules: XOctagon, input: AlertTriangle, info: Info } as const;
const TONE = { unplaced: "text-status-infeasible-fg", rules: "text-status-infeasible-fg", input: "text-status-warning-fg", info: "text-label-2" } as const;

/**
 * One problem in the planner's words (backend template), with the fixes that can actually be applied,
 * written from their params. No solver codes, ids or "manual" tags (usability B2). Duplicates arrive
 * collapsed (`count`).
 */
export function DiagnosisCard({ d, section, count = 1, onApply, applying, onChat }: { d: Diagnosis; section: ReportSection; count?: number; onApply: (suggestionId: string) => void; applying: boolean; onChat?: () => void }) {
  const { t, locale } = useI18n();
  const id = useId();
  const options = d.suggestions.map((s) => ({ s, text: formatSuggestion(s, locale) })).filter((o): o is { s: (typeof d.suggestions)[number]; text: string } => o.text !== null && o.s.applicable);
  const [choice, setChoice] = useState(options[0]?.s.id ?? "");
  const [more, setMore] = useState(false);
  const visible = more ? options : options.slice(0, 2);
  const chosen = options.find((o) => o.s.id === choice);
  const Icon = ICON[section];
  return (
    <article className="py-3.5 [&:not(:last-child)]:hairline-b" aria-labelledby={`${id}-t`} data-testid="diagnosis-card" data-code={d.code ?? ""}>
      <div className="flex items-start gap-2.5">
        <Icon className={cn("mt-0.5 size-4 shrink-0 stroke-[2]", TONE[section])} aria-hidden />
        <div className="min-w-0 flex-1">
          <p id={`${id}-t`} className="text-[13.5px] leading-5 text-label-1">
            {plannerText(d, locale)}
            {count > 1 ? <span className="ml-1.5 text-[12px] whitespace-nowrap text-label-3 tabular-nums">{t("glass.report.times", { n: count })}</span> : null}
          </p>
          {options.length ? (
            <fieldset className="mt-2.5">
              <legend className="mb-1 text-[12px] text-label-3">{t("glass.report.fixes")}</legend>
              <div role="radiogroup" aria-label={t("glass.report.fixes")} className="flex flex-col gap-1">
                {visible.map((o) => (
                  <label key={o.s.id} data-testid="diagnosis-fix-option" className={cn("flex cursor-pointer items-start gap-2 rounded-[10px] px-2.5 py-1.5 text-[13px] text-label-1 transition-colors duration-(--dur-fast)", choice === o.s.id ? "bg-tint-soft" : "hover:bg-fill-3")}>
                    <input type="radio" name={`${id}-fix`} value={o.s.id} checked={choice === o.s.id} onChange={() => setChoice(o.s.id)} className="mt-[3px] accent-(--accent)" />
                    <span className="flex-1">{o.text}</span>
                  </label>
                ))}
              </div>
              {options.length > visible.length ? (
                <button type="button" onClick={() => setMore(true)} className="mt-1 px-2.5 text-[12.5px] font-medium text-tint-text hover:underline">
                  {t("glass.report.moreFixes", { n: options.length - visible.length })}
                </button>
              ) : null}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {/* secondary: many cards share the region, so none of them is the page's single tint action (A6) */}
                <Button size="sm" variant="secondary" onClick={() => onApply(choice)} disabled={!chosen || applying} aria-label={`${t("glass.report.applyFix")}: ${chosen?.text ?? ""}`} data-testid="diagnosis-apply">
                  {applying ? <Loader2 className="animate-spin" /> : null} {t("glass.report.applyFix")}
                </Button>
                <span className="text-[12px] text-label-3">{t("glass.report.applyHint")}</span>
              </div>
            </fieldset>
          ) : onChat && section === "unplaced" ? (
            <button type="button" onClick={onChat} className="mt-1.5 inline-flex items-center gap-1 text-[12.5px] font-medium text-tint-text hover:underline">
              <MessageSquare className="size-3.5" aria-hidden /> {t("glass.report.askChat")}
              <ChevronRight className="size-3.5" aria-hidden />
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}
