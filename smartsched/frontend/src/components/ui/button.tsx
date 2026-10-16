// Source: shadcn/ui button (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2 colours + the design-system overhaul 2026-10-15 sizing system
// (docs/design/tokens.md §A.5): `size xs | sm | md | lg` reads --control-h-* (24/28/32/40 on fine pointers,
// 32/36/44/48 on coarse ones), padding-x = control height × .4375, gap 4 (xs/sm) / 6 (md/lg), icon 14 / 16.
// `shape "pill" | "rect"`: pills for actions that float or stand alone, rect (radius lg) for controls that sit
// in a row with fields, so a button and an input next to each other share height and corner.
// Legacy sizes (`default`, `icon*`) stay as aliases until every caller migrates; prefer `IconButton`.
// 2026-10-16 (ui primitives touch): `variant="bare"` + `BareButton` (moved from components/shell/bare-button); the
// coarse-pointer hit area is shared with Switch / Chip / SegmentedControl / DateField (ui/hit-area.ts).
import * as React from "react"
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

import { coarseHitArea } from "@/components/ui/hit-area"

/* Press = 0.97 scale on the snappy spring curve (CSS linear() mirror of springs.snappy; motion skill §5 press),
   removed under reduced motion by the global rule. Only transform/opacity/colour transition — never box-shadow. */
/* Touch: xs/sm stay 32/36 px tall (the coarse control scale) but their hit area is at least 44 × 44 (HIG);
   md/lg are already 44/48 on coarse pointers, so the ::after adds nothing there (ui/hit-area.ts). */
const buttonVariants = cva(
  "group/button relative inline-flex shrink-0 items-center justify-center bg-clip-padding font-medium tracking-[-0.003em] whitespace-nowrap select-none transition-[background-color,color,transform,opacity] duration-(--dur-fast) ease-(--spring-snappy) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) active:not-aria-[haspopup]:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 aria-invalid:outline-2 aria-invalid:outline-(--status-infeasible-border) [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:stroke-[1.75] " + coarseHitArea,
  {
    variants: {
      variant: {
        /* the single tint, with a 1px specular top edge so it reads as lit glass, not flat paint */
        default:
          "bg-tint text-tint-foreground shadow-[inset_0_1px_0_0_rgba(255,255,255,0.28),0_1px_2px_0_rgba(0,0,0,0.12)] hover:bg-(--accent-hover)",
        /* quiet control on any surface: thick colour + the 3:1 control edge */
        outline:
          "bg-(--mat-thick) text-label-1 shadow-(--edge-control) hover:bg-(--mat-thick-solid) aria-expanded:bg-(--mat-thick-solid)",
        secondary: "bg-fill-2 text-label-1 hover:bg-fill-1 aria-expanded:bg-fill-1",
        ghost: "text-label-1 hover:bg-fill-2 aria-expanded:bg-fill-2",
        destructive:
          "bg-status-infeasible text-status-infeasible-fg hover:bg-[color-mix(in_oklab,var(--status-infeasible-bg),var(--status-infeasible-fg)_8%)]",
        link: "h-auto! rounded-sm px-0! text-tint-text underline-offset-4 hover:underline active:scale-100",
        /** no fill, height, padding or pill: for controls that draw their own surface (see `BareButton`) */
        bare: "inline-block shrink items-stretch justify-normal whitespace-normal active:not-aria-[haspopup]:scale-100",
      },
      size: {
        xs: "h-(--control-h-xs) gap-1 px-[calc(var(--control-h-xs)*0.4375)] type-footnote font-medium [&_svg:not([class*='size-'])]:size-3.5",
        sm: "h-(--control-h-sm) gap-1 px-[calc(var(--control-h-sm)*0.4375)] type-footnote font-medium [&_svg:not([class*='size-'])]:size-3.5",
        md: "h-(--control-h-md) gap-1.5 px-[calc(var(--control-h-md)*0.4375)] type-callout font-medium [&_svg:not([class*='size-'])]:size-4",
        lg: "h-(--control-h-lg) gap-1.5 px-[calc(var(--control-h-lg)*0.4375)] type-body font-medium [&_svg:not([class*='size-'])]:size-4",
        /** @deprecated use size="md" */
        default: "h-(--control-h-md) gap-1.5 px-[calc(var(--control-h-md)*0.4375)] type-callout font-medium [&_svg:not([class*='size-'])]:size-4",
        /** @deprecated use <IconButton size="md" label=…> */
        icon: "size-(--control-h-md) [&_svg:not([class*='size-'])]:size-4",
        /** @deprecated use <IconButton size="xs" label=…> */
        "icon-xs": "size-(--control-h-xs) [&_svg:not([class*='size-'])]:size-3.5",
        /** @deprecated use <IconButton size="sm" label=…> */
        "icon-sm": "size-(--control-h-sm) [&_svg:not([class*='size-'])]:size-3.5",
        /** @deprecated use <IconButton size="lg" label=…> */
        "icon-lg": "size-(--control-h-lg) [&_svg:not([class*='size-'])]:size-4",
      },
      shape: {
        pill: "rounded-full",
        rect: "rounded-lg",
      },
    },
    compoundVariants: [
      /* trailing / leading icon: tighten the padding on that side by 2 px */
      { size: ["md", "default", "lg"], className: "has-data-[icon=inline-end]:pr-[calc(var(--control-h-md)*0.4375-2px)] has-data-[icon=inline-start]:pl-[calc(var(--control-h-md)*0.4375-2px)]" },
    ],
    defaultVariants: {
      variant: "default",
      size: "md",
      shape: "pill",
    },
  }
)

