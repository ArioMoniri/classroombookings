"use client";

import { type ColumnDef, flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, type SortingState, useReactTable } from "@tanstack/react-table";
import { AlertTriangle, Info, XOctagon } from "lucide-react";
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ParseWarning } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

type Severity = ParseWarning["severity"];
const ORDER: Record<Severity, number> = { error: 0, warning: 1, info: 2 };

export function countBySeverity(warnings: readonly ParseWarning[]): Record<Severity, number> {
  const out: Record<Severity, number> = { error: 0, warning: 0, info: 0 };
  for (const w of warnings) out[w.severity]++;
  return out;
}

export function SeverityIcon({ severity, className }: { severity: Severity; className?: string }) {
  const Icon = severity === "error" ? XOctagon : severity === "warning" ? AlertTriangle : Info;
  const colour = severity === "error" ? "text-status-infeasible-fg" : severity === "warning" ? "text-status-warning-fg" : "text-muted-foreground";
  return <Icon className={cn("size-4", colour, className)} aria-hidden />;
}

export function ParseWarningsTable({ warnings }: { warnings: readonly ParseWarning[] }) {
  const { t } = useI18n();
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [query, setQuery] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "severity", desc: false }]);
  const counts = useMemo(() => countBySeverity(warnings), [warnings]);

  const data = useMemo(() => {
    const q = query.toLocaleLowerCase("tr-TR");
    return warnings.filter((w) => (severity === "all" || w.severity === severity) && (!q || `${w.field} ${w.value ?? ""} ${w.message} ${w.row}`.toLocaleLowerCase("tr-TR").includes(q)));
  }, [warnings, severity, query]);

  const columns = useMemo<ColumnDef<ParseWarning>[]>(
    () => [
      { id: "severity", accessorFn: (w) => ORDER[w.severity], header: t("import.severity"), cell: ({ row }) => <span className="inline-flex items-center gap-1.5"><SeverityIcon severity={row.original.severity} />{t(`import.${row.original.severity}`)}</span> },
      { accessorKey: "row", header: t("import.row"), cell: ({ getValue }) => <span className="font-mono tabular-nums">{getValue<number>()}</span> },
      { accessorKey: "field", header: t("import.field") },
      { accessorKey: "value", header: t("import.value"), cell: ({ getValue }) => <span className="font-mono text-xs break-all">{getValue<string | null>() ?? "—"}</span> },
      { accessorKey: "message", header: t("import.message") },
    ],
    [t],
  );

  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel() });

  if (warnings.length === 0) return <p className="rounded-md border border-status-feasible-border bg-status-feasible px-3 py-2 text-sm text-status-feasible-fg" role="status">{t("import.noWarnings")}</p>;

  return (
    <div data-testid="parse-warnings">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("import.filterSeverity")} className="flex gap-1">
          {(["all", "error", "warning", "info"] as const).map((s) => (
            <button key={s} type="button" aria-pressed={severity === s} onClick={() => setSeverity(s)} className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs", severity === s ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>
              {s !== "all" ? <SeverityIcon severity={s} className={severity === s ? "text-primary-foreground" : undefined} /> : null}
              {s === "all" ? t("common.all") : t(`import.${s}`)} <span className="tabular-nums opacity-80">{s === "all" ? warnings.length : counts[s]}</span>
            </button>
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
                    <button type="button" className="inline-flex items-center gap-1 font-medium" onClick={h.column.getToggleSortingHandler()}>
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      <span aria-hidden className="text-muted-foreground">{{ asc: "↑", desc: "↓" }[h.column.getIsSorted() as string] ?? ""}</span>
                    </button>
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
