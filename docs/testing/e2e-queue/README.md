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

## Added 2026-10-18 11:10 UTC

- **IDP-2** (1440 and 390, tr-TR): YETKİM (SAML) wizard step 3, Gelişmiş closed by default; federation certificate saved, then re-read shows the details and "Meta veri imzalı ve doğrulandı"; removing it puts focus on the textarea. Unsigned metadata with a certificate set opens Gelişmiş by itself with the Turkish reason. "SP anahtarı oluştur" shows "Anahtar kayıtlı" + SHA-256 with focus on Kaldır; the SP metadata has an encryption KeyDescriptor; the private key never appears on screen or in the network. A mismatched pasted pair is refused. "İstekleri imzala" without a key → 422 text; with a key `/start` carries SigAlg and Signature; Kaldır while signing → 409 text. Mock IdP: AES-CBC in an unsigned Response is refused with the TR hint and an `assertion_encryption` row; signed Response passes and the row clears; GCM with an unsigned Response passes. M-01/02/03/05 on step 3.

## Added 2026-10-18 11:15 UTC

- **HB-D** (1440 and 390, tr-TR): "bunu hatırla: Pazartesi B blok" → confirm card → "Hatırla" → result → "Geri al", and Profil › Yardımcı notes update; memory off and no-consent each give a refusal card; turns from /my-bookings and a booking detail carry `context`; "Son işlemler" with "Geri al"; "Geçmişi sil" keeps notes; faculty usage shows a percentage.

## Added 2026-10-18 11:20 UTC

- **HX-18** (one stack; tr-TR): M1 at 1280/1440, "Göster" on `admin-users-invite` moves the sheet aside, the target can be clicked, "Yardımcıya dön" reopens with the thread (left-side anchor: sheet stays). M2 keyboard "Vazgeç" on confirm/form/choice puts focus on "Vazgeçildi.", never `body`; Enter on confirm keeps focus while "Kaydediliyor…". M3 dark result discs ≥ 3:1. M4 at 390 and 1440, Rehber modu "rezervasyon" shows ≤ 6 one-line rows (≥ 44 px, 56 px on phones) and ≤ 1 primary in view. M5/M6: "Devam" → "Rezerve et: …"; an expired card shows one "Yenile", the old one "· eskidi". M7: "Sohbet geçmişini sil" keeps notes; "Tüm notları sil" removes only notes. M8: `/ai/faculty` never says "token". m12/m13 at 390: the target sits in the upper half; status chip 24 px tall with a 44 px tap area; M-01/02/03/05 on /profile and the sheet. m2: forced colours keep "Düşünüyor…" visible.

## Added 2026-10-18 11:45 UTC

