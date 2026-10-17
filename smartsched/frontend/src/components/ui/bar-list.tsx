// SmartSched BarList — horizontal bars with the value printed at the bar end (design-system overhaul 2026-10-15,
// review §3 Dashboard / Run report: "bars without values"). Plain HTML, so the numbers are real text (copyable,
// screen-reader friendly, no chart axes to frame an empty state). Data marks use one categorical colour or a
// status solid, never the accent (G3). No grow-in animation (A9): data never animates on load.
// Rows with an `href` are links: the whole row (label, bar, value) is the target, at least 44 px tall on coarse
// pointers (MOBILE.md M-02; the dashboard's phone list of the utilisation heatmap). `linkAs` renders them
// (pass next/link's Link; default a plain <a>).
import * as React from "react"
import { cn } from "cn"

export interface BarItem {
  key: string
  label: React.ReactNode
  value: number
  /** formatted value; default the number */
  display?: React.ReactNode
  /** makes the row a link */
  href?: string
  /** accessible name of the row link (default: the label and the value as text) */
  linkLabel?: string
}

type LinkLike = React.ElementType<{ href: string; className?: string; "aria-label"?: string; children?: React.ReactNode }>

export function BarList({
  items,
  max,
  tone = "var(--cat-1)",
  labelWidth = "minmax(5rem, 40%)",
  className,
  linkAs: LinkAs = "a",
  "aria-label": ariaLabel,
}: {
  items: readonly BarItem[]
  /** scale maximum; default the largest value */
  max?: number
  tone?: string
  labelWidth?: string
  className?: string
  /** component for rows with an `href` (e.g. next/link) */
  linkAs?: LinkLike
  "aria-label"?: string
}) {
  const top = Math.max(max ?? 0, ...items.map((i) => i.value), 1)
  return (
    <ul aria-label={ariaLabel} className={cn("grid gap-1.5", className)} style={{ gridTemplateColumns: `${labelWidth} minmax(0,1fr) auto` }}>
      {items.map((i) => {
        const cells = (
          <>
            <span className="truncate type-footnote text-label-2">{i.label}</span>
            <span aria-hidden className="h-2.5 overflow-hidden rounded-full bg-fill-3">
              <span className="block h-full rounded-full" style={{ width: `${Math.max(i.value > 0 ? 2 : 0, (i.value / top) * 100)}%`, background: tone }} />
            </span>
            <span className="min-w-8 text-right type-footnote font-medium text-label-1 tnum">{i.display ?? i.value}</span>
          </>
        )
        return (
          <li key={i.key} className="col-span-3 grid grid-cols-subgrid items-center gap-2" data-slot="bar-item">
            {i.href ? (
              <LinkAs
                href={i.href}
                aria-label={i.linkLabel}
                className="col-span-3 -mx-2 grid grid-cols-subgrid items-center gap-2 rounded-lg px-2 py-1 hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus) pointer-coarse:min-h-11"
              >
                {cells}
              </LinkAs>
            ) : (
              cells
            )}
          </li>
        )
      })}
    </ul>
  )
}
