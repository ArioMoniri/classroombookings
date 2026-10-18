# Helper file router: "drop any file, it says what it is and gives you the next step"

Owner: product designer (hb23-design-2026-10-18) · Status: v1 spec, build-ready (2026-10-18) · Tickets: **HB-23a…d** in
`docs/ROADMAP.md` ("HB-23 · Helper file router (owner 2026-10-18)").
Extends [`helper.md`](helper.md) (card contract `helper.card.v1`, sheet, hand-overs, motion §7, a11y §8, simplicity §9).
Depends on: `docs/design/v2/phase19-intake.md` (council drop zone), `docs/design/import-wizard.md`, `docs/design/v2/motion.md`
§3.8 (OS-file drag rule) and §3.21 (helper), `docs/testing/flows/MOBILE.md` M-01…M-14.

Owner's words (2026-10-18): "the helper part for admin or academicians: maybe the admin doesn't know which type of file
he has; it should support routing the admin by getting the file and generating in-flight buttons or guidance, and should
be easy to use, tested with UX and tester and designer subagents."

---

## 0. BLUF

- **One new thing for the person:** a file can be dropped, attached (📎) or pasted into the helper sheet (desktop ⌘J side
  sheet, phone full-screen sheet), or dropped anywhere on a signed-in page. The helper answers with **one card**: what
  the file is, why it thinks so, which term it belongs to, what to watch out for, and **one primary button** that opens the
  right page with the file already attached and the form filled in.
- **No new detector.** A thin server function, `classify_file`, combines the four classifiers that already exist (§1):
  the importers' header check (`importers/detect.py`), the council's magic-byte format sniffing and shape detection
  (`council/formats.py`, `council/fastpath.py`), the council's structure analyst (`council/structure.py`) and the users
  CSV header check (`services/bookings_users.py`). Two small sniffs are new: CRBS SQL dumps and calendar files. **No
  model call.** It works in index mode with no AI key. A model can only re-order a tie, and only when the council AI
  switch (KVKK sign-off) is on (§4.6).
- **The helper never imports.** The button is a **hand-over** (helper.md §4.1 rule 3). The target page's own preview and
  "Uygula" still do the writing, with their existing guards (`term_lock`, `WrongFileError`, `term_check`, `kvkk_guard`,
  RF-06 preview, RF-08 audit).
- **No second upload.** Classify stages the bytes **encrypted, for 10 minutes, bound to the person, usable once**. The
  key exists only inside the token the browser holds (§6.3). The target page sends `upload_token` instead of the file.
  Nothing reaches the database, an import job, the upload folders or the helper history until the person presses the
  page's own action. An audit row is written when the person presses the card's button (`helper.file.handoff`).
- **Role-aware.** Routes come from the existing permission keys (`planning.edit`, `setup.rooms`, `setup.users`,
  `book_single.create` …). An academician who drops a planning list is pointed to **Derslerim**, a calendar file to
  **Profil › Takvim**, and a booking list to **Taleplerim** or **Hızlı rezervasyon**. When there is no route for them,
  the card says politely that this is a job for the planning team. It never names who holds the permission.
- **Simplicity:** one primary per state, at most two secondary buttons, "Bu dosya nedir?" folded by default, and a
  certainty word instead of a percentage.

## 1. Inventory: what already exists (reuse map)

### 1.1 Classification that already exists

| Where | What it decides | Input | Output | Notes for the router |
|---|---|---|---|---|
| `backend/app/importers/detect.py` `detect_kind(headers)` | `planning-list` · `exam-list` · `weekly-grid` · `room-master` (or None) | one header row | kind | Turkish header specs (`planning_list.HEADER_SPEC`, `exam_list.HEADER_SPEC`). It powers `WrongFileError` ("Bu dosya bir sınav listesi gibi görünüyor…") and the wizard's "… olarak içe aktar" offer (`summary.detected_kind`, M-20). **It does not check the time axis:** the transposed fixture `universal/bahar_week1_transposed.xlsx` reads as `weekly-grid`, but the weekly-grid importer cannot read it (§4.3 agreement rule) |
| `backend/app/council/formats.py` `probe` / `detect` / `precheck` | file **format** by magic bytes (xlsx, xls, ods, csv/tsv, json, xml, ics, docx, pdf, image, eml, txt), plus per-format caps (zip bombs, ODS repeats, XML entities, JSON depth, ICS expansion, image pixels) | bytes + name | format id, `route_of()` = `structured` / `ai` | Runs in the rlimit child (`safe_files.run_isolated`). The extension is only a tie-break inside one family. A renamed photo is refused by name (T-R1-26) |
| `backend/app/council/fastpath.py` `detect_shape(rendered)` | `planning-list` · `exam-list` · `weekly-grid` · `room-master` · `intake-v1` · `ics` | rendered grids | shape | Stricter than `detect_kind`: a planning list needs `end` + `definitive` too, and a weekly grid needs ≥ 5 room headers and a vertical time-slot axis. It works on **every tabular format** (CSV / ODS / XLS are transcoded by `workbook_for`) |
| `backend/app/council/structure.py` `analyze(rendered)` | `room_list` · `request_list` · `exam_list` · `timetable_grid` · `calendar` · `staff_list` · `rules` · `other`, each with a confidence | grids and text units | `SheetAnalysis` per sheet, column → field map (lexicon, TR + EN) | It recognises English headers (`universal/bahar_requests_en.csv` → `request_list` 0.9) and transposed boards. The model is an optional second voter there (`council/llm.py`) |
| `backend/app/services/bookings_users.py` `header_columns(row)` | a users CSV header (TR/EN aliases, CRBS positional fallback) | first CSV row | column map or `Refusal` | 5 MB cap in `POST /users/import` |
| `backend/app/services/import_term_check.py` `file_term(filename, path)` / `term_check(...)` | season + calendar year from the file name, else the sheet titles; mismatch with the target term and a suggested term | name + path | `{file_season, file_year, source, mismatch, suggested_term_id}` | Uses `council/term_match.py`. **Ask (HB-23b):** let `file_term` take `bytes` as well (`open_workbook` already accepts bytes), so classify never writes a plain file |
| `frontend/src/components/import/term-hint.ts` `seasonOf` / `termMismatch` | client-side season from the file name | file name | mismatch | Kept as an instant hint before the server answers |
| `frontend/src/components/onboarding/copy.ts` `predictedRoute` + `file-drop.tsx` `ACCEPTED_FORMATS` | "Doğrudan / YZ" route per extension | file name | badge | The accepted list is reused verbatim for the helper's `accept` |

Measured on the repo fixtures (2026-10-18, `detect_format` + `fastpath.detect_shape` + `structure.analyze` + `file_term`):

| Fixture | Format | Importer shape | Council kind | Term from file | Router result (§4) |
|---|---|---|---|---|---|
| `bahar_derslik_planlama_listesi_v5.xlsx` | xlsx | planning-list | request_list 0.90 | Bahar, no year (file name) | **Planlama listesi**, sure |
| `guz_derslik_planlama_2026_2027_v2.xlsx` | xlsx | planning-list | request_list 0.90 | Güz 2026 | **Planlama listesi**, sure |
| `final_planlama_listesi_2026_v2.xlsx` | xlsx | exam-list | exam_list 0.90 | Final 2026 | **Sınav listesi**, sure (the word "planlama" in the name is ignored: headers win) |
| `bahar_derslikler_takvimi_2026.xlsx` (19 sheets) | xlsx | weekly-grid | timetable_grid 0.95 | Bahar 2026 | **Haftalık derslik takvimi**, sure |
| `guz_derslikler_takvimi_2026_2027.xlsx`, `final_derslikler_takvimi_2026_v2.xlsx` | xlsx | weekly-grid | timetable_grid 0.95 | Güz 2026 / Final 2026 | **Haftalık derslik takvimi**, sure |
| `universal/bahar_week1_transposed.xlsx` | xlsx | — (detect_kind says weekly-grid) | timetable_grid 0.95 | Bahar | **Çizelge (yan çevrilmiş)** → Kurulum sihirbazı, likely |
| `universal/bahar_requests_en.csv` | csv | — | request_list 0.90 | Bahar | **Ders talep listesi (İngilizce sütunlar)** → Kurulum sihirbazı, likely |
| `room_master.csv` | csv | room-master | room_list 0.90 | — | **Derslik ana listesi**, sure |
| `universal/rules_memo.docx` | docx | — | rules 0.90 (and room_list 0.90 on another unit) | — | **Kurallar / yazı** → Kurulum sihirbazı, likely |
| `universal/final_exams_sheet.pdf`, `final_exams_page1.png` | pdf / image | — | exam_list 0.90 (pdf tables) / needs AI (image) | Final | **Sınav listesi (PDF / görüntü)** → Kurulum sihirbazı, with the AI-off warning when the switch is off |

### 1.2 Importers and their entry points (the routing targets)

| Kind | Endpoint | Permission (existing key) | Accepts | Page (prefill today) |
|---|---|---|---|---|
| Planlama listesi | `POST /imports/planning-list` (`term_code`, `week_count`, `on_conflict`, `dry_run`) | `planning.edit` (`Planner`) | .xlsx / .xlsm (the wizard refuses others: `glass.import.onlyXlsx`) | `/import?kind=planning-list` |
| Sınav listesi | `POST /imports/exam-list` | `planning.edit` | .xlsx / .xlsm | `/import?kind=exam-list` |
| Haftalık derslik takvimi | `POST /imports/weekly-grid` (`term_code`, `year`, `term_kind`) | `planning.edit` | .xlsx / .xlsm (full load) | `/import?kind=weekly-grid` |
| Derslik ana listesi | `POST /imports/room-master` | `planning.edit` **or** `setup.rooms` | .csv / .txt / .xlsx / .xlsm | `/import?kind=room-master` (`room-master-import.tsx`) |
| classroombookings (CRBS) yedeği | `POST /imports/crbs` (dumps or DSN); full upgrade `POST /crbs-upgrade` | `planning.edit` / `planning.admin` | .sql / .txt | `/import?kind=crbs` (`crbs-upgrade.tsx`) |
| Kullanıcı listesi | `POST /users/import` (`role_id`, `department_id`, `password`, `enabled`, `force_password_reset`) | `setup.users` | CSV ≤ 5 MB | `/admin/users` → "İçe aktar" sheet (`users-admin.tsx`, `data-testid="users-import"`) |
| Any other file, or several files | `POST /council/jobs` (Ingestion Council: any format, fast path for known shapes, KVKK-gated AI) | `planning.edit` | `ACCEPTED_FORMATS` (≤ 25 files, ≤ 15 MB each, ≤ 50 MB per job) | `/onboarding` (`onboarding-flow.tsx`, `file-drop.tsx`) |
| Rules from a document (chat ingest) | `POST /terms/{id}/preferences/upload` | planner | text documents | not a router target in v1 (the council covers rules documents) |

### 1.3 Guards and settings the router must reuse

| Guard / setting | File | How the router uses it |
|---|---|---|
| Byte cap, streamed (`upload_max_mb` 25), zip pre-inspection, bounded workbook open, isolated parse | `app/core/safe_files.py` (`read_upload`, `inspect_zip`, `open_workbook`, `run_isolated`, `Limits.from_settings`) | Classify reads with `min(upload_max_mb, council_max_file_mb)` = **15 MB** by default, and parses in the rlimit child with `max_rows=200` (classification needs the header area only) |
| KVKK upload guard for recording / test stacks (`KVKK_UPLOAD_GUARD=1`, dev/test only) | `app/core/kvkk_guard.py` `check(data, filename)` → `kvkk_seed_workbook` / `kvkk_unmasked_names` | Runs **before** staging. A refused file gives the `refused` state (§5) and nothing is staged. Production never reads it |
| Council AI = KVKK cross-border switch (`ai.intake_enabled`, `ai.vision_enabled`, sign-off record) | `app/ai/policy.py` `ai_allowed()`; Settings alias `council_ai_enabled` | The only gate for the optional tie-breaker (§4.6) and for the "scans need AI" warning |
| Term write lock | `app/services/term_lock.py` | Classify calls `assert_unlocked` in read mode to show a warning. The import itself still waits for or refuses the lock |
| Helper confirm-token pattern (HMAC, helper-only key label, nonce claimed once) | `app/ai/helper/confirm.py` `sign` / `verify` | The upload token copies the pattern with its own label `helper-file` (§6.3) |
| Rate limit | `app/core/ratelimit.py` | `helper.files.classify`: 20 per minute per user, 200 per day |
| Audit | `app/services/audit.py` `record` | `helper.file.handoff` on the card's button (§6.4); the import jobs keep their RF-08 audit with `source: "helper"` |

