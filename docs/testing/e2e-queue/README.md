# E2E checks queued for the single e2e lane (resource rule, 2026-10-18)

Each lane lists the browser checks it could not run. The e2e lane runs them one stack at a time
(`scripts/record/stack.sh up`, fresh seed), at 1440 mouse and 390×844 touch, tr-TR, and reports per item.

## RF-1 (catalogue, enrolment, invite e-mail) — script rf1.mjs, stack 19800/19801, REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0
1. /admin/catalog: edit an instructor's name, a course's code (search "ACU 1421"), a programme's name and a section's
   "Öğrenci sayısı"; each survives a reload; phone 44 px targets, 16 px inputs, no sideways scroll.
2. RF-01 /classes: edit the "Öğrenci" cell, reload, the value stays; a `section.update` row in /admin/audit.
3. RF-03 /admin/users › Davet et: without SMTP the switch is off and disabled with "E-posta ayarlanmadı" and a link
   to /admin/email; with SMTP it is on and the invite mail is sent.

## WG-F (welcome guide) — specs e2e/wg-*.spec.ts (helpers e2e/wg-helpers.ts); 1440 mouse + 390×844 touch, tr-TR, Europe/Istanbul
1. wg-sheet.spec.ts, then MOBILE M-01/02/03/05 on /reserve with the sheet open.
2. wg-tour.spec.ts, plus a bundle check that the tour chunk is not in /reserve's first-load JS (needs `next build`).
3. wg-checklist.spec.ts, then M-01/02/03/05 on the Daha tab.
4. wg-hints.spec.ts, plus axe on the hinted pages.
5. wg-admin.spec.ts, then M-01/02/03/05 on /admin/welcome.
On pass: tick WG-04..08 `[x]` in docs/ROADMAP.md.

## Sweeper (ops backup card)
1. /admin/ops shows the "Yedek" card with "Son yedek: …" (desktop + phone).
2. After writing a 30-hour-old timestamp into /var/lib/smartsched/textfile/backup.prom, the card turns to a warning.

## CAL-F (calendar export) — e2e/cal-export.spec.ts, E2E_REAL=1, API 19750 / web 19751
1. T1+T2: 3 taps to a link. T14: Kaldır → the link 404s and focus moves to the next row. T13: another department's
   card is closed with its reason; a forged request gets 403 `department_not_allowed`.
2. CAL-07: /profile?calendar=error&provider=google&reason=account_not_verified&domain=uni.edu.tr shows the Turkish
   sentence (no raw code) and the old panel is closed. CAL-09: the admin export block, co-instructor names off by default.
3. MOBILE M-01/02/03/05 on /profile; the W3-HUB e2e test 4 (setup-sheet embeds).
On pass: tick CAL-08/09.

## AS-B (adaptive backend; API checks on one stack)
1. RF-02/AS-01: seed + weights set in Ayarlar; runs from POST /runs, Studio and moderation re-solve; GET /runs/{id} stats show
   `seed.source=settings`, `weights_source`, `profile`.
2. AS-02: a TERM run of Bahar has no classes in the Final/BÜT weeks; `stats.horizon_skipped_weeks` lists them.
3. AS-03/04: profile draft → activate → run (profile in stats) → revert; booking in an exam week is refused with "Final haftası profili …".
4. AS-10: what-if +10 % with `solve:true` creates an inactive draft run "Senaryo: …".
5. AS-13: learning refresh, then revert to a version; the term stays pinned to it.
6. AS-18: import a grid with a "Vize haftası" sheet; /seasons/terms/{id}/periods lists a draft segment.

## VO-F (voice UI)
1. e2e/vo-admin.spec.ts (3): sync the stub provider, save the voice_stt route (only stt models listed), provider voice test
   preview "Şu cümle çok önemli…"; a second admin sees the same route; MOBILE M-01/02/03/05 on /admin/ai.
