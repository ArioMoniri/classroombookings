# Dashboard — design spec

Owner: design-pro · Status: v1 (2026-10-07) · Route: `/` (after login) · Tokens: `docs/design/tokens.md` · Charts follow the `dataviz` skill (form → colour job → validated palette → thin marks → hover layer → table view).

The dashboard answers four questions in under five seconds: **How full are the rooms? What is waiting for me? Did the last solve succeed? What do I do next?** It is not an analytics product; every number links to the surface where the planner acts.

## 1. References (Mobbin) and what we borrow

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| 1 | [Stripe — overview](https://mobbin.com/screens/02176a39-e453-4570-af73-6af00fbe681b), [Stripe — segmented bar + legend lists](https://mobbin.com/screens/54ef3db8-2b9e-4ef3-a91a-cad15de1e1c9) | **stacked status bar with a legend list beneath** (Succeeded/Uncaptured/Refunded/Failed → our Assigned/Unassigned/Locked/Conflict); "compared to previous period" selector; small "Updated 06:23" captions; "View more" links per card | sparkline-per-KPI clutter |
| 2 | [Vercel — project overview](https://mobbin.com/screens/d8e63884-5d43-4337-bf31-5667bc4ba5db), [Vercel — projects list](https://mobbin.com/screens/0f1f0fc1-b24f-4b9b-aff2-1815c823b166) | **status dot + commit-style row** for the runs list (dot · run name · "Ready" · "Apr 22 by Fatih"); yellow "Action required" banner with one CTA; "Production checklist 4/6" → our **setup checklist** for a new term (import rooms ✓, import requests ✓, run ▢, publish ▢) | |
| 3 | [Linear — project overview with progress chart and activity](https://mobbin.com/screens/43a3307a-6591-4ef2-95d8-197ea0720939) | progress summary row (Scope / Started / Completed) → our "Sections: 926 total · 880 assigned · 46 unassigned"; property list on the right | |
| 4 | [Gorgias — busiest times heatmap](https://mobbin.com/screens/67893754-21c2-4d5e-86af-dd8f5e0ce722) | **hour × weekday heatmap with Table/Heatmap toggle, hatched non-business hours, a legend "Least busy → Busiest"** — this is our utilisation heatmap almost verbatim (periods × days, hatch for pre-occupied) | |
| 5 | [Plain — reporting with "new thread volume by time and day" grid](https://mobbin.com/screens/fccb6ef9-8460-412a-a38f-c2dc93a0cbc0) | compact heatmap with Lower→Higher legend inline in the card title | |
| 6 | [Zoho CRM — analytics gallery with KPI tiles + small heatmap](https://mobbin.com/screens/09a4b6d7-d7b4-4e3a-8241-8425869e51a1) | KPI tile with delta (`149 ▲ 12.9 %`, "Last month relative: 132") | pie charts |
| 7 | [ClickUp — dashboard with progress bar and segments](https://mobbin.com/screens/2802e4dc-5a33-4b61-b556-7008bffeeb2f) | single horizontal progress bar with status segments and axis 0–100 | the three pies |
| 8 | [Gorgias — statistics overview](https://mobbin.com/screens/b16206fc-c8f4-49a7-8a17-5181fe95ae48) | KPI tiles 3-up with "0 %" delta chips, section headings "Productivity" | |
| 9 | [Toggl — admin overview with notifications](https://mobbin.com/screens/350128d2-62fa-4a48-8307-47e41fe7fce7) | right column of "Members / Top projects" cards → our "Pending requests" card with a short list and *View all* | donut |
| 10 | [Wix — site overview](https://mobbin.com/screens/e410bcaf-02f3-4c4c-ae00-0e99c82a2d67) | "Issues 5 · Recommendations 1 · Completed 13" circular counters with links; "Fix issues" button | |

## 2. Information architecture

```
/  (Dashboard)
├── Header: "Günaydın, Fatih" · Term select (2026 Bahar ▾) · Week chip (W7) · [Oluştur ▾] (primary: Program oluştur / Excel içe aktar)
├── Banner (conditional): "Son çalıştırma uygun değil (98/100) — Raporu aç" (warning) · "Yeni istekler var (12)" (info) · "Dönem kurulumu 2/4" (checklist)
├── Row 1 — KPI tiles (4)
│   ├── Oda doluluğu (bu hafta)   72 %   ▲ 3 pt vs önceki hafta   → /timetable?zoom=week
│   ├── Bekleyen istekler         12     "3'ü bugün"              → /requests?status=pending
│   ├── Atanmamış şube            46 / 926                        → /requests?status=unassigned
│   └── Son çalıştırma            100/100 · soft 87   "Run #41 · 14 dk önce" → /runs/41
├── Row 2 — Utilisation heatmap (2/3 width) · Pending requests list (1/3)
├── Row 3 — Last runs table (2/3) · Quick actions + Setup checklist (1/3)
└── Footer caption: "Veriler 10:42'de güncellendi · CRBS senkron: 09:00"
```

### 2.1 KPI tile (StatTile)
- 160 px tall, `--radius-xl`, elevation 0. Label (12/500 `--fg-muted`, uppercase, +0.02em) · value (30/700 `--fg`, tabular) · delta chip (icon ▲/▼/— + text, `--feasible-fg` / `--infeasible-fg` / `--fg-subtle`; delta direction semantics: for "Bekleyen" a decrease is good — the component takes `goodDirection: "up" | "down"`) · footnote (12 `--fg-subtle`) · whole tile is a link (focus ring on the tile). No sparkline (Stripe-style sparkline tiles rejected: the numbers are weekly, not continuous).
- Value animates with a number ticker (beUI *Number Animation* or in-house with `motion`'s `animate`), 240 ms, disabled under reduced motion.

### 2.2 Utilisation heatmap (UtilisationHeatmap)
- Form: **matrix of cells = magnitude** → sequential single hue (tokens §2.5), never categorical.
- Axes: rows = **buildings (A, B, C, D)** by default, expandable to rooms (click a building row → its rooms appear beneath, `aria-expanded`); columns = **days** (Pzt…Paz). Toggle `Gün | Periyot`: in *Periyot* mode columns = P1…P18 (18 narrow columns, labels every 3rd period, all in tooltip). Cell value = occupied room-periods / available room-periods for the selected week (or term average with the "Dönem" toggle).
- Cell: 36 × 28 px (day mode), 18 × 28 px (period mode); 2 px surface gap between cells (dataviz spacer rule); rounded 3 px; value text shown only in day mode (`--text-xs`, colour per step rule). Pre-occupied-only cells (prep school blocks) get the hatch overlay and are excluded from the % (legend: "Taralı = önceden dolu").
- Legend: 5 swatches "0 % · 25 · 50 · 75 · 100" + hatch sample, right-aligned in the card header; "Tablo" toggle swaps the heatmap for a plain `<table>` (dataviz table-view requirement) — the table is always in the DOM visually hidden for screen readers (pattern taken from beUI *Liquidity Heatmap*: real `<table>`, each cell a `<button>` with full `aria-label`, roving tabindex, arrows/Home/End move, Esc closes tooltip).
- Tooltip (hover/focus/tap): "A blok · Çarşamba · 81 % (227 / 280 oda-periyot) · 3 çakışma" + link "Programda aç" → `/timetable?day=3&buildings=A&zoom=day`.
- Click cell: navigates to the same link. Keyboard: Enter.
- Loading: skeleton rows; empty: "Bu hafta için atama yok".

### 2.3 Pending requests card
List of up to 6 rows: course code (mono) · programme · requested slot ("Çar 13:30–16:00") · age chip ("2 g") · status badge (icon + text: *Yeni*, *Eksik bilgi*, *Onay bekliyor*). Row click → `/requests/{id}`. Footer: "Tümünü gör (12)". Empty: feasible icon + "Bekleyen istek yok".

### 2.4 Last runs table
Columns: status dot + name (`Run #41 · Bahar W1–W16`), **Hard** (badge: `100/100` feasible or `97/100` infeasible with x-octagon), **Soft** (score 0–100 as number + 4-segment mini bar), duration ("2 dk 14 sn"), started ("14 dk önce · Fatih"), actions (⋯: Raporu aç, Programa uygula, Karşılaştır, Sil). Max 5 rows + "Tüm çalıştırmalar". A running solve shows a live row (beautifului *Task Rows* pattern: spinner → check, step text "CP-SAT: 42 s, 3 çözüm") updated via SSE/polling.
Also a **run history status strip** above the table: one rounded bar per run, coloured feasible/infeasible/warning (beUI *Status Bar*, MIT) — gives the "is it getting better" read at a glance; hover shows the run.

### 2.5 Quick actions + setup checklist
Four 48 px buttons with icons: *Excel içe aktar*, *Program oluştur*, *Programı aç*, *Sohbetle düzenle*. Beneath, "Dönem kurulumu 2/4" checklist (Vercel): Odalar içe aktarıldı ✓ · İstekler içe aktarıldı ✓ · İlk çalıştırma ▢ · Yayınla ▢; completed items strike through; the next item is a link.

## 3. Interaction spec

- **Term select** changes every card (URL `?term=`), with a 180 ms cross-fade of card bodies (opacity only; reduced-motion: none). Week chip opens a popover week picker.
- **Refresh**: data via TanStack Query, `staleTime 60 s`, refetch on window focus; the footer caption shows the fetch time; a manual "Yenile" icon button spins 1 turn (`--dur-max`).
- **Keyboard**: tiles and rows are links/buttons in DOM order; `⌘K` opens global command; `G` then `T` → timetable, `G R` → runs, `G I` → requests (documented in `?`).
- **Touch**: heatmap cell tap shows tooltip; second tap navigates (so the value is readable before leaving). Table rows have a 44 px height on touch.
- **States**: loading skeletons per card (not a full-page spinner); error per card with retry (others stay); empty per card; first-run state (no term) replaces the whole dashboard with the setup checklist and the two import/generate CTAs.
- **Reduced motion**: number tickers show final value; status strip bars do not grow in; cross-fades off.

## 4. Responsive behaviour

| Width | Layout |
|---|---|
| **1920** | Max content 1600 px centred; 12-col grid, 24 px gap. Row 1: 4 tiles (3 cols each). Row 2: heatmap 8 cols / pending 4. Row 3: runs 8 / actions 4. Heatmap in *Periyot* mode fits all 18 columns at 36 px. |
| **1280** | 12-col, 20 px gap; same spans; heatmap period cells 24 px; action buttons 2 × 2. |
| **768** | Tiles 2 × 2; heatmap full width above pending list; *Periyot* mode scrolls horizontally with sticky row labels; runs table hides duration + started (in row tooltip / expand), keeps Hard/Soft; actions 2 × 2 under runs. |
| **360** | Single column, 16 px gutter: banner → tiles as a 2-col compact grid (value 24 px) → quick actions (horizontal scroll row of 4 chips) → heatmap day mode (cells 40 × 32, labels abbreviated "Pt Sa Ça Pe Cu Ct Pz"; period mode replaced by "Tabloyu aç") → pending (3 rows + link) → runs as cards (name, Hard badge, Soft, time) → checklist. |

## 5. Component list

| Need | Component | Source / licence | Install / note |
|---|---|---|---|
| Cards, layout | `Card`, `Separator` | shadcn/ui — MIT | `npx shadcn@latest add card separator` |
| KPI tile | in-house `StatTile` | — | follows dataviz "stat tile" (headline number, label, delta with icon, no decorative sparkline) |
| Number ticker | beUI *Number Animation* (`@beui/number-animation`) — MIT per site FAQ (verify LICENSE on import) ; alternative in-house `useAnimatedNumber` with `motion` `animate()` | beui.dev — MIT | `npx shadcn@latest add @beui/number-animation`; strip glass tokens |
| Utilisation heatmap | in-house `UtilisationHeatmap` (table of buttons, roving tabindex); a11y/interaction pattern copied from beUI *Liquidity Heatmap* docs (not its finance-specific code) | beui.dev — MIT (pattern) | sequential palette tokens §2.5; `Tabs` for Gün/Periyot; legend in-house |
| Run history strip | beUI *Status Bar* (`@beui/status-bar`) | beui.dev — MIT | `npx shadcn@latest add @beui/status-bar`; map statuses: `feasible`, `infeasible`, `warning`, `running`, `no data`; hidden table included by the component |
| Live run row | pattern from beautifului.dev *Task Rows* (MIT, copy-paste) | beautifului.dev — MIT © Shane Levine | copy into `src/components/ui/task-rows.tsx` with licence header; style with tokens |
| Soft-score mini bar | `Progress` (4 segments) | shadcn/ui — MIT | |
| Trend chart (optional, runs page not dashboard) | evilcharts *Bar* / *Area* (Recharts) | evilcharts — MIT (LICENSE in repo) | `npx shadcn@latest add @evilcharts/recharts-area-chart`; categorical colours only from tokens §2.3 |
| Runs table | `Table`, `DropdownMenu`, `Badge` | shadcn/ui — MIT | |
| Pending list | `Table` (borderless) + `Badge` | shadcn/ui — MIT | |
| Banner | `Alert` with variant map to status tokens | shadcn/ui — MIT | |
| Checklist | in-house `SetupChecklist` (Vercel pattern) | — | |
| Quick actions | `Button` `size="lg"` with lucide icons | shadcn/ui — MIT | |
| Skeleton | `Skeleton` | shadcn/ui — MIT | |
| Reference-only (not copied) | kobra *CRM Table* / *Grouped Table* layout (Pro licence); reverseui *Timeline Progress* (no OSS licence); Kinetics *Odometer Count-up*, *Progress Ring* (licence unverified) | | |

## 6. Accessibility

- Heading order: `h1` greeting, `h2` per card; cards are `<section aria-labelledby>`.
- Every KPI tile: `<a>` with `aria-label="Oda doluluğu yüzde 72, önceki haftaya göre 3 puan artış, programı aç"`; the delta icon has `aria-hidden` and the text carries direction.
- Heatmap: real `<table>` with `<caption>` "A–D blok doluluğu, 7. hafta"; cell buttons announce building, day/period, percentage, conflicts; colour steps are also encoded as text in day mode and in the table view; hatch + legend text for pre-occupied.
- Status badges: icon + text, never dot-only (the Vercel-style dot in the runs table is accompanied by the Hard badge text).
- Live run row updates in an `aria-live="polite"` region, throttled to one announcement per 10 s.
- Contrast: all text on tiles uses `--fg`/`--fg-muted`; heatmap text colour switches at step 4 (tokens §2.5, verified ≥ 5.2:1).
- Reduced motion handled per §3; nothing auto-refreshes visually in a way that moves content (new runs append below, no reorder animation).

## 7. Open questions

1. Is "utilisation" measured over **available** room-periods (excluding pre-occupied blocks) or over all 18 × 7? Spec: excluding pre-occupied, with the hatch legend — confirm with the planner.
2. Should the heatmap default to the **current week** or the **term average**? Spec: current week with a "Dönem" toggle.
3. Does the dashboard need faculty-level breakdown (e.g. Tıp vs Mühendislik occupancy)? Not in v1; would reuse the categorical palette.
4. Who sees the dashboard — admin only, or also faculty planners with a filtered view (only their rooms)? Affects the term/faculty selectors.
5. "Compared to previous week" deltas need last week's snapshot; if the backend does not store history yet, the delta chip is hidden rather than shown as 0.
