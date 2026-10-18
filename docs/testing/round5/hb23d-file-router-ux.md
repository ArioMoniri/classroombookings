# HB-23d: helper file router, end-to-end UX test (round 5)

- Date: 2026-10-18 (Europe/Istanbul), tester: user-tester lane HB-23d
- Stack: web http://127.0.0.1:3623 (prod build), API http://127.0.0.1:8623, helper in "Rehber modu" (no AI key)
- Driver: Playwright library, Chromium. Desktop 1440×900 with a mouse. Phone 390×844 with isMobile, hasTouch and DPR 2. Locale tr-TR, timezone Europe/Istanbul
- Files: only the masked or synthetic set in `scratchpad/ux-files`. No person names appear in this report. People are named by role
- Screenshots: `docs/testing/round5/hb23d-ux/` (PNG, each under 400 KB)
- Spec: `docs/design/v3/helper-file-router.md` §0, §5, §8, §10, §11.3. Simplicity principle: `docs/agents/briefs/COMMON.md`

## BLUF

- **The core promise mostly works.** At 1440 the admin who "doesn't know the file" drops `Bahar_son.xlsx` on any page. In about 5 s he gets one clear card: "Bu bir haftalık derslik takvimi · Eminim", the evidence, and the term warning. One filled primary takes him to `/import` in about 10 s, with Bahar 2026 preselected, the file row ("Yardımcıdan geldi") and focus on "Önizle". The preview is ready about 28 s after the drop, and nothing is written before "Uygula". The `/import` "Türünü bilmiyor musunuz?" zone is the calmest path: the result is inline, with no sheet and no card, in 8 s. On the phone, the 📎 path (search › "dosya" › "Dosya ekle ve ne olduğunu öğren") reaches the same page in 15 s, with a 48 px primary, no horizontal scroll and a 16 px composer.
- **1 blocker.** U3 cannot be done with the supplied masked exam list. The test stack's KVKK guard refuses `final_planlama_listesi_2026_v2.xlsx` ("dosyada maskelenmemiş 2 kişi adı var") on both the helper and `/import`. The instructor column holds initials only. Either the guard gives a false positive or there is masking residue in the fixture (a possible KVKK issue). This needs checking.
- **8 major.**
  - (a) On desktop the sheet stays open after the hand-over and covers the target page's primary: "Önizle" is half hidden; "Uygula", "Başlat · N dosya" and "Derslik ana listesini uygula" are fully hidden.
  - (b) The room-master hand-over loses the file, so the page shows an empty drop zone. This affects admin and the rooms-only admin alike.
  - (c) Focus falls to `<body>` after the hand-over to `/onboarding`, Derslerim, Derslik bul and room master.
  - (d) The users-CSV dialog puts focus on the ✕ "Dosyayı kaldır".
  - (e) The academician's ".ics → Takvimime ekle" ends in a dead end ("Takvim aktarımı kurumunuzda kapalı").
  - (f) `belge.pdf` shows the raw English "cannot read PDF: PdfReadError".
  - (g) Palette "Nerede? › Dosyanın ne olduğunu öğren › Göster" doesn't open the helper. It says "Bu düğme şu an bu sayfada görünmüyor".
  - (h) The `/import` step-1 probe shows "İçe aktarmaya hazır" for a file the guard refuses. The 422 is then shown as "Dosya okunamadı. Doğru Excel şablonu mu?".
- **17 minor.** These are copy and polish items: grammar of the "farklı düzende" title, the dangling "Sizin için:", the "Düğme …" wording, a privacy line that mentions Önizle on cards that have none, a duplicated "tanıyamadım", double live announcements, a page scroll jump when the sheet opens, and so on.
- **Simplicity:** every card state had exactly **one** filled primary and at most two text secondaries. "Bu dosya nedir?" was collapsed. The certainty is a word, never a percentage. None of the screens felt "overwhelming". The "where do I click?" moments all come from the sheet covering the page's primary (UX-02) and from the room-master page asking for the file again (UX-03).
- **Build vs source:** the prod build at :3623 lags the source tree. For example, the privacy line on screen reads "…Önizle'ye basana kadar hiçbir şey kaydedilmez.", while `messages/tr.json` now has "…içe aktarma kaydına dönüşmez; veriler yalnızca Uygula ile kayıtlara işlenir.". The line numbers below are from the current tree.

## Tasks

Time = seconds from the task start (file drop, or the first tap for phone tasks) to the right target page with the file row. Discovery time is judged separately for the "doesn't know" admin. Wrong clicks are counted for the persona's natural path.

