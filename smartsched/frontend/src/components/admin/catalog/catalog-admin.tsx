"use client";
/**
 * Yönetim › Katalog (RF-05, owner request 2026-10-17): the institution data the workbooks imported — instructors,
 * courses, programmes, faculties and the term's sections — one searchable list per entity, an obvious "Yeni", and an
 * edit sheet ("Son değişiklik", the few common fields, the rest under "Gelişmiş", delete with its consequences).
 * Reading needs planning.view, writing planning.edit (the backend checks both again and audits every write).
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { catalogAdminApi, type Course, type Instructor, type ProgramRow, type SectionRow } from "@/lib/api/catalog-admin";
import { useI18n } from "@/lib/i18n/provider";
import { useFinePointer } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { Loading, PageTitle } from "../kit";
import { CatalogForm, SectionsLead, rowTitle, type CatalogRow } from "./catalog-forms";
import { CATALOG_TABS, hoursText, numText, type CatalogTab } from "./catalog-model";

const PAGE = 100;

interface Column {
  id: string;
  header: string;
  cell: (r: CatalogRow) => string;
  className?: string;
  numeric?: boolean;
}

function useDebounced<V>(value: V, ms: number): V {
  const [v, setV] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setV(value), ms);
    return () => clearTimeout(h);
  }, [value, ms]);
  return v;
}

function fetchPage(tab: CatalogTab, search: string, offset: number, termId: number | undefined) {
  const q = { search, limit: PAGE, offset };
  switch (tab) {
    case "instructors":
      return catalogAdminApi.instructorsPage(q);
    case "courses":
      return catalogAdminApi.coursesPage(q);
    case "programs":
      return catalogAdminApi.programsPage(q);
    case "faculties":
      return catalogAdminApi.facultiesPage(q);
    case "sections":
      return catalogAdminApi.sectionsPage({ ...q, term_id: termId ?? 0 });
  }
}

export function CatalogAdmin({ tab }: { tab: CatalogTab }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const canEdit = can("planning.edit");
  const conf = CATALOG_TABS.find((x) => x.id === tab) ?? CATALOG_TABS[0];
  const phone = useIsPhone();
  const fine = useFinePointer();
  const [q, setQ] = useState("");
  const search = useDebounced(q.trim(), 250);
  const { term, isLoading: termLoading } = useActiveTerm({ enabled: tab === "sections" });
  const termId = tab === "sections" ? term?.id : undefined;
  const list = useInfiniteQuery({
    queryKey: ["catalog", tab, search, termId ?? null],
    queryFn: ({ pageParam }) => fetchPage(tab, search, pageParam, termId),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined),
    enabled: tab !== "sections" || !!termId,
    retry: false,
  });
  const faculties = useQuery({ queryKey: ["catalog", "faculty-options"], queryFn: () => catalogAdminApi.facultiesPage({ limit: 500 }), enabled: tab === "programs", staleTime: 60_000 });
  const facultyName = new Map((faculties.data?.items ?? []).map((f) => [f.id, f.name]));
  const rows: CatalogRow[] = (list.data?.pages ?? []).flatMap((p) => p.items as CatalogRow[]);
  const total = list.data?.pages[0]?.total ?? 0;
  const [editing, setEditing] = useState<{ row: CatalogRow | null } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const lastId = useRef<number | null>(null);

  const yes = t("crbs.common.yes");
  const columns: Column[] = (() => {
    switch (tab) {
      case "instructors":
        return [
          { id: "title", header: t("catalog.col.title"), cell: (r) => (r as Instructor).title ?? "" },
          { id: "email", header: t("catalog.col.email"), cell: (r) => (r as Instructor).email ?? "", className: "hidden md:table-cell" },
        ];
      case "courses":
        return [
          { id: "name", header: t("catalog.col.courseName"), cell: (r) => (r as Course).name ?? "" },
          { id: "hours", header: t("catalog.col.hours"), cell: (r) => hoursText(r as Course), className: "hidden md:table-cell", numeric: true },
          { id: "ects", header: t("catalog.col.ects"), cell: (r) => numText((r as Course).ects, locale), className: "hidden md:table-cell", numeric: true },
        ];
      case "programs":
        return [
          { id: "faculty", header: t("catalog.col.faculty"), cell: (r) => facultyName.get((r as ProgramRow).faculty_id ?? -1) ?? "" },
          { id: "evening", header: t("catalog.col.evening"), cell: (r) => ((r as ProgramRow).is_evening ? yes : ""), className: "hidden md:table-cell" },
        ];
      case "faculties":
        return [];
      case "sections":
        return [
          { id: "name", header: t("catalog.col.courseName"), cell: (r) => (r as SectionRow).course_name ?? "" },
          { id: "program", header: t("catalog.col.program"), cell: (r) => (r as SectionRow).program_name ?? "", className: "hidden lg:table-cell" },
          { id: "students", header: t("catalog.col.students"), cell: (r) => numText((r as SectionRow).enrolment, locale), numeric: true },
          { id: "mode", header: t("catalog.col.mode"), cell: (r) => t(`catalog.mode.${(r as SectionRow).mode as "F2F"}`), className: "hidden md:table-cell" },
        ];
    }
  })();
  const firstHeader = {
    instructors: t("catalog.col.name"),
    courses: t("catalog.col.code"),
    programs: t("catalog.col.programName"),
    faculties: t("catalog.col.facultyName"),
    sections: t("catalog.col.course"),
  }[tab];
  const firstCell = (r: CatalogRow) => (tab === "courses" ? (r as Course).display_code : rowTitle(tab, r));

  const open = (row: CatalogRow | null) => {
    lastId.current = row?.id ?? null;
    setEditing({ row });
  };
  const rowEl = (id: number) => document.querySelector<HTMLElement>(`[data-catalog-row="${id}"]`);

  return (
    <div className="flex flex-col gap-4">
      <PageTitle
        className="mb-0"
        title={t("catalog.title")}
        subtitle={t("catalog.lead")}
        actions={
          canEdit && conf.canCreate ? (
            <Button className="pointer-coarse:h-11" onClick={() => open(null)} data-testid="catalog-new">
              <Plus aria-hidden />
              {t("catalog.new")}
            </Button>
          ) : undefined
        }
      />
      <nav aria-label={t("catalog.tabsLabel")} className="-mx-1 overflow-x-auto px-1 pb-1 scrollbar-thin">
        <ul className="flex w-max gap-1">
          {CATALOG_TABS.map((x) => (
            <li key={x.id}>
              <Link
                href={x.href}
                aria-current={x.id === tab ? "page" : undefined}
                className={cn(
                  "inline-flex h-8 items-center rounded-full px-3.5 type-callout font-medium whitespace-nowrap pointer-coarse:h-11 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)",
                  x.id === tab ? "bg-tint-soft text-tint-text" : "text-label-2 hover:bg-fill-2 hover:text-label-1",
                )}
                data-testid={`catalog-tab-${x.id}`}
              >
                {t(x.labelKey)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {tab === "sections" && term ? <SectionsLead term={term.name || term.code} /> : null}
      {!canEdit ? <Alert tone="info">{t("catalog.readOnly")}</Alert> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          ref={searchRef}
          type="search"
          className="max-w-sm max-sm:max-w-none"
          aria-label={t("catalog.searchLabel")}
          placeholder={t(`catalog.search.${tab}`)}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="catalog-search"
        />
        {list.isSuccess ? (
          <span className="type-footnote text-label-2" role="status" data-testid="catalog-count">
            {rows.length < total ? t("catalog.countOf", { shown: rows.length, n: total }) : t("catalog.count", { n: total })}
          </span>
        ) : null}
      </div>
      <Card className="py-0">
        {tab === "sections" && !termLoading && !term ? (
          <p className="px-4 py-6 type-callout text-label-2">{t("catalog.noTerm")}</p>
        ) : list.isLoading || (tab === "sections" && termLoading) ? (
          <Loading className="px-4" />
        ) : list.isError ? (
          <div className="flex items-center gap-3 px-4 py-6">
            <p className="type-callout text-label-2">{t("catalog.loadError")}</p>
            <Button variant="secondary" className="pointer-coarse:h-11" onClick={() => void list.refetch()}>
              {t("catalog.retry")}
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <p className="px-4 py-6 type-callout text-label-2" data-testid="catalog-empty">
            {search ? t("catalog.emptySearch", { q: search }) : t("catalog.empty")}
          </p>
        ) : phone ? (
          /* phones (MOBILE.md M-07): one 44 px+ card per record, the name on line 1, the rest on line 2 */
          <ul aria-label={t(conf.labelKey)} data-testid="catalog-cards">
            {rows.map((r) => {
              const sub = columns.map((c) => c.cell(r)).filter(Boolean).join(" · ");
              return (
                <li key={r.id} className="not-last:edge-hairline-b">
                  <Button variant="bare" className="flex min-h-14 w-full items-center gap-3 px-4 py-2.5 text-left" data-catalog-row={r.id} onClick={() => open(r)} aria-label={t(canEdit ? "catalog.editNamed" : "catalog.openNamed", { name: rowTitle(tab, r) })}>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate type-headline text-label-1">{firstCell(r)}</span>
                      {sub ? <span className="block truncate type-footnote text-label-2">{sub}</span> : null}
                    </span>
                    <Pencil className="size-4 shrink-0 text-label-3" aria-hidden />
                  </Button>
                </li>
              );
            })}
          </ul>
        ) : (
          <Table data-testid="catalog-table">
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{firstHeader}</TableHead>
                {columns.map((c) => (
                  <TableHead key={c.id} className={cn(c.className, c.numeric && "text-right")}>
                    {c.header}
                  </TableHead>
                ))}
                <TableHead className="w-14 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={`catalog-row-${r.id}`}>
                  <TableCell className="pl-4 font-medium text-label-1">{firstCell(r)}</TableCell>
                  {columns.map((c) => (
                    <TableCell key={c.id} className={cn("text-label-2", c.className, c.numeric && "text-right tabular-nums")}>
                      {c.cell(r)}
                    </TableCell>
                  ))}
                  <TableCell className="pr-4 text-right">
                    <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-11" data-catalog-row={r.id} aria-label={t(canEdit ? "catalog.editNamed" : "catalog.openNamed", { name: rowTitle(tab, r) })} onClick={() => open(r)}>
                      <Pencil />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
      {list.hasNextPage ? (
        <Button variant="secondary" className="self-center pointer-coarse:h-11" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage} data-testid="catalog-more">
          {t("catalog.more")}
        </Button>
      ) : null}
      <Sheet open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <SheetContent
          side={fine ? "right" : "bottom"}
          className="flex flex-col gap-0 overflow-y-auto sm:max-w-md"
          data-testid="catalog-sheet"
          // focus goes back to the row's button, or to the search box when the row is gone (deleted, new)
          finalFocus={() => (lastId.current !== null ? rowEl(lastId.current) : null) ?? searchRef.current ?? true}
        >
          {editing ? (
            <CatalogForm
              key={`${tab}-${editing.row?.id ?? "new"}`}
              tab={tab}
              row={editing.row}
              canEdit={canEdit}
              onDone={(outcome) => {
                if (outcome === "deleted") lastId.current = null;
                setEditing(null);
              }}
            />
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
