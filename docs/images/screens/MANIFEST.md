# SmartSched README screenshots

Captured 2026-10-08 from a production build (`next build` + `next start`, `NEXT_PUBLIC_API_MOCK=1`) on port 3300 with
Playwright/Chromium, locale EN (`NEXT_LOCALE=en` cookie), theme via the next-themes `theme` localStorage key,
`reducedMotion: reduce`, network idle + font load, toasts dismissed before each shot.

- Desktop: viewport 1440x900 @ deviceScaleFactor 1.5 -> 2160x1350 px.
- Mobile: viewport 390x844 @ deviceScaleFactor 2 -> 780x1688 px.
- Optimised with `convert -strip -define png:compression-level=9` (lossless). No file exceeded 600 KB, so no PNG8
  reduction was needed; the overview sheets were written by ImageMagick with a 255-colour palette (visually clean).
- Source snapshot: branch `claude/gracious-cerf-w1598m` HEAD `12aae44` + the main checkout's then-uncommitted
  `messages/en.json` / `messages/tr.json` (required for the in-progress Generator Studio to type-check). The
  committed snapshot alone fails `next build` (missing `studio.*` message keys).
- Room cards/detail: the mock data assigns random `picsum.photos` stock images (street, field, camera) to a few
  rooms. For the README these were nulled in the browser (Playwright route on `/api/v1/rooms*`), so every room shows
  the app's own no-photo tile (room code on gradient). Source and mocks unchanged.

Files: 46 · total 10.8 MB

