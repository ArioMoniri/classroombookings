"use client"
// SmartSched keyboard clearance (T-R1-02, R1-A-03; MOBILE.md M-05). Original work.
// A bottom sheet or phone dialog has a sticky footer, and on a phone the on-screen keyboard takes the lower half of
// the screen (the root viewport carries interactive-widget=resizes-content, so the layout viewport shrinks with it).
// Rendered as the last child of a Sheet / Dialog popup, this keeps the focused field readable:
//   - on focusin of a text field inside the popup, after the keyboard had its first frame, the field is scrolled
//     into the nearest scroller (`scrollIntoView({ block: "nearest" })`); the popup and its direct children carry
//     scroll-padding-bottom (ui/sheet, ui/dialog), so "nearest" lands above a footer of ordinary height;
//   - then, if the field still sits under a sticky footer or header of the popup (a two-button phone footer is
//     taller than any fixed padding), the nearest scroller moves by the overlap (`overlapWith`);
//   - when the visual viewport resizes while a field inside the popup has focus (the keyboard opening or closing),
//     the same runs again.
// The element itself is an empty hidden <span>; it only needs its parent (the popup).
import * as React from "react"

const FIELD = 'input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([type="file"]), textarea, select, [contenteditable=""], [contenteditable="true"]'
const BARS = { header: "[data-slot=sheet-header], [data-slot=dialog-header]", footer: "[data-slot=sheet-footer], [data-slot=dialog-footer]" } as const

type Box = Pick<DOMRect, "top" | "bottom">

export function isTextField(el: Element | null): el is HTMLElement {
  return !!el && el instanceof HTMLElement && el.matches(FIELD)
}

/**
 * How far the field's scroller must move so the field clears the popup's sticky bars: positive = down (the field
 * is under the footer), negative = up (under the header), 0 = clear. `gap` is the air kept between them.
 */
export function overlapWith(field: Box, header: Box | null, footer: Box | null, gap = 8): number {
  if (footer && field.bottom + gap > footer.top && field.top < footer.bottom) return Math.round(field.bottom + gap - footer.top)
  if (header && field.top - gap < header.bottom && field.bottom > header.top) return Math.round(field.top - gap - header.bottom)
  return 0
}

/** The popup's sticky header / footer (only a sticky bar can cover a field inside the scroller). */
function stickyBar(root: HTMLElement, which: keyof typeof BARS): HTMLElement | null {
  for (const el of root.querySelectorAll<HTMLElement>(BARS[which])) if (getComputedStyle(el).position === "sticky") return el
  return null
}

/** The nearest ancestor (up to and including the popup) that scrolls vertically. */
function scrollerOf(field: HTMLElement, root: HTMLElement): HTMLElement | null {
  let el: HTMLElement | null = field.parentElement
  while (el) {
    const cs = getComputedStyle(el)
    if (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1) return el
    if (el === root) break
    el = el.parentElement
  }
  return null
}

export function KeyboardClearance() {
  const ref = React.useRef<HTMLSpanElement>(null)
  React.useEffect(() => {
    const root = ref.current?.parentElement
    if (!root) return
    let timer: number | null = null
    const reveal = (el: Element | null) => {
      if (!isTextField(el) || !root.contains(el) || typeof el.scrollIntoView !== "function") return
      if (timer !== null) window.clearTimeout(timer)
      // one frame later than the browser's own focus scroll, and after the keyboard's first resize
      timer = window.setTimeout(() => {
        timer = null
        el.scrollIntoView({ block: "nearest", inline: "nearest" })
        const scroller = scrollerOf(el, root)
        if (!scroller) return
        const delta = overlapWith(el.getBoundingClientRect(), stickyBar(root, "header")?.getBoundingClientRect() ?? null, stickyBar(root, "footer")?.getBoundingClientRect() ?? null)
        if (delta) scroller.scrollTop += delta
      }, 80)
    }
    const onFocus = (e: FocusEvent) => reveal(e.target as Element | null)
    const onResize = () => reveal(document.activeElement)
    root.addEventListener("focusin", onFocus)
    const vv = window.visualViewport
    vv?.addEventListener("resize", onResize)
    window.addEventListener("resize", onResize)
    return () => {
      root.removeEventListener("focusin", onFocus)
      vv?.removeEventListener("resize", onResize)
      window.removeEventListener("resize", onResize)
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [])
  return <span ref={ref} hidden data-slot="keyboard-clearance" />
}