type ButtonProps = ButtonPrimitive.Props & VariantProps<typeof buttonVariants>

/** a font-weight utility (any variants) in the caller's classes: `bare` then keeps it instead of inheriting */
const WEIGHT = /(^|\s)(?:[\w-]+:)*font-(?:thin|extralight|light|normal|medium|semibold|bold|extrabold|black)(?=\s|$)/

/**
 * `variant="bare"`: the Button with no fill, height, padding or pill, for controls that draw their own surface
 * (grid cells, list rows, slot chips, cards, photo triggers). It keeps what every tab stop needs
 * (docs/design/tokens.md §A.1, §A.5): the focus ring, the disabled state, the svg defaults and the 44 × 44 hit
 * area on coarse pointers. Layout starts from the native button (inline-block, normal alignment, may shrink,
 * wraps), no press scale, and the weight follows the surrounding text unless the caller sets a `font-*`.
 * `data-slot="bare-button"`: not a sized control, so the design-system checks that read [data-slot=button] skip it.
 * `size` / `shape` default to none for `bare` (pass one explicitly to opt in).
 */
function Button({
  className,
  variant = "default",
  size = variant === "bare" ? null : "md",
  shape = variant === "bare" ? null : "pill",
  ...props
}: ButtonProps) {
  if (variant === "bare") {
    const compose = (extra: string | undefined) =>
      cn(buttonVariants({ variant, size, shape }), !WEIGHT.test(extra ?? "") && "[font-weight:inherit]", extra)
    return (
      <ButtonPrimitive
        data-slot="bare-button"
        data-size={size ?? undefined}
        data-shape={shape ?? undefined}
        className={typeof className === "function" ? (state) => compose(className(state)) : compose(className)}
        {...props}
      />
    )
  }
  return (
    <ButtonPrimitive
      data-slot="button"
      data-size={size}
      data-shape={shape}
      className={cn(buttonVariants({ variant, size, shape, className }))}
      {...props}
    />
  )
}

type BareButtonProps = Omit<ButtonProps, "variant" | "size" | "shape" | "className"> & { className?: string }

/** `<Button variant="bare">` with the narrower API callers already use (components/shell/bare-button re-exports it). */
function BareButton(props: BareButtonProps) {
  return <Button variant="bare" {...props} />
}

const iconButtonSize = {
  xs: "size-(--control-h-xs) [&_svg:not([class*='size-'])]:size-3.5",
  sm: "size-(--control-h-sm) [&_svg:not([class*='size-'])]:size-3.5",
  md: "size-(--control-h-md) [&_svg:not([class*='size-'])]:size-4",
  lg: "size-(--control-h-lg) [&_svg:not([class*='size-'])]:size-4",
} as const

type IconButtonProps = Omit<ButtonPrimitive.Props, "aria-label" | "children"> &
  Pick<VariantProps<typeof buttonVariants>, "variant" | "shape"> & {
    /** the accessible name; also the native tooltip. Required: an icon alone has no name. */
    label: string
    size?: keyof typeof iconButtonSize
    /** the icon; optional only when used as a render prop target (Base UI triggers pass their own children) */
    children?: React.ReactNode
  }

/** A square control with an icon only. `label` is required and becomes `aria-label` + `title`. */
function IconButton({ className, label, size = "md", variant = "ghost", shape = "pill", title, children, ...props }: IconButtonProps) {
  return (
    <ButtonPrimitive
      data-slot="icon-button"
      aria-label={label}
      title={title ?? label}
      className={cn(buttonVariants({ variant, shape }), "p-0", iconButtonSize[size], className)}
      {...props}
    >
      {children}
    </ButtonPrimitive>
  )
}

export { BareButton, Button, IconButton, buttonVariants, type BareButtonProps, type ButtonProps, type IconButtonProps }
