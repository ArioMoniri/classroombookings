# Flow loop round 1 · admin · 2026-10-16

Ledger: `flow-r1-admin-2026-10-16` · persona tester (admin: Fatih Bey as system administrator and planning coordinator) · plan: [README](../README.md), [MOBILE](../MOBILE.md)
Snapshot: `e77bb92` (`e77bb92ca4c99767929e7895c6a63c5658d583a1`, origin/claude/gracious-cerf-w1598m), frozen worktree in the scratchpad · stack API :19102, web :19103 (ports given by the orchestrator), SQLite in a `mktemp` folder · load 5–13 on 4 cores during the round, so timings are advisory (README §8)
Dates (README §4.3): TODAY 2026-10-16 · D1 2026-10-22 · D3 2026-11-05 · Chromium 141 (chromium-1194), Playwright 1.56 library
Data: all three real terms (Bahar 2026, Güz 2026-27, Final 2026) and the room master. Runs:
- #7 Bahar term, 682/717, hard 100, published (B0);
- #8 Güz term, 517/530, published;
- #9 Bahar week 6, made from the Studio UI (the week was meant to be 3, see R1-M-12);
- #10 Bahar week 3 with the nursing rules and the 100-in-30 pin, 694/716, hard 100;
- #11 cancelled.

Names are masked by `stack.sh` and the §4.4 seed (the §7 check returned `0`). Only fictional `@smartsched.local` accounts with initials were used.
Accounts: the seed (`personel.test`, `akademisyen.test` linked to instructor 157, `planner.test`), plus the ones made here: `ds.test*`, `limited.admin` (role "Kullanıcı yöneticisi") and `davet.test` (invite).
Preconditions applied:
- admin approves for all rooms; SMTP sink :2538;
- `approval_mode=all` set through the UI;
- calendar sync: the stack's own setup script had already signed it off, so it was switched off and then on again through the UI;
- Microsoft Entra with the fake tenant `1111…5555` for F-12, switched off afterwards;
- the public day view, a fake Telegram token, a booking policy and the exam-period mode were switched on in this round.

Viewports: desktop 1440×900 and phone 390×844 (isMobile, hasTouch, CDP hover:none / pointer:coarse, tap only). The tablet was not in this round's brief.
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/ac8cf3be-4f7b-53da-a7ff-63cf01e137b0/scratchpad/r1admin.ZXnD/ev` (`shots/`, `curl/` with tokens and secrets redacted, `mail/`, `logs/`, `scripts/`). The scripts in `scripts/` can be re-run.

## BLUF

38 findings: **1 blocker · 11 major · 22 minor · 4 suggestion**. The day-to-day admin work runs end to end in Turkish on real data:
- users, roles with no escalation (10/10 API attempts refused);
- approval mode, rejections with a required reason, the KVKK screens (data-subject requests, retention floor, inventory), webhooks, channels, the public day view;
- SSO guards with a fake tenant, the CRBS upgrade dry run, audit undo of a wizard programme;
- the week and term Excel export.

Five issues stand in the way of a go-live:
1. **R1-M-01 (blocker): the booking-conflict resolver cannot resolve anything from the UI.** "Önerilenleri uygula" makes a dry run that answers 500 (`TypeError … _after_rollback() takes 1 positional argument but 2 were given`), and the page prints "500 Internal Server Error". After a publish over real bookings, the admin has no UI path.
2. **R1-M-02: a week run cannot be published from the UI.** The confirm sends no scope confirmation. The 409 `scope_reduction` is shown as "Bu kaydı bu arada başka biri değiştirdi."
3. **R1-M-03 (Fatih Bey's infeasible scenario): the 100-students-in-30-seats hard pin is still accepted.** The rule path and the template take it, the pre-check never names it, and the run silently drops the class with hard 100. The diagnosis even calls B 201 a room that fits. The meeting edit path refuses it correctly.
4. **R1-M-04 / R1-M-05: the verdicts and scores still cannot be trusted.**
   - The run card says "hiçbir kural bozulmadı" while the report lists 78 over-capacity classes, and the counts differ between the card, the report and the API.
   - A move the server called "uygun" dropped the published run to hard 99 with no explanation.
5. **R1-M-07 (KVKK): the AI personal-data default is "Evet sayılır: geri alınmadıkça dahil".** Silence counts as consent.

Also major:
- the phone touch targets on all admin screens (R1-M-08) and the user sheet's save button, which is not sticky (R1-M-09);
- no forced-move-with-reason UI (R1-M-06);
- misleading analytics and invigilation results (R1-M-10, R1-M-11);
- the Studio overwriting the chosen week (R1-M-12).

Earlier issues verified fixed on this snapshot:
- M-12 (the presets menu works);
- M-14 (the CRBS upgrade works from the UI);
- M-27 (a cancelled run stays in the list);
- M-32 (the week export has 1 sheet);
- M-16 (Enter opens the inspector);
- M-34 (withdrawn requests appear under "Karara bağlanan");
- M-40 (the KVKK calendar screen exists);
- M-41 (webhook SSRF refused, though the message is English);
- M-42 (a disabled account gets the generic login error);
- M-46 (photo upload toast).

Still open: M-06/M-08 (R1-M-04), M-10 (R1-M-03), M-29 (R1-M-13), M-36 (R1-M-17), M-38 (R1-M-21) and M-02, which is still reachable through R1-M-05.

## Fatih Bey's scenarios

| Scenario | Result |
|---|---|
| Import the Bahar list and the weekly grid | ✓ by `stack.sh` (CLI import, 3 terms + room master). The UI import was the F-08 tester's |
| Find a course (PHAR 240) | ✓ timetable chip "PHAR 240 §1, Eczacılık 2. sınıf, A 206, Pazartesi 08:30–10:50, 80 öğrenci, 92 koltuk"; the inspector shows "Planlama listesi · Sayfa1 · satır 545" |
| Generate week 3 | ✓ run #10 694/716, FEASIBLE_PARTIAL, hard 100 (API start, Studio rules). From the Studio UI the run became week 6 (R1-M-12); its card claims "hiçbir kural bozulmadı" (R1-M-04) |
| Move PHAR 240 to A 206 from 23 Feb | ◐ PHAR 240 §1 already sits in A 206 in B0, so it was moved from week 4 to A 203 (F-10 precondition 3). The split is exact: weeks 1–3 in A 206, 4–14 in A 203 (API and term export). It needs week 4 on screen (R1-M-31), and hard dropped to 99 (R1-M-05). Toast "PHAR 240 §1 → A 203 taşındı" + "Geri al"; undo and redo work |
| Turkish request: nursing first-years before 17:30 | ◐ no AI key, the chip only fills the composer (R1-M-13). Template path: two rules, "Hemşirelik 1. sınıf … 10 derse", "Hemşirelik (İngilizce) 1. sınıf … 15 derse", both hard. Run #10: 20 placed year-1 nursing classes, all end by P11. The master's year-1 rows (HEM 566, HEM 504, HEM 509 end P12) are outside both rules, and the template never asks about them |
| Export the week to Excel | ✓ "Bu haftayı Excel'e aktar" gives 1 sheet "Hafta 4"; the term file has 14 sheets; `?weeks=99` → 422 "99. hafta dönemin dışında". Both files have the same name (R1-M-38) |
| Infeasible request (100 students → 30-seat B 201, hard) | ✗ R1-M-03 (ING 302 has 100, not 102, students in this data) |

## Coverage

| Flow / area | Desktop | Phone | Result |
|---|---|---|---|
| F-01 admin side (approval mode UI, bell → drawer, group approve, reject dialog negatives, API 422 ×3, withdraw visible, direct booking 201, planner 202) | ✓ | ✓ drawer bottom sheet, sticky approve/reject 44 px, reject sheet keeps field and confirm above a 336 px keyboard | PASS except R1-M-22, R1-M-23, R1-M-34 |
| F-04 S02/S11 calendar KVKK (UI switch, notice, ack-gated "Aç ve onayı kaydet", record "Administrator, 16 Ekim 2026 14:05 tarihinde açtı ve KVKK onayını verdi.", legal basis TR, audit `integrations.calendar_sync`) | ✓ | ✓ | PASS; turning it off is one tap with no confirm (noted) |
| F-09 Studio → run → report → publish | ✓ | ✓ stepper "1/5 · Kapsam", bottom bar above the tab bar, publish sheet with sticky "Yayınla" | FAIL R1-M-02, 03, 04, 12, 13, 14, 15; presets PASS (M-12 fixed); cancel PASS (M-27 fixed) |
| F-10 timetable (keyboard open, pick-up live region, scoped move, undo/redo, force API guards, capacity "Sığmaz", export) | ✓ | ✓ agenda view (M-08), inspector and move as full-height sheets, "Taşı" sticky | FAIL R1-M-05, 06; minor R1-M-31, 32 |
| F-11 users, CSV, roles, limited admin, rooms, features, approval mode, rules, KVKK, AI policy, audit | ✓ | ◐ users and rooms sheets | Escalation 10/10 refused. Features starter/adopt/new PASS; AI policy 422s PASS; findings R1-M-09, 16–22, 24 |
| F-12 local login, rate limit, logout revoke, `next` off-site; SSO config guards, PKCE redirect, callback refusals, ticket 401, invites 30 days, bind, break-glass 409 | ✓ | ✓ login inputs 16 px, targets 44 px | PASS; minor R1-M-25, R1-M-28 |
| F-13 admin part (reduced motion on the approvals drawer: no transform; keyboard A/D/R) | ✓ | – | R1-M-23 |
| Admin › KVKK (data-subject requests complete/refuse with mails, export zip holds only own data and gives 404 for others, retention floor "En az 365 gün olmalı.", inventory, AI default) | ✓ | ✓ | R1-M-07 |
| Ayarlar › Rezervasyon kuralları (policy 409 with TR reason, exam mode) | ✓ | ✓ | R1-M-33 |
| Ayarlar › Bildirim kanalları (secrets write-only, "Ayarlandı", KVKK sign-off with officer, limited admin 403, fake Telegram token refused) | ✓ | ✓ | PASS |
| Ayarlar › Microsoft ile giriş | ✓ | ✓ | R1-M-17, R1-M-25 |
| Admin › Kullanıcılar server-side filters (`q`, `role_id`, `enabled`, `identity`; counts from the server) | ✓ | ✓ | PASS; R1-M-30, R1-M-38 |
| /bookings/conflicts after publishing over real bookings | ✓ | ✓ | R1-M-01 (blocker), R1-M-26 |
| /public kiosk (off until a KVKK sign-off, then "Rezerve" only, no names, notes or departments in the API) | ✓ | ✓ | PASS; touch targets in R1-M-08 |
| Webhooks (off by default, loopback/private refused, secret shown once) | ✓ | ✓ | PASS; English message R1-M-17 |
| Audit undo of a wizard programme | ✓ | ✓ list | PASS; wording R1-M-18 |
| /exams/invigilation, /runs/compare, /analytics/heatmap | ✓ | ✓ | R1-M-10, R1-M-11; heat map hover hint on touch (noted) |
| CRBS legacy upgrade (structure.sql + data.sql + 2 rooms + 1 user) | ✓ dry run | – | PASS (M-14 fixed); R1-M-36 |

Security and privacy checks that passed:
- no secret is echoed back (SSO `client_secret_set: true`, channel secrets `Ayarlandı`, webhook `secret_hint` only, none in the audit);
- the public schedule API carries no person data;
- a data-subject export is limited to the requester (404 for others);
- limited-admin escalation is refused on every endpoint tried;
- the last break-glass admin cannot be demoted or disabled (409);
- `?next=//evil.example` lands on /dashboard.

