# Persona test: Fatih Bey, system administrator and timetabling coordinator (2026-10-15)

- **Ledger:** `persona-admin-2026-10-15`
- **Snapshot:** frozen copy of commit `cc9c45d` ("fix(runs): publish only finished hard-clean runs, one active run, keep the published run (review D4 / P19-01)")
- **Stacks:** `scripts/record/stack.sh`, both on SQLite.
  - Full stack: API `:18950`, web `:18951`. Bahar 2026, Güz 2026-27 and Final 2026 were imported, plus the room master. Admin language `tr`, with a teacher account.
  - Fresh stack: API `:18952`, web `:18953`, started with `--fresh`.
- **Credentials:** the local-stack defaults only (`admin@smartsched.local` / `Admin-2026!`, `ogretmen@smartsched.local` / `Teacher-2026!`). Test accounts created during the pass:
  - `planner.test@`, `viewer.test@` and `limited.admin@smartsched.local`, password `Test-2026!pw`
  - `bolum.sekreteri@` and `sekreter2@`
- **Evidence root:** `/tmp/claude-0/-home-user-classroombookings/ac8cf3be-4f7b-53da-a7ff-63cf01e137b0/scratchpad/persona-admin/` (called `EV/` below).
  - `EV/curl/*.txt` holds the exact requests and responses. Secrets are redacted: the one webhook secret the API returned is replaced by `whsec_<redacted>`.
  - `EV/shots/*.png` holds the screenshots.
  - `EV/*.json` and `EV/*.log` hold the crawl, motion, mobile and palette data.
  - `EV/scripts/*.mjs` holds the Playwright scripts. They use Chromium from `/opt/pw-browsers`.
- **Load caveat:** the machine was shared. The load average was 8–36 during most UI runs, so the frame numbers in §4 come with a same-session no-op baseline.

## 1. BLUF

- **Day-to-day admin works.** The following screens and workflows all worked end to end in Turkish, on the real Bahar/Güz/Final data:
  - users (add, edit, disable, CSV import with per-row results)
  - roles, with no-escalation enforced in both the API and the UI
  - room admin, approvals (approve, reject, withdraw)
  - the audit viewer with undo, LDAP test error path, maintenance mode, holidays
  - saved views, exports, the class inspector with provenance
  - every sidebar and ⌘K link. The four routes the strict review called 404 (`/find-room`, `/approvals`, `/admin/audit`, `/admin/approval-rules`) all render: **D6 is refuted**.
- **Not ready for a faculty go-live.** Fifty issues: **1 Blocker, 18 Major, 30 Minor, 1 Trivial**. The serious ones fall into four groups.
  - **Trust in the published timetable.**
    - A forced hard room clash keeps hard 100 and can be published (M-02).
    - A one-week run can replace the whole-term published timetable (M-04).
    - Run reports say "hiçbir kural bozulmadı" next to 34–123 over-capacity placements and a grid header showing "308 çakışma" (M-06, M-08).
    - Imported boards report 0 problems while the server lists 35–383 (M-07).
    - There is **no publish button at all** (M-03).
  - **Security.** The first-run installer can be raced into creating 10 administrators (M-01, D19).
  - **Crashes and dead ends.**
    - The Studio presets menu crashes the page (M-12).
    - One room-master job makes the whole import history fail with a fake "server error" (M-13).
    - The CRBS legacy import cannot work from the UI (M-14).
    - Keyboard users cannot open a class from the grid (M-16).
  - **Claims vs reality.** 12 of the 14 languages are 1.3 % translated (M-17). A KVKK sign-off is pre-seeded on every installation (M-18).
- **Scenarios**

| Scenario | Result |
|---|---|
| Import the Bahar list and the weekly grid (fresh stack, UI) | ✓ grid: 10,134 rows, 165 notes. List: 1,524 meetings, 507 warnings. Error messages for wrong files are generic (M-20) |
| Find a course (PHAR 240) | ✓ Studio, /classes, ⌘K, grid inspector with "Planlama listesi · Sayfa1 · satır 545" provenance |
| Generate week 3 | ✓ run #9, FEASIBLE_PARTIAL, 687/716 placed. The Studio card says "716 yerleşti" (M-11) |
| Move PHAR 240 to A 206 from 23 Feb | ✓ "23 Şubat tarihinden itibaren (4. hafta)" splits the series: weeks 1–3 in A 203, weeks 4–14 in A 206, with undo toast and focus kept. Verified in the API and in the exported xlsx |
| Turkish request: nursing first-years before 17:30 | ✗ in plain language (no AI key; chips misleading, M-29). ✓ through the "Belirli saatten sonra ders olmasın" template: Hemşirelik + 1. sınıf + "11. ders · 17:30 biter". All 25 Y1 nursing classes in run #9 end by P11 |
| Export the week to Excel | Partly: "Excel'e aktar" exports all 14 weeks while week 4 is on screen (M-32). Content correct |
| Infeasible request (102 students pinned to 30-seat B 201, hard) | ✗ accepted with no warning. The pre-check and diagnosis never name the capacity. The run silently drops the class and still shows hard 100 (M-10) |

- **Security**
  - **D1 guard:** works. Planners get 422. Admins need a written reason. `source=AI` is refused.
  - **D1 symptom:** still reachable. An admin waiver makes run #11 say "hiçbir kural bozulmadı" on its headline while 11 placed classes break capacity (for example ENG 106: 70 students in 30-seat B 406). The waiver note sits at the bottom of the report.
  - **D4:** fixed for FAILED, CANCELLED and RUNNING runs (409), and for deleting the active run (409). Still open through forced moves and week-horizon runs (M-02, M-04). The promised unique index is missing (M-05).
  - **D6:** refuted.
  - **Escalation:** 13 of 13 conclusive privilege-escalation attempts refused (ESC-12 was inconclusive because of a CSV format error).
  - **Viewer:** cannot download raw workbooks (403), but reads parsed rows and import warnings (by design).
  - **D19:** confirmed (Blocker).
  - **D16:** open in code.

## 2. Coverage checklist

✓ = tested and works · ✗ = tested and broken (issue id) · ◐ = partly · — = not present in the product

**Fresh stack (empty)**

