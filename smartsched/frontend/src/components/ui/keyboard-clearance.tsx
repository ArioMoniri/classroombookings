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
// T-R2-01 (R2-A-02, R2-S-06): `scope="document"` is the page-level twin, mounted once in the app shell: a focused field
// outside any popup is scrolled (window) clear of every sticky or fixed bar on the page — the /profile save bar, the
// /find-room search capsule, the tab bar — by the largest overlap; fields inside a popup are left to the popup's own.
import * as React from "react"

const FIELD = 'input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([type="file"]), textarea, select, [contenteditable=""], [contenteditable="true"]'
const BARS = { header: "[data-slot=sheet-header], [data-slot=dialog-header]", footer: "[data-slot=sheet-footer], [data-slot=dialog-footer]" } as const
const POPUP = "[data-slot=sheet-content], [data-slot=dialog-content], [role=dialog], [role=alertdialog]"
/** Cheap candidates for page-level bars: Tailwind keeps the words in the class list; the shell bars are header / nav. */
const BAR_CANDIDATES = '[class*="sticky"], [class*="fixed"], header, footer, nav, [data-slot$="-footer"], [data-slot$="-header"]'

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

/**
 * Page-level bars that can cover `field`: sticky or fixed, drawn, not an ancestor of the field (a sticky container
 * holding the field does not cover it), in DOM order. Exported for the unit test.
 */
export function stickyBarsOf(root: ParentNode, field: Element): HTMLElement[] {
  const out: HTMLElement[] = []
  for (const el of root.querySelectorAll<HTMLElement>(BAR_CANDIDATES)) {
    if (el.contains(field)) continue
    const cs = getComputedStyle(el)
    if (cs.position !== "sticky" && cs.position !== "fixed") continue
    if (cs.visibility === "hidden" || cs.display === "none") continue
    const r = el.getBoundingClientRect()
    if (r.height <= 0 || r.width <= 0) continue
    out.push(el)
  }
  return out
}

/**
 * The window scroll that clears every bar: the largest overlap. A bar in the lower half of the viewport (`vh`) is a
 * bottom bar (save bar, search capsule, tab bar: the field scrolls up past it), one in the upper half a top bar.
 */
export function documentOverlap(field: Box, bars: Box[], vh: number, gap = 8): number {
  let down = 0
  let up = 0
  for (const bar of bars) {
    const below = (bar.top + bar.bottom) / 2 >= vh / 2
    const d = below ? overlapWith(field, null, bar, gap) : overlapWith(field, bar, null, gap)
    if (d > down) down = d
    if (d < up) up = d
  }
  return down || up
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

export function KeyboardClearance({ scope = "popup" }: { scope?: "popup" | "document" }) {
  const ref = React.useRef<HTMLSpanElement>(null)
  React.useEffect(() => {
    const page = scope === "document"
    const root = page ? document.body : ref.current?.parentElement
    if (!root) return
    let timer: number | null = null
    const reveal = (el: Element | null) => {
      if (!isTextField(el) || !root.contains(el) || typeof el.scrollIntoView !== "function") return
      if (page && el.closest(POPUP)) return // the popup's own clearance handles it
      if (timer !== null) window.clearTimeout(timer)
      // one frame later than the browser's own focus scroll, and after the keyboard's first resize
      timer = window.setTimeout(() => {
        timer = null
        el.scrollIntoView({ block: "nearest", inline: "nearest" })
        if (page) {
          const delta = documentOverlap(el.getBoundingClientRect(), stickyBarsOf(root, el).map((b) => b.getBoundingClientRect()), window.visualViewport?.height ?? document.documentElement.clientHeight)
          if (delta) window.scrollBy({ top: delta, behavior: "instant" })
          return
        }
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
  }, [scope])
  return <span ref={ref} hidden data-slot="keyboard-clearance" data-scope={scope} />
}
