# Integrations options: per-user notification channels and login through the institution's IdP (2026-10-15)

Status: research and recommendation, no code changed. Ledger `integrations-research-2026-10-15`.
It builds on the integrations-engine decision of 2026-10-08 ([booking-enhancements.md, "Integrations engine"](booking-enhancements.md)),
the A1 SSO proposal ([booking-enhancements.md §2.5 A1](booking-enhancements.md)) and the webhook SSRF guard
([ROADMAP.md](../ROADMAP.md), M-41, and the open "operator-level webhook allowlist" item).

The owner's request, verbatim:

> "when someone sends a req for reservation of empty slot it shows first to admin and they approve or not and put reasons why they didnt and these get notified to users by the email or other connections they added also for this part or for the login via section add pipedream like maybe opensource version of it to not to deal with their crederntials"

## BLUF

**What already exists.** Half of the request is built. P1 approvals are done ([ROADMAP.md](../ROADMAP.md), P1): a request for a free
slot goes to the designated approvers, and a rejection must carry a reason (a reason code, or free text for `other`;
`smartsched/backend/app/services/approvals.py`). The requester is told by e-mail (outbox, `bookings_notify.py`) and in-app
(`inapp_notifications`). Two things are missing: **(A)** delivery to the user's other channels, and **(B)** login through
the institution's identity provider.

