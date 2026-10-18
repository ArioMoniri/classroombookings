# SmartSched security model

Owner request 2026-10-17: "all platform should have the needed security measures and RLS or needed measures".
This file covers the threat model, the controls with the files that implement them, how row-level security works,
and the risks that remain. The first version came from wave 3 lane W3-SEC (ledger `wave3-sec-2026-10-17`); the
follow-up `wave3-sec2-2026-10-17` closed F3, F8, F9, F10 and R12 and moved security.txt into the admin panel.
Update it when a control changes.

## 1. Assets and actors

| Asset | Where | Why it matters |
|---|---|---|
| Personal data (KVKK): names, e-mails, phone links, consents, DSR requests, notifications, teacher wishes, AI usage per person, welcome-guide state | PostgreSQL (`users`, `consents`, `dsr_requests`, `inapp_notifications`, `notify_channel_*`, `constraints` rows with source `TEACHER`, `ai_usage`, `welcome_progress`; the full processing inventory is `kvkk.DATA_CLASSES`, served at `GET /admin/kvkk/inventory`, counted inside `rls.system_scope`) | KVKK Art. 12 requires technical measures. A leak has to be reported. |
| Bookings and approval requests | `bookings`, `booking_series`, `approval_requests` | Integrity: a forged or cancelled booking empties a lecture hall. |
| Credentials | `users.password_hash` (argon2), JWT signing key (`APP_SECRET` / `JWT_SECRET`), Fernet-encrypted settings (AI keys, OAuth clients, SMTP), calendar feed tokens (SHA-256 only) | Any one of these lets an attacker take over accounts or integrations. |
| Planning data and the solver | runs, assignments, imports | Integrity; the cost of a CP-SAT run (DoS). |
| AI provider budget | Settings → AI, `ai_usage` | Money; prompt injection (W3-AI guardrails). |

Actors: anonymous Internet clients (sign-in, password reset, public schedule, calendar feeds with a token); signed-in
teachers, viewers, planners and approvers; administrators; workers (solver queue, outbox, sweepers, KVKK purge); an
attacker holding a stolen session, an uploaded hostile workbook, or a SQL injection / IDOR bug in a route.

## 2. Trust boundaries

```
browser ──TLS── Caddy (edge, HSTS) ── nginx (headers, CSRF fence, real IP) ──┬── Next.js route handler (httpOnly cookie → Bearer) ── FastAPI
                                                                           └── /api/v1/calendar/feeds, /ics  (token in the URL) ─────── FastAPI
FastAPI ── PostgreSQL (per-request RLS role + app.* settings) ; FastAPI ── AI providers / SMTP / webhooks (SSRF guard)
```

## 3. Controls