### 1.4 Helper pieces reused as they are

- **Card contract** `backend/app/ai/helper/schema.py` (`helper.card.v1`): `ChoiceCard` (ambiguous), `RefusalCard`
  (refused), `ErrorCard` (error), `Txt` / `Texts`, `Plain` (no URL, no HTML), `Name`, `Token`, `UtcDatetime`. **One new
  wire type, `file`** (§7.2). The client renderer `components/helper/cards/render.tsx` maps it to the new
  `cards/file.tsx`. Like every other card, an unknown type falls back to `answer` + `nav`.
- **Hand-over links** `components/helper/handover-links.ts` (`handoverHref`): add `fileHandoffHref(featureId, params)`
  (§6.5).
- **Feature links** `components/helper/feature-links.ts` + `feature-index.gen.ts`, generated from
  `backend/app/ai/helper/features.yaml`. The router names targets by `feature_id` (`import`, `onboarding`,
  `admin.users`, `profile.calendar`, `my_classes`, `my_requests`, `reserve`, `find_room`). The server never sends a URL.
- **Sheet, store, composer:** `helper-sheet.tsx`, `helper-store.ts` (add a `fileHandoff` slot), `PromptComposer` (add the
  📎 button), `cards/frame.tsx`, `cards/choice.tsx`, `cards/status.tsx`, `show-me.tsx` ("Göster" for the target control).
- **Drop zones:** `components/import/magnetic-drop.tsx` (beUI file-upload, MIT, already vendored) and
  `components/onboarding/file-drop.tsx`. For an **OS file** drag, motion.md §3.8 applies: an instant tint and outline,
  no lift and no magnet.

## 2. References (Mobbin, researched 2026-10-18) and what was taken

All references are screenshots for study. No code or assets are taken from them. Licence: Mobbin's reference use only.

