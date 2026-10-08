"use client";
/**
 * Event chip (calendar.md §7.2, §7.3): tinted faculty fill, same-hue ink, 3 px bar, no border or shadow at
 * rest. Content by height: code + glyph (1 row), + room / size (2 rows), + instructor and time (3+ rows).
 * States carry a glyph + text + shape (double bar = locked, inset ring + triangle = conflict) so they read
 * in grayscale. Opaque content: never glass.
 */
import { AlertTriangle, Circle, Lock, Moon, PencilLine } from "lucide-react";
import { memo, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { cn } from "@/lib/utils";
import { spanText } from "./model/check";
import type { CalEvent } from "./model/index-model";

export interface ChipRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface EventChipProps {
  ev: CalEvent;
  rect: ChipRect;
  /** number of 40-ish px rows the chip spans (drives which lines show) */
  lines: 1 | 2 | 3 | 4;
  line2: string;
  ariaLabel: string;
  selected?: boolean;
  culprit?: boolean;
  dimmed?: boolean;
  originDrag?: boolean;
  editable?: boolean;
  exam?: boolean;
  past?: boolean;
  tabIndex?: number;
  compareMoved?: boolean;
  onPointerDown?: (e: PointerEvent<HTMLButtonElement>, ev: CalEvent) => void;
  onKeyDown?: (e: KeyboardEvent<HTMLButtonElement>, ev: CalEvent) => void;
  onDoubleClick?: (ev: CalEvent) => void;
  onFocus?: (ev: CalEvent) => void;
  resizable?: boolean;
  onResizeStart?: (e: PointerEvent<HTMLSpanElement>, ev: CalEvent, edge: "start" | "end") => void;
}

export function chipVars(slot: number): CSSProperties {
  const s = slot >= 1 && slot <= 8 ? slot : 8;
  return { "--chip-fill": `var(--fac-${s}-fill)`, "--chip-ink": `var(--fac-${s}-ink)`, "--chip-bar": `var(--fac-${s}-bar)` } as CSSProperties;
}

function EventChipImpl(p: EventChipProps) {
  const { ev, rect, lines } = p;
  const a = ev.a;
  const glyph = ev.conflict ? (
    <AlertTriangle className="size-3 shrink-0 stroke-[2]" aria-hidden />
  ) : a.locked ? (
    <Lock className="size-3 shrink-0 stroke-[1.75]" aria-hidden />
  ) : ev.warning ? (
    <Circle className="size-2 shrink-0 fill-[var(--status-warning-solid)] stroke-none" aria-hidden />
  ) : null;
  return (
    <button
      type="button"
      className="cal-chip"
      data-testid="calendar-event"
      data-assignment-id={a.id}
      data-room-id={ev.room}
      data-selected={p.selected ? "true" : undefined}
      data-conflict={ev.conflict ? "true" : undefined}
      data-locked={a.locked ? "true" : undefined}
      data-culprit={p.culprit ? "true" : undefined}
      data-dim={p.dimmed ? "true" : undefined}
      data-origin-drag={p.originDrag ? "true" : undefined}
      data-editable={p.editable ? "true" : undefined}
      data-past={p.past ? "true" : undefined}
      aria-label={p.ariaLabel}
      aria-pressed={p.selected ?? false}
      tabIndex={p.tabIndex ?? -1}
      style={{ ...chipVars(a.slot), left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
      onPointerDown={p.onPointerDown ? (e) => p.onPointerDown?.(e, ev) : undefined}
      onKeyDown={p.onKeyDown ? (e) => p.onKeyDown?.(e, ev) : undefined}
      onDoubleClick={p.onDoubleClick ? () => p.onDoubleClick?.(ev) : undefined}
      onFocus={p.onFocus ? () => p.onFocus?.(ev) : undefined}
    >
      <span className="flex min-w-0 items-center gap-1">
        <span className="cal-code truncate">{a.code ?? a.label.split(" §")[0]}</span>
        {a.sec ? <span className="truncate text-[11px] opacity-80">§{a.sec}</span> : null}
        {a.evening ? <Moon className="size-3 shrink-0" aria-hidden /> : null}
        {p.exam ? <PencilLine className="size-3 shrink-0" aria-hidden /> : null}
        {p.compareMoved ? <span aria-hidden className="shrink-0 text-[10px]">↔</span> : null}
        <span className="ml-auto flex shrink-0 items-center">{glyph}</span>
      </span>
      {lines >= 2 ? <span className="cal-line2 truncate">{p.line2}</span> : null}
      {lines >= 3 && a.instr.length ? <span className="cal-line2 truncate">{a.instr[0]}{a.instr.length > 1 ? ` +${a.instr.length - 1}` : ""}</span> : null}
      {lines >= 4 ? <span className={cn("cal-line2 mt-auto truncate")}>{spanText(ev.sp, ev.ep)}</span> : null}
      {p.resizable ? (
        <>
          <span aria-hidden className="absolute inset-x-1 top-0 h-1.5 cursor-ns-resize" onPointerDown={(e) => p.onResizeStart?.(e, ev, "start")} />
          <span aria-hidden className="absolute inset-x-1 bottom-0 h-1.5 cursor-ns-resize" onPointerDown={(e) => p.onResizeStart?.(e, ev, "end")} />
        </>
      ) : null}
    </button>
  );
}

export const EventChip = memo(EventChipImpl);
