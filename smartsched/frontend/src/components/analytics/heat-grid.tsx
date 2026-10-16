"use client";
/**
 * A heat matrix (rooms x days, periods x days, instructors' teaching) as an ARIA grid inside a framed scroll
 * region: the header row and the first column are sticky, so a phone scrolls inside the frame and the page never
 * scrolls sideways. One tab stop (roving tabindex): arrows move, Home / End go to the row ends, Ctrl+Home / End to
 * the corners, PageUp / PageDown jump five rows, Enter activates (drill down). Every cell prints its number; the
 * readout under the grid repeats the full counts of the hovered or focused cell (numbers on hover and focus, never
 * colour alone). No motion: the grid is data (motion skill §4 "grids never animate per cell").
 */
import { useCallback, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { cellState, pctText, type CountLike } from "./heat-scale";
import "./heat.css";

export interface HeatAxisItem {
  key: string;
  /** visible header content */
  label: ReactNode;
  /** plain text for the accessible names */
  text: string;
  /** a second, quieter line (time range, room count) */
  sub?: ReactNode;
}

export interface HeatGridProps {
  label: string;
  rows: readonly HeatAxisItem[];
  cols: readonly HeatAxisItem[];
  /** the counts of a cell (undefined = no data) */
  cell: (r: number, c: number) => CountLike | undefined;
  /** the readout and accessible name of a cell */
  describe: (r: number, c: number) => string;
  /** custom text inside a cell (default: the rounded percentage) */
  cellText?: (r: number, c: number) => string;
  onActivate?: (r: number, c: number) => void;
  /** highlighted row (the drilled-down group) */
  selectedRow?: number | null;
  rowHeader?: (r: number) => ReactNode;
  corner?: ReactNode;
  locale: string;
  /** min cell width (px); the frame scrolls when the columns do not fit */
  cellWidth?: number;
  rowHeadWidth?: string;
  maxHeight?: string;
  className?: string;
  "data-testid"?: string;
  /** shown in the readout before anything is hovered or focused */
  hint?: string;
}

export function HeatGrid({
  label,
  rows,
  cols,
  cell,
  describe,
  cellText,
  onActivate,
  selectedRow,
  rowHeader,
  corner,
  locale,
  cellWidth = 40,
  rowHeadWidth = "minmax(5.5rem, max-content)",
  maxHeight = "min(70dvh, 46rem)",
  className,
  "data-testid": testId,
  hint,
}: HeatGridProps) {
  const id = useId();
  const frame = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<[number, number]>([0, 0]);
  const [readout, setReadout] = useState<string | null>(null);
  const nr = rows.length;
  const nc = cols.length;
  const [ar, ac] = [Math.min(active[0], Math.max(0, nr - 1)), Math.min(active[1], Math.max(0, nc - 1))];

  const focusCell = useCallback((r: number, c: number) => {
    setActive([r, c]);
    const el = frame.current?.querySelector<HTMLElement>(`[data-r="${r}"][data-c="${c}"]`);
    el?.focus({ preventScroll: false });
  }, []);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const t = e.target as HTMLElement;
    if (t.getAttribute("role") !== "gridcell") return;
    let [r, c] = [ar, ac];
    switch (e.key) {
      case "ArrowRight": c = Math.min(nc - 1, c + 1); break;
      case "ArrowLeft": c = Math.max(0, c - 1); break;
      case "ArrowDown": r = Math.min(nr - 1, r + 1); break;
      case "ArrowUp": r = Math.max(0, r - 1); break;
      case "Home": c = 0; if (e.ctrlKey) r = 0; break;
      case "End": c = nc - 1; if (e.ctrlKey) r = nr - 1; break;
      case "PageDown": r = Math.min(nr - 1, r + 5); break;
      case "PageUp": r = Math.max(0, r - 5); break;
      case "Enter":
      case " ":
        if (onActivate) {
          e.preventDefault();
          onActivate(r, c);
        }
        return;
      default:
        return;
    }
    e.preventDefault();
    focusCell(r, c);
  };

  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)} data-testid={testId}>
      <div ref={frame} className="relative min-w-0 overflow-auto overscroll-x-contain rounded-xl bg-card edge-hairline" style={{ maxHeight }}>
        <div
          role="grid"
          aria-label={label}
          aria-rowcount={nr + 1}
          aria-colcount={nc + 1}
          aria-describedby={`${id}-readout`}
          onKeyDown={onKey}
          className="grid w-max min-w-full gap-px p-px"
          style={{ gridTemplateColumns: `${rowHeadWidth} repeat(${nc}, minmax(${cellWidth}px, 1fr))` }}
        >
          <div role="row" aria-rowindex={1} className="contents">
            <div role="columnheader" aria-colindex={1} className="sticky top-0 left-0 z-[3] flex items-end bg-card px-2 py-1.5 type-caption text-label-2">
              {corner}
            </div>
            {cols.map((c, ci) => (
              <div key={c.key} role="columnheader" aria-colindex={ci + 2} className="sticky top-0 z-[2] flex flex-col items-center justify-end bg-card px-0.5 py-1.5 text-center type-caption font-semibold text-label-2">
                <span className="truncate">{c.label}</span>
                {c.sub ? <span className="truncate font-normal text-label-3">{c.sub}</span> : null}
              </div>
            ))}
          </div>
          {rows.map((row, ri) => (
            <div key={row.key} role="row" aria-rowindex={ri + 2} aria-selected={selectedRow === ri ? true : undefined} className="contents">
              <div role="rowheader" aria-colindex={1} className={cn("sticky left-0 z-[1] flex min-w-0 flex-col justify-center bg-card px-2 py-1 type-footnote text-label-1", selectedRow === ri && "font-semibold")}>
                {rowHeader ? rowHeader(ri) : <span className="truncate">{row.label}</span>}
                {row.sub && !rowHeader ? <span className="truncate type-caption text-label-3">{row.sub}</span> : null}
              </div>
              {cols.map((col, ci) => {
                const s = cellState(cell(ri, ci));
                const text = cellText ? cellText(ri, ci) : s.kind === "value" ? pctText(s.pct, locale) : s.kind === "blocked" ? "—" : "·";
                const name = describe(ri, ci);
                const isActive = ri === ar && ci === ac;
                return (
                  <div
                    key={col.key}
                    role="gridcell"
                    aria-colindex={ci + 2}
                    aria-label={name}
                    title={name}
                    tabIndex={isActive ? 0 : -1}
                    data-r={ri}
                    data-c={ci}
                    data-state={s.kind}
                    data-step={s.kind === "value" ? s.step : undefined}
                    data-partly={s.kind === "value" && s.partlyBlocked ? "true" : undefined}
                    data-selected={selectedRow === ri ? "true" : undefined}
                    onFocus={() => {
                      setActive([ri, ci]);
                      setReadout(name);
                    }}
                    onMouseEnter={() => setReadout(name)}
                    onClick={() => {
                      setActive([ri, ci]);
                      onActivate?.(ri, ci);
                    }}
                    className={cn(
                      "an-heat flex min-h-8 items-center justify-center rounded-xs px-0.5 type-caption tnum select-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)",
                      onActivate && "cursor-pointer",
                    )}
                  >
                    <span aria-hidden>{text}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <p id={`${id}-readout`} className="min-h-5 type-footnote text-label-2" data-testid={testId ? `${testId}-readout` : undefined}>
        {readout ?? hint ?? ""}
      </p>
    </div>
  );
}
