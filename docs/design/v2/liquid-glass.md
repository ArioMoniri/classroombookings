# SmartSched v2: Liquid Glass visual system

Owner: design-pro (liquid-glass v2) · Status: v2.0 (2026-10-08) · Supersedes: `docs/design/tokens.md` §2–§5
(colour, type, radius, elevation). The v1 motion rules in tokens.md §6 are superseded by
[`motion.md`](motion.md), which **owns motion**. This file owns **material, colour, type, shape and
fallbacks**. Research is in [`references.md`](references.md) (46 Mobbin screens and flows).

Implementation:

- `smartsched/frontend/src/app/globals.css`: every token and utility below, parsed by the contrast gate
- `smartsched/frontend/src/components/ui/**`: the primitives (§11) and the imported components (§12)
- `smartsched/frontend/src/lib/motion.ts`: motion tokens (verbatim copy of the motion_designer skill)
- `docs/design/v2/verify-contrast.mjs`: the WCAG gate (§10)

The target is macOS Tahoe / iOS 26 **Liquid Glass**, adapted for a dense web admin used all day. Glass is
reserved for the **chrome that floats** (sidebar, toolbars, popovers, sheets, palette, toasts) and for
content cards that sit directly on the scene. The data itself (grid cells, table rows, chart marks) stays
on calm, legible surfaces.

## 0. Rules (read these first)

| # | Rule |
|---|---|
| **G1** | **Choose the material by what sits behind it.** `ultra-thin`, `thin` and `regular` are allowed **only over the scene** (§3). Anything that floats over scrolling **content** uses `thick` or `chrome`. The contrast gate enforces this: the scene-only materials are not checked against content. |
| **G2** | **No glass on glass.** Inside a glass surface, use fills (`bg-fill-1/2/3`), hairlines or `--mat-thick` *colour* without `backdrop-filter`. This covers segmented thumbs, sidebar pills, inner cards, inputs and keycaps. |
| **G3** | **One tint.** `--accent` appears on the primary action, the active glyph, links, focus and selection, and nowhere else. No second brand colour, no gradients on text. |
| **G4** | **Status = glyph + word**, on a quiet translucent tint. Colour is never the only cue (tokens.md rule 1 still holds). |
| **G5** | **Depth comes from light.** A 1 px specular top edge, a 1 px hairline, and a soft, wide, low-alpha ambient shadow. Never use heavy drop shadows or dark borders. |
| **G6** | **Never animate `opacity`, `filter`, `mask` or `will-change` on an ancestor of a glass element**, and never `filter` on the glass element itself. Doing so strips or janks the blur in Chromium (motion.md §2, "backdrop-root rule"). Fade the glass element itself, or a veil inside it. |
| **G7** | **≤ 3 live `backdrop-filter` surfaces animating at once**, blur ≤ 40 px. The grid never gets per-cell glass. |

## 1. Mechanism

- Tokens are CSS custom properties in two parseable blocks: `/* @tokens light */ :root {…}` and
  `/* @tokens dark */ .dark {…}`, plus `/* @tokens accents */` presets. The dark theme uses the `.dark`
  class on `<html>` (next-themes), unchanged from v1.
- `@theme inline` maps them to Tailwind, so `bg-fill-2`, `text-label-2`, `bg-tint`, `text-tint-text`,
  `bg-status-feasible`, `rounded-2xl` and so on work everywhere.
- **Materials are `@utility` classes**: `glass-ultra-thin`, `glass-thin`, `glass-regular`, `glass-thick`,
  `glass-chrome`, plus `glass-edge`, `scene`, `hairline-t`, `hairline-b` and `focus-ring`. Because they are
  utilities, variants work (`md:glass-chrome`, `hover:…`).
- **Type styles are `type-*` utilities**, not `text-*`. `tailwind-merge` (inside `cn`) reads any unknown
  `text-x` as a colour and would silently drop it when combined with `text-label-1`.
