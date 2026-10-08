"use client"
// Source: shadcn/ui tabs (style base-nova, https://ui.shadcn.com) on @base-ui/react/tabs — Licence: MIT
// Modified: yes — Liquid Glass v2: segmented track with a morphing glass thumb (Base UI Tabs.Indicator,
// spring curve ≤ 300 ms, CSS-only so it also works before hydration). API unchanged; the indicator
// is rendered automatically inside TabsList.

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

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
  return (
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
          "pointer-events-none absolute -z-10 transition-[left,top,width,height] duration-(--dur-max) ease-(--ease-spring)",
          variant === "line"
            ? "bottom-[-5px] left-(--active-tab-left) h-0.5 w-(--active-tab-width) rounded-full bg-tint"
            : "top-(--active-tab-top) left-(--active-tab-left) h-(--active-tab-height) w-(--active-tab-width) rounded-full bg-(--mat-thick) shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline),0_1px_3px_0_rgba(0,0,0,0.1)]"
        )}
      />
    </TabsPrimitive.List>
  )
}

function TabsTrigger({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "relative inline-flex h-full flex-1 items-center justify-center gap-1.5 rounded-full px-3 text-[13px] font-medium whitespace-nowrap text-label-2 transition-colors duration-(--dur-fast) outline-none group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-label-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-(--focus) disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 data-active:text-label-1 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "group-data-[variant=line]/tabs-list:px-0.5 group-data-[variant=line]/tabs-list:data-active:text-label-1",
        className
      )}
      {...props}
    />
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
