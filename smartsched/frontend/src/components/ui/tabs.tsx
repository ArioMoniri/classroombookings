"use client"
// Source: shadcn/ui tabs (style base-nova, https://ui.shadcn.com) on @base-ui/react/tabs — Licence: MIT
// Modified: yes — the default variant is the SegmentedControl look (components/ui/segmented-control.tsx):
// same track, same --control-h, same lit thumb. Since the design-system overhaul (2026-10-15) the thumb is
// Base UI's Tabs.Indicator positioned by its CSS variables (--active-tab-left/-width): its resting place is
// pure CSS, so it cannot sit outside the track (the dark "thumb 16 px above the track" bug was a layoutId
// projection at rest). Only `transform` transitions, on --spring-glass-morph (motion pattern 2); the width
// snaps. Reduced motion: the global rule zeroes the duration. API unchanged.
// Touch (2026-10-16 mobile polish; T-R2-05): triggers are at least 44 px tall on coarse pointers (the shared track drops its
// vertical padding there, segmented-control.tsx) and carry the 44 × 44 coarse hit area (ui/hit-area.ts) for narrow ones,
// so a tap on the track's rim still selects the tab even inside a clipping list (MOBILE.md M-02).

import * as React from "react"
import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

import { coarseHitArea } from "@/components/ui/hit-area"
import { segmentedThumb, segmentedTrack } from "@/components/ui/segmented-control"

const TabsVariantContext = React.createContext<"default" | "line">("default")

function Tabs({
  className,
  orientation = "horizontal",
  ...props
}: TabsPrimitive.Root.Props) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      data-orientation={orientation}
      className={cn(
        "group/tabs flex gap-3 data-horizontal:flex-col",
        className
      )}
      {...props}
    />
  )
}

const tabsListVariants = cva(
  "group/tabs-list relative isolate w-fit text-label-2 group-data-horizontal/tabs:h-(--control-h-md) group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col group-data-vertical/tabs:pointer-coarse:py-[3px]",
  {
    variants: {
      variant: {
        /* segmented: fill track, the thumb is a small piece of thick glass */
        default: segmentedTrack,
        /* line: text tabs with a tint underline that glides */
        line: "inline-flex items-center gap-4 rounded-none bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function TabsList({
  className,
  variant = "default",
  children,
  ...props
}: TabsPrimitive.List.Props & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsVariantContext.Provider value={variant ?? "default"}>
      <TabsPrimitive.List
        data-slot="tabs-list"
        data-variant={variant}
        className={cn(tabsListVariants({ variant }), className)}
        {...props}
      >
        {children}
        <TabsPrimitive.Indicator
          data-slot="tabs-indicator"
          renderBeforeHydration
          className={cn(
            variant === "line"
              ? "pointer-events-none absolute -bottom-[5px] left-0 h-0.5 w-(--active-tab-width) translate-x-(--active-tab-left) rounded-full bg-tint transition-transform duration-(--spring-glass-morph-ms) ease-(--spring-glass-morph)"
              : cn(segmentedThumb, "left-0 w-(--active-tab-width) translate-x-(--active-tab-left)")
          )}
        />
      </TabsPrimitive.List>
    </TabsVariantContext.Provider>
  )
}

function TabsTrigger({ className, children, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "relative inline-flex h-full flex-1 items-center justify-center gap-1.5 rounded-full px-3 pointer-coarse:min-h-11 type-callout font-medium whitespace-nowrap text-label-2 transition-colors duration-(--dur-fast) group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-label-1 focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-1 focus-visible:outline-(--focus) disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 data-active:text-label-1 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "group-data-[variant=line]/tabs-list:px-0.5 group-data-[variant=line]/tabs-list:data-active:text-label-1",
        coarseHitArea,
        className
      )}
      {...props}
    >
      {children}
    </TabsPrimitive.Tab>
  )
}

function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      className={cn("flex-1 rounded-[inherit] text-sm focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
