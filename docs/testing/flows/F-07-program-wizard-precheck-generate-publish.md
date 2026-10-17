# F-07 · Program from scratch: wizard → pre-check → generate → publish

Personas: **admin** (coordinator); planner and viewer for the permission checks. Viewports: desktop, tablet, phone.
Story (needs doc §4, scenarios S1–S4): a new programme with no import and no history, entered by hand, solved, published, without disturbing what is already published.
Owner decisions and adopted defaults:
- program creation can be undone for 30 days;
- with a published plan, adding a programme re-solves with minimal change, and nothing is published before the preview is confirmed (the moderation recreate rules, F-05);
- Q9: a recreate moves 0 published classes outside its scope by default, and lists any extra move with its cause.

Testable on `b75047b` + the P19 UI follow-up (2026-10-16): **yes**. The wizard now runs on server drafts (`/program-drafts`): every step autosaves as field ops, "Taslaklarım" resumes on any device, the server validates each step in TR + EN, the pre-check runs in a rolled-back session, the commit is one transaction, and "Geri al (30 gün)" names its blockers. There is **no example button** any more (owner rule: no demo data); Part A types the real MBG Tezli YL rows instead. Steps S01–S11 and S13 are proven by `smartsched/frontend/e2e/followup.phase19.spec.ts` (tests 1, 2 and 6).

## Preconditions

1. Restore the snapshot. Create an empty future term as admin (rooms are global, so the term has rooms and nothing else):
   ```bash
   curl -fsS -X POST "$API/terms" "${H[@]}" -d '{"code":"2027-BAHAR","name":"Bahar 2027","kind":"REGULAR","start_date":"2027-02-01","end_date":"2027-05-14","week_count":14,"is_active":false}' | jq -c '{id,code}'
   ```
   Record `T27`. `GET /runs?term_id=$T27` → `[]`.
2. For Part C: the published Güz run `G0` from F-05 precondition 1.
3. Use initials only for people typed into the wizard: "T. E." and "S. K.".

## Steps

### Part A · a programme by hand in an empty term (S1 of the needs doc)

**S01 · admin · open the wizard**
- Do: sidebar **"Yeni program"** (or `/programs/new`).
- See (`wizard-landing`): title **"Yeni program"**, subtitle **"İçe aktarma olmadan program oluşturun. Yazdıkça kaydedilir."**, the intro, **"Hedef dönem"** (`wizard-term`, the real terms), **"Program oluştur"** (`wizard-start`), **"Taslaklarım"** (`draft-list`; "Henüz taslağınız yok." on a fresh stack) and **"Oluşturulanlar"** (`committed-list`, "Sihirbazla oluşturulan programlar 30 gün boyunca tek adımda geri alınabilir."). No "…örneğiyle başla" button exists.
- planner.test sees the same (planning.edit). viewer.test sees **"Program oluşturmak için planlama düzenleme izni gerekir"** with **"Programı bir koordinatöre oluşturtun ya da izin isteyin."**, and no form.

**S02 · admin · start a draft**
- Do: Hedef dönem = 2027-BAHAR → **"Program oluştur"**.
- See: the URL becomes `/programs/new/<draft id>?step=program`. The header reads **"Taslak · 2027-BAHAR dönemine henüz hiçbir şey yazılmadı"**. The rail (`wizard-rail`, label "Program sihirbazı adımları") lists **"Program · Dersler · Şubeler · Öğretim elemanları · Kohortlar · Odalar ve haftalık düzen · Kısıtlar · Oluştur ve çöz"**, each with "tamam", "başlanmadı", "{n} hata" or "{n} uyarı" (`rail-<step>` carries `data-status`). The rail foot reads **"Taslak · 2027-BAHAR dönemine son adıma kadar hiçbir şey yazılmaz, çözülmez ya da yayınlanmaz."**
- API: `GET /program-drafts?mine=true` lists the draft with `status: "draft"`.

**S03 · admin · programme, with the server's validation**
- Do: **"Ders kodu öneki"** = `MBĞ`.
- See: the save state (`save-status`) **"Kaydediliyor…"**, then **"Tüm değişiklikler kaydedildi · {when}"**; under the field **"Ders kodlarında Türkçe harf kullanılmıyor"**. "Devam ›" moves focus to the error summary (`error-summary`, **"Bu adımda {n} hata var"**) listing **"Program adı gerekli"**, with **"Yine de devam et"**.
- Do: prefix `MBG`, **"Birim (fakülte / enstitü)"** `Fen Bilimleri Enstitüsü` ("Var olan birim"), **"Program adı"** `Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (Test)`, **"Düzey"** "Tezli YL".
- See: `rail-program` turns "tamam".
- Autosave: reload the tab. The same values come back on the same step. In a **new browser context** (another device): `/programs/new` → Taslaklarım shows the draft with **"kaldığınız yer: {step}"** → **"Devam et"** opens it with everything typed so far.
- Conflict (optional, two tabs): edit the same field in both. The later save wins; the other tab shows **"Bu taslakta başka biri de çalışıyor: {n} alanı sizden önce değiştirmişti, sizin değeriniz kaydedildi."** (`overwritten`).

