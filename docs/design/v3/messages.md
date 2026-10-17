# In-app messages: bell items, toasts, banners, empty states (TR + EN)

Owner: product designer (wave3b-des2-2026-10-17) · Status: v3.0 spec (2026-10-17) · Builders: whoever owns each surface
(the bell: `components/notifications/**`; toasts: the action's own component via `ui/sonner.tsx`; banners: the surface;
backend titles/bodies: `approvals.TEXTS`, `bookings_i18n` set `email`, `notify_dispatch.Notice`), coordinated by
**W3-MAIL** for the shared wording. Companion of [`emails.md`](emails.md): same events, same words.
Depends on: [`../v2/motion.md`](../v2/motion.md) §3.1 (toasts), §5 (reduced motion); `/motion_designer` (patterns 5 toast stack,
10 success check); transitions.dev free recipes in `scratchpad/transitions/free/` (`toast.md`, `notification-badge.md`,
`success-check.md`, `banner-stacking.md`, `text-states-swap.md`) and the house copy in
`components/ui/transitions/transitions-dev.css`; existing copy `wave1.bell.*`, `quickReserve.toast.*`, `calendar.toast.*`,
`approvals.*`, `aiAdmin.banner.*`, `ops.*` in `frontend/messages/tr.json`.
Wireframe: `wireframes/messages-surfaces.svg` (bell list, toast stack, banner, empty state; 390 and 1440 in one sheet).

---

## 0. BLUF

- **Four surfaces, one rule each.** **Bell** = something happened that you did not do (decisions, bookings by others,
  alerts). **Toast** = the result of what you just did (with Geri al when reversible). **Banner** = a condition that is
  still true (limit reached, SMTP down, maintenance). **Empty state** = nothing here yet, and the one thing that fills it.
- **Same words as e-mail**: bell title = e-mail subject (emails.md §7 rule 3); bell body = the e-mail preheader; the bell
  item opens the same place as the e-mail's button.
- **Tone**: formal *siz*, no blame, one action per message, outcome first, no codes/enums, no suffix on placeholders,
  numbers and dates in the user's locale. One table of rules (§3) for everyone writing copy.
