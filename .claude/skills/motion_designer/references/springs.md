# Springs, durations, easings, stagger

The source of truth for numbers is `references/motion-tokens.ts`, which the app copies to `src/lib/motion.ts`. This file explains the numbers and gives the CSS mirror. Regenerate or extend with `python3 -I scripts/spring_table.py [stiffness damping mass]`.

## 1. Spring presets

Simulated from rest to target (semi-implicit Euler, dt = 0.25 ms). **t95** = first time at 95 % of the distance (the motion feels "arrived"). **settle** = the time after which it stays within 1 % (when the CSS mirror ends). ζ = damping ratio (1 = critical, < 1 = overshoot).

| Token (TS / CSS) | stiffness | damping | mass | ζ | t95 | settle | overshoot | Use for | Never for |
|---|---|---|---|---|---|---|---|---|---|
| `springs.snappy` / `--spring-snappy` | 520 | 42 | 0.8 | 1.03 | 195 ms | 278 ms | 0 % | press feedback, toggles, row highlight pill, drop-settle, resize steps, magnetic slot | large surfaces that need to read as "heavy" |
| `springs.smooth` / `--spring-smooth` | 380 | 36 | 1 | 0.92 | 215 ms | 281 ms | 0 % | layout reflow, list insert/remove, route content, toast stack, panel resize | tiny confirmations (feels dull) |
| `springs.bouncySubtle` / `--spring-bouncy-subtle` | 420 | 28 | 0.8 | 0.76 | 140 ms | 285 ms | 2.4 % | success check pop, chip added, badge count bump (≤ 32 px elements) | anything ≥ 64 px, anything carrying data, sheets |
| `springs.sheet` / `--spring-sheet` | 300 | 30 | 1 | 0.87 | 219 ms | 269 ms | 0.4 % | sheets, drawers, detent snap (pass `velocity` from the drag) | small controls (feels slow) |
| `springs.glassMorph` / `--spring-glass-morph` | 400 | 30 | 0.85 | 0.81 | 160 ms | 281 ms | 1.2 % | Liquid Glass shape changes: segmented pill, tab-bar pill and bar, island pill→card, palette and popover open | text-bearing elements that scale (text stretches) |
| `springs.ticker` / `--spring-ticker` | 420 | 38 | 1 | 0.93 | 206 ms | 271 ms | 0 % | number tickers, progress values | — |
| `pointerSpring` (useSpring options) | 700 | 34 | 0.5 | 0.91 | 109 ms | 141 ms | 0.1 % | smoothing pointer-driven values: specular light, magnetic pull | discrete transitions |

Why physics springs (stiffness/damping/mass) rather than `{ visualDuration, bounce }`: both forms work in motion v14, but the physics form makes the feel identical across distances and inherits velocity when interrupted (motion.dev: "Physics-based springs incorporate existing velocity"). That is what makes a sheet flick or a re-targeted pill feel continuous instead of restarting.

**Interruptibility rule**: never `await` an animation before accepting input. Start the new target on the same motion value, and the spring carries the current velocity. Never use keyframe arrays for anything the user can interrupt (keyframes restart from the first frame). The conflict shake is the exception because it is fire-and-forget.

## 2. Durations and easings (tweens and CSS fallbacks)

| Token | Value | Use |
|---|---|---|
| `dur.instant` / `--dur-instant` | 0 | colour/state swaps on grid cells while dragging |
| `dur.fast` / `--dur-fast` | 120 ms | hover, focus ring, tooltip, exits, scrim |
| `dur.base` / `--dur-base` | 180 ms | opacity entrances, label crossfades, blur clearing |
| `dur.slow` / `--dur-slow` | 240 ms | stagger window ceiling, check draw total |
| `dur.max` / `--dur-max` | 300 ms | **ceiling** for any one-shot animation |
| `ease.out` / `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | entrances |
| `ease.inOut` / `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | on-screen moves that aren't springs |
| `ease.emphasized` / `--ease-emphasized` | `cubic-bezier(0.2, 0, 0, 1)` | legacy sheets (prefer `--spring-sheet`) |
| `ease.in` / `--ease-in` (new) | `cubic-bezier(0.4, 0, 1, 1)` | exits: leave faster, at ~65 % of the entrance time |
| `tween.reduced` | 100 ms linear opacity | the reduced-motion replacement everywhere |

Looping indicators (thinking shimmer 1.6 s, "Checking…" pulse 1.2 s, spinners) are exempt from the ceiling because they represent ongoing work. They must stop when the work stops and be static under reduced motion.

## 3. CSS mirror (paste into globals.css `:root`; owned by the glass/frontend agent)

`linear()` is supported in Chromium 113+, Safari 17.2+ and Firefox 112+. The `@supports` guard keeps older engines on `--ease-out`.

