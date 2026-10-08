// Source: shadcn/ui textarea (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2 filled field.
import * as React from "react"
import { cn } from "cn"

import { fieldSurface } from "@/components/ui/field-styles"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        fieldSurface,
        "flex field-sizing-content min-h-16 w-full rounded-xl px-3 py-2 text-base md:text-[13px]",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
