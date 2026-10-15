# F-02 · Direct booking (admin / approver bypass), weekly series with book / skip / replace, cancel with a scope

Personas: **admin** (main), **staff** (the person booked for, and the owner of the booking that gets replaced), **planner** (helper: a series that must become a request). Viewports: desktop, tablet, phone.
Owner rules:
- with `bookings.approval_mode = all`, admins, designated approvers and holders of `bookings.skip_approval` book directly, and everyone else requests (ROADMAP, approval-first);
- CRBS parity: a recurring booking shows its dates first and lets the user book, skip or replace each one; cancel and edit ask for a scope (CRBS "this / this and future / all").

Testable on `b75047b`: yes, every step.

## Preconditions

1. Restore the snapshot. Apply `PUT /org/settings {"approval_mode":"all"}` (see F-01). The admin is the designated approver for all rooms (seed).
2. Dates from README §4.3: `D1` (Thursday), `D2` (the Monday after), `D3 = D1 + 14 days`, `D4 = D1 + 21 days`, `D5 = D1 + 28 days`, `D6 = D1 + 35 days` (all Thursdays). On the 2026-10-15 run: D1 = 22 Oct, D3 = 5 Nov, D4 = 12 Nov, D5 = 19 Nov, D6 = 26 Nov. The holiday Thu **29 Oct** then falls inside the series.
3. Choose the series room `RS`: an **A-block** room with ≥ 40 seats whose **P5** is `available` on every Thursday from D1 to D6 (`GET /bookings/grid?date=<each>&room_group_id=<A>`). Prefer A 202. Record it. If no room is free on all six Thursdays, take the one with the fewest busy dates and note which.
4. The admin's profile language is `tr`.

## Steps

**S01 · admin · direct booking on behalf of someone else (bypass)**
- Do: `/bookings?date=$D4`, building A. Click `RS · P5` (free). In the sheet: **"Rezervasyon türü"** = **"Tek seferlik"**; **"Kimin adına"** (`book-user`) = "P. T."; note `Bölüm toplantısı`. Read the hint under "Kimin adına": **"Başkası adına yapılan rezervasyon, SMTP tanımlıysa ilgiliye e-postayla bildirilir."** Press **"Bu saati rezerve et"** (`book-submit`).
- See: no "Bu derslik onay gerektirir" notice, because the admin bypasses approval. Toast **"RS, <D4 date> P5 için rezerve edildi"**. The cell shows the booking with "P. T." (or "Gizli" if notes and users are hidden for this role) and the note.
- API: `POST /bookings` → **201**, `status: BOOKED`, `user_id` = staff, `created_by` = admin. No approval request (`GET /approvals/inbox` unchanged).
- Notify (CRBS parity): staff gets an e-mail in the sink about the booking made on their behalf. If none arrives in 90 s: FAIL (minor), see persona-user Enh. #12.

**S02 · admin · open the weekly series form**
- Do: `/bookings?date=$D1`, click `RS · P5`. Choose **"Her hafta"**.
- See: **"Tekrar"** with **"Başlangıç"** = **"Bu tarihten (<D1>)"** (other options "Dönem başından", "Tarih seçin…") and **"Bitiş"** = **"Dönem sonuna kadar (27 Ara 2026)"** or "Tarih seçin…". Choose "Tarih seçin…" for the end and set `D6`.
- Do: **"Tarihleri göster"** (`recur-preview-btn`).

**S03 · admin · the per-date preview**
- See (`recur-preview`): one row per Thursday from D1 to D6, each with its week ("**{n}. hafta**") and a status:
  - free dates: **"Boş"**, action **"Rezerve et"**;
  - 29 Oct: **"Tatil"**, **"Atlanır"** (no action can override it);
  - D4: **"Dolu"** (the S01 booking), default action **"Atla"**, with **"Yerine geç"** offered because the admin may replace it;
  - a date held by the published timetable, if any: **"Ders programında"**, not bookable.
- Summary (`recur-summary`): **"{create} rezerve edilecek · {skip} atlanacak · {holidays} tatil"**, consistent with the rows. On the 2026-10-15 dates: **"4 rezerve edilecek · 1 atlanacak · 1 tatil"**.
- API: `POST /bookings/recurring/preview` returns the same per-date statuses (save the response).

**S04 · admin · book / skip / replace per date**
- Do: on `D3` set the action to **"Atla"** ("**{date} için işlem**" control). On `D4` set **"Yerine geç"**. Leave the rest.
- See: the summary updates at once (no reload) to 3 to book + 1 replace, 1 skipped by choice, 1 holiday. The counts and the submit label agree. Try **"Hiçbiri"** (everything set to skip; submit disabled or "0 tarihi rezerve et" disabled), then **"Boşların hepsi"**, then re-apply the D3/D4 choices. **"Yeniden denetle"** re-runs the check without losing the choices.
- Do: press **"{n} tarihi rezerve et"** (the button text carries the number).
- See: toast **"{created} tarih rezerve edildi, {skipped} tarih atlandı"** with the real numbers (2026-10-15 dates: "4 tarih rezerve edildi, 2 tarih atlandı", where the replaced date counts as created).
- API: `POST /bookings/recurring` → **201** (not 202: the admin bypasses), one series. The bookings exist on D1, D4 (replace), D5 and D6. D3 and 29 Oct have none. Staff's S01 booking is now `CANCELLED`, with a reason that names the replacement.

**S05 · staff · learns the booking was replaced**
- Do: log in as staff. `/my-bookings` → **"İptal edilen"**.
- See: the D4 booking with status **"İptal edildi"** and the reason (who replaced it, why). Bell +1, or an e-mail in the sink. At least one of the two must exist; report which.
- If neither exists: FAIL (major). Silently losing a booking is the worst booking outcome.