| # | Persona | Viewport | Path the persona took | Time to card / target | Wrong clicks | One primary obvious? | Result | Severity |
|---|---|---|---|---|---|---|---|---|
| U1 | Admin, doesn't know the file | 1440 mouse | OS drag of `Bahar_son.xlsx` onto the dashboard → edge pill "Yardımcıya bırakın: ne olduğunu söyleyeyim" → card → primary | card 5.0 s · `/import?kind=weekly-grid&term=1&year=2026&from=helper` 10.1 s · preview 28 s | 0 | Yes ("Bahar 2026 dönemine haftalık derslik takvimi olarak aktar") | Pass. Term warning seen; Bahar preselected; no import before Uygula. The sheet covers the "Uygula" button on the preview | major (UX-02) |
| U1b | Admin (alternative: "İçe aktar" in the sidebar) | 1440 | `/import` → drops onto "Türünü bilmiyor musunuz? Dosyayı bırakın, biz söyleyelim." | target 8.2 s (inline, no sheet) | 0 | Yes ("Önizle", focused) | Pass, the calmest path | minor (UX-24) |
| U1c | Admin (alternative: ⌘K "dosya" + Enter) | 1440 | Enter on the default row "Dosya içe aktar…" → `/import` → as U1b | +1 detour | 1 | n/a | Pass, but the router row is last in the palette | minor (UX-19) |
| U1d | Admin (alternative: ⌘K "bu dosya ne" → Nerede? › Göster) | 1440 | "Göster" → popover "Bu düğme şu an bu sayfada görünmüyor…" | did not reach the helper | 1–2 | No | Fail on this path | major (UX-08) |
| U2 | Admin, file in the phone's Files app | 390 touch | 🔍 → types "dosya" → "Dosya ekle ve ne olduğunu öğren" → native picker → card → primary (short label "Bahar 2026 dönemine aktar", 48 px) | card 10.2 s · target 15.2 s | 0 | Yes | Pass. No zoom, scrollWidth 390, composer 16 px, sheet closes, focus on "Önizle" | — (UX-18 n/a) |
| U3 | Planner, Güz active | 1440 sheet drop + 390 📎 + `/import` | `final_planlama_listesi_2026_v2.xlsx` | refusal card at 5 s | n/a | Only "Başka dosya seç" | **Blocked.** KVKK refusal on the masked fixture. Direct `/import` upload shows "İçe aktarmaya hazır", then fails with 422 | **blocker** (UX-01), major (UX-09) |
| U3b | Planner (exam route proven with synthetic `karisik.xlsx`) | 1440 | chooser "Sınav listesi" → card → primary | target 8.9 s, preview OK ("1 yeni kayıt eklenecek") | 0 | Yes | Pass; the exam term isn't preset (Güz 2026-27 is chosen) | minor (UX-21) |
| U4 | Planner | 1440 sheet drop | `bahar_week1_transposed.xlsx` → "Bu büyük olasılıkla bir farklı düzende bir çizelge" → primary "Kurulum sihirbazında aç" | card 4.6 s · `/onboarding?from=helper` 9.9 s | 0 | Yes | Pass with friction. The card doesn't say why the wizard is needed; the sheet covers "Başlat · 1 dosya"; focus on `<body>` | major (UX-02, UX-04), minor (UX-11) |
| U4 | Planner | 390 touch | same via 📎 | card 6.0 s · target 10.8 s | 0 | Yes | Pass. The `/onboarding` row shows "b…" and no "Yardımcıdan geldi"; focus on `<body>` | major (UX-04), minor (UX-18) |
| U5 | Planner | 1440 | `karisik.xlsx` → "Bu dosya hangisi?" with 2 rows + hints → picks "Sınav listesi" | chooser 3.7 s, pick about 2.6 s | 0 | Rows are the action; clear | Pass (≤ 20 s). The new card still says "Büyük olasılıkla" after the explicit pick | minor (UX-16) |
| U6 | Academician | 390 touch | `seminar.ics` → "Bu bir takvim dosyası … SmartSched dışarıdan takvim okumaz…" → "Takvimime ekle" | card 5.9 s · `/profile?calendar=1` 10.7 s | 0 | Yes | **Dead end.** The dialog "Takvimime ekle · Adım 1/3" says "Takvim aktarımı kurumunuzda kapalı." and offers nothing else | major (UX-06) |
| U7 | Academician | 1440 page drop | planning list → needs_planner "…Sizin için:" → "Derslerim'i aç" | card 6.4 s · `/my-classes` 11.8 s | 0 | Yes | Pass on routing. Focus on `<body>`. The page says "Hesabınız bir öğretim elemanı kaydına bağlı değil…" while the card promised "Derslerinizi SmartSched zaten biliyor" | major (UX-04), minor (UX-12, UX-26) |
| U8 | Viewer | 1440 page drop | `Bahar_son.xlsx` → "Bu dosya bir haftalık derslik takvimi. Bunu planlama ekibi içe aktarır. Sizin için:" → "Derslik bul'u aç" | card 5.0 s · `/find-room` 10.2 s | 0 | Yes | Pass. Polite, gives a next step; focus on `<body>` | major (UX-04), minor (UX-12) |
| U9 | Admin | 1440 | `notlar.xlsx` → "Bu dosyayı tanıyamadım." → "Örnek dosyaları gör" → "Planlama listesi · İndir" | card 2.3 s · download `ornek_planlama_listesi.xlsx` 3.9 s | 0 | Yes | Pass. It reads as the system's limit, not the user's fault | minor (UX-15) |
| U9 | Admin | 390 touch | same via 📎 | card 4.3 s · download 5.6 s | 0 | Yes | Pass; "İndir" links 66×44 | minor (UX-15) |
| U10 | Admin, keyboard only | 1440 | Ctrl+J → Shift+Tab to "Elimde bir dosya var, ne yapayım?" → Enter → picker → focus on the card title → Tab → primary → Enter | target 10.0 s | 0 | Yes | Pass. Tab order title → primary → "Başka bir tür seç" → "Kurulum sihirbazında aç" → "Bu dosya nedir?"; the card is announced twice | minor (UX-17) |
| X1 | Admin, users CSV | 1440 | `users_initials.csv` → "Bu bir kullanıcı listesi · Eminim" → "Kullanıcıları içe aktar" | card 3.7 s · `/admin/users` dialog 8.8 s | 0 | Yes | Pass, but focus lands on ✕ "Dosyayı kaldır: users_initials.csv" | major (UX-05) |
| X2 | Admin, `belge.pdf` | 1440 | sheet drop | card 4.2 s | n/a | "Başka dosya seç" | Refusal text is raw English: "cannot read PDF: PdfReadError" | major (UX-07) |
| X3 | Admin, planning list + board together | 1440 page drop | "2 dosya bıraktınız. Birden çok dosyayı Kurulum sihirbazı birlikte okur." → "Kurulum sihirbazında aç" | card 2.7 s · `/onboarding?from=helper` 8.2 s with both rows | 0 | Yes | Pass. Focus on `<body>`; the card focus goes to the guide field | major (UX-04), minor (UX-22) |
| X4 | Rooms-only admin, `room_master.csv` | 1440 page drop | "Bu bir derslik ana listesi · Eminim" → "Derslik ana listesi olarak içe aktar" | card 2.9 s · `/import?kind=room-master&from=helper` 8.2 s | 0 | Yes | The page opens with **no "no access"**. But **the file is not attached** (empty drop zone), the sheet hides "Derslik ana listesini uygula", focus is on `<body>`, and there are 3 silent 403s (`/imports`, `/rooms`, `/terms`) | major (UX-03) |
| X5 | Admin, `room_master.csv` (control) | 1440 | same | target 8.7 s | 0 | Yes | Same lost file, so the problem is not role-specific | major (UX-03) |

