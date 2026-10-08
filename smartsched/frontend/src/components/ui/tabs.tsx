"use client"
// Source: shadcn/ui tabs (style base-nova, https://ui.shadcn.com) on @base-ui/react/tabs — Licence: MIT
// Modified: yes — Liquid Glass v2: segmented track with a morphing thumb. The thumb is a motion `layoutId`
// element rendered inside the active tab (transform-only FLIP, springs.glassMorph, motion.md §2/§8), one
// LayoutGroup per list so two tab lists never share a thumb. The thumb is a translucent fill without
// backdrop-filter (no glass on glass) and pointer-events:none. API unchanged.

import * as React from "react"
import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cva, type VariantProps } from "class-variance-authority"
import { LayoutGroup, motion } from "motion/react"
import { cn } from "cn"

import { springs, useReduce } from "@/lib/motion"

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
  "group/tabs-list relative isolate inline-flex w-fit items-center justify-center text-label-2 group-data-horizontal/tabs:h-8 group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col",
  {
    variants: {
      variant: {
        /* segmented: fill track, the thumb is a small piece of thick glass */
        default: "gap-0.5 rounded-full bg-fill-2 p-[3px] shadow-[inset_0_0_0_1px_var(--hairline)]",
        /* line: text tabs with a tint underline that glides */
        line: "gap-4 rounded-none bg-transparent",
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
  const group = React.useId()
  return (
    <TabsVariantContext.Provider value={variant ?? "default"}>
      <LayoutGroup id={group}>
        <TabsPrimitive.List
          data-slot="tabs-list"
          data-variant={variant}
          className={cn(tabsListVariants({ variant }), className)}
          {...props}
        >
          {children}
        </TabsPrimitive.List>
      </LayoutGroup>
    </TabsVariantContext.Provider>
  )
}

function TabThumb({ variant }: { variant: "default" | "line" }) {
  const reduce = useReduce()
  return (
    <motion.span
      layoutId="tabs-thumb"
      aria-hidden
      data-slot="tabs-indicator"
      transition={reduce ? { duration: 0 } : springs.glassMorph}
      style={{ borderRadius: 999 }}
      className={cn(
        "pointer-events-none absolute -z-10",
        variant === "line"
          ? "inset-x-0 -bottom-[5px] h-0.5 bg-tint"
          : "inset-0 bg-(--mat-thick) shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline),0_1px_3px_0_rgba(0,0,0,0.1)]"
      )}
    />
  )
}

function TabsTrigger({ className, children, ...props }: TabsPrimitive.Tab.Props) {
  const variant = React.useContext(TabsVariantContext)
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      render={(renderProps, state) => (
        <button {...renderProps}>
          {state.active ? <TabThumb variant={variant} /> : null}
          {renderProps.children}
        </button>
      )}
      className={cn(
        "relative isolate inline-flex h-full flex-1 items-center justify-center gap-1.5 rounded-full px-3 text-[13px] font-medium whitespace-nowrap text-label-2 transition-colors duration-(--dur-fast) outline-none group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-label-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-(--focus) disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 data-active:text-label-1 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "group-data-[variant=line]/tabs-list:px-0.5 group-data-[variant=line]/tabs-list:data-active:text-label-1",
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
      className={cn("flex-1 text-sm outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
