# Charts & telemetry views (v3, owner request 2026-10-17)

Lane: designer (charts-des-2026-10-17). Phase 1 is this spec plus the wireframes. Phase 2 (install EvilCharts ECharts and
build the shared shell) starts only when the orchestrator says "phase 2 go". Tickets: `docs/ROADMAP.md` §"Charts &
telemetry views (owner request 2026-10-17)" CH-01…CH-12.

Wireframes are generated: `python3 -I ch.py ..` from inside `wireframes/src` (`wf.py` is the shared kit).

| File | Shows |
|---|---|
| `wireframes/charts-shell-1440.svg` | ChartCard anatomy (title, summary sentence, period, ⋯ menu, legend, partial-day hatch, tooltip, footer) and its table twin |
| `wireframes/charts-states.svg` | loading, empty, error, partial period, stale data, too few points (shown as a number) |
| `wireframes/charts-surfaces-1440.svg` | which form each surface gets: three ECharts forms, plus the three non-chart components that stay |
| `wireframes/charts-390.svg` | ChartCard on a phone (44 px period control, 7 columns, tap-to-scrub, table button) |
| `wireframes/charts-user-390.svg` | user and academician stats on a phone (totals, weekly load, AI quota): no chart library |

## 0. BLUF

1. **Most of SmartSched's statistics are not charts, and should not become charts.** Rankings use `BarList`, single values
   and quotas use `StatTile` / `Meter` / `KpiNumber`, and day × period grids use `HeatGrid`. These are light, tested,
   accessible and phone-ready, so they stay as they are.
2. **Real time series use one engine: EvilCharts ECharts** (`echarts-bar-chart`, `echarts-line-chart`,
   `echarts-area-chart`), wrapped in one shared `ChartCard` shell under `components/charts/**`. Today three time series
   use three techniques: Recharts EvilCharts on the dashboard and AI usage, and a hand-drawn SVG on ops. They converge
   on one. Recharts is removed when the last migration lands (CH-09).
3. **Why ECharts over the Recharts variant we already vendor:**
   - an SVG *or* canvas renderer per chart: SVG for print/PDF and small phone charts, canvas for the 1,440-point ops series;
   - the decal patterns (`aria.decal`) for colour-blind users and grayscale print;
   - `registerLocale("TR")` for the built-in strings;
   - large-data modes (`sampling: "lttb"`, `large`) for ops telemetry.

   Recharts offers none of these without custom work.
4. **The price is bundle weight.** Measured with esbuild (minified, gzip -9, React external):
   - ECharts tree-shaken for bar + line(area) + both renderers + aria + TR: **217 kB gz**;
   - one bar chart on canvas: 186 kB gz;
   - the Recharts set we ship today: 123 kB gz.

   Mitigation: the engine loads lazily (`next/dynamic`, `ssr: false`) only inside `ChartCard`, so routes without a chart
   pay 0 kB. When Recharts is removed, chart routes pay about +95 kB gz net.
5. **EvilCharts ECharts gaps that the shell must close** (verified in the registry source on 2026-10-17):
   - no ARIA at all: zero `aria-*`/`role` attributes and `AriaComponent` is not registered;
   - tooltip values use `toLocaleString()` with no locale, so the browser decides;
   - a 500 ms bar grow-in and a 2 s loading shimmer, both over our 300 ms ceiling and on the anti-AI list.

   All three are fixed by the shell (§5) or by a small, documented patch (CH-01).
6. **Licences: all fine to import.** EvilCharts is MIT © 2026 Gurbinder, ECharts is Apache-2.0 (keep the NOTICE), and
   zrender is BSD-3-Clause.

## 1. Inventory: every telemetry and statistics surface today (grep 2026-10-17)

Grep: `recharts|echarts|chart|sparkline|heatmap` over `smartsched/frontend/src` (tests excluded), plus the stats
endpoints in `backend/app/api/v1`. Owners come from WAVE3 lanes and the ROADMAP (W3-AI, W3-OPS, W3-SLOT). "Frontend
(dashboard)" means the design-system/dashboard frontend owner; the orchestrator assigns it if no lane holds it.

| Role | Surface | Route | File(s) | Technique today | Data / endpoint | Current owner |
|---|---|---|---|---|---|---|
| admin | Ops status cards | `/admin/ops` | `components/admin/ops/ops-panel.tsx` (cards), `ops-model.ts` | status dot + word cards, Disk meter | `GET /ops/status` | W3-OPS |
| admin | Ops "İstekler" mini chart | `/admin/ops` | `ops-panel.tsx` §mini chart (L165–205), `ops-model.ts chartGeometry/totals` | **hand-drawn `<svg>`** polyline, `role="img"` + aria-label | `GET /ops/requests?minutes=` | W3-OPS |
| admin | Grafana links / panels | `/admin/ops` › Panolar | `ops-panel.tsx GrafanaSection` | links + same-origin iframes | Grafana | W3-OPS. **Stays Grafana**: SmartSched does not rebuild Grafana |
| admin | AI usage: daily tokens by feature | `/admin/ai` › Kullanım | `components/admin/ai/usage-tab.tsx`, `ai-model.ts` (`dayChartData`, `SERIES_COLOR`) | **Recharts EvilCharts `EvilBarChart`** stacked | `GET /ai/admin/usage/summary` | W3-AI |
| admin | AI overview KPIs, budget, top users | `/admin/ai` › Genel bakış | `overview-tab.tsx`, `ai-kit.tsx` | `StatTile`, `Meter`, `BarList` | `GET /ai/admin/usage` | W3-AI |
| admin/planner | Utilisation heat maps (rooms, instructors) | `/analytics/heatmap` | `components/analytics/{heatmap-view,rooms-heat,instructors-heat,heat-grid,heat-legend,heat-model}.tsx` | custom CSS grid (`HeatGrid`) + table toggle + CSV button | `GET /analytics/heatmap/{rooms,instructors}` | frontend (analytics); AS-16 will add tabs |
| planner | Dashboard KPIs | `/dashboard` | `components/dashboard/{dashboard-view,kpi-number}.tsx` | `KpiNumber` (ticker on change) | `GET /dashboard` | frontend (dashboard) |
| planner | Occupancy by period | `/dashboard` | `components/dashboard/dashboard-charts.tsx PeriodArea` | **Recharts EvilCharts `EvilAreaChart`** + sr-only table | `GET /dashboard` | frontend (dashboard) |
| planner | Building utilisation | `/dashboard` | `dashboard-charts.tsx BuildingBars` | `BarList` | `GET /dashboard` | frontend (dashboard) |
| planner | Building × day/period heatmap | `/dashboard` | `components/dashboard/utilisation-heatmap.tsx` | custom grid, phone → ranked `BarList` | `GET /dashboard` | frontend (dashboard) |
| planner | Calendar heat tint | `/timetable` | `components/timetable/model/heat.ts` | cell tint (sequential steps) | `GET /runs/{id}/heat` | timetable lane |
| planner | Run score + soft breakdown | `/runs/[id]` | `components/runs/{run-view,soft-breakdown}.tsx` | numerals + `BarList` | `GET /runs/{id}/summary` | runs lane |
| planner | Runs list / compare scores | `/runs`, `/runs/compare` | `runs-list.tsx`, `compare/compare-view.tsx` | plain numerals ("517 / 530") | `GET /runs` | runs lane |
| planner | Studio summary readiness | `/generate` | `components/studio/summary-panel.tsx` → `ReadinessMeter` | meter | `GET /terms/{id}/studio/summary` | studio lane |
| exams admin | Invigilation load per person | `/exams` › Gözetmenler | `components/invigilation/people-view.tsx` | `BarList` + sortable table | `GET /invigilation/plans/{id}/load` | invigilation lane |
| admin | Audit | `/admin/audit` | `components/audit/audit-view.tsx` | table only, no stats | `GET /audit` | admin lane |
| admin | Integrations hub status | `/admin/integrations` | `components/admin/integrations/connector-card.tsx` | status dot (shape) + word + last check | integrations API (`lib/api`) | integrations lane |
| user | My bookings totals | `/my-bookings` | `components/bookings/my-bookings-view.tsx` (`mine-totals`) | one sentence ("3 aktif · 11 bu dönem …") | `GET /bookings/dashboard` | W3-SLOT |
| user | Profile AI usage | `/profile` | `components/admin/ai/my-ai-usage.tsx` in `components/admin/profile-view.tsx` | two `Meter`s | `GET /ai/me/usage` | W3-AI |
| academician | Own load and timetable stats | `/moderation/me`, `/timetable` | none (wishes only); `GET /terms/{id}/instructors/load` exists for the program wizard | **missing** | `GET …/instructors/load` (planner scope) | — (new, CH-11) |
| public | Kiosk / room display | `/public/rooms/[code]` | `components/public-schedule/kiosk.tsx` | no charts; motion none ("a kiosk must not twitch") | public schedule | public-schedule lane. **Stays chart-free** |
| — | Vendored, unused | — | `components/ui/evilcharts/charts/recharts-radial-chart.tsx`, `ui/recharts-{brush,background,dot}.tsx` | Recharts | — | design-system. Deleted in CH-09 |

