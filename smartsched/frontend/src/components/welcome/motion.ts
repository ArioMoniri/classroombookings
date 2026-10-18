/**
 * Welcome guide motion (WG-09; docs/design/v3/welcome-guide.md §8, motion_designer §3). One place for every timing the
 * sheet, tour, checklist and hints use, so the ceiling is checked once (`motion.test.ts`).
 *
 * The rule for this surface is calm and short: every one-shot UI motion ends within `dur.slow` (240 ms), **delays
 * included**; exits are faster than entrances; only transform and opacity move. The Lottie hero is the one exception
 * (≤ 3 s, plays once, then rests on its poster). Under reduced motion (the OS setting or the in-app switch,
 * `useReduce()`), nothing travels or scales: state changes are instant, and appearing surfaces take a ≤ 100 ms fade.
 *
 * Tweens, not springs, on purpose: the shared springs settle in 270–285 ms, over this surface's 240 ms budget, and
 * none of these moments is grabbed or re-targeted by a finger (the phone sheet drag stays on ui/dialog's own spring).
 * Every one of them is still interruptible: motion starts a new tween from the current visual value.
 */
import type { Transition } from "motion/react";
import { dur, ease, staggerRule, tween } from "@/lib/motion";

/** The ceiling for one-shot welcome UI motion, in seconds (delay + duration). */
export const WELCOME_MAX_S = dur.slow;

/** First-reveal stagger: at most 5 items stagger (cards, spec §8.1), 30 ms apart. */
export const WELCOME_STAGGER_ITEMS = 5;

/** The sheet settles in `dur.slow`; the hero starts after that (ms, for timers). */
export const WELCOME_SHEET_SETTLE_MS = Math.round(dur.slow * 1000);

/** Instant end state (reduced motion, state changes). */
export const instant: Transition = { duration: 0 };

export const welcomeMotion = {
  /** Desktop sheet cards, first reveal: y 8 → 0 + opacity; the 5th card ends at 4 × 30 + 120 = 240 ms. */
  cardReveal: (i: number): Transition => ({
    duration: dur.fast,
    ease: ease.out,
    delay: Math.min(Math.max(i, 0), WELCOME_STAGGER_ITEMS - 1) * staggerRule.step,
  }),
  /** Phone pager: the next card enters from the side it came from (x ±24 + opacity)… */
  pageEnter: { duration: dur.base, ease: ease.out } satisfies Transition,
  /** …and the old one leaves faster. */
  pageExit: { duration: dur.fast, ease: ease.in } satisfies Transition,
  /** The pager dots' active pill (layoutId) and the tour's spotlight ring re-targeting (layout, FLIP transforms). */
  dot: { duration: dur.base, ease: ease.inOut } satisfies Transition,
  ring: { duration: dur.slow, ease: ease.inOut } satisfies Transition,
  /** Checklist progress bar scaleX; data never overshoots. */
  progress: { duration: dur.slow, ease: ease.out } satisfies Transition,
  /** Checklist tick: the circle fills, then the check path draws (120 + 120 = 240 ms). */
  tickFill: { duration: dur.fast, ease: ease.out } satisfies Transition,
  tickDraw: { duration: dur.fast, ease: ease.out, delay: dur.fast } satisfies Transition,
  /** "Hepsi tamam" disc and the "Yeni" badge: scale + opacity once, no bounce (calm). */
  pop: { duration: dur.base, ease: ease.out } satisfies Transition,
  /** Hint popover and tour step card: opacity + scale .98 → 1 toward the anchor. */
  popover: { duration: dur.fast, ease: ease.out } satisfies Transition,
  /** The hero's player fades in over the empty frame once its first frame is ready. */
  heroIn: { duration: dur.slow, ease: ease.out } satisfies Transition,
  /** Reduced-motion replacement for anything that appears: opacity only, 100 ms. */
  reduced: tween.reduced satisfies Transition,
} as const;
