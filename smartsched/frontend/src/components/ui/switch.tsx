"use client"
// Source: shadcn/ui switch (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2: iOS-proportioned capsule, white lit thumb on springs.snappy (CSS mirror), tint when on. API unchanged.
// Hit area: ::after 12 px wider and 8 px taller on each side on fine pointers. Coarse pointers (T-R2-05, R2-S-08 / R2-M-13):
// the root is a REAL 44 × 44 box (min-h-11 / min-w-11, the ::after stops at its edges) and the capsule (22 × 38, sm 16 × 28)
// is drawn by ::before centred in it (the thumb travels ±8 px / ±6 px from the centre), so a tap 22 px off the thumb still lands on the switch even where an overflow:auto card list or
// a table cell clips pseudo-elements (MOBILE.md M-02). A <label> row keeps toggling the whole row (globals.css).

import { Switch as SwitchPrimitive } from "@base-ui/react/switch"
import { cn } from "cn"

function Switch({
  className,
  size = "default",
  ...props
}: SwitchPrimitive.Root.Props & {
  size?: "sm" | "default"
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative isolate inline-flex shrink-0 items-center justify-center rounded-full p-[2px] pointer-coarse:min-h-11 pointer-coarse:min-w-11 after:absolute after:-inset-x-3 after:-inset-y-2 pointer-coarse:after:inset-0 before:absolute before:inset-0 before:-z-10 before:rounded-full before:transition-colors before:duration-(--dur-base) pointer-coarse:data-[size=default]:before:inset-y-[calc(50%-11px)] pointer-coarse:data-[size=default]:before:inset-x-[calc(50%-19px)] pointer-coarse:data-[size=sm]:before:inset-y-[calc(50%-8px)] pointer-coarse:data-[size=sm]:before:inset-x-[calc(50%-14px)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) aria-invalid:outline-2 aria-invalid:outline-(--status-infeasible-border) data-[size=default]:h-[22px] data-[size=default]:w-[38px] data-[size=sm]:h-[16px] data-[size=sm]:w-[28px] data-checked:before:bg-tint data-unchecked:before:bg-fill-1 data-disabled:cursor-not-allowed data-disabled:opacity-45",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block rounded-full bg-white shadow-[0_0_0_0.5px_rgba(0,0,0,0.06),0_2px_5px_rgba(0,0,0,0.18),inset_0_-1px_0_rgba(0,0,0,0.04)] transition-transform duration-(--spring-snappy-ms) ease-(--spring-snappy) group-data-[size=default]/switch:size-[18px] group-data-[size=sm]/switch:size-3 group-data-[size=default]/switch:-translate-x-2 group-data-[size=default]/switch:data-checked:translate-x-2 group-data-[size=sm]/switch:-translate-x-1.5 group-data-[size=sm]/switch:data-checked:translate-x-1.5"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
