# F-01 · Request an empty slot → admin approves or rejects with a reason → requester notified → withdraw

Personas: **staff**, **academician** (requesters), **admin** (approver). Viewports: desktop, tablet, phone.
Owner decision (ROADMAP "Approval-first bookings + user channels + credential-free login", 2026-10-15 22:15): every request for an empty slot goes to an admin first. The admin approves, or rejects with a reason (code + text). The requester is told in My bookings, in the bell and by e-mail (later also by the channels they connected). Approvers and admins book directly.

State on `b75047b`:
- Backend done: `bookings.approval_mode`, `bookings.skip_approval`, reason codes, `notify_dispatch` (in-app + e-mail), `/me/notification-preferences`.
- UI not built yet (frontend builder waits for the shell sweep): the approval-mode setting, the reject dialog with a required reason, the reason shown to the requester, and Profile › Bildirimler. Those steps carry **[UI pending]**. Run them anyway and report `FAIL` when the old UI is still there, or `BLOCKED: <what is missing>` when the step cannot be reached at all. Always also run the **API check** in the same step: it tells the builder whether the backend side holds.
- External channels (a Pipedream-like provider) are not chosen: S13 is `BLOCKED: provider not chosen`.

## Preconditions

1. Fresh restore: `REC_SNAPSHOT=1 REC_SKIP_BUILD=1 stack.sh up`. The seed of README §4.4 has run: three accounts, admin designated approver for **all** rooms, SMTP sink on `$SMTP_PORT`, names masked.
2. Approval-first mode, as the institution profile ships it:
   ```bash
   curl -fsS -X PUT "$API/org/settings" "${H[@]}" -d '{"approval_mode":"all"}' | jq -r .approval_mode   # → all
   ```
   (S01 tries the same through the UI first. Apply this command only if S01 is BLOCKED.)
3. No approval rule exists (`GET /approval-rules` → `[]`). Part B adds one.
4. Pick the slots on `D1` (README §4.3) from the real grid. A slot is usable when both periods are free for everyone:
   ```bash
   curl -fsS "$API/bookings/grid?date=$D1&room_group_id=<C group id>" -H "Authorization: Bearer $A" > "$EV/curl/F01-pre-grid-C.json"
   ```
   The grid answers one room group (building) at a time; the group ids come from `GET /room-admin/groups` (one group per building, made by the booking setup).
   - `R1` = the first **C-block** room with ≥ 40 seats whose periods **P7 and P8** are both `available` (expected: C 303, 45 seats).
   - `R2` = the first **A-block** room with ≥ 40 seats where **P3** is `available`.
   - `R3` = **C z01** (30 seats) at **P5** on `D3`. If it is busy, take the next C-block room with P5 free.
   Write the three choices in the report header.
5. Mail sink empty except the seed's test mail. Remember the highest file number: `N0=$(ls $SINK | wc -l)`.

## Steps

Each step lists what to do, what the UI must show (Turkish strings quoted exactly from `messages/tr.json`), the API or data effect, and the notifications. "Bell +1" means the badge count (`notification-count`) rises by one and the bell's accessible name contains `"1 okunmamış"` (or the new count).

### Part A · approval_mode = all

**S01 · admin · set the approval mode in the UI** [UI pending]
- Do: Yönetim › Ayarlar (`/admin/settings`). Find the booking-approval control (target: a choice between "only rooms with an approval rule" and "every request is approved first"). Choose the second one and save.
- See: a save toast in Turkish. A one-line explanation that approvers, planning administrators and holders of `bookings.skip_approval` book directly.
- API: `GET /org/settings` → `"approval_mode":"all"`. One audit row for the change (`/admin/audit`, newest first).
- If the control does not exist: `BLOCKED: approval-mode setting not built`, and apply precondition 2 with curl.

**S02 · staff · see that the free slot needs approval**
- Do: log in as staff. Open `/bookings?date=$D1`, building tab C. Click (tap on touch viewports) the free cell `R1 · P7` (`[data-testid=booking-grid] button[data-tone=available]` in the R1 row, P7 column).
- See: the book sheet (`book-sheet`) titled with R1, P7 and the D1 date. The notice **"Bu derslik onay gerektirir"**. The primary button reads **"Talep et"** (not "Bu saati rezerve et").
- API: `GET /approvals/rooms/<R1 id>/check` as staff → `"action":"request"`, the rule's `source` is `approval_mode`.

