// SmartSched table column system (design-system overhaul 2026-10-15; review §2 "Table column system",
// all-classes.md §5). Original work; references: Airtable grid (resize, auto-fit), Linear display options
// (Mobbin H4: dense rows, a columns popover), Height's column menu (hide / pin / reorder).
//
// Pure functions (no React) so the layout rules are unit-tested:
//   - autoWidth: header + the first 200 rows measured with canvas.measureText in the cell font, clamped to
//     [min, max], plus the cell padding (and the sort glyph on sortable headers)
//   - layoutColumns: priority hiding when the container is narrower than the sum of the minimums, slack to the
//     `grow` columns, sticky offsets for left-pinned columns
//   - gridTemplate: ONE `grid-template-columns` string that the header and the virtualised body share
export type ColumnAlign = "start" | "end"

export interface ColumnSpec<Row = unknown> {
  id: string
  /** header text (measured for auto width; the visible header may be richer) */
  header: string
  minSize?: number
  maxSize?: number
  /** fixed px, or "auto" (measured) — the default */
  size?: number | "auto"
  /** share of the slack when the table is wider than its columns (Course, Program …) */
  grow?: number
  align?: ColumnAlign
  pin?: "left"
  /** can the user hide it (Görünüm › Sütunlar)? default true */
  hideable?: boolean
  /** 1 = always keep … 5 = first to hide when space runs out; default 3 */
  priority?: 1 | 2 | 3 | 4 | 5
  /** the text a cell shows, for measuring (default: no body measurement) */
  text?: (row: Row) => string
  /** extra px a cell needs besides its text (icons, badges) */
  extra?: number
  /** cell font for measuring (default the table's) */
  font?: string
}

export const CELL_FONT = "400 13px Inter, -apple-system, system-ui, sans-serif"
export const HEADER_FONT = "600 12px Inter, -apple-system, system-ui, sans-serif"
export const CELL_PAD_X = 24 // 12 + 12 (--cell-px)
export const SAMPLE_ROWS = 200
const DEFAULT_MIN = 56
const DEFAULT_MAX = 480

let ctx: CanvasRenderingContext2D | null | undefined
const cache = new Map<string, number>()

/** Width of `text` in `font`, via canvas.measureText; a character estimate where canvas is missing (SSR, jsdom). */
export function measureText(text: string, font: string = CELL_FONT): number {
  const key = `${font}\u0001${text}`
  const hit = cache.get(key)
  if (hit !== undefined) return hit
  if (ctx === undefined) {
    try {
      ctx = typeof document !== "undefined" ? (document.createElement("canvas").getContext("2d") ?? null) : null
    } catch {
      ctx = null
    }
  }
  let w: number
  if (ctx) {
    ctx.font = font
    w = ctx.measureText(text).width
  } else {
    const px = Number(/(\d+(?:\.\d+)?)px/.exec(font)?.[1] ?? 13)
    w = text.length * px * 0.56
  }
  if (cache.size > 20000) cache.clear()
  cache.set(key, w)
  return w
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n))
}

/** Measured width of a column: header and the first `SAMPLE_ROWS` rows, clamped to [min, max]. */
export function autoWidth<Row>(spec: ColumnSpec<Row>, rows: readonly Row[], opts: { sortable?: boolean; font?: string } = {}): number {
  const min = spec.minSize ?? DEFAULT_MIN
  const max = spec.maxSize ?? DEFAULT_MAX
  if (typeof spec.size === "number") return clamp(spec.size, min, max)
  let w = measureText(spec.header, HEADER_FONT) + (opts.sortable ? 16 : 0)
  if (spec.text) {
    const font = spec.font ?? opts.font ?? CELL_FONT
    const n = Math.min(rows.length, SAMPLE_ROWS)
    for (let i = 0; i < n; i++) {
      const t = spec.text(rows[i])
      if (t) w = Math.max(w, measureText(t, font) + (spec.extra ?? 0))
    }
  }
  return clamp(Math.ceil(w + CELL_PAD_X), min, max)
}

