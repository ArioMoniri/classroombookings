"use client";
/**
 * Outcome and priority as glyph + word (liquid-glass G4, priority-policy spec §8): an outcome never relies on
 * colour, a priority tier is a property (chevrons / minus) with no colour coding at all.
 */
import { ChevronDown, ChevronsUp, Circle, Minus } from "lucide-react";
import { StatusBadge } from "@/components/common/status-badge";
import type { Pair, TierCode, Verdict } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { pairText, tierOf, verdictKind } from "./moderation-model";

export function VerdictBadge({ verdict, text, planner = false, className }: { verdict: Verdict; text?: Pair | null; planner?: boolean; className?: string }) {
  const { t, locale } = useI18n();
  const word = (text ? pairText(text, locale === "tr" ? "tr" : "en") : "") || t(`moderation.verdict.${verdict}` as MessageKey);
  const kind = verdictKind(verdict);
  const label = planner ? `${word} ${t("moderation.plannerSuffix")}` : word;
  if (!kind) {
    return (
      <span data-verdict={verdict} className={cn("inline-flex items-center gap-1 whitespace-nowrap type-footnote text-label-2", className)}>
        <Circle className="size-3.5" aria-hidden />
        {label}
      </span>
    );
  }
  return <StatusBadge kind={kind} label={label} variant="plain" className={className} />;
}

const TIER_ICON = { high: ChevronsUp, normal: Minus, low: ChevronDown } as const;
const TIER_TONE = { high: "text-label-1", normal: "text-label-3", low: "text-label-2" } as const;

export function TierGlyph({ tier, className }: { tier: TierCode; className?: string }) {
  const Icon = TIER_ICON[tier];
  return <Icon className={cn("size-3.5 shrink-0", TIER_TONE[tier], className)} aria-hidden />;
}

/** "⌃ Yüksek · talep": glyph + word + where it came from (request › section › default) */
export function TierLabel({ value, source, className }: { value: number; source?: "request" | "section" | "default"; className?: string }) {
  const { t } = useI18n();
  const tier = tierOf(value);
  return (
    <span data-tier={tier} className={cn("inline-flex items-center gap-1 whitespace-nowrap type-footnote text-label-1", className)}>
      <TierGlyph tier={tier} />
      {t(`moderation.tier.${tier}`)}
      {source && source !== "default" ? <span className="text-label-3">· {t(`moderation.tierSource.${source}`)}</span> : null}
    </span>
  );
}
