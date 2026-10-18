# Key flows (sequence diagrams)

Five flows a new contributor or a reviewer meets first. Backend paths are under `/api/v1` and every browser call
goes through the Next.js BFF handler (left out below unless it does something). Index: [README.md](README.md).

## 1. Workbook import: preview → term check → Uygula

```mermaid
sequenceDiagram
  autonumber
  actor P as Planner
  participant W as import-wizard.tsx
  participant R as api/v1/imports.py
  participant J as services/import_jobs.py
  participant Q as workers/queue.py
  participant T as services/import_term_check.py
  participant L as services/term_lock.py
  participant I as importers/planning_list.py
  participant DB as PostgreSQL

  P->>W: drop workbook, pick term
  W->>R: POST /imports/planning-list (dry_run=true)
  R->>DB: import_jobs row (QUEUED, summary.dry_run)
  R->>Q: enqueue import:{id}
  R-->>W: 202 job
  Q->>J: run_preview(importer)
  J->>I: parse + write in a transaction
  I-->>J: report + diff
  J->>DB: ROLLBACK (nothing kept)
  Q->>T: term_check(file name, sheet titles, target term)
  T-->>Q: term_check (mismatch?, suggested_term_id)
  Q->>DB: job DONE, summary = report + diff + term_check
  W->>R: GET /imports/{job_id} (poll)
  R-->>W: preview, term warning
  P->>W: Uygula
  W->>R: POST /imports/{job_id}/apply
  R->>DB: new job (summary.preview_of), preview.applied_job_id
  R->>Q: enqueue import:{new id}
  Q->>L: term_write_lock(term)
  Q->>I: import for real
  I->>DB: rooms, sections, requests, blocks
  Q->>L: release lock
  Q->>DB: job DONE + audit row (who imported what)
```

Every workbook upload is a preview first: the importer runs inside a transaction that is rolled back, so the person
sees the diff and the term check before anything is written. "Uygula" imports the stored file once (a second apply
answers 409 `preview_already_applied`), under the term's write lock so two imports of one term never interleave. A
file of the wrong kind fails with `WrongFileError` and the wizard offers "… olarak içe aktar".

Where in the code: [`api/v1/imports.py`](../../smartsched/backend/app/api/v1/imports.py) (`_start_job`,
`apply_preview`), [`services/import_jobs.py`](../../smartsched/backend/app/services/import_jobs.py),
[`services/import_term_check.py`](../../smartsched/backend/app/services/import_term_check.py),
[`services/term_lock.py`](../../smartsched/backend/app/services/term_lock.py),
[`importers/detect.py`](../../smartsched/backend/app/importers/detect.py),
[`import-wizard.tsx`](../../smartsched/frontend/src/components/import/import-wizard.tsx).

## 2. Solve and publish a run

```mermaid
sequenceDiagram
  autonumber
  actor P as Planner
  participant UI as runs / timetable pages
  participant R as api/v1/runs.py
  participant Q as workers/queue.py
  participant B as services/solver_bridge.py
  participant S as solver/cpsat.py
  participant G as services/publish_guard.py
  participant C as services/planner_check.py
  participant E as services/events.py
  participant DB as PostgreSQL

  P->>UI: Oluştur (term, kind, horizon)
  UI->>R: POST /runs
  R->>DB: schedule_runs (QUEUED)
  R->>Q: enqueue run:{id}
  R-->>UI: 202 run_id
  UI->>R: GET /runs/{run_id}/events (SSE progress)
  Q->>B: run_schedule(run_id)
  B->>DB: load rows, build SolverInput (session closed)
  B->>S: solve(SolverInput) in a worker thread
  S-->>B: SolverResult (status, assignments, diagnoses)
  B->>DB: persist assignments, scores, status
  P->>UI: Yayımla
  UI->>R: POST /runs/{run_id}/activate
  R->>R: publish_blockers: status publishable, hard 100
  R->>C: check_run (only when edited by hand)
  R->>G: integrity, scope_reduction, forced breaks
  alt blocked
    R-->>UI: 409 issues / scope_reduction / forced_breaks
  else publishable
    R->>DB: previous run is_active=false, this run is_active=true
    R->>E: publish_event("run.activate")
    E->>DB: audit_events row
    E->>E: subscriber booking_conflicts.on_run_activated
    R->>DB: COMMIT
    R-->>UI: 200 (optional digest to academicians)
  end
```

A solve is a background job: the request returns 202 at once and the page follows the SSE stream. The solver never
sees the database: the bridge builds a frozen `SolverInput`, CP-SAT runs off the event loop, and the result is
written in a fresh session. Publishing is a guarded switch of `is_active` (one active run per term and kind, enforced
by a partial unique index); bookings that the new timetable now overlaps are detected in the same transaction.

