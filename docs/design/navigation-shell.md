# Navigation shell — sidebar, top bar, ⌘K palette, breadcrumb, drawer, dark mode, i18n, toasts

Owner: design-pro (B). Status: v1 spec, ready for frontend-engineer. Base stack assumed:
Next.js 15 App Router + Tailwind 4 + **shadcn/ui + Radix + motion + TanStack Table**, `lucide-react`,
`next-intl`, `next-themes`, Zustand for UI state. Tokens: `docs/design/tokens.md` is the source of truth (landed 2026-10-07); the shadcn semantic
names used below (`bg-accent`, `text-muted-foreground`, `ring-ring` …) are its `--color-*` aliases.

This document also holds the **shared component-source licence table** (§9) that the other five
surface docs reference.

---

## 1. References (what to borrow)

| # | Reference | Borrow |
|---|---|---|
| 1 | [Linear – inbox shell](https://mobbin.com/screens/beb9d6b3-ec34-46d7-9332-320fcb32a338) | 3-pane rhythm: 220 px nav rail, list pane, detail pane; workspace switcher top-left; counts next to nav items |
| 2 | [Vercel – project settings](https://mobbin.com/screens/a54fee2e-b776-42c2-bd7c-93f7e223c87c) | Top bar = `org ▾ / project ▾` crumbs; secondary left nav inside Settings; "Find…  F" search box in sidebar |
| 3 | [Neon – monitoring shell](https://mobbin.com/screens/cf45e7bf-4a0e-40cc-9db5-a29845b58d4e) | Dark theme sidebar sectioning (PROJECT / BRANCH / APP BACKEND) with uppercase 11 px group labels; "Collapse menu" at the bottom |
| 4 | [Steep – workspace switcher](https://mobbin.com/screens/d393ceef-678a-4d80-bd1b-5e32e13cc065) | Modal switcher with user row + "Log out" footer — reuse for **term switcher** (2026-BAHAR / 2026-FINAL / 2026-27 GÜZ) |
| 5 | [Supabase – command palette](https://mobbin.com/screens/9b4725f5-e038-4fc7-98ad-64a59f74b4d7) | Grouped results (SHORTCUTS / QUERIES / ACTIONS), right-aligned single-key hints (`O N`) |
| 6 | [Devin – command palette](https://mobbin.com/screens/274435b9-f420-4a7c-ab68-82514c1419f9) | Footer legend `↑↓ Navigate · esc Close · ↵ Select`; "Go to …" navigation group |
| 7 | [Juicebox – palette](https://mobbin.com/screens/84169c57-5cd6-4495-bb71-93d37266f4c4) | `Tab` to jump sections, external-link glyph on items that leave the app |
| 8 | [Slite – shortcut cheat-sheet](https://mobbin.com/screens/2e1cc584-70e7-4698-b1da-bf1e6239b00f) | Two-column keyboard shortcut sheet opened with `?` |
| 9 | [Linear – undo toast](https://mobbin.com/screens/14cbb61d-2120-46fa-b29c-b7678e4b85cc) | Bottom-right toast with inline **Undo** + close; 8 s timeout |
| 10 | [Linear – "Issue created" toast with link](https://mobbin.com/screens/1a4540b2-6c15-49ff-a07f-4fddb7490e38) | Toast carrying a title + secondary line + "View" link — use for "Run #42 finished · View" |
| 11 | [Digg iOS drawer](https://mobbin.com/screens/5894fb1e-fd26-4325-97d7-4f750f143703) / [Noom drawer](https://mobbin.com/screens/663f3d6a-ca6d-4eec-b3e4-c122b70c8da8) | Mobile drawer: avatar header, grouped items ("My stuff / & more"), app version in footer |
| 12 | [Hashnode – breadcrumb + settings list](https://mobbin.com/screens/6e5f4cb4-55de-4f70-bb57-e0f40a12be8c) | Breadcrumb `Dashboard › Navbar` in a 48 px top bar; dark-mode moon icon next to avatar |

## 2. Information architecture

```
/                      → redirect /dashboard
/dashboard                       (other agent)
/import                          Import wizard
/requests                        Requests inbox      ?kind=meetings|exams
/generate                        Generate + chat     /runs/[id]  (chat panel lives here)
/timetable                       (other agent)       /runs/[id]/grid
/runs/[id]/report                (other agent)
/rooms   /rooms/[id]             Rooms
/settings/{general,ai,solver,users,terms}
/login
```

Sidebar groups (uppercase 11 px labels, `text-muted-foreground`):

```
[Term switcher: "2026 Bahar ▾"]        ← Steep-style modal; shows kind badge REGULAR/FINAL
PLAN      Dashboard · Import · Requests (badge: NEEDS_REVIEW count) · Generate
RESULTS   Timetable · Runs (badge: RUNNING count, pulsing dot) 
MASTER    Rooms · Buildings · Programs · Instructors
ADMIN     Settings · Users
footer    [avatar + name + role]  [collapse ⌃⌘B]  [theme]  [TR/EN]
```

Top bar (48 px): `☰ (mobile) | breadcrumb | spacer | search button "Ara… ⌘K" | notifications bell | avatar menu`.
Breadcrumb = route segments resolved to labels (`Runs › #42 · Bahar W3 › Chat`). Last crumb is `aria-current="page"` and not a link.

## 3. Interaction spec

### 3.1 Sidebar
- Width 240 px expanded, 56 px collapsed (icon rail with tooltips, `delayDuration=300`). State in Zustand + `localStorage.smartsched.sidebar` (`expanded|collapsed`). Shortcut `⌘/Ctrl+B`.
- Active item: `bg-accent text-accent-foreground`, 2 px left indicator that **slides** between items (`layoutId="nav-indicator"`, spring stiffness 500 damping 40, ≈180 ms). With `prefers-reduced-motion`, indicator just appears (no layout animation).
- Badges: numeric pill right-aligned; `aria-label="Requests, 12 need review"`.
- Collapse animation: width tween 200 ms `ease-out`; labels fade 120 ms, start after 60 ms delay. Reduced motion: instant.

### 3.2 Term switcher
- Trigger shows active term code + kind badge. Opens `Dialog` (Radix) listing terms grouped by year; `is_active` tick; "+ New term" row (ADMIN only); footer = current user + Log out.
- Selecting a term sets `?term=` in URL store and refetches all queries (`queryClient.invalidateQueries({predicate: q => q.queryKey.includes('term')})`). Show a 1-line toast "Switched to 2026 Final".

### 3.3 Command palette (⌘K)
- `cmdk` (shadcn `Command`) inside `Dialog`. Open: `⌘K` / `Ctrl+K` / top-bar button / `/` when focus is not in an input.
- Groups, in order: **Actions** (Generate week…, Import file…, New room, Lock selected), **Go to** (every route), **Rooms** (async, debounced 150 ms, `GET /rooms?q=`), **Courses/Sections** (`GET /sections?q=`), **Runs** (last 10), **Settings**, **Theme/Language**.
- Query grammar shortcuts: `A 206` → room result first; `MAT 112` → section; `#42` → run; `>` prefix → actions only.
- Keys: `↑/↓` move, `Enter` run, `Tab` jump to next group, `Esc` close, `⌘Enter` open in new tab (routes only). Footer legend like Devin. Highlighted row scrolls into view.
- Empty state: "No results for "xyz" — try a room code (A 206) or course code (MAT 112)".
- Loading: skeleton rows in the async groups only; sync groups render immediately.
- Touch: palette becomes a full-height `Sheet` from bottom at < 768 px; input font-size 16 px (prevents iOS zoom).
- Motion: scale 0.98→1 + fade 150 ms; rows no stagger. Reduced motion: fade only.

### 3.4 Responsive drawer (< 1024 px)
- Sidebar becomes a `Sheet side="left"` (Radix Dialog) 280 px wide, backdrop `bg-background/60 backdrop-blur-sm`. Open via `☰`, swipe-right from the left 20 px edge (pointer events, threshold 48 px), close via `Esc`, backdrop tap, swipe-left, or route change.
- Drawer header = avatar + name + role, body = same groups, footer = theme + language + version.
- Focus trap + `aria-modal`. Return focus to `☰` on close.

### 3.5 Dark mode
- `next-themes` with `attribute="class"`, `defaultTheme="system"`, `enableSystem`. Toggle cycles `system → light → dark`. Icon morph (sun/moon/monitor) 150 ms cross-fade.
- Optional polish: beUI **Theme Toggle** uses the View Transition API radial reveal (cap at `--dur-max` 300 ms). Only enable when `!prefers-reduced-motion && document.startViewTransition`. Keep the fallback instant.
- All colours via tokens; never hard-code hex in components. Charts and the timetable grid must read tokens through CSS variables (`hsl(var(--primary))`).

### 3.6 i18n (TR/EN)
- `next-intl` with `[locale]` segment omitted (cookie-based `NEXT_LOCALE`); messages in `messages/tr.json`, `messages/en.json`. Default **tr**.
- Switcher = segmented control `TR | EN` in sidebar footer and in avatar menu. Switching does `router.refresh()`; no full reload.
- Rules: all dates via `Intl.DateTimeFormat(locale)`; day names from locale, never from the Excel strings; numbers `1.529` (tr) vs `1,529` (en); period labels `P7 13:30–14:10` are locale-neutral.
- Turkish casing: use `toLocaleUpperCase('tr')` for codes (`i → İ`). Never `toUpperCase()` on user text.
- Text expansion: Turkish strings run ~20 % longer; every button/label must tolerate 2 lines or truncate with `title`.

### 3.7 Toasts & notifications
- `sonner` (shadcn `Toaster`), position `bottom-right` desktop, `top-center` mobile; `richColors=false`, use tokens; `closeButton`; max 3 visible, newer stacks above (beUI **Animated Toast Stack** is the visual reference: 8 px vertical offset, 0.96 scale per depth).
- Variants: `info` (4 s), `success` (4 s), `warning` (8 s), `error` (sticky until dismissed, has "Details" → opens Sheet with the server error id), `progress` (solver run; shows % and "View run" link; replaced in place via toast id).
- **Undo pattern** (Linear #9): destructive-but-reversible actions (delete constraint, bulk lock, apply AI diff) show "Applied · Undo" for 8 s; the mutation is sent immediately and undo sends the inverse call (server keeps `parent_run_id`). Never delay the request to fake undo.
- Notifications bell: popover list fed by `GET /runs?status=RUNNING|FINISHED&since=` + import jobs; unread dot; items link to run report / import job. Live updates via SSE `/api/v1/events` (fallback: 10 s polling).
- Screen readers: toasts render into `aria-live="polite"`; errors `aria-live="assertive"`.

### 3.8 Global keyboard map (document in `?` sheet, Slite #8)
`⌘K` palette · `⌘B` sidebar · `g d / g i / g r / g g / g t / g s` go to Dashboard/Import/Requests/Generate/Timetable/Settings (vim-style two-key, 800 ms window) · `?` shortcuts sheet · `Esc` close topmost layer · `t` theme · `l` language (only when focus not in editable).

### 3.9 States
| State | Behaviour |
|---|---|
| Loading route | Top-bar 2 px progress bar (`motion` width 0→90 % over 1.5 s ease-out, finishes on route ready); skeleton in content area; sidebar never skeletons |
| Offline | Sticky amber banner under top bar "Bağlantı yok · retrying…"; mutations queue disabled (buttons disabled, tooltip) |
| 401 | Redirect `/login?next=` ; keep term in URL |
| 403 (VIEWER on admin page) | Inline empty-state card "You need PLANNER role" with contact hint |
| 500 | Error boundary per route segment (`error.tsx`) with "Retry" and error id |

## 4. Component list

| Component | Source | Licence | Install / note |
|---|---|---|---|
| Sidebar, Sheet, Dialog, Tooltip, DropdownMenu, Breadcrumb, Badge, Kbd, Separator, ScrollArea | shadcn/ui https://ui.shadcn.com/docs/components | MIT | `npx shadcn@latest add sidebar sheet dialog tooltip dropdown-menu breadcrumb badge separator scroll-area` |
| Command (palette) | shadcn `command` wraps `cmdk` https://github.com/pacocoursey/cmdk | MIT | `npx shadcn@latest add command` |
| Command Palette (glass, spring row) | beUI https://beui.dev/components/blocks/command-palette | MIT (site: "public library is MIT licensed, incl. commercial use") | `bunx --bun shadcn add @beui/command-palette` — optional skin over cmdk; brings `lib/command-search.ts` fuzzy ranking; copy to `components/ui/command-palette.tsx` with source header |
| Drawer (spring, backdrop blur, scroll lock) | beUI https://beui.dev/components/motion/drawer | MIT | `bunx --bun shadcn add @beui/drawer`; use for mobile nav if shadcn Sheet feels flat |
| Theme Toggle (View Transition reveal) | beUI https://beui.dev/components/motion/theme-toggle | MIT | `bunx --bun shadcn add @beui/theme-toggle`; gate on reduced-motion |
| Animated Toast Stack (visual ref) | beUI https://beui.dev/components/motion/animated-toast-stack | MIT | Reference for stacking offsets; implementation stays on `sonner` |
| Toaster | `sonner` https://github.com/emilkowalski/sonner | MIT | `npx shadcn@latest add sonner` |
| Sidebar Nav (collapsible workspace nav) | beautifului.dev https://beautifului.dev/#sidebar-nav | MIT (https://beautifului.dev/license, © 2026 Shane Levine) | copy-paste; keep licence header in file |
| Search (command search w/ empty state) | beautifului.dev https://beautifului.dev/#search | MIT | copy-paste reference for empty-state copy & live filter |
| Tab Pill Glide / Notification Slide-in / Toast Overshoot | kinetics https://kinetics.colorion.co (repo github.com/ckissi/kinetics) | **No licence file found** (raw LICENSE 404) | Reference only — reimplement the spring values (stiffness/damping readouts) in `motion`, do not paste code |
| Toast open/close, Tabs sliding, Icon swap, Panel reveal | transitions.dev https://transitions.dev/library.html (free set) | Custom: free + Pro usable in "unlimited personal and commercial projects"; must keep the `transitions.dev` comment; no redistribution of the library | copy CSS from `/detail.html?t=<slug>`; keep comment line |
| Command Menu, Navigation Menu, Toast | kobra.systems https://kobra.systems/components/command-menu | Free tier = **"Personal use only"**; Pro $199 one-time for commercial | **Do not import** unless the user buys Pro (open question) — reference only |
| Command K, Timeline Progress | reverseui https://reverseui.com/components/command-k | Paid ($50 lifetime, commercial allowed) | Reference only |
| Icons | lucide-react | ISC | already in stack |
| Theme | next-themes | MIT | `pnpm add next-themes` |
| i18n | next-intl | MIT | `pnpm add next-intl` |

## 5. Responsive behaviour

| Width | Sidebar | Top bar | Palette | Toasts |
|---|---|---|---|---|
| 360 | hidden → drawer (280 px) via ☰ / edge swipe | 48 px: ☰, page title (crumbs collapse to last 1), search icon, avatar | bottom Sheet, full height, 16 px input | top-center, full-width minus 16 px gutters, 1 visible |
| 768 | icon rail 56 px always visible; expand on hover (desktop pointer) or tap-hold (touch → opens drawer) | crumbs show last 2 | centered dialog 560 px | bottom-right 360 px |
| 1280 | expanded 240 px (user can collapse) | full crumbs | 640 px | bottom-right |
| 1920 | expanded 240 px; content max-width 1600 px centred; detail panes can be 480 px | full crumbs + term code | 720 px | bottom-right |

Side gutters: 16 px (360), 24 px (768), 32 px (≥1280). No horizontal page scroll at any width; only tables/grids scroll internally.

## 6. Accessibility
- Landmarks: `<nav aria-label="Primary">`, `<header>`, `<main id="main">`, skip link "Skip to content" first in DOM.
- All nav items are real `<a>`; current page `aria-current="page"`. Collapsed rail: icons have `aria-label`, tooltip is `role="tooltip"`.
- Palette: `role="dialog"` + `aria-label="Command palette"`, combobox semantics from cmdk (`role="listbox"/"option"`), live region announces result counts ("12 results").
- Drawer: focus trap, `Esc`, returns focus. Backdrop click closes.
- Contrast: all text ≥ 4.5:1 in both themes; focus ring 2 px `ring-ring` offset 2 px, never removed.
- Reduced motion: `useReducedMotion()` from motion gates every layout/spring animation; CSS `@media (prefers-reduced-motion: reduce) { * { animation-duration: .01ms !important; transition-duration: .01ms !important } }` as safety net.
- Language: `<html lang="tr|en">` updates on switch; `dir="ltr"` fixed.
- Touch targets ≥ 44 × 44 px in drawer and top bar.

## 7. Motion tokens used by this doc (mapped to tokens.md §6)
`--dur-fast` 120 ms (hover, chip toggle) · `--dur-base` 180 ms (indicator slide, popover) · `--dur-slow` 240 ms (sheet/drawer) · `--dur-max` 300 ms ceiling (theme View-Transition reveal is capped here, not 400 ms) · `--ease-out` for entering, `--ease-emphasized` for sheets · nav-indicator / segmented spring = `--spring-drop` (`{stiffness 520, damping 42, mass 0.8}`) · sheets/kanban = `--spring-sheet` (`{300, 30}`, settles ≤ 300 ms). Where this doc earlier said `{500,40}` / `{300,30}` / 300 ms read these tokens instead.

## 8. Open questions
1. Does the university want SSO/LDAP in the avatar menu (ROADMAP backlog) — affects login link placement.
2. Should the term switcher also scope the notifications bell, or show all terms?
3. Buy kobra.systems Pro ($199) to unlock Magnetic Dropzone / File Diff / Grouped Table? Otherwise we reimplement (see import-wizard.md, generate-and-chat.md).
4. Is `/` as palette shortcut acceptable, given Turkish keyboards put `/` on `Shift+7`? Fallback `⌘K` only.

## 9. Shared licence table (referenced by all six docs)

| Site | Licence (as found 2026-10-07) | Usable in SmartSched? |
|---|---|---|
| shadcn/ui, Radix, cmdk, sonner, vaul, TanStack, dnd-kit, motion, react-dropzone, recharts, next-themes, next-intl, react-hook-form, zod | MIT | yes |
| lucide-react | ISC | yes |
| beui.dev | MIT (stated on site; repo github.com/starc007/ui-components) | yes — add source URL header |
| beautifului.dev | MIT (https://beautifului.dev/license) | yes — keep copyright notice |
| evilcharts.com (github.com/legions-developer/evilcharts) | MIT (README) | yes |
| astryx.atmeta.com (github.com/facebook/astryx) | MIT; StyleX-based `@astryxdesign/core` | a11y reference only (styling system mismatch with Tailwind) |
| transitions.dev | Custom terms: free & Pro usable in commercial projects, keep `transitions.dev` comment, no redistribution | yes for the free set (copy CSS) |
| kinetics.colorion.co | No licence text on site or in repo | reference only; reimplement |
| kobra.systems | Free tier "Personal use only"; Pro $199 (commercial) | reference only unless Pro bought |
| reverseui.com | Paid $50 lifetime; commercial OK | reference only |