**S03 · staff · request two periods with a note**
- Do: in "Ders saatleri" (`book-periods`) add P8. Note: `Telafi dersi`. Press **"2 ders saati için talep et"** (`book-submit`).
- See: the button shows a busy label while waiting (not only a spinner). Toast: **"R1 için talebiniz gönderildi. Onaycı karar verince size bildirilecek."** Both cells now show the pending state: legend **"Onay bekliyor"**, cell text with "Siz" (U-06). Focus stays on the R1·P7 cell or moves into the toast, never to `<body>` (U-07).
- API: `POST /bookings` → **202**. `GET /approvals/mine` → **one** request group for the two periods, `status: PENDING` (A-12).
- Notify: admin bell +1, title **"Onay bekleyen oda talebi: …"** (room and date in the text). The sink receives one mail **to admin@smartsched.local**, subject starting with "Onay bekleyen oda talebi:", body "P. T. şu oda için onay istiyor: …".

**S04 · staff · a duplicate request is refused**
- Do: click R1·P7 again.
- See: the sheet opens the existing request: **"Bu talep zaten var ve onay bekliyor."** with **"Talebi aç"** (`book-duplicate-link`). There is no second "Talep et".
- API: repeat the S03 POST with curl → **409** `duplicate_request`. Save to `curl/F01-S04-duplicate.txt`.

**S05 · staff · the request in My bookings**
- Do: `/my-bookings`, section **"Taleplerim"** (`my-requests`).
- See: one row for R1 · D1 · P7–P8 (`my-request-<id>`) with status **"Bekliyor"** (icon + word). Expanded (`request-timeline`): **"P. T. talep etti"**, **"Onaycı bekleniyor"**, **"Onaycılar: Administrator"**. The header count reads "1 bekliyor".

**S06 · academician · two requests (one to reject, one to withdraw)**
- Do: log in as academician. Request `R2 · D1 · P3` with the note `Telafi: PSY 277` (as S02–S03, one period: **"Talep et"**). Then request `R3 · D3 · P5` with the note `Ders tekrarı`.
- See: two toasts as in S03. "Taleplerim" lists both as "Bekliyor".
- Notify: admin bell +2. Two more mails to admin.

**S07 · admin · approve the staff request from the bell**
- Do: log in as admin. The bell (`notification-bell`) shows at least 3 unread. Open it (`notification-panel`), select the staff item (`notification-<id>`).
- See: the browser lands on `/approvals`, box **"Açık"**, with the staff request open in the drawer (`approval-drawer`). The drawer shows the requester "P. T.", the note "Telafi dersi", the rule (approval-first), the room's day strip (`approval-room-day`) and **"Tek talep: 2 ders saati. Her saati ayrı ya da açık olanların hepsini birden karara bağlayın."**
- Do: optional note "Onaylandı, iyi dersler." in **"Talep edene not"** (`approval-note`). Press **"2 saatin hepsini onayla"** (`approval-group-approve`).
- See: toast **"2 ders saati onaylandı: R1."** The request leaves "Açık". Focus lands on the next request's title, not `<body>` (M-33, motion T4).
- API: the request is `APPROVED`; `GET /bookings/<id>` for both periods → `status: BOOKED`, owner staff. One audit row per decision.
- Notify: staff bell +1, title **"Oda talebiniz onaylandı: …"**. Sink: one mail to personel.test@…, subject "Oda talebiniz onaylandı: …", body "Administrator talebinizi onayladı: …" plus the note.

