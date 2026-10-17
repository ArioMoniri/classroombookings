# Quick reserve (`/reserve`): book one slot in three taps

Owner: product designer (wave3-des-2026-10-17) · Status: v3.0 spec (2026-10-17) · Builder: lane **W3-SLOT**
(`frontend/src/components/quick-reserve/**`, `frontend/src/app/(app)/reserve/**`, keys `quickReserve.*`).
Depends on: `docs/design/tokens.md` §A (sizes, focus, radius, type), `docs/design/v2/liquid-glass.md` (material, rule G1:
only chrome floats), `docs/design/v2/motion.md` (springs, §3.7 reservation rows reused here), `docs/testing/flows/MOBILE.md`
M-01…M-14, and `docs/design/v3/slot-display.md` (how a slot is labelled: period vs. time).
Wireframes: `wireframes/quick-reserve-390.svg`, `wireframes/quick-reserve-390-receipt.svg`,
`wireframes/quick-reserve-1440.svg`, `wireframes/quick-reserve-states.svg`.

Owner's words: "Users should be able to make slot reservations easily in a simple UI."

---

## 0. BLUF

- One route, `/reserve`, one screen, three stacked steps: **1 Ne zaman?** (day + slot) → **2 Nerede?** (free rooms for
  that slot) → **3 Onayla** (summary, optional note, one primary button). No wizard pages, no modal on the happy path.
