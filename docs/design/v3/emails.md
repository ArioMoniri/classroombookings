# Themed e-mails: one layout, every message (TR + EN)

Owner: product designer (wave3b-des2-2026-10-17) · Status: v3.0 spec (2026-10-17) · Builder: lane **W3-MAIL**
(`backend/app/emails/**` templates + renderer, `services/bookings_notify.py` rendering path, `services/bookings_i18n.py`
strings, `components/admin/email/**`); senders in other lanes: W3-IDP (invitation, account created), W3-SEC (new device),
W3-AI (AI usage), W3-OPS (ops alert).
Depends on: [`../brand.md`](../brand.md) §4 (brand colours, tile), [`../tokens.md`](../tokens.md) §A, [`../v2/liquid-glass.md`](../v2/liquid-glass.md)
§5 (labels, status colours), [`slot-display.md`](slot-display.md) §5 (one period label rule), [`ai-admin.md`](ai-admin.md) §6
(usage wording), [`ops-panel.md`](ops-panel.md) (alert wording), `app/services/approvals.py` `TEXTS` / `REASON_CODES`,
`app/services/notify_dispatch.py` `EVENTS`, `app/emails/kinds.py` (W3-MAIL's kind catalogue, read 2026-10-17 20:10).
Companion specs: [`messages.md`](messages.md) (in-app counterpart, same wording), [`integrations.md`](integrations.md) (SMTP wizard).
Mock-ups (light + dark side by side in each file, rendered and checked in Chromium):
`wireframes/email-{reset,invite,approved,rejected,approver-request}-{desktop,phone}.svg`; generator
`wireframes/src/em.py` (`python3 -I em.py ..` from inside `wireframes/src`).

Owner's words (2026-10-17): "Designers design the password-reset, invite, reservation accept/decline and all other
notification e-mails and messages, following the theme."

---

## 0. BLUF

- **One layout for every message**: 600 px card on a scene-grey canvas; header = SmartSched tile (image) + "SmartSched"
  (live text) + the organisation name; hidden preheader; optional status pill; heading; one or two short paragraphs;
  optional **details card** (room · date · period · request no.), reason callout, code block or suggestion rows; **one
  primary button** (bulletproof, 48 px); at most one secondary link; footer with organisation, *why you got this*,
  preference link and KVKK link. Phones (≤ 480 px): edge-to-edge card, 20 px padding, full-width button, details stack
  label-over-value.
- **Colours are the app's own** (brand blue `#0A63D1` / dark `#4DA0FF`, labels from liquid-glass §5.1, status tints from
  §5.3 made opaque). Every text pair is ≥ 5.5:1 in light and ≥ 6.5:1 in dark (§3.2). Dark mode is served to the clients
  that honour `prefers-color-scheme` (Apple Mail, Outlook for Mac, new Outlook / Outlook.com via `[data-ogsc]`) and the
  light design is built to survive forced inversion in Gmail and Outlook apps (§3.3).
- **Copy rules**: formal *siz*, the recipient's full name ("Merhaba Ayşe Yılmaz,"), no suffix on a placeholder, no raw
  codes or enums, subject = the in-app bell title, front-loaded and ≤ 60 characters, one action per message, never blame.
- **Security rules**: no approve/reject links in e-mail (a decision is made in the app; link scanners follow GET links),
  codes and links expire and say when, security mails cannot be switched off and say so, no passwords ever.
- **Every message** has TR + EN subject, preheader, heading, intro, button and note (§8): 26 kinds and their variants,
  mapped 1:1 to `app/emails/kinds.py` keys `<kind>.subject|preheader|heading|intro|cta|note` and `<kind>.<field>.<value>`.
- **Acceptance**: EM-01…EM-20 (§12): render matrix light/dark/images-off/text-only, 102 KB clip limit, contrast, links,
  plain-text twin, headers.

## 1. Recipients and what they need from an e-mail

| Recipient | Typical e-mail | What they need in 3 seconds | Opens on |
|---|---|---|---|
| Academician / staff who books | approved, rejected, cancelled, reminder | outcome word, room, date, period; what to do next | phone (most), Outlook desktop |
| Approver (department secretary, facilities) | new request, withdrawn | who, which room, when, how many weeks, any conflict; one button to the queue | Outlook desktop, phone |
| New user | invitation, account created | who invited me, which account to use (Microsoft / Google / local), until when | phone, then desktop |
| Anyone | password reset, new device | is this me; the code; how long it is valid; what if it was not me | phone |
| Admin / KVKK officer / IT | calendar consent, KVKK request, AI budget, ops alert | what happened, since when, where to act | desktop |

Market reality that shapes the design (Litmus, July 2026 client share): Apple Mail and Gmail together are ~90 % of opens;
Outlook ~6 %, but in a Turkish university the staff mailbox is very often Exchange/Outlook, so classic Outlook for
Windows (Word engine, no dark mode controls, no border-radius) is a first-class target, and Yandex Mail and the Turkish
operators' webmail are tested too (§11).

