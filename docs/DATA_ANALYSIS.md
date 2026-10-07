# Data Analysis: Classroom Planning Workbooks (2026 Bahar / Final / 2026-2027 Güz)

Source: `Downloads.zip` (6 workbooks, 2.3 MB). Fixture copies with ASCII names live in
`smartsched/backend/tests/fixtures/`. All text is Turkish; the university runs three "seasons"
(Güz = fall, Bahar = spring, Yaz = summer) plus Final and Bütünleme (make-up) exam periods.

There are **three file shapes**:

| Shape | Files | What it is |
|---|---|---|
| **A. Course planning request list** (long table, 1 row per section meeting) | `Bahar Derslik Planlama Listesi v5.xlsx` (1 529 rows), `2026-2027 Güz Derslik Planlama v2.xlsx` (1 037 rows) | Departments' requests + the planning office's definitive room |
| **B. Exam planning request list** | `2026 Final Planlama Listesi v2.xlsx` (926 rows) | Final/Bütünleme exam requests + definitive rooms |
| **C. Weekly room timetable grid** (room × time-slot, one sheet per week) | `2026 bahar derslikler takvimi.xlsx` (19 sheets), `2026-2027 Güz derslikler takvimi.xlsx` (2 sheets), `2026 final derslikler takvimi v2.xlsx` (3 sheets) | The published occupancy board the planner maintains by hand |

Shape A/B are **inputs** to the optimizer; shape C is the **ground-truth output** we can validate against
(and import as "existing bookings").

---

## A. Course planning request list (`Sayfa1`)

Both files have identical headers (Bahar has one extra unnamed trailing column). Excel reports
16 375 columns because of formatting; only 25–26 are populated.

