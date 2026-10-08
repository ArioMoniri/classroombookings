"use client"
// SmartSched Liquid Glass v2 — Toolbar (floating capsule). Original work.
// Pattern references: Apple Music / Maps iOS 26 floating glass bars, Fey's web dock, Things 3 bulk
// bar (docs/design/v2/references.md). Chrome material: allowed over content (rule G1).
// a11y: role="toolbar", one tab stop, ← → Home End move focus between controls (WAI-ARIA APG).
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

import { Button } from "@/components/ui/button"

const toolbarVariants = cva(
  "glass-chrome inline-flex items-center gap-0.5 rounded-full p-1 text-label-1",
  {
    variants: {
      placement: {
        inline: "",
        /* floats above content, centred at the bottom; respects the home indicator */
        "floating-bottom":
          "fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-30 -translate-x-1/2 max-w-[calc(100vw-1.5rem)] overflow-x-auto",
        "floating-top": "sticky top-2 z-30",
      },
      size: {
        sm: "h-9 [&_[data-slot=button]]:h-7",
        md: "h-11",
      },
    },
    defaultVariants: { placement: "inline", size: "md" },
  }
)

function focusables(root: HTMLElement) {
  return Array.from(
    root.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input, [role="button"]:not([aria-disabled="true"])')
  ).filter((el) => el.closest('[data-slot="toolbar"]') === root)
}

function Toolbar({
  className,
  placement,
  size,
  orientation = "horizontal",
  onKeyDown,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof toolbarVariants> & { orientation?: "horizontal" | "vertical" }) {
  const ref = React.useRef<HTMLDivElement>(null)

  // Roving tab index: only the first (or last focused) control is in the tab order.
  React.useEffect(() => {
    const root = ref.current
    if (!root) return
    const items = focusables(root)
    if (!items.some((el) => el.tabIndex === 0)) items.forEach((el, i) => (el.tabIndex = i === 0 ? 0 : -1))
  })

  return (
    <div
      ref={ref}
      role="toolbar"
      aria-orientation={orientation}
      data-slot="toolbar"
      data-glass="chrome"
      className={cn(toolbarVariants({ placement, size }), orientation === "vertical" && "h-auto flex-col rounded-3xl", className)}
      onKeyDown={(event) => {
        onKeyDown?.(event)
        if (event.defaultPrevented || !ref.current) return
        const next = orientation === "vertical" ? "ArrowDown" : "ArrowRight"
        const prev = orientation === "vertical" ? "ArrowUp" : "ArrowLeft"
        if (![next, prev, "Home", "End"].includes(event.key)) return
        const items = focusables(ref.current)
        const index = items.indexOf(document.activeElement as HTMLElement)
        if (index < 0) return
        event.preventDefault()
        const target =
          event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === next ? 1 : -1) + items.length) % items.length
        items.forEach((el, i) => (el.tabIndex = i === target ? 0 : -1))
        items[target]?.focus()
      }}
      {...props}
    />
  )
}

function ToolbarButton({ className, variant = "ghost", size = "sm", ...props }: React.ComponentProps<typeof Button>) {
  return <Button variant={variant} size={size} className={cn("text-label-1", className)} {...props} />
}

function ToolbarSeparator({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      data-slot="toolbar-separator"
      className={cn("mx-1 h-5 w-px shrink-0 bg-hairline-strong", className)}
      {...props}
    />
  )
}

function ToolbarGroup({ className, ...props }: React.ComponentProps<"div">) {
  return <div role="group" data-slot="toolbar-group" className={cn("flex items-center gap-0.5", className)} {...props} />
}

/** Short status text inside a toolbar (e.g. "3 selected"). */
function ToolbarLabel({ className, ...props }: React.ComponentProps<"span">) {
  return <span data-slot="toolbar-label" className={cn("px-2.5 text-[13px] font-medium whitespace-nowrap text-label-2 tabular-nums", className)} {...props} />
}

export { Toolbar, ToolbarButton, ToolbarSeparator, ToolbarGroup, ToolbarLabel, toolbarVariants }