| Area | Control | Implementation | Tests |
|---|---|---|---|
| Passwords | argon2id; legacy CRBS bcrypt / sha1+bcrypt verified and rehashed to argon2 | `smartsched/backend/app/core/security.py` | `tests/test_crbs_*.py` |
| Sessions | HS256 JWT `{uid, role, tv}`, 12 h; `tv` = `users.token_version`. Sign-out, a password change, disabling the account or a role change revokes every token. | `app/core/security.py` (`token_is_current`, `revoke_tokens`), `app/api/deps.py` | ARCHITECTURE "Sessions and token revocation" |
| Browser token | httpOnly cookie, `SameSite=Lax`, `Secure` in production; the browser never sees the JWT | `frontend/src/app/api/v1/[...path]/route.ts` | — |
| CSRF | SameSite=Lax. nginx also refuses state-changing `/api/` requests that the browser marks `Sec-Fetch-Site: cross-site` or whose `Origin` names another host (403) | `smartsched/deploy/nginx/default.conf` (`$smartsched_cross_site_write`, origin check) | `tests/test_w3_sec_hardening.py::test_nginx_security_headers_and_csrf_fence`; exercised with nginx 1.24 (scratch run) |
| Lockout and brute force | Failed sign-ins: 10 per identifier+address and 50 per address in 5 min (`app/core/ratelimit.py`). **New:** every sign-in limited to 60 per client address in 5 min. Reset confirm: 20 per address in 15 min. SSO exchange: 60 per address in 5 min. Own password change: 10 per user in 15 min. Reset requests: 3 per account and 20 per address (`app/core/throttle.py`). | `app/core/security_http.py` | `tests/test_w3_sec_hardening.py` |
| Entra SSO | PKCE + state + nonce, generic error codes, invites bound by verified UPN, the no-escalation rule for mapped roles, a local break-glass admin | `app/services/sso.py`, docs/deploy/sso-entra.md | `tests/test_sso_login.py`, `tests/test_sso_fake_idp.py` |
| Two-step sign-in and passkeys (AU-B, 2026-10-18) | Authenticator app (RFC 6238, secret Fernet-encrypted, a code works once), ten argon2id recovery codes, passkeys (py_webauthn 3.0.1, RP ID = public host), trusted devices (SHA-256, 0/7/30 days). The password step answers `mfa_required` with a single-use challenge signed with its own key (never a bearer token). Lockout: 5 failures → 15 min doubling (cap 24 h), 5 tries per challenge, per-address limits `mfa_verify` / `passkey_sign_in` / `mfa_setup`, per-user `mfa_reauth`. Policy `auth.mfa_policy` off / optional / required_for_roles. SSO-only accounts get no local factor. Admin MFA reset needs a reason and an identity check; admins never see secrets; the reset link e-mails the existing token. Owner-only RLS on the five tables. | `app/services/mfa.py`, `app/services/passkeys.py`, `app/core/totp.py`, `app/api/v1/mfa.py`, alembic `0043_mfa`; docs/research/2026-10-18-auth-backend.md | `tests/test_au_b_*.py` |
| Authorisation | `require_permission` (role ∪ room ACL); no-escalation (`may_grant_role`, `missing_permissions`); object checks in the services (booking owner or `*_other_booking`, feed token owner, DSR owner, own notifications, approver scopes) | `app/api/deps.py`, `app/services/bookings_perms.py`, `bookings.py`, `calendar_feeds.py` (`revoke_token`), `kvkk.py` (`export_zip`), `approvals.py` | `tests/test_crbs_bookings.py` (403 on others' bookings), `tests/test_calendar_feeds.py` (404 on another person's token), `tests/test_wave2_kvkk.py` (404 on another person's export) |
| **Row-level security** (new) | PostgreSQL policies on the per-person tables. Each signed-in request runs as the `smartsched_rls` role with `app.user_id` / `app.perms` set (§4). | `alembic/versions/0035_rls_policies.py`, `app/core/rls.py`, `app/core/db.py`, `app/api/deps.py` | `tests/test_w3_sec_rls_postgres.py`, `tests/test_w3_sec_rls_postgres_api.py` |
| Uploads | Streaming byte caps (413); OOXML zip-bomb inspection (members, sizes, ratio, sheet extent); parsing in an isolated child process with RLIMIT_AS and a timeout; magic-byte format detection; images decoded and re-encoded (no SVG or polyglots); only `/uploads/rooms` is public (nosniff, CSP `default-src 'none'`). **New:** the backend refuses any request body above max(upload, council job) + 1 MiB before reading it, and limits uploads to 30 per user in 10 min. | `app/core/safe_files.py`, `app/core/images.py`, `app/council/formats*.py`, `app/core/security_http.py` | `tests/test_safe_files.py`, `tests/test_w3_sec_hardening.py` |
| Path traversal | Uploads are stored under generated names; the import file download is authenticated; nginx returns 404 for `/uploads/*` except room photos | `app/api/v1/imports.py`, nginx | existing import tests |
| Export injection | Text cells that start with `= + - @ TAB CR` are quoted in CSV and marked quote-prefix in XLSX; ICS TEXT is escaped and drops CR/LF. **New:** the heat-map, invigilation roster / load, scenario-compare and KVKK export CSVs were unescaped and now go through `safe_writer`. A static test keeps every `csv.writer` in `app/` wrapped. | `app/core/export_safety.py`, `app/services/{utilisation,invigilation,scenario_compare,kvkk}.py` | `tests/test_w3_sec_hardening.py::test_every_csv_writer_in_the_app_escapes_formulas` and two behaviour tests |
| SSRF | Webhook, notification channel and CRBS DSN targets are resolved and refused when they point at private, loopback or link-local addresses. **AI provider base URLs** (wave3-sec2): https only, no user info, every resolved address public; link-local, metadata (169.254.169.254, fd00:ec2::254, 168.63.129.16, 100.100.100.200), unspecified, multicast and reserved addresses always refused. A local OpenAI-compatible server (Ollama, vLLM) needs the provider's explicit `allow_local` opt-in, which the admin card shows as a warning. Checked on save (no DNS, 422 `unsafe_url` TR/EN) and before every real request (after DNS). | `app/services/webhooks.py`, `app/services/channels/targets.py`, `app/services/crbs_dsn.py`, `app/ai/providers/url_guard.py`, `app/api/v1/ai_admin.py` | `tests/test_webhooks_ssrf.py`, `tests/test_channels.py`, `tests/ai/test_w3_sec2_provider_ssrf.py` (25) |
| Secrets at rest | Fernet with a key derived from `APP_SECRET`; write-only secret fields; `mask_secret`, `redact_keys`; production refuses default, short or shared secrets (`assert_secure`) | `app/core/security.py`, `app/core/config.py` | `tests/test_no_placeholder.py` |
| CORS | Explicit origin list (`CORS_ORIGINS`) with credentials; in production the browser reaches the API same-origin through Next.js | `app/main.py` | — |
| Page CSP with a nonce (wave3-sec2, F9) | `src/proxy.ts` sends a per-request policy on every page: `script-src 'self' 'nonce-<128 bit>' 'strict-dynamic'` (no `'unsafe-inline'`, no `'unsafe-eval'` outside `next dev`), plus every other rule of nginx's policy (`frame-ancestors 'none'`, `form-action 'self' https://login.microsoftonline.com`, `object-src 'none'`, `base-uri 'self'`). Next.js reads the nonce from the request's CSP header and stamps its own scripts; the root layout passes `x-nonce` to the inline appearance script and next-themes. All pages are dynamic (the root layout reads cookies), so none is prerendered without a nonce. Styles keep `'unsafe-inline'` (style attributes). nginx's own CSP stays as the fallback for API, static and Grafana responses (the `$upstream_http_content_security_policy` map; checked live with nginx 1.24: one CSP per page). | `frontend/src/proxy.ts`, `src/app/layout.tsx`, `src/components/providers.tsx` | `src/proxy.test.ts` (+6); Playwright smoke 5 routes × 1440 / 390 |
| Security headers (new) | nginx: CSP (`default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self' login.microsoftonline.com`, `frame-ancestors 'none'`, and `'self'` only under `/grafana/` for the W3-OPS panels), HSTS on TLS requests, `X-Frame-Options DENY` (SAMEORIGIN for `/grafana/`), Referrer-Policy, Permissions-Policy, COOP, nosniff. A CSP sent by the frontend (a future nonce policy) takes precedence over the one nginx adds. Caddy: HSTS with includeSubDomains, and the same headers only where missing. Backend API responses: nosniff, `X-Frame-Options DENY`, Referrer-Policy. | `smartsched/deploy/nginx/default.conf`, `smartsched/deploy/caddy/Caddyfile`, `app/core/security_http.py` | `tests/test_w3_sec_hardening.py`; nginx 1.24 `-t` plus live curl checks; `caddy adapt` 2.8.4 |
| Real client address (new) | nginx sends `X-Forwarded-For: $remote_addr` (the address after `set_real_ip_from`), not the chain the client wrote. **wave3-sec2 (F3/F8):** the Next.js route handler forwards `x-forwarded-for` / `x-real-ip`; the backend believes them only from a proxy hop (`FORWARDED_ALLOW_IPS`, default `127.0.0.1,::1,172.16.0.0/12`: loopback and Docker's bridge pools) and takes the rightmost entry that is not a hop (`security_http.client_address`), rewriting the ASGI client so the login failure cap and the audit see the browser. uvicorn uses the same list instead of `'*'`. | nginx, `frontend/src/app/api/v1/[...path]/route.ts`, `app/core/security_http.py`, `backend/docker-entrypoint.sh`, `deploy/docker-compose.yml` | `test_nginx_security_headers_and_csrf_fence`, `tests/test_w3_sec2_forwarded.py` (6), `route.test.ts` (2) |
| Grafana and metrics (W3-OPS routing, merged by W3-SEC) | `/grafana/` only through `auth_request` to the SmartSched admin session (admin 204, teacher 403, signed out 302 /login). The client's `X-WEBAUTH-USER` and `Authorization` are always overwritten. Framed same-origin only. `/metrics` and `/metrics/*` answer 404 at the proxy: the backend's Prometheus endpoint trusts private addresses, and nginx is one of them. Grafana has `GF_SECURITY_ALLOW_EMBEDDING=true` and `GF_SECURITY_COOKIE_SAMESITE=lax` (compose), so its own `X-Frame-Options` does not conflict with the proxy's; `deploy/validate.sh` now fails when either is missing (wave3-sec2). | nginx, `deploy/docker-compose.yml`, `deploy/validate.sh` | `test_nginx_grafana_behind_admin_forward_auth_and_metrics_never_routed`; live nginx check with fake upstreams |
| security.txt | RFC 9116 at `/.well-known/security.txt` and `/security.txt`, built by the backend from the institution's settings (wave3-sec2, owner request): `security.contact_email` (required), `security.contact_url`, `security.policy_url` (https), `security.preferred_languages` (default "tr, en"). Administrators set them on Ayarlar › Genel › Güvenlik iletişimi (`PUT /admin/security-contact`, validated, audited `security.contact`, "Son değişiklik: <ad>, <zaman>"); `PUT /settings` cannot bypass the validation. Expires is one year after each request; Canonical uses the panel's public URL (`integrations.public_url` / `PUBLIC_URL`), else the sanitised request host. While unset the file names `security@<host>` and the card warns "Güvenlik iletişim adresi ayarlanmadı". nginx proxies both paths to the backend (nosniff, `default-src 'none'`). | `app/services/security_txt.py`, `app/api/v1/security_contact.py`, nginx, `frontend/src/components/settings/security-contact.tsx` | `tests/test_w3_sec2_security_txt.py` (7), `security-contact.test.tsx` (5) |
| Audit | Append-only `audit_events` (triggers; KVKK windows only); admin tables audited with secrets redacted and client networks stored as an HMAC of the /24 | `app/services/audit.py`, alembic 0014 / 0032 | `tests/test_wave2_kvkk_postgres.py` |
| Logging of PII | Feed URLs are not access-logged; API keys are redacted; no request bodies are logged. One info line logs the seeded admin's e-mail at the first start. | nginx, `app/core/security.py`, `app/services/seed.py` | — |
| Supply chain | **wave3-sec2:** `shadcn` (a code generator) moved to `devDependencies` (`npm audit --omit=dev`: 7 high → 0); the validate gate prints `pip-audit --no-deps -r requirements.lock` and `npm audit --omit=dev` as a report step that never fails it (`pod-ci/gates/audit-report.sh`). `requirements.lock` pins every backend version and pod CI installs with `-c requirements.lock`; images are pinned by digest (`deploy/pins.py`); no third-party LLM gateway library is used (the LiteLLM 1.82.7 / 1.82.8 PyPI releases of March 2026 were malicious): providers are called through `anthropic` and the W3-AI gateway's own code | `smartsched/backend/requirements.lock`, `smartsched/deploy/pins.py` | §6 |

## 4. Row-level security (PostgreSQL)

**What it adds.** The API checks stay the fine-grained rules. RLS is a second fence inside the database: if a route
forgets a `WHERE user_id = …`, or an injected SQL string runs, a signed-in user's transaction still cannot read or
change another person's private rows.

**How a request is scoped.** `get_current_user` (`app/api/deps.py`) calls `rls.bind_user(session, user, perms)` on
PostgreSQL. From then on, SQLAlchemy's `after_begin` hook (`app/core/rls.py`) starts each transaction of that session
with one statement:

```sql
SELECT set_config('app.user_id', '42', true), set_config('app.role', 'TEACHER', true),
       set_config('app.perms', 'book_single.create,room.view,…', true), set_config('app.system', 'off', true),
       set_config('role', 'smartsched_rls', true)
```

All of these are transaction-local, so PostgreSQL drops them at commit or rollback and a pooled connection never
keeps them. The `NOLOGIN` role `smartsched_rls` has no `BYPASSRLS`. It holds SELECT, INSERT, UPDATE, DELETE and
REFERENCES on every table and sequence, including future ones through default privileges, but not TRUNCATE. Running
as this role makes the policies apply even when the application logs in as the table owner or as a superuser, which
is what the compose default `POSTGRES_USER` is.

**System context.** Workers, the CLI, migrations, start-up jobs and unauthenticated routes run as system: the login
role, plus `app.system = on` when that role is itself subject to RLS. The unauthenticated routes are sign-in, reset,
token calendar feeds and the public schedule; each one is protected by its token or by its own design. A deliberate
cross-user step inside a user's request is wrapped in `async with rls.system_scope(session):`.

**Fan-out inserts.** Some requests write a row for someone else, for example a notification to the requester when an
approver decides. PostgreSQL checks `INSERT … RETURNING` against the SELECT policy, so that one INSERT into
`inapp_notifications` / `ai_usage` runs with `app.system = on` (`FANOUT_INSERT_TABLES`). Reads, updates and deletes
of those rows stay owner-scoped.

**Fail-closed.** If a session runs as `smartsched_rls` without the settings, it sees no rows in the per-person
tables (`test_no_context_means_no_rows`).

**Policies** (alembic `0035_rls_policies`). Each one mirrors an existing API right. None adds a right.

| Table | Who passes | API rule mirrored |
|---|---|---|
| `inapp_notifications` | owner; `setup.users` (DSR export / erase); `setup.settings` (retention purge) | `/me/notifications` lists the caller's own; KVKK jobs |
| `consents` | owner; `setup.users`. SELECT also for any signed-in user on `purpose = 'ai_personal'` rows | the AI redactor of every AI call must know who withdrew (`app/ai/personal.py`) |
| `dsr_requests` | owner; `setup.users` | `/me/data-requests`; the admin DSR queue |
| `calendar_feed_tokens` | owner; `setup.users` | own tokens; DSR erase. The token feeds run as system and look rows up by hash |
| `ai_usage` | owner; `planning.admin`, `setup.settings` | per-user usage; the admin usage screens (W3-AI) |
| `constraints` (rows with `source = 'TEACHER'` only) | author (`created_by`); `planning.view/edit/admin`; `setup.users` | Q11: academicians see only their own wishes; coordinators moderate. Every other rule source is unaffected. |
| `bookings`, `booking_series`, `approval_requests` | owner / requester; every booking-module member (`room.view`, any `book_*` right, `planning.*`, `approvals.decide`, `audit.view`, `bookings.skip_approval`, `system.export_bookings`, `setup.rooms/settings/users`) | The booking grid shows everyone's bookings to `room.view`. Approval sweeps, conflict checks and pending-request visibility run inside any member's request, so this policy is a coarse fence: it keeps out accounts that are not members of the booking module, and the owner and `*_other_booking` checks stay in the API. |

**Proof.** `tests/test_w3_sec_rls_postgres.py` covers each of these:

- teacher A's direct SQL returns only A's rows on each table;
- A's UPDATE and DELETE on B's rows affect 0 rows;
- an INSERT in B's name fails with "row-level security";
- TRUNCATE is denied;
- the Administrator and system contexts see everything;
- a connection with no context sees nothing;
- a fan-out notification works;
- `system_scope` works;
- the API paths work, and an unfiltered query injected into a route returns the caller's rows only.

`tests/test_w3_sec_rls_postgres_api.py` re-runs 44 existing tests on PostgreSQL with RLS on: approvals,
approval-first bookings, the sweeper, KVKK, calendar feeds, teacher preferences, CRBS bookings and conflicts. All 44
pass, as they do with RLS off.

**How to run.** These tests use `SMARTSCHED_PG_URL` (for example
`docker run --rm -d -p 19525:5432 -e POSTGRES_PASSWORD=pw postgres:16` →
`SMARTSCHED_PG_URL=postgresql+psycopg://postgres:pw@127.0.0.1:19525/postgres`), else `TEST_POSTGRES_URL` (the pod CI
backend gate's postgres service, so they run in its `make check`), else the local PostgreSQL 16 binaries. Without
any of these they are skipped.

**SQLite** (tests, dev): the migration and the hook are no-ops (`test_rls_migration_is_a_noop_on_sqlite`,
`test_rls_hook_is_a_noop_on_sqlite`).

**Switch.** `SMARTSCHED_RLS=off` disables the hook. Use it only in an emergency: signed-in requests then run as the
login role, so the policies no longer apply to them.

## 5. Rate limits and headers (`app/core/security_http.py`)

One pure ASGI middleware sits inside CORS, so a 429 or 413 still carries the CORS headers. Server-sent event streams
pass through it untouched. The limits are sliding windows kept per process.

- **Per user:** the `uid` of a valid bearer token.
- **Per client address:** the TCP peer, or, when the peer is a proxy hop (`FORWARDED_ALLOW_IPS`; default loopback and
  172.16.0.0/12, the Docker bridge range), the rightmost `X-Forwarded-For` entry that is not a hop: nginx →
  Next.js → FastAPI now carries the browser's address (wave3-sec2, F3). A hop that forwards nothing is not limited
  per address.

Over a limit the answer is 429 with this body and a `Retry-After` header:

```
{code: "rate_limited", limit, retry_after, message_en, message_tr: "Çok fazla istek gönderildi. N dakika sonra yeniden deneyin."}
```

The test environment enforces the limits only when `LIMITS.enforce_in_tests` is set.

## 6. Dependency audit (2026-10-17, offline from this host)

| Check | Result |
|---|---|
| `pip-audit -r smartsched/backend/requirements.lock --no-deps` | No known vulnerabilities (94 pins). |
| `npm audit --omit=dev` (frontend) | 7 high: all from the `shadcn` CLI (`fast-glob` → `micromatch` → `braces` ReDoS, GHSA-vfj7-8cjw-p6xm). The CLI is listed under `dependencies` but is a code generator that the app never imports at runtime. Fix: move `shadcn` to `devDependencies` (frontend ask). `next` 16.4.0: no advisories. |
| LLM gateway libraries | None in the lock or in package.json (`anthropic==1.14.0` only). |

wave3-sec2 (2026-10-17): `shadcn` moved to `devDependencies`, lockfile regenerated with `npm install
--package-lock-only` (npm 10.9.4): `npm audit --omit=dev` before 7 high, after **0 vulnerabilities**. The validate
gate now runs both audits as a report step (`smartsched/deploy/pod-ci/gates/audit-report.sh`, called from
`gates/validate.sh` with `|| true`; `pod-ci/tests/test_audit_report.py`). Hash-pinning the lock (F13) stays on the
roadmap: the repository has no `pip-compile` / `uv` tooling for it yet.

## 7. Residual risks and follow-ups

| # | Risk | Severity | Status / owner |
|---|---|---|---|
| R1 | **Fixed (wave3-sec2)**: was: the Next.js route handler does not forward `X-Forwarded-For`, so every browser request reaches FastAPI from the frontend container's address. Because of that, the per-address login failure cap in `ratelimit.py` (50 in 5 min) is shared by everyone behind it: an attacker can lock out all password sign-ins for 5 min. The new per-address limits skip proxy hops for this reason. | High | Fixed: the handler forwards both headers; the backend reads the client from the trusted hop (§3 "Real client address"). |
| R2 | **Fixed (wave3-sec2)**: uvicorn ran with `--forwarded-allow-ips='*'`; now `FORWARDED_ALLOW_IPS` (default `127.0.0.1,::1,172.16.0.0/12`). The compose file declares no network, so Docker allocates the default one from its 172.16.0.0/12 pools; set the variable to the real subnet when the daemon uses other pools. | Medium | Fixed |
| R3 | **Fixed (wave3-sec2)**: pages carry a nonce + `'strict-dynamic'` CSP from `src/proxy.ts` (Next 16's middleware). `style-src` keeps `'unsafe-inline'` (style attributes cannot take a nonce). | Medium | Fixed |
| R4 | The RLS policies on bookings and approval requests are coarse (any booking-module member), because the services do cross-user sweeps inside members' requests. | Medium (accepted) | API object checks remain the real rule. Tightening them needs the sweeps moved into `rls.system_scope`. |
| R5 | `calendar_connections` (encrypted OAuth tokens), `notify_channel_*` links (phone numbers), `notice_acks` and `multi_bookings` are not under RLS yet: calendar push enqueues jobs for other people inside the actor's request. | Medium | Next wave; needs `system_scope` around the enqueue. |
| R6 | If the database login can neither create `smartsched_rls` nor join it, the policies apply only to non-owner logins. The migration logs a warning. | Low | Deploy note: run migrations as the database owner with CREATEROLE (the compose default). |
| R7 | The rate limits and lockouts are per process (2 uvicorn workers). | Low | Accepted; a shared store (PostgreSQL / Redis) if replicas grow. |
| R8 | The JWT lifetime is 12 h with no refresh rotation. A stolen cookie stays valid until sign-out. | Low | Accepted; sign-out and password change revoke every token. |
| R9 | Fernet key rotation is not supported: changing `APP_SECRET` invalidates the stored secrets. | Low | Documented; re-enter the secrets after a rotation. |
| R10 | The `users/import` CSV is read into memory before its 5 MB check. It is admin-only and behind the 50 MB proxy cap and the new body fence. | Low | Accepted. |
| R11 | **Fixed (wave3-sec2)**: the contact is set in the admin panel; until then the file names `security@<host>` and the admin card warns. | Low | Fixed |
| R12 | **Fixed (wave3-sec2)**: SSRF guard on the provider base URLs (§3 SSRF); the org-wide AI usage aggregates (budget check, budget ratio, admin reports, refusals) run in `rls.system_scope`, proven on PostgreSQL with RLS on (`tests/test_w3_sec2_ai_usage_rls.py`). | Medium | Fixed |
| R13 | DNS rebinding between the provider URL check and httpx's own resolution (the check does not pin the address). | Low | Accepted: the window is short and only the provider key is sent; pinning needs a custom httpx transport. |
| R14 | A browser whose real address lies inside the trusted hop range (a campus LAN on 172.16.0.0/12 reaching nginx directly) is treated as a hop and not limited per address; per-account limits still apply. | Low | Narrow `FORWARDED_ALLOW_IPS` to the compose subnet where that matters. |

## 8. Audit findings, 2026-10-17 (W3-SEC)

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | nginx sent every `/api/v1/calendar/feeds/*` path straight to FastAPI, including the cookie-authenticated `options`, `tokens` and `reset` routes. These answered 401, and the Next.js handler then cleared the session cookie. The result was a sign-out on /my-bookings, and feed links could not be managed through the proxy. | High | **Fixed**: only `<token>/….ics` goes direct (`test_nginx_sends_only_token_feeds_straight_to_the_backend`; browser check through nginx 1.24 at 1440 and 390 px) |
| F2 | No row-level fence in the database: one forgotten filter or an injected SQL string exposes every person's notifications, consents, DSRs, feed tokens, AI usage and teacher wishes | High | **Fixed**: alembic 0035 plus the per-request RLS role (§4) |
| F3 | All browser traffic reaches FastAPI from one address, so the per-address login failure cap can lock out every password sign-in (R1) | High | **Fixed (wave3-sec2)**: the route handler forwards the client address, the backend trusts it from proxy hops only |
| F4 | Six CSV exports wrote cells without formula escaping: room and instructor heat maps, invigilation roster and load, scenario compare, KVKK export | Medium | **Fixed**: `safe_writer`, plus a static guard test |
| F5 | Security headers were incomplete: no CSP, no Permissions-Policy, HSTS only on Caddy, and `X-Frame-Options SAMEORIGIN` | Medium | **Fixed**: nginx and Caddy (§3); Grafana gets a same-origin frame exception |
| F6 | No CSRF defence besides SameSite=Lax for the cookie-authenticated API | Medium | **Fixed**: nginx Sec-Fetch-Site / Origin fence |
| F7 | No rate limits on AI calls, uploads, reset confirm, the SSO exchange or the own password change (current-password guessing with a stolen session) | Medium | **Fixed**: `app/core/security_http.py` |
| F8 | nginx passed the client-written `X-Forwarded-For` chain upstream (`$proxy_add_x_forwarded_for`), and uvicorn trusts `*` | Medium | **Fixed**: nginx `$remote_addr` (W3-SEC); uvicorn `--forwarded-allow-ips=$FORWARDED_ALLOW_IPS` (wave3-sec2) |
| F9 | `script-src 'unsafe-inline'` is needed by Next.js without nonces | Medium | **Fixed (wave3-sec2)**: nonce + `'strict-dynamic'` page CSP in `src/proxy.ts`; Playwright smoke clean apart from F14 |
| F10 | `shadcn` CLI in `dependencies` pulls `braces` ReDoS (7 high in `npm audit --omit=dev`) | Low | **Fixed (wave3-sec2)**: `shadcn` in `devDependencies`; `npm audit --omit=dev` 0 |
| F11 | No `security.txt` | Low | **Fixed**; since wave3-sec2 the contact is set per institution in the admin panel (backend-served) |
| F12 | The backend accepted request bodies of any size when it was reached without nginx | Low | **Fixed**: body fence |
| F13 | `requirements.lock` carries no hashes | Low | **Roadmap**: hash-pinned lock needs `pip-compile`/`uv` tooling; the audit report step runs in the validate gate meanwhile |
| F14 | The CSP check found one violation per page: zod's JIT probe `Function("")` inside try/catch. It is harmless (zod falls back), and page rendering is identical with and without the CSP. | Info | Accepted; no `'unsafe-eval'` |
