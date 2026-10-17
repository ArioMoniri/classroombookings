// Source: shadcn/ui input (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2 filled field on --control-h + --edge-control (design-system overhaul 2026-10-15)
// + transitions.dev "Error state shake" hook (.t-input). 16 px text on touch phones so iOS does not zoom.
import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from "cn"

import { fieldSize, fieldSurface, type FieldSize } from "@/components/ui/field-styles"

function Input({ className, type, fieldSize: size = "md", ...props }: React.ComponentProps<"input"> & { fieldSize?: FieldSize }) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        fieldSurface,
        fieldSize[size],
        "w-full min-w-0 py-1 file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-label-1 pointer-coarse:text-base",
        className
      )}
      {...props}
    />
  )
}

/** Replays the transitions.dev "Error state shake" on an element that has `.t-input`.
 *  Call `shake()` when a submit fails; it is a no-op under prefers-reduced-motion (CSS rule). */
function useShake<T extends HTMLElement>() {
  const ref = React.useRef<T>(null)
  const shake = React.useCallback(() => {
    const el = ref.current
    if (!el) return
    el.classList.remove("is-shaking")
    void el.offsetWidth // restart the animation
    el.classList.add("is-shaking")
  }, [])
  return { ref, shake }
}

export { Input, useShake }
