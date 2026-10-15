// Source: shadcn/ui card (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — design-system overhaul 2026-10-15 (review §2 "Card / material", §4 item 2): the default is
// `plain` — an opaque surface with a hairline edge and no blur, radius xl (14 × k). The same frosted 32 px card
// around every block read as a template (anti-pattern A2); glass is for floating chrome, so `glass` stays an
// explicit opt-in (at most one hero per page, Vercel H8). `ghost` = hairline only, for groups that already sit
// on a surface; `inset` = recessed well. Radii follow the nesting rule: inner radius = outer radius − padding.
import * as React from "react"
import { cn } from "cn"

type CardVariant = "plain" | "glass" | "ghost" | "inset"

const cardVariant: Record<CardVariant, string> = {
  /* default: opaque surface + hairline, no backdrop-filter */
  plain: "bg-(--mat-regular-solid) edge-hairline",
  /* regular material over the scene (rule G1: regular never floats over content); opt-in */
  glass: "glass-regular",
  /* a group that already sits on a surface: hairline only */
  ghost: "bg-transparent edge-hairline",
  /* recessed well (filters, previews) */
  inset: "bg-fill-3 edge-hairline",
}

function Card({
  className,
  size = "default",
  variant = "plain",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "sm"; variant?: CardVariant }) {
  return (
    <div
      data-slot="card"
      data-size={size}
      data-variant={variant}
      data-glass={variant === "glass" ? "regular" : undefined}
      className={cn(
        "group/card flex flex-col gap-(--card-spacing) overflow-hidden rounded-xl py-(--card-spacing) text-sm text-card-foreground [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:rounded-lg data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-[inherit] *:[img:last-child]:rounded-b-[inherit]",
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
        "font-heading type-headline text-label-1 group-data-[size=sm]/card:type-callout group-data-[size=sm]/card:font-semibold",
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
      className={cn("type-callout text-label-2", className)}
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
