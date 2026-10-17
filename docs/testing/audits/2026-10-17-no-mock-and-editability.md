# SmartSched: audit of fake features and admin-editable institution data
Branch `claude/focused-wright-ktt0ss` @ f89efda7, audited 2026-10-17. Read-only: no repo file was changed and no stack was started.
Repro scripts and scratch DBs: `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/audit-real/repro/` (`rename.py`, `tags.py`, `t/test_audit_repro.py`).

## BLUF
**5 BLOCKER · 14 MAJOR · 10 MINOR.**

- **Redeploys are safe.** I read `deploy/seed/seed.py` and ran its 26 tests (all pass). Every seed step is recorded in the settings row `deploy.seed_profile`. A step that has finished never runs again, and a database that already has terms but no marker is left alone. So a pod redeploy (`deploy.sh --update`, volumes kept) does **not** overwrite admin edits.
- **Re-imports are not safe.** When an admin uploads a corrected workbook at /import, several of their edits are silently undone (MAJOR 5–9, 4 of them reproduced).
- **Three visible controls do nothing:**
  - the "Öğrenci" (enrolment) edit on /classes (reproduced: HTTP 200, the value does not change);
  - the admin's default solver seed and weights;
  - a permanently disabled "Davet e-postası gönder" switch.
- **Phones:** the month arrows in the phone timetable do nothing.
- **Owner request (2026-10-17): mostly not met.**
  - Instructors, courses, imported sections and faculties have no edit or delete screen. The backend routes exist (20 of them) and no screen calls them.
  - The seeded workbooks leave no trace in /import: no history, no report, no download.
  - Learned habits are read-only per person. The only fix is a reset of the whole person, term or everything.
  - Learning is frozen after the seed: extraction runs only in the seed CLI and in `POST /learning/refresh`, which has no button and no schedule.

---

## Part A: fake, stub or unfinished in production paths

