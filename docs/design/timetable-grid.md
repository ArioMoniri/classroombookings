# Timetable grid — design spec

Owner: design-pro · Status: v1 (2026-10-07) · Route: `/timetable` · Tokens: `docs/design/tokens.md` · Data: `docs/DATA_ANALYSIS.md` §C ("Time grid", "Room master").

The grid is the planner's main workspace: **60 rooms × 18 periods per day, 7 days per week, up to 16 weeks per term**, plus exam weeks. It replaces the Excel sheet (`… derslikler takvimi.xlsx`) whose layout the planner (Fatih Bey) already knows: time down the left, rooms across the top, one sheet per week. The design keeps that mental model in the **day zoom** and adds a **week zoom** for density, a conflict layer, locks, and drag-drop that the sheet never had.

## 1. References (Mobbin) and what we borrow

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| 1 | [Deputy — schedule, people × days](https://mobbin.com/screens/93321432-f493-451e-9bc7-551746341583) and [day-by-hour view](https://mobbin.com/screens/fa53831a-00a8-4442-b4e1-82cc1d259ca6) | grouped row bands per department (→ our building bands A/B/C/D), "+" affordance in empty cells, bottom status legend with counts (`0 warnings`, `1 open shift`), view switcher "Week by Area / Day by Area" | the many top toolbars; we keep one |
| 2 | [7shifts — week schedule](https://mobbin.com/screens/cba70260-5011-4d77-abb1-e890393a4844) and [day view](https://mobbin.com/screens/7ae06f41-8ff9-4ca1-8a21-74477e2e9ac3) | **conflict/overtime pills in the header** (`2 Conflicts · 2 Overtime · Fix warnings`) → our "Issues" pill; per-column head counts; department bands that collapse | hourly columns; our columns are periods |
| 3 | [Square — scheduling](https://mobbin.com/screens/66ea4b9b-7284-4f6a-bc5f-cb0860a34724) and [Workday timeline](https://mobbin.com/screens/9eba6531-f7ba-44e9-b6c0-07ccf28d85c8) | role colour = left tint + legible dark text; footer totals per column (→ per-room occupancy %) | pastel-only coding (fails CVD) |
| 4 | [Workable — work calendar](https://mobbin.com/screens/e3ef1c9a-a0f1-40b4-90a6-e11722b779cd) | "Today" highlighted column header with underline; filter row of selects above the grid | |
| 5 | [Front — week view with side editor](https://mobbin.com/screens/d72f085e-13d2-45e9-8f85-e2d5888c949d) | right-hand **sheet** for event details that does not cover the grid | |
| 6 | [Clockwise — move event with conflict dialog](https://mobbin.com/flows/0a0aa36f-0080-4531-8de0-3bac41ea58ec) (screens: ghost outline during drag, "Move event" dialog with *Conflicts · 1* and *Inconvenience* sections, "Event rescheduled" toast) | the exact post-drop confirmation pattern: **new vs original time, hard conflicts listed, soft inconveniences collapsed, Save** | |
| 7 | [Motion — rescheduling](https://mobbin.com/flows/8f2d65fa-0247-4de3-a3d4-0e7caa9de1c2) | dashed ghost at the drop target, original stays faded until commit | |
| 8 | [Rise — dark week view](https://mobbin.com/screens/007929b1-c2c1-4a42-9606-abd23f7d7548) | dark-mode event styling: 3 px left stripe + 12 % tint, white text | |
| 9 | [ClickUp — workload timeline](https://mobbin.com/screens/41e2b803-107e-44ad-95bf-63c11f49a411), [Airtable — projects timeline](https://mobbin.com/screens/508b5288-9eee-43db-bf2a-7164a55a7ef4) | rows = resources with day columns, bars with chevrons at edges for spans → our **week zoom** | |
| 10 | [Deel — month per-person grid](https://mobbin.com/screens/1643ff13-8042-4925-a1b0-b50741557681) | per-column totals row ("Out of office: 0 0 0 2 100") → per-day occupancy row in week zoom | |
| 11 | [Fresha — day, resources as columns](https://mobbin.com/screens/1b3c5a4b-5f4e-4825-a1c1-a3534bdeeec8) | **resource avatars as column headers**, hatched non-working time (→ our pre-occupied hatch), current-time line | |
| 12 | Mobile: [Saturn — period list](https://mobbin.com/screens/b710b067-25bf-4ff1-8aff-bbd93549816a), [Outlook iOS day](https://mobbin.com/screens/435d3aa8-4ff8-4bbb-9e9a-aa1a8852200f), [Jobber — Day / List / Map segmented](https://mobbin.com/screens/29dca97e-075f-4b8d-b1d3-fe1164a764d2) | the 360 px fallback: segmented Day/List, date strip, card per period with status stripe | |

## 2. Information architecture

```
/timetable?term=2026-BAHAR&week=7&day=3&zoom=day&buildings=A,C&q=BME
├── Top bar (sticky, 56 px)
│   ├── Term select · Week switcher  ‹  W7 · 16–22 Mar  ›  · [Today]
│   ├── Day tabs Pzt Sal Çar Per Cum Cmt Paz (day zoom only; Cmt/Paz muted when empty)
│   ├── Zoom: [Day | Week] (segmented) · Building chips A B C D · Tags chips TIP PC
│   ├── Search (⌘K): room, course code, instructor
│   └── Issues pill "3 conflicts · 12 warnings" → opens Issues rail · Legend (?) · Publish ▾ / Export ▾
├── Grid (full-bleed, scrolls both axes; sticky time column + sticky header)
│   ├── Building band row (A — 28 rooms) collapsible
│   ├── Room header cell: "A 204" · 156 seats (exam 74 in exam weeks) · TIP/PC chip · today-% mini-bar
│   ├── Time column: P1 08:30–09:10 … P18 22:10–22:50 (P12 shows "17:30–18:00 · 30 dk")
│   └── Cells / events (spans)
├── Event sheet (right, 420 px; bottom sheet on mobile)
└── Issues rail (right, 360 px; replaces the event sheet when open)
```

**Zoom = day** (default): rows = 18 periods, columns = rooms (filtered), exactly like the Excel sheet. One room column = a CSS grid with `grid-template-rows: repeat(18, var(--period-row-h))`; an event occupying P7–P9 is `grid-row: 7 / span 3`.

**Zoom = week**: rows = rooms, columns = 7 day groups × 18 period mini-columns (6 px each → 108 px per day, 756 px per week + 160 px room label). Events are bars (no text, colour stripe only, tooltip on hover/focus). Clicking any day group jumps to day zoom for that day. Also shows a **per-day occupancy row** at the top (`72 % · 68 % · …`).

**Event (assignment) data model** the grid renders (from `GET /api/v1/assignments?term&week`):
```ts
type GridEvent = {
  id: string; sectionId: string; code: string;          // "BME 419"
  title: string; programme: string; facultySlot: 1|2|…|8;
  roomId: string; day: 1|…|7; periodStart: 1|…|18; periodCount: number;
  weeks: number[];                                       // e.g. [1..14]
  enrolment: number; instructor?: string;
  status: "feasible" | "warning" | "infeasible" | "locked" | "preoccupied";
  issues: { kind: "hard"|"soft"; code: string; text: string }[];   // "capacity_exceeded", "tip_room_not_released", "building_mismatch"…
  note?: string;                                         // Excel comment ("ders 10 50 de bitecek")
  combinedWith?: string[];                               // "HEM 334 / NRS 304"
}
```

## 3. Cell & event anatomy (day zoom, 128 × 40 px per period)

```
┌───┬───────────────────────────────┐
│ ▌ │ BME 419  ·  🔒                 │  ← 3 px faculty stripe · code (12/600, mono) · status icon right
│ ▌ │ 102/156 · Dr. Kaya            │  ← 11/500 fg-muted: enrolment/capacity · instructor (truncate)
│ ▌ │ P7–P9  (span 3 → 120 px tall) │  ← only when span ≥ 3; otherwise in tooltip
└───┴───────────────────────────────┘
```
- Background: `--surface-raised` + faculty tint 12 %; status overrides: `infeasible` → `--status-infeasible-bg` + icon; `warning` → warning bg + icon; `locked` → locked bg + lock icon; `preoccupied` → hatch, text "HAZIRLIK", no drag handle.
- Combined lectures (`HEM 334 / NRS 304`) render as one event with a "2" chip; expanding in the sheet lists both sections.
- **Double booking** (two events, same room/period, imported or after a manual move): the cell splits vertically into two half-width events with `--status-infeasible-border` and an `x-octagon` badge "2"; it is also counted in the Issues pill.
- Empty cell: `--surface-2` on hover shows a faint "+" (Deputy); click → "New block" popover (lock a room as pre-occupied, or assign an unplaced section via search).
- Past periods on today: 40 % opacity; current period row: 2 px `--primary` left line on the time column (Fresha/Rise current-time line, but snapped to the period).

## 4. Interaction spec

### 4.1 States
| State | Visual | Notes |
|---|---|---|
| loading | skeleton grid: header + 18 rows × 8 columns shimmer; week switcher enabled | shimmer static under reduced motion |
| empty (no term/week data) | centred empty state "Bu hafta için program yok" + buttons *Import* / *Generate* | |
| read-only | banner "Yayınlanmış program — düzenlemek için taslak oluştur" ; drag disabled; cursor default | published runs or viewer role |
| stale | top toast-bar "Yeni çalıştırma hazır (Run #42) — Göster" | when a background solve finishes |
| error | inline alert in grid area + retry; last good data stays visible | |
| saving | event gets 60 % opacity + spinner badge; grid still interactive | optimistic |
| offline | Issues pill replaced with "Çevrimdışı" chip; edits queued (TanStack mutation queue) | |

### 4.2 Pointer
- **Hover** event: elevation 1, tooltip (after 300 ms) with full title, programme, weeks pattern (16 mini squares), issues list. Hover room header: tooltip with room facts + "Bu odayı filtrele".
- **Click** event: select (2 px `--primary` outline) + open sheet. Click empty cell: "+" popover. Click building band: collapse/expand (persisted).
- **Double-click** event: open sheet in edit mode (focus the room select).
- **Drag** (dnd-kit `PointerSensor`, `activationConstraint: { distance: 6 }`): the original stays in place at 40 % opacity with dashed border (Motion/Clockwise pattern); a **ghost** (DragOverlay, elevation 2, scale 1.02) follows the pointer; the pointer snaps to `(room, period)`; the target span (`periodCount` rows) highlights **`drop-ok`** (primary outline) or **`conflict`** (dashed red outline + the colliding events pulse once, 2 × 180 ms, then static).
  - Client-side validity check runs on every `onDragOver` (< 1 ms, pure function `checkMove(event, room, day, periodStart, grid)`): overlap with another event in any of the event's weeks, capacity < enrolment, TIP room without release flag, PC-lab required but room lacks `pclab`, target cell pre-occupied, event locked, span exceeds P18, P12 (30 min) inside the span → warning not conflict.
  - Modifiers: `restrictToWindowEdges`; `snapCenterToCursor` off (keep grab offset). Auto-scroll on edges (dnd-kit default).
  - Drop on `conflict`: event springs back (`--spring-drop`), toast "Taşınamadı: A 204 Çar P7 dolu (ENG 102)". No dialog.
  - Drop on `drop-ok`: event moves optimistically, then a **Move popover** anchored to the event (Clockwise): *Yeni: A 101 · Çar P7–P9 / Eski: A 204 · Çar P7–P9 (strikethrough)* · scope radio **Tüm haftalar (1–14)** / **Sadece bu hafta (W7)** / **W7'den itibaren** · collapsed "Uyarılar · 1" (soft issues) · [Geri al] [Kaydet]. Enter = Kaydet, Esc = Geri al. If the user clicks elsewhere, Kaydet is assumed after 4 s (undo toast, 6 s).
  - `PATCH /assignments/{id}` `{roomId, day, periodStart, scope}`; server re-validates hard constraints; 409 → revert + toast with the server's explanation; 200 returns updated `issues[]` for the event and the affected soft score delta ("Soft −2").
  - Alt/Option-drag = **duplicate** to another week scope (asks "Kopyala: hangi haftalar?"). Shift-drag = move without the popover (apply to all weeks, no confirm) — power-user path.
- **Resize** (bottom edge handle, 8 px, visible on hover/focus): changes `periodCount`; same validity feedback; snaps to periods.
- **Context menu** (right-click / long-press / `⇧F10`): Lock/Unlock, Move… (opens the keyboard move dialog), Unassign (send back to inbox), Mark as pre-occupied, Explain in chat, Copy code.

### 4.3 Keyboard (grid is `role="grid"`, roving tabindex, one tab stop)
| Key | Action |
|---|---|
| `Tab` | enters the grid at the last focused cell (or P1 of the first room), next `Tab` leaves to the sheet |
| `← → ↑ ↓` | move cell focus (room / period); `PageUp/PageDown` ± 6 periods; `Home/End` first/last room; `Ctrl+Home/End` P1/P18 |
| `Enter` / `Space` on event | open sheet / **pick up** (dnd-kit `KeyboardSensor`, `keyboardCodes: {start:["Space"], end:["Space","Enter"], cancel:["Escape"]}`) — Space picks up, arrows move the ghost by one cell with the same drop-ok/conflict highlighting, Space/Enter drops (opens the Move popover), Esc cancels |
| `L` | toggle lock on focused event |
| `Delete` / `Backspace` | unassign (confirm dialog) |
| `[` / `]` | previous / next week; `Shift+[ ]` ± 4 weeks; `T` today |
| `1`–`7` | jump to day (day zoom); `D` / `W` zoom |
| `/` or `⌘K` | search; `?` shortcuts dialog; `I` toggle Issues rail; `Esc` close sheet/rail |
| `⌘Z` / `⌘⇧Z` | undo / redo last move (client history, max 50; server records each PATCH) |

Custom `coordinateGetter` for dnd-kit maps arrow keys to cell coordinates (`x ± --room-col-w`, `y ± --period-row-h`) and keeps the ghost inside the scroll container (`scrollBehavior: "smooth"` unless reduced motion).

### 4.4 Touch (≥ 768 px tablets)
- `TouchSensor` with `activationConstraint: { delay: 250, tolerance: 8 }` (long-press to lift; a scroll gesture never lifts). Ghost follows the finger with a 24 px upward offset so the cell is visible. Drop opens the same Move popover; buttons are 44 px tall.
- Pinch does not zoom the grid; the zoom segmented control does. Two-finger scroll pans. `touch-action: pan-x pan-y` on the container, `none` on the ghost.
- Tooltips are replaced by the sheet (tap = select + sheet).

### 4.5 Reduced motion
Ghost follows without lag anyway (transform only). Spring-back → instant; conflict pulse → static dashed outline; week switch cross-fade → none; sheet slides → fade 100 ms; skeleton shimmer → static. Checked with `useReducedMotion()` and the global CSS rule in tokens §6.

### 4.6 Week switcher, filters, persistence
- Week switcher shows `W7 · 16–22 Mar` and the week type chip (`Ders`, `Final`, `BÜT`, `Tatil`). Holiday weeks render the grid with the hatch and a banner.
- Filters (buildings, tags, search, zoom, density, collapsed bands) live in the URL (`nuqs`) so links are shareable; density/collapsed also in `localStorage`.
- Prefetch adjacent weeks (TanStack `prefetchQuery`) on hover of ‹ ›.

## 5. Event sheet (right, Radix Sheet, 420 px)

Header: code + title, faculty stripe, status badge (icon + text), [Lock] [Move…] [⋯].
Sections: **Where/when** (room select with capacity chips, day, period range, weeks pattern as 16 toggle squares); **Fit** (enrolment vs capacity bar using sequential scale; exam capacity in exam weeks); **Requirements** (PC lab, TIP, fixed-time, instructor availability) as check/cross list; **Why here** (constraint explanations from the solver: "Requested A 2xx building ✓, capacity fit 65 % ✓, same room all weeks ✓"); **Notes** (Excel comments, editable); **History** (moves with who/when, "Geri al" per entry); footer: *Sohbette düzenle* (opens chat panel with context).

## 6. Issues rail

List grouped **Hard (n)** / **Soft (n)**; each row = severity icon + one-line text + "Göster" (scrolls and focuses the cell) + "Düzelt" (when the diagnoser offers a fix; opens the run-report fix card inline). Filter chips: building, day. Count syncs with the top pill. Empty: "Çakışma yok — 100/100" with feasible icon.

## 7. Responsive behaviour

| Width | Layout |
|---|---|
| **1920** | Top bar one row. Day zoom shows ~13 room columns (128 px) + 72 px time column before horizontal scroll; building chips default to "all". Sheet docks right (420 px) without covering the grid (grid area shrinks). Week zoom shows all 7 days for ~22 rooms before vertical scroll. |
| **1280** | Same structure; ~8 room columns visible; sheet overlays (Radix Sheet modal=false, grid still scrollable behind); Issues rail overlays. |
| **768** | Top bar wraps to two rows (switcher + zoom / chips + search). Day zoom: 4 columns of 160 px, `scroll-snap-type: x mandatory` per column, building bands become sticky chips above the grid. Week zoom hidden (replaced by the "Hafta özeti" occupancy table). Sheet = bottom sheet (beUI Bottom Sheet or Vaul) 85 vh. Drag via long-press. |
| **360** | **Agenda fallback** (no grid): segmented [Oda listesi \| Gün ajandası]. *Oda listesi*: search + building chips, then a list of room cards (name, capacity, tags, today occupancy bar 0–18, "3 çakışma" badge); tapping a room shows its 18-period list for the selected day (cards with faculty stripe, status icon, code, time, instructor). *Gün ajandası*: periods P1–P18 as section headers, under each the events across all filtered rooms. No drag-drop: each event card has "Taşı…" which opens a full-screen move form (room select → day → period range → scope) with the same validity feedback inline. Week switcher becomes a horizontal date strip (Outlook iOS). |

Breakpoints are Tailwind defaults (`sm 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536`); the agenda fallback applies `< md`.

## 8. Performance notes for the engineer

- Day zoom: ≤ 60 columns × 18 rows = 1 080 cells + ≤ ~500 events; render with plain React, memoised per room column (`React.memo`, key = roomId + week version). No virtualisation needed.
- Week zoom: 60 rows × 126 mini-cells = 7 560 cells → render each room row as **one `<div>` with CSS `background-image: linear-gradient(...)` stops** or a tiny inline SVG per row; events as absolutely positioned bars. Virtualise rows with `@tanstack/react-virtual` when rooms > 40.
- Validity checks are pure and run on a `Map<"room:day:period:week", eventId>` index built once per data load.
- `DragOverlay` renders the ghost in a portal so the scroll container never reflows.

## 9. Component list

| Need | Component | Source / licence | Install / note |
|---|---|---|---|
| Drag-drop engine | `DndContext`, `useDraggable`, `useDroppable`, `DragOverlay`, `PointerSensor`, `TouchSensor`, `KeyboardSensor` | @dnd-kit/core — MIT — https://dndkit.com | `npm i @dnd-kit/core @dnd-kit/modifiers @dnd-kit/utilities`; custom `coordinateGetter`; `accessibility.announcements` in Turkish/English ("BME 419 alındı. A 204, Çarşamba P7 üzerinde. Bırakmak için Boşluk.") |
| Grid primitives | our own `TimetableGrid`, `RoomColumn`, `GridEvent`, `PeriodAxis`, `BuildingBand` | in-house (`src/components/timetable/*`) | CSS grid, tokens §4 |
| Row virtualisation (week zoom) | `useVirtualizer` | @tanstack/react-virtual — MIT | `npm i @tanstack/react-virtual` |
| Sheet / bottom sheet | `Sheet` (Radix Dialog) ; mobile: `Drawer` (vaul) | shadcn/ui — MIT ; vaul — MIT | `npx shadcn@latest add sheet drawer` |
| Popover (Move confirm, "+" cell) | `Popover` | shadcn/ui — MIT | `add popover` |
| Tooltip | `Tooltip` with `delayDuration={300}` | shadcn/ui — MIT | `add tooltip` |
| Segmented zoom, day tabs | `ToggleGroup`, `Tabs` | shadcn/ui — MIT | `add toggle-group tabs`; sliding indicator with `motion` `layoutId` (pattern from transitions.dev "Tabs sliding" — re-implemented, not copied) |
| Filter chips | `Toggle` + `Badge` ; reference: kobra "Filter Chips" (**reference only, Pro licence**) | shadcn/ui — MIT | |
| Search / command | `Command` (cmdk) | shadcn/ui — MIT | `add command` |
| Context menu | `ContextMenu` | shadcn/ui — MIT | `add context-menu` |
| Toasts (move result, undo) | `sonner` via shadcn `Toaster`; motion reference: beUI "Animated Toast Stack" (MIT) and Kinetics "Undo Snackbar" (**reference only, licence unverified**) | sonner — MIT | `add sonner`; undo action 6 s with drain bar |
| Skeleton | `Skeleton` | shadcn/ui — MIT | |
| Legend popover | `Popover` + `StatusLegend` (in-house; lists the 7 states with icon + swatch + hatch) | | |
| Week switcher | in-house `WeekSwitcher` (Button group + `Select` for jump) | shadcn/ui — MIT | |
| Weeks pattern squares | in-house `WeekPattern` (16 toggles, `role="group"`) | | |
| Capacity-fit bar | `Progress` | shadcn/ui — MIT | sequential scale tokens §2.5 |
| URL state | `nuqs` | MIT | `npm i nuqs` |

Not adopted and why: beUI *Availability Scheduler* (it is a weekday × time-range form, not a grid); kobra *Magnetic Dropzone* (licence, and magnetism is wrong for precise cell targeting); Astryx (StyleX runtime).

## 10. Accessibility

- Grid: `role="grid"` with `aria-rowcount=18 aria-colcount=N`, cells `role="gridcell" aria-rowindex aria-colindex`, column headers `role="columnheader"` ("A 204, 156 koltuk, TIP"), row headers `role="rowheader"` ("P7, 13:30–14:10"). Events are `<button>` inside the cell with `aria-label="BME 419, A 204, Çarşamba P7–P9, 102 öğrenci, 156 koltuk, kilitli"` and `aria-describedby` to their issues list.
- Live region (`aria-live="polite"`) for drag announcements (dnd-kit `announcements`) and for save results ("BME 419 A 101'e taşındı. Geri almak için ⌘Z").
- Every status has icon + text (tokens §2.2); the hatch pattern survives `forced-colors`; faculty stripe is never the only identity (code text always present).
- Focus ring 2 px `--focus` + 2 px offset, visible on cells and events; focus is never lost when the sheet closes (returns to the event).
- Zoom to 200 %: grid scrolls horizontally; sticky headers stay; nothing clips. Text in week-zoom bars does not exist, so nothing shrinks below 10 px.
- Touch targets 44 px on touch; period rows stay 40 px in comfortable density (compact 28 px is pointer-only and is disabled on touch).
- Language: `lang="tr"` with `hreflang` toggles; all shortcuts are letter-independent of locale except `L`/`D`/`W` which are remapped in `en` → `L`/`D`/`W` (same) and documented in the `?` dialog.
- Reduced motion per §4.5; no content flashes more than 3 times per second (conflict pulse is 2 cycles).

## 11. Open questions (for the orchestrator / user)

1. Should the default zoom be **day** (Excel-like) or **week** (overview)? Spec assumes day; week is one key away.
2. Exam weeks: does the grid show **exam capacity** in the room header automatically (data says A 101 58→30)? Spec assumes yes, from `terms.kind` / `weeks.type`.
3. TIP release: who can toggle "released for others" on A 201–203 — only admin or also the medicine planner (Gözde Hanım)? Affects the lock/unlock affordance.
4. Move scope default: *all weeks* vs *this week only*. Spec defaults to all weeks for lecture terms and *this week only* for exam weeks.
5. Do combined lectures (`HEM 334 / NRS 304`) move as one unit always? Spec: yes, with a warning if their enrolments differ.
6. Saturday/Sunday: hide by default when a week has no weekend events? Spec: show muted tabs, hide columns in week zoom when empty.
7. Multi-select drag (move several events at once) is **out of scope** for v1 — confirm.
