# Design tokens — SmartSched admin panel

Owner: design-pro → frontend-engineer (design-system overhaul) · Status: **v3 (2026-10-15)** · Consumers: `smartsched/frontend/src/app/globals.css`, every component in `src/components/ui`.

**Read §A first.** §A is the sizing, focus and edge system shipped by the design-system overhaul of
2026-10-15 (`docs/review/2026-10-15-uiux-visual-review.md`). It is authoritative wherever it disagrees with
the v1 sections below (§0–§9 are kept as history) or with `v2/liquid-glass.md` §6–§7 (type sizes, radii).
Material and colour stay in `v2/liquid-glass.md`; motion stays in `v2/motion.md`.

## A. Design-system overhaul (2026-10-15)

### A.1 Focus (P0)

| Token / rule | Value | Use |
|---|---|---|
| unlayered `:focus-visible { --tw-outline-style: solid }` | last rule of globals.css, outside every `@layer` | makes any `focus-visible:outline-*` width paint, even after `outline-hidden` |
| `--focus-ring-width` | 2px | every tab stop |
| `--focus-ring-offset` | 2px | free-standing controls |
| `--focus-ring-offset-inset` | -2px | rows, cells and items inside scroll containers / grids (`focus-visible:-outline-offset-2`, utility `focus-ring-inset`) |
| fields | 2 px outline at offset 0 + 3 px soft halo | Input, Select, NativeSelect, DateField; InputGroup draws it on the group |

`outline-none` is banned in `src/` (gate: `npm run check:design`). Popup containers that are not tab stops
(menu, dialog, command list) and items with a highlight use `outline-hidden`.

### A.2 Edges and the control border

| Token | Light | Dark | Use |
|---|---|---|---|
| `--border-control` | `rgba(20,24,36,.48)` (3.15:1 worst on the card) | `rgba(255,255,255,.34)` (3.07:1 worst) | field / checkbox / switch-off boundary (WCAG 1.4.11) |
| `--edge-control` / utility `edge-control` | `inset 0 0 0 1px var(--border-control)` | same | every field surface |
| `--edge-hairline` / `edge-hairline` | `inset 0 0 0 1px var(--hairline)` | same | plain cards, separators around blocks |
| `--edge-hairline-b`, `--edge-hairline-t` / `edge-hairline-b` | inset 1 px bottom / top | same | rows, headers |
| `--edge-glass` | `= --glass-edge` (specular + hairline) | same | glass chrome only |

`shadow-[…]` arbitrary strings are allowed only inside `components/ui/**`; screens use `edge-*`,
`shadow-elev-*` or the glass utilities. `--hairline` is for separators only, never for a control boundary.

### A.3 Radius (`--corner-k`)

Base × `--corner-k`; k = **1** without squircles and **1.25** with `corner-shape: squircle` (Chromium 139+).

| Tailwind | Base | Use |
|---|---|---|
| `rounded-xs` | 4 | grid events, keycaps |
| `rounded-sm` | 6 | menu items, checkboxes |
| `rounded-md` | 8 | wells, inner rows |
| `rounded-lg` | 12 | inputs, tooltips, select triggers (rect controls) |
| `rounded-xl` | 14 | **page cards** (Card default) |
| `rounded-2xl` | 18 | sidebar, sheets |
| `rounded-3xl` | 24 | dialogs, bottom sheets, palette |
| `rounded-4xl` | 24 | deprecated alias of 3xl |
| `rounded-full` | capsule | pill buttons, chips, segmented controls, switches |

Nesting: inner radius = outer − padding. No card or glass panel exceeds 24 × k (e2e check).

### A.4 Type

Fluid titles (390 → 1440 px viewport) and fixed data sizes. Use the `type-*` utilities, never `text-[Npx]`
(gate: 0 outside the allow-list). `cn` (tailwind-merge semantics) treats an unknown `text-x` as a colour,
which is why the scale is `type-*`.