**S08 · admin · reject the academician request with a required reason** [UI pending for the dialog]
- Do: open the academician's R2 request. Press **"Reddet"** (`approval-reject`).
- See (target): a dialog, or a bottom sheet on phone, with a **required reason code** (radio group or select) offering exactly **"Oda uygun değil"**, **"Kapasite yetersiz"**, **"Rezervasyon kurallarına uygun değil"**, **"Diğer"**, plus a text field "Gerekçe". The confirm button stays disabled until a code is chosen. With "Diğer" it also needs non-blank text (spaces and NBSP count as blank).
- Do (negative first): confirm with nothing chosen. Then choose "Diğer" with an empty text. Both must be refused in the UI, with a Turkish message next to the field (not only a red outline).
- Do: choose **"Oda uygun değil"**, text `Bu saatte bölüm sınavı var.`, confirm.
- See: toast **"Reddedildi. Talep edene bildirildi."** Focus as in S07.
- API check (run it whatever the UI shows; use a second academician request for the negatives so the real one stays open):
  - `POST /approvals/<id>/decide {"decision":"reject"}` → **422** `reason_required`, message in TR and EN.
  - `{"decision":"reject","reason_code":"other"}` → **422**. `{"decision":"reject","reason_code":"bogus"}` → **422**.
  - `{"decision":"reject","reason_code":"room_unavailable","reason":"Bu saatte bölüm sınavı var."}` → **200**. `GET /approvals/<id>` → `reason_code: room_unavailable`, the text stored, `decided_by` = admin.
- Today's UI only has "Talep edene not" with an optional note: report `FAIL` (major) with the ticket hint "reject dialog with required reason code + text".

**S09 · academician · sees the decision and the reason everywhere**
- Bell: +1, title **"Oda talebiniz reddedildi: …"**. Selecting it opens `/my-bookings?request=<id>` with that request expanded.
- My bookings: the R2 row reads **"Reddedildi"** (icon + word). The timeline shows **"Administrator reddetti"** and the reason **"Oda uygun değil: Bu saatte bölüm sınavı var."** [UI pending: today the reason may be missing → FAIL]. If the admin suggested another room: **"Bunun yerine önerilen"** with **"Boş derslik bul"**.
- E-mail: one new mail to akademisyen.test@…, subject **"Oda talebiniz reddedildi: …"**, body contains **"Gerekçe: Oda uygun değil: Bu saatte bölüm sınavı var."**. Save it to `mail/`.
- The staff member sees nothing of this decision (Q11): `GET /approvals/mine` as staff does not list R2.

**S10 · academician · withdraw a pending request**
- Do: in "Taleplerim", on the R3 row press **"Talebi geri çek"** (`withdraw-<id>`).
- See: confirm **"R3 talebi geri çekilsin mi?"**, body **"Onaycılara bildirilir ve saat serbest kalır."** Confirm. Toast **"Talep geri çekildi."** Status **"Geri çekildi"**. Focus goes to the same row or to the list heading, not `<body>`.
- API: `POST /approvals/<id>/withdraw` → 200. A second withdraw → **409**. Staff tries the same id → **403** `not_requester`. The cell R3·P5 on D3 is free again in the grid.
- Admin: the request is no longer in **"Açık"**. It shows as "Geri çekildi" under **"Karara bağlanan"** or in the history (M-34). The bell does not offer a stale "decide" link.

**S11 · staff · notification preferences** [UI pending: Profile › Bildirimler]
- Do (target UI): `/profile` → Bildirimler. A matrix of events × channels. The events read: "Onayımı bekleyen yeni oda talepleri", "Talebim onaylandı", "Talebim reddedildi (gerekçesiyle)", "Talebimi geri çektim", "Talebimin süresi doldu"; the channels read "Uygulama içi" and "E-posta" (exact labels as built). Switch off e-mail for "Talebim onaylandı" and save.
- API check: `PUT /me/notification-preferences {"events":{"approval.approved":{"email":false}}}` as staff → 200, and `GET` returns it.
- Then: staff requests one more free slot (`R1 · D3 · P7`), admin approves it. The staff bell gets the in-app notice. **No** new mail to personel.test@… arrives within 90 s.

**S12 · admin · approvers book directly**
- Do: as admin, book a free cell on D1 (any room) with the note `Bölüm toplantısı`.
- See: the sheet shows **"Bu saati rezerve et"** with no approval notice. Toast **"…için rezerve edildi"**.
- API: `POST /bookings` → **201**, status `BOOKED`. No approval request is created.
- Planner check (helper account): planner.test books a free cell → **202** request (the PLANNER role has no `approvals.decide` and no `bookings.skip_approval`). After the admin grants `bookings.skip_approval` to the planner role in `/admin/roles`, the next planner booking → **201**.

