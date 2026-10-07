# Requests inbox — meeting & exam requests, parsed chips, statuses, bulk actions, filters

Owner: design-pro (B). Route `/requests?kind=meetings|exams`. Backend:
`GET/PUT /requests/meetings`, `/requests/exams` (search, paging, filters), fields from `meeting_requests`
/ `exam_requests` (ARCHITECTURE › Domain model). Statuses `NEW · PARSED · NEEDS_REVIEW · LOCKED`.
Licences: `navigation-shell.md §9`.

---

## 1. References

| # | Reference | Borrow |
|---|---|---|
| 1 | [Linear – Inbox 3-pane](https://mobbin.com/screens/beb9d6b3-ec34-46d7-9332-320fcb32a338) | List pane (avatar, title, subtitle, age, status glyph) + detail pane with **Properties** sidebar (Status, Priority, Assignee, Date) and Activity log |
| 2 | [Linear – grouped list by status](https://mobbin.com/screens/10d46768-7ef5-4140-9f5f-22a97a207759) | Collapsible status groups (`In Progress 2 · Todo 2/3 · Done 11`) with per-group `+`; label chips right-aligned; "1 issue hidden by filters · Clear filters" |
| 3 | [Linear – AI filter](https://mobbin.com/screens/10d46768-7ef5-4140-9f5f-22a97a207759) | Filter input accepting natural phrases ("assigned to me") — we accept Turkish ("eczacılık perşembe") |
| 4 | [ClickUp – board + nested filter](https://mobbin.com/screens/7ba9940a-ff0d-4162-a8bf-5fa148096de4) | Filter builder `Field · is · value`, "Saved filters", "Add nested filter"; kanban cards with coloured status columns |
| 5 | [Asana – board](https://mobbin.com/screens/e51854b0-c808-437e-ad96-fe406f23e986) | Compact kanban card: code, label chips, status pill, date; column counts |
| 6 | [Jira – board with Group by](https://mobbin.com/screens/c9cd8d74-16ee-43ba-939a-33b4a45b5244) | "Group ▾" (None/Assignee/Epic) → ours: Faculty / Program / Day / Building |
| 7 | [Trello – filter sheet](https://mobbin.com/screens/ac71e4ce-aee6-461e-87c6-a5eb35e7a4b1) | Right-side filter `Sheet` with checkbox groups — mobile filter pattern |
| 8 | [Attio – records table with tag chips](https://mobbin.com/screens/4e6934cc-b936-43f9-a098-f7d7868fadf6) | Multi-value chips inside table cells, "Sorted by · Filter" toolbar, count footer |
| 9 | [Attio – review values w/ inline fix](https://mobbin.com/screens/60a1cfe5-3788-49e3-b3ae-3da62a33f7ee) | "Needs review 3" group with raw → mapped value pairs — the model for free-text → chips |
| 10 | [Airbnb – filter chips popover](https://mobbin.com/screens/5f99d74b-4947-427a-8ef9-d98d9a62f55e) | Multi-select chip grid in a popover with `Clear · Show 120 results` |

## 2. Information architecture

```
/requests
  toolbar:  [Meetings | Exams] segmented · search · Filter ▾ (builder) · Group by ▾ · [Table | Board] · Saved views ▾
  filter chips row (active filters as removable chips)
  body:     Table (default)  |  Board (columns = status)
  right:    Detail pane (Sheet on <1280, inline pane ≥1280) for selected request
  footer:   "1 529 requests · 31 need review · 412 locked"   bulk bar when selection > 0
```

### Table columns (meetings)
`☐ · Status · Course (code + name) · Program (faculty › program, İÖ badge) · Year · Day · Periods (P7–P9 13:30–15:50) · Weeks (chip "1–14" / "1,3,5…") · Enrolment · Requested room (chips) · Definitive room · Mode · Instructor · Warnings · Updated`
Default sort: `status (NEEDS_REVIEW first) → day → start_period`. Column visibility & order persisted per user (`localStorage.smartsched.requests.cols`).

### Table columns (exams)
`☐ · Status · Course · Program(s) (merge_key group shows stacked avatars-style chips "3 programs · 70 students") · Date · Time · Enrolment · Requested venue (chips: rooms=2, min cap 60, PC lab, invigilators) · Definitive · On-campus ✓ · No-exam ✓ · Warnings`

### Detail pane (Linear #1)
Header: course code + name, status pill with menu, `Lock` toggle, prev/next (`j/k`).
Properties: Day, Periods, Weeks, Enrolment, Mode, Program(s), Instructor(s), Requested room (chip editor), Definitive room, Flexible day, Notes (free text from `Derse Özel Açıklama`), Source row (collapsible raw Excel row `source_row`).
Activity: parse log (import job, warnings), status changes, AI suggestions, user edits (who/when).

## 3. Interaction spec

### 3.1 Status model & transitions
| Status | Meaning | Colour token | Allowed actions |
|---|---|---|---|
| NEW | imported, not parsed yet | `muted` | Parse, Edit |
| PARSED | parser confident, no warnings | `primary` | Edit, Lock, Mark needs review |
| NEEDS_REVIEW | warnings or unparsed free text | `warning` | Fix (chip editor), Accept suggestion, Skip, Lock |
| LOCKED | planner-confirmed; solver treats requested fields as hard | `success` | Unlock, Edit (asks to unlock) |
Status pill = dot + text (never colour only). Change via pill menu, detail pane, bulk bar, or keys (`1..4`).

### 3.2 Table (TanStack Table + react-virtual)
- Row height 44 px, sticky header, sticky first 2 columns (checkbox, status) and course column on ≥ 1280.
- Row click → opens detail pane; `Shift+click` range select; `⌘/Ctrl+click` toggle.
- Inline edit: double-click or `Enter` on Day / Periods / Enrolment / Definitive room cells opens the matching control in place (Select, period range picker, number, room combobox). `Esc` cancels, `Enter` saves (`PUT /requests/meetings/{id}` optimistic, rollback + toast on error).
- Group by (Jira #6): Faculty / Program / Day / Building / Status → collapsible group headers with counts (Linear #2); virtualiser handles group rows.
- Hidden-by-filter line in footer: "212 hidden by filters · Clear".
- Loading: 12 skeleton rows; subsequent pages via infinite scroll (page size 100), sentinel at 80 %.
- Empty: illustration-free card "No requests yet — import a planning list" with CTA to `/import`.
- Error: inline banner with retry.

### 3.3 Board (kanban)
- Columns = statuses (fixed order), each with count and "Lock all parsed" quick action on the PARSED column. Cards (Asana #5): course code, program short, day+period line, requested-room chips (max 2 + "+n"), warning count icon.
- Drag between columns with `@dnd-kit` → status change (same validation as pill menu; LOCKED column refuses cards with unresolved errors — card springs back + toast). Keyboard DnD via dnd-kit's `KeyboardSensor` (Space pick up, arrows move, Space drop).
- Column virtualised when > 200 cards.

### 3.4 Free-text requested room → structured chips (core of this surface)
Source: `requested_room_text` (113–147 distinct free strings, e.g. `A103 (Bilg. Lab. Zorunlu)`, `72 kişilik C blok 601-602 vb`, `A301-A302-A303 MULTİDİSİPLİN`, `A Blok'ta Derslik`, `1 derslik`, `DERSLİK+HASTANE`).
The parser (backend `importers/normalize.py` + LLM fallback) yields structured fields; the UI renders them as **chips** inside a **chip editor**:

| Chip kind | Icon | Example | Backing field |
|---|---|---|---|
| Room | door | `A 103` | `requested_room_ids[]` |
| Building | building | `C Blok` | `requested_building` |
| Tag | tag | `PC` `LAB` `TIP` `AMPHI` | `requested_tags[]` |
| Capacity | users | `≥ 72` | `requested_capacity` |
| Count | hash | `2 rooms` (exams) | `requested_room_count` |
| Flag | flag | `flexible day`, `multi-room split OK`, `same room as OPT 126` | `flexible_day`, params |
| Unparsed | help-circle (amber) | `"vb"` | leftover text |

- Chip editor (popover from the cell, inline in detail pane): shows the raw text in a muted quote on top; chips below; input "Add…" with autocomplete (rooms by code `A 20` → A 201…, buildings, tags, `≥ 60` capacity grammar, `2x` count grammar). Backspace removes last chip; `←/→` move between chips; `Delete` removes focused chip; `Enter` adds.
- Provenance: chips produced by regex are solid; chips produced by the LLM have a dashed border + sparkle icon and tooltip "Suggested by AI from 'Bilg. Lab. Zorunlu'"; the user **accepts** (click ✓ or `a`) which makes them solid and moves status to PARSED. Never auto-accept AI chips (ARCHITECTURE › AI layer: validate model output).
- Conflicts (e.g. room `A 103` capacity 47 < enrolment 60) are shown as a red inline note under the chips with a "Switch to capacity ≥ 60" fix link.
- "Re-parse with AI" button in the editor → `POST /requests/meetings/{id}/parse` (spinner in button ≤ 3 s, streaming not needed). Error → toast.

### 3.5 Filters
- Filter builder popover (ClickUp #4): rows `Field ▾ · operator ▾ · value`; fields: Faculty, Program, Day, Building (from requested/definitive), Status, Mode, Year, Week, Has warnings, Enrolment range, Instructor, Import job. Values are multi-select chip grids (Airbnb #10) with search; "Clear · Show 318 results".
- Quick chips row under the toolbar: `Needs review (31)` `Today's import` `Unroomed` `TIP rooms` `İÖ (evening)`; active filters appear as removable chips; `Esc` clears focus not filters.
- Search box: tokens `MAT 112`, `Perşembe`, instructor surname; Turkish-aware casefold (`İ/ı`), diacritic-insensitive (`sube` finds `şube`).
- Saved views (Linear "Your view was created" toast #): name + filters + columns + grouping; stored server-side per user (`PUT /settings/views`).
- URL mirrors filters (`?status=NEEDS_REVIEW&faculty=ecz&day=4`) for sharing.

### 3.6 Bulk actions
Selection bar slides up from the footer (150 ms, reduced motion: appears): "31 selected · Lock · Set status ▾ · Set definitive room… · Accept AI chips · Re-parse · Export .xlsx · Delete". Confirm dialog for Delete and for Lock when any selected row has errors ("3 of 31 have unresolved warnings — lock the other 28?"). Progress for > 50 rows uses a toast with count; results summarised ("28 locked, 3 skipped · Undo").

### 3.7 Keyboard
`j/k` next/prev row · `x` toggle select · `Enter` open detail · `e` inline edit focused cell · `l` lock/unlock · `1-4` set status · `f` focus filter · `/` search · `g b` board view, `g t` table view · `Esc` close pane/popover · `?` cheatsheet. Arrow keys navigate cells when a row is focused (`role="grid"`).

### 3.8 Touch
Rows 48 px tall on touch; swipe-right on a row reveals **Lock**, swipe-left reveals **Needs review** (beUI Swipeable List pattern); long-press enters multi-select. Detail pane = bottom Sheet (snap 60 % / 100 %).

### 3.9 Motion
Status pill colour change 150 ms; row insert/remove `AnimatePresence` height 180 ms; kanban card drop spring {300, 30}; chip add scale .9→1 120 ms. Reduced motion: all instant, keep opacity fades ≤ 100 ms.

## 4. Component list

| Component | Source | Licence | Note |
|---|---|---|---|
| DataTable (TanStack Table v8) | https://tanstack.com/table | MIT | `pnpm add @tanstack/react-table @tanstack/react-virtual` |
| Table, Badge, Popover, Select, Combobox (Command), Sheet, Toggle Group, Checkbox, DropdownMenu, AlertDialog | shadcn/ui | MIT | `npx shadcn@latest add …` |
| Chip editor | build `components/ui/chip-input.tsx` on Radix Popover + cmdk; model after **Tag Input** (kinetics) / **Filter Chips** (kobra, paid) | ours | kinetics/kobra reference only |
| Records Table (CRM grid w/ tags, sorting, relationship status) | beautifului.dev https://beautifului.dev/#records-table | MIT | copy the chip-in-cell rendering |
| Filter Table (status chips filtering) | beautifului.dev https://beautifului.dev/#filter-table | MIT | quick-chips row |
| Recommendation Card (confidence meter + actions) | beautifului.dev https://beautifului.dev/#recommendation-card | MIT | AI chip acceptance card in detail pane |
| Kanban DnD | `@dnd-kit/core` + `@dnd-kit/sortable` | MIT | already in stack |
| Swipeable List | beUI https://beui.dev/components/blocks/swipeable-list | MIT | `bunx --bun shadcn add @beui/swipeable-list` (mobile rows) |
| Bottom Sheet (snap points) | beUI https://beui.dev/components/motion/bottom-sheet | MIT | mobile detail pane; or `vaul` (MIT) |
| Status Pill / Pulse Badge | kinetics | no licence | reimplement (dot pulse for RUNNING re-parse) |
| Multi Select, Filter Chips, CRM Table | kobra.systems | paid | reference only |

## 5. Responsive behaviour

| Width | Table | Board | Filters | Detail |
|---|---|---|---|---|
| 360 | card list: status dot, course, program, day/period line, chips (2 + n), warning icon; checkbox appears in select mode | horizontal scroll-snap columns, 85 vw each | `Sheet` from right (Trello #7) with checkbox groups; quick chips scroll horizontally | bottom Sheet |
| 768 | 6 columns (status, course, program, day, periods, requested); rest in expander | 2 columns visible, scroll-snap | popover builder | right Sheet 420 px |
| 1280 | full table, sticky cols | 4 columns | inline builder | inline pane 400 px (collapsible) |
| 1920 | full table + Instructor + Notes columns | 4 columns wider cards | inline | pane 480 px, activity log visible |

## 6. Accessibility
- Table uses `role="grid"` with roving tabindex; sortable headers are buttons with `aria-sort`.
- Status conveyed by icon + text; chips have `aria-label` with kind ("Room A 103"); AI-suggested chips announce "suggested".
- Chip editor: `role="listbox"` for chips, `aria-multiselectable`, removal announced via live region.
- Kanban: dnd-kit announcements in TR/EN (`announcements` prop) — "Picked up MAT 112. Press arrows to move between columns".
- Bulk bar is `role="toolbar"` with `aria-label="31 selected"`.
- Minimum touch target 44 px; swipe actions also available via row menu (⋯).
- Contrast of status colours checked in light/dark; warning amber paired with icon.

## 7. Open questions
1. Should faculty secretaries get a VIEWER-like "submit request" role later (ROADMAP backlog "Request inbox workflow")? If yes the inbox needs a `SUBMITTED` status before NEW.
2. Exam merge: show merged exam (BME 419 ×3 programs) as one row with a stacked chip or three rows grouped? Spec: **one row per merge_key** with expandable members; needs backend `merge_key` grouping in `GET /requests/exams`.
3. Definitive room column editable here or only in the timetable grid? Spec: editable here (planner's habit from Excel column 18) with conflict check via `POST /runs/{id}/assignments/{aid}/move` semantics — backend needs a request-level equivalent.
4. LLM re-parse per row costs tokens; batch endpoint for bulk re-parse?
