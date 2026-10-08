# Generator Studio: shape a run in one guided screen

Owner: design-pro (Generator Studio). Status: v1 spec (2026-10-08), ready for backend-engineer, ai-engineer and frontend-engineer. Phase 8 in `docs/ROADMAP.md`.
Route: `/generate`. It replaces `src/components/generate/generate-view.tsx`. Run pages `/runs/[id]`, `/runs/[id]/grid` and `/runs/[id]/report` stay as they are.
Tokens and motion: `docs/design/tokens.md` is the source of truth. Licences: `navigation-shell.md §9`, plus the new checks in §9 below.
Sibling specs reused here: `requests-inbox.md` (table, chip editor, filters, bulk bar), `import-wizard.md` (dropzone, review table, Diff tiles), `generate-and-chat.md` (horizon picker, proposal cards, run status card, constraint drawer), `run-report.md` (DiagnosisCard, apply-fix flow, scenario comparison), `timetable-grid.md` (period labels, status tokens).

**Who this is for.** A university planning officer (persona: Fatih Bey). Today he runs the term from Excel. He knows rooms, programmes and the 18-period day by heart. He does not know what a "hard constraint" or a "weight" is, and he should not need to.

**What it must do (user requirement).** "The generator should have the setting to adjust list of classes, change preferences, adjust rules by natural language, upload preference files or Excels and any other method you think could be possible, and it should have easy understandable UI/UX."

**Design principle: one rule shape.** Every input becomes the same visible, editable **rule card**: a typed sentence, a picked template, an uploaded file row, a rule copied from last term, a preset, a pin set in the class list, or a fix accepted in the pre-check. This follows ARCHITECTURE "Everything is a constraint object". The planner learns one object, and the solver gets one list.

---

