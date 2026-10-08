# Calendar v2: the timetable on Liquid Glass

Owner: design-pro (v2 calendar + all-classes) · Status: spec v2.0 (2026-10-08) · Route: `/timetable` (kept, so existing links still work)
Supersedes the visual and IA parts of `docs/design/timetable-grid.md` (v1). v1 still holds for anything this doc doesn't change: the dnd-kit sensor config, the move-scope popover, and the `checkMove` rules.
Depends on: `docs/design/v2/liquid-glass.md` for materials, glass tokens and glass components, and `docs/design/v2/motion.md` (plus the `/motion_designer` skill) for springs and choreography. Base tokens come from `docs/design/tokens.md` (faculty palette §2.3, sequential scale §2.5, durations §6).
Data: `docs/DATA_ANALYSIS.md`. About 60 rooms in buildings A–D (capacity, TIP/PC tags), 18 periods from 08:30 to 22:50 (P12 is a 30-minute transition), 14 lecture weeks plus exam weeks, about 1,300 placed meetings per term, and evening (İÖ) programmes from 18:00.
Companion: `docs/design/v2/all-classes.md` shares the inspector, filters, copy and the anti-AI checklist. Wireframes: `docs/design/v2/wireframes/calendar-*.svg`.

---

## 0. Why v1 reads as "AI-generated" (from `docs/images/screens/timetable-*`)

| v1 symptom (screenshot) | Why it feels generic | v2 answer |
|---|---|---|
| A page H1 "Timetable" repeats the top-bar title "Timetable", and a giant run pill sits on the right | Template scaffolding, and it wastes 120 px of height | No page H1. The canvas title is the date range ("16–22 Mart 2026 · Hafta 7"), as in Apple Calendar. The run lives in the sidebar. |
| The toolbar is a bordered card holding 14 pill chips (days, view, A/B/C/D/TIP/PC, search, status pill, legend) | Everything has the same visual weight, a "kitchen-sink" look | Three floating glass capsules (navigate · lens · subject/actions). Filters move into the sidebar. |
| A saturated blue fills the active segment ("Wed", "Day view", "A") | Bootstrap look, not Apple's | Glass segmented control with a raised neutral thumb. Accent colour only for today and selection. |
| A green "0 conflict · 0 over capacity" pill is always on | It celebrates a zero; noise | Issue counts appear only when > 0 (red/amber capsule in the toolbar). |
| JetBrains Mono for every code ("BME 419 §1") | Monospace is the house style of AI dashboards | System font (SF Pro / Inter) with `tabular-nums`, weight 600 for the code. |
| Two-line period labels "P7 / 13:30– / 14:10" in a 100 px gutter | Cramped and noisy | Gutter shows "13:30" only (P7 in a tooltip and on focus). The width drops to 56 px. |
| A capacity mini-bar in every room header | Decoration that is unreadable at 2 px | Capacity as a number ("156"). Occupancy appears only in the Month/Term heat. |
| Week view: tiny unlabeled coloured slivers | Data without meaning | The week strip shows code text from 32 px wide, and the heat only below that. |
| Chips with a 3 px stripe, white fill and a grey border | The v0/shadcn default card | Apple Calendar chip: tinted fill, a darker same-hue ink, a 3 px bar, no border, no shadow at rest. |
| Rooms page: gradient hero tiles with giant room codes | The most recognisable AI-UI trope | Out of scope here; flagged for the rooms spec. |

## 1. Principles

1. **Content is opaque; chrome is glass.** Apple's HIG puts Liquid Glass on a functional layer of controls and navigation that floats above content, and it cautions against glass on content elements like cards and rows ([HIG: Materials](https://developer.apple.com/design/human-interface-guidelines/materials), [HIG: Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)). Event chips, grid cells and heat cells are never `backdrop-filter`. The capsules, sidebar, inspector, scrubber, popovers and bulk bar are.
2. **One dataset, many lenses.** Every lens reads the same client-side index (§13) and shares selection, filters, the compare run and undo. Switching lens never refetches.
3. **The Excel mental model is the floor, not the ceiling.** The planner's sheet (time down, rooms across, one sheet per week) is lens 1, pixel-familiar. The other lenses are views Excel could never give him.
4. **Every placement is explainable in place.** Select any chip, and the inspector says why it is there, where it came from, and what breaks if you move it.
5. **Motion explains cause and effect only:** ≤ 300 ms, springs from motion.md, nothing decorative, all of it removed under `prefers-reduced-motion`.

## 2. References (Mobbin + Apple HIG), with what we borrow

