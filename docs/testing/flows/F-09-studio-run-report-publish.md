# F-09 · Generator Studio → run → run report with an honest verdict → publish, and the partial-publish confirm

Personas: **admin** (Fatih Bey, coordinator), **planner** (permission differences). Viewports: desktop for the full flow; tablet and phone for the run card, the run report and the publish confirm.
This flow carries Fatih Bey's own scenarios: generate **Bahar week 3**; the Turkish request **"Hemşirelik 1. sınıf dersleri 17:30'dan sonra olmasın"**; the infeasible request **102 students in a 30-seat room on a full day**; publish.
Owner decisions:
- **Hard-rule integrity.** A run is 100/100 or an explained infeasibility.
- **Partial publish.** A FEASIBLE_PARTIAL run with hard 100 may be published after an explicit confirm that **lists the unplaced classes**.
- **Scope.** A one-week run must not silently replace the term-wide published plan (M-04: 409 unless the scope reduction is confirmed).
- **Q8.** A lock over room capacity is refused at the edit unless explicitly overridden.
- **Publish guard.** No publishing of FAILED, CANCELLED or RUNNING runs. One active run per term.

Testable on `b75047b`: yes. Natural-language rules need an AI key: S03's free-text path is `SKIP (NEEDS-AI)`, and the template path is tested.

## Preconditions

1. Full stack with the four solver runs (README §4.2). The Bahar term run `B0` is published. Record `B0` and its stats (`placed/events_total`, hard score).
2. Bahar facts used below (fixtures): PHAR 240 §1 (Monday P1–P3, 80 students, list room A 206); ING 302 (102 students); **B 201** has 30 seats; the nursing programmes "Hemşirelik" and "Hemşirelik (İngilizce)"; P11 ends at 17:30.
3. AI policy off, no key.

## Steps

**S01 · admin · scope**
- Do: `/generate` (sidebar "Oluştur"). Step **"Kapsam"** (`studio-step-scope`): term **2026-BAHAR**, kind course (`scope-kind`), horizon **week** (`scope-horizon`), week chip **3**.
- See: the scope sentence (`scope-sentence`) names the week and its real counts (classes and rooms, M-26), and they equal `GET /runs` scope stats or the API preview. The horizon control is one segmented control on one row (UI review blocker: it wrapped to 2 rows at 1440).

**S02 · admin · classes**
- Do: **"Dersler"** (`classes-step`). Search `PHAR 240` (`class-search`).
- See: the row (`class-row`) with 80 students and the source. Inline-editing the students shows the hint with the imported value ("içe aktarılan değer … idi"). The pin dialog (`pin-room`) offers only rooms that fit 80.

**S03 · admin · the nursing rule, in Turkish**
- Do (AI path): **"Kurallar ve tercihler"** (`rules-step`). Write in the composer (`rule-composer-input`): `Hemşirelik 1. sınıf dersleri 17:30'dan sonra olmasın`.
- See with no key: a clear sentence that free text needs AI and **the matching structured template opens** (M-29), not misleading chips. With a key: `SKIP (NEEDS-AI)`.
- Do (template path): the template gallery (`template-gallery`) → "Belirli saatten sonra ders olmasın" → programme **Hemşirelik** and **Hemşirelik (İngilizce)**, class year **1**, **"Bu saatten sonra ders yok"** = 17:30 (the end of P11).
- See: the reach count (`affected-count`) is **> 0** and lists both nursing programmes' year-1 classes (needs-doc M5, regression of usability B1). Target: a question whether to include the nursing master's year-1 rows (e.g. HEM 566 on Saturday 13:40–18:00), because they would be the only violators. Report what is offered.
- Choose the hardness (`rule-hardness`) **Zorunlu** and add the rule. It appears in the rule list with the source "şablon".

