# Sign-in, 2FA and passkeys — backend research (owner request 2026-10-18)

Lane AU-B (`au-b-2026-10-18`). Scope: two-factor authentication with an authenticator app (TOTP), passkeys
(WebAuthn) as a second factor and, when the institution allows it, as the only factor; recovery codes; trusted
devices; administrator resets for accounts the administrators created by e-mail (not through an identity provider).
The identity providers themselves (Entra, Google, OIDC, SAML) were built by W3-IDP and are not changed here.

Sources were read on 2026-10-17/18 (UTC). Where a statement comes from a standard, the section is named.

## 1. Sources

| # | Source | What it settles |
|---|---|---|
| S1 | RFC 6238 *TOTP: Time-Based One-Time Password Algorithm* (2011), §4, §5.2, §6, Appendix B test vectors — https://www.rfc-editor.org/rfc/rfc6238 | Algorithm, time step, drift window, resynchronisation |
| S2 | RFC 4226 *HOTP* §4 (R6: shared secret ≥ 128 bits, 160 recommended), §5.3 dynamic truncation — https://www.rfc-editor.org/rfc/rfc4226 | Secret length, truncation |
| S3 | Google Authenticator *Key Uri Format* (`otpauth://totp/Issuer:account?secret=…&issuer=…`) — https://github.com/google/google-authenticator/wiki/Key-Uri-Format | QR content every authenticator app reads |
| S4 | PyPI `pyotp` 2.10.0 (MIT, 2026-06-14) — https://pypi.org/project/pyotp/ | Library option for TOTP |
| S5 | PyPI `webauthn` 3.0.1 (BSD-3-Clause, Duo Labs, uploaded 2026-09-25; pure-Python wheel `py3-none-any`; requires `cbor2>=6.1.2`, `cryptography>=49`, `pyOpenSSL>=26.3`, `pyasn1>=0.6.2`, `pyasn1-modules>=0.4.2`) — https://pypi.org/project/webauthn/ ; source read from the sdist (`webauthn/registration/verify_registration_response.py`, `authentication/verify_authentication_response.py`) | Server-side ceremonies, sign-count rule |
| S6 | W3C *Web Authentication Level 3* (Candidate Recommendation) §5.1.3/5.1.4 (create/get), §6.1 (authenticator data flags UP/UV/BE/BS), §6.1.1 (signature counter), §7.1/§7.2 (RP operations), §5.4.6 (`residentKey`), §13.4.1 (RP ID and the public suffix list) — https://www.w3.org/TR/webauthn-3/ | RP ID, UV, resident keys, counters |
| S7 | NIST SP 800-63B-4 *Digital Identity Guidelines: Authentication and Authenticator Management* (final, 2025) — https://pages.nist.gov/800-63-4/sp800-63b.html — §3.1.2 look-up secrets, §3.1.4 single-factor OTP verifiers, §3.2.2 rate limiting, §3.2.7 replay resistance, §4.1.2 binding additional authenticators, §4.2.1.1 saved recovery codes, §4.6 account notifications, Appendix B syncable authenticators | Rate limits, recovery codes, notifications, passkeys at AAL2 |
| S8 | OWASP ASVS 5.0.0 (May 2025) chapter V6 *Authentication* — https://github.com/OWASP/ASVS/blob/master/5.0/en/0x15-V6-Authentication.md — 6.1.1, 6.3.1, 6.3.5, 6.3.7, 6.3.8, 6.4.3, 6.4.4, 6.4.6, 6.5.1–6.5.6, 6.7.2, 6.8.4 | Verification checklist |
| S9 | OWASP *Multifactor Authentication Cheat Sheet* — https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html | Reset of MFA, trusted devices, recovery |
| S10 | Public Suffix List — https://publicsuffix.org/list/ (sslip.io / nip.io style wildcard DNS) | RP ID on sslip.io |
| S11 | This repository: docs/SECURITY.md (W3-SEC), `app/core/security_http.py`, `app/core/rls.py`, `app/services/sso.py`, `app/services/identity/**`, `app/services/mail.py` `send_kind`, `app/emails/kinds.py` | Existing controls the design reuses |

