# F-03 · Find a room with capacity and a feature → reserve (or request) from the results

Personas: **staff** (direct booking, `approval_mode = rules`), **academician** (the same search when every request needs approval). The admin only prepares data. Viewports: desktop, tablet, phone.
Story (academician needs, persona-academician §5 row 18): "I need a computer lab for 42 students on Thursday afternoon for a make-up session; show me what fits and let me book it from the list."

Testable on `b75047b`: yes. A-11 (no feature facets, "PC" text contradicted by "PC özellikli oda; istenmedi") is reported fixed by the backend agent and is re-verified here.
Revised against `deb38315` (T-R2-35): the texts of S02 and S11 are the built ones (`wave1.find.*` and the server's reason sentences from `app/services/find_room.py`). On the phone the whole form, including **"Arama metni"** (`fr-text`), stays on the page; only "Özellikler" / "Binalar" move into the filters sheet (`fr-filters-sheet`).

## Preconditions

1. Restore the snapshot. Part A uses `{"approval_mode":"rules"}`, Part B `{"approval_mode":"all"}` (`PUT /org/settings`).
2. Typed room features exist: as admin,
   ```bash
   curl -fsS -X POST "$API/room-admin/features/template"   "${H[@]}" | jq length   # starter catalogue
   curl -fsS -X POST "$API/room-admin/features/adopt-tags" "${H[@]}" | jq length   # room-master tags (PC, LAB, AMPHI…) become features
   curl -fsS "$API/rooms/facets" -H "Authorization: Bearer $A" | jq '[.[]|.name]'   # must not be []
   ```
   Note the feature that carries the **PC** tag (`PC_FEATURE`, e.g. "Bilgisayar") and its id. (F-11 S04 tests the same through the admin UI.)
3. `D1` from README §4.3. Search window: **P7–P8** on D1. Headcount **42**.
4. Expected rooms, from `room_master.csv`: **A 105** (60 seats, PC) fits. Rooms with ≥ 42 seats and no PC tag do not. Rooms with PC but < 42 seats are "Küçük". The published Güz board may already hold A 105 at that time. Then the expected top result is the next free PC room ≥ 42 seats; record what the API returns in precondition 5.
5. Oracle: run the same search through the API before the UI:
   ```bash
   curl -fsS -X POST "$API/rooms/find" "${H[@]}" -d "{\"date\":\"$D1\",\"start\":7,\"end\":8,\"headcount\":42,\"features\":[{\"field\":$PC_FEATURE_ID}]}" > "$EV/curl/F03-oracle.json"
   ```
   A feature filter is `{"field": <feature id or name>, "op"?, "value"?}` (`app/schemas/find_room.py` `FeatureFilter`); `{"id": …}` is a 422. Every room in the "fits" part has capacity ≥ 42 and the PC feature. Save the ordered codes. The UI must show the same set in the same order.

## Steps

### Part A · approval_mode = rules (direct booking)

**S01 · staff · open Find a room**
- Do: log in as staff. Sidebar or tab bar **"Boş derslik bul"** (or ⌘K "Boş derslik bul"). The URL is `/find-room`.
- See: page title **"Boş derslik bul"**, lead **"Bir tarih, dönem haftalarında bir gün ya da bir tarih aralığı için boş derslikler, uygunluğa göre sıralı."** The empty state reads **"Ne zaman ve kaç kişi olduğunu seçip arayın."** The form shows "Ne zaman" (Tarih / Gün / Aralık), "Saat" or "Ders saati", **"Kaç kişi"** (hint "0 = fark etmez"), **"Özellikler"**, **"Binalar"**, **"Arama metni"**.
- Building chips read **"A Blok"**, not "A Blok Blok" (U-10).

**S02 · staff · search with capacity and a feature**
- Do: "Tarih" = D1 (`fr-date`). Switch time to **"Ders saati"**: "İlk ders saati" = 7, "Son ders saati" = 8. "Kaç kişi" = 42 (`fr-headcount`). In "Özellikler" (`fr-features`) select `PC_FEATURE` (`fr-feature-<id>`). Press **"Ara"** (`fr-search`).
- See while waiting: the button reads **"Aranıyor…"** and has `aria-busy="true"` (U-19, motion T1).
- See after: the summary (`fr-summary`, `role="status"`, announced) reads **"{n} derslik"** plus the open dates, e.g. "1/1 tarih boş". Results (`fr-results`) list the oracle's rooms in the oracle's order. Each card (`fr-room-<code>`) shows the code, the building, a status word **"Boş"**, the fit sentence **"Kapasite {cap}: 42 kişi için %{spare} boş koltuk"** (e.g. "Kapasite 60: 42 kişi için %30 boş koltuk"; the fit bar carries the same numbers) and the matched feature.
- The rooms without the feature sit in a collapsed **"Özelliği eksik odalar ({n})"** group; too-small rooms read **"Küçük"**; busy rooms are hidden until **"Dolu derslikleri de göster"** and then read **"Dolu: {what}"** (what holds the room: a course code or "rezervasyon", never a person name).
- Fail if any room with fewer than 42 seats, or without the feature, is in the main list (that was A-11's contradiction).

**S03 · staff · typed text finds features**
- Do: clear the feature chip. In **"Arama metni"** (`fr-text`; on the phone it is further down the same form, not in the filters sheet: scroll to it, `getByTestId('fr-text').scrollIntoViewIfNeeded()`; round 2 reported S03/S04 NOT RUN on the phone for want of this) type `PC` → Ara.
- See: the same rooms as S02 (the text matches the room's features, not just its notes). No result says "PC özellikli oda; istenmedi".

**S04 · staff · text that matches nothing**
- Do: text `yarın 14:00 60 kişi` → Ara.
- See: **"Metinle eşleşen derslik yok: “yarın 14:00 60 kişi”."** with **"Metni temizle"** (`fr-clear-text`). Pressing it runs the search again without the text. The text does not stay hidden in "Son aramalar" as a filter that empties later searches (U-25).

**S05 · staff · capacity edge**
- Do: back to S02's search, headcount **61**.
- See: A 105 (60 seats) leaves the main list with **"Küçük"**. With headcount **60** it is in the main list, and its fit bar shows a full room.

**S06 · staff · reserve from the results**
- Do: S02 search again. On the first result press **"Rezerve et"** (`fr-reserve-<code>`; accessible name **"<code> rezerve et"**).
- See: the book sheet opens prefilled: the room, D1, P7–P8 (two period chips). Note `Telafi dersi`. The button reads **"2 ders saatini rezerve et"**. Press it.
- See: toast **"<code>, <D1 date>: 2 ders saati rezerve edildi"**. The result list refreshes and the room is no longer "Boş" for that window. Focus returns to the result list (its heading or the next card), not `<body>` (A-21).
- API: `POST /bookings` → 201 for both periods (or one grouped booking). `/my-bookings` shows it (one row for the span is the target, persona-user Enh. #2).

**S07 · staff · the room was taken meanwhile**
- Do: run the S02 search again, so the list shows the next fitting room `RX`. In another context, the admin books `RX · D1 · P7` through the API. Then press "Rezerve et" on `RX` and submit.
- See: **"Bu derslik az önce doldu. Liste yenilendi."** RX leaves the main list. No half-booking exists (check `GET /bookings/grid` for P8).

**S08 · staff · few rooms: alternatives**
- Do: headcount **150** with `PC_FEATURE`, same window.
- See: **"Seçenekler"** / **"Üçten az derslik boş. Bunlar yakın:"** (`fr-alternatives`) with typed suggestions **"Başka saat"**, **"Başka gün"**, **"Neredeyse uygun"** (`fr-alt-<code>`). Each states what differs. Choosing one fills the form. If nothing at all fits: **"Bu arama için boş derslik yok."**

**S09 · staff · a holiday**
- Do: date **29 Oct 2026** (Cumhuriyet Bayramı) when it is in the future. Otherwise create a test holiday on D3 as admin (`POST /holidays`) and use D3.
- See: **"1 tarih kapalı"** and no free rooms. Each card reads **"0/1 tarih boş"** or **"Kapalı"**. Nothing can be reserved.

**S10 · staff · recent searches**
- See: **"Son aramalar"** (`fr-recent`) lists the S02 query with its date, window, people and feature. Selecting it restores the form and runs it.

### Part B · approval_mode = all (request from the results)

**S11 · academician · the same search, now requests**
- Do: set `approval_mode=all`. Log in as academician. Repeat S02 for `D3`.
- See: every result's status reads **"Onay gerekir"**; the card's first reason line is the server's **"Onay gerekli: talep oluşturulur"** and the helper text reads **"Bu dersliği bir onaycı onaylar: rezervasyonunuz talep olur."** The button reads **"Talep et"** (accessible name **"<code> için talep et"**).
- Do: "Talep et" → the sheet (note `Telafi: PSY 277`) → **"2 ders saati için talep et"**.
- See: toast **"<code> için talebiniz gönderildi. Onaycı karar verince size bildirilecek."** (on the phone wait for the toast with `getByRole('status')` before reading it; round 2 missed it by sampling too early).
- API: 202. The admin's bell and the sink receive "Onay bekleyen oda talebi: …" (F-01 S03).

**S12 · academician · make-up shortcut** (enhancement check, persona-academician Enh. #2)
- Target: from the academician's own class (after P19-T1 "Derslerim"), "Bu ders için boş oda bul" prefills the headcount, the features (PC lab for the PSY 277 lab) and the A-block preference. Today: `BLOCKED: P19-T1 not built` (rounds 1 and 2; FLE-001 family).

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Form in one column** (MOBILE.md M-10). The date field opens a localised picker. The time window uses two selects or a stepper, each ≥ 44 px.
- **"Özellikler"** and **"Binalar"** open in a bottom sheet titled "Filtreler" (or each as its own sheet) with ≥ 44 px chips. The selected count shows on the trigger ("Özellikler · 1").
- **"Ara"** is a sticky primary action at the bottom of the form, inside the thumb zone (M-05). It does not scroll away when the form is taller than the screen.
- **Results** are a card list (M-07). "Rezerve et" / "Talep et" is a full-width or right-aligned ≥ 44 px button in each card. The fit bar has a text equivalent ("Kapasite 60: 42 kişi için %30 boş koltuk") visible on phone, not only in a tooltip (M-11).
- After a search on phone, focus or scroll moves to the summary line, so the user sees that results arrived (and the live region announces it).
- **Tablet 768:** form and results may sit side by side. The results column is ≥ 360 px. Otherwise as on phone.

## Flow acceptance

1. The main result list contains exactly the rooms that are free in the whole window, have ≥ the headcount in seats and have every requested feature. Its order equals the API's.
2. Typed text matches features. Nothing contradicts the filter ("istenmedi" next to a requested feature).
3. Reserving from a result books exactly the shown room, date and periods. A taken room is refused with "Bu derslik az önce doldu. Liste yenilendi."
4. Under `approval_mode=all`, results say "Onay gerekir" and the action is a request (202).
5. Busy state, the live result count and focus after booking meet README §4.7. MOBILE.md passes on `/find-room` (form, filters sheet, results) at 390 and 768.

## Earlier issues to re-verify here

A-11 (features), U-10 ("A Blok Blok"), U-19 (busy state and announcement), U-25 (text that empties later searches), A-21 (focus after a booking from the results), motion T2/T3 (stale signal and long frames on re-search: record the probe numbers, README §8).
