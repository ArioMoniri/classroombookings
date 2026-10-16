# F-13 · Language TR/EN, reduced motion and transparency, keyboard-only pass over F-01..F-04

Personas: **staff** and **academician** (the F-01..F-04 surfaces); **admin** for the approval steps of F-01. Viewports:
- Part A (language) and Part B (motion): desktop and phone;
- Part C (keyboard only): desktop, plus a 768 × 1024 tablet with a hardware keyboard (`hasTouch: true`, keyboard input).

Owner decisions:
- **Languages.** Reduced to **TR + EN**. The picker offers only tr / en, and other stored codes render English.
- **Language source.** The UI follows the **profile** language from the first paint, with no TR/EN flip between routes.
- **Mobile.** Part of the definition of done for every screen.

Testable: yes. F-01's former UI gaps (the reject dialog and the reason display) are built since 2026-10-16.

## Preconditions

1. Restore the snapshot. Prepare the F-01..F-04 preconditions (approval_mode=all, KVKK calendar sign-off on: the README §4.2 stack leaves it off (`REC_CAL_SIGNOFF=0`), so as admin `PUT /calendar/admin/settings {"calendar_sync_enabled":true}`; features catalogue, the staff bookings of F-04 precondition 2). This flow replays parts of them.
2. Shared helpers for Part C (put them in your script):
   ```js
   // the focused element draws a visible ring: a solid outline ≥ 2 px, or a ≥ 2 px box-shadow ring
   export const ringOf = (page) => page.evaluate(() => {
     const el = document.activeElement; const cs = getComputedStyle(el);
     const shadowPx = [...(cs.boxShadow || "").matchAll(/0px 0px 0px (\d+(?:\.\d+)?)px/g)].map((m) => +m[1]);
     return { tag: el.tagName, label: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 50),
              outline: cs.outlineStyle, width: parseFloat(cs.outlineWidth) || 0, shadow: Math.max(0, ...shadowPx),
              ok: (cs.outlineStyle !== "none" && (parseFloat(cs.outlineWidth) || 0) >= 2) || Math.max(0, ...shadowPx) >= 2 };
   });
   // English UI words that must not appear in TR mode (accessible names and visible text of controls)
   export const EN_WORDS = /\b(Close|Loading|Save|Cancel|Search|Submit|Next|Previous|Error|Something went wrong|Delete|Edit|Back|Open|Retry|Command or Control)\b/;
   // raw i18n keys in visible text (e.g. "wave1.find.title")
   export const RAW_KEY = /\b(?:wave1|crbs|reserve|glass|moderation|learning|programWizard|calendar|studio|common|admingaps)\.[A-Za-z0-9_.]+\b/;
   ```

## Part A · language

**A01 · staff · Turkish everywhere in TR mode**
- Do: profile language tr. Visit `/bookings`, `/my-bookings`, `/find-room`, `/profile`, a 404 (`/yok-boyle-sayfa`), and open the book sheet and the sync sheet.
- Check on each:
  - the visible text and every accessible name (`page.accessibility.snapshot()` or `locator.evaluateAll` over `button, a, [role]`) contain no `EN_WORDS` match and no `RAW_KEY` match;
  - `document.title` is Turkish: "Rezervasyonlar · SmartSched", "Rezervasyonlarım · SmartSched", "Boş derslik bul · SmartSched", "Profil · SmartSched" (U-09);
  - the sheet close button is named "Kapat";
  - the 404 is inside the shell, in Turkish, with a role-aware home link (`not-found`, `not-found-home` → `/bookings` for staff);
  - `/profile` shows the role in Turkish ("Öğretim elemanı"), not "Teacher".
- Dates read Turkish ("22 Eki 2026", "Perşembe"), numbers use tr-TR grouping ("1.524"), and date inputs are gg.aa.yyyy or a localised picker, never mm/dd/yyyy.

