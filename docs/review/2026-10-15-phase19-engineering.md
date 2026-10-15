# Phase 19 gap analysis and technical design (strict engineer, 2026-10-15)

Read-only analysis at HEAD `de2d10e`, plus the council branch `origin/claude/smartsched-universal`.

Path prefixes:
- `B/` = `smartsched/backend/`
- `F/` = `smartsched/frontend/src/`
- `CRBS/` = `crbs-core/application/`
- `UNI:` = a file on the council branch

User decisions it follows (docs/ROADMAP.md, Phase 19):
- AI extraction with review of every row, a KVKK notice and an admin off-switch.
- Memory reset per person, per term or all.
- Conflict policy: locks first, then priority, then most classes placed.
- Suggest only; accepting adds a soft preference.

Checks run:
- tests: `tests/test_safe_files.py tests/test_api_imports.py tests/ai tests/test_studio_classes.py`, 49 passed, 2 skipped
- an activate probe
- a solver probe
- a normaliser fuzz pass
- `parity_check.py --dry-run`: 192 rows, GAP 20

## 1. BLUF

1. **CRBS parity is close to done.** I spot-checked all 25 rows (P1–P3) of the 2026-10-08 UI-gap audit against the code, and every one is now PRESENT. That audit doc is out of date. The real gaps:
   - Four nav/⌘K links point to pages that don't exist (404).
   - The room-master import has no UI.
   - The live CRBS MySQL upgrade has never been run against a real install.
2. **None of the four new capabilities works end to end today.** Intake should extend the council branch rather than add a second parser stack. But the council branch can't be merged as is:
   - It bypasses the safe_files zip-bomb and memory caps (BLOCKER).
   - It brings back MSW mock mode (BLOCKER).
   - It has no admin AI switch and no KVKK notice.
3. **There is a proven hole in hard-rule integrity.** One untargeted *soft* `capacity` constraint seated 180 students in a 50-seat room. The run reported OPTIMAL with hard_score 100 and no warning. This has to be closed before any learned or AI suggestion is allowed to create constraints.
4. **Learning has nothing to learn from yet.**
   - No planning edit is audited: requests, moves, locks, forced moves, run activate/delete, constraints.
   - Rejected proposals are not stored.
   - `Instructor` has no `User` link.
   - Programs can't be created from scratch through the API: sections, courses, instructors and meeting requests only come from imports.
5. **Re-solve already exists.** A child run with `parent_run_id` gets the previous assignments, the carried locks and the stability objective (`B/app/services/solver_bridge.py:1050-1110`). LNS repair is in `B/app/solver/repair.py` and the chat flow uses it. What is missing:
   - moderation read models
   - priority
   - deterministic re-solves
   - a publish guard: today a FAILED run can be published (proven by probe)

## 2. CRBS parity truth table

Every action of every controller in `CRBS/controllers/**` was walked and re-checked against the code at HEAD `de2d10e`.