| # | Sev | file:line | What the user sees | Why it is fake or unfinished | Fix (owning area) |
|---|---|---|---|---|---|
| A1 | **BLOCKER** | `frontend/src/components/classes/classes-page.tsx:210-230`; `backend/app/schemas/requests.py:44-62,111-125` | /classes: edit the "Öğrenci" cell → toast "kaydedildi · sonraki çalıştırmada"; after a reload the old number is back | The UI sends `{enrolment}` to `PUT /requests/meetings|exams/{id}`. Neither schema has an `enrolment` field, and pydantic drops unknown fields. **Repro** (`t/test_audit_repro.py`): `PUT {"enrolment":77}` → 200, enrolment stays 10 | Write `section.enrolment` (as `PUT /sections/{id}` / `studio/meetings/bulk` already do), or add `extra="forbid"` so the call fails loudly (requests API + classes UI) |
| A2 | **BLOCKER** | `backend/app/services/studio.py:816-821`, `backend/app/api/v1/runs.py:111-115`; `frontend/src/components/studio/use-generate.tsx:40-44`, `generate-step.tsx:78,107` | Ayarlar › Çözücü: the admin saves a default seed and default weights. The studio's Generate step shows them as the values in use | The backend falls back only to `solver_default_time_limit` and `solver_workers`. `solver_weights` is written (`settings.py:198`) and never read; `solver_default_seed` (stored via `extra`) is never read. The studio sends `seed`/`weights` only after the planner edits them, so runs use the built-in defaults while the UI shows the admin's. Planners get 403 on `/settings`, so for them the defaults are not even shown | Merge both settings into the run params on the server, in `studio.generate` and `runs._params` (solver/studio) |
| A3 | **BLOCKER** | `frontend/src/components/admin/users-admin-identity.tsx:390-395` | /admin/users › Davet et: switch "Davet e-postası gönder" is off, disabled, with "Henüz yok: bağlantıyı kopyalayıp kendiniz iletin." | Permanently disabled. `POST /auth/sso/admin/invites` accepts `send_email` (`backend/app/api/v1/sso.py:221-231`), and the /admin/authentication invites panel already sends (`components/identity/invites-panel.tsx:57`) | Enable the switch and send `send_email` (identity UI) |
| A4 | **BLOCKER** | `frontend/src/components/timetable/mobile-calendar.tsx:117` (buttons at `heat-lenses.tsx:252-254`) | Phone /timetable › Ay: the ‹ › month arrows do nothing | `onMonth={() => undefined}`; the month is computed from `date` and cannot change. `unplacedByDay={new Map()}` also hides unplaced counts on phones | Keep month state as `calendar-view.tsx:770` does (timetable UI) **after mobile optimisers** |
| A5 | MAJOR | `frontend/src/components/settings/settings-view.tsx:219-220`, `shell/app-shell.tsx:160-163`, `ui/data-table/data-table.tsx:112,180`, `app/globals.css:233,364,669` | Ayarlar › Görünüm › Yoğunluk: "Sıkı görünüm çizelgeye daha çok ders saati sığdırır" | Half-working. The value goes to `html[data-density]` and changes only `--row-h` in data tables, through CSS inheritance. That breaks the virtualiser, which still sizes rows at 44 px (`data-table.tsx:112`). The timetable uses its own view-state density, the booking grid uses the admin's slot density, and `--period-row-h` is never used. The per-user density override from the hand-off is therefore **visible but fake** | Wire it into the timetable/booking grid with admin slot density as the default, and feed the virtualiser the computed density, or remove the control (settings/timetable UI) **after mobile optimisers** |
| A6 | MAJOR | `backend/app/emails/kinds.py` (`booking_reminder`, `series_created`, `series_changed`, `approval_submitted`, `calendar_consent`, `new_device_sign_in`); `services/bookings_notify.py:347-354` | /admin/email lists these kinds with "Şablon hazır". Admins can edit, preview and test-send them | No code path sends them. `series.created` sends the `booking_created` mail instead. No reminder scheduler exists | Write the senders: reminder job, series digest, approval-submitted receipt, consent mail (mail). `new_device_sign_in` **after security follow-up** |
| A7 | MAJOR | `backend/app/services/identity/saml.py:150-197` (`parse_metadata`) | A SAML provider can take a federation aggregate URL (YETKİM/eduGAIN) | The aggregate's XML signature is not checked: signing certificates are read from whatever the URL returns. Absent, not faked | Check the metadata signature against a pinned federation certificate (identity) **after SAML library** |
| A8 | MINOR | `backend/app/emails/kinds.py:88-101` (`invitation`, `account_created`), `ops_alert` entry | /admin/email badge "Şablon hazır · W3-IDP/W3-OPS bağlayınca gönderilir" | Stale flag: these are sent (`services/identity/invites.py:126,364`; `ops_alerts.py:134` → outbox kind `ops_alert`, `notify_dispatch.py:211`) | Set `sender="wired"` (mail) |
| A9 | MINOR | `backend/app/emails/render.py:326,361`, `layout.py:172` | Mails have no "details card" (room · date · period · request no.) | The renderer exists, but no sender passes `details`. **Absent in effect** | Pass `details` from bookings/approvals notify (mail) |
| A10 | MINOR | (no code) | Mails have no one-click unsubscribe | `List-Unsubscribe` / `-Post` appear nowhere. **Absent** | Signed one-event-off token + header on "switchable" kinds (mail) |
| A11 | MINOR | (no code) | No "Takvime ekle (.ics)" link in mails | **Absent** | Signed one-event `.ics` link (mail) **after CAL-B** |
| A12 | MINOR | `saml.py:300-301` | An IdP that encrypts assertions fails with "encrypted assertions are not supported" | Honest refusal. **Absent** | XML-enc decrypt with an SP key (identity) **after SAML library** |
| A13 | MINOR | `frontend/src/components/identity/profile-microsoft.tsx`; `backend/app/api/v1/sso.py:133-145` (`/entra/link` only) | /profile can link a Microsoft account only | Google / OIDC / SAML profile linking is **absent** | Generic `/{slug}/link` (identity) |
| A14 | MINOR | `backend/app/importers/planning_list.py:589-591` vs `importers/preference_rules.py:213` | The import report says notes-column wishes "wait for review (soft, switched off)" | They are created with `enabled=True` (on while they wait) | Fix the wording (importers) **after lane C** |
| A15 | MINOR | `frontend/src/lib/api/endpoints.ts:105-114,~256` | (only if `/dashboard` returns 404/405/501) | `composeDashboard` fallback with hard-coded `current_week: 1`; `/dashboard` exists, so this is dead code | Delete the fallback (frontend api) |
| A16 | MINOR | `backend/app/services/learning_extract.py:573-580`; `services/moderation.py:143-146,1074-1076`; `services/solver_bridge.py:685-690` | Not visible | TODO stubs: `_planning_audit` returns `[]` (audited moves are not learned); department-secretary scope; requests with only a duration and no start are reported, never scheduled | Learning/moderation/solver backlog |

