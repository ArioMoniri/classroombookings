# Motion v2: SmartSched on Liquid Glass

Owner: design-pro (motion_designer) · Status: v2.1 (2026-10-15: audit §3.7, Phase 19 §3.8–§3.11, §10; v2.0 2026-10-08) · Skill: `.claude/skills/motion_designer` (invoke `/motion_designer` for any motion work).
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
| Week / day change, grid still rendering (2026-10-15, audit T2/T3) | any week or day step | the toolbar title, mini calendar, scrubber and URL show the target at once; the lens renders deferred values (`useDeferredValue`, interruptible). While they differ, a canvas veil on top dims the old grid to ~60 % after 120 ms (`StaleVeil`, a veil and not a faded wrapper, so the glass headers keep their blur); the canvas is `aria-busy` | `--dur-fast`, delay 120 ms | cut (global rule), no travel | veil is the opaque canvas | §12 veil |
| Close the inspector (2026-10-15, audit T4) | ✕ / Esc | no motion; focus returns to the class chip it showed (else the title) | — | — | — | — |
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
| Tray card leaves (built 2026-10-15, audit T5) | accept / dismiss | `AnimatePresence mode="popLayout"`: the card fades with a 2 % scale on `tween.fadeOut`, siblings reflow by `layout` (FLIP, `smooth`). Accept: the rules refetch first, so the new rule card mounts with the card's `layoutId` and travels into its group; one-to-one batches of ≤ 12 only, the layoutId is cleared 400 ms later. > 40 pending: no animation, the count is announced. Focus moves to the next card | `smooth`, exit `tween.fadeOut` | `useReduce()` (OS or in-app switch): 100 ms fade, no layout, no travel | — | §6 |
| Rule list above 40 cards (2026-10-15) | compact density | window-virtualised; no card animates | — | — | — | §4 |
| Busy button (2026-10-15, audit T1) | any async action | `aria-busy` at once; after 150 ms the label becomes the gerund ("Ekleniyor…") with a spinner; the button stays focusable (`aria-disabled`) | spinner loop, stops with the work | a static hourglass instead of the spinner | — | `ui/busy-label.tsx` |
| Remove a rule / pin / override (2026-10-15, audit T4) | menu, button | no motion; focus moves to the neighbouring card, else the list heading (`studio/focus-after.ts`) | — | — | — | — |
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

### 3.7 Reservation panel, wave 1, calendar sync (target state after the 2026-10-15 audit)

