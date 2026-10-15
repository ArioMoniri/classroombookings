# Persona test: senior academician on SmartSched (2026-10-15)

Ledger: `persona-academician-2026-10-15`. Issue ids: `A-01` … `A-32`.

**Persona.** A senior academician in Psikoloji who teaches 3 courses in Bahar 2026 and is referred to only as **"the instructor of PSI 214 / PSY 214 / PSY 278"** (KVKK).
- **Bahar 2026:** 4 meetings, all LOCKED to A-block rooms by the planner:
  - PSI 214 §1: Wednesday P7–P9, A 206, 90 students.
  - PSY 214 §1: Wednesday P3–P5, A 109, 40 students.
  - PSY 278 §1 theory: Tuesday P3–P5, A 308, 40 students.
  - PSY 278 §1 lab: Tuesday P10–P11, A 105 (PC), 40 students.
- **Güz 2026-27:** PSI 213, PSY 213 and PSY 277 (theory in A 308, lab in A 105).
- **Strong wishes from the fixture:**
  - "Atanacak dersliğin kürsü bilgisayarına da JASP yüklenmesi gerekmektedir" (Bahar row 1119): the lectern PC must have JASP installed.
  - "Bilgisayar Laboratuvarı (JAMOVI)" (row 1120): a computer lab with JAMOVI.
  - The needs doc (L1) shows the same person kept 8/8 roomed classes in A block across two terms.
- Internal instructor id: `157`.

Fatih Bey's scenarios (week 3, PHAR 240 pin, the nursing rule, the Excel export, the 102-in-30 refusal) are tested by the admin persona. They are out of scope here, except where an academician sees their effect.

## Setup (as run)

- **Code:** frozen snapshot of commit `cc9c45d` (`persona-src`, not modified).
- **Stack:** `scripts/record/stack.sh up` with `REC_API_PORT=18940`, `REC_WEB_PORT=18941`, `REC_TEACHER=1`, `REC_LANG=tr`.
  - FastAPI on SQLite.
  - All three real terms imported (Bahar 2026, Güz 2026-27, Final 2026), plus the room master.
  - Production `next build` / `next start`.
- **Solver runs** (`stack.sh runs`, with `REC_RUNS` extended by two Bahar runs because the persona teaches in Bahar):

  | Run | Term | Scope | Status | Placed | Hard score | Active |
  |---|---|---|---|---|---|---|
  | #7 | Bahar | week 3 | FEASIBLE_PARTIAL | 687/716 | 100 | |
  | #8 | Bahar | full term | FEASIBLE_PARTIAL | 681/717 | 100 | yes |
  | #9 | Güz | week 3 | FEASIBLE_PARTIAL | 524/530 | 100 | |
  | #10 | Güz | full term | FEASIBLE_PARTIAL | 517/530 | 100 | yes |

- **Accounts:**
  - The seeded teacher account `ogretmen@smartsched.local` (role TEACHER) plays the academician.
  - The seeded admin plays the coordinator view.
  - Credentials are in the `stack.sh` header and are not repeated here.
- **Test fixture created through the API, not a product test:**
  - The admin was designated as approver for all rooms (`PUT /approvals/approvers/1`).
  - One approval rule was added: "PC lab onayı", entity_type `tag`, tag `PC`.
  - Without these, no booking can reach PENDING.
- **Driver:** Playwright 1.56 library with Chromium from `/opt/pw-browsers`.
  - Viewport 1440×900, plus 390×844 (mobile, touch).
  - Locale `tr-TR`.
  - Teacher profile language switched TR, then EN, then back to TR.
- **Evidence root:** `EV=/tmp/claude-0/-home-user-classroombookings/ac8cf3be-4f7b-53da-a7ff-63cf01e137b0/scratchpad/persona-academician`.
  - Screenshots: `EV/shots/*.png`.
  - curl output: `EV/curl/*`.
  - Scripts: `EV/scripts/*.mjs`.
  - Logs: `EV/*.log`.
  - Screenshots show fixture instructor names. Keep them out of the repository (KVKK).
- **Host load caveat:** the VM has 4 cores and a load average of 24–28 during the test, because other agents' stacks were running. Frame and latency numbers are inflated. The no-op baseline (0.8 dropped frames per interaction) shows the probe still separates the slow interactions.

---

## 1. BLUF

- **An academician cannot see their own teaching anywhere.**
  - No login is linked to an instructor: `User` has no instructor field, and `Instructor.email` is empty for 490/490 instructors.
  - The TEACHER role lacks `planning.view`.
  - So the teacher lands on `/timetable`, which says "Bu dönem için henüz bir program yok" and offers "Program oluştur" / "Excel'den içe aktar" (A-01).
  - The only way to find PSY 277 is to scan the room grid day by day for the code (A-02).
  - No calendar feed contains a single class (A-14).
- **The booking side works for a make-up session, end to end:**
  - find room (date, time, 42 people, text "PC"), then book C 303 directly, or request A 105 (PENDING);
  - the approver sees the request with its note, rule and deadline;
  - approve or reject, then bell notifications in the recipient's language;
  - "Taleplerim" statuses update;
  - the ICS feed parses cleanly with `icalendar` 7.3 and moves TENTATIVE → CONFIRMED / CANCELLED.
  - What is wrong:
    - one session is split into one item per period in the list, the approval inbox and the ICS (A-12);
    - a PC lab cannot be asked for; the free-text match is contradicted by "PC özellikli oda; istenmedi" (A-11);
    - focus drops to `<body>` after every decision (A-21).
- **The persona's strongest wishes are invisible to everyone.**
  - "JASP on the lectern PC" and "JAMOVI" live in the notes column.
  - The class inspector never shows notes (A-04).
  - The explanation claims "İstenen derslik (A 308) verildi" when nothing was requested (A-05).
- **Parser bugs from the needs doc, checked in the real UI:**
  - ING 302 "Mümkünse B Blok olmasın" sits in the notes column, so the real UI shows **no wrong rule but also no "unparsed" signal**. Its definitive set (row 366) includes B 202, so the wish is broken silently. The parser still returns *prefer B* when the text is in a parsed cell (A-06).
  - "A veya C blokta" is dropped the same way. Three NUT rows got B-block rooms unnoticed (A-07).
  - Final row 19 (PTL252) shows "A 206 C 403 +4": alternatives are flattened, and a building "A" is invented (A-08).
  - **New:** "dersliğin büyük olmasına gerek yok" (the room need not be large) becomes an **AMPHI** requirement on four NUT oral exams (A-09).
- **Counts:** 32 issues: **0 Blocker, 17 Major, 15 Minor**.
- **Motion:** 8 of 12 measured interactions exceed the frame budget, even allowing for host load. One new surface is slow: the My Bookings row expand, 451 ms long frame (A-32). Reduced motion passes.

---

## 2. Coverage checklist

**Academician (TEACHER login):**

