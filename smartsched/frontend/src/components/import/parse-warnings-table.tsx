"use client";

import { type ColumnDef, flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, type SortingState, useReactTable } from "@tanstack/react-table";
import { AlertTriangle, Info, XOctagon } from "lucide-react";
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ParseWarning, WarningGroup } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { BareButton } from "@/components/shell/bare-button";
import { warningTr } from "./warning-tr";

type Severity = ParseWarning["severity"];
const ORDER: Record<Severity, number> = { error: 0, warning: 1, info: 2 };

export function countBySeverity(warnings: readonly ParseWarning[]): Record<Severity, number> {
  const out: Record<Severity, number> = { error: 0, warning: 0, info: 0 };
  for (const w of warnings) out[w.severity]++;
  return out;
}

/** The import listed only the first warnings (M-21): "{count} uyarı, ilk {shown} gösteriliyor". Nothing otherwise. */
export function TruncatedWarnings({ summary }: { summary: { warnings_count?: number; warnings_shown?: number; warnings_truncated?: boolean } }) {
  const { t, n } = useI18n();
  if (!summary.warnings_truncated || summary.warnings_count == null || summary.warnings_shown == null) return null;
  return (
    <p className="flex items-center gap-1.5 type-footnote text-label-2" role="note" data-testid="warnings-truncated">
      <Info className="size-4 shrink-0 text-label-3" aria-hidden />
      {t("import.warningsTruncated", { count: n(summary.warnings_count), shown: n(summary.warnings_shown) })}
    </p>
  );
}

export function SeverityIcon({ severity, className }: { severity: Severity; className?: string }) {
  const Icon = severity === "error" ? XOctagon : severity === "warning" ? AlertTriangle : Info;
  const colour = severity === "error" ? "text-status-infeasible-fg" : severity === "warning" ? "text-status-warning-fg" : "text-muted-foreground";
  return <Icon className={cn("size-4", colour, className)} aria-hidden />;
}

/** The sentence of one warning in the reader's language: the importer's own (PER-F05), else the client's reading. */
export function warningText(w: ParseWarning, locale: string): string {
  if (locale === "tr") return w.message_tr ?? warningTr(w.message);
  return w.message_en ?? w.message;
}

/**
 * PER-F05 (fix-h-2026-10-18): the import's warnings by kind, the biggest first ("Kişi olmayan öğretim elemanı değeri ·
 * 37 satır"), each opening to its sentences and row numbers; the table below keeps every row.
 */