## Findings

### UX-01 · blocker · Planner · 1440 and 390 · the masked exam list is refused by the KVKK guard (U3 cannot be done)

- **Repro:**
  1. Sign in as the planner.
  2. Press Ctrl+J and drop `final_planlama_listesi_2026_v2.xlsx` (or 📎 it on the phone, or upload it on `/import?kind=exam-list`).
- **Expected:** a card "Bu bir sınav listesi" despite "planlama" in the name, then the exam-list preview (§11.3 U3).
- **Actual:** a refusal card "KVKK: dosyada maskelenmemiş 2 kişi adı var. Bu test yığınında adlar yalnızca baş harfleriyle yüklenebilir; maskelenmiş kopyayı kullanın ($REC_WORKDIR/fixtures)." The direct `/import` upload gets a 422 with the same code. The instructor column holds initials only (checked by pattern, without reading values), and the workbook metadata holds one-word values only. So the 2 hits are other string items. Either they are a false positive of `unmasked_hits` (e.g. a course title matching a name pair) or residue in the masked fixture. The second would be a KVKK issue in the fixture set, so the owner of the fixtures should check it. The planning list `bahar_derslik_planlama_listesi_v5.xlsx` passes the guard, which shows the router itself is fine. U3's routing (exam list → `/import?kind=exam-list`) was proven with `karisik.xlsx` (U3b).
- **Screenshots:** `hb23d-ux/U3-planner-1440-b-card.png`, `hb23d-ux/U3-planner-390-b-card.png`, `hb23d-ux/direct-exam-list-after.png`, `hb23d-ux/U3b-planner-1440-karisik-exam-preview.png`
- **Source:** `smartsched/backend/app/core/kvkk_guard.py:102-141` (`unmasked_hits` / `check`), and the masked fixture `final_planlama_listesi_2026_v2.xlsx`.

### UX-02 · major · all personas · 1440 · after the hand-over the open sheet covers the target page's primary

- **Repro:**
  1. Sign in as admin and drop `Bahar_son.xlsx` on the dashboard.
  2. Press the card's primary.
  3. On `/import`, press "Önizle".
- **Expected:** the person sees the page's own primary (§8.2: "After the primary button, the sheet closes … Focus goes to the page's own primary"). On desktop the non-modal sheet must not cover it.
- **Actual:** the 400 px sheet stays open over the page, and the page content is not inset.
  - On `/import`, "Önizle" is cut in half (x 981–1048; the sheet starts at about 1032).
  - On the preview, **"Uygula" is fully hidden**.
  - On `/onboarding`, "Başlat · 1 dosya" and the file row's "Yardımcıdan geldi" and ✕ are hidden.
  - On room master, "Derslik ana listesini uygula" is hidden.
  - Esc with focus on the page doesn't close the sheet.

  The persona asks "Uygula nerede?", which is a "where do I click?" moment.
- **Proposal:** close the sheet on a file hand-over on desktop too, as it already does on the phone, and leave a one-line "Yardımcıyı aç" toast. The other option is to inset the page by the sheet width.
- **Screenshots:** `hb23d-ux/U1-admin-1440-c-target.png`, `hb23d-ux/U1-admin-1440-d-preview.png`, `hb23d-ux/U4-planner-1440-c-target.png`, `hb23d-ux/X4-roomsonly-1440-c-target.png`
- **Source:** `smartsched/frontend/src/components/helper/helper-sheet.tsx:80-81` (`go`: `if (!desktop) closeSheet()`).

### UX-03 · major · Admin and rooms-only admin · 1440 · the room-master hand-over loses the file

- **Repro:**
  1. Sign in as `derslik@` (or admin) and drop `room_master.csv`.
  2. Press "Derslik ana listesi olarak içe aktar".
