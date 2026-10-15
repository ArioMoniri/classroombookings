# Motion audit: surfaces changed since 2026-10-08

Ledger: `motion-audit-phase19-2026-10-15` · Owner: motion_designer skill (design-pro) · Date: 2026-10-15
Method: `.claude/skills/motion_designer` §1 workflow, §8 checklist and `references/audit.md`. Specs: `docs/design/v2/motion.md` (§3.7 now holds the target rows for these surfaces).
Code read at `bdb6742` plus the uncommitted wave-1 work in the tree at 15:00 (find-room, features admin, approvals, i18n). The universal onboarding was read from `origin/claude/smartsched-universal` (`419a6aa`).

## BLUF

- **35 findings: 0 blocker, 12 major, 23 minor.** A further 14 moments pass the checklist (marked "ok" in the table).
- **Nothing breaks the motion ceiling and nothing animates in reduced motion.** No finite animation runs over 300 ms on any measured interaction. Under OS reduced motion and under the in-app "Reduce motion" switch, sheets and popovers reach their end state on the next frame with no transform animation. Under reduced transparency, sheets and popovers are opaque (`rgb(247,248,250)` / `rgb(255,255,255)`, `backdrop-filter: none`).
- **The problems are not too much motion. They are missing feedback and main-thread stalls.**
  1. **Busy state is spinner-only.** 56 `Loader2 animate-spin` buttons in 39 files keep their label, and none sets `aria-busy`. Under reduced motion the spinner freezes into a static glyph, so the only remaining signal is `disabled`.
  2. **The grid gives no signal while it refetches.** Day/week navigation keeps the old grid at full opacity (`keepPreviousData`), and the date label still shows the old day until data arrives.
  3. **Opening a sheet or popover blocks the main thread.** The book sheet, the bell popover, the day change and find-room results each produce 100–650 ms long animation frames on a quiet machine (baseline 0 dropped frames). That fails the CI gate (≤ 3 dropped frames per interaction, no LoAF > 100 ms). It isn't the animation itself: the CSS transitions are compositor-only. The click and render work delays the first frame.
  4. **Focus is lost after confirm-and-remove** (audit Undo, Withdraw request, delete feature, approvals decide, onboarding accept).
  5. **The Studio review tray animates `height`** and ignores the in-app reduced-motion switch (`useReducedMotion` from motion/react). Accepting a proposal still lacks the specified travel into the rule list.
- **Top fixes (in order):** T1 busy-state primitive · T2 stale-while-refetch signal · T3 main-thread budget for sheet/popover/grid swap · T4 focus after removal · T5 review-tray `layout` + `useReduce` + `layoutId` travel · T6 onboarding progress live region and one focal indicator.
- Measured on a real stack (FastAPI on SQLite with the Bahar 2026 workbooks, production `next build`, Chromium 141 headless shell, 1× CPU, 1440 × 900). Backend port 18850, frontend port 18851, workdir `/tmp/motion-audit-31164`. Device check (headed GPU, 4× CPU): **not run**, because no GPU is available in this container.

## 1. Measurements (real backend, production bundle, headless, 1× CPU)

Probe: the rAF + Long Animation Frames probe and Layout-event trace from `references/audit.md` §2, driven by a Playwright-library script (`page.evaluate` + `browser.startTracing`). Each figure is the range over two clean runs. The no-op baseline was 0 dropped frames in both runs, so the deltas belong to the UI and not to the machine. An earlier noisy run (baseline 3.3 per interaction) was discarded.

