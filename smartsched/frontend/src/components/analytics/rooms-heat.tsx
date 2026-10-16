"use client";
/**
 * Room utilisation: (1) the overview, one row per group (every room first) x day or exam date, with the group
 * total; (2) the drilled-down group as period x day, so a planner sees which hours are full; (3) the rooms of that
 * group, each linking to its room page. Pre-occupied cells are hatched and left out of the % (backend
 * `pct = occupied / (capacity − blocked)`); `pct_with_blocks` is in the readout.
 */
import Link from "next/link";
import { useMemo } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { csvHref, errorText, pairOf, useRoomHeatmap, type HeatCount, type HeatPeriod, type RoomHeatmap, type RoomHeatQuery } from "@/lib/api/analytics";
import { useI18n } from "@/lib/i18n/provider";
import { HeatGrid, type HeatAxisItem } from "./heat-grid";
import { HeatLegend } from "./heat-legend";
import { columnHeader, detailCells, indexCells, overviewRows } from "./heat-model";
import { pctText } from "./heat-scale";
import { CsvButton } from "./csv-button";

function pctLabel(v: number, locale: string) {
  const f = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(v);
  return locale.startsWith("tr") ? `%${f}` : `${f}%`;
}

export function useDescribe() {
  const { t, n, locale } = useI18n();
  return (where: string, c: HeatCount | undefined) => {
    if (!c || c.capacity <= 0) return t("analytics.cell.empty", { where });
    if (c.blocked >= c.capacity) return t("analytics.cell.blocked", { where, blocked: n(c.blocked), capacity: n(c.capacity) });
    const base = t("analytics.cell.value", { where, occupied: n(c.occupied), free: n(c.capacity - c.blocked), pct: pctLabel(c.pct, locale) });
    const extra = [c.blocked ? t("analytics.cell.withBlocks", { blocked: n(c.blocked), pct: pctLabel(c.pct_with_blocks, locale) }) : null, c.held ? t("analytics.cell.held", { n: n(c.held) }) : null].filter(Boolean);
    return extra.length ? `${base} · ${extra.join(" · ")}` : base;
  };
}

export function RoomsHeat({ query, group, onGroup }: { query: RoomHeatQuery; group: string; onGroup: (g: string) => void }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const q = useRoomHeatmap(query);
  const drill = useRoomHeatmap(group && query.group_by !== "room" ? { ...query, rooms: true } : null);
  const describe = useDescribe();
  const data = q.data;

  if (q.isError) return <Alert tone="error" data-testid="heat-error" action={<Button size="sm" variant="ghost" onClick={() => void q.refetch()}>{t("common.retry")}</Button>}>{errorText(q.error, lang)}</Alert>;
  if (!data) return <div className="flex flex-col gap-3" aria-busy="true" aria-label={t("analytics.loading")}><Skeleton className="h-10 w-2/3" /><Skeleton className="h-64 w-full" /><Skeleton className="h-96 w-full" /></div>;

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="rooms-heat" aria-busy={q.isFetching || undefined}>
      <Summary data={data} query={query} />
      {data.empty ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5" data-testid="heat-empty"><p className="type-callout">{pairOf(data.empty_text, lang) || t("analytics.emptyBoard")}</p></div>
      ) : (
        <>
          <HeatLegend />
          <Overview data={data} group={group} onGroup={onGroup} describe={describe} />
          <Detail data={data} group={group} describe={describe} />
          {group && data.group_by !== "room" ? <RoomsOfGroup data={drill.data} loading={drill.isLoading} error={drill.isError ? errorText(drill.error, lang) : null} group={group} describe={describe} /> : null}
          <dl className="grid gap-1 type-footnote text-label-2 md:grid-cols-3">
            {Object.entries(data.definitions).map(([k, v]) => (
              <div key={k} className="flex flex-col"><dt className="font-medium text-label-1">{t(`analytics.def.${k === "pct" || k === "held" ? k : "room_period"}`)}</dt><dd>{pairOf(v, lang)}</dd></div>
            ))}
          </dl>
        </>
      )}
      <span className="sr-only" aria-live="polite">{q.isFetching ? t("analytics.loading") : t("analytics.loaded", { n: n(data.rows.length) })}</span>
    </div>
  );
}

