# Helper ("Yardımcı") design audit: HB-07 sign-off and HX-12 (2026-10-18)

Ledger `hx-design-2026-10-18` · product designer · branch `claude/focused-wright-ktt0ss` · docs only, no app code.

Scope: `smartsched/frontend/src/components/helper/**` (palette groups, trigger, sheet, Rehber modu, cards, Göster,
status chip, memory, admin and faculty views), read against `docs/design/v3/helper.md` (v3.1) and the HB-A contract
(`API.md`, scratchpad). Method: code reading, `node scripts/check-design.mjs` (passed: 160 contrast pairs, 0 failures),
contrast computed from `src/app/globals.css` tokens, and Mobbin references. The resource rule (COMMON.md, 2026-10-18)
forbids a stack and Playwright, so **no screenshots**; the e2e checks each finding needs are listed in §5.

## 1. BLUF

- **Blockers: 0. Major: 8. Minor: 14.**
- HB-07: the field list is signed off. All 8 HX differences are accepted: 5 as they are (one with a condition, M1) and
  3 deferred until HB-D lands (helper.md §17.1).
- The build follows the spec well: tokens and type scale only, 44 px targets on touch, 16 px inputs, reduced motion and
  reduced transparency handled, focus returns, TR-first copy in formal "siz".
- The major findings are:
  - "Göster" can ring a control hidden under the desktop sheet (M1).
  - Focus is lost after "Vazgeç" (M2).
  - The done/failed disc fails contrast in dark mode (M3).
  - Rehber modu, the default mode, stacks full cards with several primary buttons (M4).
  - A form button "Rezerve et" that does not book (M5).
  - An expired card that keeps a "Yenile" button after refresh (M6).
  - "Geçmişi sil" also deletes notes (M7).
  - "token" in the faculty manager's view (M8).

## 2. References (Mobbin, web)