- **v1 names are kept as aliases** (`--bg`, `--surface`, `--fg-muted`, `--primary`, `--primary-tint`,
  `--shadow-1..3`, `--status-*`, `.shadow-elev-*`, `.hatch-preoccupied`) and re-valued, so every page
  compiles and immediately picks up v2. shadcn names (`--card`, `--muted`, `--popover`…) alias those.

## 2. Materials

Each material = `background: grain, sheen, tint` + `backdrop-filter` + `box-shadow: edge (+ ambient)`.

| Level | Light tint | Dark tint | backdrop-filter | Ambient | Solid fallback (L / D) | Use | Allowed over |
|---|---|---|---|---|---|---|---|
| `ultra-thin` | `rgba(255,255,255,.36)` | `rgba(36,37,43,.38)` | `blur(10px) saturate(160%)` | none | `#f3f4f7` / `#17181d` | hover wells, large decorative bands | scene |
| `thin` | `rgba(255,255,255,.50)` | `rgba(34,35,41,.52)` | `blur(16px) saturate(170%)` | none | `#f6f7f9` / `#1a1b20` | secondary panels, filter bars on the scene | scene |
| `regular` | `rgba(255,255,255,.64)` | `rgba(30,31,37,.66)` | `blur(24px) saturate(180%)` | `--ambient-1` | `#fafbfc` / `#1d1e23` | **cards** (Card default), DiffTable, TaskRows | scene |
| `thick` | `rgba(255,255,255,.86)` | `rgba(30,31,36,.88)` | `blur(32px) saturate(180%)` | `--ambient-3` | `#ffffff` / `#222328` | popovers, menus, tooltips, dialogs, toasts, composer | scene + content |
| `chrome` | `rgba(248,249,251,.86)` | `rgba(26,27,32,.88)` | `blur(40px) saturate(200%)` | `--ambient-2` | `#f7f8fa` / `#1b1c21` | sidebar, toolbars, sheets, top bar | scene + content |

- **Grain**: an inline SVG `feTurbulence` tile, 160 px, alpha .045 light and .07 dark. It hides banding in
  the blur and gives the "material" feel. It is removed under reduced transparency.
- **Sheen**: `linear-gradient(180deg, rgba(255,255,255,.28) → 0 at 42%)` light, `.07` dark. This is the
  diffuse light falling on the top of the glass.
- `data-glass="<level>"` is set by GlassPanel, Card, Toolbar and SidebarGlass. globals.css uses it for
  `corner-shape: squircle` and the forced-colours fallback.

## 3. Scene (what the glass refracts)

`body` paints `--scene` plus `--scene-mesh` (`background-attachment: fixed`). The mesh has three very large
radial gradients and a vertical lift:

- top-left: `color-mix(--accent 12% light / 20% dark)`. The tint quietly colours the whole app.
- top-right: warm `rgba(255,214,186,.42)` light / `rgba(120,72,40,.22)` dark
- bottom-right: cool `rgba(186,212,255,.40)` light / `rgba(40,70,130,.26)` dark
- `linear-gradient(--scene-hi → --scene)`, `#f7f8fa → #eef0f4` light, `#15171d → #0d0e12` dark

It is never noisy: no blobs that move, no more than three hues, and nothing under 600 px radius. Use the
`scene` utility on full-bleed areas that sit outside `body` (for example the login canvas, if a page paints
its own background).

## 4. Edges and elevation by light

