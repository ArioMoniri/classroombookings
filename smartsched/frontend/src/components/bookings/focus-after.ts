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
 */
export function focusAfter(selectors: (string | null | undefined)[], delay = 320, settle = 2000): void {
  if (typeof window === "undefined") return;
  const preferred = selectors.filter((s): s is string => !!s);
  const all = [...preferred, "[data-focus-fallback]", "#main"];
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
    if (done) return;
    focusFirst(all);
    window.addEventListener("pointerdown", stop, true);
    window.addEventListener("keydown", stop, true);
    const until = Date.now() + settle;
    const onPreferred = () => preferred.some((sel) => document.activeElement?.matches(sel));
    const tick = () => {
      if (done) return;
      const a = document.activeElement as HTMLElement | null;
      if (!a || a === document.body || !a.isConnected) focusFirst(all);
      else if (!onPreferred() && preferred.some((sel) => usable(document.querySelector<HTMLElement>(sel)))) focusFirst(preferred);
      if (Date.now() < until) window.setTimeout(tick, 50);
      else stop();
    };
    window.setTimeout(tick, 50);
  }, delay);
}

export const cellSelector = (s: { date: string; period_id: number; room_id: number }) => `button[data-slot-key="${s.date}|${s.period_id}|${s.room_id}"]`;
