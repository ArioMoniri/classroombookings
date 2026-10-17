# Slot display: how a bookable slot looks, set by administrators

Owner: product designer (wave3-des-2026-10-17) · Status: v3.0 spec (2026-10-17) · Builder: lane **W3-SLOT**
(`frontend/src/components/settings/slot-display.tsx`, settings keys `booking.slot_display.*` via
`app/services/settings_service.py` SPECS, read-only exposure in `app/api/v1/bookings.py`, copy `slotDisplay.*`).
Depends on: `docs/design/tokens.md` §A.5/§A.6 (control heights, `--row-h`, `data-density`), `docs/design/v2/motion.md`,
`docs/testing/flows/MOBILE.md` (M-02, M-08), `docs/design/v3/quick-reserve.md`.
Wireframes: `wireframes/slot-display-1440.svg`, `wireframes/slot-display-390.svg`, `wireframes/slot-display-matrix.svg`.

Owner's words: "How the slot size is shown is controlled by admins."

---

## 0. BLUF

- One admin card, **"Ders saati görünümü"**, with five groups: **Düzen** (period rows vs. time blocks), **Etiket**
  (period, time, or both; ordinal vs. schedule name; start vs. range), **Yoğunluk** (compact / standard / comfortable),
  **Görünen saatler** (first/last period, hide short transition slots) and **Varsayılan görünüm** (desktop and phone).
- A **live preview** sits next to the form (desktop) or opens as a bottom sheet (phone). It renders today's real periods
  through the **same render functions** the booking surfaces use, so what the admin sees is what users get.
- Every booking surface reads one resolved object (`slotDisplay`) and renders it per the matrix in §6. Phone rules from
  MOBILE.md always win (44 px rows, slot list first): the admin setting can never make the phone worse.
- Users may override density and their default view for themselves when the admin allows it (on by default).

## 1. Users and goals

| Persona | Goal | Answer |
|---|---|---|
| Booking administrator (setup.settings) | "Our teachers think in **ders saatleri** (3. ders), the staff think in clock time. Show both, but hide the 22:10 evening slots for day staff." | Etiket = both, Görünen saatler = 1–11 |
| Planning office | "The 30-minute 17:30 transition slot looks like a full lesson in the grid." | Düzen = time blocks (height ∝ minutes), or "Kısa geçiş saatlerini gizle" |
| Faculty with long blocks | "We book 3-hour labs; rows are too tall to see the day." | Yoğunluk = compact on desktop |
| Teacher on a phone | "Just show me free times." | Varsayılan görünüm (telefon) = Boş saatler / Hızlı rezervasyon |