- **Expected:** `/import?kind=room-master` with the file row "room_master.csv · Yardımcıdan geldi" and focus on the page primary (§0 "No second upload").
- **Actual:** the URL is correct and there is **no "no access"** (requirement met). But the step shows the empty "room_master.csv dosyasını buraya bırakın ya da seçmek için tıklayın" zone. The person must find the file again. `POST /helper/files/handoff` returns 200 (audit written), but the stage is never consumed. Focus is on `<body>`. For the rooms-only admin the console shows 403 on `GET /imports`, `/rooms` and `/terms` (silent, nothing visible).
- **Screenshots:** `hb23d-ux/X4-roomsonly-1440-c-target.png`, `hb23d-ux/X5-roommaster-admin-1440-c-target.png`
- **Source:** `smartsched/frontend/src/components/import/room-master-import.tsx` (no `useHelperFileHandoff`); `import-wizard.tsx:44` (`REVIEWED` includes room-master) and `:347`.

### UX-04 · major · Planner, academician, viewer, admin · 1440 and 390 · focus falls to `<body>` after the hand-over

- **Repro:**
  - Hand over to `/onboarding` (U4, X3), `/my-classes` (U7), `/find-room` (U8) or `/import?kind=room-master` (X4).
  - Then read `document.activeElement`.
- **Expected:** §10: "after the hand-over, focus goes to the target page's own primary … focus never falls to `<body>`".
- **Actual:** `<body>` in all four cases. The `/import` weekly-grid and exam routes are correct ("Önizle"), and `/profile?calendar=1` focuses the dialog heading.
- **Screenshots:** `hb23d-ux/U4-planner-390-c-target.png`, `hb23d-ux/U7-acad-1440-c-target.png`, `hb23d-ux/U8-viewer-1440-c-target.png`
- **Source:** `smartsched/frontend/src/components/onboarding/file-drop.tsx:53` (takes the hand-over, no focus effect); `smartsched/frontend/src/components/helper/file-router.ts:221-225` (non-file routes: `go(href)` with no focus target).

### UX-05 · major · Admin · 1440 · the users-CSV hand-over focuses the ✕ "Dosyayı kaldır"

- **Repro:**
  1. Drop `users_initials.csv`.
  2. Press "Kullanıcıları içe aktar".
- **Expected:** focus on the dialog's "İçe aktar" (enabled), or on the file row heading.
- **Actual:** focus is on `users-handed-file-remove` ("Dosyayı kaldır: users_initials.csv"). One Enter or Space removes the file the person just handed over.
- **Screenshot:** `hb23d-ux/X1-users-admin-1440-c-target.png`
- **Source:** `smartsched/frontend/src/components/admin/users-admin.tsx:1002` (dialog default focus = first tabbable; set the initial focus to `import-run`).

### UX-06 · major · Academician · 390 · ".ics → Takvimime ekle" leads to a dead end

- **Repro:**
  1. Sign in as the academician on the phone.
  2. 📎 `seminar.ics`.
  3. Press "Takvimime ekle".
