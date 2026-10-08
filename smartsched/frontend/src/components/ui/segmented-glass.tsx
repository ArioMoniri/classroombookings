"use client"
// SmartSched Liquid Glass v2 — SegmentedGlass. Built on the beUI Tabs component (MIT, Saurabh Chauhan,
// src/components/ui/beui/tabs.tsx): its layoutId indicator and clip-path label masking give the
// "liquid" morph — the active label is revealed exactly where the glass thumb is, mid-flight.
// Our layer adds: glass track + thumb, sizes, icons, roving focus with ← → Home End (WAI-ARIA tabs
// pattern, automatic activation), and an optional `aria-controls` per option.
import * as React from "react"
import { cn } from "cn"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/beui/tabs"

export type SegmentedOption<V extends string = string> = {
  value: V
  label: React.ReactNode
  icon?: React.ReactNode
  /** id of the panel this segment shows, if any */
  controls?: string
  disabled?: boolean
}

type SegmentedGlassProps<V extends string> = {
  options: SegmentedOption<V>[]
  value?: V
  defaultValue?: V
  onValueChange?: (value: V) => void
  size?: "sm" | "md"
  /** stretch segments to fill the container (mobile) */
  fill?: boolean
  className?: string
  "aria-label": string
}

function SegmentedGlass<V extends string>({
  options,
  value,
  defaultValue,
  onValueChange,
  size = "md",
  fill = false,
  className,
  "aria-label": ariaLabel,
}: SegmentedGlassProps<V>) {
  const [internal, setInternal] = React.useState<V | undefined>(defaultValue ?? options[0]?.value)
  const current = value ?? internal
  const listRef = React.useRef<HTMLDivElement>(null)
  const select = React.useCallback(
    (v: string) => {
      if (value === undefined) setInternal(v as V)
      onValueChange?.(v as V)
    },
    [onValueChange, value]
  )

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return
    const enabled = options.filter((o) => !o.disabled)
    const index = enabled.findIndex((o) => o.value === current)
    const rtl = listRef.current ? getComputedStyle(listRef.current.parentElement ?? document.documentElement).direction === "rtl" : false
    const forward = rtl ? "ArrowLeft" : "ArrowRight"
    const target =
      event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : (index + (event.key === forward ? 1 : -1) + enabled.length) % enabled.length
    const next = enabled[target]
    if (!next) return
    event.preventDefault()
    select(next.value)
    requestAnimationFrame(() => listRef.current?.querySelector<HTMLElement>(`[data-tabs-value="${CSS.escape(next.value)}"]`)?.focus())
  }

  const height = size === "sm" ? "h-7 text-[12px]" : "h-8 text-[13px]"

  return (
    <div ref={listRef} className={cn("contents")} data-slot="segmented-glass">
    <Tabs value={current ?? ""} onValueChange={select} variant="segment" className={cn(fill ? "w-full" : "w-fit", className)}>
      <TabsList
        aria-label={ariaLabel}
        onKeyDown={onKeyDown}
        wrapperClassName={cn(fill && "w-full")}
        className={cn(
          "gap-0.5 rounded-full bg-fill-2 p-[3px] shadow-[inset_0_0_0_1px_var(--hairline)]",
          fill && "flex w-full [&>div]:flex-1"
        )}
      >
        {options.map((option) => {
          const active = option.value === current
          return (
            <TabsTrigger
              key={option.value}
              value={option.value}
              disabled={option.disabled}
              tabIndex={active ? 0 : -1}
              aria-controls={option.controls}
              className={cn(
                "w-full gap-1.5 rounded-full px-3.5 font-medium text-label-2 transition-colors duration-(--dur-fast) hover:text-label-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-(--focus) disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-3.5 [&_svg]:shrink-0",
                height
              )}
              indicatorClassName="rounded-full bg-(--mat-thick) shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline),0_1px_3px_0_rgba(0,0,0,0.1)]"
              labelClassName="text-label-1"
            >
              {option.icon}
              {option.label}
            </TabsTrigger>
          )
        })}
      </TabsList>
    </Tabs>
    </div>
  )
}

export { SegmentedGlass }
