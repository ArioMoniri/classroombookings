# Calendar sync, connectors and webhooks: API contract

Status: **implemented** (backend-engineer "calendar sync", 2026-10-08). The reservation-panel frontend builds
against this file; the backend keeps it current. All paths are under `/api/v1`. JSON unless stated.
Decision records: `docs/product/booking-enhancements.md` "Integrations engine (decision 2026-10-08)", T6, A2,
§4.5 (A3) and "Decisions by the user" 2 (KVKK).

Three independent layers, in the order the decision asks for:

1. **Subscription feeds** (`.ics` URLs with a secret token): work with Google Calendar, Outlook / Microsoft 365,
   Apple Calendar and Thunderbird without any configuration by the university.
2. **Native push connectors** (Google Calendar API, Microsoft Graph): optional. They stay hidden until an
   administrator enters the university's own OAuth client (`configured: false` otherwise).
3. **Outgoing webhooks** (HMAC-SHA256 signed, retried, logged): feed Activepieces, n8n, Power Automate, Zapier.

## 0. The KVKK switch and other flags

`integrations.calendar_sync_enabled` (admin, default **on**; the KVKK officer sign-off of 2026-10-08 covers it).
When it is off:

* every token feed (`/calendar/feeds/{token}/…` and the older `/ics/{token}/…`) answers **404**;
* `POST /calendar/connectors/{provider}/connect` answers **403** `{"detail": "calendar sync is turned off"}`;
* queued push jobs are not sent (they are marked `SKIPPED`), nothing new is queued;
* `GET /calendar/sync` reports `enabled: false` so the panel can show "Takvim eşitleme yönetici tarafından
  kapatıldı" / "Calendar sync was turned off by the administrator".

The bearer-authenticated downloads `GET /bookings/feed/user.ics` and `/bookings/feed/room/{id}.ics` (CRBS
parity, a file the signed-in user downloads) are not affected.

`integrations.webhooks_enabled` (admin, default **off**): automations send data outside the pod and need
their own switch (decision text). While off, endpoints can be registered and tested but no event is queued.

## 1. Status for the signed-in user

### `GET /calendar/sync`  (any signed-in user)

```json
{
  "enabled": true,
  "feeds": {
    "tokens": [
      {"id": 7, "label": "Google", "created_at": "2026-10-08T12:30:00", "last_used_at": null, "hint": "x4Qa"}
    ],
    "url_templates": {
      "mine": "https://rezervasyon.example.edu.tr/api/v1/calendar/feeds/{token}/mine.ics",
      "room": "https://rezervasyon.example.edu.tr/api/v1/calendar/feeds/{token}/room/{id}.ics",
      "department": "https://rezervasyon.example.edu.tr/api/v1/calendar/feeds/{token}/department/{id}.ics",
      "room_group": "https://rezervasyon.example.edu.tr/api/v1/calendar/feeds/{token}/room-group/{id}.ics"
    }
  },
  "connectors": [
    {"provider": "google", "label": "Google Calendar", "configured": false, "connected": false},
    {"provider": "microsoft", "label": "Outlook / Microsoft 365", "configured": true, "connected": true,
     "status": "ACTIVE", "account_email": "ayse.yilmaz@uni.edu.tr", "calendar_id": "AAMk…",
     "calendar_name": "Calendar", "last_synced_at": "2026-10-08T12:40:00", "last_error": null,
     "pending_jobs": 0, "failed_jobs": 0}
  ]
}
```

* `hint` is the last 4 characters of a token (show it as `…x4Qa`), so the user can tell links apart. The token itself is shown
  **once**, when it is created; the server keeps only its SHA-256.
* `url_templates` are absolute when the public URL is configured (`integrations.public_url`, else the
  `PUBLIC_URL` environment variable); otherwise they are paths starting with `/api/v1/…` and the panel prefixes
  `window.location.origin`.
* **UI rule: hide a connector whose `configured` is `false`.** Never show a disabled "Connect" button for it.

## 2. Subscription feeds

### Creating, listing and revoking links (JWT)

| Method & path | Body | Answer |
|---|---|---|
| `POST /calendar/feeds/tokens` | `{"label": "Google"}` (optional, ≤ 64 chars, Turkish text kept) | `201` `FeedTokenCreated` |
| `DELETE /calendar/feeds/tokens/{id}` | | `204` (that link stops working at once) |
| `POST /calendar/feeds/reset` | | `201` `FeedTokenCreated`; **every** older link of the user stops working |
| `GET /calendar/feeds/options` | | the feeds the user may subscribe to (below) |