function Summary({ data, query }: { data: RoomHeatmap; query: RoomHeatQuery }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const tot = data.overall.total;
  return (
    <section aria-label={t("analytics.summary")} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="type-title-2 tnum" data-testid="heat-overall">{t("analytics.overall", { pct: pctLabel(tot.pct, locale) })}</p>
        <p className="type-callout text-label-2 tnum">{t("analytics.overallDetail", { occupied: n(tot.occupied), free: n(tot.capacity - tot.blocked), rooms: n(data.overall.rooms), withBlocks: pctLabel(tot.pct_with_blocks, locale) })}</p>
        <span className="ml-auto"><CsvButton href={csvHref.rooms(query)} label={t("analytics.csv")} testId="heat-csv" /></span>
      </div>
      <p className="type-footnote text-label-2" data-testid="heat-source-note">
        {data.source === "board" ? t("analytics.fromBoard", { runs: data.runs.map((r) => `#${r.run_id}${r.label ? ` ${r.label}` : ""}`).join(", ") || t("analytics.noPublished") }) : t("analytics.fromRun", { run: data.runs.map((r) => `#${r.run_id}${r.label ? ` ${r.label}` : ""}`).join(", ") })}
        {" · "}
        {data.scope === "week" ? t("analytics.weeksOne", { n: data.weeks.join(", ") }) : t("analytics.weeksMany", { n: n(data.weeks.length) })}
        {" · "}
        {t("analytics.counted", { assignments: n(data.counted.assignments), blocks: n(data.counted.blocks), bookings: n(data.counted.bookings) })}
      </p>
      {data.notes.map((note, i) => (
        <Alert key={i} tone="info">{typeof note === "string" ? note : pairOf(note, lang)}</Alert>
      ))}
    </section>
  );
}

function colItems(data: RoomHeatmap, locale: string): HeatAxisItem[] {
  return data.columns.map((c) => {
    const h = columnHeader(c, locale);
    return { key: c.key, label: h.label, sub: h.sub, text: h.text };
  });
}

function Overview({ data, group, onGroup, describe }: { data: RoomHeatmap; group: string; onGroup: (g: string) => void; describe: (w: string, c: HeatCount | undefined) => string }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const rows = useMemo(() => overviewRows(data), [data]);
  const cols = useMemo(() => [...colItems(data, locale), { key: "__total", label: t("analytics.total"), text: t("analytics.total") }], [data, locale, t]);
  const label = (i: number) => (rows[i]!.key === "" ? t("analytics.allRooms") : pairOf(rows[i]!.label, lang));
  const sel = Math.max(0, rows.findIndex((r) => r.key === group));
  return (
    <section aria-labelledby="heat-overview-title" className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="heat-overview-title" className="type-title-3">{t(`analytics.overview.${data.group_by}`)}</h2>
        <p className="type-footnote text-label-2">{t("analytics.overviewHint")}</p>
      </div>
      <HeatGrid
        data-testid="heat-overview"
        label={t(`analytics.overview.${data.group_by}`)}
        locale={locale}
        rows={rows.map((r, i) => ({ key: r.key || "__all", label: label(i), text: label(i), sub: t("analytics.roomsN", { n: n(r.rooms) }) }))}
        cols={cols}
        cell={(r, c) => (c === cols.length - 1 ? rows[r]!.total : rows[r]!.byCol.get(cols[c]!.key))}
        describe={(r, c) => describe(`${label(r)} · ${cols[c]!.text}`, c === cols.length - 1 ? rows[r]!.total : rows[r]!.byCol.get(cols[c]!.key))}
        onActivate={(r) => onGroup(rows[r]!.key)}
        selectedRow={sel}
        rowHeader={(r) => {
          const row = rows[r]!;
          return (
            <span className="flex min-w-0 flex-col">
              {row.roomId !== null ? (
                <Link href={`/rooms/${row.roomId}`} className="truncate font-medium hover:underline focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid="heat-room-link">{label(r)}</Link>
              ) : (
                <span className="truncate">{label(r)}</span>
              )}
              <span className="truncate type-caption text-label-3">{t("analytics.roomsN", { n: n(row.rooms) })}</span>
            </span>
          );
        }}
        corner={t(data.axis === "date" ? "analytics.corner.date" : "analytics.corner.day")}
        cellWidth={data.axis === "date" ? 44 : 40}
        rowHeadWidth="minmax(6.5rem, max-content)"
        maxHeight="min(60dvh, 34rem)"
        hint={t("analytics.readoutHint")}
      />
    </section>
  );
}

