// Source: shadcn/ui skeleton (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2: fill-2 shimmer-free pulse (static under reduced motion). API unchanged.
import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-lg bg-fill-2", className)}
      {...props}
    />
  )
}

export { Skeleton }
