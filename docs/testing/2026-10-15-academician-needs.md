# Academician and scheduling-office needs for Phase 19 (2026-10-15)

Ledger: `academician-analysis-2026-10-15`. Personas:

- **(a) a senior academician** who teaches three courses a term and has firm room and time preferences;
- **(b) "Fatih Bey"**, the faculty's classroom planning officer. Every term he collects requests from the departments as
  Excel sheets, PDF memos and e-mails, and fills the "Kesinleşen Derslik" column himself.

Scope: what the Phase 19 features (`docs/ROADMAP.md` "Phase 19") must do to be useful in a real Turkish term. The
features are: any-format intake, learned suggestions with a resettable memory, from-scratch programme creation, and a
moderation tab with re-solve.

Method: this is analysis from code and data, so no stack was started. Sources:

- the real 2026 Bahar / Güz / Final workbooks in `smartsched/backend/tests/fixtures/`, read with the importers' own
  parsers (`app.importers.normalize`);
- the importer and API code;
- the 2026-10-08 test reports: `2026-10-08-real-data-feasibility.md`, `2026-10-08-schedule-vs-planner.md` and
  `2026-10-08-planner-usability.md`.

All numbers below were measured on those fixtures today; reproduction is in the appendix. Instructors are referred to by
their course codes, not their names.

Product-owner decisions already made (2026-10-15, also in `docs/ROADMAP.md`) are treated as fixed:

- **D-PDF:** PDF/DOCX requests may be extracted with the Claude API. The coordinator reviews every row before it is
  saved. A KVKK notice is shown, and an admin can switch the feature off.
- **D-RESET:** suggestion memory can be reset per person, per term, or entirely. Resets are admin-only, audited, and
  can be undone for 30 days.
- **D-POLICY:** locks are never moved. After locks come coordinator-set priorities, then "place the most classes". The
  policy is configurable per term.
- **D-SUGGEST:** learned suggestions are never applied automatically. Accepting one adds a SOFT preference.

---

## 1. BLUF

- **Preferences mostly live in free text, and SmartSched does not read most of it.**
  - 43 % of Bahar rows (664/1 528), 48 % of Güz rows (496/1 037) and 29 % of Final rows (269/926) carry at least one
    preference signal in the request / notes / weeks columns.
  - The planning-list importer parses only the "Derslik Talebi" cell. The "Derse Özel Açıklama" column (565 non-empty
    Bahar cells, 217 distinct texts) is stored as plain text and never becomes a rule. That column holds the
    building wishes ("A veya C blokta": 7 Bahar and 17 Güz notes), the accessibility wish ("Giriş kata yakın olsun": 2 Bahar rows, 1 Güz), the
    "no class in the next 2 hours" wish (RAD 202) and most of the "same room as X" links.
- **The parser that does run mis-reads Turkish negation and alternatives.**
  - `parse_venue_request("Mümkünse B Blok olmasın")` returns *prefer building B*, the opposite of the request.
  - "A veya C blokta" becomes building C only.
  - "A 206 veya C 403-404 veya A 106-107" (Final row 19, PTL252) becomes one five-room set, so the alternatives
    are lost.
  - "kolçaklı sandalye olmasın" (5 RTT exams) and "giriş kata yakın" yield nothing.
  - Intake must fix these before any "learning" is built on top. Otherwise the memory learns the inverse.
- **The rule that makes learning safe: suggest at the level the data supports.**
  - Across terms, the same instructor keeps the same *building* in 75 of 155 cases (48 %). The same *top room*
    repeats in only 14 of 155 (9 %).
  - Bahar and Güz share only 54 course codes, because courses alternate between the seasons.
  - So suggestions must compare a term with the same season of earlier years, and work at building, feature and
    time-band level.
  - Every suggestion must carry its evidence count. It must never come from a planner error (7 locked double bookings
    in Bahar) or from a trusted over-capacity lock (33 Bahar rows).
- **The moderation tab is the coordinator's main need, and its core data already exists.**
  - The data can be joined today: request, then definitive room, then run assignment, then diagnosis.
  - Satisfaction can be measured right now. Specific-room requests were granted exactly in 73/84 Bahar cases, 49/56
    Güz and 70/100 Final; building-only requests in 4/4, 5/5 and 18/20.
  - Missing pieces:
    - a link from a login `User` to an `Instructor` (an academician cannot see "my requests");
    - a run-to-run diff;
    - an approve-then-publish step for re-solved runs;
    - a "why not" for planner decisions that came with no reason.
- **From-scratch programme creation is blocked.**
  - There is no create endpoint for faculties, courses, sections or meeting requests. Only programmes
    (`POST /departments`) and terms can be created.
  - The only route today is to type a planning-list Excel by hand.
  - The minimal flow is an 8-step wizard plus a pre-filled template download (§4).
- **The product owner still has 12 finer-grained policy questions (§6).** Each has a recommended default.
- **§7 has 37 Given/When/Then scenarios**, all built on real fixture rows.

---

## 2. Real request shapes

### 2.1 What arrives each term, and which importer handles it