| Interaction | dropped / interaction | LoAF > 50 ms | worst LoAF | Layout events | over 300 ms | reduced motion | reduced transparency |
|---|---|---|---|---|---|---|---|
| baseline: no-op click ×4 | 0 | 0 | 0 | 1 | none | — | — |
| bookings: hover sweep, 24 free cells | 0.3–0.5 | 1–5 | 74–82 ms | 24–25 | none | n/a (no motion) | n/a |
| bookings: drag a span, pointer moves only (3 cell changes) | 7–8 (≈ 2.5 per cell) | 1–3 | 79–130 ms | 5 | none | n/a | n/a |
| bookings: drag-span release → book sheet opens | **96–138** | 12–16 | **396–449 ms** | 12–14 | none | end state ✓ | opaque ✓ |
| bookings: book sheet open + Esc | **36–48** | 9–12 | **344–653 ms** | 12 | none | end state ✓ (`translate:none`, opacity 1) | opaque ✓ |
| bookings: lens Grid → Free → Grid | 9.5–13 | 10–11 | 209–456 ms (one 412 ms script with 196 ms forced layout) | 10–11 | none | — | — |
| bookings: next day ×2 (grid refetch) | **24–52** | 11–13 | **187–584 ms** | 7 | none | — | — |
| shell: bell popover open + Esc | **14.5–33** | 4–5 | **151–458 ms** | 3–5 | none | end state ✓ (in-app switch) | opaque ✓ |
| bookings: calendar-sync sheet open + Esc | 3.5–5 | 9–12 | 216–429 ms | 7 | none | — | — |
| find-room: search, results arrive | **34–74** | 9–14 | **116–288 ms** | 5–7 | none | — | — |
| approvals: box Open → Decided → Open | 8 | 3–4 | 100–123 ms | 8 | none | — | — |
| audit: expand + collapse 3 rows | 2.3–4.3 | 18–24 | 213–336 ms | 8–9 | none | — | — |
| idle /bookings, /my-bookings | — | — | — | — | no infinite animations running | — | — |

Reading the numbers:
- The CSS sheet transition is `translate` + `opacity` (compositor). The long frames sit in `#document.onclick` (97–181 ms of script, 15–28 ms forced layout), `pointerup` (146 ms) and the React commit that mounts the sheet body. So the sheet's spring starts 300–600 ms late. That is a latency problem the motion spec forbids ("the visual response starts in the same frame as the input", skill §6).
- Day navigation and find-room results are React re-renders of the 215-cell grid and the result list. No motion is involved. They are listed because they break the frame budget on the surfaces this audit covers.
- Free-cell hover and span drag stay within budget (≈ 2.5 dropped frames per cell change while dragging, at the edge of the ≤ 3 gate). Cells are `memo`, the crosshair is one injected `<style>`, and nothing animates. That is the intended design.
- Reduced transparency material is a `background-image` gradient, so `backgroundColor` reads `rgba(0,0,0,0)`. Assertions must read `backgroundImage` (see T13).

## 2. Findings

Severity: **major** = fails a §8 checklist line (non-motion signal, a11y focus, layout-property animation, reduced-motion path, frame gate). **minor** = token or pattern drift, or a missing reinforcement. **ok** = checked and passing.

