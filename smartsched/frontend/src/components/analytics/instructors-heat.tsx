"use client";
/**
 * Instructor load: how many instructors teach in each slot (coloured relative to the busiest slot, the count
 * printed in the cell), the term's load figures, and a sortable people table (periods per week, idle gaps, days,
 * busiest day, longest block). Choosing a person shows their own week. Exam-only terms answer 409 with the
 * backend's words (an instructor load needs a course run).
 */
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { csvHref, errorText, pairOf, useInstructorHeatmap, type InstructorHeatQuery, type InstructorRow } from "@/lib/api/analytics";
import { useMe } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { CsvButton } from "./csv-button";
import { HeatGrid } from "./heat-grid";
import { HeatLegend } from "./heat-legend";
import { instructorMatrix, personMatrix } from "./heat-model";

const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i");

export function InstructorsHeat({ query: base }: { query: InstructorHeatQuery }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const me = useMe();
  const [limit, setLimit] = useState<number | undefined>(undefined);
  const query = useMemo(() => ({ ...base, limit }), [base, limit]);
  const q = useInstructorHeatmap(query);
  const [search, setSearch] = useState("");
  const [person, setPerson] = useState<number | null>(null);
  const data = q.data;
  const days = useMemo(() => (data ? data.days.filter((d) => d.day <= 5 || data.matrix.some((m) => m.day === d.day && m.instructors > 0)) : []), [data]);
  const matrix = useMemo(() => (data ? instructorMatrix(data) : null), [data]);
  const rows = useMemo(() => {
    const f = fold(search.trim());
    return (data?.rows ?? []).filter((r) => !f || fold(`${r.title ?? ""} ${r.name}`).includes(f));
  }, [data, search]);
  const selected = data?.rows.find((r) => r.instructor_id === person) ?? null;

  const columns = useMemo<DataColumn<InstructorRow>[]>(
    () => [
      { id: "name", header: t("analytics.ins.col.name"), pin: "left", priority: 1, grow: 2, minSize: 150, maxSize: 360, text: (r) => `${r.title ?? ""} ${r.name}`.trim(), sortValue: (r) => r.name, cell: (r) => <span className="flex min-w-0 flex-col leading-tight"><span className="truncate font-medium">{r.name}</span>{r.title ? <span className="truncate type-caption text-label-3">{r.title}</span> : null}</span> },
      { id: "periods", header: t("analytics.ins.col.periods"), align: "end", priority: 1, text: (r) => String(r.periods_per_week), sortValue: (r) => r.periods_per_week, cell: (r) => <span className="tnum">{n(r.periods_per_week)}</span> },
      { id: "gaps", header: t("analytics.ins.col.gaps"), align: "end", priority: 2, text: (r) => String(r.gaps_per_week), sortValue: (r) => r.gaps_per_week, cell: (r) => <span className="tnum">{n(r.gaps_per_week)}</span> },
      { id: "days", header: t("analytics.ins.col.days"), align: "end", priority: 2, text: (r) => String(r.days_per_week), sortValue: (r) => r.days_per_week, cell: (r) => <span className="tnum">{n(r.days_per_week)}</span> },
      { id: "maxDay", header: t("analytics.ins.col.maxDay"), align: "end", priority: 3, text: (r) => String(r.max_periods_day), sortValue: (r) => r.max_periods_day, cell: (r) => <span className="tnum">{n(r.max_periods_day)}</span> },
      { id: "maxGaps", header: t("analytics.ins.col.maxGaps"), align: "end", priority: 4, text: (r) => String(r.max_gaps_day), sortValue: (r) => r.max_gaps_day, cell: (r) => <span className="tnum">{n(r.max_gaps_day)}</span> },
      { id: "block", header: t("analytics.ins.col.block"), align: "end", priority: 4, text: (r) => String(r.longest_block), sortValue: (r) => r.longest_block, cell: (r) => <span className="tnum">{n(r.longest_block)}</span> },
      {
        id: "byDay",
        header: t("analytics.ins.col.byDay"),
        priority: 5,
        minSize: 150,
        text: () => "00 00 00 00 00",
        cell: (r) => (
          <span className="flex gap-1 tnum type-footnote" aria-label={[1, 2, 3, 4, 5].map((d) => `${days.find((x) => x.day === d) ? pairOf(days.find((x) => x.day === d)!.label, lang) : d}: ${n(r.by_day[String(d)] ?? 0)}`).join(", ")}>
            {[1, 2, 3, 4, 5].map((d) => (
              <span key={d} aria-hidden className="w-6 rounded-xs bg-fill-3 text-center">{n(r.by_day[String(d)] ?? 0)}</span>
            ))}
          </span>
        ),
      },
    ],
    [t, n, days, lang],
  );

  if (q.isError) return <Alert tone={q.error && "status" in q.error && q.error.status === 409 ? "warning" : "error"} data-testid="ins-heat-error">{errorText(q.error, lang)}</Alert>;
  if (!data || !matrix) return <div className="flex flex-col gap-3" aria-busy="true" aria-label={t("analytics.loading")}><Skeleton className="h-20 w-full" /><Skeleton className="h-80 w-full" /></div>;

  const dayItems = days.map((d) => ({ key: String(d.day), label: pairOf(d.label, lang).slice(0, 3), text: pairOf(d.label, lang) }));
  const periodItems = data.periods.map((p) => ({ key: String(p.period), label: p.start, text: `${p.start}–${p.end}` }));
  const s = data.summary;
  const tiles: [string, string][] = [
    [t("analytics.ins.total"), n(data.instructors_total)],
    [t("analytics.ins.mean"), n(s.periods_per_week_mean)],
    [t("analytics.ins.max"), n(s.periods_per_week_max)],
    [t("analytics.ins.gapsTotal"), n(s.gaps_per_week_total)],
    [t("analytics.ins.withGaps"), n(s.with_gaps)],
  ];
  const pm = selected ? personMatrix(selected.cells) : null;

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="instructors-heat" aria-busy={q.isFetching || undefined}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="type-footnote text-label-2">
          {t(data.source === "board" ? "analytics.ins.fromBoard" : "analytics.ins.fromRun", { run: data.run_id })} · {data.weeks.length === 1 ? t("analytics.weeksOne", { n: data.weeks[0]! }) : t("analytics.weeksMany", { n: n(data.weeks.length) })}
        </p>
        <CsvButton href={csvHref.instructors(query)} label={t("analytics.csv")} testId="ins-csv" />
      </div>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {tiles.map(([label, value]) => (
          <li key={label} className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-card p-3 edge-hairline">
            <span className="truncate type-footnote text-label-2">{label}</span>
            <span className="type-title-3 tnum">{value}</span>
          </li>
        ))}
      </ul>
      <section aria-labelledby="ins-matrix-title" className="flex min-w-0 flex-col gap-2">
        <h2 id="ins-matrix-title" className="type-title-3">{t("analytics.ins.matrixTitle")}</h2>
        <p className="type-footnote text-label-2">{t("analytics.ins.matrixLead", { max: n(matrix.max) })}</p>
        <HeatLegend showBlocked={false} unit={t("analytics.ins.unit")} />
        <HeatGrid
          data-testid="ins-matrix"
          label={t("analytics.ins.matrixTitle")}
          locale={locale}
          rows={periodItems}
          cols={dayItems}
          cell={(r, c) => matrix.cell(days[c]!.day, data.periods[r]!.period)}
          cellText={(r, c) => n(matrix.cell(days[c]!.day, data.periods[r]!.period)?.count ?? 0)}
          describe={(r, c) => {
            const x = matrix.cell(days[c]!.day, data.periods[r]!.period);
            return t("analytics.ins.cell", { where: `${dayItems[c]!.text} ${periodItems[r]!.text}`, n: n(x?.count ?? 0), total: n(data.instructors_total) });
          }}
          corner={t("analytics.corner.period")}
          rowHeadWidth="4.25rem"
          hint={t("analytics.readoutHint")}
        />
      </section>
      <section aria-labelledby="ins-people-title" className="flex min-w-0 flex-col gap-2">
        <h2 id="ins-people-title" className="type-title-3">{t("analytics.ins.people")}</h2>
        {data.truncated ? (
          <Alert tone="warning" action={<Button size="sm" variant="ghost" onClick={() => setLimit(5000)}>{t("analytics.ins.loadAll")}</Button>}>{t("analytics.ins.truncated", { n: n(data.rows.length), total: n(data.instructors_total) })}</Alert>
        ) : null}
        <DataTable
          tableId="heat-instructors"
          userId={me.data?.id}
          label={t("analytics.ins.people")}
          columns={columns}
          rows={rows}
          getRowId={(r) => String(r.instructor_id)}
          onRowActivate={(r) => setPerson((p) => (p === r.instructor_id ? null : r.instructor_id))}
          rowProps={(r) => ({ "data-testid": "ins-row", "data-selected": r.instructor_id === person ? "true" : undefined })}
          defaultSort={[{ id: "periods", desc: true }]}
          maxHeight="min(70dvh, 40rem)"
          toolbar={<Input fieldSize="sm" type="search" className="w-56" placeholder={t("analytics.ins.search")} aria-label={t("analytics.ins.search")} value={search} onChange={(e) => setSearch(e.target.value)} data-testid="ins-search" />}
          empty={<p className="px-3 py-6 type-callout text-label-2">{search ? t("analytics.ins.noMatch") : t("analytics.ins.none")}</p>}
        />
      </section>
      {selected && pm ? (
        <section aria-labelledby="ins-person-title" className="flex min-w-0 flex-col gap-2" data-testid="ins-person">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="ins-person-title" className="type-title-3">{t("analytics.ins.personTitle", { name: `${selected.title ?? ""} ${selected.name}`.trim() })}</h2>
            <Button size="sm" variant="ghost" onClick={() => setPerson(null)}>{t("common.close")}</Button>
          </div>
          <p className="type-footnote text-label-2">{t("analytics.ins.personLead", { periods: n(selected.periods_per_week), gaps: n(selected.gaps_per_week), days: n(selected.days_per_week) })}</p>
          <HeatGrid
            data-testid="ins-person-grid"
            label={t("analytics.ins.personTitle", { name: selected.name })}
            locale={locale}
            rows={periodItems}
            cols={dayItems}
            cell={(r, c) => pm(days[c]!.day, data.periods[r]!.period)}
            cellText={(r, c) => {
              const v = pm(days[c]!.day, data.periods[r]!.period);
              return v && v.pct > 0 ? "●" : "";
            }}
            describe={(r, c) => {
              const v = pm(days[c]!.day, data.periods[r]!.period);
              const where = `${dayItems[c]!.text} ${periodItems[r]!.text}`;
              return v && v.pct > 0 ? t("analytics.ins.teaches", { where, share: n(Math.round(v.pct)) }) : t("analytics.ins.free", { where });
            }}
            corner={t("analytics.corner.period")}
            rowHeadWidth="4.25rem"
            hint={t("analytics.readoutHint")}
          />
        </section>
      ) : null}
    </div>
  );
}