- **Motion** uses four transitions.dev free recipes, each retuned to ≤ 300 ms and without blur on glass: *toast*
  (enter 240 ms / exit 160 ms), *banner-stacking* (max 3, older tuck), *notification-badge* (dot slides 200 ms, number pops
  on `bouncySubtle`, no pop on the first page load), *success-check* (only on the quick-reserve receipt and "integration
  enabled"). The hosted Motion Agent was **not used**: no message here is a hero moment that needs it.
- **Acceptance**: MS-01…MS-16 (§9).

## 1. Which surface for which message

| Question | Bell (`inapp_notifications`) | Toast | Banner | Empty state |
|---|---|---|---|---|
| Who caused it? | someone else / the system | you, just now | nobody: a condition | — |
| Does it persist? | yes, until read (list keeps 90 days) | 5 s (8 s with an action; stays while hovered/focused) | while the condition holds | while empty |
| Action? | open the item | Geri al / Görüntüle (one) | one fix link | one CTA |
| Live region | polite "1 yeni bildirim" (count only, once per arrival burst) | polite (`role="status"`); errors assertive | `status` (info/warn), `alert` (blocking) | none |
| Also e-mailed? | per preferences | never | never (an alert e-mail may exist for admins) | never |

Never both a toast and a bell item for the same occurrence to the same person (your own withdrawal is stored as read,
T-R1-15, and shows a toast only).

## 2. References

| # | Reference | Borrow |
|---|---|---|
| M1 | Apple HIG *Notifications* and *Alerts*: concise title, specific body, no app name in the text; alerts only when essential | title + one body line; no "SmartSched:" prefix |
| M2 | Material 3 *Snackbar*: one action, short text, no icon clutter, ≤ 2 lines on phones; banners for persistent conditions | toast/banner split, one action |
| M3 | GOV.UK Design System *Notification banner* and *Error message* guidance (plain, specific, "what to do next") | banner wording "what is true + what to do" |
| M4 | transitions.dev free recipes *Toast*, *Banner stacking*, *Notification badge*, *Success check*, *Text states swap* (Transitions.dev License: use and modify in products, no redistribution of the library) | motion shapes, retuned (§6) |
| M5 | SmartSched copy already shipped (`wave1.bell.*`, `quickReserve.toast.*`, `calendar.toast.*`, `approvals.*`) | keep the shipped strings; extend, don't rename |

Mobbin was not used (not authorised for this lane).

## 3. Tone and copy rules (also binding for e-mail)

| # | Rule | Do | Don't |
|---|---|---|---|
| T1 | Formal *siz*, neutral | "Talebiniz onaylandı" | "Talebin onaylandı", "Harika!" |
| T2 | Outcome first, then the object | "Oda talebiniz reddedildi: B-204 · 21 Eki · 3. ders" | "B-204 için 21 Ekim'de yaptığınız talep hakkında" |
| T3 | No blame; describe and offer | "Bu saatte boş derslik yok. En yakın boş saatler:" | "Yanlış saat seçtiniz" |
| T4 | One action per message | "Geri al" **or** "Görüntüle" | two buttons in a toast |
| T5 | No suffix on a placeholder | "Derslik: {room}", "{room} için" | "{room}'a", "{name}'in" |
| T6 | No codes, enums or raw ids | "Seri #44 ile değiştirildi", "Onay bekliyor" | `replaced_by_series:44`, `PENDING` |
| T7 | Numbers/dates in locale | "%84", "1.284", "21 Eki 10:30" | "84%" in TR, ISO dates |
| T8 | Errors say what to do | "Kaydedilemedi. Bağlantıyı kontrol edip tekrar deneyin." | "Hata 500", "Bir şeyler ters gitti" |
| T9 | Full name for people, never gender words | "Mehmet Kaya talebinizi onayladı" | "Mehmet Bey" |
| T10 | Sentence case, no exclamation, no emoji | "Rezerve edildi" | "REZERVE EDİLDİ!" |
| T11 | Same event, same words everywhere | bell title = e-mail subject = push title | synonyms ("iptal oldu" vs "iptal edildi") |
| T12 | English mirrors meaning, British spelling | "cancelled", "organisation" | |

`{what}` (built once on the server): "{room} · {short date} · {period}" e.g. "B-204 · 21 Eki · 3. ders" (slot-display.md §5).

## 4. Bell items (per event; title = e-mail subject)

Item anatomy: leading status glyph (lucide, in the tone colour, `aria-hidden`) · **title** (one line, 14/600) · body
(≤ 2 lines, 13/400 `label-2`) · relative time ("5 dk önce") · unread dot + bold title when unread. Click/Enter opens
`notificationHref(link)` and marks read. Grouped per request (one item updated in place, not a new item per step, so
"submitted → approved" shows the latest state with "2 güncelleme").

| Event (key) | Glyph · tone | Title TR | Body TR | Title / body EN | Opens |
|---|---|---|---|---|---|
| `approval.requested` | `inbox` · warning | Onay bekleyen oda talebi: {what} | {who} onay istiyor · {repeat_short} · {conflict_short} | Room request awaiting approval: {what} / {who} asks · … | `/approvals?request=` |
| `approval.requested` (group) | same | Onay bekleyen {n} ders saati: {room} · {date_short} | {who} · tümünü birlikte karar verebilirsiniz | {n} periods awaiting approval… / you can decide them together | same |
| `approval.submitted` | `send` · info (stored as read) | Talebiniz alındı: {what} | Onay bekliyor; karar verilince haber vereceğiz. | Your request was received… / Awaiting approval; we'll let you know. | `/my-bookings?request=` |
| `approval.approved` | `check-circle-2` · feasible | Oda talebiniz onaylandı: {what} | {who} onayladı.{note} | Your room request was approved… / {who} approved it. | same |
| `approval.rejected` | `x-octagon` · infeasible | Oda talebiniz reddedildi: {what} | Gerekçe: {reason_label}. Aynı saatte boş {alt_count} derslik var. | …declined… / Reason: … {alt_count} rooms are free at the same time. | same (shows suggestions) |
| `approval.withdrawn` (approver) | `undo-2` · neutral | Oda talebi geri çekildi: {what} | {who} geri çekti; bir şey yapmanız gerekmez. | Room request withdrawn… / nothing to do. | `/approvals` |
| `approval.expired` | `clock` · neutral | Oda talebinizin süresi doldu: {what} | Başlangıçtan önce onaylanmadı. | Your room request expired… | `/reserve?…` |
| `booking.created` (by other) | `calendar-check` · feasible | Adınıza rezervasyon yapıldı: {what} | {actor} sizin adınıza ayırdı. | A booking was made for you… / {actor} booked it for you. | `/my-bookings` |
| `room_owner.booking` | `door-open` · info | Sorumlu olduğunuz dersliğe rezervasyon: {what} | {actor}{series_text} | New booking in a room you look after… | `/bookings?room=` |
| `booking.cancelled` | `calendar-x` · infeasible | Rezervasyonunuz iptal edildi: {what} | {reason_sentence} (decoded: "{actor} iptal etti. Gerekçe: …" / "Seri #{id} ile değiştirildi" / "{actor} bir işlemi geri aldı") | Your booking was cancelled… | `/find-room?…` |
| `booking.conflict_resolved` | `shuffle` · warning | Rezervasyonunuz yayınlanan programa göre değişti | {before} → {after} | Your booking changed to fit the published timetable | `/my-bookings` |
| `booking.reminder` | `bell-ring` · info | Yarın: {room} · {period_time} | {date} · {building} | Tomorrow: … | `/my-bookings` |
| `booking.series` (created) | `repeat` · feasible | Yinelenen rezervasyon: {room} · {pattern} | {count} tarih · seri #{series_id}{skipped_text} | Recurring booking… | `/my-bookings?series=` |
| `booking.series` (changed) | `repeat` · warning | Seri #{series_id} değişti: {room} | {change_short} | Series #{id} changed… | same |
| `timetable.published` | `calendar-range` · info | {term} programı yayınlandı: derslerinizde değişiklik var | {n} derste değişiklik | The {term} timetable is published… | `/timetable?mine=1` |
| `preference.accepted` / `.rejected` | check / x · tone | Ders tercihiniz kabul edildi / kabul edilmedi: {course} | ({reason}) | Your class preference was accepted / declined… | `/moderation/me` |
| `ai.usage` near (user) | `gauge` · warning | Yapay zekâ kullanım hakkınız: %{percent} kullanıldı | {reset_date} tarihinde yenilenir. | You have used {percent}% of your AI allowance / Resets on {date}. | `/profile#ai` |
| `ai.usage` threshold (admins) | `gauge` · warning | {name} yapay zekâ sınırına yaklaştı (%{percent}) | (ai-admin.md §6) | {name} reached {percent}% of their AI limit | `/admin/ai?user=` |
| `ai.usage` org | `gauge` · warning/infeasible | Kurum yapay zekâ bütçesi: %{percent} kullanıldı | {used} / {limit} token | {percent}% of the organisation's AI budget is used | `/admin/ai` |
| `ops.alert` | `siren` · infeasible/warning | [{severity_label}] {title} | {service_label} · {since} itibarıyla | [{severity}] {title} / since {since} | `/admin/ops` |
| `ops.alert` resolved | `check-circle-2` · feasible | Çözüldü: {title} | {duration} sürdü. | Resolved: {title} | `/admin/ops` |
| `integration.error` (new, admins) | `plug-zap` · infeasible | {name} bağlantısında hata | {error_short} · Sorunu gider | {name} connection failed / {error_short} | `/admin/integrations/<key>?step=` |
| `integration.secret_expiring` (new, admins) | `key-round` · warning | {name} gizli anahtarının süresi {date} tarihinde doluyor | Yeni anahtar oluşturup 3. adımda değiştirin. | {name} secret expires on {date} | same |
| `kvkk.request` new (officer) | `shield` · warning | Yeni KVKK talebi: {request_kind_label} | Son gün {due} | New KVKK request… | `/admin/kvkk` |
| `kvkk.request` (subject) | `shield` · neutral | KVKK talebiniz alındı / yanıtlandı / hakkında yanıt | Talep no #{id} · son gün {due} | We received / answered your KVKK request | `/profile#privacy` |
| `calendar.consent` (admins) | `calendar-cog` · neutral | Takvim eşitleme açıldı (KVKK onayı kaydedildi) / kapatıldı | {actor}, {when} | Calendar sync turned on / off | `/settings?tab=integrations` |

Bell panel copy (existing keys kept): header "Bildirimler", `wave1.bell.readAll` "Tümünü okundu say", `wave1.bell.empty`
→ extended empty state (§7), new item announcement `wave1.bell.newArrived` "{count} yeni bildirim". New: filter chips
"Tümü · Okunmamış · Onaylar" (`notifications.bell.filter.*`), and footer link "Bildirim tercihleri".

## 5. Toasts (results of your own action)

Pattern: motion.md §3.1 toast stack (max 3, newest on top, older tuck), one action, `role="status"` (errors `role="alert"`).
Existing keys are kept; new ones in the same namespaces.

| Action | Toast TR | EN | Action button |
|---|---|---|---|
| Direct booking (quick reserve, book sheet) | {room} rezerve edildi (`quickReserve.toast.booked`) | {room} booked | Geri al |
| Request sent | {room} için talebiniz gönderildi (`quickReserve.toast.requested`) | Your request for {room} was sent | Görüntüle |
| Withdraw own request | Talep geri çekildi. (`wave1.mine.withdrawn`) | Request withdrawn. | — |
| Cancel own booking | Rezervasyon iptal edildi: {what} | Booking cancelled: {what} | Geri al |
| Approve (approver) | Onaylandı: {what} · {who} bilgilendirildi | Approved: {what} · {who} was notified | — |
| Reject (approver) | Reddedildi: {what} · gerekçe iletildi | Declined: {what} · reason sent | — |
| Undo succeeded | Geri alındı: {label} (`calendar.toast.undone`) | Undone: {label} | Yinele |
| Copy (integrations) | in place, not a toast (integrations.md §5.2) | | |
| Integration enabled | {name} açıldı | {name} is on | — |
| Settings saved | Kaydedildi. | Saved. | — |
| Save failed | Kaydedilemedi. Bağlantıyı kontrol edip tekrar deneyin. | Couldn't save. Check your connection and try again. | Tekrar dene |
| Notification preference toggled | Bildirim tercihi kaydedildi. (`notifications.prefs.saved`) | Notification preference saved. | — |
| One-click e-mail off (landing page, not a toast) | "{event_label}" e-postaları kapatıldı. | "{event_label}" e-mails are off. | Geri al |
| SMTP test sent | Deneme iletisi gönderildi: {to} | Test message sent to {to} | — |
| Stale/conflict on save | Bu kayıt siz düzenlerken değişti. Yenileyip tekrar deneyin. | This record changed while you were editing. Refresh and try again. | Yenile |

Durations: 5 s plain, 8 s with an action, infinite for errors with "Tekrar dene" until dismissed; timers pause on hover,
focus and when the tab is hidden. Phones: toasts sit above the tab bar (safe area + 8 px), swipe down or sideways to
dismiss, max 2 visible.

## 6. Banners (conditions)

`Alert` component, full width at the top of the affected surface (not global unless the condition is global). Tone +
icon + one sentence + one action. Several banners stack (newest first, max 3 visible, "+{n} uyarı" link).

| Condition | Where | Tone · role | TR | EN | Action |
|---|---|---|---|---|---|
| SMTP not configured / failing (admins) | `/admin/*`, Bildirimler | warning / danger · status | E-posta gönderilemiyor: {error_short}. {n} bildirim bekliyor. | E-mail can't be sent: {error_short}. {n} notifications are waiting. | Sorunu gider |
| User has no e-mail address | Profil › Bildirimler | info | Hesabınızda e-posta adresi yok; bildirimler yalnız uygulamada görünür. (`notifications.prefs.noEmail` extended) | Your account has no e-mail address; notifications appear in the app only. | — |
| IdP unreachable (sign-in page) | `/login` | warning · status | {provider} şu anda yanıt vermiyor. Birkaç dakika sonra tekrar deneyin. | {provider} isn't responding… | — |
| Break-glass missing (admins) | Kullanıcılar, Entegrasyonlar › Kimlik | warning | Acil durum hesabı yok. Kimlik sağlayıcısına ulaşılamazsa kimse giriş yapamaz. (`sso.users.breakGlass*`) | No break-glass account… | Yerel yönetici oluştur |
| Secret expires ≤ 30 days | Entegrasyonlar | warning | {name} gizli anahtarının süresi {date} tarihinde doluyor. | {name} secret expires on {date}. | Anahtarı değiştir |
| AI near / at limit | chat, NL rules, intake | warning · status / danger · alert | `aiAdmin.banner.near` / `.at` | | Yöneticiye bildir (at) |
| Maintenance (bookings paused) | booking surfaces | warning · status | `signin.notice.maintenanceTitle` + message | | — |
| Calendar sync off by admin | Profil › Bağlı takvimler | info | Kurum takvim eşitlemeyi kapattı; bağlı takvimlere aktarım durdu. | The organisation turned calendar sync off; copying stopped. | — |
| Request pending (requester's booking view) | My bookings row | info (inline, not a page banner) | Onay bekliyor · {n} gündür | Awaiting approval · {n} days | Geri çek |

## 7. Empty states

`EmptyState`: one sentence that says what will appear here, one CTA (or none if the user can't act). No illustrations.

| Surface | TR | EN | CTA |
|---|---|---|---|
| Bell (none at all) | Henüz bildirim yok. Talepleriniz ve rezervasyonlarınızla ilgili gelişmeler burada görünür. | No notifications yet. Updates about your requests and bookings appear here. | Bildirim tercihleri |
| Bell (filter "Okunmamış") | Okunmamış bildirim yok. | No unread notifications. | Tümünü göster |
| Approvals queue (open) | Sizi bekleyen talep yok. (`wave1.approvals.emptyOpen`) | Nothing is waiting for you. | — |
| My bookings | Henüz rezervasyonunuz yok. | You have no bookings yet. | Rezerve et |
| Integrations, search | "{q}" ile eşleşen entegrasyon yok. | No integration matches "{q}". | Aramayı temizle |
| Integrations, area with nothing configured | Bu alanda henüz bağlantı yok. | Nothing is connected in this area yet. | the first card's Kur |
| E-mail outbox | Gönderilmiş e-posta yok. E-posta ayarlandığında bildirimler burada listelenir. | No e-mails sent. When e-mail is set up, notifications are listed here. | E-postayı kur (admins) |
| KVKK requests | `kvkk.dsr.empty.*` (kept) | | — |

## 8. Motion (transitions.dev free recipes, retuned; rows for `v2/motion.md` §3.1 / new §3.19 Messages)

Purpose sentences: toast = "your action worked (or didn't), and you can undo"; badge = "something new arrived for you";
success check = "this important thing is done"; banner stack = "these conditions are true, newest first".

| Moment | Recipe (M4) | Retune for SmartSched | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| Toast enter / exit | *toast* (`translateY 16px`, scale .97, 2 px blur; 350 / 250 ms) | **drop the blur** (toasts are glass: no `filter` on a `backdrop-filter` element, motion.md §2); enter 240 ms y 16 → 0, scale .97 → 1 on `--spring-smooth`; exit 160 ms `--ease-in` opacity + y 8 | `smooth`, `--dur-fast` | 100 ms fade, no travel | `--mat-thick-solid` |
| Toast stacking (2–3) | *banner-stacking* (depth scale .06, fade .4, peek 12 px; 350 / 250 ms) | depth scale .05, opacity .85 / .7 (not .4: text behind must stay legible when fanned), peek 10 px, open 240 ms, the 4th leaves in 160 ms; hover/focus fans out (spread gap 8 px) | `smooth` | no tuck: plain list, 100 ms fades | solid |
| Banner stack (page banners) | *banner-stacking* principles, **no overlap**: banners are full-width blocks in the flow | new banner: height via `layout` FLIP + opacity 180 ms; removal 120 ms then siblings close the gap | `smooth` | instant | solid |
| Bell badge appears / count changes | *notification-badge* (slide −8/12 px 260 ms, pop 500 ms overshoot 1.36) | slide 200 ms `--ease-out`; number change pops scale .8 → 1 on `bouncySubtle` (≤ 285 ms, 2.4 %); **no animation on page load or when the count goes down**; the bell itself never moves | `bouncySubtle` | number swaps, no slide/pop | n/a |
| New bell item while the panel is open | list insert | item inserted at top with `layout` + 180 ms fade; no stagger | `smooth` | instant | solid |
| Success check | *success-check* (fade, rotate 80°, 40 px bob, 10 px blur, path draw; 500 ms) | only on (a) quick-reserve receipt, (b) "integration enabled"; **no rotate, no bob, no blur**; path draw 220 ms + scale .9 → 1 | `bouncySubtle` | final frame | n/a |
| Copy → Copied, "Kaydediliyor… → Kaydedildi" | *text-states-swap* | out 120 / in 180 ms, y ±4 px, no blur | `--dur-fast/base` | instant swap | n/a |
| Mark all read | — | unread dots fade 120 ms together (no per-row stagger) | `--dur-fast` | instant | n/a |

Hosted Motion Agent: **not used** (budget 1–2 per agent; none of these moments is a hero, and all four recipes fit the
existing tokens after retuning). If CSS is pasted from the recipes, keep the `/* Transitions.dev — <name> */` headers in
`components/ui/transitions/transitions-dev.css` and note the retune there, as the existing header does.

## 8a. Accessibility

- Bell button name includes the count ("Bildirimler, 3 okunmamış"); arrivals announced once per burst
  (`wave1.bell.newArrived`), never per item.
- Toasts: `role="status"`; errors `role="alert"`; focusable with F8 (or the documented shortcut) and the action reachable by
  keyboard; never the only record of something important (decisions are in the bell and the list).
- Banners: not dismissible when the condition blocks work (AI limit, maintenance); dismissible for the session otherwise.
- Status glyphs are decorative; the title carries the meaning; tone is never colour-only.
- Toast timers pause on hover and focus (WCAG 2.2.1); phones get swipe plus a visible close button (44 px).

## 8b. Mobile layout

- Bell opens a full-height sheet (detent large) with the filter chips sticky at the top and 64 px rows; tap = open + mark
  read; swipe-left "Okundu".
- Toasts bottom-centre above the tab bar, width = viewport − 32 px, max 2.
- Banners full width under the page title, text wraps, action as a text link on the next line.

## 9. Acceptance checks

| Id | Check | Pass when |
|---|---|---|
| MS-01 | Same words | for every event in §4 the bell title equals the e-mail subject (snapshot of both in TR and EN) |
| MS-02 | No double notice | own withdrawal / own cancellation: toast only, no unread bell item, no e-mail |
| MS-03 | Grouping | a request that goes submitted → approved shows one bell item with the latest state |
| MS-04 | Decoded reasons | cancelled items never show `replaced_by_series:` or `undo_of:` |
| MS-05 | Suffix rule | grep the TR catalogue: no placeholder followed by an apostrophe suffix (regex `\}'[a-zçğıöşü]`) |
| MS-06 | One action | no toast or banner renders more than one action button |
| MS-07 | Toast timing | 5 s / 8 s with action; paused on hover and focus |
| MS-08 | Toast motion | `document.getAnimations()` durations ≤ 300 ms; no `filter` animation on a toast |
| MS-09 | Reduced motion | toast, badge, check end on the next frame or ≤ 100 ms fade |
| MS-10 | Badge | no pop on first load; pops once when the count rises; bell icon transform unchanged |
| MS-11 | Live regions | one announcement per arrival burst; toasts announced; errors assertive |
| MS-12 | Banners | SMTP failing shows the admin banner with "Sorunu gider" deep-linking to the failing step |
| MS-13 | Empty states | bell, approvals, my bookings, integrations search show §7 copy with one CTA |
| MS-14 | Phone | toasts above the tab bar and safe area, swipe and close button both work |
| MS-15 | Language | EN user sees EN titles from the server (bell rows are stored in the recipient's language) |
| MS-16 | Contrast | glyph + text pairs meet tokens.md §A in light and dark |