| CRBS feature (controller::action) | SmartSched evidence | Status |
|---|---|---|
| Bookings::index grid: day/room display, columns, prev/next, date picker, room picker grouped, session switcher (current/past), group tabs with counts, week banner, legend, print, `?highlight`, crosshair | `F/components/bookings/bookings-view.tsx`, `booking-grid.tsx`, `grid-model.ts` | PRESENT |
| Bookings::filter | `bookings-view.tsx` | PRESENT |
| Bookings::view: details, timetable-week row, Occurs, photo, series link | `booking-detail-sheet.tsx` | PRESENT |
| Bookings::card (room info), photo enlarge | `room-info-sheet.tsx` | PRESENT |
| Bookings::create: single and recurring, preview book/skip/replace, period select, department, booked-by | `book-sheet.tsx`, `recurring-preview-table.tsx`; `GET /bookings/users` (`B/app/api/v1/bookings.py:441`) | PRESENT |
| Multi-booking: include, per-row department/user/notes, copy-down, recurring | `multi-book-dialog.tsx:37,135-141,242` | PRESENT |
| Bookings::edit / cancel with scope; "not your own booking" warning | `booking-detail-sheet.tsx` | PRESENT |
| Bookings::cancel_multi from the grid, including other users' bookings | `bookings-view.tsx:138,503`, `booking-grid.tsx:83` | PRESENT |
| Bookings::change_session; maintenance gate | `bookings-view.tsx`; global banner (`F/components/shell/app-shell.tsx`) | PRESENT |
| Dashboard::index: stats, mine, rooms I own, "you can create n" | `my-bookings-view.tsx:84-86` | PRESENT |
| Dashboard::changelog | `F/components/admin/whats-new.tsx` | PRESENT |
| Export::index (CSV) | `my-bookings-view.tsx` + Admin card (`admin-overview.tsx`) | PRESENT |
| Profile::edit / new_password; Login; Logout | `user-menu.tsx:74`, ⌘K `command-palette.tsx:98`, `profile-view.tsx`, `/login/change-password` | PRESENT |
| Users: index / add / edit / delete / import / import_results | `F/components/admin/users-admin.tsx`; `nav-config.ts:48` | PRESENT |
| Roles: index / add / edit / delete, user list | `roles-admin.tsx` | PRESENT |
| Departments | `departments-admin.tsx` | PRESENT |
| setup/rooms/Rooms: add / edit / delete / save_pos / photo | `rooms-admin.tsx:342,408`; `B/app/api/v1/rooms.py:55,96` | PRESENT (D15: `PUT /rooms/{id}` is still Planner-only, `rooms.py:89`) |
| Groups, Fields, Acl (room / group) | `rooms-admin.tsx` | PRESENT |
| Access_checker index / user / room (deep links) | `access-checker.tsx` | PRESENT |
| Sessions: index / view / apply_week / add / edit / delete | `session-forms.tsx:47-48,154`, `sessions-admin.tsx` | PRESENT |
| Room_schedules | `sessions-admin.tsx` | PRESENT |
| Holidays add / edit / delete, duration | `holidays-admin.tsx:38,120` | PRESENT |
| Schedules (with description), Periods, Weeks | `schedules-admin.tsx:105`, `weeks-admin.tsx` | PRESENT |
| settings/General, Organisation, Authentication (LDAP + test), setup/Language | `org-settings.tsx`, `ldap-settings.tsx` | PRESENT |
| Installer, School, Welcome | `F/app/setup/page.tsx`, `setup-wizard.tsx` | PRESENT |
| Upgrade (v1→v2) / migrate a running CRBS | `B/app/importers/crbs_legacy.py:328,796-841`; UI kind `crbs` (`import-wizard.tsx:30`) | PARTIAL: checked only against CRBS's install SQL. P18-LEGACY and P18-DIFF are still declared GAP (`B/tests/parity/inventory.py:1322,1329`) |

**Claimed or linked, but not working in the UI:**
- **/find-room, /approvals, /admin/audit, /admin/approval-rules.**
  - They are linked from `F/components/admin/nav-items.ts:27-28,36`, `wave1-sections.ts:19-20` and `command-palette.tsx:94`, but there was no `page.tsx`, so each link is a 404.
  - Find-room has no permission gate, so Teachers can see it.
  - The backends exist, and the inventory marks X-08..X-11 as UI GAP (`inventory.py:1037-1076`).
  - The wave-1 frontend agent is building these pages now.
- **Room-master import has no UI.** `POST /imports/room-master` exists (`B/app/api/v1/imports.py:154`), but it is not in the wizard's `KINDS` (`import-wizard.tsx:26-31`).
- **The parity gate can pass without running anything.**
  - The `parity_check.py` UI column only checks that a test title exists, unless `--playwright-json` is passed.
  - `e2e/bookings.spec.ts:77` calls `test.skip` whenever the backend clock is outside Bahar 2026.
  - `reserve.spec.ts` is not in `UI_SPECS`.
- **Stale docs.**
  - `docs/review/2026-10-08-crbs-ui-gap-audit.md` still lists items as MISSING that have since been fixed.
  - B4 in `2026-10-08-crbs-parity-audit.md` is fixed in code but not verified against a live MySQL.

## 3. Design

### 3a. Multi-format intake (extend the council)

**What the council covers today** (`UNI:council/render.py:36-58`):

| | Formats |
|---|---|
| Handled | xlsx/xlsm, csv/tsv, txt/md, json, docx, pdf (text layer and layout tables), png/jpg/webp/gif (Claude vision) |
| Refused with a "save as" hint | `.xls`, `.ods`, `.doc`, `.pptx` |
| Not handled | XML, ICS, EML |

How it works now:
- An extension check runs before magic-byte detection (`detect_format` :168-186).
- Text decoding tries utf-8-sig, then cp1254, cp1252, latin-1 (:297-308).
- The fast path reuses `B/app/importers/normalize.py`, but the general path has its own `council/text.py`, so there are two normalisation stacks (D9).