## 1. References (Mobbin), with what we borrow

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| 1 | [ClickUp: automation builder with sentence bar](https://mobbin.com/screens/3f70b74f-2e7b-42a4-81f7-f9750a39722c) | Footer sentence "When [Task created] and [Condition is true] then [Change status]" with every slot a clickable chip. This is our **rule sentence with slots**: "Keep [Eczacılık] in [C block] on [Monday]" | the two-column trigger/action canvas (too technical) |
| 2 | [Jira: rule editor, summary card plus side form](https://mobbin.com/screens/46e3b5f1-1939-4aae-baa2-fb6c2d09aa1e) | Left: a live preview card of the rule. Right: a form with labelled "(required)" fields and an "Add condition" link. Becomes our **structured rule builder** dialog (preview sentence on top, fields below) | the "Turn on rule" split button jargon |
| 3 | [Asana: "Add rule" template gallery](https://mobbin.com/screens/fc60cc36-cb9e-4622-8070-613cef652e41) | First two tiles are "Create custom rule" and "Create with AI", then template tiles grouped by topic. Becomes our **Add rule** menu: *Write it* / *Pick a template* / *Upload a file* / *Copy from last term* / *Use a preset* | |
| 4 | [Calendly: add automation cards](https://mobbin.com/screens/7efa8bfb-07e5-437d-a0c0-d6a4dfb897bd) | Template card = icon, title, one-line plain explanation, single CTA. Used for our 12 templates (§3.3.2) | |
| 5 | [Square: "Customize smart group", 0 matching customers](https://mobbin.com/screens/53162374-2076-479b-bb1d-5c473647d50f) | Live count "0 matching customers. That's 0% of your customer base." above the filter form. Becomes the **affected-count badge** "applies to 42 classes (3 %)", recomputed while editing | |
| 6 | [Flodesk: all/any filter groups](https://mobbin.com/screens/5fb6ac39-9629-481c-8533-1c08250d03b8) and [Qatalog: filter chip with operator popover](https://mobbin.com/screens/3f10c158-e82b-4348-92cd-15471e3467df) | "Matching **all / any** of these" segmented, plus removable filter chips whose popover holds the operator. Used for the class-list filters and the "applies to" picker in the builder | nested groups beyond one level |
| 7 | [AirOps: AI analysis review with Accept all / Decline all](https://mobbin.com/screens/88aed5b3-f244-49e5-94c6-a8b8df2790be) | Summary box on top ("Quill Analysis"), a table with a *Reasoning* column, per-row ✓ / ✕, and "Decline All · Accept All". Becomes the **uploaded-file review table** | |
| 8 | [Copy.ai: Review & finalize, tabs All / Clean / With issues](https://mobbin.com/screens/b140e578-daf5-4923-89a9-8d4530c4a432) | Tabs with counts ("All rows 2 · Clean rows 1 · Rows with issues 1") and a "Fix with AI" side panel. Becomes review tabs *All · Ready · Needs a look · Couldn't read* | |
| 9 | [Mistral Document AI: source next to extracted output](https://mobbin.com/flows/f1e42880-76f2-4b7c-abb1-6fd8f324f0ac) and [Elicit: extract data from PDFs](https://mobbin.com/flows/8adfa568-bea4-4f12-a90f-549fa45ac6dd) | Split view: the original document on the left, extraction on the right. Elicit's upload modal shows "1 of 2 · Uploading & Processing". Becomes our **provenance panel** ("from Eczacılık_talepler.xlsx, sheet Sayfa1, row 12") and the per-file stage line | |
| 10 | [7shifts: "We found some warnings. Let us fix them!"](https://mobbin.com/screens/8796902e-18e6-4f82-98d8-2146b96be325) and [Base44: readiness scan](https://mobbin.com/screens/71d29ab5-bd1b-46a9-a9d7-0932827e94a4) | Four counted categories (Exceptions / Conflicts / Overtime / Unassigned) with plain one-liners and "Yes, fix them for me". Base44 adds a readiness bar *Not ready · Needs improvement · Ready* with "Key issues" vs "Full report". Becomes the **pre-check** panel | modal interruption: our pre-check is always visible, never a blocking popup |
| 11 | [Vercel data editor: edited cell marker and "Review changes (1)"](https://mobbin.com/screens/39a4b62e-a57b-43e7-af25-cc4d651e6c8c) | Amber outline plus a revert icon on an edited cell, and a primary "Review changes (n)" button. Becomes our **changed vs imported** indicator and changes sheet | |
| 12 | [Workable: left stepper, centre form, right help panel](https://mobbin.com/screens/86098dde-cc89-427b-a616-004235ecbb24) | Three-column wizard with ✓ on done steps and a contextual right panel. Becomes our **desktop three-column layout** | the right panel as static help text: ours is a live summary |

Supporting references:
- [Clockwise: choices with one-line explanations](https://mobbin.com/screens/33610c69-37a3-4c1b-9876-20b67cc77aa2): radio cards for "Maximize / Balance / Protect". Pattern for the Must / Try-to explainer.
- [Front: rules list with Enabled toggles](https://mobbin.com/screens/5a449f27-f873-4a21-96bd-2c07e5536153): many-rules list density.
- [Semrush: original vs new with score delta](https://mobbin.com/screens/ed82aafc-c4dc-442d-87fc-359f7347f940): compare runs.
- Mobile: [Public: segmented progress bar at the top](https://mobbin.com/screens/f350f14f-30f4-4391-9326-2633d5c38c1e), [MacroFactor: numbered vertical steps with a CTA](https://mobbin.com/screens/017a7cb1-677e-44a0-97ce-bdd3b49d42e9).

### Interaction patterns named (used throughout)

| Pattern | Where |
|---|---|
| **Sentence-with-slots rule card** (ClickUp #1) | every rule, every proposal, every template |
| **Guided, not gated, stepper** (Workable #12) | steps are always reachable. Only Generate checks readiness |
| **Live consequence count** (Square #5) | affected-count badge, scope sentence, "Include only these 212" |
| **Suggest → review → accept** (AirOps #7, Copy.ai #8) | NL proposals, file extraction, copied rules, presets, pre-check fixes |
| **Provenance chip** (Mistral #9) | the source chip on each card and "from file X row 12" |
| **Readiness meter with fix-it list** (7shifts/Base44 #10) | pre-check |
| **Edited-cell marker and change review** (Vercel #11) | class list vs imported data, with undo |
| **Progressive disclosure** ("Show advanced" switch) | weights 1–10, kind names, solver options, raw params |

## 2. Information architecture and layout

```
/generate?term=2026-BAHAR&step=scope|classes|rules|check|run[&advanced=1]
┌───────────────┬──────────────────────────────────────────────┬─────────────────────────┐
│ STEP RAIL     │ STEP WORKSPACE                               │ SUMMARY  "What will      │
│ (216 px)      │ (fluid)                                      │ happen" (336 px)         │
│ 1 Scope    ✓  │  1 Scope: term · kind · horizon · weeks      │ sentence summary         │
│   Bahar W1–14 │  2 Classes: filter bar, table, bulk bar      │ 6 mini stats             │
│ 2 Classes     │  3 Rules: Add-rule bar, review tray,         │ readiness meter +        │
│   1 276 in ·  │     rule list grouped                        │   top 3 issues           │
│   38 out      │  4 Pre-check: readiness + issues + fixes     │ estimated time           │
│ 3 Rules       │  5 Generate: options, progress, result,      │ [ Generate ]  ⌘↵         │
│   23 must ·   │     compare                                  │ keep-changes-small toggle│
│   14 try · ⚠2 │                                              │ result card after a run  │
│ 4 Pre-check ⚠ │                                              │                          │
│ 5 Generate    │                                              │                          │
│ ─────────     │                                              │                          │
│ Preset ▾      │                                              │                          │
│ Undo · Redo   │                                              │                          │
│ Show advanced │                                              │                          │
└───────────────┴──────────────────────────────────────────────┴─────────────────────────┘
```

- **One screen, five steps.** The workspace shows one step at a time. The rail is a `<nav>` that shows live status under each step label. Steps are never locked: an experienced planner can jump to Rules, type one sentence and press Generate. First visit opens Scope. Later visits reopen the last step.
- **Generate is always one click away.** It lives in the summary panel on desktop and in the sticky bottom bar on smaller screens. It runs the pre-check first (§3.4). If nothing is blocking, it starts the run.
- **The studio state is a server-side draft** per term and per kind. It autosaves (§7, backend needed), so leaving and coming back restores everything. "Adjust and re-run" means you never start from an empty page.
- **Advanced layer**: the "Show advanced" switch in the rail footer (persisted in `localStorage.smartsched.studio.advanced`, mirrored in `?advanced=1`). It reveals:
  - the 1–10 weight slider next to Low/Normal/High;
  - the constraint `kind` (mono) and raw params (read-only JSON disclosure) on each card;
  - "applies to this run only / whole term";
  - global weight per preference type (the old six sliders);
  - solver time limit, seed and workers;
  - an "Export draft as JSON" option.
- **App shell**: on `/generate` below 1440 px, the global sidebar starts collapsed (56 px rail). This is allowed by `navigation-shell.md §3.1`, and the user may override it. It gives the workspace room for the class table.

### Old /generate mapped to Studio
| Today (`generate-view.tsx`) | Studio |
|---|---|
| Card 1 term/kind/horizon/week chips | Step 1 Scope (same controls plus scope sentence) |
| Card 2 prompt + chips + proposed list | Step 3 Rules → "Write it" box. Proposals land in the review tray as rule cards |
| Card 3 weight sliders, time limit, seed, stability | Advanced layer (weights per type in Rules, solver options in Generate). Stability becomes the plain toggle "Keep changes small compared with run #41" in the summary |
| Sticky Generate bar | Summary panel CTA (desktop) or sticky bottom bar (< 1280) |

## 3. Step-by-step interaction spec

### 3.1 Step 1, Scope
- **Term** `Select` (defaults to the active term from the shell term switcher; changing it here also switches the shell term, with a toast).
- **Kind** segmented control `Classes | Exams` (`Dersler | Sınavlar`).
- **Horizon** segmented control:
  - Classes: `One week | A month | Whole term`. Week chips `W1…W16` with dates; holiday weeks disabled with a reason in the tooltip.
  - Exams: `Exam period`, a `Select` of FINAL/BUT week groups plus an optional date-range picker. It maps to `horizon=WEEK` with `horizon_params.weeks` (see open question 3).
- **Scope sentence** (live, `aria-live="polite"`, recomputed on every change):
  - TR: "**14 hafta** boyunca **61 derslikte** **1.276 ders** planlıyorsunuz."
  - EN: "You are planning **1,276 classes** in **61 rooms** for **14 weeks**."
  - Numbers use `Intl.NumberFormat(locale)`, so TR gets `1.276` and EN gets `1,276` (navigation-shell §3.6).
  - Second line (muted): "38 left out · 112 pinned · 3 weeks are holidays".
- **Previous run** line: "Last good run: #41 · 2 days ago · All rules met". It is a link to the report.
- Empty states:
  - No term: CTA "Create a term" (ADMIN).
  - No requests imported for this kind: card "Nothing to plan yet. Import the planning list (Excel) first." with a primary CTA to `/import?source=planning|exam`.

### 3.2 Step 2, Class list
Data: `GET /requests/meetings?term_id=&…` (classes) or `GET /requests/exams?term_id=&…` (exams). One row is one weekly meeting of a section. Helper text: "Each row is one weekly class meeting from your planning list."

**Toolbar**
```
[Search: course, instructor, room]  [Faculty ▾] [Program ▾] [Year ▾] [Day ▾] [Building ▾] [Status ▾]  [+ Filter]  [Columns]
Quick: (Needs a room 1 302) (Changed 17) (Pinned 112) (Left out 38) (Needs review 31) (Evening İÖ 96) (No day/time 41)
```
- Filters are removable chips (Qatalog #6). The `+ Filter` builder (Flodesk #6) offers all/any and one level of groups.
- Search is Turkish-aware: casefold İ/ı, diacritic-insensitive (requests-inbox §3.5).
- **"Only these" quick action**: when any filter is active, a bar appears above the table: "212 classes match · **Plan only these** (leave out the other 1,064) · **Leave these out**". This is a single undoable action that writes the draft's include set.

**Columns** (TanStack Table plus react-virtual, 44 px rows, sticky header, first three columns sticky ≥ 1280):
`☐ · In plan (switch) · Course (code + name, §label) · Program (faculty › program, İÖ badge) · Year · Day & time (e.g. "Wed P7–P9 · 13:30–15:50") · Weeks ("1–14") · Students · Mode · Preferred rooms (chips) · Pin (lock glyph + room/time) · Status (NEEDS_REVIEW etc.) · Changed (dot)`
Exams: `☐ · In plan · Course · Programs (merged chip "3 programs · 70 students") · Date · Time · Students · Rooms needed · Venue request · Pin · Changed`.

**Include / exclude**
- The row switch "In plan" (`Plana dahil`) changes only the draft's exclusion set. It never deletes or archives the request. Excluded rows render at 60 % opacity with an "Left out" chip, and stay findable via the "Left out" quick filter.

**Inline edit** (double-click or `e`; same controls as requests-inbox §3.2)
| Field | Control | Endpoint |
|---|---|---|
| Students (enrolment) | number input | `PUT /sections/{id}` (**backend needed**: enrolment and mode live on `sections`) |
| Mode | select (Face-to-face, Online, Hybrid, UZEM, Async, Hospital, Simulation) with "needs a room" hint | `PUT /sections/{id}` (**backend needed**) |
| Day & time | day select + period-range picker (P1–P18 with clock times) + "Let SmartSched choose the day" checkbox (`flexible_day`) | `PUT /requests/meetings/{id}` |
| Weeks | week-set chip picker (1–14, "last 7 weeks" shortcut) | `PUT /requests/meetings/{id}` |
| Preferred rooms | room combobox chips (requests-inbox §3.4 chip editor) | `PUT /requests/meetings/{id}` (`requested_room_ids`, `requested_building`, `requested_tags`) |

- Save behaviour: optimistic. On failure, roll back and show an error toast with "Retry". Capacity check runs inline: "A 103 has 47 seats, this class has 60" appears under the cell, with a fix link "Pick a room with ≥ 60 seats". Backed by `POST /requests/meetings/{id}/check-room`.

**Pin** (the lock icon in the row, or `p`)
- The popover has two choices:
  - "Always in room [A 206 ▾]" creates a `room_pin` rule.
  - "Always at this day & time" creates a `fixed_time` rule.
- Pins are rule cards too (source chip **Admin**, sub-label "pinned from class list"), so they show up in Step 3 and in the pre-check. Unpinning deletes that rule (undoable).

**Bulk** (selection bar slides up, requests-inbox §3.6): "31 selected · Leave out · Put back · Set students… · Set preferred building… · Pin to room… · Make a rule from these… · Export".
- "Make a rule from these" opens the builder (§3.3.2) with "applies to" prefilled with the selection. This is method (f), see §3.3.

**Changes vs imported data** (Vercel #11)
- Edited cells get a 2 px `--warning-border` underline plus a "↺" button that reverts that field.
- The footer reads "1,276 in plan · 38 left out · 112 pinned · **17 changed from the imported file** · [Review changes]".
- "Review changes" opens a right Sheet containing a Diff Table (beautifului): each row shows course, field, imported value (struck through), current value, and a "Revert" button. "Revert all" asks for confirmation.
- Requires the imported snapshot (**backend needed**, §7).

**Undo / redo**
- A studio-wide stack (Zustand) holds every class-list and rule mutation as {forward call, inverse call}.
- `⌘Z` / `⌘⇧Z`, rail buttons, and the toast "Undo" (8 s, navigation-shell §3.7).
- Requests are sent immediately. Undo sends the inverse request. The stack survives step changes but not page reloads; after a reload, "Review changes" plus revert covers it.

**Make a rule from a row** (row ⋯ menu): "Keep this class in its current room every week", "Never use room X for this class", "Same room as…". Each opens the builder prefilled.

### 3.3 Step 3, Preferences & rules (the core)

**Layout**
```
Add-rule bar:  [ ✦ Write it in your own words…                         ] [Analyse]
               [Pick a template] [Upload a file] [Copy from last term/run] [Use a preset]
Policy switches (one-click common rules):  TIP rooms only for Medicine ◻ · Evening (İÖ) in B/C blocks ◻ · Same room every week ◼ · Don't put small classes in big halls ◼
Review tray (only when proposals exist):  "7 suggestions to review · Accept all ready (5)"   cards…
Rule list:  [Search rules] [Source ▾] [Must/Try ▾] [Problems only]   Group by: Topic | Source
            ▸ Must (23)   ▸ Try to (14)   ▸ Built-in (6, always on)   ▸ Turned off (3)
```

#### 3.3.0 Rule card anatomy (the one shape)
```
┌───────────────────────────────────────────────────────────────────────────────┐
│ [✦ AI]  Keep  [Eczacılık] classes in  [C block]  on  [Monday]          [⋯]  │  sentence with slot chips
│ (●Must | ○Try to)  How important: (Low | ●Normal | High)   applies to 42 classes ›│
│ "eczacılık pazartesi C blokta kalsın", your text, today 10:42                 │  provenance (muted, lang="tr")
│ ⚠ Clashes with "Room C 601 closed on Mondays" · [Show both] [Fix…]            │  only when a conflict exists
└───────────────────────────────────────────────────────────────────────────────┘
```
- **Sentence**: rendered from the kind template in the user's locale. The catalogue comes from `GET /constraints/kinds`, which must return titles and sentence templates (**backend needed**: today it returns names only; `app/ai/catalog.py::catalog_dict()` already holds TR/EN titles). Slots are buttons. Clicking one opens the right picker: room combobox, programme combobox, day chips, period-range picker, number stepper, week picker. Resolved entities with confidence < 0.8 get a dotted underline and "Did you mean A 205 or A 206?" from `ResolvedEntity.candidates`.
- **Source chip** (icon + text, never colour alone):

| Chip | TR | Meaning | Icon |
|---|---|---|---|
| File | Dosya | came from the imported planning list (requested room, "same room as", locked definitive room) | `file-spreadsheet` |
| Admin | Yönetici | made by a planner here (template, pin, policy switch, accepted fix) | `user-round` |
| AI | YZ | proposed by AI from typed text and accepted | `sparkles` |
| Upload | Yükleme | extracted from an uploaded preference file and accepted | `file-up` |
| Built-in | Sistem | always-on basics (no room double-booking, capacity, no clash for a programme-year or an instructor) | `shield` |

  `Upload` needs a new `source` value and a `source_ref` JSON on `constraints` (**backend needed**). Built-in cards are read-only and live in their own collapsed group.
- **Must / Try to**: a two-option segmented control (radiogroup), with plain explanation on first use and in a tooltip:
  - **Must** (`Kesin`): "SmartSched will never break this. If it can't be done, it stops and tells you exactly why." (`hardness=hard`)
  - **Try to** (`Mümkünse`): "SmartSched follows this whenever it can, and tells you where it couldn't." (`hardness=soft`)
  - When a kind only allows one hardness (catalogue), the other option is disabled with the reason ("Room double-booking is always a Must").
  - Turning a Try-to into a Must shows an inline note (not a modal): "Must-rules can make a plan impossible. The pre-check will tell you right away." The pre-check re-runs.
  - Turning a **File** Must into Try-to asks for confirmation, because the faculty asked for it.
- **How important** (Try-to only): `Low | Normal | High`, mapped to weight 2 / 5 / 8 (AI default 5 = Normal). Helper: "When two preferences compete, the more important one wins." Advanced layer adds the 1–10 slider. Values that are not 2/5/8 show as "Custom (7)" in the segmented control.
- **Affected-count badge**: "applies to 42 classes", from `POST /constraints/preview` (**backend needed**; debounced 400 ms while editing; skeleton pill while loading). Click opens Step 2 filtered to those classes (`?rule=<id>`).
  - 0 matches: amber "matches no classes, check the name", plus a Did-you-mean if any.
  - More than 50 % of classes on a Must: info note "This affects most of your classes."
- **Conflict line**: shown when the pre-check reports rule conflicts (§3.4). "Show both" scrolls to and outlines the other card (2 px `--infeasible-border`, 120 ms). "Fix…" offers: make one of them Try-to · edit · turn one off.
- **⋯ menu**: Edit in builder · Duplicate · Turn off/on (`enabled`) · Applies to this run only (advanced) · Show source (opens the provenance panel) · Delete (undoable).
- Saves: `PUT /constraints/{id}` debounced 400 ms. The card shows "Saved ✓" for 1 s (transitions.dev free "Spinner to check morph" pattern, re-implemented).

#### 3.3.1 (a) Write it in your own words (TR/EN)
- An autosize textarea (3–10 rows) with a locale placeholder. Examples (also offered as "Try:" links under the box):
  - TR: "TIP derslikleri sadece Tıp Fakültesi için olsun. Eczacılık pazartesi C blokta kalsın. Hemşirelik 1. sınıf 17:30'dan sonra ders almasın."
  - EN: "TIP rooms only for the Faculty of Medicine. Keep Pharmacy in C block on Mondays. No first-year Nursing classes after 17:30."
- **Suggestion chips** (max 8, horizontally scrollable) come from data plus locale: "Evening (İÖ) in B/C blocks", "Same room every week", "Keep A 204 free Wed afternoon", "Exams: at least 1 period between exams of the same class"… Clicking one inserts the phrase at the cursor (generate-and-chat §3.2).
- **Analyse** (`⌘↵`) calls `POST /terms/{id}/elicit {text, lang}` and returns `ElicitOut`. While it runs, the button shows a spinner and "Reading your rules…" (≤ 10 s typical); the box stays editable. Results become cards in the **review tray** with a dashed border and an AI chip. Each card has **Accept · Edit · Dismiss**. The tray header has "Accept all ready (n)". `status=needs_review` cards cannot be bulk-accepted.
  - Accept calls `POST /terms/{id}/elicit/accept {proposals}` → `AcceptOut.created[]`. The card animates from the tray into its group in the list (§6).
  - Hovering a card highlights its originating sentence in the textarea, so you can see where it came from.
  - **Unparsed** sentences become amber notes, for example: "I couldn't turn this into a rule: 'NRS 450 son 7 hafta': this is a week pattern. **Edit the class's weeks** (opens Step 2 filtered) · Keep as a note · Rephrase".
- No AI key: the box shows an inline note "Writing rules in your own words needs AI. An admin can turn it on in Settings → AI." Templates, presets and copy still work. Upload falls back to "We can read Excel/CSV columns without AI" (open question 5).

#### 3.3.2 (b) Pick a template (structured builder)
A gallery dialog (Asana #3 / Calendly #4): left, topic tabs (*Rooms · Times · Buildings · Programmes · Exams*); right, cards. Choosing a template opens the builder (Jira #2): **preview sentence on top** (live, with affected count), fields below, then "Must / Try to", "How important", and "Add rule".

| Template (EN / TR) | Fields | Kind | Default |
|---|---|---|---|
| Keep {programme/course} in building {X} [on {days}] / {Program} derslerini {X} blokta tut [{günler}] | applies-to picker, building, days | `building_preference` | Try, Normal |
| No classes after {HH:MM} [or before {HH:MM}] for {programme, year} / {Program, sınıf} için {SS:DD}'den sonra ders olmasın | time pickers snapped to periods (shows "after P11 16:50–17:30"), applies-to | `day_window` | Must |
| Room {R} only for {programme/faculty} / {R} dersliği sadece {fakülte} için | rooms, who may use them | `room_tags` (tag rooms, e.g. TIP) or **backend needed** `room_reserved_for` (selector negation) | Must |
| Never use room {R} for {…} / {R} dersliğini {…} için kullanma | rooms, applies-to | `room_forbid` | Must |
| Always put {course} in room {R} [from {date}] / {ders} her zaman {R} dersliğinde [{tarih}'den itibaren] | course, room, from date | `room_pin` | Must |
| Prefer room(s) {R…} for {…} / {…} için {R…} tercih et | ordered rooms | `room_preference` | Try, Normal |
| Same room as course {Z} / {Z} dersiyle aynı derslik | course pair/group | `same_room_group` | Try, High |
| Same room every week / Her hafta aynı derslik | applies-to (default all) | `same_room_across_weeks` | Try, Normal |
| Needs a computer lab / Bilgisayar laboratuvarı gerekli | applies-to, tag PC/LAB | `room_tags` (required) | Must |
| Room {R} closed on {day, times, weeks} / {R} {gün, saat, hafta} kapalı | room, day, periods, weeks | `room_closed` | Must |
| Evening programmes in buildings {…} / İkinci öğretim {…} bloklarında | buildings | `evening_programs_in_buildings` | Try, Normal |
| Don't put small classes in big halls / Küçük sınıfları büyük amfiye koyma | seats-per-penalty (advanced) | `min_capacity_waste` | Try, Low |
| Exams: at least {N} periods between exams of {class} / Aynı sınıfın sınavları arasında en az {N} ders saati | N (number stepper 0–6), applies-to | `exam_gap` | Must |
| Exams: at most {N} exams per day for {class} / Günde en fazla {N} sınav | N, applies-to | `max_exams_per_day` | Must |

- Field validation is client-side (zod) against the catalogue schema, then server-side on save. Required fields are marked "(required)" in text, not only with an asterisk.
- **Applies to** picker (shared with filters): Programme · Course · Year · Instructor · Faculty · "These selected classes" · "All classes". It shows a live count (Square #5).
- Kind-specific notes appear in plain words under the fields, e.g. "Periods are 40 minutes. 17:30 is the start of P12."

#### 3.3.3 (c) Upload preference files (Excel, CSV, Word, PDF, text)
Entry: the "Upload a file" button, or dropping files anywhere on Step 3 (a full-panel drop overlay appears on `dragenter`).

1. **Dropzone** (beUI File Upload block, §9): "Drop files here or choose · Excel, CSV, Word, PDF or text · up to 10 files, 20 MB each". There is also a **Paste text** tab (for e-mails from faculties). Rejected type or size shows inline per file: "This is a .pptx. Save it as PDF and try again."
2. **Processing**: per-file row with a real stage line, *Uploading 40 % → Reading → Finding rules → Ready* (Elicit #9). No fake timers. Calls `POST /terms/{id}/preferences/upload` (multipart) → `{upload_id}`, then polls `GET /terms/{id}/preferences/uploads/{upload_id}` (**backend needed**) or uses SSE.
   - If the file looks like a planning list (shape A headers), show: "This looks like a full planning list. Import it in **Import** instead?" with a link to `/import?source=planning`, plus "No, read it for preferences".
   - Scanned PDF with no text: "We couldn't find any text in this PDF (it may be a scan). Try the original Word/Excel, or paste the text."
3. **Review table** (AirOps #7 + Copy.ai #8). Summary box on top: "From 3 files we found **18 rules**: 12 ready, 4 need a look, 2 couldn't be read."
   - Tabs: `All 18 · Ready 12 · Needs a look 4 · Couldn't read 2`.
   - Columns: `☐ · From (file · sheet/page · row 12) · Original text (quote, lang-tagged) · Proposed rule (sentence card, compact) · Must/Try · Applies to (count) · Confidence (High/Medium/Low, icon + word) · Problems · Actions ✓ Accept / ✎ Edit / ✕ Reject`.
   - **Provenance panel**: clicking "From" opens a right split pane (Mistral #9). Excel shows the row highlighted with 2 rows of context and the header row. Word/PDF/text show the paragraph with the matched span highlighted (`<mark>`).
   - Edit expands the row into the full rule card editor. Accept / Reject are per row. "Accept all ready (12)" sits in the toolbar. "Reject selected" works on checkboxes. A "Couldn't read" row offers "Rephrase as text…", which moves the quote into the Write-it box.
   - Accept calls `POST /terms/{id}/elicit/accept {proposals, source:"UPLOAD"}`. Accepted rows collapse to a "✓ added" line with Undo. When all are handled, the tray closes with a toast "12 rules added from 3 files · Undo".
4. Uploaded files are listed under "Files used" (rail footer, advanced) with date and counts, and can be re-opened for review.

#### 3.3.4 (d) Copy from last term or a previous run
- Dialog with a `Select` of source: "Run #41 · Bahar W1–14 (2 days ago)" / "2025 Bahar (term)" / "2025-26 Güz (term)".
- Shows that source's rules as compact cards with checkboxes, grouped *Will match · Needs a look · Can't match*. Can't-match means names are re-resolved in the target term, for example "D 107 doesn't exist in this term" or "programme renamed?".
- Calls `POST /constraints/copy {from_run_id|from_term_id, to_term_id, ids?, dry_run}` (**backend needed**). Results land in the review tray (source chip keeps the original source, plus a sub-label "copied from 2025 Bahar").

#### 3.3.5 (e) Presets
- Rail footer `Preset ▾`: "Bahar standard", "Final week", "+ Save current as preset…", "Manage presets".
- A preset is a snapshot of rules (kind, params with names not ids, hardness, weight, enabled, nl_text), scope defaults, and include/exclude *filters* (not row ids, so it transfers across terms).
- Applying a preset first shows a Diff Table: "+ 9 rules to add · ~ 3 to change · − 2 to turn off". Then **Apply** (undoable).
- APIs: `GET/POST /presets`, `PUT/DELETE /presets/{id}`, `POST /presets/{id}/apply {term_id, dry_run}` (**backend needed**).

#### 3.3.6 Other methods (our additions)
- (f) **Make a rule from a class** (row menu / bulk bar, §3.2): prefilled builder.
- (g) **Policy switches**: the 4–6 most common university policies as one-click switches above the list. Each switch is a template instance, visible as a normal card once on.
- (h) **Paste a column from Excel** into the class list (advanced). Select a column, paste a vertical range of N values, then preview "Set students for 24 classes" and apply as one undoable bulk edit.
- (i) **Accept a fix from the pre-check** (§3.4): the fix becomes a card with source Admin and sub-label "from pre-check".
- (j) **After the run**: chat edits (generate-and-chat §3.5) are already rule cards (`add_constraint`). The studio shows them under source AI when you come back.
- Future (backlog): faculty secretaries submit preferences through a form that lands in this review tray (ROADMAP "Request inbox workflow").

#### 3.3.7 Many rules
- Groups (Must / Try to / Built-in / Turned off) are collapsible and show counts. Group by can switch to Topic (Rooms, Times, Buildings, Programmes, Exams) or Source.
- Search matches the sentence and the nl_text. Filter chips: Source, Must/Try, "Problems only" (conflicts, 0 matches, needs review), "Changed since run #41".
- More than 40 cards: compact density (one-line sentence, controls on hover/focus), plus a virtualised list (`@tanstack/react-virtual`).
- Sticky mini-counter on top: "23 must · 14 try · 2 problems".

### 3.4 Step 4, Pre-check (live feasibility)
- **When**: automatically 1.5 s after the last change anywhere in the studio, and on entering Step 4 or pressing Generate. Calls `POST /runs/precheck {term_id, kind, horizon, horizon_params, draft_id}` (**backend needed**; wraps `app/solver/diagnose.py::static_check` plus a rule-conflict pass; no CP-SAT search, so < 3 s for 1,300 events). The rail and summary show "Checking…" during the call. Results replace the previous ones without layout shift.
- **Readiness meter** (Base44 #10), three states with icon + word:
  - **Ready** (`check-circle-2`, feasible tokens): "Nothing impossible found."
  - **Needs a look** (`alert-triangle`, warning): only Try-to problems or info items.
  - **Blocked** (`x-octagon`, infeasible): at least one class can't be placed under the Must-rules.
- **Counted categories** (7shifts #10): *Impossible classes · Rules that clash · Rules that match nothing · Info*. Each is a tab with its count.
- **Issue card** (reuses run-report DiagnosisCard, compact):
  ```
  ✕ BME 419 §1 · Wed 13:30–15:50 · 102 students
    No room is big enough at that time. Only A 204 (156 seats) is big enough, and the rule
    "A 201–A 204 only for Medicine" keeps it for Medicine.
    [Allow A 204 for BME 419]  [Move to 16:00–18:00]  [Split into 2 rooms]  [Leave it out of this plan]   Show details ▾
  ```
  - The plain-language message comes from Diagnosis `message`, rendered by the AI layer or by templates when there is no key. Never show kind names outside the advanced layer.
  - Fix buttons come from structured fix actions (**backend needed**: `fixes: [{label, action: {type: "constraint_create"|"constraint_update"|"meeting_update"|"exclude", payload}}]`; today `suggestions` are strings).
  - Reuse `app/services/diagnosis_fixes.py` (integration-engineer, in progress 2026-10-08: `structure_diagnosis` / `parse_option` turn suggestion strings into `FixOption`s for a run). The pre-check needs the same parser, but **applies into the draft** (rule cards, class edits, exclusions) instead of creating locked MANUAL assignments on a run.
  - Clicking a fix applies it (undoable), creates or edits the rule card or class row, and re-runs the pre-check. The card animates out when it is resolved.
- **Rule clash card**: "These two rules can't both be true: 'MAT 112 always in A 206' and 'Never use A 206 for MAT courses'." Fixes: *Make the second one Try to · Turn one off · Edit*. Duplicates: "These two rules say the same thing", with fix *Merge*. Tension between Try-to rules (info only): "'Pharmacy in C block' and 'Evening programmes in B block' pull 6 classes in different directions. The more important one wins."
- **Human summary** (also in the right panel):
  - EN: "SmartSched will place **1,238 classes** into **61 rooms** for **weeks 1–14**. It **must** follow **23 rules** and will **try to** follow **14 preferences**. **112 classes are pinned** and won't move. **38 are left out**. It will keep as much as possible from **run #41**. This should take **about 2 minutes** (at most 5)."
  - TR: "SmartSched **1–14. haftalar** için **1.238 dersi** **61 dersliğe** yerleştirecek. **23 kesin kurala** uyacak, **14 tercihi** mümkün olduğunca gözetecek. **112 ders sabitlendi**, yeri değişmeyecek. **38 ders** plan dışında. **#41** numaralı çalıştırmadan mümkün olduğunca az değişiklik yapacak. Tahmini süre **yaklaşık 2 dakika** (en fazla 5)."
- **Estimate**: `estimate_s {low, high}` from precheck (backend heuristic from solver benchmarks: ~16 s for 300 events, ~100 s for 1,300 events, capped by the time limit). Shown as rounded words ("under a minute", "about 2 minutes").
- **Blocked + Generate**: the button stays enabled and opens a short confirmation: "2 classes can't be placed under your Must-rules. SmartSched will stop and explain why. Fix them first, or generate anyway to see the full diagnosis." Options: *Fix first* (primary) / *Generate anyway*. The confirmation respects "100/100 or explain"; we never silently relax.

### 3.5 Step 5, Generate & iterate
- **Before**: the human summary, "Keep changes small compared with run #41" (stability; on by default when a good run exists; helper "Classes that are already well placed stay where they are"), and the run name (optional `label`). Advanced: time limit, seed, workers, weights per preference type.
- **Generate** (`⌘↵`) calls `POST /runs {term_id, kind, horizon, horizon_params:{weeks}, params:{time_limit_s, seed, stability, weights, exclude_event_ids|draft_id}, parent_run_id, label}` → `202 {run_id}`.
  - **Backend needed**: `POST /runs` must accept `draft_id` (or `exclude_event_ids`) so left-out classes are not solved.
  - The studio **does not navigate away**. The summary panel morphs into the run status card from generate-and-chat §3.3: status, phase line, live "Must-rules broken: 0", elapsed time, Cancel. It uses SSE `GET /runs/{id}/events` (fallback: 2 s polling). A toast with "View run" also appears, so the planner can leave.
- **Result card** (FEASIBLE/OPTIMAL):
  ```
  ✓ Run #42 · All must-rules met · Preferences 92/100 · 1,238 placed · 0 conflicts
    vs #41: preferences +3 · 41 classes moved · 2 room changes fewer
    [View timetable] [Open report] [Compare with #41] [Adjust and run again]
  ```
  - "Adjust and run again" keeps all studio state and jumps to the last edited step.
  - "Compare" opens the run-report scenario comparison (run-report §2.5; `/runs/compare?a=41&b=42` is v2).
- **INFEASIBLE**: red result card listing the diagnoses with the same fix buttons as the pre-check. Each fix applies into the studio (not into a child run), then the planner presses Generate again.
- **FAILED**: error id, "Try again", "Copy details".
- **Run history** strip (advanced, under the result card): the last 5 runs from this studio draft with status and scores, plus "Restore this run's rules" (copies rules via §3.3.4).

## 4. States (every part)

| Part | Empty | Loading | Partial | Error | Many | Conflicting |
|---|---|---|---|---|---|---|
| Scope | no term → "Create a term"; no requests → "Import the planning list first" CTA | skeleton chips, scope sentence "Counting…" | holidays in range: "3 of 14 weeks are holidays and are skipped" | weeks failed → inline retry | 16+ weeks wrap; month picker | exam kind but no exam weeks: "This term has no exam weeks. Set them in Settings → Terms" |
| Class list | filter returns 0: "No classes match. Clear filters" | 12 skeleton rows; infinite pages of 200 | some rows NEEDS_REVIEW: amber status + "31 need review in Requests" link | edit failed: rollback + toast; list failed: banner + retry | 1,500 rows virtualised; footer counts | inline capacity note; pin vs forbid → flagged by pre-check |
| Rules | first visit: explainer card "Rules tell SmartSched what must happen and what you'd prefer. Start by writing one sentence, or pick a template." + 3 example chips; Built-in group visible | card skeletons; affected-count pill skeleton | proposals with `needs_review` can't bulk-accept; unparsed sentences as amber notes | AI error: "AI couldn't answer (timeout). Your text is kept. Try again", templates still work; no key: §3.3.1 | §3.3.7 (groups, compact, virtualised) | conflict line on both cards + pre-check tab |
| Upload | dropzone idle with examples of what files work | per-file stage line with real % | some files unreadable → "Couldn't read" tab with reasons | upload failed per file → Retry on the row; whole service down → banner | > 100 extracted rows: tabs + virtualised table + "Accept all ready" | extracted rule clashes with an existing rule → "Needs a look" with the clash shown |
| Pre-check | nothing to check (0 classes) → hidden, summary says "Add classes to plan" | "Checking…" pill; previous results dimmed 60 % | only Try-to issues → Needs a look | precheck endpoint failed → "Couldn't check right now. You can still generate", Generate stays on | > 20 issues: grouped by cause ("14 classes need a bigger room on Wednesday afternoon") with expand | rule-clash tab |
| Generate | no good previous run → stability toggle hidden | status card (QUEUED/RUNNING) | TIMEOUT with a feasible plan → result card with "Stopped at time limit, this is the best plan found" | FAILED card | — | INFEASIBLE card with fixes |

Draft concurrency: if another planner saved the same draft (etag mismatch on autosave), show a banner: "Ayşe Hanım changed this plan 2 minutes ago. **Load their version** · **Keep mine** (overwrites)."

## 5. Copy (TR / EN), key labels and helper texts

| Key | TR | EN |
|---|---|---|
| page title | Plan oluşturucu | Generator Studio |
| page subtitle | Hangi derslerin nasıl yerleşeceğini adım adım belirleyin, sonra planı oluşturun. | Decide step by step what to plan and how, then generate the timetable. |
| step.scope | Kapsam | Scope |
| step.classes | Dersler | Classes |
| step.rules | Kurallar ve tercihler | Rules & preferences |
| step.check | Ön kontrol | Pre-check |
| step.run | Oluştur | Generate |
| kind.course / kind.exam | Dersler / Sınavlar | Classes / Exams |
| horizon | Bir hafta · Bir ay · Tüm dönem · Sınav dönemi | One week · A month · Whole term · Exam period |
| scope.sentence | {weeks} hafta boyunca {rooms} derslikte {n} ders planlıyorsunuz. | You are planning {n} classes in {rooms} rooms for {weeks} weeks. |
| classes.helper | Her satır, planlama listenizdeki bir dersin haftalık bir oturumudur. | Each row is one weekly class meeting from your planning list. |
| classes.inPlan | Plana dahil | In plan |
| classes.leftOut | Plan dışı | Left out |
| classes.onlyThese | Sadece bunları planla ({n}) | Plan only these ({n}) |
| classes.changed | İçe aktarılan dosyadan {n} değişiklik | {n} changed from the imported file |
| classes.reviewChanges | Değişiklikleri gözden geçir | Review changes |
| pin.room / pin.time | Her zaman bu derslikte / Her zaman bu gün ve saatte | Always in this room / Always at this day & time |
| rule.must | Kesin | Must |
| rule.must.help | SmartSched bunu asla bozmaz. Mümkün değilse durur ve nedenini söyler. | SmartSched will never break this. If it can't be done, it stops and tells you why. |
| rule.try | Mümkünse | Try to |
| rule.try.help | SmartSched mümkün olduğunda uyar ve uyamadığı yerleri gösterir. | SmartSched follows this whenever it can and shows you where it couldn't. |
| rule.importance | Önem: Düşük · Normal · Yüksek | How important: Low · Normal · High |
| rule.importance.help | İki tercih çatışırsa önemi yüksek olan kazanır. | When two preferences compete, the more important one wins. |
| rule.appliesTo | {n} derse uygulanıyor | applies to {n} classes |
| rule.matchesNone | Hiçbir dersle eşleşmiyor, adı kontrol edin | matches no classes, check the name |
| rule.clash | Şu kuralla çelişiyor: “{other}” | Clashes with “{other}” |
| source.file / admin / ai / upload / builtin | Dosya / Yönetici / YZ / Yükleme / Sistem | File / Admin / AI / Upload / Built-in |
| add.write | Kendi cümlenizle yazın… | Write it in your own words… |
| add.analyse | Kurala çevir | Turn into rules |
| add.template / upload / copy / preset | Şablondan seç / Dosya yükle / Önceki dönemden kopyala / Hazır ayar kullan | Pick a template / Upload a file / Copy from last term / Use a preset |
| tray.title | İncelenecek {n} öneri | {n} suggestions to review |
| tray.acceptAll | Hazır olanların hepsini ekle ({n}) | Accept all ready ({n}) |
| proposal.actions | Ekle · Düzenle · Vazgeç | Accept · Edit · Dismiss |
| unparsed | Bunu kurala çeviremedim: “{text}”. {reason} | I couldn't turn this into a rule: “{text}”. {reason} |
| upload.drop | Dosyaları buraya bırakın veya seçin · Excel, CSV, Word, PDF veya metin | Drop files here or choose · Excel, CSV, Word, PDF or text |
| upload.stages | Yükleniyor · Okunuyor · Kurallar aranıyor · Hazır | Uploading · Reading · Finding rules · Ready |
| upload.from | {file} · {sheet} · {row}. satır | from {file} · {sheet} · row {row} |
| upload.tabs | Tümü · Hazır · Bakılması gereken · Okunamayan | All · Ready · Needs a look · Couldn't read |
| upload.looksLikePlanningList | Bu bir planlama listesine benziyor. İçe Aktar bölümünden yüklemek ister misiniz? | This looks like a full planning list. Import it in Import instead? |
| check.ready / needsLook / blocked | Hazır / Bakılması gereken var / Engel var | Ready / Needs a look / Blocked |
| check.blocked.confirm | {n} ders kesin kurallarınızla yerleştirilemiyor. SmartSched durup nedenini açıklayacak. | {n} classes can't be placed under your Must-rules. SmartSched will stop and explain why. |
| check.fixFirst / generateAnyway | Önce düzelt / Yine de oluştur | Fix first / Generate anyway |
| run.keepSmall | #{id} çalıştırmasına göre değişiklikleri az tut | Keep changes small compared with run #{id} |
| run.keepSmall.help | Zaten iyi yerleşmiş dersler yerinde kalır. | Classes that are already well placed stay where they are. |
| run.estimate | Tahmini süre: {words} | Estimated time: {words} |
| run.generate | Planı oluştur | Generate timetable |
| run.adjust | Düzenle ve yeniden çalıştır | Adjust and run again |
| advanced | Gelişmiş ayarları göster | Show advanced |
| noKey | Kendi cümlenizle kural yazmak için YZ gerekir. Yönetici Ayarlar → YZ'den açabilir. | Writing rules in your own words needs AI. An admin can turn it on in Settings → AI. |

Copy rules:
- Never show `hard`, `soft`, `constraint`, `weight`, `kind`, `infeasible` or `horizon` outside the advanced layer.
- Use the periods' clock times next to P-numbers ("P7 13:30").
- Use `toLocaleUpperCase('tr')` for codes.
- Turkish strings run about 20 % longer, so every chip and button tolerates 2 lines or truncates with `title`.

## 6. Interaction details: keyboard, touch, motion

**Keyboard** (documented in the `?` sheet; no single-key shortcuts fire inside inputs)
- Steps: `Alt+1…5` jump to a step · `[` / `]` previous/next step · `⌘↵` Generate (when focus is not in a textarea; in the Write-it box `⌘↵` = Turn into rules) · `⌘Z` / `⌘⇧Z` undo/redo · `⌘⇧A` toggle advanced.
- Class list (requests-inbox §3.7 conventions): `j/k` rows · `x` select · `Shift+click` range · `e` edit cell · `i` in plan / left out · `p` pin · `/` search · `f` filters · `Esc` closes the popover, then clears selection.
- Rule list: `j/k` cards · `m` / `t` set Must / Try to · `1/2/3` Low/Normal/High · `e` edit · `Enter` on a slot opens its picker · `Delete` removes (with undo toast) · `n` focus the Write-it box.
- Review tray / upload table: `a` accept · `r` reject · `e` edit · `⌘⇧Enter` accept all ready. After accept/reject, focus moves to the next pending row; when none remain, it returns to the tray heading.
- Pre-check: `Tab` through issue cards. Fix buttons are real buttons. `Enter` applies, and focus goes to the next issue.

**Touch** (≤ 1024 px or `pointer: coarse`)
- 44 px minimum targets.
- Class rows become cards with the In-plan switch at the right. Long-press (400 ms) enters select mode. Edits open bottom sheets (beUI Bottom Sheet, snap 60 / 100 %).
- Rule slot pickers open as bottom sheets.
- The upload dropzone becomes a "Choose files" button (no drag on phones) plus "Paste text".
- Swipe on rule cards is **not** used (too easy to trigger by accident on a must-rule). Actions sit in the ⋯ menu.

**Motion** (all ≤ 300 ms, token-driven, removable)

| Moment | Animation | Token | Reduced motion |
|---|---|---|---|
| Step change | content cross-fade + 8 px x-offset | `--dur-base` 180 ms, `--ease-out` | opacity only, ≤ 100 ms |
| Rail status change (count, ✓) | number tween (not spring), icon swap fade | `--dur-base` | instant |
| Proposal accepted → moves into rule list | shared-layout move (`layoutId`) | `--spring-drop` (≈ 240 ms) | card disappears from tray, appears in list (fade ≤ 100 ms) |
| Rule card add/remove | height + fade via `AnimatePresence` | `--dur-base` | instant |
| Conflict "Show both" | scroll into view + 2 px outline appears | `--dur-fast` 120 ms | `scrollIntoView({behavior:"auto"})`, outline static |
| Must/Try and Low/Normal/High indicator | segmented slide | `--spring-drop` | instant |
| Upload stage progress | width tracks real progress; stage label cross-fade | `--dur-fast` | width jumps, no fade |
| Pre-check "Checking…" | opacity pulse 1.2 s on the pill only (not layout) | n/a (looping indicator) | static "Checking…" text |
| Summary → run status card | height morph | `--dur-max` 300 ms | swap without morph |
| Selection bar | slide up 8 px + fade | `--dur-base` | appears |

- Never animate the class table rows on sort or filter (tokens.md §6).
- No count-up spring longer than 300 ms. KPI-style `--spring-count` is **not** used here.

## 7. API calls per part

Existing endpoints (verified in `smartsched/backend/app/api/v1` on 2026-10-08) and the new ones. **Backend needed** = not yet present.

| Part | Call | Status |
|---|---|---|
| Scope | `GET /terms`, `GET /terms/{id}/weeks`, `GET /rooms` (count), `GET /runs?term_id=` (last good run) | exists |
| Scope sentence / counts | `GET /requests/stats?term_id=&kind=` (counts per status) | exists (`/requests/stats`), extend with `excluded`, `pinned`, `changed` once the draft exists |
| Class list (classes) | `GET /requests/meetings?term_id&status&needs_room&day&program_id&search&limit&offset` | exists. **Backend needed**: filters `faculty_id`, `class_year`, `building`, `mode`, `changed=true`, `ids=`, `rule_id=` (classes matched by a rule) |
| Class list (exams) | `GET /requests/exams?…` | exists (same filter additions) |
| Section-level data | `GET /sections?term_id&search&program_id` | exists |
| Edit day/time/weeks/rooms/flexible | `PUT /requests/meetings/{id}`, `PUT /requests/exams/{id}` | exists |
| Edit enrolment / mode | `PUT /sections/{id}` | **backend needed** |
| Bulk edit | `PUT /requests/meetings/bulk {ids, patch}` | **backend needed** (avoid 200 sequential PUTs) |
| Capacity check | `POST /requests/meetings/{id}/check-room {room_ids}` | exists |
| Changed vs imported | `imported` snapshot (normalised values at import time) on `MeetingRequestOut` / `SectionOut`, plus `POST /requests/meetings/{id}/revert {fields}` | **backend needed** |
| Studio draft (include/exclude, scope, last step, preset) | `GET /terms/{id}/studio?kind=` → `{draft_id, etag, scope, excluded_ids, …}`; `PUT /terms/{id}/studio` (If-Match) | **backend needed** |
| Rule list | `GET /constraints?term_id=&run_id=&enabled=` | exists |
| Create / edit / delete rule | `POST /constraints`, `PUT /constraints/{id}`, `DELETE /constraints/{id}` | exists. **Backend needed**: `source` adds `UPLOAD` (and `BUILTIN` read-only), new `source_ref` JSON `{file, sheet, row, page, quote, upload_id}`, `title` |
| Catalogue (templates, sentence, allowed hardness, field schema) | `GET /constraints/kinds` returning `catalog_dict()` (TR/EN titles, descriptions, params schema, allowed hardness) | exists but returns names only, so **backend needed** (data already in `app/ai/catalog.py`) |
| Affected count while editing | `POST /constraints/preview {term_id, kind, params, hardness}` → `{affected_count, sample[], issues[]}` | **backend needed** |
| Write it (NL) | `POST /terms/{id}/elicit {text, lang}` → `ElicitOut` | implemented in `app/ai/elicit.py`, **route not yet mounted** (ai-engineer). Frontend currently calls mock `/constraints/propose`; switch to this |
| Accept proposals | `POST /terms/{id}/elicit/accept {proposals, run_id?}` → `AcceptOut` | as above (`accept_proposals` exists, route missing) |
| Upload preference files | `POST /terms/{id}/preferences/upload` (multipart, many files, or `{text}`) → `{upload_id}`; `GET /terms/{id}/preferences/uploads/{upload_id}` → `{files:[{name, status, stage, progress, error}], proposals:[ProposedConstraint + source_ref], unparsed:[…]}`; `GET /terms/{id}/preferences/uploads` (history) | **backend needed** (ai-engineer + backend). Suggested readers: `openpyxl` (MIT) for xlsx, `csv` stdlib, `python-docx` (MIT), `pypdf` (BSD-3-Clause) or the Claude API's native PDF input |
| Copy rules | `POST /constraints/copy {from_run_id|from_term_id, to_term_id, ids?, dry_run}` → `{will_match[], needs_review[], cannot_match[]}` | **backend needed** |
| Presets | `GET/POST /presets`, `PUT/DELETE /presets/{id}`, `POST /presets/{id}/apply {term_id, dry_run}` | **backend needed** |
| Pre-check | `POST /runs/precheck {term_id, kind, horizon, horizon_params, draft_id}` → `{readiness, diagnoses:[Diagnosis + fixes[]], rule_conflicts:[{rule_ids, type: contradiction|duplicate|tension, message, fixes[]}], counts, estimate_s:{low, high}, summary}` | **backend needed** (wraps `solver/diagnose.py::static_check`) |
| Generate | `POST /runs {term_id, kind, horizon, horizon_params, params, prompt?, parent_run_id, label}` → `202 {run_id}` | exists. **Backend needed**: accept `draft_id` / `params.exclude_event_ids`; optional horizon `EXAM_PERIOD` (open question 3) |
| Progress | `GET /runs/{id}/events` (SSE), `GET /runs/{id}` | exists |
| Cancel | `DELETE /runs/{id}` | exists |
| Result / compare | `GET /runs/{id}/summary`, `GET /runs/{a}` + `GET /runs/{b}` (client-side delta) | exists; `/runs/compare` is v2 (run-report §2.5) |
| Restore a run's rules | `POST /constraints/copy {from_run_id}` | **backend needed** (same as copy) |

Client-side libraries: TanStack Query keys `["studio", termId, kind]`, `["constraints", termId]`, `["meetings", termId, filters]`. Optimistic updates with rollback. The undo stack lives in a Zustand slice `studio.history`.

## 8. Responsive layout

| Width | Layout |
|---|---|
| **360** | **Stepper mode** (Public/MacroFactor refs): top progress bar with 5 segments + "2/5 · Classes"; one step per screen. Sticky bottom bar: `‹ Back` · summary pill "1,238 classes · Ready ✓" (opens the summary as a bottom sheet) · `Next ›`, which becomes **Generate** on step 5. Class list = cards (course, programme, day/time line, students, in-plan switch, pin glyph); filters in a right Sheet; "Plan only these" as a sticky chip. Rule cards are full width, controls wrap under the sentence, the slot picker is a bottom sheet. The Add-rule bar collapses to the Write-it box + a "More ways ▾" menu. Upload = file picker + paste. Pre-check is a list of issue cards with full-width fix buttons. 16 px gutters. |
| **768** | Horizontal step tabs under the page header (scrollable, with status dots); single workspace column; summary in the sticky bottom bar (sentence truncated, tap to expand as a bottom sheet) + Generate button. Class table shows 6 columns (in plan, course, program, day & time, students, pin), the rest in a row expander. Rule list single column. Upload review table → 4 columns + expander. 24 px gutters. |
| **1280** | Three columns: rail 200 px · workspace fluid · summary 304 px. App sidebar starts collapsed (56 px). On the Classes step and the upload review, the summary auto-collapses to a 48 px rail ("Summary ›" + readiness icon); Generate moves to a sticky bar under the workspace. Class table: 9 columns, sticky first three. 32 px gutters. |
| **1920** | Three columns: rail 216 px · workspace (max 1200 px) · summary 360 px. App sidebar expanded (240 px). All class table columns + Instructor + Notes. The rules step shows the rule list and the review tray side by side (tray 420 px) when a tray exists. The provenance panel opens inline (no overlay). Content max-width 1600 px, centred. |

No horizontal page scroll at any width. Only the class table and upload table scroll internally.

## 9. Component list (sources and licences)

All sources were re-checked on 2026-10-08 unless noted. The shared table is in `navigation-shell.md §9`. Note that this repo's shadcn style is `base-nova` built on `@base-ui/react` (see `src/components/ui/SOURCES.md`), not Radix. The a11y semantics are equivalent.

| Component | Use here | Source | Licence | Note |
|---|---|---|---|---|
| Button, Badge, Card, Checkbox, Dialog, DropdownMenu, Input, Label, Popover, Progress, ScrollArea, Select, Separator, Sheet, Skeleton, Slider, Switch, Table, Tabs, Textarea, Tooltip | everywhere | shadcn/ui (already in `src/components/ui`) | MIT | add `accordion`, `toggle-group`, `alert-dialog`, `radio-group` via `npx shadcn@latest add …` |
| Command (cmdk) | room/programme/course comboboxes in slots and filters | shadcn `command` + cmdk | MIT | present |
| DataTable + virtualiser | class list, upload review, many rules | `@tanstack/react-table`, `@tanstack/react-virtual` | MIT | present |
| **File Upload** (attachment rows, drag state, per-row status, retry/remove, `onFilesRejected` reasons) | upload dropzone + per-file rows | beUI https://beui.dev/components/blocks/file-upload | MIT (repo `github.com/starc007/ui-components` LICENSE: "MIT License, Copyright (c) 2026 Saurabh Chauhan", fetched 2026-10-08) | `bunx --bun shadcn add @beui/attachment-upload`. **Must change**: drive `status`/progress from the server (the demo's fixed 900 ms timer and the 420 ms remove spinner are fake; remove them, and keep the ≤ 300 ms rule for decorative motion). Re-point colours to our tokens. Add a source header + SOURCES.md row. Fallback: `react-dropzone` (MIT) as in import-wizard |
| Tabs (segment variant, spring indicator) | Must/Try, Low/Normal/High, kind, horizon | beUI https://beui.dev/components/motion/tabs | MIT | indicator spring → `--spring-drop` |
| Bottom Sheet | mobile summary, slot pickers, edits | beUI https://beui.dev/components/motion/bottom-sheet | MIT | or `vaul` (MIT) |
| Multi Select / Combobox | filters, applies-to picker | beUI https://beui.dev/components/motion/multi-select, `/combobox` | MIT | only if shadcn Command feels heavy; one of the two, not both |
| Range Slider | advanced 1–10 weight | beUI https://beui.dev/components/motion/range-slider | MIT | `aria-valuetext="importance 7 of 10"` |
| Adaptive Stepper (numeric) | considered for "N periods" fields | beUI https://beui.dev/components/motion/adaptive-stepper | MIT | **Not adopted as-is**: the liquid separation runs 600 ms with an overshoot curve, above our 300 ms ceiling. Use shadcn Input `type=number` with −/+ buttons, or adopt it only with the `Liquid` effect removed (the value roll is 180 ms and fine) |
| Diff Table | changes vs imported, preset apply preview, run compare | beautifului.dev https://beautifului.dev/#diff-table | MIT (© 2026 Shane Levine, https://beautifului.dev/license; keep the notice) | shared with run-report / import-wizard: one `components/ui/diff-table.tsx` |
| Recommendation Card | AI proposal card actions (Accept / Alternatives) | beautifului.dev #recommendation-card | MIT | our "Edit" replaces "Alternatives" |
| Task Rows | upload stage line, pre-check "Checking…" steps, run phases | beautifului.dev #task-rows | MIT | |
| Filter Table | quick filter chips row | beautifului.dev #filter-table | MIT | |
| Insight Cards | summary mini-stats | beautifului.dev #insight-cards | MIT | |
| Stepper (rail + mobile progress) | step rail / 360 progress | ours: `components/ui/stepper.tsx` from import-wizard §4 (`<ol>`, `aria-current="step"`) | MIT (ours) | shared with import wizard; add a vertical variant + per-step status line |
| Rule card, slot chip, source chip, readiness meter | core | ours (`components/studio/*`) | — | built on the above |
| Tag Input, Status Pill, Hold-to-confirm | — | Kinetics | no licence file | reference only, re-implement |
| Magnetic Dropzone, Grouped Table, Plan Card | — | kobra.systems | free tier personal use only | reference only |
| Spinner-to-check, Skeleton reveal | "Saved ✓", skeletons | transitions.dev free set | custom (commercial OK, keep comment) | re-implemented with motion; no code copied |
| xlsx preview (client) | optional: show the Excel row in the provenance panel when the server sends only coordinates | SheetJS community `xlsx` | Apache-2.0 | prefer the server returning `context_rows` so the client needs no parser |

### Tokens used (from tokens.md) and the few surface tokens added

- Colour:
  - `--fg`, `--fg-muted`, `--surface`, `--surface-2`, `--border`, `--primary`, `--primary-tint`.
  - Status: `feasible` (Ready), `warning` (Needs a look, edited-cell underline), `infeasible` (Blocked, clash outline), `locked` (pin glyph and pinned rows).
  - The AI chip is `--primary` fg on `--primary-tint` with a dashed border while still a proposal. The Must pill is `--fg` bg with `--bg` text (17.9:1). The Try-to pill is outline `--border-strong` with `--fg` text.
- Spacing (4 px base):
  - card padding 12/16 px, gap between rule cards 8 px, rail item height 56 px (label + status line);
  - surface tokens `--studio-rail-w: 216px` (200 at 1280), `--studio-summary-w: 336px` (304 at 1280, 360 at 1920), `--studio-summary-collapsed-w: 48px`, `--rule-card-min-h: 72px` (compact: 44px).
- Radius: rule cards `--radius-md` 8, slot chips `--radius-xs` 4, dropzone `--radius-lg` 12.
- Motion: `--dur-fast` 120 · `--dur-base` 180 · `--dur-slow` 240 · `--dur-max` 300 · `--spring-drop`. No new durations.
- Z: review tray sticky `--z-sticky-bar`, provenance panel `--z-sheet`.

## 10. Accessibility

- **Structure**: `<nav aria-label="Studio steps">` with `<ol>`. The current step has `aria-current="step"`. Each step link's accessible name includes its status ("Rules, 23 must, 14 try to, 2 problems"). The workspace is a `<section aria-labelledby>`. The summary panel is an `<aside aria-label="What will happen">`.
- **Live regions** (polite, throttled to one per 2 s):
  - scope sentence;
  - pre-check result ("Pre-check: 2 problems found");
  - accepted counts ("12 rules added");
  - run status (assertive only for the terminal state).
- **Rule cards**: `<article aria-labelledby="rule-123-sentence">`. Slot chips are `<button>` with names like "Change programme, currently Eczacılık". Must/Try and importance are `role="radiogroup"` with visible labels. Help text is linked via `aria-describedby`. The conflict line is linked to the other card (`aria-describedby` + link).
- **Source chip and confidence**: icon + word, never colour alone. AI proposals announce "suggested by AI, not yet added".
- **Language**: quoted original text gets `lang="tr"` (or `en`) so screen readers pronounce it correctly inside an EN UI. `<html lang>` follows the UI locale.
- **Tables**: `role="grid"` with roving tabindex (requests-inbox §6). The include switch has label "In plan: MAT 112 §1". Edited cells announce "changed from imported value 58". The Revert button is labelled.
- **Dropzone**: a keyboard-operable button (`Enter`/`Space` opens the picker). Drag feedback is also text ("Release to upload"). Per-file status uses `role="status"` and the progress uses `role="progressbar"` (beUI File Upload already does this).
- **Focus management**:
  - after accept/reject → next pending item;
  - after applying a pre-check fix → next issue, or the "Ready" heading;
  - dialogs trap and restore focus;
  - Generate keeps focus on the status card heading.
- **Contrast**: all pairs from tokens.md §2.4. The Must pill is 17.9:1. The dashed AI border is decorative (the AI chip carries the meaning).
- **Motion**: §6. Everything is gated by `useReducedMotion()` plus the global CSS safety net.
- **Touch targets**: ≥ 44 px on coarse pointers. No gesture-only actions.
- **Cognitive load**: one step visible at a time; a plain-language summary always visible; no jargon outside advanced; destructive actions are undoable rather than confirm-heavy (confirm only for reverting all changes, "Generate anyway" when blocked, and making a File-sourced Must a Try-to).

## 11. Open questions

1. **Include/exclude scope**: is "left out" per draft (spec) or should it archive the request term-wide? The spec keeps it per draft, so a Final-week scenario does not damage the Bahar term data.
2. **Edits write-through**: class-list edits write to the request (`PUT /requests/meetings/{id}`) so the inbox, grid and studio agree. Should there instead be scenario-only overrides (A/B scenarios with different enrolments)? The spec says write-through plus a revert-to-imported snapshot. Scenario overrides are backlog.
3. **Exam horizon**: add `horizon=EXAM_PERIOD` to `RunCreate`, or keep `WEEK` + exam week indexes / date range in `horizon_params`? The spec uses the latter until backend decides.
4. **"Room R only for X"**: the solver selectors have no negation. Add a `room_reserved_for` kind (or an `exclude` selector) rather than expanding to N `room_forbid` rules?
5. **Upload without an AI key**: should Excel/CSV preference sheets with known columns (course, room, day) be mapped deterministically (like the import wizard) when no key is set? That adds a column-mapping step to the upload flow.
6. **Built-in rules**: may an ADMIN turn off any of them (e.g. instructor overlap when instructor data is dirty)? The spec shows them read-only.
7. **Preset sharing**: per user or university-wide? The spec says university-wide, with author and date.
8. **Weight mapping**: are Low/Normal/High = 2/5/8 acceptable to the solver's objective scale (`solver/weights.py`)? solver-engineer to confirm.
9. **Pre-check cost**: is `static_check` fast enough to run on every change for 1,300 events (target < 3 s)? If not, run it on step change and on Generate only.
10. **Multi-planner editing**: is the etag "last writer wins with warning" model enough, or is draft locking needed?
