# Flow loop round 2 · staff (department staff member who books rooms) · 2026-10-17

Ledger: `flow-r2-staff-2026-10-17` · persona tester: the staff persona of README §2 (`personel.test@smartsched.local`, "P. T.", TEACHER), with the admin for the approver steps, the academician for the second requester and the planner helper for the planning-rights re-checks · plan: [README](../README.md), [MOBILE](../MOBILE.md), flows F-01, F-02, F-03, F-04, F-12, F-13 (the staff column of README §1) plus the re-verification of every `R1-S-nn` id of [round 1](round-1-staff.md) (F-05 S06–S10, F-08, F-09, F-10, /runs/compare, /exams/invigilation, learning, relaxation policy).
Snapshot: `deb38315` (`deb38315eac87ed0e924cdf87e886b3e46545094`, `claude/focused-wright-ktt0ss`), frozen worktree `scratchpad/r2staff/flow-src-deb3831` (removed at the end) · stack API :19210, web :19211 (`REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`), SMTP sink :2526, fresh stack for F-08 on :19212/:19213 (own workdir, stopped at the end) · load average 0.3–7.2 on 4 cores during the round (3–7 while the two other testers ran, 1.5–2.3 during the last reruns), so timing rows are advisory (README §8).
Dates (README §4.3): TODAY 2026-10-17 (a Saturday: no teaching periods today) · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D5 2026-11-19 · D6 2026-11-26 · holiday Thu 29 Oct inside the F-02 series · Chromium 141 (chromium-1194), Playwright 1.56.1 library · viewports desktop 1440×900 (mouse) and phone 390×844 (isMobile, hasTouch, `scripts/record/lib/touch.mjs`: `assertTouch` before every M-02/M-03/M-05 reading, `controlHmd` read 44px on every phone measurement) · F-13 Part C also on a 768×1024 tablet with a keyboard.
Rooms: R1 = C 303 (45), R2 = A 104 (41; the first A-block room with P3 free on D1 after the published Güz run), R3 = C 201 (C z01 is held by the timetable at P5 on D3), RS = A 202 (P5 free on every Thursday D1–D6). F-03 window: D1 P11–P12 (at P7–P8 no computer lab with ≥ 42 seats is free on this snapshot; the oracle `POST /rooms/find` chose the window), feature "Bilgisayar laboratuvarı" (id 1, from `features/template` + `adopt-tags`).
Data: the real Bahar 2026, Güz 2026-27 and Final 2026 workbooks plus the room master (`stack.sh up`, names masked to initials: `kvkk_mask.py --verify` → `left 0`). Runs from `stack.sh runs`: #7 Bahar week 3 688/716 hard 100 · #8 Bahar term 682/717 hard 100, published (B0) · #9 Güz week 3 524/530 · #10 Güz term 517/530, published (G0); during the round: #11 cancelled, #12 Final exam run 603/608 (invigilation), #13 moderation re-solve preview of G0, exam-invigilation plans #1 (board) and #2 (exam run).
Accounts: the §4.4 seed (`personel.test`, `akademisyen.test` linked to instructor 157, `planner.test`), `devre.disi@…` (disabled, F-12 S02), `davet.test@…` (SSO invite), `viewer.test` (fresh stack). No Anthropic key, AI policy off (`intake_enabled:false`).
Preconditions per flow: approval_mode set in the UI (F-01 S01) and by `PUT /org/settings` otherwise; admin approver for all rooms (seed); features catalogue (F-03); calendar sync off until F-04 S02 signs it off in the UI; F-12 S05–S07 restore `Flow-2026!pw` through the API after each change; every flow starts from `REC_SNAPSHOT=1 REC_SKIP_BUILD=1 stack.sh up`.
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2staff/ev` (`shots/`, `curl/` with tokens and codes redacted, `mail/`, `logs/*.json` one per flow × viewport, `issues.json`, `r1.json`); scripts in `…/scratchpad/r2staff/scripts/` (`lib.mjs` holds the MOBILE.md probes, `f01…f04.mjs`, `f12a/b/c.mjs`, `f13.mjs`, `f08.mjs`, `rv-api.mjs`, `rv-ui.mjs`, `run-rest2.sh`). Intake logs that held real names were deleted or masked (`<ad>`), README §7.

## BLUF

**22 new findings: 0 blocker · 6 major · 14 minor · 1 suggestion · 1 trivial.** Round-1 ids on `deb38315`: **27 verified · 6 reopened · 3 inconclusive · 3 open suggestions** (table below). 331 step × viewport rows: 206 PASS, 44 PASS* (the step held up on the device, a strict text/locator assert in my script drifted — the note says what was seen), 51 FAIL (every one tied to an `R2-S` id), 9 INCONCLUSIVE, 11 NOT RUN (harness), 8 BLOCKED (feature not built: 'Derslerim' shortcut and feed, SSO admin UI, Entra tenant), 2 SKIP (no OAuth client).

The staff member can do her week on the phone and at the desk: one-off and weekly bookings with the per-date table and the holiday skipped, requests with the '1 adımlı onay' notice and the exact toasts, the approver's reject with a reason that reaches the bell, the row and the mail, withdraw, notification preferences, free-room search with features and text, the private calendar feed (create with the KVKK consent, copy, Google/Outlook/Apple links, 4 VEVENTs with `Europe/Istanbul`, TENTATIVE → CONFIRMED on approval, reset revokes the old link, cancel drops the event), local login/lockout/rate-limit/next, the SSO guards, callbacks and invites, English UI end to end, keyboard paths on the grid and the series table, opaque sheets, 60 fps on the four hot paths. The round-1 blockers (move guard, nursing rule, docx intake) stay fixed.

Majors, all on the phone or the keyboard, none in the booking logic:
1. **R2-S-02** the forced password change saves (200, 'Parola değiştirildi') but never leaves `/login/change-password` — fields cleared, button disabled, the person has to find her own way out (both viewports);
2. **R2-S-03 / R2-S-04 / R2-S-05 / R2-S-06** the four phone screens a staff member touches most still have sub-44 px controls or a primary that scrolls away: the recurring sheet (30–38 px date-table controls), /my-bookings (117×38 tabs, 16 px checkboxes, bulk bar not sticky), /approvals (approve at y 318, no sticky footer) and /find-room (24 px chips, 30 px time segments, headcount under the keyboard, 'Ara' not sticky);
3. **R2-S-16** the withdraw confirm does not trap focus: Tab leaves the dialog into the page (desktop and tablet keyboard).

Reopened round-1 ids: R1-S-04 (re-solve after one wish still loses 17 placed classes, 1 unexplained), R1-S-16 (inspector 'Taşı…' 84×36 on the phone), R1-S-19 (no suggestion for instructor 157's wish), R1-S-22 (rail reads 'Tüm dönem · 2 hafta' while the sheet says 14), R1-S-24 (API refusal 'moving despite a conflict is admin-only' in English), R1-S-31 (intake job lost on reload). Blockers for the round: none; F-04 S12 (OAuth connectors) and F-12 S18 (real Entra tenant) cannot run on this host.

## Summary

| Severity | Count | Ids |
|---|---|---|
| blocker | 0 | – |
| major | 6 | R2-S-02, R2-S-03, R2-S-04, R2-S-05, R2-S-06, R2-S-16 |
| minor | 14 | R2-S-01, R2-S-07, R2-S-08, R2-S-09, R2-S-10, R2-S-11, R2-S-12, R2-S-13, R2-S-14, R2-S-15, R2-S-17, R2-S-19, R2-S-21, R2-S-22 |
| suggestion | 1 | R2-S-18 |
| trivial | 1 | R2-S-20 |

| Flow / area | Result | Findings |
|---|---|---|
| F-01 approval flow (staff requests, admin decides) | green at 1440 and 390: request sheet notice and toast, busy label 'Gönderiliyor…', approver bell/mail, reject dialog with reason codes and the automatic room suggestions, withdraw, preferences, planner/admin skip-approval, per-room approvers | R2-S-05 (approve button on the phone), R2-S-08 (switch sizes), R2-S-14 (dashboard digits) |
| F-02 recurring bookings | mechanics green: series with the date table (4 booked · 1 skipped · 1 holiday), edit scope 'Bu ve sonrakiler' → 4 updated, cancel one / this-and-later / all, audit undo with conflict re-check, past-date refusal; replacement path and the custom date range not exercised | R2-S-03 (sheet controls at 390), R2-S-09 (focus after undo), R2-S-13 (English API refusal), R2-S-18 (scope counts), R2-S-22 (cancel toast wording) |
| F-03 find a room | green: date/weekday/range modes, features, text, ranking, recent searches, book and request from the results, approval rooms; stale-result reserve books the remaining period silently | R2-S-01 (stale result), R2-S-06 (phone filters), R2-S-10 (span rows) |
| F-04 calendar feed | green: consent → create, copy both links, Google/Outlook/Apple, feed 200 `text/calendar` with VTIMEZONE, TENTATIVE → CONFIRMED, reset (old 404, new 200, toast, focus on the new link, other device sees 'sıfırlayın'), bulk cancel removes the event, admin off → 404 → on → 200 | R2-S-21 (URL overflow, 32 px copy buttons), R2-S-10, R2-S-11 (stray toast), R2-S-22 |
| F-12 sign-in and accounts | green: local login, wrong password, disabled user, lockout, rate limit, `next`, landing by permission, logout, SSO guards/start/callback refusals/exchange/invites/break-glass, LDAP form | R2-S-02 (forced change stays), R2-S-11, R2-S-12 (reset page copy), R2-S-19 (title-only locale toggle), R2-S-20 (plan drift) |
| F-13 i18n, motion, keyboard, frames | green: Turkish titles/labels on every route, English end to end, opaque sheets, 60 fps (worst LoAF 0 ms, dropped ≤ 7 frames in a sheet open), span selection by keyboard with live text, Esc returns focus, series table by keyboard | R2-S-15 (reduced motion ignored by the sheet), R2-S-16 (withdraw trap), R2-S-17 (j/k, `a` on /approvals) |
| MOBILE.md M-01…M-14 on every route | M-01/03/04/06/07/08/11/13/14 pass everywhere; M-02 (44 px), M-05 (primary reachable), M-09 (tab-bar labels), M-12 (keyboard clearance) fail on the routes named in the issues | R2-S-03…R2-S-08, R2-S-19 |
| Round-1 re-verification (F-05 S06–S10, F-08 fresh stack, F-09, F-10, /runs/compare, /exams/invigilation, learning, relaxation) | 27 verified · 6 reopened · 3 inconclusive · 3 open suggestions | see the table below |

### Scenario results (Fatih Bey, re-run as the planning staff where the round-1 id needed it)

| Scenario | Result |
|---|---|
| Import the Bahar list and the weekly grid | verified on the fresh stack: progress lines in Turkish, 'Yaz' confirm with the counts, docx with AI off no longer blocks (R1-S-03, S-10, S-11 verified); job B re-upload plans 0 creates (R1-S-12); the job list is still lost on reload (R1-S-31 reopened) |
| Find a course | PHAR 240 via the command palette and the timetable search; the search box still does not move focus to the class (R1-S-26 inconclusive, not reproduced by script) |
| Generate week 3 | week run #7 688/716 hard 100; verdict wording and the scope-reduction refusal verified (R1-S-06, S-07); 'Tüm dönem · 2 hafta' rail text reopened (R1-S-22) |
| Move PHAR 240 to A 206 from 23 Feb | move guard holds (dry run refuses the TIP room, R1-S-01 verified); exact week split kept; the inspector's 'Taşı…' is 84×36 on the phone (R1-S-16 reopened) |
| Nursing first-years before 17:30 (Turkish) | rule template accepted, pre-check 200 with named classes, no 500 (R1-S-02 verified); the relaxation policy text and the Studio card verified (R1-S-08, S-38 open) |
| Export the week to Excel | file name `smartsched-run7-hafta3.xlsx`, counts match (R1-S-23, S-27 verified) |
| Infeasible request (102 in a 30-seat room on a full day) | 422 'capacity' in Turkish for admin and planner, pin refused at the edit (R1-S-05 verified); forced clash on the live plan still goes live (R1-S-37 open, owner decision) |

### What passed (short)

- F-01: 'Talep et' with 'Bu derslik onay gerektirir · 1 adımlı onay', 202, toast 'A 104 için talebiniz gönderildi. Onaycı karar verince size bildirilecek.', bell '1 okunmamış', approver mail with the deep link, reject dialog reason codes + free text + automatic suggestions ('Önerilen derslikler (otomatik): A 106, A 107, A 305'), 'Reddedildi. Talep edene bildirildi.', requester card 'Oda talebiniz reddedildi: …' with 'Gerekçe: …', withdraw (API + UI), e-mail channel off → in-app only.
- F-02: 'Her hafta' legend with 'Bu tarihten (22.10.2026)' / 'Dönem sonuna kadar (27.12.2026)', per-date table with '5. hafta · Boş · Rezerve et / Atla', holiday 'Tatil · Cumhuriyet Bayramı · Atlanır', a taken date offers 'Yerine geç', '4 tarihi rezerve et', toast '4 tarih rezerve edildi, 1 tarih atlandı', the admin's audit undo dialog 'Rezervasyon #4 geri alınsın mı? … Çakışmalar yeniden denetlenir.' → 200.
- F-03: weekday/range modes, '21 boş oda · 1/1 tarih açık' live summary, 'Metinle eşleşen derslik yok: …' with 'Metni temizle', recent-search chips, 'A 105 rezerve et' → '2 ders saatini rezerve et', approval rooms 'Onay gerekir' → '2 ders saati için talep et'.
- F-04: consent dialog 'Rıza ver ve devam et' → feed 201, 'Bağlantı kopyalandı' (web and webcal), `GET …/mine.ics` 200 with 4 VEVENT and `Europe/Istanbul`, request TENTATIVE → CONFIRMED after the decision, reset dialog 'Özel bağlantı sıfırlansın mı? Eski bağlantılarla abone olunan takvimler artık güncellenmez…' → 201, old 404 / new 200, toast 'Yeni bağlantılar oluşturuldu; eski abonelikler artık güncellenmez.', focus on the new link, another device reads '1 özel bağlantınız var: 17.10.2026 tarihinde oluşturuldu … sıfırlayın'; admin switch off → 'Takvim eşitleme yönetici tarafından kapatıldı.' and 404; on → 200 again.
- F-12: field messages, disabled account refused, 5 wrong passwords → lockout text, rate limit 429 with Retry-After, `next` honoured and foreign hosts dropped, landing by permission, logout clears the cookie, SSO enable guards (422/403), start 302, forged/cancelled/reused callbacks → '/login?error=failed&ref=S-nnn' with the alert focused, exchange with a random ticket 422, invites 30 days / bind / delete / 'Bu davet artık geçerli değil.', OIDC-only hides the local fields and `?method=local` shows them for the admin only, last-admin lockout 409.
- F-13: Turkish `<title>`, `lang`, h1 and 404 page; English profile → 'Saved', every route and sheet in English, English reject mail 'Your room request was declined: … Reason: Not enough seats: …'; sheets, bell and sync panel opaque (alpha 1, no backdrop blur); load 0.47 s, worst LoAF 0 ms, dropped frames ≤ 7 in a sheet open; span selection '2 ders saati seçildi, 08:30–10:00, C 201.', Esc → focus on the cell; series table by keyboard with the polite summary; no bad focus rings.

## Step table

Result legend: PASS · PASS* (device behaviour right, my assert drifted — note says what was seen) · FAIL (tied to an `R2-S` id) · INCONCLUSIVE · NOT RUN (harness could not reach the control; the other viewport or an earlier step covers it where the note says so) · BLOCKED (feature not built) · SKIP. Evidence paths are relative to the evidence root.

| Flow | Step | Viewport | Result | Evidence | Issue / note |
|---|---|---|---|---|---|
| F-01 | F-01 S01 | desktop | PASS | `shots/F01-S01-desktop.png` | – |
| F-01 | F-01 S01 | phone | PASS | `shots/F01-S01-phone.png` | – |
| F-01 | F-01 S02 | desktop | PASS | `shots/F01-S02-desktop.png`, `curl/F01-S02-check.txt` | – |
| F-01 | F-01 S02 | phone | PASS | `shots/F01-S02-phone.png`, `curl/F01-S02-check.txt` | – |
| F-01 | F-01 S03 | desktop | PASS* | `shots/F01-S03-desktop.png`, `curl/F01-S03-mine.txt` | request sent (202), toast 'C 303 için talebiniz gönderildi…', busy label 'Gönderiliyor…' with aria-busy seen on the phone; on the desktop the POST answered before the 15 ms poll so the label could not be sampled |
| F-01 | F-01 S03 | phone | PASS* | `shots/F01-S03-phone.png`, `curl/F01-S03-mine.txt` | request sent (202), toast 'C 303 için talebiniz gönderildi…', busy label 'Gönderiliyor…' with aria-busy seen on the phone; on the desktop the POST answered before the 15 ms poll so the label could not be sampled |
| F-01 | F-01 S04 | desktop | PASS | `shots/F01-S04-desktop.png`, `curl/F01-S04-duplicate.txt` | – |
| F-01 | F-01 S04 | phone | PASS | `shots/F01-S04-phone.png`, `curl/F01-S04-duplicate.txt` | – |
| F-01 | F-01 S05 | desktop | PASS | `shots/F01-S05-desktop.png` | – |
| F-01 | F-01 S05 | phone | PASS | `shots/F01-S05-phone.png` | – |
| F-01 | F-01 S06 | desktop | PASS | `shots/F01-S06-desktop.png` | – |
| F-01 | F-01 S06 | phone | PASS | `shots/F01-S06-phone.png` | – |
| F-01 | F-01 S07 | desktop | PASS | `shots/F01-S07-desktop.png` | – |
| F-01 | F-01 S07 | phone | PASS | `shots/F01-S07-phone.png` | – |
| F-01 | F-01 S08 | desktop | PASS | `shots/F01-S08-desktop.png`, `curl/F01-S08-decide-negatives.txt` | – |
| F-01 | F-01 S08 | phone | PASS | `shots/F01-S08-phone.png`, `curl/F01-S08-decide-negatives.txt` | – |
| F-01 | F-01 S09 | desktop | PASS* | `shots/F01-S09-desktop.png` | rejection card in the bell with the reason, deep link /my-bookings?request=<id>, 'Reddedildi' row with 'Gerekçe: …', mail to the requester; the harness compared the card title with the other request |
| F-01 | F-01 S09 | phone | PASS* | `shots/F01-S09-phone.png` | rejection card in the bell with the reason, deep link /my-bookings?request=<id>, 'Reddedildi' row with 'Gerekçe: …', mail to the requester; the harness compared the card title with the other request |
| F-01 | F-01 S10 | desktop | PASS | `shots/F01-S10-desktop.png`, `curl/F01-S10-withdraw-twice.txt` | – |
| F-01 | F-01 S10 | phone | PASS | `shots/F01-S10-phone.png`, `curl/F01-S10-withdraw-twice.txt` | – |
| F-01 | F-01 S10 admin | desktop | PASS | `shots/F01-S10-admin-desktop.png` | – |
| F-01 | F-01 S10 admin | phone | PASS | `shots/F01-S10-admin-phone.png` | – |
| F-01 | F-01 S11 | desktop | PASS | `shots/F01-S11-desktop.png`, `curl/F01-S11-prefs.txt` | – |
| F-01 | F-01 S11 | phone | PASS* | `shots/F01-S11-phone.png`, `curl/F01-S11-prefs.txt` | e-mail channel switched off → toast 'Bildirim tercihi kaydedildi.', the next approval arrives in-app only and no mail is sent (expected); the 38×22 switches are R2-S-08 |
| F-01 | F-01 S12 | desktop | INCONCLUSIVE | `shots/F01-S12-desktop.png`, `curl/F01-S12-planner.txt` | admin booking without approval: sheet 'Bu saati rezerve et' (no approval notice), 201, toast — PASS; the planner's API booking returned 409 both before and after granting bookings.skip_approval (the slot the script chose was no longer free), so the planner half was not re-verified |
| F-01 | F-01 S12 | phone | PASS | `shots/F01-S12-phone.png`, `curl/F01-S12-planner.txt` | – |
| F-01 | F-01 S14 | desktop | PASS | `shots/F01-S14-desktop.png` | – |
| F-01 | F-01 S14 | phone | PASS | `shots/F01-S14-phone.png` | – |
| F-01 | F-01 S15 | desktop | INCONCLUSIVE | `shots/F01-S15-desktop.png` | staff books the open room (201, toast) and requests the approval room (202, '1 adımlı onay' notice, toast) — PASS; the reject-without-reason API guard was called with a wrong request id (404), the UI reject dialog requiring a reason was verified in S07/S08 |
| F-01 | F-01 S15 | phone | PASS | `shots/F01-S15-phone.png` | – |
| F-01 | F-01 TR scan /approvals | desktop | PASS | – | – |
| F-01 | F-01 TR scan /approvals | phone | PASS | – | – |
| F-01 | F-01 TR scan /bookings | desktop | PASS | – | – |
| F-01 | F-01 TR scan /bookings | phone | PASS | – | – |
| F-01 | F-01 TR scan /my-bookings | desktop | PASS | – | – |
| F-01 | F-01 TR scan /my-bookings | phone | PASS | – | – |
| F-02 | F-02 S01 | desktop | PASS | `shots/F02-S01-desktop.png`, `curl/F02-S01-booking.txt` | – |
| F-02 | F-02 S01 | phone | PASS | `shots/F02-S01-phone.png`, `curl/F02-S01-booking.txt` | – |
| F-02 | F-02 S01 notify | desktop | PASS | – | – |
| F-02 | F-02 S01 notify | phone | PASS | – | – |
| F-02 | F-02 S02 | desktop | PASS | – | – |
| F-02 | F-02 S02 | phone | PASS | – | – |
| F-02 | F-02 S03 | desktop | PASS | `shots/F02-S03-desktop.png`, `curl/F02-S03-preview.json` | – |
| F-02 | F-02 S03 | phone | PASS | `shots/F02-S03-phone.png`, `curl/F02-S03-preview.json` | – |
| F-02 | F-02 S04 | desktop | PASS* | `shots/F02-S04-desktop.png`, `curl/F02-S04-recurring.json` | per-date table (5 dates, holiday 29 Oct marked), 'Atla' on one date → '4 rezerve edilecek · 1 atlanacak · 1 tatil', all skipped disables the button ('0 tarihi rezerve et'), 201, toast '4 tarih rezerve edildi, 1 tarih atlandı', focus back on the cell; the per-date controls are selects labelled 'dd.mm.yyyy için işlem' instead of the planned radios (R2-S-20) |
| F-02 | F-02 S04 | phone | PASS* | `shots/F02-S04-phone.png`, `curl/F02-S04-recurring.json` | per-date table (5 dates, holiday 29 Oct marked), 'Atla' on one date → '4 rezerve edilecek · 1 atlanacak · 1 tatil', all skipped disables the button ('0 tarihi rezerve et'), 201, toast '4 tarih rezerve edildi, 1 tarih atlandı', focus back on the cell; the per-date controls are selects labelled 'dd.mm.yyyy için işlem' instead of the planned radios (R2-S-20) |
| F-02 | F-02 S05 | desktop | NOT RUN | `shots/F02-S05-desktop.png` | the replacement path (admin cancels the on-behalf booking with a reason and books a replacement) was not exercised by the harness; the staff page at that point read '0 etkin · bu dönem 1 · toplam 1' for one admin-made booking (counting bases → R2-S-10) |
| F-02 | F-02 S05 | phone | NOT RUN | `shots/F02-S05-phone.png` | the replacement path (admin cancels the on-behalf booking with a reason and books a replacement) was not exercised by the harness; the staff page at that point read '0 etkin · bu dönem 1 · toplam 1' for one admin-made booking (counting bases → R2-S-10) |
| F-02 | F-02 S06 | desktop | NOT RUN | – | harness: the custom date-range picker ('Tarih seçin…') of the series form was not reached; the default range (this date → term end) was exercised in S03/S04 |
| F-02 | F-02 S06 | phone | NOT RUN | – | harness: the custom date-range picker ('Tarih seçin…') of the series form was not reached; the default range (this date → term end) was exercised in S03/S04 |
| F-02 | F-02 S07 | desktop | PASS* | `shots/F02-S07-desktop.png` | edit sheet of a series date: scope select 'Bu tarih / Bu ve sonrakiler / Tüm seri', period and room selects, note; 'Bu ve sonrakiler' + new period → 4 updated (checked through the grid); planned radios are selects (R2-S-20) |
| F-02 | F-02 S07 | phone | PASS* | `shots/F02-S07-phone.png` | edit sheet of a series date: scope select 'Bu tarih / Bu ve sonrakiler / Tüm seri', period and room selects, note; 'Bu ve sonrakiler' + new period → 4 updated (checked through the grid); planned radios are selects (R2-S-20) |
| F-02 | F-02 S08 | desktop | PASS* | `shots/F02-S08-desktop.png` | cancel one date of the series with a reason: dialog 'Rezervasyon iptal edilsin mi?' with scope 'Bu tarih', 200 cancelled [1], toast 'Bu rezervasyon iptal edildi · Gerekçe: Oda bakımda', the date frees and the next one stays booked, focus back on the cell |
| F-02 | F-02 S08 | phone | PASS* | `shots/F02-S08-phone.png` | R2-S-22; cancel one date of the series with a reason: dialog 'Rezervasyon iptal edilsin mi?' with scope 'Bu tarih', 200 cancelled [1], toast 'Bu rezervasyon iptal edildi · Gerekçe: Oda bakımda', the date frees and the next one stays booked, focus back on the cell |
| F-02 | F-02 S09 | desktop | PASS* | `shots/F02-S09-desktop.png` | single booking cancel: dialog without scope, 200, toast '1 rezervasyon iptal edildi', only that date CANCELLED |
| F-02 | F-02 S09 | phone | NOT RUN | – | harness: the 12 Nov single booking row could not be opened from the phone list; the step passed on the desktop |
| F-02 | F-02 S10 | desktop | FAIL | `shots/F02-S10-desktop.png` | R2-S-09 |
| F-02 | F-02 S10 | phone | FAIL | `shots/F02-S10-phone.png` | R2-S-09 |
| F-02 | F-02 S11 | desktop | PASS* | `shots/F02-S11-desktop.png` | 'Bu ve sonrakiler' from 22 Oct: 200 cancelled [3], toast '3 rezervasyon iptal edildi', 12 Nov (edited out of the series earlier) stays booked |
| F-02 | F-02 S11 | phone | PASS* | `shots/F02-S11-phone.png` | R2-S-22; 'Bu ve sonrakiler' from 22 Oct: 200 cancelled [3], toast '3 rezervasyon iptal edildi', 12 Nov (edited out of the series earlier) stays booked |
| F-02 | F-02 S12 | desktop | FAIL | `shots/F02-S12-desktop.png`, `curl/F02-S12-past.txt` | R2-S-13 |
| F-02 | F-02 S12 | phone | FAIL | `shots/F02-S12-phone.png`, `curl/F02-S12-past.txt` | R2-S-13 |
| F-03 | F-03 S01 | desktop | PASS | `shots/F03-S01-desktop.png` | – |
| F-03 | F-03 S01 | phone | PASS | `shots/F03-S01-phone.png` | – |
| F-03 | F-03 S02 | desktop | PASS | `shots/F03-S02-desktop.png`, `curl/F03-oracle.json` | – |
| F-03 | F-03 S02 | phone | PASS | `shots/F03-S02-phone.png`, `curl/F03-oracle.json` | – |
| F-03 | F-03 S03 | desktop | PASS | `shots/F03-S03-desktop.png` | – |
| F-03 | F-03 S03 | phone | NOT RUN | – | harness: getByTestId('fr-text') |
| F-03 | F-03 S04 | desktop | PASS* | `shots/F03-S04-desktop.png` | free-text 'yarın 14:00 60 kişi' → 'Metinle eşleşen derslik yok: …' with 'Metni temizle', the recent-search chips keep the text; the chip count assert drifted |
| F-03 | F-03 S04 | phone | NOT RUN | – | harness: getByTestId('fr-text') |
| F-03 | F-03 S05 | desktop | PASS | `shots/F03-S05-desktop.png` | – |
| F-03 | F-03 S05 | phone | PASS | `shots/F03-S05-phone.png` | – |
| F-03 | F-03 S06 | desktop | PASS | `shots/F03-S06-desktop.png`, `curl/F03-S06-mine.txt` | – |
| F-03 | F-03 S06 | phone | PASS* | `shots/F03-S06-phone.png`, `curl/F03-S06-mine.txt` | 'A 105 rezerve et' (44 px) opens the sheet 'A 105 · P11–P12', '2 ders saatini rezerve et' books both periods (two BOOKED rows), focus lands on the result summary; the toast was not sampled in time |
| F-03 | F-03 S06 span-as-one-row | desktop | FAIL | – | R2-S-10 |
| F-03 | F-03 S06 span-as-one-row | phone | FAIL | – | R2-S-10 |
| F-03 | F-03 S07 | desktop | FAIL | `shots/F03-S07-desktop.png` | R2-S-01 |
| F-03 | F-03 S07 | phone | FAIL | `shots/F03-S07-phone.png` | R2-S-01 |
| F-03 | F-03 S08 | desktop | PASS | `shots/F03-S08-desktop.png` | – |
| F-03 | F-03 S08 | phone | PASS | `shots/F03-S08-phone.png` | – |
| F-03 | F-03 S09 | desktop | PASS | `shots/F03-S09-desktop.png` | – |
| F-03 | F-03 S09 | phone | PASS | `shots/F03-S09-phone.png` | – |
| F-03 | F-03 S10 | desktop | PASS | `shots/F03-S10-desktop.png` | – |
| F-03 | F-03 S10 | phone | PASS | `shots/F03-S10-phone.png` | – |
| F-03 | F-03 S11 | desktop | PASS | `shots/F03-S11-desktop.png` | – |
| F-03 | F-03 S11 | phone | PASS* | `shots/F03-S11-phone.png` | approval room: card 'Onay gerekir', '2 ders saati için talep et' → request sent, approver mail arrived; the toast was not sampled in time |
| F-03 | F-03 S12 | desktop | BLOCKED | – | P19-T1 'Derslerim' make-up shortcut not built |
| F-03 | F-03 S12 | phone | BLOCKED | – | P19-T1 'Derslerim' make-up shortcut not built |
| F-03 | F-03 TR scan /find-room | desktop | PASS | – | – |
| F-03 | F-03 TR scan /find-room | phone | PASS | – | – |
| F-04 | F-04 S01 | desktop | PASS | `shots/F04-S01-desktop.png`, `curl/F04-S01-tokens-off.txt` | – |
| F-04 | F-04 S01 | phone | PASS | `shots/F04-S01-phone.png`, `curl/F04-S01-tokens-off.txt` | – |
| F-04 | F-04 S02 | desktop | PASS | `shots/F04-S02-desktop.png`, `curl/F04-S02-settings.txt` | – |
| F-04 | F-04 S02 | phone | PASS | `shots/F04-S02-phone.png`, `curl/F04-S02-settings.txt` | – |
| F-04 | F-04 S03 | desktop | PASS* | `shots/F04-S03-desktop.png`, `curl/F04-S03-mine.txt` | Yaklaşan lists the three bookings with 'Ders tekrarı' notes, Taleplerim '1 bekliyor', İptal edilen shows the cancelled one with 'Gerekçe: Oda bakımda'; totals and the span rows are R2-S-10, the 16 px checkboxes R2-S-04 |
| F-04 | F-04 S03 | phone | PASS* | `shots/F04-S03-phone.png`, `curl/F04-S03-mine.txt` | Yaklaşan lists the three bookings with 'Ders tekrarı' notes, Taleplerim '1 bekliyor', İptal edilen shows the cancelled one with 'Gerekçe: Oda bakımda'; totals and the span rows are R2-S-10, the 16 px checkboxes R2-S-04 |
| F-04 | F-04 S03 span-as-one-row | desktop | INCONCLUSIVE | – | R2-S-10 |
| F-04 | F-04 S03 span-as-one-row | phone | INCONCLUSIVE | – | R2-S-10 |
| F-04 | F-04 S04 | desktop | FAIL | `shots/F04-S04-desktop.png` | R2-S-21 |
| F-04 | F-04 S04 | phone | FAIL | `shots/F04-S04-phone.png` | R2-S-21 |
| F-04 | F-04 S05 | desktop | PASS | `shots/F04-S05-desktop.png` | – |
| F-04 | F-04 S05 | phone | PASS* | `shots/F04-S05-phone.png` | Google / Outlook / Apple links carry the webcal feed URL; the clipboard toast could not be read on the phone context (no clipboard permission), verified on the desktop ('Bağlantı kopyalandı') |
| F-04 | F-04 S06 | desktop | PASS | `shots/F04-S06-desktop.png` | – |
| F-04 | F-04 S06 | phone | PASS | `shots/F04-S06-phone.png` | – |
| F-04 | F-04 S06 span-as-one-VEVENT | desktop | INCONCLUSIVE | `shots/F04-S06-desktop.png` | Telafi dersi VEVENTs: 0 |
| F-04 | F-04 S06 span-as-one-VEVENT | phone | INCONCLUSIVE | `shots/F04-S06-phone.png` | Telafi dersi VEVENTs: 0 |
| F-04 | F-04 S07 | desktop | PASS | `shots/F04-S07-desktop.png` | – |
| F-04 | F-04 S07 | phone | PASS | `shots/F04-S07-phone.png` | – |
| F-04 | F-04 S08 | desktop | PASS | `shots/F04-S08-desktop.png`, `curl/F04-S08-new.ics` | – |
| F-04 | F-04 S08 | phone | PASS | `shots/F04-S08-phone.png`, `curl/F04-S08-new.ics` | – |
| F-04 | F-04 S09 | desktop | PASS* | `shots/F04-S09-desktop.png` | no room-owner / department feeds for this staff account (no owned rooms, no department) — the sheet shows only the personal feed; the 'Derslerim' feed is not built (BLOCKED row) |
| F-04 | F-04 S09 | phone | PASS* | `shots/F04-S09-phone.png` | no room-owner / department feeds for this staff account (no owned rooms, no department) — the sheet shows only the personal feed; the 'Derslerim' feed is not built (BLOCKED row) |
| F-04 | F-04 S09 Derslerim feed | desktop | BLOCKED | `shots/F04-S09-desktop.png` | P19-T4 personal class feed not built |
| F-04 | F-04 S09 Derslerim feed | phone | BLOCKED | `shots/F04-S09-phone.png` | P19-T4 personal class feed not built |
| F-04 | F-04 S10 | desktop | PASS* | `shots/F04-S10-desktop.png`, `curl/F04-S10-mine.ics` | R2-S-22; select the 22 Oct row → '1 rezervasyonu iptal et' → dialog '1 rezervasyon iptal edilsin mi?' with the reason field → 200, toast '1 iptal edildi, 0 olduğu gibi kaldı', focus on the row's room button, the feed no longer carries the 22 Oct event (b1line empty); the toast wording is in R2-S-22, the 16 px checkbox and the non-sticky bulk bar in R2-S-04 |
| F-04 | F-04 S10 | phone | PASS* | `shots/F04-S10-phone.png`, `curl/F04-S10-mine.ics` | R2-S-22; select the 22 Oct row → '1 rezervasyonu iptal et' → dialog '1 rezervasyon iptal edilsin mi?' with the reason field → 200, toast '1 iptal edildi, 0 olduğu gibi kaldı', focus on the row's room button, the feed no longer carries the 22 Oct event (b1line empty); the toast wording is in R2-S-22, the 16 px checkbox and the non-sticky bulk bar in R2-S-04 |
| F-04 | F-04 S11 | desktop | PASS | `shots/F04-S11-desktop.png` | – |
| F-04 | F-04 S11 | phone | PASS | `shots/F04-S11-phone.png` | – |
| F-04 | F-04 S12 | desktop | SKIP | `shots/F04-S12-desktop.png` | no OAuth client; {"present":false,"btns":[]} |
| F-04 | F-04 S12 | phone | SKIP | `shots/F04-S12-phone.png` | no OAuth client; {"present":false,"btns":[]} |
| F-04 | F-04 TR scan /my-bookings(sync) | desktop | PASS | – | – |
| F-04 | F-04 TR scan /my-bookings(sync) | phone | PASS | – | – |
| F-12 | F-12 S04 logout | desktop | PASS | `shots/F12-S04-desktop.png` | – |
| F-12 | F-12 S04 logout | phone | PASS | `shots/F12-S04-phone.png` | – |
| F-12 | F-12 S05 | desktop | FAIL | `shots/F12-S05-desktop.png`, `shots/F12-S05-second-desktop.png` | R2-S-11 |
| F-12 | F-12 S05 | phone | FAIL | `shots/F12-S05-phone.png`, `shots/F12-S05-second-phone.png` | R2-S-11 |
| F-12 | F-12 S06 | desktop | FAIL | `shots/F12-S06-desktop.png` | R2-S-02 |
| F-12 | F-12 S06 | phone | FAIL | `shots/F12-S06-phone.png` | R2-S-02 |
| F-12 | F-12 S07 | desktop | FAIL | `shots/F12-S07-desktop.png` | R2-S-12 |
| F-12 | F-12 S07 | phone | FAIL | `shots/F12-S07-phone.png` | R2-S-12 |
| F-12 | F-12 S09 | desktop | NOT RUN | – | harness: getByRole('button', { name: /Bağlantıyı dene|^Dene$/ }).first() |
| F-12 | F-12 S09 | phone | BLOCKED | `shots/F12-S09-phone.png` | {"info":{"h1":"Oturum açma (LDAP)","inputs":["ldap-on:checkbox","ldap-create:checkbox","ldap-port:number","ldap-tls:checkbox","ldap-ign:checkbox","ldap-server:t |
| F-12 | F-12 S10 | phone | PASS | `shots/F12-S10-phone.png` | – |
| F-12 | F-12 S11 SSO admin UI | phone | BLOCKED | – | SSO admin UI not built on /admin/authentication (API tested below) |
| F-12 | F-12 S11 config guards | desktop | PASS | `curl/F12-SSO.json` | – |
| F-12 | F-12 S11 config guards | phone | PASS* | `curl/F12-SSO.json` | enable without tenant/client → 422, no secret leaks, four bad tenant ids → 422, admin-as-default-role → 422, planner write → 403 |
| F-12 | F-12 S12 login page SSO | desktop | PASS* | `shots/F12-S12-sso-desktop.png` | 'Microsoft ile giriş yap' (44 px) with the Turkish hints and the 'Kullanıcı adı ve parolayla giriş yap' disclosure, no sign-up, local fields hidden until the disclosure |
| F-12 | F-12 S12 login page SSO | phone | INCONCLUSIVE | `shots/F12-S12-sso-phone.png` | in the phone run the SSO link was absent and the local fields shown (the provider had been disabled by the preceding guard checks in that run's order); the desktop run shows the 44 px link |
| F-12 | F-12 S13 start (SSO disabled) | API | PASS | – | – |
| F-12 | F-12 S13 start redirect | desktop | PASS | `curl/F12-SSO.json` | – |
| F-12 | F-12 S13 start redirect | phone | PASS* | `curl/F12-SSO.json` | /auth/sso/entra/start → 302 to the IdP, a foreign ?next= is not echoed |
| F-12 | F-12 S14 callback refusals | desktop | PASS | – | – |
| F-12 | F-12 S14 callback refusals | phone | PASS* | – | forged state, user cancel and code reuse all land on /login?error=failed&ref=S-nnn with the alert 'Giriş yapılamadı. Tekrar deneyin. Sorun sürerse bu kodu yöneticinize iletin: S-nnn' focused |
| F-12 | F-12 S14 forged callback | API | PASS | – | – |
| F-12 | F-12 S15 exchange | API | PASS* | – | random ticket → 422 (too short), no session |
| F-12 | F-12 S16 invites | desktop | PASS* | – | invite 201 (30 days), bind invite 201, delete 204, used/deleted link → 'Bu davet artık geçerli değil. Yöneticinizden yeni bir davet isteyin.'; the limited-admin escalation case belongs to F-11 (admin tester) |
| F-12 | F-12 S16 invites | phone | PASS* | – | invite 201 (30 days), bind invite 201, delete 204, used/deleted link → 'Bu davet artık geçerli değil. Yöneticinizden yeni bir davet isteyin.'; the limited-admin escalation case belongs to F-11 (admin tester) |
| F-12 | F-12 S17 break-glass | desktop | PASS* | – | OIDC-only hides the local fields, ?method=local shows them, staff local login 401, admin local login 200, last-admin lockout refused 409 |
| F-12 | F-12 S17 break-glass | phone | INCONCLUSIVE | – | same as the desktop except the staff local login returned 200 in this run (the OIDC-only setting had been reverted by the preceding step in that order); not re-run |
| F-12 | F-12 S18 | desktop | BLOCKED | – | no tenant credentials |
| F-12 | F-12 S18 | phone | BLOCKED | – | no tenant credentials |
| F-12 | F-12 user menu rows@phone | phone | PASS | `shots/F12-usermenu-phone.png` | – |
| F-13 | F-13 A01 | desktop | PASS | `shots/F13-A01-_bookings-desktop.png`, `shots/F13-A01-_my-bookings-desktop.png` | – |
| F-13 | F-13 A01 | phone | PASS | `shots/F13-A01-_bookings-phone.png`, `shots/F13-A01-_my-bookings-phone.png` | – |
| F-13 | F-13 A02 | desktop | PASS* | `shots/F13-A02-desktop.png` | profile language 'English' (the picker now offers 'Kurum varsayılanı (Türkçe) / Türkçe / English', three options, the plan expected two) → toast 'Saved', every page title, h1, sheet, find-room and my-bookings text in English, no Turkish residue; the booking sheet reads 'Send request' with the approval notice |
| F-13 | F-13 A02 | phone | PASS* | `shots/F13-A02-phone.png` | profile language 'English' (the picker now offers 'Kurum varsayılanı (Türkçe) / Türkçe / English', three options, the plan expected two) → toast 'Saved', every page title, h1, sheet, find-room and my-bookings text in English, no Turkish residue; the booking sheet reads 'Send request' with the approval notice |
| F-13 | F-13 A03 | desktop | PASS | `shots/F13-A03-desktop.png` | – |
| F-13 | F-13 A03 | phone | PASS | `shots/F13-A03-phone.png` | – |
| F-13 | F-13 A04 | desktop | PASS | `shots/F13-A04-desktop.png` | – |
| F-13 | F-13 A04 | phone | PASS | `shots/F13-A04-phone.png` | – |
| F-13 | F-13 B01 | desktop | FAIL | `shots/F13-B01-desktop.png` | R2-S-15 |
| F-13 | F-13 B01 | phone | PASS | `shots/F13-B01-phone.png` | R2-S-15 |
| F-13 | F-13 B02 | desktop | FAIL | `shots/F13-B02-desktop.png` | R2-S-15 |
| F-13 | F-13 B02 | phone | FAIL | `shots/F13-B02-phone.png` | R2-S-15 |
| F-13 | F-13 B03 | desktop | PASS | `shots/F13-B03-desktop.png` | – |
| F-13 | F-13 B03 | phone | PASS | `shots/F13-B03-phone.png` | – |
| F-13 | F-13 B04 | desktop | PASS | – | – |
| F-13 | F-13 B04 | phone | PASS | – | – |
| F-13 | F-13 C01 | desktop | PASS | `shots/F13-C01-desktop.png` | – |
| F-13 | F-13 C01 | tablet | PASS | `shots/F13-C01-tablet.png` | – |
| F-13 | F-13 C02 admin | desktop | FAIL | `shots/F13-C02-admin-desktop.png` | R2-S-17 |
| F-13 | F-13 C02 admin | tablet | FAIL | `shots/F13-C02-admin-tablet.png` | R2-S-17 |
| F-13 | F-13 C02 staff | desktop | PASS* | `shots/F13-C02-desktop.png` | keyboard: arrow keys select a two-period span, live region '2 ders saati seçildi, 08:30–10:00, C 201.', Enter opens the sheet with focus inside, Tab reaches note and submit, Esc closes and focus returns to the cell; on the tablet Esc from the textarea left focus on a link ('A') — minor drift of the assert |
| F-13 | F-13 C02 staff | tablet | PASS* | `shots/F13-C02-tablet.png` | keyboard: arrow keys select a two-period span, live region '2 ders saati seçildi, 08:30–10:00, C 201.', Enter opens the sheet with focus inside, Tab reaches note and submit, Esc closes and focus returns to the cell; on the tablet Esc from the textarea left focus on a link ('A') — minor drift of the assert |
| F-13 | F-13 C02 withdraw | desktop | FAIL | – | R2-S-16 |
| F-13 | F-13 C02 withdraw | tablet | FAIL | – | R2-S-16 |
| F-13 | F-13 C03 | desktop | PASS* | `shots/F13-C03-desktop.png` | date picker in the grid header, per-date action selects labelled 'dd.mm.yyyy için işlem', live summary (polite) updates '9 rezerve edilecek' → '8 … 1 atlanacak', cancel scope reachable, 200, focus back on the cell |
| F-13 | F-13 C03 | tablet | PASS* | `shots/F13-C03-tablet.png` | date picker in the grid header, per-date action selects labelled 'dd.mm.yyyy için işlem', live summary (polite) updates '9 rezerve edilecek' → '8 … 1 atlanacak', cancel scope reachable, 200, focus back on the cell |
| F-13 | F-13 C04 | desktop | INCONCLUSIVE | `shots/F13-C04-desktop.png` | /find-room tab order: date, time, headcount, feature chips, text, 'Ara'; the live summary '21 boş oda' is polite; the result buttons are in DOM order; my visual-order heuristic flagged the chip row but nothing was out of place by eye |
| F-13 | F-13 C04 | tablet | PASS | `shots/F13-C04-tablet.png` | – |
| F-13 | F-13 C05 (desktop) | desktop | NOT RUN | – | harness: getByTestId('sync-copy-mine') |
| F-13 | F-13 C05 (tablet) | desktop | NOT RUN | – | harness: getByTestId('sync-copy-mine') |
| F-13 | F-13 C rings | desktop | PASS | – | – |
| F-13 | F-13 C rings | tablet | PASS | – | – |
| MOBILE | M-01@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-01@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-01@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-01@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-01@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-01@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-01@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-01@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-01@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-01@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-01@/login(login) | phone | PASS | `logs/mobile-login.json` | – |
| MOBILE | M-01@/login/change-password(change-password) | phone | PASS | `logs/mobile-change-password.json` | – |
| MOBILE | M-01@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-01@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-01@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-01@/my-bookings(sync-sheet) | phone | PASS | – | – |
| MOBILE | M-01@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-01@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-01@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-02@/admin/audit(audit) | phone | FAIL | `logs/mobile-audit.json` | R2-S-08 |
| MOBILE | M-02@/admin/settings(settings) | phone | FAIL | `logs/mobile-settings.json` | R2-S-08 |
| MOBILE | M-02@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-02@/approvals(reject) | phone | PASS | – | – |
| MOBILE | M-02@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-02@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-02@/bookings(recurring) | phone | FAIL | `logs/mobile-recurring.json` | R2-S-03 |
| MOBILE | M-02@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-02@/find-room(filters) | phone | FAIL | `logs/mobile-filters.json` | R2-S-06 |
| MOBILE | M-02@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-02@/find-room(results) | phone | FAIL | `logs/mobile-results.json` | R2-S-06 |
| MOBILE | M-02@/login(login) | phone | PASS | `logs/mobile-login.json` | – |
| MOBILE | M-02@/login/change-password(change-password) | phone | PASS | `logs/mobile-change-password.json` | – |
| MOBILE | M-02@/my-bookings(my-bookings) | phone | FAIL | `logs/mobile-my-bookings.json` | R2-S-04 |
| MOBILE | M-02@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-02@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-02@/my-bookings(sync-sheet) | phone | FAIL | – | R2-S-04, R2-S-08 |
| MOBILE | M-02@/profile(profile) | phone | FAIL | `logs/mobile-profile.json` | R2-S-08 |
| MOBILE | M-02@/reset-password(reset-password) | phone | FAIL | `logs/mobile-reset-password.json` | R2-S-08 |
| MOBILE | M-02@/settings(settings-integrations) | phone | FAIL | `logs/mobile-settings-integrations.json` | R2-S-08 |
| MOBILE | M-02@bell | phone | PASS | – | – |
| MOBILE | M-03@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-03@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-03@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-03@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-03@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-03@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-03@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-03@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-03@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-03@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-03@/login(login) | phone | PASS | `logs/mobile-login.json` | – |
| MOBILE | M-03@/login/change-password(change-password) | phone | PASS | `logs/mobile-change-password.json` | – |
| MOBILE | M-03@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-03@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-03@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-03@/my-bookings(sync-sheet) | phone | PASS | – | – |
| MOBILE | M-03@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-03@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-03@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-04@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-04@/approvals(reject) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-04@/bookings(cancel all) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(cancel one) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-04@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-04@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-04@/my-bookings(withdraw) | phone | PASS | – | – |
| MOBILE | M-04@bell | phone | PASS | – | – |
| MOBILE | M-05@/admin/settings(settings) | phone | NOT RUN | `logs/mobile-settings.json` | harness: the probe did not find the page's primary button (the save button lives inside the open tab panel) |
| MOBILE | M-05@/approvals(approvals) | phone | FAIL | `logs/mobile-approvals.json` | R2-S-05 |
| MOBILE | M-05@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-05@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-05@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-05@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-05@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-05@/find-room(results) | phone | FAIL | `logs/mobile-results.json` | R2-S-06 |
| MOBILE | M-05@/login(login) | phone | FAIL | `logs/mobile-login.json` | R2-S-20 |
| MOBILE | M-05@/login/change-password(change-password) | phone | FAIL | `logs/mobile-change-password.json` | R2-S-11 |
| MOBILE | M-05@/my-bookings(selection) | phone | FAIL | – | R2-S-04 |
| MOBILE | M-05@/my-bookings(sync-sheet) | phone | PASS* | – | the 'Takvime eşitle' section and its primary sit in their own card below the booking list (y 1460 at scroll 0); that is the section's place, not a sticky-footer case — the page's own primary (list actions) is at the top |
| MOBILE | M-05@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-05@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-06@/find-room | phone | PASS | – | – |
| MOBILE | M-06@/login | phone | PASS | – | – |
| MOBILE | M-06@/my-bookings | phone | PASS | – | – |
| MOBILE | M-07@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-07@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-07@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-07@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-07@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-07@/login/change-password(change-password) | phone | PASS | `logs/mobile-change-password.json` | – |
| MOBILE | M-07@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-07@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-07@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-07@/my-bookings(sync-sheet) | phone | PASS | – | – |
| MOBILE | M-07@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-07@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-07@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-08@/bookings | phone | PASS | – | – |
| MOBILE | M-09@/admin/audit(audit) | phone | FAIL | `logs/mobile-audit.json` | R2-S-07 |
| MOBILE | M-09@/admin/settings(settings) | phone | FAIL | `logs/mobile-settings.json` | R2-S-07 |
| MOBILE | M-09@/bookings(bookings) | phone | FAIL | `logs/mobile-bookings.json` | R2-S-07 |
| MOBILE | M-09@/find-room(find-room) | phone | FAIL | `logs/mobile-find-room.json` | R2-S-07 |
| MOBILE | M-09@/find-room(results) | phone | FAIL | `logs/mobile-results.json` | R2-S-07 |
| MOBILE | M-09@/login/change-password(change-password) | phone | PASS* | `logs/mobile-change-password.json` | no tab bar on the auth pages (by design); the probe reported the empty bar as a failure |
| MOBILE | M-09@/my-bookings(my-bookings) | phone | FAIL | `logs/mobile-my-bookings.json` | R2-S-07 |
| MOBILE | M-09@/my-bookings(my-bookings-cancelled) | phone | FAIL | `logs/mobile-my-bookings-cancelled.json` | R2-S-07 |
| MOBILE | M-09@/my-bookings(sync-off) | phone | FAIL | `logs/mobile-sync-off.json` | R2-S-07 |
| MOBILE | M-09@/my-bookings(sync-sheet) | phone | FAIL | – | R2-S-07 |
| MOBILE | M-09@/profile(profile) | phone | FAIL | `logs/mobile-profile.json` | R2-S-07 |
| MOBILE | M-09@/reset-password(reset-password) | phone | PASS* | `logs/mobile-reset-password.json` | no tab bar on the auth pages (by design); the probe reported the empty bar as a failure |
| MOBILE | M-09@/settings(settings-integrations) | phone | FAIL | `logs/mobile-settings-integrations.json` | R2-S-07 |
| MOBILE | M-10@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-10@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-10@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-10@/find-room | phone | PASS* | – | start/end and P1/P2 fields sit as a 159 px pair side by side with their labels above — a readable pair at 390; the small chips and segments of the same form are R2-S-06 |
| MOBILE | M-10@/find-room(book-from-results) | phone | PASS* | `logs/mobile-book-from-results.json` | start/end and P1/P2 fields sit as a 159 px pair side by side with their labels above — a readable pair at 390; the small chips and segments of the same form are R2-S-06 |
| MOBILE | M-10@/find-room(filters) | phone | PASS* | `logs/mobile-filters.json` | start/end and P1/P2 fields sit as a 159 px pair side by side with their labels above — a readable pair at 390; the small chips and segments of the same form are R2-S-06 |
| MOBILE | M-11@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-11@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-11@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-11@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-11@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-11@/login(login) | phone | PASS | `logs/mobile-login.json` | – |
| MOBILE | M-11@/login/change-password(change-password) | phone | FAIL | `logs/mobile-change-password.json` | R2-S-19 |
| MOBILE | M-11@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-11@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-11@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-11@/my-bookings(sync-sheet) | phone | PASS | – | – |
| MOBILE | M-11@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-11@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-11@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-12@/approvals(reject) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(book-sheet) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(cancel all) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(cancel one) | phone | PASS | – | – |
| MOBILE | M-12@/find-room | phone | FAIL | – | R2-S-06 |
| MOBILE | M-12@/login | phone | PASS | – | – |
| MOBILE | M-12@/login/change-password | phone | PASS | – | – |
| MOBILE | M-13@/find-room | phone | PASS | – | – |
| MOBILE | M-13@/login | phone | PASS | – | – |
| MOBILE | M-13@/my-bookings | phone | PASS | – | – |
| MOBILE | M-13@/my-bookings(sync) | phone | PASS | – | – |
| MOBILE | M-14@/find-room(search) | phone | PASS | – | – |
| MOBILE | M-14@/login | phone | PASS | – | – |
| MOBILE | M-14@/my-bookings(expand) | phone | PASS | – | – |

## Findings

### R2-S-01 (minor) F-03 S07 reserve from a stale result @1440 and @390
- Did: Searched D1 P11–P12 for 42 people with 'Bilgisayar laboratuvarı' (A 105, B 207 free). The admin then booked B 207 P11 through the API. Pressed 'B 207 rezerve et' on the stale list and submitted the sheet.
- Happened: The book sheet opened as 'B 207 · P12' (the period list starts at P12: the sheet silently dropped the taken P11) and the submit booked P12 alone: toast 'B 207, Per 22 Eki P12 için rezerve edildi'; the list refreshed to '0 boş oda' with 'Seçenekler'. No 'Bu derslik az önce doldu. Liste yenilendi.' and no sentence that the window shrank, so a user who clicked 'Rezerve et' for P11–P12 can end up with a one-period booking without noticing.
- Expected: F-03 acceptance 3: the stale card is refused with 'Bu derslik az önce doldu. Liste yenilendi.' (or the sheet states that P11 is no longer free and asks before booking P12 alone).
- Viewport: desktop, phone
- Evidence: `shots/F03-S07-desktop.png`, `shots/F03-S07-sheet-desktop.png`, `logs/f03-desktop.json`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/findroom/* (reserve from results → book sheet), components/bookings/book-sheet.tsx (span submit when one period is taken), backend POST /bookings/multi/{id}/create partial success

### R2-S-02 (major) F-12 S06 forced password change @1440 and @390
- Did: Admin set force_password_reset on the staff user. Staff logged in → /login/change-password?next=/bookings; filled the current and the new password twice; pressed 'Kaydet ve devam et'.
- Happened: POST /auth/change-password → 200 and the toast 'Parola değiştirildi', but the page stays on /login/change-password?next=… with the three fields cleared and the button disabled (no navigation to next within 15 s, on both viewports). Opening /my-bookings afterwards works (the change was saved), so the user is only stuck visually.
- Expected: After 'Parola değiştirildi' the browser lands on the next target (the flow: 'then the next target').
- Viewport: desktop, phone
- Evidence: `shots/F12-S06-desktop.png`, `shots/F12-S06-phone.png`, `logs/f12c-desktop.json`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/auth/change-password-form.tsx (router.replace(next) after success)

### R2-S-03 (major) MOBILE M-02 @/bookings book sheet (recurring) @390
- Did: Opened the admin's book sheet on the phone, 'Her hafta', 'Tarihleri göster'.
- Happened: Touch targets under 44 px inside the primary sheet: 'Tek seferlik'/'Her hafta' 116×38, 'Boşların hepsi' 108×32, 'Hiçbiri' 65×32, per-date 'Rezerve et'/'Atla' segments 85×30 (the ::after hit area does not register with elementFromPoint, so a tap 22 px off misses). The rest of the sheet passes M-04/M-05/M-10.
- Expected: Every control in the sheet ≥ 44 px or with a working 44 px hit area (MOBILE M-02).
- Viewport: phone
- Evidence: `logs/f02-phone.json`, `shots/F02-S03-phone.png`
- Seen before as: see T-R1-01 (primitive hit areas)
- File hints: smartsched/frontend/src/components/ui/segmented-control.tsx (coarseHitArea inside an overflow:auto list), components/bookings/recurring-preview-table.tsx

### R2-S-04 (major) MOBILE M-02 @/my-bookings @390
- Did: Opened /my-bookings on the phone with two bookings and one request.
- Happened: Tabs 'Yaklaşan'/'Geçmiş'/'İptal edilen' are 117×38; the per-row 'Bu rezervasyonu seç' checkboxes are 16×16 with a 1×1 sr-only label (no 44 px hit area). The bulk bar '1 rezervasyonu iptal et' sits at the top of the page (y 8–52 after scrolling), outside the thumb zone (M-05).
- Expected: Tabs and checkboxes ≥ 44 px (flow mobile expectations: 'The select checkbox has a ≥ 44 px hit area'); the bulk bar sticky at the bottom (above the tab bar).
- Viewport: phone
- Evidence: `logs/f04-phone.json`, `logs/f01-phone.json`, `shots/F04-S03-phone.png`
- Seen before as: lane A2 ask routed to B2: '/my-bookings row M-02 (checkbox hit area cut…)'
- File hints: smartsched/frontend/src/components/bookings/my-bookings-view.tsx (BookingList checkbox label, bulk bar), components/ui/tabs

### R2-S-05 (major) MOBILE M-05 @/approvals @390
- Did: Admin on the phone opened the staff request from the bell (lands on /approvals?request=…).
- Happened: '2 saatin hepsini onayla' sits at y 318–354 of 844 inside the detail (bottom 40 % starts at 506); the approve/reject buttons are not a sticky footer. The sheet itself passes M-04, the reject sheet passes M-04/M-12.
- Expected: F-01 mobile expectations: 'The approve/reject buttons are in a sticky footer' inside the bottom 40 %.
- Viewport: phone
- Evidence: `logs/f01-phone.json`, `shots/F01-S07-phone.png`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/approvals/* (drawer footer on phone)

### R2-S-06 (major) MOBILE M-02 / M-12 @/find-room @390
- Did: Opened Boş derslik bul on the phone, the filters sheet, and the results.
- Happened: Filters sheet: feature chips 'Projeksiyon' 87×24, 'Akıllı tahta' 80×24, the 'PC sayısı, en az' input 350×28. Results page: time-mode segments 'Saat'/'Ders saati'/'Süre' 106×30. M-12: with the keyboard open the 'Kaç kişi' field (y 372–416 of 508) is covered by the sticky 'Ara' capsule (elementFromPoint ≠ field). M-10: 'fr-start'/'fr-end' and 'fr-p1'/'fr-p2' share a row at 159 px each (allowed pair exception). With results open the primary 'Ara' scrolls away (M-05: at scroll 0 the button sits at y 1026, below the fold) — no sticky search button on the phone.
- Expected: Chips, segments and inputs ≥ 44 px; the focused field stays uncovered with the keyboard open.
- Viewport: phone
- Evidence: `logs/f03-phone.json`, `shots/F03-S01-phone.png`, `shots/F03-S02-phone.png`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/findroom/find-room-view.tsx (chip size in the sheet, sticky search over the form), components/ui/chip.tsx

### R2-S-07 (minor) MOBILE M-09 tab bar @390 (every staff route)
- Did: Looked at the bottom tab bar as staff on /bookings, /my-bookings, /find-room, /profile; as admin on /admin/settings, /admin/audit, /settings.
- Happened: Staff: the four items are 74 px wide with a 14 px label; 'Rezervasyonlar' and 'Rezervasyonlarım' overflow their item and overlap each other ('RezervasyonlaRezervasyonlarım', see the crop). Admin: 'Talepler' with the '99+' badge is clipped in a 59 px item (the badge is after the label in the accessible name, as fixed in T-R1-06).
- Expected: Labels fit without clipping or overlap in TR (MOBILE M-09).
- Viewport: phone
- Evidence: `shots/crop-tabbar-phone.png`, `logs/f01-phone.json`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/shell/tab-bar.tsx (label width / font-size at 390), messages/tr.json nav labels

### R2-S-08 (minor) MOBILE M-02 on secondary screens @390
- Did: M-02 on /profile (Bildirimler), /settings?tab=integrations, /admin/settings, /admin/audit, /reset-password, /timetable inspector, /classes, /settings?tab=solver.
- Happened: /profile notification switches 38×22 (pref-channel-in_app, pref-channel-email, pref-approval.*-in_app/-email, group switches); /settings webhooks-switch 38×22 and 'webhook-new' 130×36; /admin/settings 'Bildirimi kapat' 20×20 and org-language radios 16×16; /admin/audit 'Geri al' 86×36; /reset-password 'Oturum açmaya dön' 124×18; /timetable inspector 'Taşı…' 84×36; /classes filter chips 32 px; /settings?tab=solver relaxation segments 38 px. /my-bookings sync panel 'Gizlilik bölümüne git' 116×15; /find-room result card 'policy-why' 62×16. Also: /admin/audit 'Geri al' buttons 86×36 and the toast close 'Bildirimi kapat' 20×20 on the phone.
- Expected: ≥ 44 px (MOBILE M-02).
- Viewport: phone
- Evidence: `logs/f01-phone.json`, `logs/f04-phone.json`, `logs/f02-phone.json`, `logs/f12c-phone.json`, `logs/rv-ui-phone.json`
- Seen before as: R1-S-16 / R1-S-33 residue (T-R1-01, T-R1-49)
- File hints: smartsched/frontend/src/components/notifications/preferences-panel.tsx (Switch size on touch), components/ui/switch.tsx, components/audit/audit-view.tsx, components/timetable/floating-panel.tsx, components/classes/*

### R2-S-09 (minor) F-02 S10 undo from the audit log @1440
- Did: /admin/audit › newest 'Rezervasyon iptal edildi #1 … Geri al' › confirm 'Rezervasyon #1 geri alınsın mı?' › 'Geri al'.
- Happened: POST …/undo → 200, the row reads '… geri alındı', the booking is BOOKED again; but document.activeElement is <body> afterwards (the confirm closed and nothing took focus).
- Expected: Focus stays on that row (F-02 S10, motion T4 / U-07).
- Viewport: desktop
- Evidence: `logs/f02-desktop.json`, `shots/F02-S10-desktop.png`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/audit/audit-view.tsx (focus after undo)

### R2-S-10 (minor) F-04 S03 / F-03 S06 a two-period booking shows as two rows; 'etkin' count @1440 and @390
- Did: Booked P7–P8 (staff, /bookings/multi) and P11–P12 (from find-room results); opened /my-bookings.
- Happened: The span shows as two rows 'C 303 · P7' and 'C 303 · P8' (and 'A 105 P11', 'A 105 P12' in /bookings/mine). The totals line counted '0 etkin · bu dönem 4 · toplam 4' on desktop (two on-behalf bookings + one cancelled + one pending) and '2 etkin · bu dönem 4 · toplam 4' on the phone (own span + single): 'etkin' counts the user's own groups, 'bu dönem/toplam' count rows including the cancelled one, so the three numbers do not add up for the reader.
- Expected: One row per span (A-12 / persona-user Enh. #2, 'Two rows: FAIL (minor)'); totals on one counting basis.
- Viewport: desktop, phone
- Evidence: `logs/f04-desktop.json`, `logs/f04-phone.json`, `curl/F04-S03-mine.txt`
- Seen before as: A-12, persona-user Enh. #2
- File hints: smartsched/frontend/src/components/bookings/my-bookings-view.tsx (group rows by group_id; totals), backend /bookings/mine counts

### R2-S-11 (minor) stray toast 'Takvim eşitleme kurumunuzda kapalı.' @1440 and @390
- Did: As staff opened /profile (password section) and the forced-change page; calendar sync was off (no KVKK sign-off).
- Happened: A toast 'Takvim eşitleme kurumunuzda kapalı.' appears on /profile (and was listed among the toasts on /login/change-password) although the user did nothing with calendar sync. On the phone the same toast overlaps the 'Kaydet ve devam et' button (M-05 'free: false').
- Expected: No toast for a setting the user did not touch; the sync status belongs in the sync panel only.
- Viewport: desktop, phone
- Evidence: `logs/f12c-desktop.json`, `logs/f12c-phone.json`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/bookings/calendar-sync.tsx or the profile channels section (query error → toast)

### R2-S-12 (minor) F-12 S07 reset-password wording @1440
- Did: /reset-password › 'Kod gönder' for the staff e-mail; read the page and the mail.
- Happened: The mail states the expiry ('24 saat geçerli') and the subject is bilingual (good); the right code sets the password ('Parolanız değiştirildi. Şimdi oturum açabilirsiniz.') and a wrong code answers 'Kod hatalı ya da süresi dolmuş. Yenisini isteyin.' (good). Residue: the page still says 'Kodların süresi bir süre sonra dolar.' (U-21 asked for the expiry) and the code form's hint reads 'En az 8 karakter. Dizin (LDAP) hesapları için boş bırakın.' (U-21: no LDAP text on the reset form). 'Oturum açmaya dön' is a 124×18 link on the phone (R2-S-08).
- Expected: The page states the expiry (24 saat); no LDAP text on the reset form (U-21).
- Viewport: desktop, phone
- Evidence: `logs/f12c-desktop.json`, `mail/ (reset mail, code redacted)`
- Seen before as: U-21 residue (T-R1-30)
- File hints: smartsched/frontend/messages/tr.json crbs.reset.requested; components/auth/reset-password*.tsx

### R2-S-13 (minor) API refusals in English for Turkish users @API
- Did: POST /bookings for yesterday (Friday 16 Oct P1) as staff; POST /council/jobs/{id}/commit with undecided merges on the fresh stack.
- Happened: 409 {code:'range_min', message:'bookings must be made at least 0 day(s) ahead (from 17.10.2026)'} with no message_tr (and the code is not 'past' as F-02 S12 expects); 409 'N review item(s) must be decided first (e.g. Same instructor? '…' and '…')' in English and carrying the two instructor names.
- Expected: Every refusal carries message_tr (T-R1-29); the intake refusal names counts, not people (KVKK).
- Viewport: API
- Evidence: `curl/F02-S12-past.txt`, `curl/F08-jobA.json`
- Seen before as: R1-S-24 / T-R1-29 residue
- File hints: smartsched/backend/app/api/v1/bookings.py (range_min / past), app/api/v1/council.py commit guard

### R2-S-14 (minor) dashboard odometer digits in the accessible text @1440 and @390
- Did: Read main.innerText on /dashboard (admin) during the R1-S-15 check.
- Happened: 'Derslik doluluğu %23 % 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 …' and 'İnceleme bekleyen 139 0 1 2 3 4 5 6 7 8 9 …': the rolling digits of the KPI odometers are exposed (T-R1-48 hid them on the run report only).
- Expected: aria-hidden on the rolling digits of every odometer (T-R1-48 check: 'main.innerText has no 0 1 2 … 9 sequence').
- Viewport: desktop, phone
- Evidence: `logs/rv-ui-desktop.json`, `shots/R1-S-15-dashboard-desktop.png`
- Seen before as: R1-S-28 / T-R1-48 residue
- File hints: smartsched/frontend/src/components/dashboard/* (KPI odometer)

### R2-S-15 (minor) F-13 B01/B02 the book sheet animates under reduced motion @1440 and @390
- Did: Context with reducedMotion:'reduce'; and separately Ayarlar › 'Hareketi azalt' on (html[data-motion=reduced], survives reload). Opened the book sheet, the bell, the sync panel.
- Happened: Two rAF ticks after the tap the book sheet still has translate 40px / opacity 0 with a running 'translate' animation (moving: ['translate']); the bell panel and the sync panel are static. Busy buttons keep their words ('Aranıyor…').
- Expected: Under OS or in-app reduced motion nothing moves (F-13 acceptance 3).
- Viewport: desktop, phone
- Evidence: `logs/f13-desktop.json`, `logs/f13-phone.json`
- Seen before as: motion audit T? (sheets)
- File hints: smartsched/frontend/src/components/ui/sheet.tsx (enter animation not gated by prefers-reduced-motion / data-motion)

### R2-S-16 (major) F-13 C02 withdraw confirm does not trap focus @1440 and tablet
- Did: Keyboard only: Taleplerim › 'Talebi geri çek' › Enter; then Tab repeatedly inside the confirm.
- Happened: Tab order: 'Talebi geri çek' → 'Kapat' → focus leaves the dialog (an empty stop, then the page's skip link 'İçeriğe atla', 'SmartSched'): the alertdialog does not keep focus (A-20). Enter on the confirm works and focus returns to the row afterwards (good).
- Expected: The confirm traps focus (A-20).
- Viewport: desktop, tablet
- Evidence: `logs/f13-desktop.json`, `logs/f13-desktop-tablet.json`
- Seen before as: A-20
- File hints: smartsched/frontend/src/components/approvals/my-requests.tsx (confirm dialog), components/ui/alert-dialog focus trap

### R2-S-17 (minor) F-13 C02 admin keyboard legend on /approvals @1440 and tablet
- Did: Focused the first inbox item, pressed j, k, Enter, then d (reject), Escape, then a.
- Happened: j/k leave focus on the same item (approval-2 → approval-2 → approval-2); Enter opens the drawer; d opens the reject sheet (and Enter on the aria-disabled confirm shows 'Gerekçeyi yazın; yalnız boşluk sayılmaz.' and focuses the text, good); a produced no 'onaylandı' toast within 4 s. ArrowDown was not tried.
- Expected: Arrow keys or j/k move through the list; A approves the open request (F-13 C02, persona-admin 'approvals A/D/R').
- Viewport: desktop, tablet
- Evidence: `logs/f13-desktop.json`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/approvals/approvals-view.tsx (list key handling)

### R2-S-18 (suggestion) F-02 S08 scope options without counts @1440 and @390
- Did: Cancel dialog on a series date: 'Uygulanacak: Bu tarih · Bu ve sonrakiler · Tüm seri'.
- Happened: The options carry no counts ('Bu ve sonrakiler: 3 tarih'); the user learns the number only from the toast.
- Expected: Each scope option states how many dates it cancels (persona-user Enh. #7, F-02 S08 target).
- Viewport: desktop, phone
- Evidence: `shots/F02-S08-desktop.png`
- Seen before as: persona-user Enh. #7
- File hints: smartsched/frontend/src/components/bookings/booking-detail-sheet.tsx ScopePicker

### R2-S-19 (minor) MOBILE M-11 title-only locale toggle on /login/change-password @390
- Did: M-11 on /login/change-password.
- Happened: The TR/EN toggle buttons carry only a title ('Türkçe', 'English'), no accessible name; on /login the same control passes.
- Expected: aria-label on the locale buttons (M-11).
- Viewport: phone
- Evidence: `logs/f12c-phone.json`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/shell/locale-toggle.tsx (compact variant)

### R2-S-20 (trivial) test-plan and locator drift (no product defect) @1440 and @390
- Did: Compared the flow files with the build.
- Happened: F-12: the sign-in page uses signin.* strings (subtitle 'Ders programı, sınavlar ve derslik rezervasyonu', 'Kullanıcı adı veya e-posta', 'Parola', 'Parolamı unuttum', 'Kullanıcı adı, e-posta veya parola yanlış.', session notice 'Oturumunuzun süresi doldu. Yeniden giriş yaptığınızda kaldığınız sayfaya dönersiniz.'); the flow quotes the older auth.*/glass.auth.* strings; crbs.users.resetWhere still refers to “Parolanızı mı unuttunuz?”. F-04: 'sync-open' does not exist; the sync panel is inline on /my-bookings at 1440 and 390 ('Takvime eşitle' card). F-02: the end option reads 'Dönem sonuna kadar (27.12.2026)' (org date format), the kind/scope/time-mode SegmentedControls are role=tablist/tab (not radio) with a hidden select fallback. F-03: the non-matching group is 'Özelliği eksik odalar (n)', the fit text 'Kapasite 60: 42 kişi için %30 boş koltuk', the request card 'Onay gerekli: talep oluşturulur'. M-05 on /login: the centred card puts the submit at y 355–403 (not the bottom 40 %), which reads fine as a user. F-02 S12: TODAY is a Saturday (no periods); the past check used Friday through the API. F-04 S04: 'Özel bağlantılarımı oluştur' first opens a user consent dialog 'Takvim eşitleme için rızanız gerekiyor' with 'Rıza ver ve devam et' / 'Şimdi değil' / 'Gizlilik bölümüne git' (not in the flow file; sensible). F-02 S06: the planner helper's book sheet offers 'Her hafta' but can_book_recur is false for the role, so the series-as-request step is BLOCKED by the role's permissions, not by the product.
- Expected: Update the flow files / MOBILE route matrix (suggester).
- Viewport: desktop, phone
- Evidence: `logs/f12a.json`, `logs/f04-desktop.json`, `logs/f02-desktop.json`, `logs/f03-desktop.json`
- Seen before as: T-R1-43 family
- File hints: docs/testing/flows/F-12…, F-04…, F-02…, F-03…

