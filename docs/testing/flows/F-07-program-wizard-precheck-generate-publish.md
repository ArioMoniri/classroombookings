# F-07 · Program from scratch: wizard → pre-check → generate → publish

Personas: **admin** (coordinator); planner and viewer for the permission checks. Viewports: desktop, tablet, phone.
Story (needs doc §4, scenarios S1–S4): a new programme with no import and no history, entered by hand, solved, published, without disturbing what is already published.
Owner decisions and adopted defaults:
- program creation can be undone for 30 days;
- with a published plan, adding a programme re-solves with minimal change, and nothing is published before the preview is confirmed (the moderation recreate rules, F-05);
- Q9: a recreate moves 0 published classes outside its scope by default, and lists any extra move with its cause.

Testable on `b75047b`: yes. The wizard landed in `be78a8b` (`/programs/new`, `components/program-wizard/*`). Two acceptance items of S1 are not confirmed in code and are checked as targets: the suggestion panel line "Bu program için geçmiş veri yok", and the 30-day undo of a programme.

## Preconditions

1. Restore the snapshot. Create an empty future term as admin (rooms are global, so the term has rooms and nothing else):
   ```bash
   curl -fsS -X POST "$API/terms" "${H[@]}" -d '{"code":"2027-BAHAR","name":"Bahar 2027","kind":"REGULAR","start_date":"2027-02-01","end_date":"2027-05-14","week_count":14,"is_active":false}' | jq -c '{id,code}'
   ```
   Record `T27`. `GET /runs?term_id=$T27` → `[]`.
2. For Part C: the published Güz run `G0` from F-05 precondition 1.
3. Use initials only for people typed into the wizard: "T. E." and "S. K.".

## Steps

### Part A · the worked example (fast path)

**S01 · admin · open the wizard**
- Do: sidebar **"Yeni program"** (or `/programs/new`).
- See: title **"Yeni program"**, subtitle **"İçe aktarma olmadan program oluşturun. Yazdıkça kaydedilir."**, the intro, the buttons **"Program oluştur"** and **"MBG Tezli YL örneğiyle başla"**, **"Taslaklar"** ("Bu tarayıcıda taslak yok."), and **"Sunucuda kayıtlı bir programı aç"**.
- planner.test sees the same (planning.edit). viewer.test sees **"Program oluşturmak için planlama düzenleme izni gerekir"** with **"Programı bir koordinatöre oluşturtun ya da izin isteyin."**, and no form.

**S02 · admin · start from the example**
- Do: **"MBG Tezli YL örneğiyle başla"**.
- See: the rail (`rail-step-*`, label "Program sihirbazı adımları") lists **"Dönem · Birim ve program · Dersler · Şubeler ve öğretim elemanları · Haftalık düzen ve odalar · Kısıtlar · Ön kontrol · Oluştur ve çöz"**. Each step shows "tamam", "başlanmadı", "{n} hata" or "{n} uyarı". The rail foot reads **"{term} dönemine elle girilmiş satırlar olarak yazılır; son adıma kadar hiçbir şey çözülmez ya da yayınlanmaz"**, and the save state **"Bu tarayıcıda tutuluyor; dönem ve program seçilince sunucuya kaydedilir."**
- Do: **"Hedef dönem"** = 2027-BAHAR.
- See: the save state changes to **"Kaydediliyor…"**, then **"Tüm değişiklikler kaydedildi · {when}"**.

**S03 · admin · walk the steps**
- For each step, read the preview panel ("Program önizlemesi"): **"{courses} ders · {sections} şube · {people} öğretim elemanı · haftada {hours} saat"** and **"{n} yeni kişi oluşturulur"**. Continue with "Devam ›". `Enter` advances when focus is not in a grid or a textarea.
- At "Haftalık düzen ve odalar", every course shows **"{n} öğrenci · {count} oda sığar: …"**, or a warning such as **"{code}: {room} tam {n} kişilik; kayıt artarsa sığmaz."**

**S04 · admin · pre-check**
- Do: **"Ön kontrol"** → **"Ön kontrolü çalıştır"**.
- See: **"Sihirbaz denetimleri"**, then **"Hata ya da uyarı yok."** or the list. **"Oluşturucu ön kontrolü (bu programın oturumları)"** → **"Ön kontrol: 0 engel, {n} uyarı"**. Each issue has a **"Düzelt"** that jumps to the field.