- **Shell integration** (1440 and 390, tr-TR): /admin/ai?tab=helper renders; Limitler › Fakülteler: an allowance and split, a department sum over the allowance → inline Turkish message and Save disabled, valid values survive reload, strict + faculties over the org budget → 422 inline; faculty manager sees "Fakültemin yapay zekâ kullanımı" and /ai/faculty (admin and academician don't); user menu and Daha › Yardım › "Yardımcıya sor" open the sheet, focus returns, hidden when the helper is off; Göster on all 18 anchors (admin-users-invite, admin-holidays-add); `/runs/<id>?publish=1` and `/runs?publish=<id>` open the dialog without changing the run until confirm; `/admin/users?invite=1&email=a.k@uni.edu.tr&name=A.%20K.&role=TEACHER&department=<id>` opens prefilled and nothing is sent without "Davet et"; `/runs/<id>?chat=MAT%20112` prefills only. RF-16: P1 = 08:00–08:40 shows on the timetable gutter, day timeline, move dialog, classes filter, find-room default window and Rooms; a 500 on /period-grid shows the built-in times (after RF-16b: no skeleton, late grid updates in place). `E2E_REAL=1 npx playwright test e2e/motion-audit.spec.ts -g helper` with reduced motion on and off. M-01/02/03/05 on /admin/ai?tab=limits and /ai/faculty.

## Added 2026-10-18 11:50 UTC

- **HB-E:** helper `search_site` "takvim" lists Profil › Takvim (1440 and 390, tr-TR); "B 406 perşembe 13:30" reaches a confirm card with the resolved P7; /admin/ai providers tab shows the `context_unverified` warning text in TR and EN on desktop and phone.

## Added 2026-10-18 12:00 UTC

- **RF-16b** (1440 and 390, tr-TR): first visit with empty localStorage and `/api/v1/period-grid` delayed ~3 s, /timetable, /classes, /find-room show content at once, then times read 08:00 without reload, focus and scroll kept, localStorage holds the grid; reload shows 08:00 on first paint with no 08:30 flash; a 500 with a cached grid keeps the cached times, no toast; /find-room untouched start/end/window move to the new grid, typed values stay; day timeline and agenda update in place; /settings CLS 0 when the grid arrives; M-01/02/03/05 on the three screens.

## Added 2026-10-18 12:30 UTC

- **HX-15/16/17** (1440 and 390, tr-TR): confirm a helper booking, then the empty palette and the sheet show "Son işlemler" (label, time, status); "Geri al" undoes and the row reads "Geri alındı"; a stale undo shows the 409 text; no group without actions; 44 px targets. The "Bu sayfa" chip on /reserve, /rooms/<id> and /profile#ai-usage shows the right title, `/turn` carries `context` until ✕, and a page the person may not open shows no chip. "bunu hatırla: Pazartesi B blok" in AI and index mode → confirm → note listed in Profil › Yardımcı → "Geri al" removes it; without consent → refusal; "Not ekle" without consent shows the text and the Gizlilik link. Hand-over buttons open calendar, invite and publish; Göster for "Planı yayınla"/"Dışa aktar" from /runs lands on the run and rings the button. "yarın 13:30 A 204" from a shortcut and from the form; 21:00 and an off-grid minute show at the time field; the confirm card shows the period. M-01/02/03/05 on the sheet and the palette.

## Added 2026-10-18 12:45 UTC

- **HX-19** (`E2E_REAL=1 npx playwright test e2e/motion-audit.spec.ts -g "HX-19"`; 390×844, isMobile, hasTouch, tr-TR, CDP touch): a drag past 30 % closes ≤ 260 ms after release, focus on the opener; reduced motion closes ≤ 80 ms; a slow 120 px drag springs back within 600 ms and its trailing click doesn't close; a 90 px flick in 50 ms closes; keyboard ✕ "Kapat" and Esc ≤ 260 ms; the handle is ≥ 44 × 44, named, and not a Tab stop. Re-run "motion audit: helper" (desktop exit now uses tokens). Manual look on a real iPhone: the handle next to the long Bulut status chip.

## Added 2026-10-18 13:00 UTC

- **CAL-13** (needs a published Final exam run and an activated invigilation plan, `stack.sh runs`; 1440 and 390, tr-TR): academician with duties, Profil › "Takvimime ekle" shows "Sınav görevlerim" with its upcoming count → Takvim bağlantısı → the approve step says "…diğer gözetmenlerin adları gönderilmez." → tick → Onayla ve ekle → webcal/Google/Outlook links; focus on the heading at each step; 44 px targets. Subscribe `duties.ics`: "Gözetmenlik · …" at the right Istanbul times and rooms; re-solve + publish gives no duplicates; removing the subscription → 404 on the next poll. File download `sinav-gorevlerim-<term>.ics`. Admin Ayarlar › Takvim scope switch off closes the card. M-01/02/03/05 on /profile.
- **BUG-01/02:** /find-room Sunday 22.02.2026 shows no "Boş", the alert "1 tarih kapalı (Pazar rezervasyona kapalı)", and "Dolu olanları da göster" gives "Kapalı" with no 500; Friday–Sunday offers Friday only; an old closed-day card toasts "Bu gün rezervasyona kapalı"; holiday 23.04.2026 gives the Turkish text; /admin/audit booking.move shows "Derslik"/"Ders saati"/"Kişi" and "A 101 → A 106"; a teacher sees only her own name.

## Added 2026-10-18 13:55 UTC

- **FIX-B** (390×844 touch, tr-TR): CLS ≤ 0.1 with the welcome sheet dismissed on /dashboard (was 0.48) and /admin (0.43), with and without the "Başlarken" card, /settings?tab=integrations (0.41), /exams/invigilation (0.12), /reserve (content within ~1.5 s of /me); M-05 on /settings?tab=general: `mail-notices-save` and `security-contact-save` become the capsule after a change and don't overlap; /my-bookings?series=1 after /bookings/mine?series=1&booking=3 ×5 with no React #418; root 32 px at 390: /find-room and /my-bookings scrollWidth ≤ 390, /generate step 3 `bar-generate` right edge ≤ 390, /analytics/heatmap ≤ 390; M-09 at 320 and 390 in TR and EN: no ellipsis, items ≥ 44 px; /timetable at 768 column-tag ≥ 12 px; phone lens menu closes after "Ay" with focus on the menu button; `e2e/au-signin-hero.spec.ts` ×3: longest frame while typing ≤ 50 ms; M-01/02/03 on /settings, /dashboard, /admin, /find-room, /my-bookings.

## Added 2026-10-18 14:05 UTC

- **FIX-C** (1440 and 390, tr-TR and en): /login, /reserve, /dashboard first paint with no message keys and no hydration error; palette language toggle and profile language switch; /admin/welcome texts in both languages; lazy shell: ⌘K palette, "?" shortcuts, ⌘J helper and "Göster", welcome sheet on first sign-in, KVKK notice gate; bundle re-measure (`$E/bundle.py`; /dashboard ≈ 552 kB gz first load, /login ≈ 421); `e2e/charts-a11y.spec.ts` at both sizes, axis text 12 px on /dashboard, /admin/ai?tab=usage, /admin/ops; AI usage CSV has 5 features + Toplam; `e2e/wg-admin.spec.ts:67` ×3 (with the delta "Güncellendi" fix); `e2e/vo-admin.spec.ts` item 1 (Turkish failure sentence); `e2e/vo-mounts.spec.ts` test 3 (422 and text kept) and test 1 ×4 on fresh stacks.

## FIX-A (2026-10-18): session revoke, horizon, council merge/term, taken-slot copy
- AU-B 3b: sign in on A and B, use only A, `POST /auth/sessions/revoke-others` with A → `GET /auth/me` with B = 401, A = 200; repeat with `uvicorn --workers 2`.
- AS-B 2: `POST /runs {term_id:1, kind:COURSE, horizon:TERM}` → `stats.horizon_skipped_weeks` = [16,17,18,19], no class in weeks 16–19.
- Council full re-run (7 fixtures): Güz group shows 2026-GUZ / term_id 2 and commits into term 2 with no new term; the NERMİN person_merge pair is blocking before the first commit; no surprise 409.
- HB-02: a slot taken between card and confirm → the card shows "Bu saat az önce doldu.".
- Commit panel: how a blocking plan item with `term_candidates` looks (no dedicated UI yet; editing the code works).

## FIX-D (2026-10-18 14:40 UTC): HB-18 helper and sign-in findings

Browser checks for docs/testing/round4/2026-10-18-hb18.md (unit level done; every row at 1440 mouse and 390×844 touch,
tr-TR, **timezoneId Europe/Istanbul** unless noted):
- **HB18-F01:** as `akademisyen.ayse`, ⌘J (phone: Daha › Yardımcıya sor), "yarın 10:00 A 204" → the shortcut → the card reads "Rezerve et: …", not "Bu öneri eskidi."; click it → booking + result line; "Geri al" is offered and works. Same for "bunu hatırla: Pazartesi B blok" with consent. The palette's "Son işlemler" shows "az önce", not "3 saat önce". `GET /helper/actions/recent` and the card's `expires_at` end in "Z".
- **HB18-F02 (security):** open /login with the host loaded, type username + password and press "Giriş yap" (and Enter) before hydration (throttled CPU / delayed JS): the URL never holds `password`; the button is disabled until hydrated; a native submit goes `POST /api/auth/no-script` → 303 back to /login. Visiting `/login?username=x&password=y` redirects to `/login` without them (and `/reset-password?token=…&new-password=…` keeps only the token). Same pre-hydration check on /login/verify (MFA), /reset-password (both steps), the invite set-password page and /login/change-password. Server and nginx logs show no `password=`.
- **HB18-F03:** UTC or Istanbul: confirm card "yarın 14:30 A 204", another user books the slot, click "Rezerve et" → "Bu saat az önce doldu.", no "Rezerve et", "Başka saat öner" (opens the free-room form for that day) and up to 3 "B 101 · 40 kişilik" rows (each gives its own confirm card); focus never on `<body>`; an already-clicked token reads "Bu işlem zaten yapılmış.".
- **HB18-F04:** 390, "takvim" → "Takvimime ekle · Profil › Takvim" → after Profil's sections load the target sits in the upper half, ringed, not under the step card; if the section re-mounts the ring follows.
- **HB18-F05:** as `planlamaci.test`, ⌘K "planı yayınla" → Nerede? row: lands on the newest finished **unpublished** run (#8 on the gracious data) and rings Yayınla; with only a published run the card says the button is missing and lists the steps. Check whether the "'Planlama yönetimi' izni" toast still appears on that run page (not fixed here: see the report).
- **HB18-F06:** /admin/audit as `yonetici.test`: İşlem "helper.*" and Kayıt türü "Yardımcı işlemi" list the helper rows; rows read "Yardımcıyla rezerve edildi · #5", "Onay reddedildi (geçersiz onay)", "Not kaydedildi", "Sohbet geçmişi silindi"; no English or raw codes.
- **HB18-F07:** /admin/ai?tab=helper: switch an action, Kaydet → `document.activeElement` is Kaydet (also after a stale-save 409).
- **Minors:** F09 Göster from the sheet then "Yardımcıya dön" keeps "davet"/"takvim" in the guide field; F11 no "Shift Enter" keycaps on page rows at 390; F12 Göster "Tatil ekle" rings the "Ad" field; F13 `POST /helper/turn {text:"evet"}` in index mode → refusal "Onaylamak için karttaki düğmeye basın."; F14 a Göster step card left open closes when the sheet opens (focus in the sheet); F15 `E2E_REAL=1 npx playwright test e2e/motion-audit.spec.ts -g helper` in index mode passes the close step (guide field); re-check F08 (500 ms animation, 7 blur surfaces) there.

## FIX-F (2026-10-18): AS-20 and CH-12 findings

Browser checks for docs/testing/round4/2026-10-18-as20.md and -ch12.md (unit level done; 1440 mouse and 390×844 touch,
isMobile + hasTouch, tr-TR, Europe/Istanbul):
- **AS20-F02:** `planlamaci.test` → /analytics/heatmap › Yoğun saatler, Güz: basis "2 haftanın …", "düşük güven", P4/P8 cells around 85–92 % and listed as peaks; `GET /analytics/peaks?term_id=2&group_by=campus` → `weeks` [1,2]. Bahar (published) unchanged. /analytics/forecast Güz numbers re-read (the term cube no longer counts empty weeks).
- **AS20-F03:** `akademisyen.ayse` → /find-room Wed 21.10.2026 11:00–11:40, 40 kişi → "Yoğun saat" chip + "Daha sakin: …" at both sizes; the page calls `/analytics/peaks/campus` (200), never `/analytics/peaks` (403).
- **AS20-F04/F05:** /exams/advisor › Final 2026: the 3 Haziran peak card first and full width, ≤ 5 cards and ≤ 10 moves, "Tümünü göster (n)" reveals the rest; move PRO206 3 → 1 Haziran with "Uygula" → toast "PRO206 1 Haziran 2026 Pazartesi gününe taşındı." → advisor peak 126 → 125 → "Geri al" restores 3 Haziran (and 126); /admin/audit shows two `exam_request.update` rows; a LOCKED exam gives "Kilitli bir sınav taşınamaz…". "Talebi düzenle" opens /classes on the Final term with the row open. Focus never on `<body>`; 44 px buttons at 390.
- **AS20-F06 (re-measure):** /analytics/forecast at 390 in a real touch context: `matchMedia('(pointer: coarse)').matches` true, then M-02/M-03 (selects 44 px / 16 px, wi-pct 16 px, segments ≥ 44, Senaryoyu hesapla ≥ 44). If it still fails, record the computed `--control-h-md`.
- **AS20-F07:** /runs/9 (scenario draft) shows "Senaryo taslağı · Senaryo: +10 % kontenjan" under the verdict; a normal run shows nothing.
- **AS20-F08:** /admin/weeks: an active test profile v1 → "Kullanımdan kaldır" → confirm "… kullanımdan kaldırılsın mı?" → Kaldır → toast, focus on the next row, row listed as Eski.
- **AS20-F10/F11/F12:** Öğrenmeyi yenile ×2 at 1440 → focus stays on the button; "Bu sürüme dön" onto the current version → toast "N. sürüm zaten geçerli olanla aynı; yeni sürüm yazılmadı." and no new version row; onto an older different version → "N. sürüme dönüldü." and the list updates within a second; dialog title "N. sürüme dönülsün mü?". Düzenlemelerden ağırlık öner → focus stays.
- **AS20-F14:** empty stack: /analytics/forecast and /exams/advisor show "Henüz dönem yok. Önce …" + "İçe aktar" (→ /import), no empty select.
- **CH12-F01:** `yonetici.test` → /admin "Bu dönem": Haftalık rezervasyonlar / talep sonuçları list 14 Güz weeks, the 22–23 Oct C 606 requests counted, the current week marked; `GET /bookings/stats/weekly?term_id=2` → `to` = the term's last week.
- **CH12-F03/F05/F06:** peaks profile chart summary "Gün içinde en yoğun saat N. ders." on Güz; M-02 at 390 on /dashboard KPI numbers, /runs table links, /profile "Profil › Bağlı kanallar" and "Gizlilik bölümüne git" (hit area ≥ 44); `emulateMedia({media:"print"})` on /dashboard: no sidebar, top bar or tab bar.

## Added 2026-10-18 15:10 UTC

- **FIX-E** (round-4 majors; 1440 mouse and 390×844 touch, tr-TR, Europe/Istanbul; a Sunday clock where it says so):
  - **/bookings on a Sunday** (`akademisyen.ayse`): with no `date`, Gün and Salona göre open on Monday (the coming week); `?date=<Sunday>` shows "Bu gün rezervasyona kapalı." with "<Pazartesi …> gününe git", no blank grid; "Sonraki hafta" from a Sunday goes to the coming Monday, never +2 weeks; a past day's cells read "Geçmiş".
  - **/find-room**: on a Sunday the date field starts on Monday and the first "Ara" finds rooms; at 1440 only Ne zaman, Saat, Kaç kişi and "Ara" above the fold, the rest under "Gelişmiş" (opens itself when a filter is set); phone "Filtreler" sheet now also holds "Sınav".
  - **/my-bookings › Takvime eşitle** with links made on another device: no filled button; "Özel bağlantıyı sıfırla" under "Gelişmiş", outline, confirm names the effect; one date said once.
  - **/reserve at 1440**: after "Rezerve et" `document.activeElement` is `qr-receipt-title` (not BODY) for 3 s; after "Geri al" (receipt and toast) it is the booked room's row.
  - **/runs/7 and /runs/3 as `planlamaci.test`**: no "Bu işlem için yetkiniz yok" toast, no 403 in the console; at 390 the "Yayınla" capsule is free (M-05). #7: only "Yayınla" is filled; bars read "547 puan kaybı". #3 (imported board): "İçe aktarılan pano: çözücü çalışmadı…", no ✓, no KPI row, no soft score; the list shows "—" and "Yayında".
  - **/timetable** (`planlamaci.test`, `yonetici.test` fresh session): opens the published run (#3) on the current term week; "Bu haftayı Excel'e aktar" downloads `…run3-hafta<this week>.xlsx`; the narrow issues chip reads "N çakışma · M uyarı".
  - **/admin/users › Yeni kullanıcı**: 5 fields + "Gelişmiş" (closed); a user is created with only e-posta, ad, soyad, rol; `e2e/admin-gaps.spec.ts` and `e2e/bookings.spec.ts` pass with the "Gelişmiş" step. Edit `personel.test` with a Teacher role: no scope picker, the sentence + "Rolleri aç"; a forced save shows the Turkish refusal, focus not on BODY.
  - **Taleplerim** (`personel.test` after a C 606 request, 1440 and 390 tab): the request is listed with its status; no "Hesabınız bir öğretim elemanına bağlı değil" page. `akademisyen.ayse`: room requests, then "Ders planlama taleplerim".
  - **İçe aktar › Ders planlama listesi**, target Güz, file `bahar_derslik_planlama_listesi_v5.xlsx` › Önizle: the warning names Bahar 2026; "Uygula" disabled until "Evet, Güz 2026-27 dönemine uygula" is ticked (do not press Uygula on the shared stack). "Uyarıları göster": the UZEM / weeks / time rows read in Turkish.
  - **Ayarlar** as admin: opens on "Genel"; the tab reads "Takvim ve entegrasyonlar".
  - **/profile#security at 390** (`aux.plan2`): "Aç" opens a full-screen sheet, all 6 code slots visible (M-01). **Sessions**: sign in on a phone UA; after a minute of use the row reads "Safari, iPhone", not "bilinmeyen tarayıcı".
  - **Takvimime ekle**: a `calendar.department_feed` holder sees Derslerim, one "Bölüm dersleri" card (search finds "Ağız…", own department first) and Rezervasyonlarım, no 146-card list; with the panel address empty, step 2 has no "Abonelik bağlantısı" card, the sentence about the panel address, and ".ics dosyası indir"; with the address set the link card is back. "Aydınlatma metni" ≥ 44 px at 390.
  - **Welcome tour** (keyboard, 1440 and 390): at step 2 "Önce zamanı seçin" (/reserve) focus is on İleri, Tab reaches the target and returns; a sheet card ("Salon bul") lands with focus on the /find-room h1; after a first quick booking at 390 Diğer › Başlarken shows 1 / 5 without a reload; the phone toast says "…Diğer sekmesinde."; re-run `e2e/wg-admin.spec.ts:97` (Güncellendi stays).
  - **Toasts**: the region's accessible name is "Bildirimler" (no "Notifications alt+T"). /approvals with an empty inbox: no A / D / R keycaps.
  - MOBILE M-01/02/03/05 on /bookings, /find-room, /reserve, /my-bookings, /moderation/me, /runs/7, /profile at 390.

## FIX-G (2026-10-18): AS-20 / CH-12 open items (owner rule "apply the recommended option")

Browser checks for docs/testing/round4/2026-10-18-as20.md and -ch12.md (unit level done; 1440 mouse and 390×844 touch,
isMobile + hasTouch, tr-TR, Europe/Istanbul):
- **AS20-F09 (planner drafts, admin approves):** `planlamaci.test` → /admin/weeks opens (no 403 page): no "Ders haftaları" / "Dönem haftaları" editors, only "Dönem profilleri"; "Yeni profil" → Taslağı kaydet → the draft row reads "Bir yönetici onaylayınca uygulanır.", with "Düzenle" and "Taslağı sil" and no "Onayla ve etkinleştir", "Geri al", "Kullanımdan kaldır" or "Düzenlemelerden ağırlık öner"; no "Dönem takvimi" block. Düzenle → save keeps it a draft. `yonetici.test` then sees the draft with "Onayla ve etkinleştir (v1)" and activates it; /admin/audit lists `season_profile.create` / `.update` under the planner and `.activate` under the admin. API: planner `POST /seasons/profiles/{id}/activate` → 403 with message_tr. Clean up the test profile as admin.
- **AS20-F08 (fold):** /admin/weeks with a retired-only test profile: the row sits under "Eski profiller (n)" (closed), has no action buttons; the live list keeps the active / draft keys.
- **AS20-F13 (one exam unit):** /exams/advisor › Final 2026: the peak card reads "3 Haziran 2026 Çarşamba: 98 sınav; hedef en çok 74 …" (it was 126 / 85), the basis line names "birleşik sınavlar … bir kez sayılır", and the chart summary says 98 too; `GET /analytics/forecast/exams` peak 98, run data notes `exam_load` 98. Applying a move of a merge group lowers the peak by 1.
- **AS20-F14:** empty stack (19911) › /analytics/heatmap › Yoğun saatler: only "Henüz dönem yok. Önce …" + "İçe aktar" (→ /import); no term / grouping / kind selects, no CSV button; no `/analytics/peaks` request.
- **AS20-F15:** /analytics/forecast › Güz, Bina: "Bina belirtilmemiş" is the last row with "Planlama listesinde bina yazılmamış talepler" under it; no "—" per row and one line "Aralık yok: bu dönemin kendi talepleri sayıldı, tahmin edilmedi." under the card. A seasonal-naive term (if any) still shows its ranges.
- **CH12-F02:** /runs at 390 touch: a tap on a dot shows the tooltip and stays on /runs; a second tap on the same dot opens the run; a scroll that starts on the chart opens nothing; the hint reads "Bir noktaya dokunun: ilk dokunuş değeri gösterir, ikinci dokunuş o çalıştırmayı açar."; at 1440 one click opens; ←/→ + Enter opens at once.
- **CH12-F04:** /admin/ops error inbox with a `database is locked` group: the headline reads "Veritabanı meşgul: işlem tamamlanamadı, yeniden denenmeli."; no "sqlite3" / "[SQL:" text until "Ayrıntı", which shows the class, message and stack.
- **CH12-F07:** after a fresh `next build` of the commit under test: `node scripts/bundle-table.mjs --write docs/testing/bundle-baseline.json` (record the baseline, commit it), then later builds `node scripts/bundle-table.mjs --compare docs/testing/bundle-baseline.json --max-kb 0` on the chart-less routes.
- **CH12-F09:** re-run `e2e/motion-audit.spec.ts -g "run report"` without `AUDIT_RUN`: the setup log names a solver run (e.g. #8), not the import board #1, and the test passes.
- **CH12-F10:** kiosk /public/rooms/C304?date=<9 days ago>: "Bu sayfa kullanılamıyor" + "Bu ekran son 7 gün ile önümüzdeki 120 günü gösterir; …" + "Bugün" (→ /public/rooms/C304, renders); the backend log has `public_schedule.not_found reason=date`; with the view switched off the log says `reason=off`, the body is still the same 404.
- MOBILE M-01/02/03/05 on /admin/weeks (planner), /analytics/heatmap › Yoğun saatler (empty), /analytics/forecast, /runs, /public/rooms/C304 at 390.

## FIX-H (2026-10-18): open round-4 items after FIX-E

Browser checks for the FIX-H rows of docs/testing/round4/2026-10-18-{hx12b,personas,aux12,cal10}.md (unit level done;
1440 mouse and 390×844 touch, isMobile + hasTouch, tr-TR, Europe/Istanbul):
- **HX12B-F05** /runs/7 (`planlamaci.test`): above the fold only the verdict sentence, "Yayınla" (filled) and "Ayrıntılar" (closed); opening it shows the KPI row, policy/profile lines and the bars; 390: the Yayınla capsule still free (M-05). Re-run `e2e/loop-r1-laneH.spec.ts` / `loop-r2-laneE.spec.ts` KPI steps (they read text inside the closed details).
- **HX12B-F10** /reserve and /dashboard: 1440 the page title is first, "Başlarken" below the page; 390 no card, Diğer › Başlarken row present.
- **HX12B-F11** /bookings sheet on a free run: only the P-chips, no "Ders saati" select; `e2e/reserve.spec.ts` test 4 (chips used).
- **HX12B-F13 / PER-F15** M-02 at 390 on /bookings (Salon bilgisi chips), /reserve, /admin/users dialog building chips, /settings model radios, /runs/7 fix rows: every chip ≥ 44 px tall; no chip row overflows sideways (M-01).
- **HX12B-F14** /settings at 390: "Ayar grubu" select lists every tab and switches; the AI tab shows "Claude Opus 5.5".
- **HX12B-F15** /admin/users at 390: "Yeni kullanıcı" is a labelled capsule; M-05.
- **HX12B-F17 / F18** /import: room-master subtitle without "room_master.csv"; /runs column "Tercih puanı (100 üzerinden)", rows "İçe aktarılan çizelge #3".
- **PER-F04** İçe aktar › Ders planlama listesi, target Güz, `bahar_…v5.xlsx` › Önizle: warning names "Bahar 2026" (from `summary.term_check`); the same file renamed `liste.xlsx` with a "BAHAR 2026" sheet title also warns. Do not press Uygula on the shared stack.
- **PER-F05** the same preview › Uyarıları göster: "Türlerine göre" lists "Kişi olmayan öğretim elemanı değeri · N satır" first; the table rows read Turkish; a viewer sees counts only.
- **PER-F07** admin: Ayarlar has no Kullanıcılar / Rezervasyon kuralları tabs; `/settings?tab=booking-rules` lands on Kurulum › Rezervasyon kuralları (`e2e/wave2.spec.ts` test 2 opens it directly); Genel links to Ders saatleri; sidebar: 4 headings, "Daha fazla (n)" opens / closes with keyboard, opens itself on /exams/advisor; welcome tours (planner, viewer, admin) still find their nav anchors. `e2e/real-backend.spec.ts` users step goes to /admin/users.
- **PER-F09** `akademisyen.ayse` (linked): sidebar / Diğer › Derslerim → this week's classes by day with rooms; Önceki/Sonraki hafta; "N dersinize henüz derslik atanmadı" when Taleplerim has unplaced rows; an unlinked teacher sees the sentence, no 403; Profil links to it. 390: M-01/02/03.
- **AUX12-F07** /reset-password › Kodum var (and `?token=`): one password field with show/hide, "En az 12 karakter"; the SSO line under the request field; `e2e/bookings.spec.ts` test 12.
- **CAL10-F02** Ayarlar › Takvim ve entegrasyonlar with the panel address empty: the warning on the KVKK card, "Panel adresini girin" focuses the field.
- **CAL10-F03** curl a classes feed, sign in elsewhere (an audit event), curl with If-None-Match: 304, same ETag.
- **CAL10-F04** Takvimime ekle: after "Derslerim" and after "Abonelik bağlantısı" `document.activeElement` is `cal-step-heading`, never `DIV#cal-sheet`.
- **CAL10-F05** Gelişmiş › Bağlantıyı yenile: the confirm names the effect; Vazgeç keeps the link, focus back on the button; Yenile shows the new link once.
- **Video lane, publish scope reduction** (English UI): /runs/8 › Yayınla with a whole-term run published: the scope box reads "This run covers fewer weeks: … of #3 …" and "Run #8 covers weeks 1 and 2 only; …", no Turkish sentence; in Turkish "#8 yalnızca şu haftaları kapsıyor: 1. ve 2. haftalar. …".
- **Video lane, booking a week without a published timetable** (WEEK run published): the sheet shows "Bu hafta ders programı yayımlanmamış" + the sentence; first press of the one primary keeps focus on it, its label becomes "Yine de rezerve et", the warning adds "…bir kez daha basın." (announced assertively); the second press books.

## FIX-J (2026-10-18): KVKK import blocker, import preview archives, rename re-import, empty-stack next steps
One stack, `REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`. Use only `E2E_FIXTURES_DIR=$REC_WORKDIR/fixtures` (the masked workbooks `stack.sh up` writes) for every item that uploads a workbook.
- **E2EA-F01 / E2EA2-F02 (blocker):**
  - `stack.sh up` logs "KVKK: masked workbooks in …/fixtures", and `kvkk_mask.py rec.db --verify --names kvkk-names.json --uploads uploads` prints `left 0`.
  - /import › Ders planlama listesi with the raw `tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx` is refused with 422 "KVKK: bu dosya maskelenmemiş örnek çalışma kitaplarından biri…". The job is FAILED and no file is kept. The same check covers /onboarding (council).
  - The masked copy previews and applies. After Uygula, `--verify` still prints `left 0`, and /admin/audit shows initials only.
  - On a live stack: apply any change, then `stack.sh mask` succeeds; append-only audit rows are no longer an error.
  - `cat /proc/<backend pid>/environ | tr '\0' '\n' | grep -c -E 'GH_TOKEN|AWS_'` gives 0.
- **E2EA2-F01:** preview a 3-row planning list for Bahar.
  - The card leads with "N kayıt dosyada yok; arşivlenecek", and the entity lines read "… · N arşivlenecek".
  - Uygula opens "Bu dosya dönemin büyük bir kısmını arşivleyecek", with "Yine de uygula" (destructive) and Vazgeç. Nothing is applied until "Yine de uygula". Vazgeç keeps focus on Uygula. Check at 1440 and 390.
  - Do not apply: the item is preview + dialog only.
- **E2EA-F02:**
  - Rename programme #32 (append " RFB").
  - Previewing the masked Bahar planning list shows "Şubeler 0 yeni" and no archive.
  - After apply, `GET /sections?term_id=1&program_id=32&include_archived=true` holds the same ids, none archived.
  - Rename it back.
- **E2EA-F03:** the masked Güz planning list preview shows the counts and the change list, never "Bu önizlemede değişiklik listesi yok."
- **E2EA-F06:** /import history: seed rows read "İlk kurulum (sistem)" on a stack started after this change.
- **E2EB-F03 (empty stack `up --fresh`, before any import, at 1440 and 390):**
  - /analytics/heatmap shows only "Henüz dönem yok…" + İçe aktar.
  - /find-room and /reserve show "Rezervasyon yapılabilecek bir dönem yok" + "Dosyalardan kur" (→ /onboarding) for the admin, and the "yöneticinize başvurun" text for an academician.
  - M-01/02/03 pass on all three.

## FIX-I (2026-10-18): round-4 fail/partial re-checks (docs/testing/e2e-queue/results-2026-10-18-round4.md "FIX-I")

1440 mouse and 390×844 touch (isMobile, hasTouch), tr-TR, Europe/Istanbul; on a recording stack set
`E2E_FIXTURES_DIR=$REC_WORKDIR/fixtures` (e2e/helpers.ts refuses the raw workbooks there):
- **WG-09:** `E2E_REAL=1 npx playwright test e2e/motion-audit.spec.ts -g welcome` (new block): `scrimGaps` 0 on every tour step, the cross-route step 1 → 2 included, at 1440 and 390; reduced motion moves nothing; on a GPU runner add `MOTION_STRICT=1` for ≤ 3 dropped frames (WG10-F08). Re-run `e2e/wg-admin.spec.ts:97` ("Güncellendi" stays, FIX-C).
- **AUX-F:** `e2e/au-signin-security.spec.ts` ×3, serial: §16.1 and §16.2 pass (no BODY focus right after landing, no `ERR_ABORTED`); after "Bitir" focus is on "Yönet". Passwordless on, `aux.plan1` (TOTP) signs in with password + code → one `navigator.credentials.create({mediation:"conditional"})` call (AUX12-F06).
- **AU-B 1:** sign in on a desktop and a Safari-iPhone UA, plus one `curl` login used once: /profile#security lists "Chrome · Linux" (Bu cihaz), "Safari · iPhone" and "Betik ya da API istemcisi"; no "bilinmeyen tarayıcı"; an English profile reads "Script or API client"; `GET /auth/sessions` rows carry `browser`/`os`/`client`.
- **VO-F 2:** `e2e/vo-mounts.spec.ts` whole and `-g "3\."` / `-g "4\."` alone: test 3 sees 422 and the text stays in the box; AI routes and the voice switch are back to their values after the suite.
- **HX-19 / helper:** `motion-audit.spec.ts -g helper` (reduced motion on and off): no finite animation > 300 ms at sheet open (HB18-F08); record the blur-surface count with the sheet open (still > 3 is an open item); phone confirm card: its primary sits just above the guide field (HB18-F10, M-05).
- **Shell / IDP-2 / Mobile:** Göster on admin.users, admin.rooms, admin.sessions, admin.welcome rings the page heading (no "görünmüyor"), find_room.filters at 1440 rings "Gelişmiş"; after Esc / Anladım `document.activeElement` is never BODY (12 cases of E2EB-F06). /admin/ai?tab=limits strict over org → the Turkish 422 text; at 390 the changed faculty save floats above the tab bar. SAML step 3 at 390: "Kaydet" uncovered above the tab bar; "SP anahtarı oluştur" → focus on "Kaldır". Root 32 px at 390: /generate step 1 and /runs/compare?a=7&b=11 scrollWidth ≤ 390. 320×568 /bookings date chip shows the whole "22 Eki". /timetable at 768 touch: tap a chip, Esc → focus on that chip. /classes Sıkı → 32 px rows, Rahat → 56 px. Empty stack /bookings: "18.10.2026 hiçbir dönemin içinde değil." (no English).

- FIX-I/FIX-K (E2EB-F11): on touch, a tap on a class chip moves focus to the inspector heading (only when focus had fallen to <main>/<body>); Esc returns focus to the chip. Check both at 390.

## FIX-K (2026-10-18): e2e-a / e2e-a2 / e2e-b open minors, shell blur and 32 px root, run-page toast
Fresh stack (`stack.sh up`, masked fixtures) for the KVKK item; the rest on any stack. Desktop 1440 (mouse) and 390×844 touch, tr-TR.
- **E2EA-F08 (fresh stack only):**
  - Re-import the masked Bahar planning list from `$REC_WORKDIR/fixtures`. The preview shows "Öğretim elemanları 0 yeni" (it was 72 new).
  - `kvkk_mask.py --verify --names …` prints `left 0`.
  - Instructors with colliding initials read like "Ad. K." / "Ay. K.".
  - The report after Uygula reads "… oluşturuldu · N güncellendi · … atlandı" and shows a "Güncellenen" figure.
- **E2EA-F05:**
  - /import after more than 8 jobs: "Daha eski içe aktarmaları göster (n)" reveals the older jobs, the seed jobs among them.
  - Focus lands on the first revealed row's Rapor button.
- **E2EA-F07:**
  - `PUT /constraints/{FILE rule} {"params":{"buildings":["A"]}}` → 422 `rule_scope_lost`, and the rule is unchanged.
  - Studio › a planner's own rule › Kime uygulanır › Herkes still saves.
- **E2EA-F09:** /admin/ops: an unknown error class reads "Beklenmeyen bir hata. Teknik metin Ayrıntı içinde.", and the raw text appears only under Ayrıntı.
- **E2EA-F10:**
  - With password sign-in only, /admin/users shows "Davet et" (outline) beside "Yeni kullanıcı".
  - The sheet lead reads "Kişi bağlantıyı açıp kendi parolasını belirler."
  - The link opens /login?invite=… with a set-password form.
  - `?invite=1&email=…` opens the sheet.
- **E2EA-F11 / E2EA2-F07:**
  - /classes on a phone: the inspector has "Öğrenci sayısı" with − / + at 44 px and an input of at least 16 px. Kaydet shows the toast "Kaydedildi · Sonraki çalıştırmada etkili", and the value survives a reload.
  - Same on /classes › Sınavlar for an exam (`PUT /requests/exams/{id}`).
- **E2EA2-F03:** `document.activeElement` is never `<body>` after:
  - /admin/schedules Kaydet (it stays on Kaydet);
  - Varsayılana dön (it moves to P1 başlangıç);
  - /admin/weeks kind change (it stays on the select);
  - /admin/users Sonraki to the last page (it moves to Önceki);
  - /import preview Vazgeç (it moves to the drop zone).
- **E2EA2-F05:** after P1 is set to 08:00, `GET /learning/suggestions?term_id=1` `evidence.value_label.tr` reads "(08:00–13:20)".
- **E2EA2-F06 (needs a board import after FIX-K):** /admin/weeks: week 14 → Tatil → Ders. The "Elle değiştirildi" badge goes away and `GET /terms/1/weeks` shows `edited:false`.
- **E2EB-F08:** empty stack after import, 390: "Çizelge oluştur" on /dashboard is at least 44 px tall.
- **E2EB-F11:** /timetable at 768 touch: tap a class chip, and focus lands on the inspector heading; Esc returns it to the chip.
- **E2EB-F12:** /onboarding at 390:
  - after Yaz → confirm, focus is on the result line;
  - re-uploading the same room list reads "Derslikler: 87 · değişiklik yok";
  - the diff note reads "Önizleme: veritabanı değişmedi."
- **E2EB-F13:** /exams/invigilation at 390: CLS < 0.1.
- **E2EB-F14 / F15:**
  - With YETKİM metadata unsigned, the provider row shows the Turkish check sentence.
  - Step 3 has "Meta veriyi yeniden oku". After the metadata is fixed, it turns the provider green and unlocks step 4.
- **E2EB-F16:** Profil › Güvenlik after `?sso=linked&provider=keycloak`: the address is cleaned; after "Bağlantıyı kaldır" the green notice is gone.
- **E2EB-F18:** SAML sign-in of an existing unlinked account shows "Giriş yapılamadı." with the S-code and the link hint (no "bu hesap var" wording).
- **E2EB-F21:** empty stack, imported term with nothing published: /analytics/heatmap reads "Yayımlanmış program yok", not "Genel doluluk %0".
- **Orchestrator asks:**
  - 390 with `document.documentElement.style.fontSize="32px"`: /analytics/heatmap scrollWidth ≤ 390. The tab bar has no search capsule; the top bar shows the search button.
  - Open the helper sheet at 1440 and 390: at most 3 `backdrop-filter` surfaces (`getComputedStyle(el).backdropFilter !== "none"`). The top bar, sidebar and tab bar keep their tint.
  - As `planlamaci.test`, open /runs/3 and /runs/7 (all tabs, the chat included): no "izni gerekiyor" toast. A refused action, such as a forced move, still toasts.