A user may hold at most 10 links (`409` above that). `FeedTokenCreated`:

```json
{
  "id": 8, "label": "Google", "token": "sst_4dJ…(47 chars)", "hint": "x4Qa", "created_at": "…", "last_used_at": null,
  "urls": {
    "mine": "https://…/api/v1/calendar/feeds/sst_4dJ…/mine.ics",
    "room": "https://…/api/v1/calendar/feeds/sst_4dJ…/room/{id}.ics",
    "department": "https://…/api/v1/calendar/feeds/sst_4dJ…/department/{id}.ics",
    "room_group": "https://…/api/v1/calendar/feeds/sst_4dJ…/room-group/{id}.ics"
  },
  "subscribe": {
    "webcal": "webcal://…/api/v1/calendar/feeds/sst_4dJ…/mine.ics",
    "google": "https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2F…mine.ics",
    "outlook": "https://outlook.office.com/calendar/0/addfromweb?url=https%3A%2F%2F…mine.ics&name=SmartSched"
  }
}
```

`subscribe` links are for the "mine" feed; for a room / department / room group feed the panel builds the same
three links from `urls.*` (replace `{id}`, `https://` → `webcal://`, URL-encode for Google and Outlook).
Apple Calendar and Thunderbird take the `webcal://` (or plain `https://`) link.

The pre-existing CRBS endpoint `POST /bookings/feed/token` still works and is the same as `POST
/calendar/feeds/reset` (it answers `{"token", "user_feed", "room_feed"}` as before, plus the fields above).
Its links `/api/v1/ics/{token}/user.ics` and `/api/v1/ics/{token}/room/{id}.ics` keep working with any token.

`GET /calendar/feeds/options`:

```json
{
  "rooms": [{"id": 12, "code": "A101", "name": "A 101", "room_group_id": 3}],
  "room_groups": [{"id": 3, "name": "A Blok"}],
  "departments": [{"id": 5, "name": "Psikoloji"}]
}
```

Rooms are those the user may view (role or room ACL `room.view`), in the booking grid order; room groups are
those with at least one such room; departments are all departments (names in Turkish alphabetical order).

### The feeds (no JWT: the token in the path is the credential)

