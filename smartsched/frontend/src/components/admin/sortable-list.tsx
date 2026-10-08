"use client";
/**
 * Drag-to-reorder list on dnd-kit (CRBS `Groups::save_pos`, `Rooms::save_pos`). motion_designer pattern
 * §6/§7: the row you grab lifts (pre-rendered shadow layer, no box-shadow tween) and siblings reflow on
 * `springs.smooth` (CSS mirror); reduced motion drops the reflow transition. Keyboard: Space on the handle
 * picks up, arrows move, Space drops (dnd-kit keyboard sensor), or Alt+↑/↓ moves one step at once. Every
 * move is announced in the polite live region.
 */
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import { useState, type KeyboardEvent, type ReactNode } from "react";
import { cssSpring, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";

export interface SortableItem {
  id: number;
  label: string;
}

export function SortableList<T extends SortableItem>({ items, onReorder, render, label }: { items: readonly T[]; onReorder: (next: T[]) => void; render: (item: T) => ReactNode; label: string }) {
  const t = useT();
  const [announce, setAnnounce] = useState("");
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = arrayMove([...items], from, to);
    onReorder(next);
    setAnnounce(t("crbs.sort.moved", { name: items[from]?.label ?? "", pos: to + 1, total: items.length }));
  };
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    move(
      items.findIndex((i) => i.id === e.active.id),
      items.findIndex((i) => i.id === e.over?.id),
    );
  };
  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={onDragEnd}
        accessibility={{
          announcements: {
            onDragStart: ({ active }) => t("crbs.sort.picked", { name: items.find((i) => i.id === active.id)?.label ?? "" }),
            onDragOver: ({ over }) => (over ? t("crbs.sort.over", { pos: items.findIndex((i) => i.id === over.id) + 1 }) : ""),
            onDragEnd: () => "",
            onDragCancel: () => t("crbs.sort.cancelled"),
          },
          screenReaderInstructions: { draggable: t("crbs.sort.instructions") },
        }}
      >
        <SortableContext items={items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
          <ul aria-label={label} className="flex flex-col">
            {items.map((item, i) => (
              <Row key={item.id} item={item} onKeyMove={(d) => move(i, i + d)}>
                {render(item)}
              </Row>
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
    </>
  );
}

function Row({ item, children, onKeyMove }: { item: SortableItem; children: ReactNode; onKeyMove: (dir: -1 | 1) => void }) {
  const t = useT();
  const reduce = useReduce();
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    transition: reduce ? null : { duration: cssSpring.smooth.ms, easing: cssSpring.smooth.easing },
  });
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      e.stopPropagation();
      onKeyMove(e.key === "ArrowUp" ? -1 : 1);
      return;
    }
    listeners?.onKeyDown?.(e);
  };
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition: transition ?? undefined }}
      className={cn("relative flex items-center gap-2 bg-(--mat-thick-solid) px-2 py-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none", isDragging && "z-10 rounded-lg")}
      data-sort-id={item.id}
    >
      {/* lift: a pre-rendered shadow layer fades in (no box-shadow animation, motion.md §8) */}
      <span aria-hidden className={cn("pointer-events-none absolute inset-0 rounded-lg shadow-[0_8px_24px_-8px_rgba(0,0,0,0.25),0_0_0_1px_var(--hairline)] transition-opacity duration-(--dur-fast)", isDragging ? "opacity-100" : "opacity-0")} />
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        onKeyDown={onKeyDown}
        aria-label={t("crbs.sort.handle", { name: item.label })}
        className="relative flex size-8 shrink-0 cursor-grab touch-none items-center justify-center rounded-md text-label-3 outline-none hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus) active:cursor-grabbing"
      >
        <GripVertical className="size-4" aria-hidden />
      </button>
      <div className="relative min-w-0 flex-1">{children}</div>
    </li>
  );
}
