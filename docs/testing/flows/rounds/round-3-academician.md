# Flow loop round 3 · academician · 2026-10-17

Ledger: `flow-r3-academician-2026-10-17` · persona tester (academician, re-test round) · plan: [README](../README.md), [MOBILE](../MOBILE.md), briefs `scratchpad/briefs/ROUND3.md` + `ROUND2.md`
Snapshot: `8db884fd` (`8db884fdbac71c7efd7472f31fcc58b2f7e354a2`, origin/claude/focused-wright-ktt0ss), frozen worktree `scratchpad/r3acad/flow-src-8db884f` (removed at the end) · stack API :19420, web :19421 (`REC_WORKDIR=scratchpad/r3acad/stack`, `REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`), SMTP sink :2627 · load 1.3–9.1 on 4 cores during the runs (`uptime` 09:11 → 10:02 UTC; two other testers active; timing rows judged at 1×, F-13 B04 INCONCLUSIVE)
Run window: 09:10–10:10 UTC. A usage limit stopped the session at about 10:10 and the container restarted at 18:55. Every flow and probe had finished and saved its JSON before the stop, so no flow was re-run; the report was assembled at 19:00 from the captured logs (the coordinator's resume note).
Dates (README §4.3): TODAY 2026-10-17 · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D6 2026-11-26 · Chromium 141 (chromium-1194 headless shell), Playwright 1.56.1 library, touch contexts from `scripts/record/lib/touch.mjs` (`assertTouch` before every M-02/M-03/M-05/M-12, `shot()` for full-page shots)
Data: all three real terms + room master; runs #7 Bahar week 3, #8 Bahar term (683/717, published), #9 Güz week 3 (524/530), #10 Güz term (517/530, published), all hard 100. Names masked (`kvkk_mask.py --verify` → `left 0`, also re-checked at the end).
Accounts: `akademisyen.test@smartsched.local` ("A. T.", TEACHER, user 4) linked to instructor 157 ("Dr. Öğr. Üyesi S. E.", PSY 277 / PSY 278) via `PUT /auth/sso/admin/users/4/instructor` → 200; admin is the approver for every room.
Preconditions per flow after `REC_SNAPSHOT=1 REC_SKIP_BUILD=1 stack.sh up`: `approval_mode=all`, starter features + adopt-tags (PC feature = "Bilgisayar laboratuvarı", id 1), calendar sync signed off through the admin API for F-04/F-13/R3, privacy notices TR v1 / EN v2 / TR v3 for R1-A-26. Admin decisions were made through the API (the admin UI belongs to the admin tester).
Viewports: desktop 1440×900 (mouse and keyboard); phone 390×844 (isMobile + hasTouch, tap only); tablet 768×1024 + keyboard for the F-13 C02/C05/C06 trap and M-09 checks.
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r3acad/ev`: `shots/` (120), `curl/` (54, tokens and reset codes redacted), `mail/` (8 .eml), `logs/` (`*.json` per script, `*.log`), `scripts/` (round-2 flow scripts re-pointed to :19420 plus the round-3 probes `r3.mjs`, `r3b.mjs`, `r3c.mjs`, `probe-a11.mjs`, `probe-copy-enter.mjs`, `probe-frtext.mjs`; re-run with `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node <script>`). Step table generator: `scratchpad/r3acad/build_report.py`.

Scope: the round-3 re-test list for the academician (ROADMAP round-2 block), every R2-A id, R1-A-17 via T-R2-13, and the F-01/F-03/F-04/F-05/F-12/F-13 smoke at 1440 + 390 touch with MOBILE M-02/M-05 (plus M-01/03/04/07/09/10/11/12) on every route. The Fatih Bey planning scenarios belong to the admin tester.

## BLUF

**Ready for release from this persona's point of view: yes. No blocker or major is open for the academician. Every round-2 major (keyboard cover, confirm focus trap, sticky Ara, small find-room controls) is verified on the device. What remains is three minors, one trivial and one suggestion that do not stop any academician task.**

- **Re-verification: 20 ids → 16 verified · 4 reopened.** 15 of the 19 R2-A ids are verified, plus R1-A-17 (Yaklaşan now shows one row "C 303 · P7–P8"). Reopened:
  - **R2-A-11** (minor, a defect): the note still never reaches the personal calendar feed.
  - **R2-A-17 / R2-A-18** (suggestions): the enhancements FLE-009 and FLE-011 are not built.
  - **R2-A-19**: still waiting for the owner's decision on the third language entry.
- **New findings: 4. 0 blocker · 0 major · 2 minor · 1 trivial · 1 suggestion.**
  - **R3-A-01 (minor):** with the "Bilgisayar laboratuvarı" chip selected, the lab I asked for is labelled "PC özellikli oda; istenmedi, sona alındı". This is A-11 coming back through the chip path; typing "PC" is clean.
  - **R3-A-04 (minor):** the My bookings totals line counts rejected, withdrawn and pending requests ("1 etkin · bu dönem 3 · toplam 3" next to one listed booking). T-R2-13's "add up" part does not hold.
  - **R3-A-02 (trivial):** the revised F-03 says "Arama metni" stays on the phone form, but it is in the Filtreler sheet. This is flow-file drift.
  - **R3-A-03 (suggestion):** in English the /bookings building tabs still read "A Blok (20)". These are setup-named data, so T-R2-16 scoped them out.
- **Steps: 393 rows.** 370 PASS · 7 FAIL · 13 SKIP · 2 BLOCKED (F-12 S18, no tenant) · 1 INCONCLUSIVE (F-13 B04 under load 6.6). Every FAIL row maps to R2-A-11, R3-A-01 or R3-A-04. Per flow:
  - F-01: 67 pass / 0 fail / 1 skip
  - F-03: 46 / 2 / 0
  - F-04: 40 / 4 / 3
  - F-05: 59 / 0 / 2
  - F-06: 1 / 0 / 0
  - F-12: 62 / 0 / 5 skip + 2 blocked
  - F-13: 34 / 0 / 0 + 1 inconclusive
  - Round-3 ticket probes (R3 / R3b / R3c): 61 / 1 / 2
- **Shared primitives (T-R2-02/04/05):** M-09 passes on all six academician routes at 390 and 768. The tab labels are "Rezerve · Benimkiler · Taleplerim · Diğer" (44/57/56/29 px, no overlap, one aria-current). M-02 is clean on every route with its sheet or dialog open: book sheet, bell, withdraw and cancel confirms, wish sheet, filters sheet, results, /profile#notifications. M-05 passes for the book sheet, the wish sheet, /profile and /find-room. The /login centred-form rule (R2-S-20) applies there. The toast close button on the front toast is 44×44.
- **Not run:** F-12 S08 needs the TTL stack. The orchestrator did not hand me +200 ports and a second stack would have loaded a host already at 6–9, so it is `SKIP (no TTL stack)` as in rounds 1 and 2. F-04 S12 has no OAuth client; F-12 S18 has no tenant; F-05 S03 building-already is a data SKIP.

What works well now (keep):
- The tab bar on phones.
- Page-level keyboard clearance on /profile and /find-room.
- The fixed "Ara" capsule.
- Modal confirms that trap Tab and return focus on Esc.
- Selecting a bell item while on /my-bookings now opens and focuses the request.
- One row per two-period booking.
- Worded copy buttons with a Turkish refusal toast when the clipboard is denied.
- Approval-first helper texts.
- The teacher's "Taleplerim" crumb.
- "PSY 277 · Teori" cards.
- The reset page: "En az 8 karakter.", "24 saat", a coded TR refusal for a short code; the right code gives 200, reusing it gives 400.
- Multi-period requests answer 202.
- No "Takvim eşitleme" toast on /profile.
- Reduced motion: the sheet sits at translate none / opacity 1 from the first frame.

## Re-verification of round-2 ids (and R1-A-17)

| id | ticket | result | note |
|---|---|---|---|
| R2-A-01 | T-R2-04 | verified `8db884fd` | M-09 at 390 and 768 on /bookings, /my-bookings, /find-room, /moderation/me, /moderation/people/157, /profile: labels "Rezerve · Benimkiler · Taleplerim · Diğer", scrollWidth ≤ clientWidth, no label boxes overlap, one aria-current per route, stable after hydration (`logs/r3.json` M-09@*, `shots/R3-M09-tabbar-acad-phone.png`) |
| R2-A-02 | T-R2-01 | verified `8db884fd` | M-12 at 390×508: /profile "Yeni parola" 308–352, uncovered; /find-room "Kaç kişi" 320–364, uncovered, Ara 378–422 visible (`logs/f12.json`, `logs/f03.json`) |
| R2-A-03 | T-R2-02 | verified `8db884fd` | withdraw and reset-link confirms: role=alertdialog, aria-modal=true; 10 Tabs and 4 Shift+Tabs stay inside at 1440 keyboard and 768 tablet; Esc closes in one press and returns focus to "Talebi geri çek" / "Özel bağlantıyı sıfırla" (`logs/r3.json` C02-C05-trap, `logs/r3b.json` C02-esc-*) |
| R2-A-04 | T-R2-10 | verified `8db884fd` | `fr-search` capsule at y 714–758 at scroll 0 / 400 / end, before and after results (M-05 PASS) |
| R2-A-05 | T-R2-10, T-R2-05 | verified `8db884fd` | M-02 sweep with centre re-probe empty on /find-room, the filters sheet and the results. The raw chip boxes are 28 px tall, but their 44 px hit area takes the ±22 px probe (informational row F-03 M-02@filters-detail) |
| R2-A-06 | T-R2-06 | verified `8db884fd` | hint "En az 8 karakter."; requested text names "24 saat"; `{"token":"12"}` → 400 `invalid_code` "Kod hatalı ya da süresi dolmuş. Yenisini isteyin." (also in the UI, no "String should"); real code 200, reuse 400 (`curl/R3-S07-confirm.txt`, `curl/R3-S07-rightcode.txt`) |
| R2-A-07 | T-R2-16 | verified `8db884fd` | legend "Boş bir saate tıklayıp talep edin. …", sheet hint "Birlikte talep etmek için önceki ya da sonraki saatleri ekleyin.", no "rezerve" in the sheet (1440 + 390) |
| R2-A-08 | T-R2-16 | verified `8db884fd` | after the UI language switch (toast "Saved"), the /find-room chips read "Block A … Block D" at 1440 and 390. The /bookings group tabs still say "A Blok (20)" (setup data, out of the ticket's scope): R3-A-03 |
| R2-A-09 | T-R2-17 | verified `8db884fd` | on /my-bookings, the bell item → `?request=1`, the row expands and is in view with "Gerekçe: Oda uygun değil: …" and "Karar veren: Administrator", focus on the row, popover/sheet closed (1440 + 390) |
| R2-A-10 | T-R2-13 | verified `8db884fd` | Yaklaşan: one row "C 303 · P7–P8 (13:30–15:00)" with chips P7 P8 and the approver's note once (1440 + 390). The totals line beside it does not add up: R3-A-04 |
| R2-A-11 | T-R2-17 | **reopened `8db884fd`** | mine.ics on the stack has no DESCRIPTION in any VEVENT (3 and 4 events in two runs), although bookings 3/4 hold "Telafi dersi" and the owner is user 4. Everything else in the feed is right (VTIMEZONE, one VEVENT for P7–P8, statuses). The builder's pytest books directly (`env.book`); this stack's bookings came through request → approve (`curl/R3-S06-mine.ics`, `curl/F04-S06-mine-*.ics`) |
| R2-A-12 | T-R2-15 | verified `8db884fd` | phone: "Kopyala" 110×44, "webcal kopyala" 156×44; with the clipboard denied, the toast reads "Kopyalanamadı: bağlantıyı alandan seçin", the field gets focus, no pageerror; URL textarea scrollWidth = clientWidth. Desktop: Enter and Space → "Bağlantı kopyalandı" |
| R2-A-13 | T-R2-05 | verified `8db884fd` | front toast "Bildirimi kapat" 44×44 with all four ±22 px probes on target. The 41.8 px reading is the stacked back toast (scaled 0.95), which is not the tap target |
| R2-A-14 | T-R2-08 | verified `8db884fd` | /moderation/me crumb "Taleplerim" only, no "Moderasyon" (1440 + 390) |
| R2-A-15 | T-R2-17 | verified `8db884fd` | `POST /bookings/multi/{id}/create` → 202 for one period, two periods and a second one-period request (`curl/R3-pre-*.txt`) |
| R2-A-16 | T-R2-25 | verified `8db884fd` | card text "PSY 277 · Teori", "PSY 277 · Laboratuvar" (1440 + 390) |
| R2-A-17 | FLE-009 (enhancement) | reopened `8db884fd` | not built: the approved C 303 request still shows in Taleplerim ("Onaylandı") and as a booking under Yaklaşan (`shots/R3-M09-tabbar-acad-phone.png`); suggestion |
| R2-A-18 | FLE-011 (enhancement) | reopened `8db884fd` | not built: the reset mail is still bilingual for a known TR account (`mail/R3-S07-reset-code.eml`); suggestion |
| R2-A-19 | owner decision | reopened `8db884fd` | the picker still offers "Kurum varsayılanı (Türkçe)", "Türkçe", "English"; decision pending (ROADMAP "Blocked by decisions") |
| R1-A-17 | T-R2-13 | verified `8db884fd` | the span is one row in Taleplerim, Yaklaşan, the feed (one VEVENT P7–P8) and the admin mail |

## New findings

### R3-A-01 (minor) With the "Bilgisayar laboratuvarı" chip selected, the matching lab says "PC özellikli oda; istenmedi"
- Step: F-03 S02 (Part B, approval-first) · academician · desktop, phone
- Did: /find-room, D1, P7–P8 (the form sent start 3 / end 5 with flex), 40 people, chip `fr-feature-1` "Bilgisayar laboratuvarı", Ara.
- Happened: the only fitting card, A 104, reads "41 kişilik · A Blok · Bilgisayar laboratuvarı · … · Kapasite 41: 40 kişi için %2 boş koltuk · **PC özellikli oda; istenmedi, sona alındı**". The API agrees: with `features:[{"field":1}]` every PC room carries that reason and the surplus penalty (`curl/R3-F03-oracle-pc.txt`). Typing "PC" in "Arama metni" is clean (`curl/R3-F03-oracle-text.txt`).
- Expected: a requested feature is never "not asked for" (F-03 S02 fail rule, flow acceptance 2; A-11).
- Cause (read at the snapshot): `smartsched/backend/app/services/find_room.py:410-411` builds `tags` from `q.tags` and `_tags_named_in(q.text)` only. A typed feature criterion (`q.features`, catalogue field 1, adopted from the room-master "PC" tag) does not add its source tag, so `:525` marks PC as surplus.
- Evidence: `logs/probe-a11.log`, `shots/R3-A11-feature-chip-acad-desktop.png`, `shots/R3-A11-feature-chip-acad-phone.png`
- Seen before as: A-11 (text path fixed in round 1); the chip path is new evidence.

### R3-A-04 (minor) The My bookings totals count requests that are not bookings
- Step: F-04 S03 · academician · desktop, phone
- Did: had one approved two-period booking (C 303 P7–P8), one rejected request (A 104) and one pending request (C 306), then opened /my-bookings.
- Happened: "1 etkin · bu dönem 3 · toplam 3". Yaklaşan lists one booking, and `GET /bookings/mine` returns 2 rows (= 1 session). In the F-04 run (two live bookings, one cancelled, one pending) the line reads "2 etkin · bu dönem 3 · toplam 3".
- Expected: T-R2-13's check: the three numbers add up on the session basis and match `GET /bookings/mine`. Requests stay in Taleplerim, cancelled rows are reported apart.
- Evidence: `curl/R3-S03-mine-desktop.json`, `curl/R3-S03-mine-phone.json`, `shots/R3-S03-span-acad-desktop.png`, `logs/f04.json#S03`
- File hints: `smartsched/backend/app/services/bookings.py` dashboard totals (`:1766-1810` at round 2), `smartsched/frontend/src/components/bookings/my-bookings-view.tsx` (`mine-totals`)
- Seen before as: T-R2-13 third part (R2-S-10 is the staff tester's id; this is the academician's evidence).

### R3-A-02 (trivial) F-03 says "Arama metni" stays on the phone form; it is in the Filtreler sheet
- Step: F-03 S03/S04 · phone
- Happened: at 390 there is no `fr-text` on the page. It is inside `fr-filters-sheet` ("Filtreler", "Arama metni", "Dolu derslikleri de göster", …). The steps pass through the sheet: 44 px, 16 px field, the no-match sentence, "Metni temizle", and the trigger reads "Filtreler · 1". The product behaviour is fine; the revised flow text (T-R2-35) is wrong.
- Expected: the flow file matches the build. Either fix the F-03 intro and S03 note, or move the field back if the sheet was not intended.
- Evidence: `logs/r3c.json` F03-S03/S04-phone, `shots/R3-F03-filters-sheet-acad-phone.png`, `shots/R3c-F03-S04-nomatch-acad-phone.png`
- File hints: `docs/testing/flows/F-03-find-room-capacity-feature-reserve.md` (intro, S03)

### R3-A-03 (suggestion) In English the /bookings building tabs read "A Blok (20)"
- Step: F-13 A02 · desktop
- Happened: after T-R2-16, the find-room chips read "Block A"; the /bookings group tabs keep the setup's own names "A Blok (20) · B Blok (9) · …".
- Expected: the same `buildingLabel` mapping for group names of the form "<X> Blok" in EN, or a note that admin-named groups are data.
- Evidence: `logs/r3b.json` A02-chips-ui, `shots/R3b-A02-chips-en-acad-desktop.png`

## Step table (one row per step × viewport; MOBILE rows are `M-xx@route`; R3/R3b/R3c are the round-3 ticket probes)

Results were adjudicated after the runs. A row whose script expectation predates a round-2 fix (old toast wording, old receipt sentence), or that failed on my locator or sampling, is PASS with the reason in the note. Every FAIL maps to an id. Raw output: `logs/*.json`.

| Flow | Step | Viewport | Result | Issue | Note |
|---|---|---|---|---|---|
| F-01 | M-01@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-01@/my-bookings | phone | PASS | – |  |
| F-01 | M-01@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-01@/profile#notifications | phone | PASS | – |  |
| F-01 | M-02@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-02@/my-bookings | phone | PASS | – |  |
| F-01 | M-02@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-02@/profile#notifications | phone | PASS | – |  |
| F-01 | M-03@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-03@/my-bookings | phone | PASS | – |  |
| F-01 | M-03@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-03@/profile#notifications | phone | PASS | – |  |
| F-01 | M-04@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-04@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-04@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-04@/my-bookings(withdraw) | phone | PASS | – |  |
| F-01 | M-04@bell | phone | PASS | – |  |
| F-01 | M-05@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-06@/my-bookings | phone | PASS | – |  |
| F-01 | M-07@/my-bookings | phone | PASS | – |  |
| F-01 | M-07@/profile#notifications | phone | PASS | – |  |
| F-01 | M-08@/bookings | phone | PASS | – |  |
| F-01 | M-09@/my-bookings | phone | PASS | – |  |
| F-01 | M-09@/profile#notifications | phone | PASS | – |  |
| F-01 | M-10@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-10@/my-bookings(bell) | phone | SKIP | – |  |
| F-01 | M-11@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-11@/my-bookings | phone | PASS | – |  |
| F-01 | M-11@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-11@/profile#notifications | phone | PASS | – |  |
| F-01 | M-12@/bookings(book-sheet note) | phone | PASS | – |  |
| F-01 | S02 | desktop | PASS | – |  |
| F-01 | S02 | phone | PASS | – |  |
| F-01 | S02-chips | phone | PASS | – |  |
| F-01 | S02-labels | desktop | PASS | – |  |
| F-01 | S02-labels | phone | PASS | – |  |
| F-01 | S04 | desktop | PASS | – |  |
| F-01 | S04 | phone | PASS | – | a tap on the pending slot opens the request (/my-bookings?request=1): the phone's designed path; API 409 duplicate TR 'A 104 için 22.10.2026 P3 talebiniz zaten var ve onay bekliyor' |
| F-01 | S05 | desktop | PASS | – |  |
| F-01 | S05 | phone | PASS | – |  |
| F-01 | S05-approvers (r3c) | desktop | PASS | – | timeline 'A. T. talep etti · Onaycı bekleniyor · Onaycılar: Administrator · son: Per 22 Eki 13:10' |
| F-01 | S05-approvers (r3c) | phone | PASS | – | same |
| F-01 | S06-notify | desktop | PASS | – |  |
| F-01 | S06-notify | phone | PASS | – |  |
| F-01 | S06a | desktop | PASS | – |  |
| F-01 | S06a | phone | PASS | – |  |
| F-01 | S06b | desktop | PASS | – | both 202 (multi create now 202: T-R2-17 c) |
| F-01 | S06b | phone | PASS | – | both 202, P7+P8 one submission (4 requests / 2 groups); the second toast sampled late; focus passes through BODY for ~1 s then lands on the free-slot heading (R2-A-15 note, unchanged) |
| F-01 | S08 | desktop | PASS | – |  |
| F-01 | S08 | phone | PASS | – |  |
| F-01 | S09-approved-note | desktop | PASS | – |  |
| F-01 | S09-approved-note | phone | PASS | – |  |
| F-01 | S09-bell | desktop | PASS | – |  |
| F-01 | S09-bell | phone | PASS | – |  |
| F-01 | S09-mail | desktop | PASS | – |  |
| F-01 | S09-mail | phone | PASS | – |  |
| F-01 | S09-mine | desktop | PASS | – |  |
| F-01 | S09-mine | phone | PASS | – |  |
| F-01 | S10 | desktop | PASS | – |  |
| F-01 | S10 | phone | PASS | – |  |
| F-01 | S11 | desktop | PASS | – |  |
| F-01 | S11 | phone | PASS | – |  |
| F-01 | S11-honoured | desktop | PASS | – |  |
| F-01 | S11-honoured | phone | PASS | – |  |
| F-01 | errors | desktop | PASS | – |  |
| F-01 | errors | phone | PASS | – |  |
| F-01 | pre | desktop | PASS | – |  |
| F-01 | pre | phone | PASS | – |  |
| F-03 | M-01@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-01@/find-room(results) | phone | PASS | – |  |
| F-03 | M-02@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-02@/find-room(filters-detail) | phone | PASS | – | raw box sizes: chips 28 px tall, but the hit-area-aware M-02 sweep of the sheet is empty (T-R2-05 wrapper py-2 + ::after gives 44 px); informational |
| F-03 | M-02@/find-room(results) | phone | PASS | – |  |
| F-03 | M-03@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-03@/find-room(results) | phone | PASS | – |  |
| F-03 | M-04@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-04@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-05@/find-room(Ara) | phone | PASS | – |  |
| F-03 | M-05@/find-room(results) | phone | PASS | – |  |
| F-03 | M-06@/find-room | phone | PASS | – |  |
| F-03 | M-07@/find-room(results) | phone | PASS | – |  |
| F-03 | M-07@/find-room(results) | phone | PASS | – |  |
| F-03 | M-09@/find-room(results) | phone | PASS | – |  |
| F-03 | M-10@/find-room | phone | PASS | – | exception: paired period selects fr-p1/fr-p2 side by side, 150 px each (≥ 140, MOBILE M-10) |
| F-03 | M-10@/find-room(filters) | phone | PASS | – | same exception |
| F-03 | M-11@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-11@/find-room(results) | phone | PASS | – |  |
| F-03 | M-12@/find-room(headcount) | phone | PASS | – |  |
| F-03 | M-14@/find-room(Ara) | phone | PASS | – |  |
| F-03 | S01 | desktop | PASS | – |  |
| F-03 | S01 | phone | PASS | – |  |
| F-03 | S01-en | desktop | PASS | – |  |
| F-03 | S01-en | phone | PASS | – |  |
| F-03 | S02-feature-chip (probe-a11) | desktop | FAIL | R3-A-01 | D1, headcount 40, chip 'Bilgisayar laboratuvarı' (feature 1) selected: the only fitting card A 104 reads '… · Bilgisayar laboratuvarı … · PC özellikli oda; istenmedi, sona alındı' (A-11 contradiction in the feature-chip path; the text 'PC' path is clean) |
| F-03 | S02-feature-chip (probe-a11) | phone | FAIL | R3-A-01 | same card text at 390 |
| F-03 | S03 | phone | PASS | R3-A-02 | through the Filtreler sheet (r3c F03-S03-phone); the revised F-03 says fr-text stays on the page: flow-file drift |
| F-03 | S04 | desktop | PASS | – |  |
| F-03 | S04 | phone | PASS | R3-A-02 | script locator: on the phone 'Arama metni' (fr-text) lives in the Filtreler sheet, not on the page as the revised F-03 says; re-run through the sheet (probe-f03-s04-phone): 'Metinle eşleşen derslik yok' + 'Metni temizle' as expected |
| F-03 | S08-alts | desktop | PASS | – |  |
| F-03 | S08-alts | phone | PASS | – |  |
| F-03 | S08-altwhy | desktop | PASS | – |  |
| F-03 | S08-altwhy | phone | PASS | – |  |
| F-03 | S10-mine | desktop | PASS | – |  |
| F-03 | S10-mine | phone | PASS | – |  |
| F-03 | S11-notify | desktop | PASS | – |  |
| F-03 | S11-notify | phone | PASS | – |  |
| F-03 | S11-why | desktop | PASS | – |  |
| F-03 | S11-why | phone | PASS | – |  |
| F-03 | S11a | desktop | PASS | – |  |
| F-03 | S11a | phone | PASS | – |  |
| F-03 | S11b | desktop | PASS | – |  |
| F-03 | S11b | phone | PASS | – |  |
| F-03 | errors | desktop | PASS | – |  |
| F-03 | errors | phone | PASS | – |  |
| F-03 | pre | desktop | PASS | – |  |
| F-03 | pre | phone | PASS | – |  |
| F-04 | M-01@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-01@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-02@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-02@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-03@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-03@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-04@/my-bookings(cancel) | phone | PASS | – |  |
| F-04 | M-04@/my-bookings(sync) | phone | SKIP | – |  |
| F-04 | M-07@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-07@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-09@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-09@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-11@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-11@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-12@/my-bookings(cancel reason) | phone | PASS | – |  |
| F-04 | M-14@/my-bookings | phone | PASS | – |  |
| F-04 | S01 | desktop | PASS | – |  |
| F-04 | S01 | phone | PASS | – |  |
| F-04 | S02 | desktop | PASS | – |  |
| F-04 | S02 | phone | PASS | – |  |
| F-04 | S03 | desktop | PASS | – |  |
| F-04 | S03 | phone | PASS | – |  |
| F-04 | S03-totals (r3) | desktop | FAIL | R3-A-04 | state: 1 approved two-period booking (C 303 P7–P8), 1 rejected and 1 pending request: totals read '1 etkin · bu dönem 3 · toplam 3' while Yaklaşan lists one booking and GET /bookings/mine returns 2 rows = 1 session (curl/R3-S03-mine-*.json); F-04 state: '2 etkin · bu dönem 3 · toplam 3' with 2 bookings listed |
| F-04 | S03-totals (r3) | phone | FAIL | R3-A-04 | state: 1 approved two-period booking (C 303 P7–P8), 1 rejected and 1 pending request: totals read '1 etkin · bu dönem 3 · toplam 3' while Yaklaşan lists one booking and GET /bookings/mine returns 2 rows = 1 session (curl/R3-S03-mine-*.json); F-04 state: '2 etkin · bu dönem 3 · toplam 3' with 2 bookings listed |
| F-04 | S04 | desktop | PASS | – |  |
| F-04 | S04 | phone | PASS | – |  |
| F-04 | S04-copy-words | phone | PASS | – |  |
| F-04 | S05 | desktop | PASS | – |  |
| F-04 | S05 | phone | PASS | – | the script expected the old 'Bağlantı kopyalandı'; on the phone (no clipboard permission) the toast is now 'Kopyalanamadı: bağlantıyı alandan seçin' and the field is selected (r3 S05-copy): T-R2-15 behaviour; hrefs Google/Outlook/webcal right |
| F-04 | S06 | desktop | FAIL | R2-A-11 | feed right otherwise (VTIMEZONE Europe/Istanbul, B1 CONFIRMED, B2 one VEVENT P7–P8 CONFIRMED, R1 TENTATIVE, B3 CANCELLED; the 'names' flag is X-WR-CALNAME 'SmartSched – A. T.', the owner's own initials) but no DESCRIPTION/note in any VEVENT |
| F-04 | S06 | phone | FAIL | R2-A-11 | same feed, same gap |
| F-04 | S07 | desktop | PASS | – |  |
| F-04 | S07 | phone | PASS | – |  |
| F-04 | S08 | desktop | PASS | – |  |
| F-04 | S08 | phone | PASS | – |  |
| F-04 | S09 | desktop | PASS | – | room feed 234 events (14 PSY 277), department feed 462; the 'leak' flag matches the masked instructor initials 'Dr. Öğr. Üyesi S. E.' in class summaries, as round 2 (not a leak); no e-mail, no ORGANIZER/ATTENDEE |
| F-04 | S09 | phone | PASS | – | same |
| F-04 | S10 | desktop | PASS | – | toast now the unified '1 rezervasyon iptal edildi · Gerekçe: Ders iptal oldu' (T-R2-16); the script expected the old '1 iptal edildi, 0 olduğu gibi kaldı'; dialog text right, focus on the row's room button, cancelled card shows the reason, feed CANCELLED |
| F-04 | S10 | phone | PASS | – | same; cancel-selected capsule 44 px at y 712, checkbox 44 px |
| F-04 | S11 | desktop | PASS | – |  |
| F-04 | S11 | phone | PASS | – |  |
| F-04 | S12 | desktop | SKIP | – |  |
| F-04 | S12 | phone | SKIP | – |  |
| F-04 | errors | desktop | PASS | – |  |
| F-04 | errors | phone | PASS | – |  |
| F-04 | pre | desktop | PASS | – |  |
| F-04 | pre | phone | PASS | – |  |
| F-05 | KVKK-AI-row (probe-final, R1-A-24) | desktop | PASS | – | 'Kurumunuz, bu rızayı geri almayan herkesi yapay zekâ asistanı isteklerine dahil eder…' + current state line; owner decision R1-M-07 still open |
| F-05 | KVKK-export | desktop | PASS | – |  |
| F-05 | KVKK-export | phone | PASS | – |  |
| F-05 | KVKK-notice (probe-final, R1-A-26) | desktop | PASS | – | TR v1 + EN v2 (+ TR v3) published → the TR reader gets the TR notice, Esc keeps the gate, 'Okudum' → focus MAIN#main |
| F-05 | KVKK-notice (probe-final, R1-A-26) | phone | PASS | – | bottom sheet, Okudum at 784–828 (bottom 40 %), focus #main |
| F-05 | M-01@/moderation/me | phone | PASS | – |  |
| F-05 | M-01@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-01@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-02@/moderation/me | phone | PASS | – |  |
| F-05 | M-02@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-02@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-03@/moderation/me | phone | PASS | – |  |
| F-05 | M-03@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-03@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-04@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-04@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-05@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-07@/moderation/me | phone | PASS | – | cards; the probe keys on the role=table wrapper (fits, as round 2) |
| F-05 | M-07@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-09@/moderation/me | phone | PASS | – |  |
| F-05 | M-09@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-10@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-11@/moderation/me | phone | PASS | – |  |
| F-05 | M-11@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-11@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-12@/moderation/me(wish room search) | phone | PASS | – |  |
| F-05 | S01 | desktop | PASS | – | 4 rows with the assigned room, caption '4 talebiniz', subtitle 'Güz 2026-27 · Dr. Öğr. Üyesi S. E.', no coordinator tabs; the script's verdict-count check is stricter than the flow (as round 2) |
| F-05 | S01 | phone | PASS | – |  |
| F-05 | S01-api | desktop | PASS | – |  |
| F-05 | S01-api | phone | PASS | – |  |
| F-05 | S01-en | desktop | PASS | – |  |
| F-05 | S01-en | phone | PASS | – |  |
| F-05 | S01-enter | desktop | PASS | – |  |
| F-05 | S01-keys | desktop | PASS | – | Tab from 'Tercih ekle' visits all 4 rows with rings, then the document end (BODY) and wraps to the skip link: normal |
| F-05 | S01-session | desktop | PASS | – |  |
| F-05 | S01-session | phone | PASS | – |  |
| F-05 | S02 | desktop | PASS | – | crumb 'Taleplerim / Geçmişim', 2 dönem, 8 rows, JASP, no other person; 'Neden' is shown only on unmet rows, so 4 labels (r3c F05-S02-labels) |
| F-05 | S02 | phone | PASS | – | same |
| F-05 | S02-crumb-ring | desktop | PASS | – | programmatic focus() has no :focus-visible; by keyboard (r3c) the crumb shows a 2 px outline |
| F-05 | S03-building-already | desktop | SKIP | – | data: the department form asks a room / lab, not a building (as round 2) |
| F-05 | S03-building-already | phone | SKIP | – | same |
| F-05 | S03-decide | desktop | PASS | – | empty reject 422 TR, accept + reject 200, cards 'Kabul edildi' / 'Kabul edilmedi' with 'Gerekçe: Oda uygun değil: D blok bu dönem dolu.', bell +2, mail names 'Güz 2026-27'; the script expected the reason without its code label (as round 2) |
| F-05 | S03-decide | phone | PASS | – | same |
| F-05 | S03-duplicate | desktop | PASS | – |  |
| F-05 | S03-duplicate | phone | PASS | – |  |
| F-05 | S03-mine | desktop | PASS | – |  |
| F-05 | S03-mine | phone | PASS | – |  |
| F-05 | S03-room | desktop | PASS | – | 201, 'Gönderiliyor…' aria-busy, toast 'Tercihiniz onaya gönderildi', receipt focused (wish-sent) 'PSY 277: oda tercihi C 301 Bekliyor · Yumuşak tercih…'; the script expected an older receipt sentence (as round 2) |
| F-05 | S03-room | phone | PASS | – | same |
| F-05 | S03-window | desktop | PASS | – |  |
| F-05 | S03-window | phone | PASS | – |  |
| F-05 | S03-withdraw-dialog | desktop | PASS | – |  |
| F-05 | S03-withdraw-dialog | phone | PASS | – |  |
| F-05 | S03-zero | desktop | PASS | – | 0 ticked → 'En az bir ders seçin.' + disabled; the sheet's close button is named 'Kapat' (text, r3c) |
| F-05 | S03-zero | phone | PASS | – | same; Kapat 36×36 box with the 44 px hit area (M-02 sweep clean) |
| F-05 | S04 | desktop | PASS | – |  |
| F-05 | S04 | phone | PASS | – |  |
| F-05 | errors | desktop | PASS | – | one console 'resource 409' from the sheet's duplicate dry-run path (as round 2); no pageerror |
| F-05 | errors | phone | PASS | – | same |
| F-05 | pre | desktop | PASS | – |  |
| F-05 | pre | phone | PASS | – |  |
| F-06 | L1/teacher (probe-final, R1-A-34) | desktop | PASS | – | instructor 157's building-A prior: hidden / room_already_set, 8/8 rows over 2 terms; teacher GET /learning/suggestions → 403 message_tr |
| F-12 | M-01@/login | phone | PASS | – |  |
| F-12 | M-01@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-01@/profile | phone | PASS | – |  |
| F-12 | M-02@/login | phone | PASS | – |  |
| F-12 | M-02@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-02@/profile | phone | PASS | – |  |
| F-12 | M-03@/login | phone | PASS | – |  |
| F-12 | M-03@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-03@/profile | phone | PASS | – |  |
| F-12 | M-05@/login | phone | PASS | – | centred form, submit at y 355–403 right under the password: the bottom-40 % rule does not apply (MOBILE §3 /login row, R2-S-20) |
| F-12 | M-05@/login(sso-on) | phone | SKIP | – | local form collapsed behind login-disclosure; primary is the Microsoft link |
| F-12 | M-05@/profile | phone | PASS | – |  |
| F-12 | M-06@/login | phone | PASS | – |  |
| F-12 | M-07@/login | phone | PASS | – |  |
| F-12 | M-07@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-07@/profile | phone | PASS | – |  |
| F-12 | M-09@/login | phone | SKIP | – |  |
| F-12 | M-09@/login(sso-on) | phone | SKIP | – |  |
| F-12 | M-09@/profile | phone | PASS | – |  |
| F-12 | M-11@/login | phone | PASS | – |  |
| F-12 | M-11@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-11@/profile | phone | PASS | – |  |
| F-12 | M-12@/login | phone | PASS | – |  |
| F-12 | M-12@/profile(password) | phone | PASS | – |  |
| F-12 | M-13@/login | phone | PASS | – |  |
| F-12 | M-13@/profile | phone | PASS | – |  |
| F-12 | S01 | desktop | PASS | – |  |
| F-12 | S01 | phone | PASS | – |  |
| F-12 | S01-en | desktop | PASS | – |  |
| F-12 | S01-en | phone | PASS | – |  |
| F-12 | S02-caps | desktop | PASS | – |  |
| F-12 | S02-caps | phone | PASS | – |  |
| F-12 | S02-disabled | desktop | PASS | – |  |
| F-12 | S02-disabled | phone | PASS | – |  |
| F-12 | S02-empty | desktop | PASS | – |  |
| F-12 | S02-empty | phone | PASS | – |  |
| F-12 | S02-rate | desktop | PASS | – |  |
| F-12 | S02-wrong | desktop | PASS | – |  |
| F-12 | S02-wrong | phone | PASS | – |  |
| F-12 | S03 | desktop | PASS | – |  |
| F-12 | S03 | phone | PASS | – |  |
| F-12 | S03-en | desktop | PASS | – |  |
| F-12 | S03-en | phone | PASS | – |  |
| F-12 | S03-next | desktop | PASS | – |  |
| F-12 | S03-next | phone | PASS | – |  |
| F-12 | S03-welcome | desktop | PASS | – |  |
| F-12 | S03-welcome | phone | PASS | – |  |
| F-12 | S04 | desktop | PASS | – |  |
| F-12 | S04 | phone | PASS | – |  |
| F-12 | S05 | desktop | PASS | – |  |
| F-12 | S05 | phone | PASS | – |  |
| F-12 | S07-code | desktop | PASS | – | the script's code regex picked a short substring of the 32-char code; curl/R3-S07-rightcode.txt: right code → 200, same code again → 400 'Kod hatalı ya da süresi dolmuş. Yenisini isteyin.', login after reset 200 |
| F-12 | S07-request | desktop | PASS | – |  |
| F-12 | S07-rightcode (curl) | desktop | PASS | – | POST /auth/password-reset/request 202 (neutral text), mail with the 32-char code '24 saat geçerli', confirm → 200, same code again → 400 TR, login 200 (curl/R3-S07-rightcode.txt, mail/R3-S07-reset-code.eml) |
| F-12 | S07-ui | desktop | PASS | – |  |
| F-12 | S08 | desktop | SKIP | – |  |
| F-12 | S08 | phone | SKIP | – |  |
| F-12 | S10-attrs | phone | PASS | – |  |
| F-12 | S11 | desktop | PASS | – |  |
| F-12 | S12 | desktop | PASS | – |  |
| F-12 | S12 | phone | PASS | – |  |
| F-12 | S13 | desktop | PASS | – |  |
| F-12 | S13-off | desktop | PASS | – |  |
| F-12 | S14-page | desktop | PASS | – |  |
| F-12 | S14/S15 | desktop | PASS | – |  |
| F-12 | S18 | desktop | BLOCKED | – | no tenant credentials (every round) |
| F-12 | S18 | phone | BLOCKED | – | no tenant credentials (every round) |
| F-12 | errors | desktop | PASS | – | only the expected 401/403/429/400 of the negative tests |
| F-12 | errors | phone | PASS | – | same |
| F-13 | A-errors | desktop | PASS | – | the 404 page's own resource 404s only |
| F-13 | A-errors | desktop | PASS | – | the 404 page's own resource 404s only |
| F-13 | A-errors | phone | PASS | – | same |
| F-13 | A-errors | phone | PASS | – | same |
| F-13 | A01 | desktop | PASS | – |  |
| F-13 | A01 | phone | PASS | – | no EN word on 6 routes, titles TR, role 'Öğretim elemanı', 404 in the shell; the one English bell item is the desktop A02 pass's own English-mode decision ('Administrator declined your request'), stored text (A03 behaviour) |
| F-13 | A01-crumb | desktop | PASS | – |  |
| F-13 | A01-crumb | phone | PASS | – |  |
| F-13 | A02 | desktop | PASS | – | Saved/Kaydedildi toasts, titles EN, 'Send request', find-room chips 'Block A…D' (T-R2-16); the picker's third entry 'Kurum varsayılanı (Türkçe)' is the open decision R2-A-19; /bookings group tabs 'A Blok (20)' are setup-named data (R3-A-03) |
| F-13 | A02 | phone | PASS | – | same |
| F-13 | A03 | desktop | PASS | – |  |
| F-13 | A04 | desktop | PASS | – |  |
| F-13 | A04 | phone | PASS | – |  |
| F-13 | B01 | desktop | PASS | – |  |
| F-13 | B01 | phone | PASS | – |  |
| F-13 | B02 | desktop | PASS | – |  |
| F-13 | B02 | phone | PASS | – |  |
| F-13 | B03 | desktop | PASS | – | backdrop none everywhere; sheet / bell / tab bar opaque gradients; the header's opaque layer is a child span rgb(247,248,250) (probe-final), as round 2 |
| F-13 | B03 | phone | PASS | – | same |
| F-13 | B04 | desktop | INCONCLUSIVE | – | load 6.56 on 4 cores (README §8): baseline dropped 4 frames on the first click; worst LoAF 123 ms (open), 119 ms (submit), 0 (search), 64 ms (expand), none over 200 ms; no over-ceiling animations |
| F-13 | C-errors | desktop | PASS | – |  |
| F-13 | C-errors | desktop | PASS | – |  |
| F-13 | C-errors | tablet | PASS | – |  |
| F-13 | C-errors | tablet | PASS | – |  |
| F-13 | C01 | desktop | PASS | – |  |
| F-13 | C01-crumb | desktop | PASS | – |  |
| F-13 | C02 | desktop | PASS | – | the first run timed out on a locator; the clean re-run (logs/f13-c02.json) passes: grid stop, Shift+→ live '2 ders saati seçildi', Enter → sheet (focus book-period), Esc one press → cell with ring, submit 202, focus on the pending cell, withdraw confirm traps 6 Tabs |
| F-13 | C02 | tablet | PASS | – | probe-final (768 touch + keyboard): rings on every stop, live region, sheet, Esc, 202, focus on the pending cell |
| F-13 | C02 | tablet | PASS | – | probe-final (768 touch + keyboard): rings on every stop, live region, sheet, Esc, 202, focus on the pending cell |
| F-13 | C02-grid | desktop | PASS | – |  |
| F-13 | C02-withdraw | desktop | PASS | – |  |
| F-13 | C04 | desktop | PASS | – | Tab order visual, rings, chip toggles with Space, Enter in a field searches; role=status sits on the summary's parent (probe-f13), as round 2 |
| F-13 | C05 | desktop | PASS | – | tabs by arrows, Tab stays inside the reset confirm (aria-modal), reset → focus on sync-url-mine; copy by Enter and Space → 'Bağlantı kopyalandı' (probe-copy-enter, the first run sampled too early); the row checkbox is the F-04 S10 one (locator) |
| F-13 | C05-copy-keyboard (probe-copy-enter) | desktop | PASS | – | Enter and Space on 'Kopyala' → 'Bağlantı kopyalandı', focus stays on the button, no pageerror; a fresh session shows only '1 özel bağlantınız var…' without URLs (by design) |
| F-13 | C06 (probe-final) | tablet | PASS | – | 768×1024 hasTouch + keyboard: controlHmd 44px, grid Tab/arrows/Shift+→/Enter/Esc with rings on every stop, 'Vazgeç' and 'book-submit' rings, 202, focus on the pending cell |
| R3 | A02-chips | desktop | SKIP | – | method: PUT /auth/profile {language:en} did not switch the page language (title stayed TR); the UI switch is r3b A02-chips-ui / F-13 A02 |
| R3 | A02-chips | phone | SKIP | – | same method note |
| R3 | C02-C05-trap | desktop | PASS | – | aria-modal=true, 10 Tabs and 4 Shift+Tabs stay inside both confirms; the Esc part is re-run in r3b (C02-esc-*) |
| R3 | C02-C05-trap | tablet | PASS | – |  |
| R3 | M-09@/bookings | phone | PASS | – |  |
| R3 | M-09@/bookings | tablet | PASS | – |  |
| R3 | M-09@/find-room | phone | PASS | – |  |
| R3 | M-09@/find-room | tablet | PASS | – |  |
| R3 | M-09@/moderation/me | phone | PASS | – |  |
| R3 | M-09@/moderation/me | tablet | PASS | – |  |
| R3 | M-09@/moderation/people/157 | phone | PASS | – |  |
| R3 | M-09@/moderation/people/157 | tablet | PASS | – |  |
| R3 | M-09@/my-bookings | phone | PASS | – |  |
| R3 | M-09@/my-bookings | tablet | PASS | – |  |
| R3 | M-09@/profile | phone | PASS | – |  |
| R3 | M-09@/profile | tablet | PASS | – |  |
| R3 | S01-card-name | desktop | PASS | – |  |
| R3 | S01-card-name | phone | PASS | – |  |
| R3 | S01-crumb | desktop | PASS | – |  |
| R3 | S01-crumb | phone | PASS | – |  |
| R3 | S02-hints | desktop | PASS | – |  |
| R3 | S02-hints | phone | PASS | – |  |
| R3 | S03-span | desktop | PASS | – |  |
| R3 | S03-span | phone | PASS | – |  |
| R3 | S05-copy | desktop | PASS | – |  |
| R3 | S05-copy | phone | PASS | – | worded 44 px copy buttons, denied clipboard → toast 'Kopyalanamadı: bağlantıyı alandan seçin', field focused, no pageerror; the toast close read 42×42 in the sweep vs 44×44 by direct query → r3b M-02@toast-close |
| R3 | S05-profile-quiet | desktop | PASS | – |  |
| R3 | S05-profile-quiet | phone | PASS | – |  |
| R3 | S06-description | desktop | FAIL | R2-A-11 | no DESCRIPTION in any of the 3 VEVENTs although bookings 3/4 carry notes 'Telafi dersi' (reopened) |
| R3 | S06b-202 | desktop | PASS | – |  |
| R3 | S06b-202 | phone | PASS | – |  |
| R3 | S06b-202 | tablet | PASS | – |  |
| R3 | S07-reset | desktop | PASS | – |  |
| R3 | S07-reset-en | desktop | PASS | – |  |
| R3 | S09-bell-samepage | desktop | PASS | – | expanded, reason + 'Karar veren', focus on the row; the popover is keepMounted (present but closed): r3b S09-bell-panel confirms it is hidden |
| R3 | S09-bell-samepage | phone | PASS | – |  |
| R3 | errors | desktop | PASS | – |  |
| R3 | errors | phone | PASS | – |  |
| R3 | errors | tablet | PASS | – |  |
| R3 | pre | desktop | PASS | – |  |
| R3 | pre | phone | PASS | – |  |
| R3 | pre | tablet | PASS | – |  |
| R3b | A02-chips-ui | desktop | PASS | – |  |
| R3b | A02-chips-ui | phone | PASS | – |  |
| R3b | C02-esc-afterTabs | desktop | PASS | – |  |
| R3b | C02-esc-afterTabs | phone | PASS | – |  |
| R3b | C02-esc-plain | desktop | PASS | – |  |
| R3b | C02-esc-plain | phone | PASS | – |  |
| R3b | M-02@toast-close | phone | PASS | – | the front toast's close is 44×44 and takes the ±22 px probe; the 41.8 px one is the stacked back toast (sonner scales it 0.95) that is not the tap target |
| R3b | S09-bell-panel | desktop | PASS | – |  |
| R3b | S09-bell-panel | phone | PASS | – |  |
| R3b | errors | desktop | PASS | – |  |
| R3b | errors | phone | PASS | – |  |
| R3c | F01-S05-approvers | desktop | PASS | – |  |
| R3c | F01-S05-approvers | phone | PASS | – |  |
| R3c | F03-S03-phone | phone | PASS | – | text 'PC' in the sheet (44 px, 16 px) → '0 boş oda': the 4 PC-tagged rooms are all busy at that window (curl/R3-F03-oracle-text.txt), no 'istenmedi'; fr-text lives in the Filtreler sheet (R3-A-02) |
| R3c | F03-S04-phone | phone | PASS | – |  |
| R3c | F05-S02-crumb-ring | desktop | PASS | – |  |
| R3c | F05-S02-labels | desktop | PASS | – |  |
| R3c | F05-S02-labels | phone | PASS | – |  |
| R3c | F05-S03-sheet-close | desktop | PASS | – |  |
| R3c | F05-S03-sheet-close | phone | PASS | – | 'Kapat' 36×36 box, 44 px hit area (M-02@/moderation/me(wish) sweep clean) |
| R3c | errors | desktop | PASS | – |  |
| R3c | errors | phone | PASS | – |  |

## Machine-readable rows

Issue and re-verification rows: [`round-3-academician.jsonl`](round-3-academician.jsonl). Step rows (one per step × viewport) are in the evidence root `step-rows.jsonl`.