### R2-S-21 (minor) F-04 S04 private links panel @1440 and @390
- Did: 'Özel bağlantılarımı oluştur' → 'Rıza ver ve devam et' (the new consent step) → the feed block appears.
- Happened: The 'Web bağlantısı' field overflows its box (scrollWidth > clientWidth, no inner scroll: urlOverflow true) and the copy buttons 'sync-copy-mine' / 'sync-copy-webcal-mine' / 'sync-copy-room' are 32×32 icon-only buttons; 'Google Takvim'e ekle', 'Outlook'a ekle', 'Apple Takvim' are 28 px tall. Copy itself works ('Bağlantı kopyalandı', clipboard holds the https and webcal URLs) and the add-to links are right.
- Expected: The URL field wraps or scrolls inside itself; on phone every copy/add button ≥ 44 px and labelled with words (F-04 mobile expectations).
- Viewport: desktop, phone
- Evidence: `logs/f04-desktop-part.json`, `shots/F04-S04-desktop.png`
- Seen before as: – (new)
- File hints: smartsched/frontend/src/components/bookings/calendar-sync.tsx (url field overflow, icon-only copy buttons)

### R2-S-22 (minor) F-02 S08 / S11 cancel from Rezervasyonlarım
- Did: Cancelled one date of the weekly series (scope 'Bu tarih', reason 'Oda bakımda') from the /my-bookings row sheet on the phone, then 'Bu ve sonrakiler' (reason 'Dönem sonu'); the same two cancellations from the grid cell sheet on the desktop.
- Happened: The toast wording depends on where you cancel from: from the grid the one-date cancel reads 'Bu rezervasyon iptal edildi · Gerekçe: Oda bakımda' and the series cancel '3 rezervasyon iptal edildi'; from the Rezervasyonlarım row the one-date cancel reads '1 rezervasyon iptal edildi' (no reason echoed) and the series cancel of four dates reads 'Bu rezervasyon iptal edildi · Gerekçe: Dönem sonu' (singular for four). The server responses were right in all four cases (cancelled [4] / [2,3,4,5]). The bulk cancel from Rezervasyonlarım (F-04 S10) reads '1 iptal edildi, 0 olduğu gibi kaldı' — the '0 olduğu gibi kaldı' tail is noise when nothing was skipped.
- Expected: One wording per outcome: 'N rezervasyon iptal edildi' (with the reason when one was given) regardless of the entry point, singular only when one date was cancelled.
- Viewport: phone (also desktop by path)
- Evidence: `logs/f02-phone-fix.json (F-02 S08, S11 toast)`, `logs/f02-desktop.json (F-02 S08, S11 toast)`, `shots/F02-S08-phone.png`, `shots/F02-S11-phone.png`
- Seen before as: new (round 1 had no cancel-toast row); related to R1-B toast-text tickets T-R1-06
- File hints: smartsched/frontend/src/components/bookings/booking-detail-sheet.tsx (CancelDialog toast), cancel-many-dialog.tsx, messages/tr.json crbs.cancel.*



