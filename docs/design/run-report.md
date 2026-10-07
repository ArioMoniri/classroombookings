# Run report — design spec

Owner: design-pro · Status: v1 (2026-10-07) · Route: `/runs/{id}` · Tokens: `docs/design/tokens.md` · Backend contract: `docs/ARCHITECTURE.md` ("100/100 or explain", `solver/diagnose.py`, `Constraint` rows with hardness/weight/source).

A run report is the solver's **proof**: either *hard 100/100* and a soft-score breakdown the planner can argue with, or *infeasible* with minimal conflicting sets turned into fixes that are one click away. The page must be readable by a non-technical planner and by the strict reviewer who wants the evidence.

## 1. References (Mobbin) and what we borrow

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| 1 | [Lovable — Speed report](https://mobbin.com/screens/91e4caa2-3908-478a-92e5-50ed9843795d) | **four score tiles in a row (Performance 100 % · Accessibility 96 % …) and an issues list where every row has a "Try to fix" button** — the closest existing pattern to "hard/soft scores + apply fix" | the left-hand chat column |
| 2 | [Replit — Growth / SEO audit](https://mobbin.com/screens/b8fdca6e-b03f-4541-9816-6bebd8e9dee0) | issue groups with a header-level "Fix all with Agent", per-row severity chips (High/Medium/Low) + status (Unresolved), "Healthy" rating chip | |
| 3 | [Base44 — store readiness scan](https://mobbin.com/screens/71d29ab5-bd1b-46a9-a9d7-0932827e94a4) | readiness slider "Not ready → Ready", key issues up top, full report collapsible beneath, "Fix with AI" footer button → our *Sohbette düzelt* | |
| 4 | [Semrush — site audit report with Compare to period](https://mobbin.com/screens/a0e328b3-9f03-40cd-820a-542b78d36e85) | big percentage tiles (Health 80 % / AI health 99 %), "Compare to" date selector → our **scenario comparison** control; AI summary box at the top | print-page chrome |
| 5 | [Profound — page health analysis](https://mobbin.com/screens/f745335b-5517-4cbf-a0e3-f21cb23645a2) | metric tiles with "Good" label + one-line explanation under each number → soft breakdown tiles with a sentence each | |
| 6 | [Google Ads — insights with diagnostics cards](https://mobbin.com/screens/c2424eb7-b6e0-431b-a059-f310246774ea) | horizontally scrollable diagnosis cards with icon, sentence, "View details"; category filter chips (All / Assets / Budget…) | |
| 7 | [Wix — issues counters](https://mobbin.com/screens/e410bcaf-02f3-4c4c-ae00-0e99c82a2d67) | "5 Issues · 1 Recommendation · 13 Completed" counters | |
| 8 | [Vercel — deployment with rollback](https://mobbin.com/screens/d8e63884-5d43-4337-bf31-5667bc4ba5db) | "Instant Rollback" + strike-through of the replaced deployment → our "Önceki çalıştırmaya dön" and diff rows | |
| 9 | [Clockwise — move dialog with Conflicts / Inconveniences](https://mobbin.com/flows/0a0aa36f-0080-4531-8de0-3bac41ea58ec) | hard/soft split with counts in collapsible sections | |
| 10 | [Linear — project progress](https://mobbin.com/screens/43a3307a-6591-4ef2-95d8-197ea0720939) | small property table (Status / Lead / Dates) in a right column → run metadata | |

## 2. Information architecture

```
/runs/41
├── Header: ← Çalıştırmalar · "Run #41 — 2026 Bahar W1–W16" · status chip · [Programa uygula] (primary, only if 100/100) · [Yeniden çalıştır ▾] · [Karşılaştır] · [Dışa aktar ▾] · ⋯
├── Hero row
│   ├── HardScoreBadge   100/100  "Uygulanabilir"  (feasible)   | 97/100 "3 sert kısıt ihlali" (infeasible)
│   ├── SoftScore        87 / 100 with 6-segment breakdown bar
│   ├── Summary tiles: Atanan 880/926 · Oda değişikliği 14 · Kapasite uyumu 91 % · Süre 2 dk 14 sn
│   └── AI summary (2–3 sentences from the chat model, labelled "Özet (Claude)" with a sparkle icon; hidden if AI disabled)
├── Tabs: [Tanılar (3)] [Yumuşak kısıtlar] [Değişiklikler (41)] [Kısıtlar (128)] [Günlük]
│   ├── Tanılar: filter chips (Tümü · Kapasite · Oda tipi · Zaman · Öğretim elemanı · Program) · list of DiagnosisCard
│   ├── Yumuşak kısıtlar: breakdown table (family · weight · violations · score · "Göster" → grid filter)
│   ├── Değişiklikler: diff vs previous run / current timetable (moved / added / removed rows, grouped by faculty)
│   ├── Kısıtlar: the Constraint rows used (source: file / admin / LLM, hardness, weight, text) with toggle hard↔soft and delete → "Yeniden çalıştır" sticky bar appears
│   └── Günlük: solver log (CP-SAT progress, seeds, time limits) in a `<pre>` with copy
├── Right column (≥ 1280): metadata (horizon, seed, time limit, created by, input snapshot id, previous run link) · "Senaryo karşılaştırma" placeholder card
└── Sticky bottom bar (when fixes are staged): "2 düzeltme hazır — [Önizle] [Uygula ve yeniden çöz]"
```

### 2.1 HardScoreBadge
- 112 px ring (SVG, stroke 8 px) with the number inside (36/700) and label under it. Feasible: ring `--feasible-solid`, check icon drawn at the end of the ring animation (ring draw 300 ms `--ease-out`, check 120 ms; reduced motion: static). Infeasible: ring `--infeasible-solid` filled to 97/100, `x-octagon` icon, label "Uygulanabilir değil · 3 ihlal", and the badge is a link to the first diagnosis.
- Also rendered compact (24 px pill `100/100` with icon) in the runs table and the dashboard — same component, `size="sm"`.
- Never shows a soft number inside the hard ring; the two scores are separate objects (hard = proof, soft = preference).

### 2.2 SoftScore breakdown
- Headline `87 / 100` + one horizontal **stacked bar** (dataviz: single axis, thin, 2 px gaps) whose six segments are the constraint families, each sized by *points lost*; legend list beneath (Stripe pattern) with family name · weight · violations · points lost · "Göster". Families (from DATA_ANALYSIS §3): istenen oda/bina · hafta boyunca aynı oda · kapasite uyumu (boş koltuk) · programın günü tek binada · akşam programı B/C blok · kohort bölünmesi.
- Colour: segments use the **categorical palette slots 1–6** in fixed order (identity job), never status colours; the lost-points number is text, so colour is secondary.
- Clicking a family filters the timetable (`/timetable?issues=building_mismatch`) and highlights the affected events with the warning state.

### 2.3 DiagnosisCard (the core object)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ ⛔ Sert · Kapasite                                   Etkilenen: BME 419 │
│ BME 419 (102 öğrenci) Çar P7–P9 için 102+ koltuklu boş oda yok.          │
│ Tek uygun oda A 204 (156) TIP için ayrılmış.                             │
│ Çakışan küme: [BME 419] [A 204 · TIP kilidi] [Çar P7–P9 sabit zaman]     │  ← chips → hover shows the constraint row
│ ─────────────────────────────────────────────────────────────────────── │
│ Seçenekler                                                               │
│  ○ A 204'ü bu slot için serbest bırak           soft −0 · [Düzeltmeyi uygula] │
│  ○ P10–P12'ye taşı (A 204 boş)                  soft −4 · [Düzeltmeyi uygula] │
│  ○ A 101 (58) + A 106 (58) olarak böl           soft −6 · [Düzeltmeyi uygula] │
│  ○ Sohbette başka çözüm iste                                   [Sohbet] │
└─────────────────────────────────────────────────────────────────────────┘
```
- Header: severity badge (`Sert` with `x-octagon` on infeasible tokens; `Yumuşak` with `alert-triangle`), category chip, affected entity chips right-aligned (course code mono, room, slot).
- Body: the diagnoser's human sentence(s) (from `diagnose.py`); the **minimal conflicting set** as chips (each chip = a `Constraint` row; hover/focus shows source + text; click opens the Kısıtlar tab filtered).
- Options: radio list; each shows the predicted soft delta (if the backend provides `estimated_soft_delta`, else "—") and an **Apply fix** button. Apply = *stage* (not solve): the card collapses to a one-line "Hazır: A 204'ü serbest bırak · [Geri al]" and the sticky bottom bar counts staged fixes. Options are mutually exclusive within a card; across cards they accumulate.
- "Fix all with best option" header button (Replit) stages the first option of every hard diagnosis, with a confirm dialog listing them.
- Cards are grouped **Sert (n)** first, then **Yumuşak (n)**; collapsed state remembers per run (`localStorage`).
- Empty (100/100, soft 100): celebratory but quiet — feasible icon, "Tüm kısıtlar sağlandı" and the Değişiklikler tab becomes default.

### 2.4 Apply-fix flow (Preview → Re-solve → New run)
1. Sticky bar **Önizle** opens a Sheet with a **Diff Table** of constraint changes (beautifului *Diff Table* pattern): rows added (release A 204 for W1–16 Çar P7–P9 → new `Constraint` row, source `fix:41:d1`), rows relaxed (hard → soft), rows removed; each with Geri al.
2. **Uygula ve yeniden çöz** → `POST /runs {parent_run_id: 41, constraint_diff: [...]}` → navigates to `/runs/42` in *running* state: hero shows an indeterminate ring, and a live **Task Rows** list (beautifului pattern): "Girdi hazırlanıyor ✓ · CP-SAT çözüyor 00:42 (3 çözüm bulundu) · Tanılar üretiliyor ▢". SSE or 2 s polling. Cancel button → `DELETE /runs/42`.
3. On completion the hero animates to the result; a toast "Run #42 hazır · Sert 100/100 · Soft 85 (−2)" with "Karşılaştır" action (opens scenario comparison with 41 vs 42).
4. Failure (timeout, exception): hero shows `warning` state "Çözücü zaman aşımı (120 s)" with "Süreyi artır ve tekrar dene" and the log tab opens.

### 2.5 Scenario comparison (placeholder for v1, designed now)
Card in the right column: title "Senaryo karşılaştırma", empty state illustration-free: "Bir çalıştırma seçin" + `Select` of runs with the same term. When selected (v1 ships the shell + this minimal table): two-column table Hard / Soft / Atanan / Oda değişikliği / Kapasite uyumu, with a diverging arrow chip per row (▲ better `--feasible-fg`, ▼ worse `--infeasible-fg`, — same `--fg-subtle`; diverging colours only for polarity, as the dataviz rules require). "Tam karşılaştırmayı aç" links to `/runs/compare?a=41&b=42` (v2: side-by-side grids with changed events highlighted).

## 3. Interaction spec

- **States**: `queued` (hero ring grey, "Sırada"), `running` (indeterminate ring + task rows, actions disabled except Cancel), `feasible`, `infeasible`, `failed`, `applied` (chip "Programa uygulandı 12:40" and the primary button becomes "Programı aç"), `superseded` (banner "Bu çalıştırmanın yerine Run #42 uygulandı").
- **Keyboard**: tabs are Radix Tabs (arrow keys); diagnosis cards are `<article>` with heading; options are a radio group (arrows) + "Apply" button; `A` on a focused card stages its selected option; `U` undoes; `⌘Enter` = Uygula ve yeniden çöz when the sticky bar is visible; `E` export; `C` open compare.
- **Touch**: option rows 48 px; the sticky bar sits above the mobile nav; chips are 32 px with 8 px gaps.
- **Reduced motion**: ring draw and check → static final frame; task rows switch icons without the spinner rotation; number tickers → final values; sheet → fade.
- **Undo safety**: staging is client-side until Uygula; a run is never mutated — fixes always create a child run (`parent_run_id`), so "rollback" is just applying the parent again (Vercel Instant Rollback).
- **Export**: PDF (print stylesheet: hero + diagnoses + soft table, no tabs), JSON (raw `SolverResult` + diagnoses), Excel (assignments in the legacy grid layout — backend `exports`).

## 4. Responsive behaviour

| Width | Layout |
|---|---|
| **1920** | Content max 1600 px: hero row 4 tiles + AI summary; tabs area 8 cols, right column 4 cols (metadata + comparison). Diagnosis cards full width of the 8 cols with options in a 2-col grid. |
| **1280** | Right column stays (3 cols); options stack vertically. |
| **768** | Right column moves below the tabs as two stacked cards; hero becomes ring + soft bar on one row, summary tiles 2 × 2; tab labels keep counts; sticky bar full width. |
| **360** | Header actions collapse into ⋯ except the primary; hero: ring centred, soft score below with the bar; AI summary collapsible; tabs horizontally scrollable (Radix Tabs in a `ScrollArea`); diagnosis card: chips wrap, options as a radio list with a single "Düzeltmeyi uygula" button under the list; metadata as a definition list at the end; comparison card shows only the Select + "Aç". |

## 5. Component list

| Need | Component | Source / licence | Install / note |
|---|---|---|---|
| Score ring | in-house `ScoreRing` (SVG circle `stroke-dasharray`, motion `animate` on `pathLength`) — motion reference: Kinetics *Progress Ring* / *Success Check* (**reference only, licence unverified**), transitions.dev *Success check* (custom licence, reference) | — | tokens §6 durations; `role="img" aria-label="Sert kısıt puanı 100 / 100, uygulanabilir"` |
| Soft breakdown bar | in-house `SegmentedBar` (dataviz stacked bar rules) ; alternative evilcharts *Bar* if a per-run trend chart is added | evilcharts — MIT | `npx shadcn@latest add @evilcharts/recharts-bar-chart` for the trend only |
| Diagnosis card | in-house `DiagnosisCard` built from `Card`, `Badge`, `RadioGroup`, `Button`, `HoverCard` (constraint chip preview) | shadcn/ui — MIT | `npx shadcn@latest add card badge radio-group hover-card` |
| Staged-fix approval | pattern from beautifului.dev *Approval Card* (MIT © Shane Levine) for the "Hazır: … [Geri al]" collapsed state and the sticky bar | beautifului.dev — MIT | copy, licence header |
| Constraint diff preview | beautifului.dev *Diff Table* (MIT) | beautifului.dev — MIT | copy into `src/components/ui/diff-table.tsx`; rows: added / relaxed / removed with status tokens |
| Live solve progress | beautifului.dev *Task Rows* (MIT) | beautifului.dev — MIT | same component as dashboard live row |
| Tabs, Sheet, Dialog, Alert, Tooltip, ScrollArea, Table, Select, DropdownMenu | shadcn/ui | MIT | `npx shadcn@latest add …` |
| Number ticker | beUI *Number Animation* (MIT per FAQ; verify LICENSE) or in-house | beui.dev | |
| Toast with action | sonner via shadcn `Toaster` | MIT | |
| Log viewer | `<pre>` in `ScrollArea` + copy button; reference reverseui *Logs Explorer* (no OSS licence — reference only) | — | |
| Comparison table | `Table` + in-house `DeltaChip` | shadcn/ui — MIT | diverging tokens §2.5 |
| Print stylesheet | `@media print` in `globals.css` | — | hide nav/tabs, expand all cards |

## 6. Accessibility

- Page title `h1` "Run #41 — 2026 Bahar", hero scores are `role="group" aria-labelledby`; the ring has a text alternative and the number is real text (not only SVG).
- Severity is icon + word ("Sert"/"Yumuşak") on status tokens; category chips are text.
- Diagnosis options: `RadioGroup` with `aria-describedby` pointing to the soft delta; the Apply button's accessible name includes the option ("A 204'ü serbest bırak düzeltmesini uygula").
- Staging/un-staging announces via `aria-live="polite"`; the sticky bar is `role="region" aria-label="Hazır düzeltmeler"`.
- Running state: task rows in a `aria-live="polite"` region, throttled; the Cancel button keeps focus order first.
- The soft breakdown bar has a `<table>` twin (visually hidden toggle "Tablo olarak göster" is visible for everyone — dataviz table-view rule).
- Colour never alone: ring colour + icon + label; diff rows have +/−/~ glyphs; delta chips have arrows + text.
- Focus management: opening the preview Sheet moves focus to its title; closing returns to the sticky bar button.

## 7. Open questions

1. Does `diagnose.py` return **options with estimated soft deltas**, or only the conflicting set + text? The card degrades to "—" but the UX is far better with the estimate — ask solver-engineer.
2. Should "Programa uygula" be allowed for an infeasible run with the violating sections left **unassigned** (partial publish)? Spec: disabled; the planner must fix or unassign explicitly in the Tanılar tab.
3. Who may toggle a constraint hard↔soft on the Kısıtlar tab — admin only? Spec: admin; faculty planners see read-only.
4. AI summary: generated at run completion (cost per run) or on demand ("Özetle" button)? Spec: on demand, cached.
5. Scenario comparison v2 scope (side-by-side grids) — confirm it goes to `docs/ROADMAP.md`.
6. Export to Excel in the legacy grid layout: is it needed from the report page or only from the timetable? Spec: both menus call the same endpoint.