| File | Pixels | Size | Shows |
|---|---|---|---|
| `login-light.png` | 2160x1350 | 52 KB | Sign-in card (demo credentials filled, password masked), TR/EN + theme toggles. |
| `login-dark.png` | 2160x1350 | 52 KB | Sign-in card (demo credentials filled, password masked), TR/EN + theme toggles. |
| `dashboard-light.png` | 2160x1350 | 239 KB | Dashboard: infeasible-run banner, KPI cards (utilisation, needs review, sections, last run), utilisation-by-building heatmap, pending requests, last runs. |
| `dashboard-dark.png` | 2160x1350 | 242 KB | Dashboard: infeasible-run banner, KPI cards (utilisation, needs review, sections, last run), utilisation-by-building heatmap, pending requests, last runs. |
| `import-wizard-light.png` | 2160x1350 | 166 KB | Import wizard step 1 (kind picker): course/exam planning lists, weekly room grid, legacy CRBS DB; recent imports. |
| `import-wizard-dark.png` | 2160x1350 | 168 KB | Import wizard step 1 (kind picker): course/exam planning lists, weekly room grid, legacy CRBS DB; recent imports. |
| `import-report-light.png` | 2160x1350 | 285 KB | Import step 3 after the mock upload of "Bahar Derslik Planlama Listesi v5.xlsx": parse KPIs (1,529 rows / 1,526 created / 3 skipped / 12 warnings) and the severity-filterable warnings table. |
| `import-report-dark.png` | 2160x1350 | 287 KB | Import step 3 after the mock upload of "Bahar Derslik Planlama Listesi v5.xlsx": parse KPIs (1,529 rows / 1,526 created / 3 skipped / 12 warnings) and the severity-filterable warnings table. |
| `requests-light.png` | 2160x1350 | 484 KB | Requests inbox (meetings) with the row drawer open for FZY 415: day/period, enrolment, tags, building, preferred rooms, source row. |
| `requests-dark.png` | 2160x1350 | 481 KB | Requests inbox (meetings) with the row drawer open for FZY 415: day/period, enrolment, tags, building, preferred rooms, source row. |
| `rooms-light.png` | 2160x1350 | 371 KB | Rooms, cards view: 61 rooms, building/tag filter chips, capacity, exam capacity, utilisation sparkline. |
| `rooms-dark.png` | 2160x1350 | 376 KB | Rooms, cards view: 61 rooms, building/tag filter chips, capacity, exam capacity, utilisation sparkline. |
| `room-detail-light.png` | 2160x1350 | 304 KB | Room A 204 detail: facts panel and this-week occupancy heatmap (W7). |
| `room-detail-dark.png` | 2160x1350 | 312 KB | Room A 204 detail: facts panel and this-week occupancy heatmap (W7). |
| `timetable-day-light.png` | 2160x1350 | 185 KB | Run #1 day zoom, W7 Wednesday (busiest weekday), building A filter, sidebar collapsed: 10 events visible with capacity fill and period spans. |
| `timetable-day-dark.png` | 2160x1350 | 186 KB | Run #1 day zoom, W7 Wednesday (busiest weekday), building A filter, sidebar collapsed: 10 events visible with capacity fill and period spans. |
| `timetable-week-light.png` | 2160x1350 | 162 KB | Run #1 week zoom, W7: rooms x days mini-blocks with per-day utilisation; hatched = pre-occupied. |
| `timetable-week-dark.png` | 2160x1350 | 163 KB | Run #1 week zoom, W7: rooms x days mini-blocks with per-day utilisation; hatched = pre-occupied. |
| `timetable-drag-light.png` | 2160x1350 | 187 KB | Mid-drag (dnd-kit pointer): BME 217 §1 lifted from A 204 and hovering A 207 P2–P3, blue (valid) drop highlight. Drag was cancelled with Esc afterwards, so no data changed. |
| `timetable-drag-dark.png` | 2160x1350 | 190 KB | Mid-drag (dnd-kit pointer): BME 217 §1 lifted from A 204 and hovering A 207 P2–P3, blue (valid) drop highlight. Drag was cancelled with Esc afterwards, so no data changed. |
| `run-report-light.png` | 2160x1350 | 184 KB | Run #1 hero: hard-score ring 100/100 (Feasible), soft-preference breakdown 91/100 by term, stats; chat panel alongside. |
| `run-report-dark.png` | 2160x1350 | 184 KB | Run #1 hero: hard-score ring 100/100 (Feasible), soft-preference breakdown 91/100 by term, stats; chat panel alongside. |
| `run-diagnoses-light.png` | 2160x1350 | 272 KB | Run #2 (infeasible, 97/100): diagnosis cards (Hard · Critical) with suggested fixes (release_room / move / split) and Apply. |
| `run-diagnoses-dark.png` | 2160x1350 | 274 KB | Run #2 (infeasible, 97/100): diagnosis cards (Hard · Critical) with suggested fixes (release_room / move / split) and Apply. |
| `chat-panel-light.png` | 2160x1350 | 271 KB | Run #1 timetable tab with the chat panel: "Move BME 419 to A 204" -> planner reply + Proposed changes card with Apply. |
| `chat-panel-dark.png` | 2160x1350 | 273 KB | Run #1 timetable tab with the chat panel: "Move BME 419 to A 204" -> planner reply + Proposed changes card with Apply. |
| `settings-ai-light.png` | 2160x1350 | 136 KB | Settings > AI: masked Anthropic key (sk-ant-…7Qx2, connected), Test key / Replace key, model picker. |
| `settings-ai-dark.png` | 2160x1350 | 138 KB | Settings > AI: masked Anthropic key (sk-ant-…7Qx2, connected), Test key / Replace key, model picker. |
| `command-palette-light.png` | 2160x1350 | 406 KB | Ctrl+K command palette over the dashboard, searching "A 2" -> room results with capacity/tags. |
| `command-palette-dark.png` | 2160x1350 | 411 KB | Ctrl+K command palette over the dashboard, searching "A 2" -> room results with capacity/tags. |
| `mobile-dashboard-light.png` | 780x1688 | 100 KB | Mobile (390x844) dashboard: banner + stacked KPI cards. |
| `mobile-dashboard-dark.png` | 780x1688 | 103 KB | Mobile (390x844) dashboard: banner + stacked KPI cards. |
| `mobile-agenda-light.png` | 780x1688 | 148 KB | Mobile timetable agenda fallback, run #1 W7 Wednesday, building C filter: period-grouped event cards with Move… actions. |
| `mobile-agenda-dark.png` | 780x1688 | 150 KB | Mobile timetable agenda fallback, run #1 W7 Wednesday, building C filter: period-grouped event cards with Move… actions. |
| `mobile-drawer-light.png` | 780x1688 | 101 KB | Mobile navigation drawer open (term switcher, nav groups, user, TR/EN, theme). |
| `mobile-drawer-dark.png` | 780x1688 | 105 KB | Mobile navigation drawer open (term switcher, nav groups, user, TR/EN, theme). |
| `studio-scope-light.png` | 2160x1350 | 266 KB | Generator Studio step 1 Scope: term, classes/exams, horizon (whole term), "What will happen" summary + readiness (Blocked). |
| `studio-scope-dark.png` | 2160x1350 | 270 KB | Generator Studio step 1 Scope: term, classes/exams, horizon (whole term), "What will happen" summary + readiness (Blocked). |
| `studio-classes-light.png` | 2160x1350 | 341 KB | Generator Studio step 2 Classes: filters, quick-filter chips, class table with in-plan toggles. |
| `studio-classes-dark.png` | 2160x1350 | 345 KB | Generator Studio step 2 Classes: filters, quick-filter chips, class table with in-plan toggles. |
| `studio-rules-light.png` | 2160x1350 | 351 KB | Generator Studio step 3 Rules & preferences: "write it in your own words" box, one-click common rules, rule list (one rule shows its problem state). |
| `studio-rules-dark.png` | 2160x1350 | 356 KB | Generator Studio step 3 Rules & preferences: "write it in your own words" box, one-click common rules, rule list (one rule shows its problem state). |
| `studio-precheck-light.png` | 2160x1350 | 335 KB | Generator Studio step 4 Pre-check: Blocked, impossible class BME 419 §1 with fix buttons, rule that matches nothing. |
| `studio-precheck-dark.png` | 2160x1350 | 338 KB | Generator Studio step 4 Pre-check: Blocked, impossible class BME 419 §1 with fix buttons, rule that matches nothing. |
| `overview-light.png` | 1600x1012 | 121 KB | 2x2 contact sheet: dashboard, timetable-day, run-report, chat-panel (8 px gaps). |
| `overview-dark.png` | 1600x1012 | 141 KB | 2x2 contact sheet: dashboard, timetable-day, run-report, chat-panel (8 px gaps). |

## Skipped / caveats

- Nothing skipped. All 15 desktop shots, 3 mobile shots and 4 Generator Studio steps were captured in light and dark.
- Generator Studio (`studio-*`) shows the in-progress /generate rebuild as of this snapshot; it rendered without
  errors and looked finished enough to ship, but it is due to be re-shot when the rebuild lands.
- `chat-panel`: the page is at max scroll so the whole chat panel fits. The hero's "Solve time" label shows
  faintly through the translucent sticky header at top-right (real app behaviour).
- Run selector on /timetable truncates its label ("#1 · 2026-BAHAR · Feasible · 1(") on desktop and mobile:
  an app layout issue (`w-64` select), visible in timetable-day/week/drag and mobile-agenda.
- `/timetable` logs React hydration error #418 (text mismatch) in production; the page recovers and renders correctly.