## Round-1 ids re-verified on `deb38315`

Verified: R1-S-01, R1-S-02, R1-S-03, R1-S-05, R1-S-06, R1-S-07, R1-S-08, R1-S-10, R1-S-11, R1-S-12, R1-S-13, R1-S-14, R1-S-17, R1-S-18, R1-S-20, R1-S-21, R1-S-23, R1-S-25, R1-S-27, R1-S-28, R1-S-29, R1-S-30, R1-S-32, R1-S-33, R1-S-34, R1-S-35, R1-S-39.
Reopened: R1-S-04, R1-S-16, R1-S-19, R1-S-22, R1-S-24, R1-S-31.
Inconclusive (not reproduced by my script, no evidence either way): R1-S-09, R1-S-15, R1-S-26.
Open suggestions (not in the round-1 build or an owner decision): R1-S-36, R1-S-37, R1-S-38.

| Id | Round-1 severity | Round-2 result | Note |
|---|---|---|---|
| R1-S-31 | minor · Encoding and delimiter are not reported, a PNG renamed .xlsx is not re | **reopened** `deb38315` | verified: the file row reads 'CSV · Windows-1254 · ;' / 'CSV · UTF-8 · ,', a PNG renamed .xlsx is refused at upload (400); still open: after a reload /onboarding shows no job to reopen ('Son işler' empty, 0 job links) · R1-S-31 encoding UI: fresh stack /onboarding: the cp1254 ';' export's file row reads 'CSV · Windows-1254 · ;' (format chip), the UTF-8 export reads 'CSV · UTF-8 · ,'; the renamed PNG is refused at upload (400) · R1-S-31 encoding: Job C file entry: {"name":"bahar_listesi_noktali_virgul.csv","route":"fast:planning-list","warnings":[],"status":"DONE"}; Turkish letters {"ş":0,"ğ":0,"İ":0,"ı":0,"mojibake":0}; dry-run mr {} · R1-S-31 renamed PNG: {"status":400,"error":"\"\""} · R1- |
| R1-S-11 | major · 'Yaz' writes 1,527 requests without a confirm, the commit cannot be un | **verified** `deb38315` | fresh stack: xlsx + its CSV export in one job plan 1,512 creates (no double import); 'Yaz' now opens 'BAHAR dönemine yazılsın mı?' with Turkish entity names and counts and states 'Geri alınamaz: yazılan kayıtlar bu işten geri alınmaz.' (the audit row council.commit has reversible:false, the honest option F-08 S14 allows) · R1-S-11 UI: fresh stack: 'Yaz' opens the confirm 'BAHAR dönemine yazılsın mı? BAHAR dönemine 1.511 yeni talep yazılacak. Kurallar 39 yeni · 0 değişecek · Öğretim elemanları 402 yeni · Talepler 1.511 yeni · Dersli · R1-S-11 API: dry-run meeting_requests {"create":1512,"update":0,"unchanged":15,"conflict":0}; commit 200 {"term_id":1,"term_code":"2026-BAHAR","term_created":fa |
| R1-S-10 | major · With AI switched off the intake still promises AI, and progress and re | **verified** `deb38315` | fresh stack: progress and review lines in Turkish, 'Başlat · 3 dosya', AI switch disabled with 'Yönetici kapattı', scanned PDF warning in Turkish; residue: the PDF/DOCX route chip reads 'YZ' while AI is off, and the commit 409 for undecided merges is English and carries names (R2-S-13) · R1-S-10 UI progress: fresh stack: progress lines in Turkish ('Bitti · 81 ms · CSV · UTF-8 · ,', 'Bu iş için yapay zekâ kapalı; yalnız kural tabanlı okuma', 'Doğrudan · genel yol'), 'Başlat · 3 dosya', AI switch disabled w · R1-S-10 API: English fragments in review/file texts: ["DONE"]; pdf {"name":"taranmis_sinav_programi.pdf","route":"vision","warnings":[],"status":"DONE"}; ai note:  · R1-S-10 UI: {"s2":{"r |
| R1-S-03 | blocker · A Word file cannot be taken in with AI off: its table rows become 36 b | **verified** `deb38315` | fresh stack, AI off: rules_memo.docx is read on the 'general' route (rows method ai: 0), the review payload has 25 items and renders; the blocking items are the 3 instructor merges, not AI rows · R1-S-03: docx entry {"name":"rules_memo.docx","route":"general","warnings":[],"status":"DONE"}; rows method=ai 0; blocking ["Aynı öğretim elemanı mı? '<ad>' ve '<ad>'","Aynı öğretim elemanı mı? '<ad>' ve '<ad> |
| R1-S-12 | major · A re-upload of the same CSV in a new job plans 1,332 new requests and  | **verified** `deb38315` | fresh stack, before masking: re-uploading bahar_requests_en.csv in a new job (Job B, remembered items 8) dry-runs to meeting_requests create 0 · update 1 · unchanged 1,339 and instructors {} (round 1: 1,332 creates and 418 people) · R1-S-12: Job B (same CSV, before masking): meeting_requests {"create":0,"update":1,"unchanged":1339,"conflict":0} instructors {}; remembered items 8 |
| R1-S-18 | major · Instructor names travel in review item ids to a viewer with content=fa | **verified** `deb38315` | viewer GET …/review → 200 with content:false and opaque merge ids ('merge:instructor:<hash>'), POST review/commit and GET rows → 403; after masking the intake memory holds 8 items with no name-like text · R1-S-18: {"viewer":{"status":200,"content":false,"nIds":25,"nameLikeIds":0,"sampleIdShape":["x:2","x:x:94c991dc91277d5e","x:x:bf3x7bf14ec8f"],"post":403,"commit":403,"rows":403},"memory":{"n":8,"nameLike":0,"r |
| R1-S-34 | minor · stack.sh mask left 7 instructor names with a surname fragment after th | **verified** `deb38315` | fresh stack after the Job A commit: `stack.sh mask` → 'masked 403 instructors and 1088 other cells … left 0'; kvkk_mask.py --verify → left 0 on the first pass · R1-S-34: stack.sh mask → masked 403 instructors and 1088 other cells (12111 names) ¦ left 0; verify → left 0 |
| R1-S-17 | major · The assignments API marks every row SOLVER and unlocked, so the integr | **verified** `deb38315` | R1-S-17: {"total":845,"origins":{"SOLVER":845},"locked":0,"planner_lock":773,"conflict":166,"conflictWithReason":166,"cap0Conflict":41,"cap0CapacityReason":0,"cap0Sample":[]}; origin is still SOLVER for every  |
| R1-S-07 | major · The Studio run card says 'hiçbir kural bozulmadı' while the report lis | **verified** `deb38315` | R1-S-07: truth verdicts {"7":{"status":"FEASIBLE_PARTIAL","hard":100,"placed":688,"total":716,"verdict":"exceptions","headline":"688/716 ders yerleşti · kesin kurallar korundu; 400 kabul edilmiş istisna listel · R1-S-07 card: Studio text: Son başarılı çalıştırma: #8 · bugün · bazı dersler dersliksiz kaldı; 'hiçbir kural bozulmadı' present: false · R1-S-07 card: Studio text: (no run card visible); 'hiçbir kural bozulmadı' present: false |
| R1-S-05 | major · A hard pin of 100 students into a 30-seat room is accepted at the edit | **verified** `deb38315` | R1-S-05: {"adm":[422,"{\"detail\":{\"code\":\"capacity\",\"message\":\"100 students do not fit B 201 (30 seats)\",\"message_tr\":\"100 öğrenci 30 kişilik B 201'e sığmaz\",\"message_en\":\"100 students do not f |
| R1-S-02 | blocker · The nursing 17:30 rule as a hard template crashes the pre-check (500)  | **verified** `deb38315` | R1-S-02: precheck 200; named ["no_time","HEM 236 ikisi de A 204 dersliğine Perşembe 15:10-15:50 saatinde kilitli.","HEM 236 are both locked in A 204 on Thursday 15:10-15:50.","HEM 236 (#1010) both hold A204 on |
| R1-S-01 | blocker · A plain move that the server calls 'uygun' drops the published run to  | **verified** `deb38315` | move guard on B0 (#8): dry-run and real bulk-move of PHAR 240 §1 into the TIP room A 201 (from week 4) answer ok:false with the hard rule 'A 201 TIP dersliği (tıp eğitimine ayrılmış); bu ders oraya konamaz (kesin kural)', the run stays hard 100; planner force → 403; admin force without reason → 422 'forcing moves that break tip needs a written reason'; with a reason the move applies, the run reads hard 99 and lists the broken rule with reason, author and time; restore brings hard 100 back. Still open by design: POST /runs/8/activate on the already-published run answered 200 at hard 99 (the forced edit stays live: owner decision R1-S-37) · R1-S-01: {"before":{"hard":100,"active":true},"dry":{ |
| R1-S-06 | major · An ERROR run offers 'Yayınla'; the server refusal is shown as a concur | **verified** `deb38315` | R1-S-06: API: week run activate [409,"{\"detail\":{\"code\":\"scope_reduction\",\"message\":\"run 7 covers weeks [3] only; publishing it removes weeks [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 1 |
| R1-S-27 | minor · A cancelled run reads like a failure and claims all preferences were m | **verified** `deb38315` | R1-S-27: API cancelled run #11: {"status":"CANCELLED","error":"cancelled by admin@smartsched.local","finished_at":"2026-10-17T03:13:16.697386","hard":null,"soft":null}; report wording checked in the UI pass · R1-S-27: {"iptal":true,"who":"İptal edildi","badWords":[],"publish":0,"shot":"shots/R1-S-27-cancelled-desktop.png"} · R1-S-27: {"iptal":true,"who":"İptal edildi","badWords":[],"publish":0,"shot":"shots/R1-S-27-cancelled-phone.png"} |
| R1-S-19 | major · No learned suggestion for the academician (instructor 157, A-block hab | **reopened** `deb38315` | POST /learning/refresh for Güz (24,168 observations) and Bahar; GET /learning/suggestions lists 14 (Güz) / 17 (Bahar) suggestions, none with subject id 157; no cross-season room-level suggestion any more (that half is fixed) · R1-S-19: {"ref":[200,"{\"extract\":{\"added\":{\"definitive_room\":9632,\"excluded_lock\":1016,\"request_text\":1184,\"request_time\":12336},\"added_total\":24168,\"skipped\":{\"definitive_no_room_ne"],"n":14, |
| R1-S-14 | major · Invigilation does not work with the default pool on the real Final dat | **verified** `deb38315` | R1-S-14: {"board":6,"p1":[202,"{\"plan_id\":1,\"status\":\"QUEUED\"}"],"plan1":{"status":"OPTIMAL","headline":"Atanacak görev yok · Sınav çalıştırması #6 hiçbir sınavı bir salona yerleştirmemiş: gözetmen atana · R1-S-14 UI: {"pool":"Havuz: sınav listesinde 220 kişi; eğitmen kaydıyla eşleşen 133, birden çok kayda uyan 72, eğitmen listesinde olmayan 15 · havuzda 132 kişi","all":false,"headline":"846 salon-oturum, 1091 göre · R1-S-14 UI: {"pool":"Havuz: sınav listesinde 220 kişi; eğitmen kaydıyla eşleşen 133, birden çok kayda uyan 72, eğitmen listesinde olmayan 15 · havuzda 132 kişi","all":false,"headline":"846 salon-oturum, 1091 göre |
| R1-S-04 | major · Accepting one soft wish makes the minimal-change re-solve lose 17 plac | **reopened** `deb38315` | the accepted room wish (PSY 277 → C 301) and a repair re-solve of G0 (#10, run #13, 60 s) still give moved 1 · moved_unexplained 1 · newly_unplaced 17 (15 of them now flagged base_conflict) · unplaceable 26; fixed part: the preview names every loss with its cause ('… Yayımdaki hücresi artık kesin bir kuralı bozuyor …', 'ING 301 (75 öğrenci …) yerleşemedi: sığan derslikler o saatte dolu — …') and the publish confirm lists '17 ders dersliğini kaybediyor' with a required tick; the 2 unexplained losses and the 1 unexplained move remain (Q9) · R1-S-04: {"ids":[1602,1603,1900,1993],"wish":[201,"{\"dry_run\":false,\"submission\":\"06760150c909\",\"status\":\"pending\",\"items\":[{\"id\":73,\"constr |
| R1-S-29 | minor · The undo leaves the 3 new courses behind, and a console 409 appears be | **verified** `deb38315` | R1-S-29: {"tid":4,"draft":201,"val":[200,"{\"draft_id\":1,\"version\":1,\"can_commit\":true,\"counts\":{\"errors\":0,\"warnings\":0,\"info\":7},\"steps\":[{\"step\":\"program\",\"status\":\"ok\",\"errors\":[], |
| R1-S-28 | minor · The same run shows different issue counts and exception lists by viewp | **verified** `deb38315` | R1-S-28: Sorun 457 @desktop vs 457 @other; 'Diğer notlar' groups 0; digit sequence false; exceptions: planlayıcının kilitlediği derslik sınıfa küçük ya da özelliği eksik (planlama listesindeki seçim korundu) · · R1-S-28: Sorun 457 @phone vs 457 @other; 'Diğer notlar' groups 0; digit sequence false; exceptions: planlayıcının kilitlediği derslik sınıfa küçük ya da özelliği eksik (planlama listesindeki seçim korundu) · 1 |
| R1-S-23 | minor · Several Turkish sentences are ungrammatical or unclear | **verified** `deb38315` | R1-S-23 run wording: hafta [] pct [] label undefined · R1-S-23 percent suffix: moderation header: Yayında: #10 · taleplerin %95'i karşılandı · R1-S-23 invigilation decimal: decimal-point readings [] · R1-S-23 run wording: hafta [] pct [] label undefined · R1-S-23 percent suffix: moderation header: Yayında: #10 · taleplerin %95'i karşılandı · R1-S-23 invigilation decimal: decimal-point readings [] |
| R1-S-13 | major · Comparing a term run with a one-week run declares the week run better  | **verified** `deb38315` | R1-S-13: {"headline":"#7, #8 ile karşılaştırıldı: 832 ders taşındı, 5 yalnız B'de, 2 yalnız A'da yerleşti; sert 100→100, yumuşak 83→82 (-1) · Kapsamlar farklı (A 1–19. haftalar, B 3. hafta); yalnız ortak 3. ha · R1-S-13: {"headline":"#7, #8 ile karşılaştırıldı: 832 ders taşındı, 5 yalnız B'de, 2 yalnız A'da yerleşti; sert 100→100, yumuşak 83→82 (-1) · Kapsamlar farklı (A 1–19. haftalar, B 3. hafta); yalnız ortak 3. ha |
| R1-S-15 | major · The dashboard and the moderation header say nothing is planned while a | **inconclusive** `deb38315` | activating the Güz board import (#4, kind EXAM, source GRID_IMPORT) leaves #10 active too (both is_active after the call), so the dashboard ('Derslik doluluğu %23', '13 ders hâlâ derslik bekliyor (çalıştırma #10)') and the moderation header ('Yayında: #10 · taleplerin %95'i karşılandı') keep reading the solver run; the 'board alone' state of round 1 (before stack.sh runs) was not reproducible on this snapshot · R1-S-15: {"act4":200,"active":{"r4":true,"r10":true,"act4body":"{\"id\":4,\"term_id\":2,\"term_code\":\"2026-GUZ\",\"kind\":\"EXAM\",\"horizon\":\"TERM\",\"horizon_params\":{},\"status\":\"FEASIBLE\",\"params\ · R1-S-15: {"act4":200,"active":{"r4":true,"r10":true,"act4body":"{\"id\":4 |
| R1-S-25 | minor · A course code finds nobody in Kişiler, and the priority editor cannot  | **verified** `deb38315` | Moderasyon › Kişiler › 'PSY 277' now finds the instructor ('323 kişiden 1 gösteriliyor', 'Dr. Öğr. Üyesi S. E. … 4 karşılandı · 0 karşılanmadı'); on the phone the Sınıflar rows carry the priority trigger (8 found); the `p` shortcut was not confirmed on desktop (my row focus did not land) · R1-S-25: {"rows":{"n":1,"caption":"323 kişiden 1 gösteriliyor","first":"Dr. Öğr. Üyesi S. E. İnsan ve Toplum Bilimleri Fakültesi 3 4 4 / 4 0 Normal 3 2 Hayır"},"pr":{"trigger":0},"kinds":0,"en":[]} · R1-S-25: {"rows":{"n":1,"caption":"323 kişiden 1 gösteriliyor","first":"Dr. Öğr. Üyesi S. E. İnsan ve Toplum Bilimleri Fakültesi · 4 karşılandı · 0 karşılanmadı"},"pr":{"trigger":8},"kinds":0,"en":[]} |
| R1-S-24 | minor · English labels leak into the Turkish staff screens | **reopened** `deb38315` | fixed: dialog close buttons read 'Kapat', the moderation Tür column shows Turkish kinds, breadcrumbs no longer show 'recreate', the inspector Geçmiş has no 'Run #'; still English: the move-force refusal for a planner, 403 {detail:'moving despite a conflict is admin-only'} (no message_tr), the booking range_min 409 and the council commit 409 (R2-S-13) · R1-S-24 /moderation: raw kinds 0; EN ; breadcrumb undefined · R1-S-24 API refusal TR: 403 {"detail":"moving despite a conflict is admin-only"} · R1-S-24 recreate breadcrumb: breadcrumb undefined; baseline Yeni çözüm ← yayındaki plan #10 · Yayında değil · R1-S-24 inspector: Geçmiş: undefined · R1-S-24 /moderation: raw kinds 0; EN ; breadcrumb u |
| R1-S-32 | minor · 'Onaya gönder' accepts a press with '0 ders seçildi' and gives no feed | **verified** `deb38315` | R1-S-32: {"w":{"open":true,"count":"0 ders seçildi","disabled":true,"issue":"En az bir ders seçin."},"after":{"issue":"En az bir ders seçin.","toast":[],"posted":0}} · R1-S-32: {"w":{"open":true,"count":"0 ders seçildi","disabled":true,"issue":"En az bir ders seçin."},"after":{"issue":"En az bir ders seçin.","toast":[],"posted":0}} |
| R1-S-09 | major · An administrator cannot force a clash from the timetable at all; only  | **inconclusive** `deb38315` | the move dialog now has move-force / move-force-reason / move-force-admin-only elements in the build, but my script never reached an occupied room (the 'Dolu · 38' group stayed collapsed); the API side of the force path is verified under R1-S-01 (planner 403, admin reason 422/200) · R1-S-09: {"chosen":null,"force":{"conflict":"çakışıyor (A 204 Pzt 09:20–11:40)","serverOk":"✓ Sunucu kontrolü: uygun","force":null,"adminOnly":false,"confirmDis":true,"panel":false},"forceFlow":null,"plannerFo · R1-S-09: {"chosen":null,"force":{"conflict":"çakışıyor (A 204 Pzt 09:20–11:40)","serverOk":"✓ Sunucu kontrolü: uygun","force":null,"adminOnly":false,"confirmDis":true,"panel":false},"forceFlow":null,"plan |
| R1-S-26 | minor · Search does not move focus to the class, the overlay sidebar hides its | **inconclusive** `deb38315` | the timetable search box (calendar-search) and the sidebar toggle did not behave as my script expected (no focus move recorded, sidebar not reopened), so Enter-to-chip and Esc-closes-sidebar stay unverified; the API unplaced count is 35 for #8 and the inspector no longer shows the stray '“Derslik”' line · R1-S-26: {"focusAfterEnter":null,"sidebar":{"open":false,"togVisible":true,"covered":false,"openAfterEsc":false},"api":35,"derslikLine":false} · R1-S-26: {"focusAfterEnter":null,"sidebar":null,"api":35,"derslikLine":false} |
| R1-S-35 | suggestion · Some first loads are slow on the shared host (INCONCLUSIVE: load 5–13  | **verified** `deb38315` | advisory re-measure under load 3–7: /timetable 2.6–2.8 s, /generate first load 7.2–7.8 s, run report usable at once; still no skeleton on the first Studio load (FLE-007 open) · R1-S-35 /timetable load: 2996 ms to networkidle @desktop, load 2.43 · R1-S-35 /generate first load: 5512 ms · R1-S-35 /timetable load: 2988 ms to networkidle @phone, load 1.53 · R1-S-35 /generate first load: 4694 ms |
| R1-S-22 | minor · The Studio says 'Tüm dönem · 2 hafta' for the 14-week Güz term | **reopened** `deb38315` | Studio on Güz: the sentence reads '14 hafta boyunca 58 derslikte 632 ders planlıyorsunuz.' but the scope rail still reads 'Tüm dönem · 2 hafta' · R1-S-22: Güz scope: ["Tüm dönem · 2 hafta","14 hafta boyunca 58 derslikte 632 ders planlıyorsunuz."] (picked via select); the rail still reads 'Tüm dönem · 2 hafta' while the sentence says 14 hafta · R1-S-22: Güz scope: ["14 hafta boyunca 58 derslikte 632 ders planlıyorsunuz."] (picked via select) |
| R1-S-21 | minor · Once the Studio scope fell back to H1 with '0 derslikte' and 'no succe | **verified** `deb38315` | R1-S-21: quick ["Tüm dönem · 17 hafta"] settled ["Tüm dönem · 17 hafta","17 hafta boyunca 58 derslikte 869 ders planlıyorsunuz."] · R1-S-21: quick [] settled [] |
| R1-S-08 | major · The Turkish example chip leads to a dead end, and the template cannot  | **verified** `deb38315` | R1-S-08: {"title":"Belirli saatten sonra ders olmasın","progs":true,"progsCount":"2 program seçildi","year":"1","related":true,"noKey":true,"latest":["11. ders · 17:30 biter"]} · R1-S-08: {"title":"Belirli saatten sonra ders olmasın","progs":true,"progsCount":"2 program seçildi","year":"1","related":true,"affected":"23 derse uygulanıyor","noKey":true,"latest":["11. ders · 17:30 biter"] |
| R1-S-30 | minor · Reset rows show '#98' instead of the person, the typed confirm accepts | **verified** `deb38315` | 'Tümünü sıfırla…' with 'sifirla' shows 'Yazılan kelime eşleşmiyor.' before submit and keeps 'Sıfırla' disabled, autocapitalize=off; the person-reset row ('#98') could not be re-run (no suggestion for 157 on this snapshot, R1-S-19); phone card buttons not measurable for the same reason · R1-S-30: {"cards":[],"rows":[],"typed":{"mismatch":"Yazılan kelime eşleşmiyor.","confirmDis":true,"autocap":"off"}} · R1-S-30: {"cards":[],"rows":[],"typed":{"mismatch":"Yazılan kelime eşleşmiyor.","confirmDis":true,"autocap":"off"}} |
| R1-S-33 | minor · Tab-bar badge order, a missing h1, small links and an unlabelled file  | **verified** `deb38315` | tab-bar badge now after the label ('Talepler, 139 inceleme bekliyor'), /moderation/learning has one h1 'Öğrenme belleği', dashboard 'Çizelge oluştur' 153×44, /onboarding file input hidden (1×1) with the label 'Dosyaları bırakın veya seçin' and no input under 16 px, /runs/compare pickers 44 px; the clipped '99+' badge is a new row (R2-S-07) · R1-S-33 learning h1: {"h1":1,"text":"Öğrenme belleği"} · R1-S-33 compare pickers: [{"h":44,"tag":"SELECT"},{"h":44,"tag":"SELECT"}] · R1-S-33 learning h1: {"h1":1,"text":"Öğrenme belleği"} · R1-S-33 dashboard link: {"w":153,"h":44} · R1-S-33 tab-bar badge order: ["Özet¦Özet","Talepler\n99+¦Talepler, 223 inceleme bekliyor","Oluştur¦Oluştur","Çizelge¦Çizel |
| R1-S-38 | suggestion · The term policy card lives only in Ayarlar › Çözücü and follows the si | **open** `deb38315` | suggestion FLE-004 not built: the relaxation card has no term picker and its hint still points to 'Yeniden çöz' (the button is 'Koruyarak yeniden çöz') · R1-S-38: {"text":"Sığmayan dersler · 2026-BAHAR Bu dönemde kendi seçimi olmayan her çözüm bu kuralla çalışır. Bir çalıştırma kendi kuralını “Yeniden çöz” penceresinde seçebilir. Her ders sığmazsa Önce kilitlil · R1-S-38: {"text":"Sığmayan dersler · 2026-BAHAR Bu dönemde kendi seçimi olmayan her çözüm bu kuralla çalışır. Bir çalıştırma kendi kuralını “Yeniden çöz” penceresinde seçebilir. Her ders sığmazsa Önce kilitlil |
| R1-S-16 | major · On the phone the main planning controls are below 44 px or out of thum | **reopened** `deb38315` | phone, touch mode confirmed (controlHmd 44px): /timetable inspector 'Taşı…' 84×36, /classes filter chips 32 px, /settings?tab=solver relaxation segments 38 px; fixed: move-sheet scope rows 350×44 and free-room rows 44 px, publish sheet checkbox row 44 px and 'Yayınla' sticky in the bottom 40 % (rv-ui phone) · R1-S-16 inspector: {"move":{"w":84,"h":36},"m04":{"x":0,"y":200,"w":390,"h":644,"vp":{"width":390,"height":844},"scrollable":true,"closeBtn":[{"w":44,"h":44,"name":"Kapat"}],"ok":true}} · R1-S-16 move sheet: {"radios":[{"t":"Tüm haftalar (1–14)","w":350,"h":44},{"t":"Tüm haftalar (1–14)","w":350,"h":44},{"t":"Sadece 3. hafta (16 Şubat)","w":350,"h":44},{"t":"Sadece 3. hafta (16 Şubat)", |
| R1-S-20 | major · The unplaced list shows raw ids instead of course codes, and a week ru | **verified** `deb38315` | publish confirm of #8 lists the unplaced classes by course code (no '#929'-style ids; 33 codes counted) with the 'Eksik derslerle yayımlamayı onaylıyorum' tick; the week run #7 shows the scope tick ('Evet, bu haftalar yayından kalksın') in the first confirm, the API answers 409 scope_reduction with a Turkish message and 200 with confirm_scope_reduction |
| R1-S-36 | suggestion · The real lists carry duplicates that make pickers hard to use | **open** `deb38315` | suggestion FLE-002 ('Veri temizliği' list) not in the round-1 build; unchanged |
| R1-S-37 | suggestion · A forced clash on the published run goes live at once; only a later re | **open** `deb38315` | owner decision still open in ROADMAP (forced edit on the live plan); API behaviour unchanged by design |
| R1-S-39 | suggestion · README §7 / F-08 S09 masks names before the re-upload steps S10/S11, w | **verified** `deb38315` | F-08 now runs S09 (masking) after S10/S11 and says why (T-R1-43); followed in this round: Job B re-upload before masking plans 0 creates |

## Not run in this round

- F-04 S12 (Google/Microsoft connectors): no OAuth client on this host → SKIP; F-12 S18 (real Entra tenant): no credentials → BLOCKED.
- F-03 S12 'Derslerim' make-up shortcut and F-04 S09 'Derslerim' feed: not built (P19-T1 / P19-T4) → BLOCKED; F-12 S11 SSO admin UI: not built, the API was tested instead.
- F-02 S05 replacement path (admin cancels the on-behalf booking and books a replacement), F-02 S06 custom date range of a series, F-02 S09 on the phone, F-03 S03/S04 free-text on the phone, F-12 S09 'Bağlantıyı dene' (disabled without a server), F-13 C05 reset-link confirm by keyboard: my harness did not reach the control (NOT RUN rows); the desktop or the API step covers the behaviour where the note says so.
- The planner has no recurring-booking right on this build, so the planner series of F-02 was not run (R2-S-20).
- README §8: timings are advisory (load 3–7 while the other testers ran); the M-14 frame rows were read at 1.5–2.3.