**S05 · admin · generate**
- Do: **"Oluştur ve çöz"** step.
- See: **"Nasıl devam edilsin?"**. Because 2027-BAHAR has no published plan, the choice is **"Oluştur ve dönemi çöz"** ("Henüz yayında plan yok: tüm dönem için ilk çözüm başlar.") or **"Yalnızca oluştur"** ("Program, dersler ve talepler yazılı kalır; çözüm sonra.").
- Do: "Oluştur ve dönemi çöz" → **"Oluştur ve çöz"**.
- See: confirm **"Bu programla devam edilsin mi?"**, body **"2027-BAHAR: {courses} ders, {sections} şube, {meetings} haftalık oturum, {people} yeni kişi."** Confirm. The button reads **"Oluşturuluyor…"** (busy). Toast **"Program 2027-BAHAR dönemine kaydedildi."** A run starts, and you are taken to its card or report.
- API: the faculty, programme, courses, sections, instructors and meeting requests exist in T27 with `MAN:` source keys, and each create is audited. The run finishes **OPTIMAL or FEASIBLE**, with **hard 100** and **every meeting placed** (backend evidence: 6/6 for this example), and `planner_check` 0.

**S06 · admin · publish the first plan**
- Do: on the run report, **"Yayınla"** (`run-publish`).
- See: confirm **"Çalıştırma #N yayınlansın mı?"** with **"2027-BAHAR, dönemin tamamı"** and **"Bu dönemin ilk yayımlanan programı olur: rezervasyon ızgarası ve takvim akışları bunu izler."** Confirm. Toast **"Çalıştırma #N artık yayımlanan program"**.
- API: `POST /runs/N/activate` → 200, `is_active: true`.

### Part B · by hand (S1 of the needs doc)

**S07 · admin · programme and courses**
- Do: **"Program oluştur"**. Term 2027-BAHAR. **"Birim (fakülte / enstitü)"**: type `Fen Bilimleri Enstitüsü` (the existing unit is offered as "Var olan birim"). **"Program adı"**: `Moleküler Biyoloji Tezsiz YL (Test)`. **"Düzey"** = **"Tezsiz YL"**. **"Ders kodu öneki"** = `MBG`.
- Validation checks:
  - prefix `MBĞ` → **"Ders kodlarında Türkçe harf kullanılmıyor (MBĞ)."**;
  - prefix `M` → **"Önek 2–4 büyük harftir (M)."**;
  - an empty name → **"Programın bir adı olmalı."**
- Do: **"Dersler"** → **"Excel'den yapıştır"**. Paste (tab-separated: Kod, Ad, T, U, L, K, AKTS, Sınıf):
  ```
  MBG 951	Test Dersi I	3	0	0	3	7.5	1
  mbg952	Test Dersi II	3	0	0	3	7.5	1
  MBG 953	Test Semineri	1	0	0	1	5	1
  ```
- See: **"Eklenecek satırlar"**, **"3 satır eklenecek · 0 satır atlandı (başlık, boş)"**, and **"Ders kodu 'mbg952' → MBG 952 olarak düzeltildi."** Press **"3 dersi ekle"**. Pasting the first line again gives **"MBG 951 iki kez listelenmiş."**

**S08 · admin · sections and people**
- Do: one section each, with "Beklenen öğrenci" 20 / 15 / 12. MBG 951 → "1. öğretim elemanı": type `T. E.` → **"Yeni kişi: T. E."** (marked "yeni"). MBG 952 → `S. K.` (new). MBG 953 → leave **unassigned** ("Belirlenmedi").
- See: a warning (not an error) **"MBG 953 §1: atanmadı; çözüm öğretim elemanı çakışmasını kontrol edemez."** The rail shows "2 kişi" and **"2 yeni kişi oluşturulur"**.

**S09 · admin · weekly pattern and rooms**
- Do: for each course: "Haftalık saat" 3 / 3 / 1, "Teorik bloklar" = one block, **"Olası günler"** = Cumartesi only, **"Başlangıç"** = the period at 13:30 (or the first afternoon period), **"Haftalar"** 1–14.
- See: per course **"{n} saat yerleşti"**; a missing start → **"{code}: başlangıç saati seçin."**; no day → **"{code}: en az bir gün seçin."** Set **"Tercih edilen oda"** for MBG 951 to a 15-seat room → **"MBG 951: <room> (<seats>) 20 öğrenciye yetmez."** Then clear it.

