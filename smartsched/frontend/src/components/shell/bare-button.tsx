"use client";
// The Button primitive with no fill, height, padding or pill (variant / size / shape = null in the cva): for
// controls that draw their own surface (grid cells, list rows, slot chips, cards, photo triggers). It keeps what
// every tab stop needs (docs/design/tokens.md §A.1, §A.5): the focus ring, the disabled state, the svg defaults
// and the 44 × 44 hit area on coarse pointers. Layout starts from the native button (inline-block, normal
// alignment, may shrink, wraps) and weight follows the surrounding text, unless the caller's classes say otherwise. Replaces the raw button elements the design gate bans outside components/ui (review §2).
// Candidate for components/ui as `variant="bare"` (design-migration hand-off).
import { Button, type ButtonProps } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const WEIGHT = /(^|\s)(?:[\w-]+:)*font-(?:thin|extralight|light|normal|medium|semibold|bold|extrabold|black)(?=\s|$)/;

export type BareButtonProps = Omit<ButtonProps, "variant" | "size" | "shape" | "className"> & { className?: string };

export function BareButton({ className, ...props }: BareButtonProps) {
  const cls = className ?? "";
  return (
    <Button
      variant={null}
      size={null}
      shape={null}
      // not a sized control (no --control-h): the design-system checks that read [data-slot=button] skip it
      data-slot="bare-button"
      className={cn("inline-block shrink items-stretch justify-normal whitespace-normal active:not-aria-[haspopup]:scale-100", !WEIGHT.test(cls) && "[font-weight:inherit]", className)}
      {...props}
    />
  );
}
