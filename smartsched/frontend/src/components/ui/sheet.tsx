"use client"
// Source: shadcn/ui sheet (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2: chrome material floating inset from the viewport edge (iOS 26 sheet /
// macOS inspector), springs.sheet CSS mirror (270 ms), exit 120 ms ease-in, side + bottom-sheet grabber. API unchanged.
// Phones (< 640 px, 2026-10-16): the bottom sheet is full width and flush with the bottom edge (MOBILE.md M-04),
// top corners only, and a transparent bottom border of env(safe-area-inset-bottom) keeps the content above the home
// indicator while the material runs under it (a border, not padding, so callers' p-* classes keep working).
// Larger screens keep the 8 px float, lifted above the safe area. The close button is a 36 px icon button on touch
// with the shared 44 × 44 coarse hit area (ui/hit-area.ts via Button).
// Keyboard (T-R1-02): the popup and its direct children (a caller's scrolling body) carry scroll-padding-bottom of
// 6 rem, so a focused field scrolls clear of the sticky SheetFooter; ui/keyboard-clearance re-scrolls the focused
// field when the on-screen keyboard resizes the viewport.
// T-R2-02: the popup is modal — aria-modal="true" and its own Tab trap (ui/focus-trap), like ui/dialog.
// Mobile audit A (2026-10-17): the bottom sheet's grabber is a real drag handle (drag down past 30 % of the height or
// flick to close; it snaps back otherwise), phones get the opaque material (no blur pass under the slide), the bottom
// inset follows Chrome's edge-to-edge pattern (max inset, pulled down by the live one) and --kb-inset (set by
// ui/keyboard-clearance from the visual viewport) lifts the sheet above the iOS keyboard.

import * as React from "react"
import { Dialog as SheetPrimitive } from "@base-ui/react/dialog"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import { KeyboardClearance } from "@/components/ui/keyboard-clearance"
import { useFocusTrap } from "@/components/ui/focus-trap"
import { XIcon } from "lucide-react"
import { useT } from "@/lib/i18n/provider"

function Sheet({ ...props }: SheetPrimitive.Root.Props) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

function SheetTrigger({ ...props }: SheetPrimitive.Trigger.Props) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetClose({ ...props }: SheetPrimitive.Close.Props) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

function SheetPortal({ ...props }: SheetPrimitive.Portal.Props) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />
}

function SheetOverlay({ className, ...props }: SheetPrimitive.Backdrop.Props) {
  return (
    <SheetPrimitive.Backdrop
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-(--overlay) transition-opacity duration-(--dur-slow) ease-out data-ending-style:opacity-0 data-starting-style:opacity-0 data-ending-style:duration-(--dur-base)",
        className
      )}
      {...props}
    />
  )
}

/** The close button's name in the user's language (persona U-09: "Close" in the Turkish UI). */
function SheetCloseLabel() {
  const t = useT()
  return <span className="sr-only">{t("common.close")}</span>
}

/** mobile-a fix 9: a drag down closes the sheet past 30 % of its height, or on a downward flick (> 0.5 px/ms). */
export function shouldDismissSheet(dy: number, height: number, velocity: number): boolean {
  return dy > height * 0.3 || (dy > 24 && velocity > 0.5)
}

/** The open sheet's backdrop (the overlay rendered just before the popup in the same portal). */
function backdropOf(el: HTMLElement): HTMLElement | null {
  const all = el.ownerDocument.querySelectorAll<HTMLElement>("[data-slot=sheet-overlay]")
  return all.length ? all[all.length - 1]! : null
}

/**
 * The grabber's pointer handlers: the popup follows the finger (no transition) and the backdrop fades with the offset
 * (HIG sheets), then it closes or snaps back. The snap-back uses the sheet's own spring transition, which the
 * reduced-motion tokens already shorten to an instant change.
 */
