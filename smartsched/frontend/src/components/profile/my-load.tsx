"use client";
/**
 * /profile › "Haftalık ders yüküm" (CH-11, docs/design/v3/charts.md §4 row 19, wireframe charts-user-390.svg): an
 * academician's class periods per weekday in the published timetable, as a BarList (no chart library). Each row is
 * a 44 px link to that day of /timetable for their own instructor record; a day without classes reads "ders yok".
 * Shown only to people linked to an instructor record (`GET /moderation/me/preferences` → `linked`). Data:
 * `GET /me/load` (lib/api/stats.ts); while that route is missing the card says so ("veri yok"). Original work.
 */
import Link from "next/link";
import { BarList } from "@/components/ui/bar-list";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { serverMessage } from "@/lib/api/error-text";
import { isMissingRoute, useMyLoad } from "@/lib/api/stats";
import { useMyPreferences } from "@/lib/api/teacher-preferences";
import { useI18n } from "@/lib/i18n/provider";
import { loadRows, timetableDayHref } from "./my-stats-model";

export function MyLoad() {
  const prefs = useMyPreferences(null);
  const linked = prefs.data?.linked === true && prefs.data.instructor_id != null;
  if (!linked) return null;
  return <MyLoadCard instructorId={prefs.data!.instructor_id!} />;
}

function MyLoadCard({ instructorId }: { instructorId: number }) {
  const { t, locale } = useI18n();
  const q = useMyLoad(null);
  const missing = q.isError && isMissingRoute(q.error);
  const rows = q.data ? loadRows(q.data, locale, t) : [];
  const published = q.data?.run_id != null;
  const total = q.data?.total_periods ?? rows.reduce((s, r) => s + r.periods, 0);

  let body;
  if (q.isLoading) body = <Skeleton className="h-40 w-full" />;
  else if (missing) body = <p className="type-callout text-label-2">{t("charts.load.missing")}</p>;
  else if (q.isError)
    body = (
      <div role="status" className="flex flex-col items-start gap-2">
        <p className="type-callout text-label-2">{serverMessage(q.error, locale) ?? t("charts.error.title")}</p>
        <Button variant="secondary" size="md" onClick={() => void q.refetch()}>
          {t("charts.error.retry")}
        </Button>
      </div>
    );
  else if (!published) body = <p className="type-callout text-label-2">{t("charts.load.notPublished")}</p>;
  else
    body = (
      <>
        <BarList
          aria-label={t("charts.load.list")}
          linkAs={Link}
          items={rows.map((r) => ({
            key: String(r.day),
            label: r.label,
            value: r.periods,
            display: r.display,
            href: timetableDayHref(r.day, instructorId, q.data?.run_id ?? null),
            linkLabel: t("charts.load.link", { day: r.label, value: r.display }),
          }))}
        />
        <p className="type-footnote text-label-3" data-testid="my-load-total">
          {t("charts.load.total", { n: total })}
        </p>
      </>
    );

  return (
    <section aria-labelledby="my-load-title" data-testid="my-load">
      <h2 id="my-load-title" className="mb-1 type-title-3 text-label-1">
        {t("charts.load.title")}
      </h2>
      <p className="mb-3 type-footnote text-label-3">{t("charts.load.hint")}</p>
      <Card className="gap-3 px-4 py-4">{body}</Card>
    </section>
  );
}