**S10 · admin · constraints, pre-check, autosave**
- Do: **"Kısıtlar"** → **"Zaman penceresi"** Saturday 13:30–18:00, **"Zorunluluk"** = **"Mümkünse"**, **"Tüm haftalarda aynı oda"** on.
- Autosave: reload the browser tab. The wizard resumes at the same step (Taslaklar shows **"kaldığınız yer: {step}"**). In a **new browser context** (another device): **"Sunucuda kayıtlı bir programı aç"** → **"Program seçin"** → **"Aç"** rebuilds the courses, sections and people from the server.
- Pre-check as S04: **0 engel** with 1 warning (the unassigned instructor).

**S11 · admin · generate inside the term that now has a published plan**
- Do: **"Oluştur ve çöz"**.
- See: because T27 has the Part A plan published, the choice is **"Oluştur ve mevcut plana ekle"** with **"2027-BAHAR yayındaki planını (#N) en az değişiklikle yeniden çözer; önizlemeyi onaylamadan hiçbir şey yayınlanmaz."** Choose it and confirm.
- See: the moderation preview (F-05 S10 format) against #N:
  - **"Taşınan" 0** for the Part A classes;
  - the 3 new meetings under **"Yeni yerleşen"**;
  - **"Zorunlu puan" 100 → 100**;
  - the scope note "Düzenlenen kapsam dışındaki 0 ders taşındı" (S4, Q9).
- Do: **"Onayla ve yayınla"** → confirm → published.
- Target S1: the suggestion panel for this programme says **"Bu program için geçmiş veri yok"**. Report what is shown.

### Part C · into the live term (S4 of the needs doc)

**S12 · admin · add a tiny programme to 2026-GUZ** (run this last on the stack: it changes the live term)
- Do: a new wizard, term 2026-GUZ, one course `MBG 961` with one section of 10 students, 2 hours on Friday afternoon, unassigned instructor. Then "Oluştur ve mevcut plana ekle".
- See: the preview against `G0`:
  - **"Taşınan"** is 0, or **every** moved class is listed with its cause (`moderation.diff.outside` with 0 "nedensiz");
  - every lock of G0 is in place (F-05 S10 check);
  - "Değişmeyen" is all the other classes.
- Do: **"Vazgeç"**. G0 stays published. The programme's records stay in the term (or the wizard says what happens to them; record it).

### Undo

**S13 · admin · undo a programme creation** (adopted default: 30 days)
- Do: `/admin/audit`, find the Part B programme creation → Geri al.
- Target: the programme, its courses, sections, new people and requests are archived or removed in one step, and runs that reference them refuse a purge ("Purge is refused while ANY run references the row"). Report the observed behaviour. A missing undo is `FAIL (minor)`, because the default was adopted, not decided by the owner.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Compact stepper on phone:** "{i}/8 · {step name}" with a progress bar. A tap opens the step list in a bottom sheet with each step's status. The rail and the preview column are hidden, and "Önizleme" is a disclosure above the step.
- **Grids become cards** (Dersler, Şubeler): one card per row with an "Ekle" button. A tap opens a bottom-sheet form with one column of fields (M-10). "Excel'den yapıştır" sits in the ⋯ menu and opens a text area, then the same preview.
- **Weekly hours:** one day per row with a switch and a time range. "Diğer günlere kopyala" opens a day-chip sheet. Chips are ≥ 44 px.
- **Footer:** "‹ Geri" and "Devam ›" sit in a floating capsule, 44 px high, above the safe-area inset (M-05, M-06). "Devam" never hides behind the on-screen keyboard while a field is focused (M-12).
- **Offline:** with the network emulated offline (`context.setOffline(true)`), editing shows **"Çevrimdışı · değişiklikler bu cihazda tutuluyor"** (spec) and syncs back when online. Report the observed text.
- **Tablet 768:** the rail may be a top stepper and the preview a disclosure. Two-column forms are allowed only if each field is ≥ 280 px wide.

## Flow acceptance

1. A coordinator can create a programme with courses, sections, people (including "unassigned") and weekly patterns without any import. The draft autosaves and resumes on another device.
2. Validation names the course and the problem in Turkish. Errors block generation, warnings do not.
3. Generation in an empty term places every meeting with hard 100 and can be published with the first-plan confirm.
4. Adding a programme to a term with a published plan goes through the minimal-change preview: 0 unexplained moves of published classes, locks kept, nothing published without the confirm.
5. MOBILE.md passes on `/programs/new` (every step) at 390 and 768.

## Scenarios covered

needs-doc S1 (and its "no history" panel as a target), S4; S2 (joint lecture) and S3 (template round trip) are not in this round: `SKIP: next round`, kept here so the suggester tracks them.
