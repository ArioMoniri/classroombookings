"use client";
/**
 * A confirm that is a centred alertdialog on tablets and desktops and a bottom sheet on phones (owner
 * requirement 2026-10-15: every dialog is a bottom sheet at 390 px; motion pattern 4, `sheet` spring via the
 * Sheet primitive). Same parts either way: title, description, body, footer.
 */
import type { ReactNode, RefObject } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { usePhone } from "./use-media";

export function ResponsiveDialog({ open, onOpenChange, title, description, children, footer, alert = false, initialFocus, className, testId }: { open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children?: ReactNode; footer: ReactNode; alert?: boolean; initialFocus?: RefObject<HTMLElement | null>; className?: string; testId?: string }) {
  const phone = usePhone();
  if (phone) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" role={alert ? "alertdialog" : "dialog"} initialFocus={initialFocus} className={cn("max-h-[92dvh] gap-3 overflow-y-auto p-5", className)} data-testid={testId} data-variant="sheet">
          <SheetHeader className="p-0">
            <SheetTitle>{title}</SheetTitle>
            {description ? <SheetDescription>{description}</SheetDescription> : null}
          </SheetHeader>
          {children}
          <SheetFooter className="sticky bottom-0 flex-col-reverse gap-2 p-0 [&_button]:w-full">{footer}</SheetFooter>
        </SheetContent>
      </Sheet>
    );
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent role={alert ? "alertdialog" : "dialog"} initialFocus={initialFocus} className={cn("sm:max-w-lg", className)} data-testid={testId} data-variant="dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {children}
        <DialogFooter>{footer}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
