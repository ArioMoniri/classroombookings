# Welcome guide per role: research (2026-10-17)

Ledger `welcome-guide-res-2026-10-17`. Owner request (2026-10-17): "a welcome guide showing and explaining the parts for
users, admins and the other levels, as in classroombookings, and in the one you built. Research, as of October 2026,
any repo or service for building these animations or welcome guides; use the designer and motion-designer agents,
transitions.dev and the Mobbin connector; add it to the roadmap without interfering with other phases."

The design is in [docs/design/v3/welcome-guide.md](../design/v3/welcome-guide.md). The tickets are WG-01…WG-11 in
[docs/ROADMAP.md](../ROADMAP.md) under "Welcome guide per role (owner request 2026-10-17)".

---

## 0. BLUF

- **Neither app has a welcome guide today.** classroombookings (CRBS) has a three-step installer, side-panel help
  texts on a few setup screens, a login message and a changelog dot. SmartSched has the `/setup` installer, the
  `/welcome` page after a first SSO sign-in, the "Neler yeni" changelog sheet (`whats-new.tsx`, per-user "seen" on the
  server), the keyboard-shortcuts sheet and the Lottie empty states. It has no tour, no checklist and no role-specific
  introduction. (`/onboarding` is the "Dosyalardan kur" data-intake wizard, not user onboarding.)
- **Library: React Joyride 3.2 (MIT)**, loaded lazily and only while a tour runs, in controlled mode with our own
  tooltip component. It is the only maintained open-source option that ships all of the following, verified in its
  published 3.2.0 build: a focus trap, Escape, `aria-modal`/`aria-labelledby`/`aria-describedby`, an `aria-live`
  region, a `locale` object, a custom `tooltipComponent` and a controlled `stepIndex`. It supports React 16.8–19 and
  needs about 20 kB gzip (`@floating-ui/react-dom` is already in our tree). The fallback is **driver.js 1.10.1** (MIT,
  7.7 kB gzip, no dependencies, released 2026-10-15, and it now has a checklist add-on). It has no focus trap, so we
  would have to add one.
- **Not allowed:** Shepherd.js 14+ and Intro.js 8 are **AGPL-3.0** (a commercial licence is sold separately).
  Tour Kit 3 (`@tour-kit/*`) is **BUSL-1.1**. Onborda (last release 2024-12) and Reactour (2025-05) are not
  maintained. NextStep 2.3 (MIT, 5.6 kB) is Next-native, but its card shows no ARIA or focus handling in its build.
  OnboardJS is a headless flow engine at 1.0 release candidate, and `@onboardjs/react` has no licence field.
- **Hosted services** (Userpilot, Appcues, Pendo, Chameleon, Userflow, Intercom Product Tours) inject a third-party
  script that collects user identifiers and behaviour. Most host in the US, and some offer EU hosting on higher plans.
  Under KVKK Art. 9 (amended by Law 7499, in force 2024-06-01), each one would be a cross-border transfer that needs a
  standard contract notified to the Board within 5 business days, plus an Art. 10 privacy notice change. That is
  avoidable, so we keep everything first-party: a server-side table, no third-party script.
- **Animation:** motion v14 (already in the app) for every UI transition. lottie-react `LottieLight` (already in the
  app, used by `components/ui/empty-state.tsx`) for the one hero per role. No Rive, no dotLottie switch, no View
  Transitions or scroll-driven animations in this feature (reasons in §4).
- **transitions.dev (free plan):** 9 of the 32 free recipes fit. They are re-implemented and retimed to our tokens
  (≤ 300 ms, no blur on glass). 4 were considered and rejected (§5). **No hosted Motion Agent polish fix was used:**
  this pass is design-only (there is no app code to polish), and `TRANSITIONS_AGENT_LICENSE` is not set in this
  session's shell. The one fix is reserved for WG-09 (the hero sheet open), once code exists.
- **Mobbin worked.** I searched 4 queries, covering 23 apps. The patterns we adopt are in §6.

