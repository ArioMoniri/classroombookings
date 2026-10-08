// Source: shadcn/ui input (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2 filled field + transitions.dev "Error state shake" hook (.t-input).
import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from "cn"

import { fieldSurface } from "@/components/ui/field-styles"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        fieldSurface,
        "h-8 w-full min-w-0 px-3 py-1 text-base file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-label-1 md:text-[13px]",
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
