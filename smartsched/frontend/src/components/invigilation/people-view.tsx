"use client";
/**
 * Load per person: duties, periods (the fairness measure, scaled by the person's load factor in the solver), own-exam
 * duties, duty days and the busiest day (`GET …/load`), sortable. A row opens that person's duties; "Kurallar"
 * opens their pool rules (unavailability, caps, load factor), linked to the instructor record when there is one.
 */
import { CalendarCog, ListFilter } from "lucide-react";
import { useMemo, useState } from "react";
import { BarList } from "@/components/ui/bar-list";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { IconButton } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useMe } from "@/lib/api/hooks";
import { instructorIdOf, usePlanLoad, usePool, type PersonLoad, type PlanDetail } from "@/lib/api/invigilation";
import { useI18n } from "@/lib/i18n/provider";
import { PoolMemberDialog } from "./pool-form";

type Row = PersonLoad & { maxPerDay: number | null; dates: number | null };
const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i");

export function PeopleView({ plan, canEdit, onPerson }: { plan: PlanDetail; canEdit: boolean; onPerson: (key: string) => void }) {
  const { t, n } = useI18n();
  const me = useMe();
  const load = usePlanLoad(plan.id);
  const pool = usePool(plan.term_id);
  const [query, setQuery] = useState("");
  const [rules, setRules] = useState<{ personKey: string; name: string } | null>(null);
  const loadBy = useMemo(() => new Map((load.data?.rows ?? []).map((r) => [r.person_key, r])), [load.data]);
  const rows = useMemo<Row[]>(() => {
    const f = fold(query.trim());
    return plan.people
      .filter((p) => !f || fold(p.name).includes(f))
      .map((p) => ({ ...p, maxPerDay: loadBy.get(p.person_key)?.max_per_day ?? null, dates: loadBy.get(p.person_key)?.cells.length ?? null }));
  }, [plan.people, loadBy, query]);
  const member = (key: string) => (pool.data ?? []).find((m) => m.person_key === key || (instructorIdOf(key) !== null && m.instructor_id === instructorIdOf(key)));
  const fair = typeof plan.stats.fair_share_periods === "number" ? plan.stats.fair_share_periods : null;

  const columns = useMemo<DataColumn<Row>[]>(
    () => [
      { id: "name", header: t("invigilation.people.name"), pin: "left", priority: 1, grow: 2, minSize: 160, maxSize: 380, text: (r) => r.name, sortValue: (r) => r.name, cell: (r) => <span className="truncate font-medium">{r.name}</span> },
      { id: "periods", header: t("invigilation.people.periods"), align: "end", priority: 1, text: (r) => String(r.periods), sortValue: (r) => r.periods, cell: (r) => <span className="tnum">{n(r.periods)}</span> },
      { id: "duties", header: t("invigilation.people.duties"), align: "end", priority: 2, text: (r) => String(r.duties), sortValue: (r) => r.duties, cell: (r) => <span className="tnum">{n(r.duties)}</span> },
      { id: "own", header: t("invigilation.people.own"), align: "end", priority: 3, text: (r) => String(r.own_exam), sortValue: (r) => r.own_exam, cell: (r) => <span className="tnum">{n(r.own_exam)}</span> },
      { id: "days", header: t("invigilation.people.days"), align: "end", priority: 3, text: (r) => String(r.days), sortValue: (r) => r.days, cell: (r) => <span className="tnum">{n(r.days)}</span> },
      { id: "maxDay", header: t("invigilation.people.maxDay"), align: "end", priority: 4, text: (r) => String(r.maxPerDay ?? "—"), sortValue: (r) => r.maxPerDay ?? -1, cell: (r) => <span className="tnum">{r.maxPerDay === null ? "—" : n(r.maxPerDay)}</span> },
      {
        id: "act",
        header: t("common.actions"),
        hideable: false,
        priority: 2,
        size: canEdit ? 76 : 44,
        cell: (r) => (
          <span className="flex gap-1">
            <IconButton size="xs" className="max-md:size-11" label={t("invigilation.people.showDuties", { name: r.name })} onClick={(e) => (e.stopPropagation(), onPerson(r.person_key))} data-testid="invig-person-duties">
              <ListFilter aria-hidden />
            </IconButton>
            {canEdit ? (
              <IconButton size="xs" className="max-md:size-11" label={t("invigilation.people.rules", { name: r.name })} onClick={(e) => (e.stopPropagation(), setRules({ personKey: r.person_key, name: r.name }))} data-testid="invig-person-rules">
                <CalendarCog aria-hidden />
              </IconButton>
            ) : null}
          </span>
        ),
      },
    ],
    [t, n, canEdit, onPerson],
  );
  const top = plan.people.slice(0, 8);
  const target = rules ? member(rules.personKey) : undefined;

  return (
    <section className="flex flex-col gap-3" aria-label={t("invigilation.view.people")} data-testid="invig-people">
      {fair !== null ? <p className="type-footnote text-label-2 tnum">{t("invigilation.people.fair", { fair: n(fair) })}</p> : null}
      {top.length ? <BarList aria-label={t("invigilation.people.top")} items={top.map((p) => ({ key: p.person_key, label: p.name, value: p.periods, display: n(p.periods) }))} max={Math.max(fair ?? 0, ...top.map((p) => p.periods))} /> : null}
      <DataTable
        tableId="invig-people"
        userId={me.data?.id}
        label={t("invigilation.view.people")}
        columns={columns}
        rows={rows}
        getRowId={(r) => r.person_key}
        onRowActivate={(r) => onPerson(r.person_key)}
        rowProps={() => ({ "data-testid": "invig-person-row" })}
        defaultSort={[{ id: "periods", desc: true }]}
        maxHeight="min(70dvh, 40rem)"
        toolbar={<Input fieldSize="sm" type="search" className="w-56" placeholder={t("invigilation.people.search")} aria-label={t("invigilation.people.search")} value={query} onChange={(e) => setQuery(e.target.value)} />}
        empty={<p className="px-3 py-6 type-callout text-label-2">{t("invigilation.people.none")}</p>}
      />
      {rules ? (
        <PoolMemberDialog
          open
          onOpenChange={(o) => !o && setRules(null)}
          termId={plan.term_id}
          member={target ?? null}
          prefill={{ full_name: rules.name, instructor_id: instructorIdOf(rules.personKey), kind: instructorIdOf(rules.personKey) !== null ? "INSTRUCTOR" : "STAFF" }}
        />
      ) : null}
    </section>
  );
}