**Security review of the council against gracious (merge gates):**
- **Upload cap:** `create_job` calls `await f.read()` with no limit, then checks the size. Gracious streams with a cap (`B/app/core/safe_files.py` save_upload). **BLOCKER (D2).**
- **Zip bombs:** `render._xlsx` calls `zf.read(...)` with no cap on member size or compression ratio (render.py:215-232). The branch forked before safe_files existed. **BLOCKER (D2).**
- **Isolation:** `asyncio.to_thread(render_file)` (orchestrator.py:222). `wait_for` cannot kill the thread, and there is no RLIMIT_AS. Gracious uses `run_isolated` (forkserver + RLIMIT). **BLOCKER (D2).**
- **Placeholder rule:** it ships `src/mocks/*`, the `msw` dependency and the `app/api/v1/[...path]/route.ts:5,18` mock mode. That is no-placeholder audit finding B1 again. **BLOCKER (D3).**
- **Auth:**
  - create, review, commit and rerun need Planner;
  - records and artifacts are readable by Viewer (raw rows with names and notes), while the gracious equivalent needs Planner (`imports.py:205`). **MINOR (D13).**
- **Escalation:** none. Commit creates terms and rooms, and gracious's `SessionsEditor` and `RoomsEditor` both accept `planning.edit` (`terms.py:17`, `imports.py:150`).
- **KVKK:** the only controls are the env var `COUNCIL_AI` and a per-job `ai` flag that the uploader sets. There is no admin switch, no notice and no redaction. **MAJOR (D7).**
- **Idempotency:** `source_key=CC:<job>:<file>:<record>`, so re-uploading the same file in a new job duplicates rows. **MINOR (D14).**
- **Audit:** inserting terms and rooms is audited via flush tracking; sections and requests are not (D5).

**Target design:** one pluggable registry in `B/app/council/formats.py`.
- Each entry has:
  - `sniff(head: bytes) -> confidence`
  - `render(data, limits) -> Rendered`
  - `route: "structured" | "ai"`
  - `limits`
- Detection uses **magic bytes first**. The extension is only a tie-break within one container family:
  - OOXML: `[Content_Types].xml` plus `xl/` or `word/`
  - ODF: first stored member `mimetype`
  - OLE2: `D0 CF 11 E0 A1 B1 1A E1`, with a `Workbook` stream for xls and `WordDocument` for doc
- Every render goes through `safe_files.precheck_upload` / `inspect_zip`, then `run_isolated`.

| Format | Magic / sniff | Parser | Dependency | Limits | Wave |
|---|---|---|---|---|---|
| xlsx/xlsm | PK + `xl/` | openpyxl via `safe_files.open_workbook` | pinned (MIT) | existing caps: rows 20k, cols 1024, cells 2M. Refuse `xl/vbaProject.bin` unless the file is .xlsm; never executed | 1 |
| xls | OLE2 + `Workbook` | `xlrd>=2.0.1` (xls only) | **add pin** (BSD) | 20 MB, 20k rows. OLE `.doc` → "save as .docx" | 1 |
| ods | PK + `mimetype=…spreadsheet` | own `content.xml` reader on defusedxml | **pin defusedxml** (PSF) | cap the `number-columns-repeated` / `-rows-repeated` expansion to the sheet caps | 1 |
| csv/tsv | text heuristics | stdlib csv | stdlib | Encoding: BOM (EF BB BF / FF FE / FE FF), then strict UTF-8, then cp1254 (İ/ş/ğ at 0xDD/0xFE/0xF0). Delimiter: a `sep=;` first line wins; otherwise `csv.Sniffer` limited to `; , \t \|` on 8 KiB, falling back to the delimiter with the steadiest column count. Reuse the room-master decoding | 1 |
| json | `{`/`[` after BOM | stdlib | stdlib | 10 MB, depth ≤ 32, ≤ 50k objects. Native schema `smartsched.intake.v1` (rooms, requests, timetable); a generic array of objects becomes a table | 1 |
| xml | `<?xml`/`<` | defusedxml.ElementTree; SpreadsheetML 2003 → workbook | defusedxml pin | no DTDs or entities, 10 MB, ≤ 200k elements | 1 |
| ics | `BEGIN:VCALENDAR` | `icalendar` | **move dev → main** (BSD) | RRULE expansion clipped to the term, ≤ 5000 instances. Drop ORGANIZER/ATTENDEE (PII). VEVENT → booking records (a schedule map) | 1 |
| pdf (text) | `%PDF-` | pypdf text + `pdfplumber` tables | **pin pdfplumber** (MIT) | ≤ 200 pages, run_isolated + RLIMIT | 2 |
| pdf (scanned) | no text layer | `pypdfium2` render → Claude vision `transcribe_document` | **pin pypdfium2** | ≤ 20 pages, 150 dpi, ≤ 1568 px | 2 |
| docx | PK + `word/` | python-docx after `inspect_zip` | pinned | refuse `.docm`; ignore external relationships and altChunk | 2 |
| txt/md | UTF-8/cp1254 | split into lines | stdlib | 2 MB | 2 |
| eml | RFC 5322 headers | `email` with `policy.default`; HTML stripped by `html.parser` | stdlib | attachments re-enter the registry (depth 1, ≤ 10). Keep only Subject and Date | 2 |
| images | PNG/JPEG/WebP/GIF magic | Pillow verify + re-encode, EXIF stripped, ≤ 1568 px, `MAX_IMAGE_PIXELS` cap | pinned | ≤ 10 per job | 2 |