| # | Header (TR) | Meaning | Observed type(s) | Cardinality / quirks |
|---|---|---|---|---|
| 1 | Enstitü/Fakülte/Meslek Yüksekokul | Faculty / institute / vocational school | str | 9–11 distinct; inconsistent spelling & trailing spaces (`MDBF`, `MDBF ; MF`, `İnsan ve Toplum Bilimleri Fakültesi `). Needs canonical lookup. |
| 2 | Bölüm/Program | Department / programme | str | 39 (Güz) / 100 (Bahar) distinct; combos like `AHP+ANS`, `PTL - ENT - DYZ` mean a shared lecture across programmes. |
| 3 | Sınıf | Class year | int or str | `1`, `1. Sınıf`, `1.Sınıf `, `1.2`, `0`, `5` → normalise to int or list of ints. |
| 4 | Yarıyıl | Semester | int or str | `1`, `1. Yarıyıl`, `Güz`, `2025/Güz`, `Güz- Bahar`, `Bilim Tarihi ` (data entry error). |
| 5 | Ders Kodu | Course code | str | 662 / 1 003 distinct. Spacing varies (`MAT 112`, `MAT112`), some with `\n` and prefixes (` YENİ DERS\nACU 311`), some are bare dept codes (`ACU`). Canonical form: `^[A-ZÇĞİÖŞÜ]{2,5}\s?\d{3,4}[A-Z]?$` after upper-casing and collapsing whitespace. |
| 6 | Ders Adı | Course name | str | leading/trailing whitespace and newlines. |
| 7 | Şube | Section (group) | int/str/float | `1`, `1, 2`, `A`, `B1+`, `B1+Int`, `(B1+ INT A)`, `Alttan`, `YL`, `Doktora`, `\xa0`. Treat as free label; split on `,`. |
| 8 | T | Theory hours/week | int | 0–6 (`T`/`U` strings = header repeated in-data). |
| 9 | U | Practice (uygulama) hours/week | int | 0–40 |
| 10 | L | Lab hours/week | int | 0–40 |
| 11 | K | Credits | int/float | `4,5`, `4..5`, `,` → parse decimal with comma. |
| 12 | AKTS | ECTS | int | one row contains `Çarşamba` (shifted row). |
| 13 | Derse Kayıtlanacak Öğrenci Sayısı | Expected enrolment | int | `-`, `\xa0`, and one `12:30:00` (shifted row). **Drives capacity constraint.** |
| 14 | Dersin Günü | Day of week | str | `Pazartesi…Cuma`, `Cumartesi`, `Pazar`, case variants, trailing spaces, and specials: `Perşembe/Cuma`, `Çarşamba- Perşembe` (two days), `Perşembe (uygulama)`, `Çarşamba (Teorik)`, `Hafta içi hergün`, `Belirli günü yok`, `Asenkron`, `UZEM`, `ASG Hastanelerinde yapılacak.`, `Yaz döneminde yapılacak.`, `Danışman ile görüşülerek belirlenecek`. → enum + "flexible"/"not-a-room-request" flags. |
| 15 | Dersin Başlangıç Saati | Start time | time / str / datetime / int | `08:30`, `09.00`, `0`, `-`, float fractions-of-day (`0.5208`). |
| 16 | Dersin Bitiş Saati | End time | same | Durations are multiples of 50-min period grid (e.g. 11:00→13:20 = 3 periods). |
| 17 | Derslik Talebi | Requested room (free text from faculty secretary) | str/int | 113–147 distinct: exact rooms (`A 105`), room + reason (`A103 (Bilg. Lab. Zorunlu)`), building-level (`A Blok'ta Derslik`), capacity-level (`72 kişilik C blok 601-602 vb`), multi-room (`A301-A302-A303 MULTİDİSİPLİN`), generic (`Derslik`, `1 derslik`, `DERSLİK+HASTANE`), dates (`11.12.2026 tarihinde tam gün`), `--`. **This is the soft-preference source; needs an NLP/regex parser + LLM fallback.** |
| 18 | Derslik Planlama - Kesinleşen Derslik | Definitive room set by planning office | str | 103–134 distinct; single (`A 204`), multiple (`A 101 / A 106 / A 107`, `A 101 - A 102`), alternates (`A 107/ B 207`), leading spaces. **Ground truth for validating the solver.** |
| 19 | Dersin 1. Öğretim Elemanı | Primary instructor | str | 345–467 distinct; title + name, case varies, newlines; some are units (`Biyofizik Anabilim Dalı`). Needs normalisation (strip titles, casefold Turkish İ/ı). |
| 20 | Dersin 2. Öğretim Elemanı | Second instructor(s) | str | multiple names separated by `\n` or `/`. |
| 21 | Dersin Öğretim Şekli | Delivery mode | str | `Yüz yüze` (face-to-face), `Online`, `Hibrit`, `UZEM` (distance-ed centre), `Asenkron`, `Hastane` (hospital practice), `Simülasyon Eğitimi`, `Derslik`, `Çevrimiçi`, plus sentences. → enum {F2F, ONLINE, HYBRID, UZEM, ASYNC, HOSPITAL, SIMULATION, OTHER}; only F2F/HYBRID/SIMULATION/`Derslik` need rooms. |
| 22 | Derse Özel Açıklama | Free-text notes | str | 163–223 distinct: quotas (`20 kişilik kontenjan`), curriculum notes, "same room as OPT126", "1. ve 2. öğretim birlikte" (day+evening programmes merged), week lists. **Feed to LLM for constraint extraction.** |
| 23 | Dönemin Tamamı Derslikte Yapılacak | Whole term in classroom? | str | `Evet/Hayır/EVET/0/Lab/Online/Hastane Uygulaması/70% derslikte/11., 12., 13. ve 14. haftalarda`. → bool + weeks override. |
| 24 | Dersliğin Kullanılacağı Haftalar | Weeks the room is used | str/int/float | `Hepsi`, `14`, `1-14`, `1,2,3,…`, `1-5. HAFTALAR DERSLİKTE, 6-14 …`, `0.5`, `100%`, `12. Hafta tam gün derslik ihtiyacı`. → week-set parser (1..14/16) with fallback "all". |
| 25 | Teorik Dersin Uzaktan Eğitim İle Verilebilecek Yüzdesi | % of theory allowed remote | int/float/str | `0`, `0.5`, `50`, `100`, `100%%`, `UZEM`, `x`, `yok`. → 0–100 int. |
| 26 | (unnamed, Bahar only) | Extra remote-education notes | str | 73 values, year-by-year ratios. |

Pivot sheet `Sayfa2` in Güz: counts per day (Pazartesi 192, Salı 195, Çarşamba 187, Perşembe 156, Cuma 121, hospital 11, blank…). Bahar `Sayfa2`: summary (778 lessons, 48 plannable rooms, 4 computer labs, 2 pharmacy labs) + **room capacity buckets** (see Room master below).

### Derived facts (Bahar list)
- ~1 529 rows, ~1 300 have a day+time, ~1 300 have a definitive room → the rest are online/UZEM/hospital/elective placeholders.
- Multi-room definitive assignments occur (large cohorts split across adjacent rooms, e.g. `A 101 / A 106 / A 107 / A 108`).
- Start times align to the 50-minute grid (`08:30, 09:20, 10:10, 11:00, 11:50, 12:40, 13:30, 14:20, 15:10, 16:00, 16:50, 17:30, 18:00, 18:50, 19:40, 20:30, 21:20, 22:10`); a handful don't (`09:00`, `09:30`, `10:00`) → snap with warning.
- Evening (İÖ, "ikinci öğretim") programmes use 18:00–22:50.

