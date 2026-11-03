/** the page landmarks focus falls back to when no preferred target is there (yet) */
const FALLBACKS = ["[data-focus-fallback]", "#main"];

/**
 * After a successful book / save / cancel / withdraw the sheet or dialog closes and the control that was
 * pressed is gone or disabled, so the browser drops focus to <body> (persona U-07, motion audit T4). Once the
 * exit animation is over, focus the first selector that matches: the booked cell, the booking's row, then a
 * page landmark marked `data-focus-fallback`, then <main>.
 *
 * T-R1-12: a fixed delay raced the data refresh. After the first request the grid re-renders, the cell is
 * replaced and focus fell to <body> again. So the target is watched for `settle` ms after the first attempt:
 * when focus is lost (on <body>, or on a node that left the document) or still sits on a fallback while a
 * preferred target has appeared, it is focused again. Any pointer or key press by the user ends the watch.
 *
 * Focus on any other element is never taken back: a field focused without a key or pointer press (assistive
 * technology, a script, Playwright's `fill`) kept losing the focus to the target every 50 ms for 2 s, and the text
 * meant for it went nowhere (pod CI run #161: loop-r1-laneE emptied the organisation name right after a save,
 * the field kept its value, the save capsule never came back).
 */
export function focusAfter(selectors: (string | null | undefined)[], delay = 320, settle = 2000): void {
  if (typeof window === "undefined") return;
  const preferred = selectors.filter((s): s is string => !!s);
  const all = [...preferred, ...FALLBACKS];
  const usable = (el: HTMLElement | null): el is HTMLElement => !!el && el.isConnected && !(el as HTMLButtonElement).disabled;
  const focusFirst = (list: string[]): boolean => {
    for (const sel of list) {
      const el = document.querySelector<HTMLElement>(sel);
      if (usable(el)) {
        el.focus({ preventScroll: false });
        if (document.activeElement === el) return true;
      }
    }
    return false;
  };
  let done = false;
  const stop = () => {
    done = true;
    window.removeEventListener("pointerdown", stop, true);
    window.removeEventListener("keydown", stop, true);
  };
  window.setTimeout(() => {
    if (done || typeof document === "undefined") return;
    focusFirst(all);
    window.addEventListener("pointerdown", stop, true);
    window.addEventListener("keydown", stop, true);
    const until = Date.now() + settle;
    const onPreferred = () => preferred.some((sel) => document.activeElement?.matches(sel));
    const onFallback = (a: HTMLElement) => FALLBACKS.some((sel) => a.matches(sel));
    const tick = () => {
      // the page (or a test's jsdom) can be gone by the time a pending tick fires
      if (done || typeof document === "undefined") return;
      const a = document.activeElement as HTMLElement | null;
      if (!a || a === document.body || !a.isConnected) focusFirst(all);
      else if (onFallback(a) && !onPreferred() && preferred.some((sel) => usable(document.querySelector<HTMLElement>(sel)))) focusFirst(preferred);
      if (Date.now() < until) window.setTimeout(tick, 50);
      else stop();
    };
    window.setTimeout(tick, 50);
  }, delay);
}

export const cellSelector = (s: { date: string; period_id: number; room_id: number }) => `button[data-slot-key="${s.date}|${s.period_id}|${s.room_id}"]`;
