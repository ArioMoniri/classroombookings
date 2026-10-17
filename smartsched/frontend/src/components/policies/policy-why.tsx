"use client";
/**
 * "Neden?" — why a slot is refused or turns into a request (P8). The popover asks
 * `GET /booking-policies/effective?room_id=&date=&period_id=&term_id=` only when it opens, and shows the verdict, the
 * broken rules in the reader's language, every rule that binds the reader in that room (with its summary lines) and the
 * exam-period state. Planning administrators are exempt and are told so. Under approval-first (or a room's approval
 * rule) the verdict is "request" and the reasons name that setting (T-R1-10), never "Rezerve edebilirsiniz".
 *
 * Motion: the design system's popover reveal (.t-panel-slide), nothing added.
 */
import { HelpCircle, ShieldAlert, ShieldCheck, Stamp } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { useEffectivePolicies, violationText, type EffectiveQuery, type Violation } from "@/lib/api/booking-policies";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export function PolicyWhy({ query, violation, className, label }: { query: EffectiveQuery | null; violation?: Pick<Violation, "message_tr" | "message_en" | "effect"> | null; className?: string; label?: string }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const q = useEffectivePolicies(query, open);
  const e = q.data;
  const verdict = e?.verdict ?? (violation ? (violation.effect === "request" ? "request" : "refuse") : null);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button variant="link" size="sm" className={cn("h-auto min-h-0 gap-1 px-0 pointer-coarse:min-h-11", className)} data-testid="policy-why" />}>
        <HelpCircle className="size-3.5" aria-hidden />
        {label ?? t("policies.why.open")}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(22rem,calc(100vw-2rem))] gap-3 p-3" data-testid="policy-why-panel">
        <PopoverTitle className="flex items-center gap-2 type-headline">
          {verdict === "refuse" ? <ShieldAlert className="size-4 text-status-infeasible-fg" aria-hidden /> : verdict === "request" ? <Stamp className="size-4 text-tint-text" aria-hidden /> : <ShieldCheck className="size-4 text-status-feasible-fg" aria-hidden />}
          {verdict === "refuse" ? t("policies.why.refuse") : verdict === "request" ? t("policies.why.request") : verdict === "book" ? t("policies.why.book") : t("policies.why.rules")}
        </PopoverTitle>
        {violation && !e?.violations?.length ? <p className="type-callout text-label-1">{violationText(violation, locale)}</p> : null}
        {e?.violations?.length ? (
          <ul className="flex flex-col gap-1.5" data-testid="policy-why-violations">
            {e.violations.map((v, i) => (
              <li key={`${v.rule}-${v.policy_id ?? "x"}-${i}`} className="type-callout text-label-1">
                {violationText(v, locale)}
                {v.policy_name ? <span className="block type-footnote text-label-3">{t("policies.why.rule", { name: v.policy_name })}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
        {q.isLoading ? <p className="type-footnote text-label-2">{t("crbs.common.loading")}</p> : null}
        {q.isError ? <p className="type-footnote text-status-infeasible-fg">{errorText(wave1Error(q.error), locale)}</p> : null}
        {e?.exempt ? <p className="type-footnote text-label-2">{t("policies.why.exempt")}</p> : null}
        {e && e.exam_period && e.exam_period.mode !== "off" && e.exam_period.exam_room ? <p className="type-footnote text-label-2">{t(e.exam_period.mode === "closed" ? "policies.why.examClosed" : "policies.why.examRequest")}</p> : null}
        {e ? (
          e.policies.length ? (
            <div className="flex flex-col gap-1.5">
              <p className="type-footnote font-medium text-label-2">{t("policies.why.binding")}</p>
              <ul className="flex flex-col gap-2">
                {e.policies.map((p) => (
                  <li key={p.id} className="rounded-md bg-fill-3 px-2.5 py-2">
                    <p className="type-callout font-medium text-label-1">{p.name}</p>
                    <ul className="list-disc pl-4 type-footnote text-label-2">
                      {(locale === "tr" ? p.summary.tr : p.summary.en).map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            // T-R1-10: under approval-first the slot is a request although no booking rule binds the reader
            <p className="type-footnote text-label-2">{t(e.approval?.action === "request" ? "policies.why.noneElse" : "policies.why.none")}</p>
          )
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
