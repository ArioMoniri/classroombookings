# F-12 · Login, logout, password change, session expiry; later SSO

Personas: **staff**, **academician**, **admin**, limited admin (landing page). Viewports: desktop, tablet, phone.
Owner decisions (ROADMAP "Owner decisions 2026-10-15 ~22:45: channels + login" and "~22:50: identity and sign-up"):
- **Who signs in how.** Everyone, admins included, signs in with the institution's **Microsoft Entra ID** (direct OIDC with Authlib, pinned to the university tenant). Users are identified by `(tid, oid)`, never by e-mail. Roles are SmartSched's (an admin mapping, off by default). A **local break-glass admin** is kept.
- **Sign-up has two doors only:** (a) self sign-up through Entra, always as the lowest role; (b) an admin invite, bound on the first Entra login whose verified UPN/e-mail equals the invite (one-time, audited, expires after 30 days). There is no local self-registration.
- **Credentials.** Everything is built and tested **without real university credentials** (fake OIDC / mock transports in the backend tests). The owner enters the real values later, never in chat.
- **Design.** `docs/design/v2/sign-in.md` ("Microsoft first, one quiet second door"; 30 Playwright checks in its §15).

Revised against `deb38315` (round 2, T-R2-35): the sign-in page of `docs/design/v2/sign-in.md` **is built** (`components/auth/*`, `signin.*` strings). S01/S02/S05/S08 quote the built texts; the older `auth.*` / `glass.auth.*` wording ("Şifre", "Parolanızı mı unuttunuz?", "E-posta, kullanıcı adı veya şifre yanlış.", "Oturumunuz sona erdi…") is gone from the page. Where an admin screen still quotes the old label (S07), that is noted, not a finding.

State on `d2ed4a8` (an earlier revision of this file; kept for the SSO history):
- Backend `app/api/v1/sso.py` + `app/services/sso.py` exist: providers, start, callback, exchange, admin config, invites, bind, mappings.
- The sign-in page of the spec is **not built** (dedicated SSO/channels frontend agent, after the shell sweep).
- No test stack has a tenant. So S11–S17 test everything **up to the redirect to Microsoft**, plus the guards, the invites and the break-glass rules. S18, a full round trip, is `BLOCKED: no tenant credentials (owner gets them from IT)`.
- **Start URL and parameters (checked against the code on 2026-10-16, round-1 drift R1-A-39):** the Microsoft link is `/api/v1/auth/sso/entra/start?next=<path>` (`components/auth/signin-model.ts` `START_PATH`/`startUrl`; backend `app/api/v1/sso.py` `start(next, invite, prompt, login_hint)`). There is no `return_path`. Refusals and callback errors redirect to `/login?error=<code>[&ref=…]` (`app/services/sso.py` `error_url`; `/profile?error=…` for a link), never `sso_error`. The sign-in page reads `?error=` (`signin-model.ts`). sign-in.md §15.1's `/auth/oidc/microsoft/start` path is the older name: test the built page, end to end. A dead link is a FAIL.

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
- See: **"Giriş yap"** (`signin.title`), the subtitle (`signin-subtitle`) **"Ders programı, sınavlar ve derslik rezervasyonu"** (with an organisation name: **"{org} · ders programı, sınavlar ve derslik rezervasyonu"**; never "Planlama ofisi erişimi", U-20). Fields **"Kullanıcı adı veya e-posta"** (`login-identifier`, placeholder `ad.soyad`) and **"Parola"** (`login-password`). A show/hide toggle **"Parolayı göster"** / **"Parolayı gizle"** with `aria-pressed`. **"Parolamı unuttum"** (`forgot-password`). The TR/EN toggle (`locale-toggle`) and the theme toggle. The version (`app-version`). No "LDAP" text in the open form (U-21; the sentence "Yerel ve LDAP hesapları içindir…" belongs to the SSO disclosure of S12 and is shown only while SSO is enabled).
- With SSO enabled (S11) the local form sits behind the disclosure **"Kullanıcı adı ve parolayla giriş yap"** (`login-disclosure`): open it first. With SSO off (the stack default) the form is open.
- The placeholder does not repeat the label (UI review). The field borders reach ≥ 3:1 contrast (`--border-control`).

