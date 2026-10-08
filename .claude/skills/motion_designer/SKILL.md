---
name: motion_designer
description: >-
  Motion and interaction playbook for SmartSched's Apple-native Liquid Glass web UI
  (iOS 26 / macOS Tahoe feel) built with motion v14 (motion/react), React 19 and Next.js.
  Use it for any animation, transition, micro-interaction, spring, easing or duration choice,
  gesture (drag, drop, swipe, resize, reorder, pinch), layout or shared-element (layoutId)
  animation, AnimatePresence enter/exit, scroll-linked effect, skeleton/shimmer/loading state,
  toast, sheet or detent, command palette, chat streaming, hover/specular effect,
  prefers-reduced-motion or reduced-transparency behaviour, and for motion reviews or
  performance audits (dropped frames, Playwright traces, Chrome performance API).
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, WebSearch, mcp__Mobbin__search_screens, mcp__Mobbin__search_flows
---

# motion_designer

You design and review motion for SmartSched. Motion here has one job: help a planner (Fatih Bey) see **what changed, where it went, and whether it worked**, while 1,300 classes sit on screen. The visual target is Apple's Liquid Glass: fluid, morphing, spring-based and physically plausible. It must never look like an AI template (no gratuitous fades, bounces or count-ups).

Read, in this order:
1. `docs/design/v2/motion.md`, the SmartSched spec per surface. If your work changes it, update it.
2. `docs/design/v2/liquid-glass.md` and `docs/design/tokens.md` §6. Material and colour belong to the glass spec. Movement belongs to this skill.
3. `references/patterns.md` for the pattern you need. Copy from there; every snippet type-checks.

## 1. Workflow

1. **Name the moment and its purpose** in one sentence: "When X happens, motion tells the user Y." If you can't write Y, don't animate. Prefer a state change with no motion.
2. **Pick a pattern** from §5. Reuse beats invention: a new pattern needs a reason in `motion.md`.
3. **Pick a token** from §3. Never type raw numbers into components. Import `@/lib/motion` (a copy of `references/motion-tokens.ts`).
4. **Write all three variants**: full motion, reduced motion (`useReduce()`), and reduced transparency (`useReducedTransparency()`).
5. **Check the a11y note** of the pattern: focus, live region, keyboard path, and a non-motion signal.
6. **Audit** with §8, and add the row to the surface's motion table in `motion.md` (Moment | Animation | Token | Reduced motion | Reduced transparency).
7. If you edited this skill, run `python3 -I .claude/skills/motion_designer/scripts/check_snippets.py smartsched/frontend` and expect `RESULT: PASS`.

## 2. Principles

1. **Purpose first.** Every animation answers *what changed*, *where it went* or *did it work*. Apple: "Don't add motion for the sake of adding motion." Frequent actions (cell focus, typing, filtering, sorting) get **no** motion.
2. **Continuity.** The thing you touched is the thing that moves. Glass morphs between states (`layoutId`) instead of one control disappearing and another appearing ("a singular floating plane"). A panel grows from its trigger.
3. **Spatial consistency.** Direction means something: sheets come from the bottom and leave to the bottom, forward is right/down, an expand returns to the same origin it came from. If a view slides in from the top, it must not be dismissed sideways (HIG).
4. **Interruptible springs.** Everything the user can grab or re-target is a physics spring on a motion value, so a new target inherits the current velocity. Never block input while animating ("let people cancel motion"). Never use keyframes for interruptible moves.
5. **No motion without meaning, and never motion alone.** State is also carried by text, icon, outline or a live-region message. Motion is the reinforcement.
6. **Brevity.** One-shot animations finish in **≤ 300 ms** (the tokens.md ceiling). Exits take about 65 % of entrances. Only looping indicators of ongoing work (thinking shimmer, "Checking…") may run longer, and they stop with the work.
7. **Restraint in bounce.** Overshoot is for small confirmations (≤ 32 px) and the 1.2 % glass "gel". Data never overshoots: numbers, bars and grid positions use critically damped springs.
8. **Respect the person.** `prefers-reduced-motion` removes travel, scale, parallax, blur and elastic motion. Fades ≤ 100 ms remain. `prefers-reduced-transparency` (or `data-transparency="reduced"`) makes glass opaque, while the motion logic stays the same.

