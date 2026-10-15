"use client"
// Column system parts: the keyboard-accessible resize handle and the "Görünüm › Sütunlar" popover.
// Motion: none on resize (a frequent, direct-manipulation action follows the pointer 1:1, motion skill §2.1);
// the popover uses the Popover primitive's panel reveal (motion pattern 1).
import * as React from "react"
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core"
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { Columns3, GripVertical, RotateCcw } from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useI18n } from "@/lib/i18n/provider"

import { resizeStep, type ColumnSpec } from "./column-system"

/** what the menus need from a column (any row type) */
type ColumnHead = Pick<ColumnSpec, "id" | "header" | "hideable">
import type { ColumnLayoutApi, Density } from "./use-column-layout"

export const TABLE_COPY = {
  tr: {
    resize: (name: string) => `${name} sütununun genişliği`,
    view: "Görünüm",
    columns: "Sütunlar",
    more: (n: number) => `+${n} sütun`,
    moreHint: "Ekran dar olduğu için gizlendi",
    density: "Satır yüksekliği",
    densities: { compact: "Sıkı", standard: "Standart", comfortable: "Geniş" } as Record<Density, string>,
    reset: "Varsayılana dön",
    drag: (name: string) => `${name} sütununu taşı`,
    sortAsc: "artan",
    sortDesc: "azalan",
    empty: "Gösterilecek satır yok",
  },
  en: {
    resize: (name: string) => `Width of the ${name} column`,
    view: "View",
    columns: "Columns",
    more: (n: number) => `+${n} ${n === 1 ? "column" : "columns"}`,
    moreHint: "Hidden because the screen is narrow",
    density: "Row height",
    densities: { compact: "Compact", standard: "Standard", comfortable: "Comfortable" } as Record<Density, string>,
    reset: "Reset to default",
    drag: (name: string) => `Move the ${name} column`,
    sortAsc: "ascending",
    sortDesc: "descending",
    empty: "No rows to show",
  },
}
export function useTableCopy() {
  const { locale } = useI18n()
  return TABLE_COPY[locale === "tr" ? "tr" : "en"]
}

/**
 * Resize handle on a column's trailing edge: an 8 px hit area with a 1 px --border-control line on
 * hover/focus. `role="separator"` + `aria-orientation="vertical"` + `aria-valuenow` (px), ←/→ 8 px,
 * Shift 32 px, Home = auto-fit; double-click auto-fits (all-classes.md §5); drag follows the pointer 1:1.
 */
export function ColumnResizeHandle({ id, label, width, min, max, onResize, onAutoFit }: { id: string; label: string; width: number; min?: number; max?: number; onResize: (px: number) => void; onAutoFit: () => void }) {
  const copy = useTableCopy()
  const drag = React.useRef<{ x: number; w: number } | null>(null)
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={copy.resize(label)}
      aria-valuenow={Math.round(width)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      data-slot="column-resize"
      data-column={id}
      onKeyDown={(e) => {
        const d = resizeStep(e.key, e.shiftKey)
        if (d) {
          e.preventDefault()
          e.stopPropagation()
          onResize(width + d)
        } else if (e.key === "Home" || e.key === "Enter") {
          e.preventDefault()
          e.stopPropagation()
          onAutoFit()
        }
      }}
      onDoubleClick={(e) => {
        e.stopPropagation()
        onAutoFit()
      }}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => {
        if (e.button !== 0) return
        e.preventDefault()
        e.stopPropagation()
        drag.current = { x: e.clientX, w: width }
        e.currentTarget.setPointerCapture(e.pointerId)
      }}
      onPointerMove={(e) => {
        if (!drag.current) return
        onResize(drag.current.w + (e.clientX - drag.current.x))
      }}
      onPointerUp={(e) => {
        drag.current = null
        e.currentTarget.releasePointerCapture(e.pointerId)
      }}
      onPointerCancel={() => (drag.current = null)}
      className="group/resize absolute inset-y-0 -right-1 z-10 flex w-2 cursor-col-resize touch-none justify-center focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)"
    >
      <span aria-hidden className="h-full w-px bg-transparent group-hover/resize:bg-(--border-control) group-focus-visible/resize:bg-(--focus)" />
    </div>
  )
}

