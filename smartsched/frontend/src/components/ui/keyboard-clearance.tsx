"use client"
// SmartSched keyboard clearance (T-R1-02, R1-A-03; MOBILE.md M-05). Original work.
// A bottom sheet or phone dialog has a sticky footer, and on a phone the on-screen keyboard takes the lower half of
// the screen (the root viewport carries interactive-widget=resizes-content, so the layout viewport shrinks with it).
// Rendered as the last child of a Sheet / Dialog popup, this keeps the focused field readable:
//   - on focusin of a text field inside the popup, after the keyboard had its first frame, the field is scrolled
//     into the nearest scroller (`scrollIntoView({ block: "nearest" })`); the popup and its direct children carry
//     scroll-padding-bottom (ui/sheet, ui/dialog), so "nearest" lands above the sticky footer, not under it;
//   - when the visual viewport resizes while a field inside the popup has focus (the keyboard opening or closing),
//     the same scroll runs again.
// The element itself is an empty hidden <span>; it only needs its parent (the popup).
import * as React from "react"

const FIELD = 'input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([type="file"]), textarea, select, [contenteditable=""], [contenteditable="true"]'

export function isTextField(el: Element | null): el is HTMLElement {
  return !!el && el instanceof HTMLElement && el.matches(FIELD)
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