| Path | Contents |
|---|---|
| `GET /calendar/feeds/{token}/mine.ics` | the token owner's bookings: confirmed, pending approval (`STATUS:TENTATIVE`), cancelled / rejected / expired / withdrawn within the grace period (`STATUS:CANCELLED`) |
| `GET /calendar/feeds/{token}/room/{id}.ics` | confirmed bookings of a room the owner may view, cancelled ones within the grace period |
| `GET /calendar/feeds/{token}/department/{id}.ics` | bookings with that department, only in rooms the owner may view (or the owner's own bookings) |
| `GET /calendar/feeds/{token}/room-group/{id}.ics` | bookings of the group's rooms the owner may view |

Answers:

* `200 text/calendar; charset=utf-8`, `Cache-Control: private, max-age=300`, `ETag: "<sha256 prefix>"`,
  `Content-Disposition: inline; filename="….ics"`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`.
* `304` when `If-None-Match` matches (Google, Outlook and Apple poll; an unchanged calendar costs no body).
* `404 {"detail": "feed not found"}` for an unknown / revoked token, a disabled user, a room / department / room
  group that does not exist or that the owner may not see, and while the KVKK switch is off.
* `429` with `Retry-After` above 60 requests per 5 minutes per link, or 600 per 5 minutes per client address.

Feed contents (RFC 5545, validated with the `icalendar` library in the tests):

* `VTIMEZONE` for the organisation's time zone (`Europe/Istanbul`, +03:00 all year) and `DTSTART;TZID=…`;
  a zone with daylight saving is written in UTC instead.
* `UID:booking-{id}@smartsched` (stable, the same UID the older feeds used), `SEQUENCE` increments whenever a
  booking's time, room, status, notes, user or department changes, `LAST-MODIFIED` and `DTSTAMP` = that
  change's time (so an unchanged feed is byte-identical and the ETag holds).
* `SUMMARY:A 101 – P3`, `LOCATION:A 101`, `DESCRIPTION` = notes and the booking's user, each only when the
  subscriber may see them (CRBS `view_other_notes` / `view_other_users`, owner always).
* Text escaping (`\\`, `\;`, `\,`, `\n`), 75-octet folding that never splits a Turkish letter.
* Window: from `integrations.feed_past_days` (default 90) days ago onwards; cancelled bookings stay
  `integrations.feed_cancelled_grace_days` (default 14) days after the cancellation, so subscribed calendars
  remove them.

## 3. Push connectors (Google Calendar, Microsoft 365)

Off until an administrator enters the university's own OAuth client (section 5). Placeholder client ids are
never shipped; `configured` is `true` only when both the client id and the client secret are stored.

| Method & path | Body / query | Answer |
|---|---|---|
| `GET /calendar/connectors` | | the `connectors` array of `GET /calendar/sync` |
| `POST /calendar/connectors/{provider}/connect` | `{"return_path": "/profile/calendar"}` (optional, must start with `/`) | `200 {"authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?…"}`; `404` unknown provider; `409` not configured; `403` KVKK switch off |
| `GET /calendar/connectors/{provider}/callback` | `?code=&state=` (or `?error=`) — called by the provider, no JWT | `302` to the panel: `{public_url}{return_path}?calendar=connected&provider=google` or `?calendar=error&provider=google&reason=<code>` |
| `GET /calendar/connectors/{provider}/calendars` | | `200 [{"id": "primary", "name": "Ayşe Yılmaz", "primary": true, "can_write": true}]` |
| `PUT /calendar/connectors/{provider}` | `{"calendar_id": "…", "calendar_name": "Dersler"}` (name optional, shown in the panel) | `200` connector; queues a full resync into that calendar (events move out of the previous one) |
| `POST /calendar/connectors/{provider}/resync` | | `202 {"queued": 1}` (`0` when a full sync is already waiting); `403` while the KVKK switch is off |
| `DELETE /calendar/connectors/{provider}` | | `204`; tokens deleted at once and revoked at Google (background); events already written stay in the external calendar |

`calendars`, `PUT`, `resync` and `DELETE` answer `404 {"detail": "not connected"}` when the user has no connection
to that provider. `provider` is `google` or `microsoft`. `reason` codes on the callback redirect: `denied` (the user cancelled),
`state` (unknown / expired / reused state, 10-minute lifetime), `exchange` (the provider refused the code),
`disabled` (KVKK switch off), `not_configured`.

Flow for the panel: call `connect`, then `window.location.assign(authorize_url)`. After the redirect back, read
`calendar=connected|error`, refetch `GET /calendar/sync`, then let the user choose a calendar from
`/calendars` (the provider's primary calendar is used until they do).

What is pushed: the connected user's own bookings in status `BOOKED` from 7 days ago onwards (create, update,
delete; a booking that is cancelled, rejected, moved to another user or deleted is removed). Retries: 1 min,
5 min, 30 min, 2 h, 6 h, then `FAILED`. A refresh token the provider no longer accepts sets `status: "REAUTH"`
(the panel shows "Bağlantıyı yenileyin" / "Reconnect").

## 4. Outgoing webhooks (admin: `setup.settings`)

| Method & path | Body | Answer |
|---|---|---|
| `GET /webhooks/event-types` | | `["booking.created", "booking.updated", "booking.cancelled", "approval.requested", "approval.step", "approval.approved", "approval.rejected", "approval.expired", "approval.withdrawn", "ping"]` |
| `GET /webhooks` | | `[Webhook]` |
| `POST /webhooks` | `{"url", "events": [...], "description"?, "active"?: true}` | `201 Webhook + "secret"` (shown once) |
| `GET /webhooks/{id}` | | `Webhook` |
| `PUT /webhooks/{id}` | any of `url, events, description, active` | `Webhook` (re-activating clears the failure counter) |
| `DELETE /webhooks/{id}` | | `204` (its delivery log goes too) |
| `POST /webhooks/{id}/secret` | | `200 {"secret": "whsec_…"}` (new secret, shown once) |
| `POST /webhooks/{id}/test` | | `202 {"delivery_id": 41}` (a `ping` event, queued even while webhooks are switched off) |
| `GET /webhooks/{id}/deliveries` | `?status=PENDING\|SENT\|FAILED&limit=50` | `[Delivery]`, newest first |
| `POST /webhooks/deliveries/{id}/redeliver` | | `202 Delivery` (a new attempt series of the same event) |

`Webhook`: `{"id", "url", "description", "events", "active", "consecutive_failures", "disabled_reason",
"created_at", "updated_at", "secret_hint": "…a1B2"}`. `events: ["*"]` subscribes to everything.
`Delivery`: `{"id", "webhook_id", "event_id", "event_type", "status", "attempts", "next_attempt_at",
"response_status", "response_ms", "last_error", "created_at", "delivered_at"}`.

URL rules: `https://` anywhere, `http://` too (the in-pod Activepieces is `http://activepieces/…`); no user
info in the URL; link-local and cloud-metadata addresses (`169.254.0.0/16`, `fe80::/10`, `0.0.0.0`) are refused
(`422`), and the resolved address is checked again before each delivery. Redirects are not followed.

### What a receiver gets

```
POST <url>
Content-Type: application/json
User-Agent: SmartSched-Webhooks/1
X-SmartSched-Event: booking.created
X-SmartSched-Delivery: 41
X-SmartSched-Event-Id: 6c1f…(uuid)
X-SmartSched-Timestamp: 1791462000
X-SmartSched-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>

{"id": "6c1f…", "type": "booking.created", "created_at": "2026-10-08T12:40:00Z",
 "actor": {"id": 4, "name": "Ayşe Yılmaz"}, "reason": null, "audit_id": 120,
 "data": {"bookings": [{"id": 311, "status": "BOOKED", "date": "2026-02-16", "start": "08:30", "end": "09:10",
   "period": "P1", "room": {"id": 12, "code": "A101", "name": "A 101"}, "user": {"id": 4, "name": "Ayşe Yılmaz"},
   "department": {"id": 5, "name": "Psikoloji"}, "term_id": 2, "series_id": null}]}}
```

Approval events carry `data.approval = {"id", "status", "step", "booking_id", "series_id", "room_id",
"requested_by"}` and the affected `data.bookings`. Booking notes and e-mail addresses are never sent (KVKK data
minimisation). A `2xx` answer within 10 s is success; anything else is retried after 1 min, 5 min, 30 min, 2 h
and 6 h, then the delivery is `FAILED`. Five deliveries in a row that end `FAILED` switch the webhook off
(`active: false`, `disabled_reason`) and the creator gets an in-app notification.

Verification (Python, also usable in an Activepieces / n8n code step):

```python
import hashlib, hmac, time
def verify(secret: str, body: bytes, timestamp: str, signature: str, tolerance: int = 300) -> bool:
    if abs(time.time() - int(timestamp)) > tolerance:
        return False
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + mac, signature)
```

## 5. Administrator settings (`setup.settings`)

### `GET /calendar/admin/settings`

```json
{
  "calendar_sync_enabled": true,
  "calendar_sync_signoff": {"by": "…", "at": "2026-10-08", "features": ["ai_nl_booking", "calendar_sync"],
                            "legal_basis": "KVKK Art. 9 (Law 7499)"},
  "webhooks_enabled": false,
  "public_url": "https://rezervasyon.example.edu.tr",
  "public_url_source": "setting",
  "feed_past_days": 90,
  "feed_cancelled_grace_days": 14,
  "google": {"client_id": "", "client_secret": {"set": false, "masked": null}, "configured": false,
             "redirect_uri": "https://…/api/v1/calendar/connectors/google/callback"},
  "microsoft": {"client_id": "", "client_secret": {"set": false, "masked": null}, "tenant": "organizations",
                "configured": false, "redirect_uri": "https://…/api/v1/calendar/connectors/microsoft/callback"}
}
```

### `PUT /calendar/admin/settings`

Any subset of: `calendar_sync_enabled` (bool), `webhooks_enabled` (bool), `public_url` (`https://…` or
`http://localhost…`, no path; empty = use `PUBLIC_URL`), `feed_past_days` (0–730), `feed_cancelled_grace_days`
(0–90), `google_client_id`, `google_client_secret`, `microsoft_client_id`, `microsoft_client_secret`,
`microsoft_tenant` (`organizations`, `common` or a tenant GUID / domain). Secrets are write-only (stored
encrypted with `APP_SECRET`, answered masked); send `""` to clear one. Turning `calendar_sync_enabled` on or off
writes a new `calendar_sync_signoff` record (who, when, legal basis) and an audit event. Answer: the `GET` body.

`redirect_uri` is what the administrator registers in the Google Cloud console / Entra ID app registration
(how-to: `docs/deploy/calendar-oauth.md`).

### `GET /calendar/admin/jobs?status=&limit=50`

Push-sync outbox for support: `[{"id", "provider", "user_id", "booking_id", "kind", "status", "attempts",
"next_attempt_at", "last_error", "created_at", "done_at"}]`.
