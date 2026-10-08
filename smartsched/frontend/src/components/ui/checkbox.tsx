"use client"
// Source: shadcn/ui checkbox (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2: rounded square well, tint fill when checked, hairline at rest. API unchanged.

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { cn } from "cn"
import { CheckIcon } from "lucide-react"

function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative flex size-4 shrink-0 items-center justify-center rounded-[5px] bg-(--mat-thick) shadow-[inset_0_0_0_1px_var(--hairline-strong)] transition-colors duration-(--dur-fast) outline-none group-has-disabled/field:opacity-50 after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:shadow-[inset_0_0_0_1px_var(--status-infeasible-border)] data-checked:bg-tint data-checked:text-tint-foreground data-checked:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.25)]",
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