| Utility | Size | Line | Weight |
|---|---|---|---|
| `type-large-title` | `clamp(1.75rem, 1.611rem + .571vw, 2.125rem)` (28 → 34) | 1.18 | 700 — every `PageHeader` |
| `type-title-1` | `clamp(1.375rem, 1.236rem + .571vw, 1.75rem)` (22 → 28) | 1.21 | 700 |
| `type-title-2` | `clamp(1.125rem, 1.032rem + .381vw, 1.375rem)` (18 → 22) | 1.27 | 650 |
| `type-title-3` | `clamp(1rem, .954rem + .19vw, 1.125rem)` (16 → 18) | 1.33 | 600 |
| `type-kpi` | 28 / 32, tabular | — | 650 — KPI numerals (fixed so they align) |
| `type-headline` / `type-body` | 14 / 20 | — | 600 / 400 |
| `type-callout` | 13 / 18 | — | 400 — dense UI, table cells |
| `type-footnote` | 12 / 16 | — | 400 — metadata |
| `type-caption` | 11 / 14 | — | 500 — axis labels, badges; the floor |
| `text-2xs` | 10 / 12 | — | week zoom only |

Explicit `font-*` / `leading-*` utilities override the weight / line of a `type-*` (they sort later).
`tabular-nums` is no longer global (it widened hyphens: "Güz 2026 - 27"); it applies to `td`, `th`, `time`,
`kbd`, `[data-numeric]`, `[role=gridcell]`, `type-kpi` and the `tnum` utility.

### A.5 Control heights

| Token | Fine pointer | `pointer: coarse` | Used by |
|---|---|---|---|
| `--control-h-xs` | 24 | 32 | Button xs, IconButton xs, Chip sm |
| `--control-h-sm` | 28 | 36 | Button sm, Segmented sm, toolbar fields |
| `--control-h-md` | 32 | 44 | Button md (default), Input, Select, NativeSelect, DateField, Segmented md |
| `--control-h-lg` | 40 | 48 | Button lg, mobile primary actions |
| `--control-h` | = md | = md | fields read this |

Horizontal padding `calc(var(--control-h) * .4375)`; gap 6 (md/lg) / 4 (sm/xs); icon 16 (md/lg) / 14 (sm/xs).
Nothing in one row mixes heights (Apple A15, Weather scrubber; Arcade H19).

### A.6 Spacing, density, gutters

- 4 px base; steps 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, 64.
- `--pad-card` 16 / `--pad-card-sm` 12; `--pad-toolbar` 6; `--page-gutter: clamp(16px, 2.2vw, 32px)`.
- Rows: `--row-h` 44 (standard), 32 under `data-density="compact"`, 56 under `data-density="comfortable"`;
  cells `--cell-py`/`--cell-px` 8 × 12 (standard), 4 × 8 (compact).

### A.7 Contrast additions (gated by `docs/design/v2/verify-contrast.mjs`)

- `--border-control` against the card ≥ 3:1 in both themes (worst-case composite).
- Timetable faculty ink (`--fac-1..8-ink`, components/timetable/calendar.css) ≥ 4.5:1 on its fill and under
  the conflict tint; dark inks were lifted (e.g. aqua `#49b28e → #50b593`, 5.23:1) and chip line 2 lost its
  0.8 opacity (which made it 3.78:1 at 11 px).
- `text-label-4` only on `aria-hidden` / `disabled:` / `placeholder:` (source scan in the same script).

### A.9 Primitives (`src/components/ui`)

| Primitive | API | Notes |
|---|---|---|
| `Button` | `size xs \| sm \| md \| lg` (default md), `shape pill \| rect` (default pill), `variant` unchanged | heights from `--control-h-*`; `rect` (radius lg) for buttons that sit in a row with fields; xs/sm get a 44 × 44 hit area on coarse pointers. `size="default"` and `icon*` are deprecated aliases |
| `IconButton` | `label` (required), `size`, `variant` (default ghost), `shape` | `label` → `aria-label` + `title` |
| `Input` | `fieldSize sm \| md \| lg` | `fieldSurface` + `--edge-control`, 16 px text on touch phones |
| `SelectTrigger` | `size sm \| md` | same surface and heights |
| `NativeSelect` (`ui/native-select.tsx`; `common/native-select.tsx` re-exports) | `size`, `className` (wrapper), `selectClassName` | chevron centred (`inset-y-0 my-auto`) |
| `SegmentedControl` | `options[{value,label,icon,controls,disabled,text,title,testId}]`, `value` (`null` = none), `onValueChange`, `size sm \| md \| lg`, `fill`, `semantics tablist \| radiogroup`, `collapse` | the only segmented control. nowrap equal columns, CSS thumb at rest (transform-only on `--spring-glass-morph`), falls back to a NativeSelect under `@container` when narrower than its natural width. `SegmentedGlass` is a deprecated alias; `beui/tabs` and `studio/segmented` were deleted; `ui/tabs` default variant shares the track and thumb |
| `DateField` | `value` / `onChange` ISO, `min`, `max`, `size`, `required` | `Intl.DateTimeFormat(locale)` (tr `15.10.2026`), typed entry, Popover month grid (APG keys) |
| `Card` | `variant plain (default) \| glass \| ghost \| inset`, `size` | plain = opaque surface + hairline, radius xl; glass only for floating chrome / one hero |
| `Skeleton`, `LoadingValue` | `value` (`undefined` = loading), `format`, `chars`, `empty` | never 0 while loading; one loading signal per region |
| `BusyButton` (`ui/busy-label.tsx`) | `busy`, `busyLabel` | 150 ms delay before the busy glyph |
| `DataTable` (`ui/data-table/`) | see §A.10 | column system |