**S04 · admin · the infeasible request: 102 students into a 30-seat room on a full day** (needs-doc M4, Q8, M-10)
- Do: pin ING 302 (102 students) to **B 201** (30 seats) for its full day, as **hard**, through the room-pin template, or through the class's pin dialog if it lets you choose B 201.
- See: refused **at the edit**, before any solve, with the named reason **"102 öğrenci 30 kişilik B 201'e sığmaz"** (wording may differ, but it names the count, the seats and the room), plus the free rooms with ≥ 102 seats at that time.
- API: the same constraint through `POST /constraints` → **422** with that reason (TR and EN).
- Override (admin only): the admin may force it **with a written reason**. A planner cannot (403/422).
  - If you force it, the run report must list it under accepted exceptions (`verdict-exceptions`) with the capacity named, and the headline must not say "hiçbir kural bozulmadı".
  - Remove the forced rule before S06, so the publish steps run on a clean run.
- Persona-admin M-10 found the opposite: accepted silently, and the run dropped the class while still showing hard 100. That is a **major** if it is still the case.

**S05 · admin · pre-check**
- Do: **"Ön kontrol"** (`check-step`).
- See: the readiness (`readiness`) per check. Every blocker names the class and the room ("Kilitli derslik uygun değil" is never shown three times without names, UI review). Each issue has a fix (`fix-button`). With a blocker: the confirm **"{n} ders kesin kurallarınızla yerleştirilemiyor. SmartSched durup nedenini açıklayacak. Önce düzeltin ya da tam tanıyı görmek için yine de oluşturun."** with **"Yine de oluştur"** / "Önce düzelt".
- Week 3 has known planner data problems (6 locked_overlap, 201 input_conflict: ROADMAP "Solver decisions"). The pre-check lists them as data issues, not as SmartSched failures.

**S06 · admin · generate**
- Do: **"Oluştur"** (`generate-step`, `generate`).
- See: the run card (`run-card`) with live status (`run-status`) driven by events. A cancel button (`run-cancel`) is visible. When finished, `run-result` reads **"{placed}/{total} yerleşti"** with the **real** numbers: they equal `GET /runs/<id>` → `stats.placed` / `stats.events_total` (M-11: the card said 716 for 687). The persona run gave Bahar week 3 = 687/716, FEASIBLE_PARTIAL, hard 100; record yours.
- Cancel check (separate run): start one more and press "İptal". The run becomes **CANCELLED** and stays in the runs list (M-27: it was deleted).

**S07 · admin · run report: an honest verdict**
- Do: **"Raporu aç"** (`run-open-report`) → `/runs/<id>`.
- See the verdict (`run-verdict`, `run-hero`). It is **one sentence that is true**, one of:
  - **"Bütün dersler yerleşti, hiçbir kural bozulmadı."** only when every class is placed, hard is 100, **and** no structural rule was waived and no placement breaks capacity;
  - **"{placed}/{total} yerleşti; uygulanan zorunlu kurallar karşılandı, şu istisnalarla:"** followed by the exceptions (`verdict-exceptions`) whenever anything was waived, forced or over capacity (M-06, P19-00c);
  - an infeasibility explanation with the culprits.
- The same placed / unplaced / conflict numbers appear on the run card, in the report, on the timetable header and in `GET /runs/<id>` (M-08: "308 çakışma" in the grid vs 0 in the report). List all four numbers in the evidence.
- Diagnosis cards (`diagnosis-card`) for the unplaced classes give Turkish sentences (`message_tr`) and culprits. **"Uygula ve yeniden çöz"** (`diagnosis-apply`) creates a child run.
- The data-issues report downloads as xlsx.
- The nursing rule of S03: all year-1 nursing classes in this run end by P11 (check via `GET /runs/<id>/assignments`, filtered by the two programmes and year 1).

**S08 · admin · publish a week run: scope confirm**
- Do: on the week-3 report, **"Yayınla"** (`run-publish`).
- See: the confirm (`publish-confirm`):
  - **"Çalıştırma #N yayınlansın mı?"**;
  - the scope **"2026-BAHAR, 3. haftalar"**;
  - **"Yayımlanan program olarak #B0 çalıştırmasının yerini alır: rezervasyon ızgarası ve takvim akışları bunu izler."**;
  - the warning **"Bu çalıştırma yalnız bu haftaları kapsıyor, ama yayımlanınca dönemin bütün haftaları için program olur."**;
  - because it is partial: **"Bu çalıştırmada {missing} dersin dersliği yok ({placed}/{total} yerleşti)."** and **the list of unplaced classes** (course codes; owner decision);
  - an explicit scope checkbox or button ("Evet, bu haftalar yayından kalksın" or equivalent) that must be ticked before **"Yayınla"** enables.
