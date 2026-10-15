# UI/UX visual-quality review, 2026-10-15

Ledger: uiux-visual-review-2026-10-15 · Role: senior product designer / UI QA lead · Reviewer made no source edits; the orchestrator saved this report.

**Setup.**
- Snapshot: `origin/claude/gracious-cerf-w1598m` at **1e57095** (`npx tsc --noEmit` exit 0).
- Stack: `scripts/record/stack.sh up`, all three terms + the room master imported, then `stack.sh runs`.
- Runs: #7 Güz week 3 (FEASIBLE_PARTIAL, 524/530) and #8 Güz term (FEASIBLE_PARTIAL, 517/530).
- Captures: 36 admin routes and 7 teacher routes, each in light/dark at 1440/1024/390.
- Per capture: a Tab focus audit, axe-core (color-contrast, target-size, label, nested-interactive, region, heading-order) and computed-style metrics.
- Judged against the motion_designer skill + audit.md, liquid-glass.md, tokens.md, motion.md, references.md, all-classes.md, calendar.md and phase19-*.md.

**Evidence** is in the session scratchpad, abbreviated below as `EVID`:
- Folder: `EVID = /tmp/claude-0/-home-user-classroombookings/ac8cf3be-4f7b-53da-a7ff-63cf01e137b0/scratchpad/uiux-review/shots`.
- Subfolders: `admin/` and `teacher/` captures; `settled/` re-shots (use these for data screens); `crops/`; `brand/`.
- Data files: `admin/probe.json` and `metrics-*.json`.
- The capture scripts are in `../scripts/` (capture.cjs, probe.cjs, settle.cjs).

## 1. BLUF
- The owner's four complaints are confirmed. The intended system (liquid-glass.md, all-classes.md, references.md) is mostly sound. The gap is in the implementation:
  - primitives that silently break focus;
  - no sizing system and no column system;
  - per-file arbitrary pixel values: 531 font sizes, 45 shadow strings, 133 raw `<button>`s;
  - Mobbin patterns cited in the specs but not built (H6 "dot + word"; all-classes §5 column resize).
- The "AI-generated" read comes from five things:
  - (a) the same 32 px-radius frosted card around every block;
  - (b) Sparkles icons and centred hero empty states;
  - (c) duplicated numbers dressed as heroes (ring gauge, avatar circles);
  - (d) controls of different heights and shapes side by side;
  - (e) default-looking assets (Next.js favicon, lucide logo).
- Severity: 4 Blocker, 41 Major, 24 Minor.

**Top 10 fixes**
1. **Focus is invisible on nearly every screen (blocker).**
   - Cause: Tailwind v4 `outline-none` sets `--tw-outline-style:none`, and `focus-visible:outline-2` then reads that variable. Measured: 0 of 25 tab stops visible on most routes.
   - Fix: add an unlayered `:focus-visible{--tw-outline-style:solid}` in globals.css; remove `outline-none` from the primitives; widen `focus-ring.test.ts` SCOPE to all of `src/`.
2. **Remove the AI tells.**
   - The Sparkles icon appears on onboarding, what's new, chat and write-it.
   - Uniform 32 px glass cards everywhere.
   - Centred heroes on 404, onboarding and find-room.
   - The ring gauge on runs.
   - Room avatar circles.
3. **One control-size system.** Today buttons are 18/20/22/24/26/28/32/34/40 px, and 85–97 % of admin controls are under 44 px at 390.
4. **One segmented control.** There are 5 implementations. Generate's control wraps onto 2 rows, and the dark My bookings thumb sits about 16 px above its track.
5. **A table column system.** `class-table.tsx` hard-codes a WIDTH map; there is no resize, pin or visibility state; the last column is clipped; timetable chips truncate codes to 1–2 letters.
6. **Container queries.** The dashboard KPI labels overlap at 1024, and the Generate bottom bar covers the sidebar at 1024.
7. **One type scale.** There are 531 arbitrary `text-[Npx]` uses. H1 is 34 px on most pages but 22 px on timetable, classes, requests and rooms.
8. **Field and border tokens.**
   - Input fill against the card is 1.15:1 (light) and 1.34:1 (dark), below the 3:1 non-text minimum.
   - There are two select styles.
   - Native date inputs show mm/dd/yyyy in a Turkish UI.
