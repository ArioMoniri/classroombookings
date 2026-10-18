"use client"
// SmartSched DataTable — TanStack Table (sorting, row model) + the column system (auto width, resize, pin,
// hide by priority, per-user persistence) + TanStack Virtual for long lists. Header and body share ONE
// `grid-template-columns: var(--cols)` so they can never drift apart (review §2 "Table column system").
// Rows: --row-h (32 / 44 / 56 by density); numbers right-aligned with tabular numerals; status columns use
// a dot + word (Vercel H6). No row motion: sorting and filtering are frequent actions (motion skill §2.1).
// Card mode (narrow containers): the header stays for screen readers only, with no sort buttons or resize handles
// (nothing hidden is focusable); each card has ONE target that covers it (see DataCard).
import * as React from "react"
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import { ArrowDown, ArrowUp } from "lucide-react"
import { cn } from "cn"

import { Skeleton } from "@/components/ui/skeleton"

import type { ColumnSpec } from "./column-system"
import { ColumnResizeHandle, ColumnsMenu, SqueezedChip, useTableCopy } from "./parts"
import { ROW_H, useColumnLayout } from "./use-column-layout"

export interface DataColumn<Row> extends ColumnSpec<Row> {
  cell: (row: Row) => React.ReactNode
  /** enables sorting on this column */
  sortValue?: (row: Row) => string | number | null
  /** richer header content (the `header` string stays the accessible/measured name) */
  headerNode?: React.ReactNode
}

export interface DataTableProps<Row> {
  tableId: string
  userId?: string | number | null
  label: string
  columns: readonly DataColumn<Row>[]
  rows: readonly Row[] | undefined
  getRowId: (row: Row) => string
  onRowActivate?: (row: Row) => void
  /** extra props per row (data-testid, aria-current …) */
  rowProps?: (row: Row) => React.HTMLAttributes<HTMLDivElement> & Record<`data-${string}`, string | undefined>
  defaultSort?: SortingState
  defaultHidden?: readonly string[]
  empty?: React.ReactNode
  /** left side of the table toolbar (filters, counts); the columns menu sits on the right */
  toolbar?: React.ReactNode
  /** cap the scroll height (the header sticks); default: grows with the page */
  maxHeight?: string
  /**
   * Narrow containers (< `narrowBelow` px, default 600): "cards" (default) stacks each row as a card with the
   * priority 1–2 columns as label/value pairs; "scroll" keeps the grid with the first column pinned.
   */
  narrow?: "cards" | "scroll"
  narrowBelow?: number
  className?: string
  "data-testid"?: string
}

const collator = new Intl.Collator("tr", { numeric: true, sensitivity: "base" })
const VIRTUAL_FROM = 80

