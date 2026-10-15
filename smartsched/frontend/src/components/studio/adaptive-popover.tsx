"use client";

/**
 * Studio backlog: slot pickers and class edits are popovers on a fine pointer and bottom sheets on a touch
 * screen (thumb reach, 44 px targets, a titled dialog). Drop-in for Popover / PopoverTrigger / PopoverContent.
 * The coarse query is false on the server and in tests, so the popover is the default.
 */
import { createContext, useContext, useSyncExternalStore, type ReactElement, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

const COARSE_QUERY = "(pointer: coarse)";
function subscribeCoarse(onChange: () => void) {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mql = window.matchMedia(COARSE_QUERY);
  mql.addEventListener?.("change", onChange);
  return () => mql.removeEventListener?.("change", onChange);
}
/** A touch screen is the primary pointer. */
export function useCoarsePointer(): boolean {
  return useSyncExternalStore(subscribeCoarse, () => Boolean(window.matchMedia?.(COARSE_QUERY).matches), () => false);
}

const Coarse = createContext(false);

export function AdaptivePopover({ open, onOpenChange, children }: { open?: boolean; onOpenChange?: (open: boolean) => void; children: ReactNode }) {
  const coarse = useCoarsePointer();
  const change = onOpenChange ? (o: boolean) => onOpenChange(o) : undefined;
  return (
    <Coarse.Provider value={coarse}>
      {coarse ? (
        <Sheet open={open} onOpenChange={change}>
          {children}
        </Sheet>
      ) : (
        <Popover open={open} onOpenChange={change}>
          {children}
        </Popover>
      )}
    </Coarse.Provider>
  );
}

export function AdaptiveTrigger({ render, children }: { render: ReactElement; children?: ReactNode }) {
  const coarse = useContext(Coarse);
  return coarse ? <SheetTrigger render={render}>{children}</SheetTrigger> : <PopoverTrigger render={render}>{children}</PopoverTrigger>;
}

export function AdaptiveContent({ title, className, align = "start", children }: { /** the sheet's title (touch) */ title: string; className?: string; align?: "start" | "center" | "end"; children: ReactNode }) {
  const coarse = useContext(Coarse);
  const { t } = useI18n();
  if (!coarse) {
    return (
      <PopoverContent className={className} align={align}>
        {children}
      </PopoverContent>
    );
  }
  return (
    <SheetContent side="bottom" className={cn("px-4 pb-[max(1rem,env(safe-area-inset-bottom))] [&_button]:min-h-11 [&_input]:min-h-11")} showCloseButton={false}>
      <SheetHeader className="p-0">
        <SheetTitle>{title}</SheetTitle>
      </SheetHeader>
      {children}
      <SheetClose render={<Button className="w-full" />}>{t("common.close")}</SheetClose>
    </SheetContent>
  );
}
