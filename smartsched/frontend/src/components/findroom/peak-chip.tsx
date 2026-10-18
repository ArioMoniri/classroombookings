"use client";
/**
 * AS-17 "Yoğun saat" on /find-room: when the searched weekday and periods are a peak of the published history
 * (`GET /analytics/peaks/campus`, `peak: true`; AS20-F03: that route is open to everyone signed in, the planner's
 * `/analytics/peaks` answered 403 to the academicians who book rooms), one quiet line says so and names the nearest calmer span
 * of the same day. A hint only: the search and its results are unchanged. Silent when the backend has no history
 * (`confidence: none`) or the time is not a peak.
 */
import { Flame } from "lucide-react";
import { isoWeekday, peakHit, useCampusPeaks } from "@/lib/api/adaptive";
import { intlLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

export function PeakChip({ termId, slot }: { termId: number | undefined; slot: { date: string; start_period: number; end_period: number } | undefined }) {
  const { t, locale, n } = useI18n();
  const q = useCampusPeaks(termId ?? null, termId !== undefined && !!slot);
  if (!slot || !q.data || q.data.confidence === "none") return null;
  const day = isoWeekday(slot.date);
  const hit = peakHit(q.data.cells, day, slot.start_period, slot.end_period);
  if (!hit.hits.length) return null;
  const top = Math.round(Math.max(...hit.hits.map((c) => c.value)));
  const dayName = new Intl.DateTimeFormat(intlLocale(locale), { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 1, 15 + day)));
  const alt = hit.alternative;
  const span = alt ? (alt.start === alt.end ? t("adaptive.find.period", { n: alt.start }) : t("adaptive.find.periods", { from: alt.start, to: alt.end })) : null;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 type-footnote text-label-2" data-testid="fr-peak">
      <span className="inline-flex items-center gap-1 rounded-full bg-status-warning px-2 py-0.5 font-medium text-status-warning-fg">
        <Flame className="size-3.5" aria-hidden />
        {t("adaptive.find.chip")}
      </span>
      <span>{t("adaptive.find.body", { pct: `%${n(top)}` })}</span>
      {span ? <span className="text-label-1" data-testid="fr-peak-alt">{t("adaptive.find.alt", { day: dayName, span })}</span> : null}
    </p>
  );
}
