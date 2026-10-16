"use client"
// Source: shadcn/ui dialog (style base-nova, https://ui.shadcn.com) — Licence: MIT
// Modified: yes — Liquid Glass v2 thick material + transitions.dev "Modal open / close" (.t-modal), plain scrim overlay (no backdrop blur). API unchanged.
// Phones (< 640 px, 2026-10-16 mobile polish): the popup is a bottom sheet like ui/sheet (MOBILE.md M-04): full
// width, flush with the bottom edge, top corners only, at most the screen minus 3 rem tall, a transparent bottom
// border of env(safe-area-inset-bottom) so the content clears the home indicator while the material runs under it
// (a border, not padding: callers' p-* classes and the footer's -mb-5 keep working). It slides up on the sheet
// spring (transitions-dev.css, phone mapping). ≥ 640 px: centred, as before.
// T-R1-03 (R1-M-09, R1-M-37): the popup is a column: the children sit in a scrolling body ([data-slot=dialog-body],
// `-m/p` of the popup's padding so a caller's p-* on the popup still reads as the content inset), DialogHeader
// sticks to the top and DialogFooter to the bottom of that body on phones, and the close button is positioned on
// the popup, so the title, the close button and the primary action stay in view while the form scrolls
// (MOBILE.md M-05: the save button in the bottom 40 %). The phone surface is the solid thick material (no
// see-through tab bar). Keyboard: scroll-padding-bottom 6 rem + ui/keyboard-clearance, as in ui/sheet (T-R1-02).

import * as React from "react"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import { KeyboardClearance } from "@/components/ui/keyboard-clearance"
import { XIcon } from "lucide-react"
import { useT } from "@/lib/i18n/provider"

/** The close button's name in the user's language (T-R1-07: "Close" in the Turkish UI). */
function DialogCloseLabel() {
  const t = useT()
  return <>{t("common.close")}</>
}

function Dialog({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

/*
 * A plain scrim (motion.md: "scrim fade"; reduced transparency: the same scrim). No backdrop-filter: a
 * full-viewport blur re-rasterises the whole page, including every glass surface under it, on the opening
 * frame (the ⌘K long animation frame in the glass-shell motion audit), and the dialog's own thick glass
 * already separates it from the page.
 */
function DialogOverlay({
  className,
  ...props
}: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 bg-(--overlay) transition-opacity duration-(--dur-base) ease-out data-starting-style:opacity-0 data-ending-style:opacity-0 data-ending-style:duration-(--dur-fast)",
        className
      )}
      {...props}
    />
  )
}

function DialogContent({
  className,
  children,
  showCloseButton = true,
  ...props
}: DialogPrimitive.Popup.Props & {
  showCloseButton?: boolean
}) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Popup
        data-slot="dialog-content"
        className={cn(
          "t-modal glass-thick fixed top-1/2 left-1/2 z-50 flex w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-3xl [--dialog-pad:1.25rem] p-(--dialog-pad) text-sm text-label-1 outline-hidden sm:max-w-sm",
          // phone bottom sheet (see the header): these max-sm: variants sort after callers' unprefixed classes
          "max-sm:top-auto max-sm:bottom-0 max-sm:left-0 max-sm:w-full max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:max-h-[calc(100dvh-3rem)] max-sm:overflow-hidden max-sm:rounded-t-3xl max-sm:rounded-b-none max-sm:border-b-[length:env(safe-area-inset-bottom)] max-sm:border-b-transparent max-sm:bg-(--mat-thick-solid) max-sm:backdrop-filter-none",
          className
        )}
        {...props}
      >
        {/* the scrolling body: the children's grid, the popup's padding re-applied inside the scroller */}
        <div
          data-slot="dialog-body"
          className="-m-(--dialog-pad) flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain rounded-[inherit] p-(--dialog-pad) scroll-py-6 scroll-pb-24 [&>*]:scroll-pb-24"
        >
          {children}
          <KeyboardClearance />
        </div>
        {showCloseButton && (
          <DialogPrimitive.Close
            data-slot="dialog-close"
            render={
              <Button
                variant="ghost"
                className="absolute top-3 right-3 z-20 text-label-2"
                size="icon-sm"
              />
            }
          >
            <XIcon
            />
            <span className="sr-only">
              <DialogCloseLabel />
            </span>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Popup>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn(
        "flex flex-col gap-1.5 pr-8",
        // phones: stays at the top of the scrolling body, on the solid material (T-R1-03)
        "max-sm:sticky max-sm:top-0 max-sm:z-10 max-sm:-mx-(--dialog-pad) max-sm:-mt-(--dialog-pad) max-sm:bg-(--mat-thick-solid) max-sm:px-(--dialog-pad) max-sm:pt-(--dialog-pad) max-sm:pb-3",
        className
      )}
      {...props}
    />
  )
}

function DialogFooter({
  className,
  showCloseButton = false,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  showCloseButton?: boolean
}) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "-mx-5 -mb-5 flex flex-col-reverse gap-2 rounded-b-[inherit] bg-fill-3 px-5 py-4 hairline-t sm:flex-row sm:justify-end",
        // phones: sticks to the bottom of the scrolling body, opaque, so the primary action stays in thumb reach
        // while the form scrolls (T-R1-03, MOBILE.md M-05)
        "max-sm:sticky max-sm:bottom-0 max-sm:z-10 max-sm:bg-(--mat-thick-solid)",
        className
      )}
      {...props}
    >
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close render={<Button variant="outline" />}>
          <DialogCloseLabel />
        </DialogPrimitive.Close>
      )}
    </div>
  )
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn(
        "font-heading type-title-3 text-label-1",
        className
      )}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn(
        "type-callout leading-[18px] text-label-2 *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-label-1",
        className
      )}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
