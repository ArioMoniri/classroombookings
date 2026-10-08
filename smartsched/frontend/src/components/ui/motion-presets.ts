// SmartSched Liquid Glass v2 — motion preset aliases. The source of truth is `@/lib/motion` (verbatim copy of
// .claude/skills/motion_designer/references/motion-tokens.ts) and docs/design/v2/motion.md. These names
// exist so earlier imports keep working; every preset settles in ≤ 300 ms (motion.md §1).
import { type Transition } from "motion/react"

import { dur, ease, springs, useReduce } from "@/lib/motion"

/** Press / toggle feedback → springs.snappy (ζ 1.03, settles 279 ms, no overshoot). */
export const SPRING_PRESS = springs.snappy
/** Glass thumbs and highlights gliding between positions → springs.glassMorph (1.2 % gel). */
export const SPRING_MORPH = springs.glassMorph
/** Sheets, inspectors, floating toolbars arriving → springs.sheet. */
export const SPRING_SHEET = springs.sheet
/** Dropped grid events settling into a cell → springs.snappy. */
export const SPRING_DROP = springs.snappy
/** Number tickers / KPI counters → springs.ticker (the v1 {170, 26} spring settled in ~541 ms). */
export const SPRING_COUNT = springs.ticker

export const DURATION = dur
export const EASE_GLASS = [0.32, 0.72, 0, 1] as const
export const EASE_OUT = ease.out

/** Returns `transition`, or an instant transition when the user prefers reduced motion (OS or in-app). */
export function useMotionSafe(transition: Transition): Transition {
  const reduce = useReduce()
  const app = typeof document !== "undefined" && document.documentElement.dataset.motion === "reduced"
  return reduce || app ? { duration: 0 } : transition
}
