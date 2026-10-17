"use client"
// Source: shadcn/ui checkbox (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2: rounded square well, tint fill when checked, hairline at rest. API unchanged.
// Hit area: ::after 12 px wider and 8 px taller on each side on fine pointers. Coarse pointers (T-R2-05, R2-M-23): the root
// is a REAL 44 × 44 box and the 16 px well is drawn by ::before centred in it (the ::after of round 1 was clipped by
// overflow:auto lists and table cells, so the tap went to the neighbour; MOBILE.md M-02, like Switch).

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { cn } from "cn"
import { CheckIcon } from "lucide-react"

function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative isolate flex size-4 pointer-coarse:size-11 shrink-0 items-center justify-center rounded-[5px] group-has-disabled/field:opacity-50 after:absolute after:-inset-x-3 after:-inset-y-2 pointer-coarse:after:inset-0 before:absolute before:inset-0 before:-z-10 before:rounded-[5px] before:bg-(--mat-thick) before:shadow-[inset_0_0_0_1px_var(--hairline-strong)] before:transition-colors before:duration-(--dur-fast) pointer-coarse:before:inset-[14px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:before:shadow-[inset_0_0_0_1px_var(--status-infeasible-border)] data-checked:before:bg-tint data-checked:text-tint-foreground data-checked:before:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.25)]",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none [&>svg]:size-3 [&>svg]:stroke-[3]"
      >
        <CheckIcon
        />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
