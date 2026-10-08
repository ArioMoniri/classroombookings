// Source: shadcn/ui card (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2. Adds variant="glass" (default) | "plain" | "inset"; existing
// props (size) unchanged. Radii follow the nesting rule: inner radius = outer radius − padding.
import * as React from "react"
import { cn } from "cn"

type CardVariant = "glass" | "plain" | "inset"

const cardVariant: Record<CardVariant, string> = {
  /* regular material over the scene (rule G1: regular never floats over content) */
  glass: "glass-regular",
  /* grouped section that already sits on glass: hairline only, no second blur */
  plain: "bg-transparent shadow-[0_0_0_1px_var(--hairline)]",
  /* recessed well (filters, previews) */
  inset: "bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)]",
}

function Card({
  className,
  size = "default",
  variant = "glass",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "sm"; variant?: CardVariant }) {
  return (
    <div
      data-slot="card"
      data-size={size}
      data-variant={variant}
      data-glass={variant === "glass" ? "regular" : undefined}
      className={cn(
        "group/card flex flex-col gap-(--card-spacing) overflow-hidden rounded-2xl py-(--card-spacing) text-sm text-card-foreground [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:rounded-xl data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-[inherit] *:[img:last-child]:rounded-b-[inherit]",
        cardVariant[variant],
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-0.5 px-(--card-spacing) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn(
        "font-heading text-[15px] leading-5 font-semibold tracking-[-0.009em] text-label-1 group-data-[size=sm]/card:text-[13px]",
        className
      )}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-[13px] leading-[18px] text-label-2", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-(--card-spacing)", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center gap-2 bg-fill-3 p-(--card-spacing) hairline-t",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
