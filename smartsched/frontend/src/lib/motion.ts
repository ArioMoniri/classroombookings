/**
 * SmartSched motion tokens (Liquid Glass v2). Canonical copy lives here, in the
 * motion_designer skill. The frontend copies it verbatim to `src/lib/motion.ts`
 * and imports it as `@/lib/motion`. CSS mirrors live in globals.css (see
 * references/springs.md §3). Every value was simulated with
 * `scripts/spring_table.py`: all presets reach 95 % of the target in ≤ 220 ms
 * and settle within 1 % in ≤ 290 ms, so the 300 ms ceiling in tokens.md §6 holds.
 *
 * Spring parameter *ideas* were informed by Kinetics (kinetics.colorion.co,
 * no licence file, ideas only, no code) and beUI `lib/ease.ts` (MIT,
 * © 2026 Saurabh Chauhan). The numbers below are our own.
 */
"use client";

import { useSyncExternalStore } from "react";
import { useReducedMotion, type Transition } from "motion/react";

/* ------------------------------------------------------------------ springs */

/** Physics springs. Keys are camelCase in TS and kebab-case in CSS (`--spring-bouncy-subtle`). */
export const springs = {
  /** ζ 1.03, t95 196 ms, settle 279 ms, 0 % overshoot. Press, toggles, indicators that must feel instant, drop-settle. Same values as tokens.md `--spring-drop`. */
  snappy: { type: "spring", stiffness: 520, damping: 42, mass: 0.8 },
  /** ζ 0.92, t95 216 ms, settle 284 ms, 0 % overshoot. Layout moves, list reflow, route content, panels that resize. */
  smooth: { type: "spring", stiffness: 380, damping: 36, mass: 1 },
  /** ζ 0.76, t95 140 ms, settle 285 ms, 2.3 % overshoot. Small confirmations only: check badge, chip added, count bump. Never on big surfaces. */
  bouncySubtle: { type: "spring", stiffness: 420, damping: 28, mass: 0.8 },
  /** ζ 0.87, t95 219 ms, settle 270 ms, 0.4 % overshoot. Sheets, drawers, detent snaps (carries drag velocity). Same as tokens.md `--spring-sheet`. */
  sheet: { type: "spring", stiffness: 300, damping: 30, mass: 1 },
  /** ζ 0.81, t95 160 ms, settle 279 ms, 1.2 % overshoot. Liquid Glass morphs: segmented pill, tab-bar pill, island pill→card, palette open. The 1 % overshoot is the "gel". */
  glassMorph: { type: "spring", stiffness: 400, damping: 30, mass: 0.85 },
  /** ζ 0.93, t95 206 ms, settle 273 ms, 0 % overshoot (numbers must never show a wrong value). Replaces tokens.md `--spring-count` (settled in 507 ms). */
  ticker: { type: "spring", stiffness: 420, damping: 38, mass: 1 },
} as const satisfies Record<string, Transition>;

/** Options for `useSpring` when smoothing a pointer-driven value (specular light, magnetic pull). t95 110 ms. */
export const pointerSpring = { stiffness: 700, damping: 34, mass: 0.5 } as const;

export type SpringName = keyof typeof springs;

/**
 * CSS mirrors of the springs: `linear()` easings sampled from the same physics
 * (15 stops) plus the duration at which the spring is within 1 % of rest.
 * Use them for CSS transitions (Base UI `data-starting-style`), dnd-kit
 * `dropAnimation`, and WAAPI. Browsers without `linear()` (pre-2023) fall
 * back to `--ease-out` via `@supports` in globals.css.
 */
export const cssSpring = {
  snappy: {
    easing: "linear(0, 0.094, 0.267, 0.444, 0.592, 0.707, 0.794, 0.856, 0.9, 0.932, 0.953, 0.968, 0.978, 0.985, 1)",
    ms: 280,
  },
  smooth: {
    easing: "linear(0, 0.062, 0.193, 0.345, 0.488, 0.614, 0.715, 0.795, 0.857, 0.901, 0.934, 0.957, 0.973, 0.983, 1)",
    ms: 280,
  },
  bouncySubtle: {
    easing: "linear(0, 0.088, 0.272, 0.472, 0.652, 0.793, 0.894, 0.959, 0.998, 1.017, 1.023, 1.023, 1.019, 1.015, 1)",
    ms: 290,
  },
  sheet: {
    easing: "linear(0, 0.047, 0.153, 0.283, 0.416, 0.54, 0.648, 0.738, 0.81, 0.867, 0.909, 0.941, 0.964, 0.979, 1)",
    ms: 270,
  },
  glassMorph: {
    easing: "linear(0, 0.077, 0.238, 0.421, 0.587, 0.725, 0.829, 0.903, 0.953, 0.983, 1.001, 1.009, 1.012, 1.012, 1)",
    ms: 280,
  },
  ticker: {
    easing: "linear(0, 0.063, 0.196, 0.35, 0.493, 0.618, 0.72, 0.799, 0.859, 0.904, 0.935, 0.958, 0.973, 0.983, 1)",
    ms: 270,
  },
} as const satisfies Record<SpringName, { easing: string; ms: number }>;

