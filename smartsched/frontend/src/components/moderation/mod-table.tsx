"use client";
/**
 * The moderation tables (Kişiler, Talepler, Tercihler, Eşleşmeler, the re-solve preview): virtualised 36 px
 * rows, sticky header, `role="grid"` with a roving row focus (`j`/`k`, ↑/↓, Home/End, Enter), a caption with
 * the counts, and cards on phones. Same keyboard map as /classes (all-classes.md §11). The column system of
 * the design-system DataTable replaces the fixed tracks here once it lands.
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ModColumn<T> {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** CSS grid track, e.g. `minmax(12rem,2fr)` */
  width: string;
  align?: "start" | "end";
}

interface Props<T> {
  rows: readonly T[];
  columns: readonly ModColumn<T>[];
  getId: (row: T) => number | string;
  caption: string;
  onOpen?: (row: T) => void;
  /** a row key the table did not handle (`e`, `p`, `x`, …); return true when handled */
  onKey?: (key: string, row: T, e: KeyboardEvent) => boolean;
  activeId?: number | string | null;
  /** phones: one card per row instead of the grid */
  card?: (row: T) => ReactNode;
  mobile?: boolean;
  height?: number;
  empty?: ReactNode;
  testId?: string;
  rowTestId?: string;
}

export const ROW_H = 36;

export function ModTable<T>({ rows, columns, getId, caption, onOpen, onKey, activeId = null, card, mobile = false, height = 560, empty, testId, rowTestId = "mod-row" }: Props<T>) {
  const scroller = useRef<HTMLDivElement>(null);
  const [focus, setFocus] = useState(0);
  const useCards = mobile && !!card;
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => (useCards ? 92 : ROW_H),
    overscan: 12,
    measureElement: useCards ? (el) => el.getBoundingClientRect().height : undefined,
  });
  // the row list changed under the focus (filter, tab): keep the index in range, never jump to the page top
  const index = Math.min(focus, Math.max(0, rows.length - 1));
  const template = columns.map((c) => c.width).join(" ");

  const focusRow = (i: number) => {
    const next = Math.max(0, Math.min(rows.length - 1, i));
    setFocus(next);
    virtual.scrollToIndex(next, { align: "auto" });
    window.requestAnimationFrame(() => scroller.current?.querySelector<HTMLElement>(`[data-index="${next}"]`)?.focus());
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const row = rows[index];
    switch (e.key) {
      case "j":
      case "ArrowDown":
        e.preventDefault();
        focusRow(index + 1);
        return;
      case "k":
      case "ArrowUp":
        e.preventDefault();
        focusRow(index - 1);
        return;
      case "Home":
        e.preventDefault();
        focusRow(0);
        return;
      case "End":
        e.preventDefault();
        focusRow(rows.length - 1);
        return;
      case "Enter":
        if (row && onOpen) {
          e.preventDefault();
          onOpen(row);
        }
        return;
      default:
        if (row && onKey?.(e.key, row, e)) e.preventDefault();
    }
  };

  useEffect(() => {
    if (focus > rows.length - 1 && rows.length) setFocus(rows.length - 1);
  }, [rows.length, focus]);

  if (rows.length === 0) return <>{empty}</>;

  return (
    <div
      ref={scroller}
      role="grid"
      aria-rowcount={rows.length + 1}
      aria-colcount={columns.length}
      aria-label={caption}
      data-testid={testId}
      onKeyDown={onKeyDown}
      className="relative overflow-auto rounded-xl border border-hairline bg-card"
      style={{ maxHeight: height }}
    >
      <p className="sr-only" aria-live="polite">{caption}</p>
      {!useCards ? (
        <div role="row" aria-rowindex={1} className="sticky top-0 z-10 grid min-w-max items-center gap-3 border-b border-hairline bg-(--mat-thick-solid) px-3 type-caption font-semibold text-label-2" style={{ gridTemplateColumns: template, height: ROW_H }}>
          {columns.map((c) => (
            <div key={c.id} role="columnheader" className={cn("truncate", c.align === "end" && "text-right")}>
              {c.header}
            </div>
          ))}
        </div>
      ) : null}
      <div className="relative min-w-max" style={{ height: virtual.getTotalSize() }}>
        {virtual.getVirtualItems().map((v) => {
          const row = rows[v.index]!;
          const id = getId(row);
          const active = activeId !== null && activeId === id;
          return (
            <div
              key={String(id)}
              ref={useCards ? virtual.measureElement : undefined}
              role="row"
              aria-rowindex={v.index + 2}
              aria-selected={active || undefined}
              data-index={v.index}
              data-testid={rowTestId}
              data-row-id={String(id)}
              tabIndex={v.index === index ? 0 : -1}
              onFocus={() => setFocus(v.index)}
              onClick={() => {
                setFocus(v.index);
                onOpen?.(row);
              }}
              className={cn(
                "absolute inset-x-0 cursor-default outline-hidden focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-solid focus-visible:outline-(--focus)",
                useCards ? "px-2 py-1" : "grid items-center gap-3 border-b border-hairline px-3 type-callout text-label-1 hover:bg-fill-3",
                active && "bg-tint-soft",
              )}
              style={{ transform: `translateY(${v.start}px)`, ...(useCards ? {} : { height: ROW_H, gridTemplateColumns: template }) }}
            >
              {useCards ? (
                card!(row)
              ) : (
                columns.map((c) => (
                  <div key={c.id} role="gridcell" className={cn("min-w-0 truncate", c.align === "end" && "text-right tabular-nums")}>
                    {c.cell(row)}
                  </div>
                ))
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