## B. Exam planning request list (`2026 Final Planlama Listesi v2.xlsx`, `Sayfa1`, 926 rows)

| # | Header | Meaning | Type | Quirks |
|---|---|---|---|---|
| 1 | Enstitü/Fakülte/MYO | Faculty | str | 15 variants (`ECZACILIK FAKÜLTESİ` vs `Eczacılık Fakültesi`, `Rektörlük Servis` ×2 with spacing). |
| 2 | Bölüm/Program | Programme | str | 95 |
| 3 | Sınıf | Class year | int/str | `1&2`, `1,2,3`, `-` |
| 4 | Ders Kodu | Course code | str | 766 |
| 5 | Ders Adı | Course name | str | includes meeting rows (`4.SINIF STAJ PLANLAMA TOPLANTISI`). |
| 6 | Derse Kayıtlı Öğr. Sayısı | Enrolled | int | 1–200+. Same course appears once per programme (BME 419 ×3 rows = 26+25+19 = 70 students → must be merged for a shared exam; note text says total 102). |
| 7 | Öğretim Elemanı | Instructor | str | 399 |
| 8 | Sınav Tarihi | Exam date | datetime/str | 18 distinct dates (2026-05-13, 2026-06-01…06-12), ranges `11.06.2026 - 12.06.2026`, `-`. |
| 9 | Sınav Başlangıç Saati | Start | time/str | `09.00`, ` 13:30`, `-` |
| 10 | Sınav Bitiş Saati | End | time/str | |
| 11 | Sınavın Yapılacağı Yer … (Talep) | Requested venue | str | 216 distinct, highly free-form: `1 Derslik`, `2 büyük sınıf veya 3 küçük sınıf`, `1 adet sınav kapasitesi minimum 60 kişilik derslik`, `Bilgisayar laboratuvarı`, `1 Gözetmen Talebi` (invigilator request), notes about merged exams (`NUT 470 dersi ile aynı …`). |
| 12 | Kesinleşen Derslik | Definitive room(s) | str | 192 distinct, `A 101 - A 102 - A 106`, `UZEM`, `-`. |
| 13 | Kampüste Yüz Yüze Yazılı Sınav | On-campus written exam flag | `X` | 82 rows |
| 14 | Final/Bütünleme Sınavı Yapılmayacak / Ödev | No exam / assignment instead | `X`, `Final Project` | 17 rows |

## C. Weekly room timetable grid (`… derslikler takvimi.xlsx`)

One sheet per week (`2 - 8 Şubat Bahar Dönem Açılış`, `9 - 15 Şubat`, …, `Final 1 - 7 Haziran`, `BÜT 22 - 24 Haziran`, `Yaz Dönemi`). Layout (204 columns = 7 days × 29 rooms + 1 time column):

- **Row 1**: day labels merged across 29 columns each: `Pazartesi | Salı | Çarşamba | Perşembe | Cuma | Cumartesi | Pazar` (final sheets: `1 Haziran Pazartesi`).
- **Row 2**: room header per column: `"A 101\n (58)"`, `"A 201\n(96)\nTIP"`, `"B 207\nPC"`, `"D 107"` → regex `^([A-D])\s?([zZ]?\d{2,3})\s*(?:\((\d+)\))?\s*(TIP|PC)?$`. Capacity in parentheses; **in Final sheets the capacity is the exam seating (≈ half)**: A 101 58→30, A 204 156→74, A 103/104/105 unchanged (computer labs).
- **Rows 3–20**: 18 time slots in column A: `08:30-09:10 … 16:50-17:30, 17:30-18:00, 18.00-18.40 … 22.10-22-50` (note dots and the typo `22-50`).
- **Row 21/22**: second block (another 29 rooms), same structure; sheets with 73 rows have a third block (rows 44–65) for extra rooms.
- **Cells**: course code(s) occupying the room in that slot. Multi-period lessons appear as vertically merged cells (e.g. `C3:C6` = 4 periods). Combined lectures are written `HEM 334 / NRS 304`, `MBG 598\nmbg 698\nmbg 408`; placeholders `HAZIRLIK` (English prep school blocks, 660 cells in Güz week 1), `UZEM`, `ETKİNLİK`, club names, instructor names (`NAFİYE HOCA`), `Adli Tıp Staj`.
- **Fill colours** encode status (yellow `FFFFFF00` = prep school/reserved, orange `FFC000`, purple `7030A0`, blue `00B0F0`/`0070C0`, green `92D050`): used by the planner as a legend; import as `tag`.
- **Cell comments** (66–250 per sheet, author "Fatih Demir"): operational notes such as `23 şubat dahil a 206 a geçecek` (moves to A 206 from 23 Feb), `ders 10 50 de bitecek` (ends at 10:50), `nrs 450 son 7 hafta` (last 7 weeks only), `9:30 - 10:20` (real exam time). → import as free-text notes attached to assignments; candidates for LLM extraction.