| Reference | What it shows | Taken / changed |
|---|---|---|
| [HubSpot · Importing a file (flow)](https://mobbin.com/flows/76a881cf-e903-4eaf-bb60-f7a779cd06c2) | Step 1 asks "What kind of data is in your file?" with one illustrated card per object type and a sentence each; later "0 errors found, of 3 rows scanned" | **Inverted:** we detect first and only ask when unsure. The chooser (§5 ambiguous) keeps HubSpot's "kind + one sentence of what happens". The plain scanned-rows sentence became our evidence line |
| [Attio · Importing a CSV (flow)](https://mobbin.com/flows/2c5ec636-6d46-416e-b798-ae09d51881c3) | File name in the header, stepper (Upload → Map → Review → Preview), "Generating import preview", then a "Start import" confirmation | The target page keeps **its own** preview and confirm. The router only skips the "pick a kind" and "pick a file" steps. The file-name chip on the target page is taken from here |
| [Fibery · Importing a CSV (flow)](https://mobbin.com/flows/b74631cd-e3b7-4273-8803-0eebaff0d350) | A tile per source, then the chosen file shown as a chip with ✕ above a "Reupload file" zone | The handed-over file row on `/import` with ✕ "Dosyayı kaldır" and the zone kept below it |
| [Heidi · "Upload a PDF and we'll automatically detect available fields"](https://mobbin.com/screens/d30a792e-d7c0-44be-8d0c-5c65a0e21856) | Detect-on-upload promise, a red line for an unsupported file, a blue tip box, "View formatting guide" | The unknown state: one sentence of what we read, examples of each accepted file and a link to the templates (§5) |
| [Mistral AI · Upload file, "Choose how you want to use this file"](https://mobbin.com/screens/624a02f7-d62a-41c8-8d19-54a54535418d) | An explicit "File purpose" select above the zone | "Başka bir tür seç" as the purpose override when our guess is wrong |
| [Dropbox Dash · Add to Stack](https://mobbin.com/screens/ab247955-6962-47a8-bf52-e9b67a816bc4) | An amber notice inside the upload dialog about who can see the content | The KVKK line under the drop zone: "Onaylayana kadar hiçbir şey kaydedilmez." |
| [Rows · AI Analyst starters](https://mobbin.com/screens/b94ddeac-60ff-4a0a-839b-ab86fa2a85dd) | The assistant's first suggestion is "Import file or scan image" | Admin and planner starter "Elimde bir dosya var, ne yapayım?" (§8.3) |
| [Square · thread with an attached CSV](https://mobbin.com/screens/ba9fcbfc-11b2-491a-81d8-71b3e853c407) | The file appears as a chip in the user's bubble, followed by "Thinking…" | The user bubble shows a file chip. The status reads "Dosya okunuyor…" (not "Düşünüyor": no model is used) |
| [Zapier Central · action complete + action chips](https://mobbin.com/screens/cb65c41e-e7b6-4bd9-af40-cd92d768e90d) | Collapsible "Action complete" block and action chips under the reply | Our "Bu dosya nedir?" disclosure. Chips are **not** taken (one primary rule) |
| [Savee · "Just drop your images or videos here."](https://mobbin.com/screens/8494c1b0-237f-4a3e-b9bc-ba38289b0d3e) | Full-screen drop overlay with one sentence and a device picker | The page-level drop target. Ours is calmer: a tinted inset outline with one line, no full black screen (§8.4) |
| [Asana · Upload a file](https://mobbin.com/screens/e7f3cfea-d013-4586-b7fc-6a8a992249c0) and [Fiverr · drop zone](https://mobbin.com/screens/9feef30c-b0e1-4cde-ac17-6d149f641206) | Accepted formats and the max size printed under the zone | "Excel, CSV, ICS, SQL, PDF… · en çok 15 MB" under every router drop zone |

Components (all existing, no new third-party code):

| Component | Source | Licence |
|---|---|---|
| beUI `file-upload` (inside `MagneticDrop`) | `components/ui/beui/file-upload` (already in `components/ui/SOURCES.md`) | MIT (© 2026 Saurabh Chauhan) |
| `Card`, `Button`, `Alert`, `Badge`, `Popover`, `Disclosure` / `Collapsible`, `Sheet` | `components/ui/*` (shadcn on Base UI) | MIT |
| motion v14 (`motion/react`), tokens from `@/lib/motion` | npm `motion` | MIT |
| lucide icons (`FileSpreadsheet`, `ListChecks`, `Grid3x3`, `Warehouse`, `Database`, `Users`, `CalendarDays`, `FileQuestion`, `Paperclip`) | npm `lucide-react` | ISC |

## 3. Users and goals

| Persona | Situation | What the router must do |
|---|---|---|
| **Fatih Bey, admin, ex-CRBS** ("doesn't know which type of file he has") | A department sent "Bahar_son.xlsx". He does not know whether it is the planning list, the weekly board or the exam list | Say what it is in his words, show the evidence he can check (the columns), name the term, and offer one button that opens the right import with the file and the term already set |
| **Planner** | Knows the file, wants speed. Drops the Güz board while Bahar is the current term | Same card, plus the **wrong-term warning** with the matching term pre-selected on the button |
| **Dr. A. T., academician** | Drops their own Outlook export (.ics), a list of room bookings they need for a seminar series, or the department's planning list | Their own routes: Profil › Takvim, Hızlı rezervasyon / Taleplerim, Derslerim. Never an import button. When nothing fits: "Bu dosya planlama ekibinin işi" with what they can do instead |
| **Staff without planning rights** (e.g. `setup.users` only, IT) | Drops a users CSV | Kullanıcılar › İçe aktar, prefilled |
| **Viewer** | Drops anything | "needs a planner" guidance |

Non-goals (v1): importing from the helper itself, multi-file routing beyond "open the setup wizard with all of them",
editing the file, merging files, an academician sending a file to the planner (open question 6).

## 4. Classifier (server, deterministic)

### 4.1 Pipeline (`app/ai/helper/files.py`, HB-23b)

```
bytes (≤ 15 MB, streamed, safe_files.read_upload)
  1 empty? → refused(file_empty)
  2 formats.precheck(name, data)              in run_isolated   → format or refused(file_type_unsupported / file_unsafe)
  3 kvkk_guard.check(data, name)              (test stacks)     → refused(kvkk_seed_workbook / kvkk_unmasked_names)
  4 signals (all in one run_isolated call, max_rows=200, first 3 sheets + all sheet titles):
      a  importers.detect.detect_kind(header rows 1..3 of sheet 1)          (xlsx/xlsm/xls/ods/csv via workbook_for)
      b  council.fastpath.detect_shape(rendered)
      c  council.structure.analyze(rendered)[:3]  → (kind, confidence) per sheet / unit
      d  users CSV: bookings_users.header_columns(first row)   (csv/txt only; Refusal = no signal)
      e  CRBS dump: text with "CREATE TABLE" / "INSERT INTO" naming ≥ 3 of
         {bookings, rooms, periods, weeks, sessions, users, schedules, holidays, departments}   (new, ~20 lines)
      f  ICS: format == ics → VEVENT count + first/last date (formats_ics, bounded expansion)
      g  intake-v1: JSON grid origin schema == smartsched.intake.v1
  5 candidates = rules §4.3 → sorted by score
  6 term guess: import_term_check.file_term(name, bytes) + term match against the person's active term (§4.4)
  7 warnings §4.5
  8 role filter: candidate → route table §4.2 → keep the routes whose permission the person holds;
     no route left → state needs_planner with the person's own alternatives
  9 stage (only if a primary route carries the file) §6.3 → upload_token
 10 build the card (cards.py style: server-built, Txt pairs, Plain only)
```

Budget: p95 ≤ 1.5 s for a 15 MB workbook on the 4-core host (header area only, read-only open). The client shows
"Dosya okunuyor…" after 400 ms (§9).

### 4.2 Kinds, routes and permissions

`kind` is a new `Name` enum on the wire. Labels are Turkish first.

| `kind` | Label TR / EN | Primary route (`feature_id` + params) | Permission (any of) | Academician / no-permission alternative |
|---|---|---|---|---|
| `planning_list` | Planlama listesi / Planning list | `import` `{kind: planning-list, term_id}`. **CSV / ODS / XLS:** `onboarding` (the wizard reads only Excel; the council's fast path reads the same importer through `workbook_for`) | `planning.edit` | `my_classes` "Derslerinizi SmartSched zaten biliyor: Derslerim" |
| `exam_list` | Sınav listesi / Exam list | `import` `{kind: exam-list, term_id}` (non-Excel → `onboarding`) | `planning.edit` | `my_classes` (exams tab when present), else guidance |
| `weekly_grid` | Haftalık derslik takvimi / Weekly room timetable | `import` `{kind: weekly-grid, term_id, year}` | `planning.edit` | `find_room` "Boş derslik bulmak için: Derslik bul" |
| `room_master` | Derslik ana listesi / Room master | `import` `{kind: room-master}` | `planning.edit`, `setup.rooms` | `find_room` |
| `users_csv` | Kullanıcı listesi / User list | `admin.users` `{import: 1}` (opens the import sheet) | `setup.users` | needs_planner (wording: "yönetici") |
| `crbs_dump` | classroombookings yedeği / classroombookings backup | `import` `{kind: crbs}` | `planning.edit` | needs_planner |
| `intake_json` | SmartSched içe aktarma dosyası / SmartSched import file | `onboarding` | `planning.edit` | needs_planner |
| `calendar_ics` | Takvim dosyası / Calendar file | planner: `onboarding` (the council turns VEVENTs into bookings) | `planning.edit` | **`profile.calendar`** (for everyone): "SmartSched dışarıdan takvim okumaz; derslerinizi takviminize buradan eklersiniz." Secondary `reserve` |
| `request_list` | Ders talep listesi / Course request list (council `request_list` that is not the importer shape, e.g. English columns) | `onboarding` | `planning.edit` | academician whose rows have room + date + time: `reserve` "Tek tek ayırmak için: Hızlı rezervasyon" + secondary `my_requests` |
| `timetable_other` | Çizelge (farklı düzen) / Timetable (other layout) (council `timetable_grid` without the importer shape, e.g. transposed) | `onboarding` | `planning.edit` | `find_room` |
| `room_list` | Derslik listesi / Room list (council `room_list`, not the master shape) | `onboarding` | `planning.edit`, `setup.rooms` | `find_room` |
| `holidays` | Tatil ve akademik takvim / Holidays and calendar (council `calendar`) | `onboarding`. Secondary `admin.holidays` (by hand) | `planning.edit` (+ `setup.*` for the secondary, per the index entry) | needs_planner |
| `staff_list` | Personel listesi / Staff list | `admin.users` `{import: 1}` when a users header is found, else `onboarding` | `setup.users` / `planning.edit` | needs_planner |
| `rules_doc` | Kurallar ve tercihler / Rules and preferences (docx, txt, eml, pdf text) | `onboarding` | `planning.edit` | needs_planner |
| `scan` | Tarama ya da görüntü / Scan or image | `onboarding` with the AI-off warning when `vision` is off | `planning.edit` | needs_planner |
| `unknown` | — | none (guidance, §5) | — | same |

Permissions are checked on the server with the person's `Access` (`access.perms`, the same keys as
`require_permission`). The client double-checks with `usePermissions()` and `feature-links.ts` (helper.md §3.1).

### 4.3 Scoring and agreement rules (deterministic, unit-tested)

| Rule | Score |
|---|---|
| `detect_kind` **and** `detect_shape` agree on an importer shape | 0.95 (**Eminim** / sure) |
| `detect_shape` alone (stricter) | 0.90 (sure) |
| `detect_kind` says `weekly-grid` but `detect_shape` and the council say a timetable without the importer axis | `timetable_other` 0.80 (**Büyük olasılıkla** / likely); `weekly_grid` is dropped (it would fail in the importer) |
| `detect_kind` alone, `detect_shape` disagrees on another importer shape | both kept: 0.70 / 0.65 → ambiguous |
| users header (`header_columns` finds username or e-mail + ≥ 1 more) | 0.90 |
| CRBS: ≥ 5 table names | 0.95; 3–4 table names: 0.75 |
| ICS / intake-v1 | 0.98 (format proves it) |
| council kind only | `confidence × 0.85` (so 0.90 → 0.77, likely) |
| Several sheets disagree | the first sheet that has a signal wins; other sheets add one evidence line ("Sayfa2: derslik listesi") |

- **Bands:** ≥ 0.85 sure · 0.60–0.85 likely · < 0.60 unsure. The number is never shown. It goes to telemetry
  (`helper.files.classified`, no content).
- **Ambiguous** when the top two candidates both score ≥ 0.50 and are within 0.15 of each other, or when the top
  candidate is unsure but ≥ 0.40. **Unknown** when nothing reaches 0.40.
- The extension never decides alone (council rule). The **file name never decides the kind** ("final_planlama_listesi" is
  an exam list by its columns). The name only feeds the term guess.

### 4.4 Term guess

1. `file_term(name, bytes)` gives `(season, year, source)` from the file name, else the sheet titles (FALL / SPRING /
   SUMMER / FINAL …, `term_match.py`).
2. It is matched against the terms the person can see. The same season and year (or the season alone) gives the
   newest such term, which becomes the `term_id` param.
3. `matches_active` compares it with the person's active term (`useActiveTerm`). A mismatch gives the warning
   `term_mismatch`, and the **button carries the file's term**, not the active one ("Güz 2026-2027 dönemine içe aktar").
   The page still shows its own `term_check` above the counts (PER-F04). Nothing changes there.
4. When there is no season in the name or the sheets: `term_unknown` (info). The button carries the active term, and the
   target page asks as today.
5. `weekly_grid` also needs `year`: it comes from the term guess, else the active term's year.

### 4.5 Warnings (≤ 4 per card, in this order)

| `code` | When | Status | TR | EN |
|---|---|---|---|---|
| `term_mismatch` | the file's term differs from the active term | warn | Dosya {dosya_dönemi} diyor; şu an {etkin_dönem} seçili. Düğme dosyanın dönemine aktarır. | The file says {file_term}; {active_term} is selected now. The button imports into the file's term. |
| `term_unknown` | no season found | info | Dosya hangi döneme ait olduğunu söylemiyor. İçe aktarırken dönemi siz seçeceksiniz. | The file doesn't say which term it is for. You'll choose the term when importing. |
| `term_locked` | `term_lock` held for the target term | warn | {dönem} dönemine şu anda başka bir içe aktarma yazıyor. Önizleme açılır; uygulama işlem bitince yapılır. | Another import is writing {term} right now. The preview opens; applying waits until it finishes. |
| `needs_excel` | importer shape in CSV / ODS / XLS | info | İçe aktarma ekranı yalnızca Excel (.xlsx) okur. Bu dosya Kurulum sihirbazında aynı kurallarla okunur. | The import screen reads Excel (.xlsx) only. The setup wizard reads this file with the same rules. |
| `scan_ai_off` | `scan` / pdf without tables and `ai_allowed(vision)` false | warn | Taranmış sayfalar yapay zekâ olmadan okunamaz; yalnızca tablolar okunur. Yönetici Ayarlar › Yapay zekâ'dan açabilir. | Scanned pages can't be read without AI; only tables are read. An admin can turn it on in Settings › AI. |
| `too_large_for_target` | users CSV > 5 MB (the endpoint's own cap) | bad | Kullanıcı listesi en çok 5 MB olabilir; dosya {boyut}. Listeyi bölün. | A user list can be at most 5 MB; this file is {size}. Split the list. |
| `many_sheets` | > 1 sheet with different kinds | info | Dosyada {n} sayfa var; ilk sayfa "{sayfa}" okundu. | The file has {n} sheets; the first sheet "{sheet}" was read. |

The KVKK guard and the size cap are **refusals**, not warnings (§5 refused). Sheet names are passed through `scrub()`
and cut to 40 characters.

### 4.6 Optional model tie-breaker (off by default)

- It runs only when **all** of these hold: the state is ambiguous; `ai_allowed(session, "intake")` is true (the council AI
  switch with its KVKK sign-off); the helper is routed to a model (`mode: ai`); the person holds `planning.edit`; and the
  person is under their limit.
- **It sends only the canonical column labels the detectors matched, plus the sheet titles**, after `personal.py`
  masking. It never sends cell values or raw header text.
- The model can only **re-order the existing candidates**. It cannot add a kind, a route or a param. Its answer is
  validated against the candidate list, and anything else is dropped.
- The card shows the caption "Yapay zekâ ile sıralandı" under the chooser. Usage is counted under the `helper` feature.
- Recommendation: ship it behind `ai.helper.file_tiebreak` = false (open question 3).

## 5. States, copy and layout of each

Each state has **one primary**, or none for refused and error, which offer "Başka dosya seç" as their only action. Keys
are `helper.file.*`. TR comes first. Style as helper.md §6.3: formal "siz", ≤ 20 words per sentence, no exclamation
marks, no emoji.

| State | Trigger | Shows | Primary | Secondary (≤ 2) | Disclosure |
|---|---|---|---|---|---|
| **dragging** | an OS file (`dataTransfer.types` includes `Files`) enters the sheet or the page | inset 2 px `--tint` outline + `--tint-soft` fill on the sheet log (or the page edge), one line | — | — | — |
| **reading** | file received | user bubble with the file chip (name · size); status line | — (a "Vazgeç" text button) | — | — |
| **detected** | top candidate sure or likely, with a route | `file` card: icon + kind label + certainty word; evidence line(s); term line; warnings | **route button** (server label) | "Başka bir tür seç" · "Kurulum sihirbazında aç" (when the person holds `planning.edit` and the primary is not already `onboarding`) | "Bu dosya nedir?" |
| **ambiguous** | §4.3 | `choice` card: question + 2–3 candidates, each with what it would do (`hint`) | — (picking a row is the action) | "Kurulum sihirbazında aç" | — |
| **unknown** | nothing ≥ 0.40 | `file` card, state `unknown`: what was read + examples of each accepted file | "Örnek dosyaları gör" (opens the templates list, §6.6) | "Kurulum sihirbazında aç" (planner) | "Hangi dosyaları tanıyorum?" (open by default) |
| **needs_planner** | detected, but no route for this person | `file` card, state `needs_planner` | the person's best alternative (e.g. "Derslerim'i aç"), else none | ≤ 1 more alternative | "Bu dosya nedir?" |
| **refused** | empty, type, size, KVKK guard, rate limit | `refusal` card with `code` + message | "Başka dosya seç" | — | — |
| **error** | read failure, network, 5xx | `error` card | "Tekrar dene" (re-sends the same File object) | "Başka dosya seç" | — |
| **expired** | the token is older than 10 minutes when the button is pressed (or on the target page) | inline line in the card / page | "Dosyayı yeniden oku" (re-classifies the same File if the browser still holds it, else opens the picker) | — | — |

### 5.1 Copy (TR / EN)

| Key | TR | EN |
|---|---|---|
| `helper.file.attach` | Dosya ekle | Attach a file |
| `helper.file.dropHere` | Dosyayı buraya bırakın. Ne olduğunu ve ne yapacağınızı söyleyeyim. | Drop the file here. I'll tell you what it is and what to do next. |
| `helper.file.dropPage` | Yardımcıya bırakın: ne olduğunu söyleyeyim | Drop it on the helper: I'll tell you what it is |
| `helper.file.formats` | Excel, CSV, ICS, SQL, JSON, Word, PDF, görüntü · en çok {mb} MB | Excel, CSV, ICS, SQL, JSON, Word, PDF, image · up to {mb} MB |
| `helper.file.privacy` | Dosya yalnızca okunur. Siz onaylayana kadar hiçbir şey kaydedilmez. | The file is only read. Nothing is saved until you confirm. |
| `helper.file.reading` | Dosya okunuyor… | Reading the file… |
| `helper.file.cancel` | Vazgeç | Cancel |
| `helper.file.sure` | Eminim | Sure |
| `helper.file.likely` | Büyük olasılıkla | Most likely |
| `helper.file.unsure` | Emin değilim | Not sure |
| `helper.file.title` | Bu bir {tür} | This is a {kind} |
| `helper.file.titleLikely` | Bu büyük olasılıkla bir {tür} | This is most likely a {kind} |
| `helper.file.evidence.columns` | Sütunlar: {sütunlar} → {tür} | Columns: {columns} → {kind} |
| `helper.file.evidence.grid` | {n} sayfa, her biri bir hafta ("{ilk_sayfa}"); üstte gün adları, solda ders saatleri, {m} derslik | {n} sheets, one per week ("{first_sheet}"); day names on top, periods on the left, {m} rooms |
| `helper.file.evidence.transposed` | Saatler üstte, derslikler solda: yan çevrilmiş bir çizelge | Times across the top, rooms down the side: a transposed timetable |
| `helper.file.evidence.ics` | Takvim dosyası: {n} etkinlik, {ilk} – {son} | Calendar file: {n} events, {first} – {last} |
| `helper.file.evidence.sql` | Veritabanı dökümü; tablolar: {tablolar} → classroombookings | Database dump; tables: {tables} → classroombookings |
| `helper.file.evidence.users` | Sütunlar: {sütunlar} → kullanıcı listesi. Satırlar gösterilmez. | Columns: {columns} → user list. Rows are not shown. |
| `helper.file.evidence.intake` | SmartSched içe aktarma biçimi ({şema}) | SmartSched import format ({schema}) |
| `helper.file.evidence.english` | Sütun adları İngilizce; Kurulum sihirbazı onları eşleştirir | The column names are English; the setup wizard maps them |
| `helper.file.term` | Dönem: {dönem} (dosya adından) / (sayfa adından) | Term: {term} (from the file name) / (from the sheet name) |
| `helper.file.route.planning` | Planlama listesi olarak içe aktar | Import as planning list |
| `helper.file.route.planningTerm` | {dönem} dönemine planlama listesi olarak aktar | Import into {term} as planning list |
| `helper.file.route.exam` | Sınav listesi olarak içe aktar | Import as exam list |
| `helper.file.route.grid` | Haftalık derslik takvimi olarak içe aktar | Import as weekly room timetable |
| `helper.file.route.roomMaster` | Derslik ana listesi olarak içe aktar | Import as room master |
| `helper.file.route.users` | Kullanıcıları içe aktar | Import users |
| `helper.file.route.crbs` | classroombookings verisini aktar | Import classroombookings data |
| `helper.file.route.onboarding` | Kurulum sihirbazında aç | Open in the setup wizard |
| `helper.file.route.calendar` | Takvimime ekle | Add to my calendar |
| `helper.file.route.myClasses` | Derslerim'i aç | Open My classes |
| `helper.file.route.reserve` | Hızlı rezervasyonu aç | Open Quick reserve |
| `helper.file.route.myRequests` | Taleplerim'i aç | Open My requests |
| `helper.file.route.findRoom` | Derslik bul'u aç | Open Find a room |
| `helper.file.other` | Başka bir tür seç | Choose another type |
| `helper.file.what` | Bu dosya nedir? | What is this file? |
| `helper.file.chooser.q` | Bu dosya hangisi? | Which one is this file? |
| `helper.file.chooser.hint.planning` | Derslerin gün, saat ve derslik talepleri dönemin planına eklenir | Adds each course's day, time and room request to the term's plan |
| `helper.file.chooser.hint.exam` | Sınav tarihleri ve salon talepleri sınav dönemine eklenir | Adds exam dates and room requests to the exam period |
| `helper.file.chooser.hint.grid` | Haftalık derslik doluluğu (pano) yüklenir | Loads the weekly room occupancy board |
| `helper.file.chooser.hint.roomMaster` | Derslik kapasiteleri ve özellikleri güncellenir | Updates room capacities and features |
| `helper.file.chooser.hint.onboarding` | Sihirbaz dosyayı okur ve ne bulduğunu size sorar | The wizard reads the file and asks you about what it found |
| `helper.file.unknown` | Bu dosyayı tanıyamadım. {biçim} biçiminde, ama tanıdığım sütunlar yok. | I couldn't recognise this file. It is {format}, but I found no columns I know. |
| `helper.file.unknown.list` | Tanıdığım dosyalar: planlama listesi, sınav listesi, haftalık derslik takvimi, derslik ana listesi, kullanıcı listesi, classroombookings yedeği, takvim (.ics). | Files I recognise: planning list, exam list, weekly room timetable, room master, user list, classroombookings backup, calendar (.ics). |
| `helper.file.examples` | Örnek dosyaları gör | See example files |
| `helper.file.needsPlanner` | Bu dosya bir {tür}. Bunu planlama ekibi içe aktarır. Sizin için: | This file is a {kind}. The planning team imports it. For you: |
| `helper.file.needsPlanner.none` | Bu dosya bir {tür}. Bunu planlama ekibi içe aktarır; dosyayı bölüm planlamacınıza gönderebilirsiniz. | This file is a {kind}. The planning team imports it; you can send it to your department's planner. |
| `helper.file.icsAcademic` | SmartSched dışarıdan takvim okumaz. Derslerinizi ve rezervasyonlarınızı takviminize buradan eklersiniz. | SmartSched doesn't read outside calendars. You add your classes and bookings to your calendar from here. |
| `helper.file.myClasses` | Derslerinizi SmartSched zaten biliyor; dosyayı yüklemenize gerek yok. | SmartSched already knows your classes; you don't need to upload the file. |
| `helper.file.refused.empty` | Dosya boş. | The file is empty. |
| `helper.file.refused.type` | Bu tür dosyayı okuyamıyorum ({uzantı}). | I can't read this type of file ({ext}). |
| `helper.file.refused.size` | Dosya {boyut}; en çok {mb} MB okuyabilirim. | The file is {size}; I can read up to {mb} MB. |
| `helper.file.refused.rate` | Çok sayıda dosya okundu. Bir dakika sonra yeniden deneyin. | Too many files were read. Try again in a minute. |
| `helper.file.refused.kvkk` | (server `message_tr` of `kvkk_guard`, unchanged) | (server `message_en`) |
| `helper.file.error` | Dosya okunamadı. Tekrar deneyin ya da başka bir dosya seçin. | The file couldn't be read. Try again or choose another file. |
| `helper.file.retry` | Tekrar dene | Try again |
| `helper.file.another` | Başka dosya seç | Choose another file |
| `helper.file.expired` | Dosyanın süresi doldu (10 dakika). Yeniden okuyun. | The file expired (10 minutes). Read it again. |
| `helper.file.reread` | Dosyayı yeniden oku | Read the file again |
| `helper.file.many` | {n} dosya bıraktınız. Birden çok dosyayı Kurulum sihirbazı birlikte okur. | You dropped {n} files. The setup wizard reads several files together. |
| `helper.file.handed` | Yardımcıdan geldi | From the helper |
| `helper.file.remove` | Dosyayı kaldır | Remove the file |
| `helper.file.aiSorted` | Yapay zekâ ile sıralandı | Sorted with AI |

"Bu dosya nedir?" body, per kind (TR / EN; 2–3 sentences each, `explain: Texts` on the wire). Example for
`planning_list`: "Planlama listesi, bölümlerin her dersi için gün, saat, şube, öğretim elemanı ve derslik talebini
yazdığı tablodur. İçe aktarınca önce bir önizleme görürsünüz; hiçbir şey 'Uygula' demeden değişmez." / "A planning list
is the table where departments write each course's day, time, section, instructor and room request. Importing shows a
preview first; nothing changes until you press Apply." The builder writes the others in the same pattern for each kind
of §4.2 (copy review in the design checklist, §11.3).

### 5.2 Evidence rules (KVKK)

- Evidence uses the **canonical labels** of the fields the detectors matched (`HEADER_SPEC` keys →
  `detect.COLUMN_LABELS`, extended to every key the router names: "Ders Kodu", "Şube", "Dersin Günü", "Başlangıç",
  "Bitiş", "1. Öğretim Elemanı", "Sınav Tarihi", "Kesinleşen Derslik", "code", "capacity", "Kullanıcı adı", "E-posta",
  "Rol" …). **It never uses the raw header text.** The fixture's header "Kesinleşen Derslik (Sadece Derslik Planlama
  Fatih Bey doldurmalıdır)" names a person, and must show as "Kesinleşen Derslik".
- **No cell value ever leaves the server in a classify response.** Counts, dates (ICS first and last day) and CRBS table
  names are allowed. Sheet titles go through `scrub()`, are cut to 40 characters, and are dropped when
  `kvkk_guard.unmasked_hits` (with the names file) or `personal.py` finds a name in them.
- At most 6 labels per line, then "+{n}".
- The file name is shown **from the browser's File object**. The server does not echo it in the card. The audit row stores
  the extension, size and the first 12 characters of the SHA-256, never the name.

## 6. API contract (HB-23b)

### 6.1 `POST /helper/files/classify`

- **Auth:** a signed-in user with the helper available (`ai.helper` not disabled for the audience). Rate limit §1.3.
- **Request:** `multipart/form-data`:
  - `file` (exactly one);
  - `context` (optional `feature_id` of the page it was dropped on, e.g. `import`; used only to order the secondary
    buttons);
  - `lang` (`tr` | `en`, for logs only; cards carry both).
- **Response 200** (every classified outcome, including unknown and refused, so the sheet renders a card):

```json
{
  "card": { "...": "FileCard | ChoiceCard | RefusalCard | ErrorCard (helper.card.v1)" },
  "stage": { "upload_token": "…", "expires_at": "2026-10-18T16:42:00Z", "size": 1234567, "format": "xlsx" }
}
```

  `stage` is absent when no route carries the file (unknown, refused, needs_planner with no file route).
- **413** only when the stream exceeds the hard cap before a card can be built. The client pre-checks `file.size` and
  shows the refused card itself without uploading.
- **Persistence: none.**
  - No `ImportJob`, `CouncilJob` or `helper_messages` row is written, and no audit row either.
  - No plain bytes on persistent disk. The only artefact is the encrypted stage (§6.3). (Starlette spools uploads
    larger than 1 MiB to `/tmp`; the backend container mounts `/tmp` as tmpfs, `deploy/docker-compose.yml`.)
  - Telemetry `helper.files.classified {kind, band, format, ms, state}` carries no content.

### 6.2 `POST /helper/files/route` (chooser pick and "Başka bir tür seç")

- `{"upload_token": "…", "kind": "exam_list"}` → `{"card": FileCard}` for that kind.
- The server re-reads the staged bytes and re-runs the steps from §4.1 step 6, with `kind` forced, so the term,
  warnings and permission check are those of the chosen kind.
- A kind outside the person's allowed list → 403 `RefusalCard` (`code: kind_not_allowed`).
- The token stays valid; this does not consume it.
- "Başka bir tür seç" without a token (unknown state) opens the client-side list of kinds the person may import, as a
  `choice` card built on the client from `feature-links` (no server call).

### 6.3 Stage and `upload_token`

- **Storage:**
  - `${UPLOAD_DIR}/helper-stage/<stage_id>.bin`, mode 0600, outside the backup set;
  - the bytes are encrypted with AES-256-GCM under a **random per-stage key that is only in the token**;
  - the server keeps no copy of the key, so an expired or leaked file is unreadable (crypto-shredding).
- **Token:** `base64url(payload).base64url(hmac)`, signed like `confirm.py`, with its own label `helper-file`.
  `payload = {sid, uid, sess, sha256, size, fmt, kinds[], key, exp}`:
  - `exp` = issued + 10 min;
  - `sess` = the auth session id, so a revoked session kills the token;
  - `kinds` = the candidate kinds the person may route to.
- **Rules:**
  - **owner-bound:** the token's `uid` and `sess` must equal the caller's, else 403;
  - **once:** the first consume atomically renames the stage file to `.claimed`, so a second consume gets 410
    `stage_used`;
  - **expiry:** after 10 minutes, consume returns 410 `stage_expired`; a sweeper (every minute, and at start-up)
    deletes any stage older than 10 minutes;
  - **cancel:** `DELETE /helper/files/{sid}` (the card's ✕, "Vazgeç", sheet close) deletes the stage at once;
  - **one stage per person:** a new classify deletes the person's previous stage.
- **Where the token lives on the client:**
  - the `helper-store` `fileHandoff` slot, mirrored to `sessionStorage` so a reload keeps it;
  - **never** in the URL, the history, logs or `localStorage`;
  - the URL only says `from=helper`.

### 6.4 `POST /helper/files/handoff` (the card's button: the routed action's confirm)

- `{"upload_token": "…", "kind": "planning_list", "feature_id": "import", "params": {"term_id": 12}}` →
  `{"ok": true, "href_params": {...}}`.
- The server re-checks the token, the permission for `feature_id` and the params (`term_id` must be a term the person can
  see; `kind` ∈ `kinds`). It then writes the **audit row** `helper.file.handoff` with
  `{kind, feature_id, term_id, ext, size, sha12, via: "helper"}`. Only an `isTrusted` activation calls it (helper.md
  §4.1 rule 4).
- It does not consume the token. The target page does.

### 6.5 Target pages accept a handed-over file

Backend (one optional form field each, exactly one of `file` / `upload_token`):

| Endpoint | New field | Behaviour |
|---|---|---|
| `POST /imports/planning-list`, `/exam-list`, `/weekly-grid`, `/room-master` | `upload_token: str \| None = Form(None)` | `helper_files.consume(token, access)` → `(ext, bytes)` → written to `import_jobs.file_target` → the **same** `safe_files.precheck_upload` + `kvkk_guard.check` → job `summary.source = "helper"`. The file name stored is `helper-<sha12>.<ext>` unless the client sends `filename` (the browser's name, which the page already shows today) |
| `POST /imports/crbs` | `upload_tokens: list[str]` | same, per dump |
| `POST /council/jobs` | `upload_tokens: list[str]` | each token becomes one admitted file (`admit()` runs unchanged) |
| `POST /users/import` | `upload_token` | same 5 MB cap, then `import_users_csv` |

Frontend (`fileHandoffHref` in `handover-links.ts`):

| `feature_id` | Href | Page behaviour |
|---|---|---|
| `import` | `/import?kind=<importer-kind>&term=<id>&year=<y>&from=helper` | `ImportWizard` reads `term` (new) and `from=helper`. It shows the **handed-over file row** (icon · name · size · chip "Yardımcıdan geldi" · ✕ "Dosyayı kaldır") in place of the empty drop zone, and focuses the page's own primary ("Önizle"). The upload sends `upload_token`. Progress shows "Sunucuda okunuyor" directly (no bytes to send) |
| `onboarding` | `/onboarding?from=helper` | `FileDrop` lists the file as row 1 with the chip. The start button keeps its own label ("Başlat · 1 dosya" / "YZ ile oku ve başlat") |
| `admin.users` | `/admin/users?import=1&from=helper` | opens the import sheet with the file row. Role, department and password stay the page's defaults |
| `profile.calendar`, `my_classes`, `my_requests`, `reserve`, `find_room` | their plain routes (`profile.calendar` uses `/profile?calendar=1`) | no file is carried; the stage is deleted on navigation |

- **Expired or used token on the target page:** the row turns into "Dosyanın süresi doldu (10 dakika). Yeniden seçin."
  The page's drop zone comes back with the kind and term kept, and focus moves to the zone's button.
- **The person removes the file (✕):** `DELETE /helper/files/{sid}`, and the page returns to its normal empty step.

### 6.5a As built (HB-23b, 2026-10-18): API notes where the build differs from or adds to §6.1–§6.6

Everything above holds unless listed here. All additions are optional and backward compatible.

- **Classify form fields:** besides `file`, `context`, `lang`: `term_id` (optional; the page's active term from
  `useActiveTerm`, else the server's current term decides `matches_active`) and `kind` (optional; a forced kind, used
  for the chooser pick when nothing is staged).
- **`resend: true`** in the classify answer when a route carries the file but nothing was staged
  (`HELPER_FILE_STAGE=off`, no sign-in session to bind to, or several files). The target page then sends the File
  object the browser still holds; the chooser pick re-sends the file to classify with `kind`.
- **Several files** (owner decision 4, then the KVKK review item 16): one `file` card, title `helper.file.many`,
  `format: "mixed"`, evidence "1. dosya: Planlama listesi" per file (≤ 4), primary `onboarding` with
  `carries_file: true`, **no stage** and `resend: true`: the wizard uploads the File objects itself. People without
  `planning.edit` get the first file's card. An unreadable file adds the warning `file_skipped` (bad).
- **Extra warning codes:** `ics_academic` (info, the `icsAcademic` text, academician + `.ics`), `my_classes_known`
  (info, the `myClasses` text, academician + planning / exam list), `file_skipped` (several files). The term warnings
  (`term_mismatch`, `term_unknown`, `term_locked`) only appear when the primary imports into a term.
- **`FileRoute.label_short`** (§8.5) is sent for "{term} dönemine aktar" when it fits 28 characters.
- **`profile.calendar`** routes carry `params: {calendar: 1}`; `admin.holidays` ("Tatilleri elle ekle") is the
  holidays secondary.
- **Chooser:** the `onboarding` row has `value: "onboarding"`; `/route` with `kind: "onboarding"` answers a `file` card
  with `kind` absent and primary `onboarding`. The token's `kinds` are the routable candidates plus `onboarding` for
  planners; the unknown card's wizard route uses `kind` absent (= `onboarding`) on `/handoff`.
- **Unknown state** keeps "Kurulum sihirbazında aç" for planners as a secondary that **carries** the file, so a stage
  exists for planners there.
- **`/handoff`** body: `upload_token`, optional `kind` (absent = `onboarding`), `feature_id`, `params` (`kind`,
  `term_id`, `year`). It answers `{ok: true, href_params: {kind?, term_id?, year?, import?}}`. 403
  `route_not_allowed` (a page this kind is not routed to for this person), 403 `kind_not_allowed`, 422 `bad_term` /
  `bad_year`. The audit row is `helper.file.handoff` on entity `helper_file` / sha12 with
  `{kind, feature_id, term_id, ext, size, sha12, files, via: "helper"}`.
- **Stage errors** (on `/route`, `/handoff` and every target endpoint): 403 `stage_bad_token` / `stage_other_user`,
  410 `stage_expired` / `stage_used`, in the project's `{code, message_tr, message_en}` shape (the helper routes add
  `card`). Target endpoints check the token first and **consume it only after their own checks pass** (a refused
  role, a locked term or a bad form leaves the file usable).
- **Target endpoints:** `/imports/planning-list`, `/exam-list`, `/weekly-grid`, `/room-master` take `upload_token` +
  optional `filename`; exactly one of `file` / `upload_token`, else 422 `file_or_token`. `/imports/crbs` takes
  `upload_tokens`. `/council/jobs` takes `upload_tokens` + optional parallel `upload_names`. `/users/import` takes
  `upload_token`. The stored name is the browser's `filename` when its extension matches, else `helper-<sha12>.<ext>`.
- **Stage crypto:** the AES-256-GCM key is HKDF(token key, salt = stage id, info = HMAC(APP_SECRET,
  "helper-file-kek")); the claim is an exclusive `.used` tombstone written before the rename. Sign-out and KVKK
  erasure delete the person's stages. Classify telemetry is a log line (`helper.files.classified`), not a row.
- **Permissions:** the room-master import route is offered on `planning.edit` **or** `setup.rooms` (the endpoint's
  own rule), although the `import` index entry lists `planning.edit` only: the client's double-check must use the
  route, not the index entry, for `{kind: room-master}`. The setup wizard always needs `planning.edit`.
- **Sheet titles** on a card (grid evidence, `many_sheets`, "Sayfa2: …") only when every word is a week / term / day
  / month / sheet word and, for more than one word, the title holds a number (KVKK review C1).
- **Rate limit** 20 / minute, 200 / day per person **per process** (accepted).
- **Templates:** header-only (owner decision), for `planning_list` and `exam_list` (.xlsx, from `HEADER_SPEC` through
  `detect.COLUMN_LABELS`), `room_master` (.csv, `room_master.COLUMNS`) and `users_csv` (.csv, Turkish header words).
  `GET /helper/files/examples` → `[{kind, format, file_name, label, description, permission}]`; no weekly-grid or ICS
  template in v1.
- **Evidence grid count:** `{m}` is the number of distinct rooms (the board repeats each room under all 7 day columns).

### 6.6 Templates ("Örnek dosyaları gör")

- **There are no downloadable templates today**, except the room master's "Şablonu indirin" in the bulk room flow.
  HB-23b adds `GET /helper/files/examples` (a list) and `GET /helper/files/examples/{kind}.{xlsx|csv|ics}`.
  - Each example is generated from the importer's `HEADER_SPEC` (header row + 2 example rows with codes and initials,
    e.g. "Dr. A. T.").
  - No real names. The examples are static, with no database read.
- The unknown card lists each kind with one line and an "İndir" text button (44 px).

## 7. Card contract

### 7.1 Reused types

- **Ambiguous:** `ChoiceCard`:
  - `action: "classify_file"`, `arg: "kind"`, `question` = `helper.file.chooser.q`;
  - `options[]` = `{value: kind, label: kind label, hint: what it would do}` (2–3 options, plus an
    `onboarding` row for planners);
  - `args: {upload_token}`.
  - Picking an option calls `POST /helper/files/route`. **The `upload_token` in `args` is the one exception to "no
    secrets in cards"**, so this card is ephemeral (§7.3).
- **Refused:** `RefusalCard` with `code` ∈ `file_empty`, `file_type_unsupported`, `file_unsafe`, `file_too_large`,
  `kvkk_seed_workbook`, `kvkk_unmasked_names`, `rate_limited`, `kind_not_allowed`; `fallback` = ≤ 2 `nav` cards (e.g.
  `import`, `onboarding` for planners).
- **Error:** `ErrorCard` `code: file_read_failed`.

### 7.2 New wire type `file` (add to `schema.py`, `CARD_TYPES`, the JSON Schema snapshot, and `schema.gen.ts`)

```python
class FileWarning(_Strict):
    code: Annotated[str, Field(pattern=r"^[a-z_]{2,48}$")]
    message: Txt
    status: Literal["info", "warn", "bad"] = "info"

class FileRoute(_Strict):
    """A hand-over to a page's own flow. The client maps feature_id → href (handover-links.fileHandoffHref)."""
    feature_id: Name                     # import | onboarding | admin.users | profile.calendar | my_classes | …
    params: dict[Name, Scalar] = Field(default_factory=dict)   # kind, term_id, year, import
    label: Txt                           # server-built: "Güz 2026-2027 dönemine planlama listesi olarak aktar"
    carries_file: bool                   # true → the client calls /helper/files/handoff, then navigates

class FileTerm(_Strict):
    term_id: int | None
    name: Txt                            # "Güz 2026-2027"
    source: Literal["file_name", "sheet_title"]
    matches_active: bool

class FileCard(CardBase):
    type: Literal["file"] = "file"
    action: Literal["classify_file"] = "classify_file"
    state: Literal["detected", "unknown", "needs_planner"]
    kind: Name | None = None
    kind_label: Txt | None = None
    certainty: Literal["sure", "likely", "unsure"] | None = None
    format: Name                         # xlsx | csv | ics | sql | …
    evidence: Texts = Field(default_factory=Texts)           # ≤ 4 lines each language (§5.2)
    term: FileTerm | None = None
    warnings: list[FileWarning] = Field(default_factory=list, max_length=4)
    primary: FileRoute | None = None
    secondary: list[FileRoute] = Field(default_factory=list, max_length=2)
    explain: Texts = Field(default_factory=Texts)            # "Bu dosya nedir?" / unknown: accepted kinds
    examples: list[Name] = Field(default_factory=list, max_length=8)   # kinds with a template (unknown state)
    ai_sorted: bool = False
```

`title` (from `CardBase`) holds `helper.file.title` / `titleLikely` / `needsPlanner`, filled in by the server. Every
string is `Plain`. No URL, file name or cell value is allowed (§5.2).

### 7.3 Ephemeral cards

- File cards are **not** written to `helper_messages`. Classify is its own endpoint, not a `/helper/turn`.
- The client inserts the user bubble (file chip) and the card into the visible log, flagged `ephemeral: true`. They are
  gone on another device and after "Yeni konuşma".
- A typed question after a file card goes to `/helper/turn` with **no file content**. It sends only a context hint
  `{"file_kind": "planning_list"}` (an extension of the HB-D `context` field; until then nothing is sent). So the model
  can answer "Bu ne demek?" without seeing the file.
- **Thread rule:** at most one live file card. A new file collapses the previous one to a line ("Planlama listesi ·
  süresi doldu") and deletes its stage.

## 8. UI

### 8.1 Desktop helper sheet (≥ 1024, 400 / 360 px side sheet, non-modal)

```
┌ Yardımcı                         [Yerel model ▾] ⋯ ✕ ┐
│                                                       │
│                       ┌─────────────────────────────┐ │  user bubble: file chip
│                       │ ▤ Bahar_son.xlsx · 1,2 MB   │ │
│                       └─────────────────────────────┘ │
│ ┌───────────────────────────────────────────────────┐ │  file card (--fill-3 well, radius-md, pad 16)
│ │ ▤  Bu bir planlama listesi            ● Eminim     │ │  title type-headline · certainty Badge
│ │ Sütunlar: Ders Kodu, Şube, Dersin Günü, Başlangıç, │ │  type-callout, label-2
│ │ Bitiş, 1. Öğretim Elemanı → Planlama listesi       │ │
│ │ Dönem: Bahar 2026 (dosya adından)                  │ │  type-footnote
│ │ ⚠ Dosya Bahar 2026 diyor; şu an Güz 2026-2027      │ │  warning row (status-warning icon + text)
│ │   seçili. Düğme dosyanın dönemine aktarır.         │ │
│ │ ┌───────────────────────────────────────────────┐ │ │
│ │ │ Bahar 2026 dönemine planlama listesi olarak    │ │ │  PRIMARY (48 px phone / 40 px desktop, full width)
│ │ │ aktar                                          │ │ │
│ │ └───────────────────────────────────────────────┘ │ │
│ │ Başka bir tür seç · Kurulum sihirbazında aç        │ │  two text buttons (44 px hit area)
│ │ ▸ Bu dosya nedir?                                  │ │  disclosure, collapsed
│ │ Dosya yalnızca okundu; onaylayana kadar kaydedilmez│ │  type-caption label-3
│ └───────────────────────────────────────────────────┘ │
│ ─────────────────────────────────────────────────────  │
│ [AiUsageBanner]                                        │
│ [📎] Bir şey sorun ya da dosya bırakın…          [➤] │  composer: 📎 = "Dosya ekle" (IconButton 44)
└───────────────────────────────────────────────────────┘
```

- **Dragging** over the sheet: the log area shows an inset 2 px `--tint` outline + `--tint-soft` fill and a centred line
  `helper.file.dropHere` + `helper.file.formats` + `helper.file.privacy`. The composer stays visible.
- **Reading:** the status line "Dosya okunuyor…" (shimmer label only after 400 ms) + "Vazgeç".
- In **Rehber modu** (AI off, helper.md §5.3), the guide-mode search field gets the same 📎 button, and drops work
  the same. The router never needs AI.

### 8.2 Phone (390 × 844, touch; full-screen sheet)

```
┌──────────────────────────────┐
│ ✕   Yardımcı   [Kapalı] ⋯    │  56 px header
│                              │
│        ┌──────────────────┐  │
│        │ ▤ Bahar_son.xlsx │  │
│        └──────────────────┘  │
│ ┌──────────────────────────┐ │  card full width, pad 16
│ │ ▤ Bu bir planlama listesi│ │
│ │ ● Eminim                 │ │  certainty wraps under the title
│ │ Sütunlar: Ders Kodu, Şube│ │
│ │ , Dersin Günü +3         │ │  ≤ 3 labels then "+n" on phones
│ │ Dönem: Bahar 2026        │ │
│ │ ⚠ Şu an Güz 2026-2027    │ │
│ │   seçili. Düğme dosyanın │ │
│ │   dönemine aktarır.      │ │
│ │ ┌──────────────────────┐ │ │
│ │ │ Bahar 2026 dönemine   │ │ │  48 px primary, full width
│ │ │ aktar                 │ │ │  (short label on phones: server sends both; §8.5)
│ │ └──────────────────────┘ │ │
│ │ [ Başka bir tür seç    ] │ │  44 px secondary, stacked
│ │ [ Kurulum sihirbazı    ] │ │
│ │ ▸ Bu dosya nedir?        │ │  44 px row
│ └──────────────────────────┘ │
│ [📎]  Sorun…            [➤]  │  composer docked above safe area, 16 px text
└──────────────────────────────┘
```

- **No drag-and-drop on phones.** 📎 opens the native picker (`<input type="file" accept={ACCEPT}>`; iOS offers
  Files / Drive / OneDrive). Paste works where the OS supports it.
- The empty-thread starters gain "Elimde bir dosya var" (44 px chip), which opens the picker.
- After the primary button, the sheet closes and the target page opens with the file row at the top. Focus goes to the
  page's own primary.
- MOBILE.md M-01 (no horizontal scroll), M-02 (44 px), M-03 (16 px inputs) and M-05 (keyboard clearance) on the sheet
  with a card open, and on `/import?…&from=helper`.

### 8.3 Discoverability (the admin who doesn't know)

- **Starters (helper.md §6.2):** admin and planner starters gain "Elimde bir dosya var, ne yapayım?" as the **first**
  starter. Academician / staff: "Bir dosyam var, ne işe yarar?" replaces nothing; it shows only when the 3 role
  starters have been dismissed once (one interruption at a time).
- **Feature index (`features.yaml`, ask to HB-01's owner):** new entry `helper.files`:
  - `kind: control`, title "Dosyanın ne olduğunu öğren" / "Find out what a file is";
  - synonyms: bu dosya ne, hangi dosya, dosya türü, excel ne yapayım, dosyamı nereye yüklerim, yanlış dosya, which
    file, what is this file;
  - `anchor: helper-attach`, `permission: []`.
  - "Nerede?" answers it with "Göster", which rings the 📎.
- **Palette shortcut (helper.md §4.5):** "dosya" / "file" → the Kısayollar row "Dosya ekle ve ne olduğunu öğren", which
  opens the sheet with the picker.

### 8.4 Where else the drop target appears

| Surface | Behaviour |
|---|---|
| **Any signed-in page** (desktop, fine pointer) | When an OS file drag enters the window and the pointer is **not** over a local drop zone, the page shows a quiet **edge target**: a 2 px `--tint` inset outline on the viewport + a pill at the top centre with `helper.file.dropPage`. Dropping opens the helper sheet (if closed) and classifies the file. Not shown on kiosk, slot display, `/public/**`, `?embed=1`, `/setup`, `/login`, `/welcome`, or when the helper is disabled for the audience. Esc or leaving the window clears it |
| **`/import` step 0** (no kind chosen) | A drop zone above the kind list: "Türünü bilmiyor musunuz? Dosyayı bırakın, biz söyleyelim." It runs the same classify. In the detected state, the wizard **selects the kind and keeps the file** (no sheet, no card): the kind row shows a check and "Dosyanız bir planlama listesi (sütunlar: …)". The term select is preset from the guess, with the mismatch line. The page's own "Önizle" is the primary. Ambiguous and unknown states render the same choice / unknown blocks inline |
| **`/import` step 1 with a kind** | Unchanged (`MagneticDrop`). Before the upload, the client calls classify; if the kind differs, the existing `importFlows.wrongFile` line + "… olarak içe aktar" (`import-switch-kind`) appears **before** the round trip instead of after it (M-20) |
| **`/onboarding`** | `FileDrop` unchanged. The table's "Tür" column shows the router's kind label (e.g. "Planlama listesi") next to the extension when classify answered within 1.5 s; otherwise the extension only. A row that is an importer shape in Excel gets one quiet hint line under the table: "1 dosya İçe aktar ekranından da aktarılabilir." (no button; the council's fast path reads it the same way) |
| **Empty states** | `/import` history empty, `/admin/rooms` with no rooms, `/admin/users` with only the admin, `/dashboard` on a fresh install (planner/admin): the one-line link "Elinizde bir dosya mı var? Bırakın, ne olduğunu söyleyelim" opens the sheet with the picker. One link per empty state, never a second drop zone |
| **Not here** | `/timetable` and `/runs/[id]` canvases keep their own in-app drags. An OS file drag there still shows the edge target (no conflict: dnd-kit handles pointer drags, not `Files`) |

### 8.5 Button labels

- The server sends the full label ("Bahar 2026 dönemine planlama listesi olarak aktar", ≤ 48 characters).
- Under 640 px, the client uses a short label when the server provides `label_short` (optional `Txt` on `FileRoute`,
  ≤ 28 characters: "Bahar 2026'ya aktar").
- The accessible name always uses the full label.

## 9. Motion (rows for `docs/design/v2/motion.md` new §3.22 "Helper file router", handed to that file's owner)

Every moment has a purpose sentence. One focal motion at a time. Only transform and opacity animate. No blur.

| Moment | Purpose ("motion tells the user…") | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| OS file dragged over the sheet / page / zone | "you can drop it here" | **instant** tint + 2 px outline + label (motion.md §3.8 rule: an OS file is not our element, so no lift or magnet) | — | same | outline only, opaque fill |
| Drag leaves / Esc | "cancelled" | instant removal | — | same | same |
| File chip enters the log (user bubble) | "your file arrived" | opacity + y 6 → 0, once | `springs.smooth` | 100 ms opacity | — |
| Reading > 400 ms | "still working" (a real wait) | shimmer on the label "Dosya okunuyor…" only (pattern 17), stops with the result | loop 1.6 s (allowed: ongoing work) | static label | `CanvasText` |
| Card appears (detected / unknown / needs_planner / chooser) | "here is what it is and what you can do" | the card's opacity + y 6 → 0; rows do **not** stagger | `springs.smooth` (settles 281 ms) | 100 ms opacity | opaque `--fill-3` |
| "Bu dosya nedir?" opens | "more detail, same place" | height via `layout` (FLIP), content fades in after 60 ms | `springs.smooth`, exit `dur.fast` 120 | instant | — |
| Chooser pick → new card | "this is your choice now" | the picked row's tint `layoutId` moves into the new card header; the old card collapses to one line | `springs.glassMorph` (≤ 281 ms) | instant swap | — |
| Primary press → hand-over | "going to the right page" | button press scale .98 (`snappy`), then the route change (pattern 13: veil, content rises 6 px). Phone: the sheet exits down (`dur.base` + `ease.in`) **before** the route change | `snappy`, route `smooth` + 180 ms veil | no scale; 100 ms veil | opaque |
| Handed-over file row on the target page | "your file is already here" | one tint highlight on the row that fades after 2 s (like the moderation timeline) | `--dur-base` fade | highlight static 2 s, then removed | outline |
| Refused / error | "it didn't work, here is why" | message appears with `smooth`; **no shake** | `springs.smooth` | instant | — |
| Expired | — | no motion (text swap) | — | — | — |

**No motion:** certainty word, warnings list, typing, the edge target, the chooser rows (no stagger). **Budget:** shell
bar + helper sheet = 2 blur surfaces; the edge target and the card are fills (no glass on glass). **Audit:** add "drop →
card", "chooser pick" and "hand-over" to `e2e/motion-audit.spec.ts`: ≤ 3 dropped frames, nothing over 300 ms except the
reading shimmer, reduced motion = end state, reduced transparency opaque.

## 10. Accessibility

- **Never drag-only:** every drop target is also a button. 📎 "Dosya ekle" (`aria-label`, 44 px) opens the picker with
  Enter or Space. The `/import` and empty-state zones are a single button with a visible label (the T-R2-20 pattern of
  `file-drop.tsx`: no nested interactive). The `<input type=file>` has a `<label for>`.
- **Paste:** Ctrl/⌘+V with a file on the clipboard, while focus is in the composer, attaches it (`paste` event,
  `clipboardData.files`). Text paste is unchanged.
- **Keyboard:**
  - the edge target has no focus stop (it is a drag affordance only);
  - in the card, Tab moves title (`tabIndex=-1`, not in order) → primary → secondary → disclosure;
  - in the chooser, the rows are a `radiogroup` (↑ ↓ to move, Enter or Space to pick);
  - Esc closes the sheet as today (helper.md §8), and with a stage alive it also deletes the stage.
- **Focus:**
  - after the card arrives, focus goes to the **card title** (`tabIndex=-1`), so the reader hears what the file is before
    the button;
  - after a chooser pick, focus goes to the new card title;
  - after the hand-over, focus goes to the target page's own primary ("Önizle"), or to the file row's heading when that
    primary is disabled;
  - after "Dosyayı kaldır", focus goes to the page's drop zone button (the E2EA2-F03 pattern);
  - focus never falls to `<body>`.
- **Screen reader:**
  - "Dosya okunuyor…" is `role="status"`;
  - the card is `role="group"` + `aria-labelledby` = title;
  - a polite live message repeats once: "{dosya}: {tür}, {kesinlik}. {birincil düğme}";
  - warnings are inside the card with an icon **and** the text (never colour alone), and a `bad` warning uses
    `role="alert"` once;
  - the certainty badge has its word as its name;
  - the drag state is announced by the drop zone label ("Bırakın"), not by motion.
- **Targets and text:** 44 px minimum, phone primary 48 px, 16 px inputs (composer), no hover-only affordances (the
  edge target is not needed to act, only a hint).
- **Contrast:** AA light and dark. In forced colours, the drag outline uses `Highlight` and the card border uses
  `CanvasText`.
- **Language:** card strings follow the UI locale. Evidence labels are the workbook's own Turkish column names, also in
  the EN UI, marked `lang="tr"`.

## 11. Acceptance criteria and test plan (HB-23d)

### 11.1 Acceptance criteria

1. **Index mode, no AI key:** an admin drops `bahar_derslikler_takvimi_2026.xlsx` (masked copy) in the ⌘J sheet → within
   1.5 s a `file` card reads "Bu bir haftalık derslik takvimi · Eminim", evidence with sheet count and day/period axes,
   "Dönem: Bahar 2026 (dosya adından)". With Güz active, it also shows the mismatch warning. **No `ai_usage` row and no
   `ImportJob`, `CouncilJob`, `audit` or `helper_messages` row is created.**
2. The primary button writes exactly one `helper.file.handoff` audit row and opens
   `/import?kind=weekly-grid&term=<Bahar id>&year=2026&from=helper`. The file row shows "Yardımcıdan geldi", and focus is
   on "Önizle". The preview runs with `upload_token` (no second upload in the network panel). The import job has
   `summary.source = "helper"`.
3. The token is single-use (a second use → 410 `stage_used`), expires after 10 minutes (410 `stage_expired`, the UI line
   and re-pick), and is owner-bound (another user, or the same user after logout → 403). The stage file is ciphertext
   and is gone after consume, expiry or cancel.
4. `final_planlama_listesi_2026_v2.xlsx` is an **exam list** (headers beat the file name). The transposed fixture
   routes to the setup wizard (not to the weekly-grid importer). `bahar_requests_en.csv` routes to the setup wizard with
   the "İngilizce sütunlar" evidence.
5. **Ambiguous** (synthetic file with planning and exam headers mixed): a `choice` card with 2–3 options, each with a
   hint. Picking one gives the detected card of that kind (no re-upload).
6. **Unknown** (a random `.xlsx` with no known headers, or a `.zip` of photos): the unknown card with the accepted-kinds
   list, "Örnek dosyaları gör" (templates download, header-only) and, for planners, "Kurulum sihirbazında aç".
7. **Role:**
   - an academician dropping a planning list gets "Derslerim'i aç" and no import button;
   - an academician dropping an `.ics` gets "Takvimime ekle" (→ `/profile?calendar=1`);
   - a viewer gets needs_planner with no button and no person named;
   - a `setup.users`-only user dropping a users CSV gets "Kullanıcıları içe aktar" (→ the users import sheet), and the
     same user dropping a planning list gets needs_planner.
8. **KVKK:**
   - on a stack with `KVKK_UPLOAD_GUARD=1`, a raw seed workbook gives the `refused` card with the guard's own TR/EN
     message, and **no stage file exists**;
   - in any environment, the classify response JSON contains no cell value and no raw header text: no instructor name
     from the fixture's instructor columns, and not the "Fatih Bey" header fragment.
9. **Limits:** a 16 MB file is refused on the client (no request) with "en çok 15 MB". A 6 MB users CSV shows
   `too_large_for_target` and no primary. 21 classify calls in a minute → `rate_limited` card.
10. **Simplicity:** each state has at most one primary. Every card fits without scrolling at 1440 × 900 in the sheet, and
    at 390 × 844 above the composer (the disclosure is closed).
11. **Keyboard / SR:** the whole flow works without a mouse (📎 → picker → card → primary). Live and status messages fire
    once. Focus never lands on `<body>`. Reduced motion gives end states.

### 11.2 Unit tests

**Backend** (`smartsched/backend/tests/helper/test_file_router.py`; pytest, targeted; fixtures are read from
`tests/fixtures`, and responses are asserted name-free):

| Test | Fixture / input | Expect |
|---|---|---|
| `test_kind_planning_list[bahar,guz]` | `bahar_derslik_planlama_listesi_v5.xlsx`, `guz_derslik_planlama_2026_2027_v2.xlsx` | `planning_list`, sure, term Bahar (year None) / Güz 2026, primary `import` `{kind: planning-list}` |
| `test_kind_exam_list` | `final_planlama_listesi_2026_v2.xlsx` | `exam_list`, sure, term Final 2026 |
| `test_kind_weekly_grid[bahar,guz,final]` | the three `*_derslikler_takvimi_*.xlsx` | `weekly_grid`, sure, `year` param set |
| `test_transposed_goes_to_onboarding` | `universal/bahar_week1_transposed.xlsx` | `timetable_other`, likely, primary `onboarding`; `weekly_grid` not among the candidates |
| `test_english_requests` | `universal/bahar_requests_en.csv` | `request_list`, primary `onboarding`, evidence `english` |
| `test_room_master_csv` | `room_master.csv` | `room_master`, sure; `setup.rooms`-only user still gets the import route |
| `test_rules_doc`, `test_pdf_exam`, `test_scan_ai_off` | `rules_memo.docx`, `final_exams_sheet.pdf`, `final_exams_page1.png` | `rules_doc` / `exam_list` → `onboarding`; the PNG with vision off → `scan` + `scan_ai_off` |
| `test_users_csv`, `test_users_csv_too_large` | synthetic `tests/fixtures/helper_files/users_initials.csv` (initials only), 6 MB variant | `users_csv` → `admin.users {import: 1}`; `too_large_for_target`, no primary |
| `test_crbs_dump` | synthetic `helper_files/crbs_schema_only.sql` (CREATE TABLE only, no INSERT of people) | `crbs_dump`, sure |
| `test_ics_planner_vs_academician` | synthetic `helper_files/seminar.ics` (3 VEVENTs, no attendees) | planner → `onboarding`; academician → `profile.calendar` + `icsAcademic` text |
| `test_intake_json` | synthetic intake-v1 JSON | `intake_json` |
| `test_ambiguous_chooser` | synthetic xlsx with planning + exam header signals | `ChoiceCard` with 2–3 options and hints; `route` with each kind returns that kind's card |
| `test_unknown`, `test_empty`, `test_unsupported`, `test_zip_bomb` | random headers xlsx; 0 bytes; `.exe`; the existing bomb fixture of `test_formats.py` | unknown card with `examples`; refusal codes; no stage |
| `test_no_persistence` | any fixture | row counts of `import_jobs`, `council_jobs`, `audit_events`, `helper_messages`, `ai_usage` unchanged; no plain file under the upload dirs |
| `test_evidence_is_name_free` | the planning and exam fixtures | the JSON has no value from the instructor columns, and no raw header containing a person name; labels come from `COLUMN_LABELS` |
| `test_kvkk_guard_refuses_before_stage` | guard on (monkeypatched env + names file) | refusal `kvkk_seed_workbook` / `kvkk_unmasked_names`; stage dir empty |
| `test_token_owner_once_expiry` | freezegun | other user → 403; second consume → 410 `stage_used`; +10 min 1 s → 410 `stage_expired`; logout → 403; the sweeper deletes the stage |
| `test_stage_is_ciphertext` | any fixture | the stage bytes ≠ the file, and their SHA-256 ≠ the file's |
| `test_handoff_audit` | any fixture | one `helper.file.handoff` row without file name; permission re-checked (a forged `feature_id` → 403) |
| `test_imports_accept_upload_token` | planning fixture | `POST /imports/planning-list` with `upload_token` + `dry_run` → job DONE, `summary.source == "helper"`, `term_check` present |
| `test_council_accepts_upload_tokens`, `test_users_import_accepts_token` | — | as above |
| `test_card_schema` | all card outputs | `validate_card` passes; JSON Schema snapshot updated with `file` |
| `test_index_mode_no_model` | AI off, ambiguous file | no provider call, no usage row; `ai_sorted` false |
| `test_term_mismatch_button_carries_file_term` | Güz active, Bahar file | primary `params.term_id` = Bahar; warning `term_mismatch` |

**Frontend** (vitest, `--maxWorkers=1`; files under `components/helper/`):
- `file-card.test.tsx`: each state renders one primary; certainty word; warnings with icon + text; disclosure collapsed;
  the short label under 640 px.
- `file-drop.test.tsx` (helper): `dragenter` with `Files` shows the target, a text drag does not; drop → classify called
  once; paste of a file; 📎 opens the input; the pre-check over 15 MB makes no request.
- `file-handoff.test.ts`: `fileHandoffHref` per `feature_id`; the token never appears in the href;
  `sessionStorage` mirror; expiry line.
- `import-wizard-handoff.test.tsx`: `/import?kind=…&term=…&from=helper` shows the file row, focuses "Önizle", sends
  `upload_token`; ✕ deletes the stage and focuses the drop zone button.
- `a11y`: aria snapshot of the card and the chooser (`radiogroup`), focus after card / pick / hand-over, live message
  once; reduced motion = end state.
- `schema.gen.test.ts` snapshot with the `file` type.

**E2E TO RUN** (one stack, by the e2e lane; spec `e2e/hb23-file-router.spec.ts`; masked fixtures from
`$REC_WORKDIR/fixtures`):
1. Admin at 1440: ⌘J → drop the Bahar board (Güz active) → card + mismatch → primary → `/import` file row →
   Önizle → preview with `term_check`.
2. The same at 390 (touch): 📎 → picker (`setInputFiles`) → card → primary → the sheet closes → the file row; M-01, M-02,
   M-03 and M-05 on the sheet and on `/import`.
3. Planner: the transposed grid → setup wizard row 1 with the chip.
4. Academician at 390: the planning list → "Derslerim'i aç"; the `.ics` → `/profile?calendar=1`.
5. Page-level drop on `/dashboard` at 1440 → the edge target → the sheet opens with the card.
6. `/import` step 0 drop → kind preselected.
7. The KVKK guard stack: the raw seed workbook → refused card.
8. The motion-audit cases of §9.

### 11.3 UX script for the user-tester (personas; 1440 mouse and 390 touch, tr-TR, Europe/Istanbul)

Give no hints about kinds or pages. Record time-to-primary, wrong clicks and the person's own words. "Where do I
click?" or "overwhelming" is a **major** finding with a screenshot (COMMON Simplicity principle).

| # | Persona / setup | Task (say exactly this) | Success | Watch for |
|---|---|---|---|---|
| U1 | **Fatih Bey, admin, doesn't know the file type** · Güz active · masked `bahar_derslikler_takvimi_2026.xlsx` renamed `Bahar_son.xlsx` on the desktop | "Bölümden bu dosya geldi. Ne olduğunu bilmiyorum. Sisteme doğru yere koyun." | Finds the helper (⌘K / ⌘J / the starter / a page drop) in ≤ 15 s; reads the card; notices the term warning; reaches the `/import` preview in Bahar in ≤ 60 s, with ≤ 1 wrong click | Does he understand "Haftalık derslik takvimi"? Does he trust "Eminim"? Does he read the evidence? Does he expect the import to have happened already? (it must not) |
| U2 | Same, at 390 | The same task, with the file in the phone's Files app | 📎 → card → primary in ≤ 60 s; no zoom; no horizontal scroll | Thumb reach of the primary, the label length, the keyboard covering the card |
| U3 | **Planner**, Güz active | "Güz sınav listesini yükleyin." Hand over `final_planlama_listesi_2026_v2.xlsx` | Gets "Sınav listesi" despite "planlama" in the name; reaches the preview | Confusion between the file name and the card |
| U4 | Planner | "Bu dosyayı içe aktarın." The transposed grid | Accepts the wizard route; understands why (evidence line) | Does "Kurulum sihirbazı" feel like a detour? |
| U5 | Planner | An ambiguous synthetic file | Picks the right option from the chooser in ≤ 20 s | Are the hints enough? |
| U6 | **Dr. A. T., academician**, phone | "Outlook'tan aldığınız takvim dosyasını SmartSched'e ekleyin." (`seminar.ics`) | Understands that SmartSched doesn't read it, and reaches Profil › Takvim | Does the card feel like a refusal? Does the person feel lost? |
| U7 | Academician, desktop | "Bölümün planlama listesi elinizde; kendi derslerinizi görün." | Opens Derslerim from the card | Do they look for an import button? |
| U8 | Viewer | Drops any file | Reads needs_planner and knows what to do next | The wording must be polite and give a next step |
| U9 | Admin | An unknown file (`notlar.xlsx` with random columns) | Finds "Örnek dosyaları gör", downloads the planning list example | Does "Bu dosyayı tanıyamadım" feel like the system's fault or theirs? |
| U10 | Keyboard-only + NVDA/VoiceOver (desktop) | U1 without a mouse | Completes; hears kind + certainty + the button | Focus order; double announcements |

Report: `docs/testing/hb23-file-router-ux.md` (the user-tester's own file), one row per task, with severity.

### 11.4 Design review checklist (designer sign-off before HB-23c merges)

- [ ] One primary per state (§5). No chips under the card. Secondary ≤ 2. "Bu dosya nedir?" collapsed.
- [ ] No percentage or bare number anywhere. Certainty is a word. Counts have units ("19 sayfa").
- [ ] Turkish first, all keys in `tr.json` + `en.json`, `crbs_lang_import --check` run. No enum or snake_case in the UI.
- [ ] Evidence shows canonical labels only (§5.2). No cell value, no file name from the server, no person named in
      needs_planner.
- [ ] The button names the effect + object (+ term when it differs). The full accessible name is kept under 640 px.
- [ ] Every drop target has a button path. Paste works in the composer. Phone: 📎 at 44 px, primary at 48 px, 16 px
      composer.
- [ ] Focus: title → primary; hand-over → page primary; remove → zone button. Never `<body>`.
- [ ] Motion rows of §9 only. OS drag is instant (§3.8). No stagger, no shake. Reduced motion = end state. ≤ 2 blur
      surfaces.
- [ ] Rehber modu (AI off): 📎 present and working. The status chip is unchanged by file cards.
- [ ] The target pages are unchanged except for the file row, the `term` param and the "Yardımcıdan geldi" chip. Their own
      preview, `term_check` and "Uygula" are still the only writes.
- [ ] The edge target is absent on kiosk / public / embed / setup / login / welcome.
- [ ] Copy review of every "Bu dosya nedir?" text (§5.1), ≤ 3 sentences, formal "siz".
- [ ] Contrast AA in light / dark / forced colours. Reflow at 320 px and 200 % zoom.

## 12. Tokens

| Token | Value | Use |
|---|---|---|
| Card | `--fill-3` well + `edge-hairline`, `--radius-md`, padding 16, gap 12 (as helper.md §12) | file / chooser cards |
| Title / body / meta | `type-headline` / `type-callout` / `type-footnote`; caption `type-caption` `--label-3` | card text |
| Certainty badge | 24 px pill, `type-caption`: sure `--status-feasible-fg` dot, likely `--primary` dot, unsure `--status-warning-fg` dot; the word always shown | header |
| Warning row | 16 px icon: info `--label-2`, warn `--status-warning-fg`, bad `--status-infeasible-fg`; text `type-footnote` | warnings |
| Drag target | 2 px inset outline `--tint`, fill `--tint-soft`, radius = container's; forced colours `Highlight` | sheet log, zones, viewport edge |
| Edge pill | 36 px tall, `--mat-thick-solid` (no blur), `type-callout`, top inset 12 px | page drop |
| File chip | 32 px, `--fill-2`, icon 16 + name (ellipsis at 28 ch) + size `type-caption` | user bubble, target page row (44 px on phones) |
| Primary | desktop 40 px (44 px hit area), phone 48 px full width; secondary 44 px | buttons |
| Spacing | evidence → term 4; term → warnings 8; warnings → primary 12; primary → secondary 8 | card |
| Motion | `springs.smooth`, `springs.glassMorph`, `snappy`, `dur.fast` 120, `dur.base` 180, `tween.reduced` 100, shimmer loop 1.6 s | §9 |
| Limits | classify 15 MB (`min(upload_max_mb, council_max_file_mb)`), stage TTL 10 min, 20 / min / user | §1.3, §6.3 |

## 13. Components and files (HB-23b / HB-23c)

| Piece | File | Built from |
|---|---|---|
| Classifier | `backend/app/ai/helper/files.py` (`classify`, `route`, `stage`, `consume`, `sweep`) | `council/formats.py`, `council/fastpath.py`, `council/structure.py`, `importers/detect.py`, `services/bookings_users.py`, `services/import_term_check.py` (+ bytes variant), `core/safe_files.py`, `core/kvkk_guard.py`, `ai/policy.py` |
| CRBS / ICS sniffs | inside `files.py` (CRBS ~20 lines), ICS from `council/formats_ics.py` | — |
| Card types | `backend/app/ai/helper/schema.py` (`FileCard`, `FileRoute`, `FileTerm`, `FileWarning`) | `helper.card.v1` |
| Routes | `backend/app/api/v1/helper_files.py` (`/helper/files/classify`, `/route`, `/handoff`, `DELETE /{sid}`, `/examples`) | `api/v1/helper.py` patterns |
| Target endpoints | `api/v1/imports.py`, `api/v1/council.py`, `api/v1/roles.py` (`upload_token[s]`) | — |
| Examples (templates) | `backend/app/ai/helper/file_examples.py` | `HEADER_SPEC`s |
| Feature index entry | `features.yaml` `helper.files` (ask to HB-01's owner) → regenerate `feature-index.gen.ts` | — |
| Client API | `frontend/src/lib/api/helper.ts` (`classifyFile` with XHR progress, `routeFile`, `handoffFile`, `dropStage`) | React Query |
| Card | `frontend/src/components/helper/cards/file.tsx` (+ `render.tsx` mapping) | `cards/frame.tsx`, `Badge`, `Button`, `Collapsible` |
| Drop + 📎 + paste | `frontend/src/components/helper/file-drop.tsx`, composer slot in `helper-sheet.tsx`, `page-file-target.tsx` (mounted once in `app-shell.tsx`, an ask to the shell owner) | motion.md §3.8 behaviour; `ACCEPT` from `onboarding/file-drop.tsx` |
| Hand-over | `handover-links.ts` `fileHandoffHref`; `helper-store.ts` `fileHandoff` slot + `sessionStorage` mirror; `useHelperFileHandoff()` hook | — |
| Target page adoption | `components/import/import-wizard.tsx` (step 0 zone, `term` param, file row), `components/onboarding/file-drop.tsx` (row from hand-over, kind label), `components/admin/users-admin.tsx` (`?import=1`) | asks to those owners |
| Test ids | `helper-attach`, `helper-file-drop`, `page-file-target`, `helper-card-file-<state>`, `helper-file-primary`, `helper-file-other`, `helper-file-onboarding`, `helper-file-what`, `helper-file-choice-<kind>`, `import-handed-file`, `import-handed-file-remove`, `onboarding-handed-file` | — |

## 14. Decisions

1. **One deterministic classifier composed from the four that exist, plus an agreement rule.** The importer header
   check, the council's format sniffing and shape detection, the council's structure analyst and the users header check
   all run together. Disagreement decides the route: for example, the transposed board goes to the setup wizard instead
   of failing in the weekly-grid importer. The file name only gives the term. No model is needed. A model may only
   re-order a tie, behind the KVKK switch, and is off by default.
2. **The helper hands over and never imports.** The card's one primary opens the target page with the file and the term
   prefilled. The page's own preview, `term_check` and "Uygula" stay the only writes, so every existing guard still
   applies.
3. **No second upload, and still nothing stored.** The bytes are staged encrypted for 10 minutes. The key lives only in
   the owner-bound, single-use token, which never goes into a URL. Classify writes no database row, no job and no
   helper history. The audit row is written on the card's button.
4. **The card contract grows by exactly one type (`file`), and the rest is reused.** The chooser is a `choice` card,
   refused is a `refusal` card, error is an `error` card. File cards are ephemeral, so they are not kept in the 30-day
   history.
5. **Role-aware routing comes from the existing permission keys, with real alternatives.** Academicians get Derslerim,
   Profil › Takvim, Hızlı rezervasyon and Taleplerim. When there is nothing, the card says "planning team" and names
   no one. Evidence uses canonical column labels and never cell values or raw headers.

## 15. Open questions (with the recommended answer)

1. **Is the 10-minute encrypted stage "storing" under the KVKK rule "nothing is stored until confirm"?**
   *Recommend:* treat it as transient processing (it is encrypted, the key is held only by the person, it is deleted on
   use, expiry or cancel, it is not in backups, and there is no database row). Get the KVKK officer's note in
   `docs/kvkk/`. Ship a switch `HELPER_FILE_STAGE=off`: the target page then asks the browser to re-send the same File
   object, which is still in memory, so the person does not pick it again.
2. **Page-level drop on every page, or only the helper, `/import`, `/onboarding` and empty states?**
   *Recommend:* every signed-in desktop page, as a quiet edge target (it costs nothing when unused, and it is the most
   natural move for "I have a file"). It is hidden on kiosk, public, embed and setup.
3. **Model tie-breaker on by default when the council AI switch is on?**
   *Recommend:* off in v1 (`ai.helper.file_tiebreak=false`). Turn it on only if telemetry shows more than 5 % of
   classifications ending ambiguous.
4. **Several files in one drop?**
   *Recommend:* one card, "{n} dosya bıraktınız", with the primary "Kurulum sihirbazında aç", carrying all the tokens
   (the council reads several files together). For people without `planning.edit`, classify only the first file.
5. **Templates do not exist for most kinds.**
   *Recommend:* add generated, header-only examples (`/helper/files/examples`) in HB-23b, from the importers'
   `HEADER_SPEC`s, so they can never drift from what the importer reads.
6. **Should an academician be able to send the file to the planner from the card?**
   *Recommend:* not in v1. It would store a file for someone else and needs a recipient model (messages.md). Give
   guidance only, and revisit with the messages feature.
7. **Should `/import` accept CSV / ODS planning lists by transcoding them (`workbook_for`) instead of routing them to the
   setup wizard?**
   *Recommend:* yes, as a follow-up (HB-23e). It removes the `needs_excel` detour. v1 routes them to the wizard, which
   already reads them with the same importer.
8. **Should the card say "this file was imported already"?**
   *Recommend:* v1.1. Store the SHA-256 in `ImportJob.summary` at import time, then show "Bu dosya {tarih} tarihinde
   içe aktarıldı" as an info warning, with "Önizlemeyi aç".
9. **Phone share target (PWA `share_target`) so "Share → SmartSched" from Files or Mail opens the router?**
   *Recommend:* later, after the PWA manifest work. The 📎 path covers phones in v1.
