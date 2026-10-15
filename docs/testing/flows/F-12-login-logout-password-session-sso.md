# F-12 · Login, logout, password change, session expiry; later SSO

Personas: **staff**, **academician**, **admin**, limited admin (landing page). Viewports: desktop, tablet, phone.
Owner decisions (ROADMAP "Owner decisions 2026-10-15 ~22:45: channels + login" and "~22:50: identity and sign-up"):
- **Who signs in how.** Everyone, admins included, signs in with the institution's **Microsoft Entra ID** (direct OIDC with Authlib, pinned to the university tenant). Users are identified by `(tid, oid)`, never by e-mail. Roles are SmartSched's (an admin mapping, off by default). A **local break-glass admin** is kept.
- **Sign-up has two doors only:** (a) self sign-up through Entra, always as the lowest role; (b) an admin invite, bound on the first Entra login whose verified UPN/e-mail equals the invite (one-time, audited, expires after 30 days). There is no local self-registration.
- **Credentials.** Everything is built and tested **without real university credentials** (fake OIDC / mock transports in the backend tests). The owner enters the real values later, never in chat.
- **Design.** `docs/design/v2/sign-in.md` ("Microsoft first, one quiet second door"; 30 Playwright checks in its §15).

State on `d2ed4a8` (HEAD while this file was revised):
- Backend `app/api/v1/sso.py` + `app/services/sso.py` exist: providers, start, callback, exchange, admin config, invites, bind, mappings.
- The sign-in page of the spec is **not built** (dedicated SSO/channels frontend agent, after the shell sweep).
- No test stack has a tenant. So S11–S17 test everything **up to the redirect to Microsoft**, plus the guards, the invites and the break-glass rules. S18, a full round trip, is `BLOCKED: no tenant credentials (owner gets them from IT)`.
- **Spec vs backend mismatch, to resolve before the frontend lands:**
  - sign-in.md §15.1 expects the button to point at `/api/v1/auth/oidc/microsoft/start?next=…` and errors as `?error=<code>`;
  - the backend serves `/api/v1/auth/sso/entra/start?return_path=…` and redirects errors to `/login?sso_error=<code>`.
  - Testers check whatever the built page uses, end to end. A dead link is a FAIL. The suggester files the mismatch once (owner area `approval-first`/`integrations` → SSO frontend agent).

Local login (S01–S10) is testable now.

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

### SSO: Microsoft Entra ID (credential-free login)

Preconditions for S11–S18:
- Fake but well-formed values (never real ones): tenant `11111111-2222-3333-4444-555555555555`, client id `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`, secret `test-secret-not-real`.
- `org.public_url` set to the stack's web URL, so the redirect URI is well formed.
- **Never follow the redirect to login.microsoftonline.com.** Read the `Location` header only.

**S11 · admin · configure the provider, and the guards on the configuration**
- UI target: Yönetim › Kimlik doğrulama shows a Microsoft Entra section (tenant, client id, secret, "Kendi kaydı" on/off with the default role, invite days, role mapping off, "yalnız Microsoft" for non-admins). Today: `BLOCKED: SSO admin UI not built` if absent.
- API:
  - `PUT /auth/sso/admin/entra {"enabled":true,"tenant_id":"1111…","client_id":"aaaa…","client_secret":"test-secret-not-real"}` → 200. The response **never contains the secret** (masked or `has_secret: true`). `GET` after it: the same.
  - `tenant_id` = `common`, `organizations`, `consumers`, or the consumer tenant `9188040d-6c67-4c5b-b112-36a304b66dad` → **422** each.
  - `default_role_id` = the ADMIN role → **422** (self sign-up is always the lowest role).
  - limited.admin (F-11) → **403** on every `/auth/sso/admin/*` write.
  - One audit row per change, without the secret.

**S12 · anyone · the login page offers Microsoft first** [UI pending: sign-in.md]
- `GET /auth/sso/providers` → enabled, with the TR/EN texts of the error codes.
- UI target (sign-in.md §6.1, §15 1–7):
  - one link **"Microsoft ile giriş yap"** (EN "Sign in with Microsoft") in Microsoft's colours, ≥ 44 px (≥ 48 px on touch);
  - the hints "… iş veya okul hesabınızı kullanın …" and "İlk girişinizde hesabınız **{role}** olarak açılır. Rolünüzü yalnızca bir yönetici değiştirebilir.";
  - the collapsed disclosure **"Kullanıcı adı ve parolayla giriş yap"** with "Yerel ve LDAP hesapları içindir. Bu hesapları yalnızca yöneticiler açar.";
  - no "kaydol / kayıt ol / sign up / register / hesap oluştur" anywhere;
  - the page text never says Azure, Active Directory, Entra or Office 365.