Endpoints with no UI yet that a chart could use: `GET /requests/stats`, `GET /booking-conflicts/summary` (banner only),
`GET /terms/{id}/usage`, and `GET /health/metrics` (Prometheus text, which is not for the UI).

## 2. EvilCharts ECharts study (evilcharts.com, registry `https://evilcharts.com/r/{name}.json`, 2026-10-17)

**What exists.** The registry has 8 ECharts charts plus 5 shared `ui` modules:

- charts: `echarts-area-chart`, `echarts-bar-chart`, `echarts-line-chart`, `echarts-composed-chart`,
  `echarts-pie-chart`, `echarts-radial-chart`, `echarts-radar-chart`, `echarts-sankey-chart`;
- shared `ui` modules: `echarts-chart`, `echarts-tooltip`, `echarts-legend`, `echarts-dot`, `echarts-brush`.

There is **no heatmap and no gauge**. Each chart lists npm deps `echarts` + `motion` (motion v14 is already ours) and
pulls only `@evilcharts/echarts-*` ui modules, nothing from Recharts. The registry's `target` is
`components/evilcharts/{charts,ui}/…`, and the source imports `@/registry/ui/echarts-*`. Both get re-pointed in CH-01
(as the Recharts variant was: "import paths re-pointed").

| Question | Finding | Consequence for us |
|---|---|---|
| Licence | MIT, © 2026 Gurbinder (github.com/legions-developer/evilcharts LICENSE, same text as our `src/components/ui/LICENSES/evilcharts-MIT.txt`). ECharts 6.1.0 Apache-2.0, zrender 6.1.0 BSD-3-Clause | Import allowed. Licence header per file, a SOURCES.md row, and the Apache NOTICE kept via npm |
| Tree-shaking | `echarts-chart` imports `echarts/core` + `echarts/renderers` and registers **both** Canvas and SVG. Each chart registers only its series + components (bar: `BarChart, Grid, Tooltip, DataZoom`) | Good. The full `import "echarts"` would be 383 kB gz, and the modular import avoids it |
| Bundle (measured) | bar + canvas 186 kB gz · bar + both renderers 194 · bar + SVG, no dataZoom 178 · bar + line + both + aria + TR 217 · Recharts set today 123 (all gzip -9, esbuild, React external) | Lazy chunk only (§10). Never in the first-load JS of the shell |
| Renderer | `renderer?: "canvas" \| "svg"`, default canvas; changing it re-inits the instance | Shell rule (§5.6): SVG for ≤ 300 points and print, canvas above that |
| Dark mode | A `MutationObserver` on the root class re-resolves the `--color-{key}-{n}` CSS vars and `muted-foreground/border/foreground/background` tokens. Light = root, dark = `.dark`. Our `next-themes` uses `attribute="class"` → `.dark`, so it is compatible | Works as is. Our config passes `var(--cat-n)` / `var(--seq-n)` per theme |
| Accessibility | **None.** No `aria-*`, no `role`, `AriaComponent` not registered, no keyboard path. The single decal hit is the hatched-variant texture | The shell owns a11y (§9): `aria-hidden` canvas, a `<figure>` + summary sentence + table twin, and a keyboard scrub layer. Register `AriaComponent` only for `aria.decal` |
| Locale | Tooltip values use `value.toLocaleString()` (browser locale). Axis `tickFormatter` props exist. No `registerLocale` | The shell passes `tickFormatter` / `valueFormatter` from `useI18n().n` (tr-TR). CH-01 patches the tooltip default to the injected formatter |
| Motion | `BAR_GROW_DURATION = 500` ms, a `LOADING_ANIMATION_DURATION = 2000` ms shimmer, an `animationType` prop, and `useReducedMotion()` for its motion/react bits | Always `animationType="none"` (no grow-in, A9). Loading uses our skeleton (§8), never `isLoading` |
| Touch | Tooltip trigger `axis` works on tap. `dataZoom` / brush exist | Phones: no dataZoom/brush (§7) |

**Recharts EvilCharts vs ECharts EvilCharts, same author and same API shape** (`<EvilBarChart config data>` with
compound children vs an option-driven React wrapper). Migrations are mostly prop renames, plus moving the table twin into
the shell.