**S06 · planner · the same series becomes a request under approval_mode=all**
- Do: log in as planner.test. Open a different free room at P6 on D1. "Her hafta", 3 dates, "Tarihleri göster", submit.
- See: the notice **"Bu derslik onay gerektirir"**, button **"{n} tarih için talep et"**, toast **"… için talebiniz gönderildi (3 tarih). Onaycı karar verince size bildirilecek."**
- API: `POST /bookings/recurring` → **202**, `status: PENDING`.
- Admin: `/approvals` shows one request with **"Onaylanacak tarihler"** and **"{of} tarihten {n} seçili; diğerleri reddedilir."** Uncheck one date and approve **"2 tarihi onayla"**. The planner sees 2 booked, 1 declined. The declined date carries the reason "only selected dates approved" or the reason the admin gave; an empty reason is a FAIL against the F-01 reason rule.

**S07 · admin · edit with a scope**
- Do: open the D1 booking of the series (`booking-sheet`). Press **"Düzenle"** (`booking-edit`). Change the note to `Bölüm toplantısı (haftalık)`. **"Uygulanacak"** = **"Bu ve sonrakiler"**. Save (`edit-save`).
- See: the toast names the number of bookings updated. D1 and later dates show the new note.
- API: the edit returns the updated ids. Re-read two of them.

**S08 · admin · cancel one date**
- Do: open the series booking on `D5`. **"İptal et"** (`booking-cancel`).
- See: dialog **"Rezervasyon iptal edilsin mi?"**, body **"RS, <date>, P5"**. **"Uygulanacak"**: **"Bu tarih"** · **"Bu ve sonrakiler"** · **"Tüm seri"**. Field **"Gerekçe"** with the hint **"Rezervasyonla birlikte saklanır ve rezervasyon sahibine gösterilir."** Target (persona-user Enh. #7): each scope option states how many dates it cancels ("Bu ve sonrakiler: 3 tarih (…)").
- Do: "Bu tarih", reason `Oda bakımda`, **"İptal et"**.
- See: toast **"1 rezervasyon iptal edildi"**. Only that date disappears from the grid.
- API: `POST /bookings/<id>/cancel {"scope":"one","reason":"Oda bakımda"}` → 200 with 1 id.

**S09 · admin · cancel this and future**
- Do: on D4 → "İptal et" → **"Bu ve sonrakiler"**, reason `Program değişti`.
- See: toast **"{n} rezervasyon iptal edildi"**, n = the series dates still booked from D4 on (D4 and D6 = 2, because D5 was cancelled in S08). D1 stays booked.
- API: `scope: future` → those ids are `CANCELLED`, and the earlier ones are not.

**S10 · admin · undo a cancel from the audit log**
- Do: `/admin/audit`. Find the newest booking-cancel event (a domain sentence, not a raw key). **"Geri al"**.
- See: the event reads "Geri alındı". The D4 booking is `BOOKED` again (the undo window is `bookings.audit_undo_hours` = 24 h). Focus stays on that row (motion T4).

**S11 · admin · cancel the whole series**
- Do: any remaining date → "İptal et" → **"Tüm seri"** → confirm.
- See: every remaining date of the series is cancelled. The staff booking replaced in S04 is **not** restored by this; that is correct.

**S12 · staff · a period that already started is not bookable** (U-04 regression)
- Do: as staff, during teaching hours, open `/bookings` for **today**.
- See: periods whose start time has passed (Europe/Istanbul) are not offered ("Geçmiş" or "Rezerve edilemez"), in both the grid and the phone free-slot list.
- API: `POST /bookings` for today's P1 after 09:00 local → **409** `past`. (If you run this after 17:30, use P11.)

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- The book sheet is a bottom sheet. **"Tek seferlik / Her hafta"** is one segmented control that does not wrap (UI review: one segmented control). Each segment is ≥ 44 px tall.
- **Recurring preview on phone:** one card per date (date + week on line 1, status word + icon on line 2). The per-date action is a ≥ 44 px segmented control or select, never a hover menu. The summary line and the submit button sit in a sticky footer inside the sheet (MOBILE.md M-05). Scrolling 6+ dates never scrolls the page sideways.
- The date fields use the Turkish format (gg.aa.yyyy) or a localised picker, never `mm/dd/yyyy` (UI review "Selects / dates").
- **Cancel dialog on phone:** a bottom sheet. Each scope option is a full-width ≥ 44 px radio row. The "Gerekçe" field stays above the on-screen keyboard (M-12). The destructive button is distinct in colour and text ("İptal et"), and "Vazgeç" is easy to reach.
- **"Kimin adına"** user picker on phone: a searchable list in a sheet, rows ≥ 44 px, initials only.
- **Audit log on phone** (S10): a card list. "Geri al" is a ≥ 44 px button inside the card.

## Flow acceptance

1. Admin/approver bookings are direct (201) under `approval_mode=all`. A planner's series is a request (202), unless the role holds `bookings.skip_approval`.
2. The preview lists every date with its real status. The summary always equals the per-date choices, and the result toast equals what the API created.
3. Holidays can never be booked by a series. A replaced booking is cancelled with a reason, and its owner can find out.
4. Every cancel and edit applies exactly its scope. The toast count equals the API count.
5. A cancel can be undone from the audit log inside the undo window.
6. MOBILE.md passes on `/bookings` (sheet open, recurring preview open), `/my-bookings` and `/admin/audit` at 390 and 768.

## Earlier issues to re-verify here

U-04 (past periods), persona-user Enh. #7 (scope counts before confirming) and #12 (notify the person booked for), U-07 (focus after edit/cancel), U-16 (touch targets).
