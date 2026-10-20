# Login and navbar refresh (2026-10)

Owner ask: "make login page ui better and some ui and elements issues in the navbar and in login page; better use of
empty spaces on the side; maybe use Mobbin."

Status: spec, ready for the frontend engineer. It **amends** `docs/design/v2/sign-in.md` §5 / §8 / §9 and
`docs/design/v3/auth.md` §11.3 (hero size and position only), and `docs/design/navigation-shell.md` §3.1. Everything
else in those documents still holds. No new palette: every value below is an existing token in
`src/app/globals.css` or a page-local custom property built from one.

Code touched by this spec: `src/components/auth/{signin-shell,signin-hero,sign-in-page,local-sign-in,passkey-door}.tsx`,
`src/components/ui/field-styles.ts` (no global change, see §4.3), `src/components/shell/{sidebar,tab-bar,user-menu,top-bar}.tsx`,
`src/components/ui/sidebar-glass.tsx`, `src/lib/i18n/locale-data.json` (new `signin.showcase.*` keys).

---

## 0. Summary

1. **The right side becomes a product showcase**, not an empty gradient: a centred column with a short value
   headline, three value lines (icon + one sentence, TR first) and the existing schedule hero, enlarged and centred
   under them as a real product preview. Static text, no new animation; the hero keeps its one pass ≤ 5 s and poster.
2. **The form is vertically centred in the sheet** on screens ≥ 600 px wide, so the gap under "Hesabınız yoksa…" is
   shared above and below instead of piling up at the bottom. Top-aligned on phones (keyboard safety, sign-in.md §5.4).
3. **The password field no longer looks disabled.** On the sign-in sheet every field rests on the same opaque
   surface as a focused field (`--mat-thick`), with the 3:1 control edge. Focus is shown by the ring only.
4. **The passkey and SSO buttons become outlined "neutral" buttons** on the same surface as the fields, instead of a
   grey fill that reads as disabled.
5. **Navbar:** tinted active state, a visible "Ara… ⌘K" entry, keyboard hints only on hover/focus, 44 px rows on touch,
   theme toggle moved into the account menu, collapsed-rail badges as dots, and a "Menü" tab on phones.

---

## 1. References (Mobbin, web unless marked iOS)

Mobbin screenshots are references only. Nothing is copied: no image, icon or copy from these products ships.

### 1.1 Login

