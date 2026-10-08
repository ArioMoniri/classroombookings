// Source: shadcn/ui button (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — restyled for Liquid Glass v2 (docs/design/v2/liquid-glass.md §9). API unchanged.
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/* Controls are capsules; containers use continuous radii. Press = 0.97 scale on the snappy
   spring curve (CSS linear() mirror of springs.snappy), removed under reduced motion by the global rule.
   Only transform/opacity/colour transition — never box-shadow (motion.md §8). */
const buttonVariants = cva(
  "group/button relative inline-flex shrink-0 items-center justify-center rounded-full border border-transparent bg-clip-padding text-[13px] font-medium tracking-[-0.003em] whitespace-nowrap outline-none select-none transition-[background-color,color,transform,opacity] duration-(--dur-fast) ease-(--spring-snappy) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) active:not-aria-[haspopup]:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 aria-invalid:outline-2 aria-invalid:outline-(--status-infeasible-border) [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg]:stroke-[1.75]",
  {
    variants: {
      variant: {
        /* the single tint, with a 1px specular top edge so it reads as lit glass, not flat paint */
        default:
          "bg-tint text-tint-foreground shadow-[inset_0_1px_0_0_rgba(255,255,255,0.28),0_1px_2px_0_rgba(0,0,0,0.12)] hover:bg-(--accent-hover)",
        /* "glass" control: thick tint + edge, no own backdrop-filter (it usually sits on glass) */
        outline:
          "bg-(--mat-thick) text-label-1 glass-edge hover:bg-(--mat-thick-solid) aria-expanded:bg-(--mat-thick-solid)",
        secondary:
          "bg-fill-2 text-label-1 hover:bg-fill-1 aria-expanded:bg-fill-1",
        ghost:
          "text-label-1 hover:bg-fill-2 aria-expanded:bg-fill-2",
        destructive:
          "bg-status-infeasible text-status-infeasible-fg hover:bg-[color-mix(in_oklab,var(--status-infeasible-bg),var(--status-infeasible-fg)_8%)]",
        link: "rounded-sm text-tint-text underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default:
          "h-8 gap-1.5 px-3.5 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        xs: "h-6 gap-1 px-2.5 text-xs has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 px-3 text-[12.5px] has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-10 gap-2 px-5 text-sm has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
        icon: "size-8",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 [&_svg:not([class*='size-'])]:size-3.5",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
