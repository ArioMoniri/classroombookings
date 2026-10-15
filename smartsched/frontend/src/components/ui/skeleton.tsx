// Source: shadcn/ui skeleton (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — fill-2 pulse (static under reduced motion), plus the loading rules of the design-system
// overhaul 2026-10-15 (review §2 "Loading states", motion pattern 12):
//   1. `undefined` is "not loaded yet" and renders a glyph-sized skeleton — never 0 and never "—".
//   2. One loading signal per region: a skeleton OR a busy label, not both.
//   3. Skeletons take the size of what they replace (one line of text = 1lh tall, a number = its digits wide),
//      so the content swap does not shift the layout.
import * as React from "react"
import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("animate-pulse rounded-lg bg-fill-2", className)}
      {...props}
    />
  )
}

/**
 * A value that may still be loading. `value === undefined` → an inline skeleton `chars` wide and one line tall
 * (announced as `loadingLabel` to screen readers); `null` → the `empty` text (no data, not loading);
 * anything else is formatted. Use for counts, KPIs and labels that interpolate numbers ("0 dersi 0 dersliğe").
 */
function LoadingValue<T>({
  value,
  format = (v: T) => String(v),
  chars = 3,
  empty = "—",
  loadingLabel,
  className,
}: {
  value: T | null | undefined
  format?: (v: T) => React.ReactNode
  chars?: number
  empty?: React.ReactNode
  loadingLabel?: string
  className?: string
}) {
  if (value === undefined)
    return (
      <span data-slot="loading-value" data-loading="true" className={cn("inline-block align-baseline", className)}>
        <span
          aria-hidden
          className="inline-block h-[0.85lh] translate-y-[0.1lh] animate-pulse rounded-sm bg-fill-2 align-baseline"
          style={{ width: `${chars}ch` }}
        />
        {loadingLabel ? <span className="sr-only">{loadingLabel}</span> : null}
      </span>
    )
  if (value === null) return <span className={className}>{empty}</span>
  return <span className={cn("tnum", className)}>{format(value)}</span>
}

export { Skeleton, LoadingValue }