**S04 · admin · courses from Excel**
- Do: **"Dersler"** → **"Excel'den yapıştır"** (`wizard-paste`). Paste (tab-separated: Kod, Ad, T, U, L, K, AKTS, Sınıf; the real Bahar rows R182–R198 of MBG Tezli YL):
  ```
  Kod	Ad	T	U	L	K	AKTS	Sınıf
  MBG 598	Seminer	0	0	0	0	9	1
  mbg532	Epigenetik	3	0	0	3	9	1
  MBG 534	Proteomiks	3	0	0	0	9	1
  ```
  → **"Satırları oku"**.
- See: **"Eklenecek satırlar"** (`paste-preview`), **"3 satır eklenecek · {n} satır atlandı (başlık, boş, hatalı ya da tekrar)"** and **"Ders kodu 'mbg532' → MBG 532 olarak düzeltildi."** Nothing is added before **"3 dersi ekle"**. After it: 3 rows, and a warning (never an error) **"MBG 598: T+U+L = 0; 6. adımda haftalık saat girin"**.
- **"Var olan dersi ekle"** searches the catalogue; a reused course is shown as **"Katalogdaki ders olduğu gibi kullanılır; kodu ve saatleri buradan değişmez."**

**S05 · admin · sections, joint teaching, people, cohorts**
- Şubeler: "Beklenen öğrenci" 120 / 80 / 75. **"Ortak ders ekle"** searches the term's sections (`GET /terms/{id}/sections/search`); in 2027-BAHAR there is none ("Bu dönemde eşleşen şube yok."). Part B covers a real joint lecture.
- Öğretim elemanları: MBG 598 → `T. E.` → **"Yeni kişi: T. E."** (marked "yeni"); MBG 532 → `S. K.`; MBG 534 left empty. See one warning **"MBG 534 §1: öğretim elemanı atanmadı; çözüm öğretim elemanı çakışmasını kontrol edemez"**, the rail "{n} kişi ({fresh} yeni)", and for known people the load line **"Bu dönem {n} saat"** (`instructor-load`).
- Kohortlar: **"Sınıflardan oluştur"** → one cohort **"MBG 1. sınıf"** with the compulsory courses ("Zorunlu dersler (çakışmaz)") and **"Seçmeli grubu (çakışabilir)"**. The server warns when the compulsory hours need more days than allowed (**"Haftada {h} saat zorunlu ders; kohort için en az {d} gün gerekir"**). A compulsory course in no cohort is listed under **"Hiçbir kohorta girmeyen zorunlu ders: …"**.

**S06 · admin · weekly pattern and rooms**
- Do: per course **"Başlangıç"** 14:20 / 11:00 / 10:10 and **"Olası günler"** Cuma / Salı / Cuma only.
- See: per course **"{n} saat yerleşti"** and the live fit (`fit-line`, from `GET /terms/{id}/rooms/fit`): **"120 öğrenci · {count} oda sığar: … A 207 (120) …"**. Set **"Tercih edilen oda"** of MBG 532 to `C 504` → **"C 504 (40) 80 öğrenciye yetmez · {n} oda sığar: …"**. Clear it again.

**S07 · admin · constraints and pre-check**
- Do: **"Kısıtlar"** → optionally a **"Zaman penceresi"** with **"Zorunluluk"** "Mümkünse", then **"Ön kontrolü çalıştır"** (`precheck-run`).
- See: **"Ön kontrol (bu programın oturumları, dönemin geri kalanıyla birlikte)"**, **"Taslak, dönemin geri kalanıyla birlikte denenir; hiçbir şey kaydedilmez."**, the result **"Ön kontrol: {errors} engel, {warnings} uyarı"** with readiness ("hazır", "bakılması gerekenler var", "engel var"), **"Sığan odalar"** per class (`precheck-rooms`, contains "A 207 (120)"), and each issue with **"Düzelt"** jumping to the step.
- API: `POST /program-drafts/<id>/precheck` → 200; `GET /sections?term_id=$T27` is still empty (rolled back).

