# Booking enhancements wave 1: API contract for the frontend

Status: backend implemented by backend-engineer (wave C part 1), 2026-10-08. Spec:
`docs/product/booking-enhancements.md` §4.1 (P10), §4.2 (T1), §4.6 (P7), §4.3 (P1). All routes are under
`/api/v1`, JSON, bearer token. Error bodies are `{"detail": {"code": "...", "message": "...", "message_tr": "..."}}`
for the new routes (`message_tr` is the Turkish text to show; `message` is English).

CRBS default: with no approval rule and no feature catalogue, booking behaves exactly as before. New permissions
(Administrator holds all of them; no other seeded role gets them):

| Permission | Group | Grants |
|---|---|---|
| `rooms.features` | rooms | manage the feature catalogue and room feature values (`setup.rooms` also works) |
| `audit.view` | audit | read the whole audit log with request ids and network hashes, CSV export |
| `approvals.decide` | approvals | decide requests as a designated approver; designate approvers |
| `book_single.request`, `book_recur.request` | booking scope (role or room ACL) | create requests an approver confirms |

---

## 1. T1 · Find me a room

### `POST /rooms/find`

Any signed-in user. Searches only the rooms the caller may view (`room.view` by role or room ACL; rooms without a
room group are hidden unless `show_ungrouped_rooms`, as in the booking grid). Rate limit 30/min per user (429 with
`Retry-After`, `detail.code = "rate_limited"`). Deterministic: the same query on the same data gives the same order.

Request (every field optional except `start` and one way of giving dates):

```json
{
  "term_id": 3,
  "date": "2026-02-18",                      // one date, or
  "dates": ["2026-02-18", "2026-02-25"],     // several, or
  "date_from": "2026-02-16", "date_to": "2026-05-29", "weekdays": [3],   // a range (ISO weekdays), or
  "weekday": 3, "weeks": [3, 4, 5],          // a weekday in term weeks (empty weeks = all lecture weeks)

  "start": "10:10",                          // "10:10", "10.10" (dotted), NBSP tolerated, or a period number 1..18
  "end": "12:30",                            // or "duration_periods": 3, or "duration_min": 120
  "window_end": "15:50",                     // optional: slide a duration-long block from start up to window_end

  "headcount": 90,                           // 0 = any size
  "purpose": "teaching",                     // "exam" ranks by exam capacity
  "features": [{"field": "Projeksiyon"}, {"field": 7, "op": "gte", "value": "40"},
               {"field": "Oturma düzeni", "value": "SINIF DÜZENİ"}],
  "tags": ["PC"],                            // solver tags or words: "bilgisayar", "tıp", "amfi"
  "buildings": ["A", "c blok"],              // "A Blok'ta", "C BLOĞU" also work
  "preferred_building": "A",                 // default: the building of most of the caller's bookings (90 days)
  "room_group_id": null,
  "text": "projeksiyon",                     // free text over code, name, location, notes, features (Turkish-insensitive)
  "include_busy": true,                      // false: only free / requestable / partial rooms
  "include_requestable": true,
  "flex": {"periods": 2, "other_days": false},
  "limit": 50
}
```

Times outside 08:30-22:50 answer 422 `time_outside_grid` with a Turkish `message_tr`. Feature names and option
texts are matched Turkish-case-insensitively (İ/ı, NBSP). Numbers accept `4,5`.

Response:

```json
{
  "query_echo": {...},
  "term_id": 3,
  "slots": [{"date": "2026-02-18", "start_period": 3, "end_period": 5}],
  "duration_periods": 3,
  "time": {"start": "10:10", "end": "12:30"},
  "closed_dates": [{"date": "2026-04-23", "reason": "holiday", "holiday": "Ulusal Egemenlik ..."}],
  "preferred_building": "A",
  "summary": {"rooms": 9, "free": 3, "dates": 1, "open_dates": 1,
              "text_tr": "3 boş oda · 1/1 tarih açık", "text_en": "3 free rooms · 1/1 dates open"},
  "results": [
    {
      "room_id": 11, "code": "A202", "name": "A 202", "building": "A",
      "capacity": 96, "exam_capacity": 0, "tags": ["TIP"], "features": ["Tıp Fakültesi dersliği"],
      "status": "free",            // free | requestable | partial | busy | too_small | feature_missing | capacity_unknown | closed
      "action": "book",            // book | request (P1: creates a PENDING request) | none (view only)
      "start_period": 3, "end_period": 5,
      "reason": {"tr": "Kapasite 96: 90 kişi için %6 boş koltuk", "en": "..."},
      "reasons": [{"tr": "...", "en": "..."}],
      "busy_with": null,           // busy/partial: course code, block label, or "Rezervasyon · <user> · <department>"
                                   // (user/department only with view_other_users)
      "fit": {"waste_pct": 6, "score": 0.2125},   // lower score = better fit
      "free_dates": 1, "open_dates": 1,
      "per_date": [{"date": "2026-02-18", "status": "free"}]    // only when the search has several dates
    }
  ],
  "alternatives": [               // only when fewer than 3 rooms are free
    {"kind": "time", "room_id": 2, "code": "A102", "name": "A 102", "dates": ["2026-02-18"],
     "start_period": 6, "end_period": 8, "reason": {"tr": "A 102 12:40-15:00 boş (+... ders saati)", "en": "..."}},
    {"kind": "day", ...}, {"kind": "near_miss", ...}
  ],
  "timing_ms": 41.3
}
```

Ranking: free and requestable first, then partial, busy, too small, missing features, unknown capacity. Within a
group: score = wasted seats `(capacity - headcount) / capacity` + 0.15 per solver tag the room has but the search
did not ask for (PC lab, TIP room) - 0.2 in the preferred building; ties by room order and Turkish name.

Occupancy = the published timetable (active runs of every term covering the date, e.g. Bahar and its Final) +
blocks (HAZIRLIK, UZEM ...) + bookings + PENDING requests that hold their slot. Holidays and dates outside the term
are listed in `closed_dates` and skipped.

To book a result: `POST /bookings` (one period) or the multi-booking flow with the room's periods that cover
`start_period..end_period`; pass `headcount` and `required_features` so later conflict resolution (P2) can rank
alternatives. A result with `action: "request"` creates a PENDING request (§4).

### `GET /rooms/find/recent`

The caller's last 10 search bodies (newest first), to re-run with one click.

---

## 2. P10 · Typed room features

Feature = a row of the CRBS custom-field table with a type: `BOOLEAN` (CRBS `CHECKBOX` is its alias),
`NUMBER`, `SELECT`, `MULTISELECT`, `TEXT`.

| Method & path | Guard | Purpose |
|---|---|---|
| `GET /rooms/facets` | signed in | filterable features with `counts` over the rooms the caller may view (non-public features only for feature admins) |
| `GET /room-admin/features` | `rooms.features` or `setup.rooms` | catalogue |
| `POST /room-admin/features` | same | create `{name, type, options[], filterable, public, icon, unit, solver_tag, category}` |
| `PUT /room-admin/features/{id}?confirm=` | same | update; changing or removing a `solver_tag` that rooms carry answers 409 `solver_tag_impact` with `impact` until `confirm=true` |
| `DELETE /room-admin/features/{id}?confirm=` | same | delete (200 `{deleted, impact}`); same 409 rule |
| `GET /room-admin/features/{id}/impact` | same | `{tag, rooms[], room_count, requests_needing, message, message_tr}` ("removes PC from 5 rooms; 37 requests need PC") |
| `POST /room-admin/features/adopt-tags` | same | migrate the free-text room tags (PC, TIP, LAB, AMPHI ...) into yes/no features (`Bilgisayar laboratuvarı`, `Tıp Fakültesi dersliği` ...); returns the created features |
| `POST /room-admin/features/template` | same | the optional starter catalogue (Projeksiyon, Akıllı tahta, PC sayısı, Mikrofon, Engelli erişimi, Kayıt sistemi); never automatic |
| `POST /room-admin/features/bulk-values?dry_run=true&skip_errors=false` | same | multipart `file`: CSV (UTF-8 or Windows-1254, `;` or `,`), first column room code (`kod`/`oda`/`derslik`/`code`), one column per feature name. Report per cell; apply refuses when a cell has errors unless `skip_errors` |
| `GET /room-admin/rooms/{room_id}/features` | same | `{room_id, code, tags, values: {field_id: value}, display: {name: human value}}` |
| `PUT /room-admin/rooms/{room_id}/features` | same | `{field id or name: value}`; all or nothing (422 `invalid_values` with `errors[]`) |