| Token | Light | Dark |
|---|---|---|
| `--specular` (1 px inner top) | `rgba(255,255,255,.85)` | `rgba(255,255,255,.13)` |
| `--specular-low` (1 px inner bottom) | `rgba(255,255,255,.30)` | `rgba(255,255,255,.04)` |
| `--hairline` (1 px outer) | `rgba(20,24,36,.10)` | `rgba(255,255,255,.10)` |
| `--hairline-strong` | `rgba(20,24,36,.18)` | `rgba(255,255,255,.17)` |
| `--ambient-1` | `0 1px 2px /.05, 0 6px 16px -10px /.14` | `0 1px 2px #0003, 0 8px 20px -12px #0008` |
| `--ambient-2` | `0 2px 6px /.05, 0 14px 34px -14px /.20` | `… -14px #0009` |
| `--ambient-3` | `0 4px 12px /.06, 0 28px 60px -18px /.28` | `… -18px #000b` |
| `--glass-edge` | `inset 0 1px 0 specular, inset 0 -1px 0 specular-low, 0 0 0 1px hairline` | same |

`--shadow-1/2/3` (v1, `.shadow-elev-*`) = `--glass-edge` + `--ambient-1/2/3`. Elevation goes up by moving
**up the material table** (thicker and brighter), not by darkening shadows. Hover "lift" on interactive glass
is a 7 % white veil (`::after`, pointer-events none), never a filter (G6).

## 5. Colour

### 5.1 Vibrancy labels and fills (on-glass text)

Labels are **solid** colours, not alpha, so contrast stays predictable over any composite.

| Token | Light | Dark | Use | Min ratio (worst allowed backdrop) |
|---|---|---|---|---|
| `--label-1` / `text-label-1` | `#1d1d1f` | `#f5f5f7` | primary text, values | ≥ 11 |
| `--label-2` | `#4b4b51` | `#b6b6bd` | secondary text, descriptions | ≥ 6.4 |
| `--label-3` | `#58585f` | `#a9a9b1` | captions, placeholders, section labels | **4.86** light (chrome over black content) · **4.87** dark |
| `--label-4` | `#8e8e94` | `#6e6e76` | **disabled / decorative only**, never meaningful text | — |
| `--fill-1/2/3` | `rgba(120,120,128,.20/.12/.07)` | `…/.36/.24/.14` | control fills, hover, wells | — |

v1 aliases: `--fg = label-1`, `--fg-muted = label-2`, `--fg-subtle = label-3`, `--surface-2 = fill-2`,
`--border = hairline`.

### 5.2 The single tint (configurable)

Set `data-accent="indigo|teal|graphite|orange"` on `<html>` (default **blue**). Each preset is AA-checked
by the gate in both themes.

| Preset | Light `--accent` / `--accent-text` / fg | Dark `--accent` / `--accent-text` / fg |
|---|---|---|
| blue (default) | `#0a63d1` / `#0957bb` / white | `#4da0ff` / `#6cb0ff` / `#06101f` |
| indigo | `#4f46e5` / `#4a40da` / white | `#9d97ff` / `#aaa5ff` / `#0b0a1f` |
| teal | `#0b7268` / `#08625a` / white | `#3ccfbf` / `#4fd8c9` / `#03201c` |
| graphite | `#3d3d44` / same / white | `#d1d1d6` / same / `#111114` |
| orange | `#b9470b` / `#9c3b08` / white | `#ff9f5a` / `#ffa86a` / `#221004` |

