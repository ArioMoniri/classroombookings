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