Where in the code: [`api/v1/runs.py`](../../smartsched/backend/app/api/v1/runs.py) (`create_run`, `activate_run`,
`publish_blockers`), [`services/solver_bridge.py`](../../smartsched/backend/app/services/solver_bridge.py)
(`run_schedule`), [`workers/run_jobs.py`](../../smartsched/backend/app/workers/run_jobs.py),
[`solver/cpsat.py`](../../smartsched/backend/app/solver/cpsat.py),
[`services/publish_guard.py`](../../smartsched/backend/app/services/publish_guard.py),
[`services/planner_check.py`](../../smartsched/backend/app/services/planner_check.py),
[`services/booking_conflicts.py`](../../smartsched/backend/app/services/booking_conflicts.py).

## 3. A booking, with approval

```mermaid
sequenceDiagram
  autonumber
  actor U as Staff member
  actor A as Approver
  participant R as api/v1/bookings.py
  participant S as services/bookings.py
  participant AP as services/approvals.py
  participant E as services/events.py
  participant N as notify_dispatch + workers/integrations.py
  participant DB as PostgreSQL

  U->>R: POST /bookings (room, date, period)
  R->>S: create_single(access, body)
  S->>AP: need_for(room) (rule or approval_mode=all)
  S->>S: term open, policies, window, limits
  S->>DB: find_conflict (booking_slots, published timetable)
  alt no approval needed
    S->>DB: bookings BOOKED + booking_slots (unique room/date/period)
    S->>E: publish_event("booking.create")
    E->>DB: audit_events
    E->>N: calendar push / webhook outbox rows
    R-->>U: 201 booking
  else approval needed
    S->>DB: bookings PENDING (optional tentative hold)
    S->>AP: open_request
    AP->>E: publish_event("approval.request")
    AP->>N: notify approvers (in-app + e-mail)
    R-->>U: 202 status PENDING
    A->>R: POST /approvals/{request_id}/decide
    R->>AP: decide(approve or reject + reason)
    AP->>DB: re-check slot, booking BOOKED or rejected
    AP->>E: publish_event("approval.approve" or "approval.reject")
    AP->>N: notify requester
  end
```

All booking-side changes go through `publish_event` inside the change's own transaction: it writes the audit row and
calls subscribers (calendar push, webhooks), which only enqueue outbox rows; a failing subscriber is logged and never
undoes the booking. The `booking_slots` unique key is the database guarantee against double booking. With no
approval rule the flow is the CRBS one; an approval sweep every 60 s expires overdue requests and releases holds.

Where in the code: [`api/v1/bookings.py`](../../smartsched/backend/app/api/v1/bookings.py) (`create_booking`),
[`services/bookings.py`](../../smartsched/backend/app/services/bookings.py) (`create_single`),
[`services/approvals.py`](../../smartsched/backend/app/services/approvals.py) (`need_for`, `open_request`, `decide`),
[`api/v1/approvals.py`](../../smartsched/backend/app/api/v1/approvals.py),
[`services/events.py`](../../smartsched/backend/app/services/events.py),
[`services/notify_dispatch.py`](../../smartsched/backend/app/services/notify_dispatch.py),
[`workers/integrations.py`](../../smartsched/backend/app/workers/integrations.py),
[`workers/approvals_sweeper.py`](../../smartsched/backend/app/workers/approvals_sweeper.py).

## 4. Helper turn with a confirm card (and the HB-23 file hand-over)

```mermaid
sequenceDiagram
  autonumber
  actor U as Person
  participant H as helper sheet (components/helper)
  participant T as api/v1/helper_turn.py
  participant RT as ai/helper_turn.py
  participant GW as AIClient + ai/pipeline.py
  participant TU as ai/helper/tooluse.py
  participant C as ai/helper/confirm.py
  participant SV as page service (e.g. services/bookings.py)

  U->>H: "Perşembe 10:00 A101 ayır"
  H->>T: POST /helper/turn (text, page context)
  T->>RT: run_turn (own session, streamed events)
  RT->>RT: guard.check (0 tokens), helper_status (index or AI mode)
  alt index mode (no key, no consent, not routed)
    RT-->>H: nav cards from the index, zero model calls
  else AI mode
    RT->>GW: complete (≤ 10 strict tools, ≤ max_tool_rounds)
    GW-->>RT: tool call
    RT->>TU: apply_message (offered names, strict args, person's Access)
    TU-->>RT: write → confirm card with a signed token (nothing written)
    RT-->>H: confirm card (turn ends)
  end
  U->>H: presses the card's button
  H->>T: POST /helper/actions/confirm (token)
  T->>C: confirm: verify HMAC, user, expiry, claim nonce once
  C->>SV: re-run preview, execute with Access
  SV-->>C: done (audit helper.action.*)
  C-->>H: result card + undo_token
```