`--accent-soft` (12–20 % alpha) is the selected-row, today and drop-ok tint. Text on it stays label-1 (gate
checked). Tailwind names: `bg-tint`, `text-tint-foreground`, `text-tint-text`, `bg-tint-soft`.
(`bg-accent` remains shadcn's *hover fill* alias; do not confuse the two.)

### 5.3 Status colours retuned for glass

Backgrounds are **translucent tints**, so the material shows through. Foregrounds are darker in light mode
and lighter in dark mode than v1, so they hold AA on the tint composited over a card, over the scene, and
over thick glass on black content.

| State | Glyph (lucide) | Light fg · bg · border · solid | Dark fg · bg · border · solid | Worst ratio |
|---|---|---|---|---|
| feasible | `check-circle-2` | `#0f6430` · `rgba(52,199,89,.16)` · `rgba(30,150,70,.45)` · `#1f9d4c` | `#63e08b` · `rgba(48,209,88,.18)` · `…,.5` · `#30d158` | 4.82 / 4.93 |
| infeasible | `x-octagon` | `#a3211a` · `rgba(255,59,48,.13)` · … · `#d42a20` | `#ff9d95` · `rgba(255,69,58,.20)` · … · `#ff453a` | 4.69 / 4.73 |
| warning | `alert-triangle` | `#7c4800` · `rgba(255,159,10,.18)` · … · `#f5a00a` | `#ffcc66` · `rgba(255,159,10,.20)` · … · `#ff9f0a` | 5.02 / ≥ 7 |
| locked | `lock` | `#4436c4` · `rgba(88,86,214,.13)` · … · `#5856d6` | `#bdb8ff` · `rgba(94,92,230,.26)` · … · `#8c89ff` | 5.05 / 5.12 |
| preoccupied | `ban` + hatch | `#44444a` · `rgba(120,120,128,.12)` · hatch `.22` | `#d1d1d8` · `rgba(142,142,147,.18)` · hatch `.30` | ≥ 7 |
| tip | `stethoscope` | `#a3154f` · `rgba(255,45,85,.11)` · … · `#d11d5c` | `#ffa3c2` · `rgba(255,55,95,.20)` · … · `#ff375f` | 4.79 / 5.17 |
| pclab | `monitor` | `#075a71` · `rgba(50,173,230,.15)` · … · `#08779a` | `#8fdcf7` · `rgba(100,210,255,.17)` · … · `#64d2ff` | 5.09 / 5.20 |

Text on **solid** badges: white in light mode on infeasible, locked, tip and pclab; `#111114` on warning and
feasible, and on every dark-mode solid (gate checked). The categorical faculty palette (`--cat-1..8`) and
the sequential heatmap ramp (`--seq-*`) are unchanged from v1, which validated them for CVD.

## 6. Typography

Stack: `-apple-system, BlinkMacSystemFont, var(--font-inter), "Inter", system-ui…`. On Apple platforms this
is **SF Pro**, with the system choosing Text vs Display optical sizes automatically. Everywhere else it is
**Inter**, with `font-optical-sizing: auto`. Mono: `ui-monospace, "SF Mono", JetBrains Mono`.
`tabular-nums` is global.

> Wiring note (layout.tsx, outside this scope): load Inter with the optical-size axis,
> `Inter({ …, axes: ["opsz"] })`, so non-Apple platforms also get the Display cut at large sizes.

| Utility | Size / line | Weight | Tracking | Use |
|---|---|---|---|---|
| `type-large-title` | 34 / 40 | 700 | −0.024em | page title (desktop, in content, left-aligned) |
| `type-title-1` | 28 / 34 | 700 | −0.021em | page title (mobile) / KPI hero |
| `type-title-2` | 22 / 28 | 650 | −0.017em | section title |
| `type-title-3` | 18 / 24 | 600 | −0.012em | dialog / sheet / empty-state title |
| `type-headline` | 14 / 20 | 600 | −0.006em | card titles, row titles |
| `type-body` | 14 / 20 | 400 | −0.003em | body (also the `body` default) |
| `type-callout` | 13 / 18 | 400 | 0 | dense UI text, table cells |
| `type-footnote` | 12 / 16 | 400 | +0.002em | metadata |
| `type-caption` | 11 / 14 | 500 | +0.012em | axis labels, badges |
| `type-overline` | 11 / 14 | 600 | +0.06em, uppercase | **rare**: only for a grid's column-group label |

Section labels are **sentence case, 11 px semibold, label-3** (Apple Notes and Linear), not uppercase.

## 7. Spacing, shape, focus

- **Grid**: a 4 px base and an 8 px rhythm (Tailwind `--spacing` = 4 px). Component paddings are 8/12/16/20/24,
  and gaps inside controls are 2/4/6.
- **Continuous-curvature radii.** Tokens are multiplied by `--corner-k`, which is 1.15 normally and 1.6
  where `corner-shape: squircle` is supported (Chromium 139+). The squircle looks smaller, so the radius
  is widened.

| Token | Base | Typical use |
|---|---|---|
| `rounded-xs` | 5 px | grid events, keycaps |
| `rounded-sm` | 7 px | menu items, checkboxes |
| `rounded-md` | 9 px | small wells |
| `rounded-lg` | 12 px | inputs, tooltips, select triggers |
| `rounded-xl` | 16 px | popovers, menus, small cards |
| `rounded-2xl` | 20 px | cards, side sheets, sidebar |
| `rounded-3xl` | 26 px | dialogs, bottom sheets, palette |
| `rounded-full` | capsule | **all buttons, chips, segmented controls, toolbars, switches** |

Nesting rule: inner radius = outer radius − padding (Card `rounded-2xl` with 16 px padding → inner wells
`rounded-sm`). Do not put the same radius on everything (anti-pattern A2).

- **Focus**: a global `:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px }`. Fields
  add a 3 px tint halo (`--focus` at 22 %). The ring is ≥ 3:1 on every scene sample (gate: worst 3.94,
  orange preset). No component may remove the outline without replacing it.
- **Touch**: controls are 32 px (default) / 28 px (sm) on fine pointers. On `pointer: coarse`, use `lg`
  sizes or a 44 px row (view agents' responsibility, see §15).

## 8. Fallbacks

| Condition | What happens |
|---|---|
| No `backdrop-filter` support | `@supports not (…)`: every `--mat-*` becomes its `-solid` value |
| `prefers-reduced-transparency: reduce` (Chromium only) **or** `<html data-transparency="reduced">` | solids, `--mat-*-filter: none`, no grain or sheen, flat scene |
| `prefers-contrast: more` | the same solids, plus hairlines at .42/.60 alpha and darker label-2/3 (light) or lighter (dark) |
| `forced-colors: active` | `[data-glass]` becomes `Canvas` + 1 px `CanvasText` border, no shadows. The hatch becomes a dashed border |
| `prefers-reduced-motion: reduce` **or** `<html data-motion="reduced">` | all CSS transitions and animations ~0 ms, `--spring-*-ms: 0ms`. `AppearanceMotionConfig` sets motion/react `reducedMotion="always"` |

**In-app preferences** (`components/ui/appearance-preferences.tsx`): `useAppearancePreferences(userId)`,
`<AppearancePreferencesControl>` (two Apple-style settings rows), `<AppearanceMotionConfig>` and
`appearanceInitScript` (put it in `<head>` so there is no flash). They are stored per user in
`localStorage["smartsched.appearance.<userId>"]`. The settings and shell agents wire these up (see the
hand-off).

## 9. Motion (pointer)

[`motion.md`](motion.md) is the source of truth. What the primitives use:

- CSS: `--spring-snappy | smooth | bouncy-subtle | sheet | glass-morph | ticker` (`linear()` mirrors of
  `@/lib/motion` springs) with `--spring-*-ms`, plus `--dur-*` and `--ease-out / --ease-in`. `--ease-spring`
  and `--ease-snappy` (v2.0 names) are aliases of glass-morph and snappy.
- Popovers, menus, select and tooltip: transitions.dev *Panel reveal* mapped to Base UI `data-starting-style`.
  `--spring-glass-morph`, translate 6 px + scale .97 → 1, exit 120 ms `--ease-in`, **no blur on the popup** (G6).
- Dialog: transitions.dev *Modal open/close*, scale .96 → 1 on glass-morph, exit 120 ms.
- Sheet: translate 40 px on `--spring-sheet` (270 ms), exit 120 ms.
- Tabs (shadcn) and SegmentedGlass (beUI): **layoutId thumb**, transform-only FLIP on `springs.glassMorph`.
  Sidebar pill: `layoutId` on glassMorph.
- Press: scale .97 on `--spring-snappy`, 120 ms. Switch thumb: `--spring-snappy`.
- Toasts (sonner): retimed to `--spring-smooth`, exit 120 ms, max 3 visible.
- Nothing animates `width`, `height`, `top/left`, `box-shadow` or `grid-template-rows` (motion.md §8).

## 10. Contrast verification

```bash
node docs/design/v2/verify-contrast.mjs          # 126 pairs, exit 1 on any failure
node docs/design/v2/verify-contrast.mjs --json
```

The script parses the `@tokens` blocks of `globals.css`, so it always checks what ships. It composites each
material in sRGB over its **worst-case backdrop**: the five scene samples (base, highlight, tint corner,
warm, cool) and, for thick and chrome, pure black content (light theme) or pure white content (dark theme).
It then checks labels, solid fallbacks, accent presets (text on accent, links, focus ≥ 3:1, label-1 on
accent-soft), status fg on tint and text on solid badges. The tightest passes at the time of writing:
focus orange 3.94 (needs 3), infeasible fg on tint over thick/black 4.69 (needs 4.5), and label-3 on chrome
over black 4.86. Re-run it whenever a token changes, and add it to CI next to `npm run check`.

## 11. Primitive catalogue (`src/components/ui`)

**Restyled, API unchanged**: `button` (capsules; default = tint with specular, outline = thick-colour
control, secondary/ghost = fills), `badge` (adds an optional `tone="feasible|…|tint"`), `card` (adds
`variant="glass" (default) | "plain" | "inset"`), `input` (filled field + `useShake()` for the
transitions.dev error shake), `textarea`, `input-group`, `select`, `dropdown-menu` (tint highlight),
`popover`, `tooltip` (no arrow), `dialog`, `sheet` (inset floating, bottom grabber), `tabs` (layoutId
thumb), `command` (Spotlight style), `sonner`, `table` (36 px rows, inset hairlines), `switch`,
`checkbox`, `progress`, `skeleton`, `slider`. Untouched: `avatar`, `label`, `separator`, `scroll-area`
(they read the re-valued tokens).

**New primitives**:

| Component | File | API (short) | Notes |
|---|---|---|---|
| `GlassPanel` | `glass-panel.tsx` | `material`, `radius`, `padding`, `interactive`, `render` | the only way to put raw glass on a page. Pick the material by G1 |
| `Toolbar` (+ `ToolbarButton`, `ToolbarGroup`, `ToolbarSeparator`, `ToolbarLabel`) | `toolbar.tsx` | `placement="inline \| floating-bottom \| floating-top"`, `size`, `orientation` | floating capsule, chrome material, `role="toolbar"` with roving focus (← → Home End) |
| `SidebarGlass` (+ `Header`, `Content`, `Section`, `Item`, `Footer`) | `sidebar-glass.tsx` | `floating`; Item: `active`, `icon`, `count`, `hint`, `render={<Link/>}` | inset floating chrome. The active pill glides (layoutId). Counts are plain numerals |
| `SegmentedGlass` | `segmented-glass.tsx` | `options[{value,label,icon,controls,disabled}]`, `value`, `onValueChange`, `size`, `fill`, `aria-label` | built on beUI Tabs. Clip-path label masking + glass thumb, arrow-key roving |
| `Chip` | `chip.tsx` | `selected` / `onSelectedChange` (toggle), `icon`, `onRemove` + `removeLabel`, `size` | `aria-pressed` toggles. The check pops in (no width tween) |
| `KbdHint` | `kbd-hint.tsx` | `keys={["mod","K"]}`, `sequence`, `thenLabel`, `size` | `mod` shows ⌘ on Apple and Ctrl elsewhere, with no hydration mismatch |
| `EmptyState` | `empty-state.tsx` | `title`, `description`, `actions`, `animation="hero-solver \| nl-to-rules \| file-to-rules \| precheck-fix"`, `animationLabel`, `icon`, `align="start" (default) \| "center"`, `size` | Lottie via `lottie-react` (LottieLight, client-only, JSON code-split from `src/assets/lottie`). Plays once and rests on the poster frame. Shows the **poster PNG under reduced motion**. The opaque background layer is stripped at runtime |
| Appearance prefs | `appearance-preferences.tsx` | see §8 | |
| Motion aliases | `motion-presets.ts` | `SPRING_*` → `@/lib/motion` springs | backwards-compatible names |

## 12. Imported components (how view agents should use them)

| Need | Use | Notes |
|---|---|---|
| KPI number changes | `beui/number-ticker` | pass the value; tune to `springs.ticker` if it rolls too long; final value under reduced motion |
| Run history strip (dashboard) | `beui/charts/status-bar` | days/runs as rounded bars with tooltips; give it status colours, not cat colours |
| Import upload queue | `beui/file-upload` | wire real XHR progress; restyle the row surface to `bg-fill-2` |
| Bulk actions over a table | `beui/expandable-action-bar` inside `Toolbar placement="floating-bottom"` | |
| Mobile bottom nav | `beui/dock` restyled with `glass-chrome` | or `Toolbar` with icon buttons |
| Utilisation and score charts | `evilcharts/charts/recharts-{bar,area,radial}-chart` | feed `--cat-*` / `--seq-*` / status solids via `chartConfig`; use the frosted tooltip variant |
| Solver diff / chat "apply changes" | `beautifului/diff-table` | rows = moves; labels localisable |
| Solve / import pipeline progress | `beautifului/task-rows` | status from real job events; `onRetry` |
| AI chat input | `beautifului/prompt-composer` | Enter sends, Shift+Enter breaks a line, busy → stop |
| Segmented with liquid label morph | `SegmentedGlass` (wraps `beui/tabs`) | |
| Toast stack (optional) | `beui/animated-toast-stack` | sonner stays the default; motion.md §5 allows either |

## 13. Anti-patterns checklist (for the view agents)

Tick every box before a view is "done". These are the tells that made v1 read as AI-generated.

- [ ] **A1 · No gradient or "AI purple" text.** Headings are label-1. The only gradient in the app is the scene mesh.
- [ ] **A2 · No uniform rounded-xl card grid.** Vary the container by role: page sections sit directly on the scene with a `type-title-2` heading, one or two `Card`s per view, lists inside cards are `variant="plain"`, and wells are `variant="inset"`. Four identical KPI tiles in a row is a smell. Use one hero metric plus quieter secondary numbers, or numbers inside a single card (Vercel overview, H8).
- [ ] **A3 · No emoji or illustration icons in UI.** Use lucide at stroke 1.75, 16/20 px, in label-2. Brand colour sits only on the active glyph.
- [ ] **A4 · No over-badging.** At most one badge per row, and only for *state*. Counts are plain tabular numerals (A7, H6). "Pending review" on every row of a pending list is redundant, because the list title already says it.
- [ ] **A5 · No centred-everything.** Page titles, empty states, forms and dialogs' content are left-aligned. Centre only the palette and full-bleed canvases.
- [ ] **A6 · No button rows.** One primary (tint) per view region, secondary as `outline`/`ghost`, destructive in menus. Never three tint buttons side by side.
- [ ] **A7 · No colour-only status, no rainbow.** Glyph + word, translucent tint, and the faculty stripe is secondary to the course code text.
- [ ] **A8 · No glass on glass, no blur on data.** Grid cells, table rows and chart plots are not glass. Popovers over the grid are thick.
- [ ] **A9 · No decorative motion.** No count-up on page load, no stagger on filter or sort, no hover bounce. Motion explains a change (motion.md).
- [ ] **A10 · No uppercase section labels** (except `type-overline` for grid column groups), and no letter-spaced grey "DASHBOARD" eyebrows.
- [ ] **A11 · No heavy shadows or dark borders.** Use hairlines and light (G5).
- [ ] **A12 · No generic copy.** Use real nouns from the domain ("A 206 · 156 seats", "Bahar W7"), not "Manage your items efficiently".

## 14. Accessibility notes

- All text pairs ≥ 4.5:1 on their worst allowed backdrop (§10). Non-text indicators (focus, switch on,
  checkbox, chart marks) ≥ 3:1.
- Glass is never the only boundary: every control also has a fill or a hairline, and every interactive
  element has the global focus outline.
- Keyboard: Toolbar and SegmentedGlass use roving tabindex with ← → Home End. Tabs (Base UI) and Menus
  follow the APG. SidebarGlass items are links with `aria-current="page"`. DiffTable rows expose real
  `role="checkbox"` controls. TaskRows expose `aria-expanded` / `aria-controls`. KbdHint has a spoken
  `aria-label` ("Command or Control + K").
- EmptyState is a `<section aria-labelledby>`. The Lottie has `role="img"` + `aria-label` (pass
  `animationLabel`), and the poster has the same alt text.
- `prefers-reduced-motion`, `prefers-reduced-transparency`, `prefers-contrast` and `forced-colors` are all
  handled (§8), plus the in-app switches for browsers without the transparency query.
- Toasts: sonner's live region, max 3, actions are real buttons.

## 15. Mobile layout (≤ 768 px)

- **Shell**: no sidebar. A top bar in `glass-chrome` (title in `type-title-3`, left-aligned) and a bottom
  `Toolbar placement="floating-bottom"` (or `beui/dock`) holding 4–5 destinations + search as a separate
  circle (Apple Music A1, Fey H20). Use `env(safe-area-inset-bottom)`, 44 px targets (`size="lg"` / `icon-lg`).
- **Large title** scrolls with the content (`type-title-1`). The top bar shows the small title once
  scrolled (motion.md §3.1 scroll thickening).
- **Sheets** are bottom sheets (`side="bottom"`, inset 8 px, `rounded-3xl`, grabber) for filters, event
  details and move dialogs. Dialogs become bottom sheets.
- **Segmented** controls use `fill` to stretch full width. Chips scroll horizontally in one row.
- **Cards** stack in one column with a 12 px gap. KPI numbers become a 2 × 2 grid in **one** card (A2).
- **Command palette** opens full width at the top (`top-[16%]` → `top-2` on mobile is a page-level tweak).

## 16. Known page-level issues (for the view agents; not changed here)

Seen on screenshots of `/dashboard`, `/timetable`, `/settings`, `/rooms` and `/login` (mock API, light and dark,
1440 and 390 px):

1. `shell/sidebar.tsx` is still a flat `bg-sidebar` column. Replace it with `SidebarGlass` (floating, inset 8 px).
2. Dashboard: four identical KPI cards with coloured borders (A2, A7), and a badge on every pending-request
   row (A4). The heatmap uses the v1 blue ramp with white numerals on mid steps, so check legibility. The
   "Eylemler" card repeats header actions.
3. `/login` paints its own flat background, so the scene mesh is hidden (use the `scene` utility). The card
   should be `GlassPanel material="regular"`.
4. Timetable toolbar: day chips and the view switch are separate pill groups. Use `SegmentedGlass` for
   Day/Week and the day picker, and `Toolbar` for the rest. The event cards are white blocks with a stripe.
   Move them to `--accent-soft`-style tints per faculty (stripe + 12 % `--cat-*`).
5. Settings: the model list uses outlined radio rows. Use the settings-row grammar of references.md H21 (label + hint left, control right) and add
   `AppearancePreferencesControl` under a new "Appearance" tab.
6. The layout `viewport.themeColor` is still `#ffffff` / `#0b1220`. Change it to `--scene` (`#eef0f4` /
   `#0d0e12`) in `layout.tsx`.
7. A hydration warning (React #418) appeared on login in the production mock build. It was not traced, and
   none of the new primitives are used by pages yet.
