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