**A02 · staff · switch to English**
- Do: `/profile` → **"Dil"** (`profile-language`) → English → save (`profile-save`).
- See: the picker offers **only** Türkçe and English. The save toast is **in English** ("Saved"; U-09: it was in Turkish). The whole shell switches at once, with no reload needed, or after one reload with no flash of Turkish.
- Do: run F-01 S02–S05, F-03 S01–S02 and S06, and F-04 S03–S05 in English.
- Check: no Turkish UI text is left (allow data such as room codes, course names and notes). No `RAW_KEY`. ICU plurals are right ("1 booking", "3 bookings"). Titles read "Bookings · SmartSched" and so on. Building chips read "A block" or "Building A" without doubling (U-10: "A Blok block").
- Switch back to Turkish at the end.

**A03 · academician · notifications follow the recipient's language**
- Do: set the academician's profile to English. The admin (Turkish) rejects one academician request with the reason code "Kapasite yetersiz" and the text `Sınav haftası`.
- See: the academician's bell item reads **"Your room request was declined: …"**. The sink mail's subject is "Your room request was declined: …" and its body contains **"Reason: Not enough seats: Sınav haftası"**. The admin's own UI stays Turkish.

**A04 · anyone · the login page before login**
- Do: `/login`, `locale-toggle` → EN → log in as staff (whose profile is tr).
- See: after login the profile language wins (Turkish). The login toggle only affects the login page. No route shows English afterwards in this session.

## Part B · reduced motion and reduced transparency

Probe functions: MOBILE.md M-14 (`probeStart`, `probeStop`, `overCeiling`, `moving`).

**B01 · OS reduced motion**
- Do: a context with `reducedMotion: "reduce"`. As staff open `/bookings?date=$D1`, then a free cell → the book sheet.
- Expect: two rAF ticks after the click, the sheet's computed `transform` is `none` (or translate `none`), opacity is 1, and `moving()` returns `[]`. The same holds for the bell popover, the sync sheet, the F-03 results and the F-04 Taleplerim row expand. Nothing loops on an idle page.

**B02 · in-app "Hareketi azalt"**
- Do: a normal context. `/settings` → **"Hareketi azalt"** on. Check that `<html data-motion="reduced">` is set.
- Expect: the same as B01, plus the setting survives a reload. Busy buttons still say what they do in words ("Aranıyor…"), so a frozen spinner is never the only signal (motion T1).

**B03 · reduced transparency (OS and in-app)**
- Do: `cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] })`, then separately the in-app **"Saydamlığı azalt"** (`data-transparency`). Open the book sheet, the bell panel, the sync sheet and the phone tab bar.
- Expect: `backdropFilter` is `none` on each surface. The surface is opaque: `backgroundColor` alpha is 1, **or** `backgroundImage` is a solid / opaque gradient. Read both, because glass is a gradient and `backgroundColor` alone reads transparent (motion audit T13).

**B04 · motion budget** (INCONCLUSIVE rules of README §8 apply)
- Record per F-01..F-04 key interaction: dropped frames per interaction, the worst LoAF, and `overCeiling()`:
  - book sheet open;
  - "Talep et" submit;
  - approvals approve;
  - find-room search;
  - Taleplerim expand;
  - sync sheet open.
- `overCeiling()` must be empty (no one-shot animation over 300 ms). A worst LoAF > 200 ms on a tap is a FAIL (M-14).

## Part C · keyboard only over F-01..F-04

No mouse, no `click()`, no `tap()`: only `page.keyboard`. After **every** Tab or arrow key, record `ringOf(page)`. A stop with `ok: false` is a finding (U-01, the UI review blocker). After **every** completed action, `document.activeElement` is not `BODY` (U-07).

**C01 · shell**
- First Tab: the skip link **"İçeriğe atla"** is visible. Enter → `document.activeElement.id === "main"` (U-14).
- `Ctrl+K` opens the palette. Typing "A 206" finds the room for staff (U-13). Enter goes there, and Esc closes the palette, back to the previous focus.
- `?` opens the shortcuts sheet, which lists only shortcuts this role can use (U-03).
- `g` then `b` → `/bookings`. `g` then `m` → `/my-bookings` (U-14).

