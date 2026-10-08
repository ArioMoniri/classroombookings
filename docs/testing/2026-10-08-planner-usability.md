# Planner usability test: "Fatih Bey" against the real backend (2026-10-08, user-tester)

Persona: Fatih Bey, the classroom planning officer. He is not technical and uses Excel every day. He
used SmartSched end to end on the real 2026 Bahar and Final workbooks, through the UI only. The API
and DB were used only to confirm what the UI showed.

## Setup (as run)

- Commit `56e7f36` (detached), isolated worktree.
- Backend: FastAPI on SQLite, fresh DB in the scratchpad (`fatih.db`), port **8100**, `ENVIRONMENT=dev`,
  `ADMIN_EMAIL=fatih@smartsched.local`, no `ANTHROPIC_API_KEY`.
- Imports, all through `python -m app.cli`:
  - `import room-master tests/fixtures/room_master.csv`: 87 rooms.
  - `import weekly-grid …bahar_derslikler_takvimi_2026.xlsx --term 2026-BAHAR --year 2026`: 19 weeks,
    9 043 board assignments, runs #1 (COURSE) and #2 (EXAM).
  - `import planning-list …bahar_derslik_planlama_listesi_v5.xlsx --term 2026-BAHAR`: 1 524 requests,
    1 271 sections, 5 rows skipped.
  - `import exam-list …final_planlama_listesi_2026_v2.xlsx --term 2026-FINAL`: 921 exam requests.
  - `import weekly-grid …final_derslikler_takvimi_2026_v2.xlsx --term 2026-FINAL --year 2026 --term-kind FINAL`:
    runs #3 and #4.
  - `seed-admin`.
