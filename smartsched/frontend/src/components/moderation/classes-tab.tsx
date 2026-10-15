"use client";
/**
 * Moderasyon › Sınıflar: the /classes table core (ClassTable, "Filtre +", filter chips; all-classes.md §5–§10)
 * over the published plan, read-only here. Opening a row shows the matching inspector (request → assignment,
 * reason, priority); full editing (inline cells, bulk lock / move, saved views) stays on /classes.
 */
import type { SortingState } from "@tanstack/react-table";
import { ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { ClassTable } from "@/components/classes/class-table";
import { EMPTY, applyFilters, type ClassFilters } from "@/components/classes/classes-model";
import { FilterChips, FilterMenu } from "@/components/classes/filter-bar";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useClasses } from "@/lib/api/classes";
import { useI18n } from "@/lib/i18n/provider";

const COLUMNS = ["status", "course", "program", "instructor", "students", "reqTime", "placement", "fit", "changed"];
const NONE = new Set<number>();
const NO_IDS = new Set<string>();

export function ClassesTab({ termId, runId, onOpen }: { termId: number; runId: number | null; onOpen: (requestId: number) => void }) {
  const { t, n } = useI18n();
  const classes = useClasses(termId, "meetings", runId);
  const [filters, setFilters] = useState<ClassFilters>(EMPTY);
  const [sort, setSort] = useState<SortingState>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [active, setActive] = useState<number | null>(null);
  const filterRef = useRef<HTMLButtonElement>(null);
  const all = useMemo(() => classes.data?.items ?? [], [classes.data]);
  const rows = useMemo(() => applyFilters(all, filters), [all, filters]);

  if (classes.isError) {
    return (
      <div role="alert" className="flex items-center gap-2 type-callout text-label-2">
        {t("moderation.loadError")}
        <Button size="sm" variant="ghost" onClick={() => void classes.refetch()}>{t("common.retry")}</Button>
      </div>
    );
  }
  if (!classes.data) {
    return (
      <div className="flex flex-col gap-1" aria-busy>
        {Array.from({ length: 12 }, (_, i) => <Skeleton key={i} className="h-8 w-full" />)}
      </div>
    );
  }
  if (all.length === 0) {
    return (
      <EmptyState
        title={t("moderation.empty.classes")}
        description={t("moderation.empty.classesHint")}
        actions={
          <>
            <Button size="sm" render={<Link href="/onboarding" />} nativeButton={false}>{t("moderation.empty.import")}</Button>
            <Button size="sm" variant="outline" render={<Link href="/programs/new" />} nativeButton={false}>{t("moderation.empty.newProgram")}</Button>
          </>
        }
      />
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="mod-classes">
      <div className="flex flex-wrap items-center gap-2">
        <FilterMenu rows={all} filters={filters} onChange={setFilters} shownCount={rows.length} triggerRef={filterRef} />
        <label className="relative block w-full sm:w-72">
          <span className="sr-only">{t("moderation.search")}</span>
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-label-3" aria-hidden />
          <Input value={filters.text} onChange={(e) => setFilters({ ...filters, text: e.target.value })} placeholder={t("moderation.searchPh")} className="pl-8" />
        </label>
        <span className="type-footnote text-label-2 tabular-nums" aria-live="polite">{t("moderation.caption.classes", { shown: n(rows.length), total: n(all.length) })}</span>
        <Button size="sm" variant="ghost" className="ml-auto" render={<Link href={runId ? `/classes?run=${runId}` : "/classes"} />} nativeButton={false}>
          <ExternalLink aria-hidden />
          {t("moderation.openClasses")}
        </Button>
      </div>
      <FilterChips rows={all} filters={filters} onChange={setFilters} />
      <div className="h-[min(70vh,640px)] min-h-96">
        <ClassTable
          rows={rows}
          columns={COLUMNS}
          sort={sort}
          onSort={setSort}
          group={null}
          subgroup={null}
          collapsed={collapsed}
          onCollapsed={setCollapsed}
          density="standard"
          selection={NONE}
          onSelection={() => undefined}
          activeId={active}
          onOpen={(r) => {
            setActive(r.id);
            onOpen(r.id);
          }}
          onCommit={async () => false}
          onToggleLock={() => undefined}
          onQuickFilter={() => undefined}
          onKeyAction={() => false}
          readOnly
          savingIds={NO_IDS}
          label={t("moderation.caption.classes", { shown: n(rows.length), total: n(all.length) })}
        />
      </div>
    </div>
  );
}