| Pattern | Reference | What we take |
|---|---|---|
| Palette rows: one line, one action per row, grouped headings | [Langdock command palette](https://mobbin.com/screens/ccc23b42-9e5c-4e43-bc47-89f37bcf9ae7), [Superhuman Command](https://mobbin.com/screens/85dc5994-9360-428d-9092-7425e070ed7f), [Gumloop palette](https://mobbin.com/screens/e9e0911a-09a4-4c72-bb98-6ac9357fa590) | Search hits are rows, not cards; the key hint sits at the row's end (basis for M4) |
| Assistant home with starters as rows / chips | [ClickUp Brain](https://mobbin.com/screens/03de3331-f424-43b6-85ab-05fb5951549c), [Resend Help](https://mobbin.com/screens/27ace4ea-bb61-4141-b7aa-ae5551b66dfd) | 3 starters + one composer, nothing else competing (matches §6.2) |
| Non-modal right assistant panel over the page | [HoneyBook assistant panel](https://mobbin.com/screens/fa243020-70b3-41a7-94c1-50e5d51c7355) | The page stays usable, but the panel covers the right column: right-aligned page actions sit under it (basis for M1) |
| Destructive confirm names what is deleted | [Origin "Delete chat"](https://mobbin.com/screens/7ed7c033-bdcb-49a3-92b9-06b7dae8dac0), [LangChain delete assistant](https://mobbin.com/screens/d90e3a1b-a6ba-4937-b2ee-dd9f545a8c34) | The title and the button name the object and say it cannot be undone (basis for M7) |

## 3. HB-07: decisions on HX's 8 differences

Recorded in `docs/design/v3/helper.md` §17.1. The affected sections (§0, §2.3, §2.4, §3.1, §3.3, §4.2, §4.3, §5.1,
§10, §12, A3) were edited to match.

| # | Difference | Decision | One-line reason |
|---|---|---|---|
| 1 | `path` / `steps` as text, not crumb keys | Accept | The server text is pattern-checked and TR/EN paired; routes and permissions still come from the client's link map |
| 2 | `entity.kind` = `booking \| approval_request \| note` | Accept | Covers every v1 write; "Aç" goes through `feature_id` |
| 3 | `choice` has no counter; "{n}. soru" from the second choice | Accept | The server cannot know the total, so "1 / 2" would be a guess |
| 4 | `confirm.args` prefills "Değiştir" | Accept | One source of truth; unresolved values stay visible |
| 5 | "Göster" without the 25 % scrim; the ring alone, the control stays clickable | Accept (condition M1) | A scrim adds a third layer beside the non-modal sheet; the ring is 5.6:1 light / 6.9:1 dark |
| 6 | "Son yaptıklarınız" left out | Accept as deferred (HX-15) | Starters + Git cover the empty palette until HB-D's endpoint lands |
| 7 | "Bu sayfa: …" chip left out | Accept as deferred (HX-16) | Without context, requests fall back to `choice` / `form`, which is safe |
| 8 | No "Hatırla" on cards | Accept as deferred (HX-17) | Notes are still only created by an explicit act (Profil › Not ekle) |

## 4. Findings (HX-12)

Paths are relative to `smartsched/frontend/src/` unless they start with `messages/`.

### 4.1 Blockers

None.

### 4.2 Major

| ID | Area | Where | Finding | Fix |
|---|---|---|---|---|
| M1 | Göster / layout | `components/helper/show-me.tsx:43-58`; `components/helper/helper-sheet.tsx:323` | On desktop the sheet is fixed over the right 360–400 px, and the ring (`z-[10002]`) draws **above** the sheet. A right-aligned target (page-header actions such as the planned `admin-users-invite`, `runs-publish`, `bookings-export`) is ringed but hidden and cannot be clicked. This breaks "Nerede? → Göster" for those controls | After `waitForAnchor`, compare `el.getBoundingClientRect()` with `[data-helper-sheet]`'s rect. If they intersect, call `closeSheet()` and keep `reopen: true`, so "Yardımcıya dön" reopens the sheet with the thread (the same path as on phones). Add an e2e check with a top-right anchor at 1280 and 1440 |
| M2 | Focus | `components/helper/use-helper-runner.ts:268`; `components/helper/cards/confirm.tsx:68,80`; `components/helper/cards/form.tsx:185`; `components/helper/cards/choice.tsx:30` | "Vazgeç" sets `phase: cancelled`, so the focused button unmounts and **focus falls to `<body>`** (COMMON rule 6). The confirm button also gets `disabled={busy}` while it is focused, so focus drops until the result arrives | In `cancel()` call `focusEntry(entry.key)` (the entry root has `tabIndex=-1`), or put `data-focus-target` on the "Vazgeçildi." line. On the busy button use `aria-disabled` and ignore clicks instead of `disabled` |
| M3 | Contrast (dark) | `components/helper/cards/result.tsx:48` | The done/failed disc is `bg-status-*-fg text-white`. Dark: white on `#63e08b` is **1.67:1** and on `#ff9d95` is **2.0:1**, below 3:1 for a meaningful graphic (WCAG 1.4.11). Light is fine (7.3:1) | Use `text-(--mat-thick-solid)` for the glyph: 9.4:1 / 7.8:1 in dark and white in light, or add an `--on-status-solid` token. Add both pairs to `check-design`'s contrast list |
| M4 | Simplicity | `components/helper/guide.tsx:66`; `components/helper/cards/status.tsx:24`; `components/helper/cards/nav.tsx:50` | Rehber modu (the **default** mode on a fresh install) and every `limit` / `refusal` / `error` card render each hit as a full `nav` card. `compact` only changes the padding. Up to 12 cards, each with "Göster" (primary) + "Sayfayı aç" (+ "Burada yap"), make a wall of primary buttons: "where do I click?" | A compact `nav` is one 44 px (56 px on phones) row: icon, title, grey path, trailing "Göster" hint (as the palette's `NavRow`). A tap does Göster when an anchor exists, else opens the page. At most 6 rows; the full card only for a single answer |
| M5 | Copy / explicit writes | `components/helper/cards/form.tsx:158` | The R1 form's primary button reads the action's verb, "Rezerve et", but it only asks for the preview. The person then meets "Rezerve et: A 204 · …" again. In request mode the effect is "Talep et", not "Rezerve et". A button must name its effect (§9 rule 10) | R1 and R2 forms: primary "Devam" (`helper.form.continue`) or "Önizle". The effect verb lives only on the `confirm` card. Update helper.md §4.2 `form` row (proposed in HX-18) |
| M6 | One card in focus | `components/helper/cards/confirm.tsx:36` | `expired` is also true for `parked` cards. After "Yenile" (which parks the old card) or a newer card, a timed-out card still shows its full frame and a primary "Yenile", so two cards ask for action (§4.1 rule 7) | `expired = phase === "expired" \|\| (timedOut && phase === "pending")`. Parked cards keep the one-line view (add "· eskidi" to that line when timed out) |
| M7 | Destructive copy | `components/helper/memory/memory-section.tsx:83,182,200`; `messages/tr.json` `helper.memory.deleteHistory*` | "Geçmişi sil" under "Konuşma geçmişi" calls `DELETE /helper/notes?history=true`, which also **deletes every note**. Only the dialog body says so, and it cannot be undone | Now: the button and dialog title read "Notları ve geçmişi sil" / "Notlarınız ve konuşma geçmişiniz silinsin mi?". Then (HB ask): a threads-only `DELETE /helper/threads`, so "Geçmişi sil" does what it says, and notes keep their own "Tüm notları sil" (`helper.memory.deleteAll`, unused today) |
| M8 | Jargon | `messages/tr.json` `helper.faculty.total`, `.allocation`, `.deptRow`, `.deptShare`, `.shareSum`, `.trend` (shown by `components/helper/admin/faculty-usage.tsx`) | The faculty manager (an academician, not a planner) reads "token" in every sentence. That breaks §9 rule 7 and gives no sense of scale | Lead with share and requests: "Bu ay fakülte payının %42'si kullanıldı (1.240 istek)." Show tokens only under "Gelişmiş" and in the split editor's field hint ("Aylık pay (yapay zekâ birimi)") |

### 4.3 Minor

| ID | Area | Where | Finding | Fix |
|---|---|---|---|---|
| m1 | Contrast | `components/helper/cards/frame.tsx:32` | `tone="muted"` uses `opacity-80`: the "Vazgeçildi." footnote (`label-3`) drops to 4.33:1 in light | Drop the opacity and use `text-label-2` for the state line; mute with the parked one-line view instead |
| m2 | Forced colours | `components/helper/helper.css:40-46` | "Düşünüyor…" uses transparent `-webkit-text-fill-color` with a gradient clip, which can vanish in forced-colours mode | `@media (forced-colors: active) { .helper-shimmer { animation: none; background: none; -webkit-text-fill-color: CanvasText; } }` |
| m3 | 16 px inputs | `components/helper/memory/memory-section.tsx:159`; `components/helper/admin/faculty-usage.tsx:63` | `text-base sm:type-callout` can drop below 16 px on a ≥ 640 px touch tablet | `text-base pointer-fine:sm:type-callout` (as `textarea.tsx` does) |
| m4 | i18n | `components/helper/cards/form.tsx:53-60` | The "Değiştir" form's labels (Salon, Tarih, Ders saati, Amaç) are literal TR/EN in code, not message keys (COMMON rule 6) | Keys `helper.form.fields.{room,date,period,notes}` + `translate()` for both languages |
| m5 | Form a11y | `components/helper/cards/form.tsx:91,176` | Invalid fields get `aria-invalid`, but the error line is not linked (§8: `aria-describedby`) | Give the alert an id and set `aria-describedby` on every missing field |
| m6 | Announcements | `components/helper/use-helper-runner.ts:222-223` | After confirm, the result is announced up to three times: toast, the log's polite region, and focus on the result line | While the sheet is open, skip the toast (or give it no live region). Toast only when the sheet closed before the result |
| m7 | Empty state | `components/shell/command-palette.tsx:160`; keys `helper.palette.none`, `helper.palette.offHint` unused | With AI off, a palette search with no hits shows the old text and no next step (§2.3, §9 rule 14) | With no hits: `helper.palette.none`, plus `offHint` when `/helper/status` is index mode |
| m8 | Dead keys | `messages/*.json` `helper.where.stepLabel`, `helper.palette.showKeys`, `helper.notAllowed`, `helper.memory.ask`, `helper.memory.delete`, `helper.memory.deleteAll` | Unused strings drift from the UI | Wire `deleteAll` (M7) and `memory.ask` (HX-17); delete the rest |
| m9 | Copy tone | `messages/tr.json` `helper.card.fromIndex` "Dizinden", `helper.status.fallbackBody` "…dizinden geldi", `helper.palette.askBlocked` (em dash), `helper.shortcut.roomDay` "Salonun günü" | "Dizin" is an internal word. The limit text has two punctuations for the same sentence. "Salonun günü" is unclear | "Site rehberinden" / "…bu yanıt site rehberinden geldi"; "Yardımcı bu ay sınırda; arama ve kısayollar çalışıyor."; "Salonun gün programı: {what}" (EN twins: "From the site guide", "A room's day plan") |
| m10 | Layout spec | `components/helper/helper-sheet.tsx:41` | Below 1024 px the sheet is always full screen; §12 had a right sheet at 640–1023 | Accepted as built; helper.md §12 updated (one tablet/phone layout, simpler) |
| m11 | Motion | `components/helper/helper-sheet.tsx:298-300` | Phone sheet: no drag-to-dismiss (§7). Exits use literal `0.12` / `0.18` s with no `--ease-in` | HX-11 lane: `drag="y"` with flick dismiss, the exit from `dur.fast` + `ease.in` tokens; reduced motion keeps the 100 ms fade |
| m12 | Göster on phones | `components/helper/show-me.tsx:52,112` | The target scrolls to the centre while the docked step card is ≥ 200 px tall; §11 D asks for the upper half | `block: desktop ? "center" : "start"` with a `scroll-margin-top` of the top bar + 16 px |
| m13 | Chip size | `components/helper/status-chip.tsx:126` | On touch, `size="sm"` makes the 24 px chip a 44 px tall pill in the 56 px header (correct target, heavy look) | Keep `h-6` and use `coarseHitArea` (`ui/hit-area.ts`) for the 44 px area |
| m14 | Focus after "Değiştir" | `components/helper/cards/confirm.tsx` (Değiştir handler) → `use-helper-runner.ts` `focusEntry` | Focus lands on the new form card's root, not on its first field | Mark the first field `data-focus-target` in `FormView` |

### 4.4 Passes (checked in code)

| Check | Evidence |
|---|---|
| Tokens / type scale | Only `type-*` utilities and colour tokens; `text-base` only for 16 px inputs; `check-design` passed (0 failures) |
| 44 px targets on phones | `Button` sm/xs `pointer-coarse:min-h-11`, md = 44 px on coarse (`--control-h-md`); palette rows `min-h-11` / `max-sm:min-h-14`; choice rows, chips, starters `min-h-11`; header icons `size-11`; phone primary `max-sm:h-12` |
| 16 px inputs | `Input` / `NativeSelect` `pointer-coarse:text-base`, the composer's `[&_textarea]:text-base`, the guide field `text-base`, the palette input `text-base` (see m3 for the two exceptions) |
| Focus order | Phone: ✕ first, focus trap; desktop: the composer or guide field on open, Esc closes, F6 page ↔ sheet, close returns to the opener or `main h1`; confirm → result line; undo → the new result line (see M2, m14) |
| Contrast | Body and labels ≥ 4.5:1 in both themes (`label-3` 6.9:1 light, 6.7:1 dark); warning text 7.5:1; ring 5.6:1 / 6.9:1 (see M3, m1) |
| Reduced motion | Sheet becomes a 100 ms fade (`tween.reduced`); CSS card-enter, check and shimmer off under the media query and `data-motion="reduced"`; the ring jumps; scroll `auto` |
| Reduced transparency | Sheet `--mat-thick-solid` under the media query and `data-transparency="reduced"`; phone sheet and step card always opaque |
| Turkish copy | Formal "siz", no exclamation marks or emoji, sentences ≤ 20 words, CRBS words (salon, ders saati, dönem) |
| One primary per card | `confirm`: effect button + "Değiştir" + "Vazgeç"; `form`: one submit; `result`: no competing primary; admin tab: "Kaydet" only, rest behind "Gelişmiş" (exceptions M4, M6) |

## 5. E2E TO RUN (single e2e lane; this lane ran none)

1. M1: an anchor top-right on `/admin/users` at 1280 and 1440. "Göster" from the open sheet must leave the target
   visible and clickable.
2. M2: keyboard "Vazgeç" on confirm, form and choice. `document.activeElement` is never `body`.
3. M3: dark mode, result card. Screenshot the disc and check contrast.
4. M4: Rehber modu (`mode: index`) at 390 and 1440, typing "rezervasyon": count primary buttons in view (target ≤ 1).
5. HX-13 persona runs as planned (helper.md §15).

## 6. Proposed follow-up tickets

| Ticket | Lane | Content |
|---|---|---|
| HX-15 | HX-F | "Son yaptıklarınız" palette group on HB-D's recent-actions endpoint (§2.3) |
| HX-16 | HX-F | "Bu sayfa: …" context chip on HB-D's `context` field (§2.4) |
| HX-17 | HX-F | "Hatırla" / "Hayır" on HB-D's remember card; wire `helper.memory.ask` (§4.3) |
| HX-18 | HX-F | Fix M1–M7 and m1–m8, m12–m14 (components/helper/**, messages); helper.md §4.2 `form` row to "Devam / Önizle" |
| HX-19 | HX-M | m11: phone drag-to-dismiss, exit tokens |
| HB-21 | HB | Threads-only `DELETE /helper/threads` (M7); faculty usage as share % + requests (M8, with `helper.faculty.*` copy) |
| HX-12b | design + e2e | The ROADMAP's 12-screen simplicity audit at 1440 / 390 with screenshots, once stacks are allowed again |