- Frontend: `npm ci`, then `npm run build` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8100` and
  `NEXT_PUBLIC_API_MOCK=0`, then `next start -p 3400`.
- UI driver: Playwright 1.56 library with the pre-installed Chromium (`/opt/pw-browsers`), a persistent
  profile, 1440×900 (390×844 for mobile), locale `tr-TR`, timezone Europe/Istanbul.
- Screenshots: `SHOTS=/tmp/claude-0/-home-user-classroombookings/ac8cf3be-4f7b-53da-a7ff-63cf01e137b0/scratchpad/shots`.
  Every `shots/…` path below is relative to this directory.

Runs created during the test:

| Run | What | Result |
|---|---|---|
| #5 | Bahar week 3: 2 classes left out, 1 pin, 5 rules, 1 pre-check fix | INFEASIBLE, best effort 662/683 placed, 11 s |
| #6 | child of #5 via the "move BES 560 to P16–P18" diagnosis fix | INFEASIBLE, 663/683, 32 s |
| #7 | Final exams, exam period (TERM) | INFEASIBLE, 615/629, 17 s solve, about 20 s end to end |
| #8 | Bahar week 3 plus the infeasible request (ING 302 with 102 students pinned to B 201, 30 seats) | INFEASIBLE, 661/683, 38 s |

## Scenario table

Severity is the worst finding in the row. B = BLOCKER, M = MAJOR, m = MINOR, P = POLISH.

| # | Step | Fatih expected | What happened | Sev |
|---|---|---|---|---|
| 1.1 | Log in | Lands on his current term | Login is fine; the wrong-password message is clear Turkish. He lands on **2026-FINAL**, the last imported term (`shots/01c_dashboard.png`) | M |
| 1.2 | Find the Bahar dashboard | Obvious term switch | The term switcher is easy and the toast confirms "2026-BAHAR dönemine geçildi" (`shots/02b_bahar_dashboard.png`). The subtitle reads "15 haftanın 15. haftası" in October, so the heatmap shows week 15. The two runs are both "Tüm dönem · 100/100" with no "ders/sınav" label | m |
| 1.3 | Read the dashboard at a glance | "How full are my rooms, what is waiting for me" | Tiles are readable: 44 %, 231 waiting for review, 1271 sections. "Table", "REGULAR" and "#2 · soft 100" are jargon or English. On the FINAL term the "Bekleyen talepler" list shows **Bahar** requests (not filtered by term) | M |
| 2.1 | Ctrl+K, type "PHAR 240" | The course | "PHAR 240 için sonuç yok — … ders kodu (MAT 112) deneyin". The palette only searches rooms and runs (`shots/03a_palette_phar240.png`) | M |
| 2.2 | Talepler, search "PHAR240" | Where and when it meets | 3 rows found with day and time (Pzt P1–P3 …). The room column shows only "≥ 80 🔒". The definitive room **A 206** is in the DB but not shown in the row or the drawer (`shots/04c_requests_phar240.png`, `shots/04d_request_detail.png`) | M |
| 2.3 | Çizelge, find PHAR 240 | The board, filtered to the course | The grid opens on **#4 2026-FINAL, W7** (empty) although Bahar is selected (`shots/05a_timetable_default.png`). After choosing #1, W3, Monday and filtering "A 206": the board has **HEM 334 / NRS 304** there, not PHAR 240. Every board card shows "0/92". The grid can only be filtered by room, not by course | M |
| 3.0 | Open /generate | The studio | The first open shows a red toast "**500 Internal Server Error**": two parallel requests both create the draft and hit `UNIQUE constraint failed: studio_drafts…` (`shots/07a_studio_open.png`) | M |
| 3.1 | Scope: one week, week 3 | Week 3 only | Choosing "Bir hafta" pre-selects W1, and clicking W3 **adds** it, so he plans weeks 1 and 3 ("2 hafta boyunca…"). He had to un-click W1 (`shots/08a_scope_week.png`) | M |
| 3.2 | Leave out two classes | Count goes 883 → 881 | The toggles work (FZT 270 summer clinic, FZT 3002). The footer says "**883** plana dahil · 2 plan dışı" | m |
| 3.3 | Change enrolment (PHAR 240 §1 80 → 130), then revert | Warning, then undo | Inline edit works and shows "içe aktarılan değer 80 idi" with a revert button. The warning is English ("A 206 has 92 seats, this class has 130") and **stays after the revert**. The "Değişti" chip stays at 0 (`shots/09a_enrolment_changed.png`, `shots/09b_enrolment_reverted.png`) | m |
| 3.4 | Pin a class to A 206 | Pinned | The pin popover lists only rooms that fit, with A 206 pre-selected. The pin is shown on the row and in the rules ("PHAR 240 §1 A 206 dersliğinde kalsın") (`shots/09c_pin_popover.png`) | OK |
| 3.5 | Write "Hemşirelik 1. sınıf dersleri 17:30'dan sonra olmasın" with no AI key | Clear message | "Kendi cümlenizle kural yazmak için YZ gerekir. Yönetici Ayarlar → YZ'den açabilir." His text is kept. There is no link to Settings and no hint that the **same rule exists as a chip and as a template** a few pixels below (`shots/10b_nl_no_key.png`) | m |
| 3.6 | The same rule via the template "Belirli saatten sonra ders olmasın" (Hemşirelik, 1. sınıf, P11 ends 17:30) | Applies to nursing first-years | "**0 derse uygulanıyor — Hiçbir dersle eşleşmiyor**". The DB has 9 "Hemşirelik" year-1 sections. Cause: case mismatch in the cohort key (see B1) (`shots/14a_evening_rule_zero_match.png`) | **B** |
| 3.7 | Add a template rule: "PHAR 240 her zaman A 206 … 23 Şubat'tan itibaren" | Persona task "move PHAR 240 to A 206 from 23 Feb" | Works as `room_pin`, weeks 4–19. The sentence reads "4. hafta'**den** itibaren". Week chips show "W4" with no date, so he had to know that 23 Feb is week 4. "PHAR 240 §1" appears twice (lecture and lab) and the two can't be told apart (`shots/13a_always_in_room_filled.png`) | m |
| 3.8 | Upload his 3-row Excel (Ders Kodu / Tercih Edilen Derslik / Not) | Column mapping, then rules | Excellent: all three columns are auto-mapped, and the review shows "3 hazır", the source row, "Mümkünse · Yüksek". After adding, **HEM 106 → C 201 matches 0 classes**: the request is merged into the joint lecture "BES 128 + HEM 106" (`shots/15c_mapping.png`, `shots/16a_upload_review.png`, `shots/16b_rules_with_upload.png`) | M |
| 3.9 | Pre-check, apply one fix | Readable list, one-click fix | Groups like "7 × aynı saatte aynı dersliğe kilitli" have plain Turkish cards. The fix "MBT 698 + MBT 598 için A 104, A 103, A 105 dersliklerini kullan" is applied with an undo toast (174 → 173 issues). The sentences say "882 dersi" while the summary says 883 (`shots/17a_precheck.png`, `shots/18a_locked_overlaps.png`) | m |
| 3.10 | Generate and wait | A plan for week 3 | A confirm dialog ("Engel var … yine de oluştur") appears, then run #5 finishes in 11 s with a result card in the studio. During the run, autosave failed with "**Son değişikliğiniz kaydedilemedi. (500 Internal Server Error)**" (SQLite `database is locked`) (`shots/19c_run_progress.png`) | M |
| 4.1 | Read the run report | "Is my plan OK? What is missing?" | A big **green 100/100 ring with a green tick** next to "Kısmi · 662/683 yerleşti". The cards are English and technical ("input conflict: MAT 112 §1 (#1) (day 4 P7-P9) … 'INS:1 (…)'", `no_instructor_overlap`, "manual"). The 21 unplaced classes are cards **#173–#193 of 196**, after 131 input-conflict cards. "İstem: Studio draft #1 v9: 683 events (882 classes)…" (`shots/20b_run5_report.png`) | **B** |
| 4.2 | Apply one diagnosis fix | Fix and re-run | "alternative periods on the same day: P16-P18 in C501" → **Uygula** → toast "Düzeltme uygulandı — yeniden çözüm kuyruğa alındı / #434 placed in C 501 on day 4 P16-P18 and locked" → child run #6, 663/683 (`shots/22a_unplaced_card.png`, `shots/23a_run6.png`) | m |
| 4.3 | Find the data problems in his own Excel | List of his mistakes | The pre-check shows them well: 7 locked overlaps, 33 rooms smaller than the class, 81 instructor and 50 cohort clashes between fixed times. It does **not** say which Excel row or sheet they come from. It also does not say that the published board disagrees with the planning list (PHAR 240: list A 206, board D 106) | M |
| 5.1 | Drag a class to another room | Moves, can undo | ADS 112 A 107 → A 106 shows the live status "Uygun", then the toast "ADS 112 → A 106 Çar 14:20–15:50 taşındı · Geri al", and the class is locked as MANUAL. In the first attempts dnd-kit **auto-scrolled the grid sideways** and the card landed in the wrong column (`shots/25a_drag_legal_hover.png`, `shots/28a_drag_ADS112_to_A106.png`) | M |
| 5.2 | Move via the dialog | Pick a free room | The dialog previews live and disables Confirm. It lists all 58 rooms with no free or busy hint, so for PHAR 220 §1 (Wed P3–P5) he tried **44 rooms, none free**. It worked at P13 (A 102). There is no "from this date on" option (`shots/29b_move_dialog_A206.png`, `shots/31b_after_dialog_move.png`) | M |
| 5.3 | Illegal move (PDL 112 §1, 49 students → A 104, 41 seats; FZT 222, 75 students → A 104) | Clear Turkish reason | Drag: "Taşıma reddedildi: **capacity too small, slot occupied** (ANS 214 §1)". Dialog: "capacity too small" with no numbers. The drag target outline sits one period lower (P4–P6) than the class (`shots/28c_drag_PDL112_to_A104_hover.png`, `shots/29d_move_dialog_too_small_free_slot.png`) | M |
| 5.4 | Switch week, day and zoom | Fast, clear | Fast (about 3 s for the week view). The week view is a wall of tiny unlabeled bars. For the one-week run, W4 is empty with no "this run only covers week 3" note. The grid says "250 çakışma" while the report says "Çakışma 0" (`shots/32a_week_view.png`, `shots/32b_week4_week_view.png`) | M |
| 5.5 | Mobile, 390 px | Usable on the phone | The timetable agenda view is clean, with a "Taşı…" button per class (`shots/34a_mobile_tt_run6_wed.png`). The run report overflows horizontally (scrollWidth 4267 px, from the event-id chip row) (`shots/33b_mobile_run_report.png`). The timetable again opened on FINAL #4, W7 | m |
| 6 | Export the week to Excel and open it in openpyxl | His familiar board | **Very close to his board**: row 1 day, row 2 "A 101⏎(58)", rows = 18 period times, merged spans, frozen panes, yellow HAZIRLIK blocks, grey manual moves. Differences: the sheet is "Hafta 3" instead of "16 - 22 Şubat"; the day header is "2026-02-16 Pazartesi"; there is no legend; the **20 unplaced classes are not in the file**; there is no print setup. The full-term board export took 17 s with no feedback | m |
| 7.1 | Settings → YZ: paste a fake key, Test | Clear error | There is no Test button until the key is saved. After saving, the pill says "**connected**" for a fake key. The test then shows "Anahtar sınaması başarısız: Anthropic rejected the API key (authentication error)", and the pill **still says connected** (`shots/38a_test_key_result.png`) | M |
| 7.2 | Studio rule box with the fake key | Helpful message | "YZ yanıt veremedi (Anthropic rejected the API key (authentication error)). Metniniz duruyor. **Tekrar deneyin.**" Retrying cannot help, and there is no link to Settings (`shots/38b_studio_rule_fake_key.png`) | m |
| 8 | Turkish UI check | Everything in Turkish | Most screens are well translated. See the untranslated list in m1 (run report, settings, badges, toasts, warnings) | M |
| 9.1 | Final exams: studio, Sınavlar, Sınav dönemi | Plan the exam weeks | The first open of the EXAM draft gives the same 500. The scope says "**0 hafta** … 729 ders" and "SmartSched **—. haftalar** için". The pre-check says "**-2,1,2,3. haftalar**". The class list says "dersin haftalık bir oturumudur" for exams (`shots/40a_exam_scope.png`) | M |
| 9.2 | Generate the Final run, check shared rooms | Shared rooms only where seats allow | Run #7: 615/629. 28 cases of two different single-room exams in one room at overlapping times; **6 exceed the exam capacity**, e.g. A 207 (55 exam seats): ACU 132 (122) + ACU 310 (78) on 2 June P7. Grid cards use the lecture capacity ("78/120") while the header shows exam seats (55). Shared exams render as unreadable "MT…", "AC…" stubs. "BIF111" and "BİF111" are treated as two courses (`shots/43b_exam_grid_tue_A20x.png`) | M |
| X | Persona extra: an infeasible request (102 students pinned to a 30-seat room) | "102 öğrenci 30 kişilik B 201'e sığmaz" | The pin popover rightly refuses rooms that don't fit, so he used the template. The pre-check and run #8 say "ING 302 + ING 302 §10 (#244) (size 137) has no eligible room — locked to another room ×49; not in the pinned room set (room_pin #6) ×9". **Capacity is never mentioned**, and his 102 edit is invisible because the class is merged (size 137) (`shots/44b_infeasible_precheck.png`) | M |

## Findings

### BLOCKER

**B1. Any programme/year rule built in the studio matches zero classes.** This affects the template
"Belirli saatten sonra ders olmasın", "İkinci öğretim … bloklarında" and every other `applies_to`
programme rule. It is the core persona task: keep nursing first-years before 17:30.

- Repro:
  1. /generate → Kurallar → Şablondan seç → Saatler → "Belirli saatten sonra ders olmasın".
  2. Kime uygulanır → Bir program → "Hemşirelik", "1. sınıf"; Saat → "11. ders · 17:30 biter".
  3. The builder shows "0 derse uygulanıyor — Hiçbir dersle eşleşmiyor, adı kontrol edin". The
     pre-check lists it under "Hiçbir şeyle eşleşmeyen kurallar".
- Evidence: the stored rule is
  `{"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11}`.
  The solver input carries `frozenset({'PROG:hemşirelik:Y1', …})`, because
  `solver_bridge._cohort_keys` uses `program.canonical_name` (lower-case) while the studio dropdown
  uses the display name. The DB has 9 "Hemşirelik" year-1 Bahar sections.
- Screenshot: `shots/14a_evening_rule_zero_match.png`, `shots/13c_rules_after.png`.
- Fix direction: build the selector key from the same canonical name, or casefold cohort keys on both
  sides with `str.casefold()` and Turkish-aware İ/ı handling. Add an API test that a template rule
  for a programme/year has `affected_count > 0`.

**B2. Fatih cannot read the run report, so he cannot act on it.**

- Repro: generate Bahar week 3 (run #5), then open /runs/5.
- What he sees:
  - The headline is a **green 100/100 ring and a green tick**, while 21 classes are not placed.
  - The diagnosis cards are raw English solver text, for example
    `input conflict: MAT 112 §1 (#1) (day 4 P7-P9) and MAT 102 §1 (#786) … same instructor 'INS:1 (Elçim Elgün Kırımlı)'; no room choice can resolve this`.
  - There are internal ids (#1, #198 …), rule codes (`no_instructor_overlap`), the action tag
    "manual", and "Yumuşak · Orta" severity on a "21 cannot be placed" card.
  - The unplaced classes, which are the ones he must act on, are cards 173–193 of 196.
- Screenshots: `shots/20b_run5_report.png`, `shots/22a_unplaced_card.png`, `shots/23a_run6.png`.
- Fix direction:
  - Turkish message templates on the server, keyed by `code`.
  - Day names and clock times instead of "day 4 P7-P9", and course codes instead of #ids.
  - Order the cards: unplaced, then rule clashes, then input data, then info.
  - Collapse the 131 fixed-time clashes into one "Excel'inizdeki saat çakışmaları (131)" group with
    an Excel download.

### MAJOR

**M1. Wrong context everywhere: term, run and week.**

- Repro:
  - Log in: the app lands on 2026-FINAL, the last imported term.
  - Select 2026-BAHAR, open /timetable: the picker shows "#4 · 2026-FINAL" and W7, so the grid is
    empty. It happened again on the phone.
  - The dashboard and room pages use the calendar week (W7/W15), which is outside or after the run.
- Screenshots: `shots/01c_dashboard.png`, `shots/05a_timetable_default.png`,
  `shots/33a_mobile_timetable.png`, `shots/39_rooms_15.png`.
- Expected:
  - Remember the last term.
  - The timetable picks the latest run of the selected term and a week that the run covers.
  - Show "Bu çalıştırma yalnızca 3. haftayı kapsıyor" when the user leaves that range.

**M2. He cannot find a course.**

- The palette placeholder promises "ders kodu (MAT 112)" but `command-palette.tsx` only queries
  `useRooms` and `useRuns`, so "PHAR 240" gives "sonuç yok".
- The timetable can only be filtered by room.
- The requests row and drawer hide the definitive room (A 206). The drawer's "Tercih edilen derslikler"
  is a 58-chip wall with nothing visibly selected.
- Repro: Ctrl+K → "PHAR 240"; Talepler → "PHAR240" → open §1.
- Screenshots: `shots/03a_palette_phar240.png`, `shots/04c_requests_phar240.png`,
  `shots/04d_request_detail.png`.

**M3. Studio draft creation race: a raw 500 on the first visit of every term and kind.**

- `GET /terms/{id}/studio/classes` and `/studio/rules` run in parallel and both INSERT the draft,
  causing `sqlite3.IntegrityError: UNIQUE constraint failed: studio_drafts.term_id, studio_drafts.user_id, studio_drafts.kind`.
- The toast reads "500 Internal Server Error".
- Repro: fresh DB → /generate. Also: switch the scope to 2026-FINAL plus Sınavlar.
- Screenshot: `shots/07a_studio_open.png`.
- Fix: get-or-create with `ON CONFLICT DO NOTHING`, then re-select.

**M4. Autosave fails while a run is solving (SQLite).**

- `PUT /terms/1/studio` → 500, `sqlite3.OperationalError: database is locked`.
- The UI says "Son değişikliğiniz kaydedilemedi. (500 Internal Server Error) · Tekrar dene".
- Repro: generate run #5 from the studio and keep the page open.
- Screenshot: `shots/19c_run_progress.png`.
- Fix: WAL mode plus `busy_timeout` for SQLite, a retry with backoff in autosave, and a human message.

**M5. Run status words and numbers contradict each other.**

- The run page says "Kısmi · 663/683", the run picker says "Uygunsuz · 100/100", and the runs list
  says "Katı 100/100".
- The report says "Çakışma 0" while the grid header says "250 çakışma · 0 kapasite aşımı" (exam run:
  "163 çakışma · 107 kapasite aşımı").
- The studio summary counts 883, the pre-check counts 882 and the solver counts 683 events.
- Screenshots: `shots/20a_runs_list.png`, `shots/23b_run6_grid.png`.

**M6. Uploaded preferences silently miss joint lectures.**

- "HEM 106 → C 201" is shown as ready with high confidence in the review, then saved as
  `room_preference {"event_ids": [30]}`.
- Request 30 is merged into event 28 ("BES 128 + HEM 106"), so the rule affects 0 classes. Only one of
  the two HEM 106 rows was matched.
- Repro: upload `scratchpad/files/fatih_tercihler.xlsx`, then accept all.
- Screenshot: `shots/16b_rules_with_upload.png`.
- Fix: map request ids to merged event ids in `_selector_affected` and in the solver, or store
  request ids and resolve them at build time.

**M7. The infeasible request isn't explained in terms Fatih understands.**

- "102 students in a 30-seat room" is reported as "kilitli ama bu derslik kullanılamıyor (not in the
  pinned room set (room_pin #6); …×9)" and "(size 137) has no eligible room".
- Capacity is never named. His enrolment edit (102) is hidden because the class is merged.
- Repro: Dersler → ING 302 (Çar P2–P3) → Öğrenci 102; Şablon "Her zaman bu derslikte" ING 302 → B 201
  from W1; Ön kontrol.
- Screenshot: `shots/44b_infeasible_precheck.png`.

**M8. Exam shared rooms go beyond exam capacity, and the grid hides it.**

- Run #7 puts two different single-room exams in one room 28 times; 6 exceed exam seats:
  - A 207 (55): ACU 132 (122) + ACU 310 (78), 2 June.
  - A 204 (74): MTH 104 (102) + ACU 186 (83).
  - C 201 (60): BES 118 (60) + NUT 126 (50).
- Card denominators use lecture capacity ("78/120") while the column header shows exam capacity (55).
- Shared exams render as truncated stubs.
- "BIF111" vs "BİF111" are treated as different courses (Turkish dotted İ not normalised).
- Repro: /generate → 2026-FINAL → Sınavlar → Sınav dönemi → Planı oluştur; Çizelge #7, W1 Salı,
  filter "A 20".
- Screenshot: `shots/43b_exam_grid_tue_A20x.png`.

**M9. Exam scope maths is broken.**

- "Sınav dönemi" gives "0 hafta", "Hafta 0", "SmartSched —. haftalar için 729 dersi …".
- The pre-check and run prompt say weeks "-2,1,2,3".
- The run solves 629 events while the studio says 729 and the term has 921 exam requests.
- Screenshot: `shots/40a_exam_scope.png`, `shots/40c_exam_check.png`.

**M10. Week chips toggle instead of select.**

- After "Bir hafta", W1 stays selected and W3 is added, so "1, 3. haftalar" is planned unnoticed.
- Screenshot: `shots/08a_scope_week.png`.

**M11. Moving classes is laborious.**

- The move dialog lists 58 rooms with no free, busy or fitting indicator; 44 tries found no free room.
- Reasons are English ("slot occupied", "capacity too small") with no numbers ("75 öğrenci > 41 koltuk").
- There is no week range ("23 Şubat'tan itibaren").
- During drag, dnd-kit auto-scrolls the grid sideways near the edges.
- The drop target follows the pointer rather than the card top, so the outline is one period off.
- Screenshots: `shots/29c_move_dialog_too_small.png`, `shots/30a_move_dialog_ok.png`,
  `shots/25a_drag_legal_hover.png`, `shots/28c_drag_PDL112_to_A104_hover.png`.

**M12. The AI key status is misleading.**

- A fake key shows "connected" right after saving and still after the failed test.
- There is no Test button before saving.
- Error detail is English.
- The studio tells him to "Tekrar deneyin" for an invalid key.
- Screenshots: `shots/37c_test_saved.png`, `shots/38a_test_key_result.png`,
  `shots/38b_studio_rule_fake_key.png`.

**M13. Board vs planning-list disagreements are invisible.**

- PHAR 240 §1 is locked to A 206 (Mon P1–P3) in the planning list. The published board has PHAR 240 in
  D 106 and HEM 334 / NRS 304 in A 206 at that time.
- Neither the import report, the pre-check nor the dashboard mentions it.
- Screenshot: `shots/06b_tt_filter_a206.png`. Evidence: `export_run1` Hafta 3 BF3 = PHAR 240 under
  "D 106"; the original sheet "16 - 22 Şubat" M3 has "HEM 334 / NRS 304" under "A 206".

**M14. The dashboard's pending list ignores the term.**

- On 2026-FINAL the "Bekleyen talepler" card lists Bahar course requests (FZT 3002 …), because
  `dashboard-view.tsx` calls `useMeetings({status:"NEEDS_REVIEW"})` without the term.
- The sidebar badge "231" is shown on FINAL too.
- Screenshot: `shots/01c_dashboard.png`.

### MINOR

**m1. Untranslated text in Turkish mode.**

- Status and badges: "REGULAR"/"FINAL" term badges; "Run #6"; "Table" (heatmap and soft legend);
  "stability room"; "W3"/"W7" in the grid vs "H3–3" in the studio rail; "1 Haz · EXAM".
- Event sheet: "Origin · SOLVER".
- Settings: model hints "strongest reasoning / default / fastest"; "connected".
- Request drawer: "Ders saati (end)".
- Class row: "A 206 has 92 seats, this class has 130".
- Move dialog: "P12 (30 min) inside span".
- Toasts: "#434 placed in C 501 on day 4 P16-P18 and locked".
- Run prompt: "İstem: Studio draft #1 v9: 683 events …".
- All diagnosis text (see B2).
- Screenshots: `shots/02b_bahar_dashboard.png`, `shots/29a_event_sheet.png`, `shots/37a_settings_ai.png`.

**m2. Turkish grammar.**

- "17:30'den" should be "17:30'dan".
- "4. hafta'den itibaren" should be "4. haftadan itibaren".
- "3. haftalar için" (one week, so no plural).
- "921 talepler" / "1.524 talepler" should be "921 talep".
- "(0,1 %)" should be "%0,1".
- "A 204 dersliklerini kullan" for one room.
- A suffix-harmony helper is needed. Screenshot: `shots/13c_rules_after.png`.

**m3. Count inconsistencies in the studio.**

- "883 plana dahil · 2 plan dışı" should be 881.
- "diğer 1.521 ders plan dışında kalır" when 883 are in the plan.
- The "Değişti" chip stays at 0 during an edit.
- Screenshot: `shots/09b_enrolment_reverted.png`.

**m4. Stale warning after revert.** The capacity warning stays after reverting the enrolment.
Screenshot: `shots/09b_enrolment_reverted.png`.

**m5. Look-alike items in pickers.**

- "PHAR 240 §1" is listed twice (Monday lecture, Thursday lab).
- "FZT 3002 §" has an empty section.
- "ING 302 §" is listed ten times with only the programme to tell them apart.
- Show day and time in the pickers. Screenshot: `shots/13a_always_in_room_filled.png`.

**m6. Contradictory rule accepted.** "17:30'dan sonra **veya** 17:30'dan önce ders olmasın", which
bans every period, was saved without a warning (`shots/13b_evening_template_filled.png`).

**m7. The no-key message is a dead end.** It doesn't link to Settings or offer the matching template
chip that is visible just above it (`shots/10b_nl_no_key.png`).

**m8. The Excel export misses context.**

- Sheet names are "Hafta N" instead of the original "16 - 22 Şubat".
- The day header uses ISO dates.
- There is no legend for yellow (block) and grey (manual) cells.
- There is no "Yerleşemeyenler" sheet.
- There is no landscape or fit-to-page print setup.
- The 17-second full-term export gives no feedback.
- Files: `scratchpad/files/export_run6_smartsched-run6.xlsx`, `…/export_run1_smartsched-run1.xlsx`.

**m9. The week view is unreadable.** It shows unlabeled bars, and day percentages appear on an empty
week (`shots/32a_week_view.png`, `shots/32b_week4_week_view.png`).

**m10. Mobile run report overflows horizontally** (event-id chip row). Screenshot:
`shots/33b_mobile_run_report.png`.

**m11. React hydration error #418 on /timetable** (console, every load).

**m12. Opaque CLI import warnings.** Room codes are masked as "A###" ("## room(s) … still have no
capacity: A###, A###, …"), so the planner can't tell which rooms.

**m13. Run report "Kısıtlar (0)"** although 5 rules were in play.

**m14. Wrong wording on the exam class list.** It says "Her satır … bir dersin haftalık bir oturumudur"
for exams (`shots/40b_exam_classes.png`).

### POLISH

- The table header is truncated: "Plana dah".
- The seeded admin is called "Administrator" ("Hoş geldiniz, Administrator").
- The chat panel shows the model name "claude-opus-5-5" even with no key.
- The run list shows "#5← #1" (parent arrow) with no tooltip.
- Board events show "0/92" (the board isn't linked to sections). Show "—/92" or hide it.
- Rule deletion has no confirmation (Sil was applied at once).
- The scope summary says "Son başarılı çalıştırma: #1 · · Tüm kurallar sağlandı" (empty label between
  dots). The imported board is not a solver run that "satisfied all rules".

## What felt great

- **Column mapping and review of his own Excel:** Turkish headers were auto-mapped, each rule traces
  back to "fatih_tercihler.xlsx · 2. satır", and readiness and confidence were clear. He said: "this is
  how I'd want to send faculty files in."
- **Pre-check cards for locked overlaps** read like a colleague's note: "MAT 112 §1 ve HEM 236 ikisi de
  A 204 dersliğine Perşembe 15:10-15:50 saatinde kilitli", with buttons for the fix and an undo toast.
- **"Ne olacak" summary.** One plain sentence says what the solver will do, with live counts.
- **Inline class edits** show "içe aktarılan değer 80 idi" and a one-click revert.
- **The pin popover** only offers rooms that fit, with the current room pre-selected.
- **The template gallery** has fill-in-the-blank sentences and a live "N derse uygulanıyor". The
  "hiç eşleşmiyor" warning is what exposed B1.
- **One-click diagnosis fix** creates a child run (#5 → #6), placing one more class without retyping
  anything.
- **Drag and drop** shows a live "Uygun"/"Çakışma" status, a Turkish success toast with "Geri al", and
  marks the moved class as manual and locked.
- **The Excel export looks like his own board**: same header shape "A 101 (58)", period rows, merged
  spans, frozen panes, yellow HAZIRLIK blocks.
- **The mobile agenda view** is clean, with a "Taşı…" button per class.
- **Speed:** runs take 11–38 s, a week export about 2 s, and the API never hung.
- **No-AI fallbacks** keep the text and explain why.

## Top 10 recommended changes (priority order)

1. **Fix cohort-key matching (B1)** and **map request ids to merged events (M6, M7)**. Add regression
   tests: a programme/year template has `affected_count > 0`, and an upload row for a joint-lecture
   member affects its merged event.
2. **Rewrite the run report for planners (B2).**
   - Turkish templates for every diagnosis code, with course code, day name and clock time.
   - Unplaced classes first, with a "neden + ne yapabilirim" layout.
   - Collapse input-data clashes into one group with an "Excel olarak indir" button.
   - Hide internal ids and action tags.
3. **Make the status honest (M5).**
   - The headline is "662 / 683 ders yerleşti" with an amber ring when partial.
   - One word for the status everywhere (Kısmi), and the same conflict count on the report and grid.
4. **Context memory (M1).**
   - Persist term, run and week per user.
   - The timetable defaults to the latest run of the selected term and a week inside it.
   - Show a banner when the shown week is outside the run.
5. **Course-centric search (M2).**
   - Course codes in Ctrl+K and the timetable filter, with or without a space ("PHAR240").
   - Show the definitive room on request rows and in the drawer.
   - A "PHAR 240 nerede?" panel listing its meetings across weeks.
6. **Studio robustness (M3, M4).** Idempotent draft creation, SQLite WAL plus `busy_timeout`, and
   Turkish, non-technical error toasts.
7. **Moving tools (M11).**
   - The dialog groups rooms into "boş ve sığar / sığmaz / dolu".
   - Turkish reasons with numbers.
   - A "bu haftadan itibaren / sadece bu hafta" choice.
   - Drag drop anchored to the card top, and gentler auto-scroll.
8. **Exam correctness (M8, M9).**
   - Enforce exam capacity on shared rooms.
   - Denominators use exam seats.
   - Normalise İ/I in course codes.
   - Readable shared-room cards ("2 sınav · 200/55").
   - Fix exam-period weeks and counts.
9. **AI settings truthfulness (M12, m7).**
   - The status reflects the last test.
   - Test before save.
   - Turkish errors.
   - A studio message that links to Settings and offers the matching template.
10. **Turkish polish and export completeness (m1, m2, m8).**
    - An i18n sweep and a suffix-harmony helper.
    - Export sheets named like his workbook ("16 - 22 Şubat").
    - A legend and an unplaced-classes sheet.
    - A board-vs-planning-list difference report (M13).

## Missing features a planner would expect

- **"Liste ile pano farklı" report.** Every place the published weekly board disagrees with the
  planning list (room, time), downloadable to Excel. This is his daily reconciliation job.
- **Course and instructor views:** "PHAR 240 bu dönem nerede/ne zaman", plus a teacher's week and a
  cohort's week (Hemşirelik 1. sınıf), with clash highlighting.
- **Free-room finder:** "Çarşamba 10:10–12:30 arası 90+ kişilik boş derslik".
- **Date-ranged changes** in the timetable ("23 Şubat'tan itibaren A 206"), not only as a studio rule.
- **Unplaced list as a work queue:** assign, comment and mark as resolved, plus an export for the
  faculties.
- **Excel round-trip** of the studio class list: download, edit in Excel, upload the diff.
- **Change log and "what changed since the published board"** per run, exportable for faculty
  e-mails.
- **Holiday and special-day handling** by date (e.g. 23 Nisan) visible in the week picker; week chips
  should show dates ("W4 · 23 Şub").
- **Print-ready per-building and per-day boards** (PDF or Excel print areas) for the notice boards.

## Appendix: API and CLI evidence (abridged)

```text
# B1: stored rule vs solver cohort keys
constraints#2 day_window {"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11}
solver input event 28 "BES 128 + HEM 106" cohort_keys={'PROG:beslenme ve diyetetik:Y1','PROG:hemşirelik:Y1'}
select_events(inp, {"cohorts": ["PROG:Hemşirelik:Y1"]}) -> 0
sections: Hemşirelik class_year=1 -> 9 rows

# M6: upload rule on a merged request
constraints#4 room_preference {"event_ids": [30], "room_ids": [54]} source=UPLOAD   (request 30 merged into event 28)

# M3: backend log on first /generate
sqlite3.IntegrityError: UNIQUE constraint failed: studio_drafts.term_id, studio_drafts.user_id, studio_drafts.kind
# M4: during run #5
"PUT /api/v1/terms/1/studio HTTP/1.1" 500  -> sqlite3.OperationalError: database is locked

# 4.2: diagnosis fix
POST /runs/5/diagnoses/185/apply -> 200 {"child_run_id":6,"action":"move","message":"#434 placed in C 501 on day 4 P16-P18 and locked"}

# 5.2: move dialog
POST /runs/6/assignments/11172/move -> 200 {"ok":true,... "start_period":13,"end_period":15,"room_codes":["A 102"],"is_locked":true,"origin":"MANUAL"}

# 7.1: fake key
POST /settings/test-ai -> 200 {"ok":false,"detail":"Anthropic rejected the API key (authentication error)","used_key":"stored"}
POST /terms/1/elicit   -> 502 {"detail":"Anthropic rejected the API key (authentication error)"}

# 9.2: exam shared rooms (run 7, distinct single-room exams overlapping in one room)
28 pairs, 6 over exam capacity, e.g. A207 (55) 2026-06-02: ACU132 122 (P7-8) + ACU310 78 (P6-7)
board run #4: 0 such pairs

# X: infeasible request (run 8)
no_room: ING 302 + ING 302 §10 (#244) (size 137) has no eligible room
  reasons: locked to another room ×49; not in the pinned room set (room_pin #6) ×9
```

Step scripts used (Playwright, re-runnable against :3400) live in the scratchpad `steps/` directory
with the runner `run.mjs`. Probe scripts: `cohort_probe.py`, `shared2.py`, `diag8.py`,
`inspect_xlsx.py`.