| Screen / control | Result | Issue |
|---|---|---|
| Login, keyboard only (Tab order, Enter submits) | ✓ | – |
| Landing after login (`/timetable?day=1`) | ✗ | A-01 |
| Sidebar: Rezervasyonlar, Rezervasyonlarım, Boş derslik bul | ✓ | – |
| Sidebar / phone tab bar: Çizelge | ✗ | A-01 |
| Sidebar logo (→ `/dashboard`) | ✗ | A-03 |
| ⌘K palette (search "PSY 277", "A 308", "PSI 213") | ✗ | A-23 |
| Bell: unread count in label, list, "Tümünü okundu say" | ✓ | A-16 |
| Yenilikler (what's new) button | not tested | – |
| Profile: fields, language TR ↔ EN, Kaydet | ✓ | A-17 |
| Profile: password change | not tested (would change the shared seed) | – |
| `/settings` (appearance, accessibility) | ✓ | – |
| Bookings: lens Çizelge / Boş saatler | ✓ | – |
| Bookings: Güne göre / Salona göre | ✓ | – |
| Bookings: building tabs, Bölüm filter | ✓ | – |
| Bookings: previous / next day | ✓ | A-30 |
| Bookings: date picker, Bugün, Yazdır, Çoklu seçim | not tested (URL used for dates) | – |
| Bookings: class cell (timetable slot) detail | ✓ | A-25 |
| Bookings: room info sheet (capacity, exam capacity, floor, day, next free, other free rooms) | ✓ | – |
| Bookings: free cell → book sheet → Rezerve et | ✓ | A-20, A-31 |
| Bookings: drag-span booking | ✓ (measured) | – |
| Bookings: week with no published timetable | ✗ | A-24 |
| Find room: date, start/end, Kaç kişi, Ara | ✓ | A-31 |
| Find room: feature filter (PC lab) | ✗ | A-11 |
| Find room: free text "PC" | ✗ | A-11 |
| Find room: Rezerve et (direct) | ✓ | A-21 |
| Find room: Talep et (approval rule) | ✓ | A-12 |
| Find room: holiday detection (29 Oct shows "0/1 dates open") | ✓ | – |
| Find room: "Dolu derslikleri de göster", "Bu haftanın diğer günleri" | not tested | – |
| My Bookings: totals line | ✗ | A-12 |
| My Bookings: Taleplerim list | ✓ | A-12, A-13 |
| My Bookings: Taleplerim expand | ✓ | A-32 |
| My Bookings: Talebi geri çek | ✓ | A-21 |
| My Bookings: Yaklaşan / Geçmiş / İptal edilen tabs | ✓ | – |
| My Bookings: select + cancel | ✓ | A-21, A-26 |
| My Bookings: room info button | ✓ | A-27 |
| Calendar sync: Özel bağlantılarımı oluştur | ✓ | – |
| Calendar sync: Google / Outlook / Apple links | ✓ | – |
| ICS `mine.ics`: curl and parse | ✓ | A-12, A-14, A-15 |
| ICS room feed (A 308) | ✗ | A-14 |
| Calendar sync: Özel bağlantıyı sıfırla | not tested | – |
| `/approvals` as teacher ("only approvers", link to Rezervasyonlarım) | ✓ | – |
| `/dashboard`, `/classes`, `/rooms`, `/rooms/15`, `/runs`, `/runs/7`, `/generate`, `/import` by URL | ✗ | A-03 |
| `/admin`, `/admin/rooms` by URL (proper "Bu sayfaya erişiminiz yok") | ✓ | – |
| "My timetable / my classes" | ✗ (does not exist) | A-02 |
| "My planning requests" (department requests and outcomes) | ✗ (does not exist) | §5 |
| EN pass on all teacher pages | ✓ | A-16, A-18 |
| Mobile 390 px: no horizontal page overflow, tab bar, free-slot list | ✓ | A-27 |
| Keyboard-only booking (grid arrows, Enter, sheet) | ✓ | A-20, A-22 |
| Reduced motion (OS and in-app) | ✓ | – |
| Reduced transparency | inconclusive (T13 check bug) | – |

**Coordinator view of this academician (seeded admin):**

| Screen / control | Result | Issue |
|---|---|---|
| `/timetable?subject=instructor:157&run=8&week=3`: 4 meetings, rooms, fill | ✓ (slow) | A-28 |
| `/classes`: term switcher → Bahar; search "PSY 278", "PSI 214" | ✓ (13–14 s to rows) | A-28 |
| `/classes`: instructor filter by id from the timetable | ✗ (name only, no link) | §6 |
| Class inspector: request, definitive, placement, weeks, source row | ✓ | – |
| Class inspector: notes and wishes | ✗ | A-04 |
| Class inspector: Yerleşimi açıkla | ✗ | A-05 |
| Requests view (`/requests` → `/classes?view=review`) | ✓ (persona rows are LOCKED, so not in review) | – |
| Run #8 report: satisfied vs unsatisfied for this person's sections | ✗ (only unplaced rows and aggregate soft shortfalls) | §5 |
| Approvals inbox: list, detail sheet (note, rule, deadline, day strip), Onayla, Reddet + note | ✓ | A-12, A-21 |
| Parser cases in the UI: ING 302, "A veya C", PTL252, MBG224, NUT401 | ✗ | A-06 … A-09 |
| Admin `/bookings`, `/classes` console | ✗ | A-29 |

---

## 3. Issues

Severity:
- **Blocker:** stops the persona's main task.
- **Major:** wrong, unsafe or missing for the persona's core story.
- **Minor:** friction or polish.

Paths are relative to `$SNAP/smartsched/`. `EV` is the evidence root (see Setup).

### A-01 (Major, frontend + backend)

- **Screen / URL:** login → `/timetable`; sidebar and phone tab bar "Çizelge".
- **Steps:** log in as TEACHER.
- **Expected:** the teacher lands on a page they can use (`/bookings` or `/my-bookings`). "Çizelge" is either hidden or shows the published timetable read-only.
- **Actual:**
  - The teacher lands on `/timetable?day=1`, which shows "Bu dönem için henüz bir program yok." with **Program oluştur** and **Excel'den içe aktar**.
  - `GET /terms` and `GET /runs` return 403 ("requires permission planning.view").
  - Evidence: `EV/shots/teacher-_timetable.png`, `EV/tour-teacher.log`.
- **Likely files:**
  - `frontend/src/components/auth/login-form.tsx:49-51` (redirects non-planners to `/timetable`);
  - `frontend/src/components/shell/nav-config.ts:35` and `tab-bar.tsx:24` (`permission: ["planning.view","room.view"]`);
  - `frontend/src/components/timetable/calendar-view.tsx:679-682` (the "no run" empty state is also shown on 403);
  - `backend/app/api/v1/runs.py:167` and `terms.py:25` (Viewer guard).
- **Suggested fix:**
  - Redirect non-planners to `/bookings`.
  - Drop `room.view` from the timetable nav permission until A-02 lands.
  - In `calendar-view`, render `NoAccess` when the runs/terms query is 403.
- **Acceptance:**
  - As TEACHER, the URL after login is `/bookings`.
  - Neither the sidebar nor the phone tab bar has "Çizelge".
  - `/timetable` shows "Bu sayfaya erişiminiz yok" with no "Program oluştur".
  - 0 console 403s on the landing page.

### A-02 (Major, backend + frontend)

- **Screen / URL:** none exists ("my timetable").
- **Steps:** as TEACHER, try to see this week's classes for PSY 277 / PSI 213 / PSY 213.
- **Expected:** "Derslerim": the academician's own classes this week and this term, with room, time and weeks (needs §5.1 Class and Person).
- **Actual:**
  - No such view exists.
  - `User` has no instructor link (`backend/app/models/system.py`; `users` columns: id … `token_version`, no instructor).
  - `Instructor.email` (`backend/app/models/catalog.py:115`) is empty for 490/490 instructors (DB query in `EV`).
  - The teacher can find PSY 277 only by scanning `/bookings` room by room (cell label "PSY 277").
- **Likely files:** `backend/app/models/system.py`, `models/catalog.py`, `api/v1/users.py`, `frontend/src/components/admin/users-admin.tsx`.
- **Suggested fix:**
  - P19-L1 (`Instructor.user_id`).
  - Plus new ticket P19-T1: `GET /me/classes?term_id&week` built from the active run's assignments of the linked instructor (allowed with `room.view`).
  - A "Derslerim" section at the top of `/my-bookings`.
  - A user↔instructor picker in the user admin, pre-suggested by canonical name.
- **Acceptance:**
  - A teacher linked to instructor 157 sees, for Güz week 5: PSY 277 Pzt 10:10–12:30 A 308, PSY 277 lab Pzt 13:30–15:00 A 105, PSI 213 Çar A 207, PSY 213 Sal A 207.
  - An unlinked teacher sees "Hesabınız bir öğretim elemanına bağlı değil".

### A-03 (Major, frontend)

- **Screen / URL:** `/dashboard`, `/classes`, `/rooms`, `/rooms/15`, `/runs`, `/runs/7`, `/generate`, `/import` as TEACHER; the sidebar logo.
- **Steps:** open each by URL, or click the "SmartSched" logo.
- **Expected:** the same "Bu sayfaya erişiminiz yok" page that `/admin/*` shows.
- **Actual:**
  - `/dashboard`: "Planlama listenizle başlayın" + **Talepleri içe aktar** + 3 stacked "Bu işlem için yetkiniz yok" toasts (`EV/shots/teacher-_dashboard.png`).
  - `/classes`: "Bu dönem için ders yok".
  - `/rooms`: "0 / 0 derslik".
  - `/rooms/15`: "Derslik bulunamadı" (A 206 exists and the teacher has `room.view`).
  - `/runs/7`: "Çalıştırma bulunamadı".
  - `/generate`: blank.
  - `/import`: wizard shown, `GET /imports` 403.
  - The logo links to `/dashboard`.
- **Likely files:**
  - `frontend/src/components/admin/admin-gate.tsx` (pattern to reuse);
  - `frontend/src/lib/permissions` (`canAccessRoute`);
  - `frontend/src/components/shell/sidebar.tsx:104`;
  - `frontend/src/components/dashboard/dashboard-view.tsx:124`.
- **Suggested fix:**
  - Wrap the planning routes in a `PlanningGate` that uses `canAccessRoute`.
  - Point the logo at the user's home route.
  - For `/rooms/[id]`, fall back to `GET /bookings/rooms/{id}` when the user has `room.view`.
- **Acceptance:** a crawler e2e as TEACHER finds every listed route either rendering `NoAccess` or (for `/rooms/15`) the room facts, with 0 permission toasts.

### A-04 (Major, frontend + backend)

- **Screen / URL:** `/classes?id=1117` and `?id=1118` (Bahar, admin), class inspector.
- **Steps:** open PSY 278 §1 theory and lab.
- **Expected:**
  - The inspector shows the "Derse Özel Açıklama" text: JASP on the lectern PC; JAMOVI in the lab.
  - It shows whether each wish was met or not evaluated.
- **Actual:**
  - The inspector shows only Talep "Derslik" / "Bilgisayar Laboratuvarı (JAMOVI)", the definitive room, the placement, Kim, Neden burada and Kaynak.
  - The notes appear nowhere in the inspector. The same holds for ING 302 row 366 ("Mümkünse B Blok olmasın") and ACU 303 row 609 ("Giriş Kata Yakın Olmasını rica etti hocamız").
  - Evidence: `EV/shots/c2-03-inspector-psy278-lab.png`, `EV/shots/parser-*.png`.
- **Likely files:** `frontend/src/components/classes/class-inspector.tsx`; `backend/app/services/calendar_views.py` (the class detail payload already carries `req.notes`).
- **Suggested fix:**
  - Add a "Not / özel istek" block under Talep with the original text.
  - Add a status chip: "Değerlendirilmedi" until P19-Q1 parses it; "Karşılandı / Karşılanmadı" after.
- **Acceptance:** for class 1117 the inspector shows the JASP sentence and "Değerlendirilmedi (otomatik okunmadı)".

### A-05 (Minor, backend)

- **Screen / URL:** class inspector → **Yerleşimi açıkla** (id 1117).
- **Steps:** open the explanation for a row whose request is only "Derslik" and whose definitive room is A 308.
- **Expected:** "Belirli bir derslik istenmedi" plus "Kesinleşen derslik (A 308) korundu".
- **Actual:** "✓ İstenen derslik (A 308) verildi".
- **Likely file:** `backend/app/services/calendar_views.py:1323-1331` (`wanted = req_room_ids | definitive_ids`).
- **Suggested fix:** emit separate `requested_room` and `definitive_room` lines.
- **Acceptance:** for 1117, `requested_room.state == "na"` and `definitive_room.state == "ok"`.

### A-06 (Major, importer)

- **Screen / URL:** `/classes?q=ING 302` (Bahar, admin) and the inspector of id 364 (row 366).
- **Steps:** open ING 302 §10.
- **Expected:** a soft "B Blok olmasın" (avoid B) proposal, or at least a visible "okunmadı" (unparsed) note. A B-block definitive room is flagged as against the wish.
- **Actual:**
  - Request cell "9", building `null`, warnings `[]`; the note is stored but never parsed or shown.
  - The definitive set includes **B 202**. No signal anywhere.
  - The parser still inverts it: `parse_venue_request("Mümkünse B Blok olmasın")` → `building="B", needs_room=True` (probe output in `EV`).
- **Likely files:** `backend/app/importers/normalize.py` (`parse_venue_request`, ~l.1294); `backend/app/importers/planning_list.py:250` (notes stored only).
- **Suggested fix:** P19-Q1. Run the venue parser over notes as proposals, add negation, and add a `notes_unparsed` flag shown in the inspector (A-04).
- **Acceptance:**
  - Needs-doc I1 and I2.
  - Plus: row 366 shows "B Blok olmasın (yumuşak) – B 202 ile çelişiyor".

### A-07 (Major, importer)

- **Screen / URL:** `/classes?q=NUT 256` and others (Bahar).
- **Steps:** open rows 296–298, 588, 637, 1080, 1140 (notes "A veya C blokta derslik verilmesi talep edilmektedir.").
- **Expected:** building ∈ {A, C} (soft). Rows that got B-block rooms are shown as against the wish.
- **Actual:**
  - Nothing parsed (`building: None`).
  - NUT 256 (rows 297/298) got **B 205** and NUT 362 (row 637) got **B 203**, unnoticed.
  - The parser probe on the same text returns `building="C"` only.
- **Likely file:** `backend/app/importers/normalize.py`.
- **Suggested fix:** P19-Q1 ("veya" alternatives + notes).
- **Acceptance:** needs-doc I3. NUT 256 shows "A veya C blok istendi – B 205 verildi".

### A-08 (Major, importer + frontend)

- **Screen / URL:** `/classes?kind=exams&q=PTL252` and `MBG224` (Final, admin).
- **Steps:** view the "İstenen oda" column and the inspector.
- **Expected:**
  - Three alternative sets for PTL252: {A 206}, {C 403, C 404}, {A 106, A 107}. The verdict is "Alternatifle karşılandı".
  - For MBG224: {B 202+B 203}, {B 205+B 206}, or 2 rooms in A or C.
- **Actual:**
  - PTL252: one set `[A 206, C 403, C 404, A 106, A 107]` plus an **invented building "A"**. The chip reads "A 206 C 403 +4".
  - MBG224: rooms `[B 202, B 203, B 205, B 206]`, building **C** (A lost). The chip reads "B 202 B 203 +4".
  - Evidence: `EV/shots/reqcol-PTL252.png`, `EV/curl/admin-final-exams.json`.
- **Likely files:** `normalize.py` (`parse_venue_request`); `frontend/src/components/classes/class-table.tsx` (reqRoom cell).
- **Suggested fix:** P19-Q1, plus render alternatives as "A 206 · veya C 403+404 · veya A 106+107".
- **Acceptance:** needs-doc I4 and I5.

### A-09 (Major, importer). New defect, not in the needs doc

- **Screen / URL:** `/classes?kind=exams&q=NUT401` (Final rows 105–108: NUT401, NUT402, NUT403, NUT404 oral exams).
- **Steps:** read the "İstenen oda" chip.
- **Expected:** "dersliğin büyük olmasına gerek yok" (the room need not be large) gives *no* amphitheatre requirement; a small room is fine.
- **Actual:**
  - The chip is **AMPHI** on all four rows.
  - Probe: `parse_venue_request("dersliğin büyük olmasına gerek yok")` → `tags=['AMPHI'], needs_room=False`.
  - Today the rows are LOCKED, so the solver keeps the planner's room. A re-solve or the learning memory would demand an amphitheatre.
- **Likely file:** `backend/app/importers/normalize.py` (the AMPHI keyword `büyük` is matched without negation).
- **Suggested fix:**
  - Treat "gerek yok", "olmasına gerek yok", "istemiyor" and "olmasın" as negating the preceding feature.
  - Fix the `needs_room=False` side effect.
- **Acceptance:** a unit test: that text gives `tags == []` and `needs_room is True`. The four Final rows show no AMPHI after re-import.

### A-10 (Minor, i18n)

- **Screen / URL:** `/classes` "İstenen oda" chips; find-room reasons.
- **Steps:** view in TR.
- **Expected:** Turkish labels ("Amfi", "Bilgisayar lab.", "Tıp").
- **Actual:** raw solver codes "AMPHI", "PC", "TIP" ("PC özellikli oda; istenmedi, sona alındı").
- **Likely files:** `frontend/src/components/classes/class-table.tsx`; `backend/app/services/find_room.py:428-435`.
- **Suggested fix:** map tags through one TR/EN label table.
- **Acceptance:** no `AMPHI|PC|TIP` token is visible in the TR UI.

### A-11 (Major, backend + frontend)

- **Screen / URL:** `/find-room` (teacher).
- **Steps:**
  1. Date 22.10.2026, 16:50–18:40, 42 people.
  2. Look for a PC-lab filter.
  3. Type "PC" in "Arama metni".
- **Expected:** a "Bilgisayar lab." filter. A 105 and B 207 (PC, 60 seats) listed first, as matches.
- **Actual:**
  - There is no feature filter: `GET /rooms/facets` returns `[]` for teacher and admin, because typed features were never filled from the room-master tags.
  - The text "PC" finds A 105 and B 207, but each says "**PC özellikli oda; istenmedi, sona alındı**" (PC room; not asked for; ranked lower).
  - Evidence: `EV/shots/frpc-01-results-PC.png`.
- **Likely files:**
  - `backend/app/api/v1/room_features.py:172`;
  - `backend/app/services/rooms_features.py`;
  - `backend/app/services/find_room.py:428` (`surplus` ignores text matches);
  - `frontend/src/components/findroom/find-room-view.tsx:297`.
- **Suggested fix:**
  - Expose the solver tags (PC, LAB, AMPHI, TIP) as boolean facets with TR labels.
  - Count a text match on a tag as a requested tag.
- **Acceptance:** the same search with "Bilgisayar lab." ticked lists A 105 and B 207 first, with no "istenmedi" reason.

### A-12 (Major, backend + frontend)

- **Screen / URL:** `/my-bookings`, `/approvals`, `mine.ics`.
- **Steps:** request A 105 for P11–P13 (one make-up lab, 16:50–18:40); then approve.
- **Expected:** one request "A 105 · Per 22 Eki 16:50–18:40", one approval decision, one VEVENT.
- **Actual:**
  - Three "Bekliyor" rows (P13, P12, P11), and three approval rows that the approver decides one by one.
  - Three VEVENTs (`booking-3/4/5@smartsched`).
  - The header reads "toplam 5" for 2 sessions.
  - Partial decisions are possible: P11 and P12 approved, P13 rejected, which leaves a broken lab session.
  - Evidence: `EV/shots/mine-a-01.png`, `appr-01-inbox.png`, `EV/curl/ics-parse.txt`.
- **Likely files:**
  - `backend/app/services/bookings*.py` (one Booking per period);
  - `backend/app/services/approvals.py`;
  - `backend/app/services/bookings_export.py`;
  - `frontend/src/components/bookings/my-bookings-view.tsx`;
  - `frontend/src/components/approvals/approvals-view.tsx`.
- **Suggested fix:**
  - Give every period of one submission a shared `group_id`.
  - Group by it in the lists, decide the group in one action (per-period decision behind "Ayrıntılı"), and merge contiguous periods into one VEVENT.
- **Acceptance:** P11–P13 gives 1 list row, 1 inbox row, 1 decision and 1 VEVENT 16:50–18:40. Totals count sessions.

### A-13 (Minor, frontend)

- **Screen / URL:** `/my-bookings` "Taleplerim".
- **Steps:** request P11–P13.
- **Expected:** chronological order (P11, P12, P13).
- **Actual:** P13, P12, P11.
- **Likely file:** `my-bookings-view.tsx`.
- **Suggested fix:** sort by date, then period start.
- **Acceptance:** the e2e list order is ascending.

### A-14 (Major, backend)

- **Screen / URL:** `GET /calendar/feeds/{token}/mine.ics` and `/room/20.ics`.
- **Steps:** create the private links in My Bookings; curl both feeds; parse with `icalendar`.
- **Expected:** the academician's classes are in their feed (once linked), and room feeds contain the published classes.
- **Actual:**
  - `mine.ics` has 5 VEVENTs, all bookings and no classes.
  - The A 308 room feed has **0** VEVENTs, although the active run holds PSY 277 (Mon P3–P5), FYT 117 and ACU 96AA that day.
  - Evidence: `EV/curl/ics-mine.ics`, `EV/curl/ics-room-A308.ics`.
- **Likely file:** `backend/app/api/v1/calendar_sync.py:144-160` (feeds built from bookings only).
- **Suggested fix:** new ticket P19-T4: include active-run assignments in room, department and room-group feeds; add a personal class feed after P19-L1.
- **Acceptance:** `room/20.ics` for Güz week 5 contains "PSY 277" Mon 10:10–12:30 Europe/Istanbul.

### A-15 (Minor, backend)

- **Screen / URL:** `mine.ics`.
- **Steps:** read SUMMARY.
- **Expected:** "Telafi: PSY 277 (C 303)", or the note, as SUMMARY.
- **Actual:** "C 303 – P7"; the note only in DESCRIPTION.
- **Likely file:** `backend/app/services/bookings_export.py`.
- **Suggested fix:** SUMMARY = note (truncated) + room; time in DTSTART only.
- **Acceptance:** SUMMARY contains the note's first 40 characters.

### A-16 (Minor, backend i18n)

- **Screen / URL:** bell (TR and EN).
- **Steps:** an approver rejects with suggestions.
- **Expected:** one language.
- **Actual:**
  - TR: "… Öneri / suggestions: B 207."
  - EN: "… Note: lab busy Öneri / suggestions: A 105, B 207."
  - Titles and bodies do follow the recipient's language (`EV/curl/notif-en-user.txt`).
- **Likely file:** `backend/app/services/approvals.py:931`.
- **Suggested fix:** take the label from the recipient language.
- **Acceptance:** the TR body has "Öneri:" and the EN body has "Suggestions:".

### A-17 (Minor, i18n)

- **Screen / URL:** `/profile`.
- **Steps:** open as TEACHER in TR.
- **Expected:** "Öğretim elemanı" (as the sidebar shows).
- **Actual:** "ogretmen@… · Teacher".
- **Likely files:** `frontend/src/components/admin/profile-view.tsx`; `backend/app/services/bookings_perms.py` (`ROLE_DEFAULTS` name "Teacher").
- **Suggested fix:** use the role label key, not the DB name, for seeded roles.
- **Acceptance:** the TR profile shows "Öğretim elemanı".

### A-18 (Minor, a11y i18n)

- **Screen / URL:** every sheet or dialog (book sheet, approvals sheet, confirm dialogs).
- **Steps:** read the accessible name of the close button in TR.
- **Expected:** "Kapat".
- **Actual:** "Close".
- **Likely files:** `frontend/src/components/ui/sheet.tsx:78`, `ui/dialog.tsx:83`.
- **Suggested fix:** use `t("common.close")`.
- **Acceptance:** in a TR aria snapshot no button is named "Close".

### A-19 (Minor, importer i18n)

- **Screen / URL:** class inspector (ACU 303 row 609, NUT401, PTL252).
- **Steps:** view the warnings in TR.
- **Expected:** Turkish warnings.
- **Actual:** "start time 12:00 not on the grid; snapped to P5 (11:50)", "start time 15:00 falls in a break; snapped to P9".
- **Likely file:** `backend/app/importers/normalize.py:400` and its siblings.
- **Suggested fix:** emit `{tr, en}` pairs, like `calendar_views` does.
- **Acceptance:** the TR inspector shows "12:00 ders saati değil; P5'e (11:50) kaydırıldı".

### A-20 (Major, a11y)

- **Screen / URL:** `/bookings` book sheet (keyboard).
- **Steps:** open a free cell with Enter, then press Tab 12 times.
- **Expected:** focus stays inside the modal sheet.
- **Actual:** after "Close", focus moves to a SPAN, then `<body>`, then the page's "İçeriğe atla" link behind the modal (`EV/scripts/kbd.mjs` output).
- **Likely files:** `frontend/src/components/ui/sheet.tsx`, `components/bookings/book-sheet.tsx`.
- **Suggested fix:** use a modal sheet with a focus trap, and remove the extra focusable SPAN.
- **Acceptance:** 20 Tabs inside the open sheet keep `document.activeElement` inside `[data-testid=book-sheet]`.

### A-21 (Major, a11y)

- **Screen / URL:** find-room booking, approvals Onayla / Reddet, Taleplerim "Talebi geri çek", My Bookings "İptal et".
- **Steps:** perform each action.
- **Expected:** focus moves to a sensible target (the next row, or the list heading). The decided approval sheet closes, or moves to the next item.
- **Actual:**
  - `document.activeElement` is `<body>` after every one of these actions.
  - After Onayla, the approval sheet stays open over the list, and a second row cannot be clicked until Esc.
  - This extends T4 with the find-room booking and the My Bookings cancel.
- **Likely files:** `components/findroom/find-room-view.tsx`, `components/approvals/approvals-view.tsx`, `components/bookings/my-bookings-view.tsx`.
- **Suggested fix:** move focus explicitly after each mutation; auto-advance the approvals sheet to the next open item.
- **Acceptance:** after each action, `activeElement` is not `BODY`. After approving, the sheet shows the next request, or closes with focus on the list.

### A-22 (Major, a11y)

- **Screen / URL:** `/bookings` (keyboard).
- **Steps:** Tab to "Önceki gün", the lens tabs and the nav links.
- **Expected:** a visible focus indicator (WCAG 2.4.7).
- **Actual:**
  - The computed style at focus is `outline: none 0px` and `box-shadow: none`.
  - The crop shows no ring on "Önceki gün". The nav link's grey fill looks the same as the active-page highlight.
  - Evidence: `EV/shots/focus-strip.png`.
- **Likely files:** `frontend/src/components/ui/button.tsx`, the segmented control, `components/shell/sidebar.tsx`.
- **Suggested fix:** add `focus-visible:outline-2 focus-visible:outline-(--focus)` to these primitives.
- **Acceptance:** a Playwright check: every Tab stop on `/bookings` has a non-`none` outline or box-shadow at `:focus-visible`.

### A-23 (Minor, frontend)

- **Screen / URL:** ⌘K palette (teacher).
- **Steps:** search "PSY 277", "A 308", "PSI 213".
- **Expected:** rooms the teacher may view are found; the hint matches what works.
- **Actual:**
  - Every search returns "eşleşen bir şey yok. **Ders kodu (MAT 112), derslik (A 206) veya soyadı deneyin.**"
  - Search is disabled for non-planners.
  - Admin finds all three.
- **Likely file:** `frontend/src/components/shell/command-palette.tsx:74-75`.
- **Suggested fix:** for `room.view`, search rooms through `/bookings/rooms` and the user's own bookings; show the course hint only to planners.
- **Acceptance:** as teacher, "A 308" opens the room info.

### A-24 (Major, frontend + backend)

- **Screen / URL:** `/bookings?date=2026-10-19` (Güz week 5) before the Güz term run was published.
- **Steps:** open a teaching Monday while the active Güz run was the grid import #3 (weeks 1–2 only).
- **Expected:** a banner such as "Bu hafta için yayımlanmış ders programı yok; dolu görünmeyen derslikler derste olabilir", or rooms treated as unknown.
- **Actual:**
  - Every cell showed "Boş" and was bookable (`EV/shots/t-bookings-2026-10-19.png`).
  - After run #10 was published, the same day showed 139 timetable slots, PSY 277 in A 308 among them (`EV/curl/grid-t-20261019.json`).
  - A teacher could book over a real class.
- **Likely files:** `backend/app/services/bookings*.py` (`grid`); `frontend/src/components/bookings/booking-grid.tsx`.
- **Suggested fix:** the grid payload carries `timetable_coverage: false` when the active run has no assignment for the date's week; the UI shows the banner.
- **Acceptance:** with only run #3 active, `GET /bookings/grid?date=2026-10-19` returns `timetable_coverage=false` and the banner renders.

### A-25 (Minor, frontend)

- **Screen / URL:** `/bookings` timetable cell ("Ders programı").
- **Steps:** click PSY 277 in A 105.
- **Expected:** course, section, programme/year, weeks, and "Sizin dersiniz" when linked.
- **Actual:** only "A 105 P7 yayımlanmış ders programında PSY 277 dersine ayrılmış. Ders programındaki saatler rezerve edilemez."
- **Likely file:** `frontend/src/components/bookings/bookings-view.tsx` (`slot-info`).
- **Suggested fix:** include section, programme and year in the grid slot label payload.
- **Acceptance:** the slot sheet shows "PSY 277 · Psikoloji (İngilizce) 2. sınıf".

### A-26 (Minor, a11y)

- **Screen / URL:** `/my-bookings` checkboxes.
- **Steps:** read the aria snapshot.
- **Expected:** a unique name per row.
- **Actual:** two rows are both named "22.10.2026 A 105 rezervasyonunu seç" (no period).
- **Likely file:** `my-bookings-view.tsx`.
- **Suggested fix:** add the period and time to the label.
- **Acceptance:** the names are unique.

### A-27 (Minor, mobile)

- **Screen / URL:** `/my-bookings` at 390 px.
- **Steps:** measure the tap targets.
- **Expected:** at least 24×24 px (WCAG 2.5.8); 44 px preferred.
- **Actual:**
  - "Salon bilgisi: C 303" button is 41×20.
  - The date/note button is 298×16.
  - The note is truncated on one line ("… (42 ö").
- **Likely file:** `my-bookings-view.tsx`.
- **Suggested fix:** `min-h-11` on phone; wrap the note on two lines.
- **Acceptance:** the audit script finds no target under 24 px.

### A-28 (Minor, performance; re-measure on an idle host)

- **Screen / URL:** `/classes` (Bahar, admin), `/timetable?subject=instructor:157`.
- **Steps:** open the page and wait for rows.
- **Expected:** rows in ≤ 3 s.
- **Actual:** Bahar 1 524 classes: 13.1–13.9 s until "N ders gösteriliyor". Final: 6.9–7.7 s. The instructor week view was still "Yükleniyor" at 3.5 s. (Load average about 25 on 4 cores.)
- **Likely files:** `frontend/src/components/classes/classes-page.tsx`; `backend/app/services/calendar_views.py` (`classes`).
- **Suggested fix:** paginate or virtualise; cache per run.
- **Acceptance:** on an idle host, Bahar rows appear in ≤ 3 s.

### A-29 (Minor, frontend)

- **Screen / URL:** admin `/bookings`, `/classes`.
- **Steps:** load the page.
- **Expected:** no console errors.
- **Actual:** `PAGEERROR Minified React error #418` (hydration mismatch).
- **Likely file:** whatever renders date/term text before hydration (the timetable already uses `AfterHydration`).
- **Suggested fix:** wrap it in `AfterHydration`, or render the same on the server.
- **Acceptance:** 0 page errors in the e2e.

### A-30 (Major, motion; T2 confirmed on teacher surfaces)

- **Screen / URL:** `/bookings` previous / next day.
- **Steps:** delay `/bookings/grid` by 1.5 s; press "Sonraki gün".
- **Expected:** the stale grid is dimmed, the pending date is shown, and `aria-busy` is set.
- **Actual:** during the fetch, grid opacity is 1, no `aria-busy`, and the header still says "Perşembe 22 Ekim 2026" (`EV/shots/stale-during-fetch.png`).
- **Likely file:** `components/bookings/booking-grid.tsx`, `bookings-view.tsx`.
- **Suggested fix:** T2.
- **Acceptance:** T2's acceptance.

### A-31 (Major, motion; T1 confirmed)

- **Screen / URL:** find-room **Ara**; book sheet **Rezerve et**.
- **Steps:** delay the POST by 1.5 s; click.
- **Expected:** a busy label ("Aranıyor…", "Rezerve ediliyor…") and `aria-busy="true"`.
- **Actual:**
  - `{text: "Bu saati rezerve et", ariaBusy: null, disabled: true, spinner: true}`.
  - "Ara": `{text: "Ara", busy: null, disabled: true}` with a looping spinner.
- **Likely files:** `components/findroom/find-room-view.tsx`, `components/bookings/book-sheet.tsx`.
- **Suggested fix:** T1.
- **Acceptance:** T1's acceptance.

### A-32 (Minor, motion; new surface, not in T3)

- **Screen / URL:** `/my-bookings` "Taleplerim" row expand / collapse.
- **Steps:** expand and collapse one row (measure script).
- **Expected:** ≤ 3 dropped frames; no LoAF over 100 ms.
- **Actual:** 64 dropped frames for 2 interactions; worst long frame 451 ms; one frame with 121 ms render.
- **Likely file:** `my-bookings-view.tsx` (height animation of the expanding row).
- **Suggested fix:** animate the content with transform/opacity and keep the height instant, or use the `layout` prop on the row only.
- **Acceptance:** the probe gives ≤ 3 dropped frames per interaction on an idle host.

---

## 4. Motion findings

The probe is `measure.mjs` (audit.md §2) adapted to the teacher account and Güz dates. The script is `EV/scripts/measure-teacher.mjs` and the log `EV/motion-cpu1.log`.

Conditions:
- 1× CPU, headless Chromium 141, production bundle, 1440×900.
- The host was 6× oversubscribed. That inflates "dropped" but not "over-ceiling" or the reduced-motion results.
- The 4× CPU device check was not run: on this host it would measure the scheduler, not the app.

```
Motion audit: academician surfaces (2026-10-15, cc9c45d, 1× CPU, host load ≈ 25/4 cores)
| Interaction | dropped (1× CPU; per interaction) | LoAF > 50 ms (worst) | Layout events | over-ceiling | reduced motion | reduced transparency |
| no-op click ×4 (baseline) | 3 (0.8) | 0 (0 ms) | 1 | none | – | – |
| bookings: hover sweep 24 free cells | 9 (0.4) | 1 (53 ms) | 24 | none | – | – |
| bookings: drag span, pointer moves only | 0 | 0 | 1 | none | – | – |
| bookings: drag span + release → book sheet | 7 (7) ✗ | 2 (78 ms) | 0 | none | – | – |
| bookings: book sheet open + close (Esc) | 90 (45) ✗ | 8 (387 ms) ✗ | 10 | none | end state ✓ (transform none, 0 moving animations) | inconclusive (bg reads rgba(0,0,0,0): T13) |
| bookings: lens grid → free → grid | 8 (4) ✗ | 11 (322 ms) ✗ | 11 | none | – | – |
| bookings: next day ×2 (grid refetch) | 63 (31.5) ✗ | 13 (147 ms) ✗ | 9 | none | – | – |
| shell: bell open + close | 39 (19.5) ✗ | 7 (134 ms) ✗ | 5 | none | – | inconclusive (T13) |
| bookings: calendar sync sheet open + close | 25 (12.5) ✗ | 5 (297 ms) ✗ | 8 | none | – | – |
| find-room: search + results arrive | 83 (83) ✗ | 10 (359 ms) ✗ | 6 | none | – | – |
| my-bookings: tabs upcoming → past → upcoming | 49 (24.5) ✗ | 7 (192 ms) ✗ | 8 | none | – | – |
| my-bookings: Taleplerim row expand + collapse | 64 (32) ✗ | 6 (451 ms) ✗ | 4 | none | – | – |
| in-app reduced motion (data-motion="reduced"): book sheet | – | – | – | – | 0 moving animations ✓ | – |
```

| Moment | Purpose | Non-motion signal | Busy state | Focus after | Verdict |
|---|---|---|---|---|---|
| Free cell → book sheet | "where did my choice go": the sheet carries room, period and date | ✓ title "C 303 · P7–P8 Perşembe 22 Ekim 2026" | – | ✓ moves into the sheet (period select) | ✗ trap leaks (A-20); slow open (T3) |
| Rezerve et / Talep et | "did it work" | ✓ toast with room, date, periods; the status chip has icon + text ("Bekliyor", "Onaylandı", "Reddedildi") | ✗ spinner only, no `aria-busy` (A-31 / T1) | ✗ `<body>` after a find-room booking (A-21) | ✗ |
| Find room search | "what changed" | ✓ summary "10 boş oda · 1/1 tarih açık"; holiday shows "0/1 dates open" | ✗ spinner only, label unchanged "Ara" (A-31) | – | ✗ 83 dropped (T3) |
| Day navigation | "what changed" | ✗ old date and old grid stay at full strength (A-30) | ✗ none | ✓ stays on the nav button | ✗ |
| Lens switch (Çizelge ↔ Boş saatler) | "where it went" | ✓ the selected pill + URL `lens=free` | – | ✓ | ✗ LoAF 322 ms |
| Bell | "did something happen" | ✓ "Bildirimler, 3 okunmamış" in the label; live region "4 yeni bildirim" | – | ✓ | ✗ 19.5 dropped per open (T3) |
| Approve / Reject / Withdraw / Cancel | "did it work" | ✓ toasts ("Onaylandı: A 105.", "Reddedildi. Talep edene bildirildi.", "Talep geri çekildi.", "1 iptal edildi, 0 olduğu gibi kaldı") | – | ✗ `<body>` (A-21, T4) | ✗ |
| Taleplerim expand | "where it went" | ✓ chevron + aria-expanded | – | ✓ | ✗ 451 ms frame (A-32) |
| Idle pages | – | – | ✓ no looping animation on idle `/bookings` or `/my-bookings` | – | ✓ |

All one-shot animations stayed under the 300 ms ceiling ("over" is empty for every interaction).

---

## 5. Gap check against `docs/testing/2026-10-15-academician-needs.md`

Ticket ids are from `docs/ROADMAP.md` "Phase 19 tickets" and `docs/review/2026-10-15-phase19-engineering.md` §5. "Proposed" means no ticket exists yet; the proposal follows the table.

| # | User story / scenario (needs doc) | Today | Ticket |
|---|---|---|---|
| 1 | §5.1 Class: "As an academician I see where my class is this week" | **Missing.** No User↔Instructor link; the teacher's timetable route is a dead end (A-01, A-02) | P19-L1 adds `Instructor.user_id`, but no UI ticket. **Proposed P19-T1** |
| 2 | §5.1 Person: "As the academician (TEACHER login) I see my own requests and their outcome, and add a preference" | **Missing.** "Taleplerim" covers only room-booking approvals, not the department's planning requests | No ticket (roadmap "academician self-service portal" is only a suggestion). **Proposed P19-T2** |
| 3 | M1: academician opens "Taleplerim" and sees the verdict per week, and nobody else's requests | **Missing** | **Proposed P19-T2** (needs P19-L1, P19-M1) |
| 4 | M2: the coordinator's reason ("kapasite") shows in the academician's view | **Missing.** The coordinator side is planned (P19-F2); the academician side is not | P19-F2 (coordinator) + **P19-T2** |
| 5 | §5.3.5 / M6: after publish, affected instructors get in-app + e-mail notices of only their changes | **Missing.** The bell exists, but only for booking decisions (works, A-16) | Owner UX decision (ROADMAP "Publish notifications") with no ticket id. **Proposed P19-T3** |
| 6 | Q11: the academician sees only their own data | **Partly.** No planning data is exposed to the teacher (403s); booking notes of others are visible (`*.view_other_notes`, CRBS default) | P19-T1/T2 must scope by link |
| 7 | Q12: the academician's own wish is a lower-ranked soft preference, shown next to the department form | **Missing** | **Proposed P19-T2** |
| 8 | I1: negation not inverted ("Mümkünse B Blok olmasın") | **Partly.** In the real data the text is in notes, so no wrong rule, but no "unparsed" signal and the B 202 conflict is silent (A-06). The parser still inverts | P19-Q1 (add the "unparsed" flag to its acceptance) |
| 9 | I2: notes become proposals with `source_ref` | **Missing** (A-04, A-06) | P19-Q1 + P19-I6 |
| 10 | I3: "A veya C blokta" → building ∈ {A, C} | **Missing** (A-07) | P19-Q1 |
| 11 | I4 / I5: room alternatives (PTL252, MBG224) and "Alternatifle karşılandı" | **Missing.** Flattened, plus an invented building (A-08) | P19-Q1 + P19-M1/F2 |
| 12 | I6: accessibility ("Giriş kata yakın", rows 609/610) as a person-level room requirement | **Missing.** Not shown, not parsed; the room master has no access attribute | P19-Q1 (parse). Storage and room attribute: **Proposed P19-T5** (roadmap suggestion 10, no ticket) |
| 13 | I12: an e-mail from the instructor keeps the requester and appears in their history | **Missing** | P19-A3 (EML) + P19-L1 |
| 14 | L1: "A Blok tercih" for this persona (8/8, 2 terms), no room suggestion | **Missing** | P19-L1…L4, P19-F3 |
| 15 | L7: weekday question, not a rule | **Missing** | P19-L3, P19-F3 |
| 16 | §3.2: exam room = lecture room | **Missing** | P19-L2/L3 |
| 17 | §2.2: equipment / software wishes (JASP, JAMOVI, barkovizyon, "amfi tipi") | **Missing.** Notes not shown (A-04); no room attribute for software or AV | **Proposed P19-T5** |
| 18 | Make-up session: find a free room and book it | **Works** (C 303 booked directly); a PC lab cannot be filtered (A-11); the session is split per period (A-12) | Booking module (CRBS parity), no P19 ticket. A-11/A-12 to the frontend and backend sweep |
| 19 | A booking that needs approval (PENDING) and "my requests" | **Works** end to end (request, approver sheet, decision, bell, statuses, ICS status) | – (A-12, A-13, A-21) |
| 20 | Calendar sync of own bookings (ICS) | **Works.** `text/calendar`, Europe/Istanbul VTIMEZONE, TENTATIVE / CONFIRMED / CANCELLED, parses in `icalendar` 7.3 | – (A-15) |
| 21 | Calendar sync of own classes | **Missing** (A-14) | Roadmap suggestion 11 only. **Proposed P19-T4** |
| 22 | Coordinator: one person's whole term with request history and satisfaction (§5.1 Person, People tab) | **Partly.** `/timetable?subject=instructor:157` shows the week; no history, satisfaction or requests; `/classes` cannot filter by instructor id | P19-M1, P19-F1 |
| 23 | Coordinator: "who got what they asked for" (Matching, M8) for this person's sections | **Missing.** The run #8 report lists unplaced rows and aggregate soft shortfalls ("Talep edilen derslik: 110") only; satisfied requests are not listed | P19-M1, P19-F2 |

Proposed tickets (no existing ticket):

- **P19-T1 "Derslerim" (my classes).**
  - Endpoint `GET /me/classes?term_id&week|range`, from the active run of each term; allowed with `room.view` plus the P19-L1 link.
  - A "Derslerim" block on `/my-bookings` with week/term toggle, room, weeks and lock state; a link from each class to "telafi için oda bul" (prefilled headcount, tags, building).
  - Admin picker to link a user to an instructor.
  - Acceptance: A-02.
  - Depends on P19-L1.
- **P19-T2 "Taleplerim" for planning requests (academician self-service).**
  - Read the department's rows for the linked instructor: original text, parsed meaning, verdict per week, coordinator reason.
  - "Tercih ekle" creates a lower-ranked soft preference (Q12) that waits for coordinator review.
  - Acceptance: needs M1, M2, Q11, Q12.
  - Depends on P19-L1, P19-M1.
- **P19-T3 Publish-change notifications per academician.**
  - On activate, diff against the previous active run per instructor; one in-app notice and one e-mail digest with only that person's changes; per-user e-mail opt-out.
  - Acceptance: needs M6.
  - Depends on P19-L1, P19-S2.
- **P19-T4 Class calendar feeds.**
  - Room, department and room-group feeds include active-run assignments.
  - New `mine-classes.ics` for linked users; contiguous periods merged into one VEVENT; SUMMARY = course + room.
  - Acceptance: A-14, A-15.
- **P19-T5 Room equipment, software and access attributes.**
  - Room-master columns: `step_free`, `entrance_floor`, `av` (projector / whiteboard), `seating` (fixed / armrest), `software` (list).
  - Request features that can match them (JASP, JAMOVI, "amfi tipi", "kolçaklı sandalye olmasın", "giriş katı").
  - Pre-check says when no room has a needed attribute (needs I6).
- **Extend P19-06** ("no dead nav links") to cover 403 dead ends for each role: A-01, A-03 and A-23.

---

## 6. Enhancements, ranked

1. **"Derslerim" plus a home page for the teacher** (P19-T1 + the A-01 fix). The academician's first question is "where am I teaching this week". Today the first screen says no programme exists and offers to create one.
2. **"Telafi" (make-up) shortcut from a class.**
   - "Bu ders için boş oda bul" prefills the headcount (42), the class's room needs (PC lab for PSY 277 lab), the preferred building (A block, this person's 8/8 history) and the class's time band.
   - The booking note is prefilled "Telafi: PSY 277".
   - Builds on find-room, which already ranks by fit and explains each result.
