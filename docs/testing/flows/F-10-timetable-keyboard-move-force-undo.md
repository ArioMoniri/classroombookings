# F-10 · Timetable: open a class, move it with the keyboard, forced move with a reason (admin), undo; export the week

Personas: **admin** (coordinator; the only one who may force), **planner** (refused force), **academician** (must not reach planner controls). Viewports: desktop for the keyboard and drag parts; tablet and phone for the day/agenda view, the inspector and the move dialog.
This flow carries two of Fatih Bey's scenarios: **move PHAR 240 to A 206 from 23 Feb** (needs-doc M3) and **export the week to Excel** (M-32).
Owner rules:
- **Hard-rule integrity.** Every mutation rescores. A forced hard clash makes the run unpublishable, or shows the clash with its reason (M-02).
- **Who may force.** A non-forced move with a hard conflict is a preview (200, `ok:false`). Only an administrator may force, and only with a reason (422 without one).
- **Capacity is hard for manual moves** (M-09).

Testable on `b75047b`: **partly**. Keyboard move, scopes, undo and export exist. The **forced move with a written reason** has backend support but no reason field in the move dialog yet (hand-off "forced-move reason + rules list → design-system agent"). S06 runs its API check and reports the UI as `BLOCKED: reason field not built` or `FAIL`.

## Preconditions

1. Full stack with the four runs. The Bahar term run `B0` is published.
2. Bahar week 1 starts Mon **2 Feb 2026**, so **23 Feb = week 4**.
3. PHAR 240 §1: Monday P1–P3, 80 students. Find its room in `B0` (`GET /runs/B0/assignments?q=PHAR 240`, or the timetable). If it already sits in A 206, the move goes from A 206 to another ≥ 80-seat free room, and the "from 23 Feb" scope is still the point. Its Thursday lab rows (needs-doc rows 855/856) must not change.
4. Record `B0`'s hard score and assignment count before the flow.

## Steps

**S01 · admin · open the class from the keyboard** (M-16)
- Do: `/timetable?run=B0&week=3` (week zoom). Press `Tab` until the grid (`time-grid`, `role="grid"`) has focus (one tab stop, roving). Use the arrow keys to reach the PHAR 240 chip (`calendar-event`). You may first use the search (`calendar-search`, "PHAR 240"), which highlights the chip and moves focus to it. Press **Enter**.
- See: the inspector **"Ders denetçisi"** opens with:
  - **"Ne zaman, nerede"** (Monday P1–P3, the room, **"80 öğrenci · {cap} koltuk (%{fit})"**);
  - **"Kim"** (initials only);
  - **"Neden burada"**;
  - **"Kaynak"**: **"Planlama listesi · Sayfa1 · satır 545"**, with "Satırı göster";
  - **"Haftalar 1–14"**;
  - the request's notes (A-04);
  - **"Geçmiş"**;
  - the actions **"Kilitle"** and **"Taşı…"**.
- **Esc** closes it, and focus returns to the same chip (not `<body>`, not the page top).
- Fail if Enter opens "quick create" instead (M-16).

**S02 · admin · keyboard move with a date scope** (needs-doc M3)
- Do: on the chip press **Space** (pick up).
- See: the live region **"PHAR 240 alındı. Ok tuşları taşır, Boşluk bırakır, Esc iptal eder."** The arrow keys move a ghost one cell at a time. Each step is announced: **"PHAR 240 A 206, Pzt P1 üzerinde: uygun."** (or the conflict state), with the same drop-ok / conflict highlighting as dragging.
- Do: move to the A 206 column, same day and period. Press **Space**.
- See: the move dialog (`move-dialog`) **"PHAR 240 taşı"**:
  - fields **"Derslik"**, **"Gün"**, **"Başlangıç"** / **"Bitiş"**;
  - **"Hangi haftalar"** with **"Tüm haftalar (1–14)"**, **"Sadece 3. hafta (…)"**, **"23 Şubat 2026 tarihinden itibaren (4. hafta)"** (the date next to the week number, M3);
  - **"Bu saat için boş derslikler"** grouped **"Boş ve sığar"** / **"Sığmaz"** / **"Dolu"** / **"Uygun değil"**, each with **"{n} koltuk"** and **"%{p} dolu"**;
  - the hint **"Gerekçeler sürüklerken yapılan kontrollerle aynıdır."**
- Do: choose the "from" scope with **"Başlangıç haftası"** = 4.
- See: **"Önceki haftalar {old room} dersliğinde kalır"**, then **"Sunucu kontrolü: uygun"** (`move-server-ok`) after the debounced dry run.
- Do: **"Taşı"** (`move-confirm`). The button shows "Taşınıyor…".
- See: toast **"PHAR 240 → A 206 taşındı"** with **"Geri al"**. Focus stays on the moved chip.
- API: weeks 1–3 keep the old room, and weeks 4–14 are in A 206. The Thursday lab rows are unchanged. Hard score unchanged (100). The run was rescored (`GET /runs/B0` shows a new evaluation time, or the summary). One audit row for the move.

**S03 · admin · cancel a pick-up**
- Do: Space on another chip, two arrows, then **Esc**.
- See: **"Taşıma iptal edildi."** Nothing moved.

