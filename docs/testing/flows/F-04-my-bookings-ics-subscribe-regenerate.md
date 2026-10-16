# F-04 · My bookings + calendar (ICS) subscription + regenerate the private link

Personas: **staff** (main), **academician** (department and room feeds, class meetings), **admin** (the KVKK sign-off that switches feeds on). Viewports: desktop, tablet, phone.
Rules:
- feeds are private token URLs, and anyone with the link can read them (the UI says so);
- regenerating the link invalidates the old one;
- the organisation's KVKK switch `integrations.calendar_sync_enabled` stays off until an administrator records a dated sign-off. While it is off, every token feed answers 404 (alembic 0022, CHANGELOG 0.4.1, M-18).

Testable: yes. The sign-off screen (M-40) is in Ayarlar › Entegrasyonlar since 2026-10-16; S02 runs it in the UI and checks the API. Two-way Google / Microsoft sync needs OAuth client credentials, which the stack does not have: S12 is `SKIP (no OAuth client)`.

## Preconditions

1. Restore the snapshot. `approval_mode=all`, so a request can be pending.
2. Give the staff member a known set of bookings in Güz (`D1`, `D3` from README §4.3), as admin through the API (`POST /bookings` with `"user_id": <staff id>`), in rooms that are free:
   - `B1`: D1, P3, note `Ders tekrarı` (single);
   - `B2`: D3, P7 **and** P8 in one request (a two-period span), note `Telafi dersi`;
   - `B3`: D3, P10, then cancelled with the reason `Oda bakımda` (`POST /bookings/<id>/cancel`);
   - `R1`: as staff, request D1 · P9 in any room → 202, left **pending**.
3. Calendar sync is **off** (the fresh default): `GET /calendar/admin/settings` → `calendar_sync_enabled: false`, `calendar_sync_signoff: null`.
4. Clipboard: create the browser context with `permissions: ["clipboard-read", "clipboard-write"]` (desktop only; on touch viewports read the URL from the field instead).

## Steps

**S01 · staff · feeds are off before the KVKK sign-off**
- Do: `/my-bookings` → **"Takvime eşitle"** (`sync-open`).
- See: the sheet (`sync-sheet`) titled **"Takvime eşitle"** says **"Takvim eşitleme yönetici tarafından kapatıldı."** There is no "Özel bağlantılarımı oluştur" button (or it is disabled with that reason).
- API: `POST /calendar/feeds/tokens` as staff → refused (403/409 with a Turkish message), or a token whose feed answers **404**. Save the exchange.

**S02 · admin · KVKK sign-off for calendar sync** (M-40)
- Do: `/settings?tab=integrations`, card **"Takvim eşitleme (KVKK)"** (`calendar-sync-admin`): the switch (`calendar-sync-switch`) is off. Turn it on: the notice (`calendar-notice-text`) says what is shared (booking date, time, room, notes) and with whom (the calendars users connect, Google / Microsoft 365, servers abroad, and the subscription feeds). Tick the acknowledgement (`calendar-ack`) and confirm (`calendar-confirm`).
- See: the record (`calendar-signoff`) with the admin's name, the date and **"Hukuki dayanak: KVKK md. 9 (7499 sayılı Kanun ile değişik; yurt dışına aktarım)"**.
- API equivalent (only when the UI step fails):
  ```bash
  curl -fsS -X PUT "$API/calendar/admin/settings" "${H[@]}" -d '{"calendar_sync_enabled":true}' | jq '{calendar_sync_enabled, calendar_sync_signoff}'
  ```
- API: `calendar_sync_signoff` = `{enabled:true, by:"Administrator", by_user_id, at, features:["calendar_sync"], legal_basis:"KVKK Art. 9 as amended by Law 7499 (cross-border transfer)"}`. One audit row `integrations.calendar_sync`.