Clean areas: no `process.env.*MOCK*` paths, no "coming soon" pages, every nav entry has a `page.tsx`, every non-public route needs a user (I walked all 568 routes; the 37 without one are public by design: health, login, feeds by token, SSO, public schedule, security.txt). Placeholder detection is a guard (`core/config.py`). The integration "placeholder" cards are only fallback text.

---

## Part B: seeded institution data, can admins manage it?

**How the pod is seeded.** `deploy.sh` runs `seed.py run` after every healthy start. `profile.env` has `SEED_PROFILE=institution`. Steps:
1. `approval-mode=all`
2. Bahar grid + planning list
3. Güz grid + planning list
4. Final grid + exam list
5. `room_master.csv`
6. `learning-refresh`

The files are the repo's `backend/tests/fixtures`, mounted read-only. Each finished step is recorded once. The importers derive the preference rules (`importers/preference_rules.py`) from the free-text columns. Learning runs once (`cli.py:130-150`).

**Redeploy verdict.** Seed never overwrites admin edits. The risks are:
- (a) **renaming a step or adding one** re-imports that file over admin edits, with the re-import behaviour shown in the R column;
- (b) `SEED_FORCE=1` on a database without a marker.

Columns: V = view, E = edit, D = delete, R = re-import, S = survives a redeploy / a re-import, A = audited.

| Data | V / E / D / R in the UI (route › component) | S: redeploy / re-import | A |
|---|---|---|---|
| Terms | yes/yes/yes (refused while in use) at /admin/sessions › `admin/session-forms.tsx`. Created by imports | yes / yes (imports set name and dates only when empty) | yes (`Term` tracked, `services/audit.py:248`) |
| Term week calendar (lecture/exam week kinds) | view only (timetable). **No edit UI**; `PUT /terms/{id}/weeks` (`terms.py:173`) is never called | yes / **no**: grid re-import rewrites kind and label (`weekly_grid.py:474-477`) | yes (`Week` tracked) |
| Rooms | yes/yes/yes, re-import at /import › room master: /admin/rooms › `admin/rooms-admin.tsx` | yes / **partly**: capacity edits are lost for rooms not in the room master (**repro** `rename.py`: A102 103 → 96), because `room_admin.py:289-318` never marks `custom_fields.master` (`catalog.py:99-110`) | yes (`Room` tracked) |
| Room features / tags | yes/yes/yes at /admin/rooms › features (`lib/api/wave1.ts:416-427`) | yes / **no**: a removed PC tag comes back (**repro** `tags.py`: A103 `[]` → `['PC']`, `catalog.py:111-115` merges tags even for room-master rooms) | yes (`room.features`) |
| Departments = programmes | yes/yes/yes (refused when used) at /admin/departments | yes / **no**: a rename creates a duplicate programme on the next import (**repro**: 97 → 98 programmes; `departments.py:73-80`, `catalog.py:193`) | yes (`Program` tracked as `department`) |
| Faculties | list only (inside the programme wizard). **No edit/delete UI**; `catalog_admin.py:92-112` has no caller | yes / yes | yes (API) |
| Courses | search only (wizard). **No edit/delete UI** (`catalogApi.updateCourse` has no caller) | yes / yes (imports fill empty fields only, `catalog.py:244-252`) | yes (API) |
| Sections (imported) | view in /classes. **No edit/delete UI** (`catalogApi.updateSection/deleteSection` have no callers). New programmes only through /programs/new (drafts) | yes / yes for planning-list (snapshot merge, `planning_list.py:647-710`) | yes (API) |
| Instructors | search only (learning panel, wizard). **No edit/delete/merge UI** (`catalog_admin.py:166-185` unused) | yes / yes (a title edit survived the repro) | yes (API) |
| Meeting requests | V/E at /classes › `classes/class-inspector.tsx` (status and notes; students is **fake**, A1). No delete UI (`DELETE /requests/meetings/{id}` unused) | yes / **yes**: planning-list keeps planner edits by default (`on_conflict=keep`) | yes (`requests.py`) |
| Exam requests / exam schedule | V/E at /classes (exam kind); invigilation pool and plans at /exams/invigilation. No create/delete UI | yes / **no**: exam-list re-import overwrites every field and sets `archived=False` (`exam_list.py:266-281`) | yes |
| Preference rules (`FILE`) | V/E/D at /generate › rules step (`studio/term-rule-card.tsx`) and /moderation › Tercihler | yes / **partly**: `enabled`, `review` and weight are kept; kind, params and nl_text are rewritten and hardness is forced to soft (`preference_rules.py:219-221`); edited rules still "pending/auto" are **deleted** when the wish leaves the file (`:226-229`) | yes (`constraint.*`) |
| Learned habits (see below) | Summary + resets at Ayarlar › Öğrenme and /moderation/learning; per-person habits at /moderation/people/[id]; suggestions in the console and studio | yes / n/a (reset watermark) | yes for reset, purge, erase, accept, dismiss, snooze, restore, refresh |
| Period grid (P1–P18 clock times) | **No UI.** Hard-coded in `importers/normalize.py:339-363` (also `learning.py:93`, `find_room.py:48`, `bookings_calendar.py:46-51`). /admin/schedules edits only the booking periods | n/a (code) | n/a |
| Holidays | V/E/D at /admin/holidays. None seeded | yes / yes | yes (`Holiday` tracked) |
| Approval mode | Ayarlar | yes (seed step recorded once) | yes |
| **The xlsx files themselves** | Upload a corrected file at /import (all five kinds). **The seeded files are invisible**: `cli.py:16-48` never creates an `ImportJob`, so /import shows no history, no warnings or skipped rows, and `GET /imports/{id}/file` has nothing to download | n/a | **no**: `ImportJob` has no actor (`models/system.py:55-67`, `imports.py:_new_job`), so even UI imports do not record who imported |