## Findings

| Id | Severity | Step @ viewport | Finding | Evidence |
|---|---|---|---|---|
| R1-M-01 | blocker | Bookings › Çakışmalar (/bookings/conflicts/8) after a published run @1440 | The conflict resolver cannot apply anything from the UI: the dry run answers 500 | `shots/BC-plan-desktop.png` |
| R1-M-02 | major | F-09 S08 publish a week run @1440 | Publishing a week run from the UI always fails, with a false 'someone else changed it' message | `shots/F09-S08-publish-confirm-9-desktop.png` |
| R1-M-03 | major | F-09 S04 infeasible request: 100 students hard-pinned to 30-seat B 201 @API + Studio | A hard room pin over capacity is accepted through rules, never named by the pre-check, and the run hides it | `shots/F09-S04-pin-template-desktop.png` |
| R1-M-04 | major | F-09 S06/S07 run card vs report vs API @1440 | The run card says 'hiçbir kural bozulmadı' and the counts disagree between card, report and API | `shots/F09-S06-run-card-desktop.png` |
| R1-M-05 | major | F-10 S02/S06 hard score of the published run @API | A server-checked 'uygun' move drops the published run's hard score 100 → 99 with no explanation; a forced clash then leaves it published | `shots/F10-S02-moved-desktop.png` |
| R1-M-06 | major | F-10 S06 forced move with a written reason @1440 | No UI way for the admin to force a move with a reason | `shots/F10-S06-force-ui-desktop.png` |
| R1-M-07 | major | Admin › KVKK › Yapay zekâ ve kişisel veri @1440 | The registered default treats silence as consent for sending names to Claude | `shots/KV-ai-default-desktop.png` |
| R1-M-08 | major | MOBILE M-02 @390 (admin screens, timetable sheets, kiosk) | Touch targets under 44 px across the admin screens on a phone | `shots/crawl_admin_users-phone.png` |
| R1-M-09 | major | F-11 S01 user sheet @390 (MOBILE M-05) | The user form's save button is not sticky on a phone | `shots/F11-S01-filled-phone.png` |
| R1-M-10 | major | Analytics › Senaryo karşılaştırma (/runs/compare) @1440 | Comparing a week run with a term run labels empty data as 'B daha iyi' | `shots/AN-compare-desktop.png` |
| R1-M-11 | major | Sınavlar › Gözetmen ataması (/exams/invigilation) @1440 | An empty invigilation plan is reported as 'En iyi · tümü atandı' and can be published | `shots/INV-after-run-desktop.png` |
| R1-M-12 | major | F-09 S01 Studio scope persistence @1440 | The Studio forgets or overwrites the chosen term and week; a run was generated for the wrong week | `shots/F09-studio-reopen-desktop.png` |
| R1-M-13 | minor | F-09 S03 Turkish nursing request without AI (M-29) @1440 | Example chips still need AI, and the after-hours template takes one programme at a time | `shots/F09-S03-nursing-chip-desktop.png` |
| R1-M-14 | minor | F-09 S08 partial-publish list and wording @1440 | The unplaced list is shorter than the count, and week wording is ungrammatical | `shots/F09-S08-publish-confirm-9-desktop.png` |
| R1-M-15 | minor | F-09 S10 cancelled run report @1440 | A cancelled run's report reads like a clean result | `shots/F09-S10-cancelled-run-desktop.png` |
| R1-M-16 | minor | English text in TR mode (role names, permissions, sr-only labels, title) @1440 + 390 | Built-in role names and several labels stay English in Turkish mode | `shots/crawl_admin_users-desktop.png` |
| R1-M-17 | minor | Server messages shown verbatim in English | Validation errors reach the Turkish UI in English, some with a 'Value error,' prefix | `shots/F11-S09-webhook-secret-desktop.png` |
| R1-M-18 | minor | F-11 S11 audit log wording | Many audit rows and the undo dialog show raw keys | `shots/AUD-list-desktop.png` |
| R1-M-19 | minor | F-11 S02 CSV user import | A CSV with named columns is read as positional data; every row says 'Parola yok' | `shots/F11-S02-import-results-desktop.png` |
| R1-M-20 | minor | F-11 S05 room create/edit | New room codes lose their space, capacity is not editable in the sheet, and the room is grouped three different ways | `shots/F11-S05-create-desktop.png` |
| R1-M-21 | minor | F-11 S04 limited admin (M-38) and roles editor | The user-admin lands on a locked booking grid; disabled permissions have no visible reason; the role picker shows raw keys | `shots/F11-S04-limited-landing-desktop.png` |
| R1-M-22 | minor | Focus after actions (README §4.7, M-33) | Focus falls to <body> after saving Kurum ayarları; after a rejection it jumps to the bell | `shots/F11-S07-approval-mode-desktop.png` |
| R1-M-23 | minor | F-13 C02 approvals keyboard legend | The 'D Reddet' shortcut did not open the reject dialog | `shots/F13-reduced-approvals-desktop.png` |
| R1-M-24 | minor | Onay kuralları empty state under approval_mode=all | The rules page says every booking is approved at once while approval-first is on | `shots/crawl_admin_approval_rules-desktop.png` |
| R1-M-25 | minor | F-12 S11/S16 SSO admin details | Default role picker offers roles the server refuses; a revoked invite leaves an active, sign-in-less account | `shots/F12-S11-sso-tab-desktop.png` |
| R1-M-26 | minor | Bookings › Çakışmalar plan wording and grouping | An approved two-period request is split into two independent conflict rows | `shots/BC-plan-desktop.png` |
| R1-M-27 | minor | Run report performance | The run report takes about 10 s to load | `shots/F09-S07-report-9-desktop.png` |
| R1-M-28 | minor | F-12 S02/S10 login form | Empty submit gives an empty alert; the identifier is a plain text field | `shots/F12-S02-ratelimit-desktop.png` |
| R1-M-29 | minor | MOBILE M-03 @390 | Admin form inputs under 16 px and a 10 px badge on a phone | `logs/crawl-all.json` |
| R1-M-30 | minor | MOBILE M-04 filters @390 (/admin/users, /admin/audit) | Filters push the list below the first screen on a phone | `shots/crawl_admin_users-phone.png` |
| R1-M-31 | minor | F-10 S02 move dialog details @1440 | 'From 23 Feb' needs the user to open week 4 first; small text and focus issues | `shots/F10-S02-move-dialog-desktop.png` |
| R1-M-32 | minor | F-10 S01 keyboard reach | 40 Tab stops before the timetable grid | `shots/F10-S01-inspector-desktop.png` |
| R1-M-33 | minor | Ayarlar › Rezervasyon kuralları | The exam-period card does not say which dates are exam weeks; Administrator is offered as a policy target | `shots/POL-sheet-desktop.png` |
| R1-M-34 | minor | Approvals drawer details @1440 | The drawer heading shows one period for a two-period request; duplicate 'Kapat' | `shots/F01-S07-drawer-desktop.png` |
| R1-M-35 | suggestion | Calendar push (Ayarlar › Entegrasyonlar) tenant | Microsoft 365 calendar push defaults to any tenant while sign-in pins the university tenant | `shots/F04-S02-after-desktop.png` |
| R1-M-36 | suggestion | CRBS legacy upgrade review | The dry run updates existing roles without showing what changes | `shots/CRBS-dryrun-desktop.png` |
| R1-M-37 | suggestion | Generic look on login and glass sheets | The desktop login leaves two thirds of the screen as an empty gradient; translucent sheets reduce legibility | `shots/F12-S12-login-sso-on-desktop.png` |
| R1-M-38 | suggestion | Small polish | Week export file name, filters in URL, pin-template accessible names, busy labels | `shots/F10-S09-export-menu-desktop.png` |

