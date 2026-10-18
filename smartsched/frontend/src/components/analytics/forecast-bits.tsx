"use client";
/**
 * Shared text pieces of the adaptive views (AS-16): the confidence line (badge word + basis + needs, never colour
 * alone) and a value's 80 % range. AS-21: ranges are calibrated; while confidence is `low` the range carries
 * "düşük güven"; `requests` cells are counted, so they get no range. AS20-F14: the no-term needs block.
 */
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { lowConfidence, showRange, type Confidence } from "@/lib/api/adaptive";
import { useI18n } from "@/lib/i18n/provider";

export function ConfidenceNote({ confidence, label, basis, needs }: { confidence: Confidence; label?: string; basis?: string; needs?: string | null }) {
  const { t } = useI18n();
  const tone = confidence === "high" ? "feasible" : confidence === "medium" ? "tint" : "warning";
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 type-footnote text-label-2" data-testid="confidence-note" data-confidence={confidence}>
      <Badge tone={tone}>{label || t(`adaptive.confidence.${confidence}`)}</Badge>
      {basis ? <span>{basis}</span> : null}
      {needs && confidence !== "high" ? <span className="text-label-1">{needs}</span> : null}
    </p>
  );
}

export function RangeText({ lo, hi, format, confidence, method }: { lo: number | null; hi: number | null; format: (v: number) => string; confidence: Confidence; method?: string }) {
  const { t } = useI18n();
  if (!showRange({ lo80: lo, hi80: hi, confidence, method })) return <span aria-label={t("adaptive.noRange")}>—</span>;
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-1.5" data-testid="range-text">
      <span>{t("adaptive.range", { lo: format(lo ?? 0), hi: format(hi ?? 0) })}</span>
      {lowConfidence({ confidence, method }) ? <Badge tone="warning" data-testid="low-confidence">{t("adaptive.lowConfidence")}</Badge> : null}
    </span>
  );
}

/** AS20-F14: an install with no term yet says what to do first (never an empty select and "Önce bir dönem seçin.") */
export function NoTerms() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl bg-fill-3 px-4 py-5" data-testid="adaptive-no-terms">
      <p className="type-callout text-label-1">{t("adaptive.noTerms")}</p>
      <Button variant="outline" nativeButton={false} render={<Link href="/import" />}>
        {t("adaptive.goImport")} <ArrowRight aria-hidden />
      </Button>
    </div>
  );
}