### Learning / habits module
- **What it learns** (`services/learning_extract.py:1-37`): from definitive rooms, planner corrections against the import snapshot, manual and AI moves and locks, request text and times, booking series, and approval outcomes. Subjects: course, section, instructor, programme, user. Attributes: room, building, day, period band, day×band, tag.
- **Where it is stored:**
  - `learned_observations` (also the intake memory, `subject_type="intake"`);
  - `learned_priors` (score, Wilson confidence, half-life of two terms);
  - `suggestion_feedback`;
  - `learning_resets`.
- **What it does with that:** an accepted suggestion becomes a soft `ConstraintRow(source="LEARNED")` with weight 5.
- **What admins can do:**
  - see counts (`learning-memory-panel.tsx`) and per-person habits with evidence counts (`moderation/person-profile.tsx:115-132`);
  - accept, reject, snooze or restore one suggestion;
  - reset by person, term or all, with a reason and a 30-day undo;
  - KVKK erasure;
  - forget intake memory by row or file signature.
- **What admins cannot do:**
  - **correct or forget one habit or observation.** A habit row has no actions; the only fix is resetting the whole person;
  - **switch learning off.** There is no setting;
  - **tune it.** `MIN_CONFIDENCE`, `LEARNED_WEIGHT`, the half-life and the band times are constants (`learning.py:79-93`);
  - **re-learn.** `POST /learning/refresh` has no UI and nothing schedules it (`grep`: only `cli.py:147` and `api/v1/learning.py:61`), so the intro "öğrendikleri … düzenlemelerden" (learned from edits) is true only up to the seed;
  - **see the raw priors** (`GET /learning/priors`) or **purge** on demand (`POST /learning/purge`). Both are API only.

---

## Ranked fix list by owning area
(`after <lane>` = the files collide with that running lane.)

**1. Requests / classes**: `backend/app/schemas/requests.py`, `api/v1/requests.py`, `frontend/src/components/classes/classes-page.tsx`
- A1 enrolment edit (BLOCKER). The backend part is free; the frontend part goes **after mobile optimisers** if it touches the classes page.

**2. Solver / studio**: `backend/app/services/studio.py`, `api/v1/runs.py`, `services/run_params.py`, `frontend/src/components/studio/use-generate.tsx`
- A2 apply the default seed and weights on the server (BLOCKER). Free.