### A.10 Table column system (`src/components/ui/data-table/`)

- `column-system.ts` (pure, unit-tested): `ColumnSpec {id, header, minSize, maxSize, size: number | "auto",
  grow, align, pin: "left", hideable, priority 1–5, text(row), extra, font}`; `autoWidth` measures the header and
  the first 200 rows with `canvas.measureText` in the cell font, clamps to [min, max] and adds the cell padding;
  `layoutColumns` hides by priority (5 first; never priority 1 or pinned) while the minimums do not fit, gives the
  slack to `grow` columns (never to user-sized ones), pins left columns first with sticky offsets, and returns ONE
  `grid-template-columns` string.
- `use-column-layout.ts`: per-user prefs `{order, sizing, visibility, pinning, density}` in
  `localStorage["smartsched.table.<tableId>.<userId>"]` (useSyncExternalStore, so SSR and hydration agree),
  container width from a ResizeObserver, `squeeze: false` for tables that should scroll instead (classes).
- `parts.tsx`: `ColumnResizeHandle` (8 px hit area, 1 px `--border-control` line on hover/focus,
  `role="separator" aria-orientation="vertical" aria-valuenow`, ←/→ 8 px, Shift 32 px, Home/Enter or
  double-click = auto-fit, pointer drag 1:1), `ColumnsMenu` ("Görünüm › Sütunlar": toggles, dnd-kit reorder with
  keyboard sensor, density, reset), `SqueezedChip` ("+3 sütun").
- `data-table.tsx`: `DataTable` (TanStack sorting + Virtual above 80 rows; header and body rows are
  `grid grid-cols-(--cols)`; pinned cells get an inset hairline edge once scrolled; rows on `--row-h`;
  card-list mode under 600 px containers) and `StatusDot` (Vercel H6: 8 px dot + word).
- Adopted by: `/runs` (dot + word status, plain "517 / 530" numerals, no ring gauge), `/rooms` (default view =
  table), `/classes` (measured widths, resize handles, persisted sizing; the page keeps its own Görünüm menu
  for order and visibility).

### A.8 References (Mobbin, collected in `v2/references.md`; no Mobbin tool in this session)

Linear H4 (32 px rows, view switcher) and H5 (focus ring, left-aligned empty states); Vercel H6 (status = 8 px
dot + word), H7 (key-value grid), H8 (heterogeneous cards, one hero); Apple Weather A15 and Arcade H19 (small
segmented with a lit thumb, one height per row); Apple Music A1/A2 (labelled tab bar, chrome material);
Apple Notes A6/A7 (continuous corners, plain counts); Amie H9 and Notion H12/H13 (calendar chips, today
marker, timeline row grammar); Things H1 (type does the hierarchy). Airtable grid and Height column menu are
cited by the review (all-classes.md §5) for the column system.

## 0. Rules that every surface follows