| # | App | Screen | What we take | What we do not take |
|---|---|---|---|---|
| L1 | Origin | [Split login, card + dark panel](https://mobbin.com/screens/78f8e79a-9f51-48e8-a2dd-46990e75a959) | Right panel = one short headline + one product card centred in the panel; both halves are cards with the same inset and radius | Star field photo, testimonial laurels |
| L2 | Square | [Split login, value line + product card](https://mobbin.com/screens/51358a95-0a92-40ef-b433-8120fe1bf67e) | Headline + one supporting sentence **above** the product preview; preview sized to ~50 % of the panel width | Photo background |
| L3 | Adaline | [Split login, app preview panel](https://mobbin.com/screens/a282c6a2-dd34-416f-9911-f53c534155b4) | A calm, low-contrast skeleton of the real app as the preview (our hero is the same idea); the one-line product statement bottom-left of the form side | Logo strip of customers |
| L4 | Clay | [Split login, table preview bleeding off the edge](https://mobbin.com/screens/d2e3fb23-922d-4b6a-9d65-fd9abf5570c6) | Preview is large and anchored, not a thumbnail in a corner | Real-looking personal names in the mock (KVKK: we never show names) |
| L5 | Unify | [Split login, data table preview](https://mobbin.com/screens/8886aa55-0ba2-45c2-a70f-b7bc1350e693) | Form column narrow (~360) and vertically centred; preview carries the "what this does" message | Personal names + avatars in mock data |
| L6 | SchoolAI | [Education split login](https://mobbin.com/screens/15a164e9-3509-4456-94b4-ef729012622f) | Education product: one-sentence value line over the form, a real interaction shown on the right | Large illustration orb |
| L7 | Lovable | [Split login, calm gradient + one UI element](https://mobbin.com/screens/23a8697b-220b-4ed1-90c8-94b2bbcbef67) | A gradient panel works when one real UI element sits centred on it; "Last used" tag on the last method (we already have `login-last-method`) | Saturated sunset gradient |
| L8 | Sprig | [Split login with Google + SSO](https://mobbin.com/screens/abd2da24-0cfe-43d8-ab44-1900f7477a1d) | Secondary sign-in methods as **outlined** full-width buttons, white surface, same height as the fields | Photo |
| L9 | Jira (Atlassian) | [Login with passkey + SSO list](https://mobbin.com/screens/afc5e416-7239-496c-a45a-76cf24831b76) | Passkey as its own outlined button directly under the primary submit; SSO providers grouped after; field rest state white with a visible edge | Long provider list, illustrations in the corners |
| L10 | Tailscale | [Centred login with Microsoft + passkey](https://mobbin.com/screens/627759da-58c1-4872-b051-5fc9cbcadf6a) | Microsoft and passkey buttons share one outlined style; legal line far below | Centred single column (we keep the split) |
| L11 | Height | [Card login, product line under the logo](https://mobbin.com/screens/b761817c-7ed2-4eba-976e-33ae30b15589) | A one-line product statement under the name ("Autonomous project management") | — |
| L12 | Lululemon | [Split login, passkey under the primary](https://mobbin.com/screens/9aa32d7e-2aaf-45db-a316-9ae72c82fe2a) | "veya / or" divider then "Use a passkey" outlined button, plus a "What is a passkey?" link | Photo |

Patterns named: **split login with product showcase** (L1–L7), **centred form column in its half** (L5, L1),
**outlined secondary methods** (L8–L10, L12), **one-line product statement** (L3, L11), **last-used method tag** (L7).

### 1.2 Navbars and sidebars

| # | App | Screen | What we take |
|---|---|---|---|
| N1 | Linear | [Sidebar: workspace, search, groups](https://mobbin.com/screens/fd1b4d88-f021-49a3-98af-4cd3a87e1d29) | Workspace switcher top-left with search + compose icons beside it; quiet group titles; active row = filled pill, 28–32 px rows; no shortcut hints at rest |
| N2 | Linear | [Customise sidebar](https://mobbin.com/screens/f81c0f0b-aaf3-45a0-9985-d79c9b0c0cca) | "Always show / Don't show" per item (later; our `more` flag is the v1 of this) |
| N3 | Height | [Sidebar: search field first, grouped teams](https://mobbin.com/screens/15f734f0-7a55-4fbf-9791-732bdca41869) | A search **field-shaped** entry as the first row; active item white pill on the sidebar tint; footer = account + help icons in one row |
| N4 | Tines | [Sidebar with ⌘K search row](https://mobbin.com/screens/9657da36-defe-4e07-a77b-7f9eda2f7ad7) | "Search ⌘K" as a normal nav row with the shortcut on the right; account at the top, help at the bottom |
| N5 | Wrike | [Sidebar with search ⌘K](https://mobbin.com/screens/48e627e3-78f0-456d-b073-59a5cf4f3e5f) | Search + Inbox (with count) above the groups |
| N6 | GitLab | [Sidebar: search field + grouped items](https://mobbin.com/screens/3421735a-69df-4b99-bc52-abc827c940fa) | "Search or go to…" field directly under the header; active item has a left accent bar + fill |
| N7 | Juicebox | [Sidebar footer: Quick Find ⌘K + account](https://mobbin.com/screens/22089986-2770-4a66-803c-634a16e3f65a) | Account row (name + workspace) as the last row; settings/support above it |
| N8 | Clockwise | [Calendar icon rail with labels](https://mobbin.com/screens/9dbc5005-a12f-4542-946a-257ab7543f37) | Collapsed rail where each icon keeps a tiny label; settings/help/account at the rail bottom |
| N9 | Midday | [Icon-only rail](https://mobbin.com/screens/66fa3b33-2331-47be-a997-5b4d76a7072e) | Rail of 40 px squares, active = filled square, account avatar last |
| N10 | Todoist (iOS) | [Floating tab bar with Browse](https://mobbin.com/screens/f79218a8-4100-440c-aeb2-3a32680bf787) | Floating capsule tab bar, active = filled pill, last tab "Browse" opens everything else |
| N11 | Craft (iOS) | [Floating icon tab bar + separate action](https://mobbin.com/screens/cf3931f4-9dea-4da2-a94a-b520196c7c91) | The extra action (our search circle) is a separate circle beside the capsule |

Patterns named: **workspace/term switcher at the top** (N1, N3), **search as the first row with ⌘K** (N3–N7),
**filled-pill active state** (N1, N3, N9, N10), **shortcut hints hidden at rest** (N1, N3), **account row in the
footer** (N3, N7), **icon rail with tooltip/label** (N8, N9), **floating capsule tab bar with a "more" tab** (N10, N11).

---

## 2. Login: layout per breakpoint

Nothing changes in routing, doors, notices, URL contract, keyboard safety or the sheet itself (sign-in.md §4, §5.4).
The sheet (`signin-sheet`) keeps inset 8, `rounded-2xl`, `glass-regular` tint without backdrop blur, and
`--signin-sheet-w: clamp(400px, 36vw, 480px)`. The new piece is the **showcase** in the scene to its right.

### 2.1 New page-local tokens (add to `SHEET_TOKENS` in `signin-shell.tsx`)

| Token | Value | Use |
|---|---|---|
| `--showcase-max` | `760px` | Max width of the showcase column |
| `--showcase-pad` | `clamp(32px, 4vw, 72px)` | Inline padding of the scene area |
| `--showcase-hero-w` | `min(100%, 720px)` (≥ 1280), `min(100%, 560px)` (1024–1279) | Hero frame width (was `min(52vw − 120px, 640px)` bottom-right) |
| `--showcase-gap` | `32px` (≥ 1280), `24px` (< 1280) | Copy block → hero |

### 2.2 ≥ 1280 px (reference 1440 × 900)

```
┌ 8 ┬─ sheet 480 (36vw clamp) ─────────┬──────────── showcase area (100vw − 496) ──────────────────────┐
│   │ [S] SmartSched                     │                                                               │
│   │                                    │      ┌── column max 760, centred, vertically centred ──┐      │
│   │  (flex spacer, my-auto)            │      │ DERS PROGRAMI · SINAV · DERSLİK      overline   │      │
│   │  Giriş yap               34/41     │      │ Üniversitenizin haftası,              title-1   │      │
│   │  Ders programı, sınavlar ve …      │      │ tek bir yerde.                                  │      │
│   │  [Microsoft]  (when configured)    │      │                                                 │      │
│   │  Kullanıcı adı veya e-posta        │      │ ◷ Çakışmasız program …            callout ×3    │      │
│   │  [ ad.soyad                    ]   │      │ ⌂ Boş derslik bulun …                            │      │
│   │  Parola        Parolamı unuttum    │      │ ✓ Sınav ve gözetmen planı …                      │      │
│   │  [ ••••••                    👁 ]   │      │                       32                        │      │
│   │  [ Giriş yap                    ]  │      │ ┌ hero frame 720 × 405 (16:9) ──────────────┐   │      │
│   │  ───────── veya ─────────          │      │ │ room × period grid, one pass → poster    │   │      │
│   │  [ 🔑 Geçiş anahtarıyla giriş ]     │      │ └───────────────────────────────────────────┘   │      │
│   │  Hesabınız yoksa bir yöneticiye …  │      └─────────────────────────────────────────────────┘      │
│   │  (flex spacer, my-auto)            │                                                               │
│   │  KVKK · v0.1.0        [TR|EN] ◐    │                                                               │
└───┴────────────────────────────────────┴───────────────────────────────────────────────────────────────┘
```

**Sheet (left).**
- The content between brand row and footer is vertically centred: in `SignInShell`, the wrapper
  `<div className="flex flex-1 flex-col pt-(--signin-top)">` gets an inner `<div className="min-[600px]:my-auto">`
  around `children`. When content is tall (door 2 + error + passkey), `my-auto` resolves to 0, so test #25 behaves as
  today. Keep `pt-(--signin-top)` as the minimum gap under the brand row.
- Form column stays `max-w-[400px]`; at sheet width 480 with 40 px padding the column is 400 px.
- Footer unchanged in place and order (it must remain the **first `<footer>` in the DOM**, see §6).

**Showcase (right).** Replaces "hero absolutely positioned bottom-right".
- Element: `<aside aria-labelledby="signin-showcase-title" data-testid="signin-showcase">` as a sibling after
  `<main>`, inside the `scene` flex row. Classes:
  `hidden lg:flex flex-1 min-w-0 items-center justify-center px-(--showcase-pad) py-10 forced-colors:hidden`.
  Never a `<footer>` or `<header>` element inside it.
- Inner column: `flex w-full max-w-(--showcase-max) flex-col gap-(--showcase-gap)`.
- Copy block (`data-testid="signin-showcase-copy"`), real text (not `aria-hidden`):
  - Overline: `type-overline text-label-2` (tracking from the utility), `signin.showcase.eyebrow`.
  - Headline: `<h2 id="signin-showcase-title" className="type-title-1 text-label-1 text-balance max-w-[22ch]">`.
  - Value list: `<ul className="mt-5 flex flex-col gap-3">`, each `<li className="flex items-start gap-3 type-body text-label-2">`
    with a 28 px icon chip `flex size-7 shrink-0 items-center justify-center rounded-lg bg-tint-soft text-tint-text [&_svg]:size-4 [&_svg]:stroke-[1.75]`
    (lucide `CalendarCheck2`, `DoorOpen`, `ClipboardCheck`, `aria-hidden`), then the sentence; the first clause in
    `font-semibold text-label-1`.
- Hero: `SignInHero` is rendered **inside** the column, after the copy block. Its wrapper class changes from
  `absolute right-8 bottom-8 w-[min(calc(52vw-120px),640px)]` to
  `relative w-(--showcase-hero-w) self-center` (`aria-hidden`, `pointer-events-none`, `select-none`,
  `forced-colors:hidden`, `max-lg:hidden` all stay). The frame keeps `glass-tint` with **no** `backdrop-filter`,
  `rounded-2xl`, `shadow-elev-1`. Aspect 16:9 (file is 960 × 540) so the poster and the player box match: no
  layout shift when the player replaces the poster (`aspect-video` on the frame).
- Scene background: unchanged `scene` gradient (no new colour). Optional, only if the engineer wants more depth: a
  single radial wash behind the hero, `bg-[radial-gradient(60%_50%_at_50%_60%,var(--color-tint-soft),transparent)]`
  as a static `aria-hidden` layer. No blur, no animation.

### 2.3 1024–1279 px (reference 1024 × 768)

- Sheet: `clamp(400px,36vw,480px)` → 400 px. Showcase area ≈ 608 px.
- `--showcase-pad: 32px`, `--showcase-gap: 24px`, `--showcase-hero-w: min(100%, 560px)`.
- Headline `type-title-2` (`lg:max-xl:type-title-2`), value lines `type-callout`, gap 10.
- Height guard: under 820 px tall (`[@media(max-height:820px)]`) hide the 3rd value line and the overline, so the
  column (≈ 80 + 3×22 + 24 + 315 hero) fits in 768 without scrolling. Under 700 px tall hide the value list entirely
  (headline + hero only).

### 2.4 600–1023 px (reference 768 × 1024)

- The hero is **not mounted** (it is ≥ 1024 only, AUX-10 / `au-signin-hero.spec.ts` mobile case). Keep it that way.
- The showcase shows **copy only** in the space right of the 400 px sheet (≈ 352 px): `min-[600px]:flex lg:...`
  i.e. the `<aside>` is `hidden min-[600px]:flex`; column `max-w-[300px]`, headline `type-title-2`, value lines
  `type-callout`, vertically centred. Between 600 and 767 px the area is < 300 px: hide the aside
  (`hidden md:flex`).
- No `lottie-react` request below 1024 (unchanged).

### 2.5 < 600 px (reference 390 × 844)

- The sheet is the page (unchanged). The showcase aside is not rendered (`hidden`), so nothing adds height above the
  fields (keyboard rule sign-in.md §5.4).
- No value lines are added on phones: the subtitle already carries the product statement. Phones get the field,
  button and spacing fixes in §4 only.
- Footer: stays at the end (`mt-auto`), `pb-[max(8px,env(safe-area-inset-bottom))]`; targets 44 px (already).

### 2.6 Copy (TR first; new keys in `locale-data.json`)

No person, school or course names (KVKK). Sentences ≤ 70 characters so each value line wraps to at most two lines
at 1024.

| Key | TR | EN |
|---|---|---|
| `signin.showcase.eyebrow` | Ders programı · Sınavlar · Derslikler | Timetables · Exams · Rooms |
| `signin.showcase.title` | Üniversitenizin haftası, tek bir yerde. | Your university's week, in one place. |
| `signin.showcase.point1` | **Çakışmasız program.** Her ders uygun derslik ve saate yerleşir. | **Clash-free timetables.** Every class gets a fitting room and slot. |
| `signin.showcase.point2` | **Boş derslik, saniyeler içinde.** Bulun ve ayırın. | **A free room in seconds.** Find it and book it. |
| `signin.showcase.point3` | **Sınav ve gözetmen planı.** Dönem takvimiyle uyumlu. | **Exams and invigilation.** In step with the term calendar. |

The `<b>` parts render through the existing `rich()` helper in `signin-shell.tsx`.

---

## 3. Spacing and typography (sheet)

4 px grid; values in Tailwind spacing units. Overrides sign-in.md §9 "Rhythm" only where marked **new**.

| Gap | Value | Class |
|---|---|---|
| Brand row → content (min) | `--signin-top` (unchanged) | `pt-(--signin-top)` |
| Title → subtitle | 6 | `mt-1.5` (unchanged) |
| Subtitle → first control | 28 | `mt-7` (unchanged) |
| Label → field | 6 | `gap-1.5` (unchanged) |
| Field → field | 16 | `gap-4` (unchanged) |
| Password → submit | 20 | `mt-5` (unchanged) |
| Submit → "veya" divider | **20** (was ≈ 16) | divider `mt-5 mb-4` |
| Divider → passkey button | 16 | (above) |
| Passkey → footnote | 12 | `mt-3` |
| Footer top padding | 24 (≤ 960 tall: 12) | unchanged |

Typography: title `type-large-title` (28 → 34); subtitle `type-callout text-label-2`; labels
`type-callout font-semibold text-label-1`; field text `type-body` (16 px on coarse pointers, unchanged); "Parolamı
unuttum" `type-callout text-tint-text`; footnote `type-footnote text-label-2`; version `type-footnote text-label-3
tabular-nums`. Divider label "veya": `type-footnote text-label-3`, hairlines `bg-(--hairline)`.

---

## 4. Login: field and button styling

### 4.1 Cause of the "disabled-looking" password field

`fieldSurface` (`components/ui/field-styles.ts`) rests on `bg-fill-3` and turns `bg-(--mat-thick)` only on
`focus-visible`. The identifier is focused on load, so it is white; the password, at rest, is the grey well. Next to
each other the rest state reads as disabled. The grey `secondary` passkey button below adds a third grey surface.

### 4.2 Rule

On the sign-in sheet, **every field and every secondary sign-in button rests on the same opaque surface**, and
focus is carried by the ring + halo, not by a surface change.

### 4.3 Implementation (scoped, no global change)

The sign-in sheet sets a scope class (on `signin-sheet`):

```
[&_[data-slot=input]]:bg-(--mat-thick) [&_[data-slot=input]:hover]:bg-(--mat-thick)
[&_[data-slot=input]:hover]:shadow-[inset_0_0_0_1px_var(--border-strong)]
```

- Rest: `bg-(--mat-thick)` + `shadow-(--edge-control)` (1 px `--border-control`, 3:1 against the sheet's solid
  fallback: test #26 keeps passing because the edge token is untouched).
- Hover: edge darkens to `--border-strong`; surface unchanged.
- Focus-visible: unchanged (2 px `--focus` outline + 3 px halo).
- Invalid: unchanged (`--status-infeasible-border` edge + halo).
- Autofill: unchanged (`fieldAutofill`, 7 % tint over `--mat-thick-solid`), which now reads as "filled" against
  white, as intended in auth.md §10.2.
- Reduced transparency / `contrast-more`: `--mat-thick` already resolves to its solid value.
- The eye `IconButton` inside the password field: `text-label-2 hover:text-label-1 hover:bg-fill-3`, size 44 (unchanged).

Why not change `fieldSurface` globally: in-app forms sit on cards where the filled well is the intended Liquid Glass
look (liquid-glass.md §9). The sign-in sheet is a different context (one short form, white-on-tint like L8, L9).

### 4.4 Passkey and SSO buttons ("neutral outlined")

| Button | Before | After |
|---|---|---|
| Passkey (`passkey-door`) | `BusyButton variant="secondary"` grey fill | Same component, add className `bg-(--mat-thick) text-label-1 shadow-(--edge-control) hover:bg-(--mat-thick) hover:shadow-[inset_0_0_0_1px_var(--border-strong)] active:bg-fill-3` |
| Google (when configured) | secondary | Same "neutral outlined" classes, Google "G" mark 18 px left of the label (Google branding rules) |
| Microsoft | MS brand colours (sign-in.md §7) | **Unchanged** (Microsoft's own values, never themed) |
| Submit "Giriş yap" | `variant="default"` (tint) when local is the primary door | Unchanged |

All: `size="lg" shape="rect" w-full`, height `--signin-control-h` (44 fine / 48 coarse), icon 16 px with
`stroke-[1.75]`, `gap-2`.

### 4.5 Ordering of methods

| Configuration | Order top → bottom |
|---|---|
| No SSO (today's live site) | local form → submit → "veya" → passkey → "Hesabınız yoksa…" footnote |
| Microsoft enabled | Microsoft button (primary, sign-in.md §3) → hints → hairline → door 2 disclosure (local form) → passkey under the local submit, inside door 2's flow, as today |
| Microsoft + Google | Microsoft → Google (both full width, 8 px apart) → hints → door 2 → passkey |
| Last used method known | the `login-last-method` line stays where it is (under the method it refers to), `type-footnote text-label-3` |

Rationale: institution SSO first (Tailscale L10, Jira L9 put SSO/passkey together); passkey directly after the
password submit (Jira L9, Lululemon L12) so it reads as "another way to do this", not a separate product.

---

## 5. Motion (per `/motion_designer`; rows for `v2/motion.md` §3.12 / §3.19)

Nothing new animates on the sign-in page. The showcase copy is static. The hero keeps every rule of auth.md §11.3.

| Moment | Purpose | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| Page load, showcase copy | — (initial state) | None | — | — | — |
| Hero appears (≥ 1024) | "This is the product you are signing into" | Unchanged: frame opacity 0 → 1 + 4 px rise once the first frame is ready; one pass frames 0 → 140 (4.67 s), then poster 140, no loop, holds while typing (`HERO_INPUT_HOLD_MS`) | `dur.slow` 240 ms, `ease.out` | Poster PNG, no player request, no entry motion | Frame tint → `--mat-regular-solid` (opaque) |
| Field hover | — (frequent) | Edge colour only, CSS transition | `--dur-fast` 120 ms | Instant | Same |
| Door 2, errors, language, welcome | Unchanged | sign-in.md §10 | — | — | — |

Performance note for the larger hero (720 vs 640 px wide, ≈ 1.27× the area): an SVG lottie frame costs roughly
in proportion to painted area, but the hero draws nothing while the person types, so the AUX-10 typing check is not
affected; the pass itself may cost more per frame on CPU-only renderers. **Gate:** run `e2e/au-signin-hero.spec.ts`
at 1440 × 900 and 1920 × 1080. If either case fails, cap `--showcase-hero-w` at 640 px; do not switch renderers or
add `will-change`. Also check the poster PNGs are ≥ 1440 px wide (2× of 720) so they stay sharp; if not, re-export
from `docs/lottie/build` (same licence, AGPL-3.0, same as the repo).

---

## 6. Constraints the implementer must keep

1. **`e2e/sign-in.spec.ts` #25** (1440 × 900, door 2 open + an error, `page.locator("footer").first()` fully in
   view): the sheet footer must stay the **first `<footer>` in the DOM** (the showcase is an `<aside>` after `<main>`
   and contains no `<footer>`); the `my-auto` centring wrapper collapses to 0 when the column is full, so the footer
   position in that state is unchanged. Keep `pt-(--signin-top)` and the `[@media(max-height:960px)]` tightening.
2. **`e2e/sign-in.spec.ts` #26**: `--border-control` and `--mat-regular-solid` are untouched.
3. **`e2e/au-signin-hero.spec.ts`**: hero `data-testid="signin-hero"`, `data-state`, one pass ≤ 5 s, poster frame,
   no loop, typing LoAF ≤ 50 ms, `aria-hidden`, `pointer-events-none`, hidden in forced colours, not mounted < 1024
   or on the 2FA step, no player request under reduced motion / Save-Data or at 390. The motion-audit case checks
   that the element at the hero's centre belongs to the hero: **the copy block must never overlap the hero box**
   (it is above it in normal flow; do not position the copy absolutely). "One blurred surface besides chrome": the
   showcase uses no `backdrop-filter`.
4. **`SignInHero` stays memoised with no props**, so sheet re-renders on keystrokes never reach it. Pass layout through
   CSS custom properties on the parent, not props.
5. **data-testids** stay: `signin-sheet`, `signin-brand`, `signin-org-logo`, `signin-subtitle`, `signin-hints`,
   `login-disclosure`, `login-form`, `login-identifier`, `login-password`, `login-submit`, `login-error`,
   `forgot-password`, `caps-lock`, `login-no-account`, `login-last-method`, `passkey-door`, `login-sso-microsoft`,
   `signin-kvkk`, `app-version`, `locale-toggle`, `locale-option-tr|en`, `theme-toggle`, `signin-hero`, all
   `signin-notice-*` / `signin-error-*`. New: `signin-showcase`, `signin-showcase-copy`.
6. **KVKK**: no real names in any mock content (copy, hero, posters, future screenshots). Use course codes
   (`MAT101`) and room codes (`B-204`) only.
7. **Keyboard safety** on phones (sign-in.md §5.4) untouched: nothing added above the fields below 600 px.

---

## 7. Accessibility (login)

- Landmarks: `<main>` (sheet) and `<aside aria-labelledby="signin-showcase-title">`. Tab order: sheet first; the
  aside has no focusable elements, so focus never leaves the form.
- Heading levels: `h1` "Giriş yap" in the sheet; showcase headline is `h2`.
- Contrast to verify (add rows to `docs/design/v2/verify-contrast.mjs`, light and dark, against the **lightest and
  darkest stop of the `scene` gradient**): `label-1` headline, `label-2` value text (needs ≥ 4.5:1), `tint-text` on
  `tint-soft` icon chips (non-text 3:1 is enough, icons are decorative and `aria-hidden`).
- Field boundary 3:1 (`--border-control`) unchanged; with the white field surface the boundary is now against
  `--mat-thick` on one side and the sheet on the other, both ≥ 3:1 (the white side is higher than the sheet side).
- Touch: every control ≥ 44 px (fields and buttons 48 on coarse; footer segments 44; eye button 44; "Parolamı
  unuttum" 44 hit area on coarse).
- Forced colours: showcase hidden (`forced-colors:hidden`), sheet uses `Canvas` / `CanvasText` (unchanged).
- Language: the overline/headline/points follow the selected locale; `lang` on `<html>` already switches.

---

## 8. Navbar spec

Scope: desktop sidebar (`sidebar.tsx`, `sidebar-glass.tsx`), top bar capsules (`top-bar.tsx`), account menu
(`user-menu.tsx`), mobile tab bar (`tab-bar.tsx`). I could not see the app signed in; the issues below come from
reading the code and the references. The engineer auditing the local stack should confirm or drop each one and merge
with what they see. Severity: **M** major, **m** minor.

### 8.1 Expected issues → desired state

| # | Sev | Expected issue (from code) | Desired state | Ref |
|---|---|---|---|---|
| NV-01 | M | Active item = `bg-fill-1` pill, hover = `bg-fill-3`; on the glass sidebar the two are close, and the icon/label colour is the same as inactive rows, so "where am I" is weak | Active: keep the `bg-fill-1` pill + `shadow-[inset_0_1px_0_0_var(--specular-low)]`, and add **icon `text-tint-text`** and **label `font-semibold`**. Hover on inactive: `bg-fill-3`. Active hover stays `bg-fill-1` (no flash) | N1, N3, N9 |
| NV-02 | M | Rows are `h-8` (32 px) with no coarse-pointer override; at ≥ 1024 px a touch iPad (landscape) gets 32 px targets | `pointer-coarse:min-h-11` on `SidebarGlassItem`, the "Daha fazla" row already has it | WCAG 2.5.8 / project 44 px rule |
| NV-03 | M | No search entry in the sidebar; ⌘K lives in the top-bar capsule only, so a new person does not find search/command | First row under the term switcher: a field-shaped button "Ara…" + `KbdHint ["mod","K"]` on the right, opens the existing command palette. `h-8 pointer-coarse:h-11 w-full rounded-[10px] bg-fill-3 px-2.5 type-callout text-label-3 shadow-(--edge-control)`, icon `Search` 16. Collapsed rail: a 40 × 40 icon button with tooltip "Ara (⌘K)". `data-testid="sidebar-search"` | N3, N4, N5, N6 |
| NV-04 | m | `KbdHint` "G D" etc. on every row at rest: visual noise, and meaningless on touch | Hints `opacity-0` at rest, `group-hover/sidebar-item:opacity-100 group-focus-visible/sidebar-item:opacity-100`, never on coarse pointers (`pointer-coarse:hidden`). Transition `--dur-fast`; reduced motion → instant | N1 |
| NV-05 | m | Footer packs `ChecklistPill`, `UserMenu` and a separate `ThemeToggle`; the theme toggle duplicates a setting that belongs in the account menu, and at 72 px the footer stacks three controls | Footer = `ChecklistPill` (while onboarding) + **one account row** (avatar 28, name `type-callout font-medium`, role `type-caption text-label-3`, chevron). Move theme (Açık / Koyu / Sistem, `SegmentedControl size="sm"`) and language into the account menu, under the name/email header, above "Çıkış yap". Keep `data-testid="theme-toggle"` on the new control | N1, N3, N7 |
| NV-06 | m | Collapsed rail (1024–1279 and stored collapse): counts are hidden (`count: !collapsed && …`), so "İstekler" with 12 items looks empty | Collapsed: an 8 px dot `bg-(--accent)` at the icon's top-right (`absolute top-1 right-1 size-2 rounded-full ring-2 ring-(--mat-chrome)`), tooltip text carries the count (already in `aria-label`) | N8, N9 |
| NV-07 | m | Collapsed rail active state: the pill is full row width minus padding; at 72 px it can look off-centre | Collapsed items `size-10 mx-auto justify-center`, active pill 40 × 40 `rounded-xl` | N9 |
| NV-08 | m | Group titles ("Planla", "Sonuçlar", "Yönetim") and each group's "Daha fazla" disclosure: up to 3 disclosure rows in a long list | Group titles `type-caption font-semibold text-label-3 px-2.5 pt-4 pb-1`; keep per-group "Daha fazla" but style it as a quiet row (`text-label-3`, chevron right of the label, no left icon) so it is not read as a page | N1, N2 |
| NV-09 | m | Header: logo + name + collapse toggle; the toggle is `size="sm"` (28) | Toggle `size-8 pointer-coarse:size-11`; tooltip "Kenar çubuğunu daralt (⌘B)" (exists) | — |
| NV-10 | m | Top bar: breadcrumb capsule and toolbar capsule float over content; on wide pages the breadcrumb hides middle crumbs below `xl` | Keep. Ensure the toolbar capsule holds at most: run island, notifications, help/`?`. Search moves to the sidebar (NV-03) on desktop; the top bar keeps it only below `lg` | N1 |
| NV-11 | m | Mobile tab bar: 4 planner tabs + detached search circle; the rest of the IA (Derslikler, Ayarlar, Kullanıcılar…) is only in the drawer, reachable from the top bar | Add a 5th tab **"Menü"** (`LayoutGrid` icon) that opens the existing `mobile-drawer` as a sheet from the bottom (pattern 4). Labels per `TAB_LABELS`; TR "Menü", EN "More". Keep the search circle beside the capsule | N10, N11 |
| NV-12 | m | Run island `animate-ping` loops while a run is active | Allowed (ongoing work), already `motion-safe:`; confirm it stops when the run ends and that the text count carries the state | skill §2.6 |

### 8.2 Sidebar anatomy (≥ 1280, expanded 264 px)

```
┌ SidebarGlass, inset 8, r 2xl ───────────┐
│ [S] SmartSched                     [⇤]  │ header 44
│ [ Güz 2026–27            ⌄ ]            │ TermSwitcher (unchanged)
│ [ 🔍 Ara…                 ⌘K ]           │ NV-03, 32 / 44 coarse
│                                          │
│ PLANLA                                   │ type-caption label-3
│ ▣ Özet                                   │ active: fill-1 pill, icon tint-text, semibold
│ ⇩ İçe aktar                              │
│ ✉ İstekler                         12   │ count: type-caption tabular-nums label-2
│ ▶ Oluştur                                │
│ ⌄ 2 tane daha                            │ quiet disclosure
│ SONUÇLAR                                 │
│ …                                        │
│ ─────────────────────────────────────── │
│ (ChecklistPill while onboarding)         │
│ (AB) Ad Soyad            ⌄              │ account row → menu (theme, language, version, sign out)
└──────────────────────────────────────────┘
```

Row tokens: height 32 (coarse 44), `rounded-[10px]`, `px-2.5`, `gap-2.5`, icon 16 `stroke-[1.75]`, label
`type-callout font-medium text-label-1`, inactive icon `text-label-2`. Section gap 16. Width 264 / rail 72 (unchanged).

### 8.3 Mobile (< 1024)

- Top bar 48 px + safe area (unchanged), large-title collapse (pattern 15, unchanged).
- Tab bar: floating capsule, items `min-h-12`, labels always shown (`type-caption`), active = `--mat-thick` pill
  with `layoutId="tab-pill"` (unchanged), icon + label `text-tint-text`, inactive `text-label-2`. 4 role tabs + "Menü"
  (NV-11). Bottom inset `max(8px, env(safe-area-inset-bottom))`.
- Drawer opened from "Menü": the same `NavList` (expanded rows, 44 px), search row first, account row last.

### 8.4 Navbar motion

| Moment | Purpose | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| Active item changes (navigation) | "You are now here" | Active pill moves with `layoutId="sidebar-pill"` from the old row to the new one (pattern 3) | `springs.glassMorph` | Pill appears at the new row on the next frame | Pill opaque `--mat-thick-solid` |
| Sidebar collapse / expand (⌘B) | "The sidebar got out of the way and comes back to the same place" | `layout` on the aside (FLIP, no `width` tween); labels fade out 80 ms before / in 60 ms after | `springs.smooth`; labels `dur.fast` | Width jumps; labels instant | Same |
| Shortcut hints on hover (NV-04) | — (frequent) | opacity only | `--dur-fast` | Instant | Same |
| "Menü" sheet (NV-11) | "Everything else is here, and it goes back down" | Bottom sheet (pattern 4) | `springs.sheet`, exit 120 ms | Opacity 100 ms | Opaque sheet |
| Badge count changes | — (live data) | None (no bump on live updates) | — | — | — |

Checklist: only transform/opacity; the pill is a `glass-tint` fill inside glass (no glass on glass); no fading
ancestor of the sidebar glass; ⌘B and Tab/Enter paths exist; `aria-current="page"` is the non-motion signal.

### 8.5 Navbar accessibility

- `aria-current="page"` on the active link (exists); active is not colour-only (weight + pill + `aria-current`).
- `tint-text` icon on `fill-1` over the sidebar material: verify ≥ 3:1 (non-text) in light and dark; label-1 text
  ≥ 4.5:1 (exists).
- Collapsed rail: every icon has a tooltip and an `aria-label` including the count (exists).
- Search row is a `<button>` with accessible name "Ara" and `aria-keyshortcuts="Meta+K Control+K"`.
- Touch targets: 44 px on coarse pointers for rows, toggle, search, account row, tab items (NV-02, NV-09).

---

## 9. Components, sources and licences

| Component | Source | Licence |
|---|---|---|
| `SignInShell`, `SignInHero`, `LocalSignIn`, `PasskeyDoor`, new `SignInShowcase` (inside `signin-shell.tsx` or its own file) | SmartSched (this repo) | AGPL-3.0 (repo) |
| `Input`, `Button`, `IconButton`, `BusyButton`, `SegmentedControl`, `Tooltip`, `DropdownMenu`, `Sheet` | shadcn/ui + Base UI, vendored (`components/ui/SOURCES.md`) | MIT |
| `SidebarGlass*`, `TabBar`, `CommandPalette` | SmartSched | AGPL-3.0 |
| Icons (`CalendarCheck2`, `DoorOpen`, `ClipboardCheck`, `Search`, `LayoutGrid`) | lucide-react | ISC |
| Hero animation + posters | `docs/lottie/hero-solver-*` (SmartSched) | AGPL-3.0 |
| Player | `lottie-react` | MIT |
| Microsoft / Google marks | Vendor branding guidelines (sign-in.md §7) | Trademark, drawn inline per guidelines |
| Mobbin references (§1) | Screenshots on mobbin.com | Reference only, nothing copied |

---

## 10. Acceptance checks (add to `e2e/sign-in.spec.ts` unless noted)

1. 1440 × 900 default: `signin-showcase` visible; its box does not intersect `signin-sheet`; `signin-hero` box is
   inside `signin-showcase` and horizontally centred in it (± 2 px); copy box bottom ≤ hero box top.
2. 1440 × 900: `login-identifier` and `login-password` computed `background-color` are equal while neither is focused
   (blur the identifier first), and equal to the resolved `--mat-thick`.
3. 1024 × 768: the showcase column fits without vertical scroll of the page (`document.scrollingElement.scrollHeight
   ≤ innerHeight`).
4. 768 × 1024: `signin-showcase` visible, `signin-hero` count 0, no lottie request.
5. 390 × 844: `signin-showcase` count 0 or hidden; keyboard test (sign-in.md §5.4) still green.
6. #25 and #26 unchanged and green; `e2e/au-signin-hero.spec.ts` green at 1440 × 900 (and run once at 1920 × 1080).
7. Navbar (shell tests): active link has `aria-current="page"` and `font-semibold`; `sidebar-search` opens the
   palette; on `hasTouch` the sidebar rows measure ≥ 44 px tall at 1280 × 800.
8. Motion audit: add `sign-in showcase` (no animation > 300 ms except the hero pass, which the hero spec owns) and
   `sidebar pill` cases to `e2e/motion-audit.spec.ts`.