function periodItems(periods: HeatPeriod[]): HeatAxisItem[] {
  return periods.map((p) => ({ key: String(p.period), label: p.start, sub: undefined, text: `${p.start}–${p.end}` }));
}

function Detail({ data, group, describe }: { data: RoomHeatmap; group: string; describe: (w: string, c: HeatCount | undefined) => string }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const cells = useMemo(() => detailCells(data, group), [data, group]);
  const cols = useMemo(() => colItems(data, locale), [data, locale]);
  const rows = useMemo(() => periodItems(data.periods), [data.periods]);
  const row = data.rows.find((r) => r.key === group);
  const name = row ? pairOf(row.label, lang) : t("analytics.allRooms");
  return (
    <section aria-labelledby="heat-detail-title" className="flex min-w-0 flex-col gap-2">
      <h2 id="heat-detail-title" className="type-title-3" data-testid="heat-detail-title">{t("analytics.detailTitle", { name })}</h2>
      <HeatGrid
        data-testid="heat-detail"
        label={t("analytics.detailTitle", { name })}
        locale={locale}
        rows={rows}
        cols={cols}
        cell={(r, c) => cells.get(`${cols[c]!.key}|${data.periods[r]!.period}`)}
        describe={(r, c) => describe(`${name} · ${cols[c]!.text} ${rows[r]!.text}`, cells.get(`${cols[c]!.key}|${data.periods[r]!.period}`))}
        corner={t("analytics.corner.period")}
        cellWidth={data.axis === "date" ? 44 : 40}
        rowHeadWidth="4.25rem"
        hint={t("analytics.readoutHint")}
      />
    </section>
  );
}

function RoomsOfGroup({ data, loading, error, group, describe }: { data: RoomHeatmap | undefined; loading: boolean; error: string | null; group: string; describe: (w: string, c: HeatCount | undefined) => string }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const row = data?.rows.find((r) => r.key === group);
  const rooms = useMemo(() => row?.room_rows ?? [], [row]);
  const cols = useMemo(() => (data ? [...colItems(data, locale), { key: "__total", label: t("analytics.total"), text: t("analytics.total") }] : []), [data, locale, t]);
  const byCol = useMemo(() => rooms.map((r) => indexCells(r.by_col.map((c) => ({ ...c, period: 0 })))), [rooms]);
  const name = row ? pairOf(row.label, lang) : group;
  return (
    <section aria-labelledby="heat-rooms-title" className="flex min-w-0 flex-col gap-2">
      <h2 id="heat-rooms-title" className="type-title-3">{t("analytics.roomsOf", { name })}</h2>
      {error ? (
        <Alert tone="error">{error}</Alert>
      ) : loading || !data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <HeatGrid
          data-testid="heat-rooms"
          label={t("analytics.roomsOf", { name })}
          locale={locale}
          rows={rooms.map((r) => ({ key: String(r.room_id), label: pairOf(r.label, lang), text: pairOf(r.label, lang) }))}
          cols={cols}
          cell={(r, c) => (c === cols.length - 1 ? rooms[r]!.total : byCol[r]!.get(`${cols[c]!.key}|0`))}
          describe={(r, c) => describe(`${pairOf(rooms[r]!.label, lang)} · ${cols[c]!.text}`, c === cols.length - 1 ? rooms[r]!.total : byCol[r]!.get(`${cols[c]!.key}|0`))}
          cellText={(r, c) => {
            const v = c === cols.length - 1 ? rooms[r]!.total : byCol[r]!.get(`${cols[c]!.key}|0`);
            return v && v.capacity > v.blocked ? pctText(v.pct, locale) : v && v.capacity > 0 ? "—" : "·";
          }}
          rowHeader={(r) => (
            <span className="flex min-w-0 flex-col">
              <Link href={`/rooms/${rooms[r]!.room_id}`} className="truncate font-medium hover:underline focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid="heat-room-link">
                {pairOf(rooms[r]!.label, lang)}
              </Link>
              <span className="truncate type-caption text-label-3">{t("analytics.seats", { n: n(rooms[r]!.capacity) })}</span>
            </span>
          )}
          corner={t("analytics.corner.room")}
          cellWidth={data.axis === "date" ? 44 : 40}
          rowHeadWidth="minmax(6rem, max-content)"
          maxHeight="min(60dvh, 36rem)"
          hint={t("analytics.readoutHint")}
        />
      )}
    </section>
  );
}