1. **Colour is never the only cue.** Every status gets an icon + a text label (or a hatch pattern for pre-occupied cells). A planner with deuteranopia must be able to tell locked from feasible from TIP.
2. **All text pairs ≥ 4.5:1** (WCAG AA), UI component boundaries (focus ring, toggles, chart marks against surface) ≥ 3:1. Verified ratios are in §2.4; recompute with the script in §8 when a value changes.
3. **Motion ≤ 300 ms, purposeful, and removable.** `prefers-reduced-motion: reduce` collapses every transform/layout animation to 0 ms and keeps only opacity fades ≤ 100 ms.
4. **Light and dark are both designed**, not inverted. Dark uses lighter tints on a near-black blue surface; shadows are replaced by surface steps + borders.
5. **Dark mode mechanism**: `.dark` class on `<html>` (set by `next-themes`, `attribute="class"`), with an OS fallback so SSR'd first paint is right. See §1.

## 1. Mechanism (globals.css skeleton)

```css
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));

:root { color-scheme: light; /* §2 light values */ }

/* OS preference wins only when the user has not chosen explicitly */
@media (prefers-color-scheme: dark) {
  :root:where(:not(.light):not([data-theme="light"])) { color-scheme: dark; /* §2 dark values */ }
}
.dark, :root[data-theme="dark"] { color-scheme: dark; /* §2 dark values */ }
/* The dark block appears twice (media query + class). Keep it in one place by authoring it once in
   `tokens.dark.css` and importing it under both selectors with Tailwind 4's `@import … layer(base)`,
   or generate both from a single JS object in `src/styles/tokens.ts` at build time. */

@theme inline {
  --color-background: var(--bg);
  --color-foreground: var(--fg);
  --color-card: var(--surface);
  --color-card-foreground: var(--fg);
  --color-popover: var(--surface-raised);
  --color-popover-foreground: var(--fg);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-fg);
  --color-secondary: var(--surface-2);
  --color-secondary-foreground: var(--fg);
  --color-muted: var(--surface-2);
  --color-muted-foreground: var(--fg-muted);
  --color-accent: var(--surface-2);
  --color-accent-foreground: var(--fg);
  --color-destructive: var(--danger-solid);
  --color-border: var(--border);
  --color-input: var(--border-strong);
  --color-ring: var(--focus);
  /* status + domain colours are exposed as color-status-* so `bg-status-locked` works */
  --color-status-feasible: var(--status-feasible-bg);
  --color-status-feasible-fg: var(--status-feasible-fg);
  /* …repeat for infeasible, warning, locked, preoccupied, tip, pclab, conflict */
  --radius-xs: var(--radius-xs); --radius-sm: var(--radius-sm); --radius-md: var(--radius-md);
  --radius-lg: var(--radius-lg); --radius-xl: var(--radius-xl);
  --ease-out: var(--ease-out); --ease-in-out: var(--ease-in-out); --ease-emphasized: var(--ease-emphasized);
  --font-sans: var(--font-inter); --font-mono: var(--font-jetbrains);
}
```

shadcn's generated tokens (`--primary`, `--muted`, …) are *aliases* of ours, so `npx shadcn@latest add …` components need no edits. beUI's `/theme.css` must **not** be pasted; its `--primary #0285f7` and glass tokens are replaced by this file (beUI components only read the shadcn names, which we provide).

## 2. Colour

### 2.1 Neutral + brand (light / dark)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#FFFFFF` | `#0B1220` | page background |
| `--surface` | `#F8FAFC` | `#111827` | cards, sidebar, grid header |
| `--surface-2` | `#F1F5F9` | `#1F2937` | muted fills, table stripes, empty grid cells |
| `--surface-raised` | `#FFFFFF` | `#1F2937` | popovers, sheets, dialogs |
| `--border` | `#E2E8F0` | `#273449` | hairlines (decorative, not a text contrast pair) |
| `--border-strong` | `#94A3B8` | `#475569` | inputs, resizable handles, grid period lines — 2.5:1, so interactive controls add a focus ring, never rely on border alone |
| `--fg` | `#0F172A` | `#F1F5F9` | primary text (17.9:1 / 17.1:1) |
| `--fg-muted` | `#475569` | `#A1AEC2` | secondary text (7.6:1 / 8.3:1) |
| `--fg-subtle` | `#64748B` | `#8B98AD` | captions, axis labels — AA on `--bg` (4.8:1) and dark `--surface-2` (5.0:1); **not** on light `--surface-2` (4.3:1) — use `--fg-muted` there |
| `--primary` | `#2563EB` | `#60A5FA` | buttons, links, selection, heatmap hue (5.2:1 / 7.4:1) |
| `--primary-hover` | `#1D4ED8` | `#93C5FD` | |
| `--primary-fg` | `#FFFFFF` | `#0B1220` | text on primary (5.2:1 / 7.4:1) |
| `--primary-tint` | `#EFF6FF` | `rgba(96,165,250,.14)` | selected row, drop-target OK, today column |
| `--focus` | `#2563EB` | `#93C5FD` | 2 px ring, 2 px offset (5.2:1 / 10.4:1 against bg) |
| `--overlay` | `rgba(15,23,42,.45)` | `rgba(0,0,0,.6)` | dialog scrim |