**S13 · requester · a connected external channel** — `BLOCKED: provider not chosen`
- Target once the provider exists: Profile › Bildirimler › "Bir kanal bağla" connects an account through the provider. SmartSched stores no token (verify: no secret column for the user in the database). A rejection then arrives on that channel with the same reason text.

### Part B · approval_mode = rules (the CRBS default of empty and universal installs)

**S14 · admin** sets `{"approval_mode":"rules"}` (UI as S01, or curl). Creates a rule on `R2`: `/admin/approval-rules` → **"rule-new"**, entity "Derslik" = R2, one step "designated approvers" → save (`rule-save`). API: `POST /approval-rules` 201.

**S15 · staff** books `R1 · D3 · P9` → **201** direct booking, toast "…için rezerve edildi". Requests `R2 · D3 · P4` → **202** with **"Bu derslik onay gerektirir"** and "1 adımlı onay". The admin rejects it **with a reason** (the reason rule applies in both modes; same 422 checks as S08).

## Mobile-specific expectations (phone 390×844; tablet 768×1024 where noted)

- **Book sheet** is a bottom sheet (MOBILE.md M-04): full width, anchored to the bottom, drag handle or a close button ≥ 44 px. **"Talep et"** sits in the sheet footer, sticky, inside the bottom 40 % of the screen (M-05). With the keyboard open on the note field (M-12) the field and the button stay visible.
- **Period chips** (`book-periods`) are ≥ 44 px tall and wrap. They never scroll the page sideways (M-01, M-02).
- **The grid on phone** opens on the free-slot list (`free-slots`), not the 18-column grid. Each slot is a tappable row ≥ 44 px with the room, the period and "Onay gerekir" (wave1.find.status.requestable).
- **My bookings › Taleplerim** is a card list (M-07). The status word and the room/date sit on the first two lines. "Talebi geri çek" is a ≥ 44 px button inside the card, not behind a swipe or a hover.
- **Approvals inbox (admin, phone):** the list is one column of cards. Opening one shows the detail full screen or as a 92 % bottom sheet. The approve/reject buttons are in a sticky footer. The keyboard legend (A/D/R) is hidden on touch.
- **Reject dialog (phone):** a bottom sheet. Each reason code is a ≥ 44 px row (radio). The text field scrolls into view above the on-screen keyboard (M-12). The confirm stays reachable without closing the keyboard.
- **Bell (phone):** the panel opens as a full-width sheet. Each item is ≥ 44 px. The unread count sits after the label in the tab bar or top bar (MOBILE.md M-09).
- **Tablet 768:** the approvals inbox may show list + detail side by side, but the detail must not be narrower than 360 px. Otherwise it behaves like the phone.

## Flow acceptance (all must hold for F-01 to be green)

1. With `approval_mode=all`, a non-bypass user's booking of any free slot creates a **PENDING** request (202). The grid shows it as pending to its requester. A duplicate is refused (409).
2. Admin, approvers and `bookings.skip_approval` holders book directly (201).
3. A rejection without a reason code, with an unknown code, or with "Diğer" and blank text is refused, in the UI (disabled confirm + Turkish message) and in the API (422 `reason_required`).
4. The requester sees the decision **and** the reason (label + text) and who decided, in My bookings, in the bell and in the e-mail. Nobody else sees it.
5. Approving a multi-period request is one decision, one notification and one e-mail (A-12).
6. Withdrawing frees the slot, notifies as specified, and cannot be done twice or by someone else.
7. Channel preferences are honoured: an event switched off for e-mail sends no mail.
8. Every success leaves keyboard focus on a sensible element. MOBILE.md passes on `/bookings`, `/my-bookings`, `/approvals` and the bell at 390 and 768.

## Earlier issues to re-verify here

U-06 (pending not shown, duplicate accepted), U-07 / A-21 (focus to body), A-12 (one request per period), M-33 (next request focused), M-34 (withdrawn visible to the approver, bell updates), U-16 (28 px touch targets in the toolbar and the sheet).
