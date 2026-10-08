// Source: shadcn/ui badge (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2: quieter fills, hairline instead of ring, status tones. API is a
// superset (adds tone="feasible" | … for the domain states; existing variant= values unchanged).
import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/* Badges are for state, not decoration (anti-pattern A4 in liquid-glass.md): one per row at most. */
const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent px-2 text-[11px] leading-none font-medium tracking-[0.005em] whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&>svg]:pointer-events-none [&>svg]:size-3! [&>svg]:stroke-[2]",
  {
    variants: {
      variant: {
        default: "bg-tint text-tint-foreground [a]:hover:bg-(--accent-hover)",
        secondary: "bg-fill-2 text-label-1 [a]:hover:bg-fill-1",
        destructive: "bg-status-infeasible text-status-infeasible-fg",
        outline: "border-hairline-strong text-label-2 [a]:hover:bg-fill-3 [a]:hover:text-label-1",
        ghost: "text-label-2 hover:bg-fill-2",
        link: "text-tint-text underline-offset-4 hover:underline",
      },
      tone: {
        none: "",
        feasible: "border-transparent bg-status-feasible text-status-feasible-fg",
        infeasible: "border-transparent bg-status-infeasible text-status-infeasible-fg",
        warning: "border-transparent bg-status-warning text-status-warning-fg",
        locked: "border-transparent bg-status-locked text-status-locked-fg",
        preoccupied: "border-transparent bg-status-preoccupied text-status-preoccupied-fg",
        tip: "border-transparent bg-status-tip text-status-tip-fg",
        pclab: "border-transparent bg-status-pclab text-status-pclab-fg",
        tint: "border-transparent bg-tint-soft text-tint-text",
      },
    },
    defaultVariants: {
      variant: "default",
      tone: "none",
    },
  }
)

function Badge({
  className,
  variant = "default",
  tone = "none",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant, tone }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