```css
:root {
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  /* spring fallbacks for browsers without linear() */
  --spring-snappy: var(--ease-out);       --spring-snappy-ms: 280ms;
  --spring-smooth: var(--ease-out);       --spring-smooth-ms: 280ms;
  --spring-bouncy-subtle: var(--ease-out);--spring-bouncy-subtle-ms: 290ms;
  --spring-sheet: var(--ease-out);        --spring-sheet-ms: 270ms;
  --spring-glass-morph: var(--ease-out);  --spring-glass-morph-ms: 280ms;
  --spring-ticker: var(--ease-out);       --spring-ticker-ms: 270ms;
}
@supports (transition-timing-function: linear(0, 1)) {
  :root {
    --spring-snappy: linear(0, 0.094, 0.267, 0.444, 0.592, 0.707, 0.794, 0.856, 0.9, 0.932, 0.953, 0.968, 0.978, 0.985, 1);
    --spring-smooth: linear(0, 0.062, 0.193, 0.345, 0.488, 0.614, 0.715, 0.795, 0.857, 0.901, 0.934, 0.957, 0.973, 0.983, 1);
    --spring-bouncy-subtle: linear(0, 0.088, 0.272, 0.472, 0.652, 0.793, 0.894, 0.959, 0.998, 1.017, 1.023, 1.023, 1.019, 1.015, 1);
    --spring-sheet: linear(0, 0.047, 0.153, 0.283, 0.416, 0.54, 0.648, 0.738, 0.81, 0.867, 0.909, 0.941, 0.964, 0.979, 1);
    --spring-glass-morph: linear(0, 0.077, 0.238, 0.421, 0.587, 0.725, 0.829, 0.903, 0.953, 0.983, 1.001, 1.009, 1.012, 1.012, 1);
    --spring-ticker: linear(0, 0.063, 0.196, 0.35, 0.493, 0.618, 0.72, 0.799, 0.859, 0.904, 0.935, 0.958, 0.973, 0.983, 1);
  }
}
@media (prefers-reduced-motion: reduce) {
  :root { --spring-snappy-ms: 0ms; --spring-smooth-ms: 0ms; --spring-bouncy-subtle-ms: 0ms;
          --spring-sheet-ms: 0ms; --spring-glass-morph-ms: 0ms; --spring-ticker-ms: 0ms; }
}
```

A CSS `linear()` spring cannot inherit velocity. Use it only for transitions the user doesn't grab mid-flight: popover open, palette open, dnd-kit drop. Anything draggable uses the JS spring.

## 4. Stagger

- Default step **30 ms** (`stagger(0.03)` or `staggerDelay(i)`), ceiling 40 ms. Only the **first 6** items get distinct delays, and the rest share the 6th slot. Total ≤ 180 ms.
- Stagger on **first reveal only** (page load, panel open). Never on filter, sort, search results, pagination or live updates: those use layout reflow or nothing (Linear's shortcut search filters instantly, which is the reference behaviour).
- Exits do not stagger. A group leaves together in `dur.fast`.
- Grids (heatmap, timetable cells) never stagger per cell. Reveal the grid as one layer.
- Under reduced motion every delay is 0.

```ts
import { stagger, type Variants } from "motion/react";
import { springs, staggerRule } from "@/lib/motion";

export const listVariants: Variants = {
  hidden: {},
  shown: { transition: { delayChildren: stagger(staggerRule.step) } },
};
export const itemVariants: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: springs.smooth },
};
```

## 5. Mapping from tokens.md §6 (v1) to v2

| v1 token | v2 | Change |
|---|---|---|
| `--spring-drop` {520, 42, 0.8} | `snappy` | same numbers, renamed |
| `--spring-sheet` {300, 30} | `sheet` | same numbers (mass 1 explicit) |
| `--spring-count` {170, 26} | `ticker` {420, 38, 1} | v1 settled in 507 ms, over the ceiling |
| sidebar `nav-indicator` {500, 40} (sidebar.tsx) | `glassMorph` | v2 pill morph has the 1.2 % gel |
| `--dur-*`, `--ease-*` | unchanged | `--ease-in` added for exits |

## 6. Spring parameter ideas from Kinetics (ideas only, no code)

kinetics.colorion.co shows 153 spring interactions. Its GitHub repo (ckissi/kinetics) has **no LICENSE file** and `package.json` is `private` with no `license` field. The site footer says "MIT licensed", but with no licence text in the repo we treat it as **unlicensed: record ideas, copy no code**. What we took as ideas:

| Kinetics label | Their params | ζ (m = 1) | Our reading |
|---|---|---|---|
| Card Resize | spring(320, 24) | 0.67, 5.7 % overshoot, settles 363 ms | too bouncy and slow for a planner tool, so we use `smooth` |
| Number Counter | spring(280, 18) | 0.54 | overshoot shows wrong numbers, so `ticker` is critically damped instead |
| Step Progress | spring(300, 24) | 0.69 | idea: progress fills deserve a spring, but ours is overshoot-free |
| PIN Input | spring(360, 22) | 0.58 | idea: per-cell pop on entry, which we use as `bouncySubtle` on ≤ 32 px chips only |
| Toast Overshoot | overshoot(1.08) | — | 8 % is too much; our toast stack uses `smooth` with no overshoot |
| Tab Pill Glide | glide(0.4 s) | — | 400 ms is over the ceiling; `glassMorph` arrives at 160 ms |
| Liquid Glass Press, Command Palette Bloom, Lattice Snap, Drag Stack Collect | — | — | confirmed the vocabulary: press = scale 0.97 on `snappy`, palette = scale-from-top, snap = magnetic pull with falloff |

Takeaway: Kinetics tunes for delight (ζ 0.5–0.7). SmartSched tunes for trust (ζ 0.8–1.03), with overshoot reserved for small confirmations and the 1.2 % glass "gel".