## 2. TOTP (authenticator app)

**Algorithm (S1, S2).** HOTP(K, T) with T = floor((now − T0) / X), X = 30 s, HMAC-SHA-1, 6 digits, dynamic truncation.
Every mainstream app (Google/Microsoft Authenticator, Authy, 1Password, Bitwarden, Apple Passwords, Aegis) supports
exactly SHA-1 / 6 digits / 30 s; SHA-256 and 8 digits are in the RFC but several apps ignore the parameters in the
URI and silently show wrong codes. **Decision: SHA-1, 6 digits, 30 s.**

**Secret.** 160 bits from `secrets.token_bytes(20)` (RFC 4226 R6 recommends 160; ASVS 6.5.3 CSPRNG), shown as
unpadded Base32 (32 characters) for manual entry and inside the `otpauth://totp/{issuer}:{account}?secret=…&issuer=…&
algorithm=SHA1&digits=6&period=30` URI (S3). The issuer is the institution's name (`org.name`, else "SmartSched"), the
account the person's e-mail or username.

**Drift (S1 §5.2, §6).** The RFC recommends accepting at most one step back ("one time step delay"); in practice clocks
of phones drift both ways, so we accept T−1, T, T+1 (±30 s, a 90 s window). ASVS 6.5.5 asks for a 30 s lifetime per
code: each code still belongs to a single step; the window only tolerates clock error. The server's clock is the
trusted time source (ASVS 6.5.8).

**Replay (S7 §3.2.7, ASVS 6.5.1).** The verifier stores the last accepted step and accepts only a *later* step, so a
code seen over a shoulder or in a proxy log cannot be replayed within its 90 s window.

**Library or stdlib (S4).** `pyotp` is MIT and small, but TOTP verification is ~25 lines over `hmac`/`hashlib`/
`base64`, and the replay rule needs the matched step, which `pyotp.TOTP.verify` does not return (we would call
`at()` per step anyway). **Decision: a stdlib implementation** (`app/core/totp.py`) proven against the RFC 6238
Appendix B SHA-1 vectors (59 s → 94287082, 1111111109 → 07081804, … truncated to 8 digits). One dependency fewer.

**At rest.** The secret is a shared secret, so it is stored encrypted with the existing Fernet key derived from
`APP_SECRET` (`encrypt_secret`, SECURITY.md "Secrets at rest"), never hashed. The pending secret of an unconfirmed
enrolment is encrypted too and expires after 15 minutes.

## 3. Passkeys (WebAuthn) on the server

**Library (S5).** `webauthn` (py_webauthn, Duo Labs) 3.0.1, BSD-3-Clause, released 2026-09-25 (more than two weeks
before this lane). Pure-Python wheel; its native dependency `cbor2` ships manylinux/musllinux **aarch64** and x86_64
wheels for CPython 3.10–3.14 (and a pure-Python fallback); `cryptography` 50 is already in the lock; `pyOpenSSL`,
`pyasn1`, `pyasn1-modules` are pure Python. So the arm64 server image needs no compiler. API used:
`generate_registration_options`, `verify_registration_response`, `generate_authentication_options`,
`verify_authentication_response`, `options_to_json`, `base64url_to_bytes`.

**Registration ceremony (S6 §7.1).** Server: random 32-byte challenge, `rp = {id, name}`, `user = {id: random
32-byte handle (not the e-mail or the database id), name: e-mail/username, displayName}`, `pubKeyCredParams` ES256
(−7) and RS256 (−257) (Windows Hello still uses RS256), `excludeCredentials` = the person's existing credentials (so
the same authenticator is not registered twice), `authenticatorSelection = {residentKey: "preferred",
userVerification: "preferred"}`, `attestation: "none"`, timeout 5 min. Browser: `navigator.credentials.create()`.
Server verifies challenge, origin, RP ID hash, the UP flag, the algorithm, and stores credential id, public key (COSE),
sign count, transports, the BE/BS flags (backup eligible / backed up = a synced passkey) and the AAGUID.