## 2. References (public, checked 2026-10-17)

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| R1 | Litmus, *Email client market share* (July 2026, >1 bn opens) ([litmus.com](https://www.litmus.com/email-client-market-share)); Courier summary of the same report ([courier.com](https://www.courier.com/blog/dark-mode-email-design)) | design for Apple Mail + Gmail first, test classic Outlook explicitly; >25 % read in dark mode | trusting one client's preview as "the" rendering |
| R2 | Litmus, *Ultimate guide to dark mode* ([litmus.com](https://www.litmus.com/blog/optimize-imagery-for-dark-mode)); Email on Acid dark-mode notes ([emailonacid.com](https://www.emailonacid.com/?p=12356)); Can I Email data via Buttondown ([buttondown.com](https://buttondown.com/blog/dark-mode-emails)) and dev.to summary ([dev.to](https://dev.to/pkrupar/dark-mode-in-html-email-everything-you-need-to-know-3k29)) | three dark-mode behaviours (no change / partial invert / full invert); `color-scheme` meta + `prefers-color-scheme` for Apple Mail and Outlook Mac; `[data-ogsc]`/`[data-ogsb]` for Outlook.com; Gmail supports none and inverts on its own | text in images; transparent logos with dark ink; pure `#000`/`#FFF` pairs that invert into glare |
| R3 | Litmus, *Guide to bulletproof buttons* ([litmus.com](https://www.litmus.com/blog/a-guide-to-bulletproof-buttons-in-email-design)); Microsoft Q&A on Outlook web stripping anchor padding ([learn.microsoft.com](https://learn.microsoft.com/en-us/answers/a/12348625)) | padding + border on a `<td>` with `bgcolor` (the whole cell is the colour), VML `roundrect` inside `<!--[if mso]>` for classic Outlook; never an image button | padding only on the `<a>` (Outlook web drops it) |
| R4 | Postmark, *Password reset e-mail best practices* ([postmarkapp.com](https://postmarkapp.com/guides/password-reset-email-best-practices)) and the open-source Postmark templates (MIT; layouts *Basic*, *Basic full*, *Plain*; reset, invitation, welcome) ([github.com/ActiveCampaign/postmark-templates](https://github.com/ActiveCampaign/postmark-templates)) | reset checklist: clear sender, which account, one action, expiry, "not you?" reassurance, support route; the "Plain" layout as our text twin | marketing-style hero images in utility mail |
| R5 | Litmus, *5 of the best password reset e-mails* (Jet, from Really Good Emails) ([litmus.com](https://www.litmus.com/blog/the-power-of-simplicity-5-of-the-best-password-reset-emails)); Mailosaur on the same ([mailosaur.com](https://mailosaur.com/blog/what-goes-into-a-great-password-reset-email)); Really Good Emails, *Password reset* and *Invite* categories ([reallygoodemails.com](https://reallygoodemails.com/)) | white space around one button; a confirmation after the change (our optional `password_changed`) | illustration-heavy headers |
| R6 | Google / Yahoo sender requirements (Feb 2024, one-click unsubscribe June 2024) and Microsoft Outlook.com requirements (May 2025): SPF, DKIM, DMARC alignment, RFC 8058 `List-Unsubscribe-Post` for bulk ([resend.com](https://www.resend.com/blog/microsoft-bulk-sending-requirements-2025), [valimail.com](https://valimail.com/blog/one-click-unsubscribe), [inboxally docs](https://docs.inboxally.com/support/microsoft-outlook-changes-for-bulk-senders-in-2025)) | real From/Reply-To; one-click "turn this event off" header on switchable notifications; authentication checked by the SMTP wizard ([integrations.md](integrations.md) §7) | `noreply@` with a dead mailbox |
| R7 | Apple Human Interface Guidelines (typography, dark mode) and Apple Mail's support of `color-scheme`; Microsoft *Fluent* e-mail guidance on Outlook (Segoe UI, 16 px body); Google Material e-mail patterns in Gmail transactional mails | system font stacks, 16 px body, 44–48 px targets, sentence case | custom web fonts (only Apple Mail loads them) |
| R8 | SmartSched: `approvals.TEXTS`, `REASON_CODES`, `bookings_i18n.BASE_STRINGS` (decoded cancel reasons), `notify_dispatch.EVENTS`, `signin.*` and `sso.*` copy in `frontend/messages/tr.json`, `app/emails/kinds.py` | the same words the app already uses ("Oda talebiniz onaylandı", "Gerekçe", "Microsoft iş veya okul hesabı") | new synonyms for the same thing |

Licences: everything above is used as a pattern reference only. No template code is copied. The Postmark templates
(MIT) are the closest structural relative; if W3-MAIL lifts any markup from them, keep the MIT notice in
`backend/app/emails/LICENSES/postmark-templates-MIT.txt`. Images: the SmartSched tile (`docs/images/brand/png/smartsched-tile-512.png`,
in-house).

## 3. Tokens

### 3.1 Colour (opaque only: e-mail clients do not composite alpha reliably)

| Token (`--em-*`, also the class names in the dark-mode block) | Light | Dark | Source |
|---|---|---|---|
| `canvas` (outer background) | `#EEF0F4` | `#0D0E12` | liquid-glass §3 scene |
| `card` | `#FFFFFF` | `#1B1C21` | chrome dark |
| `text-1` heading, values, body | `#1D1D1F` | `#F5F5F7` | `--label-1` |
| `text-2` secondary paragraphs | `#4B4B51` | `#B6B6BD` | `--label-2` |
| `text-3` labels, footer | `#5F5F66` | `#A9A9B1` | `--label-3`, darkened 1 step for small text on `detail` |
| `line` hairline, card edge | `#D9DCE3` | `#33343B` | decorative only |
| `button` / `button-text` | `#0A63D1` / `#FFFFFF` | `#4DA0FF` / `#06101F` | brand blue = accent (brand.md §4) |
| `link` | `#0957BB` | `#6CB0FF` | `--accent-text` |
| `detail` (details card, code block) | `#F5F7FA` | `#24252B` | |
| `ok` fg / bg | `#0F6430` / `#E6F5EA` | `#63E08B` / `#11291A` | feasible §5.3, opaque |
| `bad` fg / bg | `#A3211A` / `#FCEBEA` | `#FF9D95` / `#351614` | infeasible |
| `warn` fg / bg | `#7C4800` / `#FFF2D9` | `#FFCC66` / `#33270C` | warning |
| `info` fg / bg | `#0957BB` / `#E8F1FC` | `#6CB0FF` / `#122238` | accent |
| tile | `#0A63D1` + white glyph | same | brand.md `--brand-tile` (identical in both themes, like an app icon) |

The accent preset (`data-accent`) is **not** applied to e-mail: mail always uses the brand blue, like the logo.

### 3.2 Verified contrast (WCAG 2.x, computed with `scratchpad/des2/contrast.py`, 2026-10-17)

| Pair | Light | Dark | Needs |
|---|---|---|---|
| text-1 on card / detail / canvas | 16.83 / 15.68 / 14.75 | 15.62 / 14.03 / 17.72 | 4.5 |
| text-2 on card / detail | 8.66 / 8.07 | 8.44 / 7.58 | 4.5 |
| text-3 on card / detail / canvas | 6.33 / 5.90 / 5.55 | 7.29 / 6.55 / 8.26 | 4.5 |
| link on card / detail | 6.79 / 6.33 | 7.53 / 6.76 | 4.5 |
| button-text on button | 5.65 | 7.07 | 4.5 |
| button against card (non-text, 1.4.11) | 5.65 | 6.31 | 3 |
| ok / bad / warn / info fg on own bg | 6.45 / 6.53 / 6.81 / 5.96 | 9.27 / 8.23 / 9.80 / 7.08 | 4.5 |
| ok / bad / warn / info fg on card | 7.28 / 7.53 / 7.54 / 6.79 | 10.18 / 8.51 / 11.40 / 7.53 | 4.5 |
| light button on a Gmail-inverted dark card | 3.01 (white label on it stays 5.65) | — | 3 (shape) |
| line vs card | 1.37 | 1.37 | decorative; never the only boundary of a control |

Status is **never colour-only**: every status pill has its word ("Onaylandı", "Reddedildi", "Onay bekliyor", "İptal
edildi"), and the callout has a bold label ("Gerekçe: …").

### 3.3 Dark-mode strategy per client

| Client behaviour (R2) | Clients | What we do |
|---|---|---|
| Honours `prefers-color-scheme` | Apple Mail macOS/iOS/iPadOS, Outlook for Mac, Outlook iOS (partly), Thunderbird | `<meta name="color-scheme" content="light dark">`, `<meta name="supported-color-schemes" content="light dark">`, `:root{color-scheme:light dark}` and a `@media (prefers-color-scheme: dark)` block that swaps the §3.1 tokens by class (`.em-card`, `.em-t1` …, all `!important`) |
| Partial inversion (backgrounds only) | Outlook.com / new Outlook for Windows, Outlook Android | the same swaps under `[data-ogsc] .em-…` (text) and `[data-ogsb] .em-…` (backgrounds) |
| Full inversion, no control | Gmail iOS/Android, classic Outlook for Windows (dark theme) | the light design is inversion-safe: no text in images; the only image is the tile, which has its own opaque blue background; the university logo sits in an opaque white chip with 8 px padding; no background images; button colour mid-luminance so inversion keeps it blue |
| No dark mode | Gmail web, Yandex Mail web, classic Outlook (light) | light design |

### 3.4 Type (system stacks; no web fonts)

`font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` (Segoe UI
in Outlook, SF in Apple Mail, Roboto in Gmail Android). Monospace for codes: `ui-monospace, SFMono-Regular, Menlo,
Consolas, "Liberation Mono", monospace`. All sizes in px (Outlook ignores rem).

| Role | Desktop size / line / weight | Phone (≤ 480) | Colour |
|---|---|---|---|
| Heading (`<h1>`) | 24 / 32 / 600 | 22 / 30 / 600 | text-1 |
| Body (intro, paragraphs) | 16 / 24 / 400 | 16 / 24 | text-1 |
| Secondary paragraph (fallback, notes) | 14 / 21 / 400 | 14 / 21 | text-2 |
| Details label | 14 / 24 / 500 | 13 / 18 / 500 (above the value) | text-3 |
| Details value | 16 / 24 / 600 | 16 / 22 / 600 | text-1 |
| Status pill | 13 / 18 / 600 | same | tone fg on tone bg |
| Button label | 16 / 20 / 600 | same | button-text |
| Secondary link | 15 / 24 / 600, underlined on hover only where supported; always underlined in the plain fallback URL | same | link |
| Code | 26 / 32 / 600, letter-spacing 3 px, grouped in 4s with a hyphen | 24 / 30 | text-1 on detail |
| Footer | 13 / 20 / 400 (organisation line 600) | same | text-3 (org line text-2) |

Never `text-transform: uppercase` (Turkish dotted/dotless i breaks in clients that ignore `lang`), no letter-spaced
caps labels, no italics for meaning, left-aligned text (never centred paragraphs), max line ~70 characters (600 − 2×40 px).

### 3.5 Spacing, shape, size

| Token | Value |
|---|---|
| Card width | 600 px max (`width:100%; max-width:600px`), centred on the canvas, 24 px canvas padding above/below (desktop) |
| Card padding | 40 px desktop, 20 px phone |
| Card radius | 16 px desktop (ignored by classic Outlook: square, fine), 0 on phones (edge-to-edge) |
| Vertical rhythm | header 68 px; 24 px between blocks; 18 px heading top; 8 px heading→intro; 32 px before footer |
| Details card | radius 12, 1 px `line` border, 14 px inner top/bottom, 16 px inner left (after the 4 px tone bar), rows 24 px |
| Button | height 48, padding 14 × 28, min-width 184 (desktop), 100 % on phones, radius 12 (VML arcsize 25 %) |
| Tile | 28 × 28 (served as 56 × 56 PNG for 2× screens), `alt="SmartSched"` |
| University logo | max 32 px tall, max 160 px wide, inside a white chip (8 px padding, radius 8) |
| Total HTML size | < 90 KB per message (Gmail clips at 102 KB, which hides the footer and the unsubscribe) |

Motion: none. E-mail is static; no GIFs, no CSS animation (motion spec does not apply; `/motion_designer` rule
"results arrive, nothing performs").

## 4. Layout anatomy

```
<html lang="tr" dir="ltr">                                          (lang = recipient's language)
 head: charset, viewport, color-scheme metas, <title>{subject}</title>, <style> (dark + phone media queries only)
 body (canvas)
 ├─ preheader: hidden <div> with {preheader} + &#8199;&#65279;&#847; filler × ~90 (stops body text leaking into the preview)
 └─ <table role="presentation" width="100%"> → <table class="em-card" width="600">   aria-label = subject on the wrapper
    ├─ HEADER   [tile 28] SmartSched (live text, 16/600)          {org} or the university logo chip (right)
    │           1 px line under
    ├─ STATUS   optional pill: word + tone (only booking/approval kinds)
    ├─ HEADING  <h1> one sentence
    ├─ INTRO    1–2 paragraphs, ≤ 45 words total
    ├─ BLOCK    one of: details card · reason callout + details · code block · suggestion rows · KPI line (AI, ops)
    ├─ BUTTON   one primary (bulletproof)
    ├─ AFTER    optional: secondary link (one) · fallback URL (reset/invite only) · note (14/21, text-2)
    └─ FOOTER   line · "{org} · SmartSched" · why-you-got-this · [Bildirim tercihleri] · [KVKK Aydınlatma Metni]
```

Phone (≤ 480 px, `@media (max-width:480px)`): canvas padding 0, card radius 0 and full width, padding 20, heading 22/30,
details rows stack (label above value; `display:block` on the two `<td>`s), button `width:100%` (`display:block` on the
`<a>`, VML width ignored on phones since classic Outlook is desktop only), suggestion rows put "Bu dersliği iste" under
the room. Gmail apps that strip `<style>` still get a usable layout because the base table is fluid (`width:100%`,
`max-width:600px`) and every block is one column.

Images off: header still reads "SmartSched · {org}" (live text); nothing else is an image. Text-only (plain-text part,
§5.9): same content in the same order.

## 5. Components

### 5.1 Header
Left: tile image (`{public_url}/email/tile-56.png`, absolute https URL; `width=28 height=28`, `alt="SmartSched"`,
`style="display:block;border:0"`) + 10 px + "SmartSched" live text (16/600, text-1). Right: `{org}` (13/500, text-3), or the
university logo chip when `org.logo_url` is set (logo `alt="{org}"`). Brand rule: the mark is the tile (works on any
background, brand.md §7.2), the wordmark is never an image of text; the university logo never replaces the SmartSched
mark and vice versa (brand.md §7.3).

### 5.2 Preheader
40–110 characters, never repeats the subject, carries the second most useful fact (expiry, reason, "8 hafta · çakışma
yok"). Hidden with `display:none; max-height:0; overflow:hidden; mso-hide:all` + filler.

### 5.3 Status pill (booking and approval kinds only)
Rounded 13 px pill, tone bg + tone fg + the word. Words: Onaylandı / Approved (ok), Reddedildi / Declined (bad), Onay
bekliyor / Awaiting approval (warn), İptal edildi / Cancelled (bad), Geri çekildi / Withdrawn and Süresi doldu / Expired
(neutral = text-2 on detail), Alındı / Received (info).

### 5.4 Details card
`<table role="presentation">` with one `<tr>` per row; label column 154 px desktop. The 4 px left bar uses the status tone
(none for neutral). Canonical booking rows, in this order, only those that apply:

| Row (TR / EN) | Value format | Source |
|---|---|---|
| Talep eden / Requested by | "Ayşe Yılmaz · Bilgisayar Mühendisliği" | approver mails only |
| Derslik / Room | "B-204 · 40 kişi" (name · capacity) | room |
| Tarih / Date | org long pattern: "21 Ekim 2026 Çarşamba" / "Wednesday, 21 October 2026" | `bookings_i18n.Formatter.long` |
| Ders saati / Period | slotLabel inline form: "3. ders · 10:30–11:20"; spans "3.–4. ders · 10:30–12:20" | slot-display.md §5 (server twin) |
| Tekrar / Repeats | "Her çarşamba · 8 hafta (seri #44)" | series |
| Tarihler / Dates | ≤ 5 dates listed, then "+9 tarih daha" with the button to see all | multi-date |
| Not / Note | the requester's note as typed, ≤ 200 characters, then "…" | request |
| Çakışma / Conflict | "Yok" / "Aynı saat için 1 başka talep var" | approver mails |
| Talep no / Request no | "#128" | request id |
| Karar veren / Decided by | "Mehmet Kaya" | decisions |

### 5.5 Reason callout
Tone bg + 4 px tone bar + bold label "Gerekçe: {reason label}" + the free text on the next line. Decoded, never a code
(`approvals.reason_text`, `bookings_i18n.cancel_reason`).

### 5.6 Code block
Only for `password_reset`. `detail` background, 56 px tall, monospace 26 px, grouped "K7Q4-M2X9" (the API accepts it with
or without the hyphen and in any case). Label above: "Sıfırlama kodu" / "Reset code". Selectable text (no image).

### 5.7 Primary button (bulletproof, R3)

One per message, label = verb + object, ≤ 24 characters ("Talebi incele", "Daveti kabul et"). Markup (load-bearing):

```html
<table role="presentation" border="0" cellspacing="0" cellpadding="0" class="em-btn-wrap">
  <tr>
    <td align="center" bgcolor="#0A63D1" class="em-btn" style="border-radius:12px;background:#0A63D1;">
      <!--[if mso]>
      <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
        href="{url}" style="height:48px;v-text-anchor:middle;width:{vml_width}px;" arcsize="25%" stroke="f" fillcolor="#0A63D1">
        <w:anchorlock/>
        <center style="color:#FFFFFF;font-family:'Segoe UI',Arial,sans-serif;font-size:16px;font-weight:600;">{label}</center>
      </v:roundrect>
      <![endif]-->
      <!--[if !mso]><!-->
      <a href="{url}" class="em-btn-a" target="_blank"
        style="display:inline-block;padding:14px 28px;min-width:184px;border:1px solid #0A63D1;border-radius:12px;
               font:600 16px/20px -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
               color:#FFFFFF;text-decoration:none;text-align:center;mso-hide:all;">{label}</a>
      <!--<![endif]-->
    </td>
  </tr>
</table>
```

`{vml_width}` = max(240, 9.5 × len(label) + 56). Dark: `.em-btn{background:#4DA0FF!important}`, `.em-btn-a{color:#06101F!important;
border-color:#4DA0FF!important}`. Phone: `.em-btn-wrap,.em-btn-a{width:100%!important;display:block!important}`.
Links carry no tracking parameters and no click-tracking redirect (KVKK; also keeps Outlook Safe Links previews honest).

### 5.8 Secondary link, fallback URL, note
- **Secondary link**: one, 15/600 link colour, e.g. "Takvime ekle (.ics)", "Onay kuyruğu: 3 talep bekliyor".
- **Fallback URL** (`layout.button_fallback`): only reset and invitation, below the button: "Düğme çalışmıyorsa bu adresi
  tarayıcınıza yapıştırın:" + the URL as text (wrapped with `word-break:break-all`).
- **Note** (`<kind>.note`): the reassurance or the consequence, 14/21 text-2, or as an `info` callout for security mails.

### 5.9 Footer
1. `{org} · SmartSched` (13/600 text-2).
2. Why (`<kind>.why` or `layout.footer.reason`): "Bu e-postayı, {event_label} bildirimi açık olduğu için aldınız." For
   security/legal kinds: "Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz." / "Bu e-posta yasal bir
   bildirimdir (KVKK); kapatılamaz."
3. Links: "Bildirim tercihleri" → `{public_url}/profile?tab=notifications` (omitted on non-switchable kinds) · "KVKK
   Aydınlatma Metni" → the org's notice URL.
4. "Bu ileti otomatik gönderildi; yanıtlar {reply_to} adresine gider." only when a Reply-To is configured, otherwise
   "Bu ileti otomatik gönderildi; yanıtlanmaz."

### 5.10 Plain-text twin (multipart/alternative)
Same order: heading, blank line, intro, details as `Etiket: değer` lines, reason, the button as `{label}: {url}`, note,
`--`, footer lines. ≤ 78 characters per line, no Markdown symbols. This is also what the outbox screen shows.

## 6. Headers and delivery rules (for the renderer)

| Header / rule | Value |
|---|---|
| From | `"{from_name}" <{from_address}>`; recommended `from_name` = "{org kısa adı} SmartSched" (the SMTP wizard proposes it) |
| Reply-To | org's support address if set (never a dead `noreply@`, R6) |
| Subject | §7 rules; no "SmartSched:" prefix (the sender name already says it) |
| Message-ID / threading | `References` + `In-Reply-To` = `<request-{id}@{host}>` for every mail about the same request (submitted → requested → approved/rejected → cancelled), `<series-{id}@{host}>` for series, so Gmail/Outlook thread them; security mails never thread |
| `Auto-Submitted: auto-generated`, `X-Auto-Response-Suppress: All` | every message (stops out-of-office loops) |
| `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058) | switchable kinds only; the URL is a signed token that turns **this event** off on the e-mail channel for this user and shows a confirmation page with "Geri al"; not on security, legal or admin-alert kinds |
| Language | recipient's profile language → org default → `tr`; dates/times with the org's patterns in that language |
| Time zone | the organisation's time zone; times never carry an offset in the body; `.ics` carries `TZID` |
| `.ics` | not attached (Outlook auto-adds attachments as events); "Takvime ekle (.ics)" link to a signed one-event download |
| Public URL | required for every link-bearing kind. Without `public_url` the kind is rendered **without links** and the outbox row notes "Genel adres ayarlı değil" (the SMTP wizard blocks enabling without it) |
| Size | < 90 KB HTML; images hosted; CSS inlined, except the `<style>` block for dark + phone |

## 7. Copy rules (TR first; also in messages.md §3)

1. **Siz, never sen.** Neutral-formal: "Talebiniz onaylandı", "Parolanızı sıfırlayın". Address with the full name
   ("Merhaba Ayşe Yılmaz,"): no Hanım/Bey (gender is unknown), no first-name-only familiarity.
2. **No suffix on a placeholder.** `{room}` never gets `'e`/`'de` (vowel harmony unknown). Write "Derslik: {room}",
   "{room} için", "{inviter}, sizi … davet etti". Fixed words may take suffixes ("SmartSched'e").
3. **Subject = the bell title** for the same event (messages.md §4), front-loaded (outcome first), ≤ 60 characters
   with `{what}`; `{what}` = "{room} · {short date} · {period}" ("B-204 · 21 Eki · 3. ders").
4. **One action.** One button; at most one secondary link; no "or you can also…".
5. **No blame.** Describe what happened and what is possible: "Kod 24 saat geçerlidir", not "Kodunuz geçersiz çünkü geç
   kaldınız". Rejections give the reason and the next room, not a lecture.
6. **No codes, no enums, no IDs alone.** "Seri #44 ile değiştirildi", never `replaced_by_series:44`; a request number is
   shown with its label ("Talep no #128").
7. **Numbers and dates** with `tr-TR` / `en-GB` formats ("%84", "1.284", "21 Ekim 2026 Çarşamba").
8. **Security sentence last**, calm: "Bu isteği siz yapmadıysanız bir şey yapmanız gerekmez; parolanız değişmez."
9. English mirrors the Turkish meaning, British spelling ("cancelled", "organisation"), sentence case.

## 8. Message catalogue

Legend: **S** subject · **P** preheader · **H** heading · **I** intro · **B** button (cta) → link · **N** note / secondary.
Switchable = the user can turn the e-mail off in Bildirimler (event in `notify_dispatch.EVENTS`); default = e-mail on for a
new user. Keys: `<kind>.<part>` in set `email`; variants `<kind>.<field>.<value>.<part>`.

| # | Kind (`kinds.py`) | Variant | Event (switch) | To | Tone | Switchable / default | Button → |
|---|---|---|---|---|---|---|---|
| 8.1 | `password_reset` | — | — | the account | info | no (security) | `/reset-password?code=` |
| 8.2 | `invitation` | `provider.local|microsoft|google|oidc|saml` | — | invitee | info | no | `/login?invite=` |
| 8.3 | `account_created` | `method.sso|local` | — | new user | success | no | `/login` or set-password |
| 8.4 | `new_device_sign_in` | — | — | the account | warning | no (security) | `/profile#security` |
| 8.5 | `booking_created` | `who.self|other` | `booking.created` | booking owner | success | yes / other: on, self: off | `/my-bookings` |
| 8.6 | `room_owner_booking` | — | `room_owner.booking` | room owner | info | yes / on | `/bookings?room=` |
| 8.7 | `approval_submitted` | — | `approval.submitted` (new) | requester | info | yes / on | `/my-bookings?request=` |
| 8.8 | `approval_requested` | `scope.single|group` | `approval.requested` | approvers | warning | yes / on | `/approvals?request=` |
| 8.9 | `approval_approved` | — | `approval.approved` | requester | success | yes / on | `/my-bookings?request=` |
| 8.10 | `approval_rejected` | `reason.<code>`, `alt.some|none` | `approval.rejected` | requester | danger | yes / on | `/find-room?…` prefilled |
| 8.11 | `approval_withdrawn` | `to.requester|approver` | `approval.withdrawn` | both | neutral | yes / requester off, approver on | `/approvals` (approver) |
| 8.12 | `approval_expired` | — | `approval.expired` | requester | neutral | yes / on | `/reserve?…` prefilled |
| 8.13 | `booking_cancelled` | `reason.admin|replaced_by_series|undo_of|none` | `booking.cancelled` | booking owner | danger | yes / on | `/find-room?…` prefilled |
| 8.14 | `booking_conflict_resolved` | — | `booking.conflict_resolved` | booking owner | warning | yes / on | `/my-bookings` |
| 8.15 | `booking_reminder` | `when.day_before|hour_before` | `booking.reminder` (new) | booking owner | info | yes / off | `/my-bookings` |
| 8.16 | `series_created` | — | `booking.series` (new) | owner (if made by someone else) / room owner | success | yes / on | `/my-bookings?series=` |
| 8.17 | `series_changed` | `change.dates_added|dates_removed|room|periods|ended` | `booking.series` | owner | warning | yes / on | `/my-bookings?series=` |
| 8.18 | `calendar_consent` | `state.on|off`, `provider.org|google|microsoft` | — | admins (org) / the user (personal) | neutral | no (KVKK record) | `/settings?tab=integrations` / `/profile#privacy` |
| 8.19 | `kvkk_request` | `status.received|completed|refused|new` | — | data subject / KVKK officer (`new`) | neutral | no (legal) | `/profile#privacy` / `/admin/kvkk` |
| 8.20 | `ai_usage_alert` | `level.near|limit|org_near|org_limit` | `ai.usage` (new) | user / admins | warning | user: no for `limit`, yes for `near`; admins yes | `/profile#ai` / `/admin/ai` |
| 8.21 | `ops_alert` | `severity.critical|warning`, `state.firing|resolved` | `ops.alert` (new, admins) | ops admins | danger / success | yes / on | `/admin/ops` |
| 8.22 | `timetable_published` | — | `timetable.published` | academicians | info | yes / on | `/timetable?mine=1` |
| 8.23 | `preference_accepted` / `preference_rejected` | — | `preference.*` | academician | success / danger | yes / on | `/moderation/me` |
| 8.24 | `smtp_test` | — | — | the admin who tests | success | no | — |
| 8.25 | `password_changed` (proposed, P2) | — | — | the account | info | no (security) | `/reset-password` |

New events W3-MAIL adds to `EVENTS` (labels for the preferences screen): `approval.submitted` ("Talebim alındı" / "My
request was received"), `booking.reminder` ("Rezervasyon hatırlatmaları" / "Booking reminders"), `booking.series`
("Yinelenen rezervasyonlarım" / "My recurring bookings"), `ai.usage` ("Yapay zekâ kullanım uyarıları" / "AI usage
warnings"), `ops.alert` ("Operasyon uyarıları (yöneticiler)" / "Operations alerts (administrators)").

### 8.1 `password_reset` (mock-up: `email-reset-*.svg`)

| | TR | EN |
|---|---|---|
| S | Parola sıfırlama kodunuz | Your password reset code |
| P | Kod {valid_hours} saat geçerli. Bu isteği siz yapmadıysanız bu e-postayı yok sayın. | The code is valid for {valid_hours} hours. If you did not ask for it, ignore this e-mail. |
| H | Parolanızı sıfırlayın | Reset your password |
| I | Merhaba {name}, {org} SmartSched hesabınız ({username}) için parola sıfırlama istendi. | Hello {name}, a password reset was requested for your {org} SmartSched account ({username}). |
| Block | code block "Sıfırlama kodu" `{code}` | "Reset code" `{code}` |
| B | Parolayı sıfırla | Reset password |
| after | Kod {valid_hours} saat geçerlidir ve bir kez kullanılabilir. Düğme açılmazsa giriş sayfasında "Parolamı unuttum" adımına bu kodu yazın. | The code is valid for {valid_hours} hours and works once. If the button does not open, enter this code at "Forgot password" on the sign-in page. |
| N (info callout) | **Bu isteği siz yapmadınız mı?** Bir şey yapmanız gerekmez; parolanız değişmez. İstek: {when} · {device}. | **Didn't ask for this?** You don't need to do anything; your password stays the same. Request: {when} · {device}. |
| why | Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz. | This is a security e-mail; it cannot be turned off in notification settings. |

Only local accounts (LDAP and SSO accounts get no reset; the sign-in page explains, signin.local.*). The same text for
an unknown address is **never sent** and the page answers identically (no enumeration, sign-in.md §6.3).
New placeholders: `{username}`, `{code}`, `{when}`, `{device}` ("Chrome, Windows"; from the User-Agent, no IP).

### 8.2 `invitation` (mock-up: `email-invite-*.svg`, Microsoft variant)

Shared parts:

| | TR | EN |
|---|---|---|
| S | {inviter} sizi SmartSched'e davet etti | {inviter} invited you to SmartSched |
| S (no inviter) | SmartSched daveti: {org} | SmartSched invitation: {org} |
| H | SmartSched'e davet edildiniz | You're invited to SmartSched |
| I | {inviter}, sizi {org} ders programı ve derslik rezervasyonu sistemine davet etti. | {inviter} invited you to the {org} timetabling and room booking system. |
| Block | details: Rol {role} · Davet edilen adres {masked} · Giriş yöntemi {provider_label} · Son geçerlilik {expires} | Role · Invited address · Sign-in method · Valid until |
| B | Daveti kabul et | Accept invitation |
| N | Bu daveti beklemiyorsanız e-postayı yok sayabilirsiniz; siz giriş yapmadan hesap etkinleşmez. | If you weren't expecting this, you can ignore it; nothing is activated until you sign in. |
| why | Bu e-postayı, bir yönetici bu adresi davet ettiği için aldınız. | You received this because an administrator invited this address. |

Per provider (`invitation.provider.<p>.preheader` and `.how`, shown after the button):

| `provider` | `provider_label` TR / EN | Preheader TR | How TR (after the button) | Preheader / How EN |
|---|---|---|---|---|
| `local` | Kullanıcı adı ve parola / Username and password | Parolanızı belirleyip katılın. Davet {expires} tarihine kadar geçerli. | Açılan sayfada kullanıcı adınızı görür ve parolanızı belirlersiniz. | Set your password and join. Valid until {expires}. / On the page that opens you see your username and set a password. |
| `microsoft` | Microsoft (iş veya okul hesabı) / Microsoft (work or school account) | Microsoft iş veya okul hesabınızla katılın. Davet {expires} tarihine kadar geçerli. | Açılan sayfada "Microsoft ile giriş yap" düğmesine basın ve bu adresle giriş yapın. Hesabınız ilk girişte bağlanır. | Join with your Microsoft work or school account. Valid until {expires}. / On the page that opens choose "Sign in with Microsoft" and use this address. Your account is linked at the first sign-in. |
| `google` | Google Workspace hesabı / Google Workspace account | Google Workspace hesabınızla katılın. Davet {expires} tarihine kadar geçerli. | Açılan sayfada "Google ile oturum açın" düğmesine basın ve bu adresle giriş yapın. | Join with your Google Workspace account. … / Choose "Sign in with Google" and use this address. |
| `oidc` | {provider_name} (kurumsal giriş) / {provider_name} (organisation sign-in) | {provider_name} hesabınızla katılın. Davet {expires} tarihine kadar geçerli. | Açılan sayfada "{provider_name} ile giriş yap" düğmesine basın. | Join with your {provider_name} account. … / Choose "Sign in with {provider_name}". |
| `saml` | {provider_name} (kurumsal tek oturum) / {provider_name} (organisation single sign-on) | same as oidc | same as oidc | same as oidc |

The `{provider_name}` is the button label the admin gave the provider card (integrations.md §5, e.g. "Okta", "Kampüs
girişi"). `{masked}` = `mask_email` ("a•••@ornek.edu.tr"). `{expires}` = long date. Renew sends the same mail with
`S` = "Davetiniz yenilendi: {org}" / "Your invitation was renewed: {org}".

### 8.3 `account_created`

| | TR | EN |
|---|---|---|
| S | SmartSched hesabınız hazır | Your SmartSched account is ready |
| P (`sso`) | {provider_label} ile giriş yaptınız; rolünüz: {role}. | You signed in with {provider_label}; your role: {role}. |
| P (`local`) | Bir yönetici hesabınızı açtı. Parolanızı {valid_hours} saat içinde belirleyin. | An administrator created your account. Set your password within {valid_hours} hours. |
| H | Hoş geldiniz, {name} | Welcome, {name} |
| I (`sso`) | {org} SmartSched hesabınız ilk girişinizde açıldı. Rolünüz: {role}. Rolünüzü yalnızca bir yönetici değiştirebilir. | Your {org} SmartSched account was created at your first sign-in. Your role: {role}. Only an administrator can change it. |
| I (`local`) | {actor}, sizin için {org} SmartSched hesabı açtı. Kullanıcı adınız: {username}. | {actor} created a {org} SmartSched account for you. Username: {username}. |
| B | `sso`: SmartSched'i aç · `local`: Parolamı belirle | `sso`: Open SmartSched · `local`: Set my password |
| N | Sık kullanılanlar: Rezerve et, Rezervasyonlarım, Bildirim tercihleri (Profil). | Good to know: Reserve, My bookings, Notification settings (Profile). |
| why | Bu e-postayı, hesabınız açıldığı için aldınız. | You received this because your account was created. |

Never contains a password. `local` uses the reset token flow (same TTL). No `account_created` for a user created by CSV
import unless the admin ticks "Hoş geldiniz e-postası gönder".

### 8.4 `new_device_sign_in`

| | TR | EN |
|---|---|---|
| S | Yeni bir cihazdan giriş yapıldı | New sign-in from another device |
| P | {when} · {device}. Siz değilseniz oturumu kapatın. | {when} · {device}. If this wasn't you, sign it out. |
| H | Hesabınıza yeni bir cihazdan giriş yapıldı | Your account was used on a new device |
| I | Merhaba {name}, {org} SmartSched hesabınıza daha önce görmediğimiz bir cihazdan giriş yapıldı. | Hello {name}, your {org} SmartSched account was signed in on a device we haven't seen before. |
| Block | details: Zaman {when} · Cihaz {device} · Yöntem {method_label} · Yaklaşık konum {city} (only when known) | Time · Device · Method · Approximate location |
| B | Bu ben değilim | This wasn't me |
| N | Siz iseniz bir şey yapmanız gerekmez. Değilseniz düğme açık oturumları gösterir; tümünü kapatıp parolanızı değiştirebilirsiniz. | If it was you, there is nothing to do. If not, the button shows your sessions; you can sign them all out and change your password. |
| why | Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz. | This is a security e-mail; it cannot be turned off in notification settings. |

"New device" = a device cookie not seen for this account in 90 days. SSO sign-ins send it too (the IdP may also mail).

### 8.5 `booking_created` (`who.other`: someone booked for you; `who.self`: your own booking, opt-in)

| | TR | EN |
|---|---|---|
| S (`other`) | Adınıza rezervasyon yapıldı: {what} | A booking was made for you: {what} |
| S (`self`) | Rezervasyonunuz yapıldı: {what} | Your booking is confirmed: {what} |
| P | {room}, {date} {period}. {count_text} | {room}, {date} {period}. {count_text} |
| H | `other`: {actor} sizin adınıza derslik ayırdı · `self`: Rezervasyonunuz yapıldı | `other`: {actor} booked a room for you · `self`: Your booking is confirmed |
| status | Rezerve edildi (ok) | Booked |
| Block | details (room, date, period, repeats, note) | |
| B | Rezervasyonu görüntüle | View booking |
| N | Takvime ekle (.ics) | Add to calendar (.ics) |
| why | Bu e-postayı, "{event_label}" bildirimi açık olduğu için aldınız. | You received this because "{event_label}" notifications are on. |

`{count_text}` = "" for one, "Toplam {count} rezervasyon." for more (details list ≤ 5, "+N daha"). Keeps the old keys
`booking_created.subject/.body` as the plain-text intro (kinds.py `intro_key`).

### 8.6 `room_owner_booking`

| | TR | EN |
|---|---|---|
| S | Sorumlu olduğunuz dersliğe rezervasyon: {what} | New booking in a room you look after: {what} |
| P | {actor} · {date} {period}{series_text} | {actor} · {date} {period}{series_text} |
| H | {room} için yeni rezervasyon | New booking for {room} |
| I | {actor} sorumlu olduğunuz dersliği ayırdı. | {actor} booked a room you look after. |
| B | Dersliğin gününü aç | Open the room's day |
| why | Bu e-postayı, {room} için sorumlu olarak kayıtlı olduğunuz için aldınız. | You received this because you are listed as responsible for {room}. |

### 8.7 `approval_submitted` (new)

| | TR | EN |
|---|---|---|
| S | Talebiniz alındı: {what} | Your request was received: {what} |
| P | Onay bekliyor. Karar verildiğinde size haber vereceğiz. | Awaiting approval. We'll let you know when it's decided. |
| status | Onay bekliyor (warn) | Awaiting approval |
| H | Talebiniz onaya gönderildi | Your request was sent for approval |
| I | {room} için talebiniz {approver_text} gönderildi. Derslik, karar verilene kadar başkasına verilmez. | Your request for {room} was sent {approver_text}. The room is held until a decision is made. |
| B | Talebimi görüntüle | View my request |
| N | Vazgeçerseniz talebi Rezervasyonlarım'dan geri çekebilirsiniz. | If you change your mind, withdraw it from My bookings. |

`{approver_text}` = "onaycılara" / "to the approvers" (never names: approvers may change). "Held" is only said when the
backend actually holds the slot (pending requests block the slot today; W3-MAIL confirms with `approvals.py`).

### 8.8 `approval_requested` (mock-up: `email-approver-request-*.svg`)

| | TR | EN |
|---|---|---|
| S | Onay bekleyen oda talebi: {what} | Room request awaiting approval: {what} |
| S (`group`) | Onay bekleyen {n} ders saati: {room} · {date_short} | {n} periods awaiting approval: {room} · {date_short} |
| P | {who} {room} için onay istiyor · {repeat_short} · {conflict_short} | {who} asks for {room} · {repeat_short} · {conflict_short} |
| status | Onay bekliyor (warn) | Awaiting approval |
| H | Onayınızı bekleyen bir talep var | A request is waiting for your approval |
| I | {who} aşağıdaki derslik için onay istiyor. | {who} asks for approval for the room below. |
| Block | details: Talep eden · Derslik · Tarih · Ders saati · Tekrar · Not · Çakışma (tone warn) | |
| B | Talebi incele | Review request |
| secondary | Onay kuyruğu: {queue_count} talep bekliyor | Approval queue: {queue_count} waiting |
| N | Karar uygulamada verilir; bu e-postadaki bağlantılar tek başına onaylamaz veya reddetmez. | Decisions are made in the app; the links in this e-mail never approve or decline on their own. |
| why | Bu e-postayı, {room} için onaycı olduğunuz için aldınız. | You received this because you approve requests for {room}. |

`{repeat_short}` = "tek sefer" / "8 hafta"; `{conflict_short}` = "çakışma yok" / "1 çakışan talep". **No approve/decline
buttons in mail** (security scanners pre-fetch links; a decision needs the reason dialog and the conflict view). A burst
of requests from one requester within 2 minutes is one mail (group variant, same digest key as the in-app notice).

### 8.9 `approval_approved` (mock-up: `email-approved-*.svg`)

| | TR | EN |
|---|---|---|
| S | Oda talebiniz onaylandı: {what} | Your room request was approved: {what} |
| P | {room}, {date} {period_time} sizin. Takviminize ekleyebilirsiniz. | {room} is yours on {date}, {period_time}. You can add it to your calendar. |
| status | Onaylandı (ok) | Approved |
| H | Oda talebiniz onaylandı | Your room request was approved |
| I | {who} talebinizi onayladı. Derslik bu saatlerde sizin adınıza ayrıldı.{note} | {who} approved your request. The room is booked for you at these times.{note} |
| Block | details: Derslik · Tarih · Ders saati · (Tekrar) · Talep no (tone ok) | |
| B | Rezervasyonu görüntüle | View booking |
| secondary | Takvime ekle (.ics) | Add to calendar (.ics) |

`{note}` = " Not: {text}" when the approver wrote one (approvals.TEXTS already does this).

### 8.10 `approval_rejected` (mock-up: `email-rejected-*.svg`)

| | TR | EN |
|---|---|---|
| S | Oda talebiniz reddedildi: {what} | Your room request was declined: {what} |
| P (`alt.some`) | Gerekçe: {reason_label}. Aynı saatte boş {alt_count} derslik var. | Reason: {reason_label}. {alt_count} rooms are free at the same time. |
| P (`alt.none`) | Gerekçe: {reason_label}. Başka bir saat veya derslik deneyebilirsiniz. | Reason: {reason_label}. You can try another time or room. |
| status | Reddedildi (bad) | Declined |
| H | Oda talebiniz reddedildi | Your room request was declined |
| I | {who} talebinizi reddetti. Gerekçe ve aynı saatte boş olan derslikler aşağıda. (`alt.none`: "… Gerekçe aşağıda.") | {who} declined your request. The reason and rooms free at the same time are below. |
| Block 1 | reason callout (bad): **Gerekçe: {reason_label}** + `{reason_text}` | **Reason: {reason_label}** |
| Block 2 | details: Derslik · Tarih · Ders saati · Talep no (no tone bar) | |
| Block 3 (`alt.some`, ≤ 3) | "Aynı saatte boş derslikler": `{alt_room}` · "{capacity} kişi · {features}" · link "Bu dersliği iste" → `/reserve?room={id}&date=…&period=…` | "Rooms free at the same time" · "Request this room" |
| B | Başka bir derslik bul | Find another room |
| why | Bu e-postayı, "Talebim reddedildi" bildirimi açık olduğu için aldınız. | … "My request was declined" … |

Reason labels come from `approvals.REASON_CODES` (Oda uygun değil · Kapasite yetersiz · Rezervasyon kurallarına uygun
değil · Diğer → the free text alone) and `SYSTEM_REASONS.slot_taken` ("Aynı saat başka bir talebe verildi": then I =
"Aynı saat için başka bir talep onaylandı; sizinki kendiliğinden kapandı." / "Another request for the same time was
approved, so yours was closed automatically." and no "{who}"). Suggestions use the find-room ranking (capacity ≥ need,
same features, nearest building first); the button opens `/find-room` prefilled with date, periods and capacity.

### 8.11 `approval_withdrawn`

| | TR (`to.approver`) | EN | TR (`to.requester`, default off) | EN |
|---|---|---|---|---|
| S | Oda talebi geri çekildi: {what} | Room request withdrawn: {what} | Oda talebinizi geri çektiniz: {what} | You withdrew your room request: {what} |
| P | {who} talebini geri çekti; bir şey yapmanız gerekmez. | {who} withdrew it; nothing to do. | Derslik yeniden boş. | The room is free again. |
| status | Geri çekildi (neutral) | Withdrawn | same | |
| H | Talep geri çekildi | Request withdrawn | Talebinizi geri çektiniz | You withdrew your request |
| I | {who} onayınızı bekleyen talebini geri çekti. | {who} withdrew the request that was waiting for you. | Talebiniz geri çekildi; derslik başkalarına açıldı. | Your request was withdrawn and the room is open to others. |
| B | Onay kuyruğunu aç | Open approval queue | Yeni talep oluştur | Make a new request |

### 8.12 `approval_expired`

| | TR | EN |
|---|---|---|
| S | Oda talebinizin süresi doldu: {what} | Your room request expired: {what} |
| P | Talep, başlangıç saatinden önce onaylanmadı. | The request wasn't approved before it started. |
| status | Süresi doldu (neutral) | Expired |
| H | Talebinizin süresi doldu | Your request expired |
| I | Talebiniz başlangıçtan önce onaylanmadığı için kendiliğinden kapandı.{note} | Your request closed automatically because it wasn't approved before it started.{note} |
| B | Yeniden rezerve et | Book again |

### 8.13 `booking_cancelled` (decoded reasons)

| | TR | EN |
|---|---|---|
| S | Rezervasyonunuz iptal edildi: {what} | Your booking was cancelled: {what} |
| S (count > 1) | {count} rezervasyonunuz iptal edildi | {count} of your bookings were cancelled |
| status | İptal edildi (bad) | Cancelled |
| H | Rezervasyonunuz iptal edildi | Your booking was cancelled |
| B | Başka bir derslik bul (→ find-room prefilled) | Find another room |

Variant by reason (`booking_cancelled.reason.<code>`: preheader + intro + callout):

| `reason` | Preheader TR | Intro TR | Callout TR | EN (preheader · intro · callout) |
|---|---|---|---|---|
| `admin` (a person's words) | {actor} iptal etti. Gerekçe: {reason_short} | {actor} aşağıdaki rezervasyonunuzu iptal etti. | **Gerekçe:** {reason} | {actor} cancelled it. Reason: … · {actor} cancelled the booking below. · **Reason:** … |
| `replaced_by_series` | Yerine seri #{id} geldi. | Bu rezervasyon, aynı saatleri kapsayan seri #{id} ile değiştirildi. | **Gerekçe:** Seri #{id} ile değiştirildi | Replaced by series #{id}. · This booking was replaced by series #{id}, which covers the same times. · **Reason:** Replaced by series #{id} |
| `undo_of` | Bir işlem geri alındı. | {actor} son işlemini geri aldı; bu rezervasyon da kaldırıldı. | **Gerekçe:** Geri alma (#{id}) | An action was undone. · {actor} undid a recent change, which removed this booking. · **Reason:** Undo (#{id}) |
| `none` | {actor} iptal etti. | {actor} aşağıdaki rezervasyonunuzu iptal etti. | — | {actor} cancelled it. |

Not sent: your own cancellation (toast + Geri al is the record), and cancellations from a KVKK erasure (the person is gone).
For `replaced_by_series` where the new series is the same person's, the button is "Seriyi görüntüle" / "View series"
instead of find-room.

### 8.14 `booking_conflict_resolved`

| | TR | EN |
|---|---|---|
| S | Rezervasyonunuz yayınlanan programa göre değişti | Your booking changed to fit the published timetable |
| P | {count_text} Yeni derslik ve saatler içeride. | {count_text} New rooms and times inside. |
| H | Rezervasyonunuz değişti | Your booking changed |
| I | {term} programı yayınlandı ve rezervasyonunuz bir dersle çakışıyordu. Aşağıdaki değişiklik yapıldı. | The {term} timetable was published and your booking clashed with a class. This change was made. |
| Block | details per booking: "Önce: B-204 · 3. ders" → "Şimdi: B-301 · 3. ders" (or "İptal edildi") | Before / Now |
| B | Rezervasyonlarımı aç | Open my bookings |

### 8.15 `booking_reminder` (new, default off)

| | TR | EN |
|---|---|---|
| S (`day_before`) | Yarın: {room} · {period_time} | Tomorrow: {room} · {period_time} |
| S (`day_before`, several) | Yarınki rezervasyonlarınız ({count}) | Your bookings tomorrow ({count}) |
| S (`hour_before`) | {start} başlıyor: {room} | Starts at {start}: {room} |
| P | {date} · {period} · {building} | |
| H | Hatırlatma: yarın derslik ayırdınız / {start} başlıyor | Reminder: you have a room tomorrow / starts at {start} |
| Block | details (one per booking, ≤ 5) | |
| B | Rezervasyonu görüntüle | View booking |
| N | Gerekmiyorsa iptal edin; derslik başkasına açılır. | If you no longer need it, cancel it so others can book the room. |

One mail per day per person at 07:30 org time (`day_before` digest) or one per booking 60 min before (`hour_before`); the
user picks in Bildirimler. Never for bookings created less than 2 hours before the reminder time.

### 8.16 `series_created`

| | TR | EN |
|---|---|---|
| S | Yinelenen rezervasyon: {room} · {pattern} | Recurring booking: {room} · {pattern} |
| P | {count} tarih · seri #{series_id}{skipped_text} | {count} dates · series #{series_id}{skipped_text} |
| status | Rezerve edildi (ok) | Booked |
| H | Yinelenen rezervasyonunuz oluşturuldu | Your recurring booking was created |
| I | {who} sizin için {room} dersliğinde {pattern} rezervasyon oluşturdu. | {who} created a recurring booking for you in {room}, {pattern}. |
| I (self) | {room} için {pattern} rezervasyonunuz oluşturuldu. | Your recurring booking for {room}, {pattern}, was created. |
| Block | details: Derslik · Tekrar "{pattern} · {count} hafta" · İlk / Son tarih · Ders saati · Atlanan tarihler "29 Ekim (Cumhuriyet Bayramı)" | Skipped dates |
| B | Seriyi görüntüle | View series |

`{pattern}` = "her çarşamba" / "every Wednesday"; `{skipped_text}` = " · {n} tatil atlandı" / " · {n} holidays skipped".
Note: in "{room} dersliğinde" the suffix sits on the fixed word "derslik", not on the placeholder, so it is allowed (§7 rule 2).

### 8.17 `series_changed`

| | TR | EN |
|---|---|---|
| S | Seri #{series_id} değişti: {room} | Series #{series_id} changed: {room} |
| P | {change_short} | |
| H | Yinelenen rezervasyonunuz değişti | Your recurring booking changed |
| I | {who} seri #{series_id} üzerinde değişiklik yaptı. | {who} changed series #{series_id}. |
| Block | details "Önce / Şimdi" for the changed field; dates list for added/removed | Before / Now |
| B | Seriyi görüntüle | View series |

`change.<value>` short texts: `dates_added` "{n} tarih eklendi" / "{n} dates added"; `dates_removed` "{n} tarih çıkarıldı" /
"{n} dates removed"; `room` "Derslik {old} → {new}" / "Room {old} → {new}"; `periods` "Saat {old} → {new}" / "Time {old} →
{new}"; `ended` "Seri {date} tarihinde sona erdi" / "Series ends on {date}".

### 8.18 `calendar_consent` (KVKK record; not switchable)

| | TR (`provider.org`, to admins) | EN | TR (personal: user connected Google/Microsoft) | EN |
|---|---|---|---|---|
| S (`on`) | Takvim eşitleme açıldı (KVKK onayı kaydedildi) | Calendar sync turned on (KVKK consent recorded) | {provider_label} takviminiz bağlandı | Your {provider_label} calendar is connected |
| S (`off`) | Takvim eşitleme kapatıldı | Calendar sync turned off | {provider_label} takviminizin bağlantısı kaldırıldı | Your {provider_label} calendar was disconnected |
| P | {actor}, {when} | | Rezervasyonlarınız bu takvime aktarılır. / Aktarım durdu. | Your bookings are copied to it. / Copying stopped. |
| H | same as S | | same as S | |
| I (`on`) | {actor}, {when} tarihinde takvim eşitlemeyi açtı ve kurum adına KVKK onayını verdi. Rezervasyonların tarih, saat, derslik ve not bilgileri kullanıcıların bağladığı takvimlere aktarılabilir (sunucular yurt dışında). | {actor} turned calendar sync on at {when} and gave KVKK consent for the organisation. Booking date, time, room and note can be copied to calendars users connect (servers abroad). | Rezervasyonlarınızın tarih, saat, derslik ve not bilgileri {provider_label} takviminize aktarılır. {provider_label} sunucuları yurt dışındadır. | The date, time, room and note of your bookings are copied to your {provider_label} calendar. Its servers are outside Türkiye. |
| Block | details: Hukuki dayanak "KVKK md. 9" · Kayıt no #{audit_id} | Legal basis · Record no | details: Hesap {account} · Bağlantı zamanı {when} | Account · Connected at |
| B | Entegrasyonları aç | Open integrations | Bağlı takvimleri yönet | Manage connected calendars |
| why | Bu e-posta yasal bir bildirimdir (KVKK); kapatılamaz. | This is a legal notice (KVKK); it cannot be turned off. | same | |

Wording matches `notifications.admin.calendar.*` in tr.json.

### 8.19 `kvkk_request`

| | `received` TR | `completed` TR | `refused` TR | `new` (to KVKK officers) TR |
|---|---|---|---|---|
| S | KVKK talebiniz alındı | KVKK talebiniz yanıtlandı | KVKK talebiniz hakkında yanıt | Yeni KVKK talebi: {request_kind_label} |
| P | Yanıt en geç {due} tarihinde. Talep no #{id}. | {request_kind_label}: tamamlandı. | Gerekçe içeride. | Son gün {due} · {subject_label} |
| H | Talebinizi aldık | Talebiniz yanıtlandı | Talebiniz karşılanamadı | Yanıt bekleyen bir KVKK talebi var |
| I | {request_kind_label} talebiniz {when} tarihinde kaydedildi. Kanun, yanıt için 30 gün tanır. | {request_kind_label} talebiniz {when} tarihinde işlendi.{detail} | {request_kind_label} talebiniz aşağıdaki gerekçeyle karşılanamadı. | {subject_label} bir {request_kind_label} talebinde bulundu. |
| Block | details: Talep türü · Talep no · Son gün | details + "Silinenler" summary (`kvkk.dsr.count.*` labels) | reason callout (bad): **Gerekçe:** {reason} | details: Kişi · Talep türü · Son gün (warn if ≤ 7 days) |
| B | Taleplerimi görüntüle | Taleplerimi görüntüle | Taleplerimi görüntüle | Talebi aç |
| N | — | Kanun gereği bazı kayıtlar takma adla saklanır (denetim kaydı). | İtiraz için Kişisel Verileri Koruma Kurulu'na başvurabilirsiniz. | — |

EN: received "We received your KVKK request" / "Your request for {request_kind_label} was recorded on {when}. The law
allows 30 days for an answer." · completed "Your KVKK request was answered" · refused "About your KVKK request" /
"Your request could not be fulfilled for the reason below." / "You can appeal to the Turkish Personal Data Protection
Board (KVKK Kurulu)." · new "New KVKK request: {request_kind_label}". `request_kind_label`: Silme / Erasure, Düzeltme /
Rectification, Bilgi / Information, Veri indirme / Data export. A completed erasure mail goes to the address on file
**before** erasure (sent, then the address is erased; the outbox row is anonymised with it).

### 8.20 `ai_usage_alert` (wording = ai-admin.md §6)

| `level` | S TR | P TR | H / I TR | B TR | EN (S · I · B) |
|---|---|---|---|---|---|
| `near` (user, ≥ threshold, once per period) | Yapay zekâ kullanım hakkınız: %{percent} kullanıldı | {reset_date} tarihinde yenilenir. | Kullanım hakkınız azalıyor · Bu ayki yapay zekâ kullanım hakkınızın yüzde {percent} kadarı kullanıldı. {reset_date} tarihinde yenilenir. | Kullanımımı gör | You have used {percent}% of your AI allowance · It resets on {reset_date}. · View my usage |
| `limit` (user, 100 %) | Yapay zekâ kullanım sınırınıza ulaştınız | Ek kullanım için yöneticinize başvurun. | Kullanım sınırına ulaşıldı · Bu ayki sınırınıza ulaştınız; yapay zekâ özellikleri {reset_date} tarihine kadar kapalı. Planlama ve rezervasyon çalışmaya devam eder. | Yöneticiye bildir | You have reached your AI limit · AI features are paused until {reset_date}; planning and booking keep working. · Notify an administrator |
| `org_near` (admins, ≥ 90 %) | Kurum yapay zekâ bütçesi: %{percent} kullanıldı | {used} / {limit} token · {reset_date} yenilenir | Kurum bütçesi azalıyor · details: Kullanılan · Sınır · En çok kullanan 3 kişi | Limitleri aç | {percent}% of the organisation's AI budget is used · Open limits |
| `org_limit` (admins) | Kurum yapay zekâ bütçesi doldu | Yapay zekâ istekleri durdu. | Bütçe doldu · Yeni istekler {reset_date} tarihine kadar engelleniyor. | Limitleri aç | The organisation's AI budget is used up · Open limits |

Suffix note: `ai-admin.md` key `aiAdmin.banner.near` reads "…hakkınızın %{pct}'ini kullandınız", which is wrong for most numbers (84 → "%84'ünü", 90 → "%90'ını"). Use the suffix-free form above ("Yapay zekâ kullanım hakkınız: %{percent} kullanıldı") in the banner, bell and e-mail alike; `tr_grammar.py` has only `dative()`, no accusative/possessive helper.

`{percent}`: "%84" in TR (the `%` before the number), "84%" in EN. `limit` for the user's `downgraded` action: I = "Sınırınıza
ulaştınız; bu ay daha hızlı ve sınırlı bir modelle devam ediliyor." (ai-admin `aiAdmin.banner.downgraded`).

### 8.21 `ops_alert`

| | TR (`firing`) | EN | TR (`resolved`) | EN |
|---|---|---|---|---|
| S | [{severity_label}] {title} | [{severity_label}] {title} | Çözüldü: {title} | Resolved: {title} |
| P | {service_label} · {first_seen} itibarıyla · {count} kez | {service_label} · since {first_seen} · {count} times | {duration} sürdü. | Lasted {duration}. |
| status | Kritik (bad) / Uyarı (warn) | Critical / Warning | Çözüldü (ok) | Resolved |
| H | {title} | | {title} çözüldü | {title} resolved |
| I | {detail} | | Servis yeniden normal çalışıyor. | The service is back to normal. |
| Block | details: Servis · Başlangıç · Tekrar sayısı · Sunucu | Service · Started · Count · Host | details: Başlangıç · Bitiş | |
| B | Operasyon panelini aç | Open operations panel | Olay kaydını gör | View incident log |

`[Kritik]` is the only bracketed subject prefix in the system (sorting by severity in a shared ops mailbox). `{title}` is
the TR alert summary from ops-panel.md ("E-posta kuyruğu 30 dakikadır bekliyor"). Rate: one firing and one resolved mail per
alert per 6 hours; a flapping alert does not spam.

### 8.22–8.25 Existing and support kinds (move into the layout; copy unchanged unless noted)

| Kind | S TR / EN | H TR | B TR / EN |
|---|---|---|---|
| `timetable_published` | {term} programı yayınlandı: derslerinizde değişiklik var / The {term} timetable is published: your classes changed | Derslerinizde değişiklik var (details: per class "Önce / Şimdi") | Programımı aç / Open my timetable |
| `preference_accepted` | Ders tercihiniz kabul edildi: {course} / Your class preference was accepted: {course} | Tercihiniz kabul edildi | Tercihlerimi aç / Open my preferences |
| `preference_rejected` | Ders tercihiniz kabul edilmedi: {course} / Your class preference was declined: {course} | Tercihiniz kabul edilmedi (reason callout) | Tercihlerimi aç / Open my preferences |
| `smtp_test` | SmartSched deneme iletisi / SmartSched test message | E-posta ayarları çalışıyor. I: "{host} üzerinden gönderildi. Bu iletiyi gördüyseniz bildirimler kullanıcılara ulaşır." / "Sent through {host}. If you can read this, notifications will reach your users." | — (no button) |
| `password_changed` (proposed) | Parolanız değiştirildi / Your password was changed | I: "{when} · {device}." N: "Siz değilseniz hemen parolanızı sıfırlayın ve yöneticinize haber verin." | Parolayı sıfırla / Reset password |

## 9. Keys and placeholders (for `app/emails/strings.py`)

- Parts per kind: `subject`, `preheader`, `heading`, `intro`, `cta`, `note` (kinds.py) plus, where this spec uses them,
  `status` (pill word), `after` (text after the button), `secondary` (secondary link label), `why` (footer reason).
  Variants: `<kind>.<field>.<value>.<part>`, falling back to `<kind>.<part>`.
- Layout keys (W3-MAIL has most): `layout.footer.reason`, `layout.footer.prefs`, `layout.footer.sent_by`,
  `layout.footer.no_reply`, `layout.footer.security` ("Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz." /
  "This is a security e-mail; it cannot be turned off in notification settings."), `layout.footer.legal` ("Bu e-posta yasal
  bir bildirimdir (KVKK); kapatılamaz." / "This is a legal notice (KVKK); it cannot be turned off."), `layout.footer.kvkk`
  ("KVKK Aydınlatma Metni" / "Privacy notice (KVKK)"), `layout.button_fallback`, `layout.reason`, `layout.suggestions`
  ("Aynı saatte boş derslikler" / "Rooms free at the same time"), `layout.code`, `layout.details`, `layout.more`
  ("+{n} daha" / "+{n} more"), `layout.add_to_calendar` ("Takvime ekle (.ics)" / "Add to calendar (.ics)"), detail labels
  `layout.row.{requested_by,room,date,period,repeats,dates,note,conflict,request_no,decided_by,role,invited,method,valid_until,time,device,location}`.
- Placeholders are always filled server-side; an admin override with an unknown placeholder keeps it literally
  (`bookings_i18n._Missing`), and the template editor lists the allowed ones (kinds.py `placeholders`).
- `{what}` is built once per request (room · short date · period) and reused by subject, bell title and push.

## 10. Accessibility

- `<html lang>` = recipient language; `<title>` = subject; the wrapper table `role="article" aria-roledescription="e-posta"`
  (EN "email") `aria-label="{subject}"`; layout tables `role="presentation"`; the heading is a real `<h1>`; details use
  a `<table>` **without** `role="presentation"` and `<th scope="row">` for labels (screen readers read "Derslik, B-204").
- Body 16 px, line height 1.5, contrast §3.2, status words, no meaning in colour or position only.
- Link text says where it goes ("Rezervasyonu görüntüle", never "buraya tıklayın"); the fallback URL is the only bare URL.
- Button target 48 px tall; on phones full width; ≥ 8 px from any other link.
- Images: the tile has `alt="SmartSched"` but the header text also says it, so screen readers hear it twice: use `alt=""`
  on the tile **because** the live text follows (brand.md §8 "decorative when adjacent text says SmartSched"). University
  logo `alt="{org}"` when it replaces the org text.
- Codes: one `<span>` with `aria-label` spelled out in groups ("K 7 Q 4, M 2 X 9") so screen readers do not read it as a
  word; selectable as plain text.
- Plain-text twin always present (screen-reader users on text mail clients, Outlook "read as plain text" policies).
- Reading order = visual order (single column; no `float`).

## 11. Test matrix (W3-MAIL runs; the stack's SMTP sink on :2721 catches mail)

| Client | Mode | Must check |
|---|---|---|
| Apple Mail iOS 26 / macOS 26 | light, dark | dark tokens swap; tile visible; phone stacking; button full width |
| Gmail web, Gmail iOS, Gmail Android | light; dark (forced inversion) | no clipping (< 102 KB), button blue and readable after inversion, no white logo halo |
| Outlook classic Windows (Word engine) | light, dark | VML button, square corners OK, details columns, Segoe UI |
| New Outlook for Windows / Outlook.com | light, dark (`[data-ogsc]`) | anchor padding kept (td bgcolor), dark swaps |
| Outlook iOS / Android | light, dark | |
| Yandex Mail web (common in Türkiye), Thunderbird | light | `<style>` stripping fallback still one column |
| Images off (any) | — | header reads "SmartSched · {org}" |
| Plain-text | — | same order, URLs present, ≤ 78 columns |
| Screen reader (VoiceOver iOS on Apple Mail) | — | heading, details table read as label/value |

Without Litmus/Email on Acid seats: render the HTML in Chromium at 600 and 390 px with `prefers-color-scheme` emulated
both ways and with a simulated full inversion (`filter: invert(1) hue-rotate(180deg)` on the body, images re-inverted),
and send each kind once to a real Gmail and Outlook test mailbox before release.

## 12. Acceptance checks

| Id | Check | Pass when |
|---|---|---|
| EM-01 | Render every kind × variant in TR and EN | no `{placeholder}` left, no key name shown, no raw code (`replaced_by_series:`, `PENDING`) |
| EM-02 | HTML size | every message < 90 KB |
| EM-03 | Structure | one `<h1>`, one primary button, ≤ 1 secondary link, footer with org + why (+ prefs link on switchable kinds) |
| EM-04 | Subjects | ≤ 60 characters with a typical `{what}`; equal to the in-app title of the same event (messages.md §4) |
| EM-05 | Preheader | 40–110 characters, differs from subject, filler present |
| EM-06 | Contrast | every text/background pair of §3.1 in both themes ≥ 4.5:1 (script in CI) |
| EM-07 | Dark mode | Chromium with `prefers-color-scheme: dark` shows the dark tokens; `[data-ogsc]` rules present |
| EM-08 | Phone | at 390 px: no horizontal scroll, button 100 % width ≥ 48 px tall, details stacked |
| EM-09 | Outlook | `<!--[if mso]>` VML button present with the same href and label |
| EM-10 | Links | absolute https on `public_url`; no tracking params; without `public_url` the mail has no links and the outbox notes it |
| EM-11 | Plain text | multipart/alternative present; same facts; button as "label: url" |
| EM-12 | Headers | `Auto-Submitted`, threading ids on request mails, `List-Unsubscribe(-Post)` only on switchable kinds |
| EM-13 | One-click off | POST to the unsubscribe URL turns that event off for that user on e-mail only, audited, confirmation page has "Geri al" |
| EM-14 | Security kinds | reset/new-device/invite carry the security footer and no prefs link; reset for unknown address sends nothing |
| EM-15 | Approver mail | contains no approve/decline URL (grep for `/decide`, `approve=`) |
| EM-16 | Rejected | decoded reason label, free text, ≤ 3 suggestions with prefilled links, find-room button |
| EM-17 | Cancelled | each reason variant renders its own sentence; own cancellation sends nothing |
| EM-18 | Language | user `en` gets English with English dates; legacy `de` user gets English; org default used when user has none |
| EM-19 | Accessibility | `lang`, `role="article"`, `aria-label`, `<th scope="row">` in details, decorative tile `alt=""` |
| EM-20 | Overrides | an admin override of `approval_approved.subject` shows in the next mail; a stray `{` does not break sending |

## 13. Hand-off and asks

- **W3-MAIL**: build `layout.html.j2` (+ partials per §5) and the text twin; adopt the copy in §8 into
  `app/emails/strings.py` (where your draft differs, this spec is the design source; tell me if a sentence does not fit
  a real code path, e.g. 8.7 "held until a decision"); add the five events of §8 to `notify_dispatch.EVENTS`; contrast
  test EM-06 can reuse the numbers in §3.2.
- **W3-IDP**: send `invitation` with `provider` and `provider_name`, and `account_created` on first SSO sign-in.
- **W3-SEC** (or whoever owns sessions): `new_device_sign_in` with `{when}`, `{device}`, `{method_label}`.
- **W3-AI / W3-OPS**: `ai_usage_alert` levels and `ops_alert` states as in §8.20–8.21; the bell titles are in messages.md.
- **Orchestrator**: nothing to edit outside `docs/design/v3/`.
