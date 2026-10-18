"use client";
/**
 * "Özetim" (CH-11, docs/design/v3/charts.md §4 row 17, wireframe charts-user-390.svg) on /my-bookings and /profile:
 * three plain numbers (etkin / bu dönem / açık talep) and the quota sentence "3 / 5 aktif rezervasyon hakkı
 * kullanıldı". No chart library on these routes. Data: `GET /bookings/dashboard` (totals, limits) and
 * `GET /approvals/mine` (open requests): the same numbers the page used before, as tiles. Original work.
 */
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBookingDashboard } from "@/lib/api/crbs";
import { useMyRequests } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { openRequestCount } from "@/components/bookings/my-bookings-model";
import { myTiles, quotaSentence, type TileKey } from "./my-stats-model";

const TILE_LABEL = { active: "charts.mine.active", term: "charts.mine.term", open: "charts.mine.open" } as const satisfies Record<TileKey, string>;

/** `showTitle`: a visible "Özetim" heading (/profile); /my-bookings has its own page title, so it stays for screen readers */
export function MyStats({ headingLevel = 2, showTitle = false }: { headingLevel?: 2 | 3; showTitle?: boolean }) {
  const { t, n } = useI18n();
  const dash = useBookingDashboard();
  const requests = useMyRequests();
  const Heading = `h${headingLevel}` as "h2";
  if (dash.isError) return null;
  const tiles = dash.data ? myTiles(dash.data, openRequestCount(requests.data)) : null;
  const quota = dash.data ? quotaSentence(dash.data, t) : null;
  const limit = dash.data?.limits.max_active_bookings;
  const left = dash.data && limit != null ? Math.max(0, limit - (dash.data.totals.active_periods ?? dash.data.totals.active)) : null;
  return (
    <section aria-labelledby="my-stats-title" data-testid="my-stats">
      <Heading id="my-stats-title" className={showTitle ? "mb-3 type-title-3 text-label-1" : "sr-only"}>
        {t("charts.mine.title")}
      </Heading>
      <dl className="grid grid-cols-3 gap-2 sm:gap-3" aria-busy={dash.isLoading || undefined}>
        {(tiles ?? (["active", "term", "open"] as const).map((key) => ({ key, value: null }))).map((tile) => (
          <Card key={tile.key} className="gap-1 px-3 py-3 sm:px-4" data-testid={`my-stat-${tile.key}`}>
            <dt className="type-footnote text-label-2">{t(TILE_LABEL[tile.key])}</dt>
            <dd className="type-title-2 font-semibold text-label-1 tabular-nums">{tile.value == null ? <Skeleton className="h-[1lh] w-10" /> : n(tile.value)}</dd>
          </Card>
        ))}
      </dl>
      {quota ? (
        <p className="mt-2 type-callout text-label-2" data-testid="my-stats-quota">
          {quota}
          {left != null ? <span data-testid="mine-can-create">{` · ${t("reserve.mine.canCreate", { n: left })}`}</span> : null}
        </p>
      ) : null}
    </section>
  );
}
