"use client"
// SmartSched Liquid Glass v2 — SidebarGlass. Original work.
// Pattern references (docs/design/v2/references.md): macOS 26 / iPadOS 26 floating sidebars (inset from
// the window edge, chrome material, content scrolls *under* nothing), Linear and Vercel sidebar density
// (28–32 px rows, quiet section labels), Craft's translucent rail. The active highlight glides between
// items with springs.glassMorph via SPRING_MORPH (instant under reduced motion); the pill is a fill
// without backdrop-filter (no glass on glass) and pointer-events:none.
import * as React from "react"
import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { LayoutGroup, motion } from "motion/react"
import { cn } from "cn"

import { SPRING_MORPH, useMotionSafe } from "@/components/ui/motion-presets"

function SidebarGlass({
  className,
  floating = true,
  children,
  "aria-label": ariaLabel = "Primary",
  ...props
}: React.ComponentProps<"nav"> & { floating?: boolean }) {
  const id = React.useId()
  return (
    <LayoutGroup id={id}>
      <nav
        aria-label={ariaLabel}
        data-slot="sidebar-glass"
        data-glass="chrome"
        className={cn(
          "glass-chrome flex min-h-0 flex-col text-label-1",
          floating ? "m-2 rounded-2xl" : "rounded-none shadow-[inset_-1px_0_0_0_var(--hairline)]",
          className
        )}
        {...props}
      >
        {children}
      </nav>
    </LayoutGroup>
  )
}

function SidebarGlassHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="sidebar-glass-header" className={cn("flex items-center gap-2 px-3 pt-3 pb-2", className)} {...props} />
}

function SidebarGlassContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="sidebar-glass-content" className={cn("scrollbar-thin flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2 py-1", className)} {...props} />
}

function SidebarGlassFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="sidebar-glass-footer" className={cn("mt-auto flex flex-col gap-1 px-2 pt-2 pb-2 hairline-t", className)} {...props} />
}

function SidebarGlassSection({
  title,
  className,
  children,
  ...props
}: React.ComponentProps<"div"> & { title?: React.ReactNode }) {
  const labelId = React.useId()
  return (
    <div role="group" aria-labelledby={title ? labelId : undefined} data-slot="sidebar-glass-section" className={cn("flex flex-col gap-px", className)} {...props}>
      {title ? (
        <div id={labelId} className="px-2.5 pb-1 text-[11px] font-semibold tracking-[0.02em] text-label-3">
          {title}
        </div>
      ) : null}
      <ul className="flex flex-col gap-px">{children}</ul>
    </div>
  )
}

type SidebarGlassItemProps = useRender.ComponentProps<"a"> & {
  active?: boolean
  icon?: React.ReactNode
  /** trailing count; rendered as plain tabular text, not a badge (anti-pattern A4) */
  count?: number
  /** trailing keyboard hint, e.g. <KbdHint keys={["G","D"]} /> */
  hint?: React.ReactNode
}

/** A navigation row. Pass `render={<Link href="…" />}` for Next.js links. */
function SidebarGlassItem({ className, active = false, icon, count, hint, children, render, ...props }: SidebarGlassItemProps) {
  const transition = useMotionSafe(SPRING_MORPH)
  const element = useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "group/sidebar-item relative flex h-8 items-center gap-2.5 rounded-[10px] px-2.5 text-[13px] font-medium text-label-1 outline-none transition-colors duration-(--dur-fast) hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus) aria-[current=page]:hover:bg-transparent [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:stroke-[1.75]",
          className
        ),
        "aria-current": active ? "page" : undefined,
        children: (
          <>
            {active ? (
              <motion.span
                layoutId="sidebar-glass-active"
                transition={transition}
                aria-hidden
                className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] bg-fill-1 shadow-[inset_0_1px_0_0_var(--specular-low)]"
              />
            ) : null}
            {icon ? <span className={cn("flex text-label-2", active && "text-tint-text")}>{icon}</span> : null}
            <span className="min-w-0 flex-1 truncate">{children}</span>
            {typeof count === "number" ? <span className="text-[12px] font-normal text-label-3 tabular-nums">{count}</span> : null}
            {hint ? <span className="hidden text-label-3 group-hover/sidebar-item:inline-flex">{hint}</span> : null}
          </>
        ),
      },
      props
    ),
  })
  return <li className="relative isolate list-none">{element}</li>
}

export { SidebarGlass, SidebarGlassHeader, SidebarGlassContent, SidebarGlassFooter, SidebarGlassSection, SidebarGlassItem }