Audit and tickets: `docs/review/2026-10-15-motion-audit.md`. Rows marked † are not built yet (the audit ticket number follows).

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Free cell hover / focus ("Boş" → "+ Rezerve et") | **none**: background tint and label swap instantly (frequent action) | — | same | same |
| Span select (drag, Shift-click, Shift+arrow) | **none**: cells tint as the span grows. The cell's name says "n ders saati seçili" | — | same | same |
| Reason hint (hover 350 ms, touch-hold 450 ms) | appears in place. Optional opacity 0 → 1 | `--dur-fast` | instant | solid already |
| Day / week change (‹ › Bugün, date picker) † T2 | **no travel**. The target date label updates in the input frame. After 120 ms pending, the solid grid dims to 60 % (`data-stale`) until data arrives. The grid swap renders deferred (T3) | `--dur-fast` opacity | dim without transition | same |
| Lens switch Grid ↔ Free slots | segmented thumb morph. New lens content enters with opacity + 8 px toward its side, the old one leaves instantly | thumb `glassMorph`, content `smooth` | thumb jumps, 100 ms fade | solid thumb |
| Book / booking / room / slot sheets | §4 sheet from the right (bottom on phones). Opens in the input frame: body content that needs data renders after the open frame (T3) | `--spring-sheet` (270 ms), exit 120 ms `--ease-in` | end state next frame | `--mat-chrome-solid` |
| Room details → Reserve, slot info → other rooms † T9 | **one sheet**, content swaps (crossfade, no slide) with a "‹ Oda" back control. Never two sheets animating | `smooth` (opacity only) | 100 ms fade | solid |
| Multi-select tray (floating glass toolbar) † T8 | enters y 8 → 0 + fade on the first selection, leaves on clear. The glass element animates itself | `smooth`, exit `tween.fadeOut` | 100 ms fade | solid bar |
| Bulk cancel done † T10 | rows leave with §6 pop-out (≤ 40 visible rows, else instant). Toast with count and Undo | `smooth`, exit 120 ms | instant, toast | solid toast |
| Room photo → lightbox | dialog §1 (no shared-element zoom: the dialog is a separate portal and the photo is not the user's data) | `--spring-glass-morph` | fade | solid |
| Calendar-sync copy link † T11 | copy glyph morphs to ✓ in place for 1.5 s. Button name "Kopyalandı". Toast stays | `bouncySubtle` | static ✓ | — |
| Busy buttons (save, search, reserve, approve, connect, load more) † T1 | label → gerund after 150 ms ("Aranıyor…"), `aria-busy`. Spinner only as reinforcement | spinner loop | spinner hidden, static "…" + text | — |
| Bell badge | number swaps. Badge bump 1.08 → 1 when the unread count **grows**. This is a deliberate exception to "only the user's own action" (§3.2): a new approval request must be noticed. At most once per poll (60 s) | `bouncySubtle` | swap only | — |
| Bell popover | §1 materialise from the bell | `--spring-glass-morph` | fade | `--mat-thick-solid` |
| Run island dot | **static** dot. The "%38" text carries progress (no ping loop) | — | same | solid |
| Approvals: decide → next request | drawer content crossfades to the next request (keyed by id). Focus → new title at the start. The decided row pops out of the list (≤ 40 rows) | `smooth`, exit `tween.fadeOut` | instant swap | solid drawer |
| Approvals PENDING state | **none**: Hourglass glyph + word. Never pulse | — | — | — |
| Audit row expand / my request expand | chevron rotates. Details appear without height animation (lists can exceed 40 rows) | `--dur-fast` | chevron jumps | — |
| Audit Undo, Withdraw request, Delete feature † T4 | confirm dialog §1. On success focus moves to the surviving row control (never `<body>`). Row status text swaps | dialog `--spring-glass-morph` | fade | solid dialog |
| Find-a-room search † T2 | results replace in place (no stagger). During a re-search old results dim to 60 % after 120 ms. Phones scroll to results smoothly | `--dur-fast`, `scrollIntoView` smooth | dim without transition, `behavior:"auto"` | — |
| Deep link to a request (`?request=`) | smooth scroll to the row. Tint highlight fades out after 2 s | `--dur-base` | `auto` scroll, highlight removed without fade | — |
| Placeholders while loading † T7 | **static** placeholder rows. Data arrives with a skeleton-on-top fade-out (§12) | `tween.fadeOut` | instant | — |

### 3.8 Multi-file intake (Phase 19 3a/3e, `phase19-intake.md`)

Purpose: while files are read, motion tells the coordinator **which file is being worked on and when each one is done**. During review it tells them **what they just decided**. Everything else (1,588 rows) stays still.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| `intake.drop-hover` (OS file dragged over the zone) | zone tint + 2 px accent outline + "Bırakın" label, **instantly**. No lift or magnet: the user is not holding one of our elements, so §7 does not apply (`magnetic-drop.tsx` stays for in-app drags) | — | same | outline only |
| `intake.file-row-added` (drop or picker) | rows insert with fade + 6 px drop. Stagger only for the first drop (30 ms, first 6). More than 40 files: no animation, the count text updates | `smooth`, stagger 30 ms | appear | — |
| File removed before start | pop out of layout, siblings reflow | exit `tween.fadeOut`, reflow `smooth` | instant | — |
| Format detected (`XLSX`, `CSV · Windows-1254 · ;`) | the Biçim cell text swaps once. A server correction ("PDF · metin katmanı var → Doğrudan") gets a 2 s tint highlight that fades | `--dur-base` fade | text swap, no highlight fade | — |
| `intake.file-phase-progress` | per file a 4 px bar: indicator `scaleX` (origin left) follows the real SSE value. Never faked or eased ahead | `snappy` per update | jumps | — |
| Active phase label ("çıkarım %62") | §17 thinking shimmer on **the one active phase label of the file being read**. The council reads files one by one, so at most one shimmer per job. Queued files say "Sırada" (static) | loop 1.6 s | static text | `CanvasText` in forced colours |
| `intake.file-done` | status glyph → ✓ draw. Counts text ("1.348 toplantı · 193 kural metni") swaps in. Polite live region: "<dosya>: okundu, 1.348 satır" | §10 `bouncySubtle` | static ✓ | — |
| File failed | ✕ glyph + message in infeasible tone. **No shake** (system failure, not rejected input). "Yeniden oku" gets focus only if focus was in that row | — | same | solid tone |
| Job progress pill ("Okunuyor · %38") | number swaps per SSE event (no ticker: it updates continuously) | — | same | solid pill |
| `intake.step-change` (Dosyalar → … → Kaydet, non-linear) | stepper pill morph. Step content enters with opacity + 8 px in the travel direction (right for a later step, left for an earlier one), enter-only. Focus → step heading | pill `glassMorph`, content `smooth` | pill jumps, 100 ms fade | solid pill |
| Step count changes (`intake.mapping-changed-recount`: İnceleme 41 → 1.389) | `ticker` on the stepper count only, from the old value, because the user caused it by changing a mapping | `ticker` | final value | — |
| Rows streaming into İnceleme (SSE while reading) | **no per-row animation and no stagger** (live update). The virtualised table appends. If rows arrive below the fold, a "↓ 128 yeni satır" glass pill appears at the table bottom (chat jump-to-latest idiom, §1). The table never auto-scrolls | pill `glassMorph` | pill fades | solid pill |
| `intake.row-decided` (Bekliyor → Onaylandı / Reddedildi / Düzenlendi), `a` / `r` / `e` | **none on the row** (phase19-intake A9): glyph + word swap in the Durum cell. The row stays in place even under the "Bekleyen" filter until the filter is re-applied. A "12 karar verildi · gizle" link removes them, which avoids rows jumping under the cursor. Focus → next Bekliyor row | — | same | — |
| Reject (row) | Durum "✕ Reddedildi", row text at 55 % opacity (instant). Undo inline for 8 s | — | same | — |
| Inline cell edit | editor appears in place (no scale). Save → Düzenlendi glyph. Invalid value → §9 shake once on the cell + reason text | shake 240 ms | no shake, outline + text | — |
| `intake.bulk-bar-in` (selection) | toolbar capsule morphs into the selection bar (§19, `layoutId="toolbar-capsule"`) | `glassMorph` | swap, 100 ms fade | solid bar |
| Bulk accept / reject (40 rows) | no row animation. Counts swap. Toast "40 satır onaylandı · Geri al". Focus stays on the toast action for 8 s, then returns to the table | `smooth` (toast) | toast fades | solid toast |
| `intake.source-pane-open` / `swap` | §1/§4 inspector from the right (docked ≥ 1600 px). Swapping rows crossfades content only. The highlighted cell box in the preview jumps to the new cell (no glide across a spreadsheet image) | `sheet`, content `smooth` | 100 ms fade | `--mat-thick-solid` |
| Fark (diff) groups `Yeni · Değişecek · Aynı · Dosyada yok` | group switch = filter: **none**. Field diff `A 105 → A 105 (Bilg. Lab)` is text and colour (strike-through + accent), static | — | — | — |
| `intake.commit-confirm` | §1 dialog | `--spring-glass-morph` | fade | solid |
| `intake.committed` | Kaydet button → spinner → ✓ draw. The draft pill swaps to "Kaydedildi". The commit bar stays (no morph, it is the user's anchor). Toast "2026-BAHAR'a 412 talep yazıldı · Takvimi aç · Geri al". Polite live region | §10 + §5 `smooth` | static ✓ | solid |
| Stale (someone else decided rows) | toast only. Rows do not reshuffle until "Yenile" | `smooth` | fade | solid |

Choreography of reading three files:
```
drop       3 rows insert (smooth, 30 ms stagger) · "Başlat" focused
start      file 1 phase line: shimmer on "okuma"; files 2–3 "Sırada" (static)
SSE        file 1 bar scaleX tracks bytes/rows (snappy per event, no easing ahead)
file 1 ✓   ✓ draw (bouncy-subtle) ‖ counts swap ‖ live: "v5.xlsx: okundu, 1.348 satır" ‖ shimmer moves to file 2
job done   pill "Okuma bitti · 41 bekliyor" ‖ İnceleme count ticks once ‖ live region announces
```

### 3.9 Moderation tab (Phase 19 3b, `phase19-moderation.md`)

Purpose: switching entities and editing must feel instant (no motion). Motion is reserved for the **Recreate preview**, where it shows **which classes moved and from where**, never more than one focal change at a time.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| `moderation.tab-switch` (Dersler · Kişiler · Talepler · Tercihler · Eşleşmeler, `1–5`) | segmented thumb morph. Table content enters with opacity + 8 px toward the tab's side, enter-only, **no stagger**. Selection and scroll per tab are kept (URL) | thumb `glassMorph`, content `smooth` | thumb jumps, 100 ms fade | solid thumb |
| Filter, search, sort, quick state chips | **none** (rows swap in place, count text updates) | — | — | — |
| `moderation.inspector-open` / `swap` | §4 inspector from the right. Swapping rows crossfades content (no slide). `‹ ›` steps rows | `sheet`, content `smooth` | 100 ms fade | `--mat-thick-solid` |
| `moderation.profile-open-as-sheet` (560 px from any table) | §4 sheet. Phones: bottom sheet 45 % / 92 % | `sheet` | snaps | opaque at all detents |
| Profile tabs (Zaman çizelgesi · Tercihler · Öneriler) | segmented thumb. Content swaps enter-only | `glassMorph`, `smooth` | jump, 100 ms fade | solid |
| Timeline first load | **static** (history, nothing performs) | — | — | — |
| `moderation.timeline-group-expand` (term group, pattern occurrences) | container FLIP via `layout` (≤ 40 items in the group, else instant). Children `layout="position"`. Details fade in 60 ms after | `smooth` + fade 120 ms | instant | — |
| New timeline entry after an edit (live) | inserts at the top of its term group with fade + 6 px drop and a tint highlight that fades after 2 s. Groups over 40 items: highlight only | `smooth`, highlight `--dur-base` | highlight static 2 s, then removed | — |
| Inline edit open (popover from a row) | §1 materialise from the row's Düzenle button | `--spring-glass-morph` | fade | `--mat-thick-solid` |
| `moderation.inline-edit-saved` | popover exits 120 ms. Row shows "Kaydedildi ✓" for 1 s. Toast with Undo. Focus returns to the row's Düzenle | §10 `bouncySubtle` | static ✓ | solid toast |
| Inline edit rejected (validation / 409) | 422: §9 shake once on the field + message. 409 (changed by someone else): outline + "Fatih Bey değiştirdi · Yenile", **no shake** | shake 240 ms | outline + text | — |
| `moderation.staged-count-bump` ("12 değişiklik yayında değil") | badge bump 1 → 1.08 → 1 only on the user's own edit (§3.2 rule) | `bouncySubtle` | swap | — |
| `moderation.selection-bar` | toolbar capsule → selection bar (§19) | `glassMorph` | swap | solid |
| `moderation.recreate-start` (sheet → island) | the Recreate sheet's primary button morphs into the run island pill in the top bar: one `layoutId="run-island"` element, sheet exits 120 ms. Island shows "Yeniden çözüm · %38" (text, static dot) | `glassMorph` | island appears, sheet fades | solid island |
| `moderation.recreate-ready` | island → "✓ Önizleme hazır" (§10). Toast "Önizlemeyi aç" | §10 + §5 | static ✓ | solid |
| Preview summary line (Taşınan 2 · Değişmeyen 646 · Yeni yerleşen 1 · Yerleşemeyen 35 (önce 36)) | **static on arrival** (no count-up). "(önce 36)" is the delta, as text | — | — | — |
| `moderation.preview-group-switch` (Taşınan / Yeni yerleşen / Yerleşemeyen / Değişmeyen) | segmented thumb. Table swaps in place (filter = no motion) | `glassMorph` | jump | solid |
| Diff row encoding (table) | text first: **Taşınan** "Sal P4–P5 · A 306 → başka oda" with → glyph. **Yeni yerleşen** "— → A 306 + C 602" with a ＋ "Yeni" chip. **Yerleşemeyen** ✕ glyph + diagnosis sentence. **Değişmeyen** collapsed group, searchable, label-3. Colour is never the only signal | — | — | — |
| "Takvimde göster" (open the preview on the calendar) | the calendar opens in compare mode: ghosts at old cells (dashed, 40 %, fade 180 ms, §3.2 compare ghosts). Moved chips sit at the new cell with an accent ring. Newly placed chips carry a "Yeni" chip. **Unchanged chips get no class change and no animation**: one `data-diff="on"` attribute on the grid root dims them through CSS, applied instantly (a transition would touch 1,300 layers) | ghosts `--dur-base` | ghosts appear instantly | ghosts as 1 px dashed `CanvasText` in forced colours |
| Old → new continuity on the calendar | when compare mode opens, **only moved chips in the viewport, at most 12**, FLIP from the old cell to the new one (`layoutId={assignment.id}`), like chat Apply (§3.6). More than 12, or off-screen: no travel. Ghost + ring + caption "↗ Sal P4 · A 306'dan" carry it | `smooth` (t95 215 ms) | no FLIP | — |
| Step through changes (`j` / `k`, "1 / 3") | one focus overlay (`layoutId="diff-focus"`) glides to the next changed chip and the grid scrolls it into view. For the focused change only, an SVG arrow from the ghost to the new cell draws (`pathLength` 0 → 1) | overlay `snappy`, arrow `--dur-base` | overlay jumps, arrow static, `scrollIntoView({behavior:"auto"})` | arrow `CanvasText` |
| Before / after toggle (segmented "Önce · Sonra") | moved chips in view (≤ 12) FLIP between old and new cells. The rest swap instantly. Toggling mid-flight re-targets (springs, no restart) | `smooth` | instant swap | solid toggle |
| Yerleşemeyen list (rail or tab) | first reveal: §6 insert, stagger first 6 (30 ms). Culprit links highlight the culprit chips with a static ring (no pulse) | `smooth` | appear | — |
| "Bu taşımayı engelle" (pin, re-runs the preview) | the row gets "Yeniden hesaplanıyor…" with the §17 shimmer. When the new preview arrives, rows update in place (no reorder animation). Toast with the delta | loop 1.6 s | static text | — |
| `moderation.publish-confirm` / `published` | §1 dialog. Then the primary button → ✓, toast "Yayınlandı · 3 kişiye e-posta gönderildi · Önceki plana dön". Ghosts fade out 120 ms. Live region | §10 + §5 | static ✓, ghosts removed | solid |
| Vazgeç (discard preview) | ghosts fade out 120 ms. Moved chips in view (≤ 12) FLIP back to their old cells | `tween.fadeOut`, `smooth` | instant | — |

Choreography of opening a preview in the calendar:
```
t=0       grid root gets data-diff="on" (unchanged chips dim via CSS, no transition)
t=0       ghosts fade in at old cells (180 ms) ‖ moved chips in view (≤12) FLIP old→new (smooth)
t=0       focus → "1 / 3" stepper; live: "2 ders taşındı, 1 ders yeni yerleşti, 35 ders yerleşemedi"
j         diff-focus overlay glides to change 2 (snappy) ‖ arrow ghost→new draws (180 ms)
```

### 3.10 Suggestion cards and learning memory (Phase 19 3c, `phase19-suggestions.md`)

Purpose: a suggestion is a proposal, never an alert. Motion shows **where an accepted suggestion went** and that a dismissal can be undone. Suggestions never arrive with motion while the user works (pull, not push).

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| `suggestion.group-first-reveal` (profile, Studio tray group, intake group) | §6 insert with stagger, first 6, **first reveal only** | `smooth`, 30 ms | appear | — |
| Recomputed suggestions arrive later (`suggestion.recomputing`) | while computing: §17 shimmer on "Öneriler yeniden hesaplanıyor…" (text only). New cards insert at the top **without** stagger. Removed ones pop out. More than 40: no animation, count text | loop 1.6 s, `smooth` | static text, appear | — |
| Card hover (fine pointer) | **none** (no lift, no glow) | — | — | — |
| `suggestion.evidence-expand` ("Kanıtı göster ▾") | card FLIP via `layout` (≤ 40 evidence rows), rows fade in 60 ms after. Chevron rotates | `smooth` + fade 120 ms | instant | — |
| Accept (Kabul et, weight/scope split menu) | menu §1 from the split button. On 200: button → ✓ draw | menu `--spring-glass-morph`, ✓ `bouncySubtle` | fade, static ✓ | solid menu |
| `suggestion.accept-to-rules` (Studio tray → rule list, same screen) | the card travels into its rule group with `layoutId={suggestion.id}`, as an accepted proposal does (§3.4, audit T5). At most 12 at once. Focus → next card in the tray | `smooth` | disappears from tray, appears in list (100 ms fade) | — |
| `suggestion.accept-receipt` (profile / Öneriler, where the rule list is not on screen) | the card collapses to the one-line receipt "✓ Yumuşak tercih eklendi · Tercihler'de gör · Geri al": container FLIP via `layout`, content crossfade. After 8 s the receipt pops out (exit 120 ms) **unless it has focus or hover** (paused like a toast). Then focus → next card | `smooth`, exit `tween.fadeOut` | instant collapse, receipt removed without animation | dashed card → solid receipt (already) |
| Dismiss (Yoksay) | the card body crossfades in place to reason chips ("Artık geçerli değil" · … · "Nedensiz atla"). Picking one collapses to a receipt with Geri al (as above). Focus → first chip, then → next card | `smooth` | instant | — |
| Snooze (Ertele ▾: bir sonraki çözüm · 7 gün · gelecek dönem) | menu §1. On choice: receipt "… ertelendi · Geri al". If a "Ertelenenler (3)" group is visible, the card travels into it (`layoutId`), else it collapses to the receipt. The group count bumps (the user's own action) | `smooth`, bump `bouncySubtle` | instant | solid menu |
| Undo (receipt or toast) | the card re-inserts at its old index (§6 insert, fade + 6 px). Focus → the card's Kabul et | `smooth` | appear | — |
| Swipe on phones (right = Kabul et, left = Yoksay) | card follows the finger 1:1 (`touch-action: pan-y`). Release past 40 % of the width or > 500 px/s: flies out with the release velocity, then the receipt. Otherwise springs back. Buttons remain (never gesture-only) | release `snappy` with velocity | no swipe animation (card stays, action via buttons) | — |
| Settings › Öğrenme: scope rows | **none** | — | — | — |
| `memory.reset-confirm` (alertdialog) | §1 dialog. "SIFIRLA" typed gate: the button enables with no animation. Enter with a wrong word → §9 shake once on the field + "Yazılan kelime eşleşmiyor" | `--spring-glass-morph`, shake 240 ms | fade, outline + text | `--mat-thick-solid` |
| `memory.reset-done` | dialog exits 120 ms. Toast "Sıfırlandı · Geri al" stays **10 s** (destructive). Open suggestion lists for that scope crossfade to their empty state as one region (no per-card exit) | `smooth` toast, region fade `--dur-base` | toast fades, list swaps | solid toast |
| "Son sıfırlamalar" row + countdown ("27 gün kaldı") | row inserts at top (§6). Countdown is text, updated daily (no ticking animation) | `smooth` | appear | — |
| `memory.reset-undo` | row text → "Geri alındı". Suggestions re-appear with an enter-only fade of the list region (no stagger) | `--dur-base` | instant | — |

### 3.11 Program-from-scratch wizard (Phase 19 3d, `phase19-program-wizard.md`)

Steps: Program → Dersler → Şubeler → Öğretim elemanları → Kohortlar → Odalar ve haftalık düzen → Kısıtlar → Oluştur ve çöz. They can be visited in any order. Purpose: motion shows **where you are in the eight steps and when a step becomes complete**. Data entry has no motion.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| `wizard.step-change` (rail click, Devam ›, ‹ Geri, `Alt+1–8`) | rail pill (`glass-tint`, `layoutId="wizard-rail"`) glides to the step. Content enters with opacity + 8 px from the travel direction (forward from the right, back from the left), enter-only. The old step leaves instantly. Focus → step heading in the input frame | pill `glassMorph`, content `smooth` | pill jumps, 100 ms fade | pill `--mat-thick-solid` + 1 px border |
| `wizard.rail-status-change` | status text swaps ("7 ders · 63 AKTS", "⚠ 2"). ✓ draws **once** when a step first becomes complete. It does not redraw on revisit | §10 `bouncySubtle` | static ✓ | — |
| `wizard.autosave` ("Tüm değişiklikler kaydedildi · 1 dk önce") | text swap only (saves every 800 ms; a ✓ animation would be a frequent action) | — | — | — |
| Field-level info fix ("MBG532 → MBG 532 olarak düzeltildi") | the corrected value replaces the typed one on blur. The info line appears with no motion | — | — | — |
| Field error on blur / on Devam | outline + message, instant. On Devam with errors: §9 shake once **on the first invalid field** (not the step), focus moves there | shake 240 ms | outline + text, focus | — |
| `wizard.error-summary` (step 8 with ✕) | the summary row's ✕ glyph and text, static. "Düzelt" jumps to the step (step-change motion) | — | — | — |
| `wizard.row-added` (Dersler / Şubeler grid, + Ekle) | new row inserts with fade + 6 px drop, focus in its first cell. Grids over 40 rows: no animation | `smooth` | appear | — |
| `wizard.paste-inserted` ("Excel'den yapıştır", many rows) | **no row animation**. Count text "12 satır eklendi" + toast with Undo | `smooth` (toast) | toast fades | solid toast |
| Row removed | pop out of layout (≤ 40), toast Undo | exit `tween.fadeOut` | instant | — |
| Level choice cards (Önlisans · Lisans · Tezli YL …) | selected card: instant outline + radio dot. No scale, no bounce | — | — | — |
| `wizard.preview-card-update` (right column "7 ders · 7 şube · haftada 19 saat") | `ticker` on the numbers only, from the previous value, because the user's edit caused the change. Text lines that appear (e.g. "7 ortak ders bağlantısı") fade in 120 ms | `ticker`, `--dur-fast` | final values | `Card variant="glass"` → solid |
| `wizard.day-toggle` (weekly hours) | switch thumb travels. The time range row appears / disappears without height animation | `snappy` (beUI availability spring retimed) | thumb jumps | solid track |
| "Diğer günlere kopyala" | target day rows update in place. A 1 s tint highlight on the changed days fades | `--dur-base` | highlight static 1 s | — |
| `wizard.create-and-solve` | confirm dialog §1. Then "Oluştur ve çöz" → spinner label "Oluşturuluyor…" → the run island (§19, as Studio Generate). On finish the island links to the moderation preview (§3.9) | `glassMorph` | swap | solid island |
| Mobile compact stepper "6/8 · Odalar ve düzen ▬▬▬▬▬▬▭▭" | segment bar `scaleX` to the new fraction. Tapping opens the step list as a bottom sheet (§4) | `smooth`, `sheet` | jump, snaps | opaque |
| Offline ("Çevrimdışı · değişiklikler bu cihazda tutuluyor") | banner appears / disappears without motion | — | — | solid |

### 3.12 Sign-in and accounts (`/login`, `/welcome`, admin users; `sign-in.md` §10)

Copied from [`sign-in.md`](sign-in.md) §10 (2026-10-15); that spec owns the screens, this table owns the motion.

Purpose sentences first; nothing animates on page load (the old "card fade + rise 200 ms" was decorative, A9).

| Moment | Purpose | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| Door 2 opens / closes | "The password form appears under the row you pressed, and the column makes room" | The column is a `motion.div layout`; the form mounts in `AnimatePresence` with opacity 0 → 1 (60 ms after the layout starts), exit opacity → 0; chevron rotates 180° (transform). No `height` animation | layout `springs.smooth`; content `dur.fast` 120 ms `ease.out`, exit 80 ms `ease.in`; chevron `springs.snappy` | No layout animation; content opacity `tween.reduced` (100 ms); chevron flips instantly | Same (the sheet is opaque; motion unchanged) |
| Microsoft button pressed | "Your press registered and we are leaving for Microsoft" | Press scale .97; busy label after 150 ms | `--spring-snappy` (CSS) | No scale; label swap only | Same |
| Local sign-in failed | "It did not work; the problem is in these two fields" | Alert enters (opacity + y −4 → 0); the field group shakes once (pattern 9) | Alert `springs.snappy`; shake 280 ms (`--shake-dur-a` 80 × 2 + `--shake-dur-b` 60 × 2) | No shake, no travel; alert opacity 100 ms. The alert text, `aria-invalid` and focus carry the state | Same |
| SSO error / notice on arrival | (none: it is the page's initial state) | None | — | — | — |
| Welcome check | "The account now exists" | Check path `pathLength` 0 → 1 and the 28 px disc scale .8 → 1, once on mount (pattern 10) | `springs.bouncySubtle` (≤ 32 px, overshoot allowed) | Static check | Same |
| Language switch | "This option is now selected" | Segmented thumb (pattern 2); text changes without animation | `springs.glassMorph` | Thumb jumps | Same |
| After success | — | Standard route enter of `app/(app)/template.tsx` (pattern 13); no extra | — | per pattern 13 | — |
| Admin: invite sheet | "The form comes from the button's side and returns there" | `Sheet` (pattern 4) | `springs.sheet`, exit 120 ms | Opacity 100 ms | Opaque sheet |
| Admin: invite created | "It worked; here is the next step" | Toast (pattern 5) with "Bağlantıyı kopyala". **No row insert animation** (the users list has > 40 rows) | `springs.smooth` | Toast opacity only | Opaque toast |

Choreography and budget: one focal motion at a time; inside the glass sheet only children animate (never the sheet's
opacity or filter, G6); transform and opacity only; the layout animation touches ≤ 12 elements. Checklist §8 of the
skill: purpose sentences above; tokens from `@/lib/motion` / CSS vars; every one-shot ≤ 280 ms; re-clicking the
disclosure mid-flight re-targets (layout springs are interruptible) and input is never blocked; keyboard path = the
disclosure is a button (Enter/Space); non-motion signals = `aria-expanded`, alert text, focus.

Audit hook: add `sign-in` to `e2e/motion-audit.spec.ts` (open and close door 2 three times quickly at 4× CPU: ≤ 3
dropped frames, no `Layout` events per frame after the first, nothing > 300 ms in `document.getAnimations()`, and under
`reducedMotion: "reduce"` the form is fully visible on the next frame).

### 3.13 Design-system primitives (design-system overhaul 2026-10-15)

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| SegmentedControl value change ("the thumb travels to the view that is now on") | ONE thumb, resting place pure CSS (`translateX(index × 100%)` in equal columns); only `transform` transitions; re-targets mid-flight. Replaces the layoutId thumb, which rested ~16 px above its track in dark mode | `--spring-glass-morph` / `--spring-glass-morph-ms` (CSS mirror of `springs.glassMorph`) | duration 0 (global rule): the thumb jumps; label colour + `aria-selected`/`aria-checked` carry the state | solid `--mat-thick-solid` thumb (unchanged motion) |
| Tabs (ui/tabs default variant) | Base UI `Tabs.Indicator` positioned by `--active-tab-left/width`; `transform` transitions, width snaps | same | jumps | same |
| Column resize (DataTable, /classes) | none: direct manipulation follows the pointer 1:1 (frequent action, skill §2.1); keyboard steps 8 / 32 px | — | — | — |
| "+N çakışma" chip → popover list | popover panel reveal (pattern 1) | Popover primitive (`glass-morph`) | opacity only | thick solid |
| Forced-move reason dialog | Dialog open (pattern 1 / modal) | Dialog primitive | opacity 100 ms | opaque |
| BarList values, KPI numerals, heatmap | none on load (A9); a KPI that changes while open rolls (pattern 11) | `ticker` | final value | — |

### 3.18 Charts (`docs/design/v3/charts.md` §8; CH-02/CH-03, designer charts-p2-2026-10-17)

Numbered 3.18 because charts.md and the ROADMAP cite it (3.14–3.17 are not used yet). Purpose: "When a chart's data
arrives or changes because the user asked, motion tells them the new state is ready; it never decorates." Free
transitions.dev recipes only, re-implemented in `components/charts/chart-card.css`; Motion Agent hosted fixes used: 0.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| First load of a plot | none: no grow-in, no stagger (`animationType="none"`, ECharts `animation: false`) (A9) | — | same | — |
| Loading → plot | skeleton bars pulse while fetching (stops when the skeleton unmounts), then the plot fades in, only when it replaces a loading state | `skeleton-reveal` (free): pulse 1000 ms loop, reveal retimed 400 → 180 ms (`--dur-base`), opacity only (no blur on a plot > 400 × 300) | no pulse; 100 ms linear fade | skeleton is an opaque fill |
| Period change (user caused) | data swaps at once; the summary sentence rises in | `text-states-swap` (free), enter half only, 150 ms, 4 px | instant | — |
| "Veriyi indir → İndirildi ✓" (and back after 2 s) | label rises in; polite live region "CSV indirildi" | `text-states-swap` (free), 150 ms | instant | — |
| Tooltip (hover, tap, keyboard ←/→) | fades and scales 0.97 → 1 after 80 ms; out is instant (ECharts `display: none`) | `tooltip` (free), 150 ms in | opacity only, 100 ms | the tooltip is always solid (no glass: fading a glass ancestor strips its blur) |
| Hover emphasis on a series | ECharts `stateAnimation.duration` | 120 ms (`--dur-fast`) | 0 | — |
| Keyboard scrub (CH-03) | the tooltip jumps to the bucket (no travel); the live region reads it after 250 ms | — | same | — |
| Period control pill | existing SegmentedControl thumb (3.13) | `glass-morph` | existing | existing |
| Live telemetry tick (ops) | none; the "Güncellendi" time swaps | — | — | — |

Rejected: `number-pop-in` (500 ms count-up), `shimmer-text`, `matrix-loader`, EvilCharts' 2 s loading shimmer and 500 ms
bar grow-in. Audit: `e2e/charts-a11y.spec.ts` (keyboard, forced colours, print); the motion-audit pattern runs on the
chart routes in CH-06/CH-12.

### 3.19 Sign-in security (`docs/design/v3/auth.md` §11; AUX-10 hero, aux-10-2026-10-18)

AUX-09 adds the §11.2 rows (2FA step, codes, passkeys) here. Purpose of the hero: "While the person signs in, the scene
quietly shows what SmartSched does, then holds still; it never competes with the form." Hosted Motion Agent fixes used:
0. The one reserved fix, "signin-hero-settle", was not spent because `TRANSITIONS_AGENT_LICENSE` was not set in the
AUX-10 session. It stays reserved for this hero only.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Sign-in hero enters (≥ 1024 px, `/login` only, after `requestIdleCallback` + 300 ms, once the first frame exists) | tint frame opacity 0 → 1 with a 4 px rise; the Lottie and its player load only then | `dur.slow` 240 ms, `ease.out` | poster PNG, static (no player request) | the frame is `--mat-thin` with no backdrop-filter; the in-app setting makes it solid |
| Hero plays | `hero-solver` frames 0 → 140 once (4.67 s at 30 fps, every inner tween ≤ 9 frames, `docs/lottie/build/audit.mjs`) | `HERO_SEGMENT` | none | same |
| Hero settles | pause and seek to frame 140 (the poster frame), then hold; never loops | — | — | — |
| Theme switch after the pass started | the new theme's poster appears (fade 240 ms); no replay | `dur.slow` | instant | same |
| Save-Data / `prefers-reduced-data` | poster PNG with the entry fade | `dur.slow` | static | same |
| < 1024 px, forced colours, 2FA step / setup | not rendered (no bundle request) | — | — | — |

Audit: `e2e/au-signin-hero.spec.ts` (ends ≤ 5 s and does not loop, no LoAF > 50 ms while typing, no bundle at 390,
poster under reduced motion, motion-audit case: no finite animation > 300 ms, ≤ 2 backdrop-filter surfaces,
pointer-events none, hidden in forced colours).

### 3.20 Welcome guide (`docs/design/v3/welcome-guide.md` §8; WG-09, wg-09-2026-10-18)

Purpose: "a guide for you appeared; these are the parts; look here now; done, and the server knows." This surface
uses a stricter ceiling: **≤ 240 ms per one-shot motion, delays included**. It uses tweens from
`components/welcome/motion.ts` (the shared springs settle in 270–285 ms, and nothing here is dragged). Waiver against
§1's spring-first rule: none of these elements is grabbed or re-targeted by a finger. Hosted Motion Agent fixes used: 0
(`TRANSITIONS_AGENT_LICENSE` was not set; the one approved fix for the sheet-open + hero moment is still unspent).

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Welcome sheet opens | ui/dialog `t-modal`: desktop scale .96 → 1 + opacity; phone 2.5 rem up | `--spring-glass-morph` / `--spring-sheet` curves over `--dur-slow` (240 ms); exit `--dur-fast` `--ease-in` | none (globals.css T-R2-07) | sheet opaque |
| Cards first reveal | y 8 → 0 + opacity, stagger 30 ms, max 5 | `dur.fast` + `staggerRule.step`, ≤ 240 ms total | none | same |
| Lottie hero | after 240 ms: player fades in, plays 0 → poster frame once (`quick-reserve` 0 → 86 for academician/staff/dept admin/approver, others reuse the set), holds; once per page load | `dur.slow` fade; clip ≤ 3 s, inner tweens ≤ 9 f | poster PNG, no request | same (no glass on the hero) |
| Phone card paging | x ±24 + opacity; dot pill `layoutId` | `dur.base` in, `dur.fast` out; dot `dur.base` | 100 ms fade, instant out | same |
| Tour step card in | floater opacity + card scale .98 → 1 (`@starting-style`) | `--dur-fast` `--ease-out` | 100 ms fade | opaque card |
| Spotlight ring re-target | one ring, `layout` with `layoutDependency={target}` (scroll follows 1:1, no trailing) | `dur.slow` `ease.inOut` | jumps | unchanged |
| Checklist tick | fill, then path draw | `dur.fast` + `dur.fast` (240 ms) | instant | same |
| Checklist progress | `scaleX`, no overshoot | `dur.slow` `ease.out` | instant | same |
| All done disc / "Yeni" badge | scale .8 / .6 → 1 + opacity, no bounce | `dur.base` `ease.out` | instant | same |
| Hint popover / strip | opacity + scale .98 / opacity + y −6 | `dur.fast` / `dur.base` | 100 ms fade / instant | opaque popover |

Audit: `components/welcome/motion.test.ts` (ceiling + source guard), `welcome-hero.test.tsx`, `welcome-motion.test.tsx`;
the welcome block for `e2e/motion-audit.spec.ts` is listed in the WG-09 report as an e2e item (sheet open, tour step,
checklist tick: ≤ 3 dropped frames, no finite animation > 300 ms except the Lottie, reduced motion = end state, reduced
transparency = opaque).

### 3.21 Helper ("Yardımcı": sheet and Göster; `docs/design/v3/helper.md` §7; HX-11, shell-int-2026-10-18)

Purpose: "a helper appeared beside your page and goes back the same way; the control you asked about is here." Built in
`components/helper/helper-sheet.tsx` (motion), `components/helper/helper.css` (CSS keyframes) and the WG-05
`SpotlightRing` reused by `components/helper/show-me.tsx`. transitions.dev: the free recipes panel-reveal,
shimmer-text, skeleton-reveal and success-check were used as timing references only and re-implemented on our tokens
(nothing pasted; `components/ui/SOURCES.md` row). Hosted Motion Agent fixes used: 0.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Sheet opens, desktop (non-modal, no scrim) | the sheet itself x 24 → 0 + opacity; no blur in the motion; composer focused on frame 1 | `springs.sheet` (settles ≈ 269 ms) | 100 ms opacity (`tween.reduced`) | `--mat-thick-solid`, no backdrop-filter |
| Sheet closes, desktop | opacity + x 24 | `dur.fast` 120 ms, `ease.in` (`helperSheetExit`) | instant (HX-19) | same |
| Sheet opens, phone (full-screen dialog) | y 100 % → 0 | `springs.sheet` (pattern 4, settles ≈ 270 ms) | 100 ms opacity | opaque |
| Sheet closes, phone, ✕ / Esc / a tap on the handle (HX-19) | y → 100 % | `dur.base` 180 ms, `ease.in` (≤ 200 ms, faster than the enter) | instant, no travel | opaque |
| Drag on the handle, phone (HX-19) | the sheet follows the finger 1:1 down (no spring lag, upward clamped at 0); `will-change: transform` only during the gesture; the pill darkens (`data-dragging`) | motion value = the sheet's `y` (`sheet-drag.ts`) | 1:1 kept (direct manipulation, §5 "Drag") | opaque |
| Release past 30 % of the height or a flick > 0.5 px/ms (HX-19) | continues down y → 100 %, then the focus returns to the opener | `dur.fast` 120 ms, `ease.out` (carries the flick); rule `shouldDismissSheet` (ui/sheet, same as every bottom sheet) | instant close | opaque |
| Release short of it, or a pointer cancel (HX-19) | springs back to y 0 from the release point with the release velocity | `springs.sheet` | back on the same frame | opaque |
| Thinking ("Düşünüyor…") | label shimmer, the only loop; stops with the first token | 1.6 s linear loop (`helper-shimmer`) | static label | static label (forced colours: CanvasText) |
| Card appears | opacity + y 6 → 0, once; rows not staggered | `--dur-base` 180 ms, `--ease-out` (`helper-enter`) | none | opaque card |
| Card done | 20 px check disc scale .8 → 1 | `--dur-base`, `--spring-bouncy-subtle` (`helper-check`) | static check | same |
| "Göster" ring | WG-05 ring re-targets to `[data-tour=…]` (one element, `layout`), step card docked on phones; page scrolls the target to the centre | `dur.slow` `ease.inOut` (as §3.20) | ring jumps; `scrollIntoView` `behavior: "auto"` | opaque step card |
| Status chip word | cross-fade | `dur.base` | instant | — |

HX-19 handle (phones only): a 36 × 4 px pill in a 96 × 44 px `<button>` centred at the top (a 24 px row; the target
reaches into the header's empty middle and the header's controls sit above it). It is named "Kapat (aşağı
sürükleyin)" / "Close (drag down)", it is not a Tab stop (`tabindex=-1`: ✕ stays the first stop, Esc still closes), and
activating it (a tap, or a screen-reader double-tap) closes like ✕; the click that trails a drag is ignored.
`touch-action: none` on the handle only, so the log keeps its own scrolling. Exits are chosen per close through
AnimatePresence `custom` (`helperSheetExit(kind)`), so a drag close never replays the slower ✕ exit. Hosted
transitions.dev fixes used: 0 (none approved); no new animation library (motion v14 `useMotionValue` + `animate`).

No motion: typing, palette filtering and group reorders, the "Yardımcıya sor" rows in the user menu and "Daha", the
page-context chip, memory deletes. Blur budget with the sheet open: shell bar + sheet ≤ 3 surfaces.

Audit: `e2e/motion-audit.spec.ts` "motion audit: helper" (sheet open ⌘J, close Esc, palette › Nerede? › Shift+Enter →
ring: no finite animation > 300 ms, ≤ 3 dropped frames per interaction under MOTION_STRICT, ≤ 3 backdrop-filter
surfaces; reduced motion: no transform animation and the sheet at its end transform). HX-19 adds "motion audit: helper
drag on phones (HX-19)" at 390×844 touch (CDP touch events), with reduced motion off and on: drag past 30 % → detached
≤ 260 ms after release (120 ms exit + the removal frame; ≤ 80 ms reduced) and focus on the opener; a 120 px slow drag
→ stays and returns to an identity transform (on the next frame when reduced); its trailing click does not close; a
90 px / 50 ms flick closes; Esc exit ≤ 260 ms; the handle is ≥ 44 × 44, named, `tabindex=-1`. Queued for the e2e lane
(resource rule 2026-10-18).

### 3.22 Helper file router (`docs/design/v3/helper-file-router.md` §9; HB-23c, hb23c-2026-10-18)

Purpose: "you can drop it here; here is what it is and what you can do; your file is already on the page." Built in
`components/helper/file-drop.tsx` (sheet drop target, 📎), `components/helper/page-file-target.tsx` (page edge target),
`components/helper/cards/file.tsx` (card, disclosure, chooser) and `components/helper/handed-file-row.tsx` (target
pages). Only transform and opacity animate; one focal motion at a time; no blur (the edge target and the card are fills).

| Moment | Purpose ("motion tells the user…") | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| OS file dragged over the sheet log / the page / a zone | "you can drop it here" | **instant** 2 px inset `--tint` outline + `--tint-soft` fill + one label (§3.8: an OS file is not our element, no lift, no magnet); page: outline on the viewport + a 36 px solid pill at the top centre | — | same | outline only, opaque fill; forced colours `Highlight` |
| Drag leaves / Esc / window blur | "cancelled" | instant removal | — | same | same |
| File chip enters the log (user bubble) | "your file arrived" | opacity + y 6 → 0 once (the log entry's `helper-enter`) | `--dur-base`, `--ease-out` | none | — |
| Reading > 400 ms | "still working" | shimmer on "Dosya okunuyor…" only (`helper-shimmer`), stops with the result; before 400 ms a static label | 1.6 s loop (ongoing work) | static label | `CanvasText` |
| Card appears (detected / unknown / needs_planner / chooser / refused) | "here is what it is and what you can do" | the card's opacity + y 6 → 0; rows do not stagger; focus moves to the card title | `springs.smooth` (settles ≈ 284 ms) | 100 ms opacity (`tween.reduced`) | opaque `--fill-3` |
| "Bu dosya nedir?" opens | "more detail, same place" | the text fades in after 60 ms in place; the chevron turns | `tween.fadeIn` + 60 ms delay; chevron `--dur-fast` | instant | — |
| Chooser pick → new card | "this is your choice now" | the new card replays the card enter (keyed by its sequence); the old card is replaced in place | `springs.smooth` | 100 ms opacity | — |
| Primary press → hand-over | "going to the right page" | button press scale .97 (Button's own); phone: the sheet exits down (§3.21 exit) as the route changes | button `--dur-fast`; sheet `dur.base` + `ease.in` | no scale; instant exit | opaque |
| Handed-over file row on the target page | "your file is already here" | one `--tint-soft` highlight that fades to `--fill-3` after 2 s | `--dur-base` colour transition | highlight static 2 s, then removed | outline |
| Refused / error | "it didn't work, here is why" | the card enter; **no shake** | `springs.smooth` | 100 ms opacity | — |
| Expired | — | no motion (text swap) | — | — | — |

No motion: the certainty word, the warnings list, the edge target (on/off only), the chooser rows (no stagger), typing.
Blur budget: shell bar + helper sheet = 2 surfaces; nothing new blurs. Known gap: the spec's `layoutId` move of the
picked row's tint into the new card header is not built (the new card replays the plain enter); the e2e motion audit
can confirm that is enough. Audit (queued for the e2e lane): add "drop → card", "chooser pick" and "hand-over" to
`e2e/motion-audit.spec.ts`: ≤ 3 dropped frames, nothing over 300 ms except the reading shimmer, reduced motion = end
state, reduced transparency opaque.

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
| Reservation panel (`/bookings`) | free-cell hover sweep, drag span (3 cell changes), book sheet open, next day ×2, lens switch | sheet visible ≤ 100 ms after the click. Worst LoAF ≤ 100 ms (CI). Measured 2026-10-15: 344–653 ms, audit T3 |
| Shell bell, find-a-room, approvals, audit | bell open, search → results, box switch, row expand ×3 | bell and results: worst LoAF ≤ 100 ms |
| Intake (`/onboarding/[jobId]`) | 3-file read (SSE), step change, bulk accept 40 rows, commit | ≤ 1 shimmer running. No per-row animation in İnceleme |
| Moderation | tab switch, inspector swap, recreate preview opened in compare mode (12 FLIPs), `j` ×3 | compare-mode open: ≤ 12 animating elements, Layout events ≤ 2 per FLIP batch |
| Suggestions | accept → tray travel, dismiss → receipt, swipe on phone | — |
| Program wizard | step change ×3, paste 50 rows, preview ticker | paste: no animation, LoAF ≤ 100 ms |

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

## 10. Phase 19 additions (2026-10-15)

### 10.1 Reconciliation with the Phase 19 UX specs

The UX specs (`phase19-*.md` §11/§12) name moments and suggest patterns. This file decides. Where the decision differs:

| Spec moment | Suggested | Decided here (§3.8–§3.11) | Why |
|---|---|---|---|
| `intake.drop-hover` | §7 lift / magnetic | instant tint + outline, no lift | the dragged object is an OS file, not our element. Lift and magnet belong to in-app drags (`magnetic-drop.tsx`) |
| `intake.file-phase-progress` | upload `scaleX` | `scaleX` per SSE event + **one** shimmer per job on the active phase label | the council reads files one by one, so one focal indicator. The audit found one spinner per agent per file (audit #10) |
| `suggestion.dismiss` / `snooze` | §6 pop out + §5 undo toast | in-place receipt with Geri al (suggestions §5.2), pop-out only after 8 s and never while focused | the spec's own §5.2 keeps the receipt on the card. A toast would duplicate it |
| `memory.reset-done` / `undo` | §5 toast | toast 10 s + one region crossfade for the cleared lists | destructive: longer undo window. Many cards: one region, not per card |
| `moderation.recreate-start` | §19 island morph | sheet button → top-bar island via `layoutId="run-island"` | same island as Studio Generate (§4) |
| Recreate preview | table (moderation §5.4) | table stays primary. "Takvimde göster" adds the calendar compare mode with ≤ 12 FLIPs | user request: old → new continuity, never 1,300 cells |
| `wizard.error-summary` | §9 shake on submit | shake the **first invalid field** only, focus it | a shaking step body is a large element with no target. Shake is for the input that was rejected |

### 10.2 References (Mobbin, researched 2026-10-15)

| Flow / screen | What we took (motion and state) | Used in |
|---|---|---|
| [AWS S3 · Upload status](https://mobbin.com/screens/d0b2a1fa-99a9-4c29-ba83-f77a3f850d40) | aggregate bar on top, per-file status as text ("In progress (58%)", "Succeeded", "Pending"), no per-row animation | §3.8 file progress |
| [Whop · Bulk upload creatives](https://mobbin.com/screens/80459def-95d4-4909-9e7b-8d47d7807147) | per-file bars. A finished row turns to a tinted "Uploaded" state with a ✓, while others keep updating | §3.8 `intake.file-done` |
| [PandaDoc · Imported 0 of 4 files](https://mobbin.com/screens/6e7783c1-2ce2-4ba2-832d-bab89ec45f67) | "Imported n of N" headline with one spinner per row. We keep the headline and drop the per-row spinners (one focal motion) | §3.8 |
| [ClickUp · Importing a file (13 screens)](https://mobbin.com/flows/d179f1f7-daf7-41e5-a750-df62db769f60) | All / Valid / Invalid as filters over one table, with values mapped in place. Status is text, not motion | §3.8 review filters |
| [Notion · Importing a CSV file](https://mobbin.com/flows/b0cb149f-d742-4d9e-a22f-5dfe5d15b0b1) | static placeholder rows in the preview pane while mapping (no shimmer) | §3.8 loading, audit T7 |
| [Fibery · Importing a CSV](https://mobbin.com/flows/b74631cd-e3b7-4273-8803-0eebaff0d350) | completion as a corner toast ("Importing into Report completed") over the result table | §3.8 `intake.committed` |
| [Figma · Compare changes](https://mobbin.com/screens/ebb90bf9-735a-4f5f-968a-8152ff58dde8) | Added / Removed tags per layer + side-by-side with dashed outlines for removed objects | §3.9 ghosts and text tags |
| [Neon · Compare schemas](https://mobbin.com/screens/9cb22cfd-3f04-4161-94b9-729266bc97b0) | static before/after colouring, with "Proceed to restore" as the only action | §3.9 preview diff (static on arrival) |
| [Cursor · Diff review](https://mobbin.com/screens/fa7df34d-7288-4c26-a0e9-95a84921e34e) | file list with change counts, step through changes. No animated diff | §3.9 `j/k` stepping |
| [AirOps · Recommended prompts](https://mobbin.com/screens/ae0f151a-f195-43ba-9f2f-9c3ff74bfa10) | per-card ✕ / ✓ with "Decline all / Accept all". We keep per-card actions and drop bulk accept-all (suggestions spec) | §3.10 |
| [Rox · Recommended actions](https://mobbin.com/screens/62b4d10c-498e-49eb-bf78-3b944290f407) | acted-on items stay in place, greyed, instead of disappearing (receipt idea) | §3.10 receipt |
| [Shop · Not interested](https://mobbin.com/screens/a948e8d8-141d-4aa4-995b-9379833b68ec) | dismissal asks for a reason in a small panel | §3.10 dismiss reason chips |
| [Asana · Deleted with Undo toast](https://mobbin.com/screens/36cb9092-004d-4cfa-abc7-930e4a7ff931) | destructive result toast with Undo next to the action that caused it | §3.10 `memory.reset-done` |
| [Origin · Budget reset](https://mobbin.com/screens/51895887-f33f-42f7-a85f-1c6c6721626f) | reset confirmation as a success toast over the settings sheet | §3.10 |
| [Upwork · Creating a project (14 screens)](https://mobbin.com/flows/0c0b3422-ee47-4889-b0f0-93fff6d38aa3) | horizontal stepper where completed steps turn to ✓ and the line fills | §3.11 rail ✓ / mobile segment bar |
| [HoneyBook · Setup](https://mobbin.com/flows/83c002e5-5144-48f4-ab92-558fa8ec8cd5) | "6/7 completed" bar with ✓ per step, non-linear order | §3.11 |
| [Amie · Creating a workspace](https://mobbin.com/flows/313ec1b8-3d78-43fb-86ba-b57a2d8ef672) | one question per step, Back / Continue, choice cards with instant selection outline | §3.11 choice cards |

All are references for behaviour only. No assets or code were taken (skill §7).

### 10.3 Audit hook

The 2026-10-15 audit (`docs/review/2026-10-15-motion-audit.md`) found that reduced-transparency materials paint as `background-image` gradients, so `backgroundColor` reads transparent. RT assertions must check `backdropFilter === "none"` and an opaque `rgb(` layer in `backgroundImage` (audit T13). The template in the skill's `references/audit.md` should be updated by the skill owner.
