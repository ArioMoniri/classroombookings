# Calendar sync: configuring Google and Microsoft OAuth clients

SmartSched ships **no** OAuth client. Subscription feeds (`.ics` links) work without any of this; the push
connectors appear in the panel only after an administrator stores the university's own client here. API contract:
`docs/product/calendar-sync-api.md`.

## 0. Prerequisites

* The public address of the panel, `https://<domain>` (no path). Either set `PUBLIC_URL` in `deploy/.env` and pass
  it to the backend container (`PUBLIC_URL: ${PUBLIC_URL:-}` under `backend.environment` in
  `deploy/docker-compose.yml`, devops follow-up), or enter it in the panel (Admin › Entegrasyonlar › Genel adres,
  `integrations.public_url`, which wins over the environment). OAuth redirect URIs and the feed links shown to users
  are built from it; `http://` is accepted only for `localhost`.
* The KVKK switch `calendar_sync_enabled` is on by default (the officer sign-off of 2026-10-08). Turning it off
  makes every feed answer 404 and stops pushing; each change is stored as a dated sign-off record and an audit
  event.

The redirect URIs to register (shown in `GET /api/v1/calendar/admin/settings` as `redirect_uri`):

```
https://<domain>/api/v1/calendar/connectors/google/callback
https://<domain>/api/v1/calendar/connectors/microsoft/callback
```

## 1. Google Calendar (Google Workspace for Education)

1. Google Cloud console › create (or choose) a project owned by the university.
2. APIs & Services › Library › enable **Google Calendar API**.
3. OAuth consent screen: user type **Internal** (only accounts of the university's Workspace domain can connect;
   no Google verification needed). App name "SmartSched", support e-mail of Bilgi İşlem, authorised domain = the
   panel's domain.
4. Scopes: `openid`, `email`, `https://www.googleapis.com/auth/calendar.events`,
   `https://www.googleapis.com/auth/calendar.calendarlist.readonly` (the connector asks for exactly these).
5. Credentials › Create credentials › OAuth client ID › **Web application**; Authorised redirect URI = the Google
   URI above (exact match, https).
6. Copy the client ID (`….apps.googleusercontent.com`) and the client secret (`GOCSPX-…`) into the panel, or:

```bash
curl -X PUT https://<domain>/api/v1/calendar/admin/settings \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Content-Type: application/json" \
  -d '{"google_client_id": "<id>.apps.googleusercontent.com", "google_client_secret": "<secret>"}'
```

The secret is stored encrypted with `APP_SECRET` (like the AI key) and only ever answered masked. Changing
`APP_SECRET` makes stored secrets and user tokens unreadable: enter the secret again and users reconnect.

## 2. Microsoft 365 / Outlook (Entra ID)

1. Entra admin center › App registrations › New registration: name "SmartSched", supported account types
   **Accounts in this organizational directory only** (single tenant), Redirect URI platform **Web** = the
   Microsoft URI above.
2. API permissions › Microsoft Graph › Delegated: `Calendars.ReadWrite`, `User.Read`, `offline_access`, `openid`,
   `email`. Grant admin consent for the tenant (otherwise every teacher sees a consent prompt, or consent is
   blocked by policy).
3. Certificates & secrets › New client secret. Note its expiry (at most 24 months) and put a reminder in Bilgi
   İşlem's calendar: an expired secret makes token refreshes fail and connections show "Bağlantıyı yenileyin".
4. Overview: copy the Application (client) ID and the Directory (tenant) ID. Store them:

```bash
curl -X PUT https://<domain>/api/v1/calendar/admin/settings \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Content-Type: application/json" \
  -d '{"microsoft_client_id": "<app id>", "microsoft_client_secret": "<secret value>", "microsoft_tenant": "<tenant id>"}'
```

`microsoft_tenant` defaults to `organizations` (any work or school account); use the tenant ID to restrict sign-in
to the university.

## 3. Check

* `GET /api/v1/calendar/connectors` as any user: the provider shows `"configured": true`.
* Connect from Profil › Takvim, make a booking, and it appears in the chosen calendar within a minute; cancel it
  and it disappears. `GET /api/v1/calendar/admin/jobs` shows the outbox (status, attempts, last error).
* Retries back off 1 min, 5 min, 30 min, 2 h, 6 h, then `FAILED`. Outbox rows survive restarts; the backend picks
  them up at start.

## 4. Operations notes

* **Feed tokens in URLs.** Calendar apps cannot send headers, so the token is in the path
  (`/api/v1/calendar/feeds/<token>/…`, `/api/v1/ics/<token>/…`). The database keeps only its SHA-256, but reverse
  proxy access logs would keep the URL: exclude these paths from access logs or mask them (nginx
  `location ~ ^/api/v1/(calendar/feeds|ics)/ { access_log off; proxy_pass …; }`, devops follow-up). Users revoke a
  leaked link in the panel.
* **Rate limits** (per backend process): 60 requests per 5 minutes per link, 600 per client address. Google polls
  subscribed calendars every few hours; Outlook and Apple honour the feed's `X-PUBLISHED-TTL` (1 hour).
* **Webhooks** (Activepieces, n8n, Power Automate): off until `webhooks_enabled` is switched on in the same
  settings; each endpoint has its own secret (`X-SmartSched-Signature`, verification snippet in the API contract).
  The optional Activepieces service (`--profile automations`, decision 2026-10-08) is reached from the backend
  at its compose service name (`http://activepieces/…`), which the URL rules allow.
* **KVKK.** Pushed events contain the room, the period, the booking's notes (the user's own) and the department;
  webhooks never carry notes or e-mail addresses. Both providers process data outside Turkey (Art. 9); the
  sign-off record names the legal basis.
