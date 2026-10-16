// SmartSched NativeSelect — an OS <select> dressed as a field (design-system overhaul 2026-10-15,
// docs/design/tokens.md §A.2/§A.5). Same surface, edge and --control-h as Input, so a select and an input in
// one row share height and corner; the chevron is centred with inset-y-0 + my-auto (it sat on the bottom edge
// on Generate). Native on purpose: robust in forms, full keyboard + screen-reader support, the OS picker on touch.
// 16 px text on touch phones (built in since 2026-10-16) so focusing it does not zoom the page on iOS.
import { ChevronDown } from "lucide-react"
import type { SelectHTMLAttributes } from "react"
import { cn } from "cn"

import { fieldSize, fieldSurface, type FieldSize } from "@/components/ui/field-styles"
import { coarsePhoneText } from "@/components/ui/hit-area"

type NativeSelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> & {
  /** classes for the wrapper (width, margins); the select fills it */
  className?: string
  /** classes for the <select> itself */
  selectClassName?: string
  size?: FieldSize
}

export function NativeSelect({ className, selectClassName, size = "md", children, ...props }: NativeSelectProps) {
  return (
    <span data-slot="native-select" className={cn("relative inline-flex w-full min-w-0", className)}>
      <select
        {...props}
        className={cn(fieldSurface, fieldSize[size], "w-full min-w-0 cursor-default appearance-none truncate pr-8", coarsePhoneText, selectClassName)}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute inset-y-0 right-2.5 my-auto size-3.5 stroke-[1.75] text-label-3"
      />
    </span>
  )
}
