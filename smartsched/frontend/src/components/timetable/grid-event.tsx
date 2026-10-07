"use client";

import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { forwardRef, memo, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { STATUS_ICON } from "@/components/common/status-badge";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { STATUS_TO_KIND, type GridEvent } from "./use-grid-model";

export const STATUS_EVENT_CLASS: Record<GridEvent["status"], string> = {
  ok: "bg-popover text-foreground border-border",
  locked: "bg-status-locked text-status-locked-fg border-status-locked-border",
  conflict: "bg-status-infeasible text-status-infeasible-fg border-status-infeasible-border",
  warning: "bg-status-warning text-status-warning-fg border-status-warning-border",
  block: "hatch-preoccupied text-status-preoccupied-fg border-status-preoccupied-border",
  tip: "bg-status-tip text-status-tip-fg border-status-tip-border",
  pc: "bg-status-pclab text-status-pclab-fg border-status-pclab-border",
};

export interface GridEventProps {
  event: GridEvent;
  roomName: string;
  style?: CSSProperties;
  className?: string;
  compact?: boolean;
  selected?: boolean;
  highlighted?: boolean;
  changed?: boolean;
  conflictPulse?: boolean;
  dragging?: boolean;
  onOpen?: (event: GridEvent) => void;
  onKeyAction?: (event: GridEvent, key: string) => void;
}

export function eventAriaLabel(e: GridEvent, roomName: string, locale: string, t: (k: "common.locked" | "grid.capacityWarning" | "grid.conflict" | "common.students" | "common.seats") => string): string {
  const parts = [e.label, roomName, `${dayName(e.day, locale)} P${e.startPeriod}–P${e.endPeriod} ${periodRangeLabel(e.startPeriod, e.endPeriod)}`];
  if (e.kind === "assignment") parts.push(`${e.size} ${t("common.students")}, ${e.capacity} ${t("common.seats")}`);
  if (e.locked && e.kind === "assignment") parts.push(t("common.locked"));
  if (e.status === "warning") parts.push(t("grid.capacityWarning"));
  if (e.status === "conflict") parts.push(t("grid.conflict"));
  return parts.join(", ");
}

/** Static visual (used by the DragOverlay ghost and the live cell). */
export const EventBody = forwardRef<HTMLButtonElement, GridEventProps & { dragHandleProps?: Record<string, unknown> }>(function EventBody(
  { event, roomName, style, className, compact, selected, highlighted, changed, conflictPulse, dragging, onOpen, onKeyAction, dragHandleProps },
  ref,
) {
  const { t, locale } = useI18n();
  const Icon = STATUS_ICON[STATUS_TO_KIND[event.status]];
  const span = event.endPeriod - event.startPeriod + 1;
  const isBlock = event.kind === "block";
  const handleKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onOpen?.(event);
    } else if (!e.metaKey && !e.ctrlKey && /^[lLmM]$/.test(e.key)) {
      e.preventDefault();
      onKeyAction?.(event, e.key.toLowerCase());
    }
  };
  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onOpen?.(event);
  };
  return (
    <button
      ref={ref}
      type="button"
      data-assignment-id={event.assignment?.id ?? undefined}
      data-event-id={event.id}
      data-status={event.status}
      aria-label={eventAriaLabel(event, roomName, locale, t)}
      aria-pressed={selected}
      disabled={isBlock && !onOpen}
      onClick={handleClick}
      onKeyDown={handleKey}
      style={style}
      className={cn(
        "group/ev relative flex flex-col overflow-hidden rounded-[4px] border text-left outline-none transition-[box-shadow,opacity] duration-[var(--dur-fast)] focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
        STATUS_EVENT_CLASS[event.status],
        !isBlock && "cursor-grab hover:shadow-elev-1 active:cursor-grabbing",
        selected && "ring-2 ring-primary",
        highlighted && "ring-2 ring-primary ring-offset-1",
        changed && "animate-pulse ring-2 ring-status-feasible-border",
        conflictPulse && "outline-2 outline-dashed outline-[var(--conflict-outline)]",
        dragging && "opacity-40 border-dashed",
        compact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-1 text-xs",
        className,
      )}
      {...dragHandleProps}
    >
      <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: isBlock ? "var(--status-preoccupied-border)" : `var(--cat-${event.facultySlot})` }} aria-hidden />
      <span className="flex items-center gap-1 pl-1">
        <span className="truncate font-mono font-semibold leading-tight">{event.label}</span>
        {event.status !== "ok" ? <Icon className={cn("ml-auto shrink-0", compact ? "size-3" : "size-3.5")} aria-hidden /> : null}
      </span>
      {!compact && !isBlock ? (
        <span className="truncate pl-1 text-[11px] leading-tight opacity-80">
          {event.size}/{event.capacity}{event.assignment?.instructor ? ` · ${event.assignment.instructor.replace(/^(Prof\. Dr\.|Doç\. Dr\.|Dr\. Öğr\. Üyesi|Öğr\. Gör\.)\s*/, "")}` : ""}
        </span>
      ) : null}
      {!compact && span >= 3 ? <span className="mt-auto pl-1 text-[10px] leading-tight opacity-70">P{event.startPeriod}–P{event.endPeriod}</span> : null}
    </button>
  );
});

/** Draggable wrapper used inside the grid cells. */
export const DraggableEvent = memo(function DraggableEvent(props: GridEventProps & { disabled?: boolean }) {
  const { event, disabled, ...rest } = props;
  const { attributes, listeners, setNodeRef, isDragging, transform } = useDraggable({ id: event.id, data: { event }, disabled: disabled || event.kind === "block" || event.locked });
  const style: CSSProperties = { ...rest.style, transform: transform ? CSS.Translate.toString(transform) : undefined, zIndex: isDragging ? 20 : undefined };
  return <EventBody ref={setNodeRef} event={event} {...rest} style={style} dragging={isDragging || rest.dragging} dragHandleProps={{ ...attributes, ...listeners, tabIndex: 0, role: "button" }} />;
});