## 2. References (public, checked 2026-10-17)

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| D1 | Google Calendar "Density and color": Responsive / Comfortable / Compact, desktop only ([Google help 15619910](https://support.google.com/calendar/answer/15619910), [Workspace update July 2026](https://workspaceupdates.googleblog.com/2026/07/updated-options-to-better-view-google-Calendar-on-large-monitors.html)) | Three named densities with one-line descriptions; density is a desktop concept (phones keep touch sizes) | Colour-set options here (colour is owned by tokens) |
| D2 | Notion Calendar settings: show/hide weekends and week numbers, week start, zoom the hour grid, 1–3 days on mobile ([Notion help](https://www.notion.com/help/notion-calendar-settings)) | "Görünen saatler" as a show/hide range; phone shows fewer columns by design | Per-user zoom as the only control (admins need an org default) |
| D3 | Pickatime admin view settings: scroll range, time-label intervals, slot height ([Pickatime admin view settings](https://help.pickatime.com/books/additional-event-features/page/admin-view-settings-page/export/html)) | Admin-level range + label interval + slot height as separate controls | Free-form pixel heights (we map to tokens) |
| D4 | Skedda space views: admin-defined views that users pick from the scheduler ([Skedda support 1043927](https://support.skedda.com/en/articles/1043927)) | Admin sets the default, users can switch | Hiding views from users silently |
| D5 | Calendly "start time increments" control how slots appear to invitees ([Calendly blog](https://calendly.com/blog/new-scheduling-page-ui), [Guideflow tutorial](https://www.guideflow.com/tutorial/how-to-customize-booking-page-options-in-calendly)) | Label choice affects what the booker sees, not the underlying schedule | Changing the schedule's periods here (periods are owned by /admin/schedules) |
| D6 | Grafana panel editor and Vercel/Linear "display options" popovers: options on one side, the live result on the other, applied without a save round-trip ([Grafana panel editor docs](https://grafana.com/docs/grafana/latest/panels-visualizations/panel-editor-overview/)) | Side-by-side live preview; "Varsayılana dön" | Preview that calls the server per keystroke |
| D7 | SmartSched today: `booking-grid.tsx` (period name + "09:20–10:00" row header), `free-slots-list.tsx` (start time), `my-bookings-view.tsx` (`period_name ?? P{n}`), tokens §A.6 densities | Existing `data-density` rows 32 / 44 / 56 and the period/time strings | Four different label rules in four surfaces (fixed by §5) |

Licences: pattern references only; no code copied. Components are from `components/ui` (MIT sources listed in
`components/ui/SOURCES.md`).

## 3. Settings model (`booking.slot_display.*`, add to SPECS; all org-wide)

| Key | Kind | Default | Values | Meaning |
|---|---|---|---|---|
| `booking.slot_display.layout` | str | `periods` | `periods`, `timeline` | **Ders satırları**: every period one equal row. **Zaman blokları**: row height ∝ minutes, breaks visible as gaps |
| `booking.slot_display.label` | str | `both` | `period`, `time`, `both` | what names a slot |
| `booking.slot_display.period_name` | str | `ordinal` | `ordinal`, `schedule` | "3. ders" (ordinal, localised) or the schedule's own period name (e.g. "Öğle arası", "P3") |
| `booking.slot_display.time_format` | str | `range` | `start`, `range` | "10:10" or "10:10–10:50" |
| `booking.slot_display.density` | str | `standard` | `compact`, `standard`, `comfortable` | desktop/tablet row height 32 / 44 / 56 (`data-density`, tokens §A.6). Phones: always ≥ 44 (compact = standard) |
| `booking.slot_display.first_period` | int | `0` | 0 = first, else period number | first visible period |
| `booking.slot_display.last_period` | int | `0` | 0 = last, else period number | last visible period |
| `booking.slot_display.hide_short` | bool | `false` | | hide periods shorter than 35 min (P12 17:30–18:00) |
| `booking.slot_display.default_view_desktop` | str | `grid_day` | `grid_day`, `grid_room_week`, `free_slots`, `quick` | what `/bookings` opens on at ≥ 1024 px |
| `booking.slot_display.default_view_phone` | str | `free_slots` | `free_slots`, `room_day`, `quick` | what `/bookings` opens on at < 640 px (never a multi-room grid, M-08) |
| `booking.slot_display.quick_span` | int | `1` | 1–3 | max periods one quick reservation may cover (quick-reserve.md §4.1 "Süre") |
| `booking.slot_display.user_override` | bool | `true` | | users may change density and their default view in Görünüm (their own, localStorage + profile) |

Resolution (one pure function `resolveSlotDisplay(org, user, viewport)`, unit-tested): user override (if allowed) →
org setting → default; then the phone clamp (density ≥ standard, default view ∈ phone set). Exposed read-only as
`slot_display` on `GET /bookings/context` so every surface gets it with the data it already loads; written through the
existing `PUT /settings` (setup.settings).

Validation (inline, before save): first ≤ last (else "İlk saat son saatten sonra olamaz"); at least one visible period;
`period_name=schedule` while some periods have no name → warning "Adı olmayan saatlerde sıra numarası gösterilir" (falls
back to ordinal per period); `label=period` with `layout=timeline` is allowed (times still on the axis).

Hidden periods are a **display** filter, never a permission: a booking that falls in a hidden period still appears in
My bookings, in notifications and in the room's day, and the grid shows a "+2 gizli saat" chip at the edge that reveals
them for this session.

## 4. The settings screen

Placement: `/settings?tab=slots` ("Ders saatleri"), permission `setup.settings`, next to "Rezervasyon kuralları". The
tab entry is one line in `components/settings/settings-view.tsx`, which W3-SLOT does not own: **Ask for the
orchestrator** to add `{ value: "slots", label: t("slotDisplay.tab"), show: can("setup.settings") }` and render
`<SlotDisplaySettings />`; until then the component can be mounted under the booking-rules tab.

### 4.1 Desktop (1440, `wireframes/slot-display-1440.svg`)

Two columns inside the 960 px settings column extended to 1120 for this tab: form 560, preview 520 (sticky top 96).

1. `Card` "Ders saati görünümü" with description "Rezervasyon ekranlarında ders saatlerinin nasıl görüneceğini seçin.
   Ders saatlerini değiştirmek için Zaman çizelgeleri."(link to /admin/schedules).
2. **Düzen**: two large radio cards side by side (`BareButton` role=radio, 88 px, a 40 × 48 mini drawing each): "Ders
   satırları: her ders saati eşit yükseklikte" / "Zaman blokları: yükseklik süreyle orantılı, aralar görünür".
3. **Etiket**: `SegmentedControl` (radiogroup) "Ders · Saat · İkisi"; under it, conditional rows: "Ders adı" `SegmentedControl`
   "Sıra (3. ders) · Çizelgedeki ad"; "Saat" `SegmentedControl` "Başlangıç (10:10) · Aralık (10:10–10:50)". Each option's
   example uses the real third period of the current schedule.
4. **Yoğunluk**: `SegmentedControl` "Sıkı · Standart · Geniş" + help "Telefonda satırlar en az 44 px kalır."
5. **Görünen saatler**: two `NativeSelect`s "İlk" / "Son" listing "1. ders · 08:30" … "18. ders · 22:10"; `Switch` "Kısa
   geçiş saatlerini gizle (30 dk)" with the affected periods named ("17:30–18:00"). A one-line summary: "11 / 18 ders
   saati görünür".
6. **Varsayılan görünüm**: two `NativeSelect`s "Masaüstü" (Günlük tablo, Derslik haftası, Boş saatler, Hızlı rezervasyon)
   and "Telefon" (Boş saatler, Derslik günü, Hızlı rezervasyon).
7. **Hızlı rezervasyon**: `SegmentedControl` "En fazla 1 · 2 · 3 ders".
8. **Kullanıcılar**: `Switch` "Kullanıcılar yoğunluğu ve varsayılan görünümü kendileri değiştirebilir".
9. Sticky save bar (page-actions capsule, admin kit `PageTitle` actions pattern): "Varsayılana dön" (ghost), "Kaydet"
   (primary, disabled when clean), unsaved guard (`use-unsaved-guard.ts`) on navigation.

**Preview** (right): a `Card` (plain, not glass: content) titled "Önizleme" with the footnote "Bugünün ders saatleri ·
örnek doluluk". Controls: `SegmentedControl` surface "Tablo · Liste · Hızlı" and device "Masaüstü · Telefon" (the phone
frame is 390 wide at 0.8 scale). Body: the real component in a `preview` mode fed by the current schedule's periods
and **synthetic statuses** (free / booked / class / closed, fixed pattern), so it never calls the server per change and
never shows real people's bookings. Every form change re-renders the preview in the same frame.

### 4.2 Phone (390, `wireframes/slot-display-390.svg`)

One column (M-10). The groups stack; each `SegmentedControl` is `fill`. The sticky footer holds "Önizle" (secondary,
opens the preview in a bottom `Sheet`, M-04, with the surface switcher and the phone frame at 1:1) and "Kaydet". A
compact inline preview strip (3 slot rows of the "Liste" surface) sits under the Etiket group so the most common change
shows its effect without opening the sheet.

### 4.3 States

| State | What shows |
|---|---|
| Loading | form controls disabled with `LoadingValue` placeholders; preview shows static placeholder rows |
| No schedule / no periods | `EmptyState` "Henüz ders saati tanımlı değil" + "Zaman çizelgeleri" link; the form stays editable, preview hidden |
| Dirty | save bar "Kaydedilmemiş değişiklikler" + Kaydet enabled; leaving asks (unsaved guard) |
| Saving | `BusyButton` "Kaydediliyor…" |
| Saved | toast "Görünüm kaydedildi. Kullanıcılar sayfayı yenileyince görür." with no undo (the old values are one "Varsayılana dön"/re-edit away; audit row `settings.update`) |
| Invalid | field-level error text + `aria-invalid`; Kaydet disabled; the first invalid field gets focus on a save attempt |
| Read-only (no setup.settings) | tab hidden; users see their own override in Görünüm (appearance tab) if allowed |

## 5. One label rule for every surface

`slotLabel(period, display, locale)` returns `{ primary, secondary, a11y }`:

| label | period_name | time_format | primary | secondary | a11y (always complete) |
|---|---|---|---|---|---|
| `period` | ordinal | — | "3. ders" | — | "3. ders, 10:10–10:50" |
| `period` | schedule | — | "Öğle" (fallback "3. ders") | — | "Öğle, 3. ders, 12:40–13:20" |
| `time` | — | start | "10:10" | — | "10:10–10:50, 3. ders" |
| `time` | — | range | "10:10–10:50" | — | same |
| `both` | ordinal | start | "3. ders" | "10:10" | "3. ders, 10:10–10:50" |
| `both` | ordinal | range | "3. ders" | "10:10–10:50" | same |

Inline (one-line) form: `primary · secondary` ("3. ders · 10:10"). English: "Period 3", "10:10–10:50". The accessible name
always has both period and full time range, whatever is visible (the visible text starts the name, WCAG 2.5.3). Times use
`Intl.DateTimeFormat(locale, {hour:'2-digit', minute:'2-digit'})` (24 h for tr-TR) and `<time>` elements.

## 6. How each booking surface renders each choice

| Surface (file) | layout `periods` | layout `timeline` | label | density | visible periods | default view |
|---|---|---|---|---|---|---|
| **/bookings day grid** (rooms × periods, `booking-grid.tsx`) | equal rows on `--row-h` | row height = minutes × k (k = 1.1 / 1.4 / 1.8 px per min for compact / standard / comfortable, min 32 px fine pointer); 10-min breaks as 4 px gaps; P12 visibly shorter | row header: primary (`type-headline`) + secondary (`type-footnote`); `time` only → single line | sets `data-density` on the grid | rows filtered; "+N gizli saat" chip at top/bottom edge | `grid_day` opens here on desktop |
| **/bookings room week** (`display=room`) | equal rows | as above, shared time axis left | as above | as above | as above | `grid_room_week` |
| **Free-slot list** (`free-slots-list.tsx`, phone default) | list rows ≥ 44 px (56 comfortable) | **ignored** (lists are not time-proportional); breaks not shown | row title = inline form; a11y full | desktop only; phone ≥ 44 | filtered | `free_slots` |
| **/rooms/[id] day** (`rooms/room-day-view.tsx`) | rows | proportional rows on desktop; phone stays rows (one column, 44 px) | row label | desktop only | filtered, held bookings in hidden periods still shown with a "gizli saat" footnote | `room_day` (phone) |
| **Book sheet period chips** (`book-sheet.tsx`) | chips | ignored | chip text = primary (time label if `time`); tooltip/a11y full | chip height = control token | filtered | — |
| **Quick reserve** (`quick-reserve/*`) | slot chips (phone) / slot list (desktop) | ignored | chip = inline form ("3. ders · 10:10") | list rows on desktop follow density | filtered; smart default never picks a hidden period | `quick` |
| **/find-room** start/end selects | option text = inline form | — | as label | — | options filtered (a range may still cover hidden periods, shown in the result as time) | — |
| **/my-bookings** rows (`my-bookings-view.tsx`) | — | — | replaces `period_name ?? P{n}` with primary; spans "3.–4. ders · 10:10–11:40" | table density (DataTable prefs) | **not filtered** (your bookings always show) | — |
| **Dashboard** "Sıradaki rezervasyon" | — | — | inline form | — | not filtered | — |
| **Email / ICS / push** (`bookings_notify`) | — | — | server-side same rule (backend helper reads the same keys) | — | not filtered | — |
| **/timetable** (planner calendar) | **not affected**: the planner's calendar has its own lens and zoom (calendar.md) | | | | | |

Unknown surfaces fall back to `label=both, time_format=range`.

## 7. Copy (keys `slotDisplay.*`, TR first)

| Key | TR | EN |
|---|---|---|
| `slotDisplay.tab` | Ders saatleri | Slots |
| `slotDisplay.title` | Ders saati görünümü | Slot display |
| `slotDisplay.description` | Rezervasyon ekranlarında ders saatlerinin nasıl görüneceğini seçin. | Choose how slots appear on the booking screens. |
| `slotDisplay.schedulesLink` | Ders saatlerini değiştirmek için: Zaman çizelgeleri | To change the periods themselves: Schedules |
| `slotDisplay.layout` | Düzen | Layout |
| `slotDisplay.layout.periods` | Ders satırları | Period rows |
| `slotDisplay.layout.periodsHelp` | Her ders saati eşit yükseklikte. | Every period has the same height. |
| `slotDisplay.layout.timeline` | Zaman blokları | Time blocks |
| `slotDisplay.layout.timelineHelp` | Yükseklik süreyle orantılı; aralar görünür. | Height follows duration; breaks are visible. |
| `slotDisplay.label` | Etiket | Label |
| `slotDisplay.label.period` | Ders | Period |
| `slotDisplay.label.time` | Saat | Time |
| `slotDisplay.label.both` | İkisi | Both |
| `slotDisplay.periodName` | Ders adı | Period name |
| `slotDisplay.periodName.ordinal` | Sıra ({example}) | Number ({example}) |
| `slotDisplay.periodName.schedule` | Çizelgedeki ad | Name from the schedule |
| `slotDisplay.periodName.missing` | Adı olmayan saatlerde sıra numarası gösterilir. | Periods without a name show their number. |
| `slotDisplay.timeFormat` | Saat | Time |
| `slotDisplay.timeFormat.start` | Başlangıç ({example}) | Start ({example}) |
| `slotDisplay.timeFormat.range` | Aralık ({example}) | Range ({example}) |
| `slotDisplay.ordinal` | {n}. ders | Period {n} |
| `slotDisplay.density` | Yoğunluk | Density |
| `slotDisplay.density.compact` | Sıkı | Compact |
| `slotDisplay.density.standard` | Standart | Standard |
| `slotDisplay.density.comfortable` | Geniş | Comfortable |
| `slotDisplay.density.phoneNote` | Telefonda satırlar en az 44 px kalır. | On phones rows stay at least 44 px tall. |
| `slotDisplay.visible` | Görünen saatler | Visible periods |
| `slotDisplay.visible.first` | İlk | First |
| `slotDisplay.visible.last` | Son | Last |
| `slotDisplay.visible.hideShort` | Kısa geçiş saatlerini gizle ({list}) | Hide short transition slots ({list}) |
| `slotDisplay.visible.summary` | {n} / {total} ders saati görünür | {n} of {total} periods visible |
| `slotDisplay.visible.errorOrder` | İlk saat son saatten sonra olamaz. | The first period cannot be after the last. |
| `slotDisplay.hiddenChip` | +{n} gizli saat | +{n} hidden periods |
| `slotDisplay.hiddenNote` | Gizli saatte | In a hidden period |
| `slotDisplay.defaultView` | Varsayılan görünüm | Default view |
| `slotDisplay.defaultView.desktop` | Masaüstü | Desktop |
| `slotDisplay.defaultView.phone` | Telefon | Phone |
| `slotDisplay.view.grid_day` | Günlük tablo | Day grid |
| `slotDisplay.view.grid_room_week` | Derslik haftası | Room week |
| `slotDisplay.view.free_slots` | Boş saatler | Free slots |
| `slotDisplay.view.room_day` | Derslik günü | Room day |
| `slotDisplay.view.quick` | Hızlı rezervasyon | Quick reserve |
| `slotDisplay.quickSpan` | Hızlı rezervasyonda en fazla | Quick reserve, at most |
| `slotDisplay.quickSpan.n` | {n} ders | {n, plural, one {# period} other {# periods}} |
| `slotDisplay.userOverride` | Kullanıcılar yoğunluğu ve varsayılan görünümü kendileri değiştirebilir | Users may change density and default view for themselves |
| `slotDisplay.preview` | Önizleme | Preview |
| `slotDisplay.preview.note` | Bugünün ders saatleri · örnek doluluk | Today's periods · sample occupancy |
| `slotDisplay.preview.surface.grid` | Tablo | Grid |
| `slotDisplay.preview.surface.list` | Liste | List |
| `slotDisplay.preview.surface.quick` | Hızlı | Quick |
| `slotDisplay.preview.open` | Önizle | Preview |
| `slotDisplay.reset` | Varsayılana dön | Reset to default |
| `slotDisplay.save` | Kaydet | Save |
| `slotDisplay.saving` | Kaydediliyor… | Saving… |
| `slotDisplay.saved` | Görünüm kaydedildi. Kullanıcılar sayfayı yenileyince görür. | Display saved. Users see it after a reload. |
| `slotDisplay.unsaved` | Kaydedilmemiş değişiklikler | Unsaved changes |
| `slotDisplay.empty` | Henüz ders saati tanımlı değil. | No periods are defined yet. |

## 8. Motion

Purpose: none needed beyond the primitives. Settings changes are frequent and must feel immediate.

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Any option change → preview re-render | **none** (same frame) | — | — | — |
| SegmentedControl thumb | primitive (motion.md §3.13) | `--spring-glass-morph` | jumps | solid thumb |
| Layout radio card selected | check pop | `bouncySubtle` | static | — |
| Preview sheet (phone) | pattern 4 | `sheet`, exit 120 ms | end state | solid |
| Save → toast | pattern 5 | `smooth` | fade 100 ms | solid |
| Timeline ↔ rows in the preview | **no interpolation** of row heights (per-frame layout; motion.md §1.2 zoom rule) | — | — | — |

## 9. Accessibility and keyboard

- Each group is a `fieldset` with a `legend`; segmented groups use `semantics="radiogroup"`; arrows move, Tab leaves.
- The preview is `aria-label="Önizleme"`, `inert` for interaction (it is a picture of the result), but its text is
  readable; an `aria-live="polite"` summary under the form reads the effect ("Örnek: 3. ders · 10:10, 11 ders saati
  görünür") after a change, debounced 500 ms.
- Errors: text under the field, `aria-describedby`, focus to the first invalid field on save.
- Touch: all controls 44 px (coarse), `NativeSelect` on phones, 16 px text.
- No meaning by colour: preview statuses use the grid's existing icon + word legend.

## 10. Components

| Component | File | Use | Source / licence |
|---|---|---|---|
| `Card` | `ui/card.tsx` | settings card, preview card | shadcn/ui MIT |
| `SegmentedControl` | `ui/segmented-control.tsx` | Etiket, Ders adı, Saat, Yoğunluk, preview surface/device, quick span | in-house |
| `BareButton` radio cards | `ui/button.tsx` | Düzen | shadcn/ui MIT (modified) |
| `NativeSelect` | `ui/native-select.tsx` | İlk / Son, default views | in-house |
| `Switch` | `ui/switch.tsx` | hide short, user override | shadcn/ui MIT |
| `Sheet` | `ui/sheet.tsx` | phone preview | shadcn/ui MIT |
| `BusyButton`, `Button` | `ui/busy-label.tsx`, `ui/button.tsx` | Kaydet, Varsayılana dön | in-house / MIT |
| `EmptyState`, `LoadingValue` | `ui/empty-state.tsx`, `ui/skeleton.tsx` | states | in-house / MIT |
| page-actions capsule | `admin/kit.tsx` `PageTitle` actions | sticky save | in-house |
| `use-unsaved-guard` | `admin/use-unsaved-guard.ts` | leave guard | in-house |
| **new** `slotLabel()` + `resolveSlotDisplay()` | `components/bookings/slot-label.ts` (W3-SLOT) | the one label rule (§5) and resolution (§3), pure + unit-tested | in-house |

## 11. Acceptance checks

Admin = setup.settings; viewports 1440 (mouse) and 390 (touch, tr-TR).

| # | Check | Pass |
|---|---|---|
| SD-01 | Open `/settings?tab=slots` | card, five groups, preview visible at 1440 (side by side), "Önizle" in the sticky footer at 390 (M-05) |
| SD-02 | Change Etiket to "Saat" | preview row titles change to "10:10–10:50" in the same frame; nothing else on the page moves |
| SD-03 | Save, then open `/bookings` as a teacher | grid row headers read "10:10–10:50"; free-slot list, book-sheet chips, `/reserve` chips and `/my-bookings` all use the same text (§6) |
| SD-04 | Düzen = Zaman blokları at 1440 | in `/bookings` the 17:30–18:00 row is visibly shorter (≈ 30/40 of a lesson row) and breaks show gaps; at 390 the free-slot list is unchanged (rows ≥ 44 px) |
| SD-05 | Yoğunluk = Sıkı | desktop grid rows 32 px (`data-density="compact"`); at 390 every row/target still ≥ 44 px (M-02 PASS) |
| SD-06 | Görünen saatler 1–11 | `/bookings` shows 11 rows + "+N gizli saat" chip; a teacher's booking at 19:40 still appears in `/my-bookings` and in the room's day with "Gizli saatte" |
| SD-07 | İlk > Son | inline error, Kaydet disabled, save attempt focuses "İlk" |
| SD-08 | Varsayılan görünüm telefon = Hızlı rezervasyon | at 390 `/bookings` opens `/reserve` content (or redirects) and passes M-08 |
| SD-09 | User override off | the user's Görünüm tab hides density/default view controls; on → a user's compact choice applies only to them |
| SD-10 | Accessible names | in every surface the slot's accessible name contains both "3. ders" and "10:10–10:50", whatever the visible label |
| SD-11 | English | all §7 strings in EN; "Period 3" format |
| SD-12 | Unsaved guard | change a value, click another nav item: the guard dialog asks; Escape returns focus to the nav item |
| SD-13 | Backend | `GET /bookings/context` returns `slot_display` with resolved values; `PUT /settings` with an unknown value → 422 |