- API: `POST /runs/N/activate` without the scope confirmation → **409** (M-04). With it → 200.
- **Do not leave it published:** cancel the dialog. Or, if you published, re-publish `B0` right after (Runs list → B0 → Yayınla) and check that `B0` is active again.

**S09 · admin · publish a partial term run**
- Do: on `B0`'s report (or a fresh Bahar term run), **"Yayınla"**.
- See: **"2026-BAHAR, dönemin tamamı"**, the partial line with `{missing}` = total − placed, and the unplaced list with exactly that many entries. Confirm → toast **"Çalıştırma #N artık yayımlanan program"**. The badge reads **"Yayında"** (`run-published`). The runs list marks it (M-30).
- API: one active run per term (`GET /runs?term_id=` → exactly one `is_active`).

**S10 · admin · runs that must not be published**
- A CANCELLED run (S06) or a FAILED one: no "Yayınla", or the confirm shows **"Sunucu yayınlamadı:"** with the reason (`publish-refused`). API → 409.
- A run whose hard score is below 100: refused the same way.
- Deleting the active run: refused (409), with no delete control in the UI for it.

**S11 · admin · presets**
- Do: "Hazır ayar" (`preset-menu`) → the menu opens (M-12: it crashed the page). "Hazır ayar kullan" → apply (`preset-apply`, `preset-apply-confirm`) → toast **"“{name}” hazır ayarı uygulandı"**. Saving a preset (`preset-save`) → **"“{name}” hazır ayarı kaydedildi"**. A planner sees **"Hazır ayarları sadece yönetici silebilir"** on delete.

**S12 · planner · what a planner may do**
- Generate: allowed. Publish: allowed (planning.edit) with the same confirms.
- Forcing a capacity breach or waiving a structural rule: refused (422/403) with a message that an administrator must do it, with a reason.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- The Studio on phone is a stepper with **"{i}/5 · {step}"** (`mobile-progress`) and one step per screen. The bottom bar (`studio-bottom-bar`) is sticky inside `<main>` (never `fixed` over the sidebar at 1024, UI review). It sits above the tab bar and the safe-area inset.
- Rules and templates open as bottom sheets. The review tray is a bottom sheet with the learned-suggestions group on top (F-06).
- **Run card on phone:** status word + numbers on one line. No ring gauge filling the first screen (UI review: the run report ring at 390).
- **Run report on phone:** the verdict sentence first, then a KPI row, then the diagnosis cards. Tables become cards or scroll with the first column pinned (M-07).
- **Publish confirm on phone:** a bottom sheet. The unplaced list scrolls inside the sheet. The scope confirmation control is ≥ 44 px. "Yayınla" stays disabled until it is ticked and is reachable without closing anything.

## Flow acceptance

1. The scope and placed numbers agree everywhere (Studio, card, report, grid, API).
2. A capacity-breaking hard pin is refused at the edit with a named reason. A forced override needs an admin and a reason, and it appears as an exception in the report.
3. The Turkish nursing rule (template path) reaches both nursing year-1 programmes, and the run honours it.
4. The verdict never says "hiçbir kural bozulmadı" while something was waived, forced or over capacity.
5. Publishing a week run needs an explicit scope confirm (409 otherwise). Publishing a partial run lists every unplaced class. Refused runs cannot be published.
6. MOBILE.md passes on `/generate` (each step), `/runs/<id>` and the publish confirm at 390 and 768.

## Earlier issues to re-verify here

M-03 (publish button), M-04 (week run replaces term), M-06 / M-07 / M-08 (contradictory counts), M-10 (102-in-30 accepted), M-11 (card count), M-12 (presets crash), M-26 (scope numbers), M-27 (cancel deletes), M-29 (chips without AI), M-30 (published marker), M-49 (partial confirm). Fatih Bey's scenarios: week 3 ✓ S06, nursing ✓ S03/S07, infeasible ✓ S04.