2. e2e/vo-mounts.spec.ts (9) with Chromium's fake mic (--use-fake-device-for-media-stream --use-fake-ui-for-media-stream,
   grantPermissions(['microphone'])): consent sheet on first use; chat/write-it/upload paste/guard bench put the transcript
   into the box, never auto-send; permission_denied copy; 429 copy; spoken injection refused; provider error; focus never on <body>.
3. Behind nginx: `Permissions-Policy: microphone=(self)`; getUserMedia succeeds; a ~5 MB raw clip to
   /api/v1/ai/voice/transcribe does not get 413 (nginx allows 6 MB on that path).
On pass: tick VO-06/07/08 and VO-05.

## AU-B sessions + IdP MFA (one stack, UVICORN_WORKERS=2)
1. Sign in on desktop (1440) and phone (390×844 Safari UA); GET /auth/sessions on the phone: 2 rows, one current,
   "Safari, iPhone", network x.y.z.0/24.
2. On desktop, delete the phone session: the phone's next request gets 401 at once (repeat ~10× to hit both workers).
3. "Diğer cihazlardan çıkış yap": every other session gets 401, the current one keeps working.
4. Admin POST /admin/users/{id}/sessions/revoke and, separately, the admin MFA reset: the target gets 401 everywhere; audit rows present.
5. Fake OIDC IdP, policy required_for_roles covering the role, amr=["pwd"]: switch on → refused with Turkish
   `idp_mfa_required`; switch off → succeeds, `idp_mfa_missing` notice once; amr=["pwd","mfa"] → succeeds, no notice.

## RF-2 (mail follow-ups)
1. /bookings/mine?series=<sid>&booking=<bid> lands on /my-bookings with that booking's sheet open; closing doesn't reopen; the URL is cleaned.
2. /my-bookings?series=<sid> opens the series' earliest upcoming booking.
3. /bookings?date=<d>&series=<sid>&booking=<bid> opens the grid's detail sheet.
4. Settings › Genel › "E-posta bildirimleri": 2 h saves (toast, focus on Kaydet); 337 and "2,5" give an inline error with
   focus on the field; the new-device switch off is saved; phone 16 px / 44 px; MOBILE M-01/02/03/05 on /settings, /my-bookings, /bookings.
5. FakeSMTP: with all of a person's mails muted, a new-device sign-in still mails with the "kapatılamaz" footer; calendar
   consent on/off and a Google connect/disconnect each mail; Profil › Bildirimler doesn't list these events.

## Charts (CH-01..09)
1. `next build` route table vs the pre-CH-01 baseline: routes without a chart +0 kB; /dashboard and /admin/ai ≤ +110 kB gz;
   the lazy ECharts chunk ≤ 240 kB gz (esbuild 229.2 kB).
2. A full vitest run (CH-09).
3. e2e/charts-a11y.spec.ts at 1440 and 390 touch.
4. /dashboard as Fatih Bey: chart, summary, table toggle, CSV in a tr-TR parser; M-01/02/03/05.
5. /admin/ai: tooltip on tap, CSV with 5 feature columns + total; M-01/02/03/05.
6. /admin/ops: tooltip scrub without dropped frames, stale strip, backup card; M-01/02/03/05.

## Mobile A (scripts: scratchpad/mobile-a/scripts run.mjs, extra.mjs, chrome.mjs)
1. M-13 at 844×390 on every app route and /reserve with the new snippet: ratio ≤ 0.25 at rest and after a 300 px scroll; /reserve content ≥ 0.60.
2. M-15 CLS ≤ 0.1 on /profile, /public/buildings/A, /public/rooms/A101, /bookings at 768.
3. M-16 INP ≤ 200 ms opening the book sheet, filters and bell at 390.
4. Root 200 % at 390: no sideways scroll; body text ≥ 26 px.
5. 320×568: tab labels and the date chip are not clipped; M-02.
6. Grabber: a 500 px drag dismisses, the backdrop fades, focus returns.
7. Keyboard proxy: book-submit bottom ≤ 508 with the visual viewport at 508 (+ a real iOS 26 device if one is available).
8. Safe area (notch 59): kiosk content left ≥ 59.
9. The hosted Motion Agent polish of book sheet open + drag (orchestrator go given; name it in the report).
7. AS-18 live: upload a grid with a "Vize haftası" sheet in the council and commit → /seasons/terms/{id}/periods lists a draft MIDTERM segment.
8. /analytics/forecast: a new term of a published season shows the "düşük güven" badge and wide ranges.