Pipeline rules:
- **Wave-1 formats ship with no AI.** They use the council's deterministic structure analyst, extractor and critic.
- **AI-assisted rows must be reviewed.** Every record from an AI route gets `review_required=true`, and commit is refused until each one is accepted. `allow_pending` is ignored for AI rows.
- **Provenance per row.** Add `source_ref JSON` to `sections`, `meeting_requests`, `exam_requests` and `blocks`. It holds:
  - the job id and the file's sha256
  - the locator (sheet/row/col/cell, or page/line)
  - which extractor read it (fast/general/vision/llm), the model and the confidence
  - the reviewer and the time
- **Dry-run diff.** `POST /council/jobs/{id}/commit {dry_run:true}` runs the same writer inside a transaction that is rolled back. It returns create/update/unchanged/conflict counts per entity, and row diffs against `ImportedSnapshot` (`B/app/services/studio_classes.py:139-150`) using `on_conflict=keep|take`.
- **Requests + schedule maps → new schedule.**
  - Add `as_baseline_run`: create an `IMPORT` ScheduleRun with assignments matched to MeetingRequests by (course_key, section, day, start), generalising `B/app/importers/weekly_grid.py:512-594`.
  - That run becomes the `parent_run_id` of the new solve.
  - Deduplicate across jobs by natural key + file sha256.
- **A per-term write lock** for imports and commits (D8).

### 3b. Learning from previous changes and requests

**Signals that already exist:**
- requested vs definitive room per request, across terms (`MeetingRequest.requested_room_text/ids`, `definitive_room_ids`) — the strongest signal
- `ImportedSnapshot`: what was imported vs what the planner changed
- `Assignment.origin` (MANUAL/AI_EDIT/IMPORT), `is_locked`, and the run parent chain
- `Booking`/`BookingSeries`
- `ApprovalRequest.status`/`suggestion`
- `ConstraintRow` source/`created_by`/`enabled`
- `ChatApplyClaim`/`ChatMessage`

**Missing:**
- audit of planning edits (D5)
- rejected proposals (only accepted ones are stored, `B/app/ai/elicit.py:225-236`)
- the Instructor ↔ User link (`B/app/models/catalog.py:108-116`)

**Model: explainable, decayed frequency priors.**
- `learned_observations` (append-only, unique on `(source_table, source_id, kind)`). Columns: `id, ts, term_id, kind, subject_type, subject_key, attribute, value, sign ±1, weight, source_table, source_id, actor_id, reset_id`.
  - `subject_type` ∈ {instructor, course, section, program, user}
  - `attribute` ∈ {room, building, day, period, day_period, tag}
- Weights:

  | Event | Weight |
  |---|---|
  | definitive room | +3 |
  | planner move to X | +2 |
  | planner move away from X | −2 |
  | lock | +2 |
  | request text | +1 |
  | booking series | +1 |
  | approval approved | +1 |
  | approval rejected | −2 |
  | suggestion accepted | +2 |
  | suggestion rejected | −3 (and the suggestion is suppressed for the scope and term) |

- `learned_priors`:
  - score = Σ weight·sign·0.5^(Δterms/2)
  - confidence = Wilson lower bound
  - suggest only when support ≥ 2 across ≥ 2 terms (or ≥ 3 in one term) and confidence ≥ 0.6
- Every suggestion carries a written explanation of its evidence.
- `suggestion_feedback` records each decision.

**Where suggestions appear:**
- the moderation person and class panels
- the Studio Rules "From history" tray
- intake review
- the class inspector

**How they reach the solver (soft only):**
- Accepting a suggestion creates a `ConstraintRow` with `source="LEARNED"`, soft, weight 1..5, **targeted** params and a `source_ref`.
- The server-side allowlist is {room_preference, building_preference, same_room_across_weeks, day_window(soft)}.
- Structural kinds and untargeted rows are refused (this closes D1 for this path).
- Nothing is ever auto-applied.

