"use client"
// SmartSched focus trap for modal popups (T-R2-02, R2-A-03 / R2-S-16). Original work.
// base-ui's FloatingFocusManager traps with focus-guard spans; in the app shell a Tab from the last control of a confirm
// dialog landed on a guard and the next one left for the skip link and the logo. The popups now trap Tab themselves:
// on keydown Tab inside the popup, Tab from the last tabbable goes to the first and Shift+Tab from the first to the last;
// with nothing tabbable the key is swallowed. Everything else (Esc, initial focus, focus return) stays base-ui's.
import * as React from "react"

const TABBABLE =
  'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [contenteditable="true"], [contenteditable=""], [tabindex]:not([tabindex="-1"]), summary, iframe, audio[controls], video[controls]'

/** Drawn: no ancestor up to the popup is display:none or visibility:hidden (computed styles: works in jsdom too). */
function drawn(el: HTMLElement, root: HTMLElement): boolean {
  const view = el.ownerDocument.defaultView
  if (!view) return true
  for (let node: HTMLElement | null = el; node && node !== root.parentElement; node = node.parentElement) {
    if (node.hidden) return false
    const cs = view.getComputedStyle(node)
    if (cs.display === "none" || cs.visibility === "hidden") return false
  }
  return true
}

/** The popup's tabbable descendants in DOM order, drawn ones only, base-ui's focus guards excluded. */
export function tabbablesOf(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(TABBABLE)].filter((el) => {
    if (el.hasAttribute("data-base-ui-focus-guard") || el.getAttribute("aria-hidden") === "true" || el.closest("[inert]")) return false
    if (el.tabIndex < 0) return false
    return drawn(el, root)
  })
}

/** Keydown handler of the trap; exported so a popup can compose it with its own `onKeyDown`. */
export function trapTabKey(event: KeyboardEvent | React.KeyboardEvent, root: HTMLElement | null): void {
  if (event.key !== "Tab" || !root || event.defaultPrevented) return
  const items = tabbablesOf(root)
  if (items.length === 0) {
    event.preventDefault()
    return
  }
  const first = items[0]!
  const last = items[items.length - 1]!
  const active = root.ownerDocument.activeElement
  const inside = active instanceof HTMLElement && root.contains(active)
  if (event.shiftKey) {
    if (!inside || active === first) {
      event.preventDefault()
      last.focus()
    }
  } else if (!inside || active === last) {
    event.preventDefault()
    first.focus()
  }
}

/** Returns the keydown handler for a popup element held in `ref`. */
export function useFocusTrap<T extends HTMLElement>(ref: React.RefObject<T | null>): (event: React.KeyboardEvent<T>) => void {
  return React.useCallback((event: React.KeyboardEvent<T>) => trapTabKey(event, ref.current), [ref])
}