## Mobile B (390×844, 768×1024 touch, 844×390 landscape; tr-TR)
1. CLS ≤ 0.1 (buffered observer from navigation) on /runs/<id>, /generate step 2 (phone+tablet), /onboarding/1, /moderation (all tabs),
   /exams/invigilation, /admin, /admin/audit with filters, /dashboard, /admin/ai (overview, providers), /settings?tab=integrations, /admin/ops.
2. M-05 run-publish at 768: 44 px, fixed, not covered at scroll 0/400/end; publish sheet at 844×390: confirm visible; Escape → focus on run-publish.
3. M-07/M-02 at 768: Studio step-2 cards and /classes cards show 0 targets under 44 px.
4. M-04: Studio filters sheet is a bottom sheet at 390, ≤ 640 px wide at 768; filters-apply works.
5. Timetable at 768: toolbar 44 px; column-tag ≥ 12 px; Escape from the inspector → calendar-event chip.
6. Root 32 px at 390: scrollWidth ≤ 390 on /generate step 1, /analytics/heatmap, /admin/rooms, /runs/compare (and the charts PeriodPicker wraps).
7. M-05 at 390: compare-apply after picking a pair, recreate-open, invig-new, group-new.
8. M-10 at 768: /admin/users new-user dialog is one column, each ≥ 280 px.
9. Studio step 3 with a rule switched off: contrast ≥ 4.5:1 light and dark.
10. Hosted Motion Agent fix: publish → "✓ Yayında" (run-published-check).

## AUX-F (sign-in, 2FA, passkeys) — e2e/au-signin-security.spec.ts, Chromium, serial, CDP virtual authenticator, TOTP computed in the spec
1. §16.6 setup in ≤ 3 steps, the .txt name, "Bitir" only after the tick, the warning when closing at step 3.
2. §16.1 second step without a reload; a pasted "123 456" submits; a wrong code clears the slots and keeps focus.
3. §16.2 remember this device; the sessions list shows no network; "Diğer cihazlardan çıkış yap".
4. §16.4 add a passkey, rename it, use it as the second step. 5. §16.3 a recovery code works once.
6. §16.7/8/9/12 (390 px) once A5/A6 are mounted; AUX-03 autofill + Conditional Create; motion-audit sign-in-security;
   MOBILE M-01/02/03/05 on /login, /login/verify, /profile#security.

## AS-S (solver) — after AS-B's merges and AS-17
1. Gracious stack: a profile with peak_smoothing > 0, run Bahar week 3: the run header shows the weight; placed count and hard score match the off run.
2. A term with a published course run: a midterm exam request in lecture week 8 in a room a class holds → the exam lands elsewhere; the course run's data issues list `exam_overlap`.
3. /exams with the Final term: the advisor panel shows the 3 June peak-day card and ranked moves; accepting one lowers the count on refresh (1440 + 390 touch).
4. Planner: 5+ manual moves in a child run, then POST /learning/weights/propose → a draft "learned" profile in /admin/weeks that changes no run until activated.
7. Users list: 2FA tag and filter for on / pending (before and after the first sign-in) / an IdP-only user with no tag.
8. Policy screen counts change after one person enrols. 9. Profil › Güvenlik › Uygulamayı değiştir: the old code works until
   the new one is confirmed, then fails; recovery codes still work; the `mfa_app_changed` mail arrives.
10. The sign-in page shows the "iki aşamalı doğrulama" wording for idp_mfa_required.