---

## 1. What exists

### 1.1 classroombookings (CRBS, `crbs-core/`, PHP / CodeIgniter)

| Surface | Where | What it does | Relevance |
|---|---|---|---|
| Installer | `crbs-core/application/modules/install/controllers/Install.php` (steps `config → info → checks → complete`, session flags `step_config`, `step_info`, `step_checks`) | First-run: DB config, organisation and admin account, requirement checks | Already ported as SmartSched `/setup` (`components/admin/setup-wizard.tsx`) |
| Side help panels | `views/sessions/add_side.php`, `views/holidays/add_side.php`, `views/room_schedules/index_side.php`, language keys `session.help.*`, `session.room_schedules.help.*` | Static "what this field means / what changing it breaks" text beside a setup form | This is the CRBS idea of "explaining the parts". We keep it as inline field help. It is not a tour |
| Setup menu | `views/setup/index.php`, groups `users · resources · timetable · setup` | One page that lists every admin area, grouped | The admin's mental model. Our admin welcome cards follow the same four groups |
| Dashboard | `views/dashboard/index.php` (stats + "my bookings" + "room bookings") | Landing page after sign-in | This is where a CRBS user starts. Our checklist lives on the equivalent home |
| Changelog dot | `controllers/Dashboard.php::changelog`, `changelog_status` (per-user "touched") | Unread indicator for release notes | Already ported (`whats-new.tsx`, `GET /org/changelog`, `user.{id}.changelog_viewed_*`) |
| Login message, maintenance message | `language/english/settings_lang.php` (`settings.general.login_message`, `maintenance_mode_message`) | Institution-wide text on the login page or during maintenance | The precedent for "admins edit the texts per institution" |
| Roles | install `data.sql`: Administrator, Teacher (`room.view`, `book_single.create`, view notes) + custom roles | Permission sets, not hard-coded levels | We key the guide on permissions, not role codes (`lib/permissions.ts` rule) |

CRBS has no product tour, coach marks, checklist or role-specific welcome.

### 1.2 SmartSched (`smartsched/`)

| Surface | File(s) | Notes for the guide |
|---|---|---|
| `/setup` first-run installer | `app/setup/page.tsx`, `components/admin/setup-wizard.tsx` | Runs before any user exists. The guide never shows here |
| `/welcome` after a first SSO sign-in | `app/welcome/page.tsx`, `components/auth/welcome-view.tsx` (one-time `sessionStorage` flag, "Welcome check" motion, optional channel link) | Account confirmation, not orientation. **Name clash:** the new guide must not use the `/welcome` route. It runs after `/welcome` hands over to the role's home (`homeFor`) |
| `/onboarding` "Dosyalardan kur" | `components/onboarding/**` | Data intake for planners. It is a checklist item for planners, not part of this guide |
| "Neler yeni" | `components/admin/whats-new.tsx`, `lib/api/crbs.ts` `useChangelog`, backend `api/v1/org.py` `/changelog`, `/changelog/seen` (per-user `Setting` rows `user.{id}.changelog_viewed_at/_version`) | The per-user, server-side "seen" pattern already exists. Feature hints link into it |
| Keyboard shortcuts sheet | `components/shell/shortcuts-sheet.tsx`, user menu `user-menu-shortcuts` | The Help menu group extends this menu |
| Lottie set | `docs/lottie/*.json` (hero-solver, nl-to-rules, file-to-rules, precheck-fix; light + dark), `src/assets/lottie/*`, `components/ui/empty-state.tsx` (`LottieLight`, plays once to the poster frame, poster under reduced motion) | Reused for the planner and admin heroes. Academicians and staff need one new clip (WG-09) |
| Navigation and permissions | `components/shell/nav-config.ts` (`NAV_GROUPS`, `QUICK_RESERVE_ITEM`, `visibleNavGroups`), `components/admin/nav-items.ts`, `lib/permissions.ts` (`hasPermission`, `bookingCapabilities`, "never branch on the role code") | Each tour step anchors to an entry the user can actually see. Audiences are derived from permissions |
| Built-in roles | `backend/app/services/bookings_perms.py` `ROLE_DEFAULTS`: ADMIN (all), TEACHER (`room.view`, `book_single.create`, view notes), PLANNER (`planning.view/edit`, system.*, booking actions), VIEWER (`planning.view`, `room.view`, view others) + custom roles | There is no built-in "approver" or "department admin" role: both are custom permission sets (`approvals.decide`; `book_*.set_user` / `set_department` / `book_recur.create`) |
| Per-user key/value store | `services/bookings_settings.py` `get_user_value` / `set_user_value` (`Setting` key `user.{id}.{key}`) | Good enough for one flag. It cannot give aggregate completion rates or per-step state, so we add a small table (WG-01) |
| Public / kiosk | `app/public/**` (buildings, rooms), slot display | No signed-in user. The guide never shows there |