**Resettable memory:**
- `learning_resets`: `id, scope_type ∈ {person, term, all}, scope_value, actor, ts, expires_at = ts+30d, undone_at`.
- A reset stamps `reset_id` on the observations and sets a watermark, so they aren't re-learned.
- Undo is allowed within 30 days. A daily purge hard-deletes observations whose reset has expired (KVKK erasure).
- `planning.admin` only, audited.
- The UI must say that a reset removes the memory, not the bookings or runs.

### 3c. From-scratch program creation

Today:
- `reference.py` is GET-only.
- `requests.py` is list + PUT only.
- Sections, courses, instructors and meeting requests are created only by the importers.

New endpoints. All need `planning.edit`, are audited, use `source_key="MAN:<uuid>"` and take a snapshot on create.
- `/faculties` (CRUD)
- extend `/departments` with `faculty_id`, `is_evening`, `canonical_name`
- `/courses`, with codes checked through `canon_course_code`/`course_key`
- `/instructors`, with `user_id`
- `/sections`
- `POST /requests/meetings`, `DELETE` (archive), `POST /requests/exams`
- `POST /sections/{id}/pattern`: a weekly-pattern expander that turns T/U/L hours, blocks, days and weeks into N MeetingRequests

Terms, weeks and periods already exist. Cohorts are derived (`normalize.cohort_key`).

Wizard (`F/app/(app)/programs/new/page.tsx`):
1. Term
2. Faculty and programs
3. Courses (bulk TSV paste)
4. Sections and instructors
5. Patterns and room needs
6. Pre-check
7. Generate

### 3d. Moderation tab

**Route** `F/app/(app)/moderation/page.tsx`:
- Permissions: viewing needs `planning.view`, editing needs `planning.edit`, reset and forced moves need `planning.admin`.
- Tabs: Classes | People | Requests | Preferences | Matchings.

**Read models** (`B/app/services/moderation.py`, `B/app/api/v1/moderation.py`):
- `GET /terms/{id}/moderation/people?q=` — per person: section and request counts, match rate, preferences and priors.
- `GET /moderation/people/{instructor_id}/history?terms=` — a timeline across terms. Each request shows:
  - the raw and parsed text
  - the definitive room
  - where it sits in the active run
  - planner edits and linked bookings
  - learned habits
- `GET /terms/{id}/moderation/matchings?run_id=` — each request against its assignment, with satisfied flags for room, building, tags, day and period. Reuses `calendar_views.class_detail` and `planner_check`.

**Visualisations:**
- a day × period heatmap of requested vs assigned (`heat-lenses.tsx`)
- room-frequency bars
- a match-rate sparkline per term

**Edits:**
- the existing `PUT /requests/meetings/{id}`, studio bulk edits and constraint CRUD
- new: `PUT /moderation/matchings/{mr_id}` with pin, prefer or unlock. It always writes to a *draft child run*, never to the published run.

**Re-solve:** `POST /terms/{id}/moderation/resolve {base_run_id, changed_request_ids, mode: repair|full}`.
- It creates a child run with stability and carried locks.
- `repair` uses `solver.repair.repair`.
- It runs deterministically (workers=1).
- It never auto-activates.
- It returns the moved events and the hard score. When no solution exists it returns INFEASIBLE with a diagnosis, rather than relaxing anything silently.

**Conflict policy:**
- Add `priority` (0..3) on Section, with a MeetingRequest override, and a per-term `conflict_policy`.
- The best-effort objective today maximises the number of placed classes with equal weights (`B/app/solver/cpsat.py:445-500`). It becomes lexicographic: priority first, then count.

## 4. Risks and verified defects