## Added 2026-10-18 09:35 UTC

- **AS-F** (1440 mouse and 390×844 touch, tr-TR): `e2e/as-seasons.spec.ts`, `e2e/as-analytics.spec.ts` (gracious and empty stacks), `e2e/as-surfaces.spec.ts`. Steps are in the AS-F hand-off (PROGRESS row `as-f`): draft, activate and revert a profile on /admin/weeks with focus on the row; peaks tab P4/P8; "düşük güven" beside forecast ranges; a what-if draft-run link; the needs texts on an empty stack; the find-room peak chip on Wednesday P4; the advisor card for the Final term; "Profil:" in the run header; `slots` mode saves; Öğrenmeyi yenile and Bu sürüme dön.
- **AS-B API checks:** an EXAM run shows `stats.class_plan` and no exam takes a room a class holds; the course run's data issues show "Sınavla çakışan dersler"; `/analytics/forecast/exams/advice` answers on Final 2026; POST `/learning/weights/propose` after 5 or more edits creates a draft profile.
- **AUX-F:** `e2e/au-signin-security.spec.ts`: the 2FA tag and filter on /admin/users, the live policy sentence with counts, and "Uygulamayı değiştir" (an old-app code is refused).

## Added 2026-10-18 09:55 UTC

- **RF-M:** RF-04 phone month arrows on /timetable (390×844: › twice, ‹ once, 44 px, Yerleşmeyen counts match desktop, focus stays on the arrow); RF-10 density (Sıkı → compact room columns 112 px; toolbar override survives reload).
- **AUX-10:** `e2e/au-signin-hero.spec.ts` (one pass ≤ 5 s, no loop, reduced motion shows the poster and downloads no player, nothing at 390).
- **HB-02:** p95 of `GET /helper/search` under 50 ms on the seeded stack, 4 personas. HB-A cases 2–4 (confirm, result, undo; `/helper/status` reasons; notes withdrawn with `ai_personal`).
- **Council full re-run** (round-3 lane C's final run was lost): run it once on the gracious stack and record the result.

## Added 2026-10-18 10:05 UTC

- **WG-09** (1440 mouse and 390×844 touch, tr-TR, reduced motion on and off): first sign-in as academician shows the sheet in about 240 ms and quick-reserve plays once then rests; reopening shows only the poster; reduced motion downloads no lottie chunk. Cards settle by 240 ms; the tour ring follows 1:1 while scrolling, and the scrim must not flash between steps; the checklist tick takes 240 ms; reduced transparency makes surfaces opaque. Add a `welcome` block to `e2e/motion-audit.spec.ts` (sheet open, tour step, checklist tick: ≤ 3 dropped frames, no finite animation over 300 ms except the Lottie).

## Added 2026-10-18 10:20 UTC

- **RF-B** (seeded gracious stack): /import lists the seven seeded workbooks as "İlk kurulum (sistem)" with report and download; edit A102 capacity, remove PC from A103, rename a programme, edit and archive an exam, edit the row-431 rule, set week 1 to Tatil, re-import each file, and every edit survives; exam-list preview with one changed cell shows the conflict, "Uygula" applies once and a second apply is refused; `PUT /period-grid` P1 → 08:00 shows on the timetable, find-room and a "from grid" booking period, also on a second worker within 30 s; the users 2FA filter returns matches beyond page 1 and never IdP-only users.
- **CH-M:** /runs score line (≥ 3 finished runs; dot tap and ←/→ Enter open the run); /admin/audit daily chart and the phone toggle; /my-bookings and /profile tiles with no ECharts chunk requested. Update `e2e/loop-r2-laneB.spec.ts:140` (removed `mine-totals` sentence → tiles).

## Added 2026-10-18 10:35 UTC

- **Sweeper 2** (390 touch, M-05/M-02; 1440 unchanged): Save sits in the capsule above the tab bar at scroll 0/400/end on `/admin/ai?tab=limits`, `?tab=models`, `/programs/new` with and without drafts, `/settings?tab=ai` with and without a key. Fix 15 re-measure: Studio "İleri" at 390, "Şablondan seç" at 768, timetable "Filtreler" at 390 (worst long frame ≤ 200 ms; take a trace for Filtreler). A5: Yoğunluk Sıkı → table rows 32 px on /classes (> 80 rows) with no gaps; Rahat → 44 px. `/grafana/`: admin 200, teacher 403, signed out 302. Run chat: a second message keeps earlier context (live model).
- **Pod CI:** the first gracious deploy after this tree installs the backend with `--require-hashes` (hashed locks); watch the backend gate on arm64.

## Added 2026-10-18 10:48 UTC

- **IDP** (1440 and 390, tr-TR): Profil › Güvenlik link Keycloak (mock issuer `e2e/w3-idp-mock-issuer.py`) → "bağlandı" → unlink with password, focus on "Bağla", toast; the same with a SAML IdP and an encrypted assertion through the ACS; `?error=already_linked&provider=keycloak` shows on the Keycloak row only; admin with a federation certificate and unsigned metadata → provider "error" with the Turkish reason.

## Added 2026-10-18 10:55 UTC

- **RF-C:** /admin/schedules P1 → "08.00"–"08:40": a period habit ("sabah saatleri") in learning suggestions/priors shows "(08:00–13:20)", reset shows "(08:30–13:20)". On a stack seeded before RF-06 (or with `imported_snapshots` rows for entity 'exam' removed): edit a BME 419 exam head count, re-import a Final list where that cell differs as a preview → one conflict (planner, file, previous import); apply keeps the edit and `summary.extra.rebuilt_import_values.from_audit ≥ 1`.

## Added 2026-10-18 11:00 UTC

- **RF-F** (`e2e/rf-f.spec.ts` + the smoke import step; 1440 and 390, tr-TR): /import planning list preview → wording → Uygula → report, a second apply via API → 409, history "Önizleme · uygulandı" / "Yükleyen:" / "İlk kurulum (sistem)", download is .xlsx; exam list conflict row mine / file / previous ("bilinmiyor" on older data), Gelişmiş › "Dosyadakini al"; /admin/schedules 18 rows, P3 09.00 error at P3, 08.35 survives reload, "Varsayılana dön" restores 08:30; /admin/weeks week 14 → Tatil with badge after reload, duplicate week 1 refused inline, "Dönem profilleri" below; /admin/users 2FA filter sends `mfa_state` with offset 0 and the total matches; phones 44 px / 16 px, focus never on `<body>`.

## Added 2026-10-18 11:05 UTC

- **HX helper** (1440 and 390, tr-TR, one stack): admin index mode, "periods" finds Ders saatleri and Shift+Enter rings it, 0 `ai_usage` rows, trigger named "Ara veya sor (Ctrl+K)"; academician "kullanıcı davet" gets no admin hit; the sheet opens from ⌘J and the palette, Esc returns focus, F6 cycles; Rehber modu works without a model; at 100 % the composer is disabled; MOBILE M-01/02/03/05 on /reserve; academician "Yarın 10:00 için A 204'ü ayır" → confirm → click → the booking exists → "Geri al" cancels it; a taken slot says "Bu saat az önce doldu."; a request-mode room reads "Talep et"; `helper.action.*` audit rows exist and nothing is written without the click; staff approve and reject with a reason; Göster on "Tatil ekle" and "Davet et"; memory: add and delete a note, delete history, DSR export lists notes and threads, withdrawing `ai_personal` empties notes; admin tab: `create_booking` off → academician gets a nav card; "Yalnızca dizin" → 0 `ai_usage` rows. Spec fixes: `wave1.spec.ts:94` → `helper-trigger`; `loop-r1-laneA.spec.ts:268` → "Ara veya sor (Ctrl+K)"; testMatch `hx-[a-z-]+`.
