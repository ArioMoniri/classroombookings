/**
 * After a successful book / save / cancel / withdraw the sheet or dialog closes and the control that was
 * pressed is gone or disabled, so the browser drops focus to <body> (persona U-07, motion audit T4). Once the
 * exit animation is over, focus the first selector that matches: the booked cell, the booking's row, then a
 * page landmark marked `data-focus-fallback`, then <main>.
 */
export function focusAfter(selectors: (string | null | undefined)[], delay = 320): void {
  if (typeof window === "undefined") return;
  window.setTimeout(() => {
    for (const sel of [...selectors, "[data-focus-fallback]", "#main"]) {
      if (!sel) continue;
      const el = document.querySelector<HTMLElement>(sel);
      if (el && el.isConnected && !(el as HTMLButtonElement).disabled) {
        el.focus({ preventScroll: false });
        if (document.activeElement === el) return;
      }
    }
  }, delay);
}

export const cellSelector = (s: { date: string; period_id: number; room_id: number }) => `button[data-slot-key="${s.date}|${s.period_id}|${s.room_id}"]`;
