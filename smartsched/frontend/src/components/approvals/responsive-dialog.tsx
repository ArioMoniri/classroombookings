"use client";
/**
 * A dialog on desktop and tablet, a bottom sheet on phones (MOBILE.md M-04: full width, anchored to the bottom,
 * scrolling inside itself, the primary action in a sticky footer above the home indicator, M-05 / M-06). Used by
 * the reject dialog and the withdraw confirmation, so both read the same on every viewport.
 *
 * Motion: the design system's own dialog (.t-modal) and sheet (springs.sheet CSS mirror, 270 ms) transitions,
 * which the global reduced-motion rule already zeroes; nothing is added here.
 */
import type { ReactNode, RefObject } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { cn } from "@/lib/utils";

export function ResponsiveDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  testId,
  role,
  initialFocus,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  /** the actions (sticky sheet footer on phone); omit when the body brings its own */
  footer?: ReactNode;
  testId?: string;
  /** `alertdialog` for confirmations */
  role?: "dialog" | "alertdialog";
  initialFocus?: RefObject<HTMLElement | null>;
  className?: string;
}) {
  const phone = useIsPhone();
  if (phone) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="bottom"
          role={role}
          initialFocus={initialFocus}
          // full width and flush with the bottom edge (M-04); the Sheet's safe-area border keeps the footer above
          // the home indicator (M-06), so the footer itself pads 16 px only
          className={cn("inset-x-0! bottom-0! max-h-[calc(100dvh-1rem)]! gap-0 rounded-b-none!", className)}
          data-testid={testId}
        >
          <SheetHeader className="px-5 pt-3 pb-2 pr-12">
            <SheetTitle>{title}</SheetTitle>
            {description ? <SheetDescription>{description}</SheetDescription> : null}
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-5 pb-4">{children}</div>
          {footer ? <SheetFooter className="flex-col-reverse gap-2 px-5 pt-3 pb-4 [&>button]:w-full">{footer}</SheetFooter> : null}
        </SheetContent>
      </Sheet>
    );
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent role={role} initialFocus={initialFocus} className={cn("max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg", className)} data-testid={testId}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children ? <div className="flex flex-col gap-4">{children}</div> : null}
        {footer ? <DialogFooter>{footer}</DialogFooter> : null}
      </DialogContent>
    </Dialog>
  );
}