```mermaid
sequenceDiagram
  autonumber
  actor U as Admin or academician
  participant H as helper sheet (HB-23c, in progress)
  participant F as /helper/files/* (HB-23b, planned)
  participant PG as target page (e.g. import wizard)
  participant R as api/v1/imports.py

  U->>H: drop or attach a file
  H->>F: classify (multipart file) — planned
  F->>F: existing detectors, no model call, stage bytes encrypted 10 min — planned
  F-->>H: file card (kind, term, warnings, one button) + upload_token — planned
  U->>H: presses the card's button
  H->>F: handoff (audit helper.file.handoff) — planned
  H->>PG: open the page with the token in the store, never in the URL
  U->>PG: page's own "Önizle" then "Uygula"
  PG->>R: upload_token instead of the file — planned
  R->>R: same preview, term check and lock as flow 1
```

A write never runs from model output or from typed text. The model can only call the tools it was offered; a write
stops at a confirm card whose token is HMAC-signed, bound to the person, valid 10 minutes and usable once. The confirm
re-runs the preview and answers 409 `changed` when the world moved. The file router (second diagram, design
[helper-file-router.md](../design/v3/helper-file-router.md)) follows the same rule: the helper never imports, it hands
the staged file to the page whose own preview and "Uygula" write. Steps marked "planned" are not merged yet.

Where in the code: [`api/v1/helper_turn.py`](../../smartsched/backend/app/api/v1/helper_turn.py),
[`api/v1/helper.py`](../../smartsched/backend/app/api/v1/helper.py),
[`ai/helper_turn.py`](../../smartsched/backend/app/ai/helper_turn.py) (`run_turn`),
[`ai/helper/guard.py`](../../smartsched/backend/app/ai/helper/guard.py),
[`ai/helper/tooluse.py`](../../smartsched/backend/app/ai/helper/tooluse.py),
[`ai/helper/confirm.py`](../../smartsched/backend/app/ai/helper/confirm.py),
[`ai/pipeline.py`](../../smartsched/backend/app/ai/pipeline.py),
[`components/helper/`](../../smartsched/frontend/src/components/helper/).

## 5. Sign-in: password + second step, or SSO

```mermaid
sequenceDiagram
  autonumber
  actor U as Person
  participant LP as /login page
  participant MH as BFF auth/mfa/[step] handler
  participant A as api/v1/auth.py
  participant M as services/mfa.py
  participant MF as api/v1/mfa.py
  participant S as api/v1/sso.py + services/sso.py
  participant IdP as Identity provider

  alt password (local or LDAP)
    U->>LP: username + password
    LP->>MH: login step
    MH->>A: POST /auth/login (+ X-Trusted-Device)
    A->>A: LDAP bind or local hash, password_login_allowed
    A->>M: after_password(user, method, trusted device)
    alt second step needed
      M-->>A: challenge_token, methods
      A-->>MH: mfa_required (no session yet)
      MH->>MH: challenge in httpOnly ss_mfa cookie
      U->>LP: 6-digit code, passkey or recovery code
      LP->>MH: verify step
      MH->>MF: POST /auth/mfa/verify
      MF-->>MH: session JWT
    else trusted device or policy off
      A-->>MH: session JWT
    end
    MH->>MH: JWT into httpOnly auth cookie (page never sees it)
  else SSO (Entra, Google, OIDC, SAML)
    U->>LP: "Microsoft ile giriş"
    LP->>S: GET /auth/sso/{slug}/start
    S-->>U: 302 to IdP (PKCE, state, nonce)
    U->>IdP: sign in (IdP's own MFA)
    IdP-->>S: GET /auth/sso/{slug}/callback
    S->>S: verify id_token (JWKS, iss, tid), identity by oid+tid, never e-mail
    S-->>LP: 302 /login/sso?ticket=… (2 minutes, one use)
    LP->>S: POST /auth/sso/exchange (ticket)
    S-->>LP: session JWT (stored in the cookie by the BFF)
  end
```

The browser never holds a token: the BFF handlers keep the second-step challenge, the trusted-device token and the
session JWT in httpOnly cookies. Every JWT carries `token_version`; sign-out, a password or role change and disabling
the account raise it, so all earlier sessions die on every device. SSO accounts skip SmartSched's own second step
(the provider does it); errors on `/login?error=` never say whether an account exists.

Where in the code: [`api/v1/auth.py`](../../smartsched/backend/app/api/v1/auth.py),
[`services/mfa.py`](../../smartsched/backend/app/services/mfa.py) (`after_password`),
[`api/v1/mfa.py`](../../smartsched/backend/app/api/v1/mfa.py), [`api/v1/sso.py`](../../smartsched/backend/app/api/v1/sso.py),
[`services/sso.py`](../../smartsched/backend/app/services/sso.py),
[`services/identity/`](../../smartsched/backend/app/services/identity/),
[`core/security.py`](../../smartsched/backend/app/core/security.py),
[BFF sign-in steps](../../smartsched/frontend/src/app/api/auth/mfa/[step]/route.ts),
[`sso-exchange.tsx`](../../smartsched/frontend/src/components/auth/sso-exchange.tsx).
