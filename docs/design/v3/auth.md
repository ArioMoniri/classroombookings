# Sign-in, two-step verification and passkeys (TR + EN)

Owner request 2026-10-18 ("design the login pages, with motion design and input-box design … two-factor auth; adding
passkeys; the login providers; for users whom admins added by e-mail, an admin can reset a user's 2FA, or send a
password-reset link by e-mail"). Ledger `auth-ux-2026-10-18`. Research and sources:
[`docs/research/2026-10-18-auth-ux.md`](../../research/2026-10-18-auth-ux.md) (cited here as S1…S9, C1…C7, M1…M13).

This spec **extends** [`v2/sign-in.md`](../v2/sign-in.md) (institution sheet, door 1 / door 2, notices, URL contract)
and [`integrations.md`](integrations.md) §6 (equal provider buttons). Where it changes them it says "amends". Motion rows
are for [`v2/motion.md`](../v2/motion.md) new §3.19; e-mails follow [`emails.md`](emails.md). Backend lane AU-B
(`docs/research/2026-10-18-auth-backend.md`, AU-xx tickets) owns the API. **This spec is aligned with that research
note (read 2026-10-18)**: TOTP SHA-1/6/30 s with a 32-character Base32 key; 10 × 80-bit recovery codes
`XXXX-XXXX-XXXX-XXXX`; 30-day trusted devices; 5 tries per challenge; second-factor lockout of 15 min, doubling; admin
reset with a reason and an identity-check method; settings `auth.mfa_policy`, `auth.mfa_roles`,
`auth.mfa_grace_days`, `auth.passkeys_enabled`, `auth.passkey_first_factor`; six e-mail kinds. The remaining gaps are
asks A1a–A1g (§17).

Builders: AUX-01…AUX-12 at the end of `docs/ROADMAP.md` ("Sign-in, 2FA and passkeys (owner request 2026-10-18) — UX").

---

## 0. BLUF

- **The sign-in page stays calm and the same shape.** It is the institution sheet with the university logo and name:
  - door 1 is the provider buttons, all of equal weight;
  - door 2 is the quiet "Kullanıcı adı ve parolayla giriş yap".
  Inside door 2, the identifier field also offers **passkeys through autofill** (`autocomplete="username webauthn"`), and
  one secondary button, "Geçiş anahtarıyla giriş yap", sits under the form. Nothing new is added above the fold.
- **Who gets SmartSched's own 2FA: local and LDAP accounts only.** Accounts that sign in with Entra, Google, OIDC or
  SAML are protected by their institution; we never stack a second 2FA on them. Their screens say "Bu hesap
  {sağlayıcı} ile giriş yapıyor".
- **Methods:** authenticator app (TOTP), passkeys, and 10 single-use recovery codes. **No SMS and no e-mail codes.**
  A passkey is a full sign-in on its own. It is also accepted as the second step after a password.
- **The 2FA step** comes after a correct password, in the same sheet. It has:
  - **one real input drawn as 6 slots** (input-otp pattern, MIT), with paste, `autocomplete="one-time-code"` and
    automatic submit on the sixth digit;
  - "Başka bir yöntem" (passkey / recovery code / "Hiçbirine erişemiyor musunuz?");
  - "Bu cihazı 30 gün hatırla", off by default.
- **Profil › Giriş ve güvenlik** (`/profile#security`) has five rows:
  1. Parola.
  2. İki aşamalı doğrulama. Turning it on is one sheet: scan or paste the key, enter a code, save the recovery codes.
  3. Geçiş anahtarları: add, rename, remove; the provider name and icon come from the AAGUID.
  4. Oturumlar ve cihazlar.
  5. Son girişler, behind a disclosure.
  Every change asks for re-authentication first (valid 10 minutes) and sends an e-mail.
- **Admin › Kullanıcılar.** For local accounts there are two actions:
  - "2FA'yı sıfırla": needs a reason and how the person's identity was checked; it is audited, the user gets an
    e-mail, it signs the user out everywhere, and it removes their passkeys unless the admin ticks "koru";
  - "Parola sıfırlama bağlantısı gönder".
  For SSO accounts both actions are **replaced by an explanation row**, not by disabled buttons.
- **Org policy** is a new settings tab, Ayarlar › Giriş güvenliği:
  - 2FA Kapalı / **İsteğe bağlı** (default) / Zorunlu, chosen per role (default role: Yönetici);
  - a grace period of 7 / **14** / 30 days;
  - passkeys on (default), with "Parolasız girişe de izin ver" (backend default off; owner Q9 recommends on);
  - under "Gelişmiş": "Bu cihazı hatırla" Kapalı / 7 / **30** days (ask A1d).
- **Motion:**
  - only free transitions.dev recipes: shake, panel reveal, modal (all three already shipped), plus text swap, icon swap,
    success check and page side-by-side;
  - every moment is ≤ 300 ms and has a reduced-motion fallback;
  - one sign-in hero (reused `hero-solver` Lottie, ≥ 1024 px only, plays once in < 5 s, then rests on the poster frame);
  - one hosted Motion Agent fix is **reserved, not spent**, for that hero (§11.4).
- **E-mails:**
  - AU-B adds six kinds: `mfa_enabled`, `mfa_disabled`, `mfa_reset_by_admin`, `passkey_added`,
    `password_reset_link_by_admin`, `mfa_recovery_code_used`. This spec gives their TR/EN copy.
  - Three more are missing and are asks: `passkey_removed`, `recovery_codes_regenerated`, `mfa_required`.
  - `new_device_sign_in` is reused for "new sign-in" (§8).

## 1. Users and goals

| Who | Goal | Never |
|---|---|---|
| Academician with a Microsoft account (most people) | Press "Microsoft ile giriş yap" and arrive | See SmartSched 2FA, passkey upsells or setup nags |
| Local-account staff or guest (added by e-mail invitation) | Set a password once; sign in fast (passkey); keep the account safe | Lose access because the phone was replaced |
| Administrator | Require 2FA for the people who can change the timetable; help someone locked out, safely and on record | Reset someone by accident, or reset an SSO account that SmartSched cannot control |

Simplicity principle (COMMON.md): one primary action per screen, in plain Turkish; advanced options behind "Gelişmiş";
defaults that work without configuration.

## 2. References (detail in the research note)

| Pattern | Taken from | Licence / use |
|---|---|---|
| One real input with slot UI, paste, one-time-code | input-otp (C1), web.dev OTP form (S9), iOS Acorns / X / Strava (M10) | MIT; Mobbin for structure only |
| Quiet "use a recovery code" link; remember device | n8n, Campsite, Basecamp, Employment Hero (M9) | structure only |
| Scan + enter code side by side; "Can't scan?" | Wellfound (M1), Todoist (M2) | structure only |
| Row per method, one action each | Mistral (M4), Amazon (M7) | structure only |
| Passkey list: provider icon, created, last used, rename, remove | Shop (M6), Amazon (M7), Gemini (M8), web.dev (S6) | structure only; AAGUID list MIT (C4) |
| Re-auth before managing factors | X (M5), OWASP (S2), ASVS 5 V7.5.1 (S3) | — |
| Silent passkey creation after password sign-in | Chrome Conditional Create (S4); no full-page upsell (FIDO, S8) | — |
| Admin reset with consequence sentence; user notified | Salesforce (M13), Okta, Entra (§4.2 of research) | structure only |
| Vocabulary | e-Devlet "İki aşamalı giriş", Microsoft TR "iki aşamalı doğrulama", Apple / Google TR "geçiş anahtarı" | — |

## 3. Key decisions

| # | Decision | Why |
|---|---|---|
| D1 | SmartSched 2FA and passkeys only for `local` and `ldap` accounts; SSO accounts are explained, not offered | The IdP already does MFA (Entra Conditional Access); double prompts and two help desks otherwise |
| D2 | TOTP + passkeys + recovery codes; no SMS, no e-mail OTP | Cost, SIM swap (S1); e-mail is the reset channel so it is not a second factor |
| D3 | Passkey sign-in (only when the policy allows passwordless, `auth.passkey_first_factor`) skips the 2FA step; with it off, passkeys work as the second step only | A passkey with user verification is phishing-resistant multi-factor (AU-B §3) |
| D4 | 2FA counts as "Açık" when the account has an authenticator app **or** at least one passkey; recovery codes are created with the first one | One status word; policy "Zorunlu" is satisfied by either |
| D5 | Code input = one `<input>` drawn as 6 slots (3 + 3) | One name, one tab stop, native autofill and paste (C1, S9); big targets on phones (M10) |
| D6 | No passkey interstitial at sign-in; silent Conditional Create after a password sign-in + a card in Güvenlik | FIDO: prompts during sign-in tested poorly (S8); Chrome guidance (S4) |
| D7 | Re-authentication ("Kimliğinizi doğrulayın") before turning 2FA on/off, new recovery codes, adding/removing a passkey; valid 10 min | OWASP / ASVS (S2, S3) |
| D8 | "Bu cihazı 30 gün hatırla" skips only the second step; password always asked; off by default; revoked one by one or all at once, and by a 2FA reset or turning 2FA off (AU-B §5); asks A1c/A1d add a password change and a policy switch | Owner request vs NIST §5.2 (research §5 item 9) |
| D9 | Admin reset 2FA: reason (10–500 characters, preset chips fill it) + how the identity was checked + audit + e-mail; always signs the user out everywhere; passkeys removed unless "koru" is ticked (not offered for "Hesap ele geçirilmiş olabilir"); an admin cannot reset their own | NIST §4.2 notification, OWASP, Entra's passkey surprise (research §4.2); AU-B §6 |
| D10 | SSO accounts: the two admin actions are replaced by one explanation row; not disabled buttons | Disabled controls hide their reason on touch; the reason is the content |
| D11 | Vocabulary "Parola" (unchanged app-wide); owner question Q1 offers "Şifre" | Consistency with ~100 strings, e-mails and Microsoft TR |
| D12 | Set-password: one field with show/hide, no repeat field; min length from the policy (owner Q2) | NIST S1 (show password, no composition rules); one field fewer |

## 4. Sign-in page (`/login`, amends sign-in.md §4.1 door 2 and §6)

### 4.1 Anatomy (top to bottom inside the sheet; unchanged parts in grey in the wireframes)

1. Brand row: the university logo (admin upload, `alt=""` because the name follows), a hairline, then the SmartSched
   mark and "SmartSched" (sign-in.md §4.1, unchanged).
2. Notice slot: 0–2 notices, ordered error, invite, reason, maintenance, login message (unchanged).
3. "Giriş yap" (large title) + "{org} · ders programı, sınavlar ve derslik rezervasyonu" (unchanged).
4. **Door 1:** the provider buttons (integrations.md §6, unchanged): equal size and weight in the admins' order, at
   most 3 visible, "Diğer giriş yolları (n) ▾", a "Son girişiniz bu yöntemle" chip, and the self sign-up footnote.
5. **Door 2** (the disclosure "Kullanıcı adı ve parolayla giriş yap ⌄"). When open:
   1. **Identifier:** "Kullanıcı adı veya e-posta", `autocomplete="username webauthn"`, `inputmode="email"`,
      `enterkeyhint="next"`.
   2. **Password:** "Parola", with "Parolamı unuttum" on the label row on the right, a show/hide eye, the Caps Lock note
      and `autocomplete="current-password"`.
   3. **Submit:** "Giriş yap" (secondary while door 1 exists; primary when the form is the only door).
   4. **New:** a hairline with "veya", then a **secondary button "Geçiş anahtarıyla giriş yap"** (key icon, full width,
      44/48 px). It is shown only when the policy allows passwordless sign-in (`auth.passkeys_enabled` and
      `auth.passkey_first_factor`, from `GET /org/public`; ask A1e) and the browser has `PublicKeyCredential`.
      With passwordless off, the identifier keeps plain `autocomplete="username"` and no conditional `get()` runs.
   5. The last-method footnote (unchanged), which now also reads "Son girişiniz geçiş anahtarıyla" when the cookie says
      `passkey`.
6. Footer: KVKK, version, TR | EN, theme (unchanged).

Why the passkey button lives in door 2: SmartSched passkeys belong to local accounts (D1), so the button is not an
identity provider. Putting it beside the provider buttons would break their equal-weight rule and confuse SSO
users.

### 4.2 Door rules (amends `doorsFor`)

| Situation | Door 2 on first paint | Passkey autofill |
|---|---|---|
| No identity provider on (local only) | open, form primary (unchanged) | conditional `get()` starts on mount |
| Providers on, last method `local` or **`passkey`** (cookie `smartsched_last_signin`) | open (extends `formOpenInitially`) | starts on mount |
| Providers on, other last method | closed | starts when door 2 opens; aborted when it closes |
| `?method=local` | open (unchanged) | starts on mount |
| Invite link (`?invite=`) | only the invited method (unchanged) | off |
| Offline (`/org/public` failed) | open, form primary | off (no options endpoint) |

The conditional `get()` uses `mediation: "conditional"` with empty `allowCredentials`. It is aborted (AbortController)
when the password form submits, when door 2 closes, or before a Conditional Create (S4).

- **Picking a passkey from the autofill list** signs the person in directly. There is no 2FA step (D3), and the
  "Giriş yap" button shows its busy label.
- **The "Geçiş anahtarıyla giriş yap" button** starts a modal `get()`. The browser's own sheet then offers this device,
  another device by QR code, and security keys. We never draw a QR code for sign-in.

### 4.3 After a successful password sign-in

1. **The account needs a second step** (2FA is on and this device is not remembered): the sheet content moves to the
   **2FA step** (§5). No new page load. The URL becomes `/login/verify`, and the challenge lives in an httpOnly cookie,
   never in the URL.
2. **The policy requires 2FA and the person has none:** the **enrolment notice** (§5.6).
3. **Otherwise** the existing path: the welcome toast, then `next` or `homeFor()`.
4. In every successful case **without** a passkey on this device, when the policy allows passwordless sign-in
   (`passkey_first_factor`) and `getClientCapabilities().conditionalCreate` is true, the page calls **Conditional
   Create** silently (S4).
   - With passwordless off, Conditional Create is not used: a silent passkey would quietly switch on 2FA (D4).
   - Success: the browser shows its own note. We add a toast, "Geçiş anahtarı kaydedildi. Bir dahaki sefere parolasız
     giriş yapabilirsiniz.", and the backend sends `passkey_added`.
   - Failure: no message at all.
   - Ask A1f: a registration endpoint that accepts a conditional-create response (UP/UV flags false, S4) within
     5 minutes of a password sign-in, without a separate password prompt.

### 4.4 "Parolamı unuttum" (`/reset-password`, small amendments)

- The page is unchanged: one identifier field, then the same neutral answer whether or not the account exists.
- **Add one line under the field:** "Kurum hesabınızla (Microsoft, Google…) giriş yapıyorsanız parolanızı kurumunuzun
  sayfasından değiştirin." / "If you sign in with your organisation account (Microsoft, Google…), change your password
  on your organisation's page."
- The link is shown only when local accounts exist (`resetLink`, unchanged).
- **A reset never bypasses 2FA.** After the new password is saved, the next sign-in still asks for the second step. The
  confirm page says so when the account has 2FA: "İki aşamalı doğrulamanız değişmedi; girişte kodunuz yine sorulacak."

### 4.5 Invite and set-password page (`/login?invite=` local, `/reset-password?code=`, admin-sent link)

This is one component, `SetPasswordForm`, used in three places. It amends `local-invite-accept.tsx`.

| Part | TR | EN |
|---|---|---|
| Title | Parolanızı belirleyin | Choose your password |
| Lead | {org} SmartSched hesabınız: **{username}** | Your {org} SmartSched account: **{username}** |
| Hidden username | `<input type="text" autocomplete="username" value="{username}" readonly hidden>` so password managers save the pair | — |
| Field | Yeni parola (show/hide, `autocomplete="new-password"`, `passwordrules="minlength: {n};"`) | New password |
| Hint (always visible, under the field) | En az {n} karakter. Uzun bir cümle de olur; sık kullanılan parolalar kabul edilmez. | At least {n} characters. A long sentence works too; common passwords are refused. |
| Live counter (only below {n}) | {count}/{n} | {count}/{n} |
| Submit | Parolayı kaydet ve giriş yap | Save password and sign in |
| Error: short | Parola en az {n} karakter olmalı. | The password needs at least {n} characters. |
| Error: blocklist | Bu parola çok yaygın ya da sızdırılmış listelerde geçiyor. Başka bir parola seçin. | This password is too common or appears in breach lists. Choose another one. |
| Error: contains username | Parola kullanıcı adınızı içeremez. | The password can't contain your username. |
| Error: link expired / used | Bu bağlantının süresi dolmuş ya da daha önce kullanılmış. Yöneticinizden yeni bir bağlantı isteyin ya da "Parolamı unuttum" adımını kullanın. | This link has expired or was already used. Ask your administrator for a new one, or use "Forgot password". |
| After success | signed in (ask AU-B: accept returns a session) → if the policy requires 2FA: enrolment (§5.6); else Conditional Create (§4.3) | — |

There is no strength meter and there are no composition rules (S1). The repeat field is removed (D12); show/hide covers
the typo risk.

### 4.6 Error and state copy on `/login` (new keys; the existing `signin.error.*` and `signin.local.*` are unchanged)

| Key | When | TR | EN | Tone / focus |
|---|---|---|---|---|
| `signin.passkey.button` | door 2 | Geçiş anahtarıyla giriş yap | Sign in with a passkey | secondary button |
| `signin.passkey.cancelled` | `NotAllowedError` from the button | Geçiş anahtarı kullanılmadı. Yeniden deneyin ya da parolanızla giriş yapın. | No passkey was used. Try again or sign in with your password. | neutral notice, no focus move |
| `signin.passkey.unknown` | server: unknown credential (also `signalUnknownCredential`) | Bu geçiş anahtarı bu hesapta artık kayıtlı değil. Parolanızla giriş yapın; sonra parola yöneticinizden eski anahtarı silebilirsiniz. | This passkey is no longer registered for this account. Sign in with your password; you can then delete the old one from your password manager. | error, focus to the alert |
| `signin.passkey.failed` | other passkey failure | Geçiş anahtarıyla giriş yapılamadı. Parolanızla giriş yapın. (Destek kodu: {ref}) | Couldn't sign in with the passkey. Sign in with your password. (Support code: {ref}) | error, focus |
| `signin.passkey.disabledOrg` | passkey login while the policy is off | Kurumunuz geçiş anahtarıyla girişi kapattı. Parolanızla giriş yapın. | Your organisation turned off passkey sign-in. Sign in with your password. | neutral |
| `signin.local.lastPasskey` | cookie `passkey` | Son girişinizi geçiş anahtarıyla yaptınız. | You used a passkey last time. | footnote |
| `signin.passkey.saved` | Conditional Create success (toast) | Geçiş anahtarı kaydedildi. Bir dahaki sefere parolasız giriş yapabilirsiniz. | Passkey saved. Next time you can sign in without your password. | toast 4 s |
| `signin.reset.ssoLine` | `/reset-password` | (see §4.4) | (see §4.4) | footnote |
| `signin.reset.mfaKept` | reset confirm, account has 2FA | İki aşamalı doğrulamanız değişmedi; girişte kodunuz yine sorulacak. | Your two-step verification hasn't changed; you'll still be asked for your code. | info |

No message names whether an account exists, has 2FA, or has a passkey **before** a correct password (no enumeration).

## 5. 2FA step (`/login/verify`, inside the same sheet)

### 5.1 Anatomy (authenticator app, the default method)

1. Brand row and footer as on `/login`.
2. Title **"İki aşamalı doğrulama"** / "Two-step verification".
3. Account line: "**{masked}** olarak giriş yapılıyor" / "Signing in as **{masked}**" (`ay•••@ornek.edu.tr`), then a
   link "Farklı bir hesap" / "Use another account" (→ `/login`, cancels the challenge).
4. Lead: "Doğrulama uygulamanızdaki 6 haneli kodu girin." / "Enter the 6-digit code from your authenticator app."
5. **Code input** (§10.4): label "Doğrulama kodu" / "Verification code", 6 slots grouped 3 + 3. Focus is in the input on
   arrival (it is the page's only job).
6. Checkbox **"Bu cihazı {n} gün hatırla"** / "Remember this device for {n} days". Off by default. Hint under it: "Yalnızca
   kendi cihazınızda işaretleyin. Parolanız yine sorulur." / "Only on your own device. Your password will still be
   asked." Hidden when the policy sets it to Kapalı.
7. Primary **"Doğrula"** / "Verify" (busy: "Doğrulanıyor…", success: "Doğrulandı"). It also submits automatically on the
   sixth digit (D5); the button stays for people who paste and want to check first, and for screen-reader users.
8. Quiet link row: **"Başka bir yöntem"** / "Use another method" (disclosure, §5.2).

### 5.2 "Başka bir yöntem" (panel opens in place, under the link)

| Row (only those the account has) | Action |
|---|---|
| **Geçiş anahtarı kullan** / Use a passkey | starts a WebAuthn `get()` with this account's credentials; success signs in |
| **Kurtarma kodu kullan** / Use a recovery code | swaps the slot input for the recovery field (§5.3); the link row now reads "Doğrulama uygulamasını kullan" |
| **Hiçbirine erişemiyor musunuz?** / Can't use any of these? | expands a short text (below) |

"Hiçbirine erişemiyor musunuz?" text: "Kurum yöneticinizden iki aşamalı doğrulamanızı sıfırlamasını isteyin. Yönetici
kimliğinizi doğruladıktan sonra yalnızca parolanızla girip yeniden kurabilirsiniz." / "Ask your organisation's
administrator to reset your two-step verification. Once they have confirmed it's you, you can sign in with your
password and set it up again." Plus, when the org has a security contact (settings `security.contact_email`), a line
"İletişim: {contact}".

When the account's only method is the app, the panel shows only "Kurtarma kodu kullan" and "Hiçbirine erişemiyor
musunuz?". When it is passkey-only (D4), the default view is a primary "Geçiş anahtarı kullan" button in place of the
slots, and the panel lists "Kurtarma kodu kullan" and the help.

### 5.3 Recovery code variant

- Label "Kurtarma kodu" / "Recovery code". It is a single text field (§10.3 "recovery").
- Hint: "Kaydettiğiniz kodlardan birini girin. Her kod bir kez kullanılır." / "Enter one of the codes you saved. Each code
  works once."
- There is no automatic submit. The button is "Doğrula".
- The field ignores case, spaces and hyphens, and reads O as 0 and I/L as 1 (AU-B §4). The format is
  `XXXX-XXXX-XXXX-XXXX` (16 Crockford Base32 characters, 80 bits).
- After success, a toast on the first screen: "Bir kurtarma kodu kullandınız. {n} kod kaldı." / "You used a recovery
  code. {n} left." When n ≤ 3 (AU-B §4), it adds an action button: "Yeni kodlar oluştur" → `/profile#security`.
- The backend also sends `mfa_recovery_code_used` (S1 §4.2: recovery causes a notification).

### 5.4 States and copy

| Key | When | TR | EN | Behaviour |
|---|---|---|---|---|
| `signin.mfa.wrong` | wrong TOTP | Kod doğru değil. Uygulamadaki güncel kodu girin. | That code isn't right. Enter the current code from your app. | slots cleared, error state, shake once (§11), focus stays in the input, message under the slots (`aria-describedby`) |
| `signin.mfa.clock` | the 2nd consecutive wrong code | Kodlar telefonunuzun saatine bağlıdır. Saatin otomatik ayarlı olduğundan emin olun. | Codes depend on your phone's clock. Make sure it is set automatically. | added under the error |
| `signin.mfa.recoveryWrong` | wrong or used recovery code | Bu kurtarma kodu geçerli değil ya da daha önce kullanıldı. | This recovery code isn't valid or was already used. | field kept (they may have typed one character wrong) |
| `signin.mfa.tooMany` | 5 wrong attempts on this challenge (server) | Çok fazla hatalı deneme. Güvenliğiniz için yeniden giriş yapın. | Too many wrong attempts. Sign in again to continue. | back to `/login` with this as an error notice (focus) |
| `signin.mfa.expired` | challenge older than 5 min | Doğrulama süresi doldu. Yeniden giriş yapın. | The verification timed out. Sign in again. | back to `/login`, neutral notice |
| `signin.mfa.locked` | second step locked after 5 consecutive failures (AU-B §6: 15 min, doubling, cap 24 h); `Retry-After` gives the minutes | Çok fazla hatalı kod girildi. İkinci adım {n} dakika kilitli; sonra yeniden deneyin ya da kurum yöneticinize başvurun. | Too many wrong codes. The second step is locked for {n} minutes; try again later or contact your administrator. | error, focus to the alert; back to `/login` (the minutes update once a minute, like the password lock) |
| `signin.mfa.offline` | status 0 / 5xx | Sunucuya ulaşılamıyor. Bağlantınızı kontrol edip yeniden deneyin. | Can't reach the server. Check your connection and try again. | slots kept |

### 5.5 Remembered device

- AU-B §5: a 256-bit token that lasts 30 days, returned once and kept by the Next.js route handler in an httpOnly,
  Secure, SameSite=Lax cookie. It is sent to `POST /auth/login` as `X-Trusted-Device`, so the browser never reads
  it. It is bound to the account. On the next password sign-in on that device the 2FA step is skipped.
- The Oturumlar ve cihazlar list (§6.5) shows "2FA {date} tarihine kadar hatırlanıyor".
- Revoked by:
  - "Unutulsun" (one device) or "Hatırlanan tüm cihazları unut";
  - an admin 2FA reset;
  - turning 2FA off.
- A sign-out does not end it (AU-B). Ask A1c: also revoke on a password change.

### 5.6 Enrolment required by the policy (`/login/setup-2fa`, same sheet)

Shown after a correct password when the policy requires 2FA for the person's role and they have none.

| Part | TR | EN |
|---|---|---|
| Title | Hesabınızı iki aşamalı doğrulamayla koruyun | Protect your account with two-step verification |
| Lead | {org}, {role} hesapları için iki aşamalı doğrulamayı zorunlu tutuyor. Kurulum yaklaşık 2 dakika sürer. | {org} requires two-step verification for {role} accounts. Setting it up takes about 2 minutes. |
| Deadline (grace left) | Kurmak için {date} tarihine kadar süreniz var. | You have until {date} to set it up. |
| Deadline (passed) | Devam etmek için şimdi kurun. | Set it up now to continue. |
| Primary | Şimdi kur | Set up now |
| Secondary (grace only; text button) | Daha sonra ({n} gün kaldı) | Later ({n} days left) |

"Şimdi kur" opens the same setup flow as Profil (§6.3) inside the sheet, followed by the passkey option (§6.4) as one
line: "İsterseniz bunun yerine geçiş anahtarı ekleyin." When the grace period has passed the session is
enrolment-only: no other route opens until setup is finished (AU-B).

## 6. Profil › Giriş ve güvenlik (`/profile#security`)

### 6.1 Placement

This is a new section `id="security"` right after the details form and the Microsoft account section, before "Bağlı
kanallar". The existing `PasswordForm` moves inside it as the first row. It is the target of the `new_device_sign_in`
e-mail and of every security e-mail in §8. Section title: **"Giriş ve güvenlik"** / "Sign-in and security".

### 6.2 Rows (local and LDAP accounts)

A grouped list in one glass card (M4, M7): one row per subject. Each row has a title, one status line and one action on
the right; phones stack the action under the text.

| Row | Status line | Action |
|---|---|---|
| **Parola** / Password | Son değişiklik: {date} / Last changed {date}. LDAP: "Parolanız kurum dizininde (LDAP) değiştirilir." | "Değiştir" (opens the existing form in place). LDAP: none |
| **İki aşamalı doğrulama** / Two-step verification | Kapalı · "Girişte parolanıza ek olarak telefonunuzdaki bir kod sorulur." **or** Açık · Doğrulama uygulaması (since {date}) · Kurtarma kodları: {n}/10 kaldı | Kapalı → **"Aç"** (primary tint, the only primary in the section). Açık → "Yönet ⌄" (in-place menu: "Yeni kurtarma kodları oluştur", "Uygulamayı değiştir", "Kapat"; "Kapat" is hidden when the policy requires it, with "Kurumunuz bu hesap için zorunlu tutuyor.") |
| **Geçiş anahtarları (passkey)** | 0: "Parmak iziniz, yüzünüz ya da cihaz PIN'inizle parolasız giriş yapın." ≥ 1: the list (§6.4) | "Geçiş anahtarı ekle" (secondary). Hidden when the policy is off; the row then reads "Kurumunuz geçiş anahtarlarını kapattı." |
| **Oturumlar ve cihazlar** / Sessions and devices | the list (§6.5) | "Diğer tüm oturumları kapat" |
| **Son girişler** / Recent sign-ins | — | a disclosure "Son girişleri göster" (§6.6) |

Passkey card for local users with none and passkeys allowed (M6; replaces any upsell): inside the Geçiş anahtarları
row, two benefit lines ("Parola yazmadan, saniyeler içinde giriş" · "Oltalama sitelerinde işe yaramaz, bu yüzden daha
güvenli") and the "Geçiş anahtarı ekle" button. No colour banner, no illustration.

### 6.3 Turn on 2FA (sheet; right side 480 px at ≥ 1024, full screen below 600)

Before the sheet: **"Kimliğinizi doğrulayın"** (§6.7) if the last re-authentication is older than 10 minutes.

**At ≥ 1024 steps 1 and 2 share one view: the QR sits beside the account line and the manual key, with the code
field below it, so scanning and typing happen on one screen (M1's idea, stacked to fit the 480 px sheet). Step 3 then
replaces them. At 390 one step is shown at a time.** Header: "İki aşamalı doğrulamayı açın" plus "Adım 1–2 / 3" or
"Adım 3 / 3".

| Step | Content | TR copy | EN copy |
|---|---|---|---|
| 1 · Uygulamayı bağlayın | QR 176 px (quiet zone 16, black on white also in dark mode), account line "SmartSched ({org}) · {username}", disclosure "QR kodunu tarayamıyor musunuz?" → the 32-character Base32 key in 8 groups of 4 (two lines), monospace, with "Kopyala" | Telefonunuzdaki doğrulama uygulamasını açın (Microsoft Authenticator, Google Authenticator, 1Password ya da benzeri) ve bu kodu tarayın. | Open the authenticator app on your phone (Microsoft Authenticator, Google Authenticator, 1Password or similar) and scan this code. |
| 1 on a phone | the QR is collapsed (you cannot scan your own screen); **"Uygulamada aç"** (`otpauth://` link) is primary, the key is shown with "Kopyala" | Kurulumu bu telefonda yapıyorsanız "Uygulamada aç"a dokunun ya da anahtarı uygulamaya yapıştırın. | If you're setting up on this phone, tap "Open in app" or paste the key into your app. |
| 2 · Kodu girin | the slot input (§10.4); on success, an inline "✓ Doğrulandı" (status-feasible) and the step content moves to 3 after the check finishes (§11) | Uygulamanın gösterdiği 6 haneli kodu girin. | Enter the 6-digit code the app shows. |
| 3 · Kurtarma kodlarınızı kaydedin | 10 codes in 2 columns, monospace, numbered; actions "İndir (.txt)", "Kopyala", "Yazdır"; checkbox **"Kodları güvenli bir yere kaydettim"**; primary **"Bitir"** (enabled after the tick) | Telefonunuza erişemezseniz bu kodlarla giriş yaparsınız. Her kod bir kez kullanılır. **Bu kodlar bir daha gösterilmez.** | If you lose your phone, you can sign in with these codes. Each code works once. **They won't be shown again.** |

- 2FA is switched on **when the code in step 2 is verified**: the server enables it and returns the codes.
- Closing the sheet in step 3 without the tick asks: "Kodları kaydetmeden kapatılsın mı? İki aşamalı doğrulama açık
  kalır; Profil › Güvenlik'ten yeni kodlar oluşturabilirsiniz." → "Kapat" / "Kodlara dön".
- "Bitir" gives the toast "İki aşamalı doğrulama açıldı." The backend has already sent `mfa_enabled` at step 2.
- A step-2 enrolment that is not confirmed expires after 15 minutes (AU-B §2). The sheet then says "Kurulum süresi
  doldu; yeniden başlayın." and returns to step 1 with a new key.
- `.txt` download: file name `smartsched-kurtarma-kodlari-{org-slug}.txt`; content has a header with the org, the
  username and the date, then the codes.

"Yeni kurtarma kodları oluştur": re-authentication, then a dialog "Yeni kodlar oluşturulsun mu? Eski kodlarınız hemen
geçersiz olur." → "Oluştur" → step 3 view → e-mail `recovery_codes_regenerated` (ask A2: S1 says a replacement
triggers a notice).

"Uygulamayı değiştir": re-authentication, then steps 1–2 again. The old secret stays valid until the new code verifies.

"Kapat": re-authentication, then a dialog "İki aşamalı doğrulama kapatılsın mı? Girişte yalnızca parolanız sorulur.
Kurtarma kodlarınız ve hatırlanan cihazlarınız silinir." → "Kapat" (destructive) → e-mail `mfa_disabled`. When the
account has passkeys, the body adds: "Geçiş anahtarlarınız kalır ve girişte ikinci adım olarak istenir; tamamen
kapatmak için onları da kaldırın." (ask A1g: AU-B to confirm that passkeys keep 2FA on, per D4).

### 6.4 Passkeys list

| Part | Spec |
|---|---|
| Row | provider icon 24 (AAGUID; neutral key glyph if unknown) · **name** (default = provider name: "iCloud Anahtar Zinciri", "Google Parola Yöneticisi", "1Password", "Windows Hello", "Güvenlik anahtarı"; else "{browser} · {os}") · meta "Eklendi {date} · Son kullanım {relative}" or "Hiç kullanılmadı" · tag **"Yalnızca bu cihazda"** when not backed up |
| Actions | overflow "⋯" (44 px) → "Yeniden adlandır", "Kaldır" (destructive) |
| Rename | inline field replaces the name, `maxlength=64`, `enterkeyhint=done`, Enter saves, Escape cancels, focus returns to the row's ⋯ button |
| Remove | re-authentication → dialog "{name} kaldırılsın mı?" body "Bu geçiş anahtarıyla artık giriş yapamazsınız. Cihazınızdaki kopyayı parola yöneticinizden de silebilirsiniz." → "Kaldır" → Signal API `signalAllAcceptedCredentials` → e-mail `passkey_removed` (ask A2) |
| Last second-step method | when removing it would leave a required account with no method: the body adds "Bu, son ikinci adım yönteminiz. Kaldırırsanız bir sonraki girişte yeniden kurmanız gerekir." |
| Add | re-authentication (password, AU-B §3) → `create()` with the server's options (AU-B §3: resident key preferred, user verification preferred, `excludeCredentials` = the account's list, no `authenticatorAttachment`, attestation none) → new row named from the AAGUID and editable at once ("Adı değiştirmek ister misiniz?" inline field, optional) + toast "Geçiş anahtarı eklendi" + e-mail `passkey_added`; if no recovery codes exist yet (D4), step 3 of §6.3 follows |
| Add errors | `NotAllowedError`: neutral inline "Geçiş anahtarı oluşturulmadı." · `InvalidStateError`: "Bu parola yöneticisinde bu hesap için zaten bir geçiş anahtarı var." · limit 10: "En fazla 10 geçiş anahtarı ekleyebilirsiniz; önce birini kaldırın." |

### 6.5 Sessions and devices

- Up to 5 rows, then "Tümünü göster ({n})".
- Each row has:
  - a device glyph;
  - **"{browser} · {os}"**, with the tag "Bu cihaz" on the current one;
  - a meta line: "Son etkinlik {relative} · Giriş: {method_label}" (Parola, Parola + uygulama kodu, Geçiş anahtarı,
    Microsoft…);
  - when the device is remembered, the tag "2FA {date} tarihine kadar hatırlanıyor".
- Row actions:
  - other sessions: "Oturumu kapat";
  - the current one: none ("Çıkış yap" stays in the account menu);
  - a remembered device: "Unutulsun".
- Footer: **"Diğer tüm oturumları kapat"** (secondary destructive). It confirms first: "Bu cihaz dışındaki tüm oturumlar
  kapatılır ve hatırlanan cihazlar unutulur."
- No IP addresses and no map (KVKK, Simplicity). The city appears only if the backend already resolves it for the
  `new_device_sign_in` e-mail.
- **Dependency:** AU-B's research covers trusted devices but not a sessions list or sign-in history (ask A1a). Until
  those endpoints exist, AUX-07 ships this block as **"Hatırlanan cihazlar"**: the trusted devices with "Unutulsun" and
  "Hatırlanan tüm cihazları unut". The sessions rows and §6.6 follow when the API lands.

### 6.6 Recent sign-ins (disclosure)

- The last 20 events (90 days): time, result, method and device. Results: ✓ Başarılı, ✗ Hatalı parola, ✗ Hatalı kod,
  ⚠ Engellendi (too many attempts), "Kurtarma kodu kullanıldı".
- The result is an icon **and** a word; the colour is not the only signal.
- Footer: "Tanımadığınız bir giriş görürseniz parolanızı değiştirin ve diğer oturumları kapatın."

### 6.7 Re-authentication ("Kimliğinizi doğrulayın") dialog

- One field: "Parola". With 2FA on, it also asks for the code, or accepts a passkey through a button "Geçiş anahtarı
  kullan".
- Lead: "Güvenliğiniz için bu değişiklikten önce kimliğinizi doğrulayın." Submit: "Doğrula".
- It is valid for 10 minutes and is reused by every action in the section (ask A1b). If AU-B keeps a password field
  on each call instead, the dialog is shown before each action and passes the password through. The screen is the
  same.
- LDAP accounts: an LDAP password check.
- Errors reuse `signin.local.credentials` and `signin.mfa.wrong`.

### 6.8 SSO accounts (Entra, Google, OIDC, SAML)

The section keeps the same title and replaces the first three rows with one row:

- **Giriş yöntemi:** "{provider_label}" (e.g. "Microsoft (iş veya okul hesabı)").
- Text: "Bu hesap {provider_name} ile giriş yapıyor. Parola ve iki aşamalı doğrulama {provider_name} tarafından
  yönetilir." / "This account signs in with {provider_name}. Your password and two-step verification are managed
  there."

Oturumlar and Son girişler stay. If the account also has a local password (binding), it is treated as local for these
rows.

## 7. Admin › Kullanıcılar (`/admin/users`, amends sign-in.md §13)

### 7.1 List

- **Method cell:** add a tag **"2FA"** (shield glyph + text) after "Yerel" / "LDAP" when 2FA is on: "Yerel · 2FA". When
  the policy requires 2FA and the person has not set it up yet: "Yerel · 2FA bekleniyor ({date})" in the warning tone.
- **Filters:** one new select, "İki aşamalı doğrulama: Tümü / Açık / Kapalı / Bekleniyor". It sits in the existing
  filter row on desktop and in the filters sheet on phones.
- No new column.

### 7.2 Row menu and edit sheet ("Giriş ve güvenlik" section)

The same actions appear in both places. On phones the edit sheet is where admins act.

| Account | Menu items (group "Giriş", after a separator) |
|---|---|
| Local, has e-mail | **"Parola sıfırlama bağlantısı gönder"** · **"2FA'yı sıfırla"** (only when 2FA is on) · "Sıfırlama kodunu ekranda göster" (renamed from "Tek kullanımlık sıfırlama kodu"; kept for people without e-mail or when SMTP is not set up, AU-B §6) |
| Local, no e-mail | "Sıfırlama kodunu ekranda göster" · "2FA'yı sıfırla" · an explanation row "E-posta adresi olmadığı için bağlantı gönderilemez." |
| LDAP | "2FA'yı sıfırla" · an explanation row "Parola kurum dizininde (LDAP) değiştirilir." |
| SSO only (Microsoft, Google, OIDC, SAML) | **one explanation row (not a button):** "Bu hesap {provider_name} ile giriş yapıyor. Parola ve iki aşamalı doğrulama orada yönetilir." / "This account signs in with {provider_name}. Password and two-step verification are managed there." |
| Your own account | the 2FA item is replaced by "Kendi hesabınız için Profil › Giriş ve güvenlik'i kullanın." (link) |

The edit sheet's "Giriş ve güvenlik" block shows: method · 2FA status ("Açık · uygulama + 2 geçiş anahtarı" / "Kapalı" /
"Bekleniyor: {date}") · Son giriş {relative} · then the same actions as buttons, or the same explanation text.

### 7.3 "2FA'yı sıfırla" dialog (AU-B §6: reason 10–500 characters, identity-check method, sessions always ended)

| Part | TR | EN |
|---|---|---|
| Title | {name} için iki aşamalı doğrulama sıfırlansın mı? | Reset two-step verification for {name}? |
| Consequence (one sentence) | Doğrulama uygulaması, kurtarma kodları, geçiş anahtarları ve hatırlanan cihazlar silinir; tüm oturumları kapatılır. {name} bir sonraki girişinde yalnızca parolasıyla girer. | The authenticator app, recovery codes, passkeys and remembered devices are removed, and they are signed out everywhere. {name} will sign in with only their password next time. |
| + when required by policy | …ve iki aşamalı doğrulamayı hemen yeniden kurar. | …and must set up two-step verification again right away. |
| Reason chips (optional, fill the text) | Telefonunu kaybetti ya da değiştirdi · Kurtarma kodlarına erişemiyor · Hesap ele geçirilmiş olabilir | Lost or replaced their phone · Can't reach their recovery codes · Account may be compromised |
| Reason text (required, 10–500 characters, counter) | Gerekçe | Reason |
| Identity check (required select) | Kimliği nasıl doğrulandı? Yüz yüze · Görüntülü görüşme · Bilinen numaradan geri arama · Diğer | How was their identity checked? In person · Video call · Call back on a known number · Other |
| Checkbox (default off; hidden when the "Hesap ele geçirilmiş olabilir" chip is chosen) | Geçiş anahtarlarını koru ({n}) | Keep their passkeys ({n}) |
| Primary (destructive) | 2FA'yı sıfırla | Reset 2FA |
| Secondary | Vazgeç | Cancel |
| Toast | {name} için iki aşamalı doğrulama sıfırlandı. Kişiye e-posta gönderildi. | Two-step verification was reset for {name}. They've been e-mailed. |
| Error 409 `own_account` | Kendi hesabınız için Profil › Giriş ve güvenlik'i kullanın. | Use Profile › Sign-in and security for your own account. |
| Error 409 `sso_account` | Bu hesap {provider_name} ile giriş yapıyor; iki aşamalı doğrulama orada sıfırlanır. | This account signs in with {provider_name}; reset two-step verification there. |
| Error 403 (`guard_privileged`) | Bu kullanıcının güvenlik ayarlarını değiştirme yetkiniz yok. | You don't have permission to change this user's security settings. |

- If the admin's own sign-in is older than the re-auth window, the re-auth dialog (§6.7) comes first.
- Audit `auth.mfa_reset_by_admin` (AU-B) records the actor, target, reason, check method and kept passkeys.
- The user gets `mfa_reset_by_admin` with the admin's name. **It never includes the reason text**, which may hold
  internal notes (ask A1h).

### 7.4 "Parola sıfırlama bağlantısı gönder" dialog (AU-B §6: the existing 24 h token, e-mailed as a link)

| Part | TR | EN |
|---|---|---|
| Title | {name} adına parola sıfırlama bağlantısı gönderilsin mi? | Send a password reset link to {name}? |
| Body | **{masked}** adresine 24 saat geçerli bir bağlantı gönderilir. Mevcut parolası, bağlantı kullanılana kadar çalışmaya devam eder. İki aşamalı doğrulaması değişmez. | A link valid for 24 hours is sent to **{masked}**. Their current password keeps working until the link is used. Their two-step verification is unchanged. |
| Primary | Bağlantıyı gönder | Send link |
| Toast | Bağlantı gönderildi ({masked}). | Link sent ({masked}). |
| 409 `no_email` | Bu kullanıcının e-posta adresi yok. Sıfırlama kodunu ekranda gösterebilirsiniz. (+ button "Kodu göster") | This user has no e-mail address. You can show a reset code on screen instead. |
| 409 `mail_not_configured` | E-posta gönderimi kurulmamış. Ayarlar › Entegrasyonlar › E-posta'dan kurun ya da sıfırlama kodunu ekranda gösterin. | E-mail sending isn't set up. Set it up in Settings › Integrations › E-mail, or show a reset code on screen. |
| 409 `sso_account` | Bu hesap {provider_name} ile giriş yapıyor; parola orada değiştirilir. | This account signs in with {provider_name}; the password is changed there. |
| 409 `directory_account` | Bu hesabın parolası kurum dizininde (LDAP) değiştirilir. | This account's password is changed in the directory (LDAP). |
| 429 | Az önce bir bağlantı gönderildi. {n} dakika sonra yeniden gönderebilirsiniz. | A link was sent a moment ago. You can send another in {n} minutes. |

The admin never sees the link. A new link revokes the older ones (AU-B). The e-mail is `password_reset_link_by_admin`
(§8). Using the link revokes the user's other sessions (existing B-AUTH-11 behaviour).

## 8. E-mails (themed system, `emails.md`; sent by AU-B through `mail.send_kind`, templates in W3-MAIL's files)

**Missing from `app/emails/kinds.py` today:** every 2FA and passkey message, and the admin-sent reset.
- AU-B adds six kinds (its research note §6); this section gives their copy.
- Three more are needed and are **asks (A2)**:
  - `passkey_removed`: S1 §4.5 recommends a notice on invalidation;
  - `recovery_codes_regenerated`: S1 §4.2.1.1 requires a notice when replacement codes are issued;
  - `mfa_required`: the policy start, so people are not surprised at their next sign-in.
- `new_device_sign_in` already covers "new sign-in". It gains the method labels "Geçiş anahtarı" and "Parola +
  uygulama kodu" (ask A2).

| Kind | Status | Footer | Tone | Button → | Placeholders |
|---|---|---|---|---|---|
| `mfa_enabled` | AU-B | `security` | success | `/profile#security` | name, org, when, device |
| `mfa_disabled` | AU-B | `security` | warning | `/profile#security` | name, org, when, device |
| `mfa_reset_by_admin` | AU-B | `security` | warning | `/login` | name, org, actor, when |
| `passkey_added` | AU-B | `security` | info | `/profile#security` | name, org, passkey_name, when, device |
| `password_reset_link_by_admin` | AU-B | `security` (fallback URL under the button, emails.md §5.8) | info | `/reset-password?token=` | name, org, actor, username, valid_hours |
| `mfa_recovery_code_used` | AU-B | `security` | warning | `/profile#security` | name, org, remaining, when, device |
| `passkey_removed` | **ask A2** | `security` | info | `/profile#security` | name, org, passkey_name, when, device |
| `recovery_codes_regenerated` | **ask A2** | `security` | info | `/profile#security` | name, org, when, device |
| `mfa_required` | **ask A2** | `security` | info | `/login` | name, org, role, deadline |
| `new_device_sign_in` | existing | `security` | warning | `/profile#security` | + method_label |

Shared parts (every kind above except `mfa_required` and `password_reset_link_by_admin`):

| | TR | EN |
|---|---|---|
| why | Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz. | This is a security e-mail; it cannot be turned off in notification settings. |
| N | **Bu değişikliği siz yapmadınız mı?** Hemen parolanızı değiştirin ve kurum yöneticinize haber verin. Zaman: {when} · {device}. | **Didn't make this change?** Change your password now and tell your administrator. Time: {when} · {device}. |
| B | Güvenlik ayarlarını aç | Open security settings |

Per kind (S = subject, H = heading, I = intro; the preheader is the I sentence shortened; emails.md §7 rules: siz, no
suffix on a placeholder, the security sentence last):

| Kind | S (TR / EN) | H (TR / EN) | I (TR / EN) |
|---|---|---|---|
| `mfa_enabled` | İki aşamalı doğrulama açıldı / Two-step verification is on | Hesabınız artık daha güvende / Your account is better protected | Merhaba {name}, {org} SmartSched hesabınızda iki aşamalı doğrulama açıldı. Girişte parolanızdan sonra ikinci adım sorulacak. / Hello {name}, two-step verification is now on for your {org} SmartSched account. After your password you'll be asked for the second step. |
| `mfa_disabled` | İki aşamalı doğrulama kapatıldı / Two-step verification was turned off | İki aşamalı doğrulama kapatıldı / Two-step verification was turned off | Merhaba {name}, hesabınızda iki aşamalı doğrulama kapatıldı. Girişte artık yalnızca parolanız soruluyor. / Hello {name}, two-step verification was turned off for your account. Only your password is asked now. |
| `mfa_reset_by_admin` | Yöneticiniz iki aşamalı doğrulamanızı sıfırladı / Your administrator reset your two-step verification | İki aşamalı doğrulamanız sıfırlandı / Your two-step verification was reset | Merhaba {name}, {actor}, {org} SmartSched hesabınızın iki aşamalı doğrulamasını sıfırladı ve açık oturumlarınızı kapattı. Bir sonraki girişinizde yalnızca parolanız sorulur; ardından yeniden kurabilirsiniz. / Hello {name}, {actor} reset two-step verification on your {org} SmartSched account and signed out your open sessions. Next time only your password is asked; you can then set it up again. |
| `passkey_added` | Hesabınıza geçiş anahtarı eklendi / A passkey was added to your account | Yeni geçiş anahtarı: {passkey_name} / New passkey: {passkey_name} | Merhaba {name}, hesabınıza "{passkey_name}" adlı bir geçiş anahtarı eklendi. / Hello {name}, a passkey called "{passkey_name}" was added to your account. |
| `passkey_removed` | Hesabınızdan bir geçiş anahtarı kaldırıldı / A passkey was removed from your account | Geçiş anahtarı kaldırıldı: {passkey_name} / Passkey removed: {passkey_name} | Merhaba {name}, "{passkey_name}" geçiş anahtarı hesabınızdan kaldırıldı. / Hello {name}, the passkey "{passkey_name}" was removed from your account. |
| `recovery_codes_regenerated` | Yeni kurtarma kodları oluşturuldu / New recovery codes were created | Eski kurtarma kodlarınız artık geçersiz / Your old recovery codes no longer work | Merhaba {name}, hesabınız için yeni kurtarma kodları oluşturuldu; eski kodlar geçersiz oldu. / Hello {name}, new recovery codes were created for your account; the old ones no longer work. |
| `mfa_recovery_code_used` | Bir kurtarma kodu kullanıldı / A recovery code was used | Kurtarma koduyla giriş yapıldı / Someone signed in with a recovery code | Merhaba {name}, hesabınıza bir kurtarma koduyla giriş yapıldı. {remaining} kod kaldı. / Hello {name}, your account was signed in with a recovery code. {remaining} codes left. |
| `mfa_required` | {deadline} tarihine kadar iki aşamalı doğrulamayı kurun / Set up two-step verification by {deadline} | Kurumunuz iki aşamalı doğrulamayı zorunlu tuttu / Your organisation now requires two-step verification | Merhaba {name}, {org}, {role} hesapları için iki aşamalı doğrulamayı zorunlu tuttu. Bir sonraki girişinizde kurulum adımlarını göreceksiniz. Son tarih: {deadline}. / Hello {name}, {org} now requires two-step verification for {role} accounts. You'll see the steps at your next sign-in. Deadline: {deadline}. |

`password_reset_link_by_admin`:

| | TR | EN |
|---|---|---|
| S | Yöneticiniz parola sıfırlama bağlantısı gönderdi | Your administrator sent you a password reset link |
| H | Yeni parolanızı belirleyin | Choose a new password |
| I | Merhaba {name}, {actor}, {org} SmartSched hesabınız ({username}) için bir parola sıfırlama bağlantısı gönderdi. | Hello {name}, {actor} sent a password reset link for your {org} SmartSched account ({username}). |
| B | Yeni parola belirle | Choose a new password |
| after | Bağlantı {valid_hours} saat geçerlidir ve bir kez kullanılabilir. Mevcut parolanız, yenisini belirleyene kadar çalışır. İki aşamalı doğrulamanız değişmez. | The link is valid for {valid_hours} hours and works once. Your current password keeps working until you set a new one. Your two-step verification doesn't change. |
| N | **Beklemiyor muydunuz?** Bir şey yapmanız gerekmez; yöneticinize sorabilirsiniz. | **Weren't expecting this?** You don't need to do anything; you can ask your administrator. |
| why | Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz. | This is a security e-mail; it cannot be turned off in notification settings. |

## 9. Org policy (Ayarlar › **Giriş güvenliği**, `/settings?tab=signin-security`)

This is a new tab after "Microsoft ile giriş", visible with `setup.settings`. One card, one save bar.

| Control | TR | EN | Default |
|---|---|---|---|
| Segmented (glass-morph thumb) → `auth.mfa_policy` `off` / `optional` / `required_for_roles` | İki aşamalı doğrulama: **Kapalı · İsteğe bağlı · Zorunlu** | Two-step verification: Off · Optional · Required | İsteğe bağlı |
| Help under it | Kapalı: kimse kuramaz; kurulu olanlar askıya alınır, silinmez. İsteğe bağlı: herkes Profil'den açabilir. Zorunlu: seçtiğiniz rollerdeki yerel hesaplar süre dolunca kurmadan giriş yapamaz. | Off: nobody can set it up; existing set-ups are paused, not deleted. Optional: anyone can turn it on in Profile. Required: once the grace period ends, local accounts in the roles you choose can't sign in without it. | — |
| Role chips (only when Zorunlu) → `auth.mfa_roles` | Hangi roller için? [Yönetici] [Planlamacı] [Onaylayıcı] [Öğretim elemanı] … [Tüm roller] | Which roles? | Yönetici (AU-B default `["ADMIN"]`; owner Q4) |
| Grace period (only when Zorunlu) → `auth.mfa_grace_days` (0–90) | Kurulum için süre: 7 gün · 14 gün · 30 gün | Time to set up: 7 · 14 · 30 days | 14 gün |
| Live sentence (only when Zorunlu) | Bu ayarla {n} kişi {date} tarihine kadar kurmalı; {m} kişi zaten kurdu. | With this setting {n} people must set it up by {date}; {m} already have. | — |
| Switch → `auth.passkeys_enabled` | Geçiş anahtarları: Yerel hesaplar parmak izi, yüz ya da cihaz PIN'iyle ikinci adımı geçebilir. | Passkeys: local accounts can pass the second step with a fingerprint, face or device PIN. | Açık |
| Nested checkbox (only when passkeys are on) → `auth.passkey_first_factor` | Parolasız girişe de izin ver (geçiş anahtarı tek başına yeter) | Also allow passwordless sign-in (a passkey alone is enough) | Kapalı in AU-B; owner Q9 recommends Açık |
| Gelişmiş › select → `auth.trusted_device_days` (ask A1d; AU-B has a fixed 30) | Bu cihazı hatırla: Kapalı · 7 gün · 30 gün | Remember this device: Off · 7 days · 30 days | 30 gün |
| Note (always) | Kurum hesabıyla (Microsoft, Google…) giriş yapanlar bu kurallardan etkilenmez; onları kurumunuzun kimlik sağlayıcısı korur. | People who sign in with an organisation account (Microsoft, Google…) aren't affected; their identity provider protects them. | — |
| Banner when the saving admin is in scope and has no 2FA | Bu kural sizi de kapsıyor. {date} tarihine kadar kurun. [Şimdi kur] | This rule includes you. Set it up by {date}. [Set up now] | — |

- Saving "Zorunlu" asks once: "{n} kişiye e-posta gönderilecek ve bir sonraki girişlerinde kurulum istenecek." → "Kaydet".
- Saving "Kapalı" while people have 2FA asks: "{m} kişinin iki aşamalı doğrulaması askıya alınacak (silinmez); girişte
  yalnızca parola sorulacak." → "Kaydet" / "İsteğe bağlı kalsın" (AU-B §8: `off` keeps the factors).
- Audit row `auth.mfa_policy` (AU-B).

## 10. Input-box design system (sign-in, 2FA, security; extends `ui/field-styles.ts`)

### 10.1 Anatomy

```
Label (type-callout 15/600, label-1)                    [right-aligned link, e.g. "Parolamı unuttum"]
Hint (type-footnote 13, label-2)                         ← optional, above the field when it explains the format
┌───────────────────────────────────────────────┐
│ value                                   [icon]│  ← field: --control-h-lg (44 fine / 48 coarse on sign-in)
└───────────────────────────────────────────────┘
Message (type-footnote 13; error / success / caps)       ← one line, aria-describedby
```

Gaps: label → field 6 px, field → message 6 px, field group → field group 16 px, last field → submit 20 px.

### 10.2 States (tokens; light and dark come from the theme)

| State | Surface | Edge | Extra | Text |
|---|---|---|---|---|
| Default | `bg-fill-3` | `--edge-control` (3:1, WCAG 1.4.11) | — | `label-1`; placeholder `label-3` (examples only, never the label) |
| Hover (fine pointer) | `bg-fill-2` | same | — | — |
| Focus | `--mat-thick` | `--edge-control` | 2 px `--focus` outline at offset 0 + 3 px halo `color-mix(--focus 22%)` (decorative) | — |
| Filled | as default | as default | — | — |
| **Autofilled** | `:autofill` / `:-webkit-autofill` → `box-shadow: inset 0 0 0 100vmax color-mix(in oklab, var(--tint) 7%, var(--fill-3)), var(--edge-control)`; `-webkit-text-fill-color: var(--label-1)`; `caret-color: var(--label-1)` | as default | no yellow or blue browser fill; the 7 % tint quietly shows "filled for you" | `label-1` |
| **Error** | as default | inset 1 px `--status-infeasible-border` + 3 px halo `--status-infeasible-solid 16%` (existing `aria-invalid` rule) | message with an ⚠ glyph + text in `--status-infeasible-fg`; shake once on submit failure only (§11) | — |
| **Success** (verification fields only: OTP in setup, recovery code) | as default | inset 1 px `--status-feasible-border` | "✓ Doğrulandı" in `--status-feasible-fg`, `role="status"` | ordinary fields never show "valid" ticks |
| Disabled | 50 % opacity | — | `cursor: not-allowed` | — |
| Read-only (username on set-password) | transparent | `--edge-control` dashed 1 px | — | `label-2` |
| Caps Lock (password) | — | — | footnote `--status-warning-fg` "Caps Lock açık" | — |

### 10.3 Types, keyboards and autofill attributes

| Field | `type` | `inputmode` | `autocomplete` | `enterkeyhint` | Other |
|---|---|---|---|---|---|
| Identifier (username or e-mail) | text | email | `username webauthn` | next | `autocapitalize=none`, `autocorrect=off`, `spellcheck=false` |
| E-mail (forgot password, admin) | email | email | `email` (forgot: `username`) | send / next | same as above |
| Current password | password ↔ text | — | `current-password` | go | show/hide `IconButton` 44 px, `aria-pressed`, `aria-controls`; Caps Lock detection |
| New password | password ↔ text | — | `new-password` | go | `passwordrules="minlength: {n};"`, `minlength={n}` |
| OTP (6 digits) | text | numeric | `one-time-code` | done | `pattern="\d{6}"`, `maxlength=6`; paste strips spaces, hyphens and non-digits ("123 456", "123-456") |
| Recovery code | text | text | `off` | go | `autocapitalize=characters`, `autocorrect=off`, `spellcheck=false`, monospace; case, spaces and hyphens ignored |
| Passkey name | text | text | `off` | done | `maxlength=64` |
| Reason "Diğer" (admin) | textarea 3 rows | text | `off` | — | `maxlength=200` with counter |

On phones every field is 16 px or larger (`pointer-coarse:text-base`, already in `Input`), so iOS does not zoom. Sign-in
fields are 48 px tall on coarse pointers.

### 10.4 OTP slot input (`components/auth/otp-input.tsx`, after input-otp, MIT)

- **One real `<input>`**, transparent, spanning the slots. It has the label "Doğrulama kodu", `aria-describedby` = hint +
  message, and one tab stop. Screen readers hear one edit field with its value, never "6 edit fields".
- **Slots:**
  - size 44 × 52 (fine) or 48 × 56 (coarse), radius 10, gap 8, an extra 16 px gap between digit 3 and digit 4. Total
    width 312 / 332 px, inside the 400 / 358 px column;
  - digit type: 24 px / 600, tabular figures;
  - empty slot: fill-3 + edge-control, no placeholder digits;
  - active slot: the focus ring of §10.2 on that slot only, with a 2 × 24 px caret in `--tint` blinking at 1 s steps
    (reduced motion: a steady caret);
  - the caret and active ring jump without animation (typing is a frequent action).
- **Error:** every slot gets the error edge, the message appears below, the value is cleared and the caret returns to
  slot 1.
- **Success:** every slot gets the success edge and the "✓ Doğrulandı" status appears.
- **Password managers:** the input widens behind the last slot when a manager badge is detected (input-otp
  `pushPasswordManagerStrategy`), so the badge never covers a digit.
- **Without JavaScript:** a normal 6-character field (the input is real).

## 11. Motion (per `/motion_designer`; rows for `v2/motion.md` new §3.19 "Sign-in security")

Purpose first. Nothing animates on first paint. One focal motion at a time. Only transform and opacity animate, plus
small filters on non-glass elements up to 400 × 300 px. Tokens come from `@/lib/motion`.

### 11.1 Free transitions.dev recipes used (no Pro, no `add --pro`)

| Recipe | Status | Where | Retiming |
|---|---|---|---|
| Error state shake | shipped (`.t-input`) | wrong password, wrong code (slot group), wrong recovery code | 280 ms (unchanged) |
| Panel reveal | shipped (`.t-panel-slide`) | "Başka bir yöntem" panel, "QR kodunu tarayamıyor musunuz?" | open 240 / close 160 ms, translate 8 px, blur 2 px (panel ≤ 400 × 300) |
| Modal | shipped (`.t-modal`) | re-auth, reset 2FA, send link, remove passkey dialogs | 250 / 150 ms (unchanged) |
| **Text states swap** | new (`npx transitions-dev add text-states-swap`) | "Doğrula" → "Doğrulanıyor…" → "Doğrulandı"; "Kopyala" → "Kopyalandı" | 150 ms, 4 px, blur 2 px (unchanged) |
| **Icon swap** | new | show/hide password eye; copy → check | 250 → **180 ms** |
| **Success check** | new | the ✓ in "Doğrulandı" (setup step 2, OTP success), the shield when 2FA turns on | 500 → **240 ms** for every `--check-*-dur`, `--check-y-amount` 40 → **8 px**, blur 10 → **4 px**, path delay 80 → 40 ms |
| **Page side-by-side** | new | password step → 2FA step in the sheet; setup steps 1 → 2 → 3 | 250 → **220 ms**, distance 8 px, **blur 0** (the step content is larger than 400 × 300; motion_designer §4) |

Each new file keeps the `/* Transitions.dev — <name> */` header and gets a row in `components/ui/SOURCES.md`.

**Observation for AUX-09:** the shipped `.t-input` rule keeps `will-change: transform` on every field all the time.
motion_designer §4 says "never leave it on". Move it to `.t-input.is-shaking` only.

### 11.2 Moments

| Moment | Purpose ("motion tells the user…") | Animation | Token / recipe | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| Door 2 open / close | unchanged (motion.md §3.12) | — | — | — | — |
| Password accepted → 2FA step | "Your password was right; one more step, here" | old content: opacity → 0 in 80 ms; new content: x 8 → 0 + opacity, forward = from the right | Page side-by-side 220 ms (`ease.out`) | opacity `tween.reduced` 100 ms, no travel | same |
| Autofill passkey chosen → signed in | "It worked" | the "Giriş yap" label swaps to busy, then the standard route enter | Text states swap 150 ms; pattern 13 | text swap only | same |
| Wrong code | "That code is wrong; type here again" | the slot group shakes once; the message fades in | shake 280 ms; message opacity `dur.fast` 120 ms | no shake; message appears; `aria-invalid` + text + focus carry it | same |
| Code verified | "Verified" | ✓ draws inside the button; the label swaps to "Doğrulandı"; navigation starts after 240 ms | Success check 240 ms + Text states swap 150 ms | static ✓ and text; navigation immediately | same |
| "Başka bir yöntem" opens | "The other ways are here, under the link" | panel reveal from 8 px above; the chevron rotates 180° | Panel reveal 240 / 160 ms; chevron `springs.snappy` | opacity 100 ms; chevron flips | same |
| Slot caret | "Type here" (an indicator of focus, which is ongoing) | 1 s step blink, stops on blur | CSS `steps(1)` | steady caret | same |
| Show / hide password | "The field now shows / hides the text" | eye ↔ eye-off | Icon swap 180 ms | instant swap | same |
| Setup sheet opens / closes | unchanged sheet pattern 4 | — | `springs.sheet`, exit 120 ms | opacity 100 ms | opaque sheet |
| Setup step 1 → 2 → 3 | "Next step, same place" | Page side-by-side; focus to the step heading | 220 ms | opacity 100 ms | same |
| Recovery codes copied / downloaded | "Done" | button label "Kopyala" → "Kopyalandı ✓" for 2 s | Text states swap + Icon swap | text only | same |
| 2FA turned on | "Your account is now protected" | the row's status word changes; the shield glyph draws a ✓ once | Success check 240 ms (≤ 32 px, overshoot allowed) | static | same |
| Passkey added / removed | "Here is the new one" / "it's gone" | the list row enters / leaves with layout | pattern 6, `springs.smooth` (list < 40 rows) | no layout animation | same |
| Toasts | unchanged pattern 5 (sonner) | — | `springs.smooth` | opacity only | opaque |
| Policy segmented control | "This option is selected" | thumb morph | pattern 2, `springs.glassMorph` | thumb jumps | same |
| Admin dialogs | unchanged Modal recipe | — | 250 / 150 ms | opacity 100 ms | opaque |

Not animated: typing, slot focus, field focus (only the existing 120 ms colour transition), filters, list sorting, the
OTP digits themselves, and notices on arrival (they are the page's initial state).

### 11.3 Sign-in hero (≥ 1024 px only; the scene area right of the sheet)

This **amends sign-in.md §3.1 item 4** ("the scene, not a hero") at the owner's request. The hero keeps the calm
rules:

- **What:** the existing `docs/lottie/hero-solver-{light,dark}.json`, 960 × 540: a room × period grid filling with
  classes, one clash resolved, 100/100. It is placed in the lower right of the scene at `min(52vw − 120px, 640px)` wide,
  in a `glass-tint` frame (no `backdrop-filter`: no glass on glass, and the sheet is the only blurred surface). The
  existing caption line "Güz 2026–27 · 3. hafta / 15 Ekim 2026, Perşembe" sits under it.
- **When it plays:**
  - after first paint and `requestIdleCallback`, plus 300 ms, so it never competes with the form;
  - **once**, frames 0 → 140 (4.67 s at 30 fps, under 5 s, so WCAG 2.2.2 needs no pause control);
  - it then **stops on poster frame 140** and never loops;
  - every tween inside is ≤ 9 frames, i.e. ≤ 300 ms, which `docs/lottie/build/audit.mjs` enforces.
- **How it loads:** `lottie-react` (already a dependency) is lazy-loaded only at ≥ 1024 px and only if
  `!prefers-reduced-motion` and not `Save-Data`. Otherwise `docs/images/lottie/hero-solver-{theme}-poster.png` (2×) is
  shown as a static image. The theme follows `next-themes`.
- **Accessibility:** `aria-hidden="true"`, `pointer-events: none`. It is decorative, because the caption carries the
  information.
- **Hidden** below 1024 px and in `forced-colors`. It is never shown on the 2FA step: the hero stays on its poster frame
  while the sheet changes step.
- **Performance:** it must stay in budget with the glass sheet. At most 2 backdrop-filter surfaces exist, and only the
  sheet is blurred. Audit: no long animation frame > 50 ms while the identifier is focused and typing.

### 11.4 The hosted Motion Agent fix (free plan: 10 a month for the whole project)

**Not spent in this design pass.** There is no hero component in the code yet to polish. It is **reserved for AUX-10**
under the name **"signin-hero-settle"**: one hosted fix on `components/auth/signin-hero.tsx` once it is built, to tune
how the hero enters after idle and settles onto the poster frame (opacity 0 → 1 at 240 ms and a 4 px rise, then a
hold). No other surface in this spec may use a hosted fix. Unlimited free scans may be used on every surface. The licence
key stays in `TRANSITIONS_AGENT_LICENSE` and is never written anywhere.

**Status (AUX-10, 2026-10-18):** the hero is built to the values above (`components/auth/signin-hero.tsx`: 240 ms
`ease.out` entry with a 4 px rise, pause + seek to frame 140). The hosted fix **was not spent**: the licence variable
was not set in the AUX-10 session. "signin-hero-settle" stays reserved for this file.

## 12. Components (existing first; source and licence)

| Component | Status | Source | Licence |
|---|---|---|---|
| `SignInShell`, `SignInBrand`, `SignInFooter` | existing | ours | — |
| `ProviderButtons`, `MicrosoftSignIn` | existing | ours (Microsoft and Google brand rules) | — |
| `LocalSignInForm` | amend: `webauthn` token, the passkey button, conditional get / create | ours | — |
| `Input`, `useShake`, `fieldSurface` | existing; add the `:autofill` rule | shadcn/ui base-nova | MIT |
| `components/auth/otp-input.tsx` | **new** | `input-otp` (guilhermerodz) or the shadcn "InputOTP" wrapper | MIT |
| `components/auth/passkey.ts` (feature detection, conditional get / create, Signal API) | **new** | optional `@simplewebauthn/browser` | MIT |
| `components/auth/mfa-step.tsx`, `recovery-code-field.tsx`, `other-methods.tsx`, `enrol-notice.tsx` | **new** | ours | — |
| `components/auth/set-password-form.tsx` | **new**, replaces the body of `identity/local-invite-accept.tsx` | ours | — |
| `components/auth/signin-hero.tsx` | **new** | ours + `lottie-react` | MIT |
| `components/profile/security/{security-section,password-row,mfa-row,mfa-setup-sheet,recovery-codes,passkeys-list,sessions-list,sign-in-history,reauth-dialog}.tsx` | **new** | ours | — |
| QR rendering | **new** inside `mfa-setup-sheet` | `qrcode` (npm), or a server SVG (AU-B) | MIT |
| Passkey provider icons | data | `passkeydeveloper/passkey-authenticator-aaguids` | MIT (icons identify vendors only) |
| `components/admin/users-security.tsx` (menu items, edit-sheet block, two dialogs) | **new**, mounted from `users-admin.tsx` / `users-admin-identity.tsx` | ours | — |
| `components/settings/signin-security.tsx` (policy tab) | **new** | ours | — |
| `Dialog`, `Sheet`, `Checkbox`, `SegmentedControl`, `Chip`, `DropdownMenu`, `Alert`, `BusyButton` | existing | shadcn/ui + ours | MIT |
| transitions.dev free recipes (§11.1) | 3 shipped + 4 new | transitions.dev | Transitions.dev License (no redistribution; keep header) |

## 13. Accessibility

- **Focus:**
  - On `/login/verify` focus starts in the OTP input.
  - After an error it stays in the input; after a page-level error, focus goes to the alert (existing pattern).
  - Dialogs trap focus and return it to the trigger.
  - Rename returns focus to the row's ⋯ button.
  - Focus never falls to `<body>`.
- **Names:**
  - OTP: one field, label "Doğrulama kodu", with the hint "6 haneli kod" via `aria-describedby`.
  - Show/hide: "Parolayı göster" / "Parolayı gizle" with `aria-pressed`.
  - Passkey rows are a list (`<ul>`). Each ⋯ menu is named "{name} için işlemler".
- **Live regions:**
  - one polite status for "Doğrulanıyor…" / "Doğrulandı";
  - errors use `role="alert"` only for page-level errors (not per keystroke);
  - recovery codes are announced as a list of 10, with the codes spelled out by group.
- **No timing traps:**
  - The 5-minute challenge shows no countdown. When it expires, the person goes back with a clear message; nothing
    expires while they type.
  - The TOTP 30 s window is invisible; the clock hint covers drift.
- **Colour is never the only signal:** status words + icons ("Açık", "Kapalı", "Bekleniyor"; ✓ / ✗ / ⚠ in history).
- **Contrast:**
  - field edges ≥ 3:1 (`--edge-control`);
  - error and success text ≥ 4.5:1 (existing status tokens);
  - the QR is always black on white, with a quiet zone of 4 modules.
- **Touch:** every control is ≥ 44 px, including the "Başka bir yöntem" link row (44 px hit area), slots 48 × 56, the
  ⋯ buttons and the checkbox rows (whole row is the target).
- **Keyboard:**
  - the OTP accepts typing, paste, Backspace, ← and → (input-otp);
  - Enter submits;
  - Escape closes panels and dialogs.
- **Cognitive:**
  - one task per screen;
  - plain verbs ("Doğrula", "Bitir", "Kaldır");
  - the consequence is stated before every destructive action;
  - no "2FA" jargon in user screens (only in admin tables, where "İki aşamalı doğrulama (2FA)" is spelled out once).
- **Screen readers and passkeys:** the browser's own WebAuthn sheet is accessible by the platform. We never imitate it.
- **Reduced motion and transparency:** §11. **Forced colours:** slots use `ButtonBorder` / `Highlight`; the hero is
  hidden.

## 14. Mobile layout (390 × 844, touch, tr-TR)

- **The sheet is the page** (sign-in.md §5.3), with 16 px side padding and keyboard-safe focus (`useKeyboardSafeFocus`
  keeps the focused field centred above the keyboard).
- **2FA step:**
  - order: title, account line, lead, slots (332 px), remember checkbox row (48 px), "Doğrula" (48 px, full width,
    directly under the checkbox, never pinned), then "Başka bir yöntem";
  - with the numeric keypad open (≈ 291 px), the slots and "Doğrula" stay visible on a 844 px screen; no scrolling is
    needed;
  - iOS offers the code from Messages or Passwords above the keypad (`one-time-code`).
- **Passkey sign-in:** the button is full width under the form; the system sheet takes over.
- **Profil › Giriş ve güvenlik:**
  - rows stack, with the action under the text, full width;
  - the passkey list's ⋯ opens a bottom sheet ("Yeniden adlandır", "Kaldır");
  - the setup flow is a full-screen sheet with the step header sticky at the top and "Bitir" in the flow, above the tab
    bar safe area;
  - step 1 leads with "Uygulamada aç" and the key; the QR sits behind a disclosure.
- **Admin › Kullanıcılar:** the edit sheet's "Giriş ve güvenlik" block holds the actions. Dialogs become bottom sheets
  with detents (pattern 4). The reason select is a native select.
- **Policy tab:** the segmented control is full width; role chips wrap; the save bar is sticky above the tab bar
  (MOBILE.md M-05).

## 15. Wireframes (`wireframes/auth-*.svg`, generated by `wireframes/auth-gen.py`; purple = annotation)

| File | Shows |
|---|---|
| `auth-signin-1440.svg` | `/login` with providers, door 2 open, passkey autofill dropdown, passkey button, the hero in the scene |
| `auth-signin-390.svg` | the same at 390 (no hero), keyboard-safe order |
| `auth-2fa-1440.svg` | 2FA step: slots, remember, "Başka bir yöntem" panel open; error variant inset |
| `auth-2fa-390.svg` | 2FA step with the numeric keypad; recovery-code variant |
| `auth-security-1440.svg` | Profil › Giriş ve güvenlik rows + setup sheet (steps 1–2 in one view) |
| `auth-security-390.svg` | the section stacked + setup step 3 (recovery codes) full screen |
| `auth-admin-1440.svg` | Kullanıcılar row menu (local vs SSO explanation row) + "2FA'yı sıfırla" dialog + policy tab |
| `auth-admin-390.svg` | edit sheet "Giriş ve güvenlik" block + send-link bottom sheet + policy tab |
| `auth-inputs.svg` | the input-box system: states, OTP slot states, autofill, types and keyboards |

## 16. Acceptance checks (testers run at 1440 mouse and 390 × 844 touch, tr-TR, Europe/Istanbul; EN spot checks)

1. A local user with 2FA signs in with the password and sees the 2FA step without a page reload. Pasting "123 456"
   fills all 6 slots and submits. A wrong code clears the slots and shows `signin.mfa.wrong`, and focus stays in the
   field.
2. "Bu cihazı 30 gün hatırla" ticked: the next sign-in on the same browser skips the 2FA step. After "Hatırlanan tüm
   cihazları unut" in Profil, it asks again.
3. A recovery code signs in once and fails the second time with `signin.mfa.recoveryWrong`. The toast shows the
   remaining count, and an `mfa_recovery_code_used` e-mail arrives at the SMTP sink.
4. A passkey is added in Profil (re-auth first). The row shows the provider name and "Hiç kullanılmadı". With
   "Parolasız girişe de izin ver" on, `/login` door 2 offers it in the identifier autofill (Chromium virtual
   authenticator), and picking it signs in with no 2FA step. With it off, there is no passkey button and no autofill,
   and the passkey works as "Başka bir yöntem › Geçiş anahtarı kullan".
5. With passwordless on: after a password sign-in on a browser with Conditional Create support (virtual
   authenticator), a passkey is created silently, with no error UI when it is refused. With passwordless off, no
   create call is made.
6. Turning on 2FA takes at most three steps. The codes download as `.txt`. "Bitir" is disabled until the checkbox is
   ticked. Closing at step 3 shows the warning.
7. Admin: a local account's menu shows "Parola sıfırlama bağlantısı gönder" and "2FA'yı sıfırla". A Microsoft account
   shows "Bu hesap Microsoft ile giriş yapıyor…" as text, with no button. The admin's own row has no reset.
8. "2FA'yı sıfırla" cannot be confirmed without a reason of 10 or more characters and an identity-check method.
   Choosing the "Hesap ele geçirilmiş olabilir" chip hides "Geçiş anahtarlarını koru". The user is signed out
   everywhere. An audit row `auth.mfa_reset_by_admin` is written. The user gets `mfa_reset_by_admin`, which shows the
   admin's name and no reason text. The admin's own row offers no reset (409 `own_account` if forced).
9. Policy "Zorunlu" for Yönetici + Planlamacı with 14 days: a planner without 2FA sees the enrolment notice with the date and
   "Daha sonra (14 gün kaldı)". After the date (clock moved on the test stack) there is no "Daha sonra".
10. SSO users never see SmartSched 2FA or passkey rows (`GET /auth/mfa` → `available: false, reason:
    "sso_account"`). Profil shows the explanation row (and Oturumlar / Son girişler once ask A1a lands).
11. Reduced motion: no shake, slide, check draw or Lottie anywhere in these flows; the poster PNG shows at 1440.
    `document.getAnimations()` shows nothing over 300 ms; the hero's Lottie is not loaded.
12. MOBILE M-01/M-02/M-03/M-05 on `/login`, `/login/verify`, `/profile#security`, `/admin/users`,
    `/settings?tab=signin-security`: no horizontal scroll, every target ≥ 44 px, inputs 16 px, and the keyboard never
    covers the focused field or "Doğrula".
13. Simplicity: a first-time tester can say in one sentence what each screen asks. "Where do I click?" is a major
    finding.

## 17. Hand-off, asks and owner questions

**Asks (owners):**

| # | To | Ask |
|---|---|---|
| A1a | AU-B or W3-SEC | A sessions list (`GET /auth/sessions`, revoke one, revoke others) and sign-in history (`GET /auth/sign-ins?limit=20`, 90 days: time, result, method, device label). AU-B's research note covers trusted devices only; §6.5/§6.6 wait for this |
| A1b | AU-B | A re-auth window (`POST /auth/reauth` → valid 10 min) **or** confirm that each protected call takes `password` (+ code when 2FA is on); the dialog works with either |
| A1c | AU-B | Revoke trusted devices on a password change (own or via reset link), not only on an MFA reset or turning 2FA off |
| A1d | AU-B | Setting `auth.trusted_device_days` (0 = off, 7, 30; default 30) and `remember_allowed` / `remember_days` in the challenge answer |
| A1e | AU-B / W3-IDP | `GET /org/public` carries `passkeys_enabled` and `passkey_first_factor`, so `/login` decides the passkey button and autofill before first paint (no flash, sign-in.md §4.3) |
| A1f | AU-B | Accept a Conditional Create registration (UP/UV false, S4) within 5 min of a password sign-in without a password prompt; otherwise AUX-03 drops Conditional Create |
| A1g | AU-B | Confirm that passkeys alone keep 2FA "on" (D4): turning the app off keeps passkeys as the second step; status answers `methods: ["totp","passkey"]` |
| A1h | AU-B | `mfa_reset_by_admin` never includes the reason text; the challenge answer lists the account's methods and a masked identifier for the account line |
| A1i | AU-B | Accepting a local invite or a reset returns a session (the form signs the person in); `mfa_setup_required` + `deadline` on login and `/auth/me` |
| A2 | W3-MAIL (templates) + AU-B (senders) | Copy of §8 into `strings.py`; three missing kinds `passkey_removed`, `recovery_codes_regenerated`, `mfa_required` in `kinds.py` / `strings.py` / `samples.py`; "Geçiş anahtarı" and "Parola + uygulama kodu" method labels for `new_device_sign_in` |
| A3 | W3-IDP | `local-invite-accept.tsx` delegates to the new `SetPasswordForm`; `provider-buttons` unchanged |
| A4 | motion.md owner | Copy §11.2 as `v2/motion.md` §3.19; amend §3.12 for the hero |
| A5 | admin users owner | Mount `users-security.tsx` in the row menu and the edit sheet; rename "Tek kullanımlık sıfırlama kodu" to "Sıfırlama kodunu ekranda göster" |
| A6 | settings owner | Add the tab `signin-security` to `settings-view.tsx` |
| A7 | profile owner | Mount `SecuritySection` after `MicrosoftAccountSection` and move `PasswordForm` inside it |
| A8 | sign-in.md owner | Note the amendments: door 2 passkey button, the hero (§3.1 item 4), `/login/verify`, `/login/setup-2fa` |

**Owner questions (with recommended defaults):**

| # | Question | Recommended default |
|---|---|---|
| Q1 | "Parola" (app-wide today) or "Şifre" (e-Devlet, your brief)? | Keep **"Parola"** everywhere ("Parolamı unuttum"); switching would touch ~100 strings and the e-mails |
| Q2 | Minimum password length for new passwords? | **12** characters (8 when the account has 2FA); existing passwords are not forced to change (NIST: no periodic changes) |
| Q3 | Keep "Bu cihazı 30 gün hatırla" despite NIST §5.2? | **Keep**, off by default, password always asked, policy can switch it off (ask A1d) |
| Q4 | Which roles does "Zorunlu" pre-select? | **Yönetici** (AU-B default); suggest adding **Planlamacı** in the hint, since planners change the published timetable |
| Q5 | Should passkeys count alone as 2FA for a required role (without an authenticator app)? | **Yes** (D4): a passkey is stronger than TOTP |
| Q6 | Should SSO users get SmartSched passkeys as a shortcut past the IdP? | **No** (D1): the institution's policies (Conditional Access) must keep applying |
| Q7 | Notify other admins when one admin resets someone's 2FA? | **No e-mail**; the audit log and the user's own e-mail are enough (Simplicity); revisit if an incident shows a need |
| Q8 | Allow an admin to reset another admin's 2FA? | **Yes** when `guard_privileged` allows it, audited, with the same reason and identity check; no admin can reset their own |
| Q9 | Passwordless passkey sign-in (`auth.passkey_first_factor`) on by default? | **On** for new installs (you asked for passkeys on the login page; it is phishing-resistant MFA). AU-B ships it off; existing installs keep off until an admin ticks it |
