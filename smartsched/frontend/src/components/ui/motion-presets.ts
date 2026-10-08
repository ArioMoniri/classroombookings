// SmartSched Liquid Glass v2 — motion presets (docs/design/v2/liquid-glass.md §7).
// Original parameters. kinetics.colorion.co was used as a *reference* for feel only (it ships no
// licence, so none of its code or values are copied). Settle time of a damped spring ≈ 8·m / c
// (2 % band), so every preset below settles in ≤ 300 ms.
import { useReducedMotion, type Transition } from "motion/react"

/** Press / toggle feedback. Settles ≈ 8·0.6/42 = 114 ms. */
export const SPRING_PRESS = { type: "spring", stiffness: 620, damping: 42, mass: 0.6 } as const
/** Glass thumbs and highlights gliding between positions (segmented, sidebar). ≈ 8·0.8/30 = 213 ms, ~4 % overshoot. */
export const SPRING_MORPH = { type: "spring", stiffness: 420, damping: 30, mass: 0.8 } as const
/** Sheets, inspectors, floating toolbars arriving. ≈ 8·1/34 = 235 ms, no visible overshoot. */
export const SPRING_SHEET = { type: "spring", stiffness: 340, damping: 34, mass: 1 } as const
/** Dropped grid events settling into a cell. ≈ 8·0.8/40 = 160 ms. */
export const SPRING_DROP = { type: "spring", stiffness: 520, damping: 40, mass: 0.8 } as const
/** Number tickers / KPI counters. ≈ 8·1/28 = 286 ms. */
export const SPRING_COUNT = { type: "spring", stiffness: 180, damping: 28, mass: 1 } as const

export const DURATION = { fast: 0.12, base: 0.18, slow: 0.24, max: 0.3 } as const
export const EASE_GLASS = [0.32, 0.72, 0, 1] as const
export const EASE_OUT = [0.16, 1, 0.3, 1] as const

/** Returns `transition`, or an instant transition when the user prefers reduced motion. */
export function useMotionSafe(transition: Transition): Transition {
  const reduce = useReducedMotion()
  return reduce ? { duration: 0 } : transition
}
