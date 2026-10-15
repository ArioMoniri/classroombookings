"use client";

import { useDeferredValue } from "react";
import { cn } from "@/lib/utils";

/**
 * Week / day navigation renders the grid from deferred values (motion audit T3: the 1,000-cell lens re-render
 * is interruptible and never blocks the click frame), while the toolbar shows the target date at once.
 * `stale` is true while the grid still shows the previous week / day (T2).
 */
export function useDeferredView(week: number, day: number): { week: number; day: number; stale: boolean } {
  const w = useDeferredValue(week);
  const d = useDeferredValue(day);
  return { week: w, day: d, stale: w !== week || d !== day };
}

/**
 * The stale signal (motion audit T2): after 120 ms of pending, a canvas-coloured veil dims the old grid to
 * ~60 %. A veil on top, not a faded wrapper, so the glass headers inside keep their blur (backdrop-root
 * rule, motion_designer §4). Opacity only, no travel; under reduced motion the global rule makes it a cut;
 * under reduced transparency `cal-canvas` is already opaque. Decorative: aria-hidden, no pointer events.
 */
export function StaleVeil({ stale, className }: { stale: boolean; className?: string }) {
  return (
    <div
      aria-hidden
      data-testid="stale-veil"
      data-stale={stale ? "" : undefined}
      className={cn(
        "cal-canvas pointer-events-none absolute inset-0 z-30 opacity-0 transition-opacity duration-(--dur-fast) data-stale:opacity-40 data-stale:delay-[120ms]",
        className,
      )}
    />
  );
}
