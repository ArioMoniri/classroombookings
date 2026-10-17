# Flow loop round 3 · staff (department staff member who books rooms) · 2026-10-17

Ledger: `flow-r3-staff-2026-10-17` · persona tester: the staff persona of README §2 (`personel.test@smartsched.local`, "P. T.", TEACHER), with the admin for approver steps, the academician as second requester and the planner helper for the planning-rights checks · plan: [ROUND3 brief], [README](../README.md), [MOBILE](../MOBILE.md), the staff part of the "Re-test list for round 3" (docs/ROADMAP.md), every `R2-S-nn` of [round 2](round-2-staff.md), the open round-1 ids R1-S-09/15/16/22/24/26/31, and a smoke of F-01/F-02/F-03/F-04/F-12/F-13 at 1440 (mouse) and 390×844 (touch) with MOBILE M-02/M-05 on every route.
Snapshot: `8db884fd` (`8db884fdbac71c7efd7472f31fcc58b2f7e354a2`, `claude/focused-wright-ktt0ss`), frozen worktree `scratchpad/r3staff/flow-src-8db884f` (removed at the end) · stack API :19410, web :19411 (`REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`), SMTP sink :2626, fresh stack :19412/:19413 for F-08 (two clean databases) · load average 0.6–9.2 on 4 cores during the morning part, 2–5 after the restart, so timing rows are advisory (README §8).
Interruption: a usage limit stopped the round at 10:10 UTC; the container restarted at 18:55. Every result captured before the stop was kept (the scratch folder survived). The stack came back from its own `rec.snapshot.db`, which holds the post-`stack.sh runs` + seed state of the morning, so it was not rebuilt. Checked after the restore: #7 688/716, #8 683/717, #9 524/530, #10 517/530, all hard 100, `kvkk_mask.py --verify` → `left 0`. The remaining items ran from 19:00 to 19:30 UTC.
Dates (README §4.3): TODAY 2026-10-17 (Saturday, no teaching periods) · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D5 2026-11-19 · D6 2026-11-26 · holiday Thu 29 Oct inside the F-02 series · Chromium 141 (chromium-1194), Playwright 1.56.1 library · `scripts/record/lib/touch.mjs` (`assertTouch` before every M-02/M-03/M-05, `controlHmd` 44px) · F-13 Part C also on a 768×1024 tablet with a keyboard.
Data: real Bahar 2026, Güz 2026-27 and Final 2026 workbooks plus the room master, names masked to initials. Board-only snapshot `rec.board` taken right after the seed (R1-S-15). Accounts: the §4.4 seed (academician linked to instructor 157). No Anthropic key, AI intake off.
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r3staff/ev` (`shots/`, `curl/` with tokens and reset codes redacted, `logs/<script>-<viewport>.json|.out`, `issues.json`, `verdicts.json`, `judge.json`); scripts in `…/r3staff/scripts/` (`run-r3.sh` runner; the round-2 harness patched by `patch_r3.py`; new probes `r3.mjs`, `r3-board.mjs`, `r3-tt.mjs`, `r3-move.mjs`, `r3-toast.mjs`, `r3-reset-kb.mjs`, `r3-final.mjs`, `f08b–f08f.mjs`).

## BLUF

**Round-2 staff ids on `8db884fd`: 20 verified · 1 reopened (R2-S-08, minor) · 1 open suggestion (R2-S-18 / FLE-010).** Round-1 ids still open: **R1-S-09, R1-S-15, R1-S-22, R1-S-24, R1-S-31 verified · R1-S-16 and R1-S-26 reopened in part** (both minor residue). Ticket checks on the fresh stack: T-R2-20 and T-R2-21 verified, **T-R2-19 reopened in part**.
**6 new findings: 0 blocker · 1 major · 5 minor.** 378 step × viewport rows: 311 PASS, 44 PASS* (the behaviour was right on the device, a strict assert in my script drifted; the note says what was seen), 2 FAIL (each tied to an id), 7 NOT RUN (harness), 6 BLOCKED (not built: 'Derslerim' shortcut and feed, Entra tenant), 4 INCONCLUSIVE, 4 SKIP.

**Ready for release from this persona's point of view: no, because R3-S-04 fails on the officer's first scenario.** Re-importing the office's own Turkish Excel CSV of the unchanged Bahar list plans to rewrite the weeks of 1,333 of 1,512 requests (16 → 14 weeks). The two exports of one list disagree on the term length, so T-R2-19's "≥ 99 % unchanged" check still fails. Everything else a staff member does day to day is release-ready at the desk and on the phone.

What is fixed and holds up as a user:
- the forced password change lands on the next page;
- every main phone screen (recurring sheet, My bookings, Approvals, Find a room) has 44 px targets and its primary in thumb reach;
- the stale find-room card is refused cleanly;
- one cancel-toast wording everywhere;
- the private calendar links wrap and have worded 44 px copy buttons, a refused clipboard is handled, and the KVKK consent gate holds in the API (409 `consent_required`) and in the UI;
- reduced motion stops the sheets;
- confirms trap focus;
- j/k/Enter/a work on the approvals inbox;
- reset-page copy and coded refusals are in Turkish;
- the dashboard has no digit strip;
- the board-only dashboard, heatmap and moderation agree (24 % / 24.1 %, 72 %);
- the forced move from the timetable works end to end: planner refused, admin with a reason, hard 99, undo to 100.

New, by severity:
- **major R3-S-04**: the cp1254 ';' re-upload plans 1,333 week updates (T-R2-19 part).
- **minor R3-S-01**: a rejected request is counted in "bu dönem / toplam".
- **minor R3-S-02**: focus falls to `<body>` after the stale-card refusal.
- **minor R3-S-03**: the audit viewer labels the series parent "Booking series iptal edildi".
- **minor R3-S-05**: focus falls to `<body>` after a cancel from the My bookings row sheet at 1440.
- **minor R3-S-06**: "save-solver" is not sticky on the phone.

Reopened residue:
- R2-S-08 / R1-S-16: /classes filter chips 32 px, the inspector's "Yerleşimi açıkla" 138×36, "webhook-new" 130×36.
- R1-S-26: the overlay sidebar hides its own toggle and ignores Esc at 1440 and 1024; on the phone the search in the filters sheet does not filter the agenda.

## Summary

| Severity | Count | Ids |
|---|---|---|
| blocker | 0 | – |
| major | 1 | R3-S-04 |
| minor | 5 | R3-S-01, R3-S-02, R3-S-03, R3-S-05, R3-S-06 |

| Flow / area | Result |
|---|---|
| F-01 request / approve / reject / withdraw | green at 1440 and 390: request with the '1 adımlı onay' notice, 'Gönderiliyor…', approver mail, approve '2 ders saati onaylandı: C 303.', reject with reason reaching the bell, the row and the mail; the bell deep link expands and focuses the request (also while already on /my-bookings); preferences 44 px switches |
| F-02 recurring / cancel / undo | green: re-check keeps 'Atla' / 'Yerine geç', replaced booking 'Seri #1 ile değiştirildi', one toast wording, one audit row per booking, undo focus on the row, past date → 409 `past` with message_tr; S06 (planner series) NOT RUN (harness) · R3-S-03, R3-S-05 |
| F-03 find a room | green: capsule 'Ara' fixed in thumb reach, filters sheet 44 px, 'Kaç kişi' clear of the keyboard, stale card refused · R3-S-02 |
| F-04 my bookings + calendar feed | green: one row per span, KVKK consent gate (API 409 + inline step), wrapping link, worded copy buttons, TENTATIVE → CONFIRMED, reset (keyboard too) with focus on the new link, bulk capsule, admin switch off → 404 → on → 200 · R3-S-01 |
| F-08 intake (fresh stack, before masking) | dry run == commit, same CSV 0/0, coded 409 without names, no 'YZ' chip with AI off, recent jobs, /onboarding/<id>, keyboard drop zone; cp1254 re-upload fails · R3-S-04 |
| F-12 sign-in | green: forced change lands on next, reset page copy + coded short-code 400, session expiry for the second session, SSO guards / start / callbacks / invites / break-glass as round 2 |
| F-13 language, motion, keyboard | green: reduced motion (OS + in-app), confirm traps, inbox keyboard, English end to end; B04 frames advisory (worst LoAF 150 ms at load 5) |
| MOBILE M-02 / M-05 on every route | pass on every staff route; FAIL only on admin secondary screens (R2-S-08 residue, R3-S-06) |

### Scenario results (Fatih Bey, re-run as the planning staff)

| Scenario | Result |
|---|---|
| Import the Bahar list and the weekly grid | fresh stack: xlsx + its CSV plan and commit 1,512 requests identically (dry run == commit), the same CSV again plans 0/0, undecided merges are refused in Turkish without names, the job list and /onboarding/<id> survive a reload; **the office's cp1254 export plans 1,333 week changes on the same list (R3-S-04)** |
| Find a course | PHAR 240 through the timetable sidebar search: one chip, focus on it, a no-match sentence (R1-S-26 fixed at 1440/1024; phone and overlay residue reopened) |
| Generate week 3 | week run #7 688/716 hard 100 (as round 2); Studio rail reads 'Tüm dönem · 14 hafta' for Güz (R1-S-22 verified) |
| Move PHAR 240 to A 206 from 23 Feb | move dialog with the week-scope rows 350×44 and the room groups; a clash (A 204) is refused for the planner and forced by the admin with a reason, run hard 99 with the banner, undo back to 100 (R1-S-09 verified) |
| Nursing first-years before 17:30 (Turkish) | the Turkish chip opens 'Belirli saatten sonra ders olmasın' with 2 programmes, year 1, '11. ders · 17:30 biter', '23 derse uygulanıyor' (smoke, unchanged since round 2) |
| Export the week to Excel | not re-run (verified in round 2; T-R2-29's '-haftaN' name is the admin's item) |
| Infeasible request (102 in a 30-seat room) | not re-run (verified in round 2, R1-S-05); a planner's forced move is 403 with message_tr (R1-S-24 verified) |

## Re-verification

### Round-2 staff ids

| Id | Round-2 severity · step | Ticket | Round-3 result | What I saw |
|---|---|---|---|---|
| R2-S-01 | minor · F-03 S07 reserve from a stale result @1440 and @390 | T-R2-14 | **verified** `8db884fd` | T-R2-14: the stale card is refused with 'Bu derslik az önce doldu. Liste yenilendi.', no sheet, no POST, the room leaves the list, P12 stays free (1440 + 390). Focus after the refusal: R3-S-02 |
| R2-S-02 | major · F-12 S06 forced password change @1440 and @390 | T-R2-03 | **verified** `8db884fd` | T-R2-03: 'Kaydet ve devam et' → 200, 'Parola değiştirildi', lands on the next target, fields never shown again (1440 + 390) |
| R2-S-03 | major · MOBILE M-02 @/bookings book sheet (recurring) @390 | T-R2-05, T-R2-09 | **verified** `8db884fd` | recurring sheet at 390 touch: M-02 clean ('Tek seferlik'/'Her hafta' 44 px, per-date segments and 'Boşların hepsi'/'Hiçbiri' 44 px), M-04/M-05/M-10 pass; 'Yeniden denetle' keeps per-date choices (T-R2-09) |
| R2-S-04 | major · MOBILE M-02 @/my-bookings @390 | T-R2-11 | **verified** `8db884fd` | /my-bookings at 390: tabs 117×44, checkbox labels 44×44, M-02 clean; '1 rezervasyonu iptal et' capsule 712–756 free at scroll 0/400/end |
| R2-S-05 | major · MOBILE M-05 @/approvals @390 | T-R2-12 | **verified** `8db884fd` | /approvals at 390: M-05 PASS (approve in the sticky footer), M-02 clean, reject sheet M-02 clean |
| R2-S-06 | major · MOBILE M-02 / M-12 @/find-room @390 | T-R2-01, T-R2-10 | **verified** `8db884fd` | /find-room at 390: 'Ara' capsule fixed at 714–758 at scroll 0/400/end, free; filters sheet M-02 clean (chips 28 px in 44 px wrappers), 'Arama metni' 44 px in the sheet; M-12 'Kaç kişi' 320–364 of 508 uncovered; policy-why 62×44 |
| R2-S-07 | minor · MOBILE M-09 tab bar @390 (every staff route) | T-R2-04 | **verified** `8db884fd` | tab bar at 390: staff 'Rezerve / Benimkiler / Taleplerim / Diğer' 74×48, none clipped; admin 'Talepler 99+' badge inside the nav, name 'Talepler, 139 inceleme bekliyor' |
| R2-S-08 | minor · MOBILE M-02 on secondary screens @390 | T-R2-05, T-R2-28, T-R2-32 | **reopened** `8db884fd` | fixed: /profile switches 44×44, /reset-password 'Oturum açmaya dön' 124×44, /admin/audit 'Geri al' 44 px, /admin/settings and /settings?tab=solver M-02 clean, policy-why 62×44, the toast close 44×44. Still under 44 px at 390 touch: /classes filter chips 32 px ('Değişenler' 104×32 … 'İnceleme bekleyen' 169×32), timetable inspector 'Yerleşimi açıkla' 138×36, /settings?tab=integrations 'webhook-new' 130×36 (one of two readings) |
| R2-S-09 | minor · F-02 S10 undo from the audit log @1440 | T-R2-31 | **verified** `8db884fd` | T-R2-31: after 'Geri al' focus is on the row (LI audit-event-160), the row reads '… geri alındı', reason codes decoded (R3-S-03 for the series parent label) |
| R2-S-10 | minor · F-04 S03 / F-03 S06 a two-period booking shows as two rows; 'etkin' count @1440  | T-R2-13 | **verified** `8db884fd` | T-R2-13: one Yaklaşan row 'C 303 · P7–P8 (13:30–15:00)' with per-period chips; totals on one basis without the cancelled booking ('1 etkin · bu dönem 3 · toplam 3' = own single + live rows incl. the pending request). Residue: a rejected request still counts (R3-S-01) |
| R2-S-11 | minor · stray toast 'Takvim eşitleme kurumunuzda kapalı.' @1440 and @390 | T-R2-15 | **verified** `8db884fd` | T-R2-15: no 'Takvim eşitleme' toast or live region on /profile or /my-bookings with sync off; the card shows the quiet text 'Takvim eşitleme yönetici tarafından kapatıldı.' (no role) |
| R2-S-12 | minor · F-12 S07 reset-password wording @1440 | T-R2-06 | **verified** `8db884fd` | T-R2-06: hint 'En az 8 karakter.' without LDAP, no 'bir süre sonra', mail '24 saat geçerli', wrong code 'Kod hatalı ya da süresi dolmuş. Yenisini isteyin.', short code → 400 invalid_code with message_tr (no pydantic text) |
| R2-S-13 | minor · API refusals in English for Turkish users @API | T-R2-17, T-R2-21 | **verified** `8db884fd` | POST /bookings for Friday P1 → 409 code 'past' with message_tr; council commit with undecided merges → 409 review_pending 'Önce 3 inceleme kararı verilmeli.' with no names |
| R2-S-14 | minor · dashboard odometer digits in the accessible text @1440 and @390 | T-R2-26 | **verified** `8db884fd` | T-R2-26: /dashboard main.innerText has no digit strip ('Derslik doluluğu %23', 'İnceleme bekleyen 139') at 1440 and 390, also on the board-only database |
| R2-S-15 | minor · F-13 B01/B02 the book sheet animates under reduced motion @1440 and @390 | T-R2-07 | **verified** `8db884fd` | T-R2-07: OS reduced motion and in-app 'Hareketi azalt': book sheet translate none, opacity 1, no running animation; bell/sync static (1440 + 390); data-motion survives reload |
| R2-S-16 | major · F-13 C02 withdraw confirm does not trap focus @1440 and tablet | T-R2-02 | **verified** `8db884fd` | T-R2-02: withdraw confirm traps Tab (6 stops inside, aria-modal), Enter → 'Talep geri çekildi.', focus back on the row (1440 + 768 keyboard) |
| R2-S-17 | minor · F-13 C02 admin keyboard legend on /approvals @1440 and tablet | T-R2-12 | **verified** `8db884fd` | T-R2-12: j/k move between inbox rows, Enter puts focus on the drawer title, 'a' approves ('Onaylandı: A 101.') at 1440 and 768 |
| R2-S-18 | suggestion · F-02 S08 scope options without counts @1440 and @390 | – | **open** `8db884fd` | suggestion FLE-010 not built: the cancel scope select still offers 'Bu tarih / Bu ve sonrakiler / Tüm seri' without counts |
| R2-S-19 | minor · MOBILE M-11 title-only locale toggle on /login/change-password @390 | T-R2-05 | **verified** `8db884fd` | T-R2-05: the locale buttons on /login/change-password are named 'Türkçe' / 'English'; M-11 clean |
| R2-S-20 | trivial · test-plan and locator drift (no product defect) @1440 and @390 | T-R2-35 | **verified** `8db884fd` | T-R2-35: the corrected flow files were followable (consent step, inline sync card, tablist segments, fr-text in the sheet, F-10 probes); small drift left: F-12 S05 field messages read 'Şu anki parola yanlış.' / 'En az 8 karakter kullanın.' |
| R2-S-21 | minor · F-04 S04 private links panel @1440 and @390 | T-R2-15 | **verified** `8db884fd` | T-R2-15: the link is a wrapping read-only textarea (no overflow), copy buttons 'Kopyala' 110×44 / 'webcal kopyala' 156×44 and add links 44 px on the phone; a refused clipboard toasts 'Kopyalanamadı: bağlantıyı alandan seçin' and focuses the field, no page error |
| R2-S-22 | minor · F-02 S08 / S11 cancel from Rezervasyonlarım | T-R2-16 | **verified** `8db884fd` | T-R2-16: one toast wording from the grid and from the My bookings row sheet: '1 rezervasyon iptal edildi · Gerekçe: Oda bakımda'; series '2 rezervasyon iptal edildi · Gerekçe: Program değişti'; bulk '1 rezervasyon iptal edildi' (no '0 olduğu gibi kaldı'). 'Bu rezervasyon iptal edildi' is only the sheet's own notice |
### Round-1 ids (the open ones, plus the ones my smoke re-touched)

| Id | Round-1 severity · title | Round-2 result | Round-3 result | What I saw |
|---|---|---|---|---|
| R1-S-03 | blocker · A Word file cannot be taken in with AI off: its table rows become 36 b | verified | **verified** `8db884fd` | R1-S-03@fresh: docx entry {"name":"rules_memo.docx","route":"general","warnings":[],"status":"DONE"}; rows method=ai 0; blocking ["Aynı öğretim elemanı mı? '<ad>' ve '<ad>'","Aynı öğretim elemanı mı? '<ad>' ve '<ad> |
| R1-S-04 | major · Accepting one soft wish makes the minimal-change re-solve lose 17 plac | reopened | **not re-run** `8db884fd` | admin / lane S item (T-R2-34), on the admin tester's list |
| R1-S-07 | major · The Studio run card says 'hiçbir kural bozulmadı' while the report lis | verified | **verified** `8db884fd` | R1-S-07 card@desktop: Studio text: henüz başarılı bir çalıştırma yok.; 'hiçbir kural bozulmadı' present: false · R1-S-07 card@phone: Studio text: (no run card visible); 'hiçbir kural bozulmadı' present: false |
| R1-S-08 | major · The Turkish example chip leads to a dead end, and the template cannot  | verified | **verified** `8db884fd` | R1-S-08@desktop: {"title":"Belirli saatten sonra ders olmasın","progs":true,"progsCount":"2 program seçildi","year":"1","related":true,"noKey":true,"latest":["11. ders · 17:30 biter"]} · R1-S-08@phone: {"title":"Belirli saatten sonra ders olmasın","progs":true,"progsCount":"2 program seçildi","year":"1","related":true,"affected":"23 derse uygulanıyor","noKey":true,"latest":["11. ders · 17:30 biter"] |
| R1-S-09 | major · An administrator cannot force a clash from the timetable at all; only  | inconclusive | **verified** `8db884fd` | corrected F-10 S05/S06 steps at 1440 and 390: the busy room A 204 ('HEM 242 ile çakışıyor') picked from the 'Dolu · 37' group; planner: 'Taşı' disabled, 'Çakışmaya rağmen taşımayı yalnızca yönetici yapabilir', no force button; admin: 'Taşı' disabled, force panel 'Bu taşıma kesin bir kuralı bozuyor…', 'Yine de taşı' disabled with 'ab', enabled with a reason, POST 200 applied, run hard 99 with the banner naming the rule and reason, 'Geri al' → 'Geri alındı: …', hard 100 |
| R1-S-10 | major · With AI switched off the intake still promises AI, and progress and re | verified | **verified** `8db884fd` | smoke (fresh stack): Turkish progress lines, AI switch 'Yönetici kapattı', PDF 'Okunmadı' with the Turkish reason; the API's file status enum 'DONE' is not UI text |
| R1-S-11 | major · 'Yaz' writes 1,527 requests without a confirm, the commit cannot be un | verified | **verified** `8db884fd` | smoke: xlsx + its CSV in one job plan 1,512 creates (no double import); the 'Yaz' confirm text was not re-read this round (inconclusive UI part) |
| R1-S-12 | major · A re-upload of the same CSV in a new job plans 1,332 new requests and  | verified | **verified** `8db884fd` | R1-S-12@fresh: Job B (same CSV, before masking): meeting_requests {"create":0,"update":0,"unchanged":1340,"conflict":0} instructors {}; remembered items 8 |
| R1-S-13 | major · Comparing a term run with a one-week run declares the week run better  | verified | **verified** `8db884fd` | R1-S-13@desktop: {"headline":"#7, #8 ile karşılaştırıldı: 834 ders taşındı, 3 yalnız B'de, 7 yalnız A'da yerleşti; sert 100→100, yumuşak 83→82 (-1) · Kapsamlar farklı (A 1–19. haftalar, B 3. hafta); yalnız ortak 3. ha · R1-S-13@phone: {"headline":"#7, #8 ile karşılaştırıldı: 834 ders taşındı, 3 yalnız B'de, 7 yalnız A'da yerleşti; sert 100→100, yumuşak 83→82 (-1) · Kapsamlar farklı (A 1–19. haftalar, B 3. hafta); yalnız ortak 3. ha |
| R1-S-14 | major · Invigilation does not work with the default pool on the real Final dat | verified | **verified** `8db884fd` | smoke unchanged since round 2 (pool line, decimals) |
| R1-S-15 | major · The dashboard and the moderation header say nothing is planned while a | inconclusive | **verified** `8db884fd` | board-only snapshot (rec.board): one active Güz run (#3 GRID_IMPORT), dashboard 'Yayında: içe aktarılan pano #3', 'Derslik doluluğu %24' = heatmap 'Genel doluluk %24,1', moderation 'Yayında: #3 · taleplerin %72'si karşılandı', person rows mixed (not all 0) (1440 + 390) |
| R1-S-16 | major · On the phone the main planning controls are below 44 px or out of thum | reopened | **reopened** `8db884fd` | fixed: inspector 'Taşı…' / 'Kilitle' 175×44 in a sticky footer at y 736, 'Filtreler' trigger, move-sheet scope rows 350×44, publish capsule. Still: /classes filter chips 32 px, inspector 'Yerleşimi açıkla' 138×36 at 390 touch |
| R1-S-18 | major · Instructor names travel in review item ids to a viewer with content=fa | verified | **verified** `8db884fd` | R1-S-18@fresh: {"viewer":{"status":200,"content":false,"nIds":24,"nameLikeIds":0,"sampleIdShape":["x:2","x:x:94c991dc91277d5e","x:x:bf3x7bf14ec8f"],"post":403,"commit":403,"rows":403},"memory":{"n":8,"nameLike":0,"r |
| R1-S-21 | minor · Once the Studio scope fell back to H1 with '0 derslikte' and 'no succe | verified | **verified** `8db884fd` | Bahar rail 'Tüm dönem · 17 hafta', no '0 derslikte' |
| R1-S-22 | minor · The Studio says 'Tüm dönem · 2 hafta' for the 14-week Güz term | reopened | **verified** `8db884fd` | Studio Güz rail 'Tüm dönem · 14 hafta' agrees with '14 hafta boyunca 58 derslikte 632 ders planlıyorsunuz.' |
| R1-S-23 | minor · Several Turkish sentences are ungrammatical or unclear | verified | **verified** `8db884fd` | R1-S-23 run wording@desktop: hafta [] pct [] label undefined · R1-S-23 invigilation decimal@desktop: decimal-point readings [] · R1-S-23 run wording@phone: hafta [] pct [] label undefined · R1-S-23 invigilation decimal@phone: decimal-point readings [] |
| R1-S-24 | minor · English labels leak into the Turkish staff screens | reopened | **verified** `8db884fd` | planner forced move 403 carries message_tr; /moderation, inspector, runs show no English UI words |
| R1-S-25 | minor · A course code finds nobody in Kişiler, and the priority editor cannot  | verified | **verified** `8db884fd` | smoke: 'PSY 277' finds the instructor; priority trigger on the phone cards (8); unchanged since round 2 |
| R1-S-26 | minor · Search does not move focus to the class, the overlay sidebar hides its | inconclusive | **reopened** `8db884fd` | fixed at 1440 and 1024: 'Kenar çubuğunu göster/gizle' opens the sidebar, Enter in calendar-search filters to the one PHAR 240 chip and focuses it (aid 14631), no match → 'Bu filtrelerle gösterilecek ders yok.' with focus kept in the box. Still: the overlay sidebar covers its own toggle and Esc does not close it (1440, 1024); on the phone the search in the filters sheet does not filter the agenda (170 chips stay) and Enter focuses the first chip of the day (BB 691), no-match gives no message |
| R1-S-28 | minor · The same run shows different issue counts and exception lists by viewp | verified | **verified** `8db884fd` | R1-S-28 (half)@desktop: Sorun 398 @desktop; groups 0; digits false · R1-S-28@phone: Sorun 398 @phone vs 398 @other; 'Diğer notlar' groups 0; digit sequence false; exceptions: planlayıcının kilitlediği derslik sınıfa küçük ya da özelliği eksik (planlama listesindeki seçim korundu) · 1 |
| R1-S-30 | minor · Reset rows show '#98' instead of the person, the typed confirm accepts | verified | **verified** `8db884fd` | R1-S-30@desktop: {"cards":[],"rows":[],"typed":{"mismatch":"Yazılan kelime eşleşmiyor.","confirmDis":true,"autocap":"off"}} · R1-S-30@phone: {"cards":[],"rows":[],"typed":{"mismatch":"Yazılan kelime eşleşmiyor.","confirmDis":true,"autocap":"off"}} |
| R1-S-31 | minor · Encoding and delimiter are not reported, a PNG renamed .xlsx is not re | reopened | **verified** `8db884fd` | fresh stack: 'Son işler' lists the jobs after a reload, /onboarding/<id> opens the job (no 404), the format chip reads 'CSV · Windows-1254 · ;' |
| R1-S-32 | minor · 'Onaya gönder' accepts a press with '0 ders seçildi' and gives no feed | verified | **verified** `8db884fd` | R1-S-32@desktop: {"w":{"open":true,"count":"0 ders seçildi","disabled":true,"issue":"En az bir ders seçin."},"after":{"issue":"En az bir ders seçin.","toast":[],"posted":0}} · R1-S-32@phone: {"w":{"open":true,"count":"0 ders seçildi","disabled":true,"issue":"En az bir ders seçin."},"after":{"issue":"En az bir ders seçin.","toast":[],"posted":0}} |
| R1-S-33 | minor · Tab-bar badge order, a missing h1, small links and an unlabelled file  | verified | **verified** `8db884fd` | R1-S-33 learning h1@desktop: {"h1":1,"text":"Öğrenme belleği"} · R1-S-33 compare pickers@phone: [{"h":44,"tag":"SELECT"},{"h":44,"tag":"SELECT"}] · R1-S-33 learning h1@phone: {"h1":1,"text":"Öğrenme belleği"} · R1-S-33 dashboard link@phone: {"w":153,"h":44} · R1-S-33 tab-bar badge order@phone: ["Özet¦Özet","Talepler\n99+¦Talepler, 223 inceleme bekliyor","Oluştur¦Oluştur","Çizelge¦Çizelge","Diğer¦Diğer"] · R1-S-33 /onboarding@phone: {"ob":{"fileVisible":false,"fileSize":{"w":1,"h":1},"label":null},"inputsUnder16":[]} |
| R1-S-34 | minor · stack.sh mask left 7 instructor names with a surname fragment after th | verified | **verified** `8db884fd` | R1-S-34@fresh: stack.sh mask → masked 403 instructors and 1088 other cells (12111 names) ¦ left 0; verify → left 0 |
| R1-S-35 | suggestion · Some first loads are slow on the shared host (INCONCLUSIVE: load 5–13  | verified | **advisory** `8db884fd` | R1-S-35 /timetable load@desktop: 2831 ms to networkidle @desktop, load 2.85 · R1-S-35 /generate first load@desktop: 7992 ms · R1-S-35 /timetable load@phone: 2719 ms to networkidle @phone, load 2.18 · R1-S-35 /generate first load@phone: 5277 ms |
| R1-S-38 | suggestion · The term policy card lives only in Ayarlar › Çözücü and follows the si | open | **verified** `8db884fd` | R1-S-38@desktop: {"text":"Sığmayan dersler · 2026-BAHAR Bu dönemde kendi seçimi olmayan her çözüm bu kuralla çalışır. Bir çalıştırma kendi kuralını “Yeniden çöz” penceresinde seçebilir. Her ders sığmazsa Önce kilitlil · R1-S-38@phone: {"text":"Sığmayan dersler · 2026-BAHAR Bu dönemde kendi seçimi olmayan her çözüm bu kuralla çalışır. Bir çalıştırma kendi kuralını “Yeniden çöz” penceresinde seçebilir. Her ders sığmazsa Önce kilitlil |
### Round-2 ticket checks on the fresh stack (F-08 S07–S11, before masking)

| Ticket check | Result | What I saw |
|---|---|---|
| T-R2-19 | **reopened** | verified: Job A dry run == commit entity by entity (meeting_requests create 1,512 · unchanged 12 both, the CSV half recognised as 1,335 duplicates, no second copy); Job D (same CSV) create 0 · update 0 · unchanged 1,340. Fails: the cp1254 ';' export plans 1,333 updates (11.8 % unchanged), all weeks 1–16 → 1–14 (R3-S-04) |
| T-R2-20 | **verified** | fresh stack 1440: 'Son işler' after a reload (4 jobs), /onboarding/<id> opens the job, the drop zone is one <button> whose Enter opens the file chooser, accept lists .xlsx … image/*; the commit bar read '0 engelleyen' with 'Yaz' enabled after API decisions (fresh load; the live update without reload was not observed) |
| T-R2-21 | **verified** | commit with 3 undecided merges → 409 {code review_pending, count 3, message_tr 'Önce 3 inceleme kararı verilmeli.'}, no names in the body; PDF / DOCX rows read 'Okunmadı' / 'Doğrudan' with AI off (my first reading flagged the English `message` key and the pre-run upload chips) |
## New findings

### R3-S-01 (minor) F-04 S03 / F-01 S09 My bookings totals @1440 and @390
- Did: As the academician: one request, the admin rejects it with a reason; opened /my-bookings. Reproduced through the API (curl/R3-S-totals-rejected.txt).
- Happened: The totals line reads '0 etkin · bu dönem 1 · toplam 1' while Yaklaşan says 'Yaklaşan rezervasyonunuz yok' and GET /bookings/mine is []. GET /bookings/dashboard totals {all:1, session:1}: the rejected request is counted as a live booking (only CANCELLED is excluded).
- Expected: Rejected, withdrawn and expired requests are not bookings: 'bu dönem' and 'toplam' count live bookings (and, as T-R2-13 says, the pending ones) only, so the line matches what the page lists.
- Viewport: desktop, phone
- Evidence: `shots/R3-F01-S09-bookings-desktop.png`, `curl/R3-S-totals-rejected.txt`
- Seen before as: T-R2-13 residue (R2-S-10)
- File hints: smartsched/backend/app/services/bookings.py:1817 (rows = status != CANCELLED → also exclude REJECTED / WITHDRAWN / EXPIRED)

### R3-S-02 (minor) F-03 S07 focus after the stale-result refusal @1440 and @390
- Did: Searched D1 P11–P12 for 42 with 'Bilgisayar laboratuvarı'; the admin booked B 207 P11 through the API; pressed 'B 207 rezerve et' on the stale card.
- Happened: The refusal is right ('Bu derslik az önce doldu. Liste yenilendi.', no sheet, no booking, B 207 leaves the list), but document.activeElement is <body> afterwards: the pressed button disappeared with the refreshed list and nothing took focus.
- Expected: Focus goes to the result summary or the next card (A-21, motion T4).
- Viewport: desktop, phone
- Evidence: `shots/F03-S07-desktop.png`, `logs/f03-desktop.json`
- Seen before as: follows T-R2-14
- File hints: smartsched/frontend/src/components/findroom/find-room-view.tsx (stale refusal path: focusAfter the fr-summary)

### R3-S-03 (minor) F-02 S09/S10 audit log after a series cancel @1440 and @390
- Did: Cancelled a weekly series 'Bu ve sonrakiler' (2 dates), opened /admin/audit.
- Happened: Beside the two 'Rezervasyon iptal edildi #3 / #5' rows (one per booking, T-R2-17 e) the parent event reads 'Booking series iptal edildi #1' in the Turkish UI.
- Expected: A Turkish entity label ('Tekrarlayan rezervasyon iptal edildi #1' or 'Seri #1 iptal edildi').
- Viewport: desktop, phone
- Evidence: `shots/F02-S10-desktop.png`, `logs/f02-desktop.json`
- Seen before as: new since T-R2-17(e) added the booking_series parent event
- File hints: smartsched/frontend/src/components/audit/audit-model.ts (entity label for booking_series), messages/tr.json wave1.audit.*

### R3-S-04 (major) F-08 S11 the Turkish Excel CSV re-upload (T-R2-19 check) @1440 fresh stack
- Did: Fresh stack, before masking: Job A (planning xlsx + its English CSV) committed; Job C = bahar_listesi_noktali_virgul.csv (cp1254, ';', fast path), its 3 merge items accepted, dry run against 2026-BAHAR (twice, two fresh databases).
- Happened: meeting_requests {create 0, update 1,333, unchanged 179}: 11.8 % unchanged. Every update is the weeks field [1…16] → [1…14] (456 of 461 sampled rows; 2 rows → [4]); sections 99.9 % unchanged. The commit bar groups the English CSV as 'BAHAR · normal dönem · 16 hafta' and the cp1254 export as '14 hafta', so the same list imported in two formats disagrees on the term length.
- Expected: T-R2-19 check: Job C (cp1254) ≥ 99 % unchanged; one week count per term whatever the file.
- Viewport: desktop (API + /onboarding/<id>)
- Evidence: `curl/F08e-jobC-dry.json`, `curl/F08e-jobC-dry-full.json`, `logs/f08e.json`, `logs/f08c.json`
- Seen before as: reopens T-R2-19 part (R2-M-06); the dry run == commit and same-CSV 0/0 parts verified
- File hints: smartsched/backend/app/council/commit.py (Writer.fields_for_existing weeks; term.week_count vs the planner group's guess), council/dryrun.py

### R3-S-05 (minor) F-02 S08 / R2-S-22 cancel from the My bookings row sheet @1440
- Did: Opened a one-period booking from its /my-bookings row (date button), 'İptal et', reason 'Oda bakımda', confirmed.
- Happened: Toast '1 rezervasyon iptal edildi · Gerekçe: Oda bakımda' (right), but document.activeElement is <body> after the dialog closes (seen once at 1440; on the phone focus returned to the row's room button).
- Expected: Focus returns to the row or the list heading after the cancel (F-04 S10, U-07).
- Viewport: desktop
- Evidence: `logs/r3-desktop.json`, `shots/R2-S-22-desktop.png`
- Seen before as: new
- File hints: smartsched/frontend/src/components/bookings/booking-detail-sheet.tsx (CancelDialog focusAfter when opened from my-bookings-view)

### R3-S-06 (minor) MOBILE M-05 /settings?tab=solver @390
- Did: As admin on the phone, Ayarlar › Çözücü.
- Happened: 'save-solver' sits at y 911–955 at scroll 0 (below the fold, not free) and scrolls with the content (511 at 400, 340 at the end); the sweeper-3 capsule covers the /admin/* routes, not this tab.
- Expected: The tab's save in a sticky capsule in the bottom 40 % (MOBILE §3 /settings row).
- Viewport: phone
- Evidence: `logs/r3-phone.json`, `shots/R2-S-08-settings-solver-phone.png`
- Seen before as: sweeper-3 item 'admin page actions as a phone capsule' (admin routes only)
- File hints: smartsched/frontend/src/components/settings/settings-view.tsx (SolverForm save placement on phones)

## Step table

Result legend: PASS · PASS* (device behaviour right, my assert drifted; the note says what was seen) · FAIL (tied to an id) · INCONCLUSIVE · NOT RUN (harness) · BLOCKED (not built) · SKIP. Evidence paths are relative to the evidence root.

| Flow | Step | Viewport | Result | Evidence | Issue / note |
|---|---|---|---|---|---|
| F-01 | F-01 S01 | desktop | PASS | `shots/F01-S01-desktop.png` | – |
| F-01 | F-01 S01 | phone | PASS | `shots/F01-S01-phone.png` | – |
| F-01 | F-01 S02 | desktop | PASS | `shots/F01-S02-desktop.png`, `curl/F01-S02-check.txt` | – |
| F-01 | F-01 S02 | phone | PASS | `shots/F01-S02-phone.png`, `curl/F01-S02-check.txt` | – |
| F-01 | F-01 S03 | desktop | PASS* | `shots/F01-S03-desktop.png`, `curl/F01-S03-mine.txt` | 202, toast 'C 303 için talebiniz gönderildi. Onaycı karar verince size bildirilecek.', busy 'Gönderiliyor…' aria-busy, approver mail; my assert counted an earlier request in /approvals/mine |
| F-01 | F-01 S03 | phone | PASS* | `shots/F01-S03-phone.png`, `curl/F01-S03-mine.txt` | as desktop; the slot list has no grid legend (my assert expected one) |
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
| F-01 | F-01 S09 | desktop | PASS* | `shots/F01-S09-desktop.png` | re-checked with r3-final: the bell opens /my-bookings?request=<id> expanded with 'Gerekçe: Oda uygun değil: Bu saatte bölüm sınavı var.', 'Karar veren: Administrator' and the timeline, focus on the row (from /bookings and while already on /my-bookings); my first selector read the row header only |
| F-01 | F-01 S09 | phone | PASS* | `shots/F01-S09-phone.png` | as desktop (r3-final phone) |
| F-01 | F-01 S10 | desktop | PASS | `shots/F01-S10-desktop.png`, `curl/F01-S10-withdraw-twice.txt` | – |
| F-01 | F-01 S10 | phone | PASS | `shots/F01-S10-phone.png`, `curl/F01-S10-withdraw-twice.txt` | – |
| F-01 | F-01 S10 admin | desktop | PASS | `shots/F01-S10-admin-desktop.png` | – |
| F-01 | F-01 S10 admin | phone | PASS | `shots/F01-S10-admin-phone.png` | – |
| F-01 | F-01 S11 | desktop | PASS | `shots/F01-S11-desktop.png`, `curl/F01-S11-prefs.txt` | – |
| F-01 | F-01 S11 | phone | PASS* | `shots/F01-S11-phone.png`, `curl/F01-S11-prefs.txt` | switches 44×44 in cards, toast 'Bildirim tercihi kaydedildi.', no mail after e-mail off; my size check also measured the 1×1 sr-only labels |
| F-01 | F-01 S12 | desktop | PASS | `shots/F01-S12-desktop.png`, `curl/F01-S12-planner.txt` | – |
| F-01 | F-01 S12 | phone | PASS | `shots/F01-S12-phone.png`, `curl/F01-S12-planner.txt` | – |
| F-01 | F-01 S14 | desktop | PASS | `shots/F01-S14-desktop.png` | – |
| F-01 | F-01 S14 | phone | PASS | `shots/F01-S14-phone.png` | – |
| F-01 | F-01 S15 | desktop | PASS | `shots/F01-S15-desktop.png` | – |
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
| F-02 | F-02 S04 | desktop | PASS | `shots/F02-S04-desktop.png`, `curl/F02-S04-recurring.json` | T-R2-09: 'Atla' on 05.11 and 'Yerine geç' on 12.11 survive 'Yeniden denetle' (choices identical before/after), 201, toast '4 tarih rezerve edildi, 1 tarih atlandı', D3 free, holiday unavailable, replaced booking CANCELLED 'replaced_by_series:1' shown as 'Seri #1 ile değiştirildi'; my select-based assert found radios |
| F-02 | F-02 S04 | phone | PASS | `shots/F02-S04-phone.png`, `curl/F02-S04-recurring.json` | as desktop; focus after submit on the slot list heading |
| F-02 | F-02 S05 | desktop | PASS | `shots/F02-S05-desktop.png` | – |
| F-02 | F-02 S05 | phone | PASS | `shots/F02-S05-phone.png` | – |
| F-02 | F-02 S06 | desktop | NOT RUN | – | harness: the custom end date is a text DateField, my script looked for input[type=date]; the planner holds book_recur.create on this stack |
| F-02 | F-02 S06 | phone | NOT RUN | – | harness: as desktop |
| F-02 | F-02 S07 | desktop | PASS | `shots/F02-S07-desktop.png` | – |
| F-02 | F-02 S07 | phone | PASS | `shots/F02-S07-phone.png` | – |
| F-02 | F-02 S08 | desktop | PASS | `shots/F02-S08-desktop.png` | R3-S-05; toast '1 rezervasyon iptal edildi · Gerekçe: Oda bakımda', 1 id, focus on the cell; the scope is a select ('Bu tarih / Bu ve sonrakiler / Tüm seri') without counts (R2-S-18 / FLE-010) |
| F-02 | F-02 S08 | phone | PASS | `shots/F02-S08-phone.png` | R3-S-05; from the My bookings row; the string 'Bu rezervasyon iptal edildi' my reader caught is the sheet's own notice, the toast is '1 rezervasyon iptal edildi · Gerekçe: …' (r3-toast) |
| F-02 | F-02 S09 | desktop | PASS | `shots/F02-S09-desktop.png` | cancelled [3,5]; toast '2 rezervasyon iptal edildi · Gerekçe: Program değişti' (phone run) — the desktop reading was the sheet notice |
| F-02 | F-02 S09 | phone | PASS | `shots/F02-S09-phone.png` | toast '2 rezervasyon iptal edildi · Gerekçe: Program değişti' |
| F-02 | F-02 S09 audit rows | desktop | PASS* | `curl/F02-S09-audit.json` | T-R2-17(e): two 'Rezervasyon iptal edildi' rows (one per booking) under one parent event; the parent row reads 'Booking series iptal edildi #1' (R3-S-03) |
| F-02 | F-02 S09 audit rows | phone | PASS* | `curl/F02-S09-audit.json` | as desktop |
| F-02 | F-02 S10 | desktop | PASS | `shots/F02-S10-desktop.png` | R3-S-03; T-R2-31: undo 200, row reads '… geri alındı', focus on the row LI (audit-event-160); my assert read a different date's booking |
| F-02 | F-02 S10 | phone | PASS | `shots/F02-S10-phone.png` | R3-S-03; as desktop, 'Geri al' 44 px in the card |
| F-02 | F-02 S11 | desktop | PASS | `shots/F02-S11-desktop.png` | – |
| F-02 | F-02 S11 | phone | PASS | `shots/F02-S11-phone.png` | – |
| F-02 | F-02 S12 | desktop | PASS | `shots/F02-S12-desktop.png`, `curl/F02-S12-past.txt` | – |
| F-02 | F-02 S12 | phone | PASS | `shots/F02-S12-phone.png`, `curl/F02-S12-past.txt` | – |
| F-03 | F-03 S01 | desktop | PASS | `shots/F03-S01-desktop.png` | – |
| F-03 | F-03 S01 | phone | PASS | `shots/F03-S01-phone.png` | – |
| F-03 | F-03 S02 | desktop | PASS | `shots/F03-S02-desktop.png`, `curl/F03-oracle.json` | – |
| F-03 | F-03 S02 | phone | PASS | `shots/F03-S02-phone.png`, `curl/F03-oracle.json` | – |
| F-03 | F-03 S03 | desktop | PASS | `shots/F03-S03-desktop.png` | – |
| F-03 | F-03 S03 | phone | PASS | `shots/F03-S03-phone.png` | – |
| F-03 | F-03 S04 | desktop | PASS* | `shots/F03-S04-desktop.png` | 'Metinle eşleşen derslik yok: “yarın 14:00 60 kişi”.' with 'Metni temizle', the chips keep the text (same as round 2) |
| F-03 | F-03 S04 | phone | NOT RUN | – | harness: fr-text lives in the filters sheet on the phone (T-R2-35); S03 passed through the sheet |
| F-03 | F-03 S05 | desktop | PASS | `shots/F03-S05-desktop.png` | – |
| F-03 | F-03 S05 | phone | PASS | `shots/F03-S05-phone.png` | – |
| F-03 | F-03 S06 | desktop | PASS | `shots/F03-S06-desktop.png`, `curl/F03-S06-mine.txt` | – |
| F-03 | F-03 S06 | phone | PASS* | `shots/F03-S06-phone.png`, `curl/F03-S06-mine.txt` | 'A 105 rezerve et' 110×44, sheet 'A 105 · P11–P12', '2 ders saatini rezerve et', both booked, focus on fr-summary; toast not sampled in time |
| F-03 | F-03 S06 span-as-one-row | desktop | PASS* | – | the API keeps one row per period by design; the UI shows one row per span (F-04 S03 'C 303 · P7–P8 (13:30–15:00)') |
| F-03 | F-03 S06 span-as-one-row | phone | PASS* | – | as desktop |
| F-03 | F-03 S07 | desktop | PASS | `shots/F03-S07-desktop.png` | R3-S-02; T-R2-14: toast 'Bu derslik az önce doldu. Liste yenilendi.', no sheet, no POST, B 207 gone, P12 still free; focus falls to <body> afterwards (R3-S-02) |
| F-03 | F-03 S07 | phone | PASS | `shots/F03-S07-phone.png` | R3-S-02; as desktop (R3-S-02 for the focus) |
| F-03 | F-03 S08 | desktop | PASS | `shots/F03-S08-desktop.png` | – |
| F-03 | F-03 S08 | phone | PASS | `shots/F03-S08-phone.png` | – |
| F-03 | F-03 S09 | desktop | PASS | `shots/F03-S09-desktop.png` | – |
| F-03 | F-03 S09 | phone | PASS | `shots/F03-S09-phone.png` | – |
| F-03 | F-03 S10 | desktop | PASS | `shots/F03-S10-desktop.png` | – |
| F-03 | F-03 S10 | phone | PASS | `shots/F03-S10-phone.png` | – |
| F-03 | F-03 S11 | desktop | PASS | `shots/F03-S11-desktop.png` | – |
| F-03 | F-03 S11 | phone | PASS* | `shots/F03-S11-phone.png` | 'A 105 için talep et' → request sent, approver mail arrived; toast not sampled in time |
| F-03 | F-03 S12 | desktop | BLOCKED | – | P19-T1 'Derslerim' make-up shortcut not built |
| F-03 | F-03 S12 | phone | BLOCKED | – | P19-T1 'Derslerim' make-up shortcut not built |
| F-03 | F-03 TR scan /find-room | desktop | PASS | – | – |
| F-03 | F-03 TR scan /find-room | phone | PASS | – | – |
| F-04 | F-04 S01 | desktop | PASS | `shots/F04-S01-desktop.png`, `curl/F04-S01-tokens-off.txt` | – |
| F-04 | F-04 S01 | phone | PASS | `shots/F04-S01-phone.png`, `curl/F04-S01-tokens-off.txt` | – |
| F-04 | F-04 S02 | desktop | PASS | `shots/F04-S02-desktop.png`, `curl/F04-S02-settings.txt` | – |
| F-04 | F-04 S02 | phone | PASS | `shots/F04-S02-phone.png`, `curl/F04-S02-settings.txt` | – |
| F-04 | F-04 S03 | desktop | PASS* | `shots/F04-S03-desktop.png`, `curl/F04-S03-mine.txt` | R3-S-01; one row 'C 303 · P7–P8 (13:30–15:00)', tabs, cancelled reason; totals '1 etkin · bu dönem 3 · toplam 3' (etkin = own future single bookings, the others count live rows incl. the pending request) — my assert compared etkin with every BOOKED row |
| F-04 | F-04 S03 | phone | PASS* | `shots/F04-S03-phone.png`, `curl/F04-S03-mine.txt` | R3-S-01; as desktop; tabs 117×44, checkbox labels 44×44 |
| F-04 | F-04 S03 span-as-one-row | desktop | PASS | – | one row 'C 303 · P7–P8 (13:30–15:00)' with per-period chips |
| F-04 | F-04 S03 span-as-one-row | phone | PASS | – | as desktop |
| F-04 | F-04 S04 | desktop | PASS* | `shots/F04-S04-desktop.png` | 201, URL textarea wraps (no overflow), 'Kopyala' / 'webcal kopyala', Google/Outlook/Apple; my text capture was cut by the room picker. Consent step: verified separately (r3-final) |
| F-04 | F-04 S04 | phone | PASS | `shots/F04-S04-phone.png` | copy 110×44 / 156×44, add links 44 px, URL wraps |
| F-04 | F-04 S05 | desktop | PASS | `shots/F04-S05-desktop.png` | – |
| F-04 | F-04 S05 | phone | PASS* | `shots/F04-S05-phone.png` | hrefs right; no clipboard permission in the touch context so no toast (flow: desktop-only toast); a refused write toasts 'Kopyalanamadı: bağlantıyı alandan seçin' and focuses the field |
| F-04 | F-04 S05 clipboard-denied | desktop | PASS | – | – |
| F-04 | F-04 S05 clipboard-denied | phone | PASS | – | – |
| F-04 | F-04 S06 | desktop | PASS | `curl/F04-S06-mine.ics`, `curl/F04-S06-mine-head.txt` | – |
| F-04 | F-04 S06 | phone | PASS | `curl/F04-S06-mine.ics`, `curl/F04-S06-mine-head.txt` | – |
| F-04 | F-04 S06 span-as-one-VEVENT | desktop | INCONCLUSIVE | `curl/F04-S06-mine.ics` | the API-made span had no note, so no 'Telafi dersi' VEVENT to count |
| F-04 | F-04 S06 span-as-one-VEVENT | phone | INCONCLUSIVE | `curl/F04-S06-mine.ics` | as desktop |
| F-04 | F-04 S07 | desktop | PASS | `curl/F04-S07-mine.ics` | – |
| F-04 | F-04 S07 | phone | PASS | `curl/F04-S07-mine.ics` | – |
| F-04 | F-04 S08 | desktop | PASS | `shots/F04-S08-desktop.png`, `curl/F04-S08-new.ics` | – |
| F-04 | F-04 S08 | phone | PASS | `shots/F04-S08-phone.png`, `curl/F04-S08-new.ics` | – |
| F-04 | F-04 S09 | desktop | PASS* | `shots/F04-S09-desktop.png`, `curl/F04-S09-room.ics` | no owned rooms / department for this staff account: only the personal feed (as round 2) |
| F-04 | F-04 S09 | phone | PASS* | `shots/F04-S09-phone.png`, `curl/F04-S09-room.ics` | as desktop |
| F-04 | F-04 S09 Derslerim feed | desktop | BLOCKED | – | P19-T4 personal class feed not built |
| F-04 | F-04 S09 Derslerim feed | phone | BLOCKED | – | P19-T4 personal class feed not built |
| F-04 | F-04 S10 | desktop | PASS | `shots/F04-S10-desktop.png`, `curl/F04-S10-mine.ics` | T-R2-16: toast '1 rezervasyon iptal edildi' (no '0 olduğu gibi kaldı'), focus on a row button, the event left the feed |
| F-04 | F-04 S10 | phone | PASS | `shots/F04-S10-phone.png`, `curl/F04-S10-mine.ics` | bulk capsule 'cancel-selected' 712–756 free at 0/400/end, same toast |
| F-04 | F-04 S11 | desktop | PASS | `shots/F04-S11-desktop.png` | – |
| F-04 | F-04 S11 | phone | PASS | `shots/F04-S11-phone.png` | – |
| F-04 | F-04 S12 | desktop | SKIP | `shots/F04-S12-desktop.png` | no OAuth client; {"present":false,"btns":[]} |
| F-04 | F-04 S12 | phone | SKIP | `shots/F04-S12-phone.png` | no OAuth client; {"present":false,"btns":[]} |
| F-04 | F-04 TR scan /my-bookings(sync) | desktop | PASS | – | – |
| F-04 | F-04 TR scan /my-bookings(sync) | phone | PASS | – | – |
| F-12 | F-12 S04 logout | desktop | PASS | `shots/F12-S04-desktop.png` | – |
| F-12 | F-12 S04 logout | phone | PASS | `shots/F12-S04-phone.png` | – |
| F-12 | F-12 S05 | desktop | PASS* | `shots/F12-S05-desktop.png`, `shots/F12-S05-second-desktop.png` | field messages 'Şu anki parola yanlış.', 'İki parola aynı değil.', 'En az 8 karakter kullanın.'; 200, stays on /profile signed in; old 401 / new 200; second session → /login with 'Oturumunuzun süresi doldu…'; no sync toast. Wording differs from the flow file (trivial drift) |
| F-12 | F-12 S05 | phone | PASS* | `shots/F12-S05-phone.png`, `shots/F12-S05-second-phone.png` | as desktop |
| F-12 | F-12 S05 no sync toast | desktop | PASS | – | – |
| F-12 | F-12 S05 no sync toast | phone | PASS | – | – |
| F-12 | F-12 S06 | desktop | PASS | `shots/F12-S06-desktop.png` | – |
| F-12 | F-12 S06 | phone | PASS | `shots/F12-S06-phone.png` | – |
| F-12 | F-12 S07 | desktop | PASS | `shots/F12-S07-desktop.png` | – |
| F-12 | F-12 S07 | phone | PASS | `shots/F12-S07-phone.png` | – |
| F-12 | F-12 S07 short-code API | desktop | PASS | `curl/F12-S07-short-code.txt` | – |
| F-12 | F-12 S07 short-code API | phone | PASS | `curl/F12-S07-short-code.txt` | – |
| F-12 | F-12 S09 | desktop | NOT RUN | – | 'Bağlantıyı dene' is disabled until a test user and password are typed (F-12 S09 note) |
| F-12 | F-12 S09 | phone | NOT RUN | – | as desktop |
| F-12 | F-12 S10 | phone | PASS | `shots/F12-S10-phone.png` | – |
| F-12 | F-12 S11 config guards | desktop | PASS | `curl/F12-SSO.json` | – |
| F-12 | F-12 S11 config guards | phone | PASS | `curl/F12-SSO.json` | – |
| F-12 | F-12 S12 login page SSO | desktop | PASS* | `shots/F12-S12-sso-desktop.png` | 'Microsoft ile giriş yap' 44 px, hints in Turkish, disclosure 'Kullanıcı adı ve parolayla giriş yap', no sign-up (my brand assert drifted) |
| F-12 | F-12 S12 login page SSO | phone | PASS* | `shots/F12-S12-sso-phone.png` | as desktop, link 48 px |
| F-12 | F-12 S13 start (SSO disabled) | api | PASS | – | – |
| F-12 | F-12 S13 start redirect | desktop | PASS | `curl/F12-SSO.json` | – |
| F-12 | F-12 S13 start redirect | phone | PASS | `curl/F12-SSO.json` | – |
| F-12 | F-12 S14 callback refusals | desktop | PASS | – | – |
| F-12 | F-12 S14 callback refusals | phone | PASS | – | – |
| F-12 | F-12 S14 forged callback | api | PASS | – | – |
| F-12 | F-12 S15 exchange | api | PASS* | – | random ticket → 422 pydantic text (FLE-014, admin-facing) |
| F-12 | F-12 S16 invites | desktop | PASS* | – | invite 201 / 30 days, bind 201, delete 204, 'Bu davet artık geçerli değil.…'; the limited-admin part belongs to F-11 |
| F-12 | F-12 S16 invites | phone | PASS* | – | as desktop |
| F-12 | F-12 S17 break-glass | desktop | PASS* | – | OIDC-only hides the fields, ?method=local shows them, staff 401, admin 200, last-admin 409 (English detail 'cannot demote or deactivate the last active admin', admin-only API) |
| F-12 | F-12 S17 break-glass | phone | PASS* | – | as desktop |
| F-12 | F-12 S18 | desktop | BLOCKED | – | no tenant credentials |
| F-12 | F-12 S18 | phone | BLOCKED | – | no tenant credentials |
| F-12 | F-12 user menu rows@phone | phone | PASS | `shots/F12-usermenu-phone.png` | – |
| F-13 | F-13 A01 | desktop | PASS | `shots/F13-A01-_bookings-desktop.png`, `shots/F13-A01-_my-bookings-desktop.png` | – |
| F-13 | F-13 A01 | phone | PASS | `shots/F13-A01-_bookings-phone.png`, `shots/F13-A01-_my-bookings-phone.png` | – |
| F-13 | F-13 A02 | desktop | PASS* | `shots/F13-A02-desktop.png` | 'Saved', everything English, chips 'Block A…'; the picker has 3 entries (owner decision R2-A-19) |
| F-13 | F-13 A02 | phone | PASS* | `shots/F13-A02-phone.png` | as desktop |
| F-13 | F-13 A03 | desktop | PASS | `shots/F13-A03-desktop.png` | – |
| F-13 | F-13 A03 | phone | PASS | `shots/F13-A03-phone.png` | – |
| F-13 | F-13 A04 | desktop | PASS | `shots/F13-A04-desktop.png` | – |
| F-13 | F-13 A04 | phone | PASS | `shots/F13-A04-phone.png` | – |
| F-13 | F-13 B01 | desktop | PASS | `shots/F13-B01-desktop.png` | T-R2-07: sheet translate none / opacity 1 / nothing moving; bell transform is the identity matrix |
| F-13 | F-13 B01 | phone | PASS | `shots/F13-B01-phone.png` | – |
| F-13 | F-13 B02 | desktop | PASS | `shots/F13-B02-desktop.png` | – |
| F-13 | F-13 B02 | phone | PASS | `shots/F13-B02-phone.png` | – |
| F-13 | F-13 B03 | desktop | PASS | `shots/F13-B03-desktop.png` | – |
| F-13 | F-13 B03 | phone | PASS | `shots/F13-B03-phone.png` | – |
| F-13 | F-13 B04 | desktop | INCONCLUSIVE | – | load 5.01; worst LoAF 150 ms; overCeiling []; {"sheetOpen":{"dropped":4,"worst":133},"submit":{"dropped":1,"worst":150},"search":{"dropped":6,"worst":90},"expand":{"dropped":15,"wo |
| F-13 | F-13 B04 | phone | PASS | – | – |
| F-13 | F-13 C01 | desktop | PASS | `shots/F13-C01-desktop.png` | – |
| F-13 | F-13 C01 | tablet | PASS | `shots/F13-C01-tablet.png` | – |
| F-13 | F-13 C02 admin | desktop | PASS | `shots/F13-C02-admin-desktop.png` | T-R2-12: j approval-2→approval-4, k back, Enter → drawer title (H2), 'a' → 'Onaylandı: A 101.'; reject Enter on the disabled confirm shows 'Gerekçeyi yazın; yalnız boşluk sayılmaz.' and posts nothing |
| F-13 | F-13 C02 admin | tablet | PASS | `shots/F13-C02-admin-tablet.png` | as desktop ('Onaylandı: C 205.') |
| F-13 | F-13 C02 staff | desktop | PASS* | `shots/F13-C02-desktop.png` | span by keyboard '2 ders saati seçildi, 08:30–10:00, C 201.', Enter → sheet, '2 ders saati için talep et' 202, Esc from textarea and select closes in one press back to the cell; my script landed on C 201 P1 instead of C 303 P7 |
| F-13 | F-13 C02 staff | tablet | PASS* | `shots/F13-C02-tablet.png` | as desktop |
| F-13 | F-13 C02 withdraw | desktop | PASS | – | – |
| F-13 | F-13 C02 withdraw | tablet | PASS | – | – |
| F-13 | F-13 C03 | desktop | PASS* | `shots/F13-C03-desktop.png` | date picker focus on the day, per-date '22.10.2026 için işlem' changes the polite summary 9→8, cancel 200 with focus on the cell; the scope is a select (R2-S-20) |
| F-13 | F-13 C03 | tablet | PASS* | `shots/F13-C03-tablet.png` | as desktop |
| F-13 | F-13 C04 | desktop | INCONCLUSIVE | `shots/F13-C04-desktop.png` | tab order date, time, headcount, chips, 'Arama metni', 'Ara'; my visual-order heuristic flags the chip row (as round 2) |
| F-13 | F-13 C04 | tablet | PASS | `shots/F13-C04-tablet.png` | – |
| F-13 | F-13 C05 | desktop | PASS | `shots/F13-C05-desktop.png` | re-checked with r3-reset-kb: Tab stays in the reset confirm (aria-modal), Enter 201, toast 'Yeni bağlantılar oluşturuldu; eski abonelikler artık güncellenmez.', focus on the new link; my first run matched 'Sıfırla' case-sensitively |
| F-13 | F-13 C05 | tablet | PASS | `shots/F13-C05-tablet.png` | as desktop (768 keyboard) |
| F-13 | F-13 C05 reset trap | desktop | PASS | – | – |
| F-13 | F-13 C05 reset trap | tablet | PASS | – | – |
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
| MOBILE | M-01@/my-bookings(sync-sheet) | phone | PASS | `logs/mobile-sync-sheet.json` | – |
| MOBILE | M-01@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-01@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-01@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-02@/admin/audit(admin-audit) | phone | PASS | `shots/R2-S-08-admin-audit-phone.png` | – |
| MOBILE | M-02@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-02@/admin/settings(admin-settings) | phone | PASS | `shots/R2-S-08-admin-settings-phone.png` | – |
| MOBILE | M-02@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-02@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-02@/approvals(reject) | phone | PASS | – | – |
| MOBILE | M-02@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-02@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-02@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-02@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-02@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-02@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-02@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-02@/find-room(results, R2-S-08) | phone | PASS | `shots/R2-S-08-fr-results-phone.png` | – |
| MOBILE | M-02@/login(login) | phone | PASS | `logs/mobile-login.json` | – |
| MOBILE | M-02@/login/change-password | phone | PASS | – | – |
| MOBILE | M-02@/login/change-password(change-password) | phone | PASS | `logs/mobile-change-password.json` | – |
| MOBILE | M-02@/my-bookings(consent dialog) | phone | PASS | – | – |
| MOBILE | M-02@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-02@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-02@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-02@/my-bookings(sync-sheet) | phone | PASS | `logs/mobile-sync-sheet.json` | – |
| MOBILE | M-02@/profile#notifications(profile-notifications) | phone | PASS | `shots/R2-S-08-profile-notifications-phone.png` | – |
| MOBILE | M-02@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-02@/reset-password | phone | PASS | `shots/R2-S-08-reset-phone.png` | – |
| MOBILE | M-02@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-02@/settings(settings-integrations) | phone | FAIL | `logs/mobile-settings-integrations.json` | R2-S-08 residue: 'webhook-new' 130×36 (the r3 battery reading of the same route passed: scroll position) |
| MOBILE | M-02@/settings?tab=integrations(settings-integrations) | phone | PASS | `shots/R2-S-08-settings-integrations-phone.png` | – |
| MOBILE | M-02@/settings?tab=solver(settings-solver) | phone | PASS | `shots/R2-S-08-settings-solver-phone.png` | – |
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
| MOBILE | M-03@/my-bookings(sync-sheet) | phone | PASS | `logs/mobile-sync-sheet.json` | – |
| MOBILE | M-03@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-03@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-03@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-04@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-04@/approvals(reject) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-04@/bookings(cancel all) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(cancel future) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(cancel one) | phone | PASS | – | – |
| MOBILE | M-04@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-04@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-04@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-04@/my-bookings(withdraw) | phone | PASS | – | – |
| MOBILE | M-04@bell | phone | PASS | – | – |
| MOBILE | M-05@/admin/settings(admin-settings) | phone | NOT RUN | – | harness: as above |
| MOBILE | M-05@/admin/settings(settings) | phone | NOT RUN | `logs/mobile-settings.json` | harness: no element with the primary testid on this build (sweeper 3 moved the save into a capsule); admin route, outside the staff flows |
| MOBILE | M-05@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-05@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-05@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-05@/find-room(book-from-results) | phone | PASS | `logs/mobile-book-from-results.json` | – |
| MOBILE | M-05@/find-room(filters) | phone | PASS | `logs/mobile-filters.json` | – |
| MOBILE | M-05@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-05@/find-room(results) | phone | PASS* | `logs/mobile-results.json` | this reading followed the M-13 landscape rotation; two portrait re-measurements (r3 battery and probe-fr) read the 'Ara' capsule at y 714–758 at scroll 0/400/end, free |
| MOBILE | M-05@/login(login) | phone | PASS* | `logs/mobile-login.json` | centred card, submit at 355–403 visible with the keyboard (MOBILE §3 /login rule) |
| MOBILE | M-05@/login/change-password(change-password) | phone | PASS* | `logs/mobile-change-password.json` | 'Kaydet ve devam et' at y 577–625 (bottom 40 %); elementFromPoint hits the form because the button is disabled until the fields are filled |
| MOBILE | M-05@/my-bookings(selection) | phone | PASS | – | – |
| MOBILE | M-05@/my-bookings(sync-sheet) | phone | PASS* | `logs/mobile-sync-sheet.json` | the sync card is its own section below the list (same reading as round 2) |
| MOBILE | M-05@/profile#notifications(profile-notifications) | phone | PASS | – | – |
| MOBILE | M-05@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-05@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-05@/settings?tab=solver(settings-solver) | phone | FAIL | – | R3-S-06; R3-S-06 |
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
| MOBILE | M-07@/my-bookings(sync-sheet) | phone | PASS | `logs/mobile-sync-sheet.json` | – |
| MOBILE | M-07@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-07@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-07@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-08@/bookings | phone | PASS | – | – |
| MOBILE | M-09@/admin/audit(admin-audit) | phone | PASS | – | – |
| MOBILE | M-09@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-09@/admin/settings(admin-settings) | phone | PASS | – | – |
| MOBILE | M-09@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-09@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-09@/bookings(staff) | phone | PASS | `shots/R2-S-07-tabbar-staff-phone.png` | – |
| MOBILE | M-09@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-09@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-09@/login/change-password(change-password) | phone | PASS* | `logs/mobile-change-password.json` | no tab bar on auth pages (by design) |
| MOBILE | M-09@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-09@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-09@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-09@/my-bookings(sync-sheet) | phone | PASS | `logs/mobile-sync-sheet.json` | – |
| MOBILE | M-09@/profile#notifications(profile-notifications) | phone | PASS | – | – |
| MOBILE | M-09@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-09@/requests(admin 99+) | phone | PASS | `shots/R2-S-07-tabbar-admin-phone.png` | – |
| MOBILE | M-09@/reset-password(reset-password) | phone | PASS* | `logs/mobile-reset-password.json` | no tab bar on auth pages |
| MOBILE | M-09@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-09@/settings?tab=integrations(settings-integrations) | phone | PASS | – | – |
| MOBILE | M-09@/settings?tab=solver(settings-solver) | phone | PASS | – | – |
| MOBILE | M-10@/approvals(approvals) | phone | PASS | `logs/mobile-approvals.json` | – |
| MOBILE | M-10@/bookings(book-sheet) | phone | PASS | `logs/mobile-book-sheet.json` | – |
| MOBILE | M-10@/bookings(recurring) | phone | PASS | `logs/mobile-recurring.json` | – |
| MOBILE | M-10@/find-room | phone | PASS* | – | start/end and P1/P2 pairs at 159 px each (allowed pair exception, MOBILE M-10) |
| MOBILE | M-10@/find-room(book-from-results) | phone | PASS* | `logs/mobile-book-from-results.json` | pair exception |
| MOBILE | M-10@/find-room(filters) | phone | PASS* | `logs/mobile-filters.json` | pair exception |
| MOBILE | M-11@/admin/audit(admin-audit) | phone | PASS | – | – |
| MOBILE | M-11@/admin/audit(audit) | phone | PASS | `logs/mobile-audit.json` | – |
| MOBILE | M-11@/admin/settings(admin-settings) | phone | PASS | – | – |
| MOBILE | M-11@/admin/settings(settings) | phone | PASS | `logs/mobile-settings.json` | – |
| MOBILE | M-11@/bookings(bookings) | phone | PASS | `logs/mobile-bookings.json` | – |
| MOBILE | M-11@/find-room(find-room) | phone | PASS | `logs/mobile-find-room.json` | – |
| MOBILE | M-11@/find-room(results) | phone | PASS | `logs/mobile-results.json` | – |
| MOBILE | M-11@/login(login) | phone | PASS | `logs/mobile-login.json` | – |
| MOBILE | M-11@/login/change-password (R2-S-19) | phone | PASS | `shots/R2-S-19-change-password-phone.png` | – |
| MOBILE | M-11@/login/change-password(change-password) | phone | PASS | `logs/mobile-change-password.json` | – |
| MOBILE | M-11@/my-bookings(my-bookings) | phone | PASS | `logs/mobile-my-bookings.json` | – |
| MOBILE | M-11@/my-bookings(my-bookings-cancelled) | phone | PASS | `logs/mobile-my-bookings-cancelled.json` | – |
| MOBILE | M-11@/my-bookings(sync-off) | phone | PASS | `logs/mobile-sync-off.json` | – |
| MOBILE | M-11@/my-bookings(sync-sheet) | phone | PASS | `logs/mobile-sync-sheet.json` | – |
| MOBILE | M-11@/profile#notifications(profile-notifications) | phone | PASS | – | – |
| MOBILE | M-11@/profile(profile) | phone | PASS | `logs/mobile-profile.json` | – |
| MOBILE | M-11@/reset-password | phone | PASS | – | – |
| MOBILE | M-11@/reset-password(reset-password) | phone | PASS | `logs/mobile-reset-password.json` | – |
| MOBILE | M-11@/settings(settings-integrations) | phone | PASS | `logs/mobile-settings-integrations.json` | – |
| MOBILE | M-11@/settings?tab=integrations(settings-integrations) | phone | PASS | – | – |
| MOBILE | M-11@/settings?tab=solver(settings-solver) | phone | PASS | – | – |
| MOBILE | M-12@/approvals(reject) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(book-sheet) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(cancel all) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(cancel future) | phone | PASS | – | – |
| MOBILE | M-12@/bookings(cancel one) | phone | PASS | – | – |
| MOBILE | M-12@/find-room | phone | PASS | – | – |
| MOBILE | M-12@/login | phone | PASS | – | – |
| MOBILE | M-12@/login/change-password | phone | PASS | – | – |
| MOBILE | M-13@/find-room | phone | PASS | – | – |
| MOBILE | M-13@/login | phone | PASS | – | – |
| MOBILE | M-13@/my-bookings | phone | PASS | – | – |
| MOBILE | M-13@/my-bookings(sync) | phone | PASS | – | – |
| MOBILE | M-14@/find-room(search) | phone | PASS | – | – |
| MOBILE | M-14@/login | phone | PASS | – | – |
| MOBILE | M-14@/my-bookings(expand) | phone | PASS | – | – |
| RE-TEST | R2-S-11 /my-bookings | desktop | PASS | – | – |
| RE-TEST | R2-S-11 /my-bookings | phone | PASS | – | – |
| RE-TEST | R2-S-11 /profile | desktop | PASS | `shots/R2-S-11-profile-desktop.png` | – |
| RE-TEST | R2-S-11 /profile | phone | PASS | `shots/R2-S-11-profile-phone.png` | – |
| RE-TEST | R2-S-14 /dashboard digits | desktop | PASS | `shots/R2-S-14-dashboard-desktop.png` | – |
| RE-TEST | R2-S-14 /dashboard digits | phone | PASS | `shots/R2-S-14-dashboard-phone.png` | – |
| RE-TEST | R2-S-18 scope counts | desktop | SKIP | – | single bookings have no scope; see F-02 S08 dlg.radios for the series dialog (FLE-010 open) |
| RE-TEST | R2-S-18 scope counts | phone | SKIP | – | single bookings have no scope; see F-02 S08 dlg.radios for the series dialog (FLE-010 open) |
| RE-TEST | R2-S-22 toast parity | desktop | PASS* | `shots/R2-S-22-desktop.png` | superseded by r3-toast: one toast '1 rezervasyon iptal edildi · Gerekçe: Oda bakımda' from the grid and from the row sheet; the 'Bu rezervasyon iptal edildi' my reader caught is the sheet notice. Focus fell to <body> after the row-sheet cancel (R3-S-05) |
| RE-TEST | R2-S-22 toast parity | phone | PASS* | `shots/R2-S-22-phone.png` | row sheet toast '1 rezervasyon iptal edildi · Gerekçe: Oda bakımda'; the phone slot list does not list booked cells, so the grid half is desktop-only |
## Not run in this round

- F-02 S06 (planner's weekly series as a request): my script looked for a native date input; the custom end date is a text DateField. The planner holds `book_recur.create` on this stack. NOT RUN (harness).
- F-03 S04 on the phone: the free text sits in the filters sheet (T-R2-35); S03 passed through the sheet, S04's assert did not follow it. NOT RUN (harness).
- F-12 S09 ('Bağlantıyı dene' needs the test-account fields), F-12 S08 (TTL stack): not started in this re-test round. F-12 S18 (Entra tenant), F-04 S12 (OAuth client), F-03 S12 / F-04 S09 'Derslerim' (not built): BLOCKED / SKIP as every round.
- R1-S-11 'Yaz' confirm wording: on the fresh stack 'Yaz' was enabled after the API decisions, but no confirm was read within 8 s, and no commit happened (the job stayed READY). INCONCLUSIVE, not a finding.
- R1-S-04 (re-solve losses) is lane S / admin territory and on the admin tester's list.
- Export the week to Excel and the infeasible pin were verified in round 2 and were not re-run.
- Harness notes, not product defects: the PASS* rows say what the device did. Two F-03 rows were re-measured with direct probes (M-05 after a landscape rotation; S09's row selector). F-04 S04 needed the S01 feed token removed by id (there is no list route: `GET /calendar/feeds/tokens` → 405).
- README §8: the B04 and M-14 frame numbers are advisory (load 2–9).