**S08 · admin · generate**
- Do: **"Oluştur ve çöz"** step.
- See: the summary table (`generate-summary`) with each step's state and "Düzelt"; the panel **"Geçmiş veriden öneriler"** with **"Bu program için geçmiş veri yok"** (`wizard-no-history`) and "Öneriler, programın dersleri bir dönem planlanıp yayınlandıktan sonra oluşur ve hiçbir zaman kendiliğinden uygulanmaz."; **"Nasıl devam edilsin?"** with **"Oluştur ve dönemi çöz"** ("Henüz yayında plan yok: program yazılır, ardından tüm dönem için ilk çözüm başlar.") and **"Yalnızca oluştur"**. Errors disable the button (**"Önce hataları düzeltin; uyarılar engellemez."**); warnings never do.
- Do: **"Yalnızca oluştur"** → confirm **"Bu programla devam edilsin mi?"** ("2027-BAHAR dönemine 1 program, 3 ders, 3 şube, 1 kohort, …" and "Tek seferde yazılır; 30 gün içinde geri alınabilir.") → confirm.
- See (`wizard-committed`): **"Program oluşturuldu · 2027-BAHAR"**, the counts, **"Dönemi çöz"**, **"Moderasyonda gör"**, **"Başka bir program"**, the undo panel **"Geri al (30 gün)"** with **"{date} tarihine kadar geri alınabilir."** and the history panel again.
- API: `POST /program-drafts/<id>/commit {"solve":"none"}` → 201; 3 sections in T27 with `MAN:` keys; one audit row.
- With "Oluştur ve dönemi çöz" instead, a TERM run starts and you land on `/runs/<id>`; publish it from the run report as before (`run-publish`).

**S09 · admin · undo the creation (30 days)**
- Do: `/programs/new` → **"Oluşturulanlar"** → the row → **"Aç"** → **"Geri al"** (`undo-open`) → **"{name} geri alınsın mı?"** ("Bu oluşturmanın yazdığı her şey … arşivlenir ve kuralları kapatılır. Çözümler ve yayındaki plan değişmez.") → **"Geri al"**.
- See: **"Program geri alındı · 2027-BAHAR"** and **"Arşivlendi: 3 şube, … ders, … kişi."**; the draft is read-only (**"Bu program geri alındı; taslak salt okunur."**).
- Blockers: when something else now depends on the rows (a booking, another programme's joint link, a published run), `GET /program-drafts/<id>/undo` lists them in TR and the panel shows each under the button (`undo-blockers`); the button is disabled only when the server says `can_undo: false`.
- API: `GET /sections?term_id=$T27` → 0 items.

### Part B · a real joint lecture into the live Bahar term (S2 + S4 of the needs doc)

**S10 · admin · MBG 534 taught together with MBG 014**
- Do: a new draft in **2026-BAHAR** (it has a published plan): programme as S03, one course `MBG 534`, one section of 10. In Şubeler **"Ortak ders ekle"** → search `MBG 014` → pick the Bahar section.
- See: the link chip and **"Ortak toplam: {n} öğrenci"** (`joint-total`) = 10 + the MBG 014 enrolment; the room fit in step 6 uses that total. The pre-check reports **"{n} ortak ders tek oturumda birleşti."** (`precheck-joint`).

**S11 · admin · generate inside a term with a published plan**
- Do: **"Oluştur ve çöz"** → the choice is **"Oluştur ve mevcut plana ekle"** with **"2026-BAHAR yayındaki planını (#N) en az değişiklikle yeniden çözer; önizlemeyi onaylamadan hiçbir şey yayınlanmaz."** Confirm.
- See: you land on `/moderation/recreate/<run>` (the F-05 S10 preview), with the chain (`chain`) and the baseline switcher **"Karşılaştır:"**:
  - **"Taşınan"** is 0 for unrelated classes, or every move is explained (`moderation.diff.outside` with 0 "nedensiz");
  - the new meetings under **"Yeni yerleşen"**;
  - **"Zorunlu puan" 100 → 100**.
- Do: **"Vazgeç"** (or publish, if this stack is throwaway). Back on the draft, the result screen keeps "Geri al (30 gün)"; the published run is a blocker only if you published.

### Part C · into the live term (S4 of the needs doc)

**S12 · admin · add a tiny programme to 2026-GUZ** (run this last on the stack: it changes the live term)
- Do: a new wizard, term 2026-GUZ, one course `MBG 961` with one section of 10 students, 2 hours on Friday afternoon, unassigned instructor. Then "Oluştur ve mevcut plana ekle".
- See: the preview against `G0`:
  - **"Taşınan"** is 0, or **every** moved class is listed with its cause (`moderation.diff.outside` with 0 "nedensiz");
  - every lock of G0 is in place (F-05 S10 check);
  - "Değişmeyen" is all the other classes.
- Do: **"Vazgeç"**. G0 stays published. The programme's records stay in the term (or the wizard says what happens to them; record it).

### Undo

**S13 · admin · undo from the audit log** — covered by S09 on `/programs/new` (adopted default: 30 days). `/admin/audit` lists the creation as one row; the undo itself lives on the wizard's result screen, not in the audit log.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Compact stepper on phone:** "{i}/8 · {step name}" with a progress bar. A tap opens the step list in a bottom sheet with each step's status. The rail and the preview column are hidden, and "Önizleme" is a disclosure above the step.
- **Grids become cards** (Dersler, Şubeler): one card per row with an "Ekle" button and one column of fields (M-10). "Excel'den yapıştır" opens as a bottom sheet (`paste-dialog` with `data-variant="sheet"`), then the same preview.
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

needs-doc S1 (with its "no history" panel), S2 (joint lecture, Part B), S4; S3 (template round trip) is not in this round: `SKIP: next round`, kept here so the suggester tracks it.