| Item | Result |
|---|---|
| First-run installer: `/` while no user exists | ◐ redirects to `/login?next=/` with an "İlk kurulumu başlat" link, not straight to the installer |
| Installer: requirements step | ◐ two warning details are in English (M-39) |
| Installer: organisation step | ✓ "Kurumun adını yazın." on an empty name |
| Installer: admin step (empty, weak, mismatched password, then valid) | ✓ messages · ✗ focus stays on the submit button; the LDAP "leave empty" hint contradicts the rule (M-39) |
| Installer: race | ✗ M-01 |
| Import kind: planning list (Bahar v5) | ✓ 1,524 meetings, 507 warnings (500 shown) |
| Import kind: weekly grid (Bahar, Final) | ✓ 10,134 / 2,615 rows |
| Import kind: exam list (Final v2) | ✓ 926 rows, 5 errors, 500 warnings · the term had to be created first, and "Yeni dönem" has no Final/exam kind |
| Import kind: catalog | — no separate kind; the catalogue is derived from the planning list |
| Import kind: CRBS legacy | ✗ M-14, M-23 |
| Import kind: room master | ✗ no UI (M-24); API only |
| Wrong file type: `.csv` / `.png` | ✓ client toast "Yalnızca Excel dosyaları (.xlsx)…" |
| Wrong file type: CSV renamed to `.xlsx` | ◐ "Dosya okunamadı. Doğru Excel şablonu mu?" (M-20) |
| Wrong file type: grid workbook uploaded as a planning list | ✗ the same generic text, although the server knows the reason (M-20) |
| Import history list | ✗ M-13 |
| Data-issues report on a solver run (#10) + xlsx | ✓ `smartsched-run10-data-issues.xlsx` downloaded |
| Data-issues report on an imported run | ✗ M-07 |

**Generator Studio**

| Item | Result |
|---|---|
| Scope (term, kind, horizon, week chips) | ◐ M-26 |
| Classes (search, filters, inline student edit with "içe aktarılan değer 100 idi", pin dialog offers only rooms that fit) | ✓ |
| Rules: template gallery, day-window template, room-pin template | ◐ M-28 |
| Rules: NL without key | ✓ message "Kendi cümlenizle kural yazmak için YZ gerekir…" · ✗ chips (M-29) |
| Policy switches | ✓ rendered |
| Presets | ✗ crash (M-12) |
| Pre-check (blocked state, fixes, "Yine de oluştur" / "Önce düzelt" confirm) | ✓ |
| Generate + live run card | ◐ M-11 |
| Cancel a running run | ✗ deletes the run (M-27) |
| Undo / redo buttons | ✓ present (not deeply tested) |

**Runs**

| Item | Result |
|---|---|
| Runs list | ◐ M-30 |
| Live progress | ✓ in the Studio run card |
| Run report (KPIs, soft-preference chart, diagnosis with "Uygula ve yeniden çöz", tabs) | ◐ M-06 |
| Partial runs | ◐ M-49 |
| Diagnosis TR / EN | ✓ every server diagnosis carries `message_tr` and `message` · ◐ M-10 |
| Activate / publish from the UI | ✗ M-03 |
| Activate a FAILED, CANCELLED or RUNNING run (API) | ✓ refused with 409 |
| Activate a partial run (API) | ◐ allowed (M-49) |
| Activate a week run (API) | ✗ allowed (M-04) |
| Delete the active run (API) | ✓ 409 |
| Delete the active run (UI) | — no delete control |

**Timetable and /classes**

| Item | Result |
|---|---|
| Lenses Pano, Hafta, Gün, Ay, Dönem, Ajanda | ✓ no page errors · ◐ M-50 |
| Class inspector (why here, provenance, weeks strip) | ✓ |
| Manual move (preview, scopes all / week / from) | ✓ · ✗ capacity is soft (M-09) |
| Lock / unlock with undo | ✓ |
| Forced move | ◐ no force in the UI (confirm disabled on a clash). Planner + `force:true` → 403. Admin force → M-02 |
| Undo (toast) | ✓ |
| ⌘Z | not tested |
| Keyboard path to move | ✗ M-16 |
| Excel export | ◐ M-32 |
| /classes all-classes view (system views, search, saved view "Farklı kaydet" → `POST /views` 201) | ✓ |
| /classes export menu (planning-list xlsx, CSV, ICS) | ✓ |
| /classes provenance | ✓ |
| /classes default run | ◐ M-31 |

**Other planning screens**

| Item | Result |
|---|---|
| Chat panel without a key | ✓ "Asistan için YZ anahtarı gerekiyor. Ayarlar'dan ekleyin"; textarea and send disabled |
| Requests views | ✓ `/requests` → `/classes?view=review` ("İnceleme bekleyen 231") |

**Users and roles**

| Item | Result |
|---|---|
| Users: add (validation), edit, disable (login then returns 403 "user disabled"), import CSV (created / "Parola yok" / "Kullanıcı adı var") | ✓ · M-42 |
| Users: reset code, access check from the row menu | ✓ present |
| Roles: create | ✓ |
| Roles: limited admin cannot grant what they lack (UI) | ✓ checkboxes `aria-disabled`; role picker shows "(eksik: …)" |
| Roles: limited admin cannot grant what they lack (API) | ✓ 403 |
| Limited admin's landing page | ✗ M-38 |
| Departments | ✓ list; add/edit present · data-quality enhancement E-12 |

**Rooms**

| Item | Result |
|---|---|
| Room add / delete | ✓ |
| Room edit (owner, location, icon, notes, custom fields) | ✓ · no capacity field (M-46) |
| Room photo: valid PNG | ✓ HTTP 200 but no feedback (M-46) |
| Room photo: wrong type | ✓ refused · mixed language (M-36) |
| Delete a room that has bookings | ✓ guarded text |
| Groups: add, reorder with Alt+↑ ("5 içinde 4. sıraya taşındı", focus kept), delete, "Her bina için bir grup" | ✓ |
| Custom fields (text / bool / choice) | ✓ |
| Typed room features: starter catalogue, CSV, adopt tags | ✓ starter catalogue added 6+ typed features |
| ACL form | ✓ · English labels (M-36) |
| Access checker | ✓ shows "rolden" per permission · raw codes (M-36) |

**Booking setup**

| Item | Result |
|---|---|
| Sessions (create "Final 2026", open for booking) | ✓ |
| Weeks | ✓ empty-state + add form |
| Periods / schedules (18 periods) | ✓ |
| Holidays (add "Ara tatil (test)") | ✓ |
| Booking limits (role form) | ✓ |
| Maintenance mode (teacher gets 503 and a banner; admin bypasses) | ✓ · M-48, M-36 |

**Approvals and audit**

| Item | Result |
|---|---|
| Approval rule create (UI validation "Her adım için en az bir onaycı seçin") | ◐ M-35 |
| Inbox: approve (keyboard `a`), reject with note, withdraw (teacher) | ✓ · M-33, M-34 |
| Audit viewer (filters, expand, before/after, CSV) | ✓ |
| Audit undo (booking restored) | ✓ |
| Audit coverage | ✗ M-15 |

**Integrations and settings**

| Item | Result |
|---|---|
| Calendar sync admin (Google / Microsoft config) | — no admin UI (M-40); API shows both "configured: false" |
| Webhooks (default off: `webhooks_enabled:false`, list empty) | — no UI (M-40) · M-41 |
| KVKK switches | — no UI (M-40) · M-18 |
| LDAP test-connection error path | ✓ "Dizine ulaşılamıyor" (`Connection refused` in the API) |
| Org settings | ✓ |
| Language files | ✓ "Kendi ifadeleriniz" overrides UI present |
| Languages: 3 spot-checked (TR, EN, DE / FR / ES) | ✗ M-17 |
| Exports: run xlsx, classes xlsx/csv/ics, audit CSV, data-issues xlsx | ✓ |
| What's new | ✓ · English content (M-36) |
| Notification bell | ✓ · M-34 |
| ⌘K: 20 static destinations + run entries, no 404 (`EV/palette3.json`) | ✓ · M-44 |

**Cross-cutting**

| Item | Result |
|---|---|
| Sidebar crawl: 42 URLs, all HTTP 200, no 404 | ✓ (`EV/crawl.json`) · M-37 |
| Security spot-checks | §5 |
| Mobile 390 px (13 admin screens) | ◐ M-43 |
| Keyboard-only | ◐ skip link ✓, palette ✓, approvals A/D/R ✓ · M-16, M-45 |
| Reduced motion | ◐ §4 |
| Motion frame budget | ✗ §4 (M-19) |

## 3. Issues

Severity: **Blocker** = must fix before any deployment · **Major** = wrong data, a crash, a missing core function or a security gap · **Minor** = friction, inconsistency or polish · **Trivial**. Paths are relative to the snapshot root: `B/` = `smartsched/backend/app/`, `F/` = `smartsched/frontend/src/`.

| ID | Screen/URL | Steps | Expected | Actual | Severity | Area | Likely file(s) | Suggested fix + acceptance check |
|---|---|---|---|---|---|---|---|---|
| M-01 | `POST /api/v1/org/setup` (`/setup`) | Empty `users` table. Fire 10 parallel `POST /org/setup` with different e-mails (`EV/curl/d19-setup-race.txt`) | One 201, nine 409 | **10 × 201, 10 ADMIN users** | Blocker | security (D19) | `B/api/v1/org.py:140-170` (`first_run_setup`: count, then insert) | Take a DB lock or insert a unique sentinel row (`org_setup_done`) in the same transaction (SQLite `BEGIN IMMEDIATE`, PG advisory lock). **Check:** 10 concurrent setups give exactly 1 admin and 9 × 409 |
| M-02 | Grid move / `POST /runs/{id}/assignments/bulk-move` | Admin `force:true` moves BCT 128 onto HEM 242 (A 204, Mon P2–4) in run 9, then `POST /runs/9/activate` (`EV/curl/forced-moves.txt` FORCE-7…9) | Hard score drops below 100; activate → 409 | Both rows `is_conflict:true` "room overlap", but `hard_score` stays **100** and activate returns **200** | Major | integrity (D4) | `B/api/v1/calendar.py:217-268` (`_bulk`, also bulk-lock and restore) never calls `_rescore` (`B/api/v1/runs.py:594`; only the single-move endpoint at `runs.py:570` does) | Call `_rescore(db, run)` after every applied bulk-move, bulk-lock and restore. **Check:** after a forced clash, `GET /runs/9` has `hard_score < 100` and activate is 409 with the clash listed |
| M-03 | `/runs/{id}`, `/runs`, `/timetable` | Look for a publish / "Yayınla" control as admin | A publish button with a confirm (and the D4 blockers shown) | None. `api.runs.activate` exists but no component calls it; the only path is chat "undo" | Major | planning UX | `F/lib/api/endpoints.ts:207`, `F/components/runs/run-view.tsx`, `F/components/runs/runs-list.tsx` | Add "Yayınla" to the run report header and the runs list. Show the 409 `issues[]` in Turkish; mark the active run with a "Yayında" badge. **Check:** e2e publishes run #1 from the UI and sees the badge; publishing a FAILED run shows the blockers |
| M-04 | `POST /runs/{id}/activate` | Activate run 9 (`horizon WEEK`, weeks [3]) while run 1 (term board) is active (`EV/curl/forced-moves.txt` FORCE-5) | Refuse, or require an explicit "replace whole term with week 3" confirm | 200: the Bahar term's published timetable becomes one week | Major | integrity (D4) | `B/api/v1/runs.py:251-262` (`publish_blockers`) | Refuse non-TERM horizons unless the request sets `scope_ok` / merge-into-parent. **Check:** activating a WEEK run while a TERM run is active returns 409 "week run cannot replace the term timetable" |
| M-05 | DB schema | `sqlite_master` for `schedule_runs` | `uq_schedule_runs_active` partial unique index (the `activate_run` docstring promises it) | Missing from the models and from every migration (head is `0017`). Only serialisation on SQLite keeps one active run (5 parallel races, `EV/curl/d4-partial-race.txt`) | Major | integrity (D4/P19-01) | `B/models/runs.py`, `alembic/versions/` (no `0018`) | Add `Index('uq_schedule_runs_active', 'term_id', 'kind', unique=True, postgresql_where=is_active, sqlite_where=is_active)` plus migration 0018. **Check:** PG test with 2 concurrent activations leaves exactly one active |
| M-06 | `/runs/7`, `/runs/10`, `/runs/11` | Open the report of any solver run | Headline lists rule breaches | "681/717 ders yerleşti · hiçbir kural bozulmadı / Yerleşen her ders bütün kurallara uyuyor" while: run 7 has **123** over-capacity placements (MAT 112 §1 180 in C 201/126, RAD 274 80 in D 106); run 11 has a capacity waiver with 11 breaches (shown last in the diagnosis list) | Major | integrity / UX (D1) | `F/components/runs/run-view.tsx:42`, `messages/tr.json:103` `runs.partialRing`, `B/services/planner_check.py` | Build the headline from `stats.planner_check` + `waived_rules` + trusted-lock capacity counts: "681/717 yerleşti · 77 ders planlayıcının küçük dersliğinde · kapasite kuralı esnek". Waivers go first. **Check:** run 11 headline names "kapasite esnek, 11 ders" |
| M-07 | `/runs/1` (imported board) | Open the imported Bahar board report (fresh and full stacks) | Data issues visible and downloadable | "100/100 Uygun · Sorunlar 0 · İhlal yok. Tüm katı kısıtlar sağlanıyor", "Yerleşen 0", no Excel button. `GET /runs/1/data-issues` has 383 (fresh) / 35 (full) `locked_room_too_small` items, e.g. "MAT 112 §1: A204 74 kişilik, bu derste 180 öğrenci var" | Major | integrity / UX | `F/components/runs/issue-groups.tsx`, `F/lib/api/shell-extra.ts:181-186`, `F/components/runs/runs-list.tsx` (`isImportBoard`) | Always render the server issue groups and the xlsx link, including for import runs; compute KPIs from assignments. **Check:** `/runs/1` shows "Planlanan derslik öğrenci sayısından küçük 35" and downloads the xlsx |
| M-08 | `/timetable?run=7`, assignments API | Open run 7 on the grid | One conflict count across report, grid and API | Grid header **"308 çakışma · 79 uyarı"**; run 9 API flags 389/842 `is_conflict` (310 "room overlap", mostly co-taught rows such as MAT 112 §1 #14236/#14237, PSK 122/PSK 132 in C 205); report "0 çakışma" | Major | integrity / UX | `B/services/calendar_views.py:489,670` (`enrich…is_conflict`), `B/services/planner_check.py` | Use one source of truth (`planner_check`); treat same-slot co-taught / listed-twice rows as "ortak ders", not overlap. **Check:** run 9 grid and report show the same count |
| M-09 | Move dialog (`move-preview`) | PHAR 240 §1 (80 students), choose C 606 (30 seats) | Hard refusal, or explicit admin override with a reason | `ok:true`, capacity `severity:"soft"`, "Taşı" enabled; no force or reason needed (`EV/shots/m63-move-small-room-preview.png`) | Major | integrity (Q8 in academician-needs) | `B/api/v1/calendar.py` move check, `F/components/timetable/move-dialog.tsx` | Treat capacity shortfall as hard unless `force` + reason (admin). Show "80 öğrenci 30 kişilik C 606'ya sığmaz". **Check:** preview `ok:false` with code `capacity` |
| M-10 | Studio rules → precheck → run → diagnosis | ING 302 students 100→102; template "Her zaman bu derslikte" ING 302 → B 201 (30), Kesin; precheck; "Yine de oluştur" (run #10) | Rule refused or warned at once: "102 öğrenci 30 kişilik B 201'e sığmaz" | Preview `issues:[]`. Precheck: "ING 302 için kurallardan sonra hiç derslik kalmadı (room is forbidden for this event (room_forbid); not in the pinned room set (room_pin #2); room carries forbidden tag(s) ['TIP'] (room_tags))" (English, cites a non-existent room_forbid, no capacity). Run diagnosis: "52 derslik yasaklı, 5 derslik sabitlenen derslik değil…". Run FEASIBLE_PARTIAL, hard 100 | Major | planning UX / solver explain | `B/api/v1/studio.py` (`/studio/constraints/preview`), `B/solver/domains.py:226-257` reasons, `B/solver/diagnose.py` | Preview: intersect the pin with the capacity/tags of the target classes and return an issue. Diagnosis: report the per-room reason for the pinned set first. **Check:** preview of `{event_ids:[244], room_ids:[21]}` returns "102 öğrenci 30 kişilik B 201'e sığmaz" |
| M-11 | Studio step 5 run card | Generate week 3 (run #9) | "687/716 yerleşti" | **"716 yerleşti · 0 çakışma · Tüm kesin kurallar sağlandı"** and "#7 ile karşılaştırma: yerleşen −13" (a week run compared with a term run) | Major | planning UX | `F/components/studio/run-cards.tsx` | Use `stats.placed` / `events_total`; compare only runs of the same horizon and weeks. **Check:** card for run 9 reads 687/716 |
| M-12 | `/generate` → "Hazır ayar kullan" | Click the preset menu | Menu opens | Page replaced by "Something went wrong · Base UI error #31" (deterministic, `EV/shots/m165-presets-crash.png`) | Major | crash | `F/components/studio/presets.tsx:39` (`DropdownMenuLabel` = `Menu.GroupLabel` outside a `Menu.Group`; the only such use in the app) | Wrap the label and items in `<DropdownMenuGroup>`. **Check:** clicking `preset-menu` shows "Paylaşılan hazır ayarlar"; add a unit test rendering `PresetMenu` |
| M-13 | `/import` | Any `room-master` job exists (e.g. API upload), then open `/import` | History list | Two "Sunucuda bir sorun oluştu…" toasts; history missing although `GET /imports` is 200 | Major | import | `F/lib/api/schemas.ts:198` (`ImportKind` lacks `"room-master"`), `F/lib/api/endpoints.ts:54,148` | Add `"room-master"` (and tolerate unknown kinds with `.catch`). **Check:** fresh stack with a room-master job lists all 5 jobs without a toast |
| M-14 | `/import?kind=crbs` | Enter a DSN, start | Import, or a clear error | `POST /imports/crbs` 202, the job FAILED with "pip install pymysql…". The UI shows no job state, only generic toasts. The SQL-dump upload the API supports has no UI | Major | parity / import | `F/components/import/import-wizard.tsx:149-152`, `B/api/v1/imports.py:167-181`, `smartsched/backend/Dockerfile:33` | Offer SQL-dump upload (the default path); show `job.error` translated; ship pymysql or hide DSN when absent. **Check:** upload a CRBS dump fixture → report with users/rooms/bookings counts |
| M-15 | `/admin/audit` | Bulk-move, force-move, lock/unlock, Studio enrolment edit 100→102 | Each has an audit row with before/after | None of them appear (last 50 actions: `room.update`, `run.activate`, `constraint.*`, `user.*` …) | Major | audit (D5/P19-02) | `B/api/v1/calendar.py` (`_bulk`, bulk-lock, restore), `B/api/v1/studio.py` (`/studio/meetings/bulk`) | `publish_event("assignment.move"/"assignment.lock"/"meeting.update", before, after)`. **Check:** a forced move creates one `assignment.move` row with `force:true` |
| M-16 | `/timetable` keyboard | Tab to a class chip (focus ring visible), press Enter | Inspector opens (then "Taşı") | Quick-create dialog for the grid's focused empty slot ("A 204 · Pzt 08:30–09:10 … Rezervasyon / Ders talebi"); Space does nothing; no keyboard path to move a class | Major | a11y | `F/components/timetable/time-grid.tsx`, `F/components/timetable/event-chip.tsx` (Enter handler bubbling to the grid) | Handle Enter/Space on `.cal-chip` and `stopPropagation`; Enter → inspector, `m` → move dialog. **Check:** keyboard-only e2e moves PHAR 240 |
| M-17 | `/profile`, Kurum ayarları → Diller | Enable Deutsch/Français/Español, select one | Translated UI | Every page is English: 12 languages have **36 / 2,743** strings (`locale-data.json`, "Kısmi çeviri · %1"). ROADMAP Phase 18 marks "All 13 classroombookings UI languages" as done | Major | i18n / parity | `smartsched/frontend/messages/{cs,cy,da,de,es,fi,fr,it,nl,pt,pt-br,sv}.json`, `docs/ROADMAP.md` Phase 18 | Import the CRBS language files for the booking strings, hide languages under a threshold (e.g. 60 %), and correct the ROADMAP tick. **Check:** `/approvals` in Deutsch shows "Genehmigungen" |
| M-18 | `GET /api/v1/calendar/admin/settings` | Fresh install | No KVKK sign-off until an officer records one | `calendar_sync_enabled:true` and `calendar_sync_signoff` = "KVKK officer (institution user decision)", 2026-10-08, enabled, shipped as the **default for every installation** | Major | KVKK | `B/services/bookings_settings.py:124-140` (`KVKK_SIGNOFF_2026_10_08`, `INTEGRATIONS_SPECS`) | Default `calendar_sync_enabled:false`, sign-off `null`; record this institution's decision with a migration or data seed for this deployment only. **Check:** fresh stack returns `calendar_sync_signoff:null` |
| M-19 | Studio / run report / grid / approvals | §4 probes | ≤ 3 dropped frames per interaction, no LoAF > 100 ms | 13.7–56.5 dropped per interaction, worst LoAF 142–380 ms (low-load re-run); approvals sheet still animates `translate` under reduced motion | Major | motion / perf | `F/components/timetable/*`, `F/components/studio/studio-view.tsx`, `F/components/ui/sheet.tsx` | See §4 (T3 continuation). **Check:** audit §2 spec passes on CI for these four flows |
| M-20 | `/import` | Upload a CSV renamed `.xlsx`, or the grid workbook as a planning list | Specific reason ("Bu bir haftalık derslik takvimi (Şekil C) gibi görünüyor") | "Dosya okunamadı. Doğru Excel şablonu mu?" for both. Server: "the workbook is not a valid .xlsx…" / "planning list is missing columns: ['code','day','start','end']; headers=[None,'Pazartesi',…]" | Minor | import UX | `F/components/import/import-wizard.tsx:100-105`, `B/importers/planning_list.py` | Map server errors to TR texts; detect the other kinds from headers and offer "Haftalık takvim olarak aktar". **Check:** grid-as-list shows the suggestion |
| M-21 | Import report | Bahar grid / list | Translated, deduplicated warnings with row numbers | English messages; grid notes repeated ×5 per sheet ("room A103 has capacity 47 and 33…"); row "0"; `unparseable start time datetime.datetime(2025, 10, 10, 0, 0)`; capped at 500 of 507 without saying so | Minor | import | `B/importers/weekly_grid.py`, `B/importers/normalize.py`, `B/importers/report.py` | Dedupe per (sheet, room); TR message keys; format cell values; show "507 uyarı, ilk 500 gösteriliyor". **Check:** Bahar grid shows ≤ 43 distinct notes |
| M-22 | Import drop zone | Upload a 0.8 MB workbook | "Sunucuda okunuyor…" while parsing | sr-only status stays "Uploading" (English) for 50+ s while the server parses; text swapped by a DOM-patch effect | Minor | import / a11y | `F/components/import/magnetic-drop.tsx:70-93`, `F/components/ui/beui/file-upload.tsx:80-82` | Pass translated labels as props; map `processing` to its own status. **Check:** screen-reader text "İşleniyor" during parse |
| M-23 | `POST /imports/crbs` | Planner token, `dsn=mysql://u:p@127.0.0.1:18951/crbs` | Admin only + host allowlist | Accepted (202) and the backend tries the host (failed only because pymysql is absent) | Minor | security (D16) | `B/api/v1/imports.py:167-181`, `B/importers/crbs_legacy.py` | `require_permission("planning.admin")` + allowlist setting. **Check:** planner gets 403; admin to a non-allowed host gets 422 |
| M-24 | `/import`, `/admin/rooms` | Look for a room-master import | Upload `room_master.csv` with a diff | No UI (API `POST /imports/room-master` only) | Minor | import / parity (P19-I7) | `F/components/import/import-wizard.tsx:27-30` | Add the kind with a diff preview. **Check:** e2e uploads `room_master.csv` |
| M-25 | Import wizard | Steps "Tür seç · Yükle · Önizle · Bitti" | "Önizle" before commit | Committed on upload; step 3 is the report | Minor | import (P19-I4) | `F/components/import/import-wizard.tsx`, `B/api/v1/imports.py` | Dry-run + commit. **Check:** DB unchanged until "Uygula" |
| M-26 | `/generate` scope | Güz term; Bahar + week 3 | "14 hafta, 58 derslik" (API) | "2 hafta boyunca **0 derslikte** 635 ders"; "SmartSched 3. hafta için 874 dersi 0 dersliğe…"; "Bu dönem için henüz başarılı bir çalıştırma yok" while runs #7/#9 exist; once the rail said "Hafta seçilmedi" while the summary said "3. hafta" (seen once) | Minor | planning UX | `F/components/studio/studio-reducer.ts:380-400` (`rooms: i.summary?.counts.rooms ?? 0`), `F/components/studio/scope-step.tsx:179` | Show "Sayılıyor…" until the summary for the current term arrives. **Check:** after switching to Bahar the sentence reads 58 rooms |
| M-27 | Studio run card "İptal" | Cancel a running generation | Run → CANCELLED, stays in history | `api.runs.cancel` sends `DELETE /runs/{id}`: the run is deleted (`EV/curl/cancel-deletes.txt`, 204 then 404) | Minor | planning | `F/lib/api/endpoints.ts:180`, `F/components/studio/run-cards.tsx:115` | Call `POST /runs/{id}/cancel` (ROADMAP review follow-up). **Check:** run listed as "İptal" afterwards |
| M-28 | Studio rule templates | Add the day-window rule; open "Her zaman bu derslikte" | Rule card appears; reach count current | Rule list keeps "Kesin (0)" until reload; reach preview trails one change (5 shown, server 10); empty template shows "873 derse uygulanıyor (100 %)"; course picker lists "ING 302 §" twice with nothing to tell the rows apart; week chips "W1…W19" in English; stored text lower-cased "hemşirelik 1. sınıf" | Minor | planning UX | `F/components/studio/template-gallery.tsx`, `F/components/studio/slot-picker.tsx`, `F/components/studio/use-rule-actions.ts` | Invalidate the rules query on create; debounce + abort stale previews; show day/time/size per course row; use "H". **Check:** the new rule shows without reload |
| M-29 | Studio rules without an AI key | Click "Hemşirelik 1. sınıf 17:30'dan sonra ders almasın" | Opens the matching structured template | Appends the sentence into the composer; "Kurala çevir" stays disabled; one click fired `POST /elicit` → 409 silently | Minor | AI / UX | `F/components/studio/write-it.tsx` | Without a key, map each example chip to its template prefilled. **Check:** chip opens "Belirli saatten sonra ders olmasın" with Hemşirelik/1/17:30 |
| M-30 | `/runs` | Look at labels and status | Given labels; published marker | Labels ignored ("#10 çalıştırma #9 üzerinden"); cancelled run #8 shown as "İçe aktarılan pano #8"; no "Yayında" marker | Minor | planning UX | `F/components/runs/runs-list.tsx:27-31` (`isImportBoard` heuristic) | Use `params.source == GRID_IMPORT` (keep it in the schema); show `label`, `is_active`. **Check:** run 8 shows "İptal · D4 probe…" |
| M-31 | `/timetable?run=7`, `/classes` | Open a Bahar run while the switcher says Güz | Context follows the run; /classes shows the published run | Switcher stays "Güz 2026-27"; /classes defaults to the latest run #10 (week-3 test) | Minor | planning UX | `F/components/shell/term-switcher.tsx`, `F/components/classes/classes-page.tsx` | Sync the term with the run; default /classes to `is_active`. **Check:** /classes for Bahar shows "Run #1 · Yayında" |
| M-32 | `/timetable` → Diğer → "Excel'e aktar" | Viewing week 4 | This week (or a choice) | All 14 weeks (`EV/curl/ui-tt-smartsched-run7.xlsx`); API supports `?weeks=` | Minor | export | `F/components/timetable/capsule-toolbar.tsx` | Add "Bu hafta / Tüm dönem"; pass `weeks`. **Check:** export at week 4 has one sheet "Hafta 4" |
| M-33 | `/approvals` | Select a request, press `a` | Next request focused; sheet closes or advances | Toast "Onaylandı: B 207." but focus falls to `<body>` and the decided request's sheet stays open over the list | Minor | a11y (T4) | `F/components/approvals/*` | Advance to the next pending item and move focus to it. **Check:** after `a`, `document.activeElement` is `approval-2` |
| M-34 | Bell, `/approvals` | Approve #1, reject #2, teacher withdraws #3 | Notifications update; withdrawn visible to approver | Bell still shows 3 unread "Onay bekleyen oda talebi"; withdrawn #3 is in neither tab | Minor | notifications | `B/services/approvals*.py`, `F/components/shell/notification-bell.tsx` | Resolve the in-app notification on decide/withdraw; add a "Geri çekildi" filter. **Check:** bell count 0 after all three |
| M-35 | `/admin/approval-rules`, `/admin/users` | Create a rule with "Atanmış onaycılar" before anyone is designated; edit the admin user | Warning "Bu derslik için atanmış onaycı yok"; approver field on every admin user form | Rule saved; the admin's edit form has no `user-room` "Onayladığı derslikler" (only the new-user form) | Minor | approvals | `F/components/admin/users-admin.tsx`, `F/components/admin/approval-rules*.tsx` | Show approver scope on edit; warn on rules without approvers. **Check:** admin edit shows the field |
| M-36 | Many (TR UI) | Use the UI in Turkish | Turkish everywhere | English leaks: dialog/sheet sr-only "Close" (`F/components/ui/dialog.tsx:83`, `sheet.tsx:78`); "Run #10"; permission groups "rooms/audit/approvals" + descriptions; ACL "Request single bookings that an approver confirms"; access checker raw `book_single.request`; audit filter raw `room_field`, `schedule`, `period`, `timetable_week`, `translation`, `building`, `user_constraints`; teacher maintenance page "bookings are in maintenance mode"; photo "unsupported image type (jpg, png, gif)"; installer requirement details; changelog; role matrix aria-labels "Tek seferlik: Create single bookings"; grid aria "çakışma: room overlap: A 107 with #13828"; error boundary "Something went wrong / Retry" | Minor | i18n | files listed; `B/services/bookings_i18n.py`, `messages/tr.json` | Add the keys; translate server `detail` codes. **Check:** i18n test fails on English words in TR snapshots of these screens |
| M-37 | Most pages | Load `/dashboard`, `/bookings`, `/admin/*` | No hydration errors | Intermittent "Minified React error #418 (HTML)" on 14 of 42 crawled routes (`EV/crawl.json`, `EV/palette3.json`) | Minor | frontend | layout / date or locale-dependent SSR text (not isolated) | Run a dev build to get the diff; gate time/locale text behind `after-hydration`. **Check:** crawl reports 0 page errors |
| M-38 | Login as a user without `planning.view` (limited admin) | Log in | Land on a permitted page | `/timetable` with "Bu dönem için henüz bir program yok", buttons "Program oluştur" / "Excel'den içe aktar", toast "Bu işlem için yetkiniz yok"; sidebar shows "Çizelge" | Minor | permissions UX | `F/app/page.tsx` landing logic, `F/components/admin/nav-items.ts` | Choose the landing page by permission; hide Çizelge without `planning.view`. **Check:** limited admin lands on /admin/users |
| M-39 | `/setup` | Run the installer | Consistent copy, focus on the first error | "Üç kısa adım" with 4 steps; password hint "Dizin (LDAP) hesapları için boş bırakın" but the empty first-admin password is refused; focus stays on the submit button (same in the user form) | Minor | onboarding | `F/app/setup/page.tsx`, `F/components/admin/users-admin.tsx` | Fix copy; focus the first invalid field. **Check:** after an empty submit, focus is on `#email` |
| M-40 | Admin | Look for webhooks, calendar-sync provider config, KVKK switches | Admin screens (APIs exist) | No UI for `/webhooks`, `/calendar/admin/settings` (Google/Microsoft client ids), or any KVKK/AI-intake switch | Minor | integrations / KVKK (P19-A1) | `F/components/admin/` (missing), `B/api/v1/webhooks.py`, `B/api/v1/calendar_sync.py` | Add "Entegrasyonlar" and "KVKK" sections. **Check:** webhooks can be enabled, tested and disabled from the UI |
| M-41 | `POST /api/v1/webhooks` | Admin URL `http://127.0.0.1:18951/` | Private / loopback refused like metadata | 201 (metadata 169.254.169.254 is refused with 422) | Minor | security | `B/api/v1/webhooks.py` URL validator | Refuse loopback/RFC1918 unless an allowlist setting permits. **Check:** 127.0.0.1 → 422 |
| M-42 | `POST /auth/login` | Disabled user, correct password | Generic "E-posta veya şifre hatalı" | `403 {"detail":"user disabled"}` reveals the account state | Minor | security | `B/api/v1/auth.py` | Same response as bad credentials (log the reason server-side). **Check:** both return 401 with the same body |
| M-43 | 390 px | `/admin/rooms`; long forms | No horizontal scroll; content clear of the tab bar | Tabs 414 px wide → page scrolls sideways; the floating tab bar covers the last form rows (e.g. "Kullanıcılar'da göster" on Roles) | Minor | mobile | `F/app/(app)/admin/rooms/page.tsx` tabs, shell bottom padding | Make the tabs scroll inside their container; add `padding-bottom` = tab bar height. **Check:** `scrollWidth == 390` on all 13 screens (`EV/mobile.json`) |
| M-44 | ⌘K | Type "Roller", "Denetim", "Onay kur" | Setup sections listed | Only course matches (BES 535 "Ağırlık Denetim…") or nothing; setup sections absent | Minor | navigation | `F/components/shell/command-palette.tsx`, `F/components/admin/wave1-sections.ts` | Include `ADMIN_SECTION_NAV_ITEMS`. **Check:** "Onay kur" → "Onay kuralları" |
| M-45 | Sidebar (keyboard) | Tab from the skip link | Visible focus | Logo link, collapse button and nav links: computed `outline:none`, no box-shadow at focus | Minor | a11y | `F/components/shell/sidebar*.tsx` | Add `focus-visible:outline-2`. **Check:** visual focus on every sidebar item |
| M-46 | `/admin/rooms` | Create "Z 999"; edit C 606; upload a photo | Capacity editable here; upload feedback | No capacity field in the edit panel (only on `/rooms`); photo upload 200 with no toast or preview change; "Z 999" silently created building #5 "Z" | Minor | rooms admin | `F/components/admin/rooms-admin.tsx`, `B/api/v1/rooms.py` | Add capacity / exam capacity; toast "Fotoğraf yüklendi"; ask before creating a building. **Check:** edit C 606 capacity from Kurulum |
| M-47 | `POST/PUT /constraints` | Planner: soft capacity with `{"match":""}`, `{"event_ids":[]}`, `{"match":" "}` (`EV/curl/d1-guard-bypass.txt`) | 422 (untargeted) | 200/201: `is_targeted` checks key presence, while `select_events` treats an empty selector as "every event". Harmless today (pruning stays hard for targeted soft rules), but `waived_rules()` then reports `capacity` as waived and a later solver change would open D1 | Minor | security (D1) | `B/solver/constraints/_common.py:92-96`, `B/services/constraint_guard.py:44-50` | Treat empty/blank selectors as untargeted. **Check:** these 3 bodies return 422 for a planner |
| M-48 | Kurum ayarları | Toggle "Bakım modu", navigate away | Saved, or an unsaved-changes guard | Toggle alone does nothing (needs "Kaydet" at the bottom); no guard (my "off" toggle silently left maintenance on) | Minor | settings UX | `F/components/admin/org-settings.tsx` | Autosave switches, or a dirty-state guard. **Check:** navigating with unsaved changes prompts |
| M-49 | `POST /runs/7/activate` | Partial run, 36 classes unplaced | Explicit confirm listing unplaced classes | 200, no confirmation possible (and no UI, M-03) | Minor | policy (D4) | `B/api/v1/runs.py:248` (`PUBLISHABLE` includes partial) | Require `accept_unplaced:true` with the count. **Check:** without it, 409 "36 ders yerleşmedi" |
| M-50 | `/timetable` | Open with no params (Güz, today = week 4) | Current week; one title | Week 1; heading "Hafta 1 · Hafta 1 · Ders" | Trivial | UX | `F/components/timetable/model/view-state.ts:68` | Default to the term week of today. **Check:** `/timetable` opens on Hafta 4 |

## 4. Motion findings

Method: the `motion_designer` skill (§2 principles, `references/audit.md` §2). Each flow ran through the rAF probe and Long Animation Frames, a `devtools.timeline` trace for Layout events, and `document.getAnimations()` checks for the 300 ms ceiling, infinite loops and transform under reduced motion. Scripts: `EV/scripts/motion.mjs` and `EV/scripts/probe.mjs` (the same code as `scratchpad/measure.mjs`), headless, 1× CPU. Two sessions: high load (`EV/motion.log`) and lower load (`EV/motion-lowload.log`; the baseline was 3.3 there). Reduced transparency was not measured.

| Interaction | dropped / interaction | LoAF > 50 ms | worst LoAF | Layout events | over 300 ms | reduced motion | reduced transparency |
|---|---|---|---|---|---|---|---|
| baseline: no-op click ×4 | 1.3 / 3.3 | 1 / 1 | 92 / 189 ms | 0 | none | — | — |
| studio: rail step changes ×3 | **33 / 39.7** | 11 / 15 | **272 / 320 ms** | 17 | none | no loops ✓ | not measured |
| studio generate: click → "Engel var" confirm → "Önce düzelt" | **17.5 / 24** | 5 / 7 | 149 / 185 ms | 14–16 | none | no loops after check ✓ | not measured |
| studio generate → run card (whole progress period, high load) | 561 dropped over ~60 s | 79 | 472 ms | 87 | none | — | — |
| run report: tabs Çizelge → Kurallar → Sorunlar | **11.3 / 13.7** | 8–10 | 114 / 142 ms | 10 | none | load: no movement ✓ | not measured |
| run report: "2 seçenek daha" + scroll | **26 / 22.5** | 8–9 | 167 / 232 ms | 1 | none | — | — |
| run report: first open from list | 98 in 244 frames | 12 | 300 ms | 22 | none | — | — |
| grid: confirm move (1 week) + toast undo | **81 / 56.5** | 18–23 | **482 / 380 ms** | 15–17 | none | — | not measured |
| grid: scoped move "from week 4" (scenario) | 108 in 90 frames | 13 | 292 ms | 9 | none | — | — |
| approvals: Karara bağlanan ↔ Açık | **24.5 / 14.5** | 6–10 | 192 / 150 ms | 8–12 | none | — | not measured |
| approvals: open request sheet + Esc | **36 / 23.5** | 8–10 | 209 / 193 ms | 8–9 | none | **✗ `translate` animation still runs** | not measured |
| approvals: approve (keyboard `a`) | 124 in 148 frames | 17 | 440 ms | 11 | none | — | — |
| audit: expand/collapse 3 rows (high load, budget 83 ms) | — (invalid baseline) | 24 | 282 ms | 9 | none | — | — |

Per-moment judgement (skill §2):

| Moment | Purpose ("motion tells the user …") | Non-motion signal | Busy state | Focus after action | Verdict |
|---|---|---|---|---|---|
| Studio generate | "the plan is being made; here is its result" | ✓ "Kontrol ediliyor ve kaydediliyor…" label, then the run card with text | ✓ button `disabled` · ✗ no `aria-busy`; a 1–3 min wait with no live region announcing completion | ✓ confirm dialog focuses "Yine de oluştur" | ✗ frame budget; ✗ the number in the result card is wrong (M-11) |
| Run report | "here is how the run went" (ring + tickers) | ✓ `dl` with plain numbers; digit strips are `aria-hidden` | ✓ skeletons | n/a | ✗ frame budget on tab switch; ✗ the headline text is wrong (M-06), so motion reinforces a false message |
| Grid move | "the class went there" (drop-settle, toast with undo) | ✓ toast "PHAR 240 §1 → A 206 taşındı · Geri al", inspector text | ✓ "✓ Sunucu kontrolü: uygun" before confirm | ✓ returns to `inspector-move` | ✗ 380–482 ms main-thread stall on confirm/undo: the whole grid re-renders (memoise chips, one overlay — skill §4 "grids never animate per cell") |
| Approvals inbox | "the request was decided and left the list" | ✓ toast "Onaylandı: B 207." / "Reddedildi. Talep edene bildirildi." | n/a | ✗ focus to `<body>`, sheet stays open (M-33) | ✗ frame budget; ✗ reduced motion still translates the sheet (`F/components/ui/sheet.tsx` should use `useReduce()` / `data-motion` → opacity ≤ 100 ms) |
| Import upload | "bytes are going up, then the server reads" | ◐ visible text "Yüklendi. Sayfalar sunucuda okunuyor…" | ✗ sr-only says "Uploading" during processing (M-22) | n/a | ◐ |
| Idle pages | no motion | — | — | — | ✓ no infinite animations on /dashboard, /generate, /runs/10, /timetable |

The 300 ms ceiling was never exceeded. Under reduced motion the palette and the run report have no transform animations. The failures are main-thread work, not the animations themselves: these continue ROADMAP motion ticket **T3**, and the approvals focus problem is **T4**.

## 5. Security findings

**D1 (soft untargeted structural rule): guard confirmed fixed; symptom partly open** (`EV/curl/d1-guard.txt`, `d1-guard-bypass.txt`, `d1-waiver-run.txt`)

| Request | Result |
|---|---|
| Planner `POST /api/v1/constraints {"term_id":1,"kind":"capacity","params":{},"hardness":"soft","weight":5}` | **422** "…only a planning administrator may waive it, with a reason" |
| Admin, the same without a reason | **422** "a waiver needs a written reason" |
| Admin `"source":"AI"` | **422** (schema allows ADMIN/FILE only) |
| Planner `PUT /constraints/1 {"params":{}}` | **422** |
| Planner hardness omitted | **422** |
| Planner `{"match":""}`, `{"event_ids":[]}`, `{"match":" "}` | **200/201**, accepted (M-47). Not exploitable today: targeted soft capacity keeps hard pruning |
| Admin with reason "D1 probe…" | **201**, `source_ref.waiver` recorded and an audit `constraint.waive` row written |
| Run #11 (Bahar week 3) with that waiver | FEASIBLE_PARTIAL, **hard 100**, `stats.waived_rules == ["capacity"]` (P19-00c ✓). 4 new over-capacity placements vs run #10 (e.g. ENG 106: 70 students in B 406, 30 seats); the diagnosis says 11 placed classes break capacity |

- **Answer to the review question.** Yes: the run puts classes into rooms that are too small while showing 100/100. The report does name the waiver now, but only as the last diagnosis item. Its headline still reads "693/716 ders yerleşti · hiçbir kural bozulmadı" (M-06).
- **Same symptom without any waiver.** It occurs through planner-locked rows. Run #7 places MAT 112 §1 (180 students) in C 201 (126 seats) and RAD 274 (80) in D 106 (82; the lock expects 320), with hard 100 and "hiçbir kural bozulmadı" (123 over-capacity placements in total).
- **Manual moves.** Capacity is soft there too (M-09).

**D4 (publish guard): fixed for the reviewed cases; open through other paths** (`EV/curl/d4.txt`, `d4-partial-race.txt`, `forced-moves.txt`)

| Request | Result |
|---|---|
| `POST /runs/8/activate` (CANCELLED) | **409** `{"message":"run cannot be published","issues":["run 8 is CANCELLED…","run 8 breaks hard rules (hard score None)…"]}` (the second message is misleading for a cancelled run) |
| `POST /runs/7/activate` while RUNNING | **409** |
| `DELETE /runs/3` (active) | **409** "run 3 is the published timetable; activate another run first" |
| Viewer activate | **403** |
| Planner activate (FEASIBLE import run) | **200** (planning.edit) |
| `POST /runs/7/activate` (FEASIBLE_PARTIAL, 36 unplaced) | **200** (M-49) |
| `POST /runs/9/activate` (WEEK run) while TERM run 1 is active | **200** (M-04) |
| Admin forced clash (`bulk-move … "force":true` onto HEM 242), then `POST /runs/9/activate` | hard stays 100, **200** (M-02) |
| 5 × parallel `activate` of runs 1 and 7 | exactly one active each time on SQLite. The `uq_schedule_runs_active` index the code relies on does not exist (M-05) |
| Planner `bulk-move … "force":true` | **403** "moving despite a conflict is admin-only" |

**D6 (dead nav routes): refuted on cc9c45d.**
- Crawl: 42 URLs from the sidebar, the admin hub and the ⌘K list, all HTTP 200 with headings.
- `/find-room` "Boş derslik bul", `/approvals` "Onaylar", `/admin/audit` "Denetim kaydı" and `/admin/approval-rules` "Onay kuralları" all render.
- ⌘K: every destination opens a real page (`EV/palette3.json`; "Yeni derslik" opens `/admin/rooms?tab=rooms&new=1` with the dialog open).

**Privilege escalation via role edit: confirmed safe (13 / 13 conclusive attempts refused; ESC-12 inconclusive, wrong CSV columns)** (`EV/curl/escalation.txt`)

Setup: the limited admin holds `setup.users`, `setup.roles` and `room.view`.

| Request | Result |
|---|---|
| `POST /roles {"permissions":["planning.admin"]}` | 403 "to grant these permissions you need permissions you do not hold: planning.admin" |
| `PUT /roles/5` (own role) + `setup.settings` | 403 |
| `PUT /roles/3` (Planner), description only | 403 "to edit this role you need…" |
| `PUT /users/5 {"role_id":1}` / `{"role":"ADMIN"}` | 403 |
| `POST /users` with role_id 1 / role ADMIN | 403 |
| `POST /users/1/password`, `PUT /users/1 {"is_active":false}`, `PUT /users/1 {"email":…}`, `POST /users/1/reset-token` | 403 "managing this account requires every permission its role holds" |
| `POST /users/import` with default `role_id=1` | 403 |
| `POST /users/import` with a CSV `role` column "Administrator" | row status `forbidden` |
| UI | checkboxes for missing permissions are `aria-disabled`; role options read "Administrator (eksik: approvals.decide, audit.view, …)" |

**Viewer reading raw import rows** (`EV/curl/viewer-raw-rows.txt`, `viewer-raw-rows-fresh.txt`)

| Request | Result |
|---|---|
| `GET /imports/5/file` (raw workbook) | **403** ✓ |
| `GET /imports` and `GET /imports/5` | **200**: the summary with 500 row-level warnings (cell values such as "row 48: unparseable start time …") |
| `GET /requests/meetings?term_id=1` | **200**: 1,524 parsed rows with instructor names and free-text notes |
| Teacher on the same endpoints | 403 |

By design (`planning.view`), but it is personal data under KVKK. Consider a narrower `planning.view_people`.

**Other checks**

| Finding | Ref |
|---|---|
| **D19 confirmed**: 10 concurrent installers → 10 admins | Blocker, M-01 |
| **D16 open in code**: Planner may submit any DSN host | M-23 |
| Webhooks: admin-only ✓, default off ✓, metadata IP refused ✓, loopback accepted | M-41 |
| Disabled-account message leaks state | M-42 |
| KVKK sign-off pre-seeded | M-18 |
| Maintenance mode: teacher `POST /bookings` → 503; admin (bypass permission) → 201 ✓ | `EV/curl/maintenance.txt` |

## 6. Classroombookings parity (admin features tried)

| CRBS admin feature | SmartSched | Note |
|---|---|---|
| Installer (requirements, org, first admin) | partly | works; race (M-01), copy (M-39) |
| Users: add / edit / disable / delete / import CSV | works | delete present (not executed); CSV import richer than CRBS |
| Roles + permissions + booking limits | works | no-escalation stricter than CRBS |
| Departments | works | 146 imported programmes incl. near-duplicates (E-12) |
| Rooms: add / edit / delete / photo / owner / location / icon | partly | capacity not on the admin edit panel; no photo feedback (M-46) |
| Room groups + ordering | works | keyboard reordering announced |
| Room custom fields | works | text / yes-no / choice |
| Room ACL (role / department / user, per room or group) | works | English labels (M-36) |
| Access checker | works | (beyond CRBS) |
| Sessions (terms) incl. selectable / current | works | no exam kind in "Yeni dönem" |
| Holidays | works | |
| Timetable weeks (A/B) | works | |
| Schedules / periods | works | 18 periods |
| Settings: org name, logo, timezone, date formats, grid display, login message | works | |
| Maintenance mode | works | needs "Kaydet" (M-48); English message for staff (M-36) |
| LDAP settings + test | works | |
| E-mail (SMTP) | present | test not executed |
| Language files (CRBS: 13 languages + DB overrides) | partly | overrides UI present; 12 languages at 1.3 % (M-17) |
| Booking conflicts screen | present | renders (not exercised) |
| Bookings export (CSV) | works | via `system.export_bookings` |
| Legacy data import (CRBS DB) | missing in UI | DSN only, needs pymysql; dump upload has no UI (M-14) |
| Approvals, audit + undo, typed features, find-room | beyond CRBS | work (with M-33, M-34, M-15) |

## 7. Enhancements (ranked)

| # | Enhancement | Value for Fatih Bey | ROADMAP mapping |
|---|---|---|---|
| E-1 | Publish button with blockers, history and rollback ("Yayında" badge, diff vs previous published run) | Fixes M-03/M-04/M-49 in one place | P19-01 (UI part) + "publish history and rollback" (Phase 19 proposed later) |
| E-2 | One integrity headline per run: placed / unplaced / planner-room shortfalls / waived rules / co-taught rows, the same on the grid, the report and the Studio card | Fixes M-06/M-07/M-08/M-11 | P19-00c (report part) + new **P19-00d "single integrity summary"** |
| E-3 | Capacity as a hard edit rule with an admin override + reason, listed under "kabul edilen istisnalar" | Fixes M-09, academician Q8 | new; relates to D1 / P19-00a |
| E-4 | Import dry-run with kind auto-detection and Turkish errors ("bu bir haftalık takvim") | Fixes M-20/M-25 | P19-I4, P19-I1 |
| E-5 | Room-master and CRBS-dump import in the wizard | Fixes M-14/M-24, parity | P19-I7; Phase 18 "Legacy CRBS upgrade path" |
| E-6 | Audit every planning action (move, lock, force, studio edit, cancel) | Accountability for forced moves | P19-02 |
| E-7 | Keyboard-first grid: Enter → inspector, `m` → move, arrows across slots | Fixes M-16 | Backlog "grid … context menu, move-scope popover, undo/redo" + new a11y item |
| E-8 | Integrations & KVKK admin screens (webhooks, Google/Microsoft keys, AI intake switches, sign-off record) | Fixes M-18/M-40 | P19-A1; calendar sync follow-ups |
| E-9 | Studio template targeting several programmes at once (Hemşirelik + Hemşirelik (İngilizce), year 1) and example chips that open templates without an AI key | Completes the nursing scenario without AI | new (Studio backlog) |
| E-10 | Translation completeness gate (hide languages < 60 %) + import the CRBS language files | Honest language list | Phase 18 language item (reopen) |
| E-11 | Export dialog: this week / date range / whole term, per room or programme | Fixes M-32 | Calendar follow-ups ".ics export per subject" (extend) |
| E-12 | Department/programme merge tool (e.g. "Cerrahi Hastalıklar…" vs "Cerrahi Hastalıkları…", "Ameliyathane" vs "Amelihathane", "Bahar") | Clean pickers in users, rules and the data-issues report | new (P19-C1 CRUD scope) |
| E-13 | ⌘K: setup sections and actions ("Yeni kullanıcı", "Bakım modunu aç") | Faster admin navigation | P19-06 (extend) |
| E-14 | Bell: resolve approval notifications on decision; withdrawn filter | Fixes M-34 | Phase 17 A3 notification hub |

## Appendix: data left on the isolated stacks

Everything is in throw-away SQLite databases under `EV/work*`.

- **Bahar term rules**
  - constraint 1: day_window "Hemşirelik 1. sınıf, P11"
  - constraint 2: room_pin "ING 302 → B 201"
  - ING 302 (meeting 244) enrolment 102
  - the D1 waiver (constraint 3) was deleted
- **Run 7 edits**
  - PHAR 240 split: weeks 1–3 in A 203, weeks 4–14 in A 206
  - BCT 128 lock was toggled on and back off
- **Run 9 edits:** BCT 128 force-moved onto HEM 242
- **Published runs:** run 1 (Bahar board) is active again.
- **Bookings:** approval rule "B 207 onaylı rezervasyon (test)"; bookings 1 (approved and restored), 2 (rejected), 3 (withdrawn), 4 (admin).
- **Settings:** holiday "Ara tatil (test)" (Güz); maintenance off; languages back to tr + en.
- **Fresh stack:** the installer was run on purpose (users table emptied twice and restored from a backup).
