"use client";
/**
 * Tamamlanma (spec §4.6): the last 7 / 30 / 90 days per audience: Gördü, Tur %, Liste ≥ %80, Kapattı %, and the median
 * days to the first booking (booking audiences only). Groups under 5 people say "5'ten az" with no numbers. Aggregate
 * only: no per-person list, no export. One card per audience (a grid on desktop, a column on phones).
 */
import { useState } from "react";
import { Loading } from "@/components/admin/kit";
import { Card } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { type StatRow, useWelcomeStats } from "@/lib/api/welcome";
import { formatNumber, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { audienceKey } from "../content";

const RANGES = ["7", "30", "90"] as const;
const BOOKING_AUDIENCES = ["academician", "staff", "dept_admin", "approver"];

const pct = (v: number | null | undefined, locale: Locale) => (v == null ? null : formatNumber(locale, v / 100, { style: "percent", maximumFractionDigits: 0 }));

function StatCard({ row }: { row: StatRow }) {
  const { t, locale } = useI18n();
  const none = t("welcome.admin.stats.none");
  const cells: { label: string; value: string | null }[] = [
    { label: t("welcome.admin.stats.shown"), value: row.shown == null ? null : formatNumber(locale, row.shown) },
    { label: t("welcome.admin.stats.tour"), value: pct(row.tour_completed_pct, locale) },
    { label: t("welcome.admin.stats.checklist"), value: pct(row.checklist_80_pct, locale) },
    { label: t("welcome.admin.stats.dismissed"), value: pct(row.dismissed_pct, locale) },
    ...(BOOKING_AUDIENCES.includes(row.audience) ? [{ label: t("welcome.admin.stats.median"), value: row.median_days_to_first_booking == null ? null : t("welcome.admin.stats.medianValue", { n: formatNumber(locale, row.median_days_to_first_booking, { maximumFractionDigits: 1 }) }) }] : []),
  ];
  return (
    <Card className="gap-3 px-4 py-4" data-testid={`welcome-stats-${row.audience}`} data-small={row.small_group || undefined}>
      <p className="type-headline text-label-1">{t(audienceKey(row.audience))}</p>
      {row.small_group ? (
        <div>
          <p className="type-title-3 text-label-1">{t("welcome.admin.stats.small")}</p>
          <p className="type-footnote text-label-3">{t("welcome.admin.stats.smallBody")}</p>
        </div>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
          {cells.map((c) => (
            <div key={c.label}>
              <dt className="type-caption text-label-3">{c.label}</dt>
              <dd className="type-headline text-label-1 tabular-nums">{c.value ?? none}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

export function WelcomeStatsTab() {
  const { t } = useI18n();
  const [days, setDays] = useState<(typeof RANGES)[number]>("30");
  const q = useWelcomeStats(Number(days));
  return (
    <div className="flex flex-col gap-4">
      <SegmentedControl
        semantics="radiogroup"
        aria-label={t("welcome.admin.stats.range")}
        value={days}
        onValueChange={setDays}
        options={RANGES.map((d) => ({ value: d, label: t("welcome.admin.stats.days", { n: d }), testId: `welcome-days-${d}` }))}
        className="self-start"
      />
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <p className="type-callout text-label-2">{t("welcome.admin.stats.loadFailed")}</p>
      ) : !q.data?.rows.length ? (
        <p className="type-callout text-label-2">{t("welcome.admin.stats.empty")}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.rows.map((r) => (
            <StatCard key={r.audience} row={r} />
          ))}
        </div>
      )}
      <p className="type-footnote text-label-3">{t("welcome.admin.stats.privacy")}</p>
    </div>
  );
}