3. **Group multi-period bookings** (A-12): one session is one request, one decision and one calendar event.
4. **Room facets that match how academicians ask** (A-11, P19-T5): "Bilgisayar lab.", "Amfi", "Projeksiyon", "Yazılım: JASP/JAMOVI", "Giriş katı".
5. **Show every free-text wish next to its outcome** (A-04): in the coordinator's inspector now, in the academician's Taleplerim later (P19-T2). Unparsed wishes should say "okunmadı", never disappear.
6. **Recurring make-up or lab sessions for teachers through approval.**
   - The TEACHER role has `book_single.create` only (`allow_recur: false` in the grid), so a weekly extra lab needs N single bookings.
   - Offer `book_recur.request` (an approver confirms) as a per-installation option.
7. **Teacher palette search** (A-23): rooms, own bookings and (after P19-T1) own courses.
8. **Classes in calendar feeds** (P19-T4): room feeds with classes help every teacher check a room before booking.
9. **Coordinator: from the instructor timetable to the filtered class list.**
   - Add a "Bu öğretim elemanının dersleri" link carrying `instructor:<id>` to `/classes`.
   - Add an instructor-id filter; today it matches by folded name only (`classes-model.ts:132`).
10. **Banner when a week has no published timetable** (A-24). It protects real classes from being booked over during the gap between import and publish.