- With SSO disabled (`enabled:false`): no Microsoft link, and the local form is open.

**S13 · anyone · the start redirect is a correct, pinned OIDC request**
- `curl -sS -o /dev/null -D - "$API/auth/sso/entra/start?return_path=/bookings"` (and the URL the UI link uses, if different).
- Expect: **302** to `https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/oauth2/v2.0/authorize?…` with `response_type=code`, the `client_id`, a `redirect_uri` under the stack's public URL ending in `/auth/sso/entra/callback`, a `scope` containing `openid`, `code_challenge_method=S256`, a `code_challenge`, a `state` and a `nonce`. The tenant is the configured one, never `common`.
- With SSO disabled: 302 to `/login?sso_error=not_configured`, and the page shows a Turkish message, not a blank page.
- `return_path=//evil.example` or `https://evil.example` → dropped (the user lands on the role home after sign-in).

**S14 · anyone · the callback refuses what it must**
- `GET /auth/sso/entra/callback?state=forged&code=x` → 302 to `/login?sso_error=failed…` with a reference. The page shows **"Giriş yapılamadı."** with the reference code and focuses the alert.
- `?error=access_denied&state=<a real state from S13>` → the **cancelled** status ("Microsoft girişi tamamlanmadı. Hazır olduğunuzda tekrar deneyin.", `role="status"`, focus not stolen).
- Re-using a state after it was consumed or expired (10 min) → failed.
- `failed` with an unknown code and `failed` with a nonsense code render **byte-identical** text, the reference aside (no enumeration, §15.16).

**S15 · anyone · the one-time ticket**
- `POST /auth/sso/exchange {"ticket":"random"}` → **401**, the generic "invalid or expired sign-in ticket". No user data in the body.

**S16 · admin · invites and binding (door b)**
- Do: invite `davet.test@smartsched.local`, name "D. T.", role TEACHER (`POST /auth/sso/admin/invites`). UI target: the Users screen invite sheet, with the status as "dot + word".
- Expect:
  - listed with an expiry of **30 days** (`invite_days`);
  - limited.admin inviting with role ADMIN → **403** (no escalation);
  - `POST /auth/sso/admin/users/<staff id>/bind` → the staff row shows "Sonraki Microsoft girişinde bağla";
  - deleting the invite makes `/login?invite=<token>` show "Bu davet artık geçerli değil."
- Audit rows for create, bind and revoke.

**S17 · admin · break-glass stays**
- `PUT /auth/sso/admin/entra {"oidc_only_non_admins":true}` while the seeded admin has a local password → 200.
  - Non-admins no longer see the password door (or it is hidden behind `?method=local` for admins only).
  - The admin can still sign in locally with `?method=local`.
  - staff local login → refused with the generic 401 text.
- Disable the seeded admin's local password (or make it SSO-only) while it is the only break-glass admin → **422**. The last break-glass admin can never be locked out.
- Switch `oidc_only_non_admins` back off for the other flows.

**S18 · a real Entra round trip** — `BLOCKED: no tenant credentials`
- Kept for the round with IT's registration (`docs/deploy/sso-entra.md`):
  - the first sign-in creates a TEACHER (door a) and shows `/welcome` "Hesabınız oluşturuldu";
  - an invited address binds once;
  - an e-mail that equals an existing local account without an invite is refused (`account_exists`);
  - a guest or other-tenant account gets the `tenant` error;
  - sign-out and disabling revoke the session;
  - nothing of the IdP is stored except oid, tid, the e-mail and the display name.

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
6. SSO is configured with pinned-tenant guards. The start redirect is a correct PKCE request. Forged callbacks and tickets are refused without enumeration. Invites follow no-escalation and expire. A break-glass admin always remains. The full round trip waits for the tenant credentials.
7. MOBILE.md passes on `/login`, `/login/change-password`, `/reset-password` and `/profile` at 390 and 768.

## Earlier issues to re-verify here

U-02, U-03, U-05, U-20, U-21, M-38, M-39 (installer copy, on a fresh stack only), M-42, the TR/EN flip between routes (UI review §3 Shell).