Apple's first-party apps (Calendar, Numbers) are not indexed on Mobbin. Apple Calendar behaviour is described from the shipping iOS 26 / macOS 26 apps and the HIG. Mobbin covers the third-party apps that already ship the iOS 26 idiom.

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| A1 | Apple Calendar macOS 26 / iOS 26 (no Mobbin entry; HIG [Materials](https://developer.apple.com/design/human-interface-guidelines/materials), [Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars), [Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars), [Sheets](https://developer.apple.com/design/human-interface-guidelines/sheets)) | Toolbar items grouped into floating glass capsules. Inset glass sidebar with the mini-month and calendar list. Tinted event chips with same-hue ink. Red now-line with a time capsule in the gutter. Inspector popover/sheet. Day/Week/Month/Year shortcuts. "Up Next" list. Drag-to-create, edge resize. | Year view as twelve tiny months (it doesn't fit 14 weeks × 7 days of heat; we use the Term lens) |
| 1 | [Outlook iOS: day view with a week strip](https://mobbin.com/screens/435d3aa8-4ff8-4bbb-9e9a-aa1a8852200f) | 360 px phone header: month title, a 7-day strip with the selected day as a filled circle, a grabber to expand into a month, an "All day" row, and the now-time label in the gutter | The heavy blue header fill |
| 2 | [Todoist iOS: calendar day, iOS 26 chrome](https://mobbin.com/screens/d47e73a3-2711-4811-b66f-616f1c905bf3) | iOS 26 floating glass tab bar, glass circle buttons top-right, red now-line with a red time pill ("02:19"), all-day chip row | Pastel chips without bars |
| 3 | [Amie iOS: day list with a floating capsule](https://mobbin.com/screens/5330247b-2fcd-497e-9dfe-8355835bfb14) | A dark floating capsule toolbar at the bottom; chips with duration right-aligned ("1h 30m"); a past event faded only slightly | Emoji in titles |
| 4 | [Structured iOS: timeline under a glass sheet](https://mobbin.com/screens/b083bbe4-0775-444c-91f7-85cde51983db) | A glass bottom sheet with a grabber floating over the timeline, and the tab bar separate from the floating "+" | Icon-only timeline (no text) |
| 5 | [Apple Store iOS: Upcoming](https://mobbin.com/screens/010ffa81-7808-4692-8140-09b04cf01a65) | Apple's own iOS 26 idiom: a glass tab bar with the search button detached as a circle, a day strip with a black selected circle, a plain list with no cards | |
| 6 | [Saturn iOS: period list](https://mobbin.com/screens/b710b067-25bf-4ff1-8aff-bbd93549816a) | School-period agenda: one row per period with a time range under the title, and a hatched "Free period" row. This becomes our mobile day list and the hatched pre-occupied rows. | Emoji icons |
| 7 | [Jobber iOS: Day / List / Map](https://mobbin.com/screens/2ed89ad5-4fb9-4c08-8a4a-fe521a09bfe9) | A segmented lens switch under the title on phones (Liste / Zaman çizelgesi) | |
| 8 | [Notion Calendar: month board](https://mobbin.com/screens/5b3dd0a5-2981-487b-9510-c7d46f221c53) and [timeline with a today marker](https://mobbin.com/screens/6d9641f2-a575-4695-92ef-aea771018018) | Month cells that carry real content; "Today ‹ ›" as one control group; the today marker as a red day bubble plus a vertical line | |
| 9 | [Amie web: week with an all-day band](https://mobbin.com/screens/05c4146b-77d3-486d-809d-d8173d8aa4d6) and [inspector sheet over the grid](https://mobbin.com/screens/610e4725-cbc6-4b32-8fa7-67c40bbe589a) | An all-day band with compact chips stacked above the time grid; a red now-line from the gutter across today only; an event inspector floating over the grid, not a full-height drawer; a "W16" week number next to the month | |
| 10 | [Proton Calendar: event popover](https://mobbin.com/screens/46a7f681-3db4-4285-a50a-ba469acf7399) | Popover anatomy: a colour bar beside the title, date line, icon rows (place, people, calendar, notes), edit/duplicate/delete icons top-right; mini-month with week numbers | The dark purple sidebar |
| 11 | [Rise: mini-month popover from the title](https://mobbin.com/screens/4f21d518-0765-4ad8-8e80-d4e0afeb794f) | Clicking the date title opens a glass mini-month with week numbers; the tooltip shows its shortcut ("Go to previous month ↑"). This is our week jump. | |
| 12 | [Motion: week + "Up next" rail + hatched time](https://mobbin.com/screens/4ef5e33f-7a9e-4b62-a46a-1a56b3a4e08d) | Hatched blocked time; a right-hand list grouped by day (our Agenda/Up Next panel on ≥ 1920); a sidebar with mini-month plus calendar checkboxes | Too many small icons per chip |
| 13 | [Front: translucent sidebar with mini-month and calendar list](https://mobbin.com/screens/a1949523-861d-4384-ae89-bb62d192eddd) | Sidebar order: mini-month, find field, calendar checkboxes with colour swatches. Ours lists faculties with their colour swatch. | |
| 14 | [Microsoft Teams: anchored event popover](https://mobbin.com/screens/d9bcba76-bfa9-4876-998e-e85dade2cc34) | Popover anchored beside the chip with primary/secondary actions (Join/Edit becomes Open/Move); the today column with a coloured top rule | |
| 15 | [ClickUp Planner: quick-create popover](https://mobbin.com/screens/f8df4ef0-9a4a-4eee-a4f1-dbd8a299c13c) | Quick-create popover with type tabs (Event/Task/…) and "Save ⌘↵". Ours: tabs **Rezervasyon / Ders talebi**. Also "3 events" counts in the all-day row. | |
| 16 | [Superhuman: drag-create selection](https://mobbin.com/flows/b4ca3bce-acb9-4c1e-b65d-4c0f5a365ce2) and [Skiff create flow](https://mobbin.com/flows/278b5778-83b4-4ad3-a5ea-296d26fa2abb) | A dashed selection block that shows its live time range ("9:00 – 12:00") while dragging, then a compact form; the new block stays visible while the form is open | |
| 17 | [Fibery: create in place](https://mobbin.com/flows/0e14a1e2-233f-4045-9c7e-4863b30ab622) | After drag-create, typing goes straight into the block (title-in-place), then the time label appears | |
| 18 | [SavvyCal: hatched unavailable + "Overlay my calendar"](https://mobbin.com/screens/f17fcec4-d647-43a1-a527-a8cd1b5589b9) | Hatching for unavailable time, which becomes our pre-occupied HAZIRLIK/UZEM blocks; the overlay toggle becomes **Compare runs** ghost overlay | |
| 19 | [Deputy: banded rows with LOCKED/OPEN badges + legend counts](https://mobbin.com/screens/9915dbfc-159b-425c-a1be-e1fc81df62a8) | Collapsible group bands (building A/B/C/D), tiny state badges on chips, a footer legend with counts ("2 open shifts · 0 warnings") | Pastel-on-pastel badges |
| 20 | [Workable: people × days with a multi-day dashed bar](https://mobbin.com/screens/eb1665f6-d109-4724-999e-89f7cdc569b4) | A multi-day bar spanning columns with a dashed outline, which becomes our term-long bands; the today column underline | |
| 21 | [Aboard: floating "‹ › Today" capsule + today line](https://mobbin.com/screens/0773086c-2875-4071-a373-d1c07f44d554) | A bottom-floating navigation capsule over a timeline, a blue today line through all rows, shaded weekends. This is our week scrubber's home. | |
| 22 | [Square: per-column totals row](https://mobbin.com/screens/66ea4b9b-7284-4f6a-bc5f-cb0860a34724) | A totals row under a resource × day grid (becomes per-day occupancy in the week strip) | |
| 23 | [Turo: resource row with a range scrub + side tabs](https://mobbin.com/screens/1a894579-8255-422c-92fc-2cf9639d6461) | A range drawn across day columns with handles; a right panel with tabs. Used for the Term lens week-range brush. | |
| 24 | [Steep: heat with a threshold legend editor](https://mobbin.com/screens/4b8bbec1-fe24-48c7-83f2-cfd5d75cd2d2) | Heat cells with an explicit legend and adjustable thresholds (Min/Mid/Max). Becomes the Month/Term heat legend popover. | Red-green diverging scale (CVD) |
| 25 | [Wix: filter accordions under the mini-month](https://mobbin.com/screens/a606e4dd-7378-4301-a245-12a36d5eeb42) | Sidebar filter sections (Services/Staff/Location becomes Bina/Fakülte/Etiket/Durum) with Reset | Dense admin chrome |
| 26 | [Clockwise: "Schedule or reschedule…" field](https://mobbin.com/screens/7b2b7989-fe8c-43b2-8992-9243fe76c3ba) | A natural-language field with the promise "Nothing will change until explicitly confirmed". Our ⌘K jump-to accepts "A 204 perşembe" and never mutates. | |

## 3. Interaction patterns named

| Pattern | Where |
|---|---|
| **Floating capsule toolbar** (grouped glass capsules; A1, #21) | top of canvas; week scrubber at bottom |
| **Inset glass sidebar** (mini-month, then filters; A1, #13, #25) | left, collapsible |
| **Inspector sheet** (non-modal glass panel; #9, #10, #14) | right; bottom sheet with detents on phones |
| **Lenses over one index** (Board / Week / Day / Month / Term / Agenda) | §4 |
| **Subject picker** (week calendar of one room / instructor / cohort / section) | toolbar capsule 3 |
| **Slot magnetism** (snap to period edges, pull toward nearest valid slot) | drag, resize, create |
| **Live conflict preview** (target outline + reason capsule + highlighted culprits) | drag, resize, multi-move |
| **Lasso multi-select** (⇧-drag on empty canvas) and ⌘-click | Board, Week strip, Day timeline |
| **Drag-to-create, then a typed popover** (#15, #16, #17) | empty slots |
| **Ghost overlay compare** (#18) | toolbar ⋯ › Karşılaştır |
| **Scrubbable week rail** (#21, #23) | bottom capsule |
| **Heat calendar** (#24) | Month, Term |
| **Command jump-to** (#26) | ⌘K |
| **Undo stack with toast** | every mutation |

## 4. Information architecture: six lenses on one dataset

```
/timetable?term=2026-BAHAR&run=42&lens=board|week|day|month|term|agenda
          &week=7&day=3&subject=room:12|instructor:45|cohort:118-2|section:991
          &b=A,C&fac=3,5&tags=PC&status=conflict&density=standard&zoom=3&compare=41
```
All of it is URL state (`nuqs`), so every view is linkable. Selection is not URL state (it is ephemeral); the selected event id is (`&sel=8812`), so links can deep-link to an inspector.

| Lens (TR / EN) | Rows × columns | Question it answers | Default for |
|---|---|---|---|
| **Pano / Board**, sub-mode **Gün** (day) | 18 periods × N rooms (one day) | "What is in each room on Wednesday?" Exactly the Excel sheet. | Planner (ADMIN/PLANNER) |
| **Pano / Board**, sub-mode **Hafta şeridi** (week strip) | N rooms × (7 days × 18 periods) | "Where are the holes this week?" | |
| **Hafta / Week** | 18 periods × 7 days, for **one subject** | "What does A 204 / Dr. Kaya / Eczacılık 2. sınıf / BME 419 §1 look like this week?" The Apple Calendar week. | Viewer, faculty secretary |
| **Gün / Day timeline** | N rooms × periods (time runs horizontally), one day, now-line | "Which rooms are free right now / at 14:20?" The operational and quick-booking lens. | Front desk (CRBS-style booking) |
| **Ay / Month** | 7 × 5–6 days, occupancy heat + markers | "Which days are crowded; where are exams and holidays?" | |
| **Dönem / Term** | 14–16 weeks × 7 days heat (+ split by building) | "How does load move across the term; which weeks break?" | Dashboards, run comparison |
| **Ajanda / Agenda** | List: day, then period, then events | "What's next?" Also the phone default and the screen-reader-friendly lens. | 360 px |

**Subjects** (for Week, Agenda, and as a filter for all lenses):
- `room:<id>`: e.g. "A 204 · 156".
- `instructor:<id>`: names are normalised; the backend already returns `instructors[]`.
- `cohort:<program_id>-<year>`: e.g. "Eczacılık · 2. sınıf". Overlaps here are **cohort conflicts**.
- `section:<id>`: e.g. "BME 419 §1", a student group.
- `all`: the Week lens with no subject packs everything, so it is disabled. The toolbar shows "Bir oda, hoca veya program seçin" ("Pick a room, instructor or programme").

### 4.1 Lens switching
- Lens segmented control in capsule 2: `Pano · Hafta · Gün · Ay · Dönem · Ajanda`, shortcuts `B W D M Y A` (§12).
- Selection and focus survive a switch. If the selected event exists in the target lens, it stays selected and scrolled into view. The chip morphs with a shared `layoutId` (240 ms, motion.md "lens morph"; reduced motion: instant).
- Drill-down: Term cell → Day (Board · Gün for that date). Month cell → Board · Gün. Week-strip day header → Board · Gün. Room header in any lens → Week lens with `subject=room`. Instructor name in the inspector → Week lens for that instructor.

## 5. Layout and chrome (desktop 1440 × 900, light)

Wireframe: `wireframes/calendar-desktop.svg`.
```
┌─ shell rail 64 ─┬─ SIDEBAR (inset glass, 272) ─┬───────────── CANVAS (opaque, full-bleed) ─────────────┬─ INSPECTOR (inset glass, 360) ─┐
│ icons only on   │ 2026 Bahar ▾   Run #42 ✓ ▾   │ ╭──────────────╮ ╭─────────────────────────╮ ╭──────────╮ │ BME 419 §1                 ⋯ ✕ │
│ /timetable      │ ┌ Mart 2026        ‹ › ┐    │ │☰ ‹ Hafta 7 › │ │Pano Hafta Gün Ay Dönem Aj│ │A 204 ▾ ⌕ ⋯│ │ Biyomedikal Müh. · 3. sınıf    │
│                 │ │ H  Pt Sa Ça Pe Cu Ct Pz│    │ ╰──────────────╯ ╰─────────────────────────╯ ╰──────────╯ │ ● Yerleşti · Kilitli           │
│                 │ │ 7  16 17 18 19 20 21 22│    │ 16–22 Mart 2026  Hafta 7 · Ders        2 çakışma ▸         │ ───────────────────────────── │
│                 │ │ …  heat dots under days│    │ ┌────┬──────┬──────┬──────┬──────┬──────┬──────┬───      │ Ne zaman, nerede              │
│                 │ └────────────────────────┘    │ │Tüm │ ░░░ HAZIRLIK (dönem boyu) ░░░░░░░░░░░░░░░ │          │  Çar 13:30–15:50 (P7–P9)      │
│                 │ Görünüm                       │ │gün │ Resmî tatil: 23 Nisan                     │          │  A 204 · 156 koltuk · %65 dolu │
│                 │  Pano › Gün | Hafta şeridi    │ ├────┼──────┼──────┼──────┼──────┼──────┼──────┤          │  Haftalar ▣▣▣▣▣▣▣▣▣▣▣▣▣▣ 1–14   │
│                 │ Binalar  ☑A ☑B ☑C ☐D          │ │    │A 204 │A 203 │C 201 │A 207 │A 102 │A 201 │ …        │ Kim                            │
│                 │ Fakülteler ● Mühendislik  212 │ │    │ 156  │148 TIP│ 126 │ 120  │  96  │96 TIP│          │  102 öğrenci · Dr. Ayşe Kaya   │
│                 │            ● Tıp          188 │ │08:30│▌BME 217                                       │ Neden burada  [Açıkla]         │
│                 │            ● Sağlık B.    140 │ │09:20│▌49/156                                        │  ✓ İstenen bina A              │
│                 │ Etiket  TIP · PC · Lab        │ │ …  │                                                 │  ✓ Kapasite uyumu %65          │
│                 │ Durum   ⚠ Çakışma 2 · Kısmi 21│ │13:30│▌BME 419  ▌FTR 412 ▌NUT 418 ▌CSE 225           │ Kaynak                         │
│                 │ Yerleşmeyenler (21)  ▸        │ │ —— 13:47 ───────────────── now-line (today) ──── │  Bahar Derslik Planlama v5     │
│                 │ Karşılaştır: Run #41 ▾        │ │ …  │                                                 │  Sayfa1 · satır 412            │
│                 │ Lejant ▸                      │ │22:10│                                                │ Geçmiş ▸                       │
│                 │                               │ ╰─ week scrubber capsule: ‹ W1 ▮▮▮▮▮▮[W7]▮▮▮▮▮▮▮ W14 › Bugün ─╯ │ [Taşı…] [Kilidi aç]            │
└─────────────────┴───────────────────────────────┴─────────────────────────────────────────────────────────┴────────────────────────────────┘
```

### 5.1 Capsule toolbar (floating, glass; macOS 26 toolbar grouping)
- Three capsules, 12 px from the canvas top. Height 44 px with pointer, 48 px on touch. Radius `full`. Gap 8 px. Capsule 1 is left-aligned, capsule 2 centred, capsule 3 right-aligned. Material: liquid-glass.md **regular glass** (role `glass/regular`; see §8.2).
  1. **Navigate**: sidebar toggle · `‹` · range title button ("Hafta 7", opens the mini-month popover, #11) · `›` · **Bugün**.
  2. **Lens**: segmented control with a glass thumb (a raised, lighter glass lozenge; no saturated fill). The Board button carries a tiny chevron menu: Gün / Hafta şeridi.
  3. **Subject and actions**: subject picker ("A 204 ▾" or "Tümü"), search (⌘K), issue capsule (only when > 0: "2 çakışma · 5 uyarı", red/amber glyph + text), undo/redo (shown only when the stack is non-empty), `⋯` menu (Karşılaştır…, Yoğunluk, Hafta sonu, Akşam saatleri, Dışa aktar, Yazdır, Lejant).
- **Scroll behaviour**: when the canvas scrolls down more than 24 px, the capsules shrink to 36 px and drop their text labels (icons + "Hafta 7" stay). This follows the iOS 26 tab bar shrink. 240 ms, motion.md "chrome-condense"; reduced motion: no shrink.
- The **canvas title row** (not glass): "16–22 Mart 2026" at 22/28 semibold, then "Hafta 7 · Ders" (week type: Ders / Final / BÜT / Tatil) at 13/18 `--fg-muted`. It sits under the capsules and scrolls with the content in Month/Term/Agenda; it is sticky in the time-grid lenses.

### 5.2 Sidebar (inset glass panel, 272 px)
Inset 8 px from the window edges, radius 20 (concentric with the 12 px chip radius inside at 8 px padding). It floats over the canvas edge on < 1600 px and pushes the canvas on ≥ 1600 px. Sections, top to bottom:
1. **Term and run**: "2026 Bahar ▾" · "Run #42 ✓ Uygulanabilir ▾" (lists runs with status glyph, objective, created time; "Aktif" badge on the activated run).
2. **Mini-month** (react-day-picker): week numbers in the left column (term weeks "7", not ISO), today as a filled accent circle, the selected range as a glass-tint row, and one **heat dot** under each day (3 sizes: < 40 %, 40–75 %, > 75 % occupancy; tooltip "%72 dolu · 2 çakışma"). Holidays have their number struck through in `--fg-subtle`; exam weeks carry a tiny "S" under the week number.
3. **Filters** (Wix #25 accordions; each has a count and a reset ↺):
   - Binalar: A B C D checkboxes with room counts.
   - Fakülteler: colour swatch + name + meeting count, from the faculty palette. `⌥`-click isolates one faculty (Apple Calendar "show only this calendar").
   - Etiketler: TIP · PC · Lab · Amfi.
   - Durum: Çakışma · Uyarı · Kilitli · Kısmi · Önceden dolu · Rezervasyon.
   - Kapasite ≥ (slider snapping to the room-master buckets 30/40/58/64/72/96/120/156).
   - Mod: Yüz yüze · Hibrit · Simülasyon (online/UZEM have no room, so they are hidden from the calendar and listed in All classes).
4. **Yerleşmeyenler (21)**: an unplaced tray of dashed chips, draggable onto the canvas (§9.2). Its count matches the run's FEASIBLE_PARTIAL summary.
5. **Karşılaştır**: compare run picker plus a toggle "Hayalet katmanı göster" (§9.9).
6. **Lejant**: an inline legend of every state from §7.3, with the real chip rendering, not swatches.
Collapsed with `⌘⌥S` or the ☰ button. On < 1280 it becomes a popover from ☰.

### 5.3 Inspector (inset glass panel, 360 px; bottom sheet on phones)
Non-modal: the grid stays interactive and the inspector follows the selection. It is shared with all-classes.md §9 (same component, `ClassInspector`). Sections:
1. **Header**: faculty bar · code 17/22 semibold · course name · programme · year · status line with glyph + text ("Yerleşti · Kilitli", "Çakışıyor: A 204 Çar P8 ENG 102", "Kısmi: 12/14 hafta"). Icon actions: Kilitle/Kilidi aç · Taşı… · ⋯ (Kopyala, Kurala dönüştür, Sohbette aç, Tüm derslerde göster).
2. **Ne zaman, nerede**: room combobox (rooms sorted by fit, each with capacity and a "%65" fit figure; incompatible rooms disabled with a reason), day select, period range picker ("P7–P9 · 13:30–15:50"), a week pattern of 14 (or 16) toggle squares, and the scope radio for edits (Tüm haftalar / Sadece bu hafta / Bu haftadan itibaren). Edits commit through the same Move flow as drag (§9.2).
3. **Kim**: enrolment vs capacity ("102 / 156"), instructors (each a link to their Week lens), programme/year (links to the cohort Week lens), section.
4. **Neden burada** (why here): the solver check list (✓/✕/–): requested room/building honoured, capacity fit, tags (PC/TIP), same room all weeks, instructor free, cohort free. Button **Yerleşimi açıkla** (Explain placement) streams a TR/EN paragraph (§17: needs a per-assignment explain endpoint).
5. **Kaynak** (provenance): file name, sheet, row ("Bahar Derslik Planlama Listesi v5.xlsx · Sayfa1 · satır 412"), raw request text in a muted quote ("C 301 veya C 302"), Excel cell comment if imported from the grid ("23 şubat dahil a 206 a geçecek"). "Dosyayı aç" downloads the source (`GET /imports/{id}/file`).
6. **Geçmiş** (history): moves and locks with who/when and per-entry "Geri al".
Empty selection: the inspector collapses. With multi-selection it shows the **selection summary** instead ("6 ders seçili · 412 öğrenci · 3 bina"), with bulk actions (Kilitle, Taşı…, Karşılaştırmada göster, Tüm derslerde aç).

### 5.4 Week scrubber (bottom floating capsule)
- Centred, 16 px above the bottom edge, height 44. Contents: `‹`, then 14 week ticks (or 16 with exam weeks, which get a different tick shape: a hollow square), then `›`, then **Bugün**.
- Each tick is 20 × 24 px with a vertical heat fill (sequential scale step) showing that week's occupancy; holiday weeks are hatched; the current week has a thumb (raised glass lozenge) and the label "H7" above it.
- **Scrub**: press and drag along the ticks. The canvas swaps weeks live (data is already in the index, so there is no fetch). A floating label shows "Hafta 9 · 30 Mar–5 Nis". Arrow keys move one week when focused; `Home`/`End` go to the first/last week.
- Brushing (⇧-drag) selects a week range, used by Compare (diff only those weeks), Export, and "Bu haftalar için kilitle".
- Hidden in Month/Term (they already show all weeks); in Agenda it becomes a date strip.

## 6. Lens specs

### 6.1 Pano · Gün (Board, day): the Excel sheet
- Rows: P1…P18. Row height = density (§14). P12 renders at 0.6× height with "17:30" and a tooltip "30 dk geçiş".
- Columns: rooms in the planner's order (building bands A → B → C → D, then capacity descending inside each building, the Excel order). Column width 120 (standard). Sticky room header 48 px: "A 204" (13/16 semibold), and "156" plus a TIP/PC tag glyph in 11/14 `--fg-muted`. In exam weeks the header shows the exam capacity "74 sınav".
- **Building bands**: a 24 px glass-tint strip above the room headers ("A Blok · 28 oda"), clickable to collapse the building into a single 32 px column showing a stacked occupancy bar. Persisted per user.
- The time gutter is 56 px and sticky left: "13:30" in 11/14 tabular `--fg-subtle`, and the current period's label in accent.
- **All-day band** (§7.5) sits above P1, sticky with the header, collapsible.
- Empty cells show nothing at rest. On hover, a faint "+" appears at the cell centre; drag-to-create starts here (§9.4).

### 6.2 Pano · Hafta şeridi (Board, week strip)
- Rows: rooms (row height 32 standard / 24 compact), with building bands as sticky row groups.
- Columns: 7 day groups × 18 period slots. Slot width depends on zoom: 6 px at zoom 1, then 10, 14, 20 (default), 28. At ≥ 14 px the chip shows its code (truncated); below that, only a filled bar plus a tooltip.
- Per-day **totals row** (Square #22), sticky at the top: "%72" occupancy and the conflict count per day.
- Weekend groups collapse to 24 px when they have no events (Auto setting).

### 6.3 Hafta (Week, one subject): the Apple Calendar week
- Columns: Pzt…Paz (weekend auto-hidden when empty). Day header: "Çar 18" with today as an accent number in a filled circle (A1). Rows: P1–P18.
- Overlapping events (the subject is in two places at once) are laid out side by side. For a room, instructor or cohort subject an overlap is **always a conflict**, so both chips get the conflict treatment and a red bracket on the left of the pair.
- Subject header (left of the title): avatar-less, text only, e.g. "A 204 · 156 koltuk · TIP" or "Dr. Ayşe Kaya · 14 ders · 31 saat/hafta" or "Eczacılık 2. sınıf · 9 ders · 3 bina".
- **Free-slot hint** (rooms only): free periods ≥ 2 long show a hairline outline on hover, labelled "Boş · 3 ders saati", which helps quick booking.

### 6.4 Gün (Day timeline, rooms × time): operations and booking
- Rows: rooms (40 px), grouped by building. Columns: time, **proportional** (minutes, not periods), 08:30–22:50, with period ticks; 1 minute = 1.4 px at standard zoom, so 860 min ≈ 1,204 px.
- **Now-line**: a vertical 2 px red line through all rows, with a time capsule ("13:47") at the top. Past time is shaded with a 4 % neutral overlay.
- Free-now filter: "Şu an boş" (Free now) toggles rooms with no event in the current period to the top; "≥ 60 kişi" (60+ seats) and "PC" chips make the classic front-desk question one click.
- **Sıradaki** (Up Next) panel on ≥ 1920 or as a sidebar section: the next 2 periods across the filtered rooms, as in Apple's Up Next.
- This is the lens where **quick booking** (CRBS parity) is fastest: drag across a free range in a room row, then the popover (§9.4).

### 6.5 Ay (Month): occupancy heat
- Grid: 7 columns × 5–6 rows; term week numbers in the left gutter ("H7"). The cell is ≥ 112 × 96 px at 1440.
- Cell content: day number (top-left; accent circle for today), **occupancy %** large (20/24 semibold tabular) at bottom-left, and up to 2 marker lines: "Sınav: 14", "Tatil", "2 çakışma" (red glyph). Fill = sequential heat step (tokens §2.5) at **40 % strength** over `--bg`. All text inside heat cells is `--fg`, never `--fg-muted` (computed in §15: `--fg` is ≥ 8.28:1 light and ≥ 5.63:1 dark on every step; muted drops to 3.51 / 2.75 on the top steps).
- Days outside the term are `--surface-2` with a dot pattern ("no data", never step 1).
- Legend capsule bottom-right: "%0 · 1–25 · 26–50 · 51–75 · 76–100", with a popover to switch the metric: Doluluk / Çakışma / Yerleşmeyen / Değişiklik (vs compare run).

### 6.6 Dönem (Term): 14 weeks × days heat calendar
Wireframe: `wireframes/calendar-term-heat.svg`.
- Rows W1…W14 (plus F1, F2, BÜT when the term has exam weeks; separated by an 8 px gap and labelled), columns Pzt…Paz. Cells 40 × 32 px, radius 6, 3 px gap. The whole term fits in 330 px of height.
- Row label: "H7 · 16 Mar" plus a week-type chip. Right column: a weekly mini bar ("%68"). Bottom row: per-weekday average.
- **Metric switch** (segmented, top-right): Doluluk (occupancy %) · Çakışma (count) · Yerleşmeyen (count) · Değişiklik (moved vs compare run). Each uses the sequential scale except the comparison metric, which uses the diverging pair (tokens §2.5) and is always labelled with numbers, never colour alone.
- **Böl: Bina** (split by building) shows 4 small multiples A/B/C/D side by side (at 1440 each is 7 × 22 px cells), sharing one scale.
- Interactions: hover shows a tooltip "Hafta 7 · Çar 18 Mart · %72 dolu (942/1.296 oda-ders saati) · 2 çakışma"; click drills into Board · Gün for that date; ⇧-drag brushes a week range (Turo #23), which sets `&weeks=5-9` for Compare, Export and bulk lock.
- Values: occupancy = occupied room-periods ÷ (bookable rooms × 18) for that date. Pre-occupied blocks count as occupied, and the tooltip splits "%58 ders + %14 önceden dolu".

### 6.7 Ajanda (Agenda) and Up Next
- A virtualised list: day header (sticky glass: "Çarşamba, 18 Mart · Hafta 7"), then period subheaders ("13:30 · P7"), then event rows.
- Row: faculty bar · code (semibold) · course name (`--fg-muted`, truncated) · room · "P7–P9" · status glyph. Height 44 (touch 52).
- When the date is today, the top section is **Şimdi** (Now: running events with a progress hairline) followed by **Sıradaki** (Up next).
- It scrolls infinitely across the term. The date strip (phone) or the scrubber (desktop) jumps.

## 7. Visual language

### 7.1 Layers (back to front)
1. **Canvas** (opaque `--bg`): grid lines are 1 px hairlines `rgba(var(--fg-rgb), .08)` for period lines and `.14` for day/building separators; no zebra striping.
2. **Content**: chips, bands, heat cells. Opaque tinted fills, no blur.
3. **Overlay content**: now-line, selection rings, drag ghost, compare ghosts, lasso rectangle.
4. **Chrome (glass)**: capsules, sidebar, inspector, scrubber.
5. **Transient glass**: popovers, menus, ⌘K, toasts, bulk bar.

### 7.2 Event chip anatomy (Apple Calendar-style)
```
╭──────────────────────────────╮
▌ BME 419                    🔒 │  code 12/16 w600 in faculty INK · state glyph 12 px right
▌ A 204 · 102/156              │  11/14 w400 ink at 80 % (shown at h ≥ 2 rows)
▌ Dr. Ayşe Kaya                │  11/14 (h ≥ 3 rows)
▌ 13:30–15:50                  │  11/14 tabular (h ≥ 3 rows, bottom-aligned)
╰──────────────────────────────╯
```
- Fill: faculty **fill** (14 % hue over white, or 26 % over the dark bg; §8.1). Bar: 3 px faculty hue, inset 2 px top/bottom, radius 2. Text: faculty **ink** (contrast ≥ 5.0:1 on its fill, computed below). No border and no shadow at rest. Radius 6. Inner padding 4/6 px. 1 px gap between stacked chips.
- Content by height. At 1 row only the code and glyph show; a tooltip carries the rest. In the week strip below 14 px wide, only the fill and bar show.
- Evening (İÖ) programmes get a 12 px moon glyph after the code. Combined lectures ("HEM 334 / NRS 304") show the first code plus a "+1" capsule.
- Exam weeks: chips show a pencil glyph and the size uses the exam capacity ("70/74 sınav").
- **CRBS-style booking** chips use a neutral fill (`--surface-2`), a `--fg-muted` 3 px bar, text "Rezervasyon · Kimya Böl." and a calendar-user glyph. They are never faculty-coloured, so a booking is never mistaken for a class.

### 7.3 States (each has icon + text + shape; colour is never the only cue)

| State (TR / EN) | Visual | Text/aria suffix |
|---|---|---|
| Yerleşti / Placed | default chip | — |
| Seçili / Selected | 2 px ring in the faculty **bar** colour, offset 1 px, plus a 1 px inner white (light) / black (dark) halo; elevation 1. The fill stays tinted, because white text fails on blue (4.42:1) and yellow (2.17:1); see §8.1. | "seçili" |
| Odak / Focused (keyboard) | 2 px `--focus` ring, 2 px offset (outside the selection ring when both apply) | — |
| Çakışma / Conflict (hard) | 1.5 px `--status-infeasible-border` inset ring, a red triangle glyph replacing the state glyph, a 10 % red wash over the fill; colliding chips pulse once (2 × 150 ms) | "çakışma: {neden}" |
| Çift rezervasyon / Double booking (same room+period) | the cell splits into side-by-side half-width chips joined by a red bracket and a "2" capsule | "2 ders aynı odada" |
| Uyarı / Warning (soft; e.g. capacity 102/96, building mismatch) | amber dot glyph; the second line shows the reason ("96 koltuk < 102") in amber ink | "uyarı: …" |
| Kilitli / Locked | lock glyph (12 px), and the bar becomes 3 px **double** (two 1 px lines), a shape cue that survives grayscale | "kilitli" |
| Kısmi / Partial (placed some weeks, or split rooms) | a 14-tick week-pattern micro-bar along the bottom edge (filled = placed weeks) and a half-circle glyph; split rooms show "A 101 +2" | "kısmi: 12/14 hafta" |
| Yerleşmedi / Unplaced | only in the unplaced tray and All classes: dashed 1 px outline in ink, no fill | "yerleşmedi" |
| Önceden dolu / Pre-occupied (HAZIRLIK, UZEM, ETKİNLİK, imported blocks) | **hatched frost**: `--surface` at 72 % with 45° hatch lines (1 px at 10 % `--fg`, 6 px pitch), a 1 px top inner highlight (white 40 % light / 8 % dark) so it reads as frosted glass; label in 10/12 caps `--fg-muted`. No backdrop blur (hundreds of blocks; performance and HIG §1). | "önceden dolu: HAZIRLIK" |
| Kaydediliyor / Saving | 60 % opacity plus a 10 px spinner in the glyph slot | "kaydediliyor" |
| Kaydedilemedi / Save failed | snaps back (spring) plus a red outline that fades after 2 s; toast with "Tekrar dene" | — |
| Karşılaştırma hayaleti / Compare ghost | 1 px dashed outline in `--fg-subtle`, no fill, label "Run #41" in 10 px; with a moved counterpart an arrow glyph "↔" on the live chip | "Run #41'de: A 102 Sal P3" |
| Yeni (compare) / Only in this run | a small "+" capsule on the chip's corner | "yalnız bu çalıştırmada" |
| Geçmiş / Past (Day timeline today only) | fill desaturated to 60 % | — |
| Salt okunur / Read-only | no hover "+", no resize handles, default cursor | — |

### 7.4 Now-line
- Colour: system red (`--now`: `#FF3B30` light / `#FF453A` dark, the Apple systemRed values). 2 px across **today's column only** in Week; across all room columns in Board · Gün when the day is today; vertical in Day timeline.
- In the gutter, a red capsule with the time "13:47" (11/14 semibold). White on `#FF3B30` is only 3.55:1, so the capsule uses `--now-strong`: light `#D70015` (Apple's high-contrast systemRed) with white text at 5.38:1; dark `#FF453A` with `#0B1220` text at 5.50:1. The line itself stays `--now` (non-text; 3.55:1 light, 5.50:1 dark against `--bg`, both ≥ 3:1).
- In period lenses its position is interpolated inside the period (13:47 is 17/40 of P7). During a 10-minute break it sits in the gap between rows.
- Updates every 60 s with no animation.

### 7.5 All-day and term-long bands
- A band row above P1 ("Tüm gün", sticky): holiday banners ("Resmî tatil · 23 Nisan", hatched across all columns), exam-day markers, room closures ("C 601 kapalı · bakım"), CRBS all-day bookings, and **term-long blocks**, e.g. HAZIRLIK booked every weekday 08:30–12:30 in B 202–B 206. These are summarised as one bar per room ("HAZIRLIK · P1–P5 · dönem boyu") so the grid below can show them as hatched cells without repeating the label 70 times.
- At most 2 visible rows, then a "+3" capsule that expands the band (Workable #20 dashed spanning bar for multi-day items).

### 7.6 Period axis and density
| Density (TR / EN) | Row h | Room col w | Chip text |
|---|---|---|---|
| Sıkı / Compact | 28 | 96 | code only |
| Standart / Standard | 40 | 120 | code + line 2 |
| Rahat / Comfortable | 52 | 152 | all 4 lines at ≥ 2 rows |

Zoom (§9.7) scales row height in 5 steps (24/32/40/52/64) and is independent of density, which sets paddings and type.

## 8. Tokens (consumed; source of truth in parentheses)

### 8.1 Faculty chip colours: fill / ink / bar (computed 2026-10-08, WCAG relative luminance; script in §15)

Light (fill = 14 % hue over `#FFFFFF`; ink = hue darkened until ≥ 5.0:1 on the fill):

| Slot | Bar (tokens §2.3) | `--fac-N-fill` | `--fac-N-ink` | Ink on fill |
|---|---|---|---|---|
| 1 blue · Mühendislik | `#2a78d6` | `#E1ECF9` | `#2262AF` | 5.09 |
| 2 orange · Tıp | `#eb6834` | `#FCEAE3` | `#A44924` | 5.05 |
| 3 aqua · Sağlık B. | `#1baf7a` | `#DFF4EC` | `#127351` | 5.05 |
| 4 yellow · İİBF | `#eda100` | `#FCF2DB` | `#8C5F00` | 5.03 |
| 5 magenta · Hukuk | `#e87ba4` | `#FCEDF2` | `#97506B` | 5.04 |
| 6 green · Fen-Edebiyat | `#008300` | `#DBEEDB` | `#007200` | 5.06 |
| 7 violet · Eğitim | `#4a3aa7` | `#E6E3F3` | `#4A3AA7` | 6.79 |
| 8 red · Diğer | `#e34948` | `#FBE6E5` | `#AF3837` | 5.08 |

Dark (fill = 26 % hue over `#0B1220`; ink = hue lightened until ≥ 5.0:1):

| Slot | Bar | Fill | Ink | Ink on fill |
|---|---|---|---|---|
| 1 | `#3987e5` | `#173053` | `#67A3EB` | 5.01 |
| 2 | `#d95926` | `#412422` | `#E2815A` | 5.00 |
| 3 | `#199e70` | `#0F3635` | `#49B28E` | 5.03 |
| 4 | `#c98500` | `#3C3018` | `#D19726` | 5.03 |
| 5 | `#d55181` | `#402239` | `#E07DA0` | 5.02 |
| 6 | `#008300` | `#082F18` | `#52AB52` | 5.07 |
| 7 | `#9085e9` | `#2E3054` | `#A39AED` | 5.04 |
| 8 | `#e66767` | `#442832` | `#EA8282` | 5.04 |

Why selection is a ring and not a solid fill: white on the solid hue is 4.42 (blue), 3.20 (orange), 2.82 (aqua), 2.17 (yellow), 2.69 (magenta), 4.95 (green), 8.56 (violet), 3.95 (red). Six of eight fail, so Apple's "selected = solid" would need per-hue text rules. A ring keeps one rule.

Other colours: `--now` (above); `--booking-fill` = `--surface-2`; `--ghost-stroke` = `--fg-subtle`; conflict, warning and locked come from the status tokens in tokens §2.2; heat from §2.5.

### 8.2 Glass roles (names resolve to `liquid-glass.md`; if a name differs, liquid-glass.md wins)
| Role | Used by | Requirement from this spec |
|---|---|---|
| `glass/regular` | capsules, scrubber, sidebar, inspector | Effective tint ≥ 72 % opacity in light and dark, because `--fg-muted` text must stay ≥ 4.5:1 over the most saturated chip behind it (§15). Blur radius per liquid-glass.md. |
| `glass/thin` (clear) | sticky day headers, building bands, Agenda day headers | Primary text only (`--fg`) at ≥ 64 % tint; no muted text on it |
| `glass/thumb` | the segmented-control thumb, scrubber thumb | Lighter than the capsule (+8 % white in light, +6 % white in dark), plus a 0.5 px highlight stroke |
| `glass/popover` | popovers, menus, ⌘K, quick-create, toasts | ≥ 80 % tint (it carries form controls and muted helper text) |
| Fallback | `prefers-reduced-transparency: reduce`, `forced-colors: active`, or the in-app "Saydamlığı azalt" | Solid `--surface-raised` plus a 1 px `--border-strong`; no blur |

### 8.3 Spacing and sizes
Capsule height 44 (touch 48), capsule gap 8, inset from the canvas edge 12. Sidebar 272, inspector 360, both inset 8 with radius 20. Chip radius 6, chip padding 4/6, stacked chip gap 1. Gutter 56. Room header 48. Building band 24. All-day band 22 per row. Scrubber tick 20 × 24. Month cell ≥ 112 × 96. Term cell 40 × 32 (gap 3). Touch targets ≥ 44 × 44: on touch, resize handles grow to 16 px hit areas that are invisible until selected.

### 8.4 Motion (durations here; curves and springs live in `motion.md`; ceiling 300 ms)
| Moment | Duration | Curve (motion.md / tokens §6) | Reduced motion |
|---|---|---|---|
| Chip hover, focus ring, selection ring | 120 ms | `--ease-out` | instant |
| Drag lift (scale 1.02 + elevation 2) | 120 ms | `--ease-out` | no scale, elevation only |
| Magnet snap to slot | 120 ms | `--ease-out` | instant |
| Drop settle / spring-back on invalid | ≈ 240 ms | `--spring-drop` | instant |
| Conflict pulse on culprits | 2 × 150 ms | `--ease-in-out` | static red ring |
| Popover / quick-create open (scale .96 → 1 + fade) | 180 ms in, 120 ms out | `--ease-emphasized` | fade ≤ 100 ms |
| Inspector / bottom sheet in | ≤ 300 ms | `--spring-sheet` | fade 100 ms |
| Lens switch (cross-fade + selected chip `layoutId` morph) | 240 ms | `--ease-in-out` | instant |
| Week change (scrubber, `[` `]`) | 180 ms content cross-fade, horizontal offset 12 px | `--ease-out` | instant |
| Capsule condense on scroll | 240 ms | `--ease-in-out` | none |
| Scrubber thumb travel | ≈ 240 ms | `--spring-drop` | instant |
| Heat cells on metric change | 180 ms colour cross-fade, **no stagger** | linear | instant |
| Toast / undo | sonner default (≤ 300 ms) | — | fade |
| Zoom step | 180 ms row-height interpolation, anchored at the pointer | `--ease-out` | instant |

Never animate: the now-line, scroll position (except keyboard `scrollIntoView` when motion is allowed), counts in the capsules (they swap; no tickers on a working surface), or heat-cell cascades.

## 9. Interactions

### 9.1 Selection, multi-select, lasso
- Click a chip to select it and open the inspector. `⌘`-click (Ctrl on Windows/Linux) toggles a chip in the selection. `⇧`-click extends the selection to all chips in the rectangle between the anchor and the clicked chip (same lens).
- **Lasso**: `⇧`-drag starting on empty canvas draws a 1 px accent rectangle with a 6 % accent fill and selects every chip it intersects, live. A plain drag on empty canvas creates instead (§9.4; Apple Calendar behaviour). On touch: the **Seç** (Select) button in capsule 3 enters select mode, where taps toggle chips and a drag lassos.
- `⌘A` selects everything visible under the current filters (capped at 500, with a toast if more). `Esc` clears.
- The selection count shows in the inspector header and is announced politely ("6 ders seçildi").

### 9.2 Drag to move (single or multi), with slot magnetism and live conflict preview
- Lift: pointer down plus 6 px movement (touch: 250 ms long-press, tolerance 8 px). The original stays at 40 % with a dashed outline; the ghost (DragOverlay) gets elevation 2 and scale 1.02.
- **Magnetism** (two levels):
  1. *Edge snap*: the ghost's top edge snaps to the nearest period boundary, and its column to the nearest room/day, once within 12 px (120 ms ease). It never rests between periods.
  2. *Valid-slot pull*: if the hovered target is invalid, the nearest valid slot **in the same room and day** (search ±3 periods) gets a hairline accent outline labelled "Boş: P10–P12". Releasing with `⌥` held, or pausing 600 ms over the invalid target, moves the ghost there with a 120 ms magnet animation. It never auto-drops; the user still releases.
- **Live conflict preview** (on every `dragover`, rAF-throttled, < 1 ms pure `checkMove` against the index, §13):
  - Valid target: 2 px accent outline over the target span, and a glass reason capsule under the ghost: "A 101 · Çar P7–P9 · 58 koltuk ✓".
  - Hard conflict: dashed red outline, capsule "✕ ENG 102 ile çakışıyor (A 101 Çar P8)". The culprit chips get a red ring and pulse once.
  - Soft issue: amber outline, capsule "⚠ 58 koltuk < 102 öğrenci".
  - Checks: room overlap in any of the event's weeks; **instructor** overlap; **cohort** (programme+year) overlap; capacity (lecture or exam); TIP room without release; PC requirement; pre-occupied; locked event; span beyond P18; P12 inside the span (warning).
- Drop on valid: optimistic move, then the **Move popover** (v1 §4.2: new vs old, scope radio, soft warnings, Kaydet/Geri al; auto-save after 4 s; `Enter`/`Esc`). `⇧`-drop skips the popover and applies to all weeks.
- Drop on a hard conflict: spring back; toast "Taşınamadı: ENG 102 ile çakışıyor" with "Yine de taşı" (Planner only; sends `force: true`). Then the event shows the conflict state.
- **Multi-move**: dragging any selected chip moves the whole selection, preserving relative room/period offsets. Each ghost is validated separately. The capsule summarises "6 ders · 5 uygun · 1 çakışma". On drop the Move popover lists the conflicting item with "Atla / Yine de taşı". Committed as one undo entry. (Backend: a bulk endpoint with atomic semantics is needed; until then, sequential `move` calls with client rollback, §17.)
- **Unplaced tray to canvas**: dragging a dashed tray chip onto the grid creates an assignment with the same preview and popover (backend needed: create assignment).
- Server: `POST /runs/{run_id}/assignments/{aid}/move` with `{day, start_period, end_period, room_ids, week?, force}`. A 409 or `ok: false` with `conflicts[]` triggers a revert and toast with the server's reason. A `dry_run` flag is requested (§17) so the popover can show server-confirmed soft deltas.

### 9.3 Resize
Top and bottom edge handles: 6 px visible on hover/selection, 16 px hit area on touch. They snap per period and use the same preview and checks. The capsule reads "P7–P10 · 13:30–16:40 · +1 ders saati". Commits through Move (changed `end_period`/`start_period`). Duration below 1 period is not possible. P12 inside the new span shows the warning.

### 9.4 Quick-create (click-drag on empty slots): booking or meeting request
- Drag vertically (Board · Gün, Week) or horizontally (Day timeline) across empty cells. A dashed accent selection block shows its live label "A 204 · Çar 13:30–15:50 (3 ders saati)" (Superhuman #16). A single click on an empty cell selects one period. Pressing `N` with focus on an empty cell does the same from the keyboard.
- Release opens a glass **quick-create popover** anchored to the block (ClickUp #15), with a segmented control at the top:
  - **Rezervasyon** (Booking, CRBS-style; default in the Day timeline): Başlık (title), Kim adına (department/user; defaults to me), Tekrar (recurrence: this week only / weeks 1–14 / custom week set via the 14-square picker), Not. Primary button "Rezerve et ⌘↵". Creates a booking through the CRBS-parity bookings API (backend-engineer, `docs/CRBS_PARITY.md`, §17).
  - **Ders talebi** (Meeting request; default in Board/Week): a search field "Ders ara…" over **unplaced** sections first ("Yerleşmeyenler (21)"), then all sections; or "Yeni talep" (course code, programme, year, enrolment). Options: "Bu odaya sabitle" (pin room) and "Bu saate sabitle" (pin time), which create `room_pin` / `fixed_time` constraints. Primary "Yerleştir ⌘↵" places it (backend needed: create assignment) or saves the request for the next run ("Sonraki çalıştırmada yerleştir").
- Typing a course code right after the drag (with no click) jumps into the Ders talebi search (Fibery #17 title-in-place).
- Live validity stays visible in the popover header ("✓ 156 koltuk · boş"). If the range overlaps a pre-occupied block, the popover offers "Önceden dolu bloğu kaldır" (admin only).
- `Esc` cancels and removes the block. Creation is one undo entry.

### 9.5 Inspector edit
Every field in the inspector edits in place. Room, day, periods and weeks go through Move (with preview and the scope radio); lock goes through `POST /runs/{run_id}/assignments/{aid}/lock?locked=`; request-level fields (enrolment, preferred rooms) go through `PUT /requests/meetings/{id}` and show "Sonraki çalıştırmada etkili" (applies on the next run). Save state appears in the header ("Kaydedildi" for 1 s). Errors show inline under the field.

### 9.6 Week scrubber
§5.4. Also `[` / `]` for previous/next week, `⇧[` / `⇧]` for ±4 weeks, `T` for today. Holiday weeks are scrubbable and render the hatched band "Tatil haftası".

### 9.7 Zoom
- Touch: pinch on the canvas scales row height (vertical pinch) or column width (horizontal pinch), snapping to the 5 steps on release; the focal point stays under the fingers.
- macOS: `⌘`+scroll and trackpad pinch (which arrives as `wheel` with `ctrlKey`) inside the canvas. Windows/Linux: `Ctrl`+scroll inside the canvas only. We `preventDefault` only while the pointer is over the canvas; **browser zoom (`⌘+`/`⌘−`, `Ctrl+`/`Ctrl−`) is never intercepted**, for accessibility.
- Keyboard: `+` / `−` (no modifier) while the canvas has focus, and `0` to reset to standard.
- A zoom level indicator appears for 1 s as a small glass capsule ("Yakınlık 4/5").

### 9.8 Jump-to (⌘K)
- Registers a "Takvimde git" (Go to in calendar) scope in the shell command palette (navigation-shell.md). Groups: Odalar, Dersler, Öğretim elemanları, Programlar, Haftalar/Tarihler, Eylemler.
- Grammar: "A 204", "a204", "BME 419", "kaya", "eczacılık 2", "h7" or "hafta 7", "18 mart", "yarın", "şimdi", and combinations ("A 204 perşembe" opens the Week lens for A 204 and scrolls to Thursday). Turkish casefold (İ/ı) and diacritic-insensitive matching.
- Eylemler: "Run #41 ile karşılaştır", "Dönem görünümüne geç", "Yoğunluk: Sıkı", "Excel'e aktar".
- The footer states "Gezinme hiçbir şeyi değiştirmez" ("Navigating never changes anything"; Clockwise #26).

### 9.9 Compare two runs (ghost overlay)
- Toolbar `⋯ › Karşılaştır…` or the sidebar picker: choose Run B. The current run (A) renders normally; B's placements render as **ghosts** (§7.3) only where they differ.
- Matching key: `meeting_request_id` (or `exam_request_id`) plus week. Categories: *Same* (no ghost), *Moved* (ghost at B's position, "↔" on A's chip, and a hairline connector drawn on hover/selection only), *Only in A* ("+" capsule), *Only in B* (ghost with "−").
- Summary capsule (replaces the issue capsule while comparing): "Run #41 ile: 37 taşındı · 4 yalnız burada · 2 yalnız orada", with each number a filter toggle. "Karşılaştırmayı kapat ✕".
- Term and Month lenses switch their metric to **Değişiklik** (changes) automatically.
- Data: `GET /runs/{a}/assignments` and `GET /runs/{b}/assignments` (whole term, once each); the diff runs in the worker. An optional `GET /runs/{id}/diff?against=` is listed in §17.

### 9.10 Undo / redo
- A client stack (Zustand), up to 100 entries, holding `{label, forward(), inverse()}` for move, resize, multi-move, lock, create booking, create placement and inspector edits. It is per run and survives lens/week changes, but not reloads.
- `⌘Z` / `⌘⇧Z` (Ctrl/Ctrl+Shift, and also Ctrl+Y on Windows). The undo/redo buttons appear in capsule 3 only when available. Every mutation toasts "BME 419 A 101'e taşındı · Geri al" (6 s).
- Undo of a server mutation calls the inverse endpoint. If the inverse fails (e.g. the slot was taken meanwhile), the toast says so and the entry stays.

### 9.11 Context menu (right-click, long-press, `⇧F10`)
Aç · Taşı… · Kilitle/Kilidi aç · Yerleşimi açıkla · Tüm derslerde göster · Bu odanın haftası · Bu hocanın haftası · Bu programın haftası · Karşılaştırmada göster · Kopyala (kod) · Yerleşimi kaldır (unassign; confirm).

### 9.12 Touch summary
Tap selects and opens the sheet. Long-press lifts for a move. On empty space, long-press creates. Pinch zooms. Two-finger pan scrolls. Swipe on the scrubber or the date strip changes week. No hover-dependent information: the tooltips' content is in the sheet.

## 10. States (whole surface)

| State | Trigger | Treatment (TR copy) |
|---|---|---|
| Loading (first) | no index yet | Chrome renders immediately (capsules, sidebar with skeleton lines). The canvas shows the empty grid lines and the title; a single small spinner sits in capsule 1 ("Yükleniyor"). No chip skeleton cascade. |
| Loading (week) | never; the data is term-wide in memory | — |
| Empty: no run | term has no run | Centre of canvas: "Bu dönem için henüz bir program yok." with buttons **Program oluştur** (/generate) · **Excel'den içe aktar** (/import). No illustration. |
| Empty: filtered out | filters hide everything | "Bu filtrelerle gösterilecek ders yok." plus **Filtreleri temizle** and a list of the active filters as removable chips |
| Empty: subject has no events | Week lens | "A 204 bu hafta boş." plus "Rezervasyon için boş bir alanı sürükleyin." |
| Partial run | FEASIBLE_PARTIAL | Issue capsule "21 yerleşmedi"; the sidebar tray opens once per session |
| Stale | a newer run finished (SSE `GET /runs/{id}/events`) | Glass banner under the capsules: "Yeni çalıştırma hazır: Run #43 · %98 yerleşti · Göster · Karşılaştır" |
| Read-only | viewer role, or a published/activated run without a draft | Capsule 3 shows a "Salt okunur" glyph; drag/create disabled; a tooltip explains why |
| Saving | a mutation is in flight | per-chip saving state; capsule 1 shows nothing (no global spinner) |
| Error: load | fetch failed | Inline glass banner in the canvas: "Program yüklenemedi. Tekrar dene". The last good data stays visible (the cache). |
| Error: mutation | 409 / 5xx | revert plus toast with the server reason and "Tekrar dene" |
| Offline | `navigator.onLine` false | Capsule 3 shows "Çevrimdışı"; edits are queued (TanStack mutation queue) with a "3 değişiklik bekliyor" capsule |
| Holiday week | `weeks.type = HOLIDAY` | hatched band across all days plus "Tatil haftası"; the grid stays usable for bookings |

## 11. Copy (TR / EN), key labels

| Key | TR | EN |
|---|---|---|
| lens.board / day / strip | Pano · Gün · Hafta şeridi | Board · Day · Week strip |
| lens.week / day / month / term / agenda | Hafta · Gün · Ay · Dönem · Ajanda | Week · Day · Month · Term · Agenda |
| nav.today | Bugün | Today |
| nav.weekTitle | Hafta {n} · {tür} | Week {n} · {type} |
| weekType | Ders · Final · Bütünleme · Tatil | Lecture · Final · Make-up · Holiday |
| subject.placeholder | Bir oda, hoca veya program seçin | Pick a room, instructor or programme |
| subject.kinds | Oda · Öğretim elemanı · Program ve sınıf · Şube | Room · Instructor · Programme & year · Section |
| allDay | Tüm gün | All day |
| termLong | Dönem boyu | Term-long |
| now / upNext | Şimdi · Sıradaki | Now · Up next |
| state.placed / conflict / warning / locked / partial / unplaced / preoccupied / booking | Yerleşti · Çakışma · Uyarı · Kilitli · Kısmi · Yerleşmedi · Önceden dolu · Rezervasyon | Placed · Conflict · Warning · Locked · Partial · Unplaced · Pre-occupied · Booking |
| issues.capsule | {n} çakışma · {m} uyarı | {n} conflicts · {m} warnings |
| drag.ok | {oda} · {gün} {aralık} · {kapasite} koltuk | {room} · {day} {range} · {capacity} seats |
| drag.conflict | {kod} ile çakışıyor | Clashes with {code} |
| drag.capacity | {kapasite} koltuk < {öğrenci} öğrenci | {capacity} seats < {students} students |
| drag.free | Boş: {aralık} | Free: {range} |
| move.cannot | Taşınamadı: {neden} | Couldn't move: {reason} |
| move.force | Yine de taşı | Move anyway |
| move.scope | Tüm haftalar · Sadece bu hafta · Bu haftadan itibaren | All weeks · This week only · From this week on |
| create.tabs | Rezervasyon · Ders talebi | Booking · Class request |
| create.book | Rezerve et | Book |
| create.place | Yerleştir | Place |
| create.later | Sonraki çalıştırmada yerleştir | Place in the next run |
| compare.summary | Run #{b} ile: {m} taşındı · {a} yalnız burada · {r} yalnız orada | vs Run #{b}: {m} moved · {a} only here · {r} only there |
| inspector.sections | Ne zaman, nerede · Kim · Neden burada · Kaynak · Geçmiş | When & where · Who · Why here · Source · History |
| explain | Yerleşimi açıkla | Explain placement |
| source.line | {dosya} · {sayfa} · satır {n} | {file} · {sheet} · row {n} |
| undo / redo | Geri al · Yinele | Undo · Redo |
| toast.moved | {kod} {oda}'e taşındı | {code} moved to {room} |
| density | Sıkı · Standart · Rahat | Compact · Standard · Comfortable |
| heat.metrics | Doluluk · Çakışma · Yerleşmeyen · Değişiklik | Occupancy · Conflicts · Unplaced · Changes |
| heat.split | Binaya göre böl | Split by building |
| empty.noRun | Bu dönem için henüz bir program yok. | There's no timetable for this term yet. |
| empty.filtered | Bu filtrelerle gösterilecek ders yok. | No classes match these filters. |
| stale | Yeni çalıştırma hazır | A newer run is ready |
| readOnly | Salt okunur | Read-only |
| reduceTransparency | Saydamlığı azalt | Reduce transparency |

The Turkish suffix after room codes ('e/'a/'ye) depends on how the code is read aloud. i18n uses ICU `select` on the last spoken syllable of the room code (A 101 = "yüz bir", so 'e). Fallback: rephrase as "{kod} → {oda} taşındı" when unsure.

## 12. Keyboard map (browser-safe; shown in `?`)

| Keys | Action |
|---|---|
| `B` `W` `D` `M` `Y` `A` | Lens: Board · Week · Day timeline · Month · Term ("Year") · Agenda (Google Calendar letters; `⌘1–6` is avoided because browsers use it for tabs) |
| `⇧B` | Toggle Board sub-mode Gün ↔ Hafta şeridi |
| `T` | Today |
| `J` / `K` or `]` / `[` | Next / previous range (day, week, month by lens) |
| `⇧]` / `⇧[` | ±4 weeks |
| `G` then `W` | Go to week… (number input) |
| `⌘K` / `Ctrl+K` | Jump-to palette |
| `/` | Focus the sidebar filter search |
| `S` | Subject picker |
| `Tab` | Enter the grid at the last focused cell; `Tab` again leaves to the inspector |
| `←` `→` `↑` `↓` | Move cell focus (room/day × period); `PageUp/PageDown` ±6 periods; `Home/End` first/last column; `⌘↑/⌘↓` P1/P18 |
| `Enter` | Open the focused event in the inspector; on an empty cell, start quick-create |
| `N` | New (quick-create) at the focused cell |
| `Space` | Pick up the focused event (keyboard move); arrows move the ghost with live preview; `Space`/`Enter` drops; `Esc` cancels |
| `⇧↑` / `⇧↓` on a focused event | Resize the end by one period (with preview) |
| `⌥↑` / `⌥↓` | Resize the start by one period |
| `X` | Toggle the focused event in the selection |
| `⌘A` | Select all visible |
| `L` | Lock / unlock |
| `E` | Explain placement (focuses inspector § Neden burada) |
| `C` | Toggle compare overlay (when a compare run is set) |
| `I` | Toggle inspector · `⌘⌥S` toggle sidebar |
| `+` / `−` / `0` | Zoom in / out / reset (canvas focused) |
| `⌘Z` / `⌘⇧Z` (`Ctrl+Z` / `Ctrl+Shift+Z`, `Ctrl+Y`) | Undo / redo |
| `Delete` / `Backspace` | Remove placement (confirm) |
| `⇧F10` / `Menu` | Context menu |
| `Esc` | Close popover, then clear selection, then close inspector (in that order) |
| `?` | Shortcut sheet |

## 13. Performance and virtualisation

**Data volume**: about 1,300 weekly meetings × up to 14 weeks; 60 rooms; 18 periods; 7 days. Pre-occupied blocks are up to about 700 cells per week (HAZIRLIK in Güz week 1: 660).

1. **One fetch per run, an index in a worker.** `GET /runs/{run_id}/assignments` (no `week` filter: about 1,300 enriched rows, ≈ 100 KB gzip) plus `GET /runs/{run_id}/grid?week=` for blocks (prefetched per week; or a `blocks` term endpoint, §17). A Web Worker builds:
   - `occ: Map<"room:day:period:week", id[]>` (≈ 45k entries),
   - `byInstructor`, `byCohort` (same key shape), for the drag checks,
   - `heat[week][day]` occupancy, conflicts, unplaced and changes (98 cells × metrics),
   - a compare diff when a compare run is set.
   It posts back transferable typed arrays for heat and plain objects for the per-week visible set. A week switch is then a synchronous lookup, so the scrubber is live.
2. **Board · Gün** (≤ 60 columns × 18 rows): the grid background is one CSS `repeating-linear-gradient` per pane, not 1,080 cell divs. Columns are virtualised horizontally with `@tanstack/react-virtual` (overscan 4) when > 24 rooms are visible; the sticky gutter and headers stay outside the virtualiser. Chips are absolutely positioned (`top = (p-1)*rowH`, `height = span*rowH - 1`). Room columns are `React.memo` keyed on `roomId + weekVersion`.
3. **Week strip** (60 rows × 126 slots): rows are virtualised vertically (row 32, overscan 8). Each row is one div with a gradient background plus absolutely positioned bars. Day totals are computed in the worker.
4. **Week / Agenda**: ≤ about 60 chips (Week); Agenda is a virtualised list with variable heights (`measureElement`).
5. **Month / Term**: 35–42 and 98–112 cells (up to 4 × 112 with the building split): plain DOM, values from the worker; no virtualisation needed. Tooltips are one shared floating element, not one per cell.
6. **ARIA with virtualisation**: `aria-rowcount`/`aria-colcount` give the totals, and each rendered cell carries `aria-rowindex`/`aria-colindex`. A roving-focus cursor scrolls the virtualiser before it moves focus, so focus never lands on an unmounted cell.
7. **Drag**: hit-testing is arithmetic (pointer position, then room/period), never `elementFromPoint`. `checkMove` is pure, runs at most once per animation frame, and costs < 1 ms. Only transforms animate. DragOverlay renders in a portal.
8. **Glass cost**: at most 5 `backdrop-filter` surfaces on screen at once (3 capsules + sidebar + inspector; popovers are transient). Never on chips, cells or sticky row headers in the strip. The blur radius drops to the liquid-glass.md "low" value while a drag is active to keep 60 fps on integrated GPUs.
9. **Budgets** (measured in CI with a Playwright trace on the Bahar fixture): first chips on screen ≤ 800 ms after data; week switch ≤ 16 ms main-thread; drag frame ≤ 8 ms; Term lens render ≤ 50 ms; worker index build ≤ 150 ms.

## 14. Density and responsive behaviour

| Width | Layout |
|---|---|
| **360–430 (phone)** | iOS-style **day list**. Glass large-title nav ("Çarşamba", "18 Mart · Hafta 7" subtitle) that collapses on scroll. A **horizontal day strip** (7 days of the term week, swipe to change week; each day has a heat dot) under it (Outlook #1, Apple Store #5). A segmented control **Liste · Zaman çizelgesi** (List · Timeline, Jobber #7). *Liste* = the Agenda for one day, grouped by period with Şimdi/Sıradaki on today (Saturn #6). *Zaman çizelgesi* = the Week lens for one subject collapsed to one day column, with a now-line and pill (Todoist #2). The subject chip row is horizontal: "Tümü · A 204 · Dr. Kaya · Eczacılık 2". Tap a row to open the glass bottom sheet (detents: medium 50 %, large 92 %) with the inspector. Moving uses **Taşı…** in the sheet (a form: room, day, periods, scope, with the same live validity); no drag. The `+` floating circle creates (Rezervasyon / Ders talebi sheet). Month and Term are available from the title menu: Month as a compact month with heat dots; Term as a 7 × 14 grid of 36 px cells (fits 360). Wireframe: `wireframes/calendar-mobile-day.svg`. |
| **768–1179 (tablet)** | The sidebar becomes a popover from ☰. The inspector is an overlay sheet from the right (420 px) in landscape, or a bottom sheet in portrait. Board · Gün shows 5–6 room columns with `scroll-snap-type: x proximity`. The week strip is available in landscape only. Touch drag via long-press, pinch zoom. Capsules: 48 px tall. |
| **1280–1599 (laptop)** | As §5. The sidebar overlays (it doesn't push); the inspector overlays. Board · Gün shows about 9 room columns at standard density, about 12 at compact. |
| **1600–2559 (desktop)** | Sidebar and inspector docked (they push). Board · Gün shows about 13 columns. Day timeline gets the **Sıradaki** panel. Term lens split by building fits without scrolling. |
| **≥ 2560 (4K / 5K at 1×–1.5×)** | Board · Gün shows all ~28 rooms of one building band at standard (or all 60 at compact, no horizontal scroll at 3840). Optional **two-day split** (`⋯ › Yan yana iki gün`) for comparing Wednesday and Thursday. Term lens shows split-by-building small multiples at 48 × 36 cells. Type does not scale up; density options do the work. The max chip width is clamped to 200 px so codes don't float in wide cells. |

Density is set in `⋯ › Yoğunluk` and persisted per user; Compact is pointer-only (disabled when `pointer: coarse`).

## 15. Accessibility

- **ARIA grid** for Board, Week strip, Week and Day timeline: `role="grid"`, `aria-label="Pano, Çarşamba 18 Mart, Hafta 7"`, with `aria-rowcount`/`aria-colcount` totals. Column headers use `role="columnheader"` ("A 204, 156 koltuk, TIP"); row headers use `role="rowheader"` ("P7, 13:30–14:10"); cells use `role="gridcell"`. Chips are buttons inside cells, `aria-label="BME 419, Biyomedikal 3. sınıf, A 204, Çarşamba 13:30–15:50, 102 öğrenci, 156 koltuk, kilitli"` and `aria-describedby` pointing to the issue text. One tab stop with a roving tabindex (APG grid pattern).
- **Month** follows the APG date-grid pattern (`role="grid"`, day cells as `gridcell` with buttons, `aria-selected` on the selected day, `aria-current="date"` on today). The heat value is in the label: "18 Mart, yüzde 72 dolu, 2 çakışma".
- **Term** is a `role="grid"` with week rows; each cell is labelled "Hafta 7, Çarşamba 18 Mart: yüzde 72 dolu". Each metric switch is announced. A "Tablo olarak göster" toggle renders the same numbers as a plain `<table>` (also useful for print).
- **Agenda** is a `role="feed"` of `article`s by day, the best lens for screen readers, and it is offered via a skip link "Ajanda görünümüne geç".
- **Live regions**: one `polite` region for drag announcements (dnd-kit `announcements` in TR/EN: "BME 419 alındı. A 101, Çarşamba P7 üzerinde, uygun. Bırakmak için Boşluk."), save results, filter counts (debounced 500 ms), and week changes ("Hafta 9, 30 Mart–5 Nisan"). One `assertive` region only for hard-conflict drop refusals.
- **Contrast on glass** (computed with the §8.1 script, alpha-blend model without blur, which is a worst case because blur averages the backdrop):

  | Glass tint over the most saturated chip | `--fg` | `--fg-muted` |
  |---|---|---|
  | light 64 % over violet `#4a3aa7` | 9.45 | **4.01 ✕** |
  | light 72 % over violet | 11.03 | 4.68 ✓ |
  | light 80 % over violet | 12.76 | 5.42 ✓ |
  | dark 64 % over violet `#9085e9` | 8.93 | **4.36 ✕** |
  | dark 72 % over violet | 10.39 | 5.07 ✓ |

  Hence §8.2: glass carrying muted text needs ≥ 72 % tint; thin glass (≥ 64 %) carries primary text only. Popovers (forms) use ≥ 80 %.
- **Heat cells** (40 % step over `--bg`): `--fg` on steps 1–5 is 17.26 / 15.57 / 12.56 / 9.86 / 8.28 (light) and 15.75 / 14.14 / 11.05 / 7.87 / 5.63 (dark). `--fg-muted` fails on step 5 (3.51 light, 2.75 dark), so heat cells use `--fg` only.
- **Non-text contrast**: chip bars are decorative (the code text carries identity). Selection and focus rings are ≥ 3:1 against both the chip fill and the canvas. The now-line red against `--bg`: 3.55:1 light, 5.50:1 dark (≥ 3:1 ✓). The time capsule text: 5.38:1 light (white on `#D70015`) and 5.50:1 dark (`#0B1220` on `#FF453A`).
- `prefers-reduced-transparency`, `forced-colors: active`, and the in-app **Saydamlığı azalt** setting all switch glass to solid (§8.2). Under forced colours the hatch becomes `1px dashed CanvasText` and chips get a `ButtonText` border.
- `prefers-reduced-motion`: the §8.4 column. `prefers-contrast: more`: chip fills go to 22 %, inks go darker by 10 %, and hairlines double.
- **Targets**: ≥ 44 px on touch (rows ≥ 52 in Agenda; capsule buttons 44 × 44). Resize handles get 16 px hit areas on touch, and keyboard resize exists (§12).
- **Zoom 200 % / reflow**: the canvas scrolls in two dimensions (exempt as a 2-D data grid under WCAG 1.4.10). The chrome reflows: capsules wrap into two rows and the sidebar becomes a popover.
- **Language**: `lang="tr"` default; all shortcuts are Latin letters that exist on Turkish Q and F keyboards (`B W D M Y A T J K N L E C I X S`). Use `KeyboardEvent.key` comparisons, casefolded with `toLocaleLowerCase('tr')` and a fallback for `İ`/`ı`.

Contrast script (copy; same as tokens §8):
```python
def mix(a,b,t): return [a[i]*(1-t)+b[i]*t for i in range(3)]
# fill = mix(white, hue, .14); ink = mix(hue, black, t) with t raised until cr(ink, fill) >= 5.0
# glass check: cr(fg, mix(chip_hue, glass_base, alpha))
```

## 16. Components (mapped to what the glass-system agent imports)

| Need | Component | Source · licence (checked 2026-10-08) | Notes |
|---|---|---|---|
| Glass capsule, glass panel, glass thumb, solid fallback | `GlassCapsule`, `GlassPanel`, `GlassSegmented` | **liquid-glass.md** (glass-system agent) on shadcn `ToggleGroup`/`Button` · MIT | consume; don't fork |
| Segmented lens switcher | beUI **Tabs** (segment style) re-skinned as `GlassSegmented` | https://beui.dev · MIT (site FAQ: public library MIT; Pro separate) | sliding thumb via `motion` `layoutId` |
| Floating scrubber / dock feel | beUI **Dock** / **Expandable Action Bar** as a reference | beUI · MIT | the scrubber itself is in-house (`WeekScrubber`) |
| Sidebar shell | shadcn **Sidebar** | https://ui.shadcn.com · MIT | inset variant + `GlassPanel` |
| Mini-month | shadcn **Calendar** (react-day-picker, `showWeekNumber`, custom `DayButton` with heat dot) | shadcn MIT · react-day-picker MIT | term week numbers through a `formatWeekNumber` override |
| Inspector (desktop) | shadcn **Sheet** (`modal={false}`) inside `GlassPanel` | shadcn · MIT | shared `ClassInspector` (all-classes.md §9) |
| Inspector (phone) | beUI **Bottom Sheet** (snap points; glass surface) | beUI · MIT | `vaul` (MIT) as an alternative |
| Popover, Tooltip, ContextMenu, DropdownMenu, Dialog, Command (⌘K) | shadcn primitives (already installed: popover, tooltip, dropdown-menu, dialog, command) | shadcn · MIT; cmdk · MIT | add `context-menu` |
| Toasts with undo | **sonner** (installed) | MIT | |
| Explain placement (streamed text, "thinking" state) | beautifului **Streaming Text** + **Thinking** | https://beautifului.dev · MIT (© 2026 Shane Levine; licence page checked) | keep the licence header in copied files |
| Fix suggestions in "Neden burada" | beautifului **Recommendation Card** | beautifului · MIT | |
| Multi-select action bar (desktop) | beautifului **Selection Actions** | beautifului · MIT | re-skinned on `GlassCapsule` |
| Weekly occupancy mini-bars (Term right column, scrubber tooltip) | evilcharts **Bar chart** (Recharts engine; `npx shadcn@latest add @evilcharts/recharts-bar-chart`, confirm the slug on first install) | https://evilcharts.com · MIT (LICENSE: © 2026 Gurbinder; checked) | only where a real chart is needed; heat cells are in-house |
| Heat calendar (Month, Term, mini-month dots) | in-house `HeatGrid` (CSS grid, tokens §2.5); a11y pattern referenced from beUI **Liquidity Heatmap** | beUI · MIT (reference) | no chart lib for 98 cells |
| Drag/drop, keyboard DnD | `@dnd-kit/core` + `/utilities` (installed); add `/modifiers` | MIT | custom `coordinateGetter` |
| Virtualisation | `@tanstack/react-virtual` (installed) | MIT | |
| URL state | `nuqs` | MIT | `npm i nuqs` |
| Undo stack | `zustand` (installed) | MIT | |
| Grid primitives | in-house `CalendarCanvas`, `PeriodAxis`, `RoomHeader`, `BuildingBand`, `AllDayBand`, `EventChip`, `NowLine`, `LassoLayer`, `GhostLayer`, `QuickCreatePopover`, `MovePopover`, `UnplacedTray` | ours | replace `src/components/timetable/{day-grid,week-grid,grid-event,legend,agenda-view}.tsx` |

Not adopted: beUI *Availability Scheduler* (a weekday × time-range form, not a grid); kobra/reverseui components (licences; reference only per tokens §9); Kinetics (no LICENSE file).

## 17. API endpoints (prefix `/api/v1`; from `smartsched/backend/app/api/v1`)

**Existing, used as-is**
| Endpoint | Used for |
|---|---|
| `GET /terms`, `GET /terms/{term_id}/weeks` | term picker; week types (Ders/Final/BÜT/Tatil), dates for the scrubber and Term rows |
| `GET /buildings`, `GET /rooms` | room columns, capacities (lecture/exam), tags, bookability |
| `GET /faculties`, `GET /programs`, `GET /instructors`, `GET /sections` | sidebar filters, subject picker |
| `GET /runs?…`, `GET /runs/{run_id}` | run picker, status (FEASIBLE / FEASIBLE_PARTIAL), objective |
| `GET /runs/{run_id}/assignments?week=&day=&room=` | **the index** (called without filters, once per run) |
| `GET /runs/{run_id}/grid?week=&blocks=true` | pre-occupied blocks per week |
| `GET /runs/{run_id}/summary` | issue and unplaced counts |
| `GET /runs/{run_id}/events` (SSE) | the stale banner when a newer run finishes |
| `POST /runs/{run_id}/assignments/{aid}/move` `{day,start_period,end_period,room_ids,week,force}` | drag, resize, inspector edits, keyboard move |
| `POST /runs/{run_id}/assignments/{aid}/lock?locked=` | lock/unlock |
| `POST /runs/{run_id}/diagnoses/{idx}/apply` | "Düzelt" (fix) from issue rows |
| `POST /runs/{run_id}/explain` `{lang,use_model}` | run-level explanation (fallback until the per-assignment endpoint lands) |
| `POST /runs/{run_id}/chat` | "Sohbette aç" (open in chat) |
| `GET /runs/{run_id}/export?format=xlsx\|csv\|ics\|crbs` | `⋯ › Dışa aktar` |
| `PUT /requests/meetings/{mr_id}`, `POST /requests/meetings/{mr_id}/check-room` | request-level edits from the inspector |
| `POST /constraints` (`room_pin`, `fixed_time`) | "Bu odaya/saate sabitle" (pin to this room/time) in quick-create |
| `GET /imports/{job_id}`, `GET /imports/{job_id}/file` | provenance: "Dosyayı aç" |
| `GET /dashboard` | (Term lens fallback for building × day utilisation when no run is selected) |

**Backend needed** (proposed shapes; owners in brackets)
| Endpoint | Why |
|---|---|
| `POST /runs/{run_id}/assignments/{aid}/move` + `dry_run: true` → `MoveOut` without commit [backend] | a server-confirmed preview in the Move popover (soft-score delta) |
| `POST /runs/{run_id}/assignments/bulk-move` `{moves:[{aid,…}], atomic:true, dry_run}` [backend] | multi-move as one transaction and one undo entry |
| `POST /runs/{run_id}/assignments` `{meeting_request_id\|exam_request_id, day, start_period, end_period, room_ids, weeks}` and `DELETE /runs/{run_id}/assignments/{aid}` [backend] | place unplaced classes (tray, quick-create); unassign |
| `POST /runs/{run_id}/assignments/{aid}/explain` `{lang}` → `ExplainOut` (sections: rules met, alternatives considered, what would break) [ai-engineer] | **Yerleşimi açıkla** per placement |
| `GET /runs/{run_id}/blocks` (term-wide pre-occupied blocks with week sets) [backend] | avoids 14 grid calls for the index |
| `GET /runs/{run_id}/heat?metric=occupancy\|conflicts\|unplaced&by=day[,building]` [backend, optional] | Term/Month without loading the full index (viewer dashboards, phones) |
| `GET /runs/{run_id}/diff?against={other}` [backend, optional] | compare without loading two full runs on phones |
| Bookings: `GET /bookings?room_id=&from=&to=`, `POST /bookings`, `PATCH /bookings/{id}`, `DELETE /bookings/{id}` with recurrence by week set [backend-engineer, CRBS parity, `docs/CRBS_PARITY.md`] | quick-create **Rezervasyon**, booking chips, all-day bookings; final shape owned by the CRBS-parity work |
| `import_job_id` + `sheet_name` on `meeting_requests`/`exam_requests` (and in `AssignmentOut` enrichment) [backend] | provenance "file · sheet · row"; today only `source_row_index` and `sections.source_row` exist |
| `GET /audit?entity=assignment&id=` (who/when per move/lock) [backend] | inspector **Geçmiş** (history) across sessions |

## 18. Anti-AI-look checklist (calendar)

Reviewers tick every line before merge; the strict-reviewer agent blocks on any ✕.

1. ☐ No page H1 that repeats the nav title; the date range is the title.
2. ☐ No card or border wrapping the grid; the canvas is full-bleed and the chrome floats.
3. ☐ Glass only on chrome (capsules, sidebar, inspector, scrubber, popovers). Never on chips, cells, heat, or rows.
4. ☐ No gradients anywhere on content (chips, heat, headers). No glow, no neon borders, no coloured shadows.
5. ☐ No monospace for codes; system font with `tabular-nums`, code at w600.
6. ☐ At most one accent colour (selection, today). Red is reserved for the now-line and conflicts.
7. ☐ Segmented controls use a neutral glass thumb, not a saturated filled segment.
8. ☐ No zero-celebration chips ("0 conflicts"). Counts appear only when > 0.
9. ☐ Filters live in the sidebar, not as a row of 10+ pills in the toolbar.
10. ☐ Chips have no border and no shadow at rest; a 1 px gap separates stacked chips; radius 6, concentric with containers.
11. ☐ The time gutter shows clock times ("13:30"), not "P7 / 13:30– / 14:10" stacks.
12. ☐ No decorative per-header micro-bars; numbers or nothing.
13. ☐ Icons: lucide at 1.5 stroke, 14–16 px, monochrome. No icon-in-coloured-tile, no sparkles for AI (Explain uses a text-bubble glyph and the word "Açıkla").
14. ☐ No skeleton shimmer cascades and no staggered entrance animations; chrome is instant, content appears once.
15. ☐ Empty states have one sentence and one or two actions, with no illustration, emoji or exclamation mark.
16. ☐ Copy is specific ("ENG 102 ile çakışıyor"), sentence case, no marketing verbs ("seamlessly", "effortlessly", "powerful").
17. ☐ Real density: ≥ 9 room columns at 1280 and ≥ 13 at 1920 in standard density.
18. ☐ Hairlines at 8–14 % alpha, no 1 px solid grey borders on every cell.
19. ☐ States are distinguishable in grayscale (glyph + shape: double bar for locked, hatch for pre-occupied, dashed for ghost/unplaced).
20. ☐ Everything aligns to a 4 px grid; capsule/panel radii are concentric (panel 20 = chip 12 + padding 8).
21. ☐ Dark mode is designed, not inverted: fills are 26 % hue over `#0B1220`, inks are lightened, and glass tint stays ≥ 72 %.

## 19. Open questions

1. Default lens per role: Board · Gün for planners, and Week (subject = own programme) for faculty secretaries once roles exist. Confirm.
2. Should bookings (CRBS parity) block the solver as pre-occupied input on the next run? This spec assumes **yes**, shown as booking chips, not hatched blocks.
3. Proportional time in the Day timeline vs period rows elsewhere: is the mixed model acceptable? (It is how front-desk staff think, "14:20", and planners think, "P8".)
4. Should the Term lens include Final/BÜT weeks by default, or only when the run kind is EXAM?
5. Multi-move across days (keep relative offsets) or only within a day? This spec allows across days; the conflict preview makes it safe.
6. Is `force` (move despite a conflict) allowed for PLANNER, or ADMIN only?