function SortableColumnRow({ spec, visible, onToggle }: { spec: ColumnHead; visible: boolean; onToggle: (on: boolean) => void }) {
  const copy = useTableCopy()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: spec.id })
  const cbId = React.useId()
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("flex h-8 items-center gap-2 rounded-md px-1.5 hover:bg-fill-3", isDragging && "relative z-10 bg-(--mat-thick-solid) shadow-elev-2")}
    >
      <button
        type="button"
        aria-label={copy.drag(spec.header)}
        className="inline-flex size-6 cursor-grab touch-none items-center justify-center rounded-sm text-label-3 hover:text-label-1 focus-visible:outline-2 focus-visible:outline-(--focus)"
        {...attributes}
        {...listeners}
      >
        <GripVertical aria-hidden className="size-3.5" />
      </button>
      <Checkbox id={cbId} checked={visible} disabled={spec.hideable === false} onCheckedChange={(v) => onToggle(Boolean(v))} />
      <label htmlFor={cbId} className="min-w-0 flex-1 truncate type-callout text-label-1">
        {spec.header}
      </label>
    </li>
  )
}

/** "Görünüm › Sütunlar": toggle, drag (or keyboard) reorder, density, reset. Linear display options (H4). */
export function ColumnsMenu({ api, specs, trigger }: { api: ColumnLayoutApi; specs: readonly ColumnHead[]; trigger?: React.ReactElement }) {
  const copy = useTableCopy()
  const order = React.useMemo(() => {
    const o = api.prefs.order ?? []
    const ids = specs.map((s) => s.id)
    return [...o.filter((id) => ids.includes(id)), ...ids.filter((id) => !o.includes(id))]
  }, [api.prefs.order, specs])
  const byId = new Map(specs.map((s) => [s.id, s]))
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return
    api.setOrder(arrayMove(order, order.indexOf(String(e.active.id)), order.indexOf(String(e.over.id))))
  }
  return (
    <Popover>
      <PopoverTrigger render={trigger ?? <Button variant="ghost" size="sm" data-testid="table-columns-menu" />}>
        <Columns3 aria-hidden />
        {copy.view}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 gap-2 p-2">
        <p className="px-1.5 type-caption text-label-3">{copy.columns}</p>
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={order} strategy={verticalListSortingStrategy}>
            <ul className="grid max-h-80 overflow-y-auto" data-testid="table-columns-list">
              {order.map((id) => {
                const s = byId.get(id)
                if (!s) return null
                return <SortableColumnRow key={id} spec={s} visible={!api.hidden.has(id)} onToggle={(on) => api.setHidden(id, !on)} />
              })}
            </ul>
          </SortableContext>
        </DndContext>
        {api.layout.squeezed.length ? (
          <p className="px-1.5 type-footnote text-label-2">
            {copy.more(api.layout.squeezed.length)} · {copy.moreHint}
          </p>
        ) : null}
        <div className="grid gap-1 border-t border-hairline pt-2">
          <p className="px-1.5 type-caption text-label-3">{copy.density}</p>
          <div role="radiogroup" aria-label={copy.density} className="grid grid-cols-3 gap-1">
            {(["compact", "standard", "comfortable"] as const).map((d) => (
              <Button key={d} role="radio" aria-checked={api.density === d} size="xs" shape="rect" variant={api.density === d ? "secondary" : "ghost"} onClick={() => api.setDensity(d)}>
                {copy.densities[d]}
              </Button>
            ))}
          </div>
          <Button size="xs" shape="rect" variant="ghost" className="justify-start" onClick={api.reset}>
            <RotateCcw aria-hidden />
            {copy.reset}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** "+3 sütun": columns hidden by priority because the container is narrow (names in the tooltip). */
export function SqueezedChip({ api, specs }: { api: ColumnLayoutApi; specs: readonly ColumnHead[] }) {
  const copy = useTableCopy()
  if (!api.layout.squeezed.length) return null
  const names = api.layout.squeezed.map((id) => specs.find((s) => s.id === id)?.header ?? id).join(", ")
  return (
    <span
      data-testid="table-squeezed"
      title={`${copy.moreHint}: ${names}`}
      className="inline-flex h-(--control-h-xs) items-center rounded-full bg-fill-2 px-2.5 type-footnote font-medium text-label-2"
    >
      {copy.more(api.layout.squeezed.length)}
      <span className="sr-only">: {names}</span>
    </span>
  )
}