**Attestation "none".** We do not need to know the authenticator's make and model, and requesting attestation
triggers an extra consent prompt in some browsers. With `none`, synced passkeys (iCloud Keychain, Google Password
Manager, 1Password, Bitwarden) and security keys all work. NIST 800-63B-4 Appendix B allows syncable authenticators
up to AAL2, which is the level here (S7).

**User verification.** As a *second* factor after the password, UV is `preferred` (a security key without a PIN
still proves possession). As the *only* factor, UV is `required` and the server checks the UV flag: possession +
biometric/PIN on the device makes it multi-factor and phishing-resistant on its own (S6 §6.1, S7 §3.1.7).

**Resident (discoverable) keys (S6 §5.4.6).** `preferred`: passkey-first sign-in needs a discoverable credential
(the browser offers the account without a typed name); a security key that cannot store one still works as a second
factor. The passkey-first options therefore carry an empty `allowCredentials`; the response's credential id finds the
account (`webauthn_credentials.credential_id` is unique).

**RP ID (S6 §13.4.1, S10).** The RP ID is the host of the panel's public URL (`integrations.public_url`, else
`PUBLIC_URL`) — e.g. `plan.uni.edu.tr` — and the expected origin is `https://plan.uni.edu.tr` (with the port when it
is not 443). The RP ID may be a registrable suffix of the host (`uni.edu.tr`) but never a public suffix. On sslip.io /
nip.io test hosts (`smartsched.10-0-0-5.sslip.io`) the RP ID must be **the full host**: `sslip.io` is a shared
wildcard domain and browsers refuse an RP ID that is (or would be) a public suffix, and sharing an RP ID across
unrelated test servers would let one server's page request another's credentials. Consequence: a passkey made on the
sslip.io host does not work after the move to the real domain; the person registers a new one there (the panel can
say so). WebAuthn needs a secure context, so plain `http://` works only on `localhost`. Without a public URL, outside
production, the backend accepts the request's own `Origin` when it is `localhost`; otherwise passkeys answer
`passkeys_unavailable` (a configured public URL is required).

**Signature counter (S6 §6.1.1, S5).** py_webauthn refuses an assertion whose counter is not greater than the stored
one *when either is non-zero*. Synced passkeys always send 0, so the counter is meaningful only for hardware keys. A
refused counter (possible cloned key) is audited as `auth.passkey_counter_error` and the sign-in fails; we store the
new counter after every success.

**Several passkeys per person (S7 §4.1.2: "CSPs SHALL permit the binding of multiple authenticators").** Up to 10,
each with a name the person chooses ("iPhone", "YubiKey"), created / last used dates, and remove. Adding one requires
re-authentication (the password) and sends `passkey_added` (S7 §4.6: binding notification).

**First factor vs. second factor.** Second factor: after the password, like TOTP. First factor (passkey-only
sign-in): only when the institution switches it on (`auth.passkey_first_factor`), only with UV, only for local and
LDAP accounts (an SSO account signs in at its provider), and it fully replaces password + second factor (it is
already phishing-resistant MFA). Passwords stay: the passkey is an extra door, not a replacement.

## 4. Recovery codes

