# F-12 · Login, logout, password change, session expiry; later SSO

Personas: **staff**, **academician**, **admin**, limited admin (landing page). Viewports: desktop, tablet, phone.
Owner request (ROADMAP "Approval-first bookings + user channels + credential-free login"): login through a provider "so SmartSched never handles the users' credentials". The provider is **not chosen**. The research doc `docs/product/2026-10-15-integrations-options.md` does not exist on `b75047b`. So the SSO part (S11–S13) is written as acceptance criteria and reported `BLOCKED: SSO provider not chosen`. Everything about local login is testable now.

## Preconditions

1. Restore the snapshot (seeded accounts, profile language tr).
2. Session-expiry stack (S08 only): a second stack started with a short token lifetime. Use your re-test ports (README §4.2), its own `REC_WORKDIR`, and `REC_SNAPSHOT=1` with a copy of your snapshot files:
   ```bash
   JWT_EXPIRE_MINUTES=2 REC_WORKDIR="$SCR/flow-stack-<persona>-ttl" REC_API_PORT=… REC_WEB_PORT=… REC_SNAPSHOT=1 bash "$SNAP/scripts/record/stack.sh" up
   ```
   (`stack.sh` passes the variable to uvicorn through the environment. The setting is `jwt_expire_minutes`, default 720.)
3. SMTP sink running (S07 reset codes).
4. A browser context per persona. Clear cookies between personas (`context.clearCookies()`).

## Steps

**S01 · anyone · the login page**
- Do: `/login`.
- See: **"Giriş yap"**, the subtitle **"Derslik rezervasyonu ve planlama"** (not "Planlama ofisi erişimi", U-20). Fields **"E-posta veya kullanıcı adı"** (`login-identifier`) and **"Şifre"** (`login-password`). A show/hide toggle **"Şifreyi göster"** / **"Şifreyi gizle"** with `aria-pressed`. **"Parolanızı mı unuttunuz?"** (`forgot-password`). The TR/EN toggle (`locale-toggle`) and the theme toggle. The version (`app-version`). No "LDAP" text (U-21).
- The placeholder does not repeat the label (UI review). The field borders reach ≥ 3:1 contrast (`--border-control`).

**S02 · anyone · wrong input**
- Do: submit empty.
- See: a text message per field ("E-posta veya kullanıcı adı gerekli" or equivalent), linked by `aria-describedby`, not only red outlines (U-20).
- Do: right e-mail, wrong password.
- See: the alert **"E-posta, kullanıcı adı veya şifre yanlış."**, focus moves to the alert, the password field is cleared, and a short shake runs (no shake under reduced motion).
- Do: type the password with Caps Lock on (`page.keyboard.down("CapsLock")`).
- See (target, U-20): "Caps Lock açık" near the field.
- Do: log in as a disabled user (F-11 S01).
- See: the **same** message and the same status as a wrong password (M-42).
- Rate limit (`app/core/ratelimit.py`: 10 failures per identifier, 50 per address, per window): the 11th wrong attempt for one identifier answers **429**. The UI shows a Turkish "too many attempts" message with the wait time, not the wrong-password text. After the window the correct password works again. Use a throwaway identifier (`ds.test@…`), so the persona accounts are not locked for other flows.

**S03 · each persona · successful login and landing**
- Do: correct credentials, Enter submits.
- See: the button reads **"Giriş yapılıyor…"** while busy. The toast **"Hoş geldiniz, {name}"** shows initials. The landing page:
  - **staff and academician → `/bookings`** (U-02, A-01; not `/timetable`, not `/dashboard`);
  - **admin → `/dashboard`**;
  - **limited admin → the first page they may use** (M-38).
- The landing page makes 0 requests that answer 403 (README §4.7) and shows no "yetkiniz yok" toast (U-03).
- The UI language is the **profile** language from the first paint. No TR → EN flip between routes in one session (UI review; `687a91e`).
- `?next=`:
  - `/login?next=/my-bookings` lands on `/my-bookings`;
  - `?next=//evil.example` and `?next=https://evil.example` land on the role's default page, never off-site.

**S04 · each persona · logout**
- Do: the user menu (`user-menu`) → **"Çıkış yap"** (`logout`).
- See: `/login`. The cookie `smartsched_token` is gone (`context.cookies()`). Browser Back twice ends on `/login?next=…`, never on a page with data. A direct URL (`/my-bookings`) → `/login?next=/my-bookings`.
- API: the old token (copied before logout) → **401** on `GET /auth/me`. The logout revokes it, it does not just delete the cookie.

**S05 · staff · change the password**
- Do: `/profile` → the password section, one column of 360 px fields (`140ded9`).
  - Wrong current password → **"Mevcut şifre yanlış ya da yeni şifre eskisiyle aynı."**
  - New ≠ repeat → **"İki şifre aynı değil."**
  - New shorter than 8 → the hint **"En az 8 karakter, mevcut şifreden farklı."** shown as an error.
  - Correct → submit.
- See: the session ends **visibly**. Either a redirect to `/login` with the notice (`login-session-notice`) **"Parolanız değiştirildi. Yeni parolanızla yeniden giriş yapın."**, or the session stays valid. Never an app shell with false empty lists, "…" as the avatar, or "missing bearer token" (U-05).
- Do: log in with the old password → refused. With the new one → OK.
- Other sessions: a second context logged in as staff before the change → its next action leads to `/login` with **"Oturumunuz sona erdi. Kaldığınız yerden devam etmek için yeniden giriş yapın."**
- Restore the seed password at the end (`Flow-2026!pw`), so other flows still work.

