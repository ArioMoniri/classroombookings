# Settings & auth — login, API key (masked + test), model picker, solver defaults, users/roles

Owner: design-pro (B). Routes `/login`, `/settings/{general,ai,solver,users,terms}`. Backend:
`POST /auth/login`, `GET /auth/me` (JWT bearer), `GET/PUT /settings` (API key write-only, masked on read;
`anthropic_model`, `solver_default_time_limit` …), `POST /settings/test-ai` (1-token verification),
users table `email, password_hash, role ∈ {ADMIN, PLANNER, VIEWER}, is_active`, `settings` rows with
`is_secret` encrypted via Fernet. Model default `claude-sonnet-5-5`, admins may pick `claude-opus-5-5`.
Licences: `navigation-shell.md §9`.

---

## 1. References

| # | Reference | Borrow |
|---|---|---|
| 1 | [Tana – sign in with error banner](https://mobbin.com/screens/b27499c8-03d4-4894-a25d-4d7f5c6630b6) | Centered 400 px card, logo above, red alert at top of the form ("Invalid email or password"), labelled fields, "Forgot your password?" right-aligned on the password label row, full-width dark primary, "Go back" link |
| 2 | [Cursor – dark login](https://mobbin.com/screens/8ccf775a-474f-4c37-9ced-a480df4f1929) | Same layout in dark theme; magic-link alternative button above fields (→ our future SSO button slot) |
| 3 | [OpenAI Platform – inline field error](https://mobbin.com/screens/5fe45e48-5dbc-4903-8ca4-ecfe5507ace9) | Error text under the field with icon; email shown read-only with "Edit" |
| 4 | [Expedia – "Keep me signed in"](https://mobbin.com/screens/182271ba-42b2-4d24-9776-6a00936105af) | Checkbox with explanatory sub-text about shared devices |
| 5 | [Fireflies – Developer settings API key](https://mobbin.com/screens/b9680340-94f9-42ad-8145-1c998862a228) | Masked key `••••••••` with copy + eye icons, "Reset" button; secret key field with regenerate + eye |
| 6 | [Twingate – Connect 1Password (API key modal)](https://mobbin.com/screens/390ee4a7-6f67-40c9-9f5d-0c6f1f741502) | Explanation paragraph + "Learn more" link, API Key field with eye toggle, single "Connect" CTA |
| 7 | [Cofounder – Stripe keys card with status badges](https://mobbin.com/screens/8d35c689-2898-470c-a4e1-cf9375d261e2) | "Not Connected" badge + **Recheck** button; per-environment status chips `KEYS ✗ Missing` |
| 8 | [LangChain – Missing API key inline prompt with model dropdown](https://mobbin.com/screens/bf5c0b07-f753-4000-a6e9-69b99c003075) | When the key is missing, the feature itself shows "Missing API key — get one" + model select + masked input + Save — reuse on `/generate` |
| 9 | [Steep – data source connection with "Test and save"](https://mobbin.com/screens/e6729530-deb2-4891-a6a8-b031c3375a85) | Grey helper card "Test and save your data source connection" with a disabled Continue until tested |
| 10 | [Vercel – settings sections with per-card Save](https://mobbin.com/screens/a54fee2e-b776-42c2-bd7c-93f7e223c87c) | Section cards: title, description, control, footer with "Learn more" + **Save** (disabled until dirty) |
| 11 | [Vercel – Add env var side panel with Sensitive toggle + validation](https://mobbin.com/screens/a6b44af9-ef61-4e1c-bab2-829a9d847ceb) | Side panel form, "Sensitive" switch, red validation text — model for "Add user" and "Add term" |
| 12 | [Vercel – Danger zone](https://mobbin.com/screens/0654916b-7bfa-44f7-9854-bd8fc7bb1865) | Red-tinted footer card "Delete project" |
| 13 | [Claude – model picker with descriptions + toggle](https://mobbin.com/screens/a584de73-9ae1-4c5c-851d-73c1131e0a21) | Model list with one-line descriptions and a "More models ›" row |
| 14 | [Canny – API page with secret shown in plain text](https://mobbin.com/screens/125cbbf9-7d3c-4355-9d6c-0223592f8f34) | Anti-pattern: never render the secret in plain text after save |

## 2. Information architecture

```
/login                     card: logo, "SmartSched'e giriş", email, password (eye), keep-me-signed-in, [Giriş yap], TR/EN + theme at footer
/settings                  left secondary nav (Vercel #10): General · AI · Solver · Users · Terms  (+ "Danger zone" at bottom of General)
  /general                 University name, default locale, time zone (Europe/Istanbul fixed, shown), period grid (read-only table of P1–P18), CRBS connection (DSN, Test), export defaults
  /ai                      API key card · Model card · Behaviour card (language of explanations, max tokens, auto-propose constraints on import) · Usage card (last 30 days calls/tokens if tracked)
  /solver                  Defaults: time limit (s), seed, workers, stability on/off, default weights table (kind → weight), "Reset to defaults"
  /users                   table + "Invite user" side panel; roles; deactivate; reset password
  /terms                   terms table (code, kind, dates, weeks, active) + week calendar editor (kind per week LECTURE/EXAM/HOLIDAY/MAKEUP)
```
VIEWER: no /settings link; PLANNER: General (read), Solver (edit), Terms (edit), AI (no key); ADMIN: all.

## 3. Interaction spec

### 3.1 Login
- Layout (Tana #1): centred card 400 px, 24 px padding, logo + product name, `h1` "Giriş yap". Fields: Email (`type=email`, `autocomplete=username`, `inputmode=email`), Password (`autocomplete=current-password`, eye toggle button `aria-pressed`, `aria-label="Show password"`), checkbox "Bu cihazda oturumum açık kalsın" with sub-text (Expedia #4) → refresh token 30 d vs session.
- Submit: button shows spinner + "Giriş yapılıyor…", disabled; `Enter` submits. On 401: red alert at top (Tana #1) "E-posta veya şifre hatalı", focus moves to the alert (`role="alert"`), password cleared, email kept. On 423/429: "Çok fazla deneme · 5 dk sonra tekrar deneyin" with countdown. On network error: "Sunucuya ulaşılamıyor" + retry.
- Field-level validation only on blur/submit (OpenAI #3): invalid email format, empty password.
- Success: redirect to `?next=` or `/dashboard`; toast "Hoş geldiniz, Fatih Bey" (first name from `/auth/me`).
- Footer: TR | EN segmented, theme toggle, version, "Forgot password?" → if no email service configured, shows "Ask an administrator to reset it" (open question §7.1).
- Future SSO slot (Cursor #2): a secondary button "Üniversite hesabıyla giriş" above the fields, hidden until LDAP is configured.
- Motion: card fade+rise 200 ms on mount; error shake 300 ms (transitions.dev "Error state shake", free) — disabled under reduced motion (alert still appears).

### 3.2 Settings shell
- Secondary nav left (200 px; on < 1024 becomes a top `Tabs` scroller). Each page = stack of **section cards** (Vercel #10): title (h2), description (muted), control(s), footer row: helper link left, **Save** right (disabled until dirty; `⌘S` saves the focused card). Cards save independently (`PUT /settings` with only the changed keys).
- Dirty-state guard: navigating away with unsaved cards opens `AlertDialog` "Unsaved changes in AI settings — Discard / Keep editing".
- Success: card footer shows "Saved · 2 s ago" with a check morph (transitions.dev "Spinner to check", free); error: red text under the control + toast.

### 3.3 AI settings — API key card (the critical one)
- Explanatory text (Twingate #6): "SmartSched uses your own Anthropic API key. It is encrypted at rest and never shown again after saving." + "Get a key ↗" link (console.anthropic.com).
- States:
  - **Not set**: status badge `Not connected` (Cofounder #7); input `type=password` with eye toggle (shows while typing only), placeholder `sk-ant-…`, paste-friendly (trim whitespace), client-side shape check `^sk-ant-[A-Za-z0-9_-]{20,}$` → inline hint, not blocking. Buttons: **Test connection** (secondary; enabled when input non-empty; calls `POST /settings/test-ai` with the *typed* key in the body — backend should accept a transient key for testing) and **Save** (disabled until a successful test, Steep #9 pattern; can be overridden via "Save without testing" in the ⋯ menu).
  - **Testing**: button spinner "Testing…" ≤ 10 s; result chip: ✓ "Connected · claude-sonnet-5-5 · 212 ms" or ✗ with mapped reasons (401 "Invalid key", 403 "Key has no access to this model", 429 "Rate limited — key works", network "Can't reach api.anthropic.com from the server (proxy/egress?)").
  - **Set**: read-only masked display `sk-ant-••••••••••••••••••••••••••••3f9a` — backend returns only the last 4 chars (`GET /settings` masked). Buttons: **Recheck** (test with stored key), **Replace key** (reveals the input again), **Remove** (danger, confirm dialog, explains that Generate-with-preferences and chat stop working). No copy button, no eye on the stored key (Canny #14 anti-pattern; Fireflies #5 shows copy — we deliberately omit it).
  - Last check line: "Last verified 2026-10-07 09:12 by admin@… · OK".
- Audit: every change logs `who/when` (no key material) shown in a small "History" expander.
- Security notes for implementation: field `autocomplete="off"`, `spellcheck=false`; never put the key in URL/query/logs/analytics; mask in React DevTools by keeping it in a ref, not state, until submit; clear the input after save; `PUT /settings` body over HTTPS only.

### 3.4 Model card
- Radio-list (Claude #13): `claude-sonnet-5-5` "Fast, good for parsing & chat (default)" · `claude-opus-5-5` "Strongest reasoning for complex constraints · higher cost" · "Custom model id" (text input, ADMIN only, validated by a test call). Each option shows an approximate cost hint ("$ / $$$"), no real prices in UI (they change; link to pricing page instead).
- Below: "Explanation language" (Follow UI / TR / EN), "Auto-propose constraints after import" switch, "Max tokens per chat reply" number (default from backend), "Temperature" hidden (fixed low) — open question §7.3.
- Save per card; changing model triggers a quick test (`test-ai` with model) and shows the chip result.

### 3.5 Solver defaults
- Fields: Time limit (s) slider 30–900 with input; Seed (number, "random" checkbox); Workers (1–8, hint "CPU cores on server: 4"); Stability default (switch); LNS repair passes (0–5).
- **Default weights table**: rows = soft constraint kinds from `GET /constraints/kinds` (honour requested room, same building per day, capacity fit, minimise room changes across weeks, evening in B/C …), columns: Weight (1–10 slider), Enabled by default (switch), Description. "Reset to defaults" with confirm. These seed new terms; per-term overrides live in the constraints drawer (generate-and-chat §3.4).
- Validation: time limit × workers warning if > 30 CPU-min ("Long runs block the queue").

### 3.6 Users & roles
- Table (TanStack): Avatar/initials, Name, Email, Role (badge: ADMIN `primary`, PLANNER `secondary`, VIEWER `muted`), Status (Active/Inactive dot), Last login, ⋯ (Edit, Reset password, Deactivate/Activate, Delete).
- "Invite user" opens a right side panel (Vercel #11): Name, Email, Role radio with 1-line permission summary each, Temporary password (generated, shown **once** with copy + "I've shared it" checkbox before closing) or "Send e-mail" if mail configured. Validation inline in red.
- Role summary (also shown as a help popover):
  | | VIEWER | PLANNER | ADMIN |
  |---|---|---|---|
  | View timetables/reports | ✓ | ✓ | ✓ |
  | Import, edit requests, generate, chat | – | ✓ | ✓ |
  | Rooms/terms master data | – | ✓ | ✓ |
  | AI key, model, users | – | – | ✓ |
- Guards: cannot deactivate yourself; cannot remove the last ADMIN (button disabled with tooltip).
- Session card at the bottom: "Your sessions" list (device, last seen, "Sign out everywhere").

### 3.7 Terms
- Table + "New term" panel: code (`2026-BAHAR` pattern validated), name, kind, start/end dates (beUI Date Range Picker), week count (derived, editable), period grid preset (default 18-period). Week calendar editor: 16 rows, kind `Select` per week (LECTURE/EXAM/HOLIDAY/MAKEUP), label; bulk "Mark weeks 15–16 as EXAM". "Set active" action with confirm (affects everyone's term switcher).

### 3.8 Keyboard & touch
`⌘S` save focused card · `Esc` close panel (asks if dirty) · Tab order follows visual order; eye toggle after the input. Touch: side panels become full-screen Sheets; sliders have ±buttons beside them for precision.

### 3.9 Motion
Card save check morph 250 ms; panel slide 200 ms; error shake 300 ms (login only); badge colour fade 150 ms. Reduced motion: none of the above except opacity.

## 4. Component list

| Component | Source | Licence | Note |
|---|---|---|---|
| Form, Input, Label, Checkbox, RadioGroup, Switch, Slider, Select, Tabs, Card, Alert, AlertDialog, Sheet, Table, Badge, Tooltip, Separator | shadcn/ui | MIT | `npx shadcn@latest add form input label checkbox radio-group switch slider select tabs card alert alert-dialog sheet table badge tooltip separator` |
| Forms & validation | `react-hook-form` + `zod` (`@hookform/resolvers`) | MIT | schema per card; TR/EN messages via next-intl |
| Password input with eye toggle | build `components/ui/password-input.tsx` (shadcn Input + button) | ours | `aria-pressed`, keeps caret position |
| OTP Input (focus ring, error shake, success check) | beUI https://beui.dev/components/blocks/otp-input | MIT | reserve for future 2FA (reverseui "Multifactor Authentication" is paid reference) |
| Date Range Picker | beUI https://beui.dev/components/motion/date-range-picker | MIT | terms |
| Switch (spring) | beUI https://beui.dev/components/motion/switch | MIT | optional skin over Radix Switch; keep Radix semantics |
| Animated Alert | beUI https://beui.dev/components/motion/alert | MIT | login error banner |
| Error state shake, Spinner to check morph, Success check | transitions.dev free set | custom (commercial OK, keep comment) | copy CSS |
| Password Meter, Floating Label, Copy Button | kinetics | no licence | reference only; password meter reimplemented with `zxcvbn-ts` (MIT) if we add strength rules |
| Role-Based Access Control, Multifactor Authentication, Bot Protection | reverseui | paid | reference only for the role matrix visual |
| Input OTP | kobra (Free set, personal use only) | personal-only | do not import; use beUI or shadcn `input-otp` (MIT) |
| Accessible form patterns | astryx.atmeta.com (MIT, StyleX) | MIT | read their Checkbox/Switch a11y notes; do not install (styling mismatch) |

## 5. Responsive behaviour

| Width | Login | Settings |
|---|---|---|
| 360 | card full-width with 16 px gutters, no outer card border (flat), footer controls stacked | secondary nav → top horizontal `Tabs` scroller; cards full-width; Save buttons full-width; side panels = full-screen Sheets; weights table → list rows with slider under label |
| 768 | 400 px centred card | nav as tabs; cards 720 px |
| 1280 | 400 px card; optional right-side illustration/quote column (Unify-style split) | left nav 200 px + 760 px content |
| 1920 | same (do not scale the card) | content max 880 px; usage charts can sit in a second column |

## 6. Accessibility
- Login: `<form>` with `aria-describedby` to the alert; alert `role="alert"` receives focus on error; password toggle is a button with `aria-pressed` and `aria-controls`; "keep me signed in" has visible helper text linked via `aria-describedby`.
- Autocomplete tokens set correctly so password managers work; no `autocomplete=off` on login (only on the API key field).
- Settings cards: each `<section aria-labelledby>`; Save button state announced ("Saved"); dirty state not colour-only (text "Unsaved changes").
- API key: input labelled "Anthropic API key"; masked display is text with `aria-label="API key ending in 3f9a"`; test result chip in `role="status"`.
- Sliders: Radix semantics + numeric input twin; weights table rows have `<th scope="row">`.
- Users table: role badges include text; ⋯ menu is a `DropdownMenu` with full keyboard support; destructive items marked `aria-describedby` warning.
- Contrast and focus rings per navigation-shell §6; forms work at 200 % zoom (no fixed heights).

## 7. Open questions
1. Password reset: no mail service in ARCHITECTURE — admin-only reset with a one-time password shown once? (spec assumes yes)
2. `POST /settings/test-ai` must accept a transient key in the request body (not only the stored one) so the admin can test **before** saving; confirm with backend-engineer. Also return model id + latency.
3. Expose temperature/max tokens at all, or keep them in backend config only? Spec hides temperature.
4. Session policy: JWT lifetime, refresh tokens for "keep me signed in", and whether VIEWER accounts are even needed in v1.
5. Should PLANNER be allowed to see (masked) whether an AI key is configured? Spec: yes (status badge only), so they understand why chat is disabled.
6. LDAP/SSO (ROADMAP backlog) — keep the button slot or remove until planned?
