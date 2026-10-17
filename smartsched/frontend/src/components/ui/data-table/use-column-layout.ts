"use client"
// React side of the column system: per-user persisted prefs, auto widths, container-driven layout.
// Persistence: localStorage["smartsched.table.<tableId>.<userId>"] = { order, sizing, visibility, pinning, density }
// (review §2). Read through useSyncExternalStore so the server render and the first client render agree.
import * as React from "react"

import { autoWidth, clamp, layoutColumns, type ColumnLayout, type ColumnSpec } from "./column-system"

export type Density = "compact" | "standard" | "comfortable"

export interface TablePrefs {
  order?: string[]
  sizing?: Record<string, number>
  /** false = hidden by the user */
  visibility?: Record<string, boolean>
  pinning?: { left?: string[] }
  density?: Density
}

export const prefsKey = (tableId: string, userId: string | number | null | undefined) => `smartsched.table.${tableId}.${userId ?? "anon"}`
const EVENT = "smartsched:table-prefs"

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function useTablePrefs(tableId: string, userId: string | number | null | undefined) {
  const key = prefsKey(tableId, userId)
  const raw = React.useSyncExternalStore(
    (cb) => {
      const on = (e: Event) => {
        if (e instanceof StorageEvent ? e.key === key : (e as CustomEvent<string>).detail === key) cb()
      }
      window.addEventListener("storage", on)
      window.addEventListener(EVENT, on)
      return () => {
        window.removeEventListener("storage", on)
        window.removeEventListener(EVENT, on)
      }
    },
    () => read(key),
    () => null,
  )
  const prefs = React.useMemo<TablePrefs>(() => {
    if (!raw) return {}
    try {
      return JSON.parse(raw) as TablePrefs
    } catch {
      return {}
    }
  }, [raw])
  const update = React.useCallback(
    (patch: (p: TablePrefs) => TablePrefs) => {
      let current: TablePrefs = {}
      try {
        current = JSON.parse(read(key) ?? "{}") as TablePrefs
      } catch {
        current = {}
      }
      try {
        localStorage.setItem(key, JSON.stringify(patch(current)))
      } catch {
        /* storage full or blocked: the layout still works for this session */
      }
      window.dispatchEvent(new CustomEvent(EVENT, { detail: key }))
    },
    [key],
  )
  return { prefs, update, key }
}

/** Width of an element's content box, tracked with a ResizeObserver (0 until measured). */
export function useContainerWidth(ref: React.RefObject<HTMLElement | null>): number {
  const [w, setW] = React.useState(0)
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver((entries) => {
      const next = Math.floor(entries[0]?.contentRect.width ?? 0)
      setW((prev) => (prev === next ? prev : next))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}

export interface ColumnLayoutApi {
  layout: ColumnLayout
  prefs: TablePrefs
  density: Density
  setDensity: (d: Density) => void
  setWidth: (id: string, px: number) => void
  autoFit: (id: string) => void
  setHidden: (id: string, hidden: boolean) => void
  setOrder: (ids: string[]) => void
  reset: () => void
  /** style for the scroll container: --cols (shared template) and --table-w */
  style: React.CSSProperties
  hidden: Set<string>
  /** measured container width (0 before the first measurement) */
  container: number
}

export function useColumnLayout<Row>({
  tableId,
  userId,
  specs,
  rows,
  containerRef,
  sortable,
  defaultHidden,
  squeeze = true,
}: {
  tableId: string
  userId: string | number | null | undefined
  specs: readonly ColumnSpec<Row>[]
  rows: readonly Row[]
  containerRef: React.RefObject<HTMLElement | null>
  sortable?: ReadonlySet<string>
  defaultHidden?: readonly string[]
  /** hide low-priority columns when the minimums do not fit (false = scroll horizontally instead) */
  squeeze?: boolean
}): ColumnLayoutApi {
  const { prefs, update } = useTablePrefs(tableId, userId)
  const container = useContainerWidth(containerRef)
  // auto widths are measured once per data set (header + first 200 rows), not per render
  const auto = React.useMemo(() => {
    const sample = rows.length > 200 ? rows.slice(0, 200) : rows
    const out: Record<string, number> = {}
    for (const s of specs) out[s.id] = autoWidth(s, sample, { sortable: sortable?.has(s.id) })
    return out
  }, [specs, rows, sortable])
  const sizing = React.useMemo(() => prefs.sizing ?? {}, [prefs.sizing])
  const base = React.useMemo(() => ({ ...auto, ...sizing }), [auto, sizing])
  const userSized = React.useMemo(() => new Set(Object.keys(sizing)), [sizing])
  const hidden = React.useMemo(() => {
    const h = new Set<string>(defaultHidden ?? [])
    for (const [id, on] of Object.entries(prefs.visibility ?? {})) {
      if (on) h.delete(id)
      else h.add(id)
    }
    for (const s of specs) if (s.hideable === false) h.delete(s.id)
    return h
  }, [prefs.visibility, defaultHidden, specs])
  const layout = React.useMemo(
    () => layoutColumns(specs, base, { container, hidden, userSized, order: prefs.order, squeeze }),
    [specs, base, container, hidden, userSized, prefs.order, squeeze],
  )
  const byId = React.useMemo(() => new Map(specs.map((s) => [s.id, s])), [specs])
  const setWidth = React.useCallback(
    (id: string, px: number) => {
      const s = byId.get(id)
      const w = Math.round(clamp(px, s?.minSize ?? 56, s?.maxSize ?? 480))
      update((p) => ({ ...p, sizing: { ...(p.sizing ?? {}), [id]: w } }))
    },
    [byId, update],
  )
  const autoFit = React.useCallback(
    (id: string) =>
      update((p) => {
        const next = { ...(p.sizing ?? {}) }
        delete next[id]
        return { ...p, sizing: next }
      }),
    [update],
  )
  return {
    layout,
    prefs,
    density: prefs.density ?? "standard",
    setDensity: (d) => update((p) => ({ ...p, density: d })),
    setWidth,
    autoFit,
    setHidden: (id, h) => update((p) => ({ ...p, visibility: { ...(p.visibility ?? {}), [id]: !h } })),
    setOrder: (ids) => update((p) => ({ ...p, order: ids })),
    reset: () => update(() => ({})),
    style: { "--cols": layout.template, "--table-w": `${layout.total}px` } as React.CSSProperties,
    hidden,
    container,
  }
}