### R1-M-01 (blocker) The conflict resolver cannot apply anything from the UI: the dry run answers 500
- **Step:** Bookings › Çakışmalar (/bookings/conflicts/8) after a published run @1440
- **Action:** Published Güz run #8 over real bookings (forced ENT 121 onto the approved C 303 · P7–P8 request of P. T., then 'Yeniden tara' found 2 conflicts). On /bookings/conflicts/8 pressed 'Önerilenleri uygula', then '0 kararı gözden geçir'.
- **Result:** The page shows 'Hiçbir değişiklik yapılmadı' and the raw line '500 Internal Server Error'; nothing is resolved. POST /bookings/conflicts/8/apply with dry_run:true → 500 every time. Backend log: TypeError: kick_after_commit.<locals>._after_rollback() takes 1 positional argument but 2 were given (services/booking_conflicts.py:729). The same body with dry_run:false → 200 (moved both to C 403, 1 mail 'Rezervasyonlarınız yeni programa göre güncellendi: 2 değişiklik'), so only the API path works.
- **Expected:** The dry run returns the preview (counts, who is notified) and the admin can confirm it in the UI. Errors are shown in Turkish, never a raw '500 Internal Server Error'.
- **Repro:** Publish a run whose class sits on an existing booking (or force-move one with a reason), POST /bookings/conflicts/<run>/detect, open /bookings/conflicts/<run>, 'Önerilenleri uygula'. Or: curl -X POST …/bookings/conflicts/8/apply -d '{"items":[{"conflict_id":1,"action":"move_room","option_id":"room:40","scope":"one"}],"dry_run":true}'.
- **Evidence:** `shots/BC-plan-desktop.png`, `shots/BC-after-apply-desktop.png`, `curl/BC-apply-dry.txt`, `curl/BC-apply-real.txt`
- **File hints:** smartsched/backend/app/workers/integrations.py:168-172 (the after_soft_rollback listener gets (session, previous_transaction)); smartsched/backend/app/services/booking_conflicts.py:729 (dry run rolls back a savepoint after a kick was queued); frontend conflict page error text

