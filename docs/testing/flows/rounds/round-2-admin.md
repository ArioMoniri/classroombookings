# Flow loop round 2 · admin · 2026-10-17

Ledger: `flow-r2-admin-2026-10-17` · persona tester (admin: Fatih Bey as classroom planning officer, system administrator and approver for every room; plus the limited admin helper for F-11) · plan: [README](../README.md), [MOBILE](../MOBILE.md), brief `scratchpad/briefs/ROUND2.md`
Snapshot: `deb38315` (`deb38315eac87ed0e924cdf87e886b3e46545094`, `claude/focused-wright-ktt0ss`), frozen worktree in the scratchpad (removed at the end) · main stack API :19230, web :19231 (`REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`), fresh stack API :19232, web :19233 (`--fresh`, F-08 only; F-07 ran on the main stack because its preconditions need rooms and the published Bahar/Güz plans) · SMTP sink :2528 · load 0.1–7.7 on 4 cores (2–4 while the flows ran; 7+ only during the two frontend builds), so M-14 timings are advisory and were not run (README §8)
Dates (README §4.3): TODAY 2026-10-17 · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D5 2026-11-19 · D6 2026-11-26 · Chromium 141 (chromium-1194), Playwright 1.56 library, `scripts/record/lib/touch.mjs` contexts (`assertTouch` before every phone measurement, `shot()` for full-page screenshots)
Data: all three real terms (Bahar 2026, Güz 2026-27, Final 2026) and the room master. Runs made by `stack.sh runs` before the snapshot: #7 Bahar week 3 (688/716, hard 100), #8 Bahar term (683/717, hard 100, published = B0), #9 Güz week 3 (524/530), #10 Güz term (517/530, published = G0). Made during the round: #11 Bahar week 3 from the Studio (688/716, hard 100), #12 Bahar term cancelled, #13 planner week run, Güz re-solves #11 (= N), #12 (pin + rerun, published in F-05 S12), #13 (F-07 Part C preview, discarded).
Names: masked by `stack.sh` and the §4.4 seed (`kvkk_mask.py --verify` → `left 0` on both stacks; the fresh stack was masked in F-08 S09 after S11). Only fictional `@smartsched.local` accounts with initials were used; the seeded admin's display name is "Administrator".
Accounts: the seed (`personel.test` P. T., `akademisyen.test` A. T. linked to instructor 157 "S. E.", `planner.test` P. L., `viewer.test` V. T.), plus `ds.test`, `ds.test2`, `nopass.test` (F-11 S01/S02), `limited.admin` L. A. (role "Kullanıcı yöneticisi": setup.users, setup.roles, room.view, book_single.create), `davet.test` D. T. (invite).
Preconditions applied: admin approves for all rooms; `approval_mode=all` set through the UI (F-01 S01) and re-applied with curl after every restore; F-01 Part B switched it to `rules` and back; calendar sync signed off and switched off again in F-11 S09; Microsoft Entra with the fake tenant `1111…5555` for F-12 (switched off afterwards); AI policy on/off with a sign-off in F-11 S10; webhooks switched on with one external URL; a forced pin #74 (ING 302 → B 201, admin reason) for F-09 S04–S07, removed before S08.
Viewports: desktop 1440×900 (mouse, keyboard) and phone 390×844 (isMobile, hasTouch, tap only; landscape 844×390 for M-13). The tablet was not in this round's brief.
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2admin/ev` (`shots/` 183 files, `logs/` 132 JSON results incl. every MOBILE battery, `curl/` 57 request/response captures and exports with tokens redacted, `scripts/` 44 Playwright scripts that can be re-run, `../mail/` 45 sink messages). Paths below are relative to that root.

## BLUF

**27 new findings: 0 blocker · 6 major · 18 minor · 3 suggestion.** Round-1 ids: **38 R1-M re-run → 27 verified, 7 verified in part (the part that stays open is named), 3 reopened, 1 not re-run** (R1-M-36 CRBS upgrade); the 7 integrity items from the staff round: **R1-S-01/06/07/09/17 verified, R1-S-04 reopened, R1-S-02 not re-run**.

The hard rules of the integrity fix hold on this snapshot: an impossible pin is refused on every write path with "100 öğrenci 30 kişilik B 201'e sığmaz" (API 422, Studio template toast, planner 422 even with a reason, admin only with a written reason, named in the pre-check and in the run as "kesin kural #74 … sığmaz"); one headline for the verdict on the Studio card, the run report, the timetable header and the API; a week run cannot be published without the scope tick ("Evet, 3. hafta dışındaki haftalar #8 programından yayından kalksın", 409 `scope_reduction` without it); a forced clash needs an administrator and a reason ("Yine de taşı" + "Gerekçe (zorunlu)"), drops the published run to 99 with a banner that names the rule and the reason, and a non-active run with a forced break answers 409 `forced_breaks`; a week-vs-term comparison no longer says "B daha iyi"; an empty invigilation plan is "Boş plan" and `activate` answers 409 `empty_plan`.

What still blocks a confident go-live from the admin's chair:
1. **R2-M-01 (major, F-02):** "Yeniden denetle" in the weekly series preview silently resets every per-date choice; the summary counts coincide, so the admin books the date he skipped and never replaces the one he chose to replace.
2. **R2-M-02 (major, F-05):** publishing a re-solve preview succeeds on the server (G0 → #12) while the admin sees an English error toast "Invalid response for POST /runs/12/activate: Invalid input" and a page that still says "Yayında değil".
3. **R2-M-03 (major, F-05/F-07, reopens R1-S-04):** a minimal-change re-solve after one priority edit moves 6 classes "nedensiz" and loses 2 planner-locked rows; the pin + rerun loses 17 placed classes. The confirm now lists each loss with a cause and a tick, which is the honest half of the fix.
4. **R2-M-04 (major, F-09, reopens part of R1-M-04):** the run report still shows two numbers for its problems: "Sorun 457" / tab "Sorunlar 457" next to the headline's "398 kabul edilmiş istisna" (and 400 diagnosis items).
5. **R2-M-05 (major, F-06):** "Öğrenilenleri sıfırla" for one person reports "Sıfırlandı" but the person's open suggestions stay open (same ids and states before and after).
6. **R2-M-06 (major, F-08):** the intake dry run and the commit disagree (dry run "create 1511" meeting requests, commit "duplicates_skipped 1332, updated 6"); a re-upload of the same CSV after the commit changes 779 rows, not 0; the cp1254 CSV of the same list updates 1332.

Also open from round 1: R1-M-07 (KVKK AI default still "Evet sayılır: geri alınmadıkça dahil", waiting for the owner), R1-M-26 (a two-period request is still two conflict rows; T-R1-13), R1-M-35 (calendar push tenant text), and the parts named in the re-verification table (R1-M-14 unplaced list shorter than its count, R1-M-17 English server strings, R1-M-20 room code loses its space, R1-M-21 no disabled-permission reasons, R1-M-29 solver tab inputs 14 px, R1-M-38 week export file name).

## Fatih Bey's scenarios

| Scenario | Result |
|---|---|
| Import the Bahar list and the weekly grid | ✓ by `stack.sh` on the main stack (3 terms + room master, names masked). On the fresh stack through the UI (F-08): xlsx + CSV export + scanned PDF in one job, 2,926 direct rows, PDF marked "Okunmadı: bu dosyada okunabilir metin yok … yapay zekâ modeli gerekir", dry run plans 1,512 meeting requests for the two formats together (no double import inside a job). The dry run ≠ commit counts and the re-upload deltas are R2-M-06 |
| Find a course (PHAR 240) | ✓ timetable chip "PHAR 240 §1, Eczacılık 2. sınıf, A 206, Pazartesi 08:30–10:50, 80 öğrenci, 92 koltuk"; inspector "Kaynak: Planlama listesi · Sayfa1 · satır 545", "Neden burada" with ✓ rows, "Geçmiş" across runs #7/#8/#11/#13 |
| Generate week 3 | ✓ run #11 from the Studio: 688/716, FEASIBLE_PARTIAL, hard 100, 5 s solve; the card, the report, the timetable header and `stats.truth` all say "688/716 ders yerleşti · kesin kurallar korundu; 398 kabul edilmiş istisna listelendi" (R1-M-04/R1-S-07 verified). The report's "Sorun 457" is R2-M-04 |
| Move PHAR 240 to A 206 from 23 Feb | ◐ PHAR 240 §1 already sits in A 206 and no other ≥80-seat room is free Monday P1–P3 in any week (the dialog lists A 206 as "Şu anki oda" and 6 "Sığmaz", 12 "Dolu", 12 "Uygun değil" rooms), so the date-split was exercised the other way round: Monday P11–P13 in A 102 from week 4 through the new "Başlangıç haftası" picker (R1-M-31 verified). Split exact (weeks 1–3 A 206, 4–14 A 102, API and the audit's two `assignment.bulk_move` rows), hard stays 100 (R1-M-05/R1-S-01 verified), toast "PHAR 240 §1 → A 102 taşındı · Geri al", focus on the chip, undo/redo with "Geri alındı: …" / "Yinelendi: …". TIP rooms A 201/A 203 are "Uygun değil · TIP dersliği … bu ders oraya konamaz (kesin kural)" |
| Turkish request: nursing first-years before 17:30 | ✓ without an AI key the example chip opens "Belirli saatten sonra ders olmasın" prefilled with Hemşirelik + Hemşirelik (İngilizce), 1. sınıf, 17:30 ("23 derse uygulanıyor (%2,6)") and asks "Adı benzeyen 6 program daha var (yüksek lisans / doktora olabilir). Kural onlara da uygulansın mı?" (R1-M-13/T-R1-46 verified). Run #11 honoured it: 19 placed year-1 nursing classes, none after P11 |
| Export the week to Excel | ◐ "Bu haftayı Excel'e aktar" with week 4 on screen gives one sheet "Hafta 4", the term file 14 sheets, `?weeks=99` → 422 "99. hafta dönemin dışında"; both files are still named `smartsched-run8.xlsx` (R1-M-38 part reopened) |
| Infeasible request (100 students → 30-seat B 201, hard; ING 302 has 100, not 102, in this data) | ✓ refused at the edit: Studio template "Sunucu bu isteği kabul etmedi. 100 öğrenci 30 kişilik B 201'e sığmaz", API 422 `capacity`, planner 422 with a reason, admin 201 only with a reason (`source_ref.capacity_override` audited); pre-check "Kesin kural #74 ING 302 dersini B 201'e sabitliyor: 100 öğrenci 30 kişilik B 201'e sığmaz" with three fixes; run #11 diagnosis "ING 302 yerleşemedi: kesin kural #74 onu yalnız B 201'e sabitliyor ve 100 öğrenci 30 kişilik B 201'e sığmaz … (sığan derslikler: A207 (120 kişilik), C201 (126 kişilik), A204 (156 kişilik))" (R1-M-03 verified). Residual friction in R2-M-12 |

## Step table

Result codes: PASS · PASS* (passes with a note or locator drift) · FAIL (issue id in the last column) · BLOCKED · SKIP · INCONCLUSIVE · NOT RUN. MOBILE rows are per route and viewport; `M-xx@route` rows that passed are folded into one "M-01…M-13@route" row, failing criteria get their own row.

| Flow | Step | Persona | Viewport | Result | Evidence | Issue |
|---|---|---|---|---|---|---|
| F-01 | S01 approval mode in the UI, toast "Kaydedildi", focus stays in the form, audit `settings.update`, roles page "Onaysız doğrudan rezervasyon" | admin | desktop | PASS | `shots/F01-S01-approval-mode-desktop.png`, `curl/F01-S01-org-settings.txt`, `logs/f01-a.json` | – |
| F-01 | S02–S05 staff request C 303 P7–P8 ("Talep et", busy label, toast, pending cells, one group, duplicate 409 + detail sheet, Taleplerim "1 bekliyor") | staff (precondition) | desktop | PASS | `shots/F01-S03-staff-desktop.png`, `curl/F01-S04-duplicate.txt`, `curl/F01-S02-check.txt` | – |
| F-01 | S06 academician requests (API 202 ×4) | academician (precondition) | – | PASS | `logs/f01-a.json` | – |
| F-01 | S07 bell "Bildirimler, 5 okunmamış" → /approvals?request=1&group=1, drawer "Per 22 Eki · P7–P8 (13:30–15:00)", "Tek talep: 2 ders saati…", "2 saatin hepsini onayla" → toast "2 ders saati onaylandı: C 303.", focus on the next request's H2, one mail with the note | admin | desktop | PASS | `shots/F01-S07-drawer-desktop.png`, `shots/F01-S07-after-approve-desktop.png`, `../mail/0007.eml` | – |
| F-01 | S07 bell sheet, drawer as bottom sheet, sticky "Onayla" 44 px, legend hidden | admin | phone | PASS | `shots/F01-S07-bell-phone.png`, `shots/F01-S07-drawer-phone.png`, `logs/f01-phone-approvals-drawer.json` | – |
| F-01 | S08 reject dialog: 4 codes ≥ 44 px, "0 / 1000", confirm aria-disabled, "Bir gerekçe türü seçin." / "Gerekçeyi yazın; yalnız boşluk sayılmaz.", toast "Reddedildi. Talep edene bildirildi.", focus on the next H2; API 422 `reason_required` ×2, `reason_code` for bogus, 200 with code + text | admin | desktop | PASS | `shots/F01-S08-reject-dialog-desktop.png`, `curl/F01-S08-decide-*.txt` | – |
| F-01 | S08 reject sheet on phone (M-04, rows 44×350, M-12 field and confirm above a 336 px keyboard, M-05) | admin | phone | PASS | `shots/F01-S08-reject-phone.png`, `logs/f01-c.json` | – |
| F-01 | S09 academician mail "Oda talebiniz reddedildi: …" with "Gerekçe: Oda uygun değil: Bu saatte bölüm sınavı var." and "Önerilen derslikler (otomatik): B 207."; staff `GET /approvals/mine` lists only own ids | admin/API | – | PASS | `../mail/0008.eml`, `logs/f01-b.json` | – |
| F-01 | S10 withdraw 200, second 409 `not_pending`, staff 403 `not_requester`; "Geri çekildi" under "Karara bağlanan" | admin | desktop + phone | PASS | `curl/F01-S10-withdraw.txt`, `shots/F01-S10-decided-phone.png` | – |
| F-01 | S12 admin books directly ("Bu saati rezerve et", 201, toast "C 201, Per 22 Eki P1 için rezerve edildi"); planner → 202 PENDING | admin | desktop + phone | PASS | `shots/F01-S12-booksheet-phone.png`, `logs/f01-b.json` | – |
| F-01 | S14–S15 rules mode in the UI, rule on A 104 (1 step, designated approvers), staff direct 201 and request 202 "1 adım", reject without reason 422 | admin | desktop + phone | PASS | `shots/F01-S14-rule-form-desktop.png`, `shots/F01-S14-rule-form-phone.png`, `logs/f01-d.json` | – |
| F-01 | M-01…M-13@/approvals (list, drawer open, Karara bağlanan) | admin | phone | PASS* | `logs/f01-phone-approvals-*.json` | toast close 20×20, tabs 38 px → R2-M-13 |
| F-01 | M-01…M-13@/bookings (free-slot list, book sheet, M-12 note) | admin | phone | PASS | `logs/f01-phone-bookings.json`, `logs/f01-phone-booksheet.json` | – |
| F-01 | M-01…M-13@/admin/approval-rules (+ rule form sheet) | admin | phone | PASS* | `logs/f01-phone-rule-form.json` | rule name input 32 px, switches 38×22 → R2-M-13 |
| F-02 | S01 direct booking on behalf of P. T. (hint about SMTP, no approval notice, 201, toast, mail "Sizin adınıza rezervasyon yapıldı") | admin | desktop + phone | PASS | `shots/F02-S01-sheet-desktop.png`, `../mail/0025.eml` | – |
| F-02 | S02–S03 weekly preview: 6 rows with week numbers, "Tatil · Cumhuriyet Bayramı · Atlanır", D4 "Dolu" with "Yerine geç", summary "4 rezerve edilecek · 1 atlanacak · 1 tatil" = API preview | admin | desktop + phone | PASS | `shots/F02-S03-preview-desktop.png`, `curl/F02-S03-preview.txt` | – |
| F-02 | S04 per-date choices, "Hiçbiri" → "0 tarihi rezerve et" disabled, "Boşların hepsi", submit with choices (phone run: body carries do_not_book / replace, staff booking cancelled "replaced by series #1") | admin | phone | PASS | `logs/f02-phone-a.json` | – |
| F-02 | S04 "Yeniden denetle" then submit: the request body is back to the defaults, D3 booked, D4 kept | admin | desktop | FAIL | `logs/f02-desktop-a.json` (`S04.posts`), `shots/F02-S04-choices-desktop.png` | R2-M-01 |
| F-02 | S05 staff: cancelled booking with reason, bell "Rezervasyonunuz iptal edildi", mail | staff/API | – | PASS* | `logs/f02-phone-a.json` | reason text "replaced by series #1" is English → R2-M-18 |
| F-02 | S06 planner series → 202; drawer "Onaylanacak tarihler · 2 tarihten 2 seçili; diğerleri reddedilir."; "1 tarihi onayla"; declined date "Aynı saat başka bir talebe verildi" | admin | desktop + phone | PASS | `shots/F02-S06-instances-desktop.png`, `logs/f02-desktop-b.json` | – |
| F-02 | S07 edit scope "Bu ve sonrakiler" → "4 rezervasyon güncellendi", focus on "Düzenle" | admin | desktop + phone | PASS | `logs/f02-*-b.json` | – |
| F-02 | S08/S09/S11 cancel one / future / all: dialog, "Gerekçe" hint, toasts "1 / 2 / 2 rezervasyon iptal edildi", API scopes exact, focus on the freed cell | admin | desktop + phone | PASS* | `shots/F02-S08-cancel-desktop.png`, `shots/F02-S09-cancel-phone.png` | scope options carry no date counts → R2-M-22; on phone the scope is a `<select>` |
| F-02 | S10 audit undo "Rezervasyon #5 geri alınsın mı?" → "1 rezervasyon geri getirildi", booking BOOKED again | admin | desktop + phone | PASS* | `shots/F02-S10-audit-desktop.png` | focus to BODY, duplicate row "#3", "undo of #164" → R2-M-11 |
| F-02 | S12 past period: POST for yesterday → 409 `range_min` "bookings must be made at least 0 day(s) ahead" | staff/API | – | PASS* | `curl/F02-S12-past.txt` | English message, code not `past` → R2-M-18 |
| F-02 | M-02@/bookings (recurring preview sheet): per-date segments 85×30, "Boşların hepsi" 32, "Takvimi aç" 32×32 | admin | phone | FAIL | `logs/f02-phone-a.json` | R2-M-13 |
| F-02 | M-01…M-13@/my-bookings, @/admin/audit (filters sheet exists, cards, undo 36 px) | admin | phone | PASS* | `logs/f02-phone-audit.json` | undo buttons 36 px → R2-M-13 |
| F-05 | S00 user ↔ instructor link: "Öğretim elemanı kaydı · S. E. · Değiştir", search by initials, "Öğretim elemanı bağlandı" | admin | desktop | PASS* | `logs/f05.json` | an audit row is written although the same instructor was picked again → R2-M-20 |
| F-05 | S05 console: tabs with counts, "2026-GUZ · Yayında: #10 · taleplerin %95'i karşılandı", "Bekleyen değişiklik yok" | admin | desktop + phone | PASS | `shots/F05-S05-console-desktop.png`, `shots/F05-phone-console.png` | – |
| F-05 | S06 Kişiler search "PSY 277" → 1 row, Enter → profile "2 dönem geçmişi", timeline with "Talep metni", "Öneriler" tab | admin | desktop + phone | PASS | `shots/F05-S06-profile-desktop.png`, `shots/F05-phone-profile.png` | `habits` test id absent (drift) |
| F-05 | S07 Eşleşmeler: chips, search under the default chip "Karşılanmayan" finds 0, under "Tümü" 2 rows; inspector "İstenen / Atanan / Oda: istenmedi … Gün: karşılandı"; Esc returns focus to the row; Bahar PHY 102 "Karşılanmadı: planlama birimi kararı (gerekçe girilmemiş)" | admin | desktop | PASS* | `shots/F05-S07-inspector-desktop.png` | default chip hides results → R2-M-16 |
| F-05 | S08 priority: `p` opens the inspector with the priority editor, "Şu an: Yüksek · kişi", staged link "2 değişiklik yayında değil", G0 unchanged; person priority toast "Dr. Öğr. Üyesi S. E.: öncelik kaydedildi (4 talep). Bir sonraki çözümde etkili."; viewer 403, planner section 200 | admin | desktop + phone | PASS* | `shots/F05-S08-priority-desktop.png`, `logs/f05.json` | planner person priority → 200 (R2-M-08); focus to BODY after save (R2-M-11) |
| F-05 | S09 recreate sheet (base #10, 2 staged changes listed, "En az değişiklik", limits, policy line) → "Yeniden çözüm #11 başladı." → run #11 parent 10, inactive, workers 1 | admin | desktop + phone | PASS | `shots/F05-S09-recreate-desktop.png`, `shots/F05-phone-recreate.png` | – |
| F-05 | S10 preview #11: "9 taşınan, 2 yeni yerleşen, 10 yerleşemeyen", chain "#11 ← #10", "Zorunlu puan 100 → 100", locks: 2 of 563 planner-locked rows missing in N, "Düzenlenen kapsam dışındaki 9 ders taşındı (6 tanesi nedensiz)" | admin | desktop + phone | FAIL | `shots/F05-S10-preview-desktop.png`, `logs/F05-diff-11.json`, `shots/F05-phone-preview.png` | R2-M-03 |
| F-05 | S10 determinism (second preview with nothing changed) | admin | API | NOT RUN | – | `POST /moderation/resolve` needs `changed_request_ids` for a repair; not re-issued from the UI for lack of time |
| F-05 | S11 pin "Bu taşımayı engelle (eski yerinde tut)" → "ACU 141: eski yerine sabitlendi", rerun → #12 "1 taşınan, 1 yeni yerleşen, 26 yerleşemeyen (17 yeni)", chain "#12 ← #11 ← #10" | admin | desktop | FAIL | `logs/f05-b.json` | R2-M-03 (17 losses); the edit list shows the pin twice |
| F-05 | S12 publish confirm: counts, "17 ders dersliğini kaybediyor:" with causes and a tick, "Yayınla" disabled until ticked; server activates #12 (G0 inactive, audit `run.activate`); UI toast "Invalid response for POST /runs/12/activate: Invalid input", state stays "Yayında değil" | admin | desktop | FAIL | `shots/F05-S12-confirm-desktop.png`, `shots/F05-S12-published-desktop.png`, `logs/f05-c.json` | R2-M-02 |
| F-05 | S13/S14 no changed class for the linked academician → no notice, no mail (correct); `/moderation/me/matchings` follows run 12 | academician/API | – | PASS | `logs/f05-c.json` | – |
| F-05 | M-01…M-13@/moderation (console, inspector sheet, recreate sheet), @/moderation/people/157, @/moderation/recreate/11 (capsule sticky above the tab bar) | admin | phone | PASS* | `logs/f05-phone-*.json` | chips 28 px, priority segments 30 px, row actions 36 px → R2-M-13 |
| F-06 | S01 cards on instructor 98: "Öneri · Bina tercihi", confidence word + meter, claim, "Kanıt" toggle, impact line, "farklı dönem verisi içerir", "Kabul et · Normal / Reddet / Ertele" | admin | desktop + phone | PASS | `shots/F06-S01-cards-desktop.png`, `shots/PB-_moderation_people_98_Öneriler_-phone.png` | – |
| F-06 | S03 accept → one LEARNED soft constraint weight 5 with `source_ref.prior_id`, receipt "Yumuşak tercih eklendi", live "Öneri kabul edildi: yumuşak tercih eklendi.", focus on the card; undo switches the rule off and reopens the suggestion; "Kalıcı tercih olarak kabul et…" confirm with the three sentences → `scope: persistent` | admin | desktop | PASS | `shots/F06-S03-receipt-desktop.png`, `logs/f06.json` | – |
| F-06 | S04 reject with "Bu dönem farklı", refresh keeps it dismissed, history undo | admin | desktop | NOT RUN | `logs/f06.json` | the tester's API call accepted SR before the UI step; not repeated |
| F-06 | S05 snooze "Bir sonraki çözüme kadar" → receipt "Ertelendi: Bir sonraki çözüme kadar · …", live "Öneri ertelendi." | admin | desktop | PASS | `logs/f06.json` | – |
| F-06 | S06 Studio Güz rules: group "Öğrenilen öneriler (11)" | admin | desktop | PASS | `shots/F06-S06-studio-desktop.png` | – |
| F-06 | S07 planner accepts 201, reset 403, persistent 403, memory page "Öğrenme belleğini yalnızca planlama yöneticileri yönetebilir"; viewer "Yalnızca görüntüleme…" with no action buttons | planner/viewer | desktop | PASS | `logs/f06.json` | – |
| F-06 | S08 memory summary = API (24.171 observations, "10 açık · 3 kabul · 0 red") | admin | desktop + phone | PASS* | `shots/F06-S08-memory-desktop.png` | the snoozed count is not shown |
| F-06 | S09 L5/L6: 14 open suggestions are building / period / tag only; no room-level claim, no A 204 or B 407 value, cross-season evidence only on building claims | admin | API | PASS | `curl/F06-suggestions.json` | – |
| F-06 | S10 reset person: dialog texts, "Sıfırla" disabled under 3 characters, toast "Sıfırlandı · Geri al", row "Bir kişinin belleği · … · Geri alma için 29 gün kaldı", undo "Sıfırlama geri alındı"; the person's suggestions stay `open` throughout | admin | desktop | FAIL | `logs/f06.json` | R2-M-05 |
| F-06 | S11 reset term "2026-GUZ öğrenmeden çıkarılsın mı?" + undo | admin | desktop | INCONCLUSIVE | `logs/f06.json` | the accepted building suggestion kept its state; open ones not re-read before the undo |
| F-06 | S12 reset all: "sifirla" → "Yazılan kelime eşleşmiyor.", "sıfırla" accepted, summary {} after, undo restores "10 açık · 3 kabul · 1 ertelenmiş" | admin | desktop + phone | PASS | `logs/f06.json`, `logs/pb-_moderation_learning__reset_dialog_.json` | – |
| F-06 | S13 KVKK erase: dialog, typed word, "Şimdi sil", row "KVKK silme · … · Hemen silindi" with no Geri al; `/learning/priors` for the person still returns a section-level prior | admin | desktop | PASS* | `logs/f06.json` | a section prior of the erased person remains (note) |
| F-07 | S01 landing (title, subtitle, Hedef dönem, Taslaklarım, Oluşturulanlar, no example button); viewer "Program oluşturmak için planlama düzenleme izni gerekir" | admin/viewer | desktop + phone | PASS | `logs/f07.json`, `shots/F07-phone-landing.png` | – |
| F-07 | S02 start → `/programs/new/1?step=program`, rail with statuses, draft listed by the API | admin | desktop | PASS | `logs/f07.json` | – |
| F-07 | S03 "MBĞ" → "Ders kodlarında Türkçe harf kullanılmıyor"; "Devam" focuses the error summary "Bu adımda 3 hata var" with "Yine de devam et"; reload keeps the values; another context resumes from "Taslaklarım · kaldığınız yer: Program" | admin | desktop | PASS | `logs/f07.json` | – |
| F-07 | S04 paste: "3 satır eklenecek · 1 satır atlandı …", "Ders kodu 'mbg532' → MBG 532 olarak düzeltildi.", "3 dersi ekle", warning "MBG 598: T+U+L = 0; 6. adımda haftalık saat girin" | admin | desktop | PASS | `logs/f07.json` | – |
| F-07 | S05 sections 120/80/75, "Bu dönemde eşleşen şube yok.", people "T. E. · yeni", "S. K. · yeni", warning "MBG 534 §1: öğretim elemanı atanmadı…", cohort "MBG 1. sınıf" with "Haftada 7 saat zorunlu ders; kohort için en az 1 gün gerekir" | admin | desktop | PASS* | `logs/f07.json` | the same new person could be added twice → R2-M-07 |
| F-07 | S06 patterns and fit: "120 öğrenci · 3 oda sığar: A 207 (120), C 201 (126), A 204 (156)", "3 saat yerleşti" | admin | desktop | PASS | `logs/f07.json` | – |
| F-07 | S07 pre-check and S08 "Yalnızca oluştur" (confirm "2027-BAHAR dönemine 1 program, 3 ders, 3 şube, 1 kohort … 30 gün içinde geri alınabilir.") | admin | desktop | FAIL | `logs/f07.json`, `curl/F07-S08-commit.txt` | R2-M-07: pre-check and commit refuse with "Kayıt yazılamadı: instructor 491 is listed twice" (422), nothing committed, S09 undo therefore BLOCKED |
| F-07 | S12 Part C: tiny programme into Güz, "Oluştur ve plana ekle" → preview #13 "1 taşınan, 3 yeni yerleşen, 24 yerleşemeyen", "Zorunlu puan 100 → 100", MBG 961 §1 under "Yeni yerleşen"; "Vazgeç" keeps #12 published; the programme's records stay in the term (audit `program_draft.commit`) | admin | desktop | PASS* | `shots/F07-S12-preview-desktop.png`, `logs/f07.json` | "1 ders taşındı (1 tanesi nedensiz)" → R2-M-03 |
| F-07 | M-01…M-13@/programs/new (landing, step "8/8 · Oluştur ve çöz", stepper sheet, sticky footer 56 px) | admin | phone | PASS* | `shots/F07-phone-step.png`, `logs/f07.json` | "Düzelt" 37×16 → R2-M-13; two `<main>` landmarks → R2-M-20 |
| F-08 | S01 `/onboarding`: "Kurulum", drop zone is a `div` with one nested interactive, labelled file input without an `accept` list, "Dosya seç", "Hatırlanan kararlar" | admin | desktop + phone | PASS* | `logs/f08.json`, `shots/F08-phone-onboarding.png` | HEAD wording; zone not a button (note for the suggester) |
| F-08 | S02 three files: "Başlat · 3 dosya", "· Yönetici kapattı" next to the AI switch | admin | desktop | PASS | `shots/F08-S02-files-desktop.png` | – |
| F-08 | S03 progress "Okunuyor · Kural tabanlı (yapay zekâsız) · dosya 1/3 …" per-file phases; job REVIEW; `/onboarding?job=1` | admin | desktop | PASS* | `shots/F08-S03-job-desktop.png` | `/onboarding/1` is a 404 (the job lives at `?job=`), so the phone battery of the job page could not run |
| F-08 | S04 PDF: "Okunmadı: bu dosyada okunabilir metin yok (taranmış belge ya da görsel olabilir); okumak için yapay zekâ modeli gerekir", xlsx/csv "Bu iş için yapay zekâ kapalı; yalnız kural tabanlı okuma · 206 kural benzeri metin bulundu…" | admin | desktop | PASS | `logs/f08.json` | – |
| F-08 | S05 review: 33 items (file, merge, issue, rule_text, plan), 3 blocking merge questions, no column-mapping items (both files took direct paths); accept-all → READY, blocking 0 | admin | API | PASS* | `logs/F08-review-A.json`, `curl/F08-S05-review-post.txt` | the "Eşleme" column UI of the spec is not what HEAD shows |
| F-08 | S06 rows 2,926 all `direct` / `ready`; provenance fields present (`provenance` key); 2 rows rejected | admin | API | PASS* | `logs/F08-rows-A.json` | the PHAR 240 R545 cross-check was not isolated by the harness |
| F-08 | S07 dry run: meeting_requests create 1512 / unchanged 15, courses 933, instructors 403; nothing written | admin | API | PASS | `curl/F08-S07-dryrun.txt`, `logs/F08-dryrun-A.json` | – |
| F-08 | S08 commit from the UI: bar "Döneme yaz … 3 engelle", button disabled although the API review had cleared the blockers; API commit after Job B: "duplicates_skipped 1332, meeting_requests_updated 6" versus the dry run's "create 1511" | admin | desktop + API | FAIL | `logs/f08.json`, `logs/F08-dryrun-A.json` | R2-M-06 |
| F-08 | S10 Job B (CSV again): 4 items "remembered from … job 1" with suggestions, commit without decisions 409 "3 review item(s) must be decided first"; after Job A's commit a fresh CSV re-upload dry run = create 0 / update 779 / unchanged 569 | admin | API | FAIL | `logs/F08-review-B.json`, `logs/f08.json` | R2-M-06 |
| F-08 | S11 Job C (cp1254 `;`): Turkish letters intact (17 in the first 5 rows); dry run update 1332 / unchanged 179; the file entry carries `format` but no `encoding`/`delimiter` fields | admin | API | FAIL | `logs/F08-dryrun-C.json` | R2-M-06 |
| F-08 | S09 `stack.sh mask` → "masked 399 instructors and 19 other cells · left 0" | admin | CLI | PASS | `logs/f08.json` | – |
| F-08 | S12 viewer: review 200 without samples, POST review 403, commit 403, UI without enabled decision buttons | viewer | desktop + API | PASS | `logs/f08.json` | – |
| F-08 | S13 PNG renamed `.xlsx` refused at upload: "sahte.xlsx: Dosyanın adı .xlsx ile bitiyor (Excel çalışma kitabı), ama içeriği bir görsel; adını gerçek türüne göre düzeltin ya da asıl tabloyu yükleyin" (400) | admin | API | PASS* | `logs/f08.json` | the weekly grid workbook in the same job was refused with it; routing not seen |
| F-08 | S14 undo of `council.commit` from the audit log | admin | desktop | NOT RUN | `logs/f08.json` | the audit row for the commit exists (`council.commit`); its "Geri al" was not exercised |
| F-09 | S01 scope: Bahar → Bir hafta → H3, "1 hafta boyunca 58 derslikte 869 ders planlıyorsunuz.", reload keeps H3 (`aria-pressed`), no late overwrite; a new browser context still opens on today's term (known follow-up) | admin | desktop | PASS | `shots/F09-S01-scope-desktop.png`, `logs/f09-a.json` | – |
| F-09 | S02 Dersler: PHAR 240 rows with 80 students, source; pin button opens "Her zaman bu derslikte" | admin | desktop | PASS* | `logs/f09-a.json` | the pin dialog is the generic template, not a room list limited to ≥ 80 seats → R2-M-12 |
| F-09 | S03 nursing rule: no-key sentence, chip → prefilled template, both programmes, "23 derse uygulanıyor", master's question, "Kesin" rule listed as "Hemşirelik, Hemşirelik (İngilizce) 1. sınıf için 17:30'dan sonra ders olmasın" | admin | desktop | PASS* | `shots/F09-S03-chip-template-desktop.png`, `shots/F09-S03-builder-desktop.png` | no toast after "Kuralı ekle" (the "Ekleniyor…" busy label is the only signal) |
| F-09 | S04 infeasible pin: API 422, planner 422, admin override 201 audited; template refusal toast; course picker lists each ING 302 meeting twice without day/time | admin | desktop + API | PASS* | `shots/F09-S04-pin-refused-desktop.png`, `curl/F09-S04-pin-*.txt` | R2-M-12 |
| F-09 | S05 pre-check: "Engel var · 10 ders kesin kurallarınızla yerleştirilemiyor", "İmkânsız dersler 6", pin #74 named with 3 fixes, "MBT 698 + MBT 598 C 205 … özellikleri uymuyor (PC)" | admin | desktop + API | PASS* | `shots/F09-S05-precheck-desktop.png`, `curl/F09-S05-precheck.json` | "10 ders" vs "6" in one panel (note) |
| F-09 | S06 generate: confirm "Yine de oluştur", run #11 card "688/716 ders yerleşti · kesin kurallar korundu; 398 kabul edilmiş istisna listelendi" + exception lines, numbers = API | admin | desktop | PASS | `shots/F09-S06-run-card-desktop.png`, `logs/F09-run11.json` | – |
| F-09 | S06 cancel: a QUEUED run has no cancel button and `POST /cancel` answers 422 until it is RUNNING; cancelled run #12 stays in the list | admin | desktop + API | PASS* | `logs/f09-d.json` | R2-M-17 |
| F-09 | S07 report: verdict + exceptions identical on card / report / grid header / API, 14 diagnosis cards in Turkish with culprits, "Dersliksiz kalan 28 ders", nursing year-1 classes all ≤ P11, planner_lock / exception_reasons on the rows; load 78 ms to network idle | admin | desktop + phone | FAIL | `shots/F09-S07-report-desktop.png`, `logs/F09-run11-asg.json`, `shots/F09-phone-report.png` | R2-M-04 (KPI "Sorun 457") |
| F-09 | S08 publish week run: scope "2026-BAHAR, 3. hafta", partial line "28 dersin dersliği yok (688/716 yerleşti)", unplaced list, partial tick, scope tick "Evet, 3. hafta dışındaki haftalar #8 programından yayından kalksın", 409 `scope_reduction` without it, "Yayınla" enabled only with both, toast "Çalıştırma #11 artık yayımlanan program" | admin | desktop + phone | PASS* | `shots/F09-S08-publish-confirm-desktop.png`, `curl/F09-S08-activate-noconfirm.txt`, `shots/F09-phone-publish.png` | list shows 19 of 28 (R1-M-14 part); focus to BODY after publish |
| F-09 | S09 re-publish B0: "dönemin tamamı", "34 dersin dersliği yok (683/717 yerleşti)", list 22 of 34, toast, badge "Yayında", exactly one active run | admin | desktop | PASS* | `shots/F09-S09-runs-list-desktop.png` | list shorter than its count (R1-M-14 part) |
| F-09 | S10 refusals: cancelled run "İptal edildi · admin@smartsched.local tarafından · …", no Yayınla, KPIs "—", activate 409 "only a finished run…", delete active 409, no delete button; forced-break run 11 → 409 `forced_breaks` (TR message) and 200 with `confirm_forced_breaks` | admin | desktop + API | PASS* | `shots/F09-S10-cancelled-desktop.png`, `curl/F10-S06-activate-forced-noconfirm.txt` | cancelled-by shows the e-mail, not the name → R2-M-17; re-activating the already-active broken run #8 answered 200 without the tick (note) |
| F-09 | S11 presets: menu opens, "Mevcut ayarları kaydet…" → "“Bahar test ayarı” hazır ayarı kaydedildi" | admin | desktop | PASS | `shots/F09-S11-presets-desktop.png` | – |
| F-09 | S12 planner: start a week run 202; forcing the capacity pin 422 `capacity` | planner/API | – | PASS | `logs/f09-d.json` | – |
| F-09 | M-01…M-13@/generate (5 steps via "Geri / İleri", template gallery sheet, classes filters) | admin | phone | FAIL | `logs/f09-phone2-s*.json`, `shots/F09-phone-step3.png` | rule cards: 32 × "Kesin/Mümkünse" 88×38 and "Düşük/Normal/Yüksek" 66×38, policy switches 38×22, class checkboxes 16×16 → R2-M-13/R2-M-23 |
| F-09 | M-01…M-13@/runs/11 (+ publish sheet) | admin | phone | PASS* | `logs/f09-phone-report.json`, `logs/f09-phone-publish.json` | tabs 38 px, "Tümünü göster" 36 px |
| F-10 | S01 keyboard: skip link "Izgaraya geç" (`skip-to-grid`) at the 30th Tab, Enter lands on "Pano, Pazartesi, 3. hafta"; Enter on the chip opens the inspector (Ne zaman nerede, Kim, Neden burada ✓ rows, Kaynak satır 545, Haftalar 1–14, Not, Geçmiş, Taşı…/Kilitle); Esc returns to the chip | admin | desktop | PASS* | `shots/F10-S01-inspector-desktop.png`, `logs/f10.json` | no `calendar-search` on 1440 (drift); 30 stops before the skip link |
| F-10 | S02 pick-up "PHAR 240 §1 alındı. Ok tuşları taşır, Boşluk bırakır, Esc iptal eder.", arrow "… A 307, Pzt 08:30–10:50 üzerinde: SOS 432 §1 ile çakışıyor…", Space → move dialog with "Boş ve sığar / Sığmaz / Dolu / Uygun değil" and seat counts, scopes + "Başlangıç haftası", "Sunucu kontrolü: uygun", "Önceki haftalar A 206 dersliğinde kalır", "Taşınıyor…", toast, split exact, hard 100, audit | admin | desktop | PASS | `shots/F10-S02-move-dialog-desktop.png`, `shots/F10-S02-moved-desktop.png`, `logs/f10.json` | – |
| F-10 | S03 cancel pick-up "Taşıma iptal edildi."; S04 undo / redo toasts and API | admin | desktop | PASS | `logs/f10.json` | – |
| F-10 | S05 planner: dialog "Çakışmaya rağmen taşımayı yalnızca yönetici yapabilir", Taşı disabled; API force 403 "moving despite a conflict is admin-only", plain move `ok:false` with conflicts | planner | desktop + API | PASS | `shots/F10-S05-planner-desktop.png`, `curl/F10-S05-planner-force.txt` | – |
| F-10 | S06 admin force: panel "Bu taşıma kesin bir kuralı bozuyor… Gerekçe (zorunlu)", "Yine de taşı" disabled until the reason, then banner "Yayımdaki program 1 kesin kuralı bozuyor (katı puan 99) · derslik çakışması: A102 week 3 day 1 P1: PHAR 240 §1, PHAR 474 §1 · gerekçe: “Bölüm başkanı onayı, tek seferlik” (Administrator)", report verdict "683/717 ders yerleşti · 1 kesin kural bozuk (1 gerekçeli zorunlu taşıma)", API 422 without reason; undo (API move back) → hard 100, broken 0 | admin | desktop | PASS* | `shots/F10-S06-force-ui-desktop.png`, `shots/F10-S06-forced-desktop.png`, `shots/F10-S06-report-desktop.png` | mixed-language rule text → R2-M-18 |
| F-10 | S07 capacity: "Sığmaz" rows say "80 öğrenci 72 kişilik C 301'e sığmaz" and open the reason panel; the plain "Taşı" stays enabled and does nothing when pressed | admin | desktop | PASS* | `shots/F10-S07-plain-desktop.png`, `logs/f10-c.json` | R2-M-12 |
| F-10 | S08 lock: "PHAR 240 §1 kilitlendi · Geri al", chip label "… kilitli"; "Kilidi aç" works; the split week-3 row has no "Kilitle" in its inspector | admin | desktop | PASS* | `logs/f10-c.json` | R2-M-15 |
| F-10 | S09 export: week file 1 sheet "Hafta 4", term file 14 sheets, `?weeks=4` → 1 sheet, `?weeks=99` → 422 "99. hafta dönemin dışında"; both downloads named `smartsched-run8.xlsx` | admin | desktop | PASS* | `curl/ui-week4-smartsched-run8.xlsx`, `curl/smartsched-run8.xlsx`, `curl/F10-export-w4.xlsx` | R1-M-38 part reopened |
| F-10 | S10 academician `/timetable` → "Bu sayfaya erişiminiz yok …" inside the shell, no toasts, no 403 noise | academician | desktop | PASS* | `logs/f10-c.json` | `timetable-no-access` id absent (drift) |
| F-10 | M-08@/timetable agenda list, chips 365×60 with full course codes | admin | phone | PASS | `shots/F10-phone-timetable.png`, `logs/f10-phone-timetable.json` | – |
| F-10 | M-05@/timetable (inspector sheet): "Taşı…" 36 px at the top of the sheet, no sticky footer | admin | phone | FAIL | `logs/f10-phone-inspector.json`, `shots/F10-phone-inspector.png` | R2-M-15 |
| F-10 | M-04/M-02/M-03@/timetable (move sheet): rooms 342×44, selects 44 px / 16 px, sheet full width | admin | phone | PASS | `logs/f10-phone-move.json`, `shots/F10-phone-move.png` | – |
| F-10 | filters sheet (`open-filters`) | admin | phone | NOT RUN | – | no `open-filters` trigger on the phone timetable (drift or missing) → R2-M-15 |
| F-11 | S01 user form: empty submit → "Kullanıcı adı ya da e-posta yazın." next to the field, the missing role only as a toast "Bir rol seçin."; API create / disable; disabled and wrong password both 401 `invalid credentials` | admin | desktop | PASS* | `logs/f11.json`, `logs/f11-b.json` | role error as a toast → R2-M-20 |
| F-11 | S02 CSV with a header row: "2 ds.test Oluşturuldu · 3 nopass.test Parola yok · 4 personel.test E-posta var", summary "3 satır: 1 oluşturuldu, 1 parola yok, 1 e-posta var" | admin | desktop | PASS | `shots/F11-S02-import-desktop.png` | – |
| F-11 | S03 role "Kullanıcı yöneticisi" (keys in tooltips, 70 permissions), limited.admin created | admin | desktop | PASS* | `logs/f11.json` | focus to BODY after "Kaydet" |
| F-11 | S04 limited admin: 8/8 escalation attempts 403 (own role, ADMIN user, self, TEACHER + skip_approval, new role, admin password, ADMIN invite, org settings); landing `/bookings` without 403s; picker "Yönetici (eksik: Rezervasyon taleplerini onayla…)" disabled; roles editor 70 disabled boxes with 0 `role-disabled-hint` | limited admin | desktop | PASS* | `shots/F11-S04-limited-desktop.png`, `logs/f11.json` | R1-M-21 part reopened |
| F-11 | S05 room: "Test dersliği oluşturuldu", stored as `T101`, edit sheet with "Kişi sayısı" (42 saved), bad photo "Dosya bir jpg, png, gif ya da webp görseli değil.", delete of a booked room 409 | admin | desktop + phone | PASS* | `shots/F11-S05-room-desktop.png`, `logs/f11-b.json`, `logs/pb-_admin_rooms__new_room_sheet_.json` | code loses its space (R1-M-20 part); "Görsel işlenemedi: the file is not a readable…" tail in English → R2-M-18 |
| F-11 | S06 features: starter "6 özellik eklendi: Projeksiyon, …", adopt "Eklenecek yeni bir şey yok.", facets list Projeksiyon, impact endpoint | admin | desktop + phone | PASS* | `logs/f11.json`, `logs/pb-_admin_rooms__features_.json` | "a feature named 'Projeksiyon' exists" English → R2-M-18; features grid 16 px checkboxes → R2-M-13 |
| F-11 | S07 approval mode: 422 for "sometimes", limited 403, "all" saved | admin | API | PASS | `logs/f11.json` | – |
| F-11 | S08 rules on C Blok and on tag PC saved; after removing the admin's approver scope the rules page shows no "onaycı yok" warning | admin | desktop | FAIL | `shots/F11-S08-rules-noapprover-desktop.png` | R2-M-19 |
| F-11 | S09 calendar KVKK: "Onay kaydı yok…", notice text, confirm disabled until the ack, API record with by/at/legal basis, audit, off again; webhooks off by default, loopback refused in Turkish, secret `whsec_…` shown once | admin | desktop + phone | PASS* | `shots/F11-S09-integrations-desktop.png`, `logs/f11.json` | stray toast "Takvim eşitleme kapatıldı." while saving a webhook → R2-M-10; `calendar-signoff` text not found by id (drift) |
| F-11 | S10 AI policy: pill "Yapay zekâ kapalı", confirm disabled without the ack, API 422 ×2, sign-off "Administrator tarafından 17 Ekim 2026 06:43 tarihinde KVKK onayıyla açıldı … · bildirim 2026-10-15", audit, off again | admin | desktop + phone | PASS | `shots/F11-S10-ai-policy-desktop.png`, `logs/pb-_settings__AI_policy_.json` | – |
| F-11 | S11 audit domain sentences ("Yapay zekâ politikası değiştirildi", "Webhook eklendi · https://…", "Takvim eşitleme ayarı değiştirildi"), actor filter, CSV export | admin | desktop + phone | PASS* | `shots/F11-S11-audit-desktop.png` | raw keys stay as subjects ("#ai.kvkk_signoff") |
| F-11 | M-01…M-13@/admin/users (list, filters sheet, new-user sheet: opaque, save sticky, M-12), @/admin/roles, @/admin/rooms (+ new room sheet, features) | admin | phone | PASS* | `logs/pb-_admin_*.json`, `shots/PB-_admin_*-phone.png` | roles 16 px boxes and non-sticky save, tabs 38 px → R2-M-13 |
| F-12 | S01/S02/S10 login page: labels, per-field messages, `inputmode=email`, `autocomplete`, alert gets focus, password cleared, 429 after 10 failures with Retry-After 299; phone inputs 16 px / 48 px, M-12 | all | desktop + phone | PASS | `shots/F12-S01-login-*.png`, `logs/f12-login.json` | – |
| F-12 | S03 landings: staff/academician/limited → `/bookings`, admin/planner → `/dashboard`, no 403, `?next=/my-bookings` kept, `//evil.example` and `https://evil.example` → `/bookings` | all | desktop | PASS* | `logs/f12.json` | the welcome toast prints only the first initial ("Hoş geldiniz, A.") |
| F-12 | S04 logout: cookie gone, old token 401, Back and direct URL → `/login?next=…` | staff | desktop | PASS | `logs/f12.json` | – |
| F-12 | S05 password change: "Şu anki parola yanlış.", "İki parola aynı değil.", "En az 8 karakter kullanın.", old 401 / new 200, second session → `/login?…&reason=expired` with "Oturumunuzun süresi doldu. Yeniden giriş yaptığınızda kaldığınız sayfaya dönersiniz." | staff | desktop | PASS* | `shots/F12-S05-after-change-desktop.png`, `logs/f12-b.json` | the changed session itself stays on /profile with only the stray calendar toast → R2-M-10 |
| F-12 | S06 forced change page texts, autocomplete, redirect back until done, "Parola değiştirildi" then `/my-bookings` | staff | desktop | PASS | `logs/f12-b.json` | – |
| F-12 | S07 reset code: neutral answer, mail "SmartSched parola sıfırlama / password reset" with "24 saat geçerli", wrong code "Kod hatalı ya da süresi dolmuş. Yenisini isteyin.", right code → "Parolanız değiştirildi. Şimdi oturum açabilirsiniz.", reuse refused; admin "Tek kullanımlık sıfırlama kodu" dialog says the code was mailed and is not shown | staff/admin | desktop + phone | PASS* | `logs/f12-b.json`, `logs/pb-_reset-password.json` | page says "Kodların süresi bir süre sonra dolar." (R1 U-21 wording) → R2-M-22 |
| F-12 | S09 LDAP "Dene" | admin | desktop | INCONCLUSIVE | `logs/f12-b.json` | the button stays disabled until base DN etc. are filled |
| F-12 | S11 SSO config: 422 `no_public_url` until a public URL exists, then 200 without echoing the secret, tenants common/organizations/consumers/consumer-GUID 422, ADMIN default role 422 `default_role_privileged`, limited 403 | admin | API | PASS | `curl/F12-S11-entra-put.txt`, `logs/f12-b.json` | – |
| F-12 | S12 login with SSO on: "Microsoft ile giriş yap" 400×44, hints, collapsed local door, no forbidden words; off → no link | anyone | desktop | PASS | `shots/F12-S12-login-sso-desktop.png` | – |
| F-12 | S13 start → 302 to login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize with code, S256, state, nonce, redirect_uri under the public URL; evil `next` dropped; off → `/login?error=not_enabled` | anyone | API | PASS | `logs/f12-b.json` | – |
| F-12 | S14 forged state → `/login?error=failed&ref=…` ("Giriş yapılamadı." focused), access_denied → `cancelled` (status, focus not stolen), state reuse → failed; failed vs nonsense identical text | anyone | API + desktop | PASS | `logs/f12-b.json` | – |
| F-12 | S15 exchange with a random ticket → 422 "String should have at least 16 characters" | anyone | API | PASS* | `logs/f12-b.json` | validation detail instead of the generic 401 → R2-M-22 |
| F-12 | S16 invite 30 days, limited ADMIN invite 403, bind 201, revoke 204 leaves the placeholder inactive, list does not repeat the token | admin | API | PASS | `logs/f12-b.json` | the revoked-link page text was not captured |
| F-12 | S17 oidc-only: staff local 401, admin local 200 and `?method=local` shows the form, last admin lock/demote 409 | admin | API + desktop | PASS | `logs/f12-b.json` | – |
| F-13 | A03 recipient language: academician in EN gets bell "Your room request was declined: …" and mail "Reason: Not enough seats: Sınav haftası"; admin UI stays Turkish | admin | API | PASS | `../mail/0041.eml` | – |
| F-13 | B01 OS reduced motion: drawer and bell open with `transform: none`, no moving animations, nothing idle | admin | desktop + phone | PASS | `logs/f13.json`, `logs/f13-b.json` | – |
| F-13 | B02 in-app "Hareketi azalt" (`/settings?tab=appearance`): `data-motion=reduced` survives a reload, drawer transform none | admin | desktop | PASS | `logs/f13-b.json` | – |
| F-13 | B03 reduced transparency (in-app and OS media): drawer, bell and phone tab bar `backdrop-filter: none` with an opaque gradient | admin | desktop + phone | PASS | `logs/f13-b.json` | – |
| F-13 | B04 motion budget | admin | phone | INCONCLUSIVE | – | load 2–4 on 4 cores while other testers ran solvers (README §8) |
| F-13 | C02 admin keys: `d` on a focused row opens the reject dialog; after Enter the drawer autofocuses "Talep edene not", so `a` types into it | admin | desktop | PASS* | `logs/f01-d.json` | R2-M-09 |
| MOBILE | crawl of 42 routes (M-01, M-03, M-06 meta `viewport-fit=cover, interactive-widget=resizes-content`, M-07, M-09 5 tabs with labels, M-11, M-13) | admin | phone | PASS* | `logs/crawl-phone-*.json`, `shots/crawl_*-phone.png` | M-09 "Talepler 99+" badge clipped; /admin/departments table not pinned; /rooms and /admin/roles title-only tooltips → R2-M-13 |
| Re-verify | R1-M-01 resolver: 3 conflicts for the staff's pending C 303 requests after a forced move, options with reasons, dry run 200, real apply 200 (moved 1, notified 1) | admin | desktop + API | PASS* | `shots/R1M01-conflicts-desktop.png`, `curl/R1M01-apply-dry.txt`, `curl/R1M01-apply-real.txt` | "Önerilenleri uygula" gave no visible result → R2-M-21 |
| Re-verify | R1-M-10 compare #8 vs #11: the page keeps "Karşılaştır" disabled, API "#8 ve #11 aynı dönemin aynı türden çalıştırmaları değil" | admin | desktop + API | PASS* | `curl/R1M10-compare.json` | wrong reason sentence → R2-M-21 |
| Re-verify | R1-M-11 invigilation on the Final board: "Boş plan", no scores, no publish button, `activate` 409 `empty_plan` with the reason, "Tüm eğitmenlerle yeniden çalıştır" offered | admin | desktop + API | PASS | `shots/R1M11-invigilation-desktop.png` | – |
| Re-verify | R1-M-33 exam-period card lists "Final 2026: 1.–3. haftalar (01.06.2026 – 21.06.2026)", "Bahar 2026: 17.–19. haftalar (…)", "0 sınav odası seçili" | admin | desktop | PASS | `logs/reverify.json` | – |
| Re-verify | R1-M-07 KVKK AI default: "Evet sayılır: geri alınmadıkça dahil · Kayıtlı ayar" still selected | admin | desktop | FAIL | `shots/R1M07-kvkk-ai-desktop.png` | R1-M-07 open (owner decision) |