Feature object: `{id, name, type, kind, options: [{id, value}], filterable, public, icon, unit, solver_tag, category,
pos, counts?}`; `kind` is the normalised type (CHECKBOX → BOOLEAN). `category` ∈ av, seating, accessibility, lab,
other. Values: BOOLEAN accepts `true/false`, `evet/hayır`, `var/yok`, `x`; NUMBER accepts `40`, `4,5` (never
negative); SELECT/MULTISELECT accept option ids or option texts.

Solver contract unchanged: a yes/no feature with a `solver_tag` reads and writes `rooms.tags` (the solver's
vocabulary); other typed features with a solver tag add it when true (NUMBER > 0). Manual tags are never touched.
`GET /bookings/rooms` and `GET /bookings/rooms/{id}` (room info) now show typed values (`fields[].value` is the
human value, plus `unit` and `icon`); the CRBS `/room-admin/fields` routes keep working on the same table.

---

## 3. P7 · Audit log and undo

Every booking, series, approval, feature, approval-rule and approver change is recorded explicitly through
`app/services/events.publish_event` (the hook calendar sync and webhooks subscribe to); every user, role, room ACL,
room, room group, custom field, setting, schedule, period, session, timetable week, holiday, department,
translation and building change made through the API is recorded by the audit flush hook. Secrets (password
hashes, tokens, secret settings) are stored as `***`; the client address only as an HMAC of its /24 network.

| Method & path | Guard | Purpose |
|---|---|---|
| `GET /audit?entity_type=&entity_id=&actor_id=&action=&from=&to=&cursor=&limit=` | signed in | newest first; `{items: [event], next_cursor}`; `action` is a prefix (`booking.`); without `audit.view` only the caller's own actions and events of their own bookings, without `request_id`/`ip_hash` |
| `GET /audit/{id}` | same visibility | one event + `children` (bulk operations) |
| `POST /audit/{id}/undo` | same visibility + the permission the inverse needs | undo `booking.create`, `series.create`, `booking.move`, `booking.cancel` |
| `GET /audit/export.csv?from=&to=&entity_type=` | `audit.view` | CSV (formula-safe) |

Event: `{id, ts, actor_type, actor_id, actor_label, action, entity_type, entity_id, term_id, before, after, diff
({field: [old, new]}), reason, reversible, undo_of, parent_id, undone, request_id?, ip_hash?}`. Actions:
`booking.create|move|update|cancel|restore`, `series.create`, `approval.request|step|approve|reject|expire|withdraw`,
`approval_rule.create|update|delete`, `approver.update`, `room.features`, `room_feature.create|update|delete`, and
`<entity>.create|update|delete` for `user`, `role`, `room_acl`, `room`, `room_group`, `room_field`, `schedule`,
`period`, `session`, `timetable_week`, `holiday`, `department`, `translation`, `building`, `term`,
`user_constraints`, plus `settings.update`.

Undo rules: the event is reversible, not undone yet, younger than `bookings.audit_undo_hours` (org setting, default
24) **or** before the booking starts, and no later event touched the same bookings (409 `changed_since`,
`message_tr` "Bu kayıttan sonra 2 değişiklik yapıldı"). Undoing a cancel whose slot was taken meanwhile answers 409
`conflict` with `alternatives` (T1). Response `{undone, action, booking_ids}`. For the "Geri al" toast: every
booking mutation response is followed by an audit event; fetch it with
`GET /audit?entity_type=booking&entity_id=<id>&limit=1` (or by action), then `POST /audit/{id}/undo`.
Audit rows cannot be changed or deleted (no route; the database refuses UPDATE/DELETE).

---

## 4. P1 · Approval workflows

Defaults: no rule → CRBS behaviour. A rule on a room, room group or room type (tag, e.g. `TIP`) makes bookings
there `PENDING` requests for everyone except (when the rule allows self-approval) its own approvers.

### Booking changes

* `POST /bookings` answers **202** with the booking and `status: "PENDING"` when approval is needed (201 otherwise).
  `POST /bookings/recurring` answers 202 with `{series_id, status: "PENDING", created[], skipped[]}`;
  `POST /bookings/recurring/preview` adds `requires_approval`.