**S03 · staff · My bookings content**
- Do: reload `/my-bookings`.
- See: the totals line (`mine-totals`) **"{active} etkin · bu dönem {session} · toplam {all}"** with numbers that match the API. Tabs **"Yaklaşan"** · **"Geçmiş"** · **"İptal edilen"**.
  - Yaklaşan: B1 and B2. B2 is **one** row reading "P7–P8" (target, A-12 / persona-user Enh. #2). Two rows: FAIL (minor).
  - **"Taleplerim"**: R1 with "Bekliyor".
  - İptal edilen: B3 with "İptal edildi" and the reason "Oda bakımda".
- Each row has a room-info button (`mine-room-<id>`) that opens the room sheet. "Bu rezervasyonu seç" checkboxes (accessible name **"{date} {room} rezervasyonunu seç"**) are present.

**S04 · staff · create the private links**
- Do: "Takvime eşitle" → **"Özel bağlantılarımı oluştur"** (`sync-create`).
- See: the lead **"Bir kez abone olun, takvim uygulamanız kendini güncel tutar: Google Takvim, Outlook, Apple Takvim ve diğerleri."** A feed block **"Rezervasyonlarım"** (`sync-feed-mine`) with **"Web bağlantısı"** (`sync-url-mine`, https) and **"Takvim uygulaması bağlantısı"** (webcal). Buttons **"Google Takvim'e ekle"**, **"Outlook'a ekle"**, **"Apple Takvim"**. The warning **"Bu bağlantılara sahip herkes içindeki rezervasyonları görebilir. Kimseyle paylaşmayın."** and the note **"Google abone olunan takvimleri anında değil, birkaç saatte bir yeniler."**
- The URL field shows the full URL without overflowing the sheet (wraps or scrolls inside the field).

**S05 · staff · copy**
- Do: **"Web bağlantısı kopyala"** (`sync-copy-mine`), then the webcal copy (`sync-copy-webcal-mine`).
- See: toast **"Bağlantı kopyalandı"** each time. `navigator.clipboard.readText()` returns `https://…/calendar/feeds/<token>/mine.ics`, then `webcal://…/mine.ics`.
- Google link (`sync-google-mine`): href opens Google Calendar's add-by-URL with the webcal/https URL encoded. Outlook (`sync-outlook-mine`): Outlook's add-calendar URL. Apple (`sync-apple-mine`): `webcal://`. Do not follow them. Check the hrefs only.

**S06 · staff · fetch and parse the feed**
- Do: `curl -sS -D "$EV/curl/F04-S06-head.txt" -o "$EV/curl/mine.ics" "<https url>"` (redact the token in what you save).
- Expect: **200**, `Content-Type: text/calendar` (charset utf-8). Parse:
  ```bash
  python3 -I -c "import icalendar,sys;c=icalendar.Calendar.from_ical(open(sys.argv[1],'rb').read());ev=[e for e in c.walk('VEVENT')];print(len(ev));[print(e.get('STATUS'),e.get('DTSTART').dt,e.get('SUMMARY'),e.get('UID')) for e in ev]" "$EV/curl/mine.ics"
  ```
  - a `VTIMEZONE` with `TZID:Europe/Istanbul`, and DTSTART in local time matching the period start;
  - B1 → `CONFIRMED`; B2 → `CONFIRMED`, one VEVENT spanning P7–P8 (target; two VEVENTs = FAIL minor, A-12); R1 → `TENTATIVE`; B3 → `CANCELLED` (inside the cancelled-grace window, `feed_cancelled_grace_days`);
  - SUMMARY carries the room code and the note. No other person's name, and no e-mail address.

**S07 · admin → staff · a decision reaches the feed**
- Do: admin approves R1 (F-01 S07). Fetch the feed again.
- Expect: the same `UID` now has `STATUS:CONFIRMED`, and `SEQUENCE` is higher (or `LAST-MODIFIED` is newer). No duplicate VEVENT.

**S08 · staff · regenerate the private link**
- Do: "Takvime eşitle" → **"Özel bağlantıyı sıfırla"** (`sync-reset`).
- See: confirm **"Özel bağlantı sıfırlansın mı?"**, body **"Eski bağlantılarla abone olunan takvimler artık güncellenmez. Yeni bağlantılarla yeniden abone olun."** Confirm. Toast **"Yeni bağlantılar oluşturuldu; eski abonelikler artık güncellenmez."** Focus moves to the new URL field `sync-url-mine` (U-22).
- API: the old URL → **404**. The new URL → 200 with the same events.
- A later visit (new browser context) shows **"{n} özel bağlantınız var ({hints}). Bağlantılar yalnızca bir kez gösterilir; burada görmek için yeni bir bağlantı oluşturun."** and does not reveal the token again.

**S09 · academician · room and department feeds include classes**
- Do: log in as academician. "Takvime eşitle" → **"Abone olunacak derslik"** (`sync-room-select`) = A 308 (where PSY 277 theory meets in Güz). **"Abone olunacak bölüm"** (`sync-dept-select`): the default reads "Bölüm seçin", never the alphabetically first department (U-23). Choose Psikoloji.
- Fetch both feeds.
- Expect: the room feed contains this room's bookings **and** the class meetings of the published Güz run, with the course code only (A-14 fix). The department feed is the same for the department's rooms. **No instructor names** in any VEVENT (KVKK; check `SUMMARY`, `DESCRIPTION`, `ORGANIZER`, `ATTENDEE`).
- Target (P19-T4, not built): a personal "Derslerim" feed of the academician's own classes. `BLOCKED: P19-T4`.

**S10 · staff · cancel from My bookings**
- Do: select B1's checkbox → **"1 rezervasyonu iptal et"** (`cancel-selected`).
- See: **"1 rezervasyon iptal edilsin mi?"**, body **"Artık iptal edilemeyenler (başlamış olanlar) olduğu gibi bırakılır."** Confirm. Toast **"1 iptal edildi, 0 olduğu gibi kaldı"**. B1 moves to "İptal edilen". Focus goes to the next row or the list heading.
- Feed: B1 becomes `CANCELLED`.

**S11 · admin · switching the KVKK switch off kills every feed**
- Do: `PUT /calendar/admin/settings {"calendar_sync_enabled":false}`.
- Expect: the new staff URL → **404** at once. The staff sync sheet shows "Takvim eşitleme yönetici tarafından kapatıldı." Switch it back on and the same token works again (the token is not deleted by the switch). Report what you observe for the last point.

**S12 · staff · two-way sync** — `SKIP (no OAuth client)`
- On this stack "Google Takvim'i bağla" / "Microsoft 365'i bağla" must be hidden, or explain that the institution has not set it up. A button that leads to an error page: FAIL (minor).

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **My bookings on phone:** the tabs are one segmented control with labels that do not wrap. Its thumb rests inside the track (UI review: dark-mode thumb offset). Rows are cards (M-07): date + period on line 1, room + note on line 2, status word on line 3. The select checkbox has a ≥ 44 px hit area. The bulk bar "{n} rezervasyonu iptal et" replaces the tab bar or sits sticky above it.
- **Sync sheet on phone:** a bottom sheet with full-height detent. URL fields wrap or scroll inside themselves: the page never scrolls sideways (M-01). Every copy / add button is ≥ 44 px and labelled with words (not icon-only). The privacy warning is visible without expanding anything.
- "Bağlantı kopyalandı" is announced (live region), because a phone user does not see a clipboard change.
- **Tablet 768:** the sync panel may be a side sheet ≥ 360 px wide. Otherwise as on phone.

## Flow acceptance

1. No feed works until an admin has recorded a KVKK sign-off. Switching it off makes every feed 404 at once.
2. My bookings lists exactly the user's bookings and requests, with correct counts and statuses.
3. The feed is valid iCalendar (`icalendar` parses it) in Europe/Istanbul, with statuses CONFIRMED / TENTATIVE / CANCELLED, and updates in place when a decision is made.
4. Regenerating invalidates the old URL at once, and the UI confirms it and moves focus to the new URL.
5. Room and department feeds carry class meetings by course code only. No personal names appear in any feed.
6. MOBILE.md passes on `/my-bookings` (with the sync sheet open) at 390 and 768.

## Earlier issues to re-verify here

U-22 (no toast and no focus move on regenerate), U-23 (department default), A-12 (span as one item), A-14 / A-15 (classes in room feeds, ICS details), M-18 (no pre-seeded sign-off), M-40 (no KVKK admin screen), A-32 (Taleplerim row expand long frame: run the probe on expand, README §8).