## Round-1 ids re-run on deb38315

| Id | Result | Note |
|---|---|---|
| R1-M-01 | verified | dry run and real apply answer 200 through `/bookings/conflicts/12/apply`; the page shows no "500". UI apply button: see R2-M-21 |
| R1-M-02 | verified | scope tick and partial tick; 409 `scope_reduction` without `confirm_scope_reduction`; server words in the confirm |
| R1-M-03 | verified | refused on API, template (toast), planner; admin override needs a reason; pre-check `pin_capacity`; run diagnosis names rule #74 and the fitting rooms |
| R1-M-04 | verified in part | one headline on card/report/grid/API; the KPI "Sorun 457" / tab "Sorunlar 457" next to 398 listed exceptions is R2-M-04 |
| R1-M-05 | verified | a clean move keeps hard 100; the forced clash lowers it to 99 with a banner, reason and author; undoing the override restores 100 and empties `truth.broken` |
| R1-M-06 | verified | "Yine de taşı" + "Gerekçe (zorunlu)" in the move dialog; planners read "Çakışmaya rağmen taşımayı yalnızca yönetici yapabilir" |
| R1-M-07 | reopened | still "Evet sayılır: geri alınmadıkça dahil · Kayıtlı ayar" (owner decision pending) |
| R1-M-08 | verified in part | top bar 44×44, Kurulum sub-navigation 44 px, inspector/move rows 44 px, bell items 98 px; the residual sub-44 controls are listed in R2-M-13 |
| R1-M-09 | verified | user sheet full height, opaque white, "Oluştur" sticky at 712–756 px, M-12 passes |
| R1-M-10 | verified | no "B daha iyi"; a week-vs-term comparison is refused (misleading sentence, R2-M-21) |
| R1-M-11 | verified | "Boş plan", no scores, no publish, 409 `empty_plan` |
| R1-M-12 | verified | H3 survives a reload and a click right after load; a new browser context opens on today's term (known follow-up, not a regression) |
| R1-M-13 | verified | chip → prefilled template, two programmes in one rule, master's programmes offered |
| R1-M-14 | verified in part | week wording "3. hafta" fixed; the unplaced list still shows fewer entries than its count (19/28, 22/34) |
| R1-M-15 | verified | "İptal edildi · … tarafından · …", "Çalıştırma bitmeden durduruldu: çizelgesi, puanı ve sorun listesi yok; yayımlanamaz.", KPIs "—" |
| R1-M-16 | verified | built-in roles read Yönetici / Planlamacı / Öğretim elemanı / İzleyici in the users table, pickers and the login hint; dialogs close with "Kapat"; `/runs` title "Çalıştırmalar · SmartSched". "Administrator" on screen is the seeded admin's display name |
| R1-M-17 | verified in part | webhook loopback, photo type, SSO tenant refusals are Turkish; still English: `range_min` message, "a feature named … exists", "Görsel işlenemedi: the file is not a readable …", "replaced by series #1", "undo of #164", the move-preview conflict sentences and the forced-break rule text (R2-M-18) |
| R1-M-18 | verified | domain sentences in the audit list and the undo dialog ("Rezervasyon #5 geri alınsın mı?"); raw keys only as subjects |
| R1-M-19 | verified | header row detected, per-row results, summary line and toast |
| R1-M-20 | verified in part | capacity editable in the sheet; the code is still stored without its space (`T101`); the three-way grouping was not re-checked |
| R1-M-21 | verified in part | the limited admin lands on a page he can use and the role picker says "(eksik: …)" in Turkish; the roles editor still shows 0 disabled-permission reasons |
| R1-M-22 | verified | focus stays in the form after "Kaydet" and moves to the next request's title after a decision |
| R1-M-23 | verified | `d` on a focused row opens the reject dialog |
| R1-M-24 | verified | "Onay kuralı yok; şu anda her talep önce onaya gider (Rezervasyon onayı: Her talep önce onaya)." |
| R1-M-25 | verified | ADMIN default role 422, revoked invite leaves the account inactive, the invite list does not repeat the token |
| R1-M-26 | reopened | the staff's two-period request appears as separate one-period conflict rows (T-R1-13 open) |
| R1-M-27 | verified | report reaches network idle in well under a second on this stack |
| R1-M-28 | verified | per-field messages, `inputmode=email`, focus on the alert |
| R1-M-29 | verified in part | admin inputs 16 px on phone except `/settings?tab=solver` (six 14 px number inputs, 16 px checkboxes) |
| R1-M-30 | verified | "Filtreler" sheets on /admin/users and /admin/audit |
| R1-M-31 | verified | "Başlangıç haftası" picker on any week; focus back on the chip; dative "C 301'e" |
| R1-M-32 | verified in part | "Izgaraya geç" skip link exists and works, but it is the 30th Tab stop (41 without it) |
| R1-M-33 | verified in part | exam weeks and dates are shown; the Administrator-as-target part was not re-checked |
| R1-M-34 | verified | "Per 22 Eki · P7–P8 (13:30–15:00)", one "Kapat" |
| R1-M-35 | reopened | "Kiracı (tenant): organizations (her kurum hesabı), common, …" unchanged |
| R1-M-36 | not re-run | the CRBS dry run needs a dump; not repeated this round |
| R1-M-37 | verified in part | sheets are opaque; the desktop login layout is unchanged (suggestion stays) |
| R1-M-38 | verified in part | busy labels are gerunds ("Taşınıyor…", "Ekleniyor…"); week export still `smartsched-run8.xlsx`; URL filters and pin-template names not re-checked |
| R1-S-01 | verified | TIP rooms are "Uygun değil · kesin kural" in the dialog; a clean move keeps 100 |
| R1-S-02 | not re-run | the nursing rule was entered with class year 1 (the chip's prefill); the programme-wide hard window was not re-issued |
| R1-S-04 | reopened | 2 locked rows lost and 6 unexplained moves after one priority edit; 17 losses after pin + rerun (the confirm now lists them with a tick) — R2-M-03 |
| R1-S-06 | verified | cancelled run has no Yayınla; forced-break run answers 409 `forced_breaks` in Turkish |
| R1-S-07 | verified | the card sentence equals the report's |
| R1-S-09 | verified | "Yine de taşı" with a required reason for the administrator |
| R1-S-17 | verified | rows carry `planner_lock` (773 of 837 in run 11) and `exception_reasons`; origin stays SOLVER but the flags make the audit possible |

## New findings

| Id | Severity | Step @ viewport | Finding |
|---|---|---|---|
| R2-M-01 | major | F-02 S04 @1440 | "Yeniden denetle" silently discards the per-date book / skip / replace choices |
| R2-M-02 | major | F-05 S12 @1440 | Publishing a re-solve preview succeeds on the server while the UI shows an English error and "Yayında değil" |
| R2-M-03 | major | F-05 S10/S11, F-07 S12 @1440 | A minimal-change re-solve moves classes without a reason and loses planner-locked rows |
| R2-M-04 | major | F-09 S07 @1440 + 390 | The run report counts its problems twice: "Sorun 457" next to "398 kabul edilmiş istisna" |
| R2-M-05 | major | F-06 S10 @1440 | Resetting one person's learning memory leaves their open suggestions untouched |
| R2-M-06 | major | F-08 S07/S08/S10/S11 @API | The intake dry run does not predict the commit, and re-uploads change hundreds of rows |
| R2-M-07 | minor | F-07 S05/S07/S08 @1440 | The wizard accepts the same new person twice on a section and then fails with a raw message |
| R2-M-08 | minor | F-05 S08 @API | A planner can set a person-level priority (200) |
| R2-M-09 | minor | F-13 C02 @1440 | Enter on an approvals row focuses the note textarea, so the A/D/R keys type into it |
| R2-M-10 | minor | F-02 S07–S11, F-11 S09, F-12 S05 @1440 + 390 | Stray calendar-sync toasts on pages that did not ask for calendar sync |
| R2-M-11 | minor | F-02 S10, F-05 S08 @1440 | Audit undo: duplicate row, English "undo of #164", focus falls to body after undo and after priority save |
| R2-M-12 | minor | F-09 S02/S04, F-10 S07 @1440 | Capacity: no fit hint before submitting a pin, no UI override, plain "Taşı" enabled on a "Sığmaz" room and silent |
| R2-M-13 | minor | MOBILE M-02 @390 | Residual controls under 44 px on admin screens |
| R2-M-14 | minor | /settings?tab=solver @390 + 1440 | Solver tab: 14 px inputs, every default weight shows 0, raw "w" header |
| R2-M-15 | minor | F-10 @390 | Phone timetable: inspector actions at the top of the sheet, no "Kilitle" on a split row, no filters trigger, title flips to "Pazartesi" |
| R2-M-16 | minor | F-05 S07 @1440 + 390 | Searching Eşleşmeler under the default "Karşılanmayan" chip returns 0 rows silently |
| R2-M-17 | minor | F-09 S06/S10 @1440 | A queued run cannot be cancelled; the cancelled-by line shows the e-mail address |
| R2-M-18 | minor | several @1440 | English or mixed-language server strings reach the Turkish UI |
| R2-M-19 | minor | F-11 S08 @1440 | A rule whose scope no approver covers shows no warning |
| R2-M-20 | minor | F-05 S00, F-07, F-11 S01 @1440 + 390 | Small defects: needless `user.instructor_link` audit row, two `<main>` landmarks in the wizard, role error only as a toast |
| R2-M-21 | minor | R1-M-01/R1-M-10 re-checks @1440 | "Önerilenleri uygula" gives no visible result; the compare refusal names the wrong reason |
| R2-M-22 | suggestion | F-02 S08, F-12 S07/S15 | Cancel scopes without date counts; "bir süre sonra" on the reset page; 422 instead of 401 for a bad ticket |
| R2-M-23 | minor | F-09 @390 | Rule cards on the phone: 160 segmented controls at 38 px and 16 px class checkboxes |
| R2-M-24 | suggestion | F-09 S07 @1440 | The forced capacity override is not listed under the run's accepted exceptions |
| R2-M-25 | minor | F-08 S01/S03 @390 + 1440 | Intake: the job page is not addressable (`/onboarding/1` → 404), the drop zone is not a button, no `accept` list |
| R2-M-26 | minor | F-09 S08/S09, F-05 S08 @1440 | Focus falls to body after "Yayınla" and after saving a person priority |
| R2-M-27 | suggestion | F-12 S03 @1440 | "Hoş geldiniz, A." greets with the first initial only |

### R2-M-01 (major) "Yeniden denetle" silently discards the per-date book / skip / replace choices
- **Step:** F-02 S04 @1440 (phone run without the recheck passes)
- **Action:** Weekly series A 202 · P5 from D1 to D6. Set D3 (5 Kas) to "Atla" and D4 (12 Kas, the staff booking) to "Yerine geç", pressed "Yeniden denetle", then "4 tarihi rezerve et".
- **Result:** The request body `POST /bookings/recurring` carried the defaults again (`2026-11-05: book`, `2026-11-12: do_not_book`): D3 was booked, the staff booking on D4 was kept, the summary read "4 rezerve edilecek · 1 atlanacak · 1 tatil" before and after because the counts coincide, and the toast "4 tarih rezerve edildi, 1 tarih atlandı" matched the wrong plan. Without the recheck (phone run) the body carried `do_not_book` / `replace` and the staff booking was cancelled "replaced by series #1".
- **Expected:** "Yeniden denetle" re-runs the availability check and keeps every choice (F-02 S04). If a choice can no longer apply, the row says so.
- **Repro:** `/bookings?date=2026-10-22` → A 202 · P5 → Her hafta → end 26.11.2026 → Tarihleri göster → set two rows → Yeniden denetle → submit; compare the request body.
- **Evidence:** `logs/f02-desktop-a.json` (`S04.posts`), `logs/f02-phone-a.json`, `shots/F02-S04-choices-desktop.png`
- **Seen before as:** – (new)
- **File hints:** smartsched/frontend/src/components/bookings/book-sheet.tsx (`runPreview` → `dispatch({ type: "reset" })`), recurring-preview.ts reducer

### R2-M-02 (major) Publishing a re-solve preview succeeds on the server while the UI shows an English error and "Yayında değil"
- **Step:** F-05 S12 @1440
- **Action:** On `/moderation/recreate/12` pressed "Onayla ve yayınla", ticked the losses acknowledgement, pressed "Yayınla".
- **Result:** `POST /runs/12/activate` made #12 the active Güz run (#10 inactive, audit `run.activate`), but the page showed the toast "Invalid response for POST /runs/12/activate: Invalid input" and the state stayed "Yayında değil"; no "Yayınlandı: #12 artık geçerli plan" toast. The admin cannot tell that he just published.
- **Expected:** The publish toast of the spec, the state "Yayında", and no English zod message in the Turkish UI.
- **Repro:** Any re-solve preview with losses → publish from the preview; watch the response validation (the client's zod schema for `ActivateOut` rejects a field the server now sends, probably `notified` / `forced` lists).
- **Evidence:** `shots/F05-S12-published-desktop.png`, `logs/f05-c.json`
- **Seen before as:** – (new; related to T-R1-48's `ScheduleRun.error` zod work)
- **File hints:** smartsched/frontend/src/lib/api (activate response schema), components/moderation/recreate-preview.tsx `publish()`

### R2-M-03 (major) A minimal-change re-solve moves classes without a reason and loses planner-locked rows
- **Step:** F-05 S10/S11, F-07 S12 @1440
- **Action:** Raised PSY 277 §1's section priority and the person priority (2 staged changes, "4 talep değişmiş sayılır"), ran "En az değişiklik" → #11; pinned ACU 141 to its old place and re-ran → #12; added a one-section programme to Güz through the wizard → #13.
- **Result:** #11: "9 taşınan, 2 yeni yerleşen, 10 yerleşemeyen (2 yeni)", "Düzenlenen kapsam dışındaki 9 ders taşındı (6 tanesi nedensiz)", and two planner-locked rows of #10 (BP 127 §1 B 204, NUT 121 C 501) have no row in #11 ("kilit çakışması" reasons). #12: "26 yerleşemeyen (17 yeni)"; the confirm lists "17 ders dersliğini kaybediyor" with causes such as "Yayımdaki hücresi artık kesin bir kuralı bozuyor (sonradan eklenen rezervasyon / blok ya da taslak kuralı)". #13: "1 ders taşındı (1 tanesi nedensiz)". Hard score 100 → 100 in all three.
- **Expected:** Q9: 0 unexplained moves outside the edited scope; a soft change never costs placed, locked classes; every loss names a cause the coordinator can act on.
- **Repro:** F-05 S08 → S09 with the defaults; then S11.
- **Evidence:** `logs/F05-diff-11.json`, `shots/F05-S10-preview-desktop.png`, `logs/f05-b.json`, `shots/F05-S12-confirm-desktop.png`, `logs/f07.json`
- **Seen before as:** R1-S-04 (reopened: the magnitude dropped from 17 to 2 on the first step and the confirm now warns, but the pin + rerun reproduces the 17)
- **File hints:** smartsched/backend/app/services/moderation.py (repair radius / changed_request_ids), app/solver repair mode, the diff's `moved_unexplained`

### R2-M-04 (major) The run report counts its problems twice: "Sorun 457" next to "398 kabul edilmiş istisna"
- **Step:** F-09 S07 @1440 + 390
- **Action:** Opened `/runs/11` after the Studio run.
- **Result:** The verdict says "688/716 ders yerleşti · kesin kurallar korundu; 398 kabul edilmiş istisna listelendi" (same on the card, the grid header and `stats.truth`), but the KPI reads "Sorun 457" and the tab "Sorunlar 457"; the API's `diagnosis` has 400 items and `planner_check.exceptions_by_cause` sums to 393. Three numbers for one thing on one screen.
- **Expected:** One problem count (the truth's) everywhere, or a label that says what the 457 counts.
- **Repro:** Any Studio run → Raporu aç → compare the hero sentence with the KPI row.
- **Evidence:** `shots/F09-S07-report-desktop.png`, `logs/f09-c.json`, `logs/F09-run11.json`
- **Seen before as:** R1-M-04 (part), M-06/M-08
- **File hints:** smartsched/frontend/src/components/runs/run-view.tsx KPI "Sorun" and the tab count; run-truth.ts

### R2-M-05 (major) Resetting one person's learning memory leaves their open suggestions untouched
- **Step:** F-06 S10 @1440
- **Action:** `/moderation/people/98` → ⋯ → "Öğrenilenleri sıfırla…" → reason "görev değişikliği" → Sıfırla.
- **Result:** Toast "Sıfırlandı · Geri al", a row in "Son sıfırlamalar" with "Geri alma için 29 gün kaldı" and the undo works, but `GET /learning/suggestions?person_id=98&state=all` returns the same ids and states before and after (1781 accepted, 5579 open, 5762 open); the profile still shows the open cards. Only the "reset all" (S12) emptied the summary.
- **Expected:** L9: the person's open, snoozed and dismissed suggestions and learned habits are gone until the undo; accepted preferences stay.
- **Repro:** As above; read the suggestions API after the toast.
- **Evidence:** `logs/f06.json` (`S10.after`, `S10.undo`)
- **Seen before as:** – (new)
- **File hints:** smartsched/backend/app/services/learning (reset scope person → priors hidden but suggestions not recomputed / filtered)

### R2-M-06 (major) The intake dry run does not predict the commit, and re-uploads change hundreds of rows
- **Step:** F-08 S07/S08/S10/S11 @API (fresh stack)
- **Action:** Job A (xlsx + EN CSV + PDF): dry run, then Job B (EN CSV) was committed first by the harness, then Job A's dry run and commit, then a fresh CSV re-upload (Job D) and the cp1254 CSV (Job C) as dry runs.
- **Result:** Job A dry run after Job B: `meeting_requests create 1511, update 6, unchanged 10`; the real commit answered `duplicates_skipped 1332, meeting_requests_updated 6` — the dry run promised 1,511 new rows that the writer then recognised as duplicates. Job D (same CSV re-uploaded after everything was committed): `create 0, update 779, unchanged 569` instead of 0 changes. Job C (the Turkish-Excel CSV of the same list): `update 1332, unchanged 179` instead of ≥ 99 % unchanged. Inside one job the two formats dedupe correctly (1,512 planned creates).
- **Expected:** I4: dry-run counts equal the commit's; I5/D14: a re-upload of the same meetings changes 0 rows; the cp1254 export is ≥ 99 % unchanged.
- **Repro:** Fresh stack, F-08 S02–S08, then S10/S11 as written.
- **Evidence:** `logs/F08-dryrun-A.json`, `logs/f08.json`, `logs/F08-dryrun-B.json`, `logs/F08-dryrun-C.json`
- **Seen before as:** ROADMAP intake I4/I5 (new as a defect)
- **File hints:** smartsched/backend/app/services/council commit writer (dry-run path vs `duplicates_skipped`), natural keys of CSV-export rows vs planning-list rows

### R2-M-07 (minor) The wizard accepts the same new person twice on a section and then fails with a raw message
- **Step:** F-07 S05/S07/S08 @1440
- **Action:** On "Öğretim elemanları" typed "T. E." and pressed "Yeni kişi" twice (a double tap does the same), then "Ön kontrolü çalıştır" and "Yalnızca oluştur".
- **Result:** The step shows "T. E. · yeni" twice with no error (rail "1 uyarı" for the unassigned course only); the pre-check panel and the commit answer "Kayıt yazılamadı: instructor 491 is listed twice" (422, half English, no "Düzelt" link, no step marked). Nothing was committed, so the 30-day undo could not be tested.
- **Expected:** The second pick is refused or merged; if the server refuses, the message is Turkish and points to the step.
- **Repro:** `/programs/new` → draft → instructors → add the same new person twice → pre-check.
- **Evidence:** `logs/f07.json`, `curl/F07-S08-commit.txt`
- **Seen before as:** – (new)
- **File hints:** smartsched/frontend/src/components/program-wizard/steps.tsx (instructor pick), backend program_drafts validation

### R2-M-08 (minor) A planner can set a person-level priority (200)
- **Step:** F-05 S08 @API
- **Action:** `PUT /moderation/people/157/priority {term_id: 2, priority: "high"}` as planner.test.
- **Result:** 200. The flow's adopted default says person-level priority is coordinator/admin only (403 for a planner). Section priority 200 (correct), viewer 403 (correct).
- **Expected:** 403 for a planner, or the default documented the other way.
- **Evidence:** `logs/f05.json` (`S08.perms`)
- **File hints:** smartsched/backend/app/api/v1/moderation.py people priority permission

### R2-M-09 (minor) Enter on an approvals row focuses the note textarea, so the A/D/R keys type into it
- **Step:** F-13 C02 @1440
- **Action:** Focused a request row, pressed Enter, then `a`.
- **Result:** The drawer opens with focus in "Talep edene not" and the `a` is typed into the note; the legend's shortcuts only work after Tab-bing out. `d` on the focused row (without Enter) opens the reject dialog correctly.
- **Expected:** After Enter the focus lands on the drawer title or the first action, so A/D/R act at once.
- **Evidence:** `logs/f01-d.json` (`C02.enter`, `C02.a`)
- **File hints:** smartsched/frontend/src/components/approvals/approvals-view.tsx (drawer autofocus)

### R2-M-10 (minor) Stray calendar-sync toasts on pages that did not ask for calendar sync
- **Step:** F-02 S07–S11 (phone, `/my-bookings`), F-11 S09 (`/settings?tab=integrations`), F-12 S05 (`/profile`) @1440 + 390
- **Result:** After an edit or a cancel on `/my-bookings` the toast "Takvim eşitleme yönetici tarafından kapatıldı." appears next to the real toast; on `/profile` every password attempt shows "Takvim eşitleme kurumunuzda kapalı." as the first alert; saving a webhook shows "Takvim eşitleme kapatıldı.". The stack runs with calendar sync off, which is the normal state of a fresh install.
- **Expected:** A disabled integration is a quiet card state, never a toast on unrelated actions.
- **Evidence:** `logs/f02-phone-b.json`, `logs/f11.json` (`S09.webhookLoopback`), `logs/f12-b.json` (`S05.*`)
- **File hints:** smartsched/frontend/src/components/bookings/calendar-sync.tsx (error → toast on refetch), profile sync card

### R2-M-11 (minor) Audit undo: duplicate row, English "undo of #164", focus falls to body after undo and after priority save
- **Step:** F-02 S10, F-05 S08 @1440
- **Result:** A "Bu ve sonrakiler" cancel of two bookings wrote three "Rezervasyon iptal edildi" rows (#3 twice, #5 once); the undone row reads "Rezervasyon geri yüklendi #5 · #164 geri alındı · … · undo of #164"; after "Geri al" `document.activeElement` is `<body>`; the same after saving a person priority ("öncelik kaydedildi" toast, focus to body).
- **Expected:** One row per cancelled booking, Turkish tail, focus on the undone row / the edited row (motion T4).
- **Evidence:** `logs/f02-desktop-b.json` (`S10.*`), `logs/f05.json` (`S08.person`)
- **File hints:** backend audit writer for `cancel` scope future; audit-view.tsx undo focus; priority-editor.tsx

### R2-M-12 (minor) Capacity: no fit hint before submitting a pin, no UI override, plain "Taşı" enabled on a "Sığmaz" room and silent
- **Step:** F-09 S02/S04, F-10 S07 @1440
- **Result:** The pin template lists "B 201 · 30 koltuk" for the 100-student ING 302 without a "sığmaz" mark and says "1 derse uygulanıyor"; the refusal comes only after "Ekle" as a toast, and the admin's written-reason override exists only in the API (201 with `capacity_override`). The course picker lists each ING 302 meeting twice with no day/time. In the move dialog a "Sığmaz" room opens the reason panel correctly, but the plain "Taşı" stays enabled and does nothing when pressed. The forced pin never appears under the run's accepted exceptions (`forced_overrides: 0`; see R2-M-24).
- **Expected:** The template marks rooms that cannot seat the class and offers the admin override with a reason; "Taşı" is disabled (or explains) when only the forced path is possible.
- **Evidence:** `shots/F09-S04-pin-template-desktop.png`, `shots/F09-S04-pin-refused-desktop.png`, `shots/F10-S07-plain-desktop.png`, `logs/f10-c.json`
- **File hints:** smartsched/frontend/src/components/studio/slot-picker.tsx (rooms / courses fields), template-gallery.tsx Builder, timetable/move-dialog.tsx confirm state

### R2-M-13 (minor) Residual controls under 44 px on admin screens
- **Step:** MOBILE M-02 @390 (touch verified with `assertTouch`, `--control-h-md` 44 px)
- **Result:** Switch primitive 38×22 everywhere (profile notification matrix ×17, /settings AI switches, SSO, channels, integrations, Kurum ayarları, user sheet, room sheet, Studio policies); segmented controls 38 px (dashboard day/period, /my-bookings and /approvals tabs, rooms tabs, run report tabs, timetable "Liste / Zaman çizelgesi"); recurring preview per-date segments 85×30 and "Boşların hepsi / Hiçbiri" 32 px, "Takvimi aç" 32×32; cancel-scope options collapse into a select; roles editor 35 checkbox spans 16×16 and features grid 16×16 boxes / 80×28 inputs; /admin/schedules 28×16 boxes; moderation chips 28 px, priority segments 30 px, diff row actions 36 px; audit "Geri al" 36 px; toast close 20×20; heat-map source/scope 30 px; /rooms code links 20 px with title-only tooltips; /runs "İçe aktarılan pano #3" 20 px; "Oturum açmaya dön" 18 px on /reset-password; wizard "Düzelt" 37×16. M-09: the "Talepler 99+" badge is clipped in the tab bar. M-07: /admin/departments table scrolls without a pinned first column.
- **Expected:** MOBILE.md M-02/M-07/M-09.
- **Evidence:** `logs/crawl-phone-*.json`, `logs/pb-*.json`, `logs/f0*-phone*.json`, `shots/crawl_*-phone.png`
- **Seen before as:** R1-M-08 (the top bar, sub-navigation and sheet rows are fixed; this is the rest)
- **File hints:** components/ui/switch.tsx (coarse-pointer hit area), segmented-control.tsx sizes on touch, roles-admin.tsx / features-admin.tsx checkboxes, tab-bar badge

### R2-M-14 (minor) Solver tab: 14 px inputs, every default weight shows 0, raw "w" header
- **Step:** `/settings?tab=solver` @390 + 1440
- **Result:** Six number inputs at 14 px and 16 px checkboxes on the phone; "Varsayılan yumuşak ağırlıklar" lists every constraint with the slider at 0 and the column header "w". Either the defaults really are 0 (then the runs' soft scores of 77–99 come from elsewhere) or the screen does not load the saved values.
- **Expected:** 16 px inputs on phone; the real default weights; a Turkish column label.
- **Evidence:** `logs/crawl-phone-_settings_tab_solver.json`, `shots/crawl_settings_tab_solver-phone.png`
- **Seen before as:** R1-M-29 (part), sweeper-2 ask in HANDOFF
- **File hints:** components/settings/settings-view.tsx solver card

### R2-M-15 (minor) Phone timetable: inspector actions at the top of the sheet, no "Kilitle" on a split row, no filters trigger, title flips to "Pazartesi"
- **Step:** F-10 @390
- **Result:** The inspector opens as a 45 % bottom sheet with "Taşı…" (36 px) in the sheet body, not in a sticky footer (M-05 fails for the route's primary action); the week-3 row of PHAR 240 (a one-week piece after the split) offers "Taşı…" only, no "Kilitle"; there is no `open-filters` trigger and no filters sheet on the agenda view; while the agenda loads, `document.title` is "Pazartesi" before "Çizelge · SmartSched".
- **Expected:** F-10 mobile expectations ("Taşı…" and "Kilitle" ≥ 44 px in the sheet footer, a filters sheet).
- **Evidence:** `logs/f10-phone-inspector.json`, `shots/F10-phone-inspector.png`, `logs/f10-phone.json`
- **File hints:** components/timetable/mobile-calendar.tsx / floating-panel.tsx (inspector sheet footer), lock action for split rows

### R2-M-16 (minor) Searching Eşleşmeler under the default "Karşılanmayan" chip returns 0 rows silently
- **Step:** F-05 S07 @1440 + 390
- **Result:** The Eşleşmeler tab opens on "Karşılanmayan 30"; a search for "PSY 277" (all satisfied) shows an empty table with no hint that the chip hides 1,001 rows. "Tümü" shows the 2 rows.
- **Expected:** The empty state says "Karşılanmayan filtresinde yok; Tümü'nde 2 sonuç" or the search widens the chip.
- **Evidence:** `logs/f05.json` (`S07.rowsDefaultChip`)
- **File hints:** components/moderation/moderation-console.tsx matchings empty state

### R2-M-17 (minor) A queued run cannot be cancelled; the cancelled-by line shows the e-mail address
- **Step:** F-09 S06/S10 @1440
- **Result:** Right after `POST /runs` (QUEUED) the report has no cancel button and `POST /runs/12/cancel` answers 422; the cancel works once the run is RUNNING. The cancelled report reads "admin@smartsched.local tarafından" instead of the name.
- **Expected:** Cancel works from QUEUED; the by-line uses the display name like the rest of the UI.
- **Evidence:** `logs/f09-d.json`
- **File hints:** backend runs cancel guard; run-view.tsx cancelled-by

### R2-M-18 (minor) English or mixed-language server strings reach the Turkish UI
- **Step:** several @1440
- **Result:** Forced-break banner and report: "derslik çakışması: A102 week 3 day 1 P1: PHAR 240 §1, PHAR 474 §1"; `POST /bookings` for a past date: 409 `range_min` "bookings must be made at least 0 day(s) ahead (from 17.10.2026)"; feature create: "a feature named 'Projeksiyon' exists"; room photo: "Görsel işlenemedi: the file is not a readable jpg, png or gif image"; the cancel reason the staff member sees for a replaced booking: "replaced by series #1"; the audit tail "undo of #164"; move preview conflicts in the API "A 102 is taken by PHAR 474 §1 (Pazartesi P1-P4)"; Kurum ayarları shows the English feature sentence "Roles with permission sets and booking limits (active bookings, booking window, recurring instances), per-user overrides, and the Teacher self-service role."; the publish error of R2-M-02.
- **Expected:** Turkish messages (M-36); English only in an expandable detail.
- **Evidence:** `shots/F10-S06-forced-desktop.png`, `curl/F02-S12-past.txt`, `logs/f11.json`, `logs/f11-b.json`, `logs/f02-phone-a.json`, `logs/crawl-phone-_admin_settings.json`
- **Seen before as:** R1-M-17 (part)
- **File hints:** app/services/move_guard.py / run_truth.py broken messages (tr), bookings range_min error, features importer, room photo validator, series replace reason, audit undo label, org-settings feature description

### R2-M-19 (minor) A rule whose scope no approver covers shows no warning
- **Step:** F-11 S08 @1440
- **Result:** With the admin's approver scope reduced to one room, the C Blok and PC rules still read "Atanmış onaycılar · — · Etkin" and the page carries no "Bu derslik için atanmış onaycı yok" text (`approvers-empty` absent).
- **Expected:** M-35: the rule is flagged; a request still falls back to the all-room approvers, the owner, then administrators.
- **Evidence:** `shots/F11-S08-rules-noapprover-desktop.png`, `logs/f11-b.json`
- **File hints:** components/approvals/rules-admin.tsx (approver coverage per rule)

### R2-M-20 (minor) Small defects: needless `user.instructor_link` audit row, two `<main>` landmarks in the wizard, role error only as a toast
- **Step:** F-05 S00, F-07 S02–S08, F-11 S01 @1440 + 390
- **Result:** Picking the already-linked instructor again writes a `user.instructor_link` audit row (the flow expects none); `/programs/new/<draft>` renders two `<main>` elements (the shell's and the wizard's); the user form reports a missing role only as the toast "Bir rol seçin." while the e-mail message sits next to its field.
- **Evidence:** `logs/f05.json` (`S00.audit`), `logs/f07.json` (`mainCount`), `logs/f11.json` (`S01.created`)
- **File hints:** users-admin-identity.tsx apply(), program-wizard.tsx `<main>` → `<section>`, users-admin.tsx role validation

### R2-M-21 (minor) "Önerilenleri uygula" gives no visible result; the compare refusal names the wrong reason
- **Step:** R1-M-01 / R1-M-10 re-checks @1440
- **Result:** On `/bookings/conflicts/12` (3 conflicts with options "C 403 aynı saatte boş (45 kişilik) · En uygun") pressing "Önerilenleri uygula" changed nothing on the page, showed no dialog and no toast, and the plan still had 3 open conflicts; the API dry run and apply work (200, moved 1, notified 1). `/runs/compare` keeps "Karşılaştır" disabled for #8 vs #11 and the API says "#8 ve #11 aynı dönemin aynı türden çalıştırmaları değil" although both are Bahar course runs (they differ in horizon).
- **Expected:** The button opens the review step with the dry-run counts; the compare message names the horizon.
- **Evidence:** `shots/R1M01-after-apply-desktop.png`, `curl/R1M01-apply-dry.txt`, `curl/R1M10-compare.json`
- **File hints:** components/conflicts/* apply button handler; app/api/v1/analytics.py compare message

### R2-M-22 (suggestion) Cancel scopes without date counts; "bir süre sonra" on the reset page; 422 instead of 401 for a bad ticket
- **Step:** F-02 S08, F-12 S07/S15
- **Result:** "Bu tarih · Bu ve sonrakiler · Tüm seri" never say how many dates each cancels (persona-user Enh. #7); the reset page says "Kodların süresi bir süre sonra dolar." while the mail says "24 saat geçerli"; `POST /auth/sso/exchange {"ticket":"random"}` answers 422 "String should have at least 16 characters" instead of the generic 401.
- **Evidence:** `shots/F02-S08-cancel-desktop.png`, `logs/f12.json` (`S07.requested`), `logs/f12-b.json` (`S15`)

### R2-M-23 (minor) Rule cards on the phone: 160 segmented controls at 38 px and 16 px class checkboxes
- **Step:** F-09 @390 (Studio step 3 and step 2)
- **Result:** Each of the 32 rule cards renders "Kesin / Mümkünse" (88×38) and "Düşük / Normal / Yüksek" (66×38); the Dersler step has 16×16 row checkboxes next to 38×22 "in-plan" switches. The page never overflows (M-01) and the bottom bar is sticky.
- **Expected:** 44 px rows on touch (MOBILE.md M-02).
- **Evidence:** `logs/f09-phone2-s3.json`, `logs/f09-phone2-s2.json`, `shots/F09-phone-rules.png`
- **File hints:** components/studio/rule-card.tsx hardness / importance controls, classes-step.tsx row checkbox

### R2-M-24 (suggestion) The forced capacity override is not listed under the run's accepted exceptions
- **Step:** F-09 S07 @1440
- **Result:** With the admin-overridden pin #74 in place, run #11's truth has `forced_overrides: 0` and the exceptions list four data causes only; the class sits under "Dersliksiz kalan" with the right sentence. The reader of the verdict cannot see that an administrator knowingly kept an impossible rule.
- **Expected:** One exception line "1 kesin kural yönetici gerekçesiyle kapasiteyi aşıyor (ING 302 → B 201)".
- **Evidence:** `logs/F09-run11.json`

### R2-M-25 (minor) Intake: the job page is not addressable, the drop zone is not a button, no `accept` list
- **Step:** F-08 S01/S03 @390 + 1440
- **Result:** The running job lives at `/onboarding?job=1`; `/onboarding/1` (the route the plan and the phone battery use) is a 404. The drop zone is a `div` with a nested button (Enter/Space on the zone do nothing); the file input is labelled but carries no `accept` list. The commit bar stayed "3 engelle" with a disabled button after the API had cleared the blockers, until a reload.
- **Expected:** A stable job URL; a button drop zone; `accept` with the formats the lead names; the bar follows the review state.
- **Evidence:** `logs/f08.json` (`S01`, `S03.url`, `S08.bar`), `shots/F08-phone-onboarding.png`
- **File hints:** components/onboarding/file-drop.tsx, onboarding-flow.tsx routing

### R2-M-26 (minor) Focus falls to body after "Yayınla" and after saving a person priority
- **Step:** F-09 S08/S09, F-05 S08 @1440
- **Result:** After the publish toast "Çalıştırma #11 artık yayımlanan program" `document.activeElement` is `<body>`; the same after "Dr. Öğr. Üyesi S. E.: öncelik kaydedildi (4 talep)".
- **Expected:** Focus on the "Yayında" badge or the publish button; on the edited row (README §4.7).
- **Evidence:** `logs/f09-d.json` (`S08.after`), `logs/f05.json` (`S08.person`)

### R2-M-27 (suggestion) "Hoş geldiniz, A." greets with the first initial only
- **Step:** F-12 S03 @1440
- **Result:** With masked names ("A. T.") the toast takes the first token: "Hoş geldiniz, A.", "Hoş geldiniz, L.". Real names would show the first name, so this is a masking artefact that still reads oddly for anyone whose display name is initials.
- **Evidence:** `logs/f12.json` (`S03.acad`, `S03.limited`)