Greps for `tour`, `coachmark`, `joyride`, `driver`, `shepherd`, `onboarding` (as user onboarding) and `whats-new` found
nothing besides the items above.

### 1.3 Audiences (levels) and their main areas

These come from permissions. A person can match several audiences. Each audience is listed with its signal and the
areas it can see.

| Audience (TR / EN) | Signal (any of) | Main areas |
|---|---|---|
| Öğretim elemanı / Academician | `book_single.create`, no `planning.view`, linked to an `Instructor` (`Instructor.user_id`) | `/reserve`, `/my-bookings`, `/find-room`, `/moderation/me` (Taleplerim), Profil › Takvim (calendar export), Bildirimler |
| İdari personel / Staff | `book_single.create`, no `planning.view`, not linked to an instructor | `/reserve`, `/find-room`, `/bookings`, `/my-bookings`, Bildirimler |
| Onaylayıcı / Approver | `approvals.decide` | `/approvals` (badge), approve / reject with a reason |
| Bölüm yöneticisi / Department admin | `book_single.set_user` or `book_*.set_department` or `book_recur.create` without `planning.edit` | Booking for others, department assignment, recurring series, the department calendar feed (`calendar.department_feed`, CAL-03) |
| İzleyici / Viewer | `planning.view` without `planning.edit` | `/dashboard`, `/timetable`, `/runs`, `/runs/compare`, `/analytics/heatmap` |
| Planlamacı / Planner | `planning.edit` | `/onboarding`, `/import`, `/requests`, `/generate`, `/moderation`, `/programs/new`, `/timetable`, `/runs` |
| Yönetici / Admin | any `setup.*` or `planning.admin` | `/admin/*` (users, roles, rooms, access, sessions, schedules, approval rules, e-mail, KVKK, audit), `/settings`, `/admin/integrations`, `/admin/ai`, `/admin/ops`, the new `/admin/welcome` |
| Kiosk / public | no session | `/public/**`, slot display. **No guide** |

---

## 2. Open-source tour and onboarding libraries (checked 2026-10-17)

Sources: the npm registry (`registry.npmjs.org/<pkg>`: licence, peers, release dates), bundlephobia (min + gzip) and
the published files on jsdelivr (I searched the shipped builds for ARIA and keyboard handling). The GitHub API was not
enabled for this session, so the npm release cadence is the maintenance signal.