**S02 · anyone · wrong input**
- Do: submit empty.
- See: a text message per field, **"Kullanıcı adı veya e-posta gerekli"** (`login-identifier-required`) and **"Parola gerekli"** (`login-password-required`), linked by `aria-describedby`, not only red outlines (U-20).
- Do: right e-mail, wrong password.
- See: the alert **"Kullanıcı adı, e-posta veya parola yanlış."** (`login-error`), focus moves to the alert, the password field is cleared, and a short shake runs (no shake under reduced motion).
- Do: type the password with Caps Lock on (`page.keyboard.down("CapsLock")`).
- See (U-20): **"Caps Lock açık"** (`caps-lock`) near the field.
- Do: log in as a disabled user (F-11 S01).
- See: the **same** message and the same status as a wrong password (M-42).
- Rate limit (`app/core/ratelimit.py`: 10 failures per identifier, 50 per address, per window): the 11th wrong attempt for one identifier answers **429**. The UI shows **"Çok fazla deneme. {n} dakika sonra tekrar deneyin."** with the wait time, not the wrong-password text. After the window the correct password works again. Use a throwaway identifier (`ds.test@…`), so the persona accounts are not locked for other flows.

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
- Other sessions: a second context logged in as staff before the change → its next action leads to `/login` with the notice (`login-session-notice`) **"Oturumunuzun süresi doldu. Yeniden giriş yaptığınızda kaldığınız sayfaya dönersiniz."**
- Restore the seed password at the end (`Flow-2026!pw`), so other flows still work.

**S06 · staff · forced password change**
- Do: admin edits the staff user → "Şifre değişikliği iste" (`force_password_reset: true`). Staff logs in.
- See: `/login/change-password` **"Yeni şifre belirleyin"**, **"Devam etmeden önce yöneticiniz şifrenizi değiştirmenizi istiyor."**, fields **"Mevcut şifre"** (hint "Geçici şifreyle girdiyseniz boş bırakın."), **"Yeni şifre"**, **"Yeni şifre (tekrar)"**, the button **"Kaydet ve devam et"**. After saving: **"Şifre değiştirildi"**, then the `next` target. Every other route redirects back here until the change is done.

**S07 · staff · forgotten password with a code**
- Do: `/reset-password` → request with the staff e-mail.
- See: a neutral answer (the same for an unknown e-mail). The sink receives the code mail at once (`deliver_now`; README §4.5). The expiry time is stated in the mail or on the page (U-21: not "bir süre sonra").
- Do: "Kodum var" → a wrong code → refused in Turkish. The right code + a new password → success → log in with it. The hint reads "En az 8 karakter.", with no LDAP text (U-21).
- Admin path: the admin issues a reset code from the user row menu (`reset-token`, dialog `token-dialog`). The code is shown once. The dialog's hint still quotes the old login label ("Kullanıcı kodu oturum açma sayfasında “Parolanızı mı unuttunuz?” altında girer.", `crbs.users.resetWhere`) while the page reads "Parolamı unuttum": known wording drift of the T-R2-06 family (lane A); note it, no new finding.
- Page copy on `deb38315`: the hint reuses the LDAP sentence, the requested text says "bir süre sonra" and a short code is refused in English → T-R2-06 (lane A). Until it is ticked, report those three as `FAIL (T-R2-06)` and nothing else on this step.