| ID | Sev | Where | Evidence | Fix |
|---|---|---|---|---|
| D1 | **BLOCKER** | `B/app/solver/constraints/__init__.py:142-166`; `B/app/ai/catalog.py`; `B/app/solver/build.py:28-49` | `validate_params("capacity", {}, "soft")` is accepted (also room_tags, fixed_time, room_pin, room_forbid). Probe: Room(cap 50) + Event(size 180) is INFEASIBLE; add `Constraint("capacity", {}, hard=False)` and it becomes OPTIMAL with hard_score=100 and no warning. Any Planner can create this via `POST /constraints` | Refuse untargeted soft structural rules except for `planning.admin` with a reason, and never from AI/UPLOAD/LEARNED. Record `stats.waived_rules` and show them in the run report |
| D2 | **BLOCKER** | `UNI:council/render.py:215-232`, `UNI:api/v1/council.py`, `UNI:council/orchestrator.py:222` | uncapped `zf.read`, unbounded `await f.read()`, thread parse with no RLIMIT | route through `safe_files.save_upload`/`precheck_upload`/`inspect_zip`/`run_isolated` |
| D3 | **BLOCKER** | `UNI:frontend/src/app/api/v1/[...path]/route.ts`, `UNI:…/src/mocks/*`, `msw` | the mock mode removed under no-placeholder B1 | drop it on merge |
| D4 | MAJOR | `B/app/api/v1/runs.py:242-257`, `:189-195` | `POST /runs/{id}/activate` on a FAILED run returns 200 with is_active=True; active runs drive the booking grid. No unique-active index, so activations race, and the active run can be deleted | allow activation only for finished runs with hard 100 or listed waivers; partial unique index `(term_id, kind) WHERE is_active`; 409 on deleting the active run |
| D5 | MAJOR | `B/app/services/audit.py:228-248`; nothing recorded in `runs.py`, `calendar.py`, `requests.py`, studio, `ai/chat.py` | planning entities and forced moves are not tracked | track them and record the actions |
| D6 | MAJOR | `nav-items.ts:27-28,36`, `wave1-sections.ts:19-20`, `command-palette.tsx:94` | four routes are 404; Find-room is shown to everyone | hide until built, then build |
| D7 | MAJOR | `B/app/api/v1/chat.py:167-190`; `settings_service.py:27-28` | uploaded text goes to Anthropic whenever a key exists | `ai.intake_enabled`/`ai.vision_enabled` (default off) + a sign-off record |
| D8 | MAJOR | no locks anywhere; `B/app/workers/queue.py:66` (concurrency 2) | two imports of the same term can run at once | per-term write lock |
| D9 | MINOR | `normalize.py:220-246` | `parse_day("PAZARTESI"/"CARSAMBA"/"PERSEMBE"/"CUMARTESI"/"Sali")` returns `[]` | fold diacritics first; one shared lexicon |
| D10 | MINOR | `normalize.course_key` | `course_key("İŞL101")="IŞL101"` ≠ `course_key("ISL101")="ISL101"` | ASCII-fold (see the ÇEV ≡ CEV decision) |
| D11 | MINOR | `normalize.py:836-849` | `parse_int_loose("12:30:00")` → 12; `"999999999999"` is accepted | refuse time-shaped values; bound enrolment |
| D12 | MINOR | `parse_time`/`parse_pct` | `"24:00"` → 00:00; `parse_pct("-5")` → 5 | map 24:00 to end of day; reject negatives |
| D13 | MINOR | `UNI:api/v1/council.py` | a Viewer can read the raw extracted rows | require Planner |
| D14 | MINOR | `UNI:council/commit.py` | the job id in `source_key` makes re-uploads duplicate rows | natural key + sha256 |
| D15 | MINOR | `B/app/api/v1/rooms.py:89` | a `setup.rooms` admin can't edit rooms | use `RoomsEditor` |
| D16 | MINOR | `imports.py:170`, `crbs_legacy.py:224` | the CRBS DSN form lets a Planner open TCP connections to any host (SSRF) | admin only + host allowlist |
| D17 | MINOR | `settings_service.py:30`, `cpsat.py:89-121` | time-limited runs with workers=8 are not reproducible | deterministic mode for moderation re-solves |
| D18 | MINOR | `scripts/parity_check.py`, `e2e/bookings.spec.ts:77` | UI rows PASS without the tests running; a date-gated skip | require `--playwright-json`; add `reserve.spec.ts` |
| D19 | MINOR | `B/app/api/v1/org.py:141-170` | first-run setup counts users, then inserts, so two concurrent calls can create two admins | lock or a sentinel row |

**Checked and fine:**
- reset codes are redacted from the outbox
- the SQL dump loader runs single statements only, so ATTACH is impossible
- LIKE filters use bound parameters
- the only unauthenticated routes are the intended ones
- uploaded text is wrapped as `<document>` data
- the AI's term context contains no instructor names

**Risks of the new features:**
- **Uploads:**
  - per-format caps (the table in §3a)
  - ODS/XML/PDF/image/EML bombs are capped
  - macro files are refused
  - a 30-day retention purge for stored files
- **KVKK:**
  - names, e-mails and phone numbers in DOCX/EML, and GPS in EXIF
  - sending to Anthropic is a cross-border transfer and needs the officer's sign-off
  - redact e-mails and phone numbers before sending, strip EXIF, keep only Subject and Date from e-mail headers
  - a person-level reset is the erasure path