| # | Document (as it really arrives) | Real fields / content (from fixtures) | SmartSched path today | Gap (severity) |
|---|---|---|---|---|
| A | **Department planning list**, Excel `… Derslik Planlama Listesi.xlsx`. Sheet `Sayfa1` has 25 columns. Sheet `Sayfa2` has the room buckets | Enstitü/Fakülte/MYO, Bölüm/Program, Sınıf, Yarıyıl, Ders Kodu, Ders Adı, Şube, T/U/L/K, AKTS, Derse Kayıtlanacak Öğrenci Sayısı, Dersin Günü, Başlangıç/Bitiş Saati, **Derslik Talebi (Sekreterlik)**, **Kesinleşen Derslik (only Fatih Bey fills this)**, 1./2. Öğretim Elemanı, Öğretim Şekli (Yüz yüze/Online/Hibrit), **Derse Özel Açıklama**, Dönemin Tamamı Derslikte, Kullanılacağı Haftalar, Uzaktan Eğitim Yüzdesi | `importers/planning_list.py` (`POST /imports/planning-list`, xlsx/xlsm): sections, meetings, weeks, mode, definitive rooms as LOCKED, non-room venues | **Notes column not parsed** (B). Request-cell negation and alternatives (B, see 2.3). No `.xls`/`.ods` (m: every fixture is `.xlsx`, so it is unverified that departments send these) |
| B | **Exam planning list**, `… Final Planlama Listesi.xlsx`, 14 columns | Fakülte, Program, Sınıf, Ders Kodu, Ders Adı, Kayıtlı Öğr. Sayısı, Öğretim Elemanı, Sınav Tarihi, Başlangıç/Bitiş, **Sınavın Yapılacağı Yer (Bölüm talebi)**, **Kesinleşen Derslik**, Kampüste Yüz Yüze, Yapılmayacak/Ödev | `importers/exam_list.py` (`POST /imports/exam-list`) | Same venue-parser gaps. The venue column is the richest free text of all (alternatives, "same room as my lecture", "same floor", furniture) (B) |
| C | **Weekly room board** ("schedule map"), `… derslikler takvimi.xlsx`, one sheet per week, rooms × 18 periods, merged cells, blocks (HAZIRLIK, ETKİNLİK, UZEM, staj) | Room headers with capacity and tags, class codes in cells, closures | `importers/weekly_grid.py` (`POST /imports/weekly-grid`): blocks and capacities. The board's class placements are *not* an input | The Güz board has weeks 1–2 only; Final sheet 3 copies the previous week's headers; board-only codes are not reported (schedule-vs-planner §6). The board is never used as "last term's map" for learning (M) |
| D | **Room master** (the coordinator's own list), CSV/xlsx | `code, capacity, exam_capacity, tags, building, floor, bookable, notes` (`tests/fixtures/room_master.csv`, 87 rooms) | `importers/room_master.py` (`POST /imports/room-master`) | No column for **step-free access**, entrance floor or lift, AV / board, or seating type (fixed desks vs armrest chairs). These attributes are needed by real requests (2.2). Typed room features exist (`services/rooms_features.py`) but are not part of this file (M) |
| E | **Preference sheets and memos** from instructors or departments (xlsx, csv, docx, pdf, txt) | Free form | AI path: `POST /terms/{id}/preferences/upload` (`ai/ingest.py`: xlsx/xlsm/csv/docx/pdf/txt/md, 5 MiB, 1 500 units, each with a `SourceRef` file/sheet/row/page/line; proposals only). No-AI path: `POST /terms/{id}/studio/preferences/mapping` (xlsx/csv column mapping) | Scanned PDFs: `pypdf` reads only the text layer, so a scanned EBYS letter gives no units. Needs an explicit "metin yok" message, or OCR behind D-PDF (M). No `.eml`/`.msg` (M). No KVKK notice and no admin off-switch exist yet. AI is "off" only when no `anthropic_api_key` is set (`ai/client.py`, `services/settings_service.py`), so D-PDF's switch and notice are still to build |
| F | **E-mails** from instructors ("Hocam, Cuma olmasın …") | Free text, often forwarded by the secretariat | None. Today the secretariat retypes them into the notes column. Real traces: "Giriş Kata Yakın Olmasını rica etti hocamız" (Bahar rows 609, 610; Güz row 543), "Dersliğin B blokta olmasını talep ediyor hocamız" (Bahar row 1529) | `.eml` intake through path E, with the sender kept as the requester. The sender is the person whose history the moderation tab shows (M) |
| G | **Student-system (OBS) export**, CSV, with the enrolment per section | **No sample in the repo**, so the columns cannot be verified | None. Enrolment comes only from list column A. 76 Bahar classes have no enrolment and are planned with an estimate (feasibility doc, "Review fixes") | An enrolment-only update import keyed by course code + şube that changes nothing else and reports the change against the room (M). **Action: ask the registrar for one real export before designing the mapping. Do not guess its columns** |
| H | **Legacy CRBS database** | Bookings, rooms, users | `importers/crbs_legacy.py` (`POST /imports/crbs`) | Out of scope here |
| I | **JSON** | Not seen in any department submission | No importer reads JSON. Studio presets have a portable form (`studio_rules.to_portable` / `from_portable`) | Define JSON as SmartSched's own round-trip format: requests, preferences and rules of a term, used for copying and archiving. Do not use it for third-party formats (m) |

### 2.2 What the free text actually asks for

These are keyword counts over the request, notes, "dönemin tamamı" and weeks columns (Final: the venue, "kampüste" and
"yapılmayacak" columns). One row can hit several categories. The regexes are approximate; for example "olmasın" also
matches "olmasını".

| Category | Bahar rows | Güz rows | Final rows | Real example (fixture row) | Parsed today? |
|---|---|---|---|---|---|
| Same room as / taught jointly with another course | 133 | 81 | 60 | "ODY124 ile aynı derslikte olacaktır." · "MBG YL programında MBG 546 kodlu dersle aynı yer ve gün ve zamanda açılacaktır." | Request cell only (`same_room_as`); the notes column is not parsed |
| Online / UZEM / asynchronous (no room) | 206 | 149 | 0 | "Asenkron", "Ders çevrimiçi işlenecektir." | Yes (`parse_mode`, `parse_weeks`) |
| Lab / PC / workshop | 168 | 118 | 58 | "A 103 BİLG. LAB. ZORUNLU", "Ders OPT Labda yapılacak", "Bu ders D302 Atölyemizde yapılacaktır." | Partly (PC tag; a lab outside the pool gets `needs_room=false`) |
| Specific room | 83 | 57 | 104 | "A207 nolu sınıf istenmektedir" (RAD 202, rows 1052/1058) | Yes |
| Capacity / quota / combined size | 65 | 66 | 42 | "Moleküler Biyoloji, Biyomedikal…, Tıp Fakültesi ortak alacağı için toplam 70 kişilik sınıf" · "Sunuşlar yapılacak. Toplam 102 öğrenci var." | Only "N kişilik"; "toplam N öğrenci" in a note is ignored |
| Hospital / off-campus | 53 | 52 | 7 | "Hastane Uygulaması", "Yok, Acıbadem Maslak" | Yes (no room) |
| Week ranges | 48 | 44 | 10 | "İLK 7 HAFTA YÜRÜTÜLECEK", "12., 13. ve 14. hafta derslik kullanılacaktır." | Yes in the weeks column; **not in the notes column** |
| Building wish | 26 | 30 | 21 | "A veya C blokta derslik verilmesi talep edilmektedir." (7 Bahar notes, 17 Güz notes) | Request cell only, and alternatives collapse to the last building |
| 1st + 2nd shift (öğretim) taught together | 22 | 0 | 10 | "1. ve 2. ÖĞRETİM BİRLİKTE DERS ALACAKTIR." | No (merge decided by the identity rules only) |
| Avoid (negative) | 5 | 1 | 11 | "Mümkünse B Blok olmasın" (ING 302, rows 366/636) · "kolçaklı sandalye olmasın" (RTT 124/222/282/292/294) | **Inverted** (becomes *prefer B*) or ignored |
| Time buffer / back-to-back / before-after | 8 | 2 | 0 | "Arkasındaki 2 saate ders konmaması rica olunur" (RAD 202) · "OPT126 ile ard arda yapılacak aynı derslik olsun lütfen" (OPT 118, row 335) · "dersliği 13:30 itibariyle rezerve etmemiz rica ediliyor. Seminer öncesi bilgisayar hazırlığı" (MBG 408/416, rows 34/35) | No |
| Accessibility | 2 | 1 | 0 | "Giriş Kata Yakın Olmasını rica etti hocamız" (ACU 303, ACU177; Güz ACU 305) | No (confidence `low`, no field) |
| Equipment / room type | – | – | – | "beyaz tahta hem de barkovizyon aktif… amfi tipi derslik verilmesini rica ediyorum" (OPT 124, row 471) · "Sıralar olan sınıf" (RTT) | No |
| Exam in the lecture room | – | – | 3+ | "Ders yaptığım sınıf uygundur. A101" (ACU 244) · "B blokta ders yaptığım sınıf büyüklüğü uygundur" (ACU 140, ACU 302) | Only an explicit room code. "My lecture room" is not resolved |
| Same floor / same block for split exams | – | – | 3 | "En az 2 büyük sınıf (mümkünse aynı katta, aynı katta olamıyorsa da aynı blokta…)" (PHAR 132/128, 156/122, 156/124) | No (count 2 + AMPHI tag only) |
| Faculty-wide policy written per row | 72 | – | – | "Eczacılık Fakültesinde ders çakışma kuralları uygulanacak." | No. It is one rule, not 72 notes |
| Pending / unknown | 5 | – | – | "Dersi verecek öğretim üyesi henüz belli değildir." · "Gün ve saat bilgisi henüz planlanmadığı için boş bırakılmıştır." | Imported as a gap. Should be the request status "Bekliyor" (waiting) |

What the coordinator needs from intake:

- **Every extracted item shows its source cell or line**, the original Turkish text, and the proposed structured rule
  side by side. `SourceRef` already does this for path E. Rows from paths A and B need the same.
- **"Mümkünse", "rica olunur" and "olabilirse" mean soft. "zorunlu", "mutlaka" and "gerekmektedir" mean hard.** The
  proposed hardness must follow the wording. Example: "A 103 BİLG. LAB. ZORUNLU" is hard, while "mümkünse amfi" is soft.
- **Alternatives ("veya") stay alternatives.** If the definitive room equals any one of them, the request is satisfied.
- **One policy line repeated on 72 rows** should be proposed once, as a faculty-scope rule, with "72 satırda geçiyor".
- **Spelling variants of one course**, such as `PSI 214`/`PSY 214`, `SYS 18`/`SYS 018`, `BİF111`/`BIF111` and the
  "2022-2023 / 2024-2025 müfredatı" pairs, are proposed as one lecture with a confirmation. They must never be merged
  silently.

### 2.3 Parser defects found today (inputs to the intake tickets)

Probe: `parse_venue_request(text)` (`app/importers/normalize.py:1294`). It is applied to planning-list "Derslik Talebi"
and exam-list "Yapılacağı Yer" only.

| Real text | Result today | Expected | Sev. |
|---|---|---|---|
| "Mümkünse B Blok olmasın" | `building="B"`, needs_room, medium | avoid B (soft) | **B** (the inverted preference would also feed learning) |
| "A veya C blokta derslik verilmesi talep edilmektedir." | `building="C"` | building ∈ {A, C} (soft) | M |
| "A 206 veya C 403-404 veya A 106-107" (Final 19, PTL252) | one set `[A206, C403, C404, A106, A107]` | three alternative sets. The planner granted C 403 - C 404, so the request is *satisfied* | M |
| "64 Mevcut… B202 ve B203 olabilir. Veya B205-B206, veya A veya C blokta iki adet sınıf." (Final 431, MBG 224) | rooms `[B202, B203, B205, B206]`, building `C` | alternatives {B202+B203} or {B205+B206} or two rooms in A or C. Exam seats ≥ 64 | M |
| "Giriş Kata Yakın Olmasını rica etti hocamız" | nothing (confidence low) | accessibility: step-free / entrance-floor room, scoped to the **person** | M |
| "Sıralar olan sınıf (kolçaklı sandalye olmasın)" | nothing | room feature "fixed desks", hard for the exam | m |
| "Ders yaptığım sınıf uygundur. A101" | room A101 | the same, plus "the lecture room of this course" as a reusable pattern | m |
| "En az 2 büyük sınıf (mümkünse aynı katta…)" | count 2, tag AMPHI | count ≥ 2, large; soft same-floor, else same-building | m |
| Notes column (any text) | stored in `MeetingRequest.notes`, never parsed (`planning_list.py:250`) | the same parser runs over notes, and its results are proposals that need review | **B** |

---

## 3. Preference and learning expectations

### 3.1 What "previous changes or requests" exist to learn from

| Signal | Where it is stored today | What it tells the coordinator |
|---|---|---|
| Department request vs the coordinator's definitive room | `MeetingRequest.requested_*` vs `definitive_room_*`, and the same for exams | What Fatih Bey grants, and what he does not. **Measured:** specific-room requests granted exactly in 73/84 (Bahar), 49/56 (Güz) and 70/100 (+5 partly, Final) cases; building-only requests honoured in 4/4, 5/5 and 18/20 |
| Coordinator edits after import | `ImportedSnapshot` vs the current row (`studio_classes.changed_fields`) | Systematic corrections, such as always raising one course's enrolment, or always moving one lecture out of B 4xx |
| Manual moves on a run | `Assignment.origin = MANUAL`, `is_locked` | "He always drags ADS 112 back to A 106" |
| Accepted / rejected rule proposals and diagnosis fixes | `ConstraintRow.source` (`FILE/ADMIN/AI/UPLOAD`), `source_ref`, audit events | What he agrees with |
| Previous terms' definitive rooms and times | earlier terms in the same DB | Year-over-year stability |
| Weekly board (last published map) | `blocks` only; the placements are not stored | **Not available.** Importing the board's placements as a "published map" snapshot would give a second ground truth (schedule-vs-planner found 46 board/list time differences in Bahar week 3) |

### 3.2 Which repeated patterns he wants surfaced (and what the data supports)

| Pattern | Measured on Bahar 2026 + Güz 2026 (main instructor, canonical name) | Level to suggest at |
|---|---|---|
| Same instructor, same room across terms | 155 instructors have definitive rooms in both terms. Top room equal: **14 (9 %)**; share at least one room: 41 (26 %) | **Do not suggest the room** from a different season. Suggest only when the same course repeats in the same season with a history of at least 2 terms |
| Same instructor, same building across terms | Top building equal for **75/155 (48 %)**. Example: the instructor of PSI214/PSY214/PSY278 (Bahar) and PSI213/PSY213/PSY277 (Güz) has 8 of 8 roomed rows in A block, in at least four different rooms (A 206, A 109, A 207, A 308) | **Building**, stated with its evidence count |
| Same instructor, same room within one term | 43/118 Bahar and 30/78 Güz instructors with at least 3 roomed rows have one room for ≥ 60 % of them | Room, within the term ("bu dönemki diğer derslerinizle aynı derslik") |
| Same slot across terms | Only **54 course codes** occur in both Bahar and Güz (seasonal alternation). 24 of them share a weekday, and only 2 share a room | Compare the same season year over year (Bahar 2026 → Bahar 2027). With one year of data, no slot suggestions |
| Avoided days | 78 instructors have at least 3 dated rows in each term. 59 of them never teach on at least one weekday in either term; **33 never on Friday**. Example: the instructor of ACU105/ACU138/TUR102 (Bahar) and ACU105/ACU135/TUR101 (Güz), 20 rows, Monday–Thursday only | Suggest a **question**, not a rule: "Cuma günü hiç dersiniz olmadı (2 dönem, 20 ders). Cuma'dan kaçınılsın mı?" With 3–6 rows, an unused day is often a coincidence |
| Lab needs | 168 Bahar and 118 Güz rows mention a lab | Suggest the tag (PC / LAB) for the same course next term. Only exact-course carry-over |
| Joint lectures and "same room as" | 133 Bahar, 81 Güz, 60 Final | Carry the link to the next same-season term as a proposal ("geçen Bahar ODY124 ile aynı derslikteydi") |
| Accessibility | 3 explicit rows (2 Bahar, 1 Güz) | **Never inferred.** See 3.4 |
| Exam room = lecture room | ACU 140 / 244 / 302 say so explicitly | Propose the lecture room for the exam when its *exam* capacity fits |
| Coordinator's habitual overrides | 11 Bahar / 6 Güz / 25 Final specific requests ended in another room. Examples: PHY 102 asks D 204 and gets D 202 (rows 49, 210); PTL 204 asks C 403 and gets C 501 | Surface the pattern to the **coordinator**, not the instructor: "PHY 102 için D 204 talebi 2 kez D 202'ye çevrildi. Talep formunu güncelleyelim mi?" |

### 3.3 How suggestions should be phrased

The persona asked for: Turkish first; one sentence; evidence with counts and terms; what accepting does; three buttons.
Examples (a TR string with its EN equivalent):

> **Öneri:** PSI 214 için A Blok tercih edilsin mi?
> *Gerekçe:* Bu öğretim üyesinin son 2 dönemdeki 8 derslikli dersinin 8'i A Blok'taydı (Bahar 2026: 4/4, Güz 2026: 4/4).
> *Kabul ederseniz:* yumuşak tercih (ağırlık 5) eklenir; kesin kural değildir.
> [Kabul et] [Bu dönem değil] [Bir daha önerme]

> **Suggestion:** Prefer A block for PSI 214?
> *Why:* 8 of this instructor's 8 roomed classes in the last 2 terms were in A block (Bahar 2026: 4/4, Güz 2026: 4/4).
> *If accepted:* adds a soft preference (weight 5), not a hard rule.

Rules for the text:

- name the scope: course, section, person, programme or faculty;
- give the count and the terms;
- show the weight;
- never say "her zaman" (always) when the evidence is from fewer than 3 terms;
- link "Kanıtı göster" (show evidence) to the source rows.

### 3.4 When a suggestion must NOT be applied (and when it must not even be shown)

D-SUGGEST covers the "never auto-apply" part. These cases should also **suppress** a suggestion or force a question
instead:

1. **The evidence comes from a planner error.** The 7 locked double bookings in Bahar (MAT 112 §1 / HEM 236 in A 204;
   PSK 254 §1 / EHM 312 §1 / ING 102 §8 in C 602 …, schedule-vs-planner §3) must not teach "HEM 236 → A 204".
2. **The evidence is a trusted over-capacity lock (D1).** Examples: MBG 034 §1 with 80 students in B 407 (30 seats),
   and MBG 012 §1 with 80 in C 504 (40). That makes 33 Bahar and 44 Güz rows.
3. **The room changed:** it is now non-bookable, re-tagged, or below the class's current enrolment.
4. **The instructor changed**, or the instructor is a placeholder: "Yabancı Diller", "Yüz yüze" in the instructor
   field, or a coordinator listed as the instructor (the Güz case in schedule-vs-planner §3).
5. **The row is online, UZEM, hospital or off-campus.** Its "room" is no evidence of a preference.
6. **The evidence is one-off:** a single week, an ETKİNLİK week, or a week-split segment.
7. **The evidence is from the other season,** for room or slot suggestions (3.2).
8. **The suggestion contradicts an explicit request this term.** The explicit request always wins and the suggestion
   is hidden.
9. **Accessibility or health:** never inferred from history. The system may ask "Bu dersin hocası geçen dönem giriş
   katı istedi; bu dönem de geçerli mi?" only when the earlier request was explicit. The stored item is a room
   requirement ("basamaksız erişim gerekli"). It never stores the reason, which can be health data under KVKK
   art. 6.
10. **The same suggestion was dismissed with "Bir daha önerme".**

### 3.5 What "reset memory" means to them

The scopes were decided (D-RESET). What each scope must and must not delete, from the coordinator's point of view:

| Scope | Deletes | Keeps | Why |
|---|---|---|---|
| **Per person** (an instructor) | learned patterns about that person, their pending suggestions, their "Bir daha önerme" dismissals | their requests, run history, audit log; **accepted** preferences (these are ordinary soft rules now, listed separately with their own delete) | Typical trigger: the instructor changed their working pattern (became dean, new lab, part-time). Their history is still true |
| **Per term** | patterns *derived from* that term's data (e.g. Güz 2026 was abnormal because of building works) | the term itself, its runs, and rules accepted in later terms | Excludes one term from the evidence; it does not erase the term |
| **Everything** | all learned patterns, all pending suggestions, all dismissals | all source data and all accepted rules | "Start learning again" after a policy change |

Additional expectations:

- The reset dialog shows what will disappear, e.g. "Bu öğretim üyesi için 3 öneri ve 1 'bir daha önerme' kaydı
  silinecek." Undo is listed in an "Son sıfırlamalar" (recent resets) list for 30 days.
- **A reset is not a KVKK erasure.** A data-subject deletion request needs a separate admin flow that also removes the
  source data. The UI must not suggest that a memory reset satisfies one.
- Accepted rules that came from suggestions keep a `source_ref` back to the suggestion. After a reset they still say
  "öğrenilmiş öneriden kabul edildi (öneri hafızası sıfırlandı)" ("accepted from a learned suggestion; the suggestion
  memory has been reset").

---

## 4. From-scratch program creation

Case: a new master's programme opens in Bahar 2027, with no prior term and no planning list. Real patterns for such
programmes in the fixtures:

- weekend afternoon blocks: HEM 566 and HEM 504 on Saturday 13:40–18:00, HEM 509 on Sunday;
- small enrolments;
- joint teaching with an undergraduate or another graduate course ("MBG 534 … MBG YL dersi ile aynı yer, gün ve
  saatte");
- the instructor not yet known ("Dersi verecek öğretim üyesi henüz belli değildir").

**Today:**

- `POST /terms` and `POST /departments` (programme) exist.
- There is no create endpoint for faculties, courses, sections or meeting requests. `reference.py` is read-only, and
  `studio_classes` offers only bulk edit and revert.
- So the only route is to hand-build a planning-list Excel and import it (Severity **B** for this feature).

Minimal steps the coordinator expects (a wizard, each step skippable when the data exists):

1. **Term:** pick an existing term (e.g. 2027-BAHAR) or create one with weeks and holidays. This exists.
2. **Unit and programme:**
   - pick or create the faculty/institute (e.g. Sağlık Bilimleri Enstitüsü), then create the programme ("… Tezsiz Yüksek
     Lisans");
   - mark it evening/weekend if relevant. This links to the existing `evening_programs_in_buildings` rule.
3. **Courses:**
   - code, name, T/U/L/K, AKTS, class year (1–2 for a master's programme);
   - the code checker warns about collisions and near-duplicates (`PSI`/`PSY`, leading zeros).
4. **Sections:**
   - şube and expected enrolment. With no history, enrolment is required, or marked "tahmini" (estimated) and shown as
     such in reports;
   - instructors: pick an existing person, create one, or set "Belirlenmedi" (not yet assigned), which blocks only
     instructor-clash checks.
5. **Meetings:**
   - day and time fixed, or flexible over a list of days (as BES 439: "Salı / Çarşamba / Perşembe / Cuma");
   - weeks ("Tüm haftalar", "İlk 7 hafta");
   - mode: online meetings need no room;
   - room needs: capacity, tags, building wish.
6. **Links:**
   - "same room / same time as" an existing course (joint lecture);
   - "back to back with" (the OPT 118 / OPT 126 pattern);
   - shift merge ("1. ve 2. öğretim birlikte").
7. **Pre-check:** the existing studio pre-check, scoped to the new programme first, then the term.
8. **Place without disturbing others:**
   - generate with `stability` against the active run (`parent_run_id`). That machinery exists (`solver/repair.py`,
     weights `stability_room` 20, `stability_time` 30);
   - show the diff (§5.3); approve and publish.

Shortcuts the coordinator will use more than the wizard:

- **"Şablon indir"** (download template): the department's own 25-column `Sayfa1` template, with programme and faculty
  pre-filled. The department fills it, and it comes back through the normal planning-list import.
- **"Önceki programdan kopyala"** (copy from an earlier programme): copy the courses, sections and rules of a similar
  existing programme, then edit.
- The suggestion panel says "Bu program için geçmiş veri yok; öneri üretilmedi" ("no history for this programme; no
  suggestions yet"). It does not stay empty and it does not borrow other programmes' patterns.

---

## 5. Moderation tab

One admin area, "Moderasyon", with five entity views. Each list has search, filters (term, faculty, programme, status)
and an export. Every edit is audited and creates a pending change, not a silent edit of the published run.

### 5.1 User stories and what to see at a glance

| Entity | User stories | At a glance (list columns) | Detail panel | Edits |
|---|---|---|---|---|
| **Class** (section + its meetings) | As the coordinator I open "PHAR 240" and see every meeting across weeks, with its room and status. As an academician I see where my class is this week | Code, şube, programme/year, enrolment vs seats, instructor(s), day/time, room, weeks, status chip (Yerleşti / Kısmen / Yerleşmedi), lock icon, changed-since-import chip | Timeline across weeks (week splits visible); the planning-list row and board cell it came from; diagnosis codes in Turkish; linked joint lectures | Enrolment, time, room pin (with "from week N / date"), weeks, needs_room, links. Each edit shows the imported value and has a revert |
| **Person / academician** | As the coordinator I see one person's whole term and their request history. As the academician (TEACHER login) I see my own requests and their outcome, and add a preference | Name, title, unit, number of classes, number of requests, **satisfaction rate** (this term and earlier terms), open suggestions, accessibility flag (yes/no only) | Week view of all their classes with clash highlights; request history per term with outcome and reason; preferences (explicit vs learned-accepted); dismissed suggestions; "reset this person's memory" (admin) | Preferences (add, soften, hard↔soft), priority, link to a login user. **Missing today: `User` ↔ `Instructor` link (B for the academician story)** |
| **Request** (one row or document item) | As the coordinator I see every request from the files, mail and uploads, and its fate. I close the loop with the department | Source (file / sheet / row, or upload / page / line, or e-mail sender), requester, original text, parsed meaning, hardness, status (Yeni / İnceleniyor / Kabul / Reddedildi / Karşılandı / Karşılanmadı / Bekliyor), last change | Original text next to the structured interpretation; history (imported → edited → accepted); every run's outcome for it | Re-interpret (pick the alternative, change hardness), accept or reject with a reason (the reason is sent back to the requester), mark duplicate |
| **Preference** (rule / constraint) | As the coordinator I see all rules in force, where they came from, and how many classes they touch | Kind, scope (course / person / cohort / faculty), hard/soft + weight, source (FILE / ADMIN / AI / UPLOAD / **LEARNED**), matched class count (0 is a red warning: the usability B1 bug), satisfied in the active run (n/m) | Rule sentence in Turkish; matched classes; provenance; conflicts with other rules | Enable/disable, weight, hardness, scope, delete, copy to another term |
| **Matching** (request ↔ assignment) | As the coordinator I ask "who got what they asked for, who didn't, and why" | Request, granted room/time, verdict (**Karşılandı / Alternatifle karşılandı / Kısmen / Karşılanmadı / Değerlendirilmedi**), reason code, who decided (solver / coordinator / import) | Why not: the diagnosis (`Diagnosis.code`, `params`: holder of the room, capacity, grid block, cohort busy) in Turkish; the free options that would satisfy it | Accept the alternative, pin the requested room (pre-checked), record a coordinator reason when the import carried none |

"Why not" for imported planner decisions: the planning list stores the definitive room, but no reason for it. Example:
PHY 102 asked for D 204 and got D 202.

- The verdict reads "Karşılanmadı: planlama birimi kararı (gerekçe girilmemiş)" (unsatisfied: planning-office
  decision, no reason given).
- The coordinator can add a reason from a short list: kapasite (capacity), çakışma (clash), bina (building), ekipman
  (equipment), diğer (other, with text).

Satisfaction rates should count:

- "Alternatifle karşılandı" (satisfied with an alternative) as satisfied;
- "Değerlendirilmedi" (online, hospital, not evaluated) as neither.

### 5.2 Fairness views the coordinator asked for

- Satisfaction per department and per person, for this term and earlier ones. A department whose building wishes are
  always denied must be visible.
- "3 dönemdir karşılanmadı" (unsatisfied for 3 terms) badge on a person or request (see Q6).
- Requests that arrived after the department deadline are shown with a "geç" (late) tag (see Q3).

### 5.3 How "recreate schedule" must behave

1. **Scope first.** Choose "only what my edits affect" (default), a programme or faculty, or the whole term. The
   default re-solves the smallest neighbourhood, using the existing repair path (`solver/repair.py`) and `stability`
   against the active run.
2. **Minimal disruption:**
   - published placements that are neither locked nor in scope may move only if that is needed to place more
     classes;
   - every such move is listed with its cause ("PHAR 240 §1 A 206'ya alındığı için HEM 334 A 207'ye kaydı": "HEM 334
     moved to A 207 because PHAR 240 §1 took A 206");
   - optional move budget: "en fazla N yayınlanmış ders yer değiştirsin" (at most N published classes may move).
3. **Diff before publish.** The draft run is compared with the active run. **There is no run diff endpoint or UI
   today.** The diff shows:
   - moved, newly placed and newly unplaced classes (before → after room/time and the trigger);
   - affected people ("Bu değişiklik 4 öğretim üyesini etkiliyor");
   - satisfaction delta;
   - hard score.
4. **Approval:**
   - the draft stays inactive until the coordinator approves;
   - optionally a second approver, such as the faculty secretary, for changes that touch other faculties' rooms. The
     existing approvals module can carry this;
   - "Yayınla" (publish) = `POST /runs/{id}/activate`.
5. **After publish:**
   - affected instructors get an in-app and e-mail notice listing only *their* changes;
   - the previous run stays re-activatable ("Önceki sürüme dön", back to the previous version).
6. **Integrity:** the hard score stays 100 on placed events, or the infeasibility is explained per event (unchanged
   product rule). A recreate never drops a lock (D-POLICY).

---

## 6. Fairness and priority questions for the product owner

D-POLICY fixed the order: locks, then coordinator-set priority, then most classes placed. These are the finer
questions it leaves open, each with a recommended default.

| # | Question | Recommended default | Why |
|---|---|---|---|
| Q1 | What does "coordinator-set priority" attach to: request, section, programme, cohort or person? | **Per request**, defaulting from tiers: (1) compulsory undergraduate courses with fixed times, (2) service courses with many cohorts (ING/ENG, MAT 112), (3) electives ("Alan Seçmeli"), (4) graduate. The coordinator can override per item | Mirrors how Fatih Bey triages, and keeps the priority visible per row |
| Q2 | Does academic seniority (Prof. / Doç. / Dr. Öğr. Üyesi / Öğr. Gör.) raise priority? | **No by default.** It is an explicit per-term toggle, shown in the run report when on | Titles are in every name cell, so it is easy to apply by accident. Students' needs (cohort clashes, capacity) and accessibility should outrank rank |
| Q3 | First-come vs deadline batch: does submission time matter? | **Everything received before the department deadline is equal.** Late requests rank below on-time ones. Submission order is never a tie-breaker within the window | Departments submit through secretaries at different speeds. First-come would reward the fastest secretariat, not the strongest need |
| Q4 | What if a lock contradicts an explicit accessibility requirement of its instructor? | **Block the run** at pre-check with a named conflict, and let the coordinator move the lock. Locks are never moved automatically (D-POLICY) | Neither may be broken silently |
| Q5 | Two locks hold one room at once (the planner's own double booking, 7 pairs in Bahar): which is placed? | **Neither is chosen silently.** Pre-check lists the pair. If the coordinator runs anyway, the higher-priority one (Q1) is placed, and the run report and the moderation "Matching" view show the other as "Karşılanmadı: kilit çakışması" (lock clash) | Today the relaxation keeps "the most events, then locks", which is invisible to the department |
| Q6 | Should a person or department denied repeatedly get a boost ("rotation")? | **Show it, don't automate it:** a "N dönemdir karşılanmadı" badge and a sort; the coordinator raises priority by hand | An automatic boost is hard to explain and can be gamed |
| Q7 | Weight of an accepted learned preference vs an explicit request this term | **Learned < explicit:** learned 5, explicit soft 10 (the current `room_preference` default) | Explicit wishes of this term must win over history |
| Q8 | May a lock seat more students than the room holds (D1 `trust_locked_rooms`)? E.g. 102 students pinned to a 30-seat room | **Refuse at the edit** with the capacity named ("102 öğrenci 30 kişilik B 201'e sığmaz"). Allow only an explicit override with a reason, listed under accepted exceptions | The 2026-10-08 usability test (scenario X) showed the capacity is never named today |
| Q9 | How many already-published classes may move in a recreate? | **Default 0 outside the scope.** Any extra move needs it to place more classes and is listed with its cause. A per-run budget is optional | Minimal disruption is the coordinator's first concern after publication |
| Q10 | Should satisfaction be balanced across departments (e.g. building wishes)? | **Report only in v1**, per department; no balancing objective | Measure first; the data shows building wishes are already granted (4/4, 5/5, 18/20) |
| Q11 | Who sees whose requests and history? | Academician: own only. Department secretary: own department. Coordinator/admin: all. Accessibility shown as yes/no only, reason never stored | KVKK data minimisation |
| Q12 | The department form and the academician's own wish disagree. Which counts? | **The department form is the official request.** The academician's wish is a soft preference, shown side by side, ranked lower | Matches the "Sekreterlik fills the request" column ownership |

---

## 7. Acceptance scenarios (Given / When / Then)

Fixtures: `smartsched/backend/tests/fixtures/`. Abbreviations: "Bahar list" = `bahar_derslik_planlama_listesi_v5.xlsx`,
"Final list" = `final_planlama_listesi_2026_v2.xlsx`. Row numbers are 1-based sheet rows of `Sayfa1`.

### Intake

**I1. Negation is not inverted (unit test).**
- Given the text "Mümkünse B Blok olmasın".
- When `parse_venue_request` (or its successor) parses it.
- Then the result is a soft avoid on building B, and `building` is not "B".

**I2. Notes become proposals, not rules.**
- Given the Bahar list is imported.
- When the coordinator opens the intake review for Bahar row 366 (ING 302).
- Then a proposal "B Blok olmasın (yumuşak)" is listed with `source_ref {file, sheet: "Sayfa1", row: 366, excerpt}`.
- And no constraint exists until he accepts it.

**I3. Building alternatives.**
- Given a notes cell "A veya C blokta derslik verilmesi talep edilmektedir." (7 Bahar rows, 17 Güz rows).
- When it is parsed.
- Then the proposal is building ∈ {A, C} (soft), proposed once per row, and "N satırda aynı ifade" groups them in the
  review.

**I4. Room alternatives and satisfaction.**
- Given Final row 19 (PTL252), with request "A 206 veya C 403-404 veya A 106-107" and definitive "C 403 - C 404".
- When the exam list is imported.
- Then three alternative room sets are stored.
- And the moderation Matching verdict is "Alternatifle karşılandı".

**I5. Alternatives with exam seats.**
- Given Final row 431 (MBG 224).
- When it is parsed.
- Then the alternatives are {B 202 + B 203}, {B 205 + B 206}, or 2 rooms in A or C, with exam seats ≥ 64.

**I6. Accessibility is a person-level room requirement that needs confirmation.**
- Given Bahar rows 609/610 ("Giriş Kata Yakın Olmasını rica etti hocamız").
- When the review shows the proposal.
- Then it is "Basamaksız erişimli derslik (öğretim üyesi için)", it needs explicit acceptance, and it stores no reason
  text.
- And if the room master has no access attribute for any room, pre-check says so. It does not silently ignore the rule.

**I7. Faculty policy de-duplicated.**
- Given 72 Bahar rows with "Eczacılık Fakültesinde ders çakışma kuralları uygulanacak."
- When they are reviewed.
- Then one faculty-scope proposal is shown with "72 satır" and links to the rows. No 72 separate rules are created.

**I8. CSV encoding.**
- Given a room-master CSV saved in Windows-1254 with `;` delimiters and the codes `C z01` and `B Blok Bilg. Lab.`.
- When it is imported.
- Then Turkish letters (ş, ğ, İ) round-trip, and `B Blok Bilg. Lab.` maps to B 207.

**I9. Scanned PDF.**
- Given a PDF with no text layer.
- When it is uploaded to the preferences endpoint.
- Then the response says "Bu PDF'de okunabilir metin yok (taranmış belge olabilir)" and creates 0 proposals. It is not
  an empty success.

**I10. AI off-switch and KVKK (D-PDF).**
- Given the admin AI switch is off.
- When a DOCX is uploaded.
- Then the user gets a clear refusal, and the xlsx/csv column-mapping path is offered.
- Given the switch is on and the user has not acknowledged the notice.
- When the user uploads for the first time.
- Then the KVKK notice must be acknowledged before any text leaves the server.

**I11. Review every row (D-PDF).**
- Given a DOCX yielding 12 proposals.
- When the coordinator accepts 10 and rejects 2.
- Then exactly 10 constraints exist with `source="UPLOAD"` and a `source_ref` (file, paragraph).
- And the 2 rejections are kept as negative feedback for the suggestion memory.

**I12. E-mail intake keeps the requester.**
- Given an `.eml` from an instructor asking "Cuma olmasın".
- When it is ingested.
- Then the proposal's requester is that sender (linked to the Instructor when the e-mail matches), and it appears in
  that person's request history.

**I13. JSON round trip.**
- Given Bahar 2026 is imported.
- When the term's requests and rules are exported to JSON and imported into an empty term.
- Then the counts of sections, meetings and constraints and the definitive rooms are identical.

### Learning and memory

**L1. Building suggestion with evidence.**
- Given Bahar 2026 and Güz 2026 are imported, and a new same-season term exists.
- When suggestions are generated for the instructor of PSI214/PSY214/PSY278.
- Then the suggestion is "A Blok tercih" with "8/8 derslikli ders, 2 dönem".
- And no specific room is suggested, because at least 4 different rooms were used.

**L2. No cross-season room suggestion.**
- Given only Güz 2026 history for a course.
- When Bahar 2027 suggestions are generated.
- Then no room or slot suggestion is made for it. At most a building suggestion, labelled "farklı dönem verisi".

**L3. Never auto-applied (D-SUGGEST).**
- Given 5 pending suggestions.
- When the coordinator generates a run without accepting any.
- Then the run's constraint set and its `params` are identical to a run made with suggestions disabled.

**L4. Accepting adds a soft rule.**
- When the coordinator accepts L1.
- Then one constraint is added with `hardness="soft"`, weight 5, `source="LEARNED"` and a `source_ref` to the
  suggestion and its evidence rows.

**L5. No learning from planner errors.**
- Given the Bahar locked double booking MAT 112 §1 / HEM 236 in A 204 (Thursday).
- When suggestions are generated.
- Then none proposes A 204 for HEM 236 (or MAT 112 §1) on the strength of that row.

**L6. No learning from over-capacity locks.**
- Given MBG 034 §1, 80 students locked in B 407 (30 seats).
- When suggestions are generated.
- Then B 407 is not suggested for MBG 034.

**L7. Weekday question, not rule.**
- Given the instructor of ACU105/ACU138/TUR102 (20 rows, Monday–Thursday only).
- When suggestions are generated.
- Then the item is phrased as a question ("Cuma'dan kaçınılsın mı?"), and accepting creates a soft `day_window`
  rule.

**L8. Dismissal sticks.**
- Given "Bir daha önerme" on L1.
- When the term is re-imported (`on_conflict=keep`).
- Then L1 is not shown again.

**L9. Per-person reset (D-RESET).**
- Given 3 suggestions and 1 dismissal for person X and 5 suggestions for others.
- When an ADMIN resets X.
- Then X has 0 suggestions and 0 dismissals, and the others still have 5.
- And one audit event is written, and X's accepted rules are untouched.
- And a PLANNER gets 403 for the same call.

**L10. Undo window.**
- Given the reset in L9.
- When an admin undoes it within 30 days, the 3 suggestions and the dismissal return.
- When an admin tries after 30 days, the undo is refused with the date it expired.

**L11. Per-term reset excludes that term's evidence only.**
- Given L1's evidence from Bahar 2026 and Güz 2026.
- When Güz 2026 memory is reset.
- Then L1 recomputes from Bahar 2026 alone ("4/4, 1 dönem").
- And Güz 2026 runs and requests still exist.

### From scratch

**S1. New programme with no data.**
- Given the term 2027-BAHAR, empty except for rooms.
- When the coordinator creates through the wizard:
  - the programme "… Tezsiz Yüksek Lisans";
  - 3 courses and their sections with estimated enrolments;
  - Saturday 13:40–18:00 meetings;
  - one section with instructor "Belirlenmedi".
- Then pre-check passes, generate places every meeting, and the suggestion panel says "Bu program için geçmiş veri
  yok".

**S2. Joint lecture with an existing course.**
- Given S1, and an existing graduate course in the term.
- When a new course is linked "aynı yer, gün ve saatte".
- Then both are one solver event with the summed enrolment, and the moderation Class view shows the link on both.

**S3. Template round trip.**
- When the coordinator downloads the programme template and fills 3 rows in Excel.
- And re-imports it through `POST /imports/planning-list`.
- Then the rows match what the wizard would create (same sections, meetings and weeks).

**S4. Adding a programme does not reshuffle the term.**
- Given an active Bahar run.
- When S1's programme is added and placed with stability.
- Then the diff shows 0 moved published classes, or lists each move with its cause.

### Moderation, recreate, publish

**M1. Academician sees own history.**
- Given a TEACHER user linked to the instructor of RAD 202.
- When they open "Taleplerim".
- Then they see "A 207 + sonraki 2 saat boş" (rows 1052/1058) with the verdict per week, and nobody else's requests.

**M2. Unexplained planner decision.**
- Given Bahar rows 49/210 (PHY 102, requested D 204, definitive D 202).
- When the Matching view opens.
- Then the verdict is "Karşılanmadı: planlama birimi kararı (gerekçe girilmemiş)".
- And the coordinator can add the reason "kapasite", which then shows in the academician's view.

**M3. Move from a date.**
- Given PHAR 240 §1 (Bahar row 545: Monday 08:30–10:50, 80 students, list room A 206) and its Thursday lab rows
  855/856.
- When the coordinator pins the lecture to A 206 "23 Şubat'tan itibaren".
- Then the pin covers week 4 to term end, and the UI shows the date next to the week number.
- And the two lab rows are not affected.
- And the recreate diff lists only the classes that had to move for it.

**M4. Infeasible request refused with the reason.**
- Given ING 302 with 102 students.
- When the coordinator pins it to B 201 (30 seats) on a full day.
- Then the edit is refused before solving with "102 öğrenci 30 kişilik B 201'e sığmaz", together with the free rooms
  with at least 102 seats at that time.
- And when the coordinator overrides with a reason, the run report lists it under accepted exceptions with the
  capacity named.

**M5. Turkish cohort rule matches the right cohorts.**
- When the coordinator writes "Hemşirelik 1. sınıf dersleri 17:30'dan sonra olmasın".
- Then the preview lists Hemşirelik Y1 and Hemşirelik (İngilizce) Y1 with a match count > 0. This is the regression
  for usability B1.
- And it asks whether to include the year-1 rows of the nursing master's programmes, e.g. HEM 566 on Saturday
  13:40–18:00. They would be the only violators, since the Bahar list has no undergraduate nursing year-1 row ending
  after 17:30.

**M6. Diff and approval before publish.**
- Given any coordinator edit.
- When "Yeniden oluştur" (recreate) finishes.
- Then the new run is inactive, and the diff vs the active run lists moved, new and unplaced classes and the affected
  people.
- And "Yayınla" needs a confirm.
- And after publishing, the affected instructors are notified with their own changes only, and the previous run can be
  re-activated.

**M7. Recreate never drops a lock.**
- Given 522 planner locks in Bahar week 3.
- When a scoped recreate runs.
- Then every lock that was placed before is still placed in the same room.
- And any lock that cannot be placed was already unplaced before, with the same reason code.

**M8. Satisfaction numbers.**
- Given the three fixtures imported.
- When the Matching dashboard opens.
- Then specific-room requests show 73/84 (Bahar), 49/56 (Güz) and 70/100 + 5 partly (Final), and building-only
  requests 4/4, 5/5 and 18/20.
- Today Final row 19 (PTL252) counts as "partly", because its three alternatives are flattened into one five-room set.
  After the alternatives fix (I4) it counts as satisfied, so the exact Final number rises.

**M9. Zero-match rule warning.**
- Given any preference whose selector matches 0 classes.
- When the Preference list renders.
- Then the row is red, with "Hiçbir dersle eşleşmiyor", and generate warns before running.

---

## Appendix: reproduction

All measurements use `python3 -I`. The scripts import `app.importers.normalize` from `smartsched/backend` (path added
explicitly). The fixtures are the repo's own files.

- **Free-text categories (§2.2):** each row's request, notes, "dönemin tamamı" and weeks cells (Final: venue,
  definitive, on-campus, no-exam) are joined, folded with `tr_casefold`, and matched against keyword regexes per
  category. Rows are counted when columns 0–5 are not blank.
- **Parser probes (§2.3):** `parse_venue_request(text)` printed for each quoted text, plus every request/venue cell
  containing `olmasın`, `istemiyor` or `veya`.
- **Grant rate (§3.1, M8):** a row counts if `parse_venue_request(request).room_codes` is non-empty. That set is
  compared with `parse_definitive_rooms(definitive).room_codes`: equal, overlapping, or disjoint. Building-only means
  the request has a building but no room codes, and every definitive room is in that building.
- **Cross-term patterns (§3.2):**
  - main instructor = the first canonical name from the "1. Öğretim Elemanı" cell (`split_person_names` +
    `canon_person_name`);
  - weekday from `parse_day`, only when exactly one day is given;
  - rooms from `parse_definitive_rooms`;
  - "top room" / "top building" = the most frequent per instructor per term;
  - course codes via `canon_course_code`.

  Counts are first-instructor only, and an instructor is matched across terms by canonical name. A title change is
  folded by `canon_person_name`; a renamed person would be missed.
- **Code facts:**
  - create endpoints: `app/api/v1/reference.py` has GET only;
  - `departments.py` has POST;
  - `studio.py` has no class create;
  - `imports.py` has planning-list / exam-list / weekly-grid / room-master / crbs;
  - preference intake: `app/api/v1/chat.py:167` (`/terms/{id}/preferences/upload`) and `app/api/v1/studio.py:277`
    (`/studio/preferences/mapping`);
  - stability: `app/services/run_params.py` (`stability`), `app/services/studio.py:485` (`parent_run_id`),
    `app/solver/repair.py`;
  - no run diff route in `app/api/v1/runs.py`;
  - `User` has no instructor link (`app/models/system.py`).