| # | Surface | Moment | Current | Problem | Fix (pattern + token) | Severity |
|---|---|---|---|---|---|---|
| 1 | all new screens (39 files) | busy buttons (save, search, reserve, approve, connect, load more, start, commit) | `Loader2 animate-spin` is prepended. The label is unchanged. `disabled` is set, with no `aria-busy`. calendar-sync Connect/Disconnect shows no indicator at all | Under reduced motion the spinner freezes (global 0.01 ms rule) into a static glyph that reads as an icon. Screen readers hear nothing. No text signal ("did it work" has no answer while waiting) | Shared busy state: `Button loading` prop (or `<BusyLabel>`) that swaps the label to the gerund ("Aranıyor…", "Kaydediliyor…"), sets `aria-busy`, and renders the spinner `motion-reduce:hidden` plus the static "…" glyph (motion.md §5 "Loops"). Spinner appears only after 150 ms. Kit `Loading` already does this right | major |
| 2 | reservation panel `/bookings` | day / week change (‹ › Today, date picker) | `keepPreviousData`: the old grid stays at full opacity and the date picker shows the old date until the response. Only `aria-busy` on the wrapper | No feedback in the input frame. A slow response looks like an ignored click | Target date label from the URL param immediately. After 120 ms of pending, `data-stale` on the grid wrapper → `opacity: .6` via `transition-opacity duration-(--dur-fast)` (solid grid, no glass inside, so the backdrop-root rule is safe). No travel: day stepping is a frequent action | major |
| 3 | reservation panel | drag-span release / free-cell click → book sheet | the sheet springs in (`--spring-sheet`, 270 ms) | Opening costs a 344–653 ms long frame (click handler + sheet body mount). The spring starts late and ≥ 36 frames drop | Open the shell in the input frame: mount `SheetContent` with header + skeleton-free static rows. Defer the preview query and recurring-preview table with `startTransition` / `useDeferredValue`. Gate: LoAF ≤ 100 ms, ≤ 3 dropped frames | major |
| 4 | reservation panel | grid swap when the new day arrives | 215-cell `BookingGrid` re-renders | 24–52 dropped frames per change, LoAF up to 584 ms | Render the incoming grid in a transition (`useDeferredValue(grid)`). Keep cells `memo` with stable props (`selected`/`spanKeys` per cell, not whole sets). No motion added | major |
| 5 | shell | notification bell popover open | `glass-thick` popover, `t-panel-slide` | 14.5–33 dropped frames, LoAF up to 458 ms: list + recent runs + `StatusBadge` render on open | Keep the popover body mounted after first open (Base UI `keepMounted`) or prefetch on hover/focus of the bell. Render the runs list lazily below the fold | major |
| 6 | find-a-room `/find-room` | search → results | results replace in place (correct) | 34–74 dropped frames, LoAF up to 288 ms on arrival. During a re-search the old results stay fully opaque with no stale signal | Same as #2 (stale dim after 120 ms + `aria-busy`) and #4 (deferred render). Results still arrive with no animation | major |
| 7 | audit viewer, my requests, features admin, approvals | confirm → item changes or disappears (Undo, Withdraw, Delete feature, Approve/Reject → next request) | `ConfirmDialog` returns focus to its trigger, but the trigger (Undo / Withdraw / Delete) is gone after the refetch. Approvals: `RequestDetail key={id}` remounts, so the focused Approve button unmounts | Focus falls to `<body>`. The keyboard user loses their place (§8 "focus never lost") | After success, move focus explicitly at the start of the transition: audit → the row's toggle (it now reads "Geri alındı"); withdraw → the request row button; delete → the next row or the list heading; approvals → the new request's title (`tabIndex=-1`). Live region: the toast text | major |
| 8 | Studio review tray | accept / reject a proposal | exit `{opacity 0, height 0}` over a raw 0.18 s. Reduced: raw 0.1 s. Uses `useReducedMotion` from motion/react | Animates `height` (a layout property, §4). Ignores the in-app "Reduce motion" switch (`MotionConfig "always"` drops transform/layout, not height), so the height collapse still runs with the switch on. Raw numbers | `AnimatePresence mode="popLayout"` + `layout` on items. Exit `{opacity: 0, scale: .98}` with `tween.fadeOut`. Siblings reflow with `springs.smooth`. `useReduce()` from `@/lib/motion` → exit `tween.reduced`, no layout | major |
| 9 | Studio review tray → rule list | accept proposal | card fades out in the tray. The rule appears in its group with no link | Spec §3.4 "the card travels from the tray into its rule group (`layoutId={proposal.id}`)" is not built. "Where did it go" is unanswered | One `LayoutGroup` around tray + rules list. `layoutId={proposal.id}` on the tray card and the new rule card, `springs.smooth`, at most 12 travelling at once ("Accept all" above 12 → no travel, count toast). Reduced: disappears/appears with a 100 ms fade | major |
| 10 | universal onboarding (council progress) | per-file, per-agent status while the council runs | one `Loader2 animate-spin` per RUNNING agent per file. Raw enum text (`RUNNING`). No live region | Several loops at once (no single focal motion). Nothing announced for a multi-minute job. Raw status words | Per file, one phase line ("okuma ✓ · yapı ✓ · çıkarım %62"). Only the active phase label gets the §17 thinking shimmer (loop 1.6 s, static under reduced motion). Others show static glyphs. Polite live region per file completion and job end (phase19-intake.md §10). See motion.md §3.8 | major |
| 11 | universal onboarding (review panel) | Accept / Reject an item | every button gets `disabled={busy}` during the request | A focused button that becomes disabled is blurred by Chromium, so focus goes to `<body>` after every decision | `aria-disabled` + ignore clicks while busy (never `disabled` on the focused control). On success, focus the next undecided item (as `review-tray.tsx` `focusNext` does). Live region "12 satır onaylandı" | major |
| 12 | Studio review tray | "Accept all ready" with many proposals (file upload can yield hundreds) | `layout` on every `motion.li`, no size cap | Lists over 40 items must not animate insert/remove (§4) | `const animate = pending.length <= 40 && !reduce`. Above that, render plain `li` and announce the count | major |
| 13 | reservation panel | grid / date loading | `Skeleton` = `animate-pulse` (2 s infinite) on a 420 px block and on the date pill. Same in `AffectedBadge` (rule card) | Pulsing placeholder on a working surface (motion.md anti-AI rule, §3.3 "static placeholder rows (no shimmer)") | Static placeholder rows. On data arrival the placeholder fades out on top (§12 skeleton-on-top, `tween.fadeOut` 120 ms). Make the `Skeleton` primitive static by default with an opt-in `pulse` | minor |
| 14 | reservation panel | multi-select tray (floating-bottom glass toolbar) | mounts and unmounts instantly | Spec §3.3/§3.4: a selection bar enters with 8 px rise + fade and leaves faster | `AnimatePresence`. Enter `{y: 8 → 0, opacity}` `springs.smooth`, exit `tween.fadeOut`. Animate the glass element itself (no fading wrapper). Reduced: 100 ms fade | minor |
| 15 | Studio classes step | bulk bar | `transition={{ duration: 0.18 }}` (raw tween), no exit, `useReducedMotion` | raw number, not a spring, exit missing, in-app switch ignored | As #14 with `springs.smooth` / `tween.fadeOut` / `useReduce()` | minor |
| 16 | reservation panel | room details → "Reserve" (and slot info → "Other rooms") | the room sheet closes (120 ms) while the book sheet opens (270 ms) from the same edge | Two glass sheets animate at once: two focal motions and two live backdrop surfaces | Keep one `Sheet` and swap its content (crossfade `springs.smooth` opacity only, as in the inspector swap §3.2) with a "‹ Oda" back affordance. Focus moves to the new title at the start | minor |
| 17 | my bookings + grid multi-select | bulk cancel done | rows vanish on refetch. Toast with no Undo | Bulk action spec: count toast with Undo. Rows disappear with no "what changed" cue | ≤ 40 visible rows: §6 pop-out (`springs.smooth` reflow, exit `tween.fadeOut`). More: instant. Toast "3 rezervasyon iptal edildi · Geri al" via the P7 audit undo | minor |
| 18 | calendar-sync settings | copy feed link (https / webcal) | toast only, at the screen edge | "Did it work" is answered far from the button | Copy icon morphs to ✓ in place for 1.5 s (§10 check, `springs.bouncySubtle`, ≤ 32 px) + `aria-live` "Kopyalandı". Keep the toast | minor |
| 19 | reservation panel (Free slots lens), Studio scope weeks | press on slot chips / week chips | `active:scale-[0.97]` for every pointer. `duration-(--dur-fast)` with `ease-(--spring-snappy)` | The spring curve is sampled for 280 ms but compressed into 120 ms. The coarse-pointer scale is used on a fine pointer (§2 input modality) | `duration-(--spring-snappy-ms) ease-(--spring-snappy)`. `active:scale-[0.98]` and `pointer-coarse:active:scale-[0.97]` | minor |
| 20 | shell bell | unread badge bump | badge is keyed on `bump`, so the old badge exits (raw `duration: 0.1`) while the new one pops 0.6 → 1 | Two badges overlap for 100 ms. 40 % scale travel (spec: 1 → 1.08 → 1). Raw number | Keep one badge mounted. Key only the number text. On bump `animate(badge, { scale: [1.08, 1] }, springs.bouncySubtle)`. Exit `tween.fadeOut`. Allowed on poll arrival (deliberate exception, motion.md §3.7) | minor |
| 21 | shell bell | "N new notifications" announcement | the `role=status` text is set and never cleared | The same text twice in a row is not re-announced | Clear the message after 1 s, or append an invisible counter | minor |
| 22 | shell top bar | run island dot | `motion-safe:animate-ping` (infinite scale ×2) for the whole run, next to "%38" | A decorative loop on persistent chrome that duplicates a real status (anti-AI rule "typing dots when a real status exists") | Static dot. The progress text carries the state. If a loop is wanted, the §17 shimmer on the label, stopping with the run | minor |
| 23 | find-a-room (phone) | results after search | `scrollIntoView({block:"start"})` jumps | No spatial continuity on phones | `behavior: reduce ? "auto" : "smooth"` (as `term-rule-card.tsx` does) | minor |
| 24 | my requests | deep link `?request=` | instant `scrollIntoView` + a permanent `bg-tint-soft/40` | Highlight never clears. Jump without continuity | Smooth scroll (reduce-aware). Highlight fades out after 2 s with `transition-colors duration-(--dur-base)`. Focus the row button | minor |
| 25 | Studio rule card | "Saved ✓" | scale 0.8 → 1 on the default MotionConfig transition (`smooth`). `useReducedMotion` | Spec token is `bouncySubtle` (§3.4, pattern §10). In-app switch ignored | `transition={pick(reduce, springs.bouncySubtle)}` with `useReduce()` | minor |
| 26 | Studio rules step | sticky counter | `bg-background/95 backdrop-blur-sm` over the scrolling list | An extra live `backdrop-filter` surface outside the shell blur budget (`blur-budget.ts`), repainting on every scroll frame | Tint only: `bg-(--mat-thick-solid)` + hairline (hard edge §15) | minor |
| 27 | universal onboarding | overall progress bar | `Progress value` jumps per snapshot, no value text | A number the user watches has no text, and no continuity | Indicator as `scaleX` (origin left) with `springs.snappy` per SSE update (motion.md §3.4 upload stage) + "%38" text. Reduced: jump | minor |
| 28 | universal onboarding | drop → job workspace | drop card unmounts, progress mounts instantly | Abrupt region swap | Enter-only: the new region rises 6 px + fades (`springs.smooth`, §13 veil idea). The old one leaves instantly. Reduced: 100 ms fade | minor |
| 29 | universal onboarding | commit result | result card appears with `role=status` | No "did it work" reinforcement | Commit button → ✓ (§10 `bouncySubtle`). Result card enters with `springs.smooth`. Toast "Kaydedildi · Takvimi aç" | minor |
| 30 | universal onboarding | drop zone (`role=button`) | Enter/Space open the picker. Space does not `preventDefault` | Space also scrolls the page | Use a real `<button>` (phase19-intake.md §10) | minor |
| 31 | reservation panel | lens switch Grid ↔ Free slots | segmented thumb morphs (primitive). Content swaps instantly | Spec lens switch (§3.2) enters content with 8 px toward the lens direction. A 196 ms forced layout inside the commit (one run) | Enter-only `opacity` + `x: ±8` `springs.smooth`. Old leaves instantly. Find the layout read in `fitColumns` / grid measure and move it to a `ResizeObserver` | minor |
| 32 | all sheets on the new surfaces | sheet material | `glass-chrome` = `blur(40px) saturate(2)` | Over the 215-cell grid the radius exceeds the skill's ≤ 24 px budget for large blurred areas (owner: liquid-glass.md) | Raise with liquid-glass owner: chrome sheets `--mat-chrome-filter` ≤ 24 px, or the solid variant over working grids (as `blur-budget.ts` does for the shell) | minor |
| 33 | approvals inbox | decide → next request in the drawer | drawer content remounts instantly. The decided row vanishes from the list | Both answer "what changed" only through the toast | Drawer: content crossfade keyed by id (`springs.smooth`, opacity only). List ≤ 40 rows: §6 pop-out (exit `tween.fadeOut`). Focus as in #7 | minor |
| 34 | audit viewer / my requests | "Load more" | spinner in the button, label unchanged (#1). New rows append instantly | Append with no animation is correct (no stagger on pagination). Only the busy label is missing | Covered by T1 | minor |
| 35 | features admin (in progress) | adopt / template / save / delete | spinner-only busy, dialogs, toasts | Same as #1 and #7 | T1, T4 | minor |
| — | reservation panel | free cell hover "Boş → Rezerve et" | instant background + label swap | frequent action, no motion: correct | — | ok |
| — | reservation panel | span select (drag, Shift-click, Shift+arrow) | cells tint instantly, per-cell `aria-label` "n periods selected" | correct. ≈ 2.5 dropped frames per cell change | — | ok |
| — | reservation panel | crosshair (`grid_highlight`) | one injected `<style>`, paint only | correct | — | ok |
| — | reservation panel | reason hint | appears after 350 ms hover / 450 ms hold, no fade, `aria-hidden` (reason is in the cell's name) | correct (a 120 ms fade is optional) | — | ok |
| — | reservation panel | department lens, legend counts | instant, `aria-live` polite | correct | — | ok |
| — | all sheets / dialogs / popovers | open / close | `--spring-sheet` 270 ms / glass-morph CSS, exit 120 ms `--ease-in` | within ceiling; reduced motion end state ✓; RT opaque ✓ | — | ok |
| — | find-a-room, audit, my requests | `<details>` / row expand chevrons | `transition-transform duration-(--dur-fast)`, panel appears without height animation | correct (lists can exceed 40 rows) | — | ok |
| — | approvals | PENDING state | Hourglass glyph + word, no motion | correct: do not add a pulse | — | ok |
| — | approvals, my bookings | Open / Decided, Upcoming / Past tabs | segmented thumb, list swaps instantly | correct (filter = frequent) | — | ok |
| — | audit viewer | before → after diff | red strike-through → green, text-based | non-motion signal ✓ | — | ok |
| — | Studio term-rule card | "Show both" scroll | `behavior: reduce ? "auto" : "smooth"` | correct | — | ok |
| — | studio polish fixes (`bd0db48`, tree) | plural strings, unlock-vs-pin | no motion change | — | — | ok |
| — | global | `data-motion="reduced"` (Settings → Appearance) | CSS `transition-duration: 0.01ms`, `MotionConfig reducedMotion="always"` | verified on the real stack: sheet `translate:none`, no running animations | — | ok |
| — | global | over-ceiling scan | `document.getAnimations()` after every interaction | none over 300 ms | — | ok |

Counts: major 12 (#1–#12), minor 23 (#13–#35), ok 14.

## 3. Tickets for frontend-engineer

Each ticket lists files, the change, and acceptance checks. "Reduced-motion e2e" assertions go into `smartsched/frontend/e2e/motion-audit.spec.ts` (extend the existing spec. Use `page.emulateMedia({ reducedMotion: "reduce" })` and, for the in-app switch, write `localStorage["smartsched.appearance.<userId>"] = {"motion":"reduced"}` before navigation).

**T1 · Busy state that is not motion-only** (#1, #34, #35; major)
- Files: `src/components/ui/button.tsx` (add `loading?: boolean | string`), then replace `{x.isPending ? <Loader2 className="animate-spin" …/> : …}` in `components/bookings/{book-sheet,multi-book-dialog,booking-detail-sheet,calendar-sync}.tsx`, `components/findroom/find-room-view.tsx`, `components/approvals/approvals-view.tsx`, `components/audit/audit-view.tsx`, `components/admin/*.tsx` (incl. `features-admin.tsx`), `components/studio/{template-gallery,generate-step,rule-card}.tsx`, `components/settings/settings-view.tsx`, and the onboarding panels after the merge.
- Behaviour: label swaps to a gerund after 150 ms. `aria-busy="true"`. Spinner has `motion-reduce:hidden` and is followed by a static "…". The button keeps focus (use `aria-disabled`, never `disabled` while focused).
- Acceptance: unit test: `render(<Button loading="Aranıyor…">Ara</Button>)` → accessible name "Aranıyor…", `aria-busy="true"`. e2e (reduced motion): click `fr-search` and, while pending, `expect(button).toHaveAttribute("aria-busy","true")`, `expect(button).toHaveAccessibleName(/Aranıyor/)`, and `document.getAnimations().filter(a => a.effect.target.closest('[aria-busy=true]') && a.effect.getComputedTiming().iterations === Infinity).length === 0`. `grep -rn 'Loader2 className="[^"]*animate-spin' src | grep -v motion-reduce` returns 0 lines outside `ui/button.tsx` and `admin/kit.tsx`.

**T2 · Stale-while-refetch signal** (#2, #6; major)
- Files: `components/bookings/bookings-view.tsx` (grid wrapper at the `aria-busy={grid.isFetching}` div, date picker value from `params.date`), `components/findroom/find-room-view.tsx` (results section).
- Behaviour: target date shown in the input frame. `data-stale` after 120 ms of `isPlaceholderData || busy` → `opacity-60 transition-opacity duration-(--dur-fast)`. Cleared on data. No travel.
- Acceptance: e2e (normal): click `nav-next`; within one rAF the date button text equals the next day. While the request is held (`page.route` delay 800 ms), `[data-stale]` is present after 200 ms and `aria-busy="true"`. e2e (reduced motion): `getComputedStyle(wrapper).transitionDuration` ≤ `0.1s` (the global rule gives `1e-05s`). No element under the grid has a transform animation.

**T3 · Main-thread budget for sheet / popover / grid swap** (#3, #4, #5, #6 render part, #31 forced layout; major)
- Files: `components/bookings/book-sheet.tsx` (defer the preview query and `recurring-preview-table` with `startTransition` after the open frame), `components/bookings/bookings-view.tsx` + `booking-grid.tsx` (`useDeferredValue(grid)`, per-cell primitive props, find the forced layout in `fitColumns`), `components/notifications/notification-bell.tsx` (`keepMounted` or prefetch on pointerenter/focus; recent runs below the fold), `components/findroom/find-room-view.tsx` (deferred result render).
- Acceptance: extend `e2e/motion-audit.spec.ts` with the five interactions from §1 using the existing `startFrameProbe` / `stopFrameProbe`. With `MOTION_STRICT=1` on the device check (headed GPU, `MOTION_CPU=4`): ≤ 3 dropped frames per interaction and worst LoAF ≤ 150 ms. In CI (headless, 1×): worst LoAF ≤ 100 ms for book-sheet open and bell open, and log the rest. Sheet visible (`[data-slot=sheet-content][data-open]`) within 100 ms of the click.

**T4 · Focus after confirm-and-remove** (#7, #33; major)
- Files: `components/audit/audit-view.tsx` (`UndoDialog` onSuccess → focus the row toggle), `components/approvals/my-requests.tsx` (withdraw → row button), `components/admin/features-admin.tsx` (delete → next row or heading), `components/approvals/approvals-view.tsx` (on `onDone`/`onSwitch`, focus the new `SheetTitle` with `tabIndex={-1}`; content crossfade keyed by id with `springs.smooth`, opacity only; list removal §6 when ≤ 40 rows).
- Acceptance: e2e: undo an audit event via keyboard (Tab to Undo, Enter, Enter), then `expect(page.locator(':focus')).toHaveAttribute('aria-controls', /^audit-/)`. Approvals: press `a` and, after the toast, `document.activeElement` is inside `[data-testid=approval-drawer]` and is not `body`. Reduced motion: after decide, `document.getAnimations().length === 0` within two frames.

**T5 · Review tray: layout, reduced motion, travel** (#8, #9, #12, #15, #25; major)
- Files: `components/studio/review-tray.tsx`, `rules-step.tsx` (wrap tray + rule list in `LayoutGroup`, `layoutId={proposal.id}` on the accepted rule card), `rule-card.tsx`, `classes-step.tsx`, and also `run-cards.tsx`, `check-step.tsx` (same `useReducedMotion` import). Add an ESLint `no-restricted-imports` rule for `useReducedMotion` from `motion/react` outside `components/ui/**`.
- Acceptance: unit: no `height` key in any `exit`/`animate` object in `components/studio` (grep test). e2e (normal): accept one proposal and sample the card's `getBoundingClientRect()` over 3 frames, which must move toward the rule list. e2e (in-app reduced, via localStorage): accept, and within two frames `document.getAnimations().filter(a => /height|transform|translate|scale/.test(JSON.stringify(a.effect.getKeyframes()))).length === 0`. More than 40 pending: no `motion.li` with `layout`.

**T6 · Onboarding progress and review (after the universal merge)** (#10, #11, #27, #28, #29, #30; major)
- Files: `components/onboarding/{council-progress,review-panel,commit-panel,file-drop,onboarding-flow}.tsx`. Target layout: phase19-intake.md §5.3 and motion.md §3.8.
- Acceptance: unit: one shimmer at most per file row (`[data-shimmer]` count ≤ number of RUNNING files). A polite live region receives "<file>: çıkarım tamamlandı, 64 satır" once per file, not per SSE snapshot (test with 20 snapshots). Accepting an item keeps `document.activeElement !== document.body` and moves to the next `Bekliyor` item. e2e (reduced motion): no infinite animations (`iterations === Infinity`) on `/onboarding/<job>` while RUNNING. The progress indicator has no transform animation.

**T7 · Static placeholders** (#13; minor)
- Files: `components/ui/skeleton.tsx` (static by default, opt-in `pulse`), `components/bookings/bookings-view.tsx`, `components/studio/rule-card.tsx` (`AffectedBadge`).
- Acceptance: e2e: while `/bookings` loads (route delay), `document.getAnimations().filter(a => a.animationName === 'pulse').length === 0`.

**T8 · Selection bars enter/exit** (#14, #15; minor)
- Files: `components/bookings/bookings-view.tsx` (multi tray), `components/studio/classes-step.tsx`.
- Acceptance: e2e (normal): after the first selection, the tray's animations are ≤ 300 ms and use `transform`/`opacity` only. e2e (reduced): the tray's `transform` is `none` on the next frame.

**T9 · One sheet for room details ↔ reserve** (#16; minor)
- Files: `components/bookings/bookings-view.tsx`, `room-info-sheet.tsx`, `book-sheet.tsx`.
- Acceptance: e2e: open room details → Reserve; at most one `[data-slot=sheet-content]` is in the DOM at any sampled frame, and focus is on the book sheet title.

**T10 · Bulk cancel feedback** (#17; minor; Undo depends on P7 audit undo for `booking.cancel`)
- Files: `components/bookings/my-bookings-view.tsx`, `cancel-many-dialog.tsx`.
- Acceptance: toast has an Undo action that restores the bookings (API test). Lists ≤ 40 rows animate removal with exit ≤ 120 ms. Reduced motion: none.

**T11 · Small confirmations and tokens** (#18, #19, #20, #21, #22, #23, #24, #26; minor)
- Files: `components/bookings/calendar-sync.tsx` (copy ✓), `free-slots-list.tsx` + `studio/scope-step.tsx` (press tokens), `notifications/notification-bell.tsx` (badge + live region), `shell/top-bar.tsx` (static island dot), `findroom/find-room-view.tsx` + `approvals/my-requests.tsx` (reduce-aware smooth scroll, highlight fade), `studio/rules-step.tsx` (no backdrop blur).
- Acceptance: grep: no `duration: 0.1` / `duration: 0.18` literals in `src/components/**` (use `tween.*`), no `animate-ping` in `shell/`, no `backdrop-blur` in `components/studio/`. e2e: copying a feed link sets the button name to "Kopyalandı" for ≥ 1 s. Bell: two consecutive increments produce two announcements.

**T12 · Glass radius over working grids** (#32; minor; owner: liquid-glass.md)
- Decide in `liquid-glass.md` whether chrome sheets over `/bookings` and `/timetable` use ≤ 24 px blur or the solid variant. Acceptance: `getComputedStyle(sheet).backdropFilter` on `/bookings` matches the decision. RT stays `none`.

**T13 · Fix the RT assertion in the audit template**
- File: `e2e/motion-audit.spec.ts` (and the skill template, by the skill owner). Materials paint as `background-image` gradients, so assert `backgroundImage` contains an opaque `rgb(` layer and `backdropFilter === "none"`, not `backgroundColor`. Measured: RT sheet `linear-gradient(rgb(247, 248, 250), …)`, RT popover `linear-gradient(rgb(255, 255, 255), …)`.

## 4. Not audited (and why)

- **Features admin, approvals inbox, audit viewer and find-a-room are in progress** (uncommitted or `wip` commits). Findings #5–#7, #33–#35 reflect the tree at 15:00. Re-run §1 when they land.
- **Universal onboarding** was read statically from `origin/claude/smartsched-universal`. It is not on this branch yet, so there is no measurement.
- **Device check** (headed GPU, 4× CPU) needs a GPU machine. Run `MOTION_STRICT=1 MOTION_CPU=4 npx playwright test e2e/motion-audit.spec.ts --headed` there after T3.
- One reserve e2e check (`13. room owner…`) failed during setup on the scratch database. It is not a motion issue and was not investigated (scratch data, my-bookings limit text).
