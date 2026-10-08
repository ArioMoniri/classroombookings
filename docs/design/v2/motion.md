# Motion v2: SmartSched on Liquid Glass

Owner: design-pro (motion_designer) · Status: v2.0 (2026-10-08) · Skill: `.claude/skills/motion_designer` (invoke `/motion_designer` for any motion work).
Tokens and hooks: `.claude/skills/motion_designer/references/motion-tokens.ts` → copy to `smartsched/frontend/src/lib/motion.ts`. Patterns §1–§19: `references/patterns.md`, all type-checked against motion 14.0.0.
Precedence: **this file owns motion** (springs, durations, choreography, reduced motion). `liquid-glass.md` owns material (`--mat-*`, tint, blur, rim, reduced-transparency surfaces). `calendar.md` and `all-classes.md` own layout and copy. Where a sibling spec gives a duration or curve, this file wins (see §1.2).

The planner moves 1,300 classes through 60 rooms × 18 periods × 14 weeks. Motion answers three questions only: **what changed, where did it go, did it work.** Everything else stays still.

## 0. The motion language in six rules

1. **Chrome morphs, content doesn't.** Glass controls (capsules, segmented thumbs, tab bar, island, sheets) change shape with `glassMorph`, following Apple's "singular floating plane". Opaque content (chips, rows, cells) only moves when the user moved it.
2. **The thing you touched moves.** Drag is 1:1. On release a spring carries your velocity into the slot. Rejected moves spring back to where they came from.
3. **Results arrive. Nothing performs.** No count-ups on page load, no stagger cascades on working surfaces, no looping hero animations, no parallax on content, no animated gradients except the single "thinking" shimmer.
4. **≤ 300 ms, interruptible, never blocking.** Every one-shot animation settles within 300 ms, and the next input re-targets the spring. Nothing waits for an animation.
5. **Every state has a non-motion signal.** Text, icon, outline or live-region message first. Motion reinforces it.
6. **Reduced motion and reduced transparency are first-class designs**, not degradations (§5, §6).

**Anti-AI-look motion rules** (reject in review): fade-up-on-scroll for every card · KPI numbers counting from 0 on each visit · springy bounce on cards or modals · hover lift + glow on every tile · shimmering skeletons on a working grid · gradient borders that rotate · "typing dots" when a real status exists.

## 1. Tokens

### 1.1 Springs and durations (full table in `springs.md`)

| Token | k / c / m | arrives (t95) | settles (1 %) | overshoot | SmartSched use |
|---|---|---|---|---|---|
| `snappy` | 520 / 42 / 0.8 | 195 ms | 278 ms | 0 | press, toggles, palette row pill, drop-settle, resize steps, scrubber thumb, magnetic slot |
| `smooth` | 380 / 36 / 1 | 215 ms | 281 ms | 0 | list reflow, lens content, route content, toast stack, inspector content swap |
| `bouncySubtle` | 420 / 28 / 0.8 | 140 ms | 285 ms | 2.4 % | Saved ✓, chip added, issue-count badge bump |
| `sheet` | 300 / 30 / 1 | 219 ms | 269 ms | 0.4 % | inspector, bottom sheets, filter sheet, detents |
| `glassMorph` | 400 / 30 / 0.85 | 160 ms | 281 ms | 1.2 % | segmented/lens thumb, tab-bar pill, capsule condense, island, selection bar, popover/⌘K open |
| `ticker` | 420 / 38 / 1 | 206 ms | 271 ms | 0 | numbers that change while you watch |
| `pointerSpring` | 700 / 34 / 0.5 | 109 ms | 141 ms | 0 | specular light, magnetic pull |
| durations | fast 120 · base 180 · slow 240 · max 300 ms | | | | `--dur-*` |
| easings | `--ease-out` in, `--ease-in` out (new), `--ease-in-out` on-screen tweens | | | | |
| CSS springs | `--spring-<name>` (`linear()`) + `--spring-<name>-ms` | | | | Base UI popups, dnd-kit drop |

### 1.2 Reconciliation (all specs and code written in parallel on 2026-10-08)

