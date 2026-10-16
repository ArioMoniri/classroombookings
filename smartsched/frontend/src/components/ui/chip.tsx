"use client"
// SmartSched Liquid Glass v2 — Chip. Original work. Filter / token capsule.
// References: Apple Mail & Photos iOS 26 filter capsules, Linear filter chips, Kinetics "Choice Chips"
// (feel reference only, no code). Selected = tint-soft fill + a check that pops in (transform/opacity only,
// springs.bouncySubtle CSS mirror, motion.md §3.2). No width animation: the check slot appears instantly.
// Touch: 24 / 28 px tall, but the chip and its remove button get a 44 × 44 hit area on coarse pointers (ui/hit-area.ts);
// the remove button is 30 px wide there so its hit area stays inside the chip's own end padding.
import * as React from "react"
import { CheckIcon, XIcon } from "lucide-react"
import { cn } from "cn"

import { coarseHitArea } from "@/components/ui/hit-area"

type ChipProps = Omit<React.ComponentProps<"button">, "onChange"> & {
  /** toggle chips: pass `selected` + `onSelectedChange`; static token chips: omit both */
  selected?: boolean
  onSelectedChange?: (selected: boolean) => void
  icon?: React.ReactNode
  /** renders a trailing remove button with this accessible label */
  removeLabel?: string
  onRemove?: () => void
  size?: "sm" | "md"
}

function Chip({ className, selected, onSelectedChange, icon, removeLabel, onRemove, size = "md", children, onClick, ...props }: ChipProps) {
  const toggle = typeof selected === "boolean"
  const height = size === "sm" ? "h-6 type-footnote px-2.5" : "h-7 type-callout px-3"
  return (
    <span data-slot="chip" className="inline-flex shrink-0 items-center">
      <button
        type="button"
        aria-pressed={toggle ? selected : undefined}
        onClick={(event) => {
          onClick?.(event)
          if (!event.defaultPrevented && toggle) onSelectedChange?.(!selected)
        }}
        className={cn(
          "relative inline-flex items-center gap-1.5 rounded-full font-medium whitespace-nowrap select-none transition-[background-color,color,transform] duration-(--dur-fast) ease-(--spring-snappy) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-3.5 [&_svg]:shrink-0",
          coarseHitArea,
          height,
          selected
            ? "bg-tint-soft text-tint-text shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--accent)_30%,transparent)]"
            : "bg-fill-2 text-label-1 shadow-[inset_0_0_0_1px_var(--hairline)] hover:bg-fill-1",
          onRemove && "rounded-r-none pr-2",
          className
        )}
        {...props}
      >
        {toggle ? (
          selected ? (
            <span
              aria-hidden
              className="-ml-0.5 flex animate-in zoom-in-50 fade-in duration-(--spring-bouncy-subtle-ms) ease-(--spring-bouncy-subtle)"
            >
              <CheckIcon className="stroke-[2.5]" />
            </span>
          ) : null
        ) : null}
        {icon}
        {children}
      </button>
      {onRemove ? (
        <button
          type="button"
          aria-label={removeLabel ?? "Remove"}
          onClick={onRemove}
          className={cn(
            "relative inline-flex items-center justify-center rounded-r-full pr-2 pl-1 text-label-3 transition-colors hover:text-label-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) pointer-coarse:pr-2.5 pointer-coarse:pl-2 [&_svg]:size-3",
            coarseHitArea,
            size === "sm" ? "h-6" : "h-7",
            selected ? "bg-tint-soft" : "bg-fill-2 shadow-[inset_0_1px_0_0_var(--hairline),inset_0_-1px_0_0_var(--hairline),inset_-1px_0_0_0_var(--hairline)] hover:bg-fill-1"
          )}
        >
          <XIcon className="stroke-[2.25]" />
        </button>
      ) : null}
    </span>
  )
}

export { Chip, type ChipProps }