export function WarningGroups({ groups }: { groups: readonly WarningGroup[] }) {
  const { t, n, locale } = useI18n();
  if (!groups.length) return null;
  const tr = locale === "tr";
  return (
    <section aria-label={t("import.groupsTitle")} className="flex flex-col gap-1.5" data-testid="warning-groups">
      <h4 className="type-subheadline font-semibold text-label-1">{t("import.groupsTitle")}</h4>
      <ul className="flex flex-col gap-1">
        {groups.map((g) => (
          <li key={g.code}>
            <details className="group rounded-lg bg-fill-3 px-3 py-1.5" data-testid={`warning-group-${g.code}`}>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 type-callout text-label-1 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) pointer-coarse:min-h-11">
                <span className="min-w-0">{tr ? g.label_tr : g.label_en}</span>
                <span className="shrink-0 type-footnote text-label-2 tabular-nums">{t("import.groupRows", { n: n(g.count) })}</span>
              </summary>
              <ul className="mt-1 flex flex-col gap-1 pb-1">
                {g.items.map((it) => (
                  <li key={it.message_tr} className="type-footnote text-label-1">
                    {tr ? it.message_tr : it.message_en}
                    <span className="text-label-3 tabular-nums">
                      {" · "}
                      {it.rows.length ? t("import.groupAt", { rows: it.rows.join(", ") + (it.count > it.rows.length ? " …" : "") }) : t("import.groupRows", { n: n(it.count) })}
                    </span>
                  </li>
                ))}
                {(g.variants ?? g.items.length) > g.items.length ? <li className="type-footnote text-label-3">{t("import.groupMore", { n: n((g.variants ?? 0) - g.items.length) })}</li> : null}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ParseWarningsTable({ warnings, groups }: { warnings: readonly ParseWarning[]; groups?: readonly WarningGroup[] }) {
  const { t, locale } = useI18n();
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [query, setQuery] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "severity", desc: false }]);
  const counts = useMemo(() => countBySeverity(warnings), [warnings]);

  const data = useMemo(() => {
    const q = query.toLocaleLowerCase("tr-TR");
    return warnings.filter((w) => (severity === "all" || w.severity === severity) && (!q || `${w.field} ${w.value ?? ""} ${w.message} ${warningText(w, "tr")} ${w.row}`.toLocaleLowerCase("tr-TR").includes(q)));
  }, [warnings, severity, query]);

  const columns = useMemo<ColumnDef<ParseWarning>[]>(
    () => [
      { id: "severity", accessorFn: (w) => ORDER[w.severity], header: t("import.severity"), cell: ({ row }) => <span className="inline-flex items-center gap-1.5"><SeverityIcon severity={row.original.severity} />{t(`import.${row.original.severity}`)}</span> },
      { accessorKey: "row", header: t("import.row"), cell: ({ getValue }) => <span className="font-mono tabular-nums">{getValue<number>()}</span> },
      { accessorKey: "field", header: t("import.field") },
      { accessorKey: "value", header: t("import.value"), cell: ({ getValue }) => <span className="font-mono text-xs break-all">{getValue<string | null>() ?? "—"}</span> },
      // PER-F05: the importer's own Turkish sentence (fix-h), else the client's reading (unknown shapes stay as written)
      { accessorKey: "message", header: t("import.message"), cell: ({ row }) => warningText(row.original, locale) },
    ],
    [t, locale],
  );

  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel() });

  if (warnings.length === 0) return <p className="rounded-md border border-status-feasible-border bg-status-feasible px-3 py-2 text-sm text-status-feasible-fg" role="status">{t("import.noWarnings")}</p>;

  return (
    <div data-testid="parse-warnings">
      {groups?.length ? <div className="mb-3"><WarningGroups groups={groups} /></div> : null}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("import.filterSeverity")} className="flex gap-1">
          {(["all", "error", "warning", "info"] as const).map((s) => (
            <BareButton key={s} aria-pressed={severity === s} onClick={() => setSeverity(s)} className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs", severity === s ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>
              {s !== "all" ? <SeverityIcon severity={s} className={severity === s ? "text-primary-foreground" : undefined} /> : null}
              {s === "all" ? t("common.all") : t(`import.${s}`)} <span className="tabular-nums opacity-80">{s === "all" ? warnings.length : counts[s]}</span>
            </BareButton>
          ))}
        </div>
        <Input aria-label={t("common.search")} placeholder={t("common.search")} value={query} onChange={(e) => setQuery(e.target.value)} className="ml-auto w-full sm:w-56" />
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <caption className="sr-only">{t("import.warningsTable")}: {data.length}</caption>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id} aria-sort={h.column.getIsSorted() === "asc" ? "ascending" : h.column.getIsSorted() === "desc" ? "descending" : "none"}>
                    <BareButton className="inline-flex items-center gap-1 font-medium" onClick={h.column.getToggleSortingHandler()}>
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      <span aria-hidden className="text-muted-foreground">{{ asc: "↑", desc: "↓" }[h.column.getIsSorted() as string] ?? ""}</span>
                    </BareButton>
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id} data-severity={row.original.severity}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className="align-top">{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                ))}
              </TableRow>
            ))}
            {table.getRowModel().rows.length === 0 ? <TableRow><TableCell colSpan={5} className="text-muted-foreground">{t("common.noData")}</TableCell></TableRow> : null}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
