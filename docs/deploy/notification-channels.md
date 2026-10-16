# Notification channels: what to request from the university, and how to switch each one on

Status: the backend ships complete and tested without real credentials (ledger `notify-channels-apprise-2026-10-15`).
Every channel is **off** until an administrator enters the institution's sender and the KVKK officer's sign-off is
recorded. No demo or placeholder sender exists. Design: [docs/product/2026-10-15-integrations-options.md](../product/2026-10-15-integrations-options.md).

Enter the values in the admin settings (the API is `PUT /api/v1/channels/admin/{kind}`; the settings page follows),
**never in chat, e-mail or a ticket**. The secrets are stored Fernet-encrypted with `APP_SECRET` and are never shown
again; the page shows only "configured". Rotating `APP_SECRET` makes them unreadable, so they must be entered again.

## 0. Prerequisites for every channel

| Item | Who | Where it goes |
|---|---|---|
| The public URL of SmartSched (for example `https://smartsched.uni.edu.tr`) | IT / devops | Calendar settings `public_url` (or `PUBLIC_URL` env). Links in messages and the Telegram webhook use it |
| **KVKK sign-off per channel**: the officer's name, the legal basis (KVKK Art. 9 after Law 7499; for example the Board's standard contract and the date it was notified to the Board) | KVKK officer | `kvkk_signoff: {signed: true, officer, legal_basis}` on each channel. Who signed and when is recorded from the signed-in administrator |
| The content mode per channel: `link_only` (default; "SmartSched'de yeni bildirim" + a link, no personal data) or `full` (room, date, periods, decision, reason; never names or notes) | KVKK officer + owner | `content_mode` |

All channels are abroad (Telegram, Meta, Twilio / Vonage, Microsoft, Slack, the browser push services), so each one
needs its own sign-off. Withdrawing a sign-off (`{signed: false}`) stops sending at once, including rows already queued.

## 1. Browser / phone push (Web Push, VAPID)

Nothing to request from the university. The key pair is generated on the server.