## 3. Tokens (summary; full table and CSS in `references/springs.md`)

| Spring | stiffness / damping / mass | ζ | arrives (t95) / settles (1 %) | overshoot | Use |
|---|---|---|---|---|---|
| `snappy` | 520 / 42 / 0.8 | 1.03 | 195 / 278 ms | 0 | press, toggles, row pill, drop-settle, resize steps |
| `smooth` | 380 / 36 / 1 | 0.92 | 215 / 281 ms | 0 | layout reflow, lists, route content, toast stack |
| `bouncy-subtle` | 420 / 28 / 0.8 | 0.76 | 140 / 285 ms | 2.4 % | check pop, chip added, badge bump (≤ 32 px) |
| `sheet` | 300 / 30 / 1 | 0.87 | 219 / 269 ms | 0.4 % | sheets, drawers, detents (pass drag velocity) |
| `glass-morph` | 400 / 30 / 0.85 | 0.81 | 160 / 281 ms | 1.2 % | segmented/tab pill, island, palette/popover open |
| `ticker` | 420 / 38 / 1 | 0.93 | 206 / 271 ms | 0 | number tickers, progress values |
| `pointerSpring` (useSpring) | 700 / 34 / 0.5 | 0.91 | 109 / 141 ms | 0 | specular light, magnetic pull |

- **Durations** (CSS `--dur-*`, motion seconds): instant 0, fast 120, base 180, slow 240, max 300 ms.
- **Easings**: `--ease-out` (0.16, 1, 0.3, 1) for entrances, `--ease-in` (0.4, 0, 1, 1) for exits, `--ease-in-out` for on-screen tweens.
- **CSS springs**: `--spring-<name>` is a `linear()` easing sampled from the same physics, with `--spring-<name>-ms` as its duration. Use it for Base UI `data-starting-style` transitions and dnd-kit `dropAnimation`.
- **Reduced replacement**: `tween.reduced` = 100 ms linear opacity.
- **Stagger**: 30 ms step (max 40), first 6 items only, total ≤ 180 ms. First reveal only, never on filter/sort/live updates, and never on exits.
- New spring? Run `scripts/spring_table.py <k> <c> <m>`. It must reach t95 ≤ 220 ms and settle ≤ 300 ms, or it doesn't ship.

## 4. Performance budget

- **Animate only `transform` and `opacity`**, plus `filter` on small, non-glass elements (≤ 400 × 300 px). Never animate `width`, `height`, `top`/`left`, `margin`, `padding`, `border-width`, `box-shadow`, `background-position` (except the one shimmer) or `font-*`. For size and position changes use the `layout` prop (FLIP: two measurements, then transforms). Shadows fade in as a pre-rendered layer's opacity.
- **Backdrop-filter rules** (Liquid Glass):
  - **Backdrop-root rule.** An ancestor with `opacity` < 1, `filter`, `mask`, `clip-path`, `mix-blend-mode` or `will-change` on those strips the blur from every glass inside it (verified in Chromium 141). So do not fade a wrapper that contains glass. Fade the glass element itself, or fade a veil on top (patterns 12, 13). `transform` on ancestors is safe.
  - **Never animate `filter` on the element that carries `backdrop-filter`.** Measured: 7× more dropped frames at 1× CPU (28 vs 4 over 18 cycles) and about 3× at 4× CPU than putting the blur on its content child.
  - **Never animate the blur radius.** Thicken the material by fading a `glass-tint` layer (pattern 15).
  - **No glass on glass.** Pills and indicators inside glass are `glass-tint` fills without `backdrop-filter`.
  - **At most 3 live backdrop-filter surfaces per viewport during an animation** (shell bar, one floating panel, one sheet). Large blurred areas over scrolling content repaint every frame, so keep blur radius ≤ 24 px and prefer the regular variant.
  - Decorative layers are `aria-hidden` and `pointer-events: none`. The harness caught a header tint layer swallowing clicks.