### 2.2 Status colours (the six domain states + two transient ones)

Each state has `-fg` (text/icon), `-bg` (cell/badge fill), `-border` (1 px, left-stripe 3 px on grid events), `-solid` (filled badge / progress). The **icon** column is mandatory wherever the colour appears.

| State | Meaning in SmartSched | Icon (lucide) | Light fg / bg / border | Dark fg / bg / border |
|---|---|---|---|---|
| `feasible` | hard 100/100, assignment valid | `check-circle-2` | `#15803D` / `#DCFCE7` / `#86EFAC` | `#4ADE80` / `#14532D` / `#22C55E` |
| `infeasible` | hard violation, double booking, capacity breach | `x-octagon` | `#B91C1C` / `#FEE2E2` / `#FCA5A5` | `#FCA5A5` / `#7F1D1D` / `#EF4444` |
| `warning` | soft-constraint violation (wrong building, 20 in 156 seats) | `alert-triangle` | `#B45309` / `#FEF3C7` / `#FCD34D` | `#FCD34D` / `#78350F` / `#F59E0B` |
| `locked` | pinned by the planner; solver will not move it | `lock` | `#4338CA` / `#E0E7FF` / `#A5B4FC` | `#C7D2FE` / `#312E81` / `#818CF8` |
| `preoccupied` | imported block (HAZIRLIK, UZEM, ETKİNLİK, club) — not solvable | `ban` + 45° hatch | `#3F3F46` / `#F4F4F5` hatch `#E4E4E7` / `#D4D4D8` | `#D4D4D8` / `#27272A` hatch `#3F3F46` / `#52525B` |
| `tip` | Faculty of Medicine room (A 201–203), needs release | `stethoscope` | `#9D174D` / `#FCE7F3` / `#F9A8D4` | `#FBCFE8` / `#831843` / `#EC4899` |
| `pclab` | computer lab (A 103/104/105, B 207, B BİLGİ LAB) | `monitor` | `#0E7490` / `#CFFAFE` / `#67E8F9` | `#A5F3FC` / `#164E63` / `#22D3EE` |
| `conflict` (transient) | live drag target collides | `x-octagon`, 2 px dashed outline, pulse | `--infeasible-*` + `outline: 2px dashed #DC2626` | same with `#F87171` |
| `drop-ok` (transient) | live drag target valid | `check` | `--primary-tint` + `outline: 2px solid #2563EB` | tint + `#60A5FA` |

Solid fills (for badges with white text / progress bars): `--feasible-solid #16A34A` (white text 3.3:1 → use only on ≥ 18.5 px bold or with the dark `--fg` text, 8.3:1 on `#F59E0B` for warning), `--infeasible-solid #DC2626` (white 4.8:1 ✓), `--warning-solid #F59E0B` (use `--fg` text, 8.3:1 ✓), `--locked-solid #4F46E5`, `--tip-solid #DB2777`, `--pclab-solid #0891B2`. Rule: **solid badges carry dark text on warning and feasible, white text on infeasible/locked/tip/pclab.**

Hatch for `preoccupied`:
```css
background: repeating-linear-gradient(45deg, var(--status-preoccupied-bg) 0 6px, var(--status-preoccupied-hatch) 6px 8px);
```
`forced-colors: active` → drop hatch, keep `border: 1px dashed CanvasText` and the icon.

### 2.3 Categorical (faculty / programme) colours

Used for the **left 3 px stripe + 12 % tint** on grid events and for series in dashboard charts. We adopt the validated eight-slot palette from the `dataviz` skill (`references/palette.md`), which passes CVD separation on adjacent pairs in both modes; do not reorder or add hues. Assignment is **fixed per faculty in `settings`**, never by index in the current result set.

