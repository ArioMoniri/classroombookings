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
