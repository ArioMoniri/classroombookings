# Flow loop round 2 · academician · 2026-10-17

Ledger: `flow-r2-academician-2026-10-17` · persona tester (academician) · plan: [README](../README.md), [MOBILE](../MOBILE.md), brief `scratchpad/briefs/ROUND2.md`
Snapshot: `deb38315` (`deb38315eac87ed0e924cdf87e886b3e46545094`, origin/claude/focused-wright-ktt0ss), frozen worktree `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2acad/flow-src-deb3831` (removed at the end) · stack API :19220, web :19221 (`REC_WORKDIR=/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2acad/stack`, `REC_TEACHER=1 REC_LANG=tr REC_CAL_SIGNOFF=0`) · load 0.1–3.5 on 4 cores during the round (`uptime` 00:43 → 02:02; two other testers running), timing rows PASS at 1×
Dates (README §4.3): TODAY 2026-10-17 · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D6 2026-11-26 · Chromium 141 (chromium-1194 headless shell), Playwright 1.56.1 library, touch contexts from `scripts/record/lib/touch.mjs` (`assertTouch` before every M-02/M-03/M-05/M-12, `shot()` for full-page shots)
Data: all three real terms + room master; runs #7 Bahar week 3 (688/716), #8 Bahar term (683/717, published), #9 Güz week 3 (524/530), #10 Güz term (517/530, published), all hard 100. Names masked by `stack.sh` + the §4.4 seed (`kvkk_mask.py --verify` → `left 0`).
Accounts: `akademisyen.test@smartsched.local` ("A. T.", TEACHER, user 4) linked to instructor 157 ("Dr. Öğr. Üyesi S. E.", PSY 277 / PSY 278) through `PUT /auth/sso/admin/users/4/instructor` → 200; `personel.test` (staff helper), admin as approver for all rooms. SMTP sink :2527 (`/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2acad/mail`).
Preconditions applied per flow after `REC_SNAPSHOT=1 REC_SKIP_BUILD=1 stack.sh up`: `approval_mode=all`, starter feature catalogue (+adopt-tags; PC feature = 'Bilgisayar laboratuvarı' id 1), calendar sync signed off by the admin API for F-04/F-13, `integrations.public_url` = the web URL (F-12 SSO), Microsoft Entra with the fake tenant `1111…5555` for F-12 S11–S15 only (switched off afterwards), privacy notices TR v1 / EN v2 / TR v3 for the R1-A-26 re-check. Admin decisions (approve, reject with reason, accept/reject wishes, publish notices) were made through the API; the admin UI is the admin tester's.
Rooms (F-01): R2 = A 104 (id 4, 41 seats) · D1 · P3; R3 = C 306 (id 37, 30 seats; C z01 holds ING 105 at P5) · D3 · P5; two-period RG = C 303 (id 34) · D3 · P7–P8. F-04: B1 A 104 D1 P3, B2 C 303 D3 P7+P8, B3 C 304 D3 P10 (cancelled 'Oda bakımda'), R1 = the first free A-block slot on D1 (A 107 P5).
Viewports: desktop 1440×900 (mouse, keyboard) and phone 390×844 (isMobile + hasTouch, tap only); tablet 768×1024 + keyboard for F-13 C06 only (the brief's two viewports).
Evidence root (scratch, not committed): `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2acad/ev` — `shots/` (99), `curl/` (50, tokens redacted), `mail/` (8 .eml), `logs/` (`f*.json`, `f*.log`, `step-table.md`), `scripts/` (`lib.mjs`, `mobile.mjs`, `f01/f03/f04/f05/f12/f13.mjs`, `probe-*.mjs`; re-runnable with `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node <script>`).

Scope note: the Fatih Bey planning scenarios (week 3, PHAR 240 move, nursing rule, Excel export, 102-in-30) belong to the admin tester and were not run here.

## BLUF

**Round-1 ids: 40 re-run → 37 verified · 3 reopened** (R1-A-17 only partly: the booking list still splits a span; R1-A-35 and R1-A-36 are the two unbuilt suggestions FLE-001 / FLE-006).
**New findings: 19 — 0 blocker · 4 major · 10 minor · 2 trivial · 3 suggestion.** The academician finishes every flow on both viewports; the round-1 majors (Taleplerim layout and loading, approval-first wording, focus after actions, the KVKK export, the phone keyboard in the sheets, the bell sheet, notification cards, breadcrumbs, the login form) are fixed and hold.

The four majors:
1. **R2-A-02** · page-level fields hide under the keyboard: `/profile` 'Yeni parola' under the sticky Kaydet bar, `/find-room` 'Kaç kişi' below the viewport (the T-R1-02 clearance only lives in sheets).
2. **R2-A-03** · the confirm dialogs (withdraw a request, reset the private link) do not trap focus: Tab leaves to the page's skip link and logo (A-20 regression, `alertdialog` without `aria-modal`).
3. **R2-A-04** · `/find-room` 'Ara' is not sticky on the phone (scrolls away at 400 px; round 1 saw it too, no ticket took it).
4. **R2-A-05** · small controls on `/find-room` at 390: 'Neden?' 62×16, filter chips 24 px, switches 38×22, the 'PC sayısı' input 28 px.

Most visible minor: **R2-A-01**, the four-tab bar now overlaps 'Rezervasyonlar' and 'Rezervasyonlarım' into one word on every phone route.

Steps: F-01: 63 pass / 2 fail / 1 skip · F-03: 40 pass / 10 fail / 0 skip · F-04: 37 pass / 5 fail / 3 skip · F-05: 55 pass / 2 fail / 2 skip · F-06: 1 pass / 0 fail / 0 skip · F-12: 59 pass / 3 fail / 7 skip · F-13: 23 pass / 5 fail / 0 skip (one row per step × viewport, MOBILE.md criteria included; FAIL rows all map to an R2 id). Full table below.

What works well now (keep): approval-first everywhere (cells, slots, cards, popover, policy API); request → reject with reason → bell/mail/Taleplerim → withdraw, with focus kept; one Taleplerim row per submission; the bell as a bottom sheet; notification cards by role; Taleplerim at 1440 with the assigned room, session labels and 35 ms render; 'Tercih ekle' with duplicate and fixed-class guards and the focused receipt; the KVKK export with instructor, planning requests and wishes; the notice in the reader's language with focus to `#main`; login messages, Caps Lock, per-identifier lock, SSO-off sentence, PKCE start redirect; language switch toasts; reduced motion/transparency; the keyboard path over the grid (live region, Esc, rings) and Taleplerim rows.

## Round-1 ids re-verified on deb38315

| id | result | note |
|---|---|---|
| R1-A-01 | verified `deb38315` | F-05 S01 @1440: every mine-pair cell scrollWidth ≤ clientWidth and names the assigned room ('… → Çar P7–P9 13:30–15:50 · A 207'); table columns Ders / İstenen → Atanan / Durum / Neden / Tercihim |
| R1-A-02 | verified `deb38315` | M-02 clean on /login, /bookings (+book sheet, bell), /my-bookings (+withdraw, cancel), /moderation/me (+wish sheet), /moderation/people/157, /profile (+#notifications) at 390 touch with assertTouch; the sweep's switch hits were collapsed groups. New small controls elsewhere: R2-A-05, R2-A-13 |
| R1-A-03 | verified `deb38315` | book sheet note 228–292 and 'Talep et' 452–496 at 390×508; wish room search 316–360, 'Onaya gönder' 392–436; cancel reason 262–326; meta has interactive-widget=resizes-content. Page-level forms are a new case: R2-A-02 |
| R1-A-04 | verified `deb38315` | inputsUnder16 = [] on every route (16 px on touch); badge 11 px |
| R1-A-05 | verified `deb38315` | grid cells 'A 104, P3, 10:10–10:50, boş, Talep et · Onay gerekir'; phone slots '… için talep et (onay gerekir)'; find-room 'Onay gerekir' + 'Talep et'; popover 'Onaylayıcılara gider: Rezervasyon onayı ayarı «Her talep önce onaya»…'; GET /booking-policies/effective → request/approval_mode. Two helper texts left: R2-A-07 |
| R1-A-06 | verified `deb38315` | after requesting C 303 the card reads 'Talebiniz bekliyor' with 'Talebi aç' → /my-bookings?request=2; phone slot list shows free-slot-pending 'talebiniz bekliyor, talebi aç' |
| R1-A-07 | verified `deb38315` | one 'Başka saat' alternative worded 'A 103 12:40-14:10 boş (1 ders saati erken başlar)'; the 19 feature-missing rooms sit collapsed under 'Özelliği eksik odalar (19)' |
| R1-A-08 | verified `deb38315` | no 'ms' in the result header |
| R1-A-09 | verified `deb38315` | TR mail/bell: 'Gerekçe: Oda uygun değil: Bu saatte bölüm sınavı var.' + 'Önerilen derslikler (otomatik): B 207.'; EN: 'Reason: Not enough seats: Sınav haftası' + 'Suggested rooms (automatic): …'; second withdraw 409 'Bu talep geri çekilmiş; geri çekilemez.' (no enum) |
| R1-A-10 | verified `deb38315` | profile role 'Öğretim elemanı'; SSO hint 'hesabınız Öğretim elemanı olarak açılır'; dialog close buttons 'Kapat'; toast close 'Bildirimi kapat'; search trigger 'Komut paleti (Ctrl+K)'; 403s carry message_tr ('Yalnız kendi taleplerinizi görebilirsiniz.', 'Bu işlem için … izni gerekiyor') |
| R1-A-11 | verified `deb38315` | /moderation/people/157 crumb 'Taleplerim / Geçmişim', no id; the crumb link shows a 2 px outline on Tab. The /moderation/me crumb still starts with 'Moderasyon': R2-A-14 |
| R1-A-12 | verified `deb38315` | subtitle 'Güz 2026-27 · Dr. Öğr. Üyesi S. E.'; hint 'Bir derse tıklayın ya da dokunun…'; rows labelled Teori / Laboratuvar; 'Erişilebilirlik ihtiyacı yok'; wish mail names 'Güz 2026-27' |
| R1-A-13 | verified `deb38315` | second identical building wish → 409 'Bu tercih zaten gönderildi ve koordinatörün kararını bekliyor.' |
| R1-A-14 | verified `deb38315` | Zaman aralığı on fixed classes: warning + 'Onaya gönder' disabled, no console error; 0 classes → 'En az bir ders seçin.' disabled |
| R1-A-15 | verified `deb38315` | focus after the first grid request = the pending cell; after a sent wish = DIV[wish-sent]; after Ara = P[fr-summary]; after 'Okudum' = #main (both viewports) |
| R1-A-16 | verified `deb38315` | 'Talep et' → 'Gönderiliyor…' with aria-busy=true (MutationObserver) |
| R1-A-17 | reopened `deb38315` | Taleplerim now shows one row 'C 303 · P7–P8 (13:30–15:00)' with one status and the admin mail/ICS treat it as one; but the Yaklaşan booking list still lists P7 and P8 as two rows: R2-A-10 |
| R1-A-18 | verified `deb38315` | unread count unchanged (1 → 1) after my own withdrawal |
| R1-A-19 | verified `deb38315` | phone bell = full-width bottom sheet (390 px, flush with the bottom, role dialog, data-variant sheet), items 98–114 px, badge 11 px |
| R1-A-20 | verified `deb38315` | room select 'Oda seçin', department select 'Bölüm seçin' (147 options) |
| R1-A-21 | verified `deb38315` | with a link in place only 'Özel bağlantıyı sıfırla' is offered; a new context reads '1 özel bağlantınız var: 17.10.2026 tarihinde oluşturuldu…'; reset → old URL 404, new 200 |
| R1-A-22 | verified `deb38315` | cancelled card 'Gerekçe: Ders iptal oldu'; approved rows 'Onaylayanın notu: Onaylandı, iyi dersler.'; the dialog hint reads 'Gerekçe iptal edilen rezervasyonla birlikte saklanır ve kartında görünür.' |
| R1-A-23 | verified `deb38315` | phone: 0 tables, 0 sideways scrollers, 3 card groups; no 'Onayımı bekleyen…' / 'Sorumlu olduğum…' rows for the teacher |
| R1-A-24 | verified `deb38315` | the row now says plainly 'Kurumunuz, bu rızayı geri almayan herkesi yapay zekâ asistanı isteklerine dahil eder. Geri aldığınızda … yer tutucuyla değiştirilir.' (an objection to an institutional default); the owner decision R1-M-07 stays open |
| R1-A-25 | verified `deb38315` | the zip (58 files) has instructor.json, instructor_sections, planning_requests.json (8 rows = 4 Güz + 4 Bahar), teacher_preferences.json (2 wishes with status and the coordinator's reason), README.txt; no other user's e-mail |
| R1-A-26 | verified `deb38315` | TR v1 + EN v2 published → GET /me/privacy (tr) returns v1 'Aydınlatma metni (test)'; the gate shows it, Esc does not dismiss, 'Okudum' → focus MAIN#main; phone: bottom sheet, Okudum in the bottom 40 % |
| R1-A-27 | verified `deb38315` | empty submit → 'Kullanıcı adı veya e-posta gerekli' / 'Parola gerekli' with aria-invalid + aria-describedby; wrong password → focus on login-error, password cleared; 'Caps Lock açık'; inputmode=email + autocomplete username/current-password |
| R1-A-28 | verified `deb38315` | 11 failures → 429 'Çok fazla deneme. 5 dakika sonra tekrar deneyin.' and the button disabled; typing another identifier re-enables it |
| R1-A-29 | verified `deb38315` | SSO off: 302 /login?error=not_enabled (no ref) → 'Microsoft ile giriş bu kurumda henüz açık değil.' |
| R1-A-30 | verified `deb38315` | TR→EN save toast 'Saved', EN→TR 'Kaydedildi' (both viewports) |
| R1-A-31 | verified `deb38315` | tab bar Rezervasyonlar · Rezervasyonlarım · Taleplerim · Diğer; exactly one aria-current on every route; no 'Klavye kısayolları' in the touch user menu. The 4-tab bar now clips labels: R2-A-01 |
| R1-A-32 | verified `deb38315` | phone /bookings?date=…: 0 pageerror in both F-01 runs |
| R1-A-33 | verified `deb38315` | Tab from 'Tercih ekle' visits all four rows (tabindex 0, rings), Enter opens the sheet with the class ticked, Esc returns to the row; the hint names the Tab key |
| R1-A-34 | verified `deb38315` | plan drift (T-R1-40): instructor 157's building-A prior exists (8/8 rows over 2026-BAHAR + 2026-GUZ) and is 'hidden' with hidden_reason room_already_set; teacher GET /learning/suggestions → 403 with message_tr |
| R1-A-35 | reopened `deb38315` | enhancement FLE-001 not built: the academician's book sheet still has no 'Tek seferlik / Her hafta' choice (no fieldset or hint); unchanged, suggestion |
| R1-A-36 | reopened `deb38315` | suggestion FLE-006 not built: at 1440 the sign-in card fills the left 490 px, the rest is an empty gradient; the password field is grey while the identifier is white (phone: both grey) |
| R1-A-37 | verified `deb38315` | welcome toast gone 3.5 s after login, never over the tab bar |
| R1-A-38 | verified `deb38315` | 4 rows 35–60 ms after networkidle; only GET /moderation/me/matchings?term_id=2 (no limit=5000) |
| R1-A-39 | verified `deb38315` | F-01 S04 (detail sheet 'Onay bekliyor' + link; API 409), F-03 oracle {"field"} (200), F-12 entra/start?next= + error codes, REC_CAL_SIGNOFF=0 (signoff null), the PUT instructor link: all as the updated flow files say |
| R1-A-40 | verified `deb38315` | shortcuts sheet shows 'Ctrl K', 'Ctrl B', 'G sonra B/M/T' incl. 'Taleplerim sayfasına git', no ⌘, teacher-only entries |

## Step table (one row per step × viewport; MOBILE.md rows are `M-xx@route`)

Results were adjudicated after the script runs: a step whose first run failed on a locator or on my own data choice and passed on the re-run or the follow-up probe is PASS with the probe named in the note; every FAIL maps to an R2 id. Raw per-run output: `logs/f*.log`, `logs/f*.json`.

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
| F-01 | M-04@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-04@/my-bookings(withdraw) | phone | PASS | – |  |
| F-01 | M-04@bell | phone | PASS | – |  |
| F-01 | M-05@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-06@/my-bookings | phone | PASS | – |  |
| F-01 | M-07@/my-bookings | phone | PASS | – |  |
| F-01 | M-07@/profile#notifications | phone | PASS | – |  |
| F-01 | M-08@/bookings | phone | PASS | – |  |
| F-01 | M-09@/my-bookings | phone | FAIL | R2-A-01 |  |
| F-01 | M-09@/profile#notifications | phone | FAIL | R2-A-01 |  |
| F-01 | M-10@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-10@/my-bookings(bell) | phone | SKIP | – |  |
| F-01 | M-11@/bookings(book-sheet) | phone | PASS | – |  |
| F-01 | M-11@/my-bookings | phone | PASS | – |  |
| F-01 | M-11@/my-bookings(bell) | phone | PASS | – |  |
| F-01 | M-11@/profile#notifications | phone | PASS | – |  |
| F-01 | M-12@/bookings(book-sheet note) | phone | PASS | – |  |
| F-01 | S02 | desktop | PASS | R2-A-07 | check=request/approval_mode, effective=request, cells 'Talep et · Onay gerekir', sheet notice; helper still says 'rezerve etmek' |
| F-01 | S02 | phone | PASS | R2-A-07 | check=request/approval_mode, effective=request, cells 'Talep et · Onay gerekir', sheet notice; helper still says 'rezerve etmek' |
| F-01 | S02-chips | phone | PASS | – |  |
| F-01 | S02-labels | desktop | PASS | – |  |
| F-01 | S02-labels | phone | PASS | – |  |
| F-01 | S04 | desktop | PASS | – |  |
| F-01 | S04 | phone | PASS | – | a tap on the pending slot opens the request (/my-bookings?request=1) — the phone's designed path; API 409 duplicate_request TR |
| F-01 | S05 | desktop | PASS | – |  |
| F-01 | S05 | phone | PASS | – |  |
| F-01 | S06-notify | desktop | PASS | – |  |
| F-01 | S06-notify | phone | PASS | – |  |
| F-01 | S06a | desktop | PASS | – |  |
| F-01 | S06a | phone | PASS | – |  |
| F-01 | S06b | desktop | PASS | R2-A-15 | both 202/200, P7+P8 one submission; phone focus passes through BODY for ~1.5 s then lands on the free-slot heading |
| F-01 | S06b | phone | PASS | R2-A-15 | both 202/200, P7+P8 one submission; phone focus passes through BODY for ~1.5 s then lands on the free-slot heading |
| F-01 | S08 | desktop | PASS | – |  |
| F-01 | S08 | phone | PASS | – |  |
| F-01 | S09-approved-note | desktop | PASS | – |  |
| F-01 | S09-approved-note | phone | PASS | – |  |
| F-01 | S09-bell | desktop | PASS | – |  |
| F-01 | S09-bell | phone | PASS | – |  |
| F-01 | S09-deeplink | desktop | PASS | R2-A-09 | direct goto /my-bookings?request=1 expands with timeline + 'Karar veren: Administrator' |
| F-01 | S09-mail | desktop | PASS | – |  |
| F-01 | S09-mail | phone | PASS | – |  |
| F-01 | S09-mine | desktop | PASS | R2-A-09 | deep link expands the request on arrival from another page; not when already on /my-bookings |
| F-01 | S09-mine | phone | PASS | R2-A-09 | deep link expands the request on arrival from another page; not when already on /my-bookings |
| F-01 | S10 | desktop | PASS | – |  |
| F-01 | S10 | phone | PASS | – |  |
| F-01 | S11 | desktop | PASS | – |  |
| F-01 | S11 | phone | PASS | – |  |
| F-01 | S11-honoured | desktop | PASS | R2-A-15 | in-app notice, no mail within 90 s |
| F-01 | S11-honoured | phone | PASS | R2-A-15 | in-app notice, no mail within 90 s |
| F-01 | errors | desktop | PASS | – |  |
| F-01 | errors | phone | PASS | – |  |
| F-01 | pre | desktop | PASS | – |  |
| F-01 | pre | phone | PASS | – |  |
| F-03 | M-01@/find-room | phone | PASS | – |  |
| F-03 | M-01@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-01@/find-room(results) | phone | PASS | – |  |
| F-03 | M-02@/find-room | phone | FAIL | R2-A-05 |  |
| F-03 | M-02@/find-room(filters) | phone | FAIL | R2-A-05 |  |
| F-03 | M-02@/find-room(filters-detail) | phone | FAIL | R2-A-05 | feature chips 24 px, building chips 24 px, switches 38×22, 'PC sayısı' input 28 px, Kapat 36×36 |
| F-03 | M-02@/find-room(results) | phone | FAIL | R2-A-05 |  |
| F-03 | M-03@/find-room | phone | PASS | – |  |
| F-03 | M-03@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-03@/find-room(results) | phone | PASS | – |  |
| F-03 | M-04@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-05@/find-room | phone | FAIL | R2-A-04 |  |
| F-03 | M-05@/find-room(Ara) | phone | FAIL | R2-A-04 |  |
| F-03 | M-05@/find-room(results) | phone | FAIL | R2-A-04 |  |
| F-03 | M-06@/find-room | phone | PASS | – |  |
| F-03 | M-07@/find-room | phone | PASS | – |  |
| F-03 | M-07@/find-room(results) | phone | PASS | – | cards |
| F-03 | M-09@/find-room | phone | FAIL | R2-A-01 |  |
| F-03 | M-09@/find-room(results) | phone | FAIL | R2-A-01 |  |
| F-03 | M-10@/find-room | phone | PASS | – | exception: paired period selects fr-p1/fr-p2 side by side, 150 px each (≥ 140) |
| F-03 | M-10@/find-room(filters) | phone | PASS | – | same exception |
| F-03 | M-11@/find-room | phone | PASS | – |  |
| F-03 | M-11@/find-room(filters) | phone | PASS | – |  |
| F-03 | M-11@/find-room(results) | phone | PASS | – |  |
| F-03 | M-12@/find-room(headcount) | phone | FAIL | R2-A-02 |  |
| F-03 | M-14@/find-room(Ara) | phone | PASS | – |  |
| F-03 | S01 | desktop | PASS | – |  |
| F-03 | S01 | phone | PASS | – |  |
| F-03 | S01-en | desktop | PASS | – |  |
| F-03 | S01-en | phone | PASS | – |  |
| F-03 | S04 | desktop | PASS | – | phone: text lives in the filters sheet; 'Metinle eşleşen derslik yok: “yarın 14:00 60 kişi”.' + 'Metni temizle' → 9 boş oda; the text stays listed in Son aramalar as its own entry |
| F-03 | S04 | phone | PASS | – | phone: text lives in the filters sheet; 'Metinle eşleşen derslik yok: “yarın 14:00 60 kişi”.' + 'Metni temizle' → 9 boş oda; the text stays listed in Son aramalar as its own entry |
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
| F-04 | M-02@/my-bookings(cancelled tab) | phone | FAIL | R2-A-13 |  |
| F-04 | M-02@/my-bookings(sync panel) | phone | FAIL | R2-A-13 |  |
| F-04 | M-03@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-03@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-04@/my-bookings(cancel) | phone | PASS | – |  |
| F-04 | M-04@/my-bookings(sync) | phone | SKIP | – |  |
| F-04 | M-07@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-07@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-09@/my-bookings(cancelled tab) | phone | FAIL | R2-A-01 |  |
| F-04 | M-09@/my-bookings(sync panel) | phone | FAIL | R2-A-01 |  |
| F-04 | M-11@/my-bookings(cancelled tab) | phone | PASS | – |  |
| F-04 | M-11@/my-bookings(sync panel) | phone | PASS | – |  |
| F-04 | M-12@/my-bookings(cancel reason) | phone | PASS | – |  |
| F-04 | M-14@/my-bookings | phone | PASS | – |  |
| F-04 | S01 | desktop | PASS | – | panel: 'Takvim eşitleme yönetici tarafından kapatıldı.', no create; API token 201 but the feed answers 404 |
| F-04 | S01 | phone | PASS | – | panel: 'Takvim eşitleme yönetici tarafından kapatıldı.', no create; API token 201 but the feed answers 404 |
| F-04 | S02 | desktop | PASS | – |  |
| F-04 | S02 | phone | PASS | – |  |
| F-04 | S03 | desktop | PASS | R2-A-10 | totals, tabs, cancelled card with 'Oda bakımda'; the P7–P8 booking is two rows in Yaklaşan |
| F-04 | S03 | phone | PASS | R2-A-10 | totals, tabs, cancelled card with 'Oda bakımda'; the P7–P8 booking is two rows in Yaklaşan |
| F-04 | S04 | desktop | PASS | – |  |
| F-04 | S04 | phone | PASS | – |  |
| F-04 | S04-copy-words | phone | FAIL | R2-A-12 |  |
| F-04 | S05 | desktop | PASS | R2-A-12 | phone: toast 'Bağlantı kopyalandı' with clipboard permission; silent otherwise |
| F-04 | S05 | phone | PASS | R2-A-12 | phone: toast 'Bağlantı kopyalandı' with clipboard permission; silent otherwise |
| F-04 | S06 | desktop | PASS | R2-A-11 | the only '@smartsched' hits are UIDs; no ORGANIZER/ATTENDEE/names; SUMMARY 'A 104 – P3' without the note |
| F-04 | S06 | phone | PASS | R2-A-11 | the only '@smartsched' hits are UIDs; no ORGANIZER/ATTENDEE/names; SUMMARY 'A 104 – P3' without the note |
| F-04 | S07 | desktop | PASS | – |  |
| F-04 | S07 | phone | PASS | – |  |
| F-04 | S08 | desktop | PASS | – |  |
| F-04 | S08 | phone | PASS | – |  |
| F-04 | S09 | desktop | PASS | – | defaults 'Oda seçin'/'Bölüm seçin'; A 308: 234 events incl. 14 'PSY 277 (A 308)'; Psikoloji: 448; no names |
| F-04 | S09 | phone | PASS | – | defaults 'Oda seçin'/'Bölüm seçin'; A 308: 234 events incl. 14 'PSY 277 (A 308)'; Psikoloji: 448; no names |
| F-04 | S10 | desktop | PASS | – |  |
| F-04 | S10 | phone | PASS | – |  |
| F-04 | S11 | desktop | PASS | – |  |
| F-04 | S11 | phone | PASS | – |  |
| F-04 | S12 | desktop | SKIP | – |  |
| F-04 | S12 | phone | SKIP | – |  |
| F-04 | errors | desktop | PASS | – | phone: clipboard write denied without the permission (test context) |
| F-04 | errors | phone | PASS | – | phone: clipboard write denied without the permission (test context) |
| F-04 | pre | desktop | PASS | – |  |
| F-04 | pre | phone | PASS | – |  |
| F-05 | KVKK-export | desktop | PASS | – |  |
| F-05 | KVKK-export | phone | PASS | – |  |
| F-05 | KVKK-notice | desktop | PASS | – | TR v1 + EN v2 → TR reader gets v1; Esc keeps the gate; Okudum → focus #main (curl/KVKK-notice-lang.txt) |
| F-05 | KVKK-notice | phone | PASS | – | bottom sheet, Okudum at 784–828 (bottom 40 %), focus #main |
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
| F-05 | M-05@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-07@/moderation/me | phone | PASS | – | cards (the probe keys on the role=table wrapper) |
| F-05 | M-07@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-09@/moderation/me | phone | FAIL | R2-A-01 |  |
| F-05 | M-09@/moderation/people/157 | phone | FAIL | R2-A-01 |  |
| F-05 | M-10@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-11@/moderation/me | phone | PASS | – |  |
| F-05 | M-11@/moderation/me(wish) | phone | PASS | – |  |
| F-05 | M-11@/moderation/people/157 | phone | PASS | – |  |
| F-05 | M-12@/moderation/me(wish room search) | phone | PASS | – |  |
| F-05 | S01 | desktop | PASS | – | 4 rows in 35–60 ms after networkidle; only /moderation/me/matchings; pair cells not clipped, assigned rooms named; term name; row hint 'tıklayın ya da dokunun' |
| F-05 | S01 | phone | PASS | – | 4 rows in 35–60 ms after networkidle; only /moderation/me/matchings; pair cells not clipped, assigned rooms named; term name; row hint 'tıklayın ya da dokunun' |
| F-05 | S01-api | desktop | PASS | – |  |
| F-05 | S01-api | phone | PASS | – |  |
| F-05 | S01-en | desktop | PASS | – |  |
| F-05 | S01-en | phone | PASS | – |  |
| F-05 | S01-enter | desktop | PASS | – |  |
| F-05 | S01-keys | desktop | PASS | – | Tercih ekle → 4 rows (all tabindex 0, rings) → document end |
| F-05 | S01-session | desktop | PASS | R2-A-16 | Teori / Laboratuvar labels on both PSY 277 rows |
| F-05 | S01-session | phone | PASS | R2-A-16 | Teori / Laboratuvar labels on both PSY 277 rows |
| F-05 | S02 | desktop | PASS | – | crumbs Taleplerim / Geçmişim, 2 dönem, groups 'Güz 2026-27' / 'Bahar 2026', 8 rows, JASP/JAMOVI, 'Erişilebilirlik ihtiyacı yok', no other person |
| F-05 | S02 | phone | PASS | – | crumbs Taleplerim / Geçmişim, 2 dönem, groups 'Güz 2026-27' / 'Bahar 2026', 8 rows, JASP/JAMOVI, 'Erişilebilirlik ihtiyacı yok', no other person |
| F-05 | S02-crumb-ring | desktop | PASS | – | by keyboard (probe-f13.mjs): crumb 'Taleplerim' outline 2 px |
| F-05 | S03-building-already | desktop | SKIP | – | data: the department form asks 'Derslik' / a lab, not a building, so already_requested cannot fire for PSY 277 |
| F-05 | S03-building-already | phone | SKIP | – | data: the department form asks 'Derslik' / a lab, not a building, so already_requested cannot fire for PSY 277 |
| F-05 | S03-decide | desktop | PASS | – | empty reject 422 TR; accepted + rejected with reason shown, bell +2, mail names 'Güz 2026-27' (the room/building swap was my id order) |
| F-05 | S03-decide | phone | PASS | – | empty reject 422 TR; accepted + rejected with reason shown, bell +2, mail names 'Güz 2026-27' (the room/building swap was my id order) |
| F-05 | S03-duplicate | desktop | PASS | – |  |
| F-05 | S03-duplicate | phone | PASS | – |  |
| F-05 | S03-mine | desktop | PASS | – |  |
| F-05 | S03-mine | phone | PASS | – |  |
| F-05 | S03-room | desktop | PASS | – | 201, 'Gönderiliyor…' aria-busy, receipt focused (wish-sent), toast 'Tercihiniz onaya gönderildi' |
| F-05 | S03-room | phone | PASS | – | 201, 'Gönderiliyor…' aria-busy, receipt focused (wish-sent), toast 'Tercihiniz onaya gönderildi' |
| F-05 | S03-window | desktop | PASS | – |  |
| F-05 | S03-window | phone | PASS | – |  |
| F-05 | S03-withdraw-dialog | desktop | PASS | – |  |
| F-05 | S03-withdraw-dialog | phone | PASS | – |  |
| F-05 | S03-zero | desktop | PASS | – | 'En az bir ders seçin.' + disabled |
| F-05 | S03-zero | phone | PASS | – | 'En az bir ders seçin.' + disabled |
| F-05 | S04 | desktop | PASS | – |  |
| F-05 | S04 | phone | PASS | – |  |
| F-05 | errors | desktop | PASS | – | one console 'resource 409' from the sheet's dry-run/duplicate path; no pageerror |
| F-05 | errors | phone | PASS | – | one console 'resource 409' from the sheet's dry-run/duplicate path; no pageerror |
| F-05 | pre | desktop | PASS | – |  |
| F-05 | pre | phone | PASS | – |  |
| F-06 | L1/teacher | desktop | PASS | – | R1-A-34 re-check: suggestion for 157 is 'hidden' with hidden_reason room_already_set, 8/8 rows over 2 terms (plan drift, T-R1-40); teacher GET /learning/suggestions → 403 with message_tr |
| F-12 | M-01@/login | phone | PASS | – |  |
| F-12 | M-01@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-01@/profile | phone | PASS | – |  |
| F-12 | M-02@/login | phone | PASS | – |  |
| F-12 | M-02@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-02@/profile | phone | PASS | – | the 3 sweep hits were switches inside collapsed groups; centre re-probe clean |
| F-12 | M-03@/login | phone | PASS | – |  |
| F-12 | M-03@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-03@/profile | phone | PASS | – |  |
| F-12 | M-05@/login | phone | PASS | – | fits without scrolling; submit directly under the password (F-12 mobile rule), y 355–403 of 844 |
| F-12 | M-05@/login(sso-on) | phone | SKIP | – | local form collapsed behind the disclosure; primary = Microsoft link 358×48 |
| F-12 | M-05@/profile | phone | PASS | – |  |
| F-12 | M-06@/login | phone | PASS | – |  |
| F-12 | M-07@/login | phone | PASS | – |  |
| F-12 | M-07@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-07@/profile | phone | PASS | – |  |
| F-12 | M-09@/login | phone | SKIP | – | no tab bar outside the shell |
| F-12 | M-09@/login(sso-on) | phone | SKIP | – | no tab bar outside the shell |
| F-12 | M-09@/profile | phone | FAIL | R2-A-01 |  |
| F-12 | M-11@/login | phone | PASS | – |  |
| F-12 | M-11@/login(sso-on) | phone | PASS | – |  |
| F-12 | M-11@/profile | phone | PASS | – |  |
| F-12 | M-12@/login | phone | PASS | – |  |
| F-12 | M-12@/profile(password) | phone | FAIL | R2-A-02 |  |
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
| F-12 | S04 | desktop | PASS | – | re-run: cookie gone, old token 401, Back → /login, direct URL → /login?next= |
| F-12 | S04 | phone | PASS | – | re-run: cookie gone, old token 401, Back → /login, direct URL → /login?next= |
| F-12 | S05 | desktop | PASS | – | errors in TR; new password works, old 401; other session → 'Oturumunuzun süresi doldu…'; restored |
| F-12 | S05 | phone | PASS | – | errors in TR; new password works, old 401; other session → 'Oturumunuzun süresi doldu…'; restored |
| F-12 | S07 | desktop | PASS | – | neutral answer; code mail (24 saat) to the sink; API: wrong 400, right 200, reuse 400 (curl/F12-S07-confirm.txt) |
| F-12 | S07-code | desktop | PASS | – |  |
| F-12 | S07-request | desktop | PASS | – |  |
| F-12 | S07-ui | desktop | FAIL | R2-A-06 |  |
| F-12 | S08 | desktop | SKIP | – |  |
| F-12 | S08 | phone | SKIP | – |  |
| F-12 | S10-attrs | phone | PASS | – |  |
| F-12 | S11 | desktop | PASS | – |  |
| F-12 | S12 | desktop | PASS | – |  |
| F-12 | S12 | phone | PASS | – |  |
| F-12 | S13 | desktop | PASS | – |  |
| F-12 | S13-off | desktop | PASS | – |  |
| F-12 | S14-page | desktop | PASS | – |  |
| F-12 | S14/S15 | desktop | PASS | – | forged → error=failed+ref, access_denied → error=cancelled, 32-char ticket → 401; a <16-char ticket → 422 (pydantic) |
| F-12 | S18 | desktop | BLOCKED | – |  |
| F-12 | S18 | phone | BLOCKED | – |  |
| F-12 | errors | desktop | PASS | – | only the expected 401/403/422/429 of the negative tests |
| F-12 | errors | phone | PASS | – | only the expected 401/403/422/429 of the negative tests |
| F-13 | A-errors | desktop | PASS | – | the 404 page's own resource errors |
| F-13 | A-errors | phone | PASS | – | the 404 page's own resource errors |
| F-13 | A01 | desktop | PASS | – | no EN words on 6 routes + sheet + bell; titles TR; 404 in the shell → /bookings; role 'Öğretim elemanı' |
| F-13 | A01 | phone | PASS | – | no EN words on 6 routes + sheet + bell; titles TR; 404 in the shell → /bookings; role 'Öğretim elemanı' |
| F-13 | A01-crumb | desktop | FAIL | R2-A-14 |  |
| F-13 | A01-crumb | phone | FAIL | R2-A-14 |  |
| F-13 | A02 | desktop | FAIL | R2-A-08 | Saved/Kaydedildi toasts right; titles EN; 'Send request'; chips still 'A Blok' |
| F-13 | A02 | phone | FAIL | R2-A-08 | Saved/Kaydedildi toasts right; titles EN; 'Send request'; chips still 'A Blok' |
| F-13 | A03 | desktop | PASS | – |  |
| F-13 | A04 | desktop | PASS | – |  |
| F-13 | A04 | phone | PASS | – |  |
| F-13 | B01 | desktop | PASS | – | reduced motion: open transitions are 10 ms (near-zero), final state at 50 ms; nothing on an idle page |
| F-13 | B01 | phone | PASS | – | reduced motion: open transitions are 10 ms (near-zero), final state at 50 ms; nothing on an idle page |
| F-13 | B02 | desktop | PASS | – |  |
| F-13 | B02 | phone | PASS | – |  |
| F-13 | B03 | desktop | PASS | – | backdrop none; sheet/bell/tab bar opaque gradients; the header's opaque layer is a child span |
| F-13 | B03 | phone | PASS | – | backdrop none; sheet/bell/tab bar opaque gradients; the header's opaque layer is a child span |
| F-13 | B03-header | phone | PASS | – | reduced transparency, scrolled: opaque bar (child layer rgb 247,248,250) |
| F-13 | B04 | desktop | PASS | – |  |
| F-13 | C-errors | desktop | PASS | – |  |
| F-13 | C-errors | tablet | PASS | – |  |
| F-13 | C01 | desktop | PASS | – |  |
| F-13 | C01-crumb | desktop | PASS | – |  |
| F-13 | C02 | desktop | PASS | – | probe-f13b: live '2 ders saati seçildi, 10:10–11:40, A 104.', Enter → sheet (focus book-period), Esc one press → cell with ring, Tab path rings, Enter submits, focus on the pending cell |
| F-13 | C02 | tablet | PASS | – | probe-final: hasTouch + keyboard, rings on every stop |
| F-13 | C04 | desktop | PASS | – | role=status on the summary's parent |
| F-13 | C05 | desktop | FAIL | R2-A-03 | tabs arrow keys OK, copy by Enter OK (toast with clipboard permission), reset → focus sync-url-mine; the confirm lets Tab out |
| F-13 | C06 | tablet | PASS | – | grid Tab/arrows/Shift+→/Enter/Esc with visible rings (F13-C06-grid-acad-tablet.png) |

## New findings

| id | flow step | severity | what I did | what happened | expected | evidence | file hints |
|---|---|---|---|---|---|---|---|
| R2-A-01 | MOBILE M-09 on every academician route @390 | minor | Read the tab bar on /bookings, /my-bookings, /find-room, /moderation/me, /moderation/people/157, /profile at 390×844 (touch). | With four tabs (Rezervasyonlar · Rezervasyonlarım · Taleplerim · Diğer, 74 px each) the labels 'Rezervasyonlar' (83 px) and 'Rezervasyonlarım' (96 px) overflow their tabs (white-space nowrap, overflow visible) and overlap into one word, 'RezervasyonlaRezervasyonlarım'. aria-current is right (Taleplerim / Rezervasyonlarım / Diğer). | Every label fully visible (MOBILE.md M-09): shorter labels, a smaller font at 4 tabs, or two-line labels. | `shots/F12-tabbar-acad-phone.png`<br>`shots/F05-S01-taleplerim-acad-phone.png`<br>`logs/f13.json` | smartsched/frontend/src/components/shell/tab-bar.tsx (label width at 4 items; T-R1-06 added the Taleplerim tab) |
| R2-A-02 | MOBILE M-12 F-12 S05 /profile (Yeni parola) · F-03 S02 /find-room (Kaç kişi) @390 | major | Tapped the field and shrank the viewport to 390×508 (keyboard proxy, MOBILE.md M-12). | Page-level forms have no keyboard clearance: /profile 'Yeni parola' sits at 390–434 while the page's sticky 'Kaydet' bar (bottom 5.5 rem, 368–412) covers its upper half (elementFromPoint = the sticky DIV); /find-room 'Kaç kişi' stays at 513–557, fully below a 508 px viewport, nothing scrolls it into view ('Ara' is visible at 384–428). The Sheet/Dialog clearance of T-R1-02 works (book sheet note 228–292, wish room search 316–360, cancel reason 262–326 all uncovered). | The focused field stays visible and uncovered with the keyboard open, and the sticky bar clears it (M-12). | `shots/F12-S05-keyboard-acad-phone.png`<br>`logs/f12.log#M-12@/profile(password)`<br>`logs/f03-phone.log#M-12@/find-room(headcount)` | smartsched/frontend/src/components/ui/keyboard-clearance.tsx (only mounted inside Sheet/Dialog), smartsched/frontend/src/components/admin/profile-view.tsx (sticky save bar), smartsched/frontend/src/components/findroom/find-room-view.tsx |
| R2-A-03 | F-13 C02 (withdraw confirm) · F-13 C05 (reset-link confirm) @1440 keyboard | major | Opened 'Talebi geri çek' and 'Özel bağlantıyı sıfırla' by keyboard and pressed Tab repeatedly inside the confirm. | The confirm is role=alertdialog without aria-modal and does not trap focus: after 'Kapat' the next Tab lands on a SPAN outside the dialog, then BODY, then the page's skip link 'İçeriğe atla' and the 'SmartSched' logo, before coming back to 'Vazgeç'. Enter on the confirm still works and focus returns to the row / the new URL afterwards. | A modal confirm cycles focus between its own controls (A-20); aria-modal=true. | `logs/f13.log#C05`<br>`scripts/probe-f13.mjs`<br>`scripts/probe-f13b.mjs (C02-withdraw cycle)` | smartsched/frontend/src/components/ui/dialog.tsx / alert dialog (base-ui modal prop), smartsched/frontend/src/components/approvals/my-requests.tsx (withdraw ConfirmDialog), smartsched/frontend/src/components/bookings/calendar-sync.tsx (reset confirm) |
| R2-A-04 | MOBILE M-05 F-03 /find-room 'Ara' @390 | major | Ran the M-05 probe on the find-room form (fr-search) at scroll 0 / 400 / end. | 'Ara' is not sticky: y 711–755 at the top, 311–355 after 400 px, then off-screen (−1817) at the end of the results. The F-03 mobile expectation ('a sticky primary action … does not scroll away when the form is taller than the screen') is not met; round 1's M-05 table already read 'Ara not sticky' but no ticket took it. | 'Ara' stays in the bottom 40 % while the form and the results scroll (M-05). | `logs/f03-phone.log#M-05@/find-room(Ara)`<br>`shots/F03-S11-results-acad-phone.png` | smartsched/frontend/src/components/findroom/find-room-view.tsx (form footer) |
| R2-A-05 | MOBILE M-02 F-03 /find-room results + filters sheet @390 | major | Ran the M-02 probe (sweep + centre re-probe) on the results and with the 'Filtreler' sheet open. | Result cards: the 'Neden?' policy link is 62×16 with no hit area. Filters sheet: feature chips (fr-feature-1…8) and building chips 'A Blok'… are 24 px tall (Chip size sm; neighbours intercept the ±22 px probe), the two switches 38×22, the 'PC sayısı, en az' number input 28 px, 'Kapat' 36×36. F-03's mobile expectation asks for ≥ 44 px chips in that sheet. | Every control ≥ 44 px or a 44 px hit area (M-02). | `logs/f03-phone.log#M-02@/find-room(results)`<br>`scripts/probe-f03-phone.mjs output`<br>`shots/F03-filters-sheet-acad-phone.png` | smartsched/frontend/src/components/findroom/find-room-view.tsx (Chip size=sm in the sheet, number input), smartsched/frontend/src/components/policies/policy-why.tsx (trigger min-h on coarse pointers) |
| R2-A-06 | F-12 S07 /reset-password › Kodum var @1440 | minor | Opened 'Kodum var', typed a wrong 6-digit code and a new password. | The password hint reads 'En az 8 karakter. Dizin (LDAP) hesapları için boş bırakın.' (the users-admin hint reused; U-21 asked for no LDAP text here), and the wrong code is refused with the raw English 'String should have at least 8 characters' (pydantic 422: the confirm schema's token min_length=8 is not a coded Refusal). The request step is fine: neutral answer for unknown addresses, mail with '24 saat geçerli', right code 200, reuse 400. | Hint 'En az 8 karakter.'; a Turkish refusal for a wrong or short code. | `shots/F12-S07-wrongcode-acad-desktop.png`<br>`curl/F12-S07-confirm.txt`<br>`mail/F12-S07-reset-code.eml` | smartsched/frontend/src/components/admin/reset-password.tsx (crbs.users.passwordHint), smartsched/backend/app/api/v1/org.py password-reset/confirm schema (token min_length → messages.coded) |
| R2-A-07 | F-01 S02 book sheet + grid legend (approval_mode=all) | minor | Read the book sheet and the grid legend as the academician under approval-first. | Cells, slots, buttons and the popover are right ('Talep et · Onay gerekir', 'Onaylayıcılara gider'), but two helper texts still promise a booking: the sheet's period hint 'Birlikte rezerve etmek için önceki ya da sonraki saatleri ekleyin.' and the grid legend 'Boş bir saate tıklayıp rezerve edin.' | Mode-aware helper texts ('Birlikte talep etmek için…', 'Boş bir saate tıklayıp talep edin.'). | `shots/F01-S02-sheet-acad-desktop.png`<br>`logs/f01-desktop.log#S02` | smartsched/frontend/src/components/bookings/book-sheet.tsx (periods hint), smartsched/frontend/src/components/bookings/booking-grid.tsx (legend) |
| R2-A-08 | F-13 A02 English mode | minor | Switched the profile to English and visited /bookings and /find-room. | The building chips keep the Turkish word: '/bookings' group tabs 'A Blok (20) · B Blok (9) · C Blok (27) · D Blok (2)', find-room building chips 'A Blok'. Everything else switched ('Bookings · SmartSched', 'Send request', 'This room needs approval', 'Find a room', 'My bookings'). | 'Block A' / 'A block' in English (U-10's EN variant). | `shots/F13-A02-en-acad-desktop.png`<br>`logs/f13.json#A02` | room group names come from the booking setup ('A Blok'); smartsched/frontend/src/components/bookings/bookings-view.tsx group tabs, findroom/find-room-view.tsx wave1.find.building |
| R2-A-09 | F-01 S09 bell → request | minor | While already on /my-bookings, opened the bell and selected 'Oda talebiniz reddedildi: …'. | The URL changes to /my-bookings?request=1 but the request stays collapsed and focus stays on the bell; nothing visibly happens. Arriving from another page (or a direct load) expands the request with the reason, 'Karar veren: Administrator' and the timeline. | The deep link expands (and scrolls to) the request whatever the current page. | `scripts/probe-f01b.mjs output (bell→deeplink from /my-bookings: exp false; from /bookings: exp true)`<br>`shots/F01-S09-deeplink-acad-desktop.png` | smartsched/frontend/src/components/approvals/my-requests.tsx (initiallyOpen read once in useState; react to the ?request param change) |
| R2-A-10 | F-04 S03 Yaklaşan @1440/@390 | minor | Looked at an approved two-period request (C 303 P7–P8) in Rezervasyonlarım. | Taleplerim shows one row 'C 303 · Per 5 Kas · P7–P8 (13:30–15:00)' and the feed one VEVENT, but the Yaklaşan booking list shows two rows 'C 303 · P7 13:30' and 'C 303 · P8 14:20', each with the approver's note. | One row 'P7–P8' (A-12, F-04 S03 target). | `shots/F04-S03-mine-acad-desktop.png`<br>`logs/f04.json#S03` | smartsched/frontend/src/components/bookings/my-bookings-view.tsx (group the booking list by multi_booking_id / group_id, as my-requests.tsx does) |
| R2-A-11 | F-04 S06 mine.ics | minor | Parsed the personal feed. | Events carry room and period only: 'SUMMARY:A 104 – P3', 'LOCATION:A 104', no DESCRIPTION; the note typed in the sheet ('Ders tekrarı', 'Telafi dersi') never reaches the calendar. Statuses, VTIMEZONE Europe/Istanbul and the in-place CONFIRMED update are right. | SUMMARY carries the room code and the note (F-04 S06), or the note goes into DESCRIPTION. | `curl/F04-S06-mine-desktop.ics` | smartsched/backend/app/services/calendar_feeds.py (VEVENT builder) |
| R2-A-12 | F-04 S04/S05 sync panel @390 | minor | Created the private links on the phone and pressed the copy buttons. | The two copy buttons are icon-only (44×44, aria-label 'Web bağlantısı kopyala' / 'Takvim uygulaması bağlantısı kopyala', no visible word) although F-04's mobile expectation says 'labelled with words (not icon-only)'. When the browser refuses the clipboard, navigator.clipboard.writeText rejects unhandled (pageerror 'Write permission denied') and the user gets no toast at all; with permission the toast 'Bağlantı kopyalandı' appears. | Copy buttons with a word on phones; a 'Kopyalanamadı: bağlantıyı alandan seçin' toast when the clipboard is refused. | `shots/F04-S05-copy-acad-phone.png`<br>`shots/F04-S05-copy-acad-phone-noperm.png`<br>`scripts/probe-f04-copy.mjs output` | smartsched/frontend/src/components/bookings/calendar-sync.tsx (FeedRow copy(): no catch; size=icon) |
| R2-A-13 | MOBILE M-02 toast close @390 | minor | M-02 probe on /my-bookings while a toast was on screen. | The toast's close button ('Bildirimi kapat') is 20×20 with no hit area. | ≥ 44 px hit area (M-02). | `logs/f04.json#M-02@/my-bookings(sync panel)` | smartsched/frontend/src/components/ui/sonner.tsx (closeButton size on coarse pointers) |
| R2-A-14 | F-05 S01 breadcrumb @1440/@390 | minor | Read the crumb on /moderation/me as the academician. | 'Moderasyon / Taleplerim': the first crumb is the coordinator's word and links to /moderation (which renders Taleplerim for a teacher, so no dead end). The history page's crumb is right ('Taleplerim / Geçmişim'). | For a teacher the trail starts at 'Taleplerim' (no 'Moderasyon'). | `shots/F13-C01-shortcuts-acad-desktop.png (crumb visible)`<br>`logs/f13.json#A01-crumb` | smartsched/frontend/src/components/shell/breadcrumbs.ts (/moderation root label for users without planning.view) |
| R2-A-15 | F-01 S03/S06 API status | trivial | Watched the POST the sheet makes. | A one-period request (POST /bookings) answers 202; a multi-period or multi-slot request (POST /bookings/multi/{id}/create) answers 200 for the same pending outcome. | 202 for every request that goes to approval (F-01 S03). | `logs/f01-desktop.log#S06b` | smartsched/backend/app/api/v1/bookings.py (multi create status code) |
| R2-A-16 | F-05 S01 cards @390 | trivial | Read the Taleplerim cards' text. | The course code and the session label are glued in the accessible text: 'PSY 277Teori', 'PSY 277Laboratuvar' (visually spaced, but screen readers and copy read one word). | A space or separator between code and session label. | `logs/f05.json#S01-session (phone)` | smartsched/frontend/src/components/moderation/moderation-console.tsx (mine-session in the card layout) |
| R2-A-17 | F-04 / F-01 Rezervasyonlarım | suggestion | Looked at the page after my requests were approved. | An approved request is listed twice: as a 'Taleplerim' card ('C 303 · Onaylandı') and as a booking row under 'Yaklaşan' with the approver's note. The totals line counts the bookings only. | Decided requests leave 'Taleplerim' after a while (or collapse under 'Karara bağlanan'), so one booking shows once. | `shots/F04-S03-mine-acad-desktop.png` | smartsched/frontend/src/components/bookings/my-bookings-view.tsx, approvals/my-requests.tsx |
| R2-A-18 | F-12 S07 reset mail | suggestion | Read the reset-code mail. | One message carries both languages ('Parolanızı sıfırlamak için … / Use this one-time code…'). Before login the language is unknown, so this is defensible; the account's profile language (tr) was available though. | Use the profile language when the account is known; bilingual only for unknown addresses. | `mail/F12-S07-reset-code.eml` | smartsched/backend/app/services (issue_reset_token mail template) |
| R2-A-19 | F-13 A02 language picker | suggestion | Opened Profil › Dil. | The picker offers three entries: 'Kurum varsayılanı (Türkçe)', 'Türkçe', 'English'. The owner decision says tr/en only; the institution-default entry is reasonable but not in the plan. | Confirm the third entry with the owner, or drop it. | `logs/f13.json#A02 opts` | smartsched/frontend/src/components/admin/profile-view.tsx |

### Per-issue blocks

### R2-A-01 (minor) With four tabs (Rezervasyonlar · Rezervasyonlarım · Taleplerim · Diğer, 74 px each) the labels 'Rezervasyonlar
- Step: MOBILE M-09 on every academician route @390 · persona academician · viewport phone
- Expected: Every label fully visible (MOBILE.md M-09): shorter labels, a smaller font at 4 tabs, or two-line labels.
- Actual: With four tabs (Rezervasyonlar · Rezervasyonlarım · Taleplerim · Diğer, 74 px each) the labels 'Rezervasyonlar' (83 px) and 'Rezervasyonlarım' (96 px) overflow their tabs (white-space nowrap, overflow visible) and overlap into one word, 'RezervasyonlaRezervasyonlarım'. aria-current is right (Taleplerim / Rezervasyonlarım / Diğer).
- Evidence: shots/F12-tabbar-acad-phone.png, shots/F05-S01-taleplerim-acad-phone.png, logs/f13.json (under the evidence root)
- Seen before as: new, follows T-R1-06 (R1-A-31)
- File hints: smartsched/frontend/src/components/shell/tab-bar.tsx (label width at 4 items; T-R1-06 added the Taleplerim tab)

### R2-A-02 (major) Page-level forms have no keyboard clearance: /profile 'Yeni parola' sits at 390–434 while the page's sticky 'K
- Step: MOBILE M-12 F-12 S05 /profile (Yeni parola) · F-03 S02 /find-room (Kaç kişi) @390 · persona academician · viewport phone
- Expected: The focused field stays visible and uncovered with the keyboard open, and the sticky bar clears it (M-12).
- Actual: Page-level forms have no keyboard clearance: /profile 'Yeni parola' sits at 390–434 while the page's sticky 'Kaydet' bar (bottom 5.5 rem, 368–412) covers its upper half (elementFromPoint = the sticky DIV); /find-room 'Kaç kişi' stays at 513–557, fully below a 508 px viewport, nothing scrolls it into view ('Ara' is visible at 384–428). The Sheet/Dialog clearance of T-R1-02 works (book sheet note 228–292, wish room search 316–360, cancel reason 262–326 all uncovered).
- Evidence: shots/F12-S05-keyboard-acad-phone.png, logs/f12.log#M-12@/profile(password), logs/f03-phone.log#M-12@/find-room(headcount) (under the evidence root)
- Seen before as: new; same family as T-R1-02 (R1-A-03), different surfaces
- File hints: smartsched/frontend/src/components/ui/keyboard-clearance.tsx (only mounted inside Sheet/Dialog), smartsched/frontend/src/components/admin/profile-view.tsx (sticky save bar), smartsched/frontend/src/components/findroom/find-room-view.tsx

### R2-A-03 (major) The confirm is role=alertdialog without aria-modal and does not trap focus: after 'Kapat' the next Tab lands o
- Step: F-13 C02 (withdraw confirm) · F-13 C05 (reset-link confirm) @1440 keyboard · persona academician · viewport desktop
- Expected: A modal confirm cycles focus between its own controls (A-20); aria-modal=true.
- Actual: The confirm is role=alertdialog without aria-modal and does not trap focus: after 'Kapat' the next Tab lands on a SPAN outside the dialog, then BODY, then the page's skip link 'İçeriğe atla' and the 'SmartSched' logo, before coming back to 'Vazgeç'. Enter on the confirm still works and focus returns to the row / the new URL afterwards.
- Evidence: logs/f13.log#C05, scripts/probe-f13.mjs, scripts/probe-f13b.mjs (C02-withdraw cycle) (under the evidence root)
- Seen before as: regression of A-20 (persona-user), not in round 1
- File hints: smartsched/frontend/src/components/ui/dialog.tsx / alert dialog (base-ui modal prop), smartsched/frontend/src/components/approvals/my-requests.tsx (withdraw ConfirmDialog), smartsched/frontend/src/components/bookings/calendar-sync.tsx (reset confirm)

### R2-A-04 (major) 'Ara' is not sticky: y 711–755 at the top, 311–355 after 400 px, then off-screen (−1817) at the end of the res
- Step: MOBILE M-05 F-03 /find-room 'Ara' @390 · persona academician · viewport phone
- Expected: 'Ara' stays in the bottom 40 % while the form and the results scroll (M-05).
- Actual: 'Ara' is not sticky: y 711–755 at the top, 311–355 after 400 px, then off-screen (−1817) at the end of the results. The F-03 mobile expectation ('a sticky primary action … does not scroll away when the form is taller than the screen') is not met; round 1's M-05 table already read 'Ara not sticky' but no ticket took it.
- Evidence: logs/f03-phone.log#M-05@/find-room(Ara), shots/F03-S11-results-acad-phone.png (under the evidence root)
- Seen before as: round 1 table row '/find-room M-05 FAIL (Ara not sticky)' (no ticket)
- File hints: smartsched/frontend/src/components/findroom/find-room-view.tsx (form footer)

### R2-A-05 (major) Result cards: the 'Neden?' policy link is 62×16 with no hit area
- Step: MOBILE M-02 F-03 /find-room results + filters sheet @390 · persona academician · viewport phone
- Expected: Every control ≥ 44 px or a 44 px hit area (M-02).
- Actual: Result cards: the 'Neden?' policy link is 62×16 with no hit area. Filters sheet: feature chips (fr-feature-1…8) and building chips 'A Blok'… are 24 px tall (Chip size sm; neighbours intercept the ±22 px probe), the two switches 38×22, the 'PC sayısı, en az' number input 28 px, 'Kapat' 36×36. F-03's mobile expectation asks for ≥ 44 px chips in that sheet.
- Evidence: logs/f03-phone.log#M-02@/find-room(results), scripts/probe-f03-phone.mjs output, shots/F03-filters-sheet-acad-phone.png (under the evidence root)
- Seen before as: new instances; T-R1-01 (R1-A-02) cleaned the primitives
- File hints: smartsched/frontend/src/components/findroom/find-room-view.tsx (Chip size=sm in the sheet, number input), smartsched/frontend/src/components/policies/policy-why.tsx (trigger min-h on coarse pointers)

### R2-A-06 (minor) The password hint reads 'En az 8 karakter
- Step: F-12 S07 /reset-password › Kodum var @1440 · persona academician · viewport desktop
- Expected: Hint 'En az 8 karakter.'; a Turkish refusal for a wrong or short code.
- Actual: The password hint reads 'En az 8 karakter. Dizin (LDAP) hesapları için boş bırakın.' (the users-admin hint reused; U-21 asked for no LDAP text here), and the wrong code is refused with the raw English 'String should have at least 8 characters' (pydantic 422: the confirm schema's token min_length=8 is not a coded Refusal). The request step is fine: neutral answer for unknown addresses, mail with '24 saat geçerli', right code 200, reuse 400.
- Evidence: shots/F12-S07-wrongcode-acad-desktop.png, curl/F12-S07-confirm.txt, mail/F12-S07-reset-code.eml (under the evidence root)
- Seen before as: U-21 leftover; T-R1-31 family
- File hints: smartsched/frontend/src/components/admin/reset-password.tsx (crbs.users.passwordHint), smartsched/backend/app/api/v1/org.py password-reset/confirm schema (token min_length → messages.coded)

### R2-A-07 (minor) Cells, slots, buttons and the popover are right ('Talep et · Onay gerekir', 'Onaylayıcılara gider'), but two h
- Step: F-01 S02 book sheet + grid legend (approval_mode=all) · persona academician · viewport desktop, phone
- Expected: Mode-aware helper texts ('Birlikte talep etmek için…', 'Boş bir saate tıklayıp talep edin.').
- Actual: Cells, slots, buttons and the popover are right ('Talep et · Onay gerekir', 'Onaylayıcılara gider'), but two helper texts still promise a booking: the sheet's period hint 'Birlikte rezerve etmek için önceki ya da sonraki saatleri ekleyin.' and the grid legend 'Boş bir saate tıklayıp rezerve edin.'
- Evidence: shots/F01-S02-sheet-acad-desktop.png, logs/f01-desktop.log#S02 (under the evidence root)
- Seen before as: leftover of T-R1-10 (R1-A-05)
- File hints: smartsched/frontend/src/components/bookings/book-sheet.tsx (periods hint), smartsched/frontend/src/components/bookings/booking-grid.tsx (legend)

### R2-A-08 (minor) The building chips keep the Turkish word: '/bookings' group tabs 'A Blok (20) · B Blok (9) · C Blok (27) · D B
- Step: F-13 A02 English mode · persona academician · viewport desktop, phone
- Expected: 'Block A' / 'A block' in English (U-10's EN variant).
- Actual: The building chips keep the Turkish word: '/bookings' group tabs 'A Blok (20) · B Blok (9) · C Blok (27) · D Blok (2)', find-room building chips 'A Blok'. Everything else switched ('Bookings · SmartSched', 'Send request', 'This room needs approval', 'Find a room', 'My bookings').
- Evidence: shots/F13-A02-en-acad-desktop.png, logs/f13.json#A02 (under the evidence root)
- Seen before as: U-10 (EN side)
- File hints: room group names come from the booking setup ('A Blok'); smartsched/frontend/src/components/bookings/bookings-view.tsx group tabs, findroom/find-room-view.tsx wave1.find.building

### R2-A-09 (minor) The URL changes to /my-bookings?request=1 but the request stays collapsed and focus stays on the bell; nothing
- Step: F-01 S09 bell → request · persona academician · viewport desktop, phone
- Expected: The deep link expands (and scrolls to) the request whatever the current page.
- Actual: The URL changes to /my-bookings?request=1 but the request stays collapsed and focus stays on the bell; nothing visibly happens. Arriving from another page (or a direct load) expands the request with the reason, 'Karar veren: Administrator' and the timeline.
- Evidence: scripts/probe-f01b.mjs output (bell→deeplink from /my-bookings: exp false; from /bookings: exp true), shots/F01-S09-deeplink-acad-desktop.png (under the evidence root)
- Seen before as: new
- File hints: smartsched/frontend/src/components/approvals/my-requests.tsx (initiallyOpen read once in useState; react to the ?request param change)

### R2-A-10 (minor) Taleplerim shows one row 'C 303 · Per 5 Kas · P7–P8 (13:30–15:00)' and the feed one VEVENT, but the Yaklaşan b
- Step: F-04 S03 Yaklaşan @1440/@390 · persona academician · viewport desktop, phone
- Expected: One row 'P7–P8' (A-12, F-04 S03 target).
- Actual: Taleplerim shows one row 'C 303 · Per 5 Kas · P7–P8 (13:30–15:00)' and the feed one VEVENT, but the Yaklaşan booking list shows two rows 'C 303 · P7 13:30' and 'C 303 · P8 14:20', each with the approver's note.
- Evidence: shots/F04-S03-mine-acad-desktop.png, logs/f04.json#S03 (under the evidence root)
- Seen before as: A-12; T-R1-13 open part
- File hints: smartsched/frontend/src/components/bookings/my-bookings-view.tsx (group the booking list by multi_booking_id / group_id, as my-requests.tsx does)

### R2-A-11 (minor) Events carry room and period only: 'SUMMARY:A 104 – P3', 'LOCATION:A 104', no DESCRIPTION; the note typed in t
- Step: F-04 S06 mine.ics · persona academician · viewport desktop
- Expected: SUMMARY carries the room code and the note (F-04 S06), or the note goes into DESCRIPTION.
- Actual: Events carry room and period only: 'SUMMARY:A 104 – P3', 'LOCATION:A 104', no DESCRIPTION; the note typed in the sheet ('Ders tekrarı', 'Telafi dersi') never reaches the calendar. Statuses, VTIMEZONE Europe/Istanbul and the in-place CONFIRMED update are right.
- Evidence: curl/F04-S06-mine-desktop.ics (under the evidence root)
- Seen before as: new
- File hints: smartsched/backend/app/services/calendar_feeds.py (VEVENT builder)

### R2-A-12 (minor) The two copy buttons are icon-only (44×44, aria-label 'Web bağlantısı kopyala' / 'Takvim uygulaması bağlantısı
- Step: F-04 S04/S05 sync panel @390 · persona academician · viewport phone
- Expected: Copy buttons with a word on phones; a 'Kopyalanamadı: bağlantıyı alandan seçin' toast when the clipboard is refused.
- Actual: The two copy buttons are icon-only (44×44, aria-label 'Web bağlantısı kopyala' / 'Takvim uygulaması bağlantısı kopyala', no visible word) although F-04's mobile expectation says 'labelled with words (not icon-only)'. When the browser refuses the clipboard, navigator.clipboard.writeText rejects unhandled (pageerror 'Write permission denied') and the user gets no toast at all; with permission the toast 'Bağlantı kopyalandı' appears.
- Evidence: shots/F04-S05-copy-acad-phone.png, shots/F04-S05-copy-acad-phone-noperm.png, scripts/probe-f04-copy.mjs output (under the evidence root)
- Seen before as: new
- File hints: smartsched/frontend/src/components/bookings/calendar-sync.tsx (FeedRow copy(): no catch; size=icon)

### R2-A-13 (minor) The toast's close button ('Bildirimi kapat') is 20×20 with no hit area
- Step: MOBILE M-02 toast close @390 · persona academician · viewport phone
- Expected: ≥ 44 px hit area (M-02).
- Actual: The toast's close button ('Bildirimi kapat') is 20×20 with no hit area.
- Evidence: logs/f04.json#M-02@/my-bookings(sync panel) (under the evidence root)
- Seen before as: new; T-R1-07 named it 'Bildirimi kapat'
- File hints: smartsched/frontend/src/components/ui/sonner.tsx (closeButton size on coarse pointers)

### R2-A-14 (minor) 'Moderasyon / Taleplerim': the first crumb is the coordinator's word and links to /moderation (which renders T
- Step: F-05 S01 breadcrumb @1440/@390 · persona academician · viewport desktop, phone
- Expected: For a teacher the trail starts at 'Taleplerim' (no 'Moderasyon').
- Actual: 'Moderasyon / Taleplerim': the first crumb is the coordinator's word and links to /moderation (which renders Taleplerim for a teacher, so no dead end). The history page's crumb is right ('Taleplerim / Geçmişim').
- Evidence: shots/F13-C01-shortcuts-acad-desktop.png (crumb visible), logs/f13.json#A01-crumb (under the evidence root)
- Seen before as: leftover of T-R1-08 (R1-A-11)
- File hints: smartsched/frontend/src/components/shell/breadcrumbs.ts (/moderation root label for users without planning.view)

### R2-A-15 (trivial) A one-period request (POST /bookings) answers 202; a multi-period or multi-slot request (POST /bookings/multi/
- Step: F-01 S03/S06 API status · persona academician · viewport desktop
- Expected: 202 for every request that goes to approval (F-01 S03).
- Actual: A one-period request (POST /bookings) answers 202; a multi-period or multi-slot request (POST /bookings/multi/{id}/create) answers 200 for the same pending outcome.
- Evidence: logs/f01-desktop.log#S06b (under the evidence root)
- Seen before as: new
- File hints: smartsched/backend/app/api/v1/bookings.py (multi create status code)

### R2-A-16 (trivial) The course code and the session label are glued in the accessible text: 'PSY 277Teori', 'PSY 277Laboratuvar' (
- Step: F-05 S01 cards @390 · persona academician · viewport phone
- Expected: A space or separator between code and session label.
- Actual: The course code and the session label are glued in the accessible text: 'PSY 277Teori', 'PSY 277Laboratuvar' (visually spaced, but screen readers and copy read one word).
- Evidence: logs/f05.json#S01-session (phone) (under the evidence root)
- Seen before as: new
- File hints: smartsched/frontend/src/components/moderation/moderation-console.tsx (mine-session in the card layout)

### R2-A-17 (suggestion) An approved request is listed twice: as a 'Taleplerim' card ('C 303 · Onaylandı') and as a booking row under '
- Step: F-04 / F-01 Rezervasyonlarım · persona academician · viewport desktop, phone
- Expected: Decided requests leave 'Taleplerim' after a while (or collapse under 'Karara bağlanan'), so one booking shows once.
- Actual: An approved request is listed twice: as a 'Taleplerim' card ('C 303 · Onaylandı') and as a booking row under 'Yaklaşan' with the approver's note. The totals line counts the bookings only.
- Evidence: shots/F04-S03-mine-acad-desktop.png (under the evidence root)
- Seen before as: new
- File hints: smartsched/frontend/src/components/bookings/my-bookings-view.tsx, approvals/my-requests.tsx

### R2-A-18 (suggestion) One message carries both languages ('Parolanızı sıfırlamak için … / Use this one-time code…')
- Step: F-12 S07 reset mail · persona academician · viewport desktop
- Expected: Use the profile language when the account is known; bilingual only for unknown addresses.
- Actual: One message carries both languages ('Parolanızı sıfırlamak için … / Use this one-time code…'). Before login the language is unknown, so this is defensible; the account's profile language (tr) was available though.
- Evidence: mail/F12-S07-reset-code.eml (under the evidence root)
- Seen before as: new
- File hints: smartsched/backend/app/services (issue_reset_token mail template)

### R2-A-19 (suggestion) The picker offers three entries: 'Kurum varsayılanı (Türkçe)', 'Türkçe', 'English'
- Step: F-13 A02 language picker · persona academician · viewport desktop, phone
- Expected: Confirm the third entry with the owner, or drop it.
- Actual: The picker offers three entries: 'Kurum varsayılanı (Türkçe)', 'Türkçe', 'English'. The owner decision says tr/en only; the institution-default entry is reasonable but not in the plan.
- Evidence: logs/f13.json#A02 opts (under the evidence root)
- Seen before as: new (information)
- File hints: smartsched/frontend/src/components/admin/profile-view.tsx

## Not run / blocked

- **F-12 S08** (session expiry): no TTL stack this round (a second stack with `JWT_EXPIRE_MINUTES=2`): SKIP, as in round 1.
- **F-12 S18** (real Entra round trip): BLOCKED, no tenant credentials.
- **F-01 S13** (external channel): no channel enabled on this stack ('bağlı değil — Profil › Bağlı kanallar'): BLOCKED.
- **F-04 S12** (two-way sync): no OAuth client; no connector buttons are shown: SKIP.
- **F-05 S03 'Bina with the department's own block'**: SKIP (data): the department form asks for 'Derslik' / 'Bilgisayar Laboratuvarı (JASP)', not a building, so `already_requested` cannot fire for PSY 277.
- **F-13 A02 plurals** ('1 booking / 3 bookings'): the English My bookings page showed only the totals line ('0 active · 1 this session · 1 in total'); no plural string was on screen to judge.
- **M-13 landscape**: run on /login and /profile only (bars 48/390 = 12 %, no sideways scroll); M-14 at 4× CPU not run.

## Notes for the suggester

- The multi-slot request endpoint answers 200 where the single one answers 202 (R2-A-15): only the status differs, the UI handles both.
- `POST /calendar/feeds/tokens` while calendar sync is off answers 201 (a token whose feed answers 404); F-04 S01 accepts that, but the panel then offers 'reset' instead of 'create' — harmless, noted.
- Under OS or in-app reduced motion the sheets still run 10 ms open transitions (near-zero durations); a strict '2 rAF' probe catches them, a user never does. Recorded as PASS.
- The A02 'Kurum varsayılanı (Türkçe)' language entry (R2-A-19) needs an owner yes/no.