| Slot | Light | Dark | Default faculty |
|---|---|---|---|
| 1 blue | `#2a78d6` | `#3987e5` | Mühendislik |
| 2 orange | `#eb6834` | `#d95926` | Tıp (TIP rooms keep their own status colour; this is the *series* colour) |
| 3 aqua | `#1baf7a` | `#199e70` | Sağlık Bilimleri |
| 4 yellow | `#eda100` | `#c98500` | İktisadi ve İdari Bilimler |
| 5 magenta | `#e87ba4` | `#d55181` | Hukuk |
| 6 green | `#008300` | `#008300` | Fen-Edebiyat |
| 7 violet | `#4a3aa7` | `#9085e9` | Eğitim |
| 8 red | `#e34948` | `#e66767` | Diğer / Other (overflow bucket) |

A 9th faculty folds into slot 8 "Diğer"; events always show the course code as text so the stripe is secondary.

### 2.4 Verified contrast (WCAG 2.x relative luminance, computed 2026-10-07)

| Pair | Ratio | Grade |
|---|---|---|
| light `--fg` on `--bg` | 17.85 | AAA |
| light `--fg-muted` on `--bg` | 7.58 | AAA |
| light `--fg-subtle` on `--bg` | 4.76 | AA |
| light `--primary` on `--bg` / white on `--primary` | 5.17 | AA |
| light feasible fg/bg · infeasible · warning · locked · preoccupied · tip · pclab | 4.57 · 5.30 · 4.51 · 6.41 · 9.50 · 6.71 · 4.79 | AA (preoccupied AAA) |
| dark `--fg` on `--bg` · `--fg-muted` on `--surface` | 17.09 · 7.90 | AAA |
| dark `--primary` on `--bg` · `--focus` on `--bg` | 7.36 · 10.38 | AAA |
| dark feasible · infeasible · warning · locked · preoccupied · tip · pclab (fg on tint) | 5.23 · 5.28 · 6.29 · 7.66 · 10.08 · 6.98 · 7.30 | AA/AAA |
| heatmap steps with text (see §2.5) | 16.4 / 12.6 / 7.0 / 5.2 / 10.4 | AA+ |

Known sub-3:1 values: `--border` (1.2:1) and `--border-strong` (2.6 / 2.5:1). They are decorative; every interactive control also has a visible focus ring and a ≥ 3:1 fill or icon.

### 2.5 Sequential scale (utilisation heatmap, capacity-fit bars)

Single hue = `--primary`. Five steps, light: `#EFF6FF → #BFDBFE → #60A5FA → #2563EB → #1E3A8A` (0 %, 1–25, 26–50, 51–75, 76–100 occupied). Text on steps 1–3 is `--fg`, on 4–5 `#FFFFFF`. Dark: `#172554 → #1E3A8A → #2563EB → #60A5FA → #BFDBFE` with `--fg` on 1–3, `#0B1220` on 4–5. "No data" is `--surface-2` with a dot pattern, never step 1.

Diverging (run-vs-run comparison, "better/worse"): `--feasible-solid` ↔ `--surface-2` (neutral mid) ↔ `--infeasible-solid`.

## 3. Typography

Font: **Inter** (variable, `next/font/google`, `display: swap`) for UI; **JetBrains Mono** for course codes, room codes, run ids, and timestamps in tables. (v3: `tabular-nums` is no longer global; see §A.4.)

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `--text-2xs` | 10 / 12 | 500 | week-view mini labels only (never body copy) |
| `--text-xs` | 11 / 14 | 500 | grid cell second line, badges, axis labels |
| `--text-sm` | 12 / 16 | 400/600 | grid cell course code (600), table cells, captions |
| `--text-base` | 14 / 20 | 400 | body, inputs, menu items |
| `--text-md` | 16 / 24 | 500 | card titles, sheet titles |
| `--text-lg` | 18 / 26 | 600 | section headings |
| `--text-xl` | 20 / 28 | 600 | page title (mobile) |
| `--text-2xl` | 24 / 32 | 600 | page title (desktop) |
| `--text-3xl` | 30 / 36 | 700 | KPI numbers |
| `--text-4xl` | 36 / 40 | 700 | hard-score hero badge |