* Booking objects gain `headcount`, `held_until` (a tentative hold) and the statuses `PENDING`, `REJECTED`,
  `EXPIRED`, `WITHDRAWN`. A PENDING request holds its slot only when the rule has `hold_minutes > 0` (until
  `held_until`); the grid then shows the slot as booked with `booking.status = "PENDING"`.
* 403 `no_approver` when the caller has only `book_*.request` and nobody approves that room; 409 `lead_time` with
  `earliest` when the rule needs N working days' notice.

### Approvals

| Method & path | Guard | Purpose |
|---|---|---|
| `GET /approvals/rooms/{room_id}/check?term_id=` | signed in, room visible | `{action: book|request|none, rule, approvers[], summary_tr, summary_en}` for the booking sheet ("Talep et") |
| `GET /approvals/inbox?status=open|decided|all` | `approvals.decide` (else `[]`) | requests whose current step the caller approves; each with `decisions[]`, `approvers[]`, `competing[]` (other open request ids for the same slot) |
| `GET /approvals/mine` | signed in | the caller's requests with their timeline |
| `GET /approvals/{id}` | requester or an approver | one request |
| `POST /approvals/{id}/decide` | `approvals.decide` + approver of the current step | `{decision: "approve"|"reject", note?, alternative?: {room_id?, date?, period_id?, start_period?, end_period?}, instances?: [date]}` |
| `POST /approvals/{id}/withdraw` | requester | withdraw an open request |
| `POST /approvals/sweep` | `approvals.decide` or `setup.rooms_acl` | expire overdue requests, release holds that ran out (also done by every approvals call) |
| `GET /approvals/approvers` | `setup.users`, `approvals.decide` or `setup.rooms_acl` | designated approvers with `scopes` |
| `PUT /approvals/approvers/{user_id}` | `setup.users`, caller holds `approvals.decide` and may manage the user | `{scopes: [{type: all|room|room_group|tag, id?, tag?}]}`; `[]` removes the designation; the target must hold `approvals.decide` (an administrator) |
| `GET/POST /approval-rules`, `PUT/DELETE /approval-rules/{id}` | `setup.rooms_acl` | rules (below) |
| `GET /me/notifications?unread=true&limit=` | signed in | in-app notifications (bell) |
| `POST /me/notifications/read` | signed in | `{ids: [...]}` or `{all: true}` → `{read: n}` |

Request object: `{id, status, step, steps, rule (snapshot), room_id, room_name, term_id, series_id, booking_id,
requested_by, requester_name, requested_at, expires_at, decided_at, note, suggestion, bookings[], decisions[],
approvers[], competing[]}`.

Decide semantics: approve re-checks the date (holiday added since), the timetable, blocks and other bookings in one
transaction; a lost slot answers 409 `conflict` with `alternatives`. `alternative` with approve = "approve in
another room/time"; with reject = the suggestion the requester sees (without one, the service suggests up to three
free rooms itself). Approving a request rejects competing open requests for the same slot with a reason. A
requester cannot approve their own request unless the rule allows it or nobody else approves that step
(403 `self_approval`). For recurring requests `instances` approves a subset; the other dates are declined.

Rule body: `{name?, entity_type: room|room_group|tag, entity_id?, tag?, term_id?, steps: [{approvers: {type:
"designated"} | {type: "users", ids: [...]}, min_approvals: 1}], hold_minutes: 0, lead_time_workdays: 0,
expires_before_start_minutes: 0, allow_self_approve: false, active: true}`. Most specific rule wins (room > room
group > tag; a rule of the term before a rule of every term). Open requests keep the rule snapshot they were made
under. Named step approvers must be designated approvers holding `approvals.decide`.

Designation at account creation: `POST /users` and `PUT /users/{id}` accept `approves_for: [{type, id?, tag?}]`
(same rules as `PUT /approvals/approvers/{id}`); user objects return `approves_for`.

Notifications: requester and approvers get an e-mail outbox row (`notification_outbox`, kinds
`approval_requested`, `approval_approved`, `approval_rejected`, `approval_expired`) and an in-app notification
with a `link` (`/approvals?request=<id>` for approvers, `/bookings/mine?request=<id>` for the requester). Texts are
Turkish or English by the recipient's language.
