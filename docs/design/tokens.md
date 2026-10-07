# Design tokens — SmartSched admin panel

Owner: design-pro · Status: v1 (2026-10-07) · Consumers: `smartsched/frontend/src/app/globals.css`, every component in `src/components/ui`.

The admin panel is built on **Next.js 15 + Tailwind 4 + shadcn/ui (Radix) + motion + @dnd-kit** (see `docs/ARCHITECTURE.md` "Frontend"). Tokens are plain CSS custom properties on `:root`, mapped into Tailwind with `@theme inline`, so every component (ours, shadcn, beUI, evilcharts) reads the same variables. Nothing below is brand-specific to a vendor; it is the one system the four surfaces in `docs/design/*.md` share.

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

Font: **Inter** (variable, `next/font/google`, `display: swap`) for UI; **JetBrains Mono** for course codes, room codes, run ids, and timestamps in tables (`font-variant-numeric: tabular-nums` is set globally on `html` so period times and capacities align without mono).

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