/* ------------------------------------------------- durations and easings */

/** Seconds (motion uses seconds). CSS mirrors are `--dur-*` in ms. */
export const dur = { instant: 0, fast: 0.12, base: 0.18, slow: 0.24, max: 0.3 } as const;

/** Cubic-bezier tuples, identical to tokens.md §6 `--ease-*`. */
export const ease = {
  out: [0.16, 1, 0.3, 1],
  inOut: [0.65, 0, 0.35, 1],
  emphasized: [0.2, 0, 0, 1],
  /** Exits: accelerate away. Exits run at ~65 % of the entrance duration. */
  in: [0.4, 0, 1, 1],
} as const;

/** Tween presets for things that are not physical (colour, opacity-only, exits). */
export const tween = {
  fadeIn: { duration: dur.base, ease: ease.out },
  fadeOut: { duration: dur.fast, ease: ease.in },
  exit: { duration: dur.fast, ease: ease.in },
  /** Reduced-motion replacement: opacity only, ≤ 100 ms. */
  reduced: { duration: 0.1, ease: "linear" },
} as const satisfies Record<string, Transition>;

/* ----------------------------------------------------------------- stagger */

/** Stagger rules: 30 ms step, 40 ms ceiling, only the first 6 items stagger, total ≤ 180 ms. */
export const staggerRule = { step: 0.03, maxStep: 0.04, cap: 6 } as const;

/** Delay for item `i` in a first-reveal stagger. Items past the cap share the last slot. */
export function staggerDelay(i: number, step: number = staggerRule.step): number {
  const s = Math.min(step, staggerRule.maxStep);
  return Math.min(i, staggerRule.cap - 1) * s;
}

/* ------------------------------------------------------ preference hooks */

/** `true` when the user asked for reduced motion. `null` (SSR, unknown) is treated as `false`. */
export function useReduce(): boolean {
  return useReducedMotion() ?? false;
}

/** Pick the full transition or its reduced-motion replacement. */
export function pick(reduce: boolean, full: Transition, reduced: Transition = { duration: 0 }): Transition {
  return reduce ? reduced : full;
}

function subscribeMedia(query: string) {
  return (onChange: () => void) => {
    if (typeof window === "undefined" || !window.matchMedia) return () => {};
    const mql = window.matchMedia(query);
    mql.addEventListener("change", onChange);
    const root = document.documentElement;
    const mo = new MutationObserver(onChange);
    mo.observe(root, { attributes: true, attributeFilter: ["data-transparency"] });
    return () => {
      mql.removeEventListener("change", onChange);
      mo.disconnect();
    };
  };
}

const RT_QUERY = "(prefers-reduced-transparency: reduce)";
const subscribeRT = subscribeMedia(RT_QUERY);

/**
 * Reduced transparency. The OS query only works in Chromium 118+, so the app
 * also honours `<html data-transparency="reduced">` set by the in-app
 * Appearance setting (owned by the liquid-glass spec).
 */
export function useReducedTransparency(): boolean {
  return useSyncExternalStore(
    subscribeRT,
    () =>
      document.documentElement.dataset.transparency === "reduced" ||
      window.matchMedia(RT_QUERY).matches,
    () => false,
  );
}

const FINE_QUERY = "(hover: hover) and (pointer: fine)";
const subscribeFine = subscribeMedia(FINE_QUERY);

/** Hover-only effects (specular light, parallax) run only with a fine, hovering pointer. */
export function useFinePointer(): boolean {
  return useSyncExternalStore(subscribeFine, () => window.matchMedia(FINE_QUERY).matches, () => false);
}