export interface ColumnLayout {
  /** visible column ids, in order (pinned first) */
  ids: string[]
  /** final px width per visible column (header and body use the same numbers) */
  widths: Record<string, number>
  /** hidden because the container is too narrow (shown as "+N sütun") */
  squeezed: string[]
  /** sticky `left` for each pinned column */
  pinLeft: Record<string, number>
  /** id of the last pinned column (gets the scroll edge) */
  lastPinned: string | null
  /** sum of the widths (the row width) */
  total: number
  template: string
}

/**
 * Lays out the columns for a container. `base` = auto/user widths; `userSized` widths never grow;
 * `hidden` = the user's choice. Columns are dropped by priority (5 first, then 4 …; never priority 1 or pinned)
 * while the sum of the minimums is wider than the container; the slack goes to the `grow` columns.
 */
export function layoutColumns<Row>(
  specs: readonly ColumnSpec<Row>[],
  base: Record<string, number>,
  opts: { container: number; hidden?: ReadonlySet<string>; userSized?: ReadonlySet<string>; order?: readonly string[] },
): ColumnLayout {
  const order = opts.order?.length ? [...opts.order, ...specs.map((s) => s.id).filter((id) => !opts.order!.includes(id))] : specs.map((s) => s.id)
  const byId = new Map(specs.map((s) => [s.id, s]))
  let visible = order.filter((id) => byId.has(id) && !opts.hidden?.has(id))
  // pinned columns first, in their own order
  visible = [...visible.filter((id) => byId.get(id)!.pin === "left"), ...visible.filter((id) => byId.get(id)!.pin !== "left")]
  const width = (id: string) => base[id] ?? autoWidth(byId.get(id)!, [])
  const minOf = (id: string) => Math.min(width(id), byId.get(id)!.minSize ?? DEFAULT_MIN)
  const squeezed: string[] = []
  if (opts.container > 0) {
    const candidates = visible
      .filter((id) => byId.get(id)!.pin !== "left" && (byId.get(id)!.priority ?? 3) > 1)
      .sort((a, b) => (byId.get(b)!.priority ?? 3) - (byId.get(a)!.priority ?? 3) || visible.indexOf(b) - visible.indexOf(a))
    let sum = visible.reduce((s, id) => s + minOf(id), 0)
    for (const id of candidates) {
      if (sum <= opts.container) break
      squeezed.push(id)
      sum -= minOf(id)
    }
    visible = visible.filter((id) => !squeezed.includes(id))
  }
  const widths: Record<string, number> = {}
  for (const id of visible) widths[id] = width(id)
  let total = visible.reduce((s, id) => s + widths[id], 0)
  const slack = opts.container - total
  if (slack > 0) {
    const growers = visible.filter((id) => (byId.get(id)!.grow ?? 0) > 0 && !opts.userSized?.has(id))
    const share = growers.reduce((s, id) => s + (byId.get(id)!.grow ?? 0), 0)
    if (share > 0) {
      let left = slack
      growers.forEach((id, i) => {
        const add = i === growers.length - 1 ? left : Math.floor((slack * (byId.get(id)!.grow ?? 0)) / share)
        const max = byId.get(id)!.maxSize ?? Number.POSITIVE_INFINITY
        const take = Math.min(add, Math.max(0, max - widths[id]))
        widths[id] += take
        left -= take
      })
      total = visible.reduce((s, id) => s + widths[id], 0)
    }
  }
  const pinLeft: Record<string, number> = {}
  let x = 0
  let lastPinned: string | null = null
  for (const id of visible) {
    if (byId.get(id)!.pin !== "left") break
    pinLeft[id] = x
    x += widths[id]
    lastPinned = id
  }
  return { ids: visible, widths, squeezed, pinLeft, lastPinned, total, template: gridTemplate(visible, widths) }
}

export function gridTemplate(ids: readonly string[], widths: Record<string, number>): string {
  return ids.map((id) => `${Math.round(widths[id])}px`).join(" ")
}

/** Resize step for the keyboard: ← → 8 px, Shift 32 px (review §2). */
export function resizeStep(key: string, shift: boolean): number {
  const step = shift ? 32 : 8
  return key === "ArrowRight" ? step : key === "ArrowLeft" ? -step : 0
}
