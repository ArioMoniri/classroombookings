# Flow loop round 3 · admin · 2026-10-17

Ledger: `flow-r3-admin-2026-10-17` · persona tester (admin: Fatih Bey as classroom planning officer, system administrator and approver for every room; limited admin, planner and viewer helpers) · brief `scratchpad/briefs/ROUND3.md` (inherits ROUND2.md) · plan: [README](../README.md), [MOBILE](../MOBILE.md)
Snapshot: `8db884fd` (`8db884fdbac71c7efd7472f31fcc58b2f7e354a2`, `claude/focused-wright-ktt0ss`), frozen worktree `scratchpad/flow-src-8db884f` (removed at the end) · main stack API :19430, web :19431 (`REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`) · fresh stack API :19432, web :19433 (`--fresh`, F-08 only, run after the main flows) · SMTP sink :2628
Load: 0.4–8.5 on 4 cores (1.3–7 while flows ran, shared with two other testers), so M-14 timings were not taken (README §8)
Run window: 09:09–10:13 UTC; a model usage limit stopped the round at 10:13 and the container restarted at 18:55; both stacks were restored from the saved snapshots (`rec.snapshot`, `rec.board`, fresh rebuilt with `--fresh`) and only the missing steps were re-run 19:00–19:41 UTC (F-02 desktop + phone, F-05 S08–S12 follow-up, F-09 S04 template probe, F-13 C02 reject-trap probe, conflicts apply, F-05 S15 board-only, F-08 UI commit into 2026-BAHAR, re-uploads, S14).
Dates (README §4.3): TODAY 2026-10-17 · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D5 2026-11-19 · D6 2026-11-26 · Chromium 141 (chromium-1194), Playwright 1.56 library, `scripts/record/lib/touch.mjs` (`assertTouch` before every phone measurement, `shot()` for full-page shots)
Data: three real terms + room master. `stack.sh runs`: #7 Bahar week 3 (688/716, hard 100), #8 Bahar term (682/717, hard 100, published = B0), #9 Güz week 3 (524/530), #10 Güz term (517/530, hard 100, published = G0). Made in the round: Bahar Studio run #11 (688/716, hard 100), cancelled #12; Güz re-solves #11 (several, each from a fresh restore).
Names: masked by `stack.sh` + the §4.4 seed (`kvkk_mask.py --verify` → `left 0`); the fresh stack was masked after every F-08 chain (`stack.sh mask` → `left 0`). Screenshots of F-08 review tables before masking were deleted; the kept ones were taken after masking or carry counts only. Accounts: seed (`personel.test` P. T., `akademisyen.test` A. T. ↔ instructor 157, `planner.test` P. L., `viewer.test` V. T.), `ds.test2`, `limited.admin` L. A. (role "Kullanıcı yöneticisi").
Preconditions: admin approves for all rooms; `approval_mode=all` re-applied after each restore; per-flow preconditions as in the flow files.
Viewports: desktop 1440×900 (mouse, keyboard) and phone 390×844 (isMobile, hasTouch, tap; 844×390 for M-13).
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r3admin/ev` (`shots/` 188, `logs/` 215 JSON / out files incl. every MOBILE battery, `curl/` exports and captures, `scripts/` 30 re-runnable Playwright scripts; mail in `../mail/`). Paths below are relative to that root.

## BLUF

- **Round-2 ids (R2-M-01…27): 14 verified · 8 verified in part · 2 reopened (R2-M-03, R2-M-06) · 1 open by owner decision (R2-M-08) · 2 suggestions still open (R2-M-24 = FLE-012, R2-M-27 = FLE-013).**
- **Re-tested round-1 ids (R1-M-04/14/17/20/21/26/32/33/38): 7 verified · 2 verified in part (R1-M-17, R1-M-26).** R1-M-07 is still the owner's decision; R1-M-36 not run (no CRBS dump).
- **New: 9 findings — 0 blocker · 4 major · 4 minor · 1 trivial.**
  - **R3-M-01 (major, integrity):** a minimal re-solve after **one section-priority edit** (PSY 277, "Tüm şube" → Yüksek) drops the **planner-locked, published NUT 121** for the equal-priority newcomer SYB 111 ("öncelik eşit, daha çok ders ve hafta … korundu"), plus EHM 311 §A/§B; 4 newly unplaced, 16 people affected. Every loss *is* named, 0 unexplained moves, hard 100 → 100. The round-2 chain (section **and** person priority) is now clean: 0 moved, 0 unexplained, 563/563 locked rows kept.
  - **R3-M-02 (major, intake):** dry run == commit now (1,512 = 1,512) and the same CSV re-uploaded changes 0 rows, but re-uploading **the same planning workbook** plans **1,329 updates** (week lists 1–19 → 1–14) and the cp1254 CSV is only **11.8 % unchanged** (≥ 99 % required).
  - **R3-M-03 (major, phone):** `/onboarding/<id>` on a phone: "Yaz" is at the end of a 6,650 px page (not sticky) and 63 review buttons are 89×36 / 90×36.
  - **R3-M-05 (major, phone):** the new timetable filters sheet is the desktop sidebar in a 293 px left panel: 107 targets under 44 px (28 px calendar days), a 14 px search input, not a bottom sheet.
- Confirmed fixed and good to use: "Yeniden denetle" keeps every per-date choice (1440 + 390); re-solve publish shows "Yayınlandı: #N artık geçerli plan" and "✓ Yayında"; one problem count (Sorun 399 = headline = API, "Veri notları 457" labelled) and the full unplaced list (28/28, 35/35); person learning reset hides open suggestions and undo restores them; duplicate wizard person refused inline; Studio rail "Tüm dönem · 14 hafta"; pin template "· sığmaz (35 > 30)" with an admin "Gerekçe (zorunlu)" and a planner refusal; "Taşı" disabled on a "Sığmaz" room; forced-break banner in Turkish; skip link "Izgaraya geç" is the 2nd Tab stop; approvals j/k → Enter (focus on the title) → `a` approves; dialogs trap Tab; inline role error, disabled-permission reasons, per-rule approver warning, Turkish feature/photo refusals; solver tab 10/5/1/8/1/10 "Ağırlık" with 16 px inputs; no odometer digits on /dashboard; admin action capsule on the phone admin lists.

**Release verdict — ready for release from this persona's point of view: no, because a single soft priority edit can still cost a planner-locked published class (R3-M-01), re-uploading the same planning workbook would rewrite 1,329 requests (R3-M-02), and the intake job page and the timetable filters are not usable by touch on a phone (R3-M-03, R3-M-05).**

## Fatih Bey's scenarios

| Scenario | Result |
|---|---|
| Import the Bahar list and the weekly grid | ◐ Main stack by `stack.sh` (3 terms). Fresh stack through the UI: xlsx + EN CSV + scanned PDF in one job, `/onboarding/1` addressable, "Son işler" after a reload, PDF "YZ kapalı, okunmadı" / "Okunmadı: bu dosyada okunabilir metin yok…", dry run 1,512 creates = commit 1,512 rows in 2026-BAHAR. The commit panel proposes a **new** term "BAHAR · 16 hafta" unless the code is typed (R3-M-04); re-upload deltas R3-M-02 |
| Find a course (PHAR 240) | ✓ Studio "Dersler" and the timetable inspector (Monday P1–P3, A 206, 80 öğrenci); phone inspector footer "Taşı…" / "Kilitle" 44 px |
| Generate week 3 | ✓ Studio run #11: 688/716, FEASIBLE_PARTIAL, hard 100; card, report, KPI, tab and API all say 399 exceptions; unplaced list 28 = 28 |
| Move PHAR 240 to A 206 from 23 Feb | ✓ (as in round 2 the class already sits in A 206; the scope picker and split were verified in round 2). Round 3 re-checked the forced and capacity paths: busy A 204 → "HEM 242 ile çakışıyor", "Yine de taşı" only with a reason, banner "derslik çakışması: A204 · 3. hafta Pzt P2 … gerekçe: …", undo → hard 100; "Sığmaz" C 301 → "80 öğrenci 72 kişilik C 301'e sığmaz", Taşı disabled |
| Turkish request: nursing first-years before 17:30 | ✓ chip → template, "2 program seçildi", "23 derse uygulanıyor"; run #11: 19 year-1 nursing classes, 0 after P11 |
| Export the week to Excel | ✓ `smartsched-run8-hafta4.xlsx` (1 sheet) and `smartsched-run8.xlsx`; `?weeks=4` Content-Disposition `smartsched-run8-hafta4.xlsx`; `?weeks=99` → 422 |
| Infeasible request (ING 302 into 30-seat B 201) | ✓ template marks "30 koltuk · sığmaz (35 > 30)" (ING 302 §10), admin must write "Gerekçe (zorunlu)" before "Ekle" enables; planner sees "Yalnız bir yönetici gerekçeyle sabitleyebilir" and API 422 `capacity` "100 öğrenci 30 kişilik B 201'e sığmaz"; pre-check names "Kesin kural #74 … sığmaz". The forced pin is still not listed among accepted exceptions (`forced_overrides 0`, R2-M-24 / FLE-012) |

## Step table

Result codes: PASS · PASS* (with a note) · FAIL · BLOCKED · SKIP · NOT RUN. Phone battery rows fold passing criteria into one row.

| Flow | Step | Persona | Viewport | Result | Evidence | Issue |
|---|---|---|---|---|---|---|
| F-02 | S02–S03 weekly preview: 6 rows, holiday, D4 "Dolu · Bölüm toplantısı" with "Yerine geç" | admin | desktop + phone | PASS | `logs/f02-desktop-r.out`, `logs/f02-phone.json` | – |
| F-02 | S04 Atla D3 + Yerine geç D4, Hiçbiri ("0 tarihi rezerve et" disabled), Boşların hepsi, re-apply, **Yeniden denetle** → choices kept; POST body `2026-11-05 do_not_book`, `2026-11-12 replace`; toast "4 tarih rezerve edildi, 1 tarih atlandı" | admin | desktop + phone | PASS | `logs/f02-desktop-r.out` (`S04.posts`), `shots/F02-S04-afterRecheck-*.png` | R2-M-01 verified |
| F-02 | M-01…M-11 recurring sheet (Hiçbiri 64×44, Takvimi aç 44×44, M-02 0, M-05 ✓) | admin | phone | PASS | `logs/f02-phone.json` (`phoneBatt`) | – |
| F-02 | S05 staff card "Gerekçe: Seri #1 ile değiştirildi", bell "Rezervasyonunuz iptal edildi … Gerekçe: Seri #1 ile değişti", no calendar toast | staff | desktop + phone | PASS* | `logs/f02-*.out` (`S05.*`) | wording differs card vs bell → R3-M-09 |
| F-02 | S12 past date → 409 `past` with message_tr "16.10.2026 geçmiş bir tarih; …" | staff/API | – | PASS | `curl/F02-S12-past.txt` | – |
| F-02 | S10 audit undo | admin | – | NOT RUN | – | harness query; staff re-tests T-R2-31 |
| F-05 | S00 re-pick the linked instructor → 200, no `user.instructor_link` row | admin | API | PASS | `logs/f05.json` (`S00`) | R2-M-20 part verified |
| F-05 | S07 search "PSY 277" under "Karşılanmayan" → "Karşılanmayan filtresinde yok; Tümü'nde 2 sonuç" + "Tümü'nü göster" → 2 rows | admin | desktop + phone | PASS* | `shots/F05-S07-empty-desktop.png`, `logs/f05-phone.out` | phone link 121×36 (R3-M-08) |
| F-05 | S08 section priority popover "Şu an: Normal", save → toast "PSY 277: öncelik kaydedildi. Bir sonraki çözümde etkili.", staged "1 değişiklik yayında değil"; focus → `<body>` | admin | desktop | PASS* | `logs/f05b.out` | R3-M-06 |
| F-05 | S08 person priority toast "Dr. Öğr. Üyesi S. E.: öncelik kaydedildi (4 talep)…", focus stays on "Kaydet"; viewer 403; planner person priority **200** | admin/planner/viewer | desktop + API | PASS* | `logs/f05.json` (`S08.*`) | R2-M-08 owner decision |
| F-05 | S09 recreate sheet "Yayındaki plan #10 temel alınır", 2 staged changes, "En az değişiklik", policy line → run #11 parent 10, workers 1, inactive | admin | desktop + phone | PASS | `logs/f05.json`, `logs/f05-phone.out` | – |
| F-05 | S10 (section + person priority): "0 taşınan, 0 yeni yerleşen, 10 yerleşemeyen", chain "#11 ← #10", hard 100 → 100, `moved_unexplained 0`, 563/563 planner-locked rows kept | admin | desktop + API | PASS | `logs/F05-diff-11.json`, `logs/f05.json` (`S10.*`) | R2-M-03 chain part verified |
| F-05 | S10 (section priority only, twice from a fresh restore): "0 taşınan, 4 yeni yerleşen, 11 yerleşemeyen", 4 newly unplaced incl. planner-locked **NUT 121** (562/563 kept), 16 people affected, each loss named | admin | desktop + API | FAIL | `logs/F05-diff-11-sectiononly.json`, `logs/resolve-chk.json`, `logs/f05b.out` | R3-M-01 |
| F-05 | S11 pin + rerun | admin | desktop | SKIP | – | nothing moved in either preview; "Değişmeyen" rows carry no row menu |
| F-05 | S12 publish confirm (counts, "4 ders dersliğini kaybediyor:" with causes), "Yayınla" → toast "Yayınlandı: #11 artık geçerli plan. Önceki plan Çözümler'de duruyor.", state "✓ Yayında", #11 active, audit `run.activate`; focus → `<body>` | admin | desktop | PASS* | `shots/F05-S12-published-desktop.png`, `logs/f05.json`, `logs/f05b.out` | R2-M-02 verified; focus R3-M-06 |
| F-05 | S13/S14 no changed class for the linked academician → no mail, no bell; `/moderation/me/matchings` follows #11 | academician/API | – | PASS | `logs/f05.json` (`S13`, `S14`) | – |
| F-05 | S15 board-only snapshot: one active run (#3 GRID_IMPORT), dashboard "Yayında: içe aktarılan pano #3", doluluk %24 = heatmap "Genel doluluk %24,1", moderation "Yayında: #3 · taleplerin %72'si karşılandı" | admin | desktop | PASS | `logs/s15.out`, `shots/F05-S15-*.png` | (R1-S-15 evidence for the staff row) |
| F-05 | M-01…M-13 @/moderation, inspector sheet, recreate sheet, /moderation/people/157, /moderation/recreate/N | admin | phone | PASS* | `logs/pb-_moderation*.json` | chips "Herkes" 86×28, crumb/menus 36 px (R3-M-08); recreate-open at the top (M-05, R3-M-08) |
| F-06 | S10 reset P1 (instructor 98): dialog texts, "Sıfırla" disabled under 3 chars, toast "Sıfırlandı · Geri al"; suggestions before `5762 accepted, 1781 open, 5579 open` → after `5762 accepted` only, 0 cards; undo "Sıfırlama geri alındı" → identical | admin | desktop | PASS | `logs/f06.out` | R2-M-05 verified |
| F-06 | phone Öneriler / learning / reset dialog (M-12 reason field uncovered) | admin | phone | PASS* | `logs/pb-_moderation_learning*.json` | "Diğer işlemler" 36×36 (R3-M-08) |
| F-07 | S05 "T. E." then "t. e." on the same section → one entry, inline alert "Bu kişi bu şubede zaten var: t. e." | admin | desktop | PASS | `shots/F07-S05-dup-desktop.png`, `logs/f07.out` | R2-M-07 verified |
| F-07 | S07 pre-check "0 engel, 0 uyarı · hazır", "Sığan odalar" per class; no "listed twice"; one `<main>` (desktop + phone) | admin | desktop + phone | PASS | `logs/f07.out` | R2-M-20 part verified |
| F-07 | S08 "Yalnızca oluştur" confirm "… 30 gün içinde geri alınabilir" → "Program oluşturuldu · 2027-BAHAR"; S09 undo → "Arşivlendi: 3 şube, 0 yeni ders, 2 kişi…" | admin | desktop | PASS | `shots/F07-S08-committed-desktop.png` | – |
| F-07 | S12 MBG 961 into Güz → "0 taşınan, 1 yeni yerleşen", `moved_unexplained 0`, hard 100 → 100; "Vazgeç" keeps #10 | admin | desktop | PASS | `logs/F07-diff-11.json`, `shots/F07-S12-preview-desktop.png` | R2-M-03 F-07 part verified |
| F-07 | M-01…M-13 @/programs/new, draft step | admin | phone | PASS* | `logs/pb-_programs_new*.json` | wizard-start at y 410 (M-05, R3-M-08) |
| F-08 | S01 `/onboarding`: drop zone is one `<button>` (68 px, aria-labelledby/describedby), Enter and Space open the picker, `accept=".xlsx,.xlsm,.xls,.csv,.tsv,.ods,.json,.xml,.ics,.docx,.pdf,.txt,.eml,image/*"` | admin | desktop | PASS | `logs/f08-probe.json`, `shots/F08-S01-dropzone-desktop.png` | R2-M-25 verified |
| F-08 | S02–S04 "Başlat · 3 dosya", "· Yönetici kapattı"; job at `/onboarding?job=1`, `/onboarding/1` opens it; "Son işler · #1 · 3 dosya · İncelemede" after reload; badges "Doğrudan", "Doğrudan", "YZ kapalı, okunmadı" (no "YZ") | admin | desktop | PASS | `logs/f08.out` (`S03.*`), `shots/F08-S03-job-desktop.png` (masked) | – |
| F-08 | S05/S08 commit before decisions → 409 `review_pending` "Önce 3 inceleme kararı verilmeli." with no names | admin | API | PASS | `curl/F08-S08-commit-guard.txt` | – |
| F-08 | S08 live bar: page open, blockers decided via the API → "Yaz" enabled without reload | admin | desktop | PASS | `logs/f08.out` (`S08.liveBar`) | – |
| F-08 | S07/S08 dry run (UI confirm, term 2026-BAHAR) "1.512 yeni talep" → commit: fast 1,511 + general 1 (1,335 duplicates written once) = 1,512 rows in 2026-BAHAR | admin | desktop + API | PASS | `logs/F08-final-posts.json`, `logs/f08-ui2.json` | R2-M-06 dry==commit verified |
| F-08 | S08 commit panel defaults to a new term "BAHAR · normal dönem · 16 hafta" (code BAHAR); the first run created a 2nd Bahar term | admin | desktop | FAIL | `shots/F08-S08-commit-panel-desktop.png`, `logs/f08-redo.out` | R3-M-04 |
| F-08 | S10 Job D (same CSV): 4 remembered items "… 1 numaralı işten hatırlandı", commit without decisions 409, dry run create 0 · update 0 · unchanged 1,340 | admin | API + desktop | PASS | `logs/f08-re.json` (`dry.job2`) | – |
| F-08 | S11 Job C (cp1254 `;`): "CSV · Windows-1254 · ;", Turkish letters intact; dry run update 1,333 / unchanged 179 (11.8 %); same xlsx re-upload update 1,329 (`weeks`) | admin | API | FAIL | `logs/f08-re.json` (`dry.job3`, `dry.job4`), `logs/F08-final-dry-job*.json` | R3-M-02 |
| F-08 | S09 mask → "left 0" (after each chain) | admin | CLI | PASS | `logs/f08*.out` | – |
| F-08 | S12 viewer: review 200 without samples, POST review 403, commit 403 | viewer | API | PASS | `logs/f08.json` (`S12.*`) | – |
| F-08 | S13 PNG renamed .xlsx refused at upload with a Turkish reason (400) | admin | API | PASS | `logs/f08.json` (`S13`) | – |
| F-08 | S14 undo: confirm says "Geri alınamaz: yazılan kayıtlar bu işten geri alınmaz…", audit row "Council job işlendi" has no Geri al | admin | desktop | PASS* | `logs/f08-re.json` (`confirmFull`), `shots/F08-S14-audit-desktop.png` | honest; 30-day undo not built; "Council job" wording R3-M-07 |
| F-08 | M-01…M-13 @/onboarding, /onboarding/1 | admin | phone | FAIL | `logs/pb-_onboarding_1_masked_.json`, `shots/F08-phone-job-commitbar.png` | R3-M-03 |
| F-09 | S01 Güz rail "Tüm dönem · 14 hafta" = sentence "14 hafta boyunca 58 derslikte 632 ders"; Bahar H3 "1 hafta … 869 ders" | admin | desktop | PASS | `shots/F09-S01-rail-guz-desktop.png` | R1-S-22 evidence |
| F-09 | S03 nursing chip → template, "2 program seçildi", "23 derse uygulanıyor", added (busy "Ekleniyor…") | admin | desktop | PASS | `logs/f09.out` | – |
| F-09 | S02/S04 course options show time + programme ("ING 302 § · 09:20-10:50 · Hemşirelik"), rooms "30 koltuk · sığmaz (35 > 30)", hint "Yönetici olarak gerekçeyle yine de sabitleyebilirsiniz…", "Ekle" disabled until "Gerekçe (zorunlu)"; planner: no reason field, "Yalnız bir yönetici gerekçeyle sabitleyebilir", API 422 TR | admin/planner | desktop + API | PASS | `logs/f09-probe.out`, `shots/F09-S04-pin-template-*.png` | R2-M-12 verified |
| F-09 | S05 pre-check "Kesin kural #74 ING 302 dersini B 201'e sabitliyor: 100 öğrenci 30 kişilik B 201'e sığmaz." | admin | desktop | PASS | `logs/f09.out` | – |
| F-09 | S06 run #11 card "688/716 ders yerleşti · kesin kurallar korundu; 399 kabul edilmiş istisna listelendi"; cancel right after `POST /runs` → 200 CANCELLED; report "Administrator tarafından · 17 Eki 2026 12:46" | admin | desktop + API | PASS* | `shots/F09-S06-*.png`, `logs/f09.out` | QUEUED not caught (run was RUNNING at the cancel); R2-M-17 verified |
| F-09 | S07 KPI "Sorun 399" = tab "Sorunlar 399" = headline = `truth.exceptions_total`; "Veri notları 457" labelled; "Yerleşmeyen dersler 28" with 28 items = `unplaced_list` 28; 14 diagnosis cards; nursing 0 after P11 | admin | desktop + phone | PASS | `shots/F09-S07-report-desktop.png`, `logs/f09.json` | R2-M-04 verified |
| F-09 | S08 publish week: scope + partial ticks (44×44 on phone), list 28 = missing 28, 409 `scope_reduction` without tick, toast "Çalıştırma #11 artık yayımlanan program", focus on "Yayında"; S09 B0 list 35 = 35 | admin | desktop + phone | PASS | `logs/f09.out`, `logs/f09-phone.out` | R2-M-26 run part verified |
| F-09 | compare: #8 vs #10 → 422 "… karşılaştırılamaz: dönemleri farklı…"; #8 vs #7 UI "Kapsamlar farklı (A 1–19. haftalar, B 3. hafta); yalnız ortak 3. hafta karşılaştırıldı" | admin | desktop + API | PASS | `logs/misc.out`, `logs/f09.out` | R2-M-21 compare part verified |
| F-09 | M-01…M-13 @/generate steps 1–5, classes filters, template gallery, /runs/11 (+ publish sheet), cancelled run | admin | phone | PASS* | `logs/pb-_generate*.json`, `logs/pb-_runs*.json` | step 3 "İkisini göster" / "Kural #70 bu planda kapansın" 32 px, step 4 "recheck" 36, report "Tablo olarak göster" 32, "Tümünü göster"/"Excel olarak indir" 36 (R3-M-08); classes filters a side sheet (M-04 false) |
| F-10 | S01 Tab 1 "İçeriğe atla", Tab 2 "Izgaraya geç" → Enter → grid "Pano, Pazartesi, 3. hafta" | admin | desktop | PASS | `logs/f10.out` (`S01.*`) | R1-M-32 verified |
| F-10 | S01 search probe (`calendar-search` after opening the sidebar) | admin | desktop | INCONCLUSIVE | `logs/f10.out`, `logs/f09-probe.out` (`ttSearch`) | no `calendar-sidebar` / `calendar-search` in the DOM at 1440 (locator drift or removed; staff owns R1-S-26) |
| F-10 | S05 planner force → 403 with message_tr "Çakışmaya rağmen taşıma yalnız yöneticilere açık…"; plain move `ok:false` with the conflict | planner | API | PASS | `curl/F10-S05-planner-force.txt` | – |
| F-10 | S06 forced move with reason → banner "Yayımdaki program 1 kesin kuralı bozuyor (katı puan 99) · derslik çakışması: A204 · 3. hafta Pzt P2: HEM 242, PHAR 240 §1 · gerekçe: …"; undo → hard 100 | admin | desktop | PASS | `shots/F10-S06-forced-desktop.png` | R2-M-18 move part verified |
| F-10 | S07 "Sığmaz" C 301 → "80 öğrenci 72 kişilik C 301'e sığmaz", "Taşı" disabled, force panel | admin | desktop | PASS | `shots/F10-S07-sigmaz-desktop.png` | – |
| F-10 | S09 export file names `smartsched-run8-hafta4.xlsx` / `smartsched-run8.xlsx`, `?weeks=99` 422 | admin | desktop + API | PASS | `curl/smartsched-run8-hafta4.xlsx` | R1-M-38 verified |
| F-10 | S10 academician → "Bu sayfaya erişiminiz yok …", no toasts | academician | desktop | PASS | `logs/f10.out` | – |
| F-10 | phone: title "Çizelge · SmartSched" throughout; inspector sheet footer "Taşı…" / "Kilitle" 44 px at y 736 (M-05 ✓); move sheet M-02 0; `open-filters` exists | admin | phone | PASS* | `logs/pb-_timetable*.json` | toolbar 36 px, lock toast "Geri al" 24 px (R3-M-08) |
| F-10 | phone filters sheet: 293 px left panel, 107 targets < 44 px, search input 14 px | admin | phone | FAIL | `logs/pb-_timetable_filters_sheet_.json` | R3-M-05 |
| F-11 | S01 missing role → inline "Bir rol seçin." (aria-invalid, aria-describedby `u-role-error`, focus on the select), cleared on pick | admin | desktop | PASS | `shots/F11-S01-role-error-desktop.png` | R2-M-20 part verified |
| F-11 | S04 limited admin: 7/7 escalations 403, landing /bookings without 403s, roles editor reasons "Bu yetki sizde yok" (31 hints for 31 boxes), picker "Yönetici (eksik: …)" disabled | limited admin | desktop + API | PASS | `logs/f11.out` (`S04.*`), `shots/F11-S04-limited-roles-desktop.png` | R1-M-21 verified |
| F-11 | S05 room "T 101" → stored `T101`, shown "T 101"; non-image photo → "Dosya bir jpg, png, gif ya da webp görseli değil." (sheet + API message_tr) | admin | desktop + API | PASS | `shots/F11-S05-photo-refused-desktop.png` | R1-M-20 verified (canonical storage is the lane's decision) |
| F-11 | S06 duplicate feature → "Bu adda bir özellik zaten var: Projeksiyon" (dialog + toast) | admin | desktop | PASS | `shots/F11-S06-feature-dup-desktop.png` | – |
| F-11 | S08 approver scope reduced → both rules "Bu kural için atanmış onaycı yok; talepler tüm oda onaycılarına, sonra oda sorumlusuna, sonra yöneticilere düşer."; staff request still 202 PENDING | admin | desktop | PASS | `shots/F11-S08-rules-noapprover-desktop.png` | R2-M-19 verified |
| F-11 | /admin/settings: the English roles sentence sits in a closed `<details lang="en">` "İngilizce notları göster" | admin | desktop | PASS | `logs/probe2.out` (`settingsEN`) | – |
| F-11 | /admin/departments: desktop sticky first column, phone cards | admin | desktop + phone | PASS | `logs/f11.out`, `logs/phone-batch.json` | – |
| F-11 | M-01…M-13 @/admin/users (+filters, new-user sheet M-12 ✓), /admin/roles (+editor), /admin/rooms (+new room, features), /admin/approval-rules (+rule form), /admin/audit (+filters), /admin/settings | admin | phone | PASS* | `logs/pb-_admin_*.json` | capsule ✓ on users / approval-rules / audit / departments / sessions / conflicts; /admin/roles "Kaydet" not sticky (known); features "Yeni özellik" not in the capsule; rule-form name input 32 px; "Okundu say"/"Yükle" 36 px (R3-M-08) |
| F-13 | C02 j/k roving, Enter → focus on drawer title "C 303", `a` → "Onaylandı: C 303." in 1.8 s, note untouched; `d` → reject dialog, aria-modal, 12 Tabs stay inside, Esc → row | admin | desktop | PASS | `logs/misc.out`, `logs/probe2.out`, `shots/F13-C02-*.png` | R2-M-09 verified |
| misc | /settings?tab=solver: weights 10/5/1/8/1/10 "varsayılan", header "Ağırlık", phone number inputs 16 px / 44 px, M-02 0 | admin | desktop + phone | PASS | `shots/SOLVER-desktop.png`, `logs/pb-_settings_tab_solver.json` | R2-M-14 verified; save-solver below the fold at scroll 0 (M-05 note) |
| misc | /dashboard: no "0123456789" in main text (desktop + phone) | admin | desktop + phone | PASS | `logs/misc.out` | "Tümünü gör" 75×16 (R3-M-08) |
| misc | R1-M-33 new booking-rule sheet offers no Administrator target (only "Planlamacı"; "Yöneticiler için not") | admin | desktop | PASS | `shots/R1M33-policy-sheet-desktop.png` | – |
| misc | conflicts: forced move into C 303 → 3 conflicts; "Önerilenleri uygula" → "Önerileri gözden geçirin · 3 rezervasyon taşınacak, 0 iptal, 0 korunacak" with each move | admin | desktop | PASS* | `shots/R2M21-conflicts-review-desktop.png` | footer "2 satırın 2 tanesi kararlı" vs 3 decisions (R3-M-09) |
| misc | reset-password confirm `{"token":"12"}` → 400 `invalid_code` with message_tr | anyone | API | PASS | `logs/misc.out` | – |
| MOBILE | crawl of 43 routes at 390 (M-01, M-03, M-06 meta, M-07, M-09 5 labelled tabs, M-11, M-13 844×390 all ✓) | admin | phone | PASS* | `logs/crawl-phone-admin.json`, `shots/crawl_*-phone.png` | residual M-02 / M-05 in R3-M-08; /dashboard 2× 502 on `/health` right after a restore (environment) |
| MOBILE | desktop EN scan of 43 routes: only "Administrator" (the seeded display name) | admin | desktop | PASS | `logs/crawl-desktop-admin.json` | – |

## Re-verification

### Round-2 ids (R2-M-nn) on 8db884fd

| Id | Result | Note |
|---|---|---|
| R2-M-01 | verified | recheck keeps D3 skip / D4 replace at 1440 and 390; POST body and toast match |
| R2-M-02 | verified | "Yayınlandı: #11 artık geçerli plan…", "✓ Yayında", no English |
| R2-M-03 | reopened | the round-2 chain is clean (0/0/0, 563/563, F-07 S12 0 moves) but a section-only priority edit loses planner-locked NUT 121 → R3-M-01 |
| R2-M-04 | verified | Sorun 399 everywhere; "Veri notları 457" labelled |
| R2-M-05 | verified | person reset hides open suggestions, keeps accepted; undo restores |
| R2-M-06 | reopened | dry run == commit and CSV re-upload 0/0 verified; xlsx re-upload 1,329 updates and cp1254 11.8 % unchanged → R3-M-02 |
| R2-M-07 | verified | inline refusal, one entry, no "listed twice" |
| R2-M-08 | open (decision) | planner person priority still 200; owner decision pending |
| R2-M-09 | verified | Enter → drawer title; `a` approves |
| R2-M-10 | verified | no calendar toast on /my-bookings, /profile |
| R2-M-11 | verified in part | audit "undo of" / duplicate row not re-run by me (staff list); focus after section-priority save still `<body>` → R3-M-06 |
| R2-M-12 | verified | sığmaz mark, admin reason, planner refusal, day/time in course picker, Taşı disabled |
| R2-M-13 | verified in part | switches / segments / checkboxes / toast close now 44; residuals in R3-M-08 |
| R2-M-14 | verified | defaults, "Ağırlık", 16 px |
| R2-M-15 | verified in part | footer actions, Kilitle, filters trigger, stable title ✓; the filters sheet itself fails → R3-M-05 |
| R2-M-16 | verified | empty state names the hidden results |
| R2-M-17 | verified | cancel right after POST → CANCELLED; by-line "Administrator" (QUEUED state itself not caught) |
| R2-M-18 | verified in part | move, banner, photo, feature, past, replaced reason Turkish; "faculties" and "Council job …" remain → R3-M-07 |
| R2-M-19 | verified | per-rule warning with the fallback chain |
| R2-M-20 | verified | no-op relink no audit; one `<main>`; inline role error |
| R2-M-21 | verified | review dialog with counts; compare names term and horizon |
| R2-M-22 | verified in part | reset-confirm coded 400 ✓; cancel-scope date counts (FLE-010) and SSO exchange 422 (FLE-014) not built |
| R2-M-23 | verified in part | rule cards and class checkboxes 44 px; step 3 conflict buttons 32 px (R3-M-08) |
| R2-M-24 | open (suggestion) | `truth.forced_overrides 0` with the admin-forced pin present (FLE-012) |
| R2-M-25 | verified in part | job URL, button drop zone, accept, recent list, live bar ✓; phone job page → R3-M-03 |
| R2-M-26 | verified in part | run publish focus on "Yayında" ✓; preview publish and section priority still `<body>` → R3-M-06 |
| R2-M-27 | open (suggestion) | still "Hoş geldiniz, A." (FLE-013) |

### Round-1 ids re-tested

| Id | Result | Note |
|---|---|---|
| R1-M-04 | verified | one count (399) on card / report / KPI / tab / API |
| R1-M-14 | verified | unplaced list 28/28 and 35/35 |
| R1-M-17 | verified in part | move/past/photo/feature/replace TR; "faculties", "Council job işlendi" remain (R3-M-07) |
| R1-M-20 | verified | shown "T 101" everywhere checked; stored canonical `T101` by design |
| R1-M-21 | verified | reasons under disabled permissions |
| R1-M-26 | verified in part | conflicts resolver groups pending requests; two adjacent on-behalf bookings still two rows (not the original request case) |
| R1-M-32 | verified | skip link is the 2nd Tab stop |
| R1-M-33 | verified | Administrator not offered as a policy target |
| R1-M-38 | verified | `smartsched-run8-hafta4.xlsx` |
| R1-M-07 | open (decision) | not re-tested |
| R1-M-36 | not run | needs a CRBS dump |

## New findings

| Id | Severity | Step @ viewport | Finding |
|---|---|---|---|
| R3-M-01 | major | F-05 S10 @1440 | A section-priority edit re-solve drops a planner-locked published class for an equal-priority newcomer |
| R3-M-02 | major | F-08 S11 @API | Re-uploading the same planning workbook plans 1,329 updates; cp1254 only 11.8 % unchanged |
| R3-M-03 | major | F-08 @390 | Intake job page on a phone: "Yaz" not sticky, 63 review buttons 36 px |
| R3-M-04 | minor | F-08 S08 @1440 | The commit panel proposes a new term instead of the existing empty 2026-BAHAR |
| R3-M-05 | major | F-10 @390 | Timetable filters sheet is the desktop sidebar: 107 small targets, 14 px input, side panel |
| R3-M-06 | minor | F-05 S08/S12 @1440 | Focus falls to body after a section-priority save and after publishing a re-solve preview |
| R3-M-07 | minor | F-08 S08/S14 @1440 | Raw "faculties" in the intake confirm/toast; audit reads "Council job işlendi/değiştirildi" |
| R3-M-08 | minor | MOBILE M-02/M-05 @390 | Residual sub-44 controls and top-placed primary actions on admin/planning routes |
| R3-M-09 | trivial | F-02 S05, conflicts @1440 | Small wording mismatches |

### R3-M-01 (major) A section-priority edit re-solve drops a planner-locked published class for an equal-priority newcomer
- **Step:** F-05 S08 → S09 → S10 @1440, reproduced twice from a fresh snapshot restore (deterministic, workers 1)
- **Action:** `/moderation` → Eşleşmeler → PSY 277 §1 (request 1602) → `p` → Yüksek, "Tüm şube", note "akreditasyon" → Kaydet; "Planı yeniden oluştur" → "En az değişiklik" → "Önizleme oluştur" → `/moderation/recreate/11`.
- **Result:** "Önizleme hazır: 0 taşınan, 4 yeni yerleşen, 11 yerleşemeyen", `newly_unplaced 4`, `newly_unplaced_base_conflict 0`, `affected_people 16`, hard 100 → 100, `moved_unexplained 0`. Lost: **NUT 121** (planner-locked in #10; 562 of 563 locked rows kept) "yerleşemedi: sığan derslikler o saatte dolu — C501 (72 kişilik: SYB 111). Karşılanmadı: kilit çakışması; SYB 111 ile öncelik eşit, daha çok ders ve hafta, sonra daha kalabalık sınıf korundu.", EHM 311 §A + §B ("… Kilitli satır …"). Newly placed: EHM 111 §A2, EHM 111 §B1, SYB 111, NUT 402 — all outside the edited scope. With the section **and** person priority staged (the round-2 chain) the same base gives 0 / 0 / 0 and 563/563.
- **Expected:** T-R2-34: a soft change never costs a placed, planner-locked published class; `published_kept` keeps a published class over an equal-priority newcomer; the only allowed loss is a `base_conflict` with its rule. Losses are named (that half holds).
- **Evidence:** `logs/F05-diff-11-sectiononly.json`, `logs/resolve-chk.json`, `logs/f05b.out`, `scripts/r3-resolve-ui.mjs`
- **Seen before as:** R2-M-03 / R1-S-04 (same NUT 121 vs SYB 111 pair lane S named in its done-line)
- **File hints:** smartsched/backend/app/solver/policy.py (`previous` tier / `published_kept` not applied when the changed set is one section), services/moderation.py repair `free` / `scope`

### R3-M-02 (major) Re-uploading the same planning workbook plans 1,329 updates; cp1254 only 11.8 % unchanged
- **Step:** F-08 S10/S11 @API on the fresh stack, after the UI commit of Job A into 2026-BAHAR (19 weeks)
- **Action:** new jobs with (D) `bahar_requests_en.csv`, (C) `bahar_listesi_noktali_virgul.csv` (cp1254 `;`), (X) `bahar_derslik_planlama_listesi_v5.xlsx`; accept all review items; `POST /council/jobs/<id>/commit {term_id: 1, dry_run: true}`.
- **Result:** D: create 0 · update 0 · unchanged 1,340 ✓. X (the very workbook just committed): create 0 · **update 1,329** · unchanged 183; changed field `weeks` (stored 1–19, file 1–14) in every listed row. C: create 0 · **update 1,333** · unchanged 179 (11.8 %), again `weeks`, plus 39 constraint `source_ref`. The same happens against a 16-week term (weeks 1–16 → 1–14).
- **Expected:** I5 / D14: re-upload of the same meetings changes 0 rows; the cp1254 export ≥ 99 % unchanged (T-R2-19 check).
- **Evidence:** `logs/f08-re.json`, `logs/F08-final-dry-job3.json`, `logs/F08-final-dry-job4.json`, `logs/F08-redo-dryC.json`
- **Seen before as:** R2-M-06 (dry run == commit is fixed: 1,512 = 1,512)
- **File hints:** smartsched/backend/app/council/commit.py (`fields_for_existing`: the commit writes the term's week_count, the re-read derives 14), importers week derivation

### R3-M-03 (major) Intake job page on a phone: "Yaz" not sticky, 63 review buttons 36 px
- **Step:** F-08 phone battery on `/onboarding/1` and `/onboarding/2` @390 touch (assertTouch)
- **Result:** M-05: `onboarding-commit-button` at y 6,490 of a 6,652 px page, not fixed or sticky (free only at the very end); M-02: 63 offenders ("Onayla" 89×36 ×32, "Reddet" 90×36 ×31, "Engelleyenlerin hepsini onayla" 204×36). Lane C reported M-01/02/03/05 passing on this route.
- **Expected:** F-08 mobile expectations: a floating "◌ {n} bekliyor (Kaydet)" capsule above the tab bar; review actions ≥ 44 px.
- **Evidence:** `logs/pb-_onboarding_1_masked_.json`, `logs/f08-phone.json` (`jobPage`), `shots/F08-phone-job-commitbar.png`
- **File hints:** components/onboarding/commit-panel.tsx, review list buttons

### R3-M-04 (minor) The commit panel proposes a new term instead of the existing empty 2026-BAHAR
- **Step:** F-08 S08 @1440 (fresh stack: one empty term 2026-BAHAR, 19 weeks)
- **Result:** "Döneme yaz · Dönem grubu BAHAR · normal dönem · 16 hafta", fields Dönem kodu "BAHAR", Dönem adı "Bahar", Hafta 16. Pressing "Yaz" as offered created term #2 "BAHAR" (16 weeks) next to the empty 2026-BAHAR; the API dry run against term 1 and the UI write went to different terms. Typing "2026-BAHAR" / 19 writes into the existing term (confirm "2026-BAHAR dönemine yazılsın mı?").
- **Expected:** The panel offers the existing matching term (2026-BAHAR) first, or warns that a new term will be created next to it.
- **Evidence:** `shots/F08-S08-commit-panel-desktop.png`, `logs/f08-redo.out`, `logs/f08-ui2.json`
- **File hints:** components/onboarding/commit-panel.tsx term group proposal

### R3-M-05 (major) Timetable filters sheet is the desktop sidebar
- **Step:** F-10 phone, `open-filters` @390 touch
- **Result:** The trigger exists (93×36) and opens the desktop CalendarSidebar as a left panel 293 px wide (M-04 false), 107 targets under 44 px (mini calendar days 28×28, prev 32×32, class list items 261×40), a search input at 14 px (M-03), M-10 false.
- **Expected:** F-10 / MOBILE M-04: filters as a bottom sheet with ≥ 44 px controls and 16 px inputs.
- **Evidence:** `logs/pb-_timetable_filters_sheet_.json`
- **File hints:** components/timetable/calendar-view.tsx (`filters-sheet`), calendar-sidebar on coarse pointers

### R3-M-06 (minor) Focus falls to body after a section-priority save and after publishing a re-solve preview
- **Result:** after "PSY 277: öncelik kaydedildi…" `activeElement` is `<body>` (lane D reported focus on the row); after "Yayınlandı: #11 …" on `/moderation/recreate/11` also `<body>`. The person-priority save and the run-report publish keep focus correctly.
- **Evidence:** `logs/f05b.out` (`S08.after`, `S12.after`)
- **File hints:** components/moderation/priority-editor.tsx (popover close), recreate-preview.tsx publish

### R3-M-07 (minor) Raw "faculties" in the intake confirm/toast; audit reads "Council job …"
- **Result:** the commit confirm and the success toast list "faculties · 11 yeni · 0 değişecek" between Turkish entity names; the audit list reads "Council job işlendi | #1" / "Council job değiştirildi".
- **Evidence:** `logs/f08-ui2.json` (`confirm`, `toasts`), `shots/F08-S14-audit-desktop.png`
- **File hints:** onboarding entity labels, audit-model.ts labels for `council.*`

### R3-M-08 (minor) Residual sub-44 controls and top-placed primary actions
- **Result (390, touch):** /rooms code links 37×20 (88), /dashboard "Tümünü gör" 75×16, /classes and /requests chips 32 px, /moderation chips 28 px and "Diğer işlemler" 36×36, timetable toolbar 36 px, lock-toast "Geri al" 24 px tall, run report "Tablo olarak göster" 32 / "Tümünü göster" 36, Studio step 3 conflict buttons 32, step 4 "Tekrar kontrol et" 36, rule-form name input 32, `/admin/settings` "Okundu say"/"Yükle" 36, webhook/policy/session/heat-csv buttons 36. M-05: primary at the top on /moderation (recreate-open y 179), /programs/new (y 410), /exams/invigilation, /runs/compare, /onboarding, /admin/rooms features ("Yeni özellik" not in the new capsule), /admin/roles "Kaydet" (known open item).
- **Evidence:** `logs/crawl-phone-admin.json`, `logs/phone-batch.json`, `logs/pb-*.json`
- **Seen before as:** R2-M-13 rest

### R3-M-09 (trivial) Small wording mismatches
- Bell "Gerekçe: Seri #1 ile değişti" vs card "Seri #1 ile değiştirildi"; conflicts footer "2 satırın 2 tanesi kararlı" while the review lists 3 decisions.
- **Evidence:** `logs/f02-desktop-r.out`, `shots/R2M21-conflicts-review-desktop.png`

## Notes for the orchestrator
- The ledger rows (docs/PROGRESS.md START/DONE) were not written: this persona may write only under docs/testing.
- Recovery after the restart used the saved snapshots; no step result above mixes data from before and after the restart without a restore in between.

```jsonl
{"flow":"F-05","step":"S10","persona":"admin","viewport":"desktop","result":"FAIL","evidence":["logs/F05-diff-11-sectiononly.json"],"issue":"R3-M-01","severity":"major","sha":"8db884fd"}
{"flow":"F-08","step":"S11","persona":"admin","viewport":"API","result":"FAIL","evidence":["logs/f08-re.json"],"issue":"R3-M-02","severity":"major","sha":"8db884fd"}
{"flow":"F-08","step":"M-05@/onboarding/<id>","persona":"admin","viewport":"phone","result":"FAIL","evidence":["logs/pb-_onboarding_1_masked_.json"],"issue":"R3-M-03","severity":"major","sha":"8db884fd"}
{"flow":"F-08","step":"S08","persona":"admin","viewport":"desktop","result":"FAIL","evidence":["logs/f08-redo.out"],"issue":"R3-M-04","severity":"minor","sha":"8db884fd"}
{"flow":"F-10","step":"M-04@/timetable (filters)","persona":"admin","viewport":"phone","result":"FAIL","evidence":["logs/pb-_timetable_filters_sheet_.json"],"issue":"R3-M-05","severity":"major","sha":"8db884fd"}
```
