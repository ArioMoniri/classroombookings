# Calendar export and sync for academicians (research and design, 2026-10-17)

Ledger `calendar-export-res-2026-10-17`. Owner request (2026-10-17): *"For each academician, their own classes or
their department's classes should be extractable and addable to their calendar: through their connected accounts
(verified), an ICS calendar link or an ICS file. All of these must update on any change, be dynamic, easy to do, and
approved by the user."*

## BLUF

- **About 70 % of the plumbing exists. The part the owner asked for does not.** SmartSched already has hashed,
  revocable per-user feed tokens, RFC 5545 feeds with a Europe/Istanbul VTIMEZONE, ETag/304, rate limits,
  `calendar_sync` consent, KVKK sign-off, Google and Microsoft OAuth push with PKCE, an outbox, backoff and
  revoke-on-disconnect. **But an academician cannot get *their own classes* anywhere**: the personal feed (`mine.ics`)
  and push both carry **bookings only**. P19-T4 "classes in personal calendar feeds" is still open, though the
  user↔instructor link (P19-L1, `Instructor.user_id`) has landed.
- Gaps that block "dynamic, approved, department-scoped":
  1. Class events have **unstable UIDs**: `class-{assignment_id}-{room}-{date}` changes on every re-publish and every
     room move. They also have **`SEQUENCE:0` forever** and a LAST-MODIFIED equal to the run's finish time, so moved
     or cancelled classes are not marked as updates and leave no CANCELLED tombstone.
  2. **Any signed-in user can pull any department's feed** (only room visibility is checked). There is no department
     permission and no per-scope approval.
  3. **One token opens every scope.** A leaked `mine` link also serves every room and department feed.
  4. Push ignores class changes. The integrations worker subscribes only to `booking.*`, `series.*`, `approval.*` and
     `run.activate`. `assignment.move`, `assignment.bulk_move` and `assignment.restore` are published but nothing
     listens for them.
  5. Push writes into the user's **primary** calendar with the broad Google scope `calendar.events` (every
     calendar). There is no "verified account" rule.
  6. The `.ics` files disagree with each other: the run export uses floating times, run-scoped UIDs and is planner-only;
     the browser export uses UTC and yet another UID scheme, and can export a *draft* run.
- **Recommendation.** Make one class-event engine with stable, run-independent UIDs and persisted revisions. Use it
  for all three channels (subscription link, `.ics` file, push to a dedicated "SmartSched – Derslerim" calendar).
  Add two scopes, **Derslerim** (own classes, via `Instructor.user_id`) and **Bölümümün dersleri** (needs a new
  permission or membership). Bind each link to one scope, add a per-scope approval screen, and add a
  verified-account rule for push. The academician flow is **3 taps**: *what* → *how* → *approve*.
- **Expected freshness:** push reaches the calendar within about a minute of a publish or move. A subscription link
  depends on the calendar app: Apple on a Mac follows the user's 5-minute to weekly setting, Outlook takes hours, and
  Google up to about 12 hours (reported up to 24). An `.ics` file never updates. The UI must say this plainly and
  recommend push where the institution has configured it.
- **Work:** 12 tickets, CAL-01…CAL-12 (docs/ROADMAP.md, end). One backend lane runs CAL-01…07 in order with **one**
  migration (next head, `0039_calendar_classes`, down_revision `0038_email_templates` unless a later head lands
  first). One frontend lane runs CAL-08/09 and one persona tester runs CAL-10. CalDAV (iCloud) is deferred to CAL-11.

---

## 1. Current state (code audit, 2026-10-17)

### 1.1 What exists