**C02 · F-01 by keyboard (staff, then admin)**
- `/bookings?date=$D1`. Tab into the grid (one stop). Arrow keys to R1·P7. **Shift+→** extends the span to P8, and the live region announces "2 ders saati seçildi, …" (U-24). Enter opens the sheet, and focus lands inside it. Tab to the note, type, Tab to **"2 ders saati için talep et"**, Enter. Focus is not `BODY`.
- Esc from the textarea, a button and the select closes the sheet in **one** press, and focus returns to the cell (U-08).
- Admin: `/approvals`. Arrow keys or `j`/`k` through the list. The legend keys **A** (approve), **D** (reject), **R** (another room) act on the open request (persona-admin: "approvals A/D/R ✓"). After a decision, focus moves to the next request title (M-33).
- Reject dialog (`reject-dialog`): the reason radios are reachable with arrows, Tab reaches the text, and Enter on the `aria-disabled` confirm sends nothing: the message appears next to each missing field and focus goes to the first one.
- Staff: Taleplerim → Tab to **"Talebi geri çek"** → Enter → the confirm traps focus (A-20). Enter confirms. Focus returns to the row.

**C03 · F-02 by keyboard (admin)**
- The date picker: Enter opens it with focus on the **selected day**. Arrow keys move by day / week, and Enter picks (U-15).
- The recurring preview: Tab reaches each date's action control, arrows change it, and the summary updates and is announced.
- The cancel dialog: the scope radios work with arrows, Tab reaches "Gerekçe", and Enter on "İptal et" confirms. Focus goes to the next booking or the list heading.

**C04 · F-03 by keyboard (staff)**
- Every form control is reachable in visual order. The feature chips toggle with Space. Enter in any field runs the search. The result count is announced. Tab reaches each result's "Rezerve et" in order of rank.

**C05 · F-04 by keyboard (staff)**
- The tabs (Yaklaşan / Geçmiş / İptal edilen) switch with the arrow keys (`role="tablist"`). Each row checkbox toggles with Space. "Takvime eşitle" opens with Enter. The copy buttons work with Enter, and the toast is announced. "Özel bağlantıyı sıfırla" → the confirm → focus lands on the new URL field (U-22).

**C06 · tablet with a keyboard**
- Repeat C02 on 768 × 1024 with `hasTouch: true`. The same focus rings are visible (`:focus-visible` must not depend on a fine pointer).

## Mobile-specific expectations (phone 390×844)

- Language: the English strings fit. "Taslak · veritabanına henüz hiçbir şey yazılmadı" and the other long Turkish strings wrap and never truncate their meaning (spec phase19-intake.md §12). No English or Turkish label is clipped in the tab bar (MOBILE.md M-09).
- Reduced motion on phone: bottom sheets appear without the slide, and swipe-to-close still works (the gesture is fine, only the animation stops).
- An external keyboard on a phone is out of scope. Touch users rely on MOBILE.md M-02 / M-11 instead.

## Flow acceptance

1. TR mode has no English UI words and no raw keys on F-01..F-04 surfaces. EN mode has no Turkish UI words. Titles, the 404 page, plurals, dates and numbers follow the language. Mails follow the recipient's language.
2. The language comes from the profile, from the first paint, and does not flip between routes. Only TR and EN are offered.
3. Under OS or in-app reduced motion nothing moves, and every busy state still has words. Under reduced transparency every floating surface is opaque.
4. F-01..F-04 can be done with the keyboard alone. Every tab stop shows a ring, Esc closes in one press, focus never falls to `<body>` after an action, and changes are announced.

## Earlier issues to re-verify here

U-01, U-03, U-07, U-08, U-09, U-10, U-13, U-14, U-15, U-22, U-24, A-16 / A-17 / A-18 (i18n of notifications and labels), A-20, A-21, A-22, M-17 (languages), M-33, M-36, M-45, motion T1 / T4 / T13.
