"use client";
// SmartSched charts (CH-03, docs/design/v3/charts.md §6, §13.3): Profil › "Grafiklerde desen". A per-user switch
// (default off) that adds hatch patterns to chart series, so colour is never the only channel. Stored by
// use-chart-patterns.ts; forced-colors mode turns patterns on without it. Original work.
import { useId } from "react";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n/provider";
import { setChartPatterns, useChartPatterns } from "./use-chart-patterns";

/** `userId`: the signed-in user (the profile page passes `useCrbsMe().data?.id`). */
export function ChartPatternsToggle({ userId }: { userId: string | number | null | undefined }) {
  const { t } = useI18n();
  const id = useId();
  const uid = userId ?? null;
  const on = useChartPatterns(uid);
  return (
    <section aria-labelledby={`${id}-title`} id="chart-patterns" className="scroll-mt-20">
      <Card variant="glass" className="flex-row items-start justify-between gap-4 px-4">
        <div className="min-w-0">
          <label htmlFor={`${id}-switch`} id={`${id}-title`} className="type-body font-medium text-label-1">
            {t("charts.patterns.label")}
          </label>
          <p id={`${id}-hint`} className="type-footnote text-label-2">
            {t("charts.patterns.hint")}
          </p>
        </div>
        <Switch id={`${id}-switch`} checked={on} onCheckedChange={(next) => setChartPatterns(uid, next)} aria-describedby={`${id}-hint`} data-testid="chart-patterns-switch" />
      </Card>
    </section>
  );
}