### Room master (union of grid headers and Bahar `Sayfa2`)

| Bucket | Rooms (lecture capacity) |
|---|---|
| Large amphitheatres | A 204 (156), A 203 (148, TIP), C 201 (126), A 207 (120), A 102 (96), A 201 (96, TIP), A 202 (96, TIP), A 205 (94), A 206 (92), D 106 (82) |
| 70–72 seats | A 307 (70), C 301, C 302, C 401, C 402, C 501, C 502, C 601, C 602 (72) |
| 64 seats | A 305, B 202, B 203, B 204, B 205, B 206 |
| 58 seats | A 101, A 106, A 107, A 108, A 109 |
| 38–45 seats | A 306 (38), A 308 (42), C 303, C 403, C 503, C 603 (45), C 304, C 404, C 504, C 604 (40) |
| 30–32 seats | B 201, B 406, B 407, C z01, C 205, C 306, C 406, C 506, C 606 (30), C 305, C 405, C 505, C 605 (32) |
| Computer labs | A 103 (47 / 33 in some sheets), A 104 (41 / 28), A 105 (60), B 207 (PC, 60 exam), "B BİLGİ LAB" |
| Unknown capacity | D 107 (10 in exam sheet) |

Buildings: **A** (floors 1–3), **B** (2nd & 4th floors), **C** (z=ground, 2–6), **D**. TIP rooms (A 201–203) are reserved for the Faculty of Medicine and need the medicine planner's approval (comment: "Planlama için Gözde Ayrancıgil 4073").

### Time grid

18 periods/day, 40 min teaching + 10 min break, Mon–Sun (weekend used for İÖ and exams):

```
P1 08:30-09:10  P7  13:30-14:10  P13 18:00-18:40
P2 09:20-10:00  P8  14:20-15:00  P14 18:50-19:30
P3 10:10-10:50  P9  15:10-15:50  P15 19:40-20:20
P4 11:00-11:40  P10 16:00-16:40  P16 20:30-21:10
P5 11:50-12:30  P11 16:50-17:30  P17 21:20-22:00
P6 12:40-13:20  P12 17:30-18:00  P18 22:10-22:50
```
(P12 is a 30-minute transition slot; requests like 13:30–16:00 cover P7–P9 + 10 min.)

## Key modelling consequences

1. **Entities**: Term/Season → Week (1..16, with type lecture/exam/holiday) → Day → Period; Building → Room (lecture cap, exam cap, tags); Faculty → Program → Section(course, şube, year, enrolment, instructors, mode) → MeetingRequest (day, periods, weeks, room preference, notes) and ExamRequest (date, time range, size, venue preference).
2. **Hard constraints** derivable from data: room capacity ≥ enrolment (lecture) / exam-capacity ≥ cohort (exam, allow multi-room split); no two events in one room-period-week; requests that fix day/time must be honoured; mode ∉ {F2F, HYBRID, SIMULATION} ⇒ no room; TIP rooms only for medicine unless released; computer-lab requirement (`Bilg. Lab. Zorunlu`) ⇒ tags; weeks pattern ⇒ only occupy listed weeks; instructor cannot be in two rooms at once; same program+year cannot have two compulsory lectures/exams simultaneously.
3. **Soft constraints**: honour requested room / building / "same room as X" / minimise room changes across weeks / minimise cohort splitting / keep a programme's day in one building / prefer capacity fit (avoid 20 students in 156-seat hall) / keep evening programmes in B/C blocks, etc.
4. **Validation set**: the definitive-room column (A.18, B.12) plus the grid files let us measure how close the optimizer gets to the human planner, and the grid tells us which slots are already blocked (HAZIRLIK, UZEM, events).
5. **Normalisation layer is mandatory**: Turkish day names, dotted times, comma decimals, NBSP, case-insensitive course codes with Turkish İ, multi-value cells (`/`, `-`, `,`, `&`, newline).