**S08 · staff · session expiry** (TTL stack of precondition 2; without that second stack the step is `SKIP (no TTL stack)`, as both round-1 and round-2 reported. Round 3 starts the TTL stack: README §4.2 reserves the +200 ports for it)
- Do: log in. Open `/my-bookings`. Wait **130 s** without input. Then click "Geçmiş", and open the bell.
- See: a redirect to `/login?next=/my-bookings` (or a modal re-login) with the notice (`login-session-notice`) **"Oturumunuzun süresi doldu. Yeniden giriş yaptığınızda kaldığınız sayfaya dönersiniz."** No false empty state ("Yaklaşan rezervasyonunuz yok"), no raw English error, no stack of toasts. After logging in again you are back on `/my-bookings`.
- A half-filled form (the book sheet with a note typed) survives the re-login, or the user is warned before losing it. Report which.
- API: requests with the expired token → 401, and the client handles each 401 once (one redirect, not a loop).

**S09 · admin · LDAP path stays safe**
- Do: Yönetim › Kimlik doğrulama (`/admin/authentication`): enter a directory at `ldap://127.0.0.1:1`. In the **"Bağlantıyı dene"** section fill the test account fields (any user name and password: the button is **disabled until both are typed**, `ldap-settings.tsx`; the hint says nothing is saved and no account is created), then press **"Bağlantıyı dene"** (`getByRole('button', { name: 'Bağlantıyı dene' })`; while busy it reads "Denetleniyor…" with `aria-busy`).
- See: **"Dizine ulaşılamıyor"** (as the persona run found). Round 2 reported this step NOT RUN because the button was disabled: the two test fields were empty. Local login keeps working. No password field value is echoed back after save.

**S10 · all · 390 px login**
- See MOBILE.md. In particular: the e-mail field has `type="email"` or `inputmode="email"`, plus `autocomplete="username"`. The password field has `autocomplete="current-password"`, and `new-password` on the change forms. The keyboard does not cover the submit button (M-12). The show/hide toggle is ≥ 44 px.

### SSO: Microsoft Entra ID (credential-free login)

Preconditions for S11–S18:
- Fake but well-formed values (never real ones): tenant `11111111-2222-3333-4444-555555555555`, client id `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`, secret `test-secret-not-real`.
- `org.public_url` set to the stack's web URL, so the redirect URI is well formed.
- **Never follow the redirect to login.microsoftonline.com.** Read the `Location` header only.

**S11 · admin · configure the provider, and the guards on the configuration**
- UI target: Yönetim › Kimlik doğrulama shows a Microsoft Entra section (tenant, client id, secret, "Kendi kaydı" on/off with the default role, invite days, role mapping off, "yalnız Microsoft" for non-admins). On `deb38315` only the SSO settings card of lane E (T-R1-35: `sso-default-role` picker, invites) exists, not the provider form: report the UI part as `BLOCKED: SSO admin UI not built` and run the API part (round 2 did so).
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
- `curl -sS -o /dev/null -D - "$API/auth/sso/entra/start?next=/bookings"` (the same URL the "Microsoft ile giriş yap" link uses: compare its `href`).
- Expect: **302** to `https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/oauth2/v2.0/authorize?…` with `response_type=code`, the `client_id`, a `redirect_uri` under the stack's public URL ending in `/auth/sso/entra/callback`, a `scope` containing `openid`, `code_challenge_method=S256`, a `code_challenge`, a `state` and a `nonce`. The tenant is the configured one, never `common`.
- With SSO disabled: 302 to `/login?error=failed&ref=…` (at 3598c8c `not_configured` is shown as the public code `failed`; lane E's T-R1-35 gives it its own code, e.g. `not_enabled`: expect that code once T-R1-35 is ticked), and the page shows a Turkish message, not a blank page.
- `next=//evil.example` or `next=https://evil.example` → dropped (only a same-origin path is kept; the user lands on the role home after sign-in).

**S14 · anyone · the callback refuses what it must**
- `GET /auth/sso/entra/callback?state=forged&code=x` → 302 to `/login?error=failed&ref=…`. The page shows **"Giriş yapılamadı."** with the reference code and focuses the alert.
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

**S18 · a real Entra round trip** — `BLOCKED: no tenant credentials` (every round so far; stays BLOCKED until IT's registration is in `docs/deploy/sso-entra.md`)
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