| Where | Name | Values | Simulated (t95 / settle / overshoot) | Map to | Action |
|---|---|---|---|---|---|
| tokens.md §6 | `--spring-drop` | 520/42/0.8 | 195 / 278 / 0 | `snappy` | same numbers |
| tokens.md §6 | `--spring-sheet` | 300/30 | 219 / 269 / 0.4 % | `sheet` | same numbers |
| tokens.md §6 | `--spring-count` | 170/26 | 363 / 507 / 0 | `ticker` | **over the ceiling, replace** |
| `components/ui/motion-presets.ts` | `SPRING_PRESS` | 620/42/0.6 | 169 / 245 / 0 | `snappy` | within budget. Alias it to `springs.snappy` so there is one press feel |
| ″ | `SPRING_MORPH` | 420/30/0.8 | 153 / 261 / 1.1 % | `glassMorph` | equivalent, alias |
| ″ | `SPRING_SHEET` | 340/34/1 | 226 / 296 / 0.1 % | `sheet` | t95 just over 220 ms, alias to `sheet` |
| ″ | `SPRING_DROP` | 520/40/0.8 | 181 / 250 / 0 | `snappy` | alias |
| ″ | `SPRING_COUNT` | 180/28/1 | 378 / 541 / 0 | `ticker` | **over the ceiling** (its comment "≈ 286 ms" uses the underdamped envelope estimate, but ζ = 1.04 is overdamped). Replace |
| ″ | `EASE_GLASS` | (0.32, 0.72, 0, 1) | — | `--spring-sheet` for sheets, `--ease-out` otherwise | keep only for vaul-style drawers |
| `globals.css` | `--ease-spring` | `linear()` ζ ≈ 0.7, 4.5 % overshoot | — | `--spring-glass-morph` (1.2 %) | 4.5 % reads as bouncy on 300 ms tab/switch moves, so swap |
| `globals.css` | `--ease-snappy` | `linear()` ζ ≈ 0.9 | — | `--spring-snappy` | swap or alias |
| calendar.md §4.1 | "lens morph" 240 ms | — | — | lens thumb `glassMorph` + content `smooth` (§3.2) | defined here |
| calendar.md §5.1 | "chrome-condense" 240 ms | — | — | `glassMorph` (§3.1) | defined here |
| calendar.md §8.4 | popover `--ease-emphasized` 180 ms | — | — | `--spring-glass-morph` | §3.2 |
| calendar.md §8.4 | zoom step "180 ms row-height interpolation" | — | — | **no interpolation** (§3.2: per-frame layout on 1,080 cells) | corrected here |
| calendar.md §8.4 | toast "sonner default (≤ 300 ms)" | sonner default is 400 ms | — | pattern §5 retimed | corrected here |
| generate-and-chat.md §3.8 | segmented {500, 40}, streaming word fade 80 ms | — | — | `glassMorph`; chunk fade 120 ms (CSS) | superseded |