- **Frame budget**: 16.7 ms (8.3 ms at 120 Hz). Keep JS per animation frame ≤ 4 ms. One focal animation at a time. Grids (1,080 timetable cells, heatmaps) never animate per cell: use one overlay element (drop slot, highlight) that moves.
- `will-change: transform` only during a gesture (set on pointerdown, clear on settle). Never leave it on, because it pins memory and creates backdrop roots when it targets opacity or filter.
- Long lists animate only rows in view (`layout` on a virtualised list's visible items). Lists with more than 40 items get no insert/remove animation.

## 5. Pattern library (`references/patterns.md`)

| # | Pattern | Token | SmartSched uses |
|---|---|---|---|
| 1 | Glass panel appear/dismiss (materialise) | glass-morph | popovers, menus, event card, jump-to-latest pill |
| 2 | Segmented control morphing indicator | glass-morph | Day/Week, Must/Try, Low/Normal/High, Classes/Exams |
| 3 | Sidebar / tab-bar liquid morph (minimise on scroll) | glass-morph | mobile tab bar, sidebar active pill, collapse |
| 4 | Sheet with detents | sheet | event sheet, filters, slot pickers on touch |
| 5 | Toast stack | smooth | move saved + undo, run done, import done |
| 6 | List insert / remove / reorder | smooth | rule cards, review tray, issues rail |
| 7 | Drag-lift / drop-settle + magnetic snap | snappy | timetable event moves (dnd-kit) |
| 8 | Resize handles (snap per period) | snappy | event span, panel splitters |
| 9 | Conflict shake (subtle) | tween 240 ms | rejected drop, invalid edit |
| 10 | Success check draw | bouncy-subtle | Saved ✓, run finished |
| 11 | Number ticker | ticker | KPI tiles, score, placed counts |
| 12 | Skeleton → content crossfade | smooth | every async region |
| 13 | Route transitions (enter-only, veil) | smooth | app/(app)/template.tsx |
| 14 | Hover specular light + parallax | pointerSpring | KPI tiles, room cards, Studio summary |
| 15 | Scroll-linked header thickening | scroll-linked | top bar, Studio header, timetable header (hard edge) |
| 16 | Chat message streaming | smooth + CSS | assistant panel |
| 17 | AI thinking shimmer | loop 1.6 s | chat, NL rules, precheck |
| 18 | Command palette open | glass-morph + snappy | ⌘K |
| 19 | Island morph (pill → card) | glass-morph | run-in-progress island |

Every pattern lists: when to use, the motion v14 code, the reduced-motion variant and an a11y note. Global setup is `<MotionConfig reducedMotion="user" transition={springs.smooth}>`. That alone does **not** cover `filter`, `backgroundPosition`, `pathLength`, `animate()` on motion values, or CSS, so each pattern handles those with `useReduce()`.

## 6. Choreography

- **Order**: container first, content second (≤ 60 ms later). On exit, content and container leave together.
- **One focal motion.** If two things must move, the one the user caused leads and everything else follows with `smooth`, or doesn't move.
- **Origin-aware.** Popovers and menus set `transformOrigin` toward their trigger. Sheets grow from the bottom edge. The island expands from its pill.
- **Drag** is 1:1 with the pointer (no spring lag while dragging). Springs take over only on release and carry the release velocity.
- **Feedback latency**: the visual response starts in the same frame as the input (press scale, highlight). Network results animate when they arrive and never fake progress.

## 7. Sources and licences (`references/sources.md`)

- **motion** v14: MIT. **beUI**: MIT (© 2026 Saurabh Chauhan), so import with a licence header and a `components/ui/SOURCES.md` row, and retime anything over 300 ms.
- **transitions.dev**: free and Pro transitions may be used "in unlimited personal and commercial projects" and modified, but the library may not be redistributed. MIT covers only their tooling. We re-implement. If anything is pasted, keep a `/* transitions.dev: <name> */` header.
- **Kinetics**: no LICENSE file, so **ideas only, no code**.
- **Apple HIG / WWDC**: guidance only, never Apple assets.
- Research more references with `mcp__Mobbin__search_flows` / `search_screens` and record links in `motion.md`.

## 8. Review checklist (every PR with motion)

- [ ] The purpose sentence exists, and the motion is not on a frequent action.
- [ ] Tokens come from `@/lib/motion` / CSS vars. No raw durations or springs.
- [ ] One-shot ≤ 300 ms, exits faster than entrances, and loops stop with the work.
- [ ] Interruptible: re-trigger mid-flight → no restart and no jump. Input is never blocked.
- [ ] Only transform/opacity animate (plus small non-glass filter). No per-frame Layout in the trace.
- [ ] No fading or filtered ancestor of glass, no filter on a `backdrop-filter` element, no glass on glass, and decorative layers have `pointer-events: none`.
- [ ] Reduced motion: no travel/scale/blur/parallax, end state on the next frame or after a ≤ 100 ms fade.
- [ ] Reduced transparency: opaque surfaces, and contrast still AA.
- [ ] Keyboard path for every gesture (drag, resize, swipe, reorder) and focus never lost.
- [ ] A non-motion signal for every state (text, icon, outline, live region). Live regions announce results, not frames.
- [ ] Touch: 44 px targets, long-press 250 ms to lift, `touch-action` set on gesture surfaces.
- [ ] Audit row added (§9) and `motion.md` table updated.

## 9. Motion audit (`references/audit.md`)

1. **Manual** (5 min): DevTools Rendering (frame stats, paint flashing, layout shift regions), Performance with 4× CPU, and the Animations panel at 10 %. Interrupt everything.
2. **Automated**: copy the spec template from `audit.md` into `smartsched/frontend/e2e/motion-audit.spec.ts`. It records a Chrome trace (`browser.startTracing`) and counts `Layout` events. It measures main-thread frames with a rAF probe plus Long Animation Frames (`PerformanceObserver({type: "long-animation-frame"})`), lists every animation over 300 ms via `document.getAnimations()`, verifies reduced motion with `page.emulateMedia({ reducedMotion: "reduce" })`, and verifies reduced transparency through CDP `Emulation.setEmulatedMedia`. Run it with `--trace on` and open it with `npx playwright show-trace`.
3. **Gates**: CI (headless, 1× CPU) allows ≤ 3 dropped frames per interaction and no LoAF > 100 ms. The device check (headed + GPU, `MOTION_CPU=4`) allows ≤ 3 dropped frames per interaction. Over-ceiling is none. Reduced motion means end state. Reduced transparency means opaque. Any failure blocks the PR, and waivers go in `motion.md` with a reason.

## 10. Files

- `references/motion-tokens.ts` is the canonical tokens and hooks (`springs`, `cssSpring`, `dur`, `ease`, `tween`, `staggerDelay`, `useReduce`, `useReducedTransparency`, `useFinePointer`). The frontend copies it to `src/lib/motion.ts`.
- `references/springs.md`: numbers, CSS mirror, stagger, v1→v2 mapping, Kinetics ideas.
- `references/patterns.md`: the 19 patterns.
- `references/audit.md`: the audit procedure, Playwright template and measured baseline.
- `references/sources.md`: Mobbin references, licence decisions and Apple quotes.
- `scripts/spring_table.py`: simulate a spring and emit its `linear()` easing.
- `scripts/check_snippets.py`: validate the frontmatter and type-check every snippet against motion v14.