| Area | Where | What it does |
|---|---|---|
| Feed tokens | `backend/app/services/calendar_feeds.py`, `models/integrations.py` `CalendarFeedToken`, alembic `0011_integrations` | `sst_` + `secrets.token_urlsafe(32)`. Only the SHA-256 is stored, plus a 4-character hint and a label. Up to 10 links per user, each revocable, or all reset at once. `last_used_at` is written hourly. The token is shown once. |
| Feed routes | `backend/app/api/v1/calendar_sync.py` | `/calendar/feeds/{token}/mine.ics`, `room/{id}.ics`, `department/{id}.ics`, `room-group/{id}.ics`. Legacy CRBS routes `/bookings/feed/*.ics` and `/ics/{token}/*` use the same engine. |
| Feed hygiene | same + `core/throttle.py` + `deploy/nginx/default.conf:156-163` | ETag + `If-None-Match` → 304. `Cache-Control: private, max-age=300`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`. Limits: 60 requests per 5 minutes per token, 600 per 5 minutes per address. nginx sends `^/api/v1/(calendar/feeds|ics)/[^/]+/.+\.ics$` straight to the backend with **`access_log off`**, so tokens never reach the logs. |
| ICS renderer | `services/bookings_export.py` `render_calendar` | VCALENDAR with `METHOD:PUBLISH`, `X-WR-CALNAME`, `X-WR-TIMEZONE`, `REFRESH-INTERVAL;VALUE=DURATION:PT60M`, `X-PUBLISHED-TTL:PT60M`. Europe/Istanbul is written as `TZID=` + a VTIMEZONE; zones with DST are written in UTC. Lines are folded to 75 octets. CANCELLED events are `TRANSP:TRANSPARENT`. |
| Booking revisions | `CalendarEventRevision` | A booking fingerprint → `SEQUENCE` + `LAST-MODIFIED` bump. Cancelled, rejected or withdrawn bookings stay as `STATUS:CANCELLED` for `feed_cancelled_grace_days`. A-12: the periods of one submission merge into one VEVENT. |
| Class events | `calendar_feeds.class_events` (A-14) | For **room, room-group and department feeds only**: the active (published) run's meetings, `SUMMARY` = course code(s) + room. No instructor names (KVKK). Horizon `CLASS_HORIZON_DAYS = 200`. |
| Consent | `kvkk.py` purpose `calendar_sync`; `calendar_feeds.require_sync_consent` | While the KVKK switch `integrations.calendar_sync_enabled` is on (admin sign-off, audited), creating a link or connecting push needs the person's active consent (409 `consent_required`). Withdrawing the consent revokes links and disconnects push. An erasure disconnects push first and awaits the provider (≤ 20 s). |
| Push | `services/calendar_connectors.py`, `workers/integrations.py`, models `CalendarConnection`, `CalendarEventLink`, `CalendarSyncJob`, `OAuthState` | Org-supplied OAuth clients (Fernet-encrypted). Authorisation code + PKCE S256, single-use hashed state. Refresh tokens are encrypted. A durable job outbox is deduplicated while pending, uses state-based reconcile and backs off. Google event ids are deterministic (`smartsched{conn}p{booking}`, idempotent insert with 409 → PUT). Microsoft uses `Prefer: IdType="ImmutableId"`. Disconnect deletes the pushed events and revokes the Google grant. The user may choose the target calendar (`calendarList`, writer). |
| Push scopes | same, `GoogleProvider.scopes` / `MicrosoftProvider.scopes` | Google: `openid email calendar.events calendar.calendarlist.readonly`. Microsoft: `offline_access openid email User.Read Calendars.ReadWrite`. |
| Run export | `api/v1/runs.py` `format=ics` → `services/exports.py export_ics` | For planners (`planning.view`). Any run, draft or published. UID `smartsched-run{run}-a{assignment}-w{week}`. **Floating** `DTSTART` (no TZID, no Z). DESCRIPTION = board notes. No SEQUENCE. |
| Browser export | `frontend/src/components/timetable/model/ics.ts` | On `/timetable` (`planning.view`): `.ics` for the subject shown (room, instructor or cohort) of **whatever run is loaded** (it may be a draft). UTC times. UID `smartsched-{run}-{a}-{room}-{date}`. |
| Academician UI | `components/bookings/calendar-sync.tsx` (on /bookings, /my-bookings), `components/settings/calendar-connections.tsx` (Profil) | Makes a private link (https + webcal + "Google'a ekle" / "Outlook'a ekle"), picks a room or department feed, resets links, connects push (only when configured), chooses a calendar, re-syncs, disconnects, and shows "Son eşitleme" and pending/failed job counts. |
| Admin UI | `components/settings/calendar-sync-admin.tsx`, `calendar-push-admin.tsx` (Ayarlar, embedded unchanged by W3-HUB's `/admin/integrations` setup sheet) | KVKK switch, public URL, past days, cancelled grace days, Google / Microsoft client ids, secrets, tenant, redirect URI, job list. |
| Identity | `services/sso.py`, `services/identity/**` (W3-IDP, running) | Org-wide IdPs (Entra, Google Workspace pinned to a hosted domain, OIDC, SAML, LDAP). `UserIdentity` rows (provider, subject, tenant). `sso.set_instructor` links a login to an instructor (audited). |
| Events | `services/events.py` `publish_event` | `run.activate` (publish), `assignment.move`, `assignment.bulk_move`, `assignment.restore`, `assignment.lock/unlock`, `run.delete`, `run.fix`, plus every booking, series and approval event. |

### 1.2 What an academician can do today

The default `TEACHER` role has `room.view` and `book_single.*`, but no `planning.view`.

| Want | Today |
|---|---|
| My bookings in my calendar (link, push) | **Yes** (`mine.ics`; Google / M365 push once an admin has configured it) |
| **My own classes** in my calendar | **No.** `mine.ics` and push carry bookings only (P19-T4 open). The academician can approximate it with the department feed, which holds every class of the department. |
| My department's classes | **Partly.** `department/{id}.ics` holds the department's published classes and its bookings, but **any** user can open **any** department, and there is no push or file. |
| An `.ics` file of my classes | **No.** The run and browser exports need `planning.view` and may come from a draft. |
| Updates on change | Links: rebuilt on every poll, so content is current. But class UIDs churn on re-publish and room moves, SEQUENCE never moves, and removed occurrences just disappear with no CANCELLED tombstone. Push: classes are not pushed at all. |
| Approve per scope | One consent (`calendar_sync`) covers everything. Links are not bound to a scope and there is no preview of what leaves SmartSched. |
| Verified account | Push accepts any Google or Microsoft account the user signs in with. There is no link to the SSO identity, the hosted domain or the tenant (cf. FLE-005, which asks for an M365 tenant default). |
| Revocation | Yes: per link, "reset all", disconnect (events removed, grant revoked), consent withdrawal, and erasure. |
| "Son eşitleme" | Push: `last_synced_at`. Links: `last_used_at` is stored but not shown as "Takviminiz en son … çekti". |

## 2. Industry practice (October 2026)

### 2.1 Feed format (RFC 5545 / RFC 7986)

- **UID** must be globally unique and **persistent** for the same event, because a client matches updates by UID.
  **SEQUENCE** increases on every significant change (time, place, status). **DTSTAMP** and **LAST-MODIFIED** say
  when the object changed. Cancellation is the same UID with `STATUS:CANCELLED` and a higher SEQUENCE
  ([RFC 5545 §3.8.4.7 UID, §3.8.7.4 SEQUENCE, §3.8.1.11 STATUS](https://www.rfc-editor.org/rfc/rfc5545.html)).
  SmartSched's booking events follow this already; class events do not (UID churn, SEQUENCE 0).
- **RRULE + EXDATE / RECURRENCE-ID vs. expanded instances.** A weekly class with holidays, week-limited weeks and
  one-off moves needs an RRULE plus EXDATEs plus overriding VEVENTs with RECURRENCE-ID. Both Microsoft and Google
  warn that recurrence exceptions are where sync drifts: Graph's calendarView delta *expands* series into
  occurrences, and Google's sync guide makes `singleEvents` a fixed choice for the whole sync
  ([Graph event delta](https://learn.microsoft.com/en-us/graph/api/event-delta),
  [Google sync guide](https://developers.google.com/calendar/api/guides/sync)). University timetabling feeds
  (Celcat at Imperial, UCL's Scientia-based timetable) publish **one VEVENT per occurrence**
  ([Imperial iCalendar Direct](https://www.imperial.ac.uk/timetabling/view/icalendar/),
  [UCL subscription help](https://www.ucl.ac.uk/srs/timetable-icalendar-subscription)).
  **Decision: keep expanded occurrences.** SmartSched already expands, and per-occurrence UIDs make a single week's
  move or cancellation a plain update or tombstone. Size stays small: about 14 weeks × 10 meetings ≈ 140 VEVENTs
  (≈ 60 KB) for a personal feed. Keep a department feed under 1 MB, because feeds above that are reported to fail
  in Google ([Revolgy note](https://ask.revolgy.com/en/support/solutions/articles/11000117258-use-an-email-address-to-subscribe-to-a-calendar)).
- **VTIMEZONE.** Europe/Istanbul has been UTC+3 all year since September 2016. A `TZID=Europe/Istanbul` with a
  one-observance VTIMEZONE (what `render_calendar` writes) is correct and readable in Apple, Google and Outlook.
  Floating times (the run export) are wrong for anyone whose device is not set to Istanbul time.
- **RFC 7986** adds `NAME`, `SOURCE` (the URI to refresh from), `COLOR` and `REFRESH-INTERVAL` (a suggested
  *minimum* polling interval) ([RFC 7986 §5.1, §5.7–5.9](https://www.rfc-editor.org/rfc/rfc7986.html)).
  `X-PUBLISHED-TTL` is the older Microsoft hint. Both are only hints: no major client promises to honour them (a
  Mozilla bug discusses the TTL property: [bugzilla 735147](https://bugzilla.mozilla.org/show_bug.cgi?id=735147)).
  SmartSched should add `NAME` and `SOURCE` next to its current `X-WR-CALNAME`.

### 2.2 Subscription links: how others do it, and real refresh lag

| Product | Link model | Revocation |
|---|---|---|
| Google Calendar | "Secret address in iCal format" per calendar | "Reset" invalidates the old address and makes a new one ([Google help 37648](https://support.google.com/calendar/answer/37648)) |
| Moodle | `export_execute.php?…&authtoken=…` per user. Scope is "all" or "courses"; time range is week, month or recent + 60 days ([Moodle docs](https://docs.moodle.org/403/en/Calendar_export)) | Token tied to the user |
| Canvas | Per-user "Calendar Feed" URL, which a school may disable ([Canvas community](https://community.canvaslms.com/t5/Canvas-Question-Forum/Missing-Calendar-Feed-Link/m-p/506141)) | — |
| WebUntis | Teachers and students opt in themselves ("Publish the calendar" under Profile › Data access) and get a private iCal link. Untis warns the sync "can take longer than you are used to" ([Untis help](https://webhelp.untis.at/HTML/WebHelp/uk/untis/wu_ical_kalender_abonnement.htm)) | Opt out by un-publishing |
| Celcat (Imperial) | Per-person link, requested by e-mail or from a dashboard. Warns that **opening** the link makes a static copy and you must **subscribe** instead ([Imperial](https://www.imperial.ac.uk/timetabling/view/icalendar/)). Imperial also runs AutoCalEx, which pushes into Outlook and tags events with a category ([AutoCalEx](https://www.imperial.ac.uk/timetabling/view/autocalex/)) | Deactivating AutoCalEx stops sync but **leaves the events**, which users must delete by hand. This is a lesson: SmartSched must delete what it pushed. |
| UCL (Scientia) | Personal feed shown as a **separate calendar**, not merged into the main one ([UCL](https://www.ucl.ac.uk/srs/timetable-icalendar-subscription)) | — |
| TimeEdit (Twente) | Warns that iCal sync into Outlook can be late, incomplete or wrong, and that only Classic Outlook works well ([UTwente FAQ](https://utwente.nl/en/educational-systems/about-the-applications/timeedit/faq-time-edit)) | — |

Common pattern: **an unguessable per-user URL, opt-in by the user, a separate calendar, reset or revoke, and a
warning that subscription lag is the client's, not ours.**

Real refresh lag (none of these numbers is an official SLA):
- **Google** "From URL": not configurable. Universities and vendors cite up to 12 hours, and some see up to 24
  ([Georgetown](https://politics.georgetown.edu/?p=4126), [Yale](https://chaplain.yale.edu/subscription-religious-holidays-calendar),
  [usecarly](https://usecarly.com/blog/google-calendar-ics-refresh-rate/)).
- **Outlook** "Subscribe from web": several hours, not user-configurable. Desktop Outlook also refreshes at start
  ([nocal](https://nocal.app/help/ics-and-subscriptions/why-subscribed-calendars-dont-update-instantly),
  [Thomaston schools](https://www.thomastonschools.org/SubscribingtotheElectronicEventsCalendar)).
- **Apple Calendar**: on a Mac, Get Info › Auto-refresh can be set from 5 minutes to weekly. On iPhone it follows
  Settings › Fetch New Data ([autocaldata](https://autocaldata.com/guides/apple-calendar)).

So "updates on any change" holds **within minutes only for push**. For links SmartSched serves the fresh state on
every poll, but the client decides when it polls. The UI says this before the user chooses.

**Token scheme.** At least 256 bits of entropy (`token_urlsafe(32)`), only a hash stored, shown once, revocable one
by one, never logged, and `no-referrer`. SmartSched has all of this. What is missing is **binding a token to one
scope** (least privilege) and showing when each link was last fetched.

### 2.3 Caching and rate limiting

A strong `ETag` on the body plus `If-None-Match` → 304 already exists. Two improvements:
1. Compute a **cheap version key** before rendering: scope, active run ids, the newest revision, the settings
   version, and the date. A 304 then costs one or two indexed queries instead of a full build. Calendar apps poll
   every 5 to 60 minutes for each subscriber.
2. Send `Last-Modified` as well, for clients that use `If-Modified-Since`.

Keep 60 requests per 5 minutes per token and 600 per address, answering 429 with `Retry-After`. Use
`Cache-Control: private, max-age=300`, because a shared cache must never store a capability URL.

### 2.4 Push to connected accounts

**Google Calendar API**
- **Least privilege:** `https://www.googleapis.com/auth/calendar.app.created` lets the app *create secondary
  calendars and view, create, change and delete events on them*, and nothing else. It replaces `calendar.events`
  (every calendar) and `calendar.calendarlist.readonly`
  ([Calendar API scopes](https://developers.google.com/calendar/api/auth),
  [calendars.insert](https://developers.google.cn/workspace/calendar/api/v3/reference/calendars/insert?hl=en)).
  Since November 2025 a secondary calendar has one data owner, the user who created it, so create it with **user**
  OAuth, never a service account (same page).
- **Verification:** an *Internal* app in the university's Google Workspace needs no Google review of sensitive
  scopes, although Workspace admins may restrict untrusted client ids
  ([sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification),
  [consent screen](https://developers.google.com/workspace/marketplace/configure-oauth-consent-screen)).
  This matches SmartSched's "the org brings its own OAuth client" model.
- **Upserts:** a deterministic event id (base32hex) makes inserts idempotent, as SmartSched already does. Use
  `events.patch` for updates. Tag every event with `extendedProperties.private.smartsched_uid`. A nightly reconcile
  then lists only SmartSched's events with `privateExtendedProperty=smartsched_uid%3D…` or a constant marker
  ([extended properties](https://developers.google.com/calendar/api/guides/extended-properties)).
- **Incremental sync** (`syncToken`; 410 → wipe and full sync) is for reading changes back
  ([sync guide](https://developers.google.com/calendar/api/guides/sync)). SmartSched is the **only writer** of its own
  secondary calendar, so it does not need a read-sync loop. A nightly diff on the tagged events finds events the
  user deleted or edited and restores them.

**Microsoft Graph**
- `POST /me/calendars` (create a "SmartSched – Derslerim" calendar) needs `Calendars.ReadWrite`, the only and so
  the least-privileged delegated permission for it
  ([create calendar](https://learn.microsoft.com/en-us/graph/api/user-post-calendars?view=graph-rest-1.0)).
  Events go to `/me/calendars/{id}/events`. Keep `Prefer: IdType="ImmutableId"`. For idempotent creates, send a
  `transactionId` (= the SmartSched UID hash) and store the returned id.
- **Delta** (`/me/calendarView/delta`, least privilege `Calendars.Read`) and **change notifications** are for
  reading. Event subscriptions last at most 10,080 minutes (< 7 days), or 1,440 minutes with resource data, and need
  `lifecycleNotificationUrl` handling ([event delta](https://learn.microsoft.com/en-us/graph/api/event-delta),
  [subscription lifetimes](https://learn.microsoft.com/en-us/graph/api/resources/subscription?view=graph-rest-1.0)).
  Microsoft's 2026 guidance pairs notifications with delta for reconciliation, because missed notifications are not
  replayed ([M365 dev blog, June 2026](https://devblogs.microsoft.com/microsoft365dev/migrating-ews-notifications-to-microsoft-graph/)).
  **For SmartSched:** not needed in v1, for the same reason as Google (we are the only writer). A webhook would also
  need a public inbound endpoint, which many on-premises installs lack. Use the nightly reconcile instead.

**CalDAV (iCloud)**
- `caldav.icloud.com`, Apple ID + **app-specific password** (2FA required; managed school Apple IDs may not support
  it; revoking it breaks sync silently) ([Nylas iCloud CalDAV](https://cli.nylas.com/guides/icloud-caldav-settings),
  [OneCal](https://www.onecal.io/blog/how-to-integrate-icloud-calendar-api-into-your-app)).
- Apple users get a good result from the webcal link already (Mac auto-refresh down to 5 minutes). Storing
  password-equivalent secrets is a KVKK and security cost. **Defer** to CAL-11.

**Common rules:** encrypt refresh tokens at rest, refresh them before expiry, and move a connection to `REAUTH` on
`invalid_grant`. Back off exponentially with jitter on 429 and 5xx, and honour `Retry-After`. Upsert and delete are
idempotent and state-based (SmartSched already reconciles against the latest state instead of replaying events).
Disconnecting **deletes the dedicated calendar** (one call), unlike Imperial's AutoCalEx, which leaves the events
behind.

### 2.5 Consent, approval, KVKK

- **Consent per scope** with a preview of exactly what leaves SmartSched. The legal basis for the transfer to
  Google or Microsoft is the person's consent (the `calendar_sync` purpose, already wired, with the admin's KVKK
  sign-off citing Art. 9 as amended by Law 7499). Each scope a person adds is recorded as an approval (audit row
  plus `consent_id` on the subscription).
- **Minimisation** (KVKK Art. 4: relevant, limited and proportionate to the purpose;
  [Akkas summary](https://akkaslaw.com/?p=26992)). Event fields: **course code, section, course title (optional,
  admin), room, start and end, department name.** Never students, enrolment counts, co-instructor names (admin
  option, default **off**), notes, request reasons or board free text (which may hold names; A-14 already strips it).
- **The department scope needs a right to see it:** (a) the user's own department (`users.department_id`), (b) the
  department of a section the user teaches, or (c) a new permission `calendar.department_feed` (for heads of
  department and coordinators; Turkish label *"Bölüm ders takvimini dışa aktarma"*).
- **Revocation and audit:** `calendar.subscription_create / _revoke`, `calendar.push_connect / _disconnect`,
  `calendar.scope_denied`. Show "Son eşitleme" on push and "Takviminiz en son {saat} çekti" on links.
- **Only the published plan:** feeds, files and pushes read `ScheduleRun.is_active` runs only, never drafts or
  what-ifs. A re-publish is a change event.

### 2.6 Testing

- `icalendar` 7.3.0 is already in the backend venv. Round-trip every feed through `icalendar.Calendar.from_ical`.
  Lint it for: CRLF, ≤ 75-octet lines, one VTIMEZONE per TZID used, unique UIDs, DTSTAMP on each VEVENT, SEQUENCE
  never decreasing across two snapshots, and no PII field names in the output.
- Snapshot tests: a golden `.ics` for a fixed clock (Bahar 2026, `tests/crbs_env`). Then publish → move one week →
  re-publish → cancel, and assert the same UID with a higher SEQUENCE, a new time, and a CANCELLED tombstone.
- Provider tests on `httpx.MockTransport` (the pattern already used in `tests/test_calendar_connectors.py`).
- Manual check: the open validator at icalendar.org (paste the feed) and real Apple, Google and Outlook clients
  (§6).

## 3. Recommended design

### 3.1 Concepts

- **Scope** = what goes out: `my_classes` (Derslerim), `department_classes` (Bölümümün dersleri, with a
  department id), `my_bookings` (Rezervasyonlarım, the existing `mine`), plus the existing `room` and `room_group`
  scopes.
- **Channel** = how it goes out: `link` (subscription URL), `file` (one-off `.ics`), or `push:google` /
  `push:microsoft` (later `push:caldav`).
- **Subscription** = scope × channel × user, approved once and revocable. A link token is bound to one
  subscription. A push connection carries a set of scopes.

### 3.2 Data model (one migration, next head `0039_calendar_classes`)

1. `calendar_feed_tokens` gains `scope_kind VARCHAR(24) NULL`, `scope_id INT NULL`, `consent_id INT NULL` and
   `fields JSON NULL`. NULL scope = a legacy multi-scope token, which keeps working for mine, room and room-group,
   with the department check enforced (CAL-03). RLS from `0035` already covers the table.
2. New `calendar_class_revisions` (not personal data):
   `uid VARCHAR(160) PK`, `term_id`, `fingerprint CHAR(64)`, `sequence INT`, `last_modified`, `ended_at NULL`
   (set when the occurrence disappears from the published plan; tombstone until `ended_at + grace`),
   `program_id NULL`, `instructor_ids JSON` (for scope lookup), `starts_at` (for the purge).
3. `calendar_connections` gains `scopes JSON` (default `["my_bookings"]` for existing rows),
   `owned_calendar BOOL` (true when SmartSched created the calendar), `account_verified VARCHAR(16)`
   (`sso_identity` | `domain` | `tenant` | `none`) and `last_reconciled_at`.
4. `calendar_event_links` gains `item_key VARCHAR(180)` (`booking:{id}` | `class:{uid}`), keeps `booking_id`
   nullable for old rows, and gets a unique key `(connection_id, item_key)`. The migration backfills
   `item_key = 'booking:' || booking_id`.
5. `calendar_sync_jobs.kind` gains `class` (`booking_id` NULL, new `item_key`).

### 3.3 Stable class identity

`uid = "class-" + sha1(term_id | meeting_request_id or (course_key|section) | occurrence_date | ordinal)[:20] + "@" + host`.
It does not contain the run id, the assignment id or the room. A re-publish or a room move keeps the UID and bumps
SEQUENCE with a new LOCATION. The ordinal tells two meetings of the same section on one day apart, ordered by the
request's meeting index, else by start period. The fingerprint covers date, start, end, room, codes, section,
status and title. It is per-UID and viewer-independent (no names), so the department feed and the personal feed
share revisions.

Who teaches what: `Instructor.user_id = me` → `section_instructors` → `meeting_requests` → active-run
`assignments` (the same path `teacher_preferences.linked_instructors` and `moderation` use). Board rows without a
meeting request fall back to `course_codes` ∩ the instructor's section courses. Several linked instructor records
are a union.

### 3.4 Endpoints

All token feeds stay under `/api/v1/calendar/feeds/{token}/….ics`, so the existing nginx rule (no access log, direct
to the backend) covers them with **no nginx change** (nginx is W3-SEC's).

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/calendar/export/options` | JWT | Per scope: available? reason? count of upcoming events, departments the user may export, channels configured, consent state |
| POST | `/calendar/subscriptions` | JWT | `{scope_kind, scope_id?, channel: link}` → creates a scope-bound token after the consent and permission checks. Returns `{id, urls{https, webcal, google, outlook}, preview}` once. Audited. |
| GET | `/calendar/subscriptions` | JWT | Lists the person's links and push scopes with `last_used_at` / `last_synced_at` |
| DELETE | `/calendar/subscriptions/{id}` | JWT | Revoke (token deleted; for push, removes the scope's events) |
| GET | `/calendar/feeds/{token}/classes.ics` | token | `my_classes` |
| GET | `/calendar/feeds/{token}/department-classes/{id}.ics` | token | `department_classes` (permission re-checked on every poll) |
| GET | `/calendar/export/classes.ics`, `/calendar/export/department/{id}.ics`, `/calendar/export/bookings.ics` | JWT | One-off file, same builder and UIDs, `Content-Disposition: attachment; filename="derslerim-2026-bahar.ics"` |
| PUT | `/calendar/connectors/{provider}/scopes` | JWT | `{scopes: [...]}` after the approval step; queues a full reconcile |
| existing | `/calendar/feeds/{token}/mine.ics`, `room/…`, `department/…`, `/calendar/connectors/*`, `/calendar/admin/*` | | Kept. `department/{id}.ics` now enforces the department rule. |

The scope-bound token serves only its own path (404 otherwise). Legacy tokens keep their old paths.

### 3.5 Update flow

1. **Feeds and files** are computed from the published plan on each request. `calendar_class_revisions` is updated
   when the engine runs: the fingerprint is compared, SEQUENCE is bumped, and disappeared UIDs get `ended_at` and are
   emitted as `STATUS:CANCELLED` for `feed_cancelled_grace_days`.
2. To keep revisions correct without waiting for a poll, a **domain-event subscriber** (`run.activate`, `run.delete`,
   `assignment.move`, `assignment.bulk_move`, `assignment.restore`, and term holiday or week edits) runs
   `refresh_class_revisions(term_id)` **after commit**, in the integrations worker, so a solve never waits on it.
   It then queues one `class` reconcile job per affected push connection (owners of affected instructor ids and
   department subscribers).
3. **Push reconcile** per connection and scope: the desired set (UID → view) is compared with `calendar_event_links`
   (`class:` keys). Missing → insert (Google: deterministic id; Graph: `transactionId`). Changed fingerprint →
   PATCH. Gone or tombstoned → DELETE. Uses the existing backoff, dedupe and REAUTH handling.
4. **Nightly reconcile** (03:30 Istanbul) lists SmartSched-tagged events in the owned calendar and repairs drift:
   events the user deleted or edited by hand, or a deleted calendar (recreate it once, then REAUTH-like
   "Takvim silinmiş" status).
5. **Revocation:** delete the link token → the next poll is a 404. Clients keep their last copy, so the UI tells
   the user to remove the subscription in the calendar app too. Disconnecting push or withdrawing the scope deletes
   the owned calendar (Google `calendars.delete`, Graph `DELETE /me/calendars/{id}`), then revokes the grant.
   Consent withdrawal or erasure does all of this (existing hook, extended to the new tables).

### 3.6 Verified accounts and push setup

- Admin setting `integrations.push_verified_only` (default **on**). Connecting is allowed when one of these holds:
  (a) the provider account's `sub` / `oid` equals a `UserIdentity` of the same person (W3-IDP); (b) Google `hd`
  equals the Google Workspace IdP's hosted domain; (c) Microsoft `tid` equals the Entra IdP's tenant (FLE-005); or
  (d) the account e-mail domain is in the admin's allowed list. Otherwise: 403 `account_not_verified`, and the panel
  says *"Bu hesap kurumunuzun doğrulanmış hesabı değil. {alan} uzantılı hesabınızla bağlanın."*
- Optional reuse of the IdP's OAuth client (`integrations.calendar_client_source = "identity" | "own"`). Saves the
  admin a second app registration. It needs a read-only accessor from W3-IDP (ask; see the ROADMAP tickets).
- New Google connections request `openid email calendar.app.created`, and SmartSched creates "SmartSched –
  Derslerim" (`timeZone: Europe/Istanbul`). Existing connections keep their grant. The panel offers "Daha az izinle
  yeniden bağlan" (reconnect with fewer permissions). Microsoft keeps `Calendars.ReadWrite` (the least available)
  and creates its own calendar too.

### 3.7 Academician UI: 3 taps (Turkish first)

Entry points: **Profil › Takvim** ("Takvimime ekle"), a "Takvime ekle" button on the academician's own classes and
requests view (`/moderation` "me" view; P19-T1 when it lands), and the existing calendar sheet on /my-bookings.
Phone: full-screen sheet, one step per screen, sticky primary action, 44 px targets. Desktop: 560 px right sheet.

**Tap 1: "Neyi eklemek istiyorsunuz?"**
- **Derslerim**: "Verdiğiniz dersler, yayımlanmış programdan · bu dönem {n} ders saati"
- **Bölümümün dersleri**: "{Bölüm adı} bölümünün tüm dersleri". Shown disabled with a reason when not allowed:
  "Bu bölümün derslerini dışa aktarma yetkiniz yok. Bölüm başkanınızdan isteyin."
- **Rezervasyonlarım**: "Derslik rezervasyonlarınız ve talepleriniz"
- Not linked to an instructor: "Hesabınız bir öğretim elemanı kaydına bağlı değil; planlama ofisine başvurun." with
  a "Planlama ofisine yaz" mailto/notice action.

**Tap 2: "Nasıl eklemek istiyorsunuz?"** (only the configured channels; never a fake button)
- **Google hesabımla** / **Microsoft 365 hesabımla** (badge "Önerilen"): "Değişiklikler birkaç dakika içinde
  takviminize yansır. Ayrı bir 'SmartSched – Derslerim' takvimi oluşturulur."
- **Takvim bağlantısı**: "Apple Takvim, Google veya Outlook bu bağlantıya abone olur. Güncellemeler uygulamaya
  göre birkaç dakika ile 12 saat arasında gelir."
- **.ics dosyası indir**: "Tek seferlik kopya. Sonraki değişiklikler kendiliğinden gelmez."

**Tap 3: "Takviminize şunlar gönderilecek"** (the approval)
- Bullets: "Ders kodu ve şube", "Derslik", "Gün ve saat", "Bölüm adı". Then: "Öğrenci bilgisi, not ve diğer öğretim
  elemanlarının adları gönderilmez."
- A sample event card rendered from the real first upcoming event: "PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50".
- If the `calendar_sync` consent is missing, a checkbox (unticked): "Ders programımın seçtiğim takvime
  gönderilmesini onaylıyorum. İstediğim zaman geri alabilirim." Link: "Aydınlatma metni".
- Primary button: **"Onayla ve ekle"**.

**Done:**
- Push: "Derslerim Google Takviminize ekleniyor… {n}/{m}", then "Eklendi · Son eşitleme: bugün 14:05".
- Link: three buttons, "Apple Takvim'e ekle" (webcal), "Google Takvim'e ekle", "Outlook'a ekle", plus "Bağlantıyı
  kopyala" → "Kopyalandı". A note: "Bağlantıyı açmayın, abone olun; açarsanız güncellenmeyen bir kopya oluşur."
  (the Imperial lesson)
- File: download starts, plus "Güncel kalmasını istiyorsanız bağlantı ya da hesap seçeneğini kullanın."

**Manage list** (Profil › Takvim): one row per subscription, "Derslerim · Google · Son eşitleme 14:05",
"Bölümümün dersleri · Bağlantı · Takviminiz en son 13:10'da çekti". Actions: "Şimdi eşitle" (push),
"Bağlantıyı yenile" (rotate), and "Kaldır" with the confirm text "Kaldırırsanız eklenen dersler takviminizden
silinir. Bağlantı aboneliğini takvim uygulamanızdan da silin." Focus returns to the next row, never `<body>`.

English keys mirror these under `calendarExport.*` (tr.json first, en.json second).

### 3.8 Admin settings (Ayarlar › Takvim; embedded unchanged in /admin/integrations)

- Scopes on or off: Derslerim (default on), Bölümümün dersleri (default on; who may: own department, taught
  departments, `calendar.department_feed`), Rezervasyonlarım (on).
- Fields: course title (on), department name (on), co-instructor names (**off**), SmartSched link in DESCRIPTION
  (on).
- Horizon: past days (existing `feed_past_days`), future = to term end (max 200 days), cancelled grace days
  (existing).
- Push: `push_verified_only` (on), allowed e-mail domains, client source (identity / own), Google scope mode
  (`app_created` default; `events` legacy).
- Status: counts of active links, active connections by provider and scope, failed jobs, the last nightly reconcile.

### 3.9 Reuse vs. build

| Reuse as is | Extend | Build |
|---|---|---|
| Token hashing, throttles, nginx rule, `render_calendar` + VTIMEZONE, consent gate, KVKK switch and sign-off, OAuth + PKCE, token encryption, outbox + backoff, erasure hook, `subscribe_links` | `class_events` (stable UIDs, scopes, revisions), `build_feed` (new scopes, department rule), `calendar_connectors` (item keys, class jobs, owned calendar, scopes, verified check), `workers/integrations.register` (assignment and run events), `calendar-connections.tsx` (scope chips), the admin panels | `calendar_class_revisions`, the subscriptions API, the export endpoints, the nightly reconcile, the 3-tap sheet `components/calendar-export/**`, the department permission, tests `test_cal_*` |

## 4. Risks

| Risk | Mitigation |
|---|---|
| Subscription lag is read as "SmartSched is broken" | Say it in Tap 2 and recommend push. Show "Takviminiz en son … çekti" from `last_used_at`. |
| UID migration duplicates every class once (old `class-{a}-{room}-{date}` → new UIDs) | Ship before the first academician subscriptions exist (P19-T4 is new). For room and department feeds, emit the old UIDs as CANCELLED for one grace period. |
| Re-publish storms: one publish touches 600+ classes × N connections | One `class` job per connection (diff-based, not per event). Google batch or Graph `$batch` (20 per request). Jitter. Per-connection rate. |
| Leaked link | Scope-bound tokens, per-link revoke, no logs, `no-referrer`. The department scope is re-checked on every poll (moving department revokes it in effect). |
| Over-sharing (names of co-instructors, students) | A fixed field allow-list, a test asserting no PII keys, admin opt-in for co-instructors. |
| A broad Google grant on old connections | `calendar.app.created` for new connections. Old ones are flagged "Daha az izinle yeniden bağlan". |
| A personal Gmail or another tenant receives university data | `push_verified_only` on by default (hd / tid / identity match). |
| User deletes the SmartSched calendar | The nightly reconcile recreates it once, then sets a status that asks the user. |
| Lanes overlap (W3-IDP `sso.py`, `identity/**`; W3-SEC RLS on `calendar_connections`; W3-HUB status reader; the mobile optimisers on `profile-view.tsx`) | The backend reads `UserIdentity` and `SsoProvider` rows read-only through a small accessor W3-IDP exports (ask). The migration only adds columns, coordinated with W3-SEC's planned RLS (R4). Keep `connectors_out()` and `settings_out()` backward-compatible for the hub. The frontend adds one mount line to `profile-view.tsx` after mobile optimiser A hands off. |
| Migration head race | Name it "next head". The orchestrator sets `down_revision` to whatever `alembic heads` shows at launch (currently `0038_email_templates`). |

## 5. What stays out of v1

CalDAV push (CAL-11), exam and invigilation duties as a scope ("Sınav görevlerim", natural next scope: same
engine), student feeds (Untis notes the server cost), two-way sync (SmartSched stays the source of truth), and the
`List-Unsubscribe` / "Takvime ekle" link in e-mails (CAL-12).

## 6. Persona test plan (academician; phone 390×844 touch, tr-TR, Europe/Istanbul, and desktop 1440)

Setup: own stack with `REC_TEACHER=1`, KVKK sign-off on, a published Bahar 2026 run. Persona *Dr. Ayşe* is linked to
the PSY 262 instructor record in Psikoloji. A second persona, *Dr. Mehmet*, is in another department with no
department permission. An admin has configured Google push with a mock provider (`httpx.MockTransport` stub or the
lane's OAuth stub).

| # | Step | Expected (phone and desktop) |
|---|---|---|
| T1 | Profil › Takvim › "Takvimime ekle" | Sheet opens with focus on the heading. Three scope cards. Derslerim shows "{n} ders saati". |
| T2 | Derslerim → Takvim bağlantısı → approve (consent box shown the first time) | Exactly 3 taps + the consent tick. Links shown: webcal, Google, Outlook, Kopyala. Audit row `calendar.subscription_create`. |
| T3 | `curl` the https link | 200 `text/calendar`. Only Ayşe's classes (PSY 262 Mondays 13:30–15:50 at A 308). `TZID=Europe/Istanbul` + VTIMEZONE. No instructor or student names. Parses with `python -I -c "import icalendar,sys;icalendar.Calendar.from_ical(open(sys.argv[1],'rb').read())" f.ics`. Clean in the icalendar.org validator. |
| T4 | `curl` again with `If-None-Match` | 304, no body |
| T5 | Use the same token on `department-classes/{other}.ics` and on `mine.ics` | 404 (the token is bound to its scope) |
| T6 | Planner moves PSY 262 week 5 to Tuesday P3 (calendar move) and re-publishes | Feed: same UID, SEQUENCE +1, new DTSTART and LOCATION. A pushed Google event is PATCHed within 2 minutes. "Son eşitleme" updates. |
| T7 | Planner removes one week's meeting | Feed: that UID shows `STATUS:CANCELLED` (grace). Push: the event is deleted. |
| T8 | Apple Calendar on an iPhone: tap "Apple Takvim'e ekle" | iOS "Subscribe" prompt. Calendar "SmartSched – Derslerim" appears. After T6, a pull refresh shows the move. |
| T9 | Google Calendar web: "Google Takvim'e ekle" | Calendar added by URL. Note the time until T6 shows (expected hours, not a failure). |
| T10 | Outlook on the web: "Outlook'a ekle" | Subscribed calendar named correctly. Times are Istanbul. |
| T11 | Push: Derslerim → Google hesabımla → approve | OAuth consent lists only "SmartSched-created calendars". A new calendar "SmartSched – Derslerim" holds the events. A personal gmail.com account → "Bu hesap kurumunuzun doğrulanmış hesabı değil…". |
| T12 | .ics dosyası indir | Downloads `derslerim-2026-bahar.ics` with the same UIDs as the link. Importing it into Apple and then importing it again after T6 updates in place, with no duplicates. |
| T13 | Dr. Mehmet opens "Bölümümün dersleri" for Psikoloji (forged id via `curl` too) | Card disabled with the reason; the API answers 403 `department_not_allowed`. Grant `calendar.department_feed` → allowed. |
| T14 | Kaldır on the link row | Confirm text shown. The next `curl` is a 404. Focus moves to the next row. |
| T15 | Kaldır on the Google row | The SmartSched calendar is deleted at Google (mock call), the grant revoked, the row gone |
| T16 | Withdraw the `calendar_sync` consent in Profil › Gizlilik | Every link is a 404 and every push is disconnected and its calendar deleted |
| T17 | Admin turns the KVKK switch off | All feeds 404. The sheet shows the quiet off state, with no fake buttons. |
| T18 | MOBILE M-01/M-02/M-03/M-05 on /profile and the sheet | No horizontal scroll, 44 px targets, 16 px inputs, primary action in the sticky footer |
| T19 | Draft run: a planner generates a new run but does not publish | Feeds, files and push are unchanged |

Automated: pytest `tests/test_cal_*` (stable UID across re-publish, SEQUENCE monotonic, tombstones, scope binding,
department rule, verified-account rule, Graph and Google mock reconcile, PII allow-list, ETag), vitest for the sheet
model, and the Playwright spec `e2e/cal-export.spec.ts` (T1, T2, T13, T14 at 1440 and 390 touch).

## Sources

RFC 5545 https://www.rfc-editor.org/rfc/rfc5545.html · RFC 7986 https://www.rfc-editor.org/rfc/rfc7986.html ·
Google Calendar scopes https://developers.google.com/calendar/api/auth · calendars.insert
https://developers.google.cn/workspace/calendar/api/v3/reference/calendars/insert?hl=en · extended properties
https://developers.google.com/calendar/api/guides/extended-properties · sync guide
https://developers.google.com/calendar/api/guides/sync · sensitive scopes
https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification ·
consent screen https://developers.google.com/workspace/marketplace/configure-oauth-consent-screen · Google secret
address https://support.google.com/calendar/answer/37648 · Graph create calendar
https://learn.microsoft.com/en-us/graph/api/user-post-calendars?view=graph-rest-1.0 · Graph event delta
https://learn.microsoft.com/en-us/graph/api/event-delta · Graph subscription lifetimes
https://learn.microsoft.com/en-us/graph/api/resources/subscription?view=graph-rest-1.0 · M365 dev blog (June 2026)
https://devblogs.microsoft.com/microsoft365dev/migrating-ews-notifications-to-microsoft-graph/ · Moodle
https://docs.moodle.org/403/en/Calendar_export · Canvas
https://community.canvaslms.com/t5/Canvas-Question-Forum/Missing-Calendar-Feed-Link/m-p/506141 · WebUntis
https://webhelp.untis.at/HTML/WebHelp/uk/untis/wu_ical_kalender_abonnement.htm · Celcat at Imperial
https://www.imperial.ac.uk/timetabling/view/icalendar/ and https://www.imperial.ac.uk/timetabling/view/autocalex/ ·
UCL https://www.ucl.ac.uk/srs/timetable-icalendar-subscription · TimeEdit at Twente
https://utwente.nl/en/educational-systems/about-the-applications/timeedit/faq-time-edit · Google refresh lag
https://politics.georgetown.edu/?p=4126, https://chaplain.yale.edu/subscription-religious-holidays-calendar,
https://usecarly.com/blog/google-calendar-ics-refresh-rate/ · Outlook and Apple refresh
https://nocal.app/help/ics-and-subscriptions/why-subscribed-calendars-dont-update-instantly,
https://autocaldata.com/guides/apple-calendar, https://www.thomastonschools.org/SubscribingtotheElectronicEventsCalendar
· TTL hint https://bugzilla.mozilla.org/show_bug.cgi?id=735147 · 1 MB note
https://ask.revolgy.com/en/support/solutions/articles/11000117258-use-an-email-address-to-subscribe-to-a-calendar ·
iCloud CalDAV https://cli.nylas.com/guides/icloud-caldav-settings,
https://www.onecal.io/blog/how-to-integrate-icloud-calendar-api-into-your-app · KVKK Art. 4 summary
https://akkaslaw.com/?p=26992