| Step | Value |
|---|---|
| Generate the VAPID key pair (once) | `POST /api/v1/channels/admin/webpush/vapid` (`{"rotate": true}` renews it and removes every browser subscription) |
| Operator contact (the push services' abuse contact) | an e-mail such as `bilgi-islem@uni.edu.tr` → option `contact` |
| KVKK sign-off | as in §0 (the payload is end-to-end encrypted, RFC 8291; the push service sees the endpoint and the size) |

Users press "Bu cihaza bildirim gönder" on Profile. On iPhone / iPad (iOS 16.4+) this works only after "Add to Home
Screen". Accepted push services: `fcm.googleapis.com`, `updates.push.services.mozilla.com`, `*.push.apple.com`,
`*.notify.windows.com`; anything else is refused.

## 2. Telegram (institution bot)

**Request:** a bot created by the university's account with [@BotFather](https://t.me/BotFather) (`/newbot`): its
**bot token** and **user name** (ends with `bot`, for example `SmartSchedUniBot`). Suggested: `/setprivacy` enabled,
`/setjoingroups` disabled (the bot is for private chats only), the university logo and a description.

| Setting | Value |
|---|---|
| `secrets.bot_token` | the token from BotFather |
| `options.bot_username` | filled automatically by "Set up" (`POST /channels/admin/telegram/setup`, which calls `getMe`) |
| `options.update_mode` | `webhook` (default; needs the public URL reachable from Telegram) or `poll` (no inbound traffic; the Profile page asks the bot for updates while the user links) |

"Set up" registers `https://<public url>/api/v1/channels/telegram/webhook` with a random secret header
(`X-Telegram-Bot-Api-Secret-Token`); requests without it are refused. Users link with a one-time deep link
`t.me/<bot>?start=<code>` (10 minutes, single use); `/stop` in the chat or blocking the bot stops the messages.

## 3. WhatsApp (recommended: WhatsApp Business Cloud API)

**Request from the university (Meta Business Manager admin):**

1. A **WhatsApp Business Account** with a **dedicated phone number** of the institution (not a person's number),
   verified business, display name approved.
2. The number's **Phone number ID** (numeric, from WhatsApp Manager > API setup).
3. A **permanent access token** of a System User with `whatsapp_business_messaging` permission (not the 24-hour
   test token).
4. Two **approved message templates** in Turkish (`tr`) and English (`en_US`):
   - a notice template, for example `smartsched_notice`, category *Utility*, body with one variable: `{{1}}` (the
     SmartSched message text, or in link-only mode "SmartSched'de yeni bildirim var. Ayrıntılar: <link>");
   - a verification template, for example `smartsched_code`, category *Authentication*, whose variable `{{1}}` is
     the 6-digit code. If Meta requires the copy-code button parameter for your template, confirm with us before
     approval (Apprise fills the body variable).
5. Confirmation of the billing account (Meta charges per conversation; business-initiated messages need templates).

| Setting | Value |
|---|---|
| `secrets.access_token` | the System User token |
| `options.phone_number_id` | the Phone number ID |
| `options.template_notice`, `options.template_code` | the approved template names |
| `options.lang_tr`, `options.lang_en` | template language codes, default `tr` and `en_US` |

Users enter their phone number and tick the opt-in that names the institution (Meta's opt-in policy); a code is sent
on WhatsApp and typed back on Profile.

### 3b. Optional: WhatsApp Web bridge (unofficial, not recommended)

Only if the Cloud API is not possible. It uses the unofficial WhatsApp Web multi-device protocol, which **violates
WhatsApp's terms; the number can be banned**. Use a **dedicated** institution number with WhatsApp installed on a
phone the IT department keeps.

| Item | Value |
|---|---|
| Container | [`asternic/wuzapi`](https://github.com/asternic/wuzapi) (MIT, Go, on whatsmeow MPL-2.0), one small container in the backend's network, not published to the internet. Measured on 2026-10-15: 7.8 MiB idle, 11.8 MiB with one configured session (not logged in; the sandbox could not reach WhatsApp, so the logged-in figure is unmeasured, est. 30 to 60 MB) |
| Backend env | `WHATSAPP_BRIDGE_URL=http://wa-bridge:8080` (operator configuration, never user input) |
| Bridge env | `WUZAPI_ADMIN_TOKEN` and `WUZAPI_GLOBAL_ENCRYPTION_KEY` (random, kept in SSM), `TZ=Europe/Istanbul` |
| Bridge user | create one user with the admin token (`POST /admin/users {"name":"smartsched","token":"<random>"}`); history sync stays at its default 0 |
| SmartSched setting | `secrets.user_token` = that user's token; `risk_ack: true` (records who acknowledged and when) |
| Link the number | Settings > WhatsApp Web bridge > "QR göster" (`POST /channels/admin/whatsapp_web/connect`), scan with the institution phone (WhatsApp > Linked devices) |
| Session storage | the bridge's data directory on a named volume. On the AWS pod that volume sits on the encrypted gp3 EBS volume (`Encrypted: True`, infra/aws/smartsched_aws.py), so the whatsmeow session files are encrypted at rest; wuzapi's own AES key protects what wuzapi encrypts, and its README does not say the device keys are among it |

Compose sketch for devops (not applied by this change):

```yaml
  wa-bridge:
    image: asternic/wuzapi:1.0
    profiles: ["whatsapp-bridge"]
    environment:
      WUZAPI_ADMIN_TOKEN: ${WUZAPI_ADMIN_TOKEN}
      WUZAPI_GLOBAL_ENCRYPTION_KEY: ${WUZAPI_GLOBAL_ENCRYPTION_KEY}
      TZ: Europe/Istanbul
    volumes: ["wa-bridge-data:/app/dbdata"]
    mem_limit: 96m
    restart: unless-stopped
```

When both WhatsApp senders are on, the Cloud API is used. Users link "WhatsApp" once either way.

## 4. SMS

**Request:** an account with an SMS provider Apprise supports, with a sender number or approved sender ID:

| Provider | Values | Setting |
|---|---|---|
| Twilio | Account SID, Auth Token, a sender number | `options.provider: "twilio"`, `secrets.account_sid`, `secrets.auth_token`, `options.from_number` |
| Vonage | API key, API secret, a sender number | `options.provider: "vonage"`, `secrets.api_key`, `secrets.api_secret`, `options.from_number` |

Turkish providers (Netgsm, İleti Merkezi, ...) are not in Apprise; they need a small adapter (backlog). Ask the legal
officer whether booking notices need İYS registration or count as informational messages.

## 5. Microsoft Teams and Slack (department channels)

Phase 1 posts **new requests awaiting approval** to a department's channel (approvers opt in under Profile >
Notification preferences). A decision about one person never goes to a shared channel. Personal DMs are phase 2
(a Teams bot app installed by policy; Slack: "Sign in with Slack" plus a bot token).

| Service | Request | Where |
|---|---|---|
| Teams | per department: a **Workflows** webhook ("Post to a channel when a webhook request is received"); the URL is on `*.logic.azure.com` or `*.api.powerplatform.com` (Office 365 connectors were retired in 2026) | `PUT /api/v1/channels/admin/teams/departments/{department_id} {"url": ...}` |
| Slack | per department: an **incoming webhook** URL of the institution's Slack app (`https://hooks.slack.com/services/...`) | `PUT /api/v1/channels/admin/slack/departments/{department_id} {"url": ...}` |

These URLs are bearer secrets: they are stored encrypted, shown as the host only, and checked against the vendor
allowlist and the webhook SSRF guard when saved and before every post.

## 6. After entering the values

1. `GET /api/v1/channels/admin`: each channel's `missing` list must be empty and `enabled` true.
2. A test user links the channel on Profile and presses "Test gönder" (`POST /api/v1/me/channels/{id}/test`).
3. `GET /api/v1/channels/admin/deliveries` shows `SENT`, or the redacted error and the next retry (1 min, 5 min,
   30 min, 2 h, 6 h, then `FAILED`).