Letter-spacing: `-0.01em` from `--text-xl` up; `+0.02em` uppercase labels at `--text-xs`. Minimum interactive text 12 px; minimum text anywhere 10 px (week zoom only, with tooltip duplicate).

## 4. Spacing, sizing, radius, borders

- Base unit 4 px. Scale: `0, 1=4, 2=8, 3=12, 4=16, 5=20, 6=24, 8=32, 10=40, 12=48, 16=64, 20=80`. Page gutter: 16 px (≤ 768), 24 px (≤ 1280), 32 px (> 1280). Max content width 1600 px on the dashboard; the timetable is full-bleed.
- Touch target minimum 44 × 44 px on touch devices; pointer-fine minimum 32 × 28 px (shadcn `size="sm"`).
- Radius: `--radius-xs 4` (grid events, chips), `--radius-sm 6` (inputs, buttons), `--radius-md 8` (cards, popovers), `--radius-lg 12` (sheets, dialogs), `--radius-xl 16` (KPI tiles, hero badge), `--radius-full 9999`.
- Border width: 1 px default; 2 px focus/selection; 3 px event left stripe.
- Grid-specific: `--period-row-h` 40 px (comfortable) / 28 px (compact); `--room-col-w` 128 px (day zoom) / 7 × 18 × 6 px = 756 px per room-row (week zoom); `--time-col-w` 72 px; `--grid-header-h` 56 px; `--building-band-h` 24 px.

## 5. Elevation

| Level | Light | Dark | Use |
|---|---|---|---|
| 0 | none, `1px solid var(--border)` | same | cards on `--bg`, grid |
| 1 | `0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.10)` | `0 0 0 1px #273449` | hovered card, sticky header shadow when scrolled |
| 2 | `0 4px 12px rgba(15,23,42,.10), 0 1px 3px rgba(15,23,42,.08)` | `0 0 0 1px #334155, 0 8px 24px rgba(0,0,0,.5)` | popover, dropdown, drag ghost |
| 3 | `0 16px 40px rgba(15,23,42,.18)` | `0 0 0 1px #334155, 0 24px 48px rgba(0,0,0,.6)` | sheet, dialog, command palette |

Drag ghost adds `scale(1.02)` and elevation 2; drop removes both over `--dur-base`.

## 6. Motion

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 0 ms | state colour swaps on grid cells (avoid lag while dragging) |
| `--dur-fast` | 120 ms | hover, focus ring, tooltip, chip toggle |
| `--dur-base` | 180 ms | popover/dropdown open, tab indicator slide, badge count change |
| `--dur-slow` | 240 ms | sheet/drawer, dialog, page section stagger (each item ≤ 40 ms apart, max 6 items) |
| `--dur-max` | 300 ms | **ceiling**; week switch cross-fade, score ring draw |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | things entering |
| `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | things moving on screen |
| `--ease-emphasized` | `cubic-bezier(0.2, 0, 0, 1)` | sheets, dialogs |
| `--spring-drop` | motion `{ type: "spring", stiffness: 520, damping: 42, mass: 0.8 }` (settles ≈ 240 ms) | event settling into cell after drop, sortable reorder |
| `--spring-count` | `{ stiffness: 170, damping: 26 }` | number ticker on KPI / scores |

Reduced motion (global, in `globals.css`):
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
}
```
plus `useReducedMotion()` from `motion/react` in JS: springs → `{ duration: 0 }`, number tickers → render final value, the `conflict` pulse → static dashed outline, skeleton shimmer → static.

**Reconciliation with sibling specs** (`navigation-shell.md` §7, `requests-inbox.md`, `generate-and-chat.md` were written in parallel): this file is the source of truth. Mapping: their `--dur-slow: 300ms` → use `--dur-max`; their `--ease-out: cubic-bezier(.2,.8,.2,1)` → `--ease-out` here (visually equivalent, slightly less overshoot); nav-indicator / segmented spring `{500, 40}` → `--spring-drop`; sheet / kanban spring `{300, 30}` (settles ≈ 300 ms) is accepted as `--spring-sheet` and must not exceed the 300 ms ceiling; the 30 ms × ≤ 8 chip stagger (≤ 240 ms) is within the rule in this table.

Never animate: grid scroll position (except `scrollIntoView({behavior:"smooth"})` on keyboard navigation when motion allowed), table row reorders in the runs list, anything > 300 ms.

## 7. Z-index, layers, misc