**S04 · admin · undo and redo**
- Do: the S02 toast **"Geri al"**, or `Ctrl+Z` / `⌘Z` with focus in the timetable.
- See: **"Geri alındı: PHAR 240"**. The assignments are back to the precondition state (all 14 weeks in the old room). `Ctrl+Shift+Z` / "Yinele" → **"Yinelendi: PHAR 240"**.
- Re-apply S02 (it is the scenario's end state). Then check the API again.

**S05 · planner · a conflicting move is refused, and force is admin-only**
- Do: as planner.test, drag or keyboard-move a class onto an occupied cell (same room and time as another class in the same weeks).
- See: the dialog shows the clash ("{n} ders · {ok} uygun · {bad} çakışma" or "Taşınamadı: {reason}" naming the other class). "Taşı" is disabled. **"Çakışmaya rağmen taşımayı yalnızca yönetici yapabilir"**.
- API: the move with `force:true` as planner → **403**.

**S06 · admin · forced move with a reason** [UI pending: reason field]
- Do: as admin, the same clash. **"Yine de taşı"**.
- UI target: before confirming, the dialog lists what will break (the rule and the other class) and asks for a **required reason** ("Gerekçe"). Confirm stays disabled while it is empty.
- API check (whatever the UI does):
  - `POST /runs/B0/assignments/<aid>/move` (or `bulk-move`) with `force:true` and no reason → **422**;
  - with `"reason":"Bölüm başkanı onayı, tek seferlik"` → 200.
  - After it: the run's hard score is **below 100**, or the clash is listed with the reason. **Publishing that run is refused** (409) until it is resolved (M-02).
  - The audit row carries the reason.
- Then undo it (S04) and check that hard is 100 again.

**S07 · admin · capacity is hard** (M-09)
- Do: move an 80-student class (PHAR 240) into a 30-seat room (e.g. B 201).
- See: refused as a hard violation ("Sığmaz" group; the dialog names 80 vs 30), unless forced with a reason as in S06. Before the fix this was a soft warning only.

**S08 · admin · lock and unlock**
- Do: in the inspector **"Kilitle"**.
- See: toast **"PHAR 240 kilitlendi"** with Geri al. The chip shows the lock glyph and the word. **"Kilidi aç"** → **"PHAR 240 kilidi açıldı"**.

**S09 · admin · export the week (and the term) to Excel** (M-32)
- Do: the timetable menu ("Diğer" / ⋯) → **"Bu haftayı Excel'e aktar"** (`export-week`) while week 4 is on screen. Then **"Tüm dönemi Excel'e aktar"** (`export-term`).
- Expect:
  - the week file has **one** sheet, for week 4 (check with `python3 -I -c "import openpyxl,sys;print(openpyxl.load_workbook(sys.argv[1],read_only=True).sheetnames)" file.xlsx`);
  - the term file has 14 sheets;
  - in the term file, PHAR 240 is in A 206 from week 4 and in the old room in weeks 1–3;
  - the API `GET /runs/B0/export?weeks=4` gives 1 sheet, and `?weeks=99` → 422.
- Before the frontend fix the menu exported all 14 weeks with week 4 on screen: FAIL (minor) if that is still so.

**S10 · academician · no planner controls**
- Do: as academician, open `/timetable`.
- See: the no-access page (`timetable-no-access`, "Bu sayfaya erişiminiz yok"), or a read-only published view. **Never** "Program oluştur" / "Excel'den içe aktar" (U-02, A-01), and no 403 toast stack.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Day / agenda view:** at 390, `/timetable` opens a single-day view (`calendar-mobile`, `day-timeline`) or the agenda (`agenda`), never the multi-room week grid (`time-grid` not visible; MOBILE.md M-08). A day switcher (≥ 44 px) and "Bugün" are reachable with the thumb.
- **Chips never truncate the course code.** The name truncates first (UI review blocker: "Fl…", "C..").
- **Inspector:** a tap on a class opens it as a bottom sheet (45 % / 92 %). "Taşı…" and "Kilitle" are ≥ 44 px buttons in the sheet footer.
- **Move on touch:** no drag is needed. "Taşı…" opens the move dialog as a full-height bottom sheet. The scope options are full-width ≥ 44 px radios. The "Boş ve sığar" list is a card list. "Taşı" is sticky at the sheet bottom. A long-press drag is optional and never the only way (M-11).
- **Filters** (`open-filters` → `filters-sheet`) open as a bottom sheet.
- **Undo toast on phone:** sits above the tab bar and the safe-area inset. "Geri al" is ≥ 44 px and stays at least 6 s.
- **Tablet 768:** a 3-day or a single-building week view is allowed if chips stay ≥ 72 px wide. Otherwise the day view.

## Flow acceptance

1. A keyboard user can open a class, move it with a date scope, cancel, undo and redo. Focus is kept and every step is announced.
2. "From 23 Feb" splits the class exactly at week 4 and leaves the lab rows alone. The export shows the same split.
3. Clashes and capacity breaches are refused for planners. Admins can force them only with a reason. A forced clash is visible and blocks publishing.
4. Week export = one week, term export = every week.
5. Academicians never see planner tools on `/timetable`.
6. MOBILE.md passes on `/timetable` (day / agenda, inspector, move sheet, filters) at 390 and 768.

## Earlier issues to re-verify here

M-02, M-09, M-16, M-32, M-50 (opens on the current week, one title), U-02 / A-01, the timetable truncation blocker of the UI review, the grid-move long frame (380–482 ms: run the probe on the S02 confirm, README §8).