- Smart defaults make the common case **2 taps** (today's next free slot is preselected: tap a room, tap "Rezerve et").
  Any slot on the preselected day is **3 taps**. Another day is one more tap.
- The primary button says what will happen: **"Rezerve et"** when the room books directly, **"Talep et"** when the room
  or a booking policy needs approval (`request_only`, approvals check). The receipt says which one happened.
- Every success ends on a **receipt** with **"Geri al"** (10 s toast and an inline button on the receipt) and a link to
  "Rezervasyonlarım". A slot taken in the meantime ends on a **conflict** state that offers the nearest alternatives in
  place, never a dead end.
- It reuses the existing grid/find backends (`GET /bookings/grid`, `POST /rooms/find`, `POST /bookings`,
  `GET /approvals/rooms/{id}/check`, cancel/withdraw). No new endpoint is required (one optional field, §9).

## 1. Users and goals

| Persona | Goal | Today (pain) | Quick reserve answer |
|---|---|---|---|
| Teacher (öğretim elemanı), phone, between classes | "I need a room for a make-up lesson at 14:20 today" | `/bookings` opens on a free-slot list or a multi-room grid; the book sheet has single/recurring tabs, notes, department, user | Today + next slot preselected, free rooms ranked by fit, one button |
| Staff (idari personel), desktop | "Reserve a meeting room tomorrow 10:10 for 12 people" | Find-a-room is powerful but needs date + range + filters before results | Day chip "Yarın", slot chip, "Kişi" filter chip, room list, button |
| Any user under an approval rule | "Will I get the room or not?" | The difference between booked and requested is in a toast | The button text, a badge on the row and the receipt state all say "Talep" |

Non-goals (stay in `/bookings` and `/find-room`): recurring series, multi-room, multi-span drag selection, booking on
behalf of someone else (`set_user`), department assignment (`set_department`), editing existing bookings. Quick reserve
links to them ("Daha fazla seçenek") with the current day/slot/room carried in the query string.

## 2. References (public, checked 2026-10-17; Mobbin was not authorised in this session)

| # | Reference | What we borrow | What we avoid |
|---|---|---|---|
| R1 | Robin mobile booking: "+" → "Book a space", pick space, **Reserve** at the bottom of the page ([Robin help: how your team books](https://support.robinpowered.com/hc/en-us/articles/47011580690189), [getting started](https://support.robinpowered.com/hc/en-us/articles/204474494)) | One primary verb at the bottom, date/time controls on top, filters behind an icon | Map-first selection (we have no floor plans; a list is faster to scan) |
| R2 | Skedda Booking Approvals: submit button reads **"Request"** instead of "Book"; nothing appears on the scheduler until decided; the success alert links to the request ([Skedda support: booking requests](https://support.skedda.com/en/articles/11774950-booking-requests-approvals), [Skedda blog](https://www.skedda.com/blog/booking-approvals)) | "Talep et" as the button label, a receipt that links to the request, withdraw from the receipt | Hiding the approval need until after submit |
| R3 | Calendly scheduling page: only bookable slots are shown; pick a day, then a time, then confirm, "in fewer clicks" ([Calendly: new scheduling page](https://calendly.com/blog/new-scheduling-page-ui), [SaaS calendar UX patterns](https://www.saasui.design/blog/saas-calendar-scheduling-ux-patterns)) | Day → slot → confirm on one surface; unavailable slots are not choices; an unmistakable confirmation | Full month calendar as the first control (a teacher books within days, not months) |
| R4 | Outlook Room Finder: availability first, filters (capacity, building), admins set the booking rules ([Meeting Room 365 guide](https://www.meetingroom365.com/blog-md/how-to-reserve-room-outlook.md), [Room Finder for Outlook Mobile](https://m365admin.handsontek.net/page/567/)) | Rooms listed for a chosen time with capacity and building; rules enforced by the server, explained in the UI | A separate add-in pane; the event form as the entry point |
| R5 | Google Calendar room suggestions: suggest rooms by building and **frequently used rooms** ([Workspace admin help](https://knowledge.workspace.google.com/admin/calendar/set-up-google-calendar-room-booking-suggestions)) | "Son kullandığınız" ranking boost for the rooms the user booked before | Suggestions that depend on working-location settings we do not have |
| R6 | Apple HIG Undo and redo: name the result, show it when it is off-screen, let people revert ([HIG: Undo and redo](https://developer.apple.com/design/human-interface-guidelines/undo-and-redo)) | "Geri al" names what it undoes ("A 101 rezervasyonunu geri al"); focus and scroll go to the restored selection | Shake-to-undo (not a web gesture) |
| R7 | Material snackbar timing: 4–10 s on screen, one action ([Flutter SnackBar.duration](https://api.flutter.dev/flutter/material/SnackBar/duration.html), [Educative: snackbars](https://www.educative.io/answers/what-are-snackbars-in-ui-design)) | 10 s undo toast, paused on hover/focus; the receipt keeps a permanent cancel | Undo that exists only in a vanishing toast (WCAG 2.2.1) |
| R8 | Material 3 Expressive: button groups, spring motion that respects reduce-motion ([material_3_expressive docs](https://pub.dev/documentation/material_3_expressive/1.0.8/)) | Connected chip groups for day/slot with one selected state; springs only on confirmation | Shape-morphing on every press (motion.md rule 3) |
| R9 | SmartSched's own reservation panel (`components/bookings/book-sheet.tsx`, `free-slots-list.tsx`, motion.md §3.7) | Approval check, PENDING toast copy (`wave1.book.*`), busy labels, focus-after rules, reasons per slot | The sheet's tabs and optional fields on the quick path |

Licences: nothing is copied from these products; they are pattern references only. All components below are already in
`components/ui` (shadcn/ui MIT, beUI MIT, EvilCharts MIT; see `components/ui/SOURCES.md`). No new third-party code.

## 3. Interaction patterns (named)

| Pattern | Where | Rule |
|---|---|---|
| **Progressive one-screen form** (steps stacked, all visible) | whole page | Step 2 is visible but inert until step 1 has a value; step 3 until step 2 does. No "Next" buttons. |
| **Smart default** | step 1 | Day = today (after the last slot of today: the next school day). Slot = the next slot that has **any** free room for this user and has not started (`past` false). Preselected, not hidden: the chips show the selection. |
| **Choice chips as a radio group** | day strip, slot strip, filter chips | One selected; unavailable choices are shown disabled with a reason, not removed, when they explain the day (holiday, outside booking window). |
| **Ranked results list** | step 2 | Free rooms for the chosen slot, sorted by fit (see §4.3); each row is one radio. |
| **Sticky action bar** | phone footer, desktop right column | Summary line + primary. Present from first paint (button disabled until a room is chosen), so nothing jumps. |
| **Verb-honest primary** | step 3 | "Rezerve et" vs. "Talep et" decided before the tap (R2). |
| **Receipt + undo** | after submit | The step-3 card becomes the receipt (same place, same size); toast with "Geri al" for 10 s. |
| **Conflict recovery in place** | 409 | The card shows what happened and offers 3 alternatives (same slot other rooms, same room adjacent slots). |

## 4. Information hierarchy and layout

### 4.1 Phone (390 × 844, `wireframes/quick-reserve-390.svg`)

Top to bottom, one column (MOBILE M-10), no horizontal page scroll (M-01):

1. Shell top bar (existing) with the page title **"Hızlı rezervasyon"** (`type-large-title` in `PageHeader`, collapses on scroll).
2. **Step 1 · Ne zaman?**
   - Day strip: horizontally scrollable chip row inside its own scroller (not the page): "Bugün", "Yarın", then weekday
     + date ("Pzt 20"), 7 school days, then a "Tarih seç…" chip opening `DateField`'s popover as a bottom sheet. Chips
     are 44 px high on coarse pointers (`--control-h-md`). Today is labelled, not just coloured.
   - Slot strip: chips for the visible periods of that day, labelled per `slot-display.md` (default "3. ders ·
     10:10"). Started slots are hidden unless the user may book the past. Slots with no free room for this user are
     shown disabled with the word "Dolu" (so the day reads correctly), and are skipped by the smart default.
   - Optional "Süre" control only if the admin enabled multi-period quick bookings (`booking.slot_display.quick_span`,
     see slot-display.md §5): a `SegmentedControl` "1 ders · 2 ders · 3 ders". Off by default; quick reserve books one slot.
3. **Step 2 · Nerede?** header row: count ("12 boş derslik", `aria-live=polite`) and one **"Filtreler"** chip (M-04:
   opens a bottom `Sheet` with Kişi sayısı, Bina, Özellik). An active filter shows as "Filtreler · 2".
   - Room rows (`BareButton`, `role=radio`, ≥ 56 px, full width): **code + name** (`type-headline`), line 2 building ·
     capacity ("B Blok · 40 kişi"), tags as text chips (PC, Projeksiyon), right side: a "Talep" badge (Hourglass icon +
     word) when that room needs approval, a "Son kullandığınız" footnote when boosted. Selected row: check glyph in a
     24 px circle + `--primary-tint` fill + 2 px primary outline (never colour only).
   - First 8 rows, then "Tümünü göster (12)" (keeps the list short above the footer).
4. **Step 3 · Onayla**: lives in the **sticky footer** (glass chrome, `--mat-chrome`, bottom = above the tab bar,
   `env(safe-area-inset-bottom)` respected; M-05 bottom 40 %):
   - Summary line: "**A 101** · Bugün 3. ders (10:10–10:50)" or "Bir derslik seçin" when none.
   - "Not ekle" text button (opens a 1-row `Textarea` inside the footer, 16 px text, M-03/M-12).
   - Primary `Button size="lg"` full width: "Rezerve et" / "Talep et", disabled until a room is chosen.
   - Footnote under the button when relevant: remaining quota "Bu hafta 2 rezervasyon hakkınız kaldı"
     (`grid.remaining_bookings`), or the approver for "Talep et" ("Onaycı: Yapı İşleri · en geç 2 gün önce").

### 4.2 Desktop (1440 × 900, `wireframes/quick-reserve-1440.svg`)

Content width max 1200 px, centred, three columns in one row, all visible without scrolling at 900 px height:

| Column | Width | Content |
|---|---|---|
| 1 Ne zaman? | 320 | Day list (vertical radio list: Bugün, Yarın, 5 more days, "Tarih seç…" with `DateField`), slot list (vertical radio list with label + time, "Dolu" rows disabled) |
| 2 Nerede? | flexible (≥ 440) | Toolbar: count, filter chips inline (Kişi: Hepsi / ≤ 20 / ≤ 40 / 40+, Bina, Özellik) because there is room; table-like rows (code, name, building, capacity, tags, approval badge) |
| 3 Onayla | 360, sticky | `Card` (plain): summary (room, day, slot, time), approval explanation (`Alert tone="info"` when Talep), note `Textarea`, primary `Button size="lg"`, secondary link "Daha fazla seçenek" (to `/bookings?date=&room=&period=`) |

Tablet (768): columns 1 and 2 side by side, step 3 becomes the sticky footer as on the phone.

### 4.3 Room ranking (step 2)

Server order from `POST /rooms/find` (fit score) wins when present. Client tie-breaks, in order: rooms this user booked in
the last 60 days (R5, from `/bookings/mine`), direct booking before "Talep" (fewer steps for the user), smaller capacity
that still fits the "Kişi" filter, then room code. Rooms the user can see but not book are **not** listed (the grid already
filters by permission); rooms refused by a policy are listed only under "Neden bazı derslikler yok?" (a disclosure that
lists the refusal reasons, `policy.reason`), so the user understands a short list.

## 5. States

Each state lists what the user sees, the copy key and the focus rule. Copy is in §7.

| State | Trigger | Phone | Desktop | Focus / announce |
|---|---|---|---|---|
| **Loading (first paint)** | context + grid in flight | Day chips render immediately (from dates); slot strip and room list show static placeholder rows (`Skeleton`, motion.md §3.7 "Placeholders": static, crossfade out) ; footer visible, button disabled "Rezerve et" | same in columns | `aria-busy=true` on step 2; no announcement until results ("12 boş derslik") |
| **Re-loading** (day/slot/filter changed) | new query | previous rows stay, dimmed to 60 % after 120 ms (`data-stale`), count shows "Aranıyor…" | same | selection cleared only if the selected room is not in the new results; announce the new count |
| **Ready** | results | as §4 | as §4 | none (user drives) |
| **None free (this slot)** | `results=[]` | `EmptyState` (no lottie, icon `door-closed`): "Bu saatte boş derslik yok" + up to 3 **"En yakın boş saatler"** chips (same day, next slots with ≥ 1 free room, e.g. "4. ders · 11:00 · 6 derslik") + "Başka gün seç" + link "Gelişmiş arama" (`/find-room` with the query) | same, in column 2 | focus stays on the slot chip; polite announce "Bu saatte boş derslik yok. 3 öneri var." |
| **None free (whole day)** | every slot disabled | Step 1 shows the day with "Bu gün için boş saat yok" under the slot strip; the smart default moves to the next day that has one and says so: "Bugün dolu; Yarın 2. ders seçildi" (`Alert tone="neutral"`, dismissible) | same | announce the info line once |
| **Closed day** | holiday, weekend, outside term, outside booking window | Day chip disabled with reason in its accessible name and a footnote on long-press/focus: "Tatil: Cumhuriyet Bayramı", "Rezervasyon en fazla 14 gün önceden" | tooltip + footnote | disabled chips stay focusable (`aria-disabled`) so the reason is reachable by keyboard and screen readers |
| **Selected, direct** | room chosen, no approval | footer summary + "Rezerve et" | card | Enter on a row selects it and moves focus to the primary button |
| **Selected, approval-first ("Talep et")** | approvals check says the room needs approval, or `slot.request_only` | row badge "Talep"; primary "Talep et"; footnote "Onaycı: {approver} · {lead time}"; `Alert tone="info"` (desktop card, phone footer collapsible line): "Bu derslik onay gerektirir. Talebiniz onaylanınca rezervasyon kesinleşir." | same | button accessible name "A 101 için talep et" |
| **Submitting** | tap primary | `BusyButton`: label → "Rezerve ediliyor…" / "Talep gönderiliyor…" after 150 ms, `aria-busy`; the rest of the page stays usable but the primary ignores repeated taps | same | none until result |
| **Receipt, booked** | 201 | footer expands into the receipt card (phone: footer grows upward into a card with a ✓, `wireframes/quick-reserve-390-receipt.svg`): "Rezerve edildi" + "A 101 · Bugün 3. ders · 10:10–10:50" + buttons "Geri al" (secondary), "Takvime ekle" (ICS, existing feed), "Rezervasyonlarım" (link) + "Yeni rezervasyon" (ghost, resets steps 2–3, keeps the day) | column 3 card turns into the receipt | focus moves to the receipt heading (`tabIndex=-1`) at the start of the transition; polite announce "A 101 rezerve edildi. Geri almak için Geri al." Toast (sonner) with "Geri al" for 10 s, paused on hover/focus |
| **Receipt, requested** | 202 `PENDING` | same card, Hourglass glyph instead of ✓: "Talebiniz gönderildi" + "Onaycı karar verince size bildirilecek." + "Talebi geri çek" (instead of Geri al) + "Taleplerim" link | same | announce "A 101 için talebiniz gönderildi." |
| **Undo done** | "Geri al" → cancel / withdraw OK | receipt collapses back to the footer with the **same room and slot selected** (R6: the user sees what came back); toast "Rezervasyon geri alındı" (no action) | same | focus returns to the selected room row |
| **Undo failed** | 409 (someone changed it, window passed) | toast error with the server reason (`bookingErrorMessage`), receipt stays | same | assertive announce |
| **Conflict** | 409 on submit (slot taken / became request-only / limit) | the footer card shows `Alert tone="danger"`: "Bu saat az önce doldu." + **3 alternatives** as one-tap rows: same slot other rooms (from the 409 `alternatives` or a refreshed find), then same room ±1 slot; "Listeyi yenile". The taken room row in step 2 shows "Az önce doldu" and is disabled. The card shakes once (motion §8) | column 3 | focus to the alert heading; assertive announce. Choosing an alternative selects it and focuses the primary (no auto-submit) |
| **Policy refusal** | 422 / `reason: policy` (limit, lead time) | `Alert tone="warning"` with the rule text (`violationText`), `PolicyWhy` link; primary disabled | same | assertive |
| **Quota reached** | `remaining_bookings === 0` | step 3 shows "Bu dönem için rezervasyon hakkınız doldu." + link "Rezervasyonlarım"; steps 1–2 stay browsable | same | announce on load |
| **No permission** | user lacks any `book_*` | route shows `EmptyState` "Rezervasyon yetkiniz yok" + "Yöneticinize başvurun"; nav entry hidden | same | — |
| **Offline / 5xx** | network | `Alert tone="danger"` at the top of step 2 "Bağlantı sorunu. Tekrar deneyin." + "Tekrar dene" | same | assertive |
| **No published timetable** | `timetable_state` unpublished | `Alert tone="warning"` "Bu hafta için yayımlanmış ders programı yok; derslik dersle çakışabilir." (same rule as A-24 in book-sheet); primary still allowed when the backend allows it | same | polite |

## 6. Tap budget (acceptance-relevant)

| Case | Taps on a phone | Sequence |
|---|---|---|
| Today, next free slot, top-ranked room | **2** | room row → Rezerve et |
| Today, other slot | **3** | slot chip → room row → Rezerve et |
| Tomorrow / any day in the strip | 4 | day chip → slot chip → room row → Rezerve et |
| With a note | +2 | Not ekle → type → (submit) |
| Talep et | same as booking | the verb changes, not the count |
| Undo | 1 | Geri al |

"≤ 3 taps" is guaranteed for the preselected day. The day strip is scrollable without taps counting (a scroll is not a
tap). Never auto-submit on room tap: a booking is a commitment, and the 2-tap path is already the minimum.

## 7. Copy (Turkish first, English second; keys under `quickReserve.*`)

Tone: second person plural formal ("seçin", "gönderildi"), short, no exclamation marks, no raw enum keys.

| Key | TR | EN |
|---|---|---|
| `quickReserve.title` | Hızlı rezervasyon | Quick reserve |
| `quickReserve.nav` | Rezerve et | Reserve |
| `quickReserve.step.when` | Ne zaman? | When? |
| `quickReserve.step.where` | Nerede? | Where? |
| `quickReserve.step.confirm` | Onayla | Confirm |
| `quickReserve.day.today` | Bugün | Today |
| `quickReserve.day.tomorrow` | Yarın | Tomorrow |
| `quickReserve.day.pick` | Tarih seç… | Pick a date… |
| `quickReserve.day.closed.holiday` | Tatil: {name} | Holiday: {name} |
| `quickReserve.day.closed.window` | Rezervasyon en fazla {n} gün önceden yapılabilir | Bookings open {n} days ahead |
| `quickReserve.day.closed.weekend` | Hafta sonu ders yok | No classes at the weekend |
| `quickReserve.day.full` | Bu gün için boş saat yok | No free slots on this day |
| `quickReserve.day.movedToNext` | {from} dolu; {to} {slot} seçildi | {from} is full; picked {to} {slot} |
| `quickReserve.slot.full` | Dolu | Full |
| `quickReserve.duration` | Süre | Length |
| `quickReserve.duration.n` | {n} ders | {n} {n, plural, one {period} other {periods}} |
| `quickReserve.rooms.count` | {n, plural, =0 {Boş derslik yok} other {# boş derslik}} | {n, plural, =0 {No free rooms} one {# free room} other {# free rooms}} |
| `quickReserve.rooms.searching` | Aranıyor… | Searching… |
| `quickReserve.rooms.showAll` | Tümünü göster ({n}) | Show all ({n}) |
| `quickReserve.rooms.recent` | Son kullandığınız | Recently used |
| `quickReserve.rooms.capacity` | {n} kişi | {n} seats |
| `quickReserve.rooms.needsApproval` | Talep | Request |
| `quickReserve.rooms.whyMissing` | Neden bazı derslikler yok? | Why are some rooms missing? |
| `quickReserve.filters` | Filtreler | Filters |
| `quickReserve.filters.count` | Filtreler · {n} | Filters · {n} |
| `quickReserve.filters.people` | Kişi sayısı | People |
| `quickReserve.filters.people.any` | Hepsi | Any |
| `quickReserve.filters.building` | Bina | Building |
| `quickReserve.filters.feature` | Özellik | Feature |
| `quickReserve.filters.apply` | Uygula | Apply |
| `quickReserve.filters.clear` | Temizle | Clear |
| `quickReserve.summary.none` | Bir derslik seçin | Choose a room |
| `quickReserve.summary.line` | {room} · {day} {slot} ({time}) | {room} · {day} {slot} ({time}) |
| `quickReserve.note.add` | Not ekle | Add a note |
| `quickReserve.note.label` | Not (isteğe bağlı) | Note (optional) |
| `quickReserve.note.placeholder` | Örn. telafi dersi | E.g. make-up lesson |
| `quickReserve.submit.book` | Rezerve et | Reserve |
| `quickReserve.submit.bookFor` | {room} için rezerve et | Reserve {room} |
| `quickReserve.submit.request` | Talep et | Request |
| `quickReserve.submit.requestFor` | {room} için talep et | Request {room} |
| `quickReserve.submit.busyBook` | Rezerve ediliyor… | Reserving… |
| `quickReserve.submit.busyRequest` | Talep gönderiliyor… | Sending request… |
| `quickReserve.approval.body` | Bu derslik onay gerektirir. Talebiniz onaylanınca rezervasyon kesinleşir. | This room needs approval. Your booking is confirmed once the request is approved. |
| `quickReserve.approval.who` | Onaycı: {approver} · en geç {n} gün önce | Approver: {approver} · at least {n} days ahead |
| `quickReserve.quota.left` | Bu hafta {n} rezervasyon hakkınız kaldı | {n} bookings left this week |
| `quickReserve.quota.none` | Bu dönem için rezervasyon hakkınız doldu. | You have used all your bookings for this term. |
| `quickReserve.empty.slot.title` | Bu saatte boş derslik yok | No free rooms at this time |
| `quickReserve.empty.slot.nearest` | En yakın boş saatler | Nearest free times |
| `quickReserve.empty.slot.chip` | {slot} · {time} · {n} derslik | {slot} · {time} · {n} rooms |
| `quickReserve.empty.otherDay` | Başka gün seç | Pick another day |
| `quickReserve.empty.advanced` | Gelişmiş arama | Advanced search |
| `quickReserve.receipt.booked` | Rezerve edildi | Reserved |
| `quickReserve.receipt.requested` | Talebiniz gönderildi | Request sent |
| `quickReserve.receipt.requestedBody` | Onaycı karar verince size bildirilecek. | You will be notified when the approver decides. |
| `quickReserve.receipt.undo` | Geri al | Undo |
| `quickReserve.receipt.undoFor` | {room} rezervasyonunu geri al | Undo the {room} booking |
| `quickReserve.receipt.withdraw` | Talebi geri çek | Withdraw request |
| `quickReserve.receipt.calendar` | Takvime ekle | Add to calendar |
| `quickReserve.receipt.mine` | Rezervasyonlarım | My bookings |
| `quickReserve.receipt.myRequests` | Taleplerim | My requests |
| `quickReserve.receipt.again` | Yeni rezervasyon | New booking |
| `quickReserve.toast.booked` | {room} rezerve edildi | {room} reserved |
| `quickReserve.toast.requested` | {room} için talebiniz gönderildi | Request sent for {room} |
| `quickReserve.toast.undone` | Rezervasyon geri alındı | Booking undone |
| `quickReserve.toast.withdrawn` | Talep geri çekildi | Request withdrawn |
| `quickReserve.conflict.title` | Bu saat az önce doldu. | This slot was just taken. |
| `quickReserve.conflict.body` | Aynı saatte başka bir derslik ya da yakın bir saat seçin. | Pick another room at the same time or a nearby time. |
| `quickReserve.conflict.refresh` | Listeyi yenile | Refresh the list |
| `quickReserve.conflict.taken` | Az önce doldu | Just taken |
| `quickReserve.error.network` | Bağlantı sorunu. Tekrar deneyin. | Connection problem. Try again. |
| `quickReserve.error.retry` | Tekrar dene | Try again |
| `quickReserve.noPermission.title` | Rezervasyon yetkiniz yok | You cannot make bookings |
| `quickReserve.noPermission.body` | Yetki için yöneticinize başvurun. | Ask your administrator for access. |
| `quickReserve.unpublished` | Bu hafta için yayımlanmış ders programı yok; derslik dersle çakışabilir. | No published timetable for this week; the room may clash with a class. |
| `quickReserve.more` | Daha fazla seçenek | More options |

Reuse, do not duplicate: approval rule text from `wave1.book.*`, policy text from `violationText`, server errors from
`bookingErrorMessage`, day names from `days.*`.

## 8. Motion (per `docs/design/v2/motion.md`; add these rows to motion.md as §3.14 when built)

Purpose sentence: "When a reservation succeeds, motion tells the user that the card they were confirming **is** the
booking now; when it fails, it tells them the card they tapped is the one that needs attention." Everything else is still.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Day / slot / filter chip select | **none**: fill and check swap in the input frame (frequent action) | — | same | same |
| Room list replaced (new slot or filter) | **no stagger, no travel**; old rows dim to 60 % after 120 ms pending, new rows replace in place | `--dur-fast` opacity | dim without transition | same |
| Placeholder → rows (first load) | skeleton-on-top fade-out (pattern 12) | `smooth`, exit `tween.fadeOut` | instant | — |
| Room row selected | the 24 px check circle pops 0.9 → 1 (≤ 32 px, the only overshoot) | `bouncySubtle` | static check | — |
| Footer summary text changes | none (text swap) | — | — | — |
| Filters sheet (phone) | pattern 4, from the bottom, drag-down to dismiss | `sheet`, exit 120 ms `--ease-in` | end state next frame | `--mat-chrome-solid` |
| Busy primary | label → gerund after 150 ms; spinner as reinforcement only | spinner loop | static "…" + text | — |
| Footer/card → receipt | one `layout` morph of the same card (FLIP, transform only) grows upward; content crossfades ≤ 60 ms after the container; ✓ draws (pattern 10) | container `smooth`, ✓ `bouncySubtle` | instant swap, static ✓, 100 ms fade | opaque card |
| Toast with Geri al | pattern 5 | `smooth` | 100 ms fade | solid toast |
| Undo → back to selection | receipt morphs back to the footer (reverse of the same layout morph, origin preserved) | `smooth` (exit ≈ 65 %) | instant | opaque |
| Conflict | the summary card shakes once, 3 px × 2 (pattern 9); alert appears in place | tween 240 ms | **no shake**; danger outline + icon + text carry it | — |
| Alternatives appear | in place, no stagger | — | — | — |
| Route enter | shell route veil (pattern 13) | `smooth` | fade | — |

Budget: one glass surface moving at a time (the footer); the footer's `backdrop-filter` is never on an element whose
`filter` or opacity animates (backdrop-root rule): the morph animates the card's transform, the content child crossfades.
Every one-shot ≤ 300 ms.

## 9. Data contract (read by W3-SLOT; no new endpoint)

| Need | Source |
|---|---|
| Days, closed reasons, booking window | `GET /bookings/dates`, `GET /bookings/context` |
| Slots of the day, per-slot availability for this user | `GET /bookings/grid?display=day&date=` (`isSelectable`, `past`, `request_only`, `policy`) |
| Free rooms for one slot, fit, alternatives | `POST /rooms/find {date, start, end}` (`FindResult`), filters passed through |
| Approval need + approver | `GET /approvals/rooms/{id}/check` (prefetch for the top 8 rows, so the verb is known before the tap) |
| Book | `POST /bookings` (`SingleBookingIn`), 201 or 202 `PENDING` |
| Undo a booking | **preferred**: `POST /audit/{id}/undo` (P7, `bookings_undo.py`, re-checks and writes `undo_of`) when the create response carries the audit event id; **fallback today**: `POST /bookings/{id}/cancel {scope:"one", reason:"undo"}` |
| Withdraw a request | `POST /approvals/{id}/withdraw` |
| Recent rooms | `GET /bookings/mine` (last 60 days) |
| Slot labels | `booking.slot_display.*` (slot-display.md) |

Open decision for W3-SLOT / orchestrator: expose `audit_event_id` on the `POST /bookings` response so "Geri al" uses the
real undo (it keeps the audit trail honest: the cancel is recorded as an undo, not a user cancellation, and
`bookings_notify` sends no "cancelled" mail for an undo within 10 s). If not exposed, use the fallback and reason code.

## 10. Components (existing design system; nothing new from outside)

| Component | File | Use here | Source / licence |
|---|---|---|---|
| `PageHeader` / `PageTitle` | `components/admin/kit.tsx`, shell | "Hızlı rezervasyon" | in-house (AGPL-3.0, repo) |
| `Chip` | `ui/chip.tsx` | day, slot, filter chips (`role=radio` inside a `role=radiogroup`) | shadcn/ui-derived, MIT |
| `SegmentedControl` | `ui/segmented-control.tsx` | "Süre" (only if enabled) | in-house |
| `DateField` | `ui/date-field.tsx` | "Tarih seç…" | in-house |
| `BareButton` | `ui/button.tsx` | room rows (draws its own surface, keeps focus ring and hit area) | shadcn/ui MIT, modified |
| `Badge`, `StatusDot` | `ui/badge.tsx`, `ui/data-table` | "Talep" badge (Hourglass + word), "Son kullandığınız" | shadcn/ui MIT / in-house |
| `Sheet` | `ui/sheet.tsx` | filters (bottom on phone) | shadcn/ui MIT |
| `Card` (plain) | `ui/card.tsx` | step-3 card and receipt (desktop), footer card (phone) | shadcn/ui MIT |
| `Alert` | `ui/alert.tsx` / `admin/kit` `Alert` | approval info, conflict, policy, network | in-house |
| `EmptyState` | `ui/empty-state.tsx` | none free, no permission (lottie off: static icon) | in-house (lottie assets AGPL) |
| `Skeleton` / `LoadingValue` | `ui/skeleton.tsx` | placeholders | shadcn/ui MIT |
| `Button` (`size lg`), `BusyButton` | `ui/button.tsx`, `ui/busy-label.tsx` | primary, busy label | shadcn/ui MIT / in-house |
| `Textarea` | `ui/textarea.tsx` | note | shadcn/ui MIT |
| sonner `Toaster` | `ui/sonner.tsx` | receipt toast with Geri al (10 s) | sonner MIT |
| `PolicyWhy` | `components/policies/policy-why.tsx` | policy refusal "Neden?" | in-house |
| Shell tab bar | `components/shell/nav-config.ts` | append one entry "Rezerve et" (lane W3-SLOT, append only) | in-house |

New component (W3-SLOT, in `components/quick-reserve/`): **`ChipRadioGroup`** (roving-tabindex radiogroup of `Chip`s with
disabled-with-reason items). Reason: the design system has `SegmentedControl` (equal columns, ≤ 7 short options) but no
scrollable single-select chip row; days (8) and periods (up to 18) need one. Keep it local to quick-reserve until a second
surface needs it.

## 11. Accessibility and keyboard

- Landmarks: `<main>` with one `h1`; each step is `<section aria-labelledby>` with an `h2` ("1. Ne zaman?"); the step
  number is text, not only a circle.
- Day, slot and room groups are `role=radiogroup` with `aria-label` ("Gün", "Ders saati", "Derslik"); roving tabindex:
  **Tab** enters a group on its selected item, **←/→** (chips) or **↑/↓** (rooms) move and select, **Home/End** jump,
  disabled items are reachable (`aria-disabled`) and announce their reason in their name ("Pzt 28, tatil: Cumhuriyet Bayramı").
- **Enter** on a room selects it and moves focus to the primary button; **Ctrl/⌘+Enter** anywhere on the page submits when a
  room is selected. **Esc** closes the filters sheet and returns focus to "Filtreler".
- Live regions: one polite region for counts and receipts, one assertive (`role=alert`) for conflict, policy, network.
  Announce results, not loading frames.
- Focus never falls to `<body>`: after submit → receipt heading; after undo → the restored room row; after choosing an
  alternative → the primary; after closing a sheet → its trigger.
- Colour is never the only cue: selection = check glyph + outline + tint; "Talep" = Hourglass + word; "Dolu" = word;
  disabled = word + reduced contrast on `text-label-3` (not `label-4`, which is decoration only, tokens.md §A.7).
- Targets ≥ 44 × 44 on coarse pointers (`coarseHitArea`; chip rows inside a scroller pad by the extension, tokens.md §A.9).
  Inputs 16 px on phones. The note field is not covered by the keyboard (`keyboard-clearance.tsx`, M-12).
- Accessible names for buttons include the room ("A 101 için rezerve et"), so voice control ("tap Rezerve et") still works
  because the visible label starts the name (WCAG 2.5.3).
- Times are `<time datetime="2026-10-19T10:10">`. Dates use `Intl.DateTimeFormat('tr-TR')`.
- Reduced motion / transparency per §8. Forced colours: selection outline uses `Highlight`, badges keep their words.

## 12. Acceptance checks (a tester can run these; viewports per `docs/testing/flows/README.md` §3)

Run at 1440 × 900 (mouse) and 390 × 844 (touch, `isMobile`, `hasTouch`, `tr-TR`, `Europe/Istanbul`), as a teacher with
booking rights, on a stack with a published run and at least one approval-rule room.

| # | Check | Pass |
|---|---|---|
| QR-01 | Open `/reserve` at 390 | today's day chip and a slot chip are selected; room rows are visible without scrolling the page more than one screen; the footer with a disabled "Rezerve et" is in the bottom 40 % (M-05) |
| QR-02 | 2-tap path | tap the first room row, tap "Rezerve et": receipt "Rezerve edildi" with room and time; booking appears in `/my-bookings`; exactly 2 `click` events recorded |
| QR-03 | 3-tap path | tap another slot chip, a room, "Rezerve et": receipt; 3 taps |
| QR-04 | Undo | on the receipt tap "Geri al" within 10 s: toast "Rezervasyon geri alındı", the same room + slot are selected again, focus is on that room row; the booking is gone from `/my-bookings` and the audit shows an undo (or a cancel with reason `undo` on the fallback) |
| QR-05 | Approval-first | select an approval-rule room: badge "Talep", button reads "Talep et" **before** tapping, footnote names the approver; submit → receipt "Talebiniz gönderildi" with "Talebi geri çek"; request visible in `/requests` |
| QR-06 | Withdraw | "Talebi geri çek" on the receipt → toast "Talep geri çekildi", request status withdrawn |
| QR-07 | None free | pick a slot where every room is taken (or filter Kişi 40+ at a busy slot): "Bu saatte boş derslik yok" with ≤ 3 "En yakın boş saatler" chips; tapping one selects that slot and shows rooms |
| QR-08 | Conflict | open the page in two sessions, select the same room + slot, submit in session A, then in B: B shows "Bu saat az önce doldu.", the room row says "Az önce doldu", 1–3 alternatives are offered, focus is on the alert; nothing was booked twice |
| QR-09 | Closed day | a holiday or out-of-window day chip is disabled, focusable, and its accessible name contains the reason |
| QR-10 | Keyboard only (1440) | Tab reaches day group → slot group → filters → room group → note → primary; arrows move inside groups; Enter on a room focuses the primary; Ctrl+Enter submits; focus never on `<body>` (README §4.7) |
| QR-11 | Screen reader text | `aria-live` announces "N boş derslik" after a slot change and "A 101 rezerve edildi…" after submit; conflict is `role=alert` |
| QR-12 | MOBILE M-01/M-02/M-03/M-04/M-05/M-12 on `/reserve` | all pass (filters open as a bottom sheet; note input 16 px and not covered by the keyboard) |
| QR-13 | Reduced motion (`emulateMedia({reducedMotion:'reduce'})`) | receipt appears without transform animation (`document.getAnimations()` has no transform animations), conflict has no shake but shows the danger alert |
| QR-14 | Over-ceiling | no animation on the page lasts > 300 ms (motion audit template) |
| QR-15 | English | switch to EN: every string from §7 is translated; no raw keys (`quickReserve.` never visible) |
| QR-16 | Slot labels follow the admin setting | set `booking.slot_display.mode=time` in admin: slot chips read "10:10–10:50" instead of "3. ders · 10:10" (slot-display.md SD-checks) |