**3. Catalog admin UI (new, owner request)**: `frontend/src/lib/api/catalog-admin.ts` (already written, unused) + new /admin/catalog screens for instructors (edit, merge with `services/person_match.py`), courses, faculties, imported sections and meetings/exams (delete); also an editor for the term week calendar (`PUT /terms/{id}/weeks`)
- BLOCKER for the owner's ask. Free (the welcome guide only adds a tour entry later).

**4. Identity UI**: `frontend/src/components/admin/users-admin-identity.tsx`
- A3 enable the invite mail (BLOCKER). Free.
- A13 generic profile linking, A12 encrypted assertions, A7 metadata signature: **after SAML library**.

**5. Timetable phone**: `frontend/src/components/timetable/mobile-calendar.tsx`
- A4 (BLOCKER) **after mobile optimisers**.

**6. Learning**: `backend/app/services/learning.py`, `learning_extract.py`, `api/v1/learning.py`, `frontend/src/components/learning/*`, `moderation/person-profile.tsx`. Free.
- "Yeniden öğren" button + nightly refresh (MAJOR).
- Per-habit "Yanlış / unut", built as a scoped reset on (subject, attribute, value) (MAJOR).
- A `learning.enabled` setting plus editable thresholds and bands.
- Priors and purge in the UI.
- `_planning_audit` (A16).

**7. Importers re-import safety**: `backend/app/importers/exam_list.py`, `weekly_grid.py`, `preference_rules.py`, `catalog.py`, `backend/app/api/v1/room_admin.py`, `departments.py`. **After lane C** (planning-list identity / council writer).
- exam-list snapshot merge with `on_conflict`, as planning-list has.
- FILE rules: keep params and hardness once a person has edited them; never delete edited rules.
- Mark admin-edited room capacity and tags as authoritative ("master"), and respect removed tags.
- Programme aliases (keep the old canonical name on rename).
- Grid re-import keeps edited week kinds.
- A14 wording.

**8. Imports visibility and audit**: `backend/app/cli.py`, `models/system.py` + migration, `api/v1/imports.py`, `deploy/seed/seed.py`, `frontend/src/components/import/*`. **After lane C**.
- Seed imports create `ImportJob` rows, keep the file and the report, and record actor "seed".
- UI imports record `created_by` plus an `import.run` audit event.
- Seed docs: renaming a step re-imports.

**9. Period grid**: new `settings`/table read by `importers/normalize.py`, `services/find_room.py`, `services/learning.py`, `services/bookings_calendar.py`, `services/patterns.py`; frontend /admin/schedules. Larger change. **After lane C** and **after CAL-B** (feeds use the period times).

**10. Mail**: `backend/app/emails/kinds.py`, `render.py`, `services/bookings_notify.py`, new reminder worker
- A8 stale flags, A6 senders (`new_device_sign_in` **after security follow-up**), A9 details, A10 List-Unsubscribe.
- A11 `.ics` link **after CAL-B**.

**11. Appearance**: `settings-view.tsx`, `app-shell.tsx`, `data-table.tsx`, `timetable/model/view-state.ts`
- A5 **after mobile optimisers**.

**12. Cleanup**: `frontend/src/lib/api/endpoints.ts` (A15), `lib/api/adapters.ts:350` (hard-coded model list fallback).

---

## Roadmap suggestions (what a planner would expect and does not find)
1. A catalog screen ("Katalog") for instructors, courses, programmes and faculties, with merge and rename that the next import respects (aliases).
2. An import history that includes the seeded files: per-file report, "download original", "what changed since the last import", a dry-run diff before every re-import of every kind (planning-list has it; exam-list and grids do not), and undo of the last import.
3. An editable institution calendar: the period grid, lecture/exam/holiday week kinds per term, and holidays that the solver, the timetable and the class `.ics` feeds respect (today holidays affect bookings only).
4. Learning controls: on/off, "re-learn now", nightly refresh, per-habit correction, an evidence drill-down (which rows), tunable thresholds, and an "exclude this source" switch (approvals, bookings).
5. Booking reminders (the day before / an hour before) and series digests, with per-user opt-out through one-click unsubscribe.
6. A visible audit trail for data changes ("who imported or edited this course or room"), with a filter by entity and a link from each record to its history.
7. Bulk edit of rooms (capacity, features) by CSV export and import from /admin/rooms, round-tripping the room master.
8. Department-scoped planner roles (moderation TODO Q11) so secretaries see and edit only their programme.
9. Scheduling of requests that have a duration but no start time (solver TODO P19-C4).