function useSheetDrag(popupRef: React.RefObject<HTMLDivElement | null>, closeRef: React.RefObject<HTMLButtonElement | null>) {
  const start = React.useRef<{ y: number; t: number; h: number } | null>(null)
  const end = (e: React.PointerEvent) => {
    const s = start.current
    const el = popupRef.current
    start.current = null
    if (!s || !el) return
    const dy = Math.max(0, e.clientY - s.y)
    el.style.transition = ""
    const backdrop = backdropOf(el)
    if (shouldDismissSheet(dy, s.h, dy / Math.max(1, performance.now() - s.t))) closeRef.current?.click()
    else el.style.translate = ""
    if (backdrop) backdrop.style.opacity = ""
  }
  const handlers = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      const el = popupRef.current
      if (!el) return
      start.current = { y: e.clientY, t: performance.now(), h: el.getBoundingClientRect().height }
      e.currentTarget.setPointerCapture?.(e.pointerId)
      el.style.transition = "none"
    },
    onPointerMove: (e: React.PointerEvent) => {
      const s = start.current
      const el = popupRef.current
      if (!s || !el) return
      const dy = Math.max(0, e.clientY - s.y)
      el.style.translate = `0 ${dy}px`
      const backdrop = backdropOf(el)
      if (backdrop) backdrop.style.opacity = Math.max(0, 1 - dy / Math.max(1, s.h)).toFixed(3)
    },
    onPointerUp: end,
    onPointerCancel: end,
  }
  return handlers
}

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: SheetPrimitive.Popup.Props & {
  side?: "top" | "right" | "bottom" | "left"
  showCloseButton?: boolean
}) {
  const popupRef = React.useRef<HTMLDivElement>(null)
  const trapTab = useFocusTrap(popupRef)
  const closeRef = React.useRef<HTMLButtonElement>(null)
  const grab = useSheetDrag(popupRef, closeRef)
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Popup
        data-slot="sheet-content"
        data-side={side}
        aria-modal="true"
        ref={popupRef}
        onKeyDown={trapTab}
        className={cn(
          "glass-chrome fixed z-50 flex flex-col gap-4 overflow-hidden text-sm text-label-1 scroll-pb-24 [&>*]:scroll-pb-24 transition-[translate,opacity] duration-(--spring-sheet-ms) ease-(--spring-sheet) data-ending-style:opacity-0 data-ending-style:duration-(--dur-fast) data-ending-style:ease-(--ease-in) data-starting-style:opacity-0 data-[side=bottom]:inset-x-2 data-[side=bottom]:bottom-[max(0.5rem,env(safe-area-inset-bottom))] data-[side=bottom]:h-auto max-sm:data-[side=bottom]:inset-x-0 max-sm:data-[side=bottom]:bottom-[calc(var(--kb-inset,0px)+env(safe-area-inset-bottom,0px)-env(safe-area-max-inset-bottom,env(safe-area-inset-bottom,0px)))] max-sm:data-[side=bottom]:[--mat-chrome:var(--mat-thick-solid)] max-sm:data-[side=bottom]:[--mat-chrome-filter:none] max-sm:data-[side=bottom]:rounded-b-none max-sm:data-[side=bottom]:border-b-[length:env(safe-area-max-inset-bottom,env(safe-area-inset-bottom,0px))] max-sm:data-[side=bottom]:border-b-transparent data-[side=bottom]:max-h-[calc(100dvh-3rem-var(--kb-inset,0px))] data-[side=bottom]:rounded-3xl data-[side=bottom]:pt-2 data-[side=bottom]:data-ending-style:translate-y-[2.5rem] data-[side=bottom]:data-starting-style:translate-y-[2.5rem] data-[side=left]:inset-y-2 data-[side=left]:left-2 data-[side=left]:h-[calc(100%-1rem)] data-[side=left]:w-3/4 data-[side=left]:rounded-2xl data-[side=left]:data-ending-style:translate-x-[-2.5rem] data-[side=left]:data-starting-style:translate-x-[-2.5rem] data-[side=right]:inset-y-2 data-[side=right]:right-2 data-[side=right]:h-[calc(100%-1rem)] data-[side=right]:w-3/4 data-[side=right]:rounded-2xl data-[side=right]:data-ending-style:translate-x-[2.5rem] data-[side=right]:data-starting-style:translate-x-[2.5rem] data-[side=top]:inset-x-2 data-[side=top]:top-2 data-[side=top]:h-auto data-[side=top]:rounded-3xl data-[side=top]:data-ending-style:translate-y-[-2.5rem] data-[side=top]:data-starting-style:translate-y-[-2.5rem] data-[side=left]:sm:max-w-sm data-[side=right]:sm:max-w-sm",
          className
        )}
        {...props}
      >
        {side === "bottom" ? (
          <>
            <div aria-hidden data-slot="sheet-grabber" {...grab} className="relative mx-auto h-1 w-9 shrink-0 cursor-grab touch-none rounded-full bg-fill-1 after:absolute after:-inset-x-20 after:-inset-y-5 after:content-['']" />
            <SheetPrimitive.Close ref={closeRef} hidden tabIndex={-1} aria-hidden data-slot="sheet-drag-close" />
          </>
        ) : null}
        {children}
        <KeyboardClearance />
        {showCloseButton && (
          <SheetPrimitive.Close
            data-slot="sheet-close"
            render={
              <Button
                variant="ghost"
                className="absolute top-3 right-3 text-label-2"
                size="icon-sm"
              />
            }
          >
            <XIcon
            />
            <SheetCloseLabel />
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Popup>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-0.5 p-4", className)}
      {...props}
    />
  )
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 p-4 hairline-t", className)}
      {...props}
    />
  )
}

function SheetTitle({ className, ...props }: SheetPrimitive.Title.Props) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn(
        "font-heading type-title-3 text-label-1",
        className
      )}
      {...props}
    />
  )
}

function SheetDescription({
  className,
  ...props
}: SheetPrimitive.Description.Props) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("type-callout leading-[18px] text-label-2", className)}
      {...props}
    />
  )
}

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
}