| Library | Version (date) | Licence | min / gzip | React 19 · Next 16 App Router | a11y in the shipped build | i18n | Releases in the last 12 months | Verdict |
|---|---|---|---|---|---|---|---|---|
| [React Joyride](https://www.npmjs.com/package/react-joyride) ([README](https://cdn.jsdelivr.net/npm/react-joyride@3.2.0/README.md)) | 3.2.0 (2026-07-09) | MIT | dist `index.mjs` 85 kB → **≈ 20 kB gzip** (measured), plus `@floating-ui/react-dom` (already installed, 2.1.9) | peer `react 16.8 – 19`; the README says SSR-safe and names Next.js; needs a client component | **Focus trap (`useFocusTrap`), Escape, `aria-modal`, `aria-labelledby`, `aria-describedby`, `aria-live`** | `locale` object; custom `tooltipComponent` | 8 (v3 line since 2026-03) | **Chosen** |
| [driver.js](https://driverjs.com/docs/configuration) ([npm](https://www.npmjs.com/package/driver.js)) | 1.10.1 (2026-10-15) | MIT | 27.0 kB / **7.7 kB** | framework-agnostic; imperative; no React peer | popover `role="dialog"`, `aria-labelledby/describedby`, Escape (`allowKeyboardControl`), arrow keys; **no focus trap** | `nextBtnText`, `prevBtnText`, `doneBtnText`, `progressText` `{{current}}/{{total}}` | 8 (very active; new `driver.js/checklist` module with `completeWhen`, progress, events) | **Fallback** (add a focus trap and render our card) |
| [NextStep.js](https://nextstepjs.com/) ([npm](https://www.npmjs.com/package/nextstepjs)) | 2.3.0 (2026-07-20) | MIT | 19.5 kB / 5.6 kB (+ motion, already installed) | Next adapter + `nextRoute` steps across pages; peers `next ≥ 13`, `motion ≥ 11` | no ARIA strings found in `NextStepReact.js`; one Escape handler | a "Localization" docs page | 4 | Watch. A good fit for Next routing, but a11y is not proven |
| [Onborda](https://bestofjs.org/projects/onborda) | 1.2.5 (2024-12-22) | MIT | n/m | peers `framer-motion ≥ 11`, `next ≥ 13`, Radix portal; Tailwind config needed | not documented | none | **0** | Rejected (unmaintained) |
| [Reactour](https://www.npmjs.com/package/@reactour/tour) | 3.8.0 (2025-05-07) | MIT | 20.5 kB / 7.2 kB | React 19 peer | mask + popover; focus handling in `@reactour/utils` | none built in | **0** | Rejected (stalled) |
| [Shepherd.js](https://www.npmjs.com/package/shepherd.js) / react-shepherd | 15.3.0 / 7.0.6 (2026-08-24) | **AGPL-3.0** (dual, commercial licence sold; since v14, see [Drupal issue](https://www.drupal.org/node/3548174), [licence](https://unpkg.com/angular-shepherd@22.0.0/LICENSE.md)) | 44.7 kB / 15.3 kB | React 18/19 peer | good (focus, ARIA) | yes | 5 | **Rejected (licence)** |
| [Intro.js](https://www.npmjs.com/package/intro.js) | 8.6.0 (2026-09-21) | **AGPL-3.0** (commercial licence sold) | 69.4 kB / 19.2 kB | vanilla | basic | yes | 3 | **Rejected (licence)** |
| [OnboardJS](https://dev.to/somafet/building-dynamic-user-journeys-your-guide-to-nextjs-onboarding-with-onboardjs-549e) (`@onboardjs/core` / `react`) | 1.0.0-rc.5 (2026-10-02) | core MIT; **react: no licence field** | n/m | React 18/19 peers | headless (we own the UI) | ours | 6 | Not needed: our flow state is tiny and lives on the server |
| [Tour Kit](https://cdn.jsdelivr.net/npm/@tour-kit/core@1.0.7/README.md) (`@tour-kit/*`) | 3.0.1 (2026-09-24) | **BUSL-1.1** (was MIT in 1.x; pulls `@tour-kit/license`) | 1.8 MB unpacked | Next 13–15 peer (not 16) | claims a11y | yes | active | **Rejected (licence, Next 16 peer)** |
| Own engine (Base UI Popover + motion) | – | ours | ≈ 3–5 kB | native | we write the focus trap, Escape, live region, scroll-into-view and resize tracking | ours | – | Rejected for v1: React Joyride already gives us these, tested by a wider user base |

**Why React Joyride over driver.js.** Both are MIT and maintained. Joyride ships the a11y contract we would otherwise
write and test ourselves (a focus trap inside the step, Escape, `aria-modal`, a live region). Its `tooltipComponent`
lets the step card be our own `Card`/`Button` (Liquid Glass, Turkish copy, our motion tokens). Controlled `stepIndex`
lets the App Router change routes between steps (`router.push`, then wait for the anchor). driver.js costs 12 kB less
gzip, but it renders its own popover DOM, so we would portal React into it and add a focus trap. Keep driver.js as the
fallback if Joyride's overlay fights the Liquid Glass backdrop rules in WG-05's spike. Either way the library sits
behind `components/welcome/tour/engine.ts`, so swapping costs one file.

What we deliberately do **not** take from any library: its default styles, its animations (disabled, because our
motion tokens run the step card and the spotlight ring), its beacons (pulsing dots are motion without meaning), and any
analytics hook.

---

## 3. Hosted onboarding services, and why we avoid them (KVKK)

| Service | What it is | Hosting (public docs) | Notes |
|---|---|---|---|
| [Appcues](https://docs.appcues.com/installation-overview/appcues-us-and-eu-hosting-environments) | No-code flows, checklists, tooltips | US by default; EU environment on request at account creation; no migration between them | Script + identify call with user id and properties |
| [Pendo](https://europeanpurpose.com/alternative-to/pendo) | Guides + product analytics | EU environment exists; the DSR page still describes US hosting (secondary source) | Analytics-first: records every click by default |
| [Userpilot](https://userpilot.com/competitor/appcues/) | Flows, checklists, resource centre | Not stated in the public pages found | Script + identify |
| Chameleon, Userflow | Tours, checklists, launchers | Not found in public pages | Script + identify |
| [Intercom Product Tours](https://costbench.com/software/digital-adoption-platform/intercom-product-tours/) | Tours inside the Intercom messenger; Proactive Support Plus add-on (about $99 a month, third-party figure) | US by default; regional (EU) hosting only on higher plans per [third-party pricing guides](https://qualimero.com/en/blog/intercom-help-center-pricing-2026-complete-cost-guide) | Messenger script on every page |

**Why not:**
1. **KVKK Art. 9 (cross-border transfer).** Since 2024-06-01 (Law 7499), transfers abroad need an adequacy decision
   (there is none for the US), or appropriate safeguards such as a standard contract **notified to the Board within 5
   business days** of signing ([digitalpolicyalert: notification module](https://digitalpolicyalert.org/event/24042-adopted-kvkk-standard-contract-notification-module-for-cross-border-data-transfer),
   [Mondaq guide](https://www.mondaq.com/turkey/data-protection/1565750/guide-on-cross-border-transfers-of-personal-data),
   [Köksal: Law 6698](https://koksal.av.tr/en/legislation/personal-data-protection-law-kvkk-6698/)). Each university
   would carry that paperwork for a feature that needs none.
2. **Art. 10 notice and data minimisation.** These tools identify the user (id, e-mail, role, department) and record
   behaviour. Our guide needs only "this user saw step 3", and that stays in our own database. It goes into the DSR
   export and erasure (WG-03).
3. **Security posture.** A third-party script on every authenticated page widens the CSP and the supply chain. W3-SEC
   has just tightened both.
4. **Fit.** Their editors cannot see our permission model, our Turkish-first copy keys or our motion tokens, and the
   content would live outside our audit log.

What we borrow: the patterns (checklist with progress, resource centre, "launch the tour from a card", per-release
announcements), not the products.

---

## 4. Animation tooling

| Tool | State (Oct 2026) | Use here |
|---|---|---|
| **motion v14** (`motion/react`, MIT; 14.3.0 2026-10-15) | Already the app's motion layer (`@/lib/motion` tokens, `useReduce`, `MotionConfig reducedMotion="user"`) | All UI motion: sheet, step card, ring, checklist, hints |
| **Lottie via lottie-react 3.1.2 `LottieLight`** (MIT; React 19 peer) | Already used by `empty-state.tsx`; ships in the app bundle path that empty states already load (min 748 kB / 196 kB gzip for the full package per bundlephobia; the light build without expressions is what we import, dynamically and client-only) | **The one hero per role** in the welcome sheet: plays once to its poster frame (≤ 3 s); the poster PNG under reduced motion |
| dotLottie (`@lottiefiles/dotlottie-react` 0.20.0, MIT, 168 kB / 34 kB gzip + WASM) | Active; `.lottie` is a zipped, smaller container ([LottieFiles runtimes](https://lottiefiles.com/runtimes)) | Not now: it would be a second player next to lottie-react. Revisit only if the Lottie JSON payload grows past about 150 kB per clip |
| Rive (`@rive-app/react-canvas` 4.36.0, MIT runtime; 228 kB / 64 kB gzip + WASM) | Active; state machines; a separate editor and tool chain | Rejected: a new runtime and authoring tool for one hero; no added value over a 3 s Lottie |
| View Transitions API | Same-document transitions are Baseline "newly available" since Firefox 144 (Oct 2025) ([web.dev](https://web.dev/blog/same-document-view-transitions-are-now-baseline-newly-available?hl=en)); cross-document support is partial in Firefox ([caniuse](https://caniuse.com/cross-document-view-transitions)); React `<ViewTransition>` was still experimental/canary in the sources found ([Chrome blog](https://developer.chrome.com/blog/view-transitions-in-2025)) | Not used. A tour step that changes route uses the existing enter-only route veil (motion pattern 13). The ring re-targets on the new page |
| CSS scroll-driven animations (`animation-timeline`) | Chromium since 115; Safari 26; Firefox status conflicting, so not Baseline ([MDN-style reference](https://modern-css.com/reference/properties/animation-timeline/)) | Not used. No scroll-linked effect in this feature |
| transitions.dev free recipes | 32 free recipes, re-implemented under our tokens (§5) | Sheet, step paging, step card, checklist tick, completion check, badge |

---

## 5. transitions.dev free recipes (scratchpad `transitions/free/*.md`)

Licence: free recipes may be used and modified in commercial projects but not redistributed as a library. We
re-implement them. Any pasted CSS keeps a `/* transitions.dev: <name> */` header (motion_designer skill §7).

| Recipe | Its timing | Use in the welcome guide | Our retime (tokens) |
|---|---|---|---|
| `modal` | open 250 ms / close 150 ms, `cubic-bezier(.22,1,.36,1)` | Desktop welcome sheet open/close | `springs.glassMorph` (settles 281 ms) open; exit 150 ms `--ease-in`; scale .96 → 1 + opacity; no blur |
| `page-side-by-side` | 250 ms slide + fade | Card paging inside the phone sheet ("1 / 4" → "2 / 4") and step-to-step content swap in the step card | `springs.smooth` x ±24 px + opacity; exit 120 ms |
| `tooltip` | in 150 ms, out 50 ms, delay 80 ms | Step card appear on desktop; feature hint popover | in `dur.fast` (120 ms) + `--ease-out`, scale .98 → 1 from the arrow side; out 80 ms; no delay on tour steps (the user asked for it) |
| `checkbox-check` | box 150 ms, draw 350 ms | Checklist item ticks when the server confirms it | box 120 ms; path draw 240 ms (`dur.slow`) |
| `success-check` | 500 ms (opacity, rotate, bob, blur, path) | "Başlarken tamam" once all items are done | `springs.bouncySubtle` 28 px disc + path draw ≤ 285 ms; **drop rotate and blur** |
| `notification-badge` | slide 260, pop 500 ms | The "Yeni" badge on a nav entry with an unseen hint; the dot on Yardım › Neler yeni | pop `springs.bouncySubtle` (≤ 32 px, overshoot allowed); fade 120 ms |
| `skeleton-reveal` | – | The checklist panel while `GET /welcome` loads | motion pattern 12 (skeleton → content crossfade, `smooth`) |
| `texts-reveal` | 500 ms per line, stagger 40 ms, blur | The sheet title + cards on the **first** reveal only | 180 ms per item, 30 ms stagger, max 5 items (≤ 120 ms of stagger), **no blur** (the sheet is glass) |
| `toast` | open 350 / close 250 ms | "Tur bitti. Başlarken listesi kenar çubuğunda." after the last step | The existing sonner toast (pattern 5, `smooth`); no new toast motion |

Considered and rejected: `number-pop-in` (500 ms with overshoot; data never overshoots, so the "2 / 5" counter uses
the `ticker` spring), `accordion` (animates `grid-template-rows`, which is layout; checklist rows expand instantly and
their content fades in 120 ms), `banner-stacking` (hints never stack; one at a time), `panel-reveal` (400 ms, over the
ceiling, and it animates a filter on the panel).

**Hosted Motion Agent:** not used in this pass (design only; no code to scan or polish; the licence variable is unset
in this shell). WG-09 may use the project's one remaining fix for this agent on the hero moment (the welcome sheet
open plus the Lottie hero) and must name it in its report.

---

## 6. Mobbin references (searched 2026-10-17; patterns only, no assets copied)

| App | Screen / flow | Pattern we adopt |
|---|---|---|
| beehiiv | [Browse tutorial flow](https://mobbin.com/flows/2e01960d-3001-4150-9de1-f4e1fa95a825) | A "Get ready" checklist card with a progress bar ("0/5 steps completed") **and** a small welcome card with "Remind me later / Let's go". The tour step "2 of 7" has Back / Next and is anchored to a sidebar item. → Our sheet's "Sonra", the checklist on the home page, the step counter |
| Canva | [Completing a guided tour](https://mobbin.com/flows/d3237fe5-9e7c-47ec-89e6-56ccfd951dc1) | A numbered "Get started" list in the sidebar; a 3-step tour ending in "Got it"; dismissible hint cards. → The sidebar checklist pill |
| Calendly | [Starting a tour](https://mobbin.com/flows/fd004182-7143-4654-ab78-eccf171786c9) | An "Introducing the new Calendly" card with "Start the tour"; the last step anchored to Settings with Back / Done ("4 of 4"). → A release hint that offers a tour, never forces one |
| Remote | [Completing a guided tour](https://mobbin.com/flows/563658e4-72a6-4fde-9ba3-ef43d90707e7) | A "Take a quick tour" card **and** per-feature tour cards ("Begin the add hire tour"); a persistent "You are in Product Tour mode · End the Product Tour" bar. → Per-feature mini tours; "Turu bitir" always visible |
| Quicken | [Completing a tour](https://mobbin.com/flows/9711eadf-7e8f-4007-80c8-e5283615e212), [what's new](https://mobbin.com/screens/c9908794-a4c6-46aa-93cf-bb23e9432b72) | A welcome card with an illustration and "No thanks / Show me around"; "5 of 5" then "Close tour"; a "Now available" release modal with one CTA. → Two equal-weight choices on the sheet |
| Lovable, Microsoft Loop, Relume, HubSpot | [Lovable](https://mobbin.com/screens/9429ba3f-25d0-444d-b04c-5dba81377619), [Loop](https://mobbin.com/screens/45627560-4212-4ea2-90c6-fe432422c857), [Relume](https://mobbin.com/screens/25ffe8ee-9460-48a7-8bfe-4254314fde3d), [HubSpot](https://mobbin.com/screens/a2b89a62-9aa4-46af-9938-265ea73d1202) | "What's new" as a modal: Lovable lists 4 changes with icons and one "Check it out"; HubSpot uses tabs and "1/4" paging. → We do **not** add a modal for releases; our release hint is one small, anchored, non-modal card linking to "Neler yeni" |
| Hootsuite, HoneyBook, Vanta, Google Workspace, Slite, Apollo, Adaline | [Hootsuite](https://mobbin.com/screens/5aff7542-0a89-481d-af47-2b0d2ca78098), [HoneyBook](https://mobbin.com/screens/7c915d6b-2a99-4eb0-956d-e7a3a97bb265), [Vanta](https://mobbin.com/screens/d6c8a960-3253-4ca4-b4aa-06e902fa0e4e), [Google Workspace](https://mobbin.com/screens/05a829a2-525b-4a6e-911a-f4d5e2e5b9ce), [Slite](https://mobbin.com/screens/22beb365-0245-4ea3-aeb8-b073da62df0a), [Apollo](https://mobbin.com/screens/0a060199-a61f-42f2-bb2e-149ba62e6282), [Adaline](https://mobbin.com/screens/8ad4a415-bff7-4350-91af-75519784b729) | Checklists: segmented progress ("4/6 Explored", Hootsuite), "6/7 completed" with a sidebar mini-progress (HoneyBook, Vanta "15/20", Slite "71 % completed", Apollo "22 % Completed"), "Mark as done" for items the app cannot detect (Google Workspace), locked later items (Adaline). → Count "2 / 5" plus a bar; auto-detect where possible; "Bitti olarak işaretle" only for view-only items; no locked items (a teacher may book before linking a channel) |
| MD Vinyl, Mesh, Binance, Whatnot, Taco Bell, Rocket Money (iOS) | [MD Vinyl](https://mobbin.com/screens/df87f8e0-d810-4593-bb39-8b0a01a3c493), [Mesh](https://mobbin.com/screens/eddbcaf5-e84e-49c2-9a17-ea528204eb81), [Binance](https://mobbin.com/screens/f33ee12d-0477-403f-8f1f-08f8388e135b), [Whatnot](https://mobbin.com/screens/65bf9641-dffc-464c-a55b-673d73c77bea), [Taco Bell](https://mobbin.com/screens/5e08c1e9-ab7d-4736-9139-72b3a4355e03), [Rocket Money](https://mobbin.com/screens/e3e4bc57-5e3f-46ab-9ff8-2e9e9cde28e9) | Phone coach marks: a wide card just above the tab bar pointing at one tab ("2/3 · Next", MD Vinyl; "Skip" + arrow, Mesh); "1 / 4 · Skip · Next" (Binance); step dots under a carousel (Taco Bell, Rocket Money). → Our phone step = bottom sheet above the target with dots, "Turu bitir" and 48 px buttons |
| GoDaddy, Front, HoneyBook, Calendly (empty states) | [GoDaddy](https://mobbin.com/screens/6edb9213-e44d-4874-8e2c-e56570e3106e), [Front](https://mobbin.com/screens/907d6f99-e771-4cf7-96e9-22c87e8e7c31), [HoneyBook](https://mobbin.com/screens/c6ec68e2-664b-4bb0-88a0-03df3d6d3166), [Calendly](https://mobbin.com/screens/6fa055d8-a490-46f3-bd23-2378028bf727) | Empty states that coach: one sentence on what the page is for, one primary action, a "Learn more" link (Front adds a side explainer card). → Our empty states get a "Bu sayfa ne işe yarar?" line and one action; we do not add tours to empty pages |

What we avoid from these references: confetti and emoji-heavy headlines, illustration-led modals for every release,
auto-starting tours, locked checklist steps, and floating launchers over the phone tab bar (they violate Liquid Glass
rule G1).

---

## 7. Decisions carried into the design

1. Server-side state per user (table `welcome_progress`), shared across devices; never localStorage-only. Only a
   session-scoped "already auto-showed something this session" flag lives in `sessionStorage`.
2. Audiences come from permissions (plus the instructor link), computed on the server. No role codes.
3. One automatic interruption per session at most: the welcome sheet **or** one feature hint. The tour starts only
   when the user asks for it.
4. React Joyride 3.2 behind our own engine interface, with our card, our motion and Turkish copy keys.
5. Admin control: on/off per part, texts per audience (TR/EN, versioned, with "show again"), completion rates for
   groups of at least 5 people only, and audit log entries.
6. Kiosk/public and `/setup` never show a guide.