**Code smells found while reconciling** (for frontend-engineer, outside this spec's write scope): `components/ui/tabs.tsx` transitions `left, top, width, height` (layout properties) and should use a `layoutId` thumb (pattern §2). `components/ui/chip.tsx` transitions `width` on the remove-button slot and should use a `grid-template-columns` swap with no transition, or `layout`.

## 2. Global behaviour

- **Provider**: `<MotionConfig reducedMotion="user" transition={springs.smooth}>` at the root (pattern §0). It drops transform/layout animation under reduced motion. Everything it doesn't cover (filter, pathLength, backgroundPosition, `animate()` on motion values, CSS) goes through `useReduce()`.
- **Input modality** (HIG: touch gets more emphasis, trackpad less). On `pointer: coarse`, press feedback is scale 0.97 plus a `glass-tint` brighten (Liquid Glass "illuminates from within"). On a fine pointer, press is scale 0.98 with no brighten. Hover effects (specular §14) exist only on `(hover: hover) and (pointer: fine)`.
- **Focus**: never animated. The focus ring appears instantly (2 px `--focus`). Focus moves at the *start* of a transition, never after it.
- **Backdrop-root rule** (verified in Chromium 141): no `opacity` < 1, `filter`, `mask`, `clip-path` or `will-change: opacity|filter` on any ancestor of a glass element. Route and region fades use a veil on top or fade a skeleton out (patterns §12, §13).
- **Budget**: ≤ 3 live `backdrop-filter` surfaces animating at once. No `filter` animation on a `backdrop-filter` element. No animated blur radius.

## 3. Per surface

Each table row is one moment: trigger → animation → token → reduced motion → reduced transparency. "RT" = reduced transparency. Pattern numbers refer to `patterns.md`.

### 3.1 Shell (sidebar, capsule toolbar, top bar, tab bar, ⌘K, toasts, run island, routes)

| Moment | Trigger | Animation | Token | Reduced motion | RT | Pattern |
|---|---|---|---|---|---|---|
| Route change | navigation | content rises 6 px. A veil (`app-backdrop`) fades 1 → 0. The old page leaves instantly | `smooth` + 180 ms veil | 100 ms veil fade, no rise | same | §13 |
| Sidebar active item | navigation | `glass-tint` pill morphs to the new row (`layoutId="nav-pill"`) | `glassMorph` | jump | pill is `--mat-thick-solid` | §2/§3 |
| Sidebar collapse 272 → 56 px | `⌘\` / button | labels fade out (120 ms), then `aside` FLIPs to its new width with icons at `layout="position"`. Content area FLIPs too (`LayoutGroup`) | fade 120 + `glassMorph` | instant | same | §3 |
| Capsule condense ("chrome-condense") | canvas scrolls > 24 px down. Expands on scroll up or at the top | capsules shrink 44 → 36 px, text labels fade, icons stay. One layout morph per state change, not scroll-linked | `glassMorph` | no condense | same | §3 |
| Top bar / sticky header material | scroll 0 → 48 px | `glass-tint` layer opacity 0 → 1 plus a hairline (24 → 48 px). The blur is constant | scroll-linked | binary at 8 px, 180 ms fade | opaque always, hairline only | §15 |
| Mobile tab bar (< 768 px) | scroll down / up | minimises (inactive labels hide, bar narrows) / re-expands. Pill morph on tab change | `glassMorph` | no minimise, pill jumps | opaque bar | §3 |
| Term switcher, user menu, popovers | open / close | scale 0.96 → 1 from the trigger, content blur 6 → 0 px, fade. Exit 120 ms at scale 0.98 | `--spring-glass-morph` (CSS) | 100 ms fade | `--mat-thick-solid` | §1 |
| Command palette | `⌘K` | panel at the top third, y −8 → 0, scale 0.98 → 1, scrim fade 120 ms. The row pill glides with the selection | `glassMorph` (CSS) + `snappy` | 100 ms fade, pill jumps | solid panel, scrim 40 % black | §18 |
| Palette results | typing | **no animation**: results swap in place (Linear) | — | — | — | — |
| Toasts | mutation result | enters y 16 → 0 plus scale 0.96 → 1. Max 3, older tuck (−5 % / −10 px), fan out on hover/focus, swipe-x dismiss, exit 120 ms | `smooth` | fade, no swipe | `--mat-thick-solid` | §5 |
| Run island | a run is QUEUED/RUNNING anywhere | compact pill in the top bar ("Run #42 · 38 %"). Click expands into a card (phase list, elapsed, Cancel). Content crossfades | `glassMorph` | size swaps, 100 ms fade | solid | §19 |
| Island → result | run finishes | pill content swaps to "✓ Run #42 · 100/92" with the check draw. A toast with View/Compare follows | `glassMorph` + §10 | static ✓ | solid | §10/§19 |
| Theme / accent / locale switch | toggle | **instant** (no colour tween across the app) | — | — | — | — |
| Shortcuts sheet `?` | key | right sheet | `sheet` | fade | solid | §4 |

### 3.2 Timetable calendar (`/timetable`, calendar.md)

| Moment | Trigger | Animation | Token | Reduced motion | RT | Pattern |
|---|---|---|---|---|---|---|
| Lens switch ("lens morph") | `B W D M Y A` / segmented | thumb morphs to the new lens. New lens content enters with opacity plus 8 px toward the lens's direction (Board ← → Agenda order). The old lens leaves instantly. The selected chip keeps `layoutId={event.id}` if it exists in both lenses | thumb `glassMorph`, content `smooth` | thumb jumps, content 100 ms fade | same | §2/§13 |
| Week change | scrubber, `[` `]`, ‹ › | enter-only: the new week fades in and slides 12 px from the travel direction (next → from the right). No crossfade (that would render two 1,080-cell grids) | `smooth` + fade 180 ms | instant | same | — |
| Scrubber thumb | week change | thumb travels to the new week | `snappy` | jump | solid capsule | §2 |
| Drag lift | pointerdown + 6 px / long-press 250 ms / Space | ghost scale 1.03, a pre-rendered shadow layer fades in (120 ms). Origin chip goes to 40 % with a dashed outline | `snappy` | no scale, shadow only | same | §7 |
| Magnetic snap | ghost within 16 px of a valid slot | ghost pulled toward the slot's top-left (full snap inside 5 px). A single drop-slot outline glides between cells (`layoutId="drop-slot"`) | `pointerSpring` feel, slot `snappy` | no pull, outline jumps | same | §7 |
| Drop ok | release on `drop-ok` | ghost settles into the new cell, then the Move popover opens from the chip | dnd-kit `dropAnimation` = `cssSpring.snappy` (280 ms) | no drop animation | popover solid | §7/§1 |
| Drop rejected | release on `conflict` | ghost springs back to the origin (same drop animation). The origin chip plays the conflict shake once. A toast gives the reason | `snappy` + shake 240 ms | no spring, no shake, outline + toast | same | §7/§9 |
| Culprit chips during drag | hovering a conflict | static red ring, **no pulse** (v1 pulse removed) | — | — | — | — |
| Resize | bottom-edge handle / slider keys | height snaps per period (FLIP per step) with a live "P7–P10" chip at the edge | `snappy` | jump per step | same | §8 |
| Quick-create (Day timeline) | drag across a free range | the selection rectangle grows in period steps (FLIP per step), then the quick-create popover opens on release | `snappy` + §1 | steps jump | solid popover | §8/§1 |
| Lasso | ⇧-drag on empty canvas | rectangle follows the pointer 1:1 (no spring). Selected chips get rings instantly | — | same | same | — |
| Inspector open / swap | select a chip | panel slides in 24 px plus fade from the right edge. Content swaps between events crossfade (no slide) | `sheet`, content `smooth` | 100 ms fade | `--mat-thick-solid` | §1/§4 |
| Inspector on phones | select | bottom sheet with detents 45 % / 92 % | `sheet` | snaps | opaque at all detents | §4 |
| Popovers (event, quick-create, legend, move) | open / close | §1 from the anchor chip | `--spring-glass-morph` | fade | solid | §1 |
| Sticky room/day headers, building bands | scroll | Apple **hard** edge: uniform tint over header plus pinned row | scroll-linked | binary | opaque | §15 |
| Compare ghosts (Run #41) | toggle | ghosts fade in 180 ms (dashed outlines). No movement from the old to the new position | fade | instant | same | — |
| Issue capsule count | count changes | the number swaps. Badge bump scale 1 → 1.08 → 1 **only** when the count increases due to the user's own action | `bouncySubtle` | swap only | same | — |
| Zoom step | `⌘+/−`, ctrl-wheel, segmented | **instant** re-layout, with the row under the pointer kept under the pointer (scroll anchor). No row-height interpolation, because that would lay out 1,080 cells per frame | — | — | — | — |
| Pinch zoom (touch) | two fingers | the canvas layer scales 1:1 with the fingers (`transform` only), then commits the nearest zoom step on release with an instant re-layout | direct | same | same | — |
| Now-line | every 60 s | **no animation** (calendar.md §7.4) | — | — | — | — |
| Heat cells (Month/Term) | metric change | `background-color` CSS transition 180 ms, no stagger (≤ 98 cells, paint only) | `--dur-base` linear | instant | same | — |
| Undo (`⌘Z`) | key / toast | the chip FLIPs back to its previous cell | `smooth` | jump | — | §6 |
| Save failed | PATCH 409/5xx | chip springs back plus a red outline that fades after 2 s (180 ms fade) | `snappy` | jump, outline static 2 s | — | §7 |
| Agenda (phone) | scroll | sticky day headers thicken (§15) | scroll-linked | binary | opaque | §15 |

Choreography of a move (desktop):
```
t=0      pointerdown on chip
+6 px    lift: ghost scale→1.03 (snappy, t95 195 ms), shadow layer fade 120 ms, origin → 40 %
drag     ghost 1:1; slot outline glides cell→cell (snappy); magnetic pull ≤16 px
release  0–280 ms  drop animation into new cell (cssSpring.snappy)
+280 ms  Move popover opens from chip (glass-morph, t95 160 ms); focus → "Kaydet"
Enter    popover exits 120 ms; toast "BME 419 → A 101 · Geri al" enters (smooth)
```

### 3.3 All classes (`/classes`, all-classes.md)

| Moment | Trigger | Animation | Token | Reduced motion | RT | Pattern |
|---|---|---|---|---|---|---|
| Sort / filter / search / facet change | any query change | **none**: rows swap in place, and the result count text updates (polite, 500 ms debounce) | — | — | — | — |
| View tabs (saved views) | click / `1–9` | `glass-tint` thumb morph | `glassMorph` | jump | solid | §2 |
| Filter token added / removed | Enter in token input, facet click, ✕ | chip pops in (scale 0.9 → 1 plus fade). Siblings reflow (`layout`). Removal pops out of layout | `bouncySubtle` in, `smooth` reflow, exit 120 ms | appear/disappear | same | §6 |
| Group collapse / expand | chevron, `← →`, `[ ]` | chevron rotates 90° (120 ms). Rows appear/disappear **without** height animation (virtualised list) | `--dur-fast` | chevron jumps | same | — |
| Sticky header row + group headers | scroll | hard-edge thickening on `--mat-thick` | scroll-linked | binary | opaque | §15 |
| Row selection | click, `x`, ⇧-click | checkbox tick draws (120 ms). Row tint instant | `--dur-fast` | instant | same | §10 (mini) |
| Selection bar replaces toolbar capsule | first selection / clear | the capsule morphs into the selection bar: one `layoutId="toolbar-capsule"` with content crossfade, matching all-classes.md's "180 ms cross-fade" | `glassMorph` | swap, 100 ms fade | solid | §19 |
| Inline edit | double-click, `e`, Enter | the editor appears in place (no scale). On save the cell shows Saved ✓ for 1 s. Failure rolls back plus shake on the cell | ✓ `bouncySubtle`, shake 240 ms | static ✓, no shake | same | §10/§9 |
| Bulk action applied | bulk bar | affected rows get a "changed" dot instantly. A toast with Undo and count. No row flashing | `smooth` (toast) | — | — | §5 |
| Column chooser / display popover | open | §1 | `--spring-glass-morph` | fade | solid | §1 |
| Column reorder | drag header | header lifts (§7 lift), siblings reflow (`layout` on header cells only, ≤ 24 items) | `snappy` / `smooth` | no lift, jump | — | §6/§7 |
| Inspector | row open | same as calendar §3.2 (shared `ClassInspector`) | `sheet` | fade | solid | §4 |
| Loading (first) | data fetch | static placeholder rows (no shimmer). Content replaces them via skeleton-on-top fade | 120 ms fade-out | same | — | §12 |
| Mobile select mode | long-press / "Seç" | checkboxes slide in 24 px (transform), then the bulk bar replaces the tab bar (morph) | `smooth`, `glassMorph` | appear | solid | §3 |
| Mobile search circle → field | tap | the circle morphs into a full-width field (island idiom) | `glassMorph` | swap | solid | §19 |
| Mobile filter sheet | "Filtrele" | large-detent sheet. "212 dersi göster" count swaps (no ticker) | `sheet` | snap | opaque | §4 |

### 3.4 Generator Studio (`/generate`, generator-studio.md)

| Moment | Trigger | Animation | Token | Reduced motion | RT | Pattern |
|---|---|---|---|---|---|---|
| Step change | rail click, `Alt+1–5`, `[ ]` | rail pill morphs. The workspace enters with opacity plus 8 px x in the step direction. Enter-only | pill `glassMorph`, content `smooth` | pill jump, 100 ms fade | same | §2/§13 |
| Rail status (counts, ✓, ⚠) | data change | text swaps, the ✓ draws once when a step becomes complete | §10 | static | — | §10 |
| Must / Try-to, Low / Normal / High | click, `m t 1 2 3` | segmented thumb | `glassMorph` | jump | solid | §2 |
| Write it → Analyse | `⌘↵` | button label becomes "Reading your rules…" with the thinking shimmer. The textarea stays editable | loop 1.6 s | static text | — | §17 |
| Proposals arrive | elicit result | review-tray cards enter in a stagger (30 ms, first 6) | `smooth` | appear | — | §6 |
| Accept proposal | Accept / `a` | the card travels from the tray into its rule group (`layoutId={proposal.id}`). The tray closes the gap | `smooth` | disappears from tray, appears in list (100 ms fade) | — | §6 |
| Rule card add / delete | any source | insert: fade plus 6 px drop. Delete: pop out of layout, with an Undo toast | `smooth`, exit 120 ms | appear/disappear | — | §6 |
| Rule saved | `PUT` 200 | "Saved ✓" for 1 s | `bouncySubtle` | static | — | §10 |
| Clash "Show both" | button | the other card scrolls into view (instant under reduced motion) and gets a static 2 px outline (120 ms fade-in) | `--dur-fast` | `scrollIntoView({behavior:"auto"})` | — | — |
| Upload stage | progress events | the bar's `scaleX` tracks real progress (transform, origin left). The stage label crossfades 120 ms | `snappy` per update | jumps | — | — |
| Pre-check "Checking…" | 1.5 s after the last edit | thinking shimmer on the pill only. Previous results dim to 60 % (no layout shift) | loop 1.6 s | static | — | §17 |
| Fix applied | fix button | issue card resolves: ✓ draw, then pop out of layout. The next card gets focus | §10 + `smooth` | static ✓, remove | — | §10/§6 |
| Readiness meter | precheck result | icon and word swap. The meter thumb travels | `snappy` | jump | — | §2 |
| Generate → run status | `⌘↵` | the summary panel morphs into the run status card (island pattern: same container, `layout`, content crossfade) | `glassMorph` | swap | solid | §19 |
| Run progress | SSE | phase rows tick (✓ draw). The "Must-rules broken: 0" number swaps (no ticker on a working surface) | §10 | static | — | §10 |
| Result card | FEASIBLE/OPTIMAL | status card → result card morph. Score numbers tick from the previous run's values (not from 0) | `glassMorph`, `ticker` | swap, final values | solid | §19/§11 |
| Selection bar (class list) | selection | slides up 8 px plus fade | `smooth` | appear | solid | §1 |
| Template gallery / copy / presets dialogs | open | §1. The diff table appears with no stagger | `--spring-glass-morph` | fade | solid | §1 |
| Undo / redo | `⌘Z` | the affected card or row FLIPs back. Undo toast | `smooth` | jump | — | §6 |

### 3.5 Run report (`/runs/[id]/report`, run-report.md)

| Moment | Trigger | Animation | Token | Reduced motion | RT | Pattern |
|---|---|---|---|---|---|---|
| Score ring | **only when the run finishes while the page is open** (live arrival) | ring draws from the parent run's score to the new one, then the check draws | `ticker` for the arc (≤ 280 ms) + §10 | final frame | — | §10/§11 |
| Score ring on revisit / deep link | page load | **static** (no draw on every visit) | — | — | — | — |
| KPI tiles (placed, conflicts, soft score, moved) | value change while open | tick from old to new value | `ticker` | final value | — | §11 |
| Soft breakdown bars | live arrival | bars `scaleX` from previous to new (origin left), no stagger | `smooth` | final | — | — |
| Diagnosis card expand ("Show details") | click | card height FLIP (`layout`), with details fading in after 60 ms | `smooth` + fade 120 ms | instant | same | §6 |
| Apply fix | fix button | button → spinner → ✓ morph (§10). The card resolves and pops out. The toast offers Re-solve | §10 + `smooth` | static | — | §10/§6 |
| Scenario compare (41 vs 42) | open | §1 panel. Deltas appear static (no counting) | `--spring-glass-morph` | fade | solid | §1 |
| Hover on KPI tiles | fine pointer | specular light (§14), peak alpha 0.12 / 0.08 dark | `pointerSpring` | parked light | no light layer | §14 |

### 3.6 Chat panel (`⌘J`, generate-and-chat.md)

| Moment | Trigger | Animation | Token | Reduced motion | RT | Pattern |
|---|---|---|---|---|---|---|
| Panel open / close | `⌘J`, button | the glass panel slides 24 px plus fade from the right (the panel animates itself, never its wrapper). Composer focused on frame 1 | `sheet`, exit 120 ms | 100 ms fade | `--mat-thick-solid` | §1/§4 |
| User message sent | Enter | bubble enters y 8 → 0 plus fade | `smooth` | fade | — | §16 |
| Waiting | before the first token | thinking shimmer "Düşünüyor…" plus an elapsed counter after 5 s. Send becomes Stop | loop 1.6 s | static | — | §17 |
| Assistant streaming | SSE chunks | bubble enters once. Each chunk fades in 120 ms (CSS, no JS per token). Stick-to-bottom only if already at the bottom | `smooth` + CSS | no chunk fade | — | §16 |
| Scrolled up during stream | user scrolls | a "Jump to latest ↓" glass pill appears (§1) | `glassMorph` | fade | solid | §1 |
| Tool pending | tool call | card skeleton with the phase label (static bars, shimmer only on the label) | §12/§17 | static | — | §12 |
| ProposedDiff card | tool result | card enters (fade plus 6 px). Rows appear together (no stagger) | `smooth` | fade | — | §6 |
| Apply diff | `a` / Apply | button → ✓. In the grid, each moved chip FLIPs from the old to the new cell (`layoutId={assignment.id}`), max 12 chips. Beyond 12 the chips swap and the toast says "23 ders taşındı" | `smooth` | swap | — | §6/§10 |
| Undo apply (8 s) | `u` / toast | chips FLIP back | `smooth` | swap | — | §6 |
| Composer grow | typing | autosize with **no** height animation | — | — | — | — |
| Context chips (selected cell) | selection change | chips swap with no stagger | — | — | — | — |

Choreography of a chat apply:
```
Apply      button: label → spinner (≤ 1 frame), request
200 OK     button ✓ draw (bouncy-subtle, ~280 ms) ‖ grid: moved chips FLIP to new cells (smooth, t95 215 ms)
+0 ms      toast "3 değişiklik uygulandı · Geri al (8 s)" (smooth)
+0 ms      polite live region: "3 ders taşındı: PHAR 240 A 203'ten A 206'ya, …"
```

## 4. Key flows end to end

**Generate (Studio → island → report)**
```
⌘↵            summary panel → run status card (glass-morph layout morph, content crossfade)
QUEUED        shell island pill appears in the top bar (fade + scale .9→1, glass-morph)
RUNNING       phase rows ✓ draw one by one as SSE phases complete (no fake progress)
user leaves   island keeps the status; click → island card
DONE          island pill content → "✓ Run #42 · 100/92"; toast "Görüntüle · Karşılaştır"
open report   score ring draws from #41's score to #42's (ticker), KPI tickers from #41 values
revisit       everything static
```

## 5. Reduced motion (`prefers-reduced-motion: reduce`)

Apple: Reduce Motion "decreases the intensity of some effects and disables any elastic properties". Our implementation:

| Category | Full | Reduced |
|---|---|---|
| Travel (x/y), scale, layout morphs, `layoutId` | springs | **none**: end state on the next frame (`duration: 0`; MotionConfig drops transform/layout) |
| Elastic overshoot (`glassMorph`, `bouncySubtle`) | 1.2 % / 2.4 % | none |
| Opacity entrances/exits | 120–180 ms | ≤ 100 ms linear (`tween.reduced`) |
| Blur clearing (popover content, island content) | 6 → 0 px | none |
| Scroll-linked effects (header thickening, tab-bar minimise, capsule condense) | continuous | header becomes binary with a 180 ms fade. No minimise, no condense |
| Parallax and specular | pointer-driven | parked static highlight |
| Shake | 3 px × 2 | none (outline plus text) |
| Draw (check, ring) | 160–280 ms | final frame |
| Number tickers | `ticker` spring | final value |
| Loops (shimmer, Checking pulse, spinners) | animated | static text or icon. Spinners become a static "…" glyph plus text |
| Drag | 1:1 plus lift, magnet, drop spring | 1:1 only (direct manipulation stays). No lift scale, no magnet, no drop animation |
| Smooth scrolling | keyboard `scrollIntoView` smooth | `behavior: "auto"` |
| CSS | `linear()` springs | `--spring-*-ms: 0ms` and the global 0.01 ms rule (tokens.md §6) |

Verification: the audit spec in `references/audit.md` (end state on the next frame, no transform animations in `document.getAnimations()`).

## 6. Reduced transparency, increased contrast, forced colours

| Setting | Detection | Behaviour |
|---|---|---|
| Reduced transparency | `@media (prefers-reduced-transparency: reduce)` (Chromium 118+ only) **or** `<html data-transparency="reduced">` from Settings → Appearance (Safari/Firefox users, and anyone) | every `--mat-*` resolves to its `-solid` value and `-filter` to `none` (globals.css, liquid-glass.md). `glass-tint` pills become `--mat-thick-solid` with a 1 px border. Specular light is removed. Scroll-thickening keeps only the hairline. Motion is **unchanged** (springs, morphs and drag all stay), because transparency and motion are independent preferences. `useReducedTransparency()` lets JS components (patterns §1, §14) swap classes |
| Increased contrast | `@media (prefers-contrast: more)` | glass uses its solid variant plus a 1 px `--border-strong` rim (Apple: "predominantly black or white … contrasting border"). Motion unchanged |
| Forced colours | `@media (forced-colors: active)` | glass and tints become `Canvas`. The pill indicator becomes a 2 px `Highlight` outline (it would vanish otherwise). The shimmer text uses `CanvasText`. The drop-slot outline uses `Highlight`. Motion unchanged |
| Reduced motion + reduced transparency | both | union of §5 and this table |
| Dark mode | `prefers-color-scheme` / toggle | same motion. Specular peak alpha 0.08 (vs 0.12) |

## 7. Performance budgets and audit plan

Per surface, audited with `references/audit.md` (CI gate: headless, 1× CPU, ≤ 3 dropped frames per interaction, no LoAF > 100 ms. Device check: headed GPU, 4× CPU, ≤ 3 per interaction):

| Surface | Interactions to audit | Extra budget |
|---|---|---|
| Shell | palette open + 2 selection moves, sidebar collapse, route change, toast ×3 | ≤ 2 backdrop surfaces animating |
| Calendar | drag across 6 cells + drop, rejected drop, resize 3 steps, lens switch, week change, scroll 2 s with sticky headers | drag frame JS ≤ 4 ms (`checkMove` < 1 ms). Layout events during drag ≤ 2 per cell change |
| All classes | scroll 2,000 rows 3 s, selection bar morph, token add/remove, group collapse | scroll at 60 fps (all-classes.md §19). No Layout during scroll beyond virtualiser |
| Studio | step change, accept proposal (tray → list), fix applied, summary → status morph | rule list > 40 cards: no insert/remove animation |
| Run report | live finish (ring + tickers), diagnosis expand | — |
| Chat | 200-chunk stream, apply diff moving 12 chips | streaming main-thread ≤ 2 ms per chunk |

Baseline measured while validating the skill (harness, Chromium 141 headless, production bundle): segmented morph 0.25 dropped frames per interaction at 1× CPU, island 1.5, glass panel 2.5 (content blur). Putting the blur on the glass element itself measured 1.6 per interaction over 18 cycles at 1×, versus 0.2 with the blur on its content, so that variant is rejected.

## 8. Implementation hand-off (frontend-engineer)

1. Copy `references/motion-tokens.ts` → `src/lib/motion.ts`. Make `components/ui/motion-presets.ts` re-export aliases (`SPRING_PRESS = springs.snappy`, `SPRING_MORPH = springs.glassMorph`, `SPRING_SHEET = springs.sheet`, `SPRING_DROP = springs.snappy`, `SPRING_COUNT = springs.ticker`) so existing imports keep working.
2. Add the CSS mirror (`springs.md` §3) to `globals.css`, and map `--ease-spring` → `--spring-glass-morph` and `--ease-snappy` → `--spring-snappy`. Add `--ease-in`.
3. Add `MotionProvider` (pattern §0) to the client providers. Add `app/(app)/template.tsx` (pattern §13) with an `app-backdrop` class from liquid-glass.md.
4. Replace `tabs.tsx`'s `left/top/width/height` transition with a `layoutId` thumb (pattern §2). Remove the `width` transition in `chip.tsx`.
5. Timetable: `magneticSnap`, `settleDrop`, `LiftedGhost`, `DropSlot` (pattern §7). Resize (§8). Shake (§9). Remove the v1 conflict pulse.
6. Run island (§19) in the top bar, wired to `GET /runs/{id}/events`.
7. Chat: `StreamingMessage` + `useStickToBottom` + `ThinkingShimmer` (§16, §17). Replace the `Loader2` spinner in `chat-panel.tsx`.
8. Add `e2e/motion-audit.spec.ts` from `audit.md` for the palette first, then one interaction per surface (§7).

## 9. Open questions

1. Should Settings → Appearance get a "Reduce motion" app-level toggle (in addition to the OS setting), mirrored to `MotionConfig reducedMotion="always"`? Recommended yes: planners on shared lab PCs can't change OS settings.
2. Cross-route shared elements (run card → report hero) need React `<ViewTransition>`, which is still experimental in Next 16. Keep enter-only until it is stable?
3. Chat apply moves > 12 chips: is the "swap + toast count" fallback acceptable, or should the grid scroll to and FLIP the first 12 only?

## Reconciliation status (design-pro liquid-glass v2, 2026-10-08)

The §1.2 conflicts and the §9 frontend items that fall inside `components/ui`, `globals.css` and `src/lib/motion.ts` are resolved:
`src/lib/motion.ts` is a verbatim copy of `references/motion-tokens.ts`, and `components/ui/motion-presets.ts` aliases it (`SPRING_COUNT = springs.ticker`). globals.css carries the `--spring-*` `linear()` mirrors (springs.md §3) and `--ease-in`, and `--ease-spring` / `--ease-snappy` are now aliases of `--spring-glass-morph` / `--spring-snappy`. `tabs.tsx` uses a `layoutId` thumb (no left/top/width/height), and `chip.tsx` has no width transition. Glass popups (transitions.dev mapping) carry no filter or will-change, and no primitive transitions `box-shadow`, `width` or `grid-template-rows`. Sonner is retimed to `--spring-smooth` with a 120 ms exit and max 3 visible. The in-app `data-motion` / `data-transparency` preferences live in `components/ui/appearance-preferences.tsx`. Still open (outside this scope): `MotionProvider` / `AppearanceMotionConfig` in `providers.tsx`, `appearanceInitScript` in `layout.tsx`, the route `template.tsx`, and the timetable items in §9.5.
