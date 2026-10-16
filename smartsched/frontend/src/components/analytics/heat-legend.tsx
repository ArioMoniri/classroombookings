"use client";
/**
 * Scale legend of the utilisation heatmaps (dataviz skill "scale legend"): the five steps with their ranges, the
 * hatched pre-occupied swatch ("left out of the %"), the partly-blocked corner and the dotted "no rooms" swatch.
 * The swatches are the same `.an-heat` cells the grid uses, so the legend can never drift from the marks.
 */
import { useI18n } from "@/lib/i18n/provider";
import { STEP_BOUNDS } from "./heat-scale";
import "./heat.css";

export function HeatLegend({ showBlocked = true, unit = "%" }: { showBlocked?: boolean; unit?: string }) {
  const { t } = useI18n();
  return (
    <div role="group" aria-label={t("analytics.legend.title")} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 type-caption text-label-2" data-testid="heat-legend">
      <span className="font-semibold text-label-1">{t("analytics.legend.title")}</span>
      <span className="flex flex-wrap items-center gap-1">
        {STEP_BOUNDS.map((s) => (
          <span key={s.step} className="flex items-center gap-1">
            <span aria-hidden className="an-heat inline-block h-3.5 w-6 rounded-xs edge-hairline" data-state="value" data-step={s.step} />
            <span className="tnum">{s.from === s.to ? `${s.from}${unit}` : `${s.from}–${s.to}${unit}`}</span>
          </span>
        ))}
      </span>
      {showBlocked ? (
        <>
          <span className="flex items-center gap-1">
            <span aria-hidden className="an-heat inline-block h-3.5 w-6 rounded-xs edge-hairline" data-state="blocked" />
            {t("analytics.legend.blocked")}
          </span>
          <span className="flex items-center gap-1">
            <span aria-hidden className="an-heat inline-block h-3.5 w-6 rounded-xs edge-hairline" data-state="value" data-step={1} data-partly="true" />
            {t("analytics.legend.partly")}
          </span>
        </>
      ) : null}
      <span className="flex items-center gap-1">
        <span aria-hidden className="an-heat inline-block h-3.5 w-6 rounded-xs edge-hairline" data-state="empty" />
        {t("analytics.legend.empty")}
      </span>
    </div>
  );
}