**S06 · staff · forced password change**
- Do: admin edits the staff user → "Şifre değişikliği iste" (`force_password_reset: true`). Staff logs in.
- See: `/login/change-password` **"Yeni şifre belirleyin"**, **"Devam etmeden önce yöneticiniz şifrenizi değiştirmenizi istiyor."**, fields **"Mevcut şifre"** (hint "Geçici şifreyle girdiyseniz boş bırakın."), **"Yeni şifre"**, **"Yeni şifre (tekrar)"**, the button **"Kaydet ve devam et"**. After saving: **"Şifre değiştirildi"**, then the `next` target. Every other route redirects back here until the change is done.

**S07 · staff · forgotten password with a code**
- Do: `/reset-password` → request with the staff e-mail.
- See: a neutral answer (the same for an unknown e-mail). The sink receives the code mail at once (`deliver_now`; README §4.5). The expiry time is stated in the mail or on the page (U-21: not "bir süre sonra").
- Do: "Kodum var" → a wrong code → refused in Turkish. The right code + a new password → success → log in with it. The hint reads "En az 8 karakter.", with no LDAP text (U-21).
- Admin path: the admin issues a reset code from the user row menu (`reset-token`, dialog `token-dialog`). The code is shown once.

**S08 · staff · session expiry** (TTL stack of precondition 2)
- Do: log in. Open `/my-bookings`. Wait **130 s** without input. Then click "Geçmiş", and open the bell.
- See: a redirect to `/login?next=/my-bookings` (or a modal re-login) with **"Oturumunuz sona erdi. Kaldığınız yerden devam etmek için yeniden giriş yapın."** No false empty state ("Yaklaşan rezervasyonunuz yok"), no raw English error, no stack of toasts. After logging in again you are back on `/my-bookings`.
- A half-filled form (the book sheet with a note typed) survives the re-login, or the user is warned before losing it. Report which.
- API: requests with the expired token → 401, and the client handles each 401 once (one redirect, not a loop).

**S09 · admin · LDAP path stays safe**
- Do: Yönetim › Kimlik doğrulama (`/admin/authentication`): enter a directory at `ldap://127.0.0.1:1` → "Bağlantıyı dene".
- See: **"Dizine ulaşılamıyor"** (as the persona run found). Local login keeps working. No password field value is echoed back after save.

**S10 · all · 390 px login**
- See MOBILE.md. In particular: the e-mail field has `type="email"` or `inputmode="email"`, plus `autocomplete="username"`. The password field has `autocomplete="current-password"`, and `new-password` on the change forms. The keyboard does not cover the submit button (M-12). The show/hide toggle is ≥ 44 px.

### Later: SSO (credential-free login) — `BLOCKED: SSO provider not chosen`

Acceptance criteria for the login builder, to be run once the owner picks a provider. Record them as BLOCKED rows now, so the suggester keeps them visible.

**S11 · login with the institution's IdP**
- `/login` shows one button per configured provider ("Google Workspace ile giriş", "Microsoft 365 ile giriş", or the institution IdP's name). No button for a provider that is not configured (no dead button today: check that `/login` has none).
- An OIDC authorization-code flow with PKCE and `state` / `nonce` checks. SmartSched stores **no password** for SSO users: the `users` row has no password hash, or it is unusable.
- An e-mail that is not in SmartSched, or is outside the allowed domains → refused with a Turkish message, unless just-in-time creation is switched on (then the role is the institution's default, never ADMIN).
- An existing local account with the same verified e-mail is linked only after an admin allows it, or after the user proves both. Never silently.

**S12 · logout and session**
- Logout ends the SmartSched session (and optionally the IdP session, as configured). A disabled SmartSched user cannot log in through SSO either.
- The session lifetime follows `jwt_expire_minutes`, and expiry behaves as S08.

**S13 · admin controls and audit**
- The admin can require SSO and switch local login off, except for a break-glass admin account. Every SSO login, refusal and link writes an audit event. The provider's client secret is entered once and never shown again (like the SMTP password).

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- The login card fills the width with 16 px gutters. No horizontal scroll (M-01). Fields are ≥ 44 px tall and use a 16 px font (iOS zoom guard: below 16 px, focusing zooms the page).
- The submit button sits directly under the password. With the keyboard open (M-12) it stays visible, or the form scrolls it into view.
- The user menu on phone (in the tab bar's "Diğer" sheet or the top bar) lists Profil, Ayarlar, Çıkış yap as ≥ 44 px rows.
- The change-password and reset forms are one column, and the error texts are visible without scrolling past the keyboard.
- **Tablet 768:** the card is centred and at most 480 px wide.

## Flow acceptance

1. Wrong input gives specific, accessible Turkish messages. A disabled account cannot be told apart from a wrong password.
2. Each role lands on a page it can use, with no 403 noise. `next` works and cannot redirect off-site.
3. Logout revokes the token. Back and direct URLs lead to login.
4. A password change and an expired session end in a clear re-login, never in a broken shell.
5. Reset codes arrive through the SMTP sink and work once.
6. SSO criteria S11–S13 stay listed as BLOCKED until the provider decision. Then they become this flow's steps.
7. MOBILE.md passes on `/login`, `/login/change-password`, `/reset-password` and `/profile` at 390 and 768.

## Earlier issues to re-verify here

U-02, U-03, U-05, U-20, U-21, M-38, M-39 (installer copy, on a fresh stack only), M-42, the TR/EN flip between routes (UI review §3 Shell).