## 3. References (Mobbin, 2025–2026)

| App | Screen / flow | Pattern taken |
|---|---|---|
| Mintlify | [Analytics](https://mobbin.com/screens/205aefea-2dfc-4668-9af7-bc4921da1762), flows [Filtering analytics](https://mobbin.com/flows/cebcabde-65c5-4931-9d30-dd99d5603f1c), [Exporting to CSV](https://mobbin.com/flows/5aed0ec4-91c9-4db0-a3d3-e6748423ec6b) | **The current, unfinished day is hatched**, not solid. Preset period list. "Export to CSV" as a plain secondary button. The empty period shows one sentence instead of empty axes |
| Exa | [Usage over time](https://mobbin.com/screens/cfec730d-d7a7-4a8c-8fd1-d742bf18dd9f) | KPI trio above the chart (total · daily average · peak day). Dashed reference line at the peak |
| Obvious | [Usage Analytics](https://mobbin.com/screens/f8d79792-2e5d-4eac-aa5d-6050dce3aebb) | The period picker sits top right with the timezone named under the title. Empty sections keep their height and print "No … for this period" |
| Seline | [Dashboard](https://mobbin.com/screens/4e47be94-6871-46ed-b703-eeae23153be4) | Ranked lists use in-row bars with the value at the end (our `BarList`) |
| Juicebox | [Downloading a chart](https://mobbin.com/flows/c930074c-a776-4b53-a4fa-435d80897c26) | The ⋯ per card → Download (CSV / image) → "Download complete ✓" inline confirmation |
| Hotjar | [Dashboard](https://mobbin.com/screens/22203b5a-8ffd-4448-b414-e07ed0f02cd7) | KPI tile + sparkline: a sparkline only where the trend is the point |
| Sentry, OpenAI Platform, Better Stack, AWS | [Sentry](https://mobbin.com/screens/7f86dfa1-1374-48a4-82cc-80a41f400fe6), [OpenAI service health](https://mobbin.com/screens/d605f83d-3869-4ecc-8874-b913e09e2930), [Better Stack](https://mobbin.com/screens/dc1236fd-3d9b-4152-a435-f54a50642974), [AWS metrics](https://mobbin.com/screens/ec56aa54-4f6d-4c35-9d22-5b9eb179db05) | Telemetry as **small multiples** (requests, 4xx, 5xx, latency each on its own axis), never dual axes. Status line first ("All systems operational") |
| Sprig, Base44, Gemini, StackAI, QuickBooks | [Sprig](https://mobbin.com/screens/83f67504-08a2-499e-823d-03a52c3f28a3), [Base44](https://mobbin.com/screens/0510ed55-42cd-4477-8c24-d1251c4b70c7), [Gemini](https://mobbin.com/screens/1cb3c785-d4df-4a3a-992d-e887d1129667) | User-level usage = a **meter with "used / limit" and a reset date**, not a chart. A chart appears only under it (Base44 daily usage) |
| Garmin Connect, Nike Run Club, timespent, Oura (iOS) | [Garmin](https://mobbin.com/screens/ea11133b-fd2c-4d39-a12b-a2d4723c68b3), [timespent](https://mobbin.com/screens/a6da6213-c211-4798-9f31-994f176a9573), [Nike](https://mobbin.com/screens/58c10cac-14ca-40ab-8ead-372aef4d5ed2) | Phone: a full-width segmented Week/Month/Year control, the headline number first, ≤ 7 columns, and the list of the same data directly below (the table twin, visible) |

## 4. Which chart for which metric and role (decision table)

Form heuristic (dataviz skill, "choosing a form"):

| Data | Form | Component |
|---|---|---|
| change over time, ≥ 3 points | column chart | ECharts bar |
| change over time, many points or continuous | line | ECharts line |
| change over time, one series where the volume is the message | area | ECharts area |
| ranking / part-of-whole ≤ 8 items | in-row bars | `BarList` |
| one number / quota | tile or meter | `StatTile` / `Meter` / `KpiNumber` |
| two categorical axes × magnitude | grid | `HeatGrid` |
| fewer than 3 points | — | the number (`StatTile`), never a chart |

No pie, donut, radial, radar or sankey: every part-of-whole question here has ≤ 8 parts and reads better as a `BarList`.

| # | Role | Metric | Surface | Form | Component | Period / grain | Renderer |
|---|---|---|---|---|---|---|---|
| 1 | admin | AI tokens per day by feature (≤ 5 + "Diğer") | `/admin/ai` › Kullanım | stacked columns, today hatched | `echarts-bar-chart` (`stackType="stacked"`) | 7 g / 30 g / Dönem; day | SVG (≤ 31 × 6 marks) |
| 2 | admin | Requests/min, 5xx/min, p95 ms | `/admin/ops` › Durum | **3 small multiples**, shared x, one axis each | `echarts-line-chart` ×3 | 1 sa / 24 sa / 7 g; minute → `sampling: "lttb"` | canvas (1,440 points) |
| 3 | admin | Ops service health | `/admin/ops` | status cards | existing cards | — | — |
| 4 | admin | AI budget used, users vs limit | `/admin/ai` | meter, ranked list | `Meter`, `BarList` (unchanged) | month | — |
| 5 | admin | Bookings per week (term), exam weeks labelled | `/admin` overview or `/bookings` admin | columns, current week hatched, direct label "Sınav haftası" | `echarts-bar-chart` | term; ISO week | SVG |
| 6 | admin | Booking requests: approved / rejected / pending per week | `/approvals` header | stacked columns (status colours **not** used: cat-1..3 + a legend) | `echarts-bar-chart` | term; week | SVG |
| 7 | admin/planner | Room & instructor utilisation day × period | `/analytics/heatmap`, dashboard | heat grid | `HeatGrid` (unchanged; no ECharts heatmap) | week | DOM |
| 8 | planner | Occupancy by period (weighted) | `/dashboard` | area, single series, peak label | `echarts-area-chart` | week; period | SVG |
| 9 | planner | Building utilisation | `/dashboard` | ranked bars | `BarList` (unchanged) | week | — |
| 10 | planner | Placed / conflicts / soft score KPIs | `/dashboard`, `/runs/[id]` | numbers (ticker on live change) | `KpiNumber` (unchanged) | run | — |
| 11 | planner | Soft points lost per rule family | `/runs/[id]` | ranked bars | `BarList` (unchanged) | run | — |
| 12 | planner | Soft score across this term's runs (≥ 3 runs) | `/runs` list header | line + dots, active run labelled | `echarts-line-chart` | term; run | SVG |
| 13 | planner | Studio readiness | `/generate` | meter | `ReadinessMeter` (unchanged) | — | — |
| 14 | exams admin | Invigilation load per person | `/exams` | ranked bars + table | `BarList` (unchanged) | plan | — |
| 15 | admin | Audit events per day (optional, later) | `/admin/audit` | columns | `echarts-bar-chart` | 30 g | SVG |
| 16 | admin | Integrations delivery success | `/admin/integrations` | status word + "son 24 sa: 0 başarısız" text | existing card (no chart) | — | — |
| 17 | user | My bookings: active / this term / open requests, quota | `/my-bookings`, `/profile` | 3 tiles + "3 / 5 hakkı kullanıldı" sentence | `StatTile` ×3 (new layout, no chart) | term | — |
| 18 | user | My AI usage this month | `/profile` | meter + reset date | `Meter` (unchanged) | month | — |
| 19 | academician | My weekly teaching hours by day | `/profile` (and `/timetable` header) | ranked-by-day bars, "ders yok" text for 0 | `BarList`, each row a 44 px link to that day | week | — |
| 20 | public | Kiosk | `/public/rooms/[code]` | **no charts** | — | — | — |

Role scoping: every chart reads an endpoint already scoped by permission (admin `ai.admin`, `ops.view`; planner
`dashboard`; user `me`). The shell never fetches; the caller passes data. No chart shows another person's name on a
user or academician surface.

## 5. Shared chart shell (`components/charts/**`, CH-02)

### 5.1 Files

| File | Role |
|---|---|
| `components/charts/chart-card.tsx` | `<ChartCard>`: the frame, header, states, footer, table toggle, menu |
| `components/charts/chart-lazy.tsx` | `next/dynamic(() => import("./evil/…"), { ssr: false, loading: ChartSkeleton })` for each form |
| `components/charts/chart-summary.ts` | pure builders for the Turkish/English summary sentence (`peak`, `total`, `trend`, `partial`) |
| `components/charts/chart-table.tsx` | `<ChartTable>`: `<table>` with `<caption>`, `<th scope>`, the same rows the CSV writes |
| `components/charts/chart-csv.ts` | `toCsv(rows, columns, locale)` → UTF-8 BOM, `;` separator for tr (Excel tr-TR), `,` for en; filename `smartsched-<slug>-<from>_<to>.csv` |
| `components/charts/chart-format.ts` | `useChartFormat()` → `num`, `pct`, `compact`, `day`, `weekday`, `time` from `useI18n()` (`Intl` tr-TR, Europe/Istanbul) |
| `components/charts/chart-tokens.ts` | the series colour config (`cat`, `seq`, `neutral`) for EvilCharts `ChartConfig` |
| `components/charts/period-picker.tsx` | wraps the existing `SegmentedControl`; value in the URL (`?period=30d`) |
| `components/charts/evil/{charts,ui}/echarts-*.tsx` | the vendored EvilCharts files (CH-01) |
| `components/charts/*.test.ts(x)` | vitest |

### 5.2 API (sketch)

```tsx
<ChartCard
  id="ai-daily-tokens"                 // slug for CSV and test ids
  title={t("charts.ai.daily.title")}   // "Günlük token kullanımı"
  summary={summary}                    // string from chart-summary.ts; becomes aria-describedby
  period={{ value, options: ["7d", "30d", "term"], onChange }}   // optional
  state={q.isPending ? "loading" : q.isError ? "error" : rows.length === 0 ? "empty" : "ready"}
  stale={staleSince}                   // Date | undefined → warning strip
  partialFrom={todayKey}               // the last bucket is unfinished → hatched + said in the summary
  columns={[{ key: "day", label: t("charts.col.day"), format: day }, …]}   // drives the table and CSV
  rows={rows}
  onRetry={q.refetch}
  emptyAction={{ label: t("charts.empty.changePeriod"), onClick }}
>
  {(size) => <LazyBar data={rows} config={cfg} stackType="stacked" renderer={size.renderer} … />}
</ChartCard>
```

### 5.3 Anatomy (wireframe `charts-shell-1440.svg`)

1. **Title.** `type-headline`, names the measure only ("Günlük token kullanımı"), and is the `<figure>`'s accessible
   name.
2. **Summary sentence.** One plain Turkish sentence that answers the chart's question with the numbers, e.g.:
   - "Son 30 günde 1,2 milyon token; en yoğun gün 14 Ekim (82 bin). Bugün henüz bitmedi."
   - "En yoğun saat 10:30 (%86)."

   It is `aria-describedby` of the figure, and it updates when the period changes. Builders live in `chart-summary.ts`
   with tr/en message keys (`charts.summary.peakDay`, …). No invented adjectives ("harika", "dramatik").
3. **Period picker.** `SegmentedControl` (pattern 2), 7 gün / 30 gün / Dönem (or 1 sa / 24 sa / 7 g for ops). The URL
   holds it, so a link reproduces the view.
4. **⋯ menu** (44 × 44 on touch). Items:
   - **Veriyi indir (CSV)**;
   - **Görseli indir** (SVG via `getDataURL({type:"svg"})` when the SVG renderer is used, otherwise PNG at 2×);
   - **Tabloyu göster/Grafiği göster**;
   - **Yazdır**.

   On phones the menu opens as a sheet.
5. **Legend** for ≥ 2 series, in fixed order, square swatches with text in ink colour. Series with ≤ 4 items also get
   direct labels where there is room. No legend for one series (the title names it).
6. **Plot.**
   - Gridlines are recessive and the y axis has 3–4 ticks.
   - Values use `compact` (82 B, 1,2 Mn) on axes and full precision (82.300) in the tooltip and table.
   - A **partial** last bucket is hatched (decal) and named in the summary.
   - The **reference** line is dashed, labelled in text, and used only where a limit exists (a budget, capacity).
7. **Tooltip.** A frosted card listing every series in legend order with right-aligned values, and the bucket's full
   date ("14 Ekim Çarşamba").
8. **Footer.** The "Tabloyu göster" link button, plus "Güncellendi 19:42 · Europe/Istanbul" (relative in the title
   attribute).

### 5.4 States (wireframe `charts-states.svg`). The card keeps its height in every state, so nothing shifts.

| State | Shows | a11y |
|---|---|---|
| loading | title + skeleton bars (no axes), summary skeleton line | `aria-busy="true"` on the figure; nothing is announced |
| empty | sentence "Henüz gösterilecek veri yok" + reason + **one** action (change period / create the first booking). No axes, no frame | plain text |
| error | inline error panel (`message_tr` from the API), "Yeniden dene" button, and no stale chart behind it | `role="status"` on the panel; focus moves to "Yeniden dene" only if the user triggered the fetch |
| partial | the chart, last bucket hatched + "henüz bitmedi" in the summary | in the table the row says "(bugün, eksik)" |
| stale | the chart stays, with a warning strip "Son güncelleme 2 saat önce · Prometheus yanıt vermiyor" | strip text; colour never alone |
| too few points (< 3) | the number (`StatTile`) instead of a chart | — |

### 5.5 Data-table fallback and CSV

- The table twin is always in the DOM. It is `sr-only` while the chart is shown and visible after "Tabloyu göster".
  It has the same rows and columns as the CSV, a `<caption>` = title + period, and numbers formatted in tr-TR.
- The chart canvas/SVG is `aria-hidden="true"`. Screen readers get title, summary and table, in that order.
- CSV export:
  - client-side from the same `rows`, with no extra request;
  - UTF-8 BOM so Excel tr-TR opens "ç ğ ı ö ş ü" correctly, and `;` as the separator in tr (`,` in en);
  - decimal comma in tr, ISO dates (`2026-10-14`) in a second column for machines.
- The button label swaps "Veriyi indir → İndirildi ✓" for 2 s (text-states-swap, §8), and a polite live region
  says "CSV indirildi".

### 5.6 Renderer rule

- **SVG** when the series × buckets ≤ 300 marks (all of rows 1, 5, 6, 8, 12, 15): crisp on phones, lower memory, and
  the image download is a real vector.
- **Canvas** above that (ops minute series, row 2), with `sampling: "lttb"` and `large: true`.
- **Print:** the shell listens to `matchMedia("print")` / `beforeprint` and switches to SVG. The print CSS hides the
  menu and the period control and prints the table twin under the chart. PDF export (if added later) uses the same
  print path.

## 6. Colour tokens (from `src/app/globals.css`, docs/design/tokens.md §2.5)

| Job | Tokens | Rule |
|---|---|---|
| Categorical (identity) | `--cat-1` #2a78d6 · `--cat-2` #eb6834 · `--cat-3` #1baf7a · `--cat-4` #eda100 · `--cat-5` #e87ba4 (dark: #3987e5 · #d95926 · #199e70 · #c98500 · #d55181) | fixed order, never cycled. A 6th+ series folds into **"Diğer"** = `--label-3`. Colour follows the entity: AI `SERIES_COLOR` stays chat = cat-1, rules = cat-2 … |
| Sequential (magnitude, single series) | `--seq-1…5` (light #EFF6FF → #1E3A8A; dark reversed) | single-series bars/areas use `--seq-4` (light #2563EB / dark #60A5FA). An emphasised bar (exam week) uses `--seq-5`. Never the accent (G3: the accent is for actions only) |
| Neutral | `--label-3` ("Diğer"), `--separator` (grid), `--label-2` (axis text) | axis text never uses series colours |
| Status (state, reserved) | `--status-feasible/-warning/-infeasible-*` | only in strips/badges with an icon + word, never as "series 3" |
| Texture | ECharts `aria.decal` (45° hatch) for partial buckets; `decal: "auto"` per series when the user turns on Ayarlar › Erişilebilirlik › "Grafiklerde desen" or forced-colors is active | colour is never the only channel |

Validator (dataviz `validate_palette.js`, run 2026-10-17):

- **light** cat-1…5 on `#ffffff`: lightness, chroma, CVD (worst adjacent protan ΔE 9.1, tritan 5.8) and normal-vision
  floor (19.6) all **PASS**. Contrast vs surface **WARN** for cat-3 2.82, cat-4 2.17 and cat-5 2.69 (< 3:1), so the
  legend and table twin are **obligatory**, which the shell guarantees;
- **dark** cat-1…5 on `#222328`: all **PASS** (CVD 8.4, contrast ≥ 3:1).

Stacked segments keep a 2 px surface gap. Tritan 5.8 between cat-4 and cat-3 is in the 6-and-below band, so the
legend, gaps and decal must stay on for stacks.

EvilCharts wiring: `ChartConfig = { chat: { label, colors: { light: ["var(--cat-1)"], dark: ["var(--cat-1)"] } }, … }`.
EvilCharts normalises CSS vars through a canvas probe, so `var(--…)` works in both renderers.

## 7. Phone layouts (`charts-390.svg`, `charts-user-390.svg`)

- The card is full width (16 px gutters). Title, then the summary (wraps to ≤ 3 lines), then the period
  `SegmentedControl` at full width, **44 px** high.
- The plot is 200 px high. There is no horizontal scrolling and no dataZoom/brush.
- At most **7 columns or 12 points**: 30 days become 30 thin columns at ≥ 640 px but **weekly sums** (≤ 5) on phones,
  and the summary says so ("haftalık toplam").
- Y axis: 3 ticks, compact numbers. X labels: weekday initials or "14 Eki".
- Tooltip: tap a column (the hit area is the full column height, ≥ 44 px wide strips) or press-and-drag to scrub. The
  tooltip is pinned **above** the plot so the finger does not cover it, and a second tap or a tap outside closes it.
- The ⋯ menu is a bottom sheet (pattern 4). "Tabloyu göster" is a 44 px full-width secondary button under the plot; the
  table renders as stacked rows (day · total), and the full table goes to CSV.
- User and academician statistics on phones are **tiles, meters and BarLists**. ECharts is not loaded on those routes.

## 8. Motion (motion_designer skill, `docs/design/v2/motion.md` §0.3 A9; free transitions.dev recipes only)

Purpose sentence: "When a chart's data arrives or changes because the user asked, motion tells them the new state is
ready; it never decorates."

| Moment | Animation | Token / recipe | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| First load | **no grow-in, no stagger** (`animationType="none"`, ECharts `animation: false`) | — (A9) | same | — |
| Loading → content | skeleton bars pulse, then crossfade to the plot | **`skeleton-reveal` (free)**, pulse 1000 ms loop while fetching; reveal retimed 400 → **180 ms** (`--dur-base`) | 100 ms opacity, no pulse | opaque skeleton |
| Period change (user caused) | plot swaps data instantly; summary sentence text swaps | **`text-states-swap` (free)** 150 ms on the summary only | instant swap | — |
| Tooltip | appears after 80 ms hover/tap delay | **`tooltip` (free)** 150 ms in / 50 ms out | opacity only, 100 ms | solid tooltip background |
| Hover emphasis on a series | ECharts `stateAnimation.duration = 120` ms, `emphasis.focus = "series"` (others fade to 0.3) | `--dur-fast` | `stateAnimation.duration = 0` | — |
| Period control pill | existing `SegmentedControl` glass morph | pattern 2, `glass-morph` | existing | existing |
| CSV downloaded | button label "Veriyi indir → İndirildi ✓" | **`text-states-swap` (free)** 150 ms, then back after 2 s | instant | — |
| Live telemetry tick (ops, 30 s poll) | no animation; the "Güncellendi" time swaps | — | — | — |
| KPI above a chart changes while open | ticker | pattern 11, `ticker` | final value | — |

Rejected free recipes: `number-pop-in` (500 ms, count-up feel, on the anti-AI list), `shimmer-text`,
`matrix-loader` (decorative), and EvilCharts' own 2 s shimmer and 500 ms grow. **Motion Agent hosted fixes used: 0**
(none reserved for charts; no hero moment here). These rows go into `motion.md` as a new §3.18 "Charts" by its owner
when CH-02 ships.

## 9. Accessibility

- `<figure aria-labelledby=title aria-describedby=summary>`. The plot is `aria-hidden`, and the table twin is always
  present (§5.5). An axe check is part of CH-02.
- **Keyboard.** The plot wrapper is one tab stop (`tabIndex=0`, `role="group"`, label "Grafik, ok tuşlarıyla gezinin").
  ←/→ move a focused bucket (ECharts `dispatchAction({type:"showTip", dataIndex})`), Home/End jump, and Esc hides. A
  polite live region reads the bucket ("14 Ekim Çarşamba: toplam 82.300 token; Sohbet 37.120 …"), debounced 250 ms. The
  focus ring is drawn on the wrapper (outline stays visible; no `outline-none`).
- **Colour.** Never alone: legend + direct labels + decal on demand + table. Forced-colors: `decal: "auto"` and system
  colours on axes.
- **Touch.** 44 px column strips, the menu button 44 × 44, and no hover-only information (everything in the tooltip
  is also in the table).
- **Turkish first.** Every string has tr + en keys under `charts.*`, numbers and dates use `Intl` tr-TR /
  Europe/Istanbul, and no raw series keys ever reach the UI (`chat` → "Sohbet").
- **Text.** Axis text is ≥ 11 px (`text-xs`), the summary is ≥ 13 px, and the summary is never truncated.

## 10. Performance budget

| Budget | Value | How it is checked |
|---|---|---|
| First-load JS of any route without a chart | **+0 kB** (ECharts never in a shared chunk) | `next build` route table before/after (CH-01 records it) |
| Lazy chart chunk (echarts core + bar + line + Grid/Tooltip/DataZoom/Aria + Canvas + SVG + EvilCharts wrappers) | **≤ 240 kB gz** (measured engine 217 kB + wrappers) | `next build` + `gzip -9` of the chunk; CI fails above |
| Net change on a chart route once Recharts is gone (CH-09) | ≤ +110 kB gz | same |
| Time to first chart paint after data (desktop, 4× CPU) | ≤ 150 ms; phone ≤ 250 ms | Playwright `performance.measure` around `chart.on("finished")` |
| Interaction (tooltip move, keyboard scrub) | ≤ 3 dropped frames, no LoAF > 100 ms | `e2e/motion-audit.spec.ts` pattern |
| Ops canvas series | 1,440 points per series, `sampling: "lttb"`; resize via the EvilCharts `ResizeObserver` (no per-frame JS) | audit trace |
| Instances per route | ≤ 4 live ECharts instances; off-screen cards mount on intersection (`IntersectionObserver`, rootMargin 200 px) | review |
| Memory | dispose on unmount (EvilCharts does `chart.dispose()`) | vitest asserts dispose |

## 11. Migration order

1. **CH-04 Dashboard `PeriodArea`** (`components/dashboard/dashboard-charts.tsx`). The simplest single series. It
   proves the shell, SVG, the table twin and the partial bucket.
2. **CH-05 AI daily stacked bar** (`components/admin/ai/usage-tab.tsx`, `ai-model.ts`; W3-AI). Proves stacking, the
   legend, the decal, CSV and phone weekly folding.
3. **CH-06 Ops "İstekler"** (`components/admin/ops/ops-panel.tsx`, `ops-model.ts`; W3-OPS). The hand-drawn SVG becomes
   3 small multiples on canvas; this proves the canvas + large-data path.
4. **CH-09 Remove Recharts**: delete `components/ui/evilcharts/**` (Recharts), drop `recharts` from package.json,
   update SOURCES.md.

New charts follow once the shell exists:

- CH-07: bookings per week, and request outcomes;
- CH-08: soft score across runs;
- CH-10: audit events per day (optional, later).

The non-chart rows are CH-11: academician load and the user totals tiles.

## 12. Phase 2 plan and sources

Phase 2 started on "phase 2 go" (2026-10-17); CH-01 and CH-02 are done (notes below).

```bash
cd smartsched/frontend
npm install echarts                     # 6.1.0, Apache-2.0 (zrender BSD-3-Clause)
npx shadcn@latest add @evilcharts/echarts-bar-chart @evilcharts/echarts-line-chart @evilcharts/echarts-area-chart
# pulls @evilcharts/echarts-{chart,tooltip,legend,dot,brush}; lands in src/components/evilcharts/** →
# move to src/components/charts/evil/{charts,ui}/, re-point "@/registry/ui/echarts-*" imports, add headers
```

Patches allowed in the vendored files are listed in each header, as for the Recharts variant:

- import paths;
- tooltip/axis value formatting through an injected `valueFormatter` (no bare `toLocaleString()`);
- `AriaComponent` registered in `echarts-chart` for `aria.decal`.

Nothing else is changed, so diffs against the registry stay readable.

### §sources

| Item | Source URL | Licence | Notes |
|---|---|---|---|
| `charts/evil/charts/echarts-bar-chart.tsx` | https://evilcharts.com/r/echarts-bar-chart.json (repo https://github.com/legions-developer/evilcharts) | MIT © 2026 Gurbinder, `src/components/ui/LICENSES/evilcharts-MIT.txt` | added CH-01 (shadcn 4.22.0), header per file |
| `charts/evil/charts/echarts-line-chart.tsx` | https://evilcharts.com/r/echarts-line-chart.json | MIT (same) | added CH-01, header per file |
| `charts/evil/charts/echarts-area-chart.tsx` | https://evilcharts.com/r/echarts-area-chart.json | MIT (same) | added CH-01, header per file |
| `charts/evil/ui/echarts-{chart,tooltip,legend,dot,brush}.tsx` | https://evilcharts.com/r/echarts-*.json (registry dependencies) | MIT (same) | added CH-01, header per file |
| `echarts` npm 6.1.0 (pinned exactly) | https://echarts.apache.org | Apache-2.0 (NOTICE retained in node_modules) | tree-shaken `echarts/core` imports only; installed CH-01 |
| `zrender` npm 6.1.0 | https://github.com/ecomfe/zrender | BSD-3-Clause | transitive |
| transitions.dev free recipes `skeleton-reveal`, `tooltip`, `text-states-swap` | scratchpad `transitions/free/*.md` | free plan: use and modify in commercial projects, no redistribution; re-implemented, `/* transitions.dev: <name> */` header if any CSS is pasted | no Pro |
| Mobbin references | §3 links | reference only | — |

### Phase 2 notes (CH-01 + CH-02, designer charts-p2-2026-10-17)

Built: `smartsched/frontend/src/components/charts/**` (shell, lazy forms, vendored `evil/**`). No app surface uses it
yet (CH-04 onward). Where the build differs from §5–§8, and why:

| Spec | Built | Why |
|---|---|---|
| §5.3.7 frosted tooltip | solid EvilCharts `default` tooltip (bg-background) | the free `tooltip` recipe fades the tooltip root; fading an ancestor of `backdrop-filter` strips the blur (motion skill §4, backdrop-root rule). Reduced transparency is then free |
| §5.3.4 CSV in the ⋯ menu | "Tabloyu göster" and "Veriyi indir" are footer buttons (44 px on touch, full width on phones); the ⋯ menu holds "Görseli indir" and "Yazdır" | Simplicity principle: the two common actions are visible, the rare ones sit behind ⋯ |
| §5.3.4 menu as a bottom sheet on phones | Base UI dropdown on all sizes | open for CH-03 (the sheet needs the phone pattern 4 wrapper) |
| §8 skeleton-reveal (blur + fade) | 1000 ms pulse while loading, then a 180 ms opacity-only reveal, only when the plot replaces a loading state | no blur on a plot larger than 400 × 300 (motion skill §4) |
| §8 text-states-swap (exit + enter) | enter half only (150 ms, 4 px), on the summary and the CSV label; the label swaps back after 2 s | the new numbers are never delayed by the exit half |
| §8 tooltip 50 ms out | instant out | ECharts hides the root with `display: none` (`displayTransition: false`) |
| §6 "Grafiklerde desen" | `use-chart-patterns.ts`: per user in localStorage `smartsched.charts.patterns.<userId>`, default off, forced-colors turns it on; `aria.decal.show` follows it; `aria.label` stays off (no generated English description; the plot is aria-hidden) | §13.3 is still open; the toggle in /profile is CH-03's |
| §5.6 renderer | `pickRenderer`: SVG when marks ≤ 300, on phones (< 768 px) and on print (`beforeprint`/`print` media); canvas otherwise | as specified, plus phones (brief: SVG on phones) |
| §10 off-screen mount | `IntersectionObserver` (rootMargin 200 px) before the plot mounts | as specified |

Vendored patches (each file's header lists them): import paths (code and comments, `grep @/registry` = 0);
`<Tooltip valueFormatter labelFormatter className>` (tooltip values used a bare `toLocaleString()`); tooltip text
HTML-escaped (`escapeHtml`, the tooltip is innerHTML); `AriaComponent` registered; `useReducedMotion` → `useReduce`
from `@/lib/motion` (honours the in-app switch; eslint `no-restricted-imports`); file-level `react-hooks/refs` waiver
in the three chart files (the ECharts instance lives in refs by design). `chartOptions` is merged **shallowly** by
EvilCharts, so the shell only passes top-level keys (`animation`, `stateAnimation`, `aria`), never `tooltip`/`series`.

Bundle (esbuild 0.28, minified, gzip -9, React/Next/motion/lucide/Base UI and the app's `@/lib`, `@/components/ui`
external, split ESM like `next/dynamic`):

| Chunk | gz |
|---|---|
| shared engine chunk (echarts core + zrender + both renderers + Aria + `evil/ui/echarts-chart`) | 203.7 kB |
| bar form (EvilCharts bar + wrapper) | 8.6 kB |
| line form | 7.8 kB |
| area form | 9.1 kB |
| a bar route's lazy total / all three forms | 212.3 kB / 229.2 kB (budget ≤ 240 kB) |
| the shell itself, static (chart-card + table + csv + format + summary + period + skeleton) | 5.3 kB JS + 1.1 kB CSS |
| routes without a chart | +0 kB: nothing outside `components/charts/**` imports it |

`next build` was not run in phase 2: the shared host had about 2.4 GB free and even a full `tsc` was OOM-killed. The
before/after route table is the first step of CH-04 (the first route that mounts a ChartCard).

### Migration notes (CH-03 … CH-09, designer charts-p2-2026-10-17)

| Ticket | Built | Differs from the spec because |
|---|---|---|
| CH-03 | `chart-keyboard.ts` (one tab stop, ←/→/Home/End/Esc, live read-out after 250 ms), `chart-patterns-toggle.tsx` on /profile, print CSS in `chart-card.css`, `e2e/charts-a11y.spec.ts` on a vite-built fixture | `showTip` by `dataIndex` shows an empty tooltip when the axis pointer is `none` (EvilCharts bars), so `chart-api.ts` shows it by pixel. ChartCard memoises the plot element: re-rendering an EvilCharts chart re-pushes its option (`notMerge`) and dropped the keyboard tooltip. Callers should pass stable `data`/`config` (useMemo) for the same reason |
| CH-04 | `PeriodArea` on ChartCard + area form, one series `--seq-4`, `hint` = what is measured, summary "En yoğun saat 10:10 (%86)." | the dashboard's own title/hint lines moved into the card (one heading); the y axis is not pinned to 0–100 % (EvilCharts merges `chartOptions` shallowly, so `yAxis` cannot be overridden without losing its formatter) |
| CH-05 | `admin/ai/usage-chart.tsx` (moved out of usage-tab.tsx), stacked bar, `SERIES_COLOR` per feature (`dailyLegend`), today hatched (`lastIsToday`), phones fold to weekly sums (`foldWeeks`, ≤ 5 columns) | the period control stays the page's (it drives the KPI tiles too), so the card has none |
| CH-06 | `admin/ops/requests-chart.tsx`: ONE ChartCard with three small multiples (requests, 5xx, p95; shared x, own axis each), one summary/table/CSV, the keyboard scrub moves all three tooltips; stale strip when a refetch fails over old data; `chartGeometry` retired | ranges stay 30 / 60 / 180 dk: the backend caps `/ops/requests?minutes=` at 180. 24 sa / 7 g need a coarser server step (W3-OPS). ≤ 180 points per chart → SVG by the renderer rule, so `sampling: "lttb"` is not needed yet (and `series` cannot be set through the shallow `chartOptions`) |
| CH-09 | `components/ui/evilcharts/**` deleted, `recharts` uninstalled (lock: recharts + d3-*, redux, victory-vendor gone), SOURCES.md updated, `LICENSES/evilcharts-MIT.txt` kept | — |

### CH-07 / CH-08 / CH-10 / CH-11 notes (frontend builder ch-m-2026-10-18)

| Ticket | Built | Differs from the spec because |
|---|---|---|
| CH-07 | `admin/booking-weekly.tsx` (+ model) on `/admin` › "Bu dönem · {dönem}": "Haftalık rezervasyonlar" (one series `--seq-4`, current week hatched, exam weeks direct-labelled "Sınav haftası" on the axis + a text column in the table/CSV) and "Haftalık talep sonuçları" (stacked approved / rejected / pending, cat-1..3 + legend). Client `lib/api/stats.ts` | the backend route does not exist (spec below). Until it lands the section shows ONE honest empty card ("Haftalık sayımlar sunucuda henüz hazır değil"), never numbers. Gate is `system.export_bookings` (there is no `bookings.admin` permission). `GET /requests/stats` was not reused: it counts *meeting/exam requests* by status per term, not booking requests per week. Exam bars are not recoloured (`SEQ_EMPHASIS`): the vendored bar takes one colour per series, so the label carries it. Placed above "Veri" (export), below the setup groups: the setup checklist stays first |
| CH-08 | `runs/score-history.tsx` (+ model) above the runs table: line + resting dots (`LineFormProps.dots`), finished COURSE runs with a score (OPTIMAL / FEASIBLE / FEASIBLE_PARTIAL) by `finished_at`; cancelled, failed, running, exam runs and imported boards excluded; active run labelled "#12 etkin"; nothing below 3 runs; tap / click a dot or ←/→ + Enter opens `/runs/{id}` | exam runs are left out (another scale). The card is loaded with `next/dynamic` from runs-list.tsx, because the shell (command palette, notification bell) imports runs-list.tsx for helpers; `isImportBoard` moved to `runs/run-kinds.ts` (re-exported) to avoid a cycle |
| CH-10 | `audit/audit-daily.tsx` (+ model) above the audit list for `audit.view`: 30 columns, today hatched; a tap / click on a column, or ←/→ + Enter, sets the filter form's from = to = that day (the date fields show it; "Sıfırla" undoes it) and a polite live region says "Liste 13 Ekim Salı gününe süzüldü." Phones: the card sits behind one 44 px "Günlük olayları göster" button so the first event stays high | backend route missing (spec below) → honest empty card |
| CH-11 | `profile/my-stats.tsx` on `/my-bookings` (replaces the subtitle sentence) and `/profile` ("Özetim"): tiles etkin / bu dönem / açık talep + "3 / 5 aktif rezervasyon hakkı kullanıldı · 2 rezervasyon daha yapabilirsiniz" (`mine-can-create` kept). `profile/my-load.tsx` "Haftalık ders yüküm" for people linked to an instructor record (`GET /moderation/me/preferences` → `linked`): BarList Mon–Fri (+ weekend with classes), "ders yok" for 0, each row a 44 px link to `/timetable?lens=day&day=N&subject=instructor:ID&run=R` | §13.2 decided as a small `me` route (spec below), not the planner-scoped `/terms/{id}/instructors/load` (no weekday split, and a user must not page through everyone's load). Until it lands: "Ders yükü verisi sunucuda henüz hazır değil." The "toplam" number of the old sentence is gone (three tiles only); `e2e/loop-r2-laneB.spec.ts:140` asserted it |

Shell additions (CH-08/10): `ChartCard` `onSelect(index)` + `selectHint` (a visible line under the plot, no hover-only affordance); Enter / Space selects the keyboard-focused bucket (`chart-keyboard.ts`); a click / tap selects the bucket under the pointer inside the grid (`ChartApi.indexAt`, `convertFromPixel` on grid 0). No new motion: selecting is navigation / filtering (frequent, purposeful, no animation, motion skill §2.1); the phone disclosure is instant; tiles and BarList never grow in (A9). Reduced motion: nothing to remove.

Bundle: `/profile` and `/my-bookings` import no chart module (the CH-11 test fails if `chart-lazy` is imported); `/runs` loads the score card as its own chunk; `/admin` and `/admin/audit` are now chart routes (static shell ≈ 5 kB + the lazy bar chunk only when a plot renders, i.e. never while the routes are missing).

Route specs (asks for the backend owners; the frontend already parses exactly these shapes, `lib/api/stats.ts`):

1. `GET /api/v1/bookings/stats/weekly?term_id=<int>` · permission `system.export_bookings` (403 otherwise) · read-only.
   `200 {term_id, from, to, today, weeks: [{week: int ≥ 1 (term week), start, end (ISO days), exam: bool (an exam-session / exam timetable week), partial: bool (contains today), bookings: int (live BOOKED bookings dated in the week, one per booking row as /bookings/dashboard counts), requests: {approved, rejected, pending} (approval requests by the week they were submitted, current status; expired / withdrawn not counted)}]}`. 404 `{code: "term_not_found"}` for an unknown term. pytest `test_ch_07_*`: counts equal a SQL recount on the Bahar fixture; 403 without the permission.
2. `GET /api/v1/audit/stats/daily?days=<1..90, default 30>` · permission `audit.view` · `200 {from, to, days: [{day, events}]}` with days in Europe/Istanbul; days without events may be omitted (the client fills 0).
3. `GET /api/v1/me/load?term_id=<int, optional: current term>` · signed in · only the caller's instructor record (`Instructor.user_id = me`) · `200 {linked: bool, instructor_id, term_id, run_id (the published run of the term, null if none), days: [{day: 1..7 ISO weekday, periods, minutes}], total_periods}`; periods counted like `instructor_loads` (a joint lecture once). `linked: false` → `days: []`.

## 13. Open questions for the orchestrator / owner

1. **Answered in CH-07 (ch-m-2026-10-18):** a server aggregate, spec in the CH-07…CH-11 notes; asked of W3-SLOT.
   Was: bookings per week (CH-07) needs a read-only aggregate. `GET /bookings/stats/weekly?term=` does not exist. Should
   W3-SLOT add it, or should it be computed client-side from `/bookings` (too heavy at ~20k rows)?
2. **Answered in CH-11 (ch-m-2026-10-18):** a small `GET /me/load` (spec in the CH-07…CH-11 notes); asked of the backend.
   Was: should the academician's weekly load (CH-11) read `GET /terms/{id}/instructors/load` with a `me` scope (a backend
   change), or be derived from the user's own timetable feed? The latter needs no new endpoint.
3. Should the "Grafiklerde desen" accessibility toggle be an org setting, a per-user preference, or both? It could be
   proposed as a per-user preference in `/profile`.
   **Answered in CH-03:** per user, in `/profile` (`chart-patterns-toggle.tsx`, default off; forced colours turn it on).
   An org-wide default is not built; ask again if admins want one.