- **Expected:** the person reaches Profil › Takvim and can add their classes (U6 success).
- **Actual:** the dialog "Takvimime ekle · Adım 1/3 · Neyi eklemek istiyorsunuz?" says only "Takvim aktarımı kurumunuzda kapalı. Yönetici açtığında buradan ekleyebilirsiniz." There is nothing to do. The card offered a route the institution has switched off. The secondary "Hızlı rezervasyonu aç" has nothing to do with a calendar file either. The persona feels refused twice.
- **Proposal:** when calendar export is off, the card should say "Takvim aktarımı kurumunuzda kapalı; derslerinizi Derslerim'de görebilirsiniz." and use "Derslerim'i aç" as the primary.
- **Screenshots:** `hb23d-ux/U6-acad-390-b-card.png`, `hb23d-ux/U6-acad-390-c-target.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:764` and `:774-775` (`alternatives` returns `_CALENDAR` without checking the institution's calendar setting).

### UX-07 · major · Admin · 1440 · `belge.pdf` shows a raw English exception

- **Repro:** drop `belge.pdf` on the sheet.
- **Expected:** a Turkish refusal ("Dosya okunamadı. Tekrar deneyin ya da başka bir dosya seçin." or "Bu PDF'i okuyamadım…").
- **Actual:** the title and the live region read "cannot read PDF: PdfReadError".
- **Screenshot:** `hb23d-ux/X2-pdf-admin-1440-b-card.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1446` (falls back to `msg` when `i18n.localize` has no entry; the text comes from `app/council/formats_builtin.py:68`).

### UX-08 · major · Admin · 1440 · "Nerede? › Dosyanın ne olduğunu öğren › Göster" doesn't lead to the 📎

- **Repro:**
  1. Press ⌘K / Ctrl+K and type "bu dosya ne" (or "dosya").
  2. Choose the "Nerede?" row "Dosyanın ne olduğunu öğren · Yardımcı › Dosya ekle · Göster".
- **Expected:** §8.3: "'Nerede?' answers it with 'Göster', which rings the 📎". The helper should open with the 📎 ringed.
- **Actual:**
  - A popover appears: "Bu düğme şu an bu sayfada görünmüyor. Adımlar aşağıda. 1. Yardımcı 2. Dosya ekle", with "Anladım" and "Yardımcıya dön".
  - The sheet doesn't open, and step 1 doesn't say how to open the helper.
  - A first mouse click on the row showed nothing for 2 s, and focus went to `<body>`.
- **Screenshots:** `hb23d-ux/disc-admin-1440-b6-nerede-enter.png`, `hb23d-ux/disc-admin-1440-b5-nerede-goster.png`
- **Source:** `smartsched/frontend/src/components/helper/show-me.tsx:255` ("missing" state); `feature-index.gen.ts:42` (`anchor: helper-attach` lives inside the closed sheet). Show-me should open the sheet first.

### UX-09 · major · Planner · 1440 · the `/import` step-1 probe says "ready" for a refused file, and the reason is then hidden

- **Repro:**
  1. Open `/import?kind=exam-list`.
  2. Pick `final_planlama_listesi_2026_v2.xlsx`.
  3. Press "Önizle".
- **Expected:** the probe's classify answer (a refusal with code `kvkk_unmasked_names`) is shown before the upload (M-20). After a 422, the server's `message_tr` is shown.
- **Actual:** the probe's refusal is ignored and the row says "İçe aktarmaya hazır". After "Önizle", the row says "Dosya okunamadı. Doğru Excel şablonu mu?" and the status is "Başarısız". The person is told the template is wrong when the real reason is privacy.
- **Screenshots:** `hb23d-ux/direct-exam-list.png`, `hb23d-ux/direct-exam-list-after.png`
- **Source:** `smartsched/frontend/src/components/import/import-wizard.tsx:207-214` (`probeFile` only looks at `detected`) and `:306-307` (422 → `glass.import.badFile`, the server detail is dropped).

### UX-10 · minor · all · 1440 · the page jumps when the sheet opens or a card arrives

- **Repro:** on `/dashboard`, press Ctrl+J. `window.scrollY` goes 0 → 732 (also after every file card; 246–732 px depending on the page).
- **Expected:** the page stays where it was.
- **Actual:** the dashboard scrolls to its bottom behind the sheet. When the person closes the sheet, they are somewhere else.
- **Screenshot:** `hb23d-ux/U1-admin-1440-b-card.png` (compare `U1-admin-1440-a-dragging.png`)
- **Source:** `smartsched/frontend/src/components/helper/helper-sheet.tsx:192` (`field?.focus()` without `preventScroll`); `cards/file.tsx:611` (`focus({ preventScroll: false })`).

### UX-11 · minor · Planner · both · transposed-grid title grammar; no reason given for the wizard

- **Repro:** drop `bahar_week1_transposed.xlsx`.
- **Actual:** "Bu büyük olasılıkla bir farklı düzende bir çizelge" (two "bir") plus the badge "Büyük olasılıkla" (the same words twice). Nothing says why "İçe aktar" can't take it, so the wizard feels like a detour (U4 watch item).
- **Proposal:** "Bu, yan çevrilmiş bir haftalık çizelge" + evidence "Saatler üstte, derslikler solda." + one line "İçe aktar ekranı bu düzeni okuyamaz; Kurulum sihirbazı okur ve size sorar."
- **Screenshot:** `hb23d-ux/U4-planner-1440-b-card.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1179` and `:209-211` (phrase "farklı düzende bir çizelge").

### UX-12 · minor · Academician, viewer · 1440 · a dangling "Sizin için:" in the needs_planner title

- **Actual:** title "Bu dosya bir haftalık derslik takvimi. Bunu planlama ekibi içe aktarır. Sizin için:", followed by the evidence line, and only then the button. The colon points at the evidence, and the live region ends on "Sizin için:".
- **Proposal:** title "Bu bir haftalık derslik takvimi"; line above the button "Bunu planlama ekibi içe aktarır. Boş derslik arıyorsanız:".
- **Screenshots:** `hb23d-ux/U8-viewer-1440-b-card.png`, `hb23d-ux/U7-acad-1440-b-card.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1157`.

### UX-13 · minor · all · both · the privacy line mentions "Önizle" on cards that have none, and implies that Önizle saves

- **Actual:** "Dosya yalnızca türünü anlamak için okunur ve en çok 10 dakika şifreli tutulur. Açılan sayfada Önizle'ye basana kadar hiçbir şey kaydedilmez." This appears on the ICS card, "Derslerim'i aç" and "Derslik bul'u aç" (no file is carried, and there is no Önizle there). It also suggests that pressing Önizle saves, though the preview says "Henüz hiçbir şey kaydedilmedi". The source has newer copy (`privacyRead` / `privacyNotKept`), but the prod build doesn't.
- **Proposal:** for no-file routes, "Dosya yalnızca türünü anlamak için okundu; tutulmadı." For file routes, "…Uygula'ya basana kadar hiçbir şey kaydedilmez."
- **Screenshot:** `hb23d-ux/U6-acad-390-b-card.png`
- **Source:** `smartsched/frontend/src/components/helper/cards/file.tsx:311`; `messages/tr.json` `helper.file.privacyRead`.

### UX-14 · minor · Admin, planner · both · "Düğme dosyanın dönemine aktarır." is unclear

- **Actual:** "Dosya Bahar 2026 diyor; şu an Güz 2026-27 seçili. Düğme dosyanın dönemine aktarır." "Düğme" is vague, and on the inline `/import` block there is no such button (the select is already preset).
- **Proposal:** card: "Dosya Bahar 2026'ya ait; şu an Güz 2026-27 seçili. Aşağıdaki düğme dosyayı Bahar 2026'ya aktarır." `/import`: "Hedef dönem dosyaya göre Bahar 2026 olarak seçildi."
- **Screenshots:** `hb23d-ux/U2-admin-390-b-card.png`, `hb23d-ux/U1b-admin-1440-importpage-b-result.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1187`.

### UX-15 · minor · Admin · both · unknown card says "tanıyamadım" twice; the examples toggle is unannounced

- **Actual:**
  - Title "Bu dosyayı tanıyamadım." and body "Bu dosyayı tanıyamadım. Excel biçiminde, ama tanıdığım sütunlar yok."
  - "Örnek dosyaları gör" toggles a list but has no `aria-expanded`.
  - "Haftalık derslik takvimi" is listed as recognised, but there is no example for it.
- **Proposal:** body "Excel dosyası, ama tanıdığım sütun başlıkları yok."
- **Screenshot:** `hb23d-ux/U9-admin-390-c-examples.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1313`; `smartsched/frontend/src/components/helper/cards/file.tsx:336`, `:385`.

### UX-16 · minor · Planner · 1440 · after an explicit chooser pick the card still hedges

- **Actual:** after the person picks "Sınav listesi", the new card says "Bu büyük olasılıkla bir sınav listesi · Büyük olasılıkla" and needs a second press.
- **Proposal:** "Seçtiğiniz tür: Sınav listesi" with no certainty badge.
- **Screenshot:** `hb23d-ux/U5-planner-1440-c-after-pick.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1179` (title for a forced kind).

### UX-17 · minor · keyboard and screen reader · 1440 · the card is announced twice

- **Actual:** the sheet log is `role="log" aria-live="polite"` and repeats the whole card text ("Bahar_son.xlsx607 KBDosya ekleBu bir haftalık…"). The sr-only `role="status"` then says "Bahar_son.xlsx: Haftalık derslik takvimi, Eminim. …". §10 asks for one polite message.
- **Source:** `smartsched/frontend/src/components/helper/helper-sheet.tsx:110-111`; `cards/file.tsx:663`.

### UX-18 · minor · Planner · 390 · the `/onboarding` row hides the file name and the "Yardımcıdan geldi" chip

- **Actual:** the name column shows "b…"; the chip is cut off; the "Tür" text wraps over 4 lines.
- **Screenshot:** `hb23d-ux/U4-planner-390-c-target.png`
- **Source:** `smartsched/frontend/src/components/onboarding/file-drop.tsx:80`.

### UX-19 · minor · Admin · 1440 · palette "dosya" lists 5 file rows, and the router row is last

- **Actual:** "Dosyalardan kur", "İçe aktar", "Nerede? Dosyanın ne olduğunu öğren", "Dosya içe aktar…" (highlighted by default) and "Dosya ekle ve ne olduğunu öğren" (last). Enter goes to `/import`, which recovers via its own drop zone, so the person is not lost.
- **Screenshot:** `hb23d-ux/disc-admin-1440-b-palette-dosya.png`
- **Source:** palette ranking (helper.md §4.5 shortcut row).

### UX-20 · minor · Admin · 1440 · room-master evidence shows English keys

- **Actual:** "Sütunlar: code, capacity, exam_capacity, tags, building, floor, +2 → Derslik ana listesi".
- **Proposal:** "Kod, Kapasite, Sınav kapasitesi, Etiketler, Bina, Kat".
- **Screenshot:** `hb23d-ux/X4-roomsonly-1440-b-card.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:987-988`.

### UX-21 · minor · Planner · 1440 · the exam-list hand-over presets a lesson term

- **Actual:** with no term guess, `/import?kind=exam-list` preselects "Güz 2026-27 (Ders dönemi)" although "Final 2026" exists. The card had said "İçe aktarırken dönemi siz seçeceksiniz", but the select is already filled.
- **Screenshot:** `hb23d-ux/U3b-planner-1440-karisik-exam-target.png`
- **Source:** `smartsched/frontend/src/components/import/import-wizard.tsx` (term preset when `term` param is absent).

### UX-22 · minor · Admin · 1440 · several-files card focus and `/onboarding` hints

- **Actual:**
  - Focus goes to the guide field, not the card title (§10).
  - `/onboarding` shows "XLSX" only and no "1 dosya İçe aktar ekranından da aktarılabilir." (§8.4).
- **Screenshots:** `hb23d-ux/X3-many-admin-1440-b-card.png`, `hb23d-ux/X3-many-admin-1440-c-target.png`
- **Source:** `smartsched/frontend/src/components/helper/cards/file.tsx:526`, `:611`.

### UX-23 · minor · Planner · both · the refusal copy exposes an environment variable

- **Actual:** "…maskelenmiş kopyayı kullanın ($REC_WORKDIR/fixtures)." This only happens on test stacks, but it is still developer text in a card.
- **Proposal:** "…dosyanın maskelenmiş kopyasını yükleyin."
- **Source:** `smartsched/backend/app/core/kvkk_guard.py:139`.

### UX-24 · minor · Admin · 1440 · "Yardımcıdan geldi" when the helper wasn't used

- **Actual:** dropping on the `/import` "Türünü bilmiyor musunuz?" zone shows the row chip "Yardımcıdan geldi" and the URL gets `from=helper`. The person never opened the helper.
- **Proposal:** "Türü otomatik bulundu".
- **Screenshot:** `hb23d-ux/U1b-admin-1440-importpage-b-result.png`
- **Source:** `smartsched/frontend/src/components/import/import-wizard.tsx:231-233`, `:372`.

### UX-25 · minor · all · 390 · helper status chip is 132×24 on the phone

- **Actual:** "Yapay zekâ kapalı" is a button 24 px high, under M-02's 44 px.
- **Screenshot:** `hb23d-ux/U2-admin-390-b-card.png`
- **Source:** helper sheet header (`status-chip.tsx`).

### UX-26 · minor · Academician · 1440 · "Derslerinizi SmartSched zaten biliyor" vs an empty Derslerim

- **Actual:** the card promises this, but the target page says "Hesabınız bir öğretim elemanı kaydına bağlı değil; dersleriniz burada görünmez." This is data-dependent (the test account isn't linked), but the copy should not promise more than it can deliver.
- **Proposal:** "Dersleriniz SmartSched'de Derslerim sayfasında görünür."
- **Screenshot:** `hb23d-ux/U7-acad-1440-c-target.png`
- **Source:** `smartsched/backend/app/ai/helper/files.py:1171`.

## What worked well (keep)

- One filled primary in every state; two text secondaries at most; "Bu dosya nedir?" collapsed; a certainty word and no percentages.
- The edge pill "Yardımcıya bırakın: ne olduğunu söyleyeyim" appears at once on a page drag.
- The evidence is name-free, e.g. "19 sayfa, her biri bir hafta ("2 - 8 Şubat Bahar Dönem Açılış"); üstte gün adları, solda ders saatleri, 29 derslik".
- The phone primary is 48 px with a short label; secondaries are 44 px and stacked; no horizontal scroll; the composer is 16 px.
- On the weekly-grid route, the term is preset from the file name, and nothing is written before "Uygula".
- In the keyboard flow, focus goes to the card title, then Tab reaches the primary.

## Method notes

- OS drops were simulated with a `DataTransfer` built in the page (dragenter, dragover, drop) on `main` and `[data-testid=helper-log]`. Phone tasks used the native picker via `filechooser` / `input[data-testid=helper-file-input]`.
- The planner's first-visit welcome modal ("Planlama ofisine hoş geldiniz") was dismissed with "Sonra" before each task.
- Scripts are in the scratchpad `tester/` folder (not committed). No source file was edited.
- Previews created import-job rows named `Bahar_son.xlsx` and `karisik.xlsx` in "Son içe aktarmalar". Nothing was applied, and no users were imported.

## Re-check (round 2)

- Date: 2026-10-18, about 19:55–20:15 UTC. The stack was rebuilt with the fixes; the accounts and files were the same as round 1.
- Scope: only the blocker and the majors, at the sizes where they were found, plus any new blocker or major hit on the way.
- Screenshots: `hb23d-ux/*-r2*.png`.

| id | was | sizes re-tested | status | evidence |
|---|---|---|---|---|
| UX-01 | blocker | 1440 | **Fixed** | `final_planlama_listesi_2026_v2.xlsx` now gives "Bu bir sınav listesi · Eminim", "Dönem: Final 2026 (dosya adından)" and the primary "Final 2026 dönemine sınav listesi olarak aktar". It opens `/import?kind=exam-list&term=3&from=helper` with focus on "Önizle". The preview took 4 s (864 new, 58 unchanged, 863 to archive) and "Uygula" is visible. The full U3 flow takes about 15 s with 0 wrong clicks. Screenshots: `U3-planner-1440-r2-b-card.png`, `U3-planner-1440-r2-d-preview.png` |
| UX-02 | major | 1440 | **Fixed** | After the card's primary the sheet closes on every route tested: `/import` weekly grid and exam list, `/onboarding`, `/my-classes`, `/find-room` and room master. "Önizle", "Uygula", "Başlat · 1 dosya" and "Derslik ana listesini uygula" are all uncovered. Screenshots: `U3-planner-1440-r2-d-preview.png`, `U4-planner-1440-r2-c-target.png` |
| UX-03 | major | 1440 | **Fixed for admin, still open for the rooms-only admin** | Admin: the file row "room_master.csv · CSV · 4.4 KB · İçe aktarmaya hazır" is on the page, the diff reads "0 derslik değişiyor · 87 değişmiyor · 0 eşleşmedi · 0 satırda hata", and focus is on "Derslik ana listesini uygula" (`X5-roommaster-admin-1440-r2-c-target.png`). Rooms-only `derslik@`: no "no access", the file row is present, and apply works by token (`POST /imports/room-master` → 202, `"source":"helper"`, "Derslik ana listesi uygulandı · 87 satır okundu", `X5-roommaster-rooms-1440-r2-d-applied.png`). **But the diff is empty: "0 derslik değişiyor · 0 değişmiyor · 0 eşleşmedi · 0 satırda hata", with an empty table** (`X4-roomsonly-1440-r2-c-target.png`). This role gets 403 on `GET /api/v1/rooms`, `/terms` and `/imports`, so the page cannot compare and says nothing changes. The person applies blind, which breaks "Kaydetmeden önce her derslikte neyin değiştiğini görürsünüz". Also, the room-master row has no "Yardımcıdan geldi" chip (minor) |
| UX-04 | major | 1440 + 390 | **Fixed** (focus is no longer on `<body>`) | 1440: focus goes to `main#main` on `/onboarding` (one and two files), `/my-classes` and `/find-room`, and to "Derslik ana listesini uygula" on room master. 390: `/onboarding` focuses "Başlat · 1 dosya". Residual (minor): at 1440, `/onboarding` focuses `main` rather than its primary "Başlat · 1 dosya" as §10 asks, unlike the phone |
| UX-05 | major | 1440 | **Fixed** | The users CSV dialog opens with focus on "İçe aktar" (`import-run`), not the ✕ (`X1-users-admin-1440-r2-c-target.png`) |
| UX-06 | major | 390 | **Fixed** | The `seminar.ics` card reads "Bu bir takvim dosyası · Takvim dosyası: 3 etkinlik, 02.03.2026 – 16.03.2026 · Takvim aktarımı kurumunuzda kapalı; dosyayı Outlook ya da Google Takvim'e kendiniz ekleyebilirsiniz." It has no dead-end button, the unrelated "Hızlı rezervasyonu aç" is gone, and the privacy line is "Dosya yalnızca türünü anlamak için okundu; tutulmadı." (`U6-acad-390-r2-b-card.png`) |
| UX-07 | major | 1440 | **Fixed** | `belge.pdf` shows "Bu PDF dosyasını okuyamadım. Dosya bozuk ya da korumalı olabilir; başka bir kopyasını deneyin." The live region reads the same Turkish text, with no exception text (`X2-pdf-admin-1440-r2-b-card.png`) |
| UX-08 | major | 1440 | **Fixed** | The row is renamed "Nerede? › Dosya türünü öğren · Yardımcı › Dosya ekle". With Enter or a mouse click, the helper opens and focus is on `helper-attach` ("Dosya ekle") (`UX08-palette-goster-keyboard-1440-r2.png`, `UX08-palette-goster-mouse-1440-r2.png`). Minor: no visible focus ring or "ring" highlight on 📎 in the screenshot, and the page still scrolls to 732 behind the sheet (UX-10 open) |
| UX-09 | major | 1440 | **Still open (partly re-verifiable)** | None of the allowed files triggers a classify refusal on an `.xlsx` any more (UX-01 is fixed), so the original KVKK path cannot be replayed. The nearest case: on `/import?kind=exam-list` step 1, dropping or picking `belge.pdf` is **ignored silently**. There is no file row, no reason ("Yalnızca .xlsx" / "Bu PDF dosyasını okuyamadım…"), no classify and no sheet. "Önizle" is disabled, which is correct. The person drops a file and nothing happens (`UX09-drop-pdf-exam-list-1440-r2.png`). Source: `smartsched/frontend/src/components/import/magnetic-drop.tsx:135-136` (the vendored file input filters by `accept=".xlsx,.xlsm"` with no rejection message) |

### New findings in round 2

#### UX-27 · major · any persona · 1440 (and any second device) · a classify in another session of the same person deletes the staged file; the card then claims "10 dakika" expiry

- **Repro** (deterministic, `two.mjs`):
  1. Sign in as the planner at 1440 and drop `bahar_week1_transposed.xlsx`; the card appears.
  2. Sign in as the same planner on a 390 phone and 📎 `notlar.xlsx`.
  3. Back on the desktop, press "Kurulum sihirbazında aç".
- **Expected:** the hand-over works; a second device or tab doesn't destroy the first file. If a stage really is gone, the copy must not say it expired after 10 minutes.
- **Actual:** `POST /helper/files/handoff` → **410 `stage_expired`** about 2 s after the classify, whose `expires_at` was 10 minutes ahead. The card says "Dosyanın süresi doldu (10 dakika). Yeniden okuyun. · Dosyayı yeniden oku".
  - The same 410 appeared intermittently in single-session runs: 4 out of about 25 hand-overs (`users_initials.csv` twice, `room_master.csv` twice), each 1.3–1.5 s after the classify.
  - The likely cause is other agents using the same shared test accounts at the same time. No client `DELETE` was seen in the instrumented runs.
- **Screenshots:** `NEW-stage-expired-two-sessions-1440-r2.png`, `NEW-stage-expired-admin-1440-r2.png`
- **Source:** `smartsched/backend/app/api/v1/helper_files.py:76` (`hf.clear(access.user_id)`: "one live file per person" clears every session's stage on each new classify) → `smartsched/backend/app/ai/helper/files.py:1720-1727` (`clear`, per user, not per session) and `:1795-1798` (`_gone` answers `stage_expired` for a cleared stage).
- **Proposal:** scope the clear to the session (`session_tag`), or answer a distinct code ("Bu dosya başka bir oturumda yeni bir dosyayla değiştirildi. Yeniden okuyun.").

#### UX-03b · major · rooms-only admin · 1440 · empty diff before apply

This is the open part of UX-03 above. It is counted under UX-03.

### Observed in passing (minors, not re-tested systematically)

- Fixed:
  - UX-13: privacy copy now differs per route ("…Uygula ile kayıtlara işlenir." / "…okundu; tutulmadı.").
  - UX-14: "İçe aktar düğmesi dosyayı Final 2026 dönemine aktarır.".
  - UX-20: room-master evidence is now Turkish: "derslik kodu, kapasite, sınav kapasitesi, etiketler, bina, kat".
- Still open: UX-10 (the page scrolls to 732 when the sheet opens).
- New minors:
  - the room-master row has no "Yardımcıdan geldi" chip;
  - `/onboarding` at 1440 focuses `main` instead of "Başlat";
  - no visible focus indicator on 📎 after "Nerede? › Göster".

### Counts still open after round 2

- **blocker 0**
- **major 3**: UX-03 (rooms-only empty diff), UX-09 (refused or wrong-type file on step 1 has no reason), UX-27 (new: cross-session stage clear with false "10 dakika" copy)
- **minor 17**: the 17 round-1 minors minus 3 seen fixed (UX-13, UX-14, UX-20), plus 3 new minors above