- **Prompt injection:**
  - tools only, with strict schemas
  - every value must be traced to its source unit
  - the kind/hardness allowlist (D1)
  - human review
  - strip zero-width and bidi characters
  - a token budget per job
- **Data loss:**
  - keep planner edits (`on_conflict=keep`)
  - `Assignment.meeting_request_id` is SET NULL, so archive rather than delete
  - D4
- **Hard-rule integrity:**
  - learned and AI rules are soft and targeted only
  - repair either succeeds or returns INFEASIBLE with a diagnosis
  - after every solve, `evaluate()` checks that priority never broke a hard rule
- **Performance:**
  - incremental prior recomputation
  - indexes `section_instructors(instructor_id)` and `sections(term_id, course_id)`
  - the SSE stream polls every 0.5 s per client

## 5. Tickets

**Migrations** (as landed, corrected 2026-10-15):
- the head was `0016_course_code_keys` when this review was written
- gracious then gained `0017`–`0019` (0019_publish_guard_term_locks), so the council merge landed as `0020_council`
  on top of 0019, not as 0017
- new migrations build on the single current head (0021_outbox_queue, 0022_kvkk_signoff_unseed, 0023_learning,
  ...), one backend agent at a time; `alembic heads` must show one head

**Wave 0 — gates that must land before any Phase 19 feature:**

| ID | Title | Owner | Files | Acceptance |
|---|---|---|---|---|
| P19-00a | Refuse untargeted soft structural rules (admin + reason only) | backend | `api/v1/constraints.py`, `services/studio_rules.py` | `POST /constraints` with soft untargeted capacity: 422 for a Planner, 201 for an Admin with a reason |
| P19-00b | Catalogue hardness allowlist per source | ai | `ai/catalog.py`, `ai/elicit.py` | a proposal for soft untargeted `capacity` is rejected |
| P19-00c | Report waived structural rules | solver | `solver/build.py`, `cpsat.py`, `evaluate.py` | the D1 probe gives `stats.waived_rules == ["capacity"]` |
| P19-01 | Publish guard + single active run | backend | `api/v1/runs.py`, `models/runs.py`, alembic 0018 | activating a FAILED run → 409; concurrent activation leaves exactly one active; deleting the active run → 409 |
| P19-02 | Audit planning entities and actions | backend (after 01) | `services/audit.py`, `api/v1/{runs,calendar,requests}.py`, `ai/chat.py` | one audit row with before/after for each move, lock, forced bulk move, request PUT and activate |
| P19-03 | Per-term write lock | backend | `services/term_lock.py`, `api/v1/imports.py` | two parallel imports of one term: the second waits or gets 409 |
| P19-04 | Council hardening, backend | merge/backend | `council/{render,orchestrator}.py`, `api/v1/council.py` | bomb fixtures → 413/400; reading records needs Planner |
| P19-05 | Council hardening, frontend: no MSW | merge/frontend | `F/mocks/**`, `[...path]/route.ts`, package.json | no-placeholder test passes; onboarding e2e runs against the real backend |
| P19-06 | Hide or build the dead nav routes | frontend | `nav-items.ts`, `wave1-sections.ts`, `command-palette.tsx` | a crawler e2e finds no nav or ⌘K link returning 404 |

**Wave 1 — structured intake:**

| ID | Title | Owner | Depends | Acceptance |
|---|---|---|---|---|
| P19-I1 | Magic-byte registry, CSV/TSV sniffing, JSON `intake.v1` | backend | 04 | Bahar exported as cp1254 `;` CSV, UTF-8-BOM TSV and JSON yields ≥ 99 % of the xlsx meetings |
| P19-I2 | `.xls` (xlrd) + `.ods` (defusedxml, repeat caps) | backend | I1 | xls/ods records equal the xlsx ones; an ODS with repeat=16384 → 413 |
| P19-I3 | XML (SpreadsheetML) + ICS | backend | I1 | billion-laughs XML → 400; an ICS of week 3 equals the grid |
| P19-I4 | Commit dry-run diff | backend | 03 | dry-run counts equal the real commit; the DB is unchanged |
| P19-I5 | Schedule map → baseline IMPORT run; dedupe across jobs | backend | I4 | Güz board + list gives an IMPORT run; a child solve stays stable; re-uploading creates 0 duplicates |
| P19-I6 | `source_ref` provenance + inspector | backend + frontend | I1 | each committed row shows file/sheet/row in the inspector |
| P19-I7 | Room-master import in the wizard; dry-run diff panel | frontend | I4 | e2e: upload room_master.csv → see the diff → commit |
| P19-Q1 | Normaliser fixes D9–D12 | importer/backend | — | parametrised quirk tests |
| P19-Q2 | Parity gate fidelity | devops | — | CI fails when a UI spec is skipped |
| P19-Q3 | Pin xlrd, defusedxml, pdfplumber, pypdfium2, icalendar (main); upload retention purge | devops | — | a clean image build passes the import tests |