`--z-grid-sticky 10`, `--z-grid-drag 20`, `--z-sticky-bar 30`, `--z-popover 40`, `--z-sheet 50`, `--z-dialog 60`, `--z-toast 70`, `--z-command 80`.
Icons: lucide-react, 16 px in text, 20 px in buttons, 14 px in badges, `stroke-width 1.75`.
Density toggle (`data-density="compact"`) halves vertical paddings in tables and the grid; persisted in `localStorage`.
Locale: `tr-TR` default, `en` fallback; day names come from `Intl`; times are `HH:mm`, 24 h, never AM/PM.

## 8. Verification script

```bash
python3 - <<'PY'
def lum(h):
    h=h.lstrip('#'); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    la,lb=lum(a),lum(b); return (max(la,lb)+0.05)/(min(la,lb)+0.05)
print(round(cr("#15803D","#DCFCE7"),2))
PY
```
Categorical palette: `node <dataviz-skill>/scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a,#eda100,#e87ba4,#008300,#4a3aa7,#e34948" --mode light` and `--mode dark --surface "#0B1220"` — add to `make check` for the frontend once `scripts/` exists.

## 9. Component sources that consume these tokens

| Source | Licence | What we take | Install |
|---|---|---|---|
| shadcn/ui (`ui.shadcn.com`) | MIT | all primitives (Button, Badge, Card, Tabs, Sheet, Dialog, Popover, Tooltip, Command, Table, Select, Toggle Group, Skeleton, Progress, Accordion, Chart wrapper) | `npx shadcn@latest add …` into `src/components/ui` |
| Radix UI (`radix-ui.com/primitives`) | MIT | underlying a11y primitives (shadcn depends on them) | transitive |
| @dnd-kit/core + /modifiers + /utilities (`dndkit.com`) | MIT | drag-drop in the grid | `npm i @dnd-kit/core @dnd-kit/modifiers @dnd-kit/utilities` |
| motion (`motion.dev`) | MIT | springs, `AnimatePresence`, `useReducedMotion` | `npm i motion` |
| beUI (`beui.dev`, public library) | MIT per the site FAQ; verify `LICENSE` in the repo on first import and record it in `src/components/ui/SOURCES.md` | Status Bar, Liquidity Heatmap (as a11y pattern reference), Number Animation, Animated Toast Stack, Sortable List | `npx shadcn@latest add @beui/<name>` then re-point its tokens to ours |
| evilcharts (`evilcharts.com`, github legions-developer/evilcharts) | MIT (LICENSE in repo) | Bar / Area / Line / Pie / Radar on Recharts, shadcn-styled | `npx shadcn@latest add @evilcharts/recharts-<chart>` |
| beautifului.dev | MIT (© 2026 Shane Levine, `/license`) | Task Rows, Approval Card, Diff Table, Filter Table, Insight Cards (copy-paste) | copy source, keep licence header |
| Kinetics (`kinetics.colorion.co`) | **unverified** — third-party listings say MIT but the repo (`github.com/ckissi/kinetics`) shows no LICENSE file at time of writing | Progress Ring, Number Counter, Toast Overshoot, Success Check — **as motion references only**; re-implement with `motion` and our tokens | none |
| transitions.dev | custom licence: free + Pro transitions may be used in commercial products, not MIT, Pro is paid; `transitions-dev` CLI is MIT | "Tabs sliding", "Panel reveal", "Error state shake", "Success check" — references; the `npx transitions-agent` scorer may be used in CI | none for components |
| kobra.systems | free tier **personal use only**; Individual licence $199 for commercial | reference only (Magnetic Dropzone, CRM Table, Grouped Table layouts) unless the user buys a licence | none |
| reverseui.com | 19 free components with commercial use allowed, no OSS licence text; paid tiers | reference only (Timeline Progress, Logs Explorer, Award Badge); do not copy code without the licence file | none |
| Astryx (`astryx.atmeta.com`, github facebook/astryx) | MIT | StyleX-based, React 19 — **not adopted** (second styling runtime next to Tailwind); its semantic token naming and Badge/status patterns are referenced | none |

Every imported file gets a header comment `// Source: <url> — Licence: <SPDX> — Modified: yes/no` and a row in `src/components/ui/SOURCES.md` (frontend-engineer owns that file).