export function DataTable<Row>({
  tableId,
  userId,
  label,
  columns,
  rows,
  getRowId,
  onRowActivate,
  rowProps,
  defaultSort = [],
  defaultHidden,
  empty,
  toolbar,
  maxHeight,
  narrow = "cards",
  narrowBelow = 600,
  className,
  "data-testid": testId,
}: DataTableProps<Row>) {
  const copy = useTableCopy()
  const scroller = React.useRef<HTMLDivElement>(null)
  const [sorting, setSorting] = React.useState<SortingState>(defaultSort)
  const [scrolled, setScrolled] = React.useState(false)
  const data = React.useMemo(() => (rows ?? []) as Row[], [rows])
  const sortable = React.useMemo(() => new Set(columns.filter((c) => c.sortValue).map((c) => c.id)), [columns])
  const api = useColumnLayout({ tableId, userId, specs: columns, rows: data, containerRef: scroller, sortable, defaultHidden })
  const byId = React.useMemo(() => new Map(columns.map((c) => [c.id, c])), [columns])

  const defs = React.useMemo<ColumnDef<Row>[]>(
    () =>
      columns.map((c) => ({
        id: c.id,
        accessorFn: c.sortValue ? (r: Row) => c.sortValue!(r) ?? "" : undefined,
        enableSorting: Boolean(c.sortValue),
        sortingFn: (a, b, id) => {
          const x = a.getValue(id) as string | number
          const y = b.getValue(id) as string | number
          return typeof x === "number" && typeof y === "number" ? x - y : collator.compare(String(x), String(y))
        },
      })),
    [columns],
  )
  const table = useReactTable({
    data,
    columns: defs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => getRowId(r),
  })
  const model = table.getRowModel().rows
  const virtual = model.length > VIRTUAL_FROM
  // rows are exactly --row-h tall (h-(--row-h)), so the estimate is the size; re-measure when the density changes
  const rowH = ROW_H[api.density]
  const v = useVirtualizer({ count: virtual ? model.length : 0, getScrollElement: () => scroller.current, estimateSize: () => rowH, overscan: 12 })
  React.useEffect(() => v.measure(), [v, rowH])
  const { layout } = api
  const loading = rows === undefined
  const asCards = narrow === "cards" && api.container > 0 && api.container < narrowBelow

  const cellClass = (id: string) => {
    const c = byId.get(id)!
    return cn(
      "flex min-w-0 items-center px-(--cell-px)",
      c.align === "end" && "justify-end text-right tnum",
      c.pin === "left" && "sticky z-[2] bg-inherit",
      layout.lastPinned === id && "[[data-scrolled=true]_&]:shadow-[inset_-1px_0_0_0_var(--hairline)]",
    )
  }
  const pinStyle = (id: string): React.CSSProperties | undefined => (byId.get(id)?.pin === "left" ? { left: layout.pinLeft[id] } : undefined)

  const renderCard = (r: (typeof model)[number]) => {
    const [first, ...rest] = columns.filter((c) => !api.hidden.has(c.id) && (c.pin === "left" || (c.priority ?? 3) <= 2))
    return <DataCard key={r.id} row={r.original} rowIndex={r.index} first={first} rest={rest} extra={rowProps?.(r.original) ?? {}} onActivate={onRowActivate} />
  }

  const renderRow = (r: (typeof model)[number], style?: React.CSSProperties) => {
    const extra = rowProps?.(r.original) ?? {}
    return (
      <div
        key={r.id}
        role="row"
        aria-rowindex={r.index + 2}
        tabIndex={onRowActivate ? 0 : undefined}
        onClick={onRowActivate ? () => onRowActivate(r.original) : undefined}
        onKeyDown={
          onRowActivate
            ? (e) => {
                if (e.key === "Enter" && e.target === e.currentTarget) onRowActivate(r.original)
              }
            : undefined
        }
        {...extra}
        style={{ ...style, ...(extra.style ?? {}) }}
        className={cn(
          "group/row grid h-(--row-h) w-max min-w-full grid-cols-(--cols) edge-hairline-b type-callout text-label-1 bg-(--mat-regular-solid) hover:bg-[color-mix(in_srgb,var(--mat-regular-solid),var(--label-1)_4%)]",
          onRowActivate && "cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)",
          extra.className,
        )}
      >
        {layout.ids.map((id) => (
          <div key={id} role="cell" className={cellClass(id)} style={pinStyle(id)}>
            {byId.get(id)!.cell(r.original)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div data-slot="data-table" data-testid={testId} className={cn("flex min-w-0 flex-col gap-2", className)}>
      <div className="flex min-h-(--control-h-sm) flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{toolbar}</div>
        {asCards ? null : <SqueezedChip api={api} specs={columns} />}
        <ColumnsMenu api={api} specs={columns} />
      </div>
      <div
        ref={scroller}
        role="table"
        aria-label={label}
        aria-rowcount={loading ? undefined : model.length + 1}
        aria-busy={loading || undefined}
        data-density={api.density}
        data-mode={asCards ? "cards" : "grid"}
        data-scrolled={scrolled}
        onScroll={(e) => {
          const s = e.currentTarget.scrollLeft > 0
          if (s !== scrolled) setScrolled(s)
        }}
        style={{ ...api.style, maxHeight }}
        className="relative min-w-0 overflow-auto rounded-xl bg-(--mat-regular-solid) edge-hairline"
      >
        <div role="rowgroup" className={cn("sticky top-0 z-[3]", asCards && "sr-only")}>
          <div role="row" aria-rowindex={1} className="grid h-(--control-h-md) w-max min-w-full grid-cols-(--cols) bg-(--mat-regular-solid) edge-hairline-b [--row-bg:var(--mat-regular-solid)]">
            {layout.ids.map((id) => {
              const c = byId.get(id)!
              const col = table.getColumn(id)
              const sorted = col?.getIsSorted()
              return (
                <div
                  key={id}
                  role="columnheader"
                  aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : c.sortValue ? "none" : undefined}
                  className={cn(cellClass(id), "relative type-footnote font-semibold text-label-2")}
                  style={pinStyle(id)}
                  data-column={id}
                >
                  {c.sortValue && !asCards ? (
                    <button
                      type="button"
                      onClick={col?.getToggleSortingHandler()}
                      className={cn("inline-flex min-w-0 items-center gap-1 rounded-sm hover:text-label-1 focus-visible:outline-2 focus-visible:outline-(--focus)", c.align === "end" && "flex-row-reverse")}
                    >
                      <span className="truncate">{c.headerNode ?? c.header}</span>
                      {sorted === "asc" ? <ArrowUp aria-hidden className="size-3 shrink-0" /> : sorted === "desc" ? <ArrowDown aria-hidden className="size-3 shrink-0" /> : null}
                    </button>
                  ) : (
                    <span className="truncate">{c.headerNode ?? c.header}</span>
                  )}
                  {asCards ? null : <ColumnResizeHandle
                    id={id}
                    label={c.header}
                    width={layout.widths[id]}
                    min={c.minSize}
                    max={c.maxSize}
                    onResize={(px) => api.setWidth(id, px)}
                    onAutoFit={() => api.autoFit(id)}
                  />}
                </div>
              )
            })}
          </div>
        </div>
        <div role="rowgroup">
          {loading ? (
            Array.from({ length: 6 }, (_, i) => (
              <div key={i} role="row" className="grid h-(--row-h) w-max min-w-full grid-cols-(--cols) edge-hairline-b">
                {layout.ids.map((id) => (
                  <div key={id} role="cell" className={cn(cellClass(id), "[--row-bg:transparent]")}>
                    <Skeleton className="h-3 w-3/5 rounded-sm" />
                  </div>
                ))}
              </div>
            ))
          ) : model.length === 0 ? (
            <div role="row" className="px-(--cell-px) py-6">
              <div role="cell" className="type-callout text-label-2">
                {empty ?? copy.empty}
              </div>
            </div>
          ) : asCards ? (
            model.map((r) => renderCard(r))
          ) : virtual ? (
            <div style={{ height: v.getTotalSize(), position: "relative" }}>
              {v.getVirtualItems().map((vi) => renderRow(model[vi.index], { position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${vi.start}px)` }))}
            </div>
          ) : (
            model.map((r) => renderRow(r))
          )}
        </div>
      </div>
    </div>
  )
}

/** nested actions inside a card's cells sit above the card's stretched target and keep their own clicks */
const CARD_NESTED =
  "[&_dd_:is(a[href],button,input,select,textarea,label,summary,[role=button],[role=checkbox],[role=switch],[role=combobox])]:relative [&_dd_:is(a[href],button,input,select,textarea,label,summary,[role=button],[role=checkbox],[role=switch],[role=combobox])]:z-[1] [&_[data-card-title]_:is(button:not([data-card-activate]),input,select,textarea,label,summary,[role=button],[role=checkbox],[role=switch],[role=combobox])]:relative [&_[data-card-title]_:is(button:not([data-card-activate]),input,select,textarea,label,summary,[role=button],[role=checkbox],[role=switch],[role=combobox])]:z-[1]"
/** the title's link becomes the whole card's target: its ::after covers the card (a "stretched link") */
const CARD_LINK = "[&_[data-card-title]_a[href]]:after:absolute [&_[data-card-title]_a[href]]:after:inset-0 [&_[data-card-title]_a[href]]:after:content-['']"
const INTERACTIVE = "a[href],button,input,select,textarea,summary,[role=button],[role=checkbox],[role=switch],[tabindex]"

type TitleKind = "link" | "interactive" | "text"

/**
 * One row as a card (narrow containers). The whole card is ONE target (MOBILE.md M-02, WAI "one interactive element
 * per card"): when the title cell has a link, that link is stretched over the card (real link semantics: open in a
 * new tab, the link's own focus ring); otherwise, with `onActivate`, a button covers the card, named by the title
 * (the visible title text is then hidden from assistive tech so it is not read twice). Other actions in the cells
 * are lifted above the target, so they are excluded from the card's click area. No `tabIndex` on the row itself.
 */
function DataCard<Row>({
  row,
  rowIndex,
  first,
  rest,
  extra,
  onActivate,
}: {
  row: Row
  rowIndex: number
  first: DataColumn<Row> | undefined
  rest: DataColumn<Row>[]
  extra: React.HTMLAttributes<HTMLDivElement>
  onActivate?: (row: Row) => void
}) {
  const titleId = React.useId()
  // what the caller's title cell renders, read from the DOM after commit (unknown on the server / first paint)
  const [kind, setKind] = React.useState<TitleKind | null>(null)
  const measure = (el: HTMLSpanElement | null) => {
    if (!el) return
    const next: TitleKind = el.querySelector("a[href]") ? "link" : el.querySelector(INTERACTIVE) ? "interactive" : "text"
    if (next !== kind) setKind(next)
  }
  const button = Boolean(onActivate && first) && kind !== "link"
  return (
    <div
      role="row"
      aria-rowindex={rowIndex + 2}
      data-card-target={kind === "link" ? "link" : button ? "button" : undefined}
      {...extra}
      className={cn(
        // touch: the title's centre sits ≥ 22 px inside the card, so a 44 px target around it never reaches the card above
        "relative flex min-h-11 flex-col gap-1 px-(--cell-px) py-2.5 edge-hairline-b type-callout text-label-1 pointer-coarse:min-h-12 pointer-coarse:px-[max(var(--cell-px),1rem)] pointer-coarse:pt-3.5",
        (button || kind === "link") && "cursor-pointer",
        CARD_LINK,
        CARD_NESTED,
        extra.className,
      )}
    >
      {first ? (
        <div role="cell" data-card-title="" className="flex min-w-0 items-center type-headline">
          <span ref={measure} id={titleId} aria-hidden={button && kind === "text" ? true : undefined} className="contents">
            {first.cell(row)}
          </span>
          {button ? (
            <button
              type="button"
              data-card-activate=""
              aria-labelledby={titleId}
              onClick={() => onActivate?.(row)}
              className="absolute inset-0 cursor-pointer rounded-[inherit] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)"
            />
          ) : null}
        </div>
      ) : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        {rest.map((c) => (
          <div key={c.id} role="cell" className="contents">
            <dt className="type-footnote text-label-2">{c.header}</dt>
            <dd className={cn("flex min-w-0 items-center type-footnote", c.align === "end" && "tnum")}>{c.cell(row)}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** Vercel-style status: an 8 px dot + one word; colour is never the only cue (G4). `pending` is a hollow ring in
 *  label-2 ("Davet bekliyor", "Bağlantı bekliyor"; sign-in.md §14): the shape, not a hue, says "not yet". */
export function StatusDot({ tone, children, className }: { tone: "feasible" | "infeasible" | "warning" | "locked" | "neutral" | "tint" | "pending"; children: React.ReactNode; className?: string }) {
  const dot =
    tone === "neutral"
      ? "bg-label-3"
      : tone === "pending"
        ? "bg-transparent shadow-[inset_0_0_0_1.5px_var(--label-2)]"
        : tone === "tint"
          ? "bg-tint"
          : { feasible: "bg-status-feasible-solid", infeasible: "bg-status-infeasible-solid", warning: "bg-status-warning-solid", locked: "bg-status-locked-solid" }[tone]
  return (
    <span data-slot="status-dot" data-tone={tone} className={cn("inline-flex min-w-0 items-center gap-2 type-callout text-label-1", className)}>
      <span aria-hidden className={cn("size-2 shrink-0 rounded-full", dot)} />
      <span className="truncate">{children}</span>
    </span>
  )
}