9. **Contrast and colour-only status.**
   - The dark timetable chip line 2 is 3.78:1 at 11 px.
   - Room over-capacity is shown in amber only, with no glyph.
10. **Brand.** The favicon is the unmodified create-next-app "N", and the logo is a lucide CalendarRange. (A new logo has since landed in 4fe999c and is being swapped in.)

## 2. Design-system issues

| Token / primitive | Problem | Evidence | Fix (exact) | Pri |
|---|---|---|---|---|
| Focus ring, all primitives | `outline-none` + `focus-visible:outline-2` draws nothing in TW 4.3.3 (`.outline-none{--tw-outline-style:none}`; `focus-visible:outline-2` uses `outline-style:var(--tw-outline-style)`). `[data-slot=button]`, tabs-trigger, switch, sidebar links and raw buttons show `outline-style:none` on 22/22 routes. 66 class strings use the broken pair; 18 use `outline-none` with no replacement (dropdown-menu, dialog, command, tabs panel, beui/dock, beui/file-upload). | `EVID/crops/dashboard-focus-no-ring.png`, `EVID/admin/probe.json` | (1) Unlayered at the end of globals.css: `:focus-visible{--tw-outline-style:solid}`. (2) Delete `outline-none` in button, tabs, switch, chip and shell; keep `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)`. (3) In scroll containers and grid cells use `focus-visible:-outline-offset-2`. (4) `focus-ring.test.ts` SCOPE = `["components","app"]`. | P0 |
| `--border-control` (new) | Fields are fill-only: fill-2 against the card is 1.15:1 light / 1.34:1 dark; the hairline is 1.23 / 1.34. WCAG 1.4.11 needs 3:1. | `EVID/teacher/teacher-find-room-light-1440.png` | Light `--border-control: rgba(20,24,36,.48)` (3.16:1 on #fafbfc); dark `rgba(255,255,255,.34)` (3.10:1 on #1d1e23). Use it in `fieldSurface` (`shadow-[inset_0_0_0_1px_var(--border-control)]`), checkbox borders and the switch off-track. Keep `--hairline` for separators only. | P1 |
| Type scale | 531 arbitrary sizes (`[13px]` 178, `[12px]` 171, `[11px]` 104, `[12.5px]` 28 …); the `type-*` utilities are used 430 times. H1 is 34 px on 28 routes and 22 px on timetable, classes, requests and rooms. | `EVID/admin/admin-classes-light-1440.png` vs `admin-runs-light-1440.png` | Fluid titles, 390→1440: `--text-large-title: clamp(1.75rem,1.611rem+.571vw,2.125rem)` (28→34); `--text-title-1: clamp(1.375rem,1.236rem+.571vw,1.75rem)` (22→28); `--text-title-2: clamp(1.125rem,1.032rem+.381vw,1.375rem)` (18→22); `--text-title-3: clamp(1rem,.954rem+.19vw,1.125rem)` (16→18). Fixed: headline/body 14/20, callout 13/18, footnote 12/16, caption 11/14; nothing below 11 except `text-2xs` 10 in week zoom. `PageHeader` always uses large-title. Lint gate: `text-\[[0-9.]+px\]` = 0. | P1 |
| Global `tabular-nums` | Hyphens render wide ("E - posta", "Güz 2026 - 27"). Probable cause (verify in DevTools): tabular-nums on `html`. | `EVID/test/admin-login-light-1440.png` | Remove it from `html`. Add `.tnum` on `td`, `[data-numeric]`, `time`, KPIs and period labels. | P2 |
| Control heights | Buttons 28/32/40; segmented 26/32/36/52/72; chips 24; raw buttons 18–64. No `pointer:coarse` variant. At 390, controls under 44 px: roles 97/107, sessions 146/155, departments 314/320, dashboard 46/62. | `EVID/admin/metrics-admin-light-1024_390.json` | `--control-h-xs:24px; -sm:28px; -md:32px; -lg:40px`. Under `@media (pointer:coarse)`: 32/36/44/48. Padding-x `calc(var(--control-h)*.4375)`, gap 6 (md) / 4 (sm), icon 16 (md/lg) / 14 (sm/xs). Button `size xs|sm|md|lg`, `shape "pill"|"rect"`; `IconButton` with a required `label`. Input, Select and Segmented read the same tokens. Lint: no `<button` outside `components/ui/**` (133 occurrences in 76 files today). | P1 |
| Segmented control | 5 implementations (ui/tabs segment, SegmentedGlass, beui/tabs, studio/segmented.tsx, 6 hand-rolled radiogroups). Generate's horizon control wraps to 2 rows at 1440; in light the thumb is a rectangle in a capsule track; in dark the thumb sits about 16 px above the track at rest. | `EVID/crops/generate-segmented-wrap-dark.png`, `mybookings-tabs-light.png`, `mybookings-tabs-dark.png` | One `SegmentedControl` (SegmentedGlass API), `size sm|md|lg`. Track `display:inline-grid; grid-auto-flow:column; grid-auto-columns:1fr; white-space:nowrap; min-width:max-content; padding:3px`. Thumb radius `calc(var(--track-radius) - 3px)`. Fall back to a Select under `@container`. The thumb is CSS at rest; `layoutId` only during motion (motion.md §3, pattern 2). Delete the others. Reference: Apple A15/H19; Linear view switcher. | P1 |
| Radius / `--corner-k` | Card 32, sidebar 32, glass-panel 41.6, inputs 19.2, buttons capsule. Large radii everywhere read as a template; the nesting rule is broken (tabs thumb). | `EVID/admin/probe.json`, `EVID/settled/admin-dashboard-light-1440.png` | Base ×k: xs 4, sm 6, md 8, lg 12, xl 14 (page cards), 2xl 18 (sidebar, sheets), 3xl 24 (dialogs), full (pills, chips, segmented). `--corner-k:1` without squircle, `1.25` with `corner-shape:squircle`. Inner radius = outer − padding. | P1 |
| Card / material | Every block is `glass-regular`, so the frosting has no purpose (A2/A8). The mobile tab bar lets chart labels show through (G1). | `EVID/crops/mobile-tabbar-light.png` | Card default `variant="plain"` (hairline, no blur). Glass only for sidebar, top bar, toolbars, popovers, sheets and the tab bar (`glass-chrome` + an opaque `--mat-chrome-solid` fallback). At most one hero card per page (Vercel H8). | P1 |
| Borders / shadows | 45 distinct `shadow-[…]` strings; hairlines drawn three ways; buttons carry `border border-transparent`; `* {outline-ring/50}` gives a 2.2:1 outline wherever only a width is set. | grep counts; `EVID/admin/metrics-admin-light-1440.json` | Tokens `--edge-hairline: inset 0 0 0 1px var(--hairline)`, `--edge-hairline-b: inset 0 -1px 0 var(--hairline)`, `--edge-control: inset 0 0 0 1px var(--border-control)`, `--edge-glass`, `--focus-ring-width:2px; --focus-ring-offset:2px; --focus-ring-offset-inset:-2px`. Utilities `edge-hairline`, `edge-control`. Ban `shadow-[` outside `ui/`. Drop `outline-ring/50` from `*`. | P2 |
| Icons | `Sparkles` on nav Onboarding, What's new, chat-panel, write-it and source-chip. All 15 admin sections use `Settings2`. Stroke widths 1.75/2/2.25/2.5 mixed. | `EVID/crops/topbar-sparkle.png` | Onboarding `FolderInput`, What's new `Megaphone`, Chat `MessageSquareText`; a distinct icon per admin section (Users, ShieldCheck, Building2, KeyRound, CalendarOff, Clock, Mail, ScrollText …). Stroke 1.75 everywhere (`[&_svg]:stroke-[1.75]` in ui, overrides removed). | P2 |
| Status = glyph + word (G4) | Room detail "90/58" amber with no glyph. /runs shows the status twice (text + badge). | `EVID/admin/admin-rooms_1-dark-1024.png`, `admin-runs-light-1440.png` | `AlertTriangle` 14 + "90/58 · 32 fazla". Runs: one dot + word status column (Vercel H6), plain numerals. | P1 |
| Selects / dates | `NativeSelect` is v1-shadcn style next to filled fields; its chevron sits on the bottom edge on Generate; a raw OS select is on /classes; native date inputs show mm/dd/yyyy (holidays, audit, find-room) while Sessions shows dd/mm/yyyy. | `EVID/admin/admin-admin_holidays-dark-1440.png` | NativeSelect = `fieldSurface` + `edge-control`, `h-(--control-h)`, chevron `inset-y-0 my-auto`. A DateField that formats with `Intl.DateTimeFormat(locale)` (tr: gg.aa.yyyy) on a Popover calendar. | P2 |
| Loading states | Zeros while loading ("0 dersi 0 dersliğe", "Tümü 0"); a skeleton and "Yükleniyor…" show together; screens take 4–33 s to settle. | `EVID/admin/admin-generate-light-1440.png`, `admin-requests-light-1440.png` | `undefined` shows a glyph-sized Skeleton, never 0. One loading signal per region (pattern 12). | P2 |
| Container-relative layout | Viewport breakpoints inside cards: the dashboard `sm:grid-cols-4` KPIs overlap at 1024; Generate's `fixed` bottom bar overlaps the sidebar at 1024. | `EVID/crops/dashboard-kpi-collision-1024-dark.png`, `generate-bottom-bar-overlaps-sidebar-1024.png` | `@container` on card content. KPI `dl` `grid-template-columns: repeat(auto-fit, minmax(9.5rem,1fr))`. The bottom bar is `sticky bottom-3` inside `<main>`. Gutter `padding-inline: clamp(16px,2.2vw,32px)`. Sidebar collapses to a 72 px rail below 1280. | P1 |

**Sizing system (summary)**
- Spacing: 4 px base, steps 2,4,6,8,12,16,20,24,32,40,48,64.
- Paddings: cards 16 / 12 (sm); toolbars 6; cells 8×12 (standard) and 4×8 (compact).
- Rows: 32 / 44 / 56 via `--row-h` and `data-density`.
- Type, control heights, radii and edge/focus tokens: as in the table above.

**Table column system** (all tables; TanStack v8 is already installed)
- **Column meta:** `{id, minSize, maxSize, size?: number|"auto", grow?, align: "start"|"end", pin?: "left"|"right", hideable, priority: 1–5}`.
- **Auto width:** measure the header plus the first 200 rows with `canvas.measureText` in the cell font, clamp to [min, max], give slack to the `grow` columns (Course, Program), and right-align numbers with tnum.
- **Resize:**
  - `enableColumnResizing:true, columnResizeMode:"onChange"`.
  - The handle is an 8 px hit area with a 1 px `--border-control` line on hover/focus, `role="separator" aria-orientation="vertical" tabIndex=0`.
  - Keys ←/→ move 8 px (Shift: 32 px); double-click auto-fits (all-classes.md §5).
- **Pin and hide:**
  - `columnPinning` left = [select, course], sticky, with an `inset -1px 0 0 var(--hairline)` edge when scrolled.
  - A Linear-style "Görünüm › Sütunlar" popover: toggle chips and drag reorder.
  - When the container is narrower than the sum of the minimums, hide columns by priority and show a "+3 sütun" chip.
- **Layout:** the header and the virtualised body share `grid-template-columns: var(--cols)`.
- **Persistence:** `{order, sizing, visibility, pinning, density}` in `localStorage["smartsched.table.<tableId>.<userId>"]`, synced into saved views.
- **References:** Airtable grid, Linear display options, Height column menu.

## 3. Per-screen issues

| Screen | Issue | Sev | Fix | Reference |
|---|---|---|---|---|
| All (admin + teacher) | No visible focus ring: 0/25 tab stops on dashboard, bookings, settings and admin/* (`EVID/admin/admin-dashboard-light-1440-focus.png`) | Blocker | §2 focus fix | Linear 2 px ring |
| Dashboard 1024 | KPI labels overlap ("İnceleme" on "Şubeler") | Blocker | Container query, auto-fit minmax(9.5rem) | Vercel H8 |
| Timetable 1440/1024 | Overlapping events truncate codes to 1–2 letters ("Fl…", "C.."); solid red "+3" boxes have no meaning; room columns fixed at 120 px (`EVID/admin/admin-timetable-light-1440.png`) | Blocker | Min chip width 72 px; beyond 2 overlaps, a "+3 çakışma" chip with a popover list; room column `minmax(112px,1fr)` + zoom; the code never truncates, the name truncates first | Apple Calendar, Notion Calendar, Amie H9 |
| Generate 1440 | Horizon segmented wraps to 2 rows; select / segmented / wrapped segmented have 3 heights (32/52/72); chevron misplaced | Blocker | One SegmentedControl, nowrap, `--control-h-md` | Apple A15 |
| Timetable dark | Chip line 2 is 3.78:1 at 11 px (#3d997c on #0f3635), 29 axe nodes (`EVID/crops/timetable-chips-dark.png`) | Major | Dark `--fac-*-ink` ≥ 4.5:1 on its tint (e.g. #6fd3b0); add the pairs to verify-contrast.mjs | tokens §2.4 |
| Timetable | Three floating capsules wrap into 2–3 rows; "Tüm gün" floats; title is 22 px | Major | One Toolbar with ToolbarGroups and a "⋯" overflow below 1280 | Apple Calendar toolbar |
| Timetable scrubber | Thumbs look like empty placeholders | Minor | Week numbers H1…H14 + today marker | Notion timeline H13 |
| Classes / Requests | Fixed WIDTH map; last column clipped ("Kesinleşe", "Derslik Tal"); course name truncated while Program has slack (`EVID/settled/admin-classes-light-1440.png`) | Major | §2 column system | Airtable, Linear |
| Classes | OS-native `<select>` "Run #8 · Kısmi" next to the H1 | Minor | Field-styled select or popover chip | Linear view switcher |
| Classes 390 | Sticky group capsules overlap cards and leave a gap | Major | Full-width hairline group row, sticky top = toolbar height | Apple Notes A6 |
| Requests | Redirects to /classes?view=review; nav "Talepler" but breadcrumb and H1 "Tüm dersler" | Minor | Title "İnceleme bekleyen", breadcrumb Talepler | — |
| Classes loading | Skeleton + "Yükleniyor…" + "Tümü 0" | Minor | One skeleton, no zero counts | — |
| Dashboard | The "26%" ticker sits about 10 px above the baseline (`EVID/crops/dashboard-hero-baseline.png`) | Major | `inline-flex items-baseline` | — |
| Dashboard | Heatmap 0 % cells are filled boxes the same weight as data (`EVID/crops/heatmap-zero-dark.png`) | Major | 0 / no data = `--fill-3` + dot pattern, numeral in label-3 | — |
| Dashboard | Building bars have no value labels; six equal 32 px glass cards; empty chart frames show axes | Major | Values at the bar end; one hero card + plain sections; hide axes when empty | Vercel H8 |
| Dashboard 390 | The tab bar covers the chart axis and KPI row | Major | `main` bottom padding = tab bar + safe-area + 16 | Apple Music A1 |
| Mobile tab bar | Icon-only except the active item; illegible "99+" badge; square search "orb"; content shows through; the tab set flips after hydration (`EVID/crops/mobile-tabbar-light.png`) | Major | Labels always; count after the label; 48 px circle search; `glass-chrome`; render after permissions resolve | Apple Music A1/A2, Fey H20 |
| Run report | 517/530 shown 3×; an orange ring gauge as hero; bars without values; Sparkles on "Sohbet"; heading order; at 390 the ring fills the first screen | Major | Headline sentence + KPI row only; drop the ring; values on bars; `MessageSquareText` | Vercel H7 |
| Runs list | Status as text and as a badge in each row | Major | Dot + word; plain numerals | Vercel H6 |
| Rooms | 87 uniform cards with an avatar repeating "A 101"; truncated "30 sınav…"; ambiguous sparkline letters "P S Ç P C"; filter panel wraps into 3 rows with 2 select styles (`EVID/crops/rooms-card-avatar.png`) | Major | Default view = table (code, building, seats, exam seats, tags, % use bar); cards optional and without the avatar; "Pzt Sal Çar Per Cum"; one toolbar | Airtable, Linear H4 |
| Room detail | The avatar duplicates the title; over capacity colour-only; breadcrumb "#1"; heatmap chips "N…" | Major | Glyph + word; breadcrumb = room code; min chip width | G4 |
| Bookings | "Free" in every empty cell (~100×); P10 cell text overflows the grid; toolbar wraps into 2 rows; the department select is ~470 px (`EVID/crops/bookings-free-noise-clip.png`) | Major | Blank free cell + hover "+" + aria-label "A 101 P1 boş"; ellipsis + tooltip; one Toolbar; select `w-auto min-w-48 max-w-72` | Notion Calendar |
| Bookings 390 | About 300 px of controls before content | Major | "Filtreler" bottom sheet + one segmented | Apple Maps A12 |
| Find room | Fixed 320–400 px form, a one-line results column at 1440; the "Sınav" switch is misaligned; native mm/dd/yyyy | Major | 360 px form + results skeleton / quick result; align the switch; DateField | Linear filter popover |
| My bookings | Tabs thumb misplaced (dark) and radius-mismatched (light) | Major | SegmentedControl fix | Apple A2 |
| Settings | Centred max-width column while every other page is left-aligned; the Model card holds only a disabled Save | Major | Same page frame (max-w-[960px], start-aligned); empty state "Önce bir API anahtarı ekleyin" + link | Perplexity H21 |
| Setup sub-nav | 13 tabs overflow ("Sign-", "Acce" clipped); /admin/rooms overflows horizontally at 390 | Major | A "Diğer ▾" overflow with edge fades, or a grouped sub-nav | Linear settings |
| Roles | Booking-limit fields truncate "Unlimitec"; "1 users"; dev keys in mono under each permission (`EVID/crops/roles-unlimited-truncated.png`) | Major | `w-[12ch]` field, placeholder "—", hint "Sınırsız"; ICU plural; keys in a tooltip | — |
| Audit log | Titles are raw keys in mono (`room_feature.create`) | Minor | Domain sentence "Derslik özelliği eklendi · #2"; key in details | A12 |
| Users | Email shown twice; two active sidebar items (Users + Setup) | Minor | Drop one; exact `isActive` for /admin/users | — |
| Shell | Two "Kurulum" items in TR (Onboarding + Setup); Sparkles on onboarding; sidebar fixed at 264 px down to 1024; the UI language flips TR/EN between routes in one session | Major | Rename Onboarding "Dosyalardan kur"; rail below 1280; one locale source (profile) before first paint | Linear sidebar |
| Login | Placeholder repeats the label; generic centred card; input boundary 1.15:1; hyphen spacing | Minor | Placeholder "ad.soyad@…"; `--border-control`; `scene` + GlassPanel regular | liquid-glass §16.3 |
| Onboarding | Centred dashed dropzone with generic copy; axe: unlabelled `input[multiple]`, nested-interactive; disabled "0 dosyayı analiz et" at 2.0:1 | Major | Left-aligned dropzone row + files table (phase19-intake R7); `<label for>`; hide the action until there are files | Attio R1, AWS R7 |
| Generate 1024 | The fixed bottom bar overlaps the sidebar footer; the rail wraps "Gelişmiş ayarları göster"; "Engel var" repeats "Kilitli derslik uygun değil" 3× without names; 16 px links | Major | Sticky inside main; name the class/room on each line; links min-h-6 | 7shifts R6 |
| Profile | "Loading…" above a form; 3-column password row; disabled ghost button | Minor | Single column, 360 px fields, primary button | Apple Settings |
| 404 | Centred "404" hero and pill button outside the shell; admin sent to "bookings"; console error | Minor | Inside the shell, left-aligned, role-aware home link | Linear H5 |
| Teacher /timetable | Direct URL shows no-access (fine); the crumb still says "Çizelge" | Minor | Hide it from ⌘K for teachers | — |
| Approvals | Positive: keycap legend + one-line empty state follow H5/H22 | — | Keep | Linear H5 |

## 4. Top 15 changes that remove the "AI-generated" feel
1. Restore focus rings everywhere (Linear).
2. Flatten the cards: default `plain`, radius 14×k with k = 1.25, glass only on floating chrome (Vercel H8, Things H1).
3. Remove every Sparkles icon; a distinct icon per admin section; one stroke weight (1.75).
4. One type scale: fluid titles, no arbitrary px, the same large title on every page.
5. One control-height and segmented system; nothing wraps; no mixed heights in a row (Apple A15).
6. The table column system for rooms, users, runs and classes (Airtable / Linear H4).
7. Timetable chips: never truncate codes; "+N çakışma"; auto-width rooms (Apple Calendar, Notion Calendar, Amie H9).
8. Delete duplicated data: the ring gauge, status text + badge, room avatars, email twice (Vercel H6/H7).
9. Brand: replace the Next.js favicon and the lucide tile (done in 4fe999c; swap in progress).
10. Empty and loading states: left-aligned, task-specific; skeletons instead of zeros; no centred 404 hero.
11. Field grammar: one field style with a 3:1 control border; a localised DateField; styled selects.
12. Dashboard truthfulness: baseline-aligned hero, a "no data" heatmap pattern, values on bars.
13. Mobile: a labelled tab bar on chrome material, bottom safe padding, filters in a sheet.
14. Copy: domain sentences instead of raw keys, ICU plurals, one locale per session.
15. Bookings grid noise: blank free cells with a hover "+"; the legend in a popover.

## 5. Acceptance checks (automatable)
Playwright `e2e/visual-quality.spec.ts`:
- Every tab stop over 25 presses on each route draws a ≥ 2 px solid outline, or a 3 px field halo, that is not clipped by an overflow ancestor.
- Control heights come from {24, 28, 32, 40} on fine pointers and are ≥ 44 on coarse pointers (390, `hasTouch`).
- Segmented controls never wrap (all children share one top value) and are ≤ 46 px tall.
- Font sizes are on the scale; card and glass radii are ≤ 24.
- No KPI overlap at 1024 and no horizontal overflow at 390 on any route.
- Column resize handles exist and their widths persist across a reload.
- axe color-contrast / target-size / label / nested-interactive return 0 violations on all routes × both themes.
- Field boundary contrast is ≥ 3:1.
- The favicon md5 is not the Next.js default (`2be26fb5639bc7a24d9c816567b0de5f`).
- Visual baselines with `toHaveScreenshot` (maxDiffPixelRatio 0.01, `[data-dynamic]` masked).

Static CI gates on `smartsched/frontend/src`:
- `outline-none` = 0, with `focus-ring.test.ts` SCOPE = all of components + app.
- `text-\[[0-9.]+px\]` = 0.
- `shadow-\[` outside `components/ui/**` = 0.
- `<button` outside `components/ui/**` = 0, or an allow-list.
- `Sparkles` = 0.
- `verify-contrast.mjs` extended with: dark `--fac-*` ink on tint, `--border-control` against the card (≥ 3), and label-4 not used for meaningful text.

Motion (skill §8): the segmented thumb rests inside its track (±1 px) 500 ms after load in both themes.

## 6. Brand as rendered (before 4fe999c)
- The favicon is the create-next-app "N" (md5 identical); there is no apple-touch-icon or SVG icon.
- The sidebar mark is a lucide `CalendarRange` in a 28 px tint tile (`rounded-[9px]`), which flips to a light-blue tile in dark mode, so its identity changes per theme. The wordmark is plain UI text.
- The login page centres the tile, title and card: the most template-like screen.
- The mobile top bar shows no mark.

## 7. Method notes and limits
- The Mobbin MCP was not available to the reviewer. Benchmarks use the references already collected (references.md A1–A16, H1–H26, F1–F3; all-classes.md refs #3 and #5; calendar.md; phase19-*.md).
- Judgements on data screens use the settled re-shots.
- The tnum-hyphen cause is a hypothesis.
- The cause of the dark tabs-thumb offset (layout projection timing) was not traced.
