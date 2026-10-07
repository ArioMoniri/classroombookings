# Rooms — cards/grid with photo, capacity, exam capacity, tags, building/floor filter, room detail with weekly occupancy sparkline

Owner: design-pro (B). Routes `/rooms`, `/rooms/[id]`, `/buildings`. Backend:
`GET/POST/PUT/DELETE /rooms`, `/buildings`, `POST /rooms/{id}/photo`, `GET /runs/{id}/assignments?room=`,
`GET /runs/{id}/grid?week=`. Room fields: `building_id, code (A101), display_name (A 101), floor, capacity,
exam_capacity, tags [TIP, PC, LAB, AMPHI], is_bookable, notes, photo_url, legacy_crbs_room_id`.
Data: 60 rooms across buildings A (floors 1–3), B (2, 4), C (z, 2–6), D; buckets 156 → 30 seats; TIP rooms
A 201–203 need medicine-planner approval; exam capacity ≈ half of lecture capacity except PC labs.
Licences: `navigation-shell.md §9`. Chart colours: run the `dataviz` skill palette when building the sparkline.

---

## 1. References

| # | Reference | Borrow |
|---|---|---|
| 1 | [Airbnb – homes grid + map](https://mobbin.com/screens/4b9d614f-7f68-47bb-83e6-7fd35efca097) | 3-col card grid with 4:3 photo, overlay badge top-left ("Guest favorite" → our `TIP` / `PC`), heart top-right (→ pin/favourite), title + 2 muted meta lines; split view with a map on the right → ours: **building floor plan / stack** panel |
| 2 | [Airbnb – filter chips popover](https://mobbin.com/screens/5f99d74b-4947-427a-8ef9-d98d9a62f55e) | Chip grid multi-select with `Clear · Show 120 results` |
| 3 | [Airbnb – range slider filter](https://mobbin.com/screens/00f5e265-68e6-4ea8-bc26-382287e8fa9a) | Dual-thumb range popover (duration) → **capacity range** 10–160 |
| 4 | [Airbnb – filter bar with count badges](https://mobbin.com/screens/555e4698-1fca-47b8-bac9-8f83b3448c78) | `Type ▾ · Duration ▾ · Filters (3)` pill bar with active-count badge |
| 5 | [Airbnb – horizontal card rows](https://mobbin.com/screens/99e4c984-570e-4675-b8ec-e035c6298b2f) | Rows per group with chevrons → "Group by building" view: one horizontal scroll row per building |
| 6 | [Booking.com – room table with facility icon list](https://mobbin.com/screens/49b5fb0d-3b76-4221-93e1-dfede032bfd2) | Dense table alternative: room name, size, icon-labelled facilities, "Select" column → our **table view** toggle |
| 7 | [Booking.com – room detail modal with gallery + facilities checklist](https://mobbin.com/screens/9771e941-32c0-45a9-ae99-e057eb41ed9f) | Detail: gallery left, facts right (Size, beds, facilities two-column checklist) |
| 8 | [Booking.com – fullscreen gallery with thumbnails + side panel](https://mobbin.com/screens/0a699f10-f3d3-4390-93c6-43b3052ad383) | Lightbox with counter "23 / 49", thumbnail strip, right panel |
| 9 | [Neon – metric cards with small charts](https://mobbin.com/screens/cf45e7bf-4a0e-40cc-9db5-a29845b58d4e) | Small time-series per card with hatched "inactive" area → occupancy sparkline with hatched blocked periods |
| 10 | [Steep – stat cards with bar sparkline](https://mobbin.com/screens/d393ceef-678a-4d80-bd1b-5e32e13cc065) | Bar sparkline per weekday (M T W T F S S) with the active bar highlighted — exact shape of the room card mini-chart |

## 2. Information architecture

```
/rooms
  toolbar: search (code/name) · Building ▾ (A B C D) · Floor ▾ · Tags ▾ (TIP PC LAB AMPHI) · Capacity range ▾ · Exam cap ≥ · Bookable ☐ · [Cards | Table] · Group by building ☐ · Week/Run context ▾ · + Room (ADMIN)
  active filter chips
  body: card grid (default) | table | grouped rows
  side (≥1280): building stack panel — floors as rows, rooms as small squares coloured by utilisation for the selected week; click = filter
/rooms/[id]
  header: breadcrumb Rooms › A › A 204 · name · tags · bookable switch · Edit · ⋯ (photo, archive, open in CRBS)
  gallery (photos) | facts card (capacity, exam capacity, floor, building, legacy id, notes)
  occupancy: week switcher + 7-day sparkline strip + full day×period heat strip; list of assignments for the week (course, program, periods, origin)
  rules: constraints that mention this room (TIP reservation, blocks HAZIRLIK/UZEM) with links to the constraint drawer
  history: edits (capacity changed 58→30 for exam sheet, who/when)
/buildings  (simple table: code, name, floors, room count, utilisation)
```

Card anatomy (Airbnb #1, 4:3 photo):
```
┌────────────────────────────┐
│ [TIP]              [☆ pin] │   photo (or generated placeholder: building colour + big code)
│                            │
├────────────────────────────┤
│ A 204                 156 👥│   display_name · capacity (users icon)
│ A Blok · 2. kat · amfi     │   building · floor · tag words
│ Sınav 74 · PC ✗            │   exam capacity · tags as icons (PC, LAB, AMPHI)
│ ▁▃▇▇▅▁▁  72 % this week    │   7-bar weekday sparkline + utilisation %
└────────────────────────────┘
```

## 3. Interaction spec

### 3.1 Grid & filters
- Grid: CSS grid `repeat(auto-fill, minmax(260px, 1fr))`, gap 16/24 px; cards are `<a>` to `/rooms/[id]`; hover lifts 2 px + shadow (150 ms); focus ring visible. Reduced motion: shadow only.
- Filters (Airbnb #2–#4): each is a popover; Building/Floor/Tags = chip grids; Capacity = dual range (10–160, steps of 2) with histogram of room counts behind it (bars = count per 10-seat bucket; uses the data from the Bahar `Sayfa2` buckets); Exam cap = single min input. Active-filter count badge on the Filters pill. "Clear all" resets URL.
- Search: by code (`a20` → A 201…A 207), by name, by tag word (`tıp`), diacritic-insensitive. Debounced 150 ms; results count "12 rooms".
- Week/Run context ▾: choose a run (default active run) + week to colour sparklines/utilisation; stored in URL `?run=42&week=3`. Without a run, sparklines show imported grid occupancy (origin IMPORT) or hide with "no schedule yet".
- Sorting: dropdown — Code (default), Capacity ↓, Utilisation ↓, Floor.
- Views: Cards / Table (TanStack: code, building, floor, capacity, exam cap, tags, bookable, utilisation %, actions; inline edit for capacity/exam cap/tags for ADMIN/PLANNER) / Group by building (Airbnb #5: horizontal scroll-snap rows per building with a "See all 18 →" link).
- Building stack panel (≥1280): a vertical stack per building, each floor a row of 12 px squares (one per room), colour = utilisation quantile (5-step sequential palette from `dataviz`), hatched = not bookable, outlined = TIP. Hover → tooltip "A 204 · 156 · 72 %"; click → filter grid to that room; keyboard: squares are buttons in a `role="grid"`.
- States: loading → 12 skeleton cards (photo block + 3 lines, shimmer only without reduced motion); empty (no rooms) → CTA "Import the weekly grid or CRBS to create rooms" + "Add room"; empty (filters) → "No rooms match · Clear filters"; error → banner + retry.

### 3.2 Card sparkline
- 7 bars (Mon–Sun) = occupied periods / 18 for the selected week; evening periods (P13–P18) stacked in a lighter shade on top of day periods so İÖ usage is visible; blocked periods (HAZIRLIK/UZEM) hatched (Neon #9).
- Height 28 px, bar width 8 px, gap 3 px; today's/selected day bar in `primary`, others `muted-foreground/60`. Tooltip on hover/focus per bar "Çarşamba · 11/18 periods · 2 blocked".
- Implement as inline SVG (no chart lib) for the card; `aria-label="Weekly occupancy: Mon 40 %, Tue 60 % …"`, `role="img"`.
- Animation: bars grow from 0 on first paint 200 ms stagger 20 ms; reduced motion: static.

### 3.3 Room detail
- Gallery: primary photo 16:9 with thumbnail strip; click → lightbox (beUI Image Viewer: swipe, keyboard ←/→, zoom; counter "2 / 5"); ADMIN: drag-drop upload onto the gallery (`POST /rooms/{id}/photo`, multipart, 10 MB, jpg/png/webp; client resizes to 2048 px with `canvas` before upload), reorder by drag (dnd-kit), set cover, delete with confirm. No photo → placeholder: building colour wash + large code glyph + "Add photo".
- Facts card: capacity / exam capacity (with "≈ half of lecture" hint when equal to `round(capacity/2)`), floor, building, tags (editable chip input), bookable switch (off → explains "excluded from solver; existing assignments stay"), notes textarea (autosave 800 ms, "saved" check), legacy CRBS id + link if `crbs` profile is on.
- Occupancy section:
  - Week switcher (same component as timetable; `←/→` keys) + run context.
  - **Day × period heat strip**: 7 rows × 18 columns of 14 px cells; colour: free (transparent border), occupied (`primary`, intensity by cohort size vs capacity), blocked (hatched), conflict (destructive); hover shows course code; click → opens assignment popover (course, program, instructor, weeks pattern, origin, "Open in timetable"). Keyboard: `role="grid"`, arrow keys.
  - Sparkline strip (large version, 7 bars) above the heat strip with the week's utilisation % and a 16-week mini line (one point per week) using evilcharts/recharts **Area chart** stripped of axes (sparkline). Values: occupied periods per week / (18×7).
  - Assignment list below (TanStack, 44 px rows): Day, Periods, Course, Program, Enrolment vs capacity (bar), Weeks, Origin badge (SOLVER / AI_EDIT / MANUAL / IMPORT), lock icon; row → timetable deep link `/runs/{run}/grid?week=&room=`.
- Rules section: constraints referencing the room (`GET /constraints?room_id=`) rendered as the same rows as generate-and-chat §3.4, read-only here with "Edit in constraints".
- Edit mode (ADMIN/PLANNER): `Edit` toggles inline forms; save bar sticky bottom "Unsaved changes · Discard · Save" (Vercel pattern); validation: capacity ≥ 1, exam_capacity ≤ capacity, code unique per building (`^[A-D]\s?[zZ]?\d{2,3}$` with preview of canonical `A101` and display `A 101`).
- Danger: Archive room (soft delete; blocked if it has assignments in the active run → explains and links).

### 3.4 Keyboard & touch
Grid: `/` search, `f` filters, `v` toggle view, `←/→/↑/↓` move focus among cards (roving), `Enter` open, `p` pin. Detail: `e` edit, `←/→` week, `Esc` close lightbox/popover. Touch: cards 100 % width at 360; filter bar scrolls; heat-strip cells 24 px on touch with pinch-less horizontal scroll; lightbox swipe.

### 3.5 Motion
Card hover 150 ms; photo cross-fade on load 200 ms (blur-up from a 20 px thumbnail, `next/image` `placeholder="blur"`); lightbox open scale .96→1 200 ms; heat strip cells colour fade 150 ms when switching weeks (no per-cell stagger, > 100 cells). All gated by reduced motion.

## 4. Component list

| Component | Source | Licence | Note |
|---|---|---|---|
| Card, Badge, Popover, Slider (dual), Toggle Group, Switch, Input, Textarea, Table, Tooltip, Sheet, Dialog, Skeleton | shadcn/ui | MIT | `npx shadcn@latest add …` |
| Image Viewer (lightbox: swipe, keyboard, zoom, pan) | beUI https://beui.dev/components/motion/image-viewer | MIT | `bunx --bun shadcn add @beui/image-viewer` |
| Sortable List (photo reorder with keyboard) | beUI https://beui.dev/components/motion/sortable-stack | MIT | or dnd-kit sortable directly |
| Tilt Card (3D hover + glare) | beUI https://beui.dev/components/motion/tilt-card | MIT | **do not use** for the grid (60 cards, motion noise); optional on the detail cover only, off under reduced motion |
| Range Slider | beUI https://beui.dev/components/motion/range-slider | MIT | capacity filter (needs dual-thumb; else Radix Slider with two thumbs) |
| Area chart (sparkline base) | evilcharts https://evilcharts.com/docs (`@evilcharts/recharts-area-chart`, repo github.com/legions-developer/evilcharts) | MIT | 16-week trend line; hide axes/grid, height 40 px; colours via tokens |
| Status Bar chart | beUI https://beui.dev/charts/status-bar | MIT | alternative for the day×period strip (status segments) |
| Insight Cards (paged insights with live charts) | beautifului.dev https://beautifului.dev/#insight-cards | MIT | building panel summary cards (optional) |
| Weekday bar sparkline | custom inline SVG `components/ui/sparkline-bars.tsx` | ours | Steep #10 as visual reference |
| Image upload | `react-dropzone` | MIT | gallery drop target |
| Lightbox (kobra) | kobra.systems Content › Lightbox | paid/personal-only | reference only |
| Stacked Cards / Hex Outline | reverseui | paid | reference only |

## 5. Responsive behaviour

| Width | /rooms | /rooms/[id] |
|---|---|---|
| 360 | 1-col cards (photo 16:9), filter bar as horizontal pill scroller + "Filters (3)" opens full-screen Sheet; building panel hidden (available as a tab "Buildings"); table view = cards | gallery full-bleed carousel with dots; facts card; occupancy: week switcher + 7-bar sparkline; heat strip scrolls horizontally (18 cols × 24 px) inside a card with sticky day labels; assignment list as cards |
| 768 | 2-col cards; filters inline popovers; building panel as collapsible top strip | 2-col (gallery 60 / facts 40); heat strip fits (18 × 32 px) |
| 1280 | 3–4 col cards + right building panel 320 px | gallery 55 / facts 45; occupancy full width; rules + history two-column |
| 1920 | 5 col cards (max 1600 px content) + panel 360 px | content max 1400 px; heat strip cells 20 px |

## 6. Accessibility
- Cards: single link wrapping the card with `aria-label="A 204, A Blok floor 2, 156 seats, exam 74, TIP, 72 % used this week"`; pin button is a separate focusable control outside the link (DOM order after the link, positioned absolutely).
- Tag badges include text, not only icon (`PC` label + icon).
- Sparkline `role="img"` + summary label; heat strip `role="grid"` with `aria-rowindex/colindex`, cells `aria-label="Wednesday P7 13:30–14:10, MAT 112, 58 of 156 seats"`; colour intensity paired with a numeric tooltip.
- Capacity range slider: two thumbs with `aria-label="Minimum capacity"` / `"Maximum capacity"`, `aria-valuetext="60 seats"`.
- Lightbox: `role="dialog"`, focus trap, `Esc`, arrow keys, image `alt` from photo caption (default "Photo n of A 204").
- Hatched/blocked patterns use SVG `pattern` plus text, so they survive forced-colours mode; test `@media (forced-colors: active)`.
- Upload: dropzone also a button; progress announced.

## 7. Open questions
1. Photo source: the university panel sync (ROADMAP phase 7) may provide `photo_url`s — should manual uploads be overwritten by sync? Spec: sync fills only empty `photo_url`.
2. Floor plans per building (image overlay with room hotspots) instead of the abstract square stack? Needs assets from the university.
3. Utilisation definition for the card: occupied / 18 periods × 7 days, or / bookable periods (exclude P12 transition and weekends unless İÖ)? Spec: / 18×5 for REGULAR terms, / 18×7 for exam weeks — confirm with planner.
4. Should "exam capacity" be editable per exam period (Final sheets show different values across sheets, e.g. A 103 47/33)? Currently a single `exam_capacity` column.
5. TIP approval contact ("Gözde Ayrancıgil 4073") — store as a building/room note field or a structured `approver` field?