### R1-M-02 (major) Publishing a week run from the UI always fails, with a false 'someone else changed it' message
- **Step:** F-09 S08 publish a week run @1440
- **Action:** On /runs/9 (Bahar, 1 week, FEASIBLE_PARTIAL) pressed 'Yayınla', ticked 'Eksik derslerle yayımlamayı onaylıyorum' and pressed 'Yayınla'.
- **Result:** Toast: 'Bu kaydı bu arada başka biri değiştirdi. Sayfayı yenileyip tekrar deneyin.' POST /runs/9/activate → 409 code scope_reduction ('#9 yalnız 6. haftaları kapsıyor; yayımlanırsa #7 programının 18 haftası yayından kalkar'). The dialog shows the warning sentence 'Bu çalıştırma yalnız bu haftaları kapsıyor, ama yayımlanınca dönemin bütün haftaları için program olur.' but has no scope checkbox (publish-confirm-reduction is absent) and never sends confirm_scope_reduction.
- **Expected:** The confirm has an explicit scope control ('Evet, bu haftalar yayından kalksın' or similar) that must be ticked; with it the publish succeeds. A 409 scope_reduction is explained in its own words, not as a concurrency conflict.
- **Repro:** Generate any week run for a term that has a published term run, open its report, Yayınla, tick the partial box, Yayınla.
- **Evidence:** `shots/F09-S08-publish-confirm-9-desktop.png`, `shots/F09-S09-published-9-desktop.png`, `curl/F09-S08-activate-noconfirm.txt`
- **File hints:** smartsched/frontend/src/components/runs/* publish confirm (publish-scope-reduction / publish-confirm-reduction), the 409 → toast mapping in the API client

### R1-M-03 (major) A hard room pin over capacity is accepted through rules, never named by the pre-check, and the run hides it
- **Step:** F-09 S04 infeasible request: 100 students hard-pinned to 30-seat B 201 @API + Studio
- **Action:** POST /constraints {kind:room_pin, params:{event_ids:[521], room_ids:[21]}, hardness:hard} for ING 302 (100 students, Monday P3–P5) → B 201 (30 seats). Also opened the Studio template 'Her zaman bu derslikte'. Then 'Ön kontrol' and a Bahar week 3 run (#10).
- **Result:** POST /constraints → 201 with no warning. The template lists every room, including B 201 (30), with no fit check. The pre-check shows '3 kesin kural' and '9 ders kesin kurallarınızla yerleştirilemiyor' but no line names ING 302 / B 201 / 100 vs 30. Run #10 is FEASIBLE_PARTIAL, hard 100, and ING 302 #521 is silently unplaced; its diagnosis says 'ING 302 (100 öğrenci, Pazartesi 10:10–12:30) yerleşemedi: sığan derslikler o saatte dolu — B201 (30 kişilik: BCT 132 §1)', calling a 30-seat room 'fitting'. Only PUT /requests/meetings/521 {definitive_room_ids:[21]} is refused (422 '100 öğrenci 30 kişilik B 201'e sığmaz'; planner with a reason also 422: correct).
- **Expected:** Q8 applies to every path: the constraint/template edit is refused with '100 öğrenci 30 kişilik B 201'e sığmaz' (admin override with a written reason only), the pre-check names it, and the report lists it as the cause.
- **Repro:** As admin: POST /constraints as above (term 1); open /generate → Bahar → Ön kontrol; run week 3; GET /runs/<id> diagnosis.
- **Evidence:** `shots/F09-S04-pin-template-desktop.png`, `shots/F09-S05-precheck-desktop.png`, `curl/F09-S04-constraint.txt`, `curl/F09-S04-pin-noreason.txt`, `curl/F09-S04-pin-planner.txt`, `curl/F09-S05-precheck.json`
- **File hints:** smartsched/backend/app/api/v1/constraints.py (no capacity guard for room_pin); app/services/precheck.py:575 (hard pins not checked against capacity); diagnosis wording in app/services (sığan derslikler o saatte dolu)

### R1-M-04 (major) The run card says 'hiçbir kural bozulmadı' and the counts disagree between card, report and API
- **Step:** F-09 S06/S07 run card vs report vs API @1440
- **Action:** Generated a Bahar week run in the Studio (#9) and opened its card and report; compared with GET /runs/9 and /runs/9/assignments.
- **Result:** Card: '691/713 ders yerleşti · hiçbir kural bozulmadı'. Report headline: '691/713 yerleşti; uygulanan zorunlu kurallar karşılandı, şu istisnalarla: Izgarada 303 sınıf çakışmalı … 78 sınıf derslik kapasitesini aşıyor … 75 kilitli derslik sınıfına küçük', directly followed by 'Yerleşen her ders bütün kurallara uyuyor.' The API has 381 assignments with is_conflict and 32 with size > capacity (e.g. MAT 112 §1 180 students in 126-seat C 201); the report KPI says 'Sorun 596', the tab 'Dersliği olmayan dersler 20' while 22 are unplaced.
- **Expected:** One true sentence everywhere (M-06/M-08): never 'hiçbir kural bozulmadı' next to over-capacity placements; the same placed / unplaced / conflict / over-capacity numbers on the card, the report and the API.
- **Repro:** Studio → Bahar → Bir hafta → Planı oluştur; read run-result on the card, then Raporu aç.
- **Evidence:** `shots/F09-S06-run-card-desktop.png`, `shots/F09-S07-report-9-desktop.png`, `curl/F09-run9.json`, `curl/F09-run9-asg.json`
- **File hints:** smartsched/frontend/src/components/studio/run-cards.tsx (run-result sentence); the run report verdict (run-verdict, 'Yerleşen her ders bütün kurallara uyuyor'); backend stats used for the counts

### R1-M-05 (major) A server-checked 'uygun' move drops the published run's hard score 100 → 99 with no explanation; a forced clash then leaves it published
- **Step:** F-10 S02/S06 hard score of the published run @API
- **Action:** On published Bahar run #7 (hard 100) moved PHAR 240 §1 from 23 Feb (weeks 4–14) to A 203 through the move dialog ('✓ Sunucu kontrolü: uygun'). Later forced it onto A 204 (HEM 242) with the reason 'Bölüm başkanı onayı, tek seferlik', then moved it back.
- **Result:** After the clean move GET /runs/7 → hard_score 99 (was 100); no violation is listed anywhere (objective_breakdown only soft terms, stats.manual_edits 1). After the forced clash the score stays 99, the run stays is_active, and POST /runs/7/activate → 409 'room_double_booking: A204 week 1 day 1 P2: HEM 242, PHAR 240 §1'. So the published timetable carried a double booking while the score did not change.
- **Expected:** A move that the server called 'uygun' keeps hard 100, or the report names the broken rule. A forced hard clash on the published run is shown with its reason on the run and the timetable (M-02), and the score reflects it.
- **Repro:** Timetable /timetable?run=7&week=4 → PHAR 240 → Taşı… → A 203 → '23 Şubat tarihinden itibaren' → Taşı; GET /runs/7.
- **Evidence:** `shots/F10-S02-moved-desktop.png`, `curl/F10-S06-admin-reason.txt`, `curl/F10-S06-republish.txt`, `curl/F10-run7-after.json`
- **File hints:** backend rescoring after bulk-move (app/api/v1/calendar_v2.py bulk-move, app/services rescoring), run report

### R1-M-06 (major) No UI way for the admin to force a move with a reason
- **Step:** F-10 S06 forced move with a written reason @1440
- **Action:** As admin in the move dialog chose the occupied room A 204 for PHAR 240.
- **Result:** The row says 'HEM 242 ile çakışıyor (A 204 Pzt 09:20–11:40)' and 'Kilitli ders: taşıma kilidi korur'; 'Taşı' is disabled. There is no 'Yine de taşı', no 'Gerekçe' field. The API supports it (force without reason → 422 'forcing a move that breaks assignment needs a written reason'; with a reason → 200; planner → 403 'moving despite a conflict is admin-only').
- **Expected:** For an administrator the dialog lists what breaks and offers 'Yine de taşı' with a required 'Gerekçe'; confirm stays disabled while it is empty.
- **Repro:** Timetable → class → Taşı… → pick a room in 'Dolu'.
- **Evidence:** `shots/F10-S06-force-ui-desktop.png`, `curl/F10-S06-admin-noreason.txt`, `curl/F10-S05-planner-force.txt`
- **File hints:** smartsched/frontend/src/components/timetable/ move dialog (move-dialog, move-confirm)

### R1-M-07 (major) The registered default treats silence as consent for sending names to Claude
- **Step:** Admin › KVKK › Yapay zekâ ve kişisel veri @1440
- **Action:** Opened /admin/kvkk → 'Yapay zekâ ve kişisel veri'.
- **Result:** 'Hiç verilmemiş rıza' is set to 'Evet sayılır: geri alınmadıkça dahil' and marked 'Kayıtlı ayar': 'Herkesin adı ve e-postası yapay zekâ isteklerine girebilir; yalnızca Profil › Gizlilik bölümünde yapay zekâ rızasını geri alan kişi yer tutucuyla değiştirilir.'
- **Expected:** Under KVKK (açık rıza) consent is not presumed; a new installation should start at 'Hayır sayılır: verilmedikçe hariç', or the admin must make an explicit, dated choice before any person's name is sent abroad. AI is off on this stack, so nothing leaked, but the default is in place for the day a key is added.
- **Repro:** Fresh stack, admin, /admin/kvkk → Yapay zekâ tab.
- **Evidence:** `shots/KV-ai-default-desktop.png`
- **File hints:** smartsched/frontend/src/components/kvkk/ai-default.tsx; backend default of the ai_personal_default setting

### R1-M-08 (major) Touch targets under 44 px across the admin screens on a phone
- **Step:** MOBILE M-02 @390 (admin screens, timetable sheets, kiosk)
- **Action:** Ran the M-02 probe at 390×844 (touch, hover:none) on 30 admin routes, the timetable sheets and the kiosk.
- **Result:** Top bar 'whats-new', 'notification-bell', 'user-menu' 32×32 on every screen; the Kurulum sub-navigation pills 28 px tall ('Kurulum 72x28', 'Kullanıcılar 87x28', 'Roller 57x28' …); move sheet room rows 'free-room 342x30'; inspector 'Taşı…' 36 px; heat-map tabs 'heat-tab-rooms 91x26', 'heat-source-live 131x22'; runs list 'runs-compare 112x32', '#8 18x20'; kiosk 'kiosk-prev 32x32', 'kiosk-back 40x16', 'locale-option-tr 36x22'. Offender counts per route: /admin/users 37, /admin/rooms 40, /admin/weeks 45, /admin/departments 49.
- **Expected:** Every interactive element ≥ 44 × 44 px or with a hit area that large (MOBILE.md M-02).
- **Repro:** node ev/scripts/crawl.mjs (VPS=phone) and phone.mjs; see logs/crawl-all.json → M02.
- **Evidence:** `shots/crawl_admin_users-phone.png`, `shots/F10-phone-move-phone.png`, `shots/PUB-room-phone.png`, `logs/crawl-all.json`, `logs/phone-phone.json`
- **File hints:** smartsched/frontend/src/components/shell (top bar icons), admin sub-nav, timetable move dialog free-room rows, analytics heatmap tabs, public kiosk header

### R1-M-09 (major) The user form's save button is not sticky on a phone
- **Step:** F-11 S01 user sheet @390 (MOBILE M-05)
- **Action:** Kullanıcılar → 'Yerel hesap oluştur' at 390×844, filled the form.
- **Result:** The sheet is full height (0,48 → 390×796) but 'Oluştur' (user-save) sits at y = 1171 inside the scroll, off screen; the title and close button scroll away; the sheet is translucent, so the tab bar ('Özet', 'Talepler' …) shows through the lower fields.
- **Expected:** Save sticky in the sheet footer, inside the bottom 40 % (M-05); opaque sheet surface.
- **Repro:** Phone context, /admin/users → Yerel hesap oluştur.
- **Evidence:** `shots/F11-S01-filled-phone.png`, `logs/F11-S01-phone.json`
- **File hints:** smartsched/frontend/src/components/admin/users-admin.tsx (user-dialog footer), the shared sheet component

### R1-M-10 (major) Comparing a week run with a term run labels empty data as 'B daha iyi'
- **Step:** Analytics › Senaryo karşılaştırma (/runs/compare) @1440
- **Action:** A = #7 Bahar full term (published), B = #10 Bahar week 3, 'Karşılaştır'.
- **Result:** 'Oda doluluğu % 20,4 → %0 · yön yok', 'Eğitmen boşlukları (haftalık) 348 → 0 · B daha iyi', 'Boşluğu olan eğitmen 110 → 0 · B daha iyi', 'En yüksek haftalık yük 45 → 0 · B daha iyi'; header '832 ders taşındı'.
- **Expected:** Runs with different horizons are compared on the overlapping weeks only, or the page warns that the scopes differ; a metric that is 0 because the data is missing is never 'daha iyi'.
- **Repro:** /runs/compare → A #7, B #10 → Karşılaştır.
- **Evidence:** `shots/AN-compare-desktop.png`
- **File hints:** smartsched/backend/app/api/v1/analytics.py:34 (/compare), frontend runs/compare view

### R1-M-11 (major) An empty invigilation plan is reported as 'En iyi · tümü atandı' and can be published
- **Step:** Sınavlar › Gözetmen ataması (/exams/invigilation) @1440
- **Action:** Selected '2026-FINAL · #6 · Grid import …' and ran 'Yeni plan' with the defaults.
- **Result:** Plan #1: 'En iyi', '0/0 görev', '0 salon-oturum, 0 görev: tümü atandı', 'sert 100 · yumuşak 100', with 'Yayımla' enabled — while 'Tanılar 1 hata' says 'Gözetmen havuzu boş: sınav hocaları eşleşmedi ve havuza kimse eklenmedi'. The imported Final exam list (926 rows) gives no room-sessions for the only exam run.
- **Expected:** With 0 room-sessions the plan says that there is nothing to assign and why (no exam run with rooms), is not 'En iyi', and cannot be published.
- **Repro:** /exams/invigilation → Yeni plan → Çalıştır.
- **Evidence:** `shots/INV-after-run-desktop.png`, `shots/INV-new-plan-desktop.png`
- **File hints:** smartsched/backend/app/api/v1/invigilation.py (plans), frontend exams/invigilation view

### R1-M-12 (major) The Studio forgets or overwrites the chosen term and week; a run was generated for the wrong week
- **Step:** F-09 S01 Studio scope persistence @1440
- **Action:** Selected Bahar 2026 → Bir hafta → H3 ('Tüm değişiklikler kaydedildi' shown), closed the browser, opened /generate again; in a later session selected Bahar → H3 again and pressed 'Planı oluştur'.
- **Result:** The new session reopened on 'Güz 2026-27 · Tüm dönem · 2 hafta' with Güz rules. In the later session a late restore replaced my H3 with H6: the side panel read 'SmartSched 6. hafta için 869 dersi 61 dersliğe yerleştirecek', and run #9 was created for week 6 ('2026-BAHAR · Dersler · 6. hafta'). Audit: 'studio.draft.update {horizon: WEEK, horizon_params: {weeks: [6]}}'.
- **Expected:** The saved draft reopens with the same term, horizon and weeks, and a late load never overwrites a choice the user made after the page opened.
- **Repro:** Choose Bahar + H3, reload; or start on a draft that had another week and click H3 right after load.
- **Evidence:** `shots/F09-studio-reopen-desktop.png`, `shots/F09-S06-running-desktop.png`
- **File hints:** smartsched/frontend/src/components/studio/studio-store.ts / studio-data.tsx (draft load vs local edits), scope-step.tsx

### R1-M-13 (minor) Example chips still need AI, and the after-hours template takes one programme at a time
- **Step:** F-09 S03 Turkish nursing request without AI (M-29) @1440
- **Action:** Typed 'Hemşirelik 1. sınıf dersleri 17:30'dan sonra olmasın' and clicked the chip 'Hemşirelik 1. sınıf 17:30'dan sonra ders almasın'.
- **Result:** The chip only fills the composer; 'Kurala çevir' stays disabled with 'Kendi cümlenizle kural yazmak için YZ gerekir. Yönetici Ayarlar → YZ'den açabilir.' The template 'Belirli saatten sonra ders olmasın' works ('Hemşirelik 1. sınıf … 10 derse uygulanıyor', '(İngilizce) … 15 derse') but needs two rules for the two programmes; no toast after 'Kuralı ekle'; the list shows the name lower-cased: 'hemşirelik (ingilizce) 1. sınıf için 17:30'dan sonra ders olmasın'. Run #10 honoured it: 20 placed year-1 nursing classes, none after P11.
- **Expected:** Without a key the chip opens the matching template prefilled (M-29); the programme field accepts several programmes; names keep their case.
- **Repro:** /generate → Kurallar ve tercihler → chip; then Şablondan seç → Saatler.
- **Evidence:** `shots/F09-S03-nursing-chip-desktop.png`, `shots/F09-S03-nurse1-desktop.png`, `shots/F09-S03-nurse2-desktop.png`
- **File hints:** smartsched/frontend/src/components/studio/rules-step.tsx, template-gallery.tsx, rule-sentence.ts

### R1-M-14 (minor) The unplaced list is shorter than the count, and week wording is ungrammatical
- **Step:** F-09 S08 partial-publish list and wording @1440
- **Action:** Opened the publish confirm of run #9 (22 unplaced).
- **Result:** 'Yerleşmeyen 22 ders yayımlanan programda olmayacak:' lists 13 codes (MAT 112 §1 … NUT 404). Scope line '2026-BAHAR, 6. haftalar'; pre-check 'SmartSched 3. haftalar için 868 dersi…'.
- **Expected:** Exactly 22 entries (or '…ve 9 ders daha'); '6. hafta' / '3. hafta için'.
- **Repro:** /runs/9 → Yayınla.
- **Evidence:** `shots/F09-S08-publish-confirm-9-desktop.png`
- **File hints:** run publish confirm (publish-partial), Turkish plural helper for weeks

### R1-M-15 (minor) A cancelled run's report reads like a clean result
- **Step:** F-09 S10 cancelled run report @1440
- **Action:** Started a Bahar term run and pressed 'Çalıştırmayı iptal et' (toast 'Çalıştırma iptal edildi', status CANCELLED, kept in the list: M-27 fixed; activate → 409: correct).
- **Result:** Report: 'Bu çalıştırma çizelge üretemedi. Nedenleri aşağıda.', 'Bütün tercihler karşılandı.', 'İhlal yok. Tüm katı kısıtlar sağlanıyor.'; no word 'İptal edildi'; 'Sorun 0' right after cancel, 'Sorun 645' after a reload.
- **Expected:** The report says it was cancelled, by whom and when, and shows no 'İhlal yok' / 'karşılandı' claims.
- **Repro:** Start a run, cancel it, open /runs/<id>.
- **Evidence:** `shots/F09-S10-cancelled-run-desktop.png`
- **File hints:** run report view for CANCELLED status

### R1-M-16 (minor) Built-in role names and several labels stay English in Turkish mode
- **Step:** English text in TR mode (role names, permissions, sr-only labels, title) @1440 + 390
- **Action:** Visited the admin screens in TR (profile language tr).
- **Result:** Role names 'Administrator', 'Planner', 'Teacher', 'Viewer' in the users table, the role pickers, 'Kimler için', the SSO default role and the login hint 'İlk girişinizde hesabınız Teacher olarak açılır.' (the sidebar footer says 'Yönetici'). /admin/roles rows 'Tek seferlik: Edit other users' single bookings', 'Tekrarlayan: Cancel other users' recurring bookings'. Dialogs end with an sr-only 'Close'; toasts 'Close toast'. document.title on /runs: 'Runs · SmartSched'.
- **Expected:** Turkish names for built-in roles ('Yönetici', 'Planlamacı', 'Öğretim elemanı', 'İzleyici'), Turkish permission texts, 'Kapat', 'Çalıştırmalar · SmartSched'.
- **Repro:** Any admin page in TR; enScan in logs/crawl-all.json.
- **Evidence:** `shots/crawl_admin_users-desktop.png`, `shots/F12-S12-login-sso-on-desktop.png`, `logs/crawl-all.json`
- **File hints:** messages/tr.json, role display mapping, shared Dialog/Toaster close labels, app/(app)/runs page metadata

### R1-M-17 (minor) Validation errors reach the Turkish UI in English, some with a 'Value error,' prefix
- **Step:** Server messages shown verbatim in English
- **Action:** Triggered refusals in the admin UI and API.
- **Result:** Webhook URL: 'Value error, blocked address: webhook URLs may not point at loopback, private (RFC 1918) …'. SSO tenant: 'Value error, tenant id 'common' is not allowed: pin the university's own directory (tenant) id'. Room photo: 'Bir sorun oluştu: the file is not a jpg, png, gif or webp image'. CSV import row: 'Geçersize-mail personel.test@smartsched.local belongs to another user'. CRBS dry run warnings: 'skipped unsupported statement: …'. Withdraw twice: message_tr 'talep WITHDRAWN durumunda'. AI policy 422: English only. Move preview: 'A 204 is taken by HEM 242 (Pazartesi P2-P4)'.
- **Expected:** Turkish messages next to the field (M-36, M-41), with the technical detail only in an expandable part.
- **Repro:** Webhook 'http://127.0.0.1:19102/hook'; SSO tenant 'common'; upload a .txt renamed .png; CSV with an existing e-mail.
- **Evidence:** `shots/F11-S09-webhook-secret-desktop.png`, `shots/F12-S11-sso-common-desktop.png`, `logs/integ-desktop.json`, `logs/sso-ui-desktop.json`, `logs/F11-S05-desktop.json`, `logs/F11-S02-desktop-crbs.json`
- **File hints:** backend validators (webhooks, sso schemas, room photo, users import, approvals withdraw), frontend error mapping

### R1-M-18 (minor) Many audit rows and the undo dialog show raw keys
- **Step:** F-11 S11 audit log wording
- **Action:** Opened /admin/audit after the KVKK, channel, policy and wizard steps, and pressed 'Geri al' on the wizard programme (undo works: 'Program geri alındı · Arşivlendi: 1 program, 1 birim, 1 ders, 1 şube, 1 talep, 1 kişi').
- **Result:** Rows 'dsr_request · kvkk.dsr_refuse', 'notify_channel · channels.config', 'setting · booking_policy.exam_period', 'booking_policy eklendi', 'webhook eklendi', 'meeting eklendi', 'section eklendi', 'course eklendi', 'instructor eklendi', 'sso.config_update'. Undo dialog title: 'program.create geri alınsın mı?'. Actor filter lists 'D. S.' three times; 'Dönem' twice in the type filter.
- **Expected:** Domain sentences ('Kişisel veri talebi reddedildi · #2', 'Ders eklendi · TST 101'); the raw key only in the details.
- **Repro:** /admin/audit.
- **Evidence:** `shots/AUD-list-desktop.png`, `shots/AUD-wizard-undo-dialog-desktop.png`, `logs/audit-desktop.json`
- **File hints:** smartsched/frontend/src/components/admin/audit* (labels), messages/tr.json audit actions

### R1-M-19 (minor) A CSV with named columns is read as positional data; every row says 'Parola yok'
- **Step:** F-11 S02 CSV user import
- **Action:** İçe aktar → CSV 'email,full_name,role,password' (3 rows) → Çalıştır.
- **Result:** Results: '1 email Parola yok', '2 ds.test@… Parola yok', '3 nopass.test@… Parola yok', '4 personel.test@… Parola yok' — the header became a user row. The same data in CRBS column order works ('2 ds.test Oluşturuldu', '3 nopass.test Parola yok', '4 personel.test Geçersiz…'). No summary toast.
- **Expected:** A header row is detected by its names (email, full_name/displayname, role, password) or refused with a Turkish message; results get a total line.
- **Repro:** /admin/users → CSV içe aktar with the F-11 precondition file.
- **Evidence:** `shots/F11-S02-import-results-desktop.png`, `shots/F11-S02-import-results-crbs-desktop.png`
- **File hints:** backend users CSV importer (header detection), users-admin.tsx import-results

### R1-M-20 (minor) New room codes lose their space, capacity is not editable in the sheet, and the room is grouped three different ways
- **Step:** F-11 S05 room create/edit
- **Action:** Yeni derslik: code 'T 101', name 'Test dersliği', 40, group A Blok → Oluştur; then edited it.
- **Result:** Stored as 'T101' (the hint says 'ör. A 101' and imported rooms keep 'A 101'). The edit sheet shows 'T105 · 40 kişilik' but has no capacity field and no pointer to where it is changed. The room appears as 'Test dersliği' without its code in Erişim denetimi, the exam room picker and the move dialog ('Test dersliği'ye sığmaz'), as 'T Blok' on /public and as 'TEST Blok · 3 oda' on the timetable, while its group is A Blok.
- **Expected:** Codes are stored as typed (or normalised everywhere the same way); capacity editable or linked; pickers show code + name; one grouping.
- **Repro:** /admin/rooms → Salonlar → Yeni derslik.
- **Evidence:** `shots/F11-S05-create-desktop.png`, `shots/F11-S05-edit-desktop.png`, `shots/PUB-index-desktop.png`
- **File hints:** smartsched/frontend/src/components/admin/rooms-admin.tsx:358 (create), room code normalisation in the backend, public schedule building derivation

### R1-M-21 (minor) The user-admin lands on a locked booking grid; disabled permissions have no visible reason; the role picker shows raw keys
- **Step:** F-11 S04 limited admin (M-38) and roles editor
- **Action:** Logged in as limited.admin (role 'Kullanıcı yöneticisi': setup.users, setup.roles, room.view). Escalation: 10/10 API attempts refused (403), including bookings.skip_approval on TEACHER, ADMIN invite, own role, admin password.
- **Result:** Landing /bookings: a full grid of lock icons with no sentence why. Roles editor: 64 disabled checkboxes, 0 'role-disabled-hint' texts. User form role picker: 'Administrator (eksik: approvals.decide, audit.view, book_recur.cancel_other_booking +31) [disabled]'.
- **Expected:** Land on /admin/users (the first page they can use); each disabled permission shows its reason as text; the picker names missing permissions in Turkish.
- **Repro:** Log in as limited.admin; open /admin/roles → Kullanıcı yöneticisi; /admin/users → Yeni kullanıcı → Rol.
- **Evidence:** `shots/F11-S04-limited-landing-desktop.png`, `shots/F11-S04-role-edit-desktop.png`, `curl/F11-S04-esc1.txt`
- **File hints:** post-login landing logic, smartsched/frontend/src/components/admin/roles-admin* (role-disabled-hint), users-admin.tsx role options

### R1-M-22 (minor) Focus falls to <body> after saving Kurum ayarları; after a rejection it jumps to the bell
- **Step:** Focus after actions (README §4.7, M-33)
- **Action:** Saved 'Rezervasyon onayı' → 'Her talep önce onaya' with 'Kaydet' (toast 'Kaydedildi'); rejected A 104 with 'Reddet ve bildir'.
- **Result:** After save document.activeElement = BODY. After the rejection (toast 'Reddedildi. Talep edene bildirildi.') focus is on 'Bildirimler, 3 okunmamış', not on the next request.
- **Expected:** Focus stays on the save button or moves to the next request's title.
- **Repro:** /admin/settings → approval-mode → Kaydet; /approvals → Reddet.
- **Evidence:** `shots/F11-S07-approval-mode-desktop.png`, `shots/F01-S08-after-reject-desktop.png`
- **File hints:** admin settings form, approvals-view.tsx focus-after-decision

### R1-M-23 (minor) The 'D Reddet' shortcut did not open the reject dialog
- **Step:** F-13 C02 approvals keyboard legend
- **Action:** On /approvals with the legend 'A Onayla · D Reddet · R Başka oda' visible: focused a request row and pressed d; opened the drawer and pressed d.
- **Result:** Nothing opened in either case (reject-codes not visible). After Enter on a row, focus goes to the drawer's 'Kapat', where the keys do nothing.
- **Expected:** A/D/R act on the open request wherever focus is outside a text field.
- **Repro:** Keyboard only on /approvals.
- **Evidence:** `shots/F13-reduced-approvals-desktop.png`, `logs/f13b.json`
- **File hints:** approvals-view.tsx key handler

### R1-M-24 (minor) The rules page says every booking is approved at once while approval-first is on
- **Step:** Onay kuralları empty state under approval_mode=all
- **Action:** With approval_mode=all, opened /admin/approval-rules (no rules yet).
- **Result:** 'Onay kuralı yok. classroombookings'teki gibi her rezervasyon hemen onaylanır.' A stray 'Önceden bildirim (iş günü)' label sits above 'Yeni kural'.
- **Expected:** 'Kural yok; şu anda her talep önce onaya gider (Rezervasyon onayı: Her talep önce onaya).' No legacy product name.
- **Repro:** Set approval mode to all, open /admin/approval-rules.
- **Evidence:** `shots/crawl_admin_approval_rules-desktop.png`, `shots/F11-S08-rules-list-desktop.png`
- **File hints:** admin approval-rules view, messages/tr.json

### R1-M-25 (minor) Default role picker offers roles the server refuses; a revoked invite leaves an active, sign-in-less account
- **Step:** F-12 S11/S16 SSO admin details
- **Action:** Microsoft ile giriş tab; invited davet.test@… (D. T.), then revoked the invite.
- **Result:** 'Yeni hesapların rolü' lists Administrator, Kullanıcı yöneticisi, Planner (server: 422 default_role_privileged). After DELETE /auth/sso/admin/invites/1 the user D. T. stays 'Aktif' with Giriş yöntemi '—'. GET /auth/sso/admin/invites returns the invite link (token) again on every call.
- **Expected:** Only eligible roles are offered; revoking an invite disables or removes the placeholder account; the link is shown once.
- **Repro:** /settings?tab=sso; POST/DELETE /auth/sso/admin/invites.
- **Evidence:** `shots/F12-S11-sso-tab-desktop.png`, `shots/crawl_admin_users-desktop.png`, `curl/F12-S16-invite.txt`, `curl/F12-S16-del.txt`
- **File hints:** smartsched/frontend/src/components/identity/sso-settings.tsx; backend sso invites

### R1-M-26 (minor) An approved two-period request is split into two independent conflict rows
- **Step:** Bookings › Çakışmalar plan wording and grouping
- **Action:** Opened /bookings/conflicts/8 for the P. T. request C 303 · P7–P8.
- **Result:** Two rows ('· 13:30-14:10' and '· 14:20-15:00'), each with its own options; the second offers 'C 303 16:00-16:40 boş (+2 ders saati)', which would split the request. Reason lines say 'Kapasite 45: 45 kişi için %0 boş koltuk' although the headcount is unknown.
- **Expected:** One row per request group with options that keep both periods together; no invented headcount.
- **Repro:** As in the blocker repro.
- **Evidence:** `shots/BC-plan-desktop.png`
- **File hints:** smartsched/backend/app/services/booking_conflicts.py (grouping, reason text)

### R1-M-27 (minor) The run report takes about 10 s to load
- **Step:** Run report performance
- **Action:** Opened /runs/9 and /runs/10 (desktop and phone).
- **Result:** 10.4 s and 10.1 s to network idle at load ≈ 6 on 4 cores (other pages 1.5–3.5 s). The KPI odometers expose every digit to text ('691 0 1 2 3 4 5 6 7 8 9 … / 713').
- **Expected:** Report usable within ~3 s; digits hidden from assistive tech except the final value.
- **Repro:** Open /runs/<id>; read main.innerText.
- **Evidence:** `shots/F09-S07-report-9-desktop.png`, `logs/report-9-desktop.json`, `logs/phone-phone.json`
- **File hints:** run report data fetches; odometer component (aria-hidden on the rolling digits)

### R1-M-28 (minor) Empty submit gives an empty alert; the identifier is a plain text field
- **Step:** F-12 S02/S10 login form
- **Action:** Pressed Enter on the empty login form; inspected the fields.
- **Result:** An empty role=alert, no per-field text (U-20). 'login-identifier' is type=text with autocomplete=username and no inputmode=email. Wrong password and rate limit are good: 'Kullanıcı adı, e-posta veya parola yanlış.', password cleared, and after 10 failures 'Çok fazla deneme. 4 dakika sonra tekrar deneyin.' (429, Retry-After 300). ?next=//evil.example lands on /dashboard.
- **Expected:** 'Kullanıcı adı veya e-posta gerekli' / 'Parola gerekli' next to the fields; inputmode=email.
- **Repro:** /login → Enter.
- **Evidence:** `shots/F12-S02-ratelimit-desktop.png`, `logs/login-ui-desktop.json`
- **File hints:** smartsched/frontend/src/app/login

### R1-M-29 (minor) Admin form inputs under 16 px and a 10 px badge on a phone
- **Step:** MOBILE M-03 @390
- **Action:** M-03 probe at 390 on the admin screens.
- **Result:** Inputs < 16 px (iOS zoom on focus): org-name, org-web, org-tz, ldap-server, ldap-port, smtp-host, smtp-user, hol-name, hol-start, sess-sched, sch-name, ac-q, ac-user, sso-tenant, sso-client, cp-public-url, cp-google-id, api-key, roles 'role-name', 'role-desc', users-role-filter, heat-group, invig-run. The notification badge text '5' is 10 px.
- **Expected:** Inputs ≥ 16 px on phone; text ≥ 11 px.
- **Repro:** crawl.mjs VPS=phone → M03.
- **Evidence:** `logs/crawl-all.json`, `shots/crawl_admin_settings-phone.png`
- **File hints:** shared Input/Select sizes in admin forms, notification badge

### R1-M-30 (minor) Filters push the list below the first screen on a phone
- **Step:** MOBILE M-04 filters @390 (/admin/users, /admin/audit)
- **Action:** Opened /admin/users and /admin/audit at 390.
- **Result:** Users: search, four selects, three chips and 'Giriş yöntemi' take ≈ 550 px before the first card. Audit: the first event starts at y ≈ 355 under five filter controls.
- **Expected:** One 'Filtreler · n' trigger opening a bottom sheet (M-04).
- **Repro:** Phone context, /admin/users.
- **Evidence:** `shots/crawl_admin_users-phone.png`, `shots/AUD-phone-phone.png`
- **File hints:** users-admin.tsx, audit view filters

### R1-M-31 (minor) 'From 23 Feb' needs the user to open week 4 first; small text and focus issues
- **Step:** F-10 S02 move dialog details @1440
- **Action:** Opened the move dialog for PHAR 240 on week 3, then on week 4.
- **Result:** On week 3 the only options are 'Tüm haftalar (1–14)', 'Sadece 3. hafta (16 Şubat)', '16 Şubat tarihinden itibaren (3. hafta)': no 'Başlangıç haftası' picker. On week 4 '23 Şubat tarihinden itibaren (4. hafta)' works and splits correctly (weeks 1–3 A 206, 4–14 A 203; the term export shows the same). After 'Taşı' focus is on the inspector's 'Taşı…', not on the chip. Dative: 'Test dersliği'ye sığmaz'. Ctrl+Z / Ctrl+Shift+Z work, but the 'Yinelendi' toast appears 2–3 s late.
- **Expected:** A start-week picker in the dialog; focus back on the moved chip; correct dative.
- **Repro:** /timetable?run=7&week=3 → PHAR 240 → Taşı….
- **Evidence:** `shots/F10-S02-move-dialog-desktop.png`, `shots/F10-S02-move-ready-desktop.png`, `logs/tt6.json`
- **File hints:** smartsched/frontend/src/components/timetable/ move dialog, tr_grammar dative for names

### R1-M-32 (minor) 40 Tab stops before the timetable grid
- **Step:** F-10 S01 keyboard reach
- **Action:** From the top of /timetable?run=7&week=3 pressed Tab until focus entered the grid.
- **Result:** 40 presses; the grid stop is announced 'Pano, Pazartesi, 3. hafta'. Enter on a chip opens the inspector (not quick-create: M-16 fixed); Esc returns focus to the chip; Space picks up with 'PHAR 240 §1 alındı. Ok tuşları taşır, Boşluk bırakır, Esc iptal eder.' and Esc says 'Taşıma iptal edildi.'
- **Expected:** A skip link to the grid or a shortcut ('g t').
- **Repro:** Keyboard only on /timetable.
- **Evidence:** `shots/F10-S01-inspector-desktop.png`, `logs/tt2-desktop.json`
- **File hints:** timetable toolbar order / skip link

### R1-M-33 (minor) The exam-period card does not say which dates are exam weeks; Administrator is offered as a policy target
- **Step:** Ayarlar › Rezervasyon kuralları
- **Action:** Created policy 'Önceden bildirim testi' (Teacher, Güz, 2 iş günü: staff booking for 19.10 → 409 'Bu rezervasyon en az 2 iş günü önceden yapılır; en erken 20.10.2026 …', correct) and set 'Sınav dönemi' to 'Yalnızca talep' (toast 'Sınav dönemi kaydedildi').
- **Result:** The card never lists the exam weeks or how many rooms count as exam rooms. 'Kimler için' offers Administrator although 'Planlama yöneticileri bu kurallara hiçbir zaman bağlı değildir.'
- **Expected:** Show the exam weeks (dates) and the exam-room count; offer only roles the policy can bind.
- **Repro:** /settings?tab=booking-rules.
- **Evidence:** `shots/POL-sheet-desktop.png`, `shots/POL-exam-desktop.png`, `curl/POL-staff-lead.txt`
- **File hints:** smartsched/frontend/src/components/policies/policies-admin.tsx

### R1-M-34 (minor) The drawer heading shows one period for a two-period request; duplicate 'Kapat'
- **Step:** Approvals drawer details @1440
- **Action:** Opened the approved C 303 request (P7–P8) from the bell.
- **Result:** Heading 'Per 22 Eki · P7 (13:30–14:10)' while the list says '2 ders saati'; the drawer text ends 'Kapat Kapat'. Otherwise F-01 admin steps pass: one mail for both periods ('Oda talebiniz onaylandı: C 303, 22.10.2026 P7-P8 13:30-15:00'), the reject dialog enforces code + text ('Bir gerekçe türü seçin.', 'Gerekçeyi yazın; yalnız boşluk sayılmaz.'), withdrawn requests appear as 'Geri çekildi' under 'Karara bağlanan'.
- **Expected:** 'P7–P8 (13:30–15:00)'; one close button name.
- **Repro:** /approvals?request=1&group=1.
- **Evidence:** `shots/F01-S07-drawer-desktop.png`, `shots/F01-S10-decided-desktop.png`
- **File hints:** approvals-view.tsx drawer header

### R1-M-35 (suggestion) Microsoft 365 calendar push defaults to any tenant while sign-in pins the university tenant
- **Step:** Calendar push (Ayarlar › Entegrasyonlar) tenant
- **Action:** Read the 'Google Takvim ve Microsoft 365 aktarımı' card.
- **Result:** 'Kiracı (tenant): organizations (her kurum hesabı), common, bir kiracı kimliği (GUID) ya da alan adı.' Default 'organizations'. SSO refuses common/organizations.
- **Expected:** Default to the SSO tenant when it is configured, and say that other tenants receive booking data.
- **Repro:** /settings?tab=integrations.
- **Evidence:** `shots/F04-S02-after-desktop.png`
- **File hints:** calendar-push-admin.tsx; calendar_sync connector settings

### R1-M-36 (suggestion) The dry run updates existing roles without showing what changes
- **Step:** CRBS legacy upgrade review
- **Action:** İçe aktar → Eski CRBS veritabanı → a CRBS structure.sql + data.sql dump with two rooms and one user (initials) → Deneme çalıştırması (works from the UI: M-14 fixed; '6 tabloda 7 yeni satır', fingerprint, 'Yükseltmeyi uygula').
- **Result:** 'roles 0 yeni · 2 güncellendi' with no list of the permission changes on the existing SmartSched roles; '3 uyarı' are English parser messages.
- **Expected:** List each updated role with the permissions added or removed before 'Yükseltmeyi uygula' (an upgrade must not silently widen a role).
- **Repro:** /import → Eski CRBS veritabanı.
- **Evidence:** `shots/CRBS-dryrun-desktop.png`, `curl/CRBS-dry.json`
- **File hints:** smartsched/frontend/src/components/import/crbs-upgrade.tsx; backend CRBS importer roles step

### R1-M-37 (suggestion) The desktop login leaves two thirds of the screen as an empty gradient; translucent sheets reduce legibility
- **Step:** Generic look on login and glass sheets
- **Action:** Opened /login at 1440 and the user sheet on a phone.
- **Result:** Left card, the rest an empty pastel gradient; sheets show the content behind them.
- **Expected:** Use the space for the institution (logo, name, a short help line), and opaque sheet surfaces by default.
- **Repro:** /login.
- **Evidence:** `shots/F12-S12-login-sso-on-desktop.png`, `shots/F11-S01-filled-phone.png`
- **File hints:** login page layout, sheet surface tokens

### R1-M-38 (suggestion) Week export file name, filters in URL, pin-template accessible names, busy labels
- **Step:** Small polish
- **Action:** Exported week 4 and the term; filtered users; opened the pin template; saved a user.
- **Result:** Both files are named 'smartsched-run7.xlsx' (week file 1 sheet 'Hafta 4', term file 14 sheets: M-32 fixed). User filters are not kept in the URL. Pin template room checkboxes are named 'A 10158 koltuk' (code and seats run together). 'Oluştur' keeps its label while busy (aria-busy only).
- **Expected:** 'smartsched-run7-hafta4.xlsx'; ?role=…&q=…; 'A 101 · 58 koltuk'; 'Oluşturuluyor…'.
- **Repro:** As described.
- **Evidence:** `shots/F10-S09-export-menu-desktop.png`, `shots/F09-S04-pin-template-desktop.png`
- **File hints:** timetable export naming, users-admin.tsx query string, template-gallery pin list