NIST 800-63B-4 §4.2.1.1 (S7): saved recovery codes "SHALL include at least 64 bits", "SHALL be stored … in hashed
form", verification "SHALL be subject to the throttling requirements in Sec. 3.2.2", and after use the CSP "SHALL
invalidate that recovery code". ASVS 6.5.2: look-up secrets under 112 bits are hashed with a password hashing
algorithm with a salt. **Decision:** 10 codes, each 16 characters of Crockford Base32 (80 bits) shown as
`XXXX-XXXX-XXXX-XXXX`; stored as argon2id hashes (the existing `PasswordHasher`), single use; entry ignores case,
spaces and dashes and maps O→0, I/L→1. The codes are shown **once** (enrolment, regeneration) and never again —
not to the person and never to an administrator. Using a code e-mails the person (an account-recovery event, §4.6)
and the status shows the remaining count; at 3 or fewer the panel suggests regenerating. Regenerating requires the
password and replaces all ten.

## 5. Trusted devices

OWASP MFA cheat sheet (S9) accepts "remember this device" for a limited period with a revocable token. **Decision:**
a 256-bit random token, only its SHA-256 stored, 30 days, bound to the account (a token of another account is
ignored), revocable one by one or all at once, revoked by an MFA reset, by disabling 2FA and by a password change
(the token version check). It skips only the second factor: the password is still required. The backend returns the
token once in the sign-in answer (`trusted_device_token`); the Next.js route handler keeps it in an httpOnly,
`SameSite=Lax`, `Secure` cookie and forwards it as the `X-Trusted-Device` header to `POST /auth/login` (the browser
never reads it). The device list shows the browser/OS family label (`mail_senders.device_label`) and dates only.

## 6. Rate limits, lockout, notifications, admin reset (S7, S8)

* **Online guessing (S7 §3.2.2; ASVS 6.3.1).** A 6-digit code has ~20 bits, below 64, so rate limiting is mandatory.
  Per account: after 5 consecutive failed second-factor attempts the second factor is locked for 15 minutes, doubling
  at each further 5 (15 min, 30 min, 1 h … capped at 24 h), well under NIST's "no more than 100 consecutive failures"
  ceiling; a success resets the count. Per challenge: 5 tries, then the challenge is dead and the person signs in again
  (the password limiter of `ratelimit.py` applies to that). Per client address (the `security_http` pattern): 30
  verify calls and 60 passkey option calls per 5 minutes. A new challenge never resets the failure count (S7 §3.1.3
  wording for OOB, applied here too). Locking the second factor cannot be abused to lock strangers out: reaching it
  needs the password first.
* **Enumeration (ASVS 6.3.8).** The password step keeps its single "invalid credentials" answer. The passkey-first
  options are the same for every caller (no account named).
* **Partial success (ASVS 6.3.5).** Correct password + wrong code is audited `auth.mfa_failed` and counted.
* **Replay (S7 §3.2.7, ASVS 6.5.1).** TOTP step memory; recovery codes single use; WebAuthn challenges single use and
  bound to the challenge row (ASVS 6.6.2-style binding), 64+ bit nonces (ASVS 6.7.2: 256 bits here).
* **Notifications (S7 §4.6, ASVS 6.3.7).** E-mails for: 2FA turned on (`mfa_enabled`), off (`mfa_disabled`), reset by
  an administrator (`mfa_reset_by_admin`), a passkey added (`passkey_added`), a reset link sent by an administrator
  (`password_reset_link_by_admin`). All have the security footer (cannot be switched off) and say what to do if it was
  not the person ("contact your administrator"). Signing in with a recovery code is an account-recovery event
  ("always causes one or more notifications", S7 §4.2), so it sends a sixth kind, `mfa_recovery_code_used`, with the
  number of codes left.
* **Admin MFA reset (S8 6.4.4; S9).** Losing the phone must not end in an administrator reading a secret. The
  administrator (`setup.users`, and allowed to manage the target: `guard_privileged`) must give a reason (10–500
  characters) and say how the identity was checked (`in_person`, `video_call`, `phone_callback`, `other`); the reset
  removes the authenticator app, the recovery codes, the passkeys (optional: keep them) and the trusted devices, signs
  the person out everywhere, is audited `auth.mfa_reset_by_admin` with the reason and the check, and e-mails the person.
  Own account: refused (`own_account`, use the self-service screens). Administrators never see secrets, codes or
  public keys — only "on/off", counts, passkey names and dates.
