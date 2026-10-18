# HB-23d design review: helper file router (§11.4 sign-off)

Reviewer: design-pro (lane HB-23d), 2026-10-18. Stack: web :3623 (prod build), API :8623, index mode ("Rehber modu"),
Güz 2026-27 active. Playwright library, Chromium, 1440 × 900 mouse and 390 × 844 touch (DPR 2), tr-TR,
Europe/Istanbul. Only the synthetic or masked files in the scratch `ux-files` folder were used; nothing was imported
(Önizle was never pressed). Screenshots: `docs/testing/round5/hb23d-design/` (60 PNG, all < 260 KB).

## BLUF

**Not signed off yet: 0 blockers, 10 major, 11 minor.** The router is calm and on-spec where it matters most: every
state has at most one primary, certainty is a word, counts carry units, the evidence is name-free ("Kesinleşen
Derslik" without the person's name), Turkish comes first, phone targets are 44 px with a 48 px primary and 16 px input,
computed contrast passes AA in light and dark, the OS drag is instant, and reduced motion gives end states. The
hand-over to `/import` works (sheet closes on the phone, focus on "Önizle", "Yardımcıdan geldi" row, ✕ returns focus to
the zone).

What blocks sign-off:
1. **Focus falls to `<body>`** in four flows: "Başka bir tür seç" / "Önceki karta dön", "Vazgeç", the expired line, and the
   hand-over to `/onboarding`. A fifth flow (the `/import` step-0 zone sending a card to the helper) puts focus on the
   guide field, not the card title.
2. **Card enter is over budget.** Opacity runs as a 400 ms WAAPI animation and reaches 1 at about 340–370 ms.
3. **A PDF read failure shows raw English**: "cannot read PDF: PdfReadError".
4. **At 32 px root text** the sheet header loses its ✕ (1440) or ⋯ (390) off-screen, and a secondary button overflows the sheet.
5. **In forced colours** the primary has no visible boundary.
6. **On the phone, `/onboarding` cuts handed file names to two letters**, and the "Yardımcıdan geldi" chip is hidden.

## §11.4 checklist

| # | Line | Result | Evidence |
|---|---|---|---|
| 1 | One primary per state; no chips under the card; secondary ≤ 2; "Bu dosya nedir?" collapsed | ✅ | Primaries counted from `text-tint-foreground` buttons per state, both sizes: detected 1, ambiguous 0 (rows are the action), unknown 1, needs_planner 1, refused 1 ("Başka dosya seç", per the §5 table), error 1 ("Tekrar dene" + text "Başka dosya seç"), expired 1, several files 1. Secondary ≤ 2 everywhere. The disclosure is collapsed, except for unknown, which is open by design. `detected-1440.png`, `detected-390.png`, `ambiguous-390.png`, `unknown-390.png`, `error-390.png`, `many-390.png` |
| 2 | No percentage or bare number; certainty is a word; counts with units | ✅ | "19 sayfa … 29 derslik", "3 etkinlik", "607 KB", "Eminim" / "Büyük olasılıkla". "+5" appears only after label lists (§5.2) |
| 3 | Turkish first, keys in tr + en, `crbs_lang_import --check` run, no enum / snake_case | ❌ | All 80 `helper.file.*` keys exist in both files. `python3 -m tools.crbs_lang_import --check` exits **1**, with 3 stale derived files (DS-15). snake_case in the UI: "exam_capacity" (DS-11). Raw exception text: "cannot read PDF: PdfReadError" (DS-07) |
| 4 | Evidence canonical labels only; no cell value; no server file name; nobody named in needs_planner | ❌ | Planning and exam evidence use canonical labels, and "Kesinleşen Derslik" carries no name ✅. The sheet title "2 - 8 Şubat Bahar Dönem Açılış" passes the allow-list ✅. The file name in the chip and live line comes from the browser File ✅. Viewer needs_planner names nobody (`needs-planner-viewer-390.png`) ✅. **Room master evidence prints raw column keys** "code, capacity, exam_capacity" (DS-11) |
| 5 | Button = effect + object (+ term); full accessible name under 640 px | ✅ (minor) | "Bahar 2026 dönemine haftalık derslik takvimi olarak aktar"; the phone shows "Bahar 2026 dönemine aktar" with `aria-label` = full label. The live line carries the full label. The label is 57 characters, over the ≤ 48 budget of §8.5 (DS-12) |
| 6 | Every drop target has a button path; paste in the composer; phone 📎 44, primary 48, composer 16 px | ❌ (minor) | 📎 "Dosya ekle" is 128 × 44 (phone) and 118 × 44 (desktop). The `/import` zone is one button (`import-kind-drop`). The page edge target has no focus stop, by design. The phone primary is 48 px tall at 390 and 320. The guide input is 16 px at 390. **Paste:** in Rehber modu the guide field ignores a pasted file (DS-14). The AI composer could not be tested (no key) |
| 7 | Focus: title → primary; hand-over → page primary; remove → zone button; never `<body>` | ❌ | ✅ After the card arrives, focus is on the title. Tab order is primary → "Başka bir tür seç" → "Kurulum sihirbazında aç" → "Bu dosya nedir?". After a chooser pick, focus is on the new title. Hand-over → `import-start` "Önizle". ✕ → zone button. A page-level drop → card title. ❌ **BODY** after "Başka bir tür seç" / "Önceki karta dön" (DS-01), after "Vazgeç" (DS-02), after expired (DS-03), and after the hand-over to `/onboarding` (DS-04). ❌ The `/import` step-0 card in the helper puts focus on the guide input (DS-05) |
| 8 | Motion rows of §9 only; OS drag instant; no stagger, no shake; reduced motion = end state; ≤ 2 blur surfaces | ❌ | ✅ The drag overlay and edge target are instant (no animation at 150 ms). No stagger and no shake. The reading shimmer is 1.6 s and starts after 400 ms. Reduced motion: card opacity only, 0 → 1 in about 115 ms, no transform, no shimmer running (`reading-1440-rm.png`). The edge pill is solid with no blur. ❌ **The card enter is 400 ms of opacity** (DS-06). The handed row animates `background-color` (DS-18, minor) |
| 9 | Rehber modu: 📎 present and working; status chip unchanged | ✅ | "Dosya ekle" sits under the guide field and works at both sizes. The chip stays "Yapay zekâ kapalı" with cards in the log |
| 10 | Target pages unchanged except the file row, `term` and the chip; preview / term_check / Uygula are the only writes | ✅ | `/import?kind=weekly-grid&term=1&year=2026&from=helper` shows the "Yardımcıdan geldi" row and the Bahar 2026 term. The recent-imports list shows no job from these runs. Two Bahar_son previews at 21:35 predate the hand-over runs and are not attributable to this review |
| 11 | Edge target absent on kiosk / public / embed / setup / login / welcome | ✅ (code) | `page-file-target.tsx:24,32-34` plus the fine-pointer and signed-in gates. On a 390 touch device the target does not appear (`dragging-page` at 390: not shown). Not exercised route by route on the stack |
| 12 | Copy review of every "Bu dosya nedir?" text (≤ 3 sentences, formal "siz") | ✅ | All 15 kinds in `files.py` `KINDS[*].explain` are 2 sentences, use "siz" and have no snake_case or percentages. Other copy nits: DS-13, DS-16, DS-20 |
| 13 | Contrast AA in light / dark / forced colours; reflow at 320 px and 200 % zoom | ❌ | Computed contrast with getComputedStyle (alpha-blended up the tree; glass approximated as its tint): every card text in light and dark is ≥ 4.5:1. The lowest is the primary label at 5.65:1; caption and evidence are ≈ 7.0:1. 320 px: no horizontal scroll, the primary is 256 × 48 (`detected-320.png`). ❌ **Forced colours:** the primary has no boundary (DS-09). ❌ **32 px root:** header controls and a secondary button are clipped (DS-08) |

## Findings

Size: S = under 1 h, M = half a day, L = more than a day.

### DS-01 · major · S: focus falls to `<body>` after "Başka bir tür seç" and "Önceki karta dön"
- **Repro:** 1440 or 390. Attach `Bahar_son.xlsx`, Tab to "Başka bir tür seç", Enter. Then focus "Önceki karta dön", Enter.
- **Expected:** focus on the new card's title, "Bu dosya hangi tür?", and back on the detected title (§10: "after a chooser pick, focus goes to the new card title").
- **Actual:** `document.activeElement === body` both times. The button that had focus unmounts.
- **Screenshot:** `other-kind-1440.png`, `other-kind-390.png`.
- **Source:** `smartsched/frontend/src/components/helper/file-router.ts:197-198` (`showKinds` / `hideKinds` change `view` without bumping `seq`), `components/helper/cards/file.tsx:598-602` (title focus runs only on a `seq` change).

### DS-02 · major · S: focus falls to `<body>` after "Vazgeç" while reading
- **Repro:** throttle the network (CDP, 40 KB/s, 1.5 s latency), attach `Bahar_son.xlsx`, focus "Vazgeç", Enter.
- **Expected:** focus on the cancelled line, or on 📎 "Dosya ekle".
- **Actual:** BODY. "Dosya okunmadı." is shown, but the Vazgeç button is gone.
- **Screenshot:** `reading-1440.png`, `reading-390.png`.
- **Source:** `components/helper/file-router.ts:171-176`, `components/helper/cards/file.tsx:628-629`.

### DS-03 · major · S: focus falls to `<body>` when the stage has expired
- **Repro:** attach `room_master.csv`, route `**/helper/files/handoff` → 410 `{"detail":{"code":"stage_expired"}}` (`isStageGone` accepts it), focus the primary, Enter.
- **Expected:** focus on "Dosyayı yeniden oku" or on the expired line.
- **Actual:** the line and "Dosyayı yeniden oku" render correctly, but focus is on BODY because the primary unmounted.
- **Screenshot:** `expired-1440.png`, `expired-390.png`.
- **Source:** `components/helper/file-router.ts:234` (and `:188`, the same path for a pick), `components/helper/cards/file.tsx:368-369`.

### DS-04 · major · S: focus falls to `<body>` after the hand-over to `/onboarding`
- **Repro:** attach `room_master.csv` and `seminar.ics` together, then press "Kurulum sihirbazında aç".
- **Expected:** focus on the page's own primary, "Başlat · 2 dosya" (§10, as `/import` already does with "Önizle").
- **Actual:** BODY at both sizes.
- **Screenshot:** `handed-onboarding-1440.png`, `handed-onboarding-390.png`.
- **Source:** `smartsched/frontend/src/components/onboarding/file-drop.tsx:53-56` (the handed files are read here, but there is no focus effect like `import-wizard.tsx:116-122`).

### DS-05 · major · S: a card adopted from `/import` step 0 does not get focus
- **Repro:** go to `/import`, open "Türünü bilmiyor musunuz?", and pick `room_master.csv`. Room master is a reviewed kind, so the card goes to the helper.
- **Expected:** focus on the card title, "Bu bir derslik ana listesi".
- **Actual:** focus on `helper-guide-input`. The sheet's open-focus runs after the card's title focus. A page-level drop does not have this problem, because classify takes time and the title wins.
- **Screenshot:** `import-step0-helper-390.png`, `import-step0-helper-1440.png` (the guide field has the focus ring). `page-drop-card-1440.png` shows the control case.
- **Source:** `components/helper/file-router.ts:111-119` (`adoptClassified` shows the card, then opens the sheet), `components/helper/helper-sheet.tsx:186-191` (focus on open).

### DS-06 · major · S: the card enter exceeds the 300 ms ceiling
- **Repro:** at 1440, sample the newest card wrapper's computed opacity and transform every frame while `karisik.xlsx` arrives. Also read `document.getAnimations()`.
- **Expected (§9):** opacity + y 6 → 0, settled within `springs.smooth` (281 ms) and ≤ 300 ms. Opacity was meant to run on `tween.fadeIn` (180 ms).
- **Actual:** a WAAPI opacity animation of **400 ms** on the `Enter` wrapper (`min-w-0`). Opacity reaches 1 at 338 ms and 369 ms in two runs, and the last change comes at 360–408 ms. The per-value `opacity: tween.fadeIn` override is not applied. The disclosure's own `tween.fadeIn` correctly runs 180 ms with a 60 ms delay. Reduced motion is correct: 100 ms of opacity only.
- **Screenshot:** `detected-1440.png` (end state). The samples are in the review's `res-extras.json`.
- **Source:** `components/helper/cards/file.tsx:142-146`. Use `transition={{ default: springs.smooth, opacity: tween.fadeIn }}` or an explicit `type: "tween"` on the opacity entry.

### DS-07 · major · S: a PDF read failure shows raw English exception text
- **Repro:** attach `belge.pdf`.
- **Expected:** the unknown card (§5), or the `error` copy "Dosya okunamadı. Tekrar deneyin ya da başka bir dosya seçin."
- **Actual:** a refused card reading **"cannot read PDF: PdfReadError"**, in the TR UI, with focus on it.
- **Screenshot:** `unknown-pdf-1440.png`, `unknown-pdf-390.png`.
- **Source:** `smartsched/backend/app/ai/helper/files.py:1447` (`i18n.localize(msg, "tr") or msg` falls back to the raw `RenderError` text from `app/council/formats_builtin.py:68`).

### DS-08 · major · M: at 32 px root text the sheet header and a card button are clipped
- **Repro:** set `document.documentElement.style.fontSize = "32px"` with a detected card open.
- **Expected:** reflow with every control reachable, and no clipping (§11.4: "Reflow … 200 % zoom").
- **Actual:**
  - At 1440, the 400 px sheet does not widen. The ✕ `helper-close` sits at x 1456–1488, outside the 1440 viewport. "Kurulum sihirbazında aç" overflows the sheet (right edge 1433 against the sheet's 1424, log `scrollWidth` 409 against 400). The title wraps one word per line, and its focus ring cuts "haftalık".
  - At 390, the ⋯ `helper-menu` sits at x 432–520, off-screen, and the status chip is clipped.
  - The footer (guide text, field, "Dosya ekle") takes about half the viewport, so the card is seen through a small slice.
  - There is no page-level horizontal scroll.
- **Screenshot:** `detected-1440-32px.png`, `detected-1440-32px-primary.png`, `detected-390-32px.png`, `detected-390-32px-primary.png`.
- **Source:** `components/helper/helper-sheet.tsx:216-246` (fixed `h-14` header row without wrap or shrink), `components/helper/cards/file.tsx:383` (secondary row).

### DS-09 · major · S: in forced colours the primary has no boundary
- **Repro:** `page.emulateMedia({ forcedColors: "active" })` and a detected card.
- **Expected:** a `ButtonBorder` / `CanvasText` outline so the primary reads as a button (§10, §12).
- **Actual:** "Bahar 2026 dönemine … aktar" renders as plain centred text. Only the card frame and title ring have borders.
- **Screenshot:** `detected-1440-forced.png`.
- **Source:** `smartsched/frontend/src/components/ui/button.tsx:27`, the shared `default` variant. Add `forced-colors:border forced-colors:border-[ButtonBorder]`, or a card-local class on `PrimaryButton` (`cards/file.tsx:174`).

### DS-10 · major · S: on the phone, `/onboarding` truncates handed file names to two letters
- **Repro:** at 390, attach two files and press "Kurulum sihirbazında aç".
- **Expected:** the person can tell the rows apart and sees "Yardımcıdan geldi".
- **Actual:** "ro…" and "se…". The chip sits inside the same truncated cell and is invisible. The ✕ names exist only in `aria-label`.
- **Screenshot:** `handed-onboarding-390.png`.
- **Source:** `components/onboarding/file-drop.tsx:138-141,154-157` (`max-w-0 truncate` on the name cell, with the chip inside it).

### DS-11 · minor · S: room master evidence shows raw column keys
- **Actual:** "Sütunlar: code, capacity, exam_capacity +5 → Derslik ana listesi" (snake_case in the UI; a non-canonical label).
- **Expected:** canonical labels such as "Kod, Kapasite, Sınav Kapasitesi". `FIELD_LABELS` already has `"exam_capacity": ("Sınav Kapasitesi", …)`.
- **Screenshot:** `expired-390.png`, `needs-planner-viewer-390.png`.
- **Source:** `smartsched/backend/app/ai/helper/files.py:988` (`[(c, c) for c in sig.room_master_cols]`).

### DS-12 · minor · S: the primary label exceeds the 48-character budget
- "Bahar 2026 dönemine haftalık derslik takvimi olarak aktar" is 57 characters (§8.5). It wraps to two lines at 1440, so the button is 52 px tall.
- **Screenshot:** `detected-1440.png`.
- **Source:** `files.py:717`. Use the short object "takvim olarak aktar", or drop "olarak".

### DS-13 · minor · S: the unknown card repeats its title as the first body sentence
- **Actual:** the title "Bu dosyayı tanıyamadım." is followed by "Bu dosyayı tanıyamadım. Excel biçiminde, ama tanıdığım sütunlar yok."
- **Screenshot:** `unknown-390.png`.
- **Source:** `files.py:1313-1317`. Make the evidence "Excel biçiminde, ama tanıdığım sütunlar yok."

### DS-14 · minor · S: a pasted file is ignored in Rehber modu
- **Repro:** focus `helper-guide-input`, then dispatch a `paste` event with a File in `clipboardData`.
- **Actual:** no entry appears (0 before and after).
- **Expected:** §10 / §8.1 say drops and 📎 work the same in Rehber modu, so paste should too.
- **Source:** `components/helper/helper-sheet.tsx:288-301` (`onPaste` sits only on the AI composer).

### DS-15 · minor · S: `crbs_lang_import --check` fails
- **Actual:** exit 1, with `locale-data.json`, `crbs_lang_data.json` and `language-coverage.md` stale. The message files are not modified in the tree, so the derived files need regenerating by the owning lane.

### DS-16 · minor · S: "15 MB" breaks across lines in the drop overlay
- **Actual:** "… görüntü · en çok 15 / MB" (`dragging-1440.png`).
- **Fix:** use a no-break space in `helper.file.formats` and `helper.file.dontKnowHint`, TR and EN (`messages/tr.json`, `en.json`).

### DS-17 · minor · S: the handed row cuts the file name on the phone
- **Actual:** "Bahar_son…." because the chip takes the row width (`handed-import-390.png`, `import-step0-detected-390.png`).
- **Fix:** wrap the chip under the name below 640 px.
- **Source:** `components/helper/handed-file-row.tsx:322-330`.

### DS-18 · minor · S: the handed-row highlight animates `background-color`
- **Actual:** `transition-colors duration-(--dur-base)` animates `background-color`. The motion skill §4 allows transform and opacity only.
- **Fix:** fade a `bg-tint-soft` overlay's opacity instead.
- **Source:** `handed-file-row.tsx:317-318`.

### DS-19 · minor · S: the step-0 drop zone can flicker while dragging (code reading, not reproduced)
- `onDragLeave` clears `over` on every child leave, and there is no depth counter, unlike `SheetDropZone`.
- **Source:** `components/import/kind-drop.tsx:26-31`.

### DS-20 · minor · S: the step-0 detection on `/import` refers to a button that is not there
- **Actual:** it repeats the helper warning "… Düğme dosyanın dönemine aktarır." The page has no such button, and its term select already says Bahar 2026.
- **Screenshot:** `import-step0-detected-390.png`.
- **Fix:** use a page variant, for example "Dosya Bahar 2026 diyor; hedef dönem buna göre seçildi."
- **Source:** `components/import/import-wizard.tsx:245-246`.

### DS-21 · minor · S: the KVKK guard refusal shows a developer path to the person
- **Actual:** "… maskelenmiş kopyayı kullanın ($REC_WORKDIR/fixtures)." This was seen once in the helper card after `/import` step 0 with `final_planlama_listesi_2026_v2.xlsx`. The screenshot was later overwritten and not retaken, so the file would not be uploaded again. This happens on test stacks only.
- **Source:** `smartsched/backend/app/core/kvkk_guard.py:130-132`.

## Notes for the orchestrator

- **KVKK:** the scratch file `final_planlama_listesi_2026_v2.xlsx` was refused by the guard: "dosyada maskelenmemiş 2 kişi
  adı var". The guard refused before staging, so no stage, card data or job was created. It was uploaded once, through
  the `/import` step-0 zone, and not again. Please re-mask that file before testers use it.
- Not on the stack yet: the working tree already changes `helper.file.privacyRead` / `privacy` (they now mention "Uygula").
  The build on :3623 predates this, so that copy was not reviewed live.
- Not testable here: the AI composer paste (no key), the chooser `layoutId` tint travel timing (the probe was unreliable
  under load; the end state is in `picked-1440.png` and `picked-1440-rm.png`), and the users CSV and CRBS dump routes.
- Contrast method: text colour alpha-blended over the stacked backgrounds up to the first opaque ancestor. Glass
  surfaces were approximated by their tint, so the values are an estimate. Every value cleared 4.5:1 with margin
  (lowest 5.65).

## Re-check (round 2)

Re-checked 2026-10-18 on the rebuilt stack (:3623 / :8623), with the same accounts, files and method. Only the majors
were re-checked, at the sizes and modes where they were found. Screenshots end in `-r2`. The raw results are in the
review scratch file `res-r2.json`.

**BLUF: 8 of 10 majors are fixed.**
- DS-04 is still open (focus lands on `<main>`, not "Başlat") and is downgraded to minor, because focus is no longer lost.
- DS-08 is fixed for what it reported, but the re-check found a **new major**, DS-22: at 32 px root text the helper log
  viewport shrinks to 48 px (390) or 92 px (1440).
- One new minor, DS-23.
- **Still open: 0 blocker, 1 major (DS-22), 13 minor.** That is the 11 minors from round 1 (not re-checked), plus
  DS-04 (downgraded) and DS-23.

| Id | Round 2 | Evidence (1440 / 390) |
|---|---|---|
| DS-01 | ✅ fixed | "Başka bir tür seç" → focus on the first radio, "Planlama listesi". "Önceki karta dön" → the detected title. Same at both sizes. `other-kind-1440-r2.png`, `other-kind-390-r2.png` |
| DS-02 | ✅ fixed | "Vazgeç" → `helper-file-cancelled`, "Dosya okunmadı.", at both sizes. `reading-cancel-1440-r2.png`, `reading-cancel-390-r2.png` |
| DS-03 | ✅ fixed | 410 `stage_expired` on hand-over → focus on "Dosyayı yeniden oku"; the page stays on /dashboard. `expired-1440-r2.png`, `expired-390-r2.png` |
| DS-04 | ❌ open, now minor | After the hand-over to `/onboarding?from=helper`, focus is on `<main>` at both sizes, not on "Başlat · 2 dosya" (§10: the page's own primary). It is no longer `<body>`, so it is downgraded to minor. `handed-onboarding-1440-r2.png`, `handed-onboarding-390-r2.png`. Source: `components/onboarding/file-drop.tsx`; add a hand-over focus effect like `import-wizard.tsx:116-122` that targets the start button |
| DS-05 | ✅ fixed | `/import` step 0 with `room_master.csv` → focus on the card title "Bu bir derslik ana listesi" at both sizes. `import-step0-helper-1440-r2.png`, `import-step0-helper-390-r2.png` |
| DS-06 | ✅ fixed | Card enter: opacity reaches 1 at 139 ms, and the last opacity or transform change is at 276 ms (≤ 300). No 400 ms WAAPI animation is left. Reduced motion has only 0.01 ms opacity, with no transform |
| DS-07 | ✅ fixed | `belge.pdf` → "Bu PDF dosyasını okuyamadım. Dosya bozuk ya da korumalı olabilir; başka bir kopyasını deneyin." plus one primary, "Başka dosya seç". No exception text. `unknown-pdf-1440-r2.png`, `unknown-pdf-390-r2.png` |
| DS-08 | ✅ fixed (as reported) | At 32 px the header wraps and the controls are inside the viewport: ✕ at x 1144–1176 and ⋯ at x 1040–1128 (1440); ✕ at x 16–104 and ⋯ at x 16–104 (390). Card buttons stay inside the sheet: log `scrollWidth` equals `clientWidth`, and there is no page horizontal scroll. See DS-22 for what remains. `detected-1440-32px-r2.png`, `detected-1440-32px-buttons-r2.png`, `detected-390-32px-r2.png`, `detected-390-32px-buttons-r2.png` |
| DS-09 | ✅ fixed | Forced colours: the primary now has a `1px solid` border in the system colour. `detected-1440-forced-r2.png` |
| DS-10 | ✅ fixed (phone) | At 390, both handed rows show the full name ("room_master.csv", "seminar.ics") and "Yardımcıdan geldi", with no clipping. See DS-23 for desktop |

**Hand-over now closes the sheet on desktop (UX-02).** This harms nothing in the §11.4 checklist:
- Focus still lands on "Önizle".
- The file row is there.
- Re-opening the helper shows the entry collapsed to "Haftalık derslik takvimi · sayfası açıldı". The thread isn't lost, and no stage is deleted.
- §8.1 calls the desktop sheet non-modal but does not require it to stay open.
- Evidence: `handed-import-1440-r2.png`.

### DS-22 · major (new) · M: at 32 px root text the helper log is a 48 to 92 px slot
- **Repro:** open a detected card (`Bahar_son.xlsx`), then set `document.documentElement.style.fontSize = "32px"`.
- **Expected:** reflow at 200 % keeps the card usable, with the log taking most of the height and the footer staying compact.
- **Actual:** in a 844 px tall phone viewport, the wrapped header is 272 px, the footer is 496 px and the **log is 48 px**. At 1440 × 900 the header is 168 px, the footer 496 px and the log 92 px. The card is 1,572 px tall, so the person reads it through a slot one or two lines high. At 16 px the log is 560–568 px.
- **What fills the footer:** the guide lead, the 88 px guide field, "Dosya ekle", and the new privacy caption under it.
- **Screenshot:** `detected-390-32px-r2.png`, `detected-1440-32px-buttons-r2.png`.
- **Suggested fix:** at large text, hide the guide lead and the caption, or let the footer scroll with the log. Keep the header to one row by moving the status chip into the ⋯ menu.
- **Source:** `components/helper/helper-sheet.tsx:216-246` (header) and `:271-300` (footer).

### DS-23 · minor (new) · S: on desktop `/onboarding`, handed names are cut and the chip is hidden
- **Actual:** at 1440, the name cell is 212 px wide while the row has spare width. It reads "room_master.csv…" and "seminar.ics…", and "Yardımcıdan geldi" sits past the ellipsis, so it can't be seen.
- **Screenshot:** `handed-onboarding-1440-r2.png`.
- **Source:** `components/onboarding/file-drop.tsx:138-141,154-157`. Apply the phone layout (chip on its own line) at every width.

## Re-check (round 3)

Re-checked 2026-10-18 after the container restart: signed in again, same method. Screenshots end in `-r3`. The raw
results are in the review scratch file `res-r3.json`.

**BLUF: DS-22, DS-04 and DS-23 are fixed.** The new inline "rejected type" line and the "stage replaced" line pass the
copy and contrast checks. One new minor, DS-24 (the card title wraps one word per line at 32 px on the phone).
**Still open: 0 blocker, 0 major, 12 minor.** That is the 11 minors from round 1 (not re-checked) plus DS-24.

| Id | Round 3 | Evidence |
|---|---|---|
| DS-22 | ✅ fixed | At 32 px the whole sheet scrolls (`helper-sheet` scrollHeight 1280 against 844 at 390, and 1159 against 756 at 1440). The log keeps **464 px (390) and 495 px (1440)**, up from 48 and 92 px. The card can be read through them, and the primary, "Başka bir tür seç" and "Kurulum sihirbazında aç" are reachable by scrolling. ✕ and ⋯ come into view when focused, at both sizes. Nothing sticks out of the sheet and there is no page horizontal scroll. The normal 16 px layout is unchanged: header 56, log 560 / 568, footer 204 px, one log scroller. `detected-390-32px-r3.png`, `detected-390-32px-primary-r3.png`, `detected-1440-32px-r3.png`, `detected-1440-32px-primary-r3.png`, `detected-390-32px-header-r3.png`, `detected-390-r3.png`, `detected-1440-r3.png` |
| DS-04 | ✅ fixed | After the hand-over to `/onboarding?from=helper`, focus lands on `onboarding-start` "Başlat · 2 dosya" at 1440 and 390. `handed-onboarding-1440-r3.png`, `handed-onboarding-390-r3.png` |
| DS-23 | ✅ fixed | At 1440 both handed rows show the full name ("room_master.csv", "seminar.ics") with no clipping, and "Yardımcıdan geldi" sits inside the cell. The phone layout is unchanged and still correct. `handed-onboarding-1440-r3.png` |

**New "rejected type" line on `/import` step 1** (`/import?kind=exam-list`, `belge.pdf` picked through the zone's file
chooser): ✅
- **Copy:** "belge.pdf bu adımda içe aktarılamaz: yalnızca Excel dosyaları (.xlsx) alınır. Türünü bilmiyorsanız İçe aktar
  sayfasının başındaki "Türünü bilmiyor musunuz?" alanına bırakın." Two sentences, formal "siz", no enum, and it names
  the way out.
- **Contrast:** `--status-infeasible-fg` on the card is **7.27:1** at 13 px.
- **Behaviour:** `role="alert"`, shown next to the zone. Focus stays on the zone button at both sizes. An earlier BODY
  reading came from `setInputFiles` without a click.
- Screenshots: `import-rejected-1440-r3.png`, `import-rejected-390-r3.png`.

**New "stage replaced" line (UX-27)** (hand-over answered 410 `{"detail":{"code":"stage_replaced"}}`): ✅
- **Copy:** "Başka bir pencerede seçtiğiniz dosya bunun yerini aldı. Bu dosyayı kullanmak için yeniden okuyun." Two
  sentences, formal, and it explains the cause.
- **Contrast:** `--label-2` on the card well is **7.04:1** (1440) and **7.99:1** (390) at 12 px.
- **Behaviour:** focus lands on "Dosyayı yeniden oku", the single primary.
- Screenshots: `replaced-1440-r3.png`, `replaced-390-r3.png`.

### DS-24 · minor (new) · S: at 32 px on the phone the card title wraps one word per line
- **Actual:** at 390 with 32 px root text, the title and the certainty badge share one row. The title column gets about
  40 px, so "Bu / bir / haftalık / derslik / takvimi" wrap word by word. "haftalık" and "derslik" spill past the title's
  focus ring.
- **Impact:** the text stays readable and isn't cut off, so this is minor.
- **Screenshot:** `detected-390-32px-r3.png`.
- **Fix:** let the badge wrap under the title when the row is narrow (as §8.2 already shows for phones), for example
  `basis-full` on the title below a container width.
- **Source:** `components/helper/cards/file.tsx:157-164` (`Frame` header row).