**Wave 2 — AI-assisted intake:**

| ID | Title | Owner | Depends | Acceptance |
|---|---|---|---|---|
| P19-A1 | AI intake/vision switches (default off), KVKK sign-off + notice | ai + frontend | 00b | switch off → a PDF memo is routed to "needs AI" with 0 network calls |
| P19-A2 | Review required on every AI row | ai | A1, I4 | commit with one unreviewed vision row → 409 |
| P19-A3 | PDF tables, scanned PDF → vision, EML attachments, EXIF strip, PII redaction | ai | A1 | `final_exams_sheet.pdf` ≥ 95 % of rows; an .eml's xlsx attachment is ingested; no e-mail or phone pattern in the outgoing payload |
| P19-A4 | Injection corpus test | ai | A2 | 20 adversarial docs → 0 structural or hard changes |

**Wave 3 — learning, programs from scratch, moderation:**

| ID | Title | Owner | Depends | Acceptance |
|---|---|---|---|---|
| P19-L1 | Learning tables; `Instructor.user_id`; `LEARNED` source | backend | 02 | migration up and down; models match |
| P19-L2 | Idempotent observation extractors | backend | L1 | re-running gives 0 new rows; MAT 112's prior names its definitive room |
| P19-L3 | Priors, explanations, suggestions API, accept/reject | backend | L2, 00a | accept → `ConstraintRow(LEARNED, soft, targeted)`; reject suppresses it |
| P19-L4 | Reset per person/term/all, 30-day undo, purge, audit | backend | L3 | reset hides the suggestions; undo restores them; a Planner gets 403 |
| P19-C1 | CRUD for faculties, programs, courses, instructors | backend | 02 | audited; a duplicate code → 409 |
| P19-C2 | Sections, meeting/exam requests, pattern expander | backend | C1 | "3 periods/week, Tue or Thu, weeks 1-14" expands correctly and a run places it |
| P19-S1 | Priority-weighted best-effort placement | solver | 00c | priority 2 wins; locks never move; workers=1 is bit-identical |
| P19-S2 | `repair()` returns a moved-diff and is deterministic | solver | S1 | the same edit gives an identical child twice |
| P19-M1 | Moderation read models + indexes | backend | L3 | history lists requested vs definitive vs assigned |
| P19-M2 | `priority` on Section/MeetingRequest; per-term `conflict_policy`; solver bridge | backend | S1, M1 | the policy switch changes the placement order |
| P19-M3 | Re-solve endpoint | backend | 01, S2, M2 | one edit moves only its neighbourhood; hard 100 or an explained infeasibility |
| P19-F1 | Moderation shell + People tab | frontend | M1, 06 | real-backend e2e |
| P19-F2 | Matchings/Requests/Preferences tabs, edit, re-solve, diff, publish | frontend | M3, F1 | e2e: pin → re-solve → diff → publish |
| P19-F3 | Suggestion tray + memory reset UI | frontend | L3, L4 | accept/reject round trip; the reset confirmation names its scope |
| P19-F4 | Program-from-scratch wizard | frontend | C2 | e2e: empty term → wizard → run DONE |

**Can run in parallel without touching the same files:**
- first: {00a, 00b, 00c, 03, Q1, Q2, Q3}
- then: {I1..I3}, {01→02}, {S1→S2}
- one after another, because all touch `council/commit.py`: I4 → I5 → A2
- the L1..L4 lane, alongside the C1..C2 lane
- the frontend tickets F1..F4, after the shell and studio agents finish

## Roadmap suggestions

1. An academician self-service request portal (needs the Instructor↔User link).
2. Instructor availability and load rules: max periods per day, lunch break, consecutive classes, travel time between buildings.
3. Term workflow states: collecting → drafting → review → published → frozen.
4. Published-version history: a diff since the last publish, change notifications, rollback.
5. Department-scoped planners (row-level edit rights).
6. Swap and change requests after publishing, using the approvals engine.
7. Exam invigilator assignment (`invigilators_requested` is stored but nothing uses it).
8. Utilisation and unmet-preference reports (PDF/XLSX).
9. What-if sandboxes compared side by side.
10. OBS enrolment sync and step-free accessibility tags as hard needs.
11. Personal ICS feeds for solver assignments (needs the Instructor↔User link).