* **Admin password-reset link (S8 6.4.6).** The administrator starts the reset but never sees or chooses the password:
  the existing one-time reset token (24 h, SHA-256 at rest, single use, revokes the older ones) is e-mailed as a link
  `/reset-password?token=…`; the answer never contains the token; the outbox keeps neither the token nor the link.
  Without SMTP or without an address the call is refused (`mail_not_configured`, `no_email`) — the older
  `POST /users/{id}/reset-token` route (which shows the code when it cannot be e-mailed) stays for that case.
  A password reset never bypasses 2FA (ASVS 6.4.3): the next sign-in still asks for the second factor.

## 7. SSO accounts

When an identity provider (Entra ID, Google, an OIDC or SAML provider) signs a person in, the provider enforces its
own MFA (Entra Conditional Access, Google 2-Step); SmartSched cannot add a second factor to that sign-in without a
password it does not hold, and a second prompt after the IdP's MFA only trains people to click through. Therefore:

* An **SSO-only account** — `auth_source = 'oidc'`, or a linked `user_identities` row and no local password — is not
  offered local 2FA or passkeys (`GET /auth/mfa/status` → `available: false, reason: "sso_account"`; the enrolment
  routes answer 409 `sso_account`), never falls under `auth.mfa_policy`, and the administrator routes refuse it:
  the MFA reset with 409 `sso_account` ("reset it at the identity provider") and the reset link with 409
  `sso_account` (it has no SmartSched password).
* An account with **both** a linked identity and a local password (the break-glass administrator) keeps local 2FA
  for its password sign-in; signing in through the provider skips it.
* **LDAP** accounts (`auth_source = 'ldap'`) check the password at the directory, which has no MFA: local 2FA applies
  to them; the reset link is refused with `directory_account` (the password lives in the directory).
* Follow-up (ASVS 6.8.4): checking the IdP's `amr`/`acr` claims to prove MFA happened there (AU-13, not built).

## 8. Organisation policy

Settings rows (code defaults, nothing seeded): `auth.mfa_policy` = `off` | `optional` (default) | `required_for_roles`;
`auth.mfa_roles` = role codes (default `["ADMIN"]`); `auth.mfa_grace_days` (default 14, 0–90);
`auth.passkeys_enabled` (default true); `auth.passkey_first_factor` (default false). `off` hides enrolment and
skips the challenge (existing factors are kept, not deleted). `required_for_roles`: a person in one of the roles who has
no second factor signs in normally during the grace period (the answer says `mfa_setup_required` + the date); after it
the password step answers `mfa_setup_required` with a short-lived enrolment token that allows only TOTP or passkey
enrolment, and finishing enrolment signs them in. Changing the policy is audited (`auth.mfa_policy`).

## 9. Decisions in one table

| Topic | Decision |
|---|---|
| TOTP | stdlib RFC 6238, SHA-1/6/30 s, ±1 step, replay memory, 160-bit secret Fernet-encrypted |
| WebAuthn | `webauthn==3.0.1` (BSD-3), attestation none, ES256 + RS256, resident key preferred, UV preferred (2nd factor) / required (1st factor), RP ID = public host (full host on sslip.io) |
| Recovery | 10 × 80-bit codes, argon2id, single use, shown once |
| Trusted device | 30 days, SHA-256 stored, httpOnly cookie via the route handler, revocable |
| Challenge token | JWT with its own key (cannot be used as a bearer token), 5 min, single use, row `auth_challenges`, 5 tries |
| Lockout | 5 failures → 15 min, doubling, cap 24 h; per address limits in `security_http` |
| SSO | no local 2FA, admin reset and reset link refused (`sso_account`) |
| Admin | reason + identity check, audit, e-mail, never secrets |
| E-mail | 5 new kinds in `app/emails/kinds.py`, security footer, TR first |