**(A) Notifications: recommendation.** Build **"Bildirim kanalları" (notification channels) natively** on the e-mail outbox
and integrations worker SmartSched already has. Deliver through **[Apprise](https://github.com/caronc/apprise)**
(`BSD-2-Clause`, a Python library, v2.0.1 on 2026-10-03), plus
**[pywebpush](https://pypi.org/project/pywebpush/)** (`MPL-2.0`) for browser and PWA push.
- The bots belong to the institution: one Telegram bot, one Slack app, a WhatsApp Business number, an SMS account and
  VAPID keys.
- A user links an **address** from the Profile page: a Telegram chat id, a Slack member id, a phone number or a push
  subscription. Users never hand SmartSched an OAuth token or a password.
- No new container. The Apprise import adds an estimated 30 to 60 MB to the backend process (not measured).
- **Why not a "Pipedream Connect" clone:**
  - Notifications do not need per-user OAuth at all.
  - No OSI-licensed clone of Connect exists:
    - Nango is `Elastic-2.0`, and its free self-hosted edition offers only auth and proxy.
    - Activepieces CE has no per-end-user connections, because embedding is an enterprise feature.
    - n8n's licence excludes letting your users connect their own accounts.
    - Pipedream itself is source-available.
  - Details are in §3.

**(A) Lightweight fallback.** Run **[ntfy](https://github.com/binwiederhier/ntfy)** (`Apache-2.0 OR GPL-2.0`, v2.31.0 on
2026-10-15). It is one Go container with SQLite, an estimated 20 to 40 MB. Every user gets a private read-only topic in
the ntfy Android, iOS or web app. Phone push then works with **no third-party account for anybody**, and the message
content stays on the pod; for iOS, only a message ID goes to the upstream relay. E-mail stays as it is.

**(B) Login: recommendation.** Add **direct OpenID Connect from the FastAPI backend, with no broker.** It uses the
authorization code flow with PKCE, nonce and state, through **[Authlib](https://github.com/authlib/authlib)**
(`BSD-3-Clause`, v1.9.1 on 2026-10-14).
- It ships two presets: **Microsoft Entra ID**, pinned to the institution's tenant, and **Google Workspace**, pinned to
  its `hd` domain.
- It also takes any other IdP through generic OIDC discovery, for example a university Keycloak or Authentik, or
  Shibboleth with OIDC.
- No new container, and no measurable RAM.
- SmartSched keeps one client secret per IdP and no user passwords. It drops the IdP's tokens once the login completes.

**(B) Lightweight fallback.** Run **[Dex](https://github.com/dexidp/dex)** as a broker (`Apache-2.0`, CNCF, v2.46.0 on
2026-10-07). It is one Go container, an estimated 30 to 60 MB, and could store its data in the existing Postgres.
- Use it when the institution needs SAML 2.0, or several upstream IdPs at once.
- Caveat: Dex's own connector table marks the Google connector **alpha** and the Microsoft connector **beta**; SAML and
  LDAP are stable ([Dex connectors](https://dexidp.io/docs/connectors/)).

**Not recommended for this pod.** These do not fit one t4g.large with 8 GB, shared with CI, under a $100/month cap:
- **Novu.** It fits the features best, with per-subscriber channels, an Inbox and preferences, and its core is MIT.
  But its official single-VM sizing is 8 GB for the services plus 2 GB for MongoDB and 2 GB for Redis.
- **Activepieces.** The official app sizing is 8 GB, and per-user connections are enterprise-only.
- **Keycloak.** The official base is 1250 MB per pod.
- **Authentik.** The host minimum is 2 GB.
- **Zitadel.** It is `AGPL-3.0-only` and needs about 512 MB plus a database.
- **Others:**
  - Windmill: `AGPL-3.0` plus a proprietary CE binary.
  - Huginn: Rails, single admin.
  - Gotify: Android-only client.
  - Ory Kratos/Hydra: needs your own login UI.
  - Authelia: cannot log in through Google or Microsoft upstream.

## 1. What the owner asked for, against what exists

| Requirement | Status on 2026-10-15 | Where |
|---|---|---|
| A request for an empty slot goes to an admin first | **Built** (P1). Designated approvers (`approves_for`), PENDING requests, optional tentative hold | `app/services/approvals.py`, ROADMAP P1 |
| Approve or reject, **with a reason** | **Built.** A rejection without a reason code or text gets a 422 | `approvals.py` (`REASON_CODES`, "a rejection needs a reason") |
| Notify the user by e-mail | **Built.** Outbox, worker retries, SMTP | `app/services/bookings_notify.py` |
| Notify in-app | **Built** (shell bell) | `inapp_notifications` model |
| Notify through "other connections they added" | **Missing.** This is (A) | — |
| Login without SmartSched holding their passwords | **Missing.** Today there are local accounts and LDAP. This is (B) | `app/api/v1/auth.py`, `app/services/bookings_ldap.py` |
| Outbound events for automation tools | **Built.** Signed webhooks, off by default, SSRF-guarded | `app/services/webhooks.py` |

Event names. The brief says `booking.requested/approved/rejected`. The real names are the audit actions
`approval.request`, `approval.approve` and `approval.reject`, plus `approval.step`, `approval.expire` and
`approval.withdraw`. `publish_event` in `app/services/events.py` publishes them, and `webhooks.py` maps them to
`approval.requested`, `approval.approved` and `approval.rejected`. The reason travels in `DomainEvent.reason` and in the
in-app payload.

## 2. The budget these options must fit

| Fact | Value | Source |
|---|---|---|
| Instance | **t4g.large**: 2 vCPU Graviton (arm64), 8 GB RAM, 4 GB swap, one instance | `infra/aws/smartsched_aws.py` (default `instance_type`), [docs/deploy/AWS.md](../deploy/AWS.md) |
| Compose memory limits today | db 2 GB, backend 4 GB, frontend 1 GB, proxy 256 MB (legacy profile: crbs-db 1 GB) | `smartsched/deploy/docker-compose.yml` |
| Same box also runs | pod CI, including Playwright/Chromium | `infra/aws/smartsched_aws.py` docstring |
| Cost cap | $100/month AWS Budget, with a stop action at 100 % | same |
| Next size up | t4g.xlarge (16 GB) costs twice as much per hour. At about $98/month for compute in us-east-1, it leaves no room for EBS and the EIP under $100 | `FALLBACK_HOURLY` in `smartsched_aws.py`: t4g.large at $0.0672/h |

So the real headroom for new services is **a few hundred MB**. Anything that wants 1 GB or more means a bigger
instance, which breaks the budget, or a second machine. The RAM figures below are the vendors' **official sizing** where
one is published. Otherwise they are marked **est.** and have not been measured on the pod; measure them with
`docker stats` before adopting anything.

## 3. Candidates for (A): notifications, integrations and per-user connections

Licences were read from each project's own LICENSE file on its default branch on 2026-10-15 (links in the table).
Releases come from Docker Hub, PyPI or the GitHub releases page.

| Candidate | Licence, from the repo (SPDX) | Enterprise carve-outs that matter here | Per-end-user connection in the OSS edition? | Self-host footprint | Latest release, health | Fit |
|---|---|---|---|---|---|---|
| **Pipedream Connect** (the reference) | Components repo: "Pipedream Source Available License 1.0", no SPDX id, excludes "any commercial use" ([LICENSE](https://github.com/PipedreamHQ/pipedream/blob/master/LICENSE)) | The Connect platform is SaaS only | Yes, but only as SaaS. Pipedream holds the users' tokens, "encrypted at rest" ([Connect docs](https://pipedream.com/docs/connect)) | Not self-hostable | — | Tokens and data leave the pod. This is the thing the owner wants an open version of |
| **Nango** | `Elastic-2.0`, not OSI ([LICENSE](https://github.com/NangoHQ/nango/blob/master/LICENSE)) | Free self-hosting is "Auth + Proxy" only. Syncs, webhooks, triggers, RBAC, MFA and audit trail are paid ([self-hosting](https://www.nango.dev/docs/guides/platform/self-hosting)) | **Yes**: Connect UI (`nango.openConnectUI`), served by the free image (`FLAG_SERVE_CONNECT_UI=true` in its [compose](https://github.com/NangoHQ/nango/blob/master/docker-compose.yaml)) | nango-server (Node) + Postgres + Redis. RAM: no official figure (est. 400 to 700 MB) | v0.71.13 (2026-10-15), 12.6 k stars | The only real "Connect" clone. **Not open source**, the free tier is limited, and it is a second Node/Postgres/Redis stack. Tokens are AES-256-GCM encrypted with your `NANGO_ENCRYPTION_KEY`; without that key they are stored unencrypted ([security](https://www.nango.dev/docs/guides/platform/security)) |
| **Activepieces CE** | `MIT` outside `packages/ee/` and `packages/server/api/src/app/ee`, which are under the commercial EE licence ([LICENSE](https://github.com/activepieces/activepieces/blob/main/LICENSE)) | "Embedding is available on our enterprise plan" ([embedding](https://www.activepieces.com/docs/embedding/overview)). Embedding is the path for collecting connections from end users | **No.** In CE, connections belong to the project, so the admin owns them | App + Postgres + Redis. `AP_DB_TYPE=PGLITE` and `AP_REDIS_TYPE=MEMORY` allow a single container ([env vars](https://www.activepieces.com/docs/install/configuration/environment-variables)). Official sizing: **8 GB RAM and 2 cores for the app**, plus 1 GB each for Postgres and Redis ([hardware](https://www.activepieces.com/docs/install/configuration/hardware)) | 0.92.3 (2026-10-12), 25 k stars | Already chosen (2026-10-08) for **admin-built** custom flows fed by webhooks. Wrong tool for per-user delivery. Connections are encrypted with `AP_ENCRYPTION_KEY` |
| **n8n** | **Sustainable Use License 1.0**, not OSI; `.ee.` files are under the n8n Enterprise License ([LICENSE.md](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)). n8n itself says "we do not call ourselves open source" ([fair-code](https://docs.n8n.io/faircode-license)) | Internal use is fine, but **not** if you "make it available to your customers to connect their own accounts" ([fair-code](https://docs.n8n.io/faircode-license)) | Licence-excluded, so no | Node + Postgres (SQLite possible). RAM: no official figure checked | 2.44.2 (2026-10-15), 207 k stars, Scorecard 6.7 | **Excluded**: the licence bars exactly the per-user case |
| **Windmill** | `AGPL-3.0` for backend and frontend, `Apache-2.0` for the clients; the "Community Edition" images also contain **proprietary** code ([LICENSE](https://github.com/windmill-labs/windmill/blob/main/LICENSE)) | EE-only: `LICENSE_KEY`, Prometheus metrics, GCP Pub/Sub triggers ([README](https://github.com/windmill-labs/windmill)) | No end-user connect portal | Server + workers + Postgres. "1 worker per 1 vCPU and 1-2 GB RAM" ([README](https://github.com/windmill-labs/windmill)) | v1.837.0 (2026-10-15), 18 k stars | A developer script platform, not notifications. Rejected on 2026-10-08 as well |
| **Novu** | `MIT` ([LICENSE-MIT](https://github.com/novuhq/novu/blob/next/LICENSE-MIT)) except `enterprise/packages/` (ai, api, auth, billing, shared-services, translation), which is under a proprietary licence ([LICENSE-ENTERPRISE](https://github.com/novuhq/novu/blob/next/LICENSE-ENTERPRISE)) | Translations sit in `enterprise/`. Activity tracking, SSO and RBAC are Cloud or Enterprise; Digest and Inbox are in Community ([self-hosted vs cloud](https://docs.novu.co/community/self-hosted-and-novu-cloud)) | **Yes, in the notification sense.** Subscribers carry per-provider chat credentials such as a webhook URL; global provider keys live in the Integration Store ([chat](https://docs.novu.co/platform/integrations/chat)), encrypted with `STORE_ENCRYPTION_KEY` ([community compose](https://github.com/novuhq/novu/blob/next/docker/community/docker-compose.yml)) | api + worker + ws + dashboard + **MongoDB** + Redis + S3. Official single-VM sizing: **4 vCPU / 8 GB for the services, plus 2 GB MongoDB and 2 GB Redis** ([self-hosting](https://docs.novu.co/community/self-hosting-novu/overview)) | v3.19.0 images in the community compose, 40 k stars | **Best feature fit, does not fit the pod.** Chat providers: Slack, Teams, Telegram, WhatsApp Business, Google Chat and more. Revisit with a second instance |
| **Apprise** (library) + **apprise-api** (optional REST sidecar) | `BSD-2-Clause` ([LICENSE](https://github.com/caronc/apprise/blob/master/LICENSE)); apprise-api is `MIT` ([LICENSE](https://github.com/caronc/apprise-api/blob/master/LICENSE)) | None | Not applicable: it sends with the credentials you give it | **None** as a library (est. +30 to 60 MB inside the backend). The sidecar is one small container | 2.0.1 (2026-10-03), 17.6 k stars, Scorecard 5.6, "Maintained" 10/10 | **Recommended delivery layer.** URL schemes cover Telegram `tgram://`, Slack `slack://`, Teams Workflows `workflows://`, WhatsApp `whatsapp://`, Google Chat `gchat://`, Twilio and Vonage SMS, FCM, Web Push `vapid://`, ntfy and Gotify ([README](https://github.com/caronc/apprise/blob/master/README.md)) |
| **ntfy** | `Apache-2.0 OR GPL-2.0` (dual: [LICENSE](https://github.com/binwiederhier/ntfy/blob/main/LICENSE), [LICENSE.GPLv2](https://github.com/binwiederhier/ntfy/blob/main/LICENSE.GPLv2), README "dual licensed") | None | Per-user topics with ACLs and access tokens. `auth-default-access: deny-all` is recommended for private servers ([config](https://docs.ntfy.sh/config/)) | One Go binary + SQLite (est. 20 to 40 MB) | v2.31.0 (2026-10-15), 34.8 k stars | **Recommended fallback** for push |
| **Gotify** | `MIT` ([LICENSE](https://github.com/gotify/server/blob/master/LICENSE)) | None | Per-app tokens | One Go binary + SQLite (est. 15 to 30 MB) | 3.1.1 (2026-09-15) | **Android client only**; no iOS client is listed ([gotify.net](https://gotify.net/)) |
| **Huginn** | `MIT` ([LICENSE](https://github.com/huginn/huginn/blob/master/LICENSE)) | None | No. Its Docker guide describes a single `admin` account ([install](https://github.com/huginn/huginn/blob/master/doc/docker/install.md)) | Rails + MySQL or Postgres (est. 500 MB or more) | v2026.10.14, 50 k stars | Agent automation. It is not notification infrastructure and has no per-user model |

**Conclusion for (A).** The feature the owner has in mind, Pipedream Connect holding each user's OAuth tokens, matters
when the app acts **in the user's own account**, for example writing to their calendar. Telling a user that their
request was rejected does not need that. One **institution-owned** sender per channel, plus a per-user **address**,
covers every channel in the brief:

| Channel | Institution side (admin configures once, stored encrypted) | User side (what the user "connects") | Is a user token involved? |
|---|---|---|---|
| E-mail | SMTP (existing) | Their e-mail (existing) | No |
| Telegram | Bot token | Opens `t.me/<bot>?start=<one-time code>`; the bot receives `/start <code>` ([deep linking](https://core.telegram.org/bots/features)); SmartSched stores the chat id | No |
| Slack | Slack app (bot token) | "Sign in with Slack" (OIDC) proves who they are; SmartSched keeps `https://slack.com/user_id` and drops the token ([Sign in with Slack](https://docs.slack.dev/authentication/sign-in-with-slack/)) | Read once, then dropped |
| Microsoft Teams | Channel posts: a Workflows webhook per department. Office 365 connectors were retired in May 2026 ([MC1181996](https://mc.merill.net/message/MC1181996)). Personal DMs need a Teams bot installed for the user ([proactive messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages)) | Nothing for channel posts. For DMs, the app is installed through Teams policy; SmartSched stores the `conversationId` | No |
| Google Chat | An incoming webhook per space. It is one-way, limited to one request per second per space, and needs Workspace Business or Enterprise ([webhooks](https://developers.google.com/workspace/chat/quickstart/webhooks)) | Nothing for spaces. Per-user DMs need a Chat app (phase 2) | No |
| WhatsApp | WhatsApp Business Cloud API number and token, plus approved templates | Phone number, verified by a code. Explicit opt-in naming the institution ([Meta opt-in](https://developers.facebook.com/docs/whatsapp/overview/getting-opt-in)) | No |
| SMS | The institution's SMS provider account | Phone number, verified by a code | No |
| Browser / PWA push | VAPID key pair | The browser's push subscription (endpoint + keys). On iOS/iPadOS 16.4+ this works only when the app is added to the Home Screen ([WebKit](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)) | No. The payload is encrypted end to end, so the push service cannot read it ([RFC 8291](https://www.rfc-editor.org/rfc/rfc8291)) |
| ntfy (fallback) | ntfy server on the pod, with a publisher token | A private topic plus a read-only token, shown as a QR code | No |

The requirement "SmartSched must not store or handle the users' OAuth tokens or passwords" is therefore met **by
design**. The credentials SmartSched does hold belong to the **institution**, such as bot tokens. They are handled the
same way as the calendar OAuth client secret and the AI key today: Fernet-encrypted with `APP_SECRET`
(`app/core/security.py`), masked in the UI, and audited.

## 4. Candidates for (B): login through the institution's IdP

| Candidate | Licence, from the repo (SPDX) | Enterprise carve-outs that matter here | Login with Google / Entra upstream in OSS? | Footprint | Latest release, health | Fit |
|---|---|---|---|---|---|---|
| **Direct OIDC** (Authlib in the backend) | Authlib `BSD-3-Clause` ([LICENSE](https://github.com/authlib/authlib/blob/main/LICENSE)) | None | Yes. SmartSched is the relying party of Entra ID and Google directly | **0 containers**, a library | Authlib 1.9.1 (2026-10-14) | **Recommended.** The PKCE, state and encrypted-secret code already exists in `app/services/calendar_connectors.py` |
| **Dex** | `Apache-2.0` ([LICENSE](https://github.com/dexidp/dex/blob/master/LICENSE)) | None | Yes. Connectors: Microsoft (beta), Google (alpha), generic OIDC (beta), SAML 2.0 (stable), LDAP (stable) ([connectors](https://dexidp.io/docs/connectors/)) | One Go container; storage in SQLite or Postgres (est. 30 to 60 MB) | v2.46.0 (2026-10-07), 11 k stars, Scorecard 7.8 | **Recommended fallback** when SAML or several IdPs are needed |
| **Keycloak** | `Apache-2.0` ([LICENSE.txt](https://github.com/keycloak/keycloak/blob/main/LICENSE.txt)) | None (Red Hat sells support, not features) | Yes: identity brokering (OIDC, SAML), LDAP and Kerberos user federation | JVM + Postgres. Official base: **1250 MB per pod** ([sizing](https://www.keycloak.org/high-availability/multi-cluster/concepts-memory-and-cpu-sizing)) | 26.8.1 (2026-10-13), 37 k stars, Scorecard 8.0 | The most capable. Too heavy for this pod; right if the institution already runs one, and then SmartSched simply uses generic OIDC against it |
| **Authentik** | `MIT` outside `authentik/enterprise/` (EE licence) and `website/` (CC BY-SA 4.0) ([LICENSE](https://github.com/goauthentik/authentik/blob/main/LICENSE)) | Enterprise directory features. OAuth and SAML sources are in the MIT part | Yes (OAuth/OIDC sources for Google and Entra) | server + worker + Postgres. Redis was removed in 2025.10 ([release notes](https://docs.goauthentik.io/releases/2025.10/)). Host minimum: **2 CPU / 2 GB** ([install](https://docs.goauthentik.io/install-config/install/docker-compose/)) | 2026.8.4 (2026-10-14), 26 k stars | Good, but 2 GB does not fit |
| **Zitadel** | **`AGPL-3.0-only`**; `proto/` and `apps/docs/` are Apache-2.0; `apps/login/` and the client packages are MIT ([LICENSING.md](https://github.com/zitadel/zitadel/blob/main/LICENSING.md), [LICENSE](https://github.com/zitadel/zitadel/blob/main/LICENSE)) | A commercial licence is offered to avoid AGPL duties | Yes (IdP brokering) | Go + Postgres. "Approximately 512MB of RAM", plus the database ([production](https://zitadel.com/docs/self-hosting/manage/production)) | v4.19.5 (2026-10-15), 15 k stars | AGPL for a component the institution would modify or extend is a licence review item; RAM is borderline |
| **Ory Kratos + Hydra** | `Apache-2.0` ([Kratos](https://github.com/ory/kratos/blob/master/LICENSE), [Hydra](https://github.com/ory/hydra/blob/master/LICENSE)) | OSS Kratos is "intended for single-tenant use"; SAML (Polis), organisations and multi-tenancy are under the **Ory Enterprise License** ([OEL](https://www.ory.com/docs/self-hosted/oel), [multi-tenancy](https://www.ory.com/docs/kratos/guides/multi-tenancy-multitenant)) | Yes (social sign-in via OIDC), but you build the login UI | Two Go services + Postgres + a self-service UI (est. 100 to 200 MB) | v26.2.0 (2026-03-20), Scorecard 6.7 / 5.8 | Too much assembly for a scheduling app |
| **Authelia** | `Apache-2.0` ([LICENSE](https://github.com/authelia/authelia/blob/master/LICENSE)) | None | **No.** It is an OIDC *provider* for its own file or LDAP users; the "OpenID Connect 1.0 Relying Party" item is still at the planning stage ([roadmap](https://www.authelia.com/roadmap/prologue/introduction/)) | One Go container (small) | 4.39.28 (2026-09-17), Scorecard 9.8 | Cannot do "log in with the institution's Microsoft/Google account" |

**Conclusion for (B).** For Entra ID and Google Workspace, the institution's IdP already *is* the broker: it holds the
passwords and the MFA. The authorization code flow means SmartSched never sees a password. A broker container adds
value only when SmartSched must speak SAML or juggle several IdPs. Dex covers that case at a few tens of MB.

## 5. Architecture of the recommendation

### 5.1 Containers and RAM

| Item | Recommended (A) + (B) | (A) fallback adds | (B) fallback adds |
|---|---|---|---|
| New containers | **None** | `ntfy` (`binwiederhier/ntfy:v2.31.0`, profile `push`, `mem_limit: 96m`), behind nginx at `/push/` | `dex` (`ghcr.io/dexidp/dex:v2.46.0`, profile `sso-broker`, `mem_limit: 128m`), behind nginx at `/dex/`, database `dex` in the existing Postgres |
| Backend dependencies | `apprise==2.0.1`, `pywebpush==2.5.0`, `authlib==1.9.1` | — | — |
| RAM | est. +30 to 60 MB inside the backend's existing 4 GB limit | est. 20 to 40 MB idle | est. 30 to 60 MB idle |
| Inbound exposure | `POST /api/v1/channels/telegram/webhook`, which checks `X-Telegram-Bot-Api-Secret-Token` ([setWebhook](https://core.telegram.org/bots/api#setwebhook)); or long polling from the worker, with nothing inbound. OIDC callback `GET /api/v1/auth/oidc/{provider}/callback` | ntfy web/app endpoint | Dex issuer and callback |

For comparison, the minimum combination that is *not* recommended (Novu + Keycloak) would add more than 12 GB
following the vendors' own sizing.

### 5.2 Data (new tables, sketched)

- `user_channels`: id, user_id, kind (`telegram|slack|teams|gchat|whatsapp|sms|webpush|ntfy`), `address_enc` (Fernet:
  chat id, member id, phone, push subscription JSON or ntfy topic), `display_hint` (masked, e.g. `+90 5•• ••• •• 12`),
  verified_at, status (`active|blocked|failed`), last_error, created_at.
- `channel_link_codes`: sha256(code), user_id, kind, expires_at (10 min), used_at. Single-use, the same pattern as the
  calendar `state`.
- `notification_prefs`: user_id, event (`approval.decided`, `approval.requested` for approvers, `booking.cancelled`, …),
  kind, enabled. Default: e-mail and in-app on; the rest off until linked.
- The existing `notification_outbox` (mail queue, migration 0021) gains a `channel_id` and kind instead of a second
  queue, so retries, backoff and the delivery log are shared.
- Settings group `channels.*` (admin only, encrypted, masked, audited): telegram bot token, Slack app client id/secret
  and bot token, WhatsApp phone-id and token, SMS provider keys, VAPID private key, ntfy publisher token, and a
  per-channel `enabled` flag plus a `content` flag (`full|link_only`; see §6).

### 5.3 How a user connects a channel from the Profile page

`frontend/src/app/(app)/profile/page.tsx` gets a **"Bildirim kanalları"** card that lists the channels the admin
switched on.

1. **Telegram.** "Bağla" calls `POST /api/v1/me/channels/telegram/link`, which returns a one-time code and the
   `https://t.me/<bot>?start=<code>` deep link: QR on desktop, button on mobile. The user presses Start in Telegram. The
   bot update `/start <code>` arrives; SmartSched hashes the code, finds the user, stores the `chat.id` and replies
   "Bağlandı ✓". If the user later sends `/stop` or blocks the bot, the channel becomes `blocked`.
2. **Slack.** "Sign in with Slack" runs OIDC against the institution's Slack app. SmartSched keeps
   `https://slack.com/user_id` and `team_id`, checks that `team_id` is the institution's workspace, and discards the
   tokens. Messages are sent as the bot, through `chat.postMessage` to the member id.
3. **WhatsApp / SMS.** The user enters a phone number and receives a 6-digit code: on WhatsApp through an approved
   template, or by SMS. Entering the code verifies the channel. For WhatsApp, the opt-in text names the institution, as
   Meta's policy requires.
4. **Web Push.** "Bu cihaza bildirim gönder" calls `PushManager.subscribe({applicationServerKey: VAPID public})`, and
   the subscription JSON is posted to SmartSched. On iOS, the card tells the user to add the app to the Home Screen
   first.
5. **ntfy (fallback).** SmartSched creates an ntfy user with read-only access to a random topic `u-<128-bit>` and shows a
   QR code with the server URL, topic and token for the ntfy app.
6. **Teams / Google Chat.**
   - **Phase 1:** channel or space posts that the admin configures per department.
   - **Phase 2:** personal Teams DMs through a Teams bot app. Personal Google Chat DMs need a Chat app instead.
   - A user never pastes their own webhook URL. That URL is a bearer secret, and accepting it would reopen SSRF (§5.6).
7. Every channel has **"Test gönder"** and **"Kaldır"**. Removing a channel deletes the stored address at once. Each
   connect and disconnect is an audit event (`channel.link` / `channel.unlink`).

### 5.4 How SmartSched triggers a notification without seeing a user's token

```
approver rejects (POST /approvals/{id}/decide, reason required)
  └─ approvals.py → publish_event("approval.reject", reason=…, payload={room, dates, reason_code, reason_text})
       ├─ audit row                                (existing)
       ├─ legacy e-mail + in-app                   (existing)
       ├─ webhooks subscriber → webhook_deliveries  (existing, off by default)
       └─ NEW channels subscriber (same transaction):
            for each recipient (requester; approvers for approval.request):
              for each active user_channel allowed by notification_prefs:
                 INSERT notification_outbox(kind, channel_id, event, audit_id, status=PENDING)
  commit
  └─ integrations worker (kick_after_commit → drain):
       row → render the template in the user's language (bookings_i18n, "link_only" if the channel is set so)
           → decrypt the institution credential + the user address at send time only
           → Apprise (tgram:// slack:// whatsapp:// workflows:// gchat:// twilio:// ntfy://) or pywebpush
           → SENT / FAILED with retries (1 min … 6 h, same as webhooks); 403 "blocked" → channel status=blocked
```

- The subscriber only queues. Nothing calls out inside the booking transaction, which is the rule stated in the
  `events.py` docstring.
- SmartSched never holds a user OAuth token or password. It holds institution credentials, which are encrypted at rest
  and decrypted only in the worker, and user addresses, which are encrypted at rest because phone numbers are personal
  data.
- The rejection reason reaches every channel the user linked. A `link_only` channel shows "Talebiniz sonuçlandı — ayrıntı
  için SmartSched'i açın" and a deep link instead.

### 5.5 How login maps an IdP identity onto a SmartSched user and role without escalation

Flow:

`GET /api/v1/auth/oidc/{provider}/start` creates a state (stored hashed, 10 min), a nonce and a PKCE S256 verifier
(encrypted). It reuses the helpers of `calendar_connectors.py`, then redirects to the IdP.
`GET …/callback` exchanges the code and validates the ID token: signature through JWKS, exact `iss`, `aud`, `exp`,
`nonce`. It then applies the rules below. On success it issues **SmartSched's own session token, exactly as the LDAP
path does**, records `auth.login` with method `oidc` in the audit log, and **drops the IdP access and refresh tokens**.

Rules (each one closes a known escalation path):

1. **The identity key is `(iss, sub)`, never the e-mail.**
   - Microsoft says `email` and `preferred_username` are mutable and "can't be used to make authorization decisions".
     It also says to use `sub` or `oid`, with `tid` ([Entra ID token claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference)).
   - Google says to "use `sub` … as the unique-identifier key"
     ([Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)).
   - New table `user_identities(user_id, provider, issuer, subject, tenant_id, email_at_login, last_login_at)`, unique
     on `(issuer, subject)`.
2. **Tenant and domain pinning.**
   - Entra: use the tenant-specific authority `https://login.microsoftonline.com/{tenant-id}/v2.0`, not `/common`, so
     `iss` is compared exactly. Reject the consumer tenant `9188040d-6c67-4c5b-b112-36a304b66dad`, and refuse guests by
     default (`idp` ≠ `iss`). Microsoft advises treating guests as brand-new users.
   - Google: require the **`hd` claim** to equal the configured domain. Google warns that the `hd` request parameter is
     only a UI hint. Also require `email_verified`.
3. **No silent account takeover by e-mail.**
   - A first OIDC login whose e-mail matches an existing local or LDAP account is **not** linked automatically if that
     account has an ADMIN role, any `approves_for` scope, or an elevated custom role. Such accounts link from Profile →
     "Kurumsal hesabı bağla" while signed in the old way, which proves both sides. An admin can also pre-bind an
     identity.
   - Auto-linking of ordinary accounts by verified e-mail is a setting that is off by default.
4. **Roles come only from an admin-maintained mapping, never from the IdP's role names.**
   - With no mapping, a just-in-time user gets the configured `default_role_id`, as LDAP does in
     `bookings_ldap.py`. That is the lowest role.
   - For Entra, the recommended source is **app roles** (the `roles` claim) assigned to groups in the app
     registration. They avoid the group-overage problem: more than 200 groups in a JWT drops the `groups` claim.
   - Otherwise, map immutable **group object IDs**, not display names.
   - For Google, group membership needs the Directory API and a service account; that is an open question (§8).
5. **The IdP cannot grant ADMIN by default.**
   - `allow_admin_mapping` is false. Turning it on needs an existing admin and is audited.
   - A **break-glass local admin** always keeps local login, even when "OIDC only" is switched on for everyone else (A1
     acceptance in booking-enhancements.md).
6. **Re-evaluation on every login.**
   - The mapping is applied again at each login, so a removed group demotes the user. A demotion bumps `token_version`
     (`users.token_version`, already used to revoke sessions).
   - `is_active=false` in SmartSched always wins.
   - `users.auth_source` gains `oidc`, which fits `String(8)`. OIDC users have no `password_hash`, so the local password
     path refuses them, the same way it treats LDAP accounts.
7. **Deprovisioning gap.** Without SCIM, a user deleted at the IdP can no longer log in, but an existing SmartSched
   session lives until it expires. Keep the session TTL short for OIDC users until SCIM (A1) lands.

The same Entra and Google app registrations that calendar sync already asks the admin to create
(`integrations.{google,microsoft}_client_id`) can serve login. Login only adds a redirect URI and the
`openid profile email` scopes. That means one registration for the IT department to manage, not two.

### 5.6 Webhooks, SSRF and the operator allowlist

- The channel dispatcher does **not** go through `app/services/webhooks.py`. Its targets are fixed provider hosts
  (`api.telegram.org`, `slack.com`, `graph.facebook.com`, the SMS provider) and the admin-configured Workflows and
  Google Chat URLs.
- Two inputs can still be steered by a user or an admin, and both must pass the existing M-41 guard: save-time and
  send-time resolution, plus the connect-time `GuardedBackend`, reused rather than copied.
  - **Web Push endpoints**, which come from the browser and could be forged. Restrict them further to an allowlist of
    real push services: `fcm.googleapis.com`, `updates.push.services.mozilla.com`, `*.push.apple.com`,
    `*.notify.windows.com`.
  - **Admin-entered Workflows and Google Chat webhook URLs.** Allow only `chat.googleapis.com` and the hosts
    that Workflows issues webhook URLs on (`*.logic.azure.com` and the Power Platform hosts; confirm at build time).
- The in-pod ntfy (fallback) is reached at an **operator-set** `NTFY_URL=http://ntfy:80`, from configuration rather than
  user input. It therefore needs no exception in the webhook guard.
- If the owner later chooses an in-pod engine fed by **webhooks** (Activepieces, or Novu on a second box reached
  privately), the open ROADMAP item "operator-level webhook allowlist (env, empty by default)" becomes a prerequisite.
  Until then, `webhooks.py` refuses those URLs. `docs/deploy/calendar-oauth.md` and `docs/product/calendar-sync-api.md`
  still say they are allowed, which ROADMAP already flags.

## 6. KVKK / GDPR

- **Self-hosting keeps the hub on the pod.** Preferences, addresses, the outbox and the delivery log stay in the
  SmartSched Postgres. This is the data-residency advantage over Pipedream Connect or Novu Cloud.
- **The channels themselves are abroad**: Telegram, Slack, Meta (WhatsApp), Microsoft and Google, which depends on the
  tenant's region, and the browser push services. Every message sent through them is a cross-border transfer. After
  Law 7499, Art. 9 works in three tiers:
  - an adequacy decision; as of July 2026 there were none;
  - an appropriate safeguard such as the Board's standard contract, which must be notified to the Board within five
    business days of signature;
  - otherwise, only the limited incidental cases of Art. 9(6)
    ([Köksal](https://koksal.av.tr/en/knowledge-centre/how-to-compliantly-transfer-data-abroad-from-turkiye/),
    [Erdem & Erdem](https://erdem-erdem.av.tr/en/insights/public-announcement-on-key-considerations-for-standard-contracts-to-be-used-in-the-cross-border-transfer-of-personal-data),
    [Mondaq](https://www.mondaq.com/cross-border-transfer-of-personal-data-and-key-considerations/1836354)).

  Recurring booking notifications are unlikely to count as incidental. **Each foreign channel therefore needs the KVKK
  officer's sign-off**, recorded the same way as the 2026-10-08 sign-off for AI booking and calendar sync: who, when,
  which channel, and the legal basis.
- **Minimisation by design.**
  - External messages carry room, date, periods, the decision and the reason. They never carry booking notes, other
    people's names or e-mail addresses, which is the same rule as the webhook payloads.
  - Each channel has a `link_only` switch for the strictest reading.
  - **Web Push** content is end-to-end encrypted (RFC 8291), so the push service sees only ciphertext and the endpoint.
  - **ntfy on iOS** forwards only a message ID, as "New message", to the upstream relay, and the app then fetches the
    content from the pod ([ntfy config](https://docs.ntfy.sh/config/)).

  These two are the only push paths whose *content* never leaves the pod.
- **Login.** Entra ID and Google already hold these identities, because the institution chose them. OIDC sends
  SmartSched only the ID token claims requested (`openid profile email`). SmartSched stores `(iss, sub, tid)` and the
  e-mail at login, and no IdP tokens.
- **Data subject rights.** Unlinking a channel deletes its address immediately. KVKK export and delete (A4) must include
  `user_channels`, `user_identities` and the outbox rows.

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Bot or token compromise: an institution credential leaks | Spam in the institution's name | Fernet at rest, admin-only, masked, audited; rotate from the settings page; one token per channel, so the blast radius stays small |
| A user links someone else's chat or phone | Notifications go to the wrong person | One-time codes (10 min, single use, hashed); phone verified by code; Slack verified by OIDC |
| Delivery failures and silent drops (Teams Workflows changes, WhatsApp template rejections, a bot blocked by the user) | Missed decisions | E-mail and in-app stay on by default; per-channel status shown on Profile; blocked channels are flagged, not retried forever |
| Cost: WhatsApp per-conversation charges and SMS charges | Budget | Off by default; admin enables per channel; monthly counter on the admin page |
| Teams DMs need a Teams app and tenant policy | Teams limited to channel posts in phase 1 | Open question 4 |
| IdP misconfiguration (`/common` authority, missing `hd` check) | Anyone with any Microsoft or Google account could log in | Presets that pin the tenant and domain; the backend refuses to enable a provider without them; tests per rule in §5.5 |
| Account takeover through e-mail reuse | Escalation to admin | §5.5 rules 1, 3 and 5 |
| RAM estimates not measured | Pod pressure | Measure with `docker stats` on the pod before adopting a fallback container; `mem_limit` on each |
| Dex's Google connector is alpha | Breakage on upgrade | Use Dex only for SAML or multi-IdP; keep direct OIDC for Google and Entra |
| Licence drift: projects change licence (Zitadel moved from Apache-2.0 to AGPL-3.0 with v3, [blog](https://zitadel.com/blog/apache-to-agpl); n8n is source-available) | Redistribution of SmartSched | Apprise (BSD), Authlib (BSD), pywebpush (MPL, used as a library, unmodified), ntfy (Apache) and Dex (Apache) are all permissive or weak-copyleft; check again at each upgrade |

## 8. Open questions for the owner

1. **Which channels first?** Suggested order: Web Push and Telegram (free, no Meta or Microsoft paperwork), then Slack if
   the institution uses it, then WhatsApp and SMS (cost, opt-in), then Teams and Google Chat DMs (app approval).
2. **The KVKK officer's sign-off per foreign channel**, and the default for external messages: full text including the
   reason, or `link_only`?
3. **SMS provider.** Turkish providers such as Netgsm are not in Apprise's list; a small custom Apprise plugin or a
   direct HTTP adapter would be needed. Do booking notices need İYS registration, or are they informational? This is
   for the KVKK or legal officer.
4. **Teams.** Is posting to department channels enough, or must each user get a personal Teams DM? DMs need a Teams app
   published to the institution's catalog and installed by policy.
5. **IdPs.** Does the institution use Entra ID, Google Workspace, both, or a SAML federation? If SAML, Dex (the fallback)
   is needed. Which **tenant id or domain** should be pinned?
6. **Role mapping source.** Should Entra app roles be assigned to groups (recommended)? For Google, should SmartSched
   read group membership, which needs a service account with Directory API scope, or should roles stay
   SmartSched-managed and only the identity come from Google?
7. **Linking existing accounts.** Should ordinary accounts link automatically by verified e-mail on first login? It is
   off by default; admins and approvers never link automatically.
8. **"OIDC only" mode.** Once SSO works, should local passwords be switched off for everyone except the break-glass
   admin? LDAP stays as it is.
9. **Calendar sync tokens.** Calendar sync (`calendar_connectors.py`) is the one place where SmartSched holds per-user
   OAuth tokens, encrypted, because it writes into the user's own calendar. That is the case a Connect product exists
   for. The only self-hostable Connect product, Nango, is `Elastic-2.0` with a limited free tier and its own
   Node/Postgres/Redis stack. The recommendation is to keep the native encrypted storage, but the owner should confirm
   that this exception is acceptable.
10. **More budget?** If a second instance or a larger budget appears, Novu (MIT core) becomes the better notification
    hub, with Inbox, preferences, digest and per-subscriber channels. The channel subscriber in §5.4 would then call
    Novu's trigger API instead of Apprise, and the Profile page would stay the same.

## 9. Method and sources

Method:
- **Licences:** raw LICENSE, LICENSE.md, LICENSE.txt or LICENSING.md files fetched from each repository's default
  branch on 2026-10-15. The links are in the tables.
- **Releases:** Docker Hub tag dates, PyPI upload times, `git ls-remote --tags` and GitHub releases pages.
- **Stars and OpenSSF Scorecard:** [deps.dev](https://deps.dev/). This session could not reach the GitHub REST API, so
  contributor counts are not given; stars, release cadence and the Scorecard "Maintained" check stand in for them.
- **RAM:** vendor sizing pages where they exist; anything else is marked est.

Sources (beyond the repository files linked inline):
- Pipedream Connect: https://pipedream.com/docs/connect · licence https://github.com/PipedreamHQ/pipedream/blob/master/LICENSE
- Nango: https://www.nango.dev/docs/guides/platform/self-hosting · https://www.nango.dev/docs/guides/platform/security · https://github.com/NangoHQ/nango
- Activepieces: https://www.activepieces.com/docs/embedding/overview · https://www.activepieces.com/docs/install/configuration/environment-variables · https://www.activepieces.com/docs/install/configuration/hardware
- n8n: https://docs.n8n.io/faircode-license · https://github.com/n8n-io/n8n/blob/master/LICENSE.md
- Windmill: https://github.com/windmill-labs/windmill · https://github.com/windmill-labs/windmill/releases
- Novu: https://docs.novu.co/community/self-hosting-novu/overview · https://docs.novu.co/community/self-hosted-and-novu-cloud · https://docs.novu.co/platform/integrations/chat · https://github.com/novuhq/novu/tree/next/enterprise/packages · https://github.com/novuhq/novu/blob/next/docker/community/docker-compose.yml
- Apprise: https://github.com/caronc/apprise/blob/master/README.md · https://pypi.org/project/apprise/
- pywebpush: https://pypi.org/project/pywebpush/
- ntfy: https://docs.ntfy.sh/config/ · https://github.com/binwiederhier/ntfy
- Gotify: https://gotify.net/
- Huginn: https://github.com/huginn/huginn/blob/master/doc/docker/install.md
- Keycloak: https://www.keycloak.org/high-availability/multi-cluster/concepts-memory-and-cpu-sizing
- Authentik: https://docs.goauthentik.io/install-config/install/docker-compose/ · https://docs.goauthentik.io/core/architecture/ · https://docs.goauthentik.io/releases/2025.10/ · https://goauthentik.io/blog/2025-11-13-we-removed-redis/
- Zitadel: https://zitadel.com/docs/self-hosting/manage/production · https://zitadel.com/blog/apache-to-agpl · https://github.com/zitadel/zitadel/blob/main/LICENSING.md · https://github.com/zitadel/zitadel/releases
- Ory: https://www.ory.com/docs/self-hosted/oel · https://www.ory.com/docs/kratos/guides/multi-tenancy-multitenant · https://www.ory.com/docs/ecosystem/projects/
- Authelia: https://www.authelia.com/roadmap/prologue/introduction/
- Dex: https://dexidp.io/docs/connectors/ · https://github.com/dexidp/dex/releases
- Microsoft Entra ID token claims: https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference
- Google OpenID Connect: https://developers.google.com/identity/openid-connect/openid-connect
- Telegram: https://core.telegram.org/bots/features · https://core.telegram.org/bots/api#setwebhook
- Slack: https://docs.slack.dev/authentication/sign-in-with-slack/ · https://docs.slack.dev/reference/methods/users.lookupByEmail
- Microsoft Teams: https://mc.merill.net/message/MC1181996 · https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages
- Google Chat webhooks: https://developers.google.com/workspace/chat/quickstart/webhooks
- WhatsApp opt-in: https://developers.facebook.com/docs/whatsapp/overview/getting-opt-in
- Web Push: https://www.rfc-editor.org/rfc/rfc8291 · https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- KVKK Art. 9 after Law 7499: https://koksal.av.tr/en/knowledge-centre/how-to-compliantly-transfer-data-abroad-from-turkiye/ · https://erdem-erdem.av.tr/en/insights/public-announcement-on-key-considerations-for-standard-contracts-to-be-used-in-the-cross-border-transfer-of-personal-data · https://www.mondaq.com/cross-border-transfer-of-personal-data-and-key-considerations/1836354
- Repository: `infra/aws/smartsched_aws.py`, `docs/deploy/AWS.md`, `smartsched/deploy/docker-compose.yml`, `smartsched/backend/app/services/{events,webhooks,approvals,bookings_notify,bookings_ldap,calendar_connectors}.py`, `smartsched/backend/app/models/system.py`, `docs/ROADMAP.md`, `docs/product/booking-enhancements.md`
