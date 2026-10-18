# Wave 3b: identity, e-mail and integration setup (owner request 2026-10-17 ~20:15 UTC)

Owner's words: "Microsoft and other auth providers must be settable in the admin panels, shared between all admins
(when one sets it, everyone gets it from there). Use Pipedream-like things for easier setup. Identity-provider
settings for logins and invitations, e-mail SMTP and the related settings live in the admin settings tab. Designers
design the password-reset, invite, reservation accept/decline and all other notification e-mails and messages,
following the theme."

Read COMMON.md and WAVE3.md (same folder) first; their rules apply (no commits, test-first, own ports, never
`pkill -f`, nice, Turkish first, 44 px / 16 px on phones). **Many agents run on this 4-core host: do backend and
unit-test work first and start a stack only for the final checks.** Ledger rows `<role> (wave3b-<lane>-2026-10-17)`;
features.yml rows; a `### Wave 3b — <lane> (2026-10-17)` section at the end of docs/ROADMAP.md.

"Shared between all admins": every setting lives in the database for the organisation (never per browser/user),
secrets encrypted at rest like `anthropic_api_key`, write-only in the API (masked), every change audited with the
actor, and the screen shows "Son değişiklik: <ad>, <zaman>". "Pipedream-like": a gallery of connector cards, each
with a guided setup (presets per provider, the exact values to copy into the provider's console such as redirect
URIs and scopes with copy buttons, paste-in fields, a live "Bağlantıyı dene" test, then enable), status
(Bağlı / Yapılandırılmadı / Hata + last check) and a disable switch.

| Lane | Owns (write) | Migration |
|---|---|---|
| W3-IDP identity providers | `backend/app/services/sso.py` (+ new `services/identity/**`), `api/v1/sso.py`, `models/sso*.py`, `services/bookings_ldap.py`, invite paths, `frontend/src/components/identity/**`, `components/admin/ldap-settings.tsx`, `components/admin/users-admin-identity*`, `components/auth/sign-in-page.tsx` (provider buttons only), tests `test_w3b_idp_*` | `0037_identity_providers` (down_revision `0036_error_events`) |
| W3-MAIL SMTP + themed e-mails | new `backend/app/emails/**` (templates + renderer), `services/mail*.py` / the SMTP sender, `services/bookings_notify.py` (rendering path), `services/bookings_i18n.py` (strings), `api/v1/` mail admin routes, `components/admin/email-settings.tsx`, new `components/admin/email/**`, tests `test_w3b_mail_*` | `0038_email_templates` (down_revision `0037_identity_providers`) only if template overrides need a table |
| W3-HUB integrations gallery | new `frontend/src/components/admin/integrations/**`, `frontend/src/app/(app)/admin/integrations/**`, `frontend/src/lib/api/integrations.ts`, one backend status aggregator `api/v1/integrations.py` (read-only, calls the other lanes' status functions), tests `test_w3b_hub_*` | none |
| W3-DES2 e-mail + message design | `docs/design/v3/emails.md`, `docs/design/v3/messages.md`, `docs/design/v3/integrations.md`, `docs/design/v3/wireframes/**` (new files only) | — |

Shared: `frontend/messages/{tr,en}.json` (own namespaces `identity.*`, `email.*`, `integrations.*`), the admin
navigation `components/shell/nav-config.ts` (append one entry), `frontend/playwright.config.ts` (`w3-[a-z]+` pattern
covers `w3-idp.spec.ts` etc.). Existing calendar connectors (`services/calendar_connectors.py`,
`components/settings/calendar-push-admin.tsx`), channels (`services/channels/**`) and webhooks keep their owners:
the hub links to their screens and reads their status; it does not rewrite them.
Ports: W3-IDP 19710/19711 (a mock OIDC/SAML IdP on 19712), W3-MAIL 19720/19721 (SMTP sink 2721), W3-HUB 19730/19731.
