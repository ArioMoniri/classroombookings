"use client";

import { type Table as TableInstance, flexRender } from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface Props<T> {
  table: TableInstance<T>;
  emptyLabel: string;
  selectedId?: number | null;
  getId: (row: T) => number;
  onSelect?: (row: T) => void;
  rowTestId?: string;
}

/** Generic sortable TanStack table renderer (one `Table` instance, any row type). */
export function DataTable<T>({ table, emptyLabel, selectedId, getId, onSelect, rowTestId }: Props<T>) {
  const rows = table.getRowModel().rows;
  const colCount = table.getAllLeafColumns().length;
  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((hg) => (
          <TableRow key={hg.id}>
            {hg.headers.map((h) => {
              const sorted = h.column.getIsSorted();
              return (
                <TableHead key={h.id} aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"} className="whitespace-nowrap">
                  {h.column.getCanSort() ? (
                    <button type="button" className="inline-flex items-center gap-1 font-medium" onClick={h.column.getToggleSortingHandler()}>
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      <span aria-hidden className="text-muted-foreground">{sorted === "asc" ? "↑" : sorted === "desc" ? "↓" : ""}</span>
                    </button>
                  ) : (
                    flexRender(h.column.columnDef.header, h.getContext())
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const id = getId(row.original);
          const selected = selectedId !== undefined && selectedId === id;
          return (
            <TableRow
              key={row.id}
              tabIndex={onSelect ? 0 : undefined}
              data-testid={rowTestId}
              onClick={onSelect ? () => onSelect(row.original) : undefined}
              onKeyDown={onSelect ? (e) => { if (e.key === "Enter") onSelect(row.original); } : undefined}
              className={cn(onSelect && "cursor-pointer", selected && "bg-primary-tint")}
              aria-selected={onSelect ? selected : undefined}
            >
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id} className="align-top">{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
              ))}
            </TableRow>
          );
        })}
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={colCount} className="py-8 text-center text-muted-foreground">{emptyLabel}</TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
}
