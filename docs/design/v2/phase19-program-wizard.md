# Phase 19 · Program wizard: create a program from scratch, no import

Owner: design-pro (Phase 19 surfaces) · Status: spec v1.0 (2026-10-15) · Routes: **`/programs/new`** → **`/programs/new/[draftId]?step=program|courses|sections|instructors|cohorts|rooms|constraints|generate`**, and **`/programs`** (list + drafts)
Related: [`phase19-intake.md`](phase19-intake.md) (the import path; same stepper), [`phase19-moderation.md`](phase19-moderation.md) §5.4 (minimal-change re-solve and preview), [`../generator-studio.md`](../generator-studio.md) (rules, pre-check, generate), `components/admin/setup-wizard.tsx` (the CRBS first-run wizard: a different, one-time flow that is not changed here), [`liquid-glass.md`](liquid-glass.md), [`motion.md`](motion.md) (motion is owned there).

Worked example throughout: **Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans** (Fen Bilimleri Enstitüsü) for 2026-GÜZ, rebuilt by hand. Its real Bahar rows are 182–199 of `bahar_derslik_planlama_listesi_v5.xlsx`. Rooms and capacities come from `room_master.csv`.

---

## 0. BLUF

- **Eight steps in a left rail**: Program → Dersler → Şubeler → Öğretim elemanları → Kohortlar → Odalar ve haftalık düzen → Kısıtlar → Oluştur ve çöz. Steps can be visited in any order. Each shows ✓, a warning count or an error count in the rail.
- **Saved as you type, resumable anywhere.** A server-side draft autosaves (800 ms debounce) and shows "Tüm değişiklikler kaydedildi · 1 dk önce". Drafts are listed under Programlar › Taslaklar and resume on the step where you left. **A draft never touches the term.** Only the last step writes, as one transaction with audit and 30-day undo.
- **Inline validation at three levels.** Field errors appear on blur ("Ders kodu 'MBG532' → MBG 532 olarak düzeltildi" is an info fix). Step checks appear in the rail ("MBG 541: 3 saatlik ders için yalnızca 2 saat yerleştirildi"). Feasibility checks at step 8 reuse the Studio pre-check. Errors only block the final write. Warnings never block.
- **Built for real university shapes**: joint teaching with another program ("MBG 534, lisans MBG 014 ile aynı yer, gün ve saatte"), multi-program seminars (MBG 598 with MBG 408, 416, 698 in A 207), T/U/L hours that become weekly blocks, lab tags, İÖ evening windows, and rooms with no known capacity (B 501).
- **Step 8 has two paths**: "Oluştur ve mevcut plana ekle" runs a minimal-change re-solve against the published 2026-GÜZ plan and opens the moderation preview (nothing is published until approved). "Yalnızca oluştur" writes the program without solving.

## 1. User stories

| # | As a… | I want to… | So that… | Acceptance |
|---|---|---|---|---|
| W1 | institute coordinator | create a new graduate program with no Excel to import | a program that exists only on paper gets a timetable | `/programs/new` starts a draft with no file needed |
| W2 | coordinator | paste my course list from Excel into the courses step | I don't retype 7 courses | pasting TSV fills rows (Kod, Ad, T, U, L, K, AKTS, Sınıf), with a preview of the parsed rows before insert |
| W3 | coordinator | link a course to an existing undergraduate course taught together | joint teaching is modelled, not double-booked | "Ortak ders: MBG 014 (Proteomiks, lisans 4. sınıf, 75 öğr.)" in Şubeler. Both share one meeting |
| W4 | coordinator | pick instructors who already exist and see their load | I don't overbook a professor | the instructor combobox shows "Bu dönem 9 saat" next to each name, and warns above the configured limit |
| W5 | coordinator | define how T3 becomes weekly blocks | "3 saat tek blok" vs "2+1" is my decision | the pattern picker shows options derived from T/U/L, with the total checked |
| W6 | coordinator | be told early when no room fits | I fix it before solving | "MBG 598 + 3 ortak ders: 120 öğrenci · sığan odalar: A 207 (120), C 201 (126), A 203 (148), A 204 (156)" or an error when none exists |
| W7 | coordinator | stop and resume tomorrow | creating a program takes several sittings | the draft is in Programlar › Taslaklar with "Kaldığınız yer: Kohortlar" |
| W8 | coordinator | add the program to the published plan without reshuffling everyone | other programs keep their rooms | step 8 defaults to minimal change and lands in the moderation preview |
| W9 | admin | undo a program created by mistake | data stays clean | the creation is one audit event with "Geri al" for 30 days (archives everything it created) |

## 2. References

| # | App · screen / flow (Mobbin, web) | Pattern we take | Avoid |
|---|---|---|---|
| R1 | [Lyssna · Study setup › Availability](https://mobbin.com/screens/68486aa6-77c8-4d4a-ab37-5ab93bbdeb84) | **Left step rail with ✓ per step** (Study details ✓ · Screener · Team members ✓ · Availability ✓), **"All changes saved · 1 minute ago"** under the rail, "Next: Recruit" as the primary, and a **weekly-hours editor** (day toggle + from–to + add/copy) | — |
| R2 | [Outseta · Setup guide 8/8](https://mobbin.com/screens/b1bcf27d-e787-4a4d-81f7-a1ec5515f5fe) and [Front · Setup guide](https://mobbin.com/screens/e89fb38e-4c40-41be-afe3-89e75623822b) | Checklist with a description per step, "Completed" state on the right, and a progress bar. Used for the Taslaklar list and the step-8 summary | yellow celebration ticks |
| R3 | [Time2book · Get started with your studio](https://mobbin.com/screens/2e6265e9-a171-4d31-b7f7-fe0433cfe5c0) | **Numbered steps with a contextual action button per step** ("Add service", "Set up schedule"). Used for the step-8 summary's "Düzelt" links | — |
| R4 | [Motion · Creating a workspace (7 screens)](https://mobbin.com/flows/423c6fa6-9b73-409e-b306-30a1b6d07521) | **Live preview on the right** that fills in as you type (workspace → project → tasks table). Used for the Program step's preview card of the timetable-to-be | — |
| R5 | [Amie · Creating a workspace (13 screens)](https://mobbin.com/flows/313ec1b8-3d78-43fb-86ba-b57a2d8ef672) | Choice cards for the first decision ("For work / For school"), then plain grouped fields with Back / Continue. Used for program level (Lisans / Tezli YL / Tezsiz YL / Doktora / Önlisans) | — |
| R6 | [Calendly · Availability › Weekly hours](https://mobbin.com/screens/996d3389-4459-4e04-b563-71d25dc070a0) and [Apollo · default availability](https://mobbin.com/screens/37590a83-31a5-4ad7-b640-d995d34cbe1d) | Per-day rows with time ranges, "+" to add a range, **copy to other days**, and "Unavailable" days. Used for program time windows and instructor unavailability | — |
| R7 | [Pipedrive · Define availability (1/3)](https://mobbin.com/screens/6f395235-ab5c-4ceb-96f9-b73f59a52611) | A duration segmented control ("15 min · 30 min · 45 min · 1 h …"), which becomes the block-length picker (1 · 2 · 3 · 4 ders saati) | — |
| R8 | [Customer.io · Mapping fields](https://mobbin.com/flows/246ac8d9-3fc6-42e1-a04c-aede744f7879) | Paste preview as cards per column with "This column will be skipped". Used for TSV paste in Dersler | — |
| R9 | [Wix · Mobile app setup checklist](https://mobbin.com/screens/ba505e36-28c4-4b67-a1f5-d59e715d1e37) | Struck-through completed step + highlighted current step with its action, plus "1/6" progress. Used for the mobile compact stepper | — |

Component sites: beUI **availability-scheduler** (`@beui/availability-scheduler`, "Weekly availability editor where each day springs between available and unavailable", MIT) for time windows. beUI **table-editable** (`@beui/table-editable`, inline cell edit with `@tanstack/react-virtual`, MIT) for the courses grid. beUI **adaptive-stepper** (`@beui/adaptive-stepper`, numeric stepper, MIT) for section counts and hours.

## 3. Interaction patterns chosen, and why

| Pattern | Why |
|---|---|
| **Vertical step rail with status + autosave line** (R1) | Eight steps don't fit a horizontal stepper with counts. A rail also gives every step a persistent status and a place for "kaydedildi" |
| **Non-linear steps, gated only at the write** | Real work is iterative ("I'll come back to instructors"). Blocking navigation would push people to fake data |
| **Spreadsheet-like grid with paste** (beUI table-editable, R8) for courses and sections | Coordinators think in Excel. Paste-to-grid is the fastest honest input |
| **Derived defaults** (sections from courses, cohorts from Sınıf, patterns from T/U/L, capacity from enrolment) | Every later step starts pre-filled from earlier answers, so the wizard is mostly review |
| **Weekly-hours editor** (R1, R6) for program windows and instructor unavailability | A known pattern for "when can this happen". Copy-to-days saves clicks |
| **Live consequence lines** under each step ("En büyük ortak ders 120 öğrenci → 4 oda sığar: A 207, C 201, A 203, A 204") | Validation that teaches. The coordinator sees the room problem at the moment the number is typed |
| **One transactional write + undo** | A program touches 6 tables. Partial creation would be worse than none |
| **Minimal-change hand-off to the moderation preview** | Adding a program to a live term must not reshuffle 1,300 other classes |

## 4. Steps in detail

The rail always shows: step name · status (✓ / ⚠ n / ✕ n / –) · one summary line once filled ("7 ders · 63 AKTS").

### 4.1 Program

Fields: **Program adı** (required, unique within the unit; "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans"), **Birim** (faculty/institute select from `GET /faculties`: Fen Bilimleri Enstitüsü), **Düzey** as choice cards (Önlisans · Lisans · Tezli YL · Tezsiz YL · Doktora), **Öğretim** (Normal / İkinci öğretim (İÖ)), **Dil** (Türkçe / İngilizce / karma), **Dönem** (target term, default the next unpublished term: 2026-GÜZ; 14 weeks from the term), **Ders kodu öneki** (MBG; 2–4 uppercase letters, Turkish letters normalised for codes: "MBĞ" → error "Ders kodlarında Türkçe harf kullanılmıyor"), **Sınıf sayısı** (YL: 2, Lisans: 4).

Validation: an existing program with the same name in the unit → error with a link ("Bu birimde aynı adlı program var · Var olanı aç"). A prefix used by another program → warning, because shared prefixes are real (MBG is used by the lisans and the YL programs).

Right side (R4): a **preview card** that grows as steps fill: "2026-GÜZ · Fen Bilimleri Enstitüsü · 0 ders". Later it reads "7 ders · 7 şube · 7 ortak ders bağlantısı · 5 öğretim elemanı · haftada 19 saat".

### 4.2 Dersler (courses)

A grid (beUI table-editable) with columns **Kod · Ad · T · U · L · K · AKTS · Sınıf · Zorunlu/Seçmeli · Mod (Yüz yüze / Online / Hibrit / UZEM) · Not**.

Real rows for the example:

| Kod | Ad | T | U | L | AKTS | Sınıf | Mod |
|---|---|---|---|---|---|---|---|
| MBG 598 | Seminer | 0 | 0 | 0 | 9 | 1 | Yüz yüze |
| MBG 532 | Epigenetik | 3 | 0 | 0 | 9 | 1 | Yüz yüze |
| MBG 534 | Proteomiks | 3 | 0 | 0 | 9 | 1 | Yüz yüze |
| MBG 546 | Genetik ve Genomiks | 3 | 0 | 0 | 9 | 1 | Yüz yüze |
| MBG 502 | İleri Moleküler Genetik | 3 | 0 | 0 | 9 | 1 | Yüz yüze |
| MBG 541 | Gen Mühendisliği ve Biyoteknoloji | 3 | 0 | 0 | 9 | 1 | Yüz yüze |
| MBG 549 | Kanser İmmünolojisi | 3 | 0 | 0 | 9 | 1 | Yüz yüze |

- **Paste**: `⌘V` on the grid opens a preview (R8): detected columns, rows to add (7), and rows ignored (header, empty). Nothing is inserted until "7 dersi ekle".
- **Existing catalogue**: "Var olan dersi ekle" searches `GET /courses` (for example MBG 014 Proteomiks, lisans), for when the YL program takes an existing course as is.
- **Inline validation**: codes are normalised on blur ("MBG532" → "MBG 532", info). A duplicate code within the draft is an error. **MBG 598 with T=U=L=0** is a warning, not an error, because seminars are often entered as 0+0 in the source; the user must set "Haftalık saat" in step 6 (real case: Bahar R182 lists 0 0 0 but meets Fri 14:20–15:00). Non-numeric AKTS is an error. More than 30 AKTS in one Sınıf in one term is a warning.

### 4.3 Şubeler (sections)

One row per course, pre-filled with 1 şube. Columns: **Ders · Şube sayısı** (adaptive stepper) · **Beklenen öğrenci / şube** · **Ortak ders** · **Ortak toplam**.

- **Ortak ders** (joint teaching) links this section to sections of other programs that meet together. Search lists sections of the target term ("MBG 014 Proteomiks · MBG lisans 4. sınıf · 75"). Real joint links in the example: MBG 534 ↔ MBG 014; MBG 532 ↔ MBG 012; MBG 546 ↔ MBG 027 + MBG 404; MBG 502 ↔ MBG 613 (Doktora); MBG 541 ↔ MBG 631; MBG 549 ↔ MBG 645; MBG 598 ↔ MBG 408 + MBG 416 + MBG 698.
- **Ortak toplam** = the sum of linked enrolments, which drives the room size. For MBG 598 that is 120 (from the Bahar rows).
- Validation: 0 students is an error unless Mod is Online. A joint link to a section with a **different weekly length** is a warning ("MBG 549 3 saat, MBG 645 3 saat ✓" vs a mismatch). A joint link to a section already placed in a published plan shows its current time and room, because the new course will follow it.

### 4.4 Öğretim elemanları (instructors)

Per section: **1. öğretim elemanı** (required for Yüz yüze) and **2. öğretim elemanı**, both comboboxes over `GET /instructors` with title + name, unit and **load this term** ("Bu dönem 9 saat"). "Yeni kişi" opens a small form (Unvan, Ad Soyad, e-posta, Birim). New people are created only at the final write.

- Validation: a section with no instructor is a warning ("Atanmadı; çözüm öğretim elemanı çakışmasını kontrol edemez"). A load above the institution limit (setting, default 20 saat) is a warning. The same person in two joint-linked sections at different times is an error.
- Person matching uses the same normalisation as moderation identity matching, so "ARŞ.GÖR. …" and "Arş. Gör. …" are proposed as one person (moderation §5.2).

### 4.5 Kohortlar (cohorts)

Cohorts are pre-built from Sınıf: "MBG YL 1. sınıf". Each cohort lists its **compulsory** courses (must not overlap) and **elective groups** (may overlap within a group). Columns: **Kohort · Öğrenci · Zorunlu dersler · Seçmeli grupları**.

- Validation: a compulsory course in no cohort is a warning. Two compulsory courses of one cohort that are joint-linked to sections fixed at the same published time is an error ("MBG 534 ve MBG 546 aynı kohortta ama ortak oldukları dersler aynı saatte").
- Consequence line: "Haftada 19 saat zorunlu ders; kohort için en az 3 gün gerekir."

### 4.6 Odalar ve haftalık düzen (rooms and weekly patterns)

Per course, three things:

1. **Pattern**: options derived from T/U/L hours, chosen with a segmented control (R7). T3: "3 saat tek blok" · "2 + 1" · "1 + 1 + 1". U and L blocks are separate meetings with their own room needs. For 0-hour courses (MBG 598) the user enters "Haftalık saat: 1" (Fri 14:20–15:00 in Bahar is a 1-period block).
2. **Haftalar**: "Dönemin tamamı (1–14)", or chips for a subset.
3. **Oda ihtiyacı**: capacity, defaulted from Ortak toplam (read-only with an override); tags (Derslik, Laboratuvar, PC, Amfi); building preference; optional preferred room.

Program-level **Zaman penceresi** (time window) uses the weekly-hours editor (beUI availability-scheduler; R1, R6). Default: Mon–Fri 08:30–17:30 for Normal, 17:30–22:50 for İÖ. Days can be marked unavailable, and a window can be copied to other days.

**Live consequence and validation** (using `GET /rooms` and the room pool):
- MBG 598 + joint seminars, 120 students: "Sığan odalar: A 207 (120), C 201 (126), A 203 (148), A 204 (156)". Bahar used A 207, which fits exactly, so a warning reads **"A 207 tam 120 kişilik; kayıt artarsa sığmaz"**.
- MBG 502 + MBG 613 asked for B 501 in Bahar: **"B 501: kapasite bilinmiyor ve planlanabilir oda havuzunda değil (room_master: 'named in definitive rooms only')"**. This is an error if B 501 is set as the required room, and a warning if it is only preferred.
- MBG 532 (Epigenetik) + MBG 012 together have 80 students (Bahar R188), but the room asked for in Bahar was C 504 with 40 seats. If C 504 is set as the preferred room, the step says **"C 504 (40) 80 öğrenciye yetmez · 10 oda sığar: D 106 (82), A 206 (92), A 205 (94), …"**.
- A pattern total ≠ T+U+L is an error ("MBG 541: 3 saatlik ders için yalnızca 2 saat yerleştirildi").
- A lab without a Laboratuvar-tagged room in the pool is an error.

### 4.7 Kısıtlar (constraints)

The Studio rule system, scoped to this program. Nothing new is invented here.
- **Hazır politikalar** (Studio `policy-switches.tsx`): TIP rooms forbidden for non-medicine, İÖ programs in B/C buildings, same room in all weeks, fit capacity.
- **Öğretim elemanı uygunluğu**: per instructor, the weekly-hours editor marks unavailable times. This creates `day_window` soft or hard rules (Must / Try-to via `HardnessControl`).
- **Şablondan kural** (Studio templates) and **Kendi cümlenizle** (NL rule, needs AI and shows the KVKK line from the intake spec).
- Each rule renders as a Studio `RuleCard`, with source chip "Yönetici".
- Validation: the Studio pre-check runs live (1.5 s after the last edit, generator-studio.md §3.4) for this program's events only, and its issue count appears in the rail.

### 4.8 Oluştur ve çöz (create and solve)

```
Özet                                                     Hazır · 2 uyarı
1  Program        MBG Tezli YL · Fen Bilimleri Enstitüsü · 2026-GÜZ      ✓
2  Dersler        7 ders · 63 AKTS                                       ✓
3  Şubeler        7 şube · 7 ortak ders bağlantısı                        ✓
4  Öğretim el.    5 kişi (1 yeni)                                        ✓
5  Kohortlar      1 kohort · 19 saat zorunlu                              ✓
6  Odalar         ⚠ MBG 502: B 501 planlanabilir değil · ⚠ MBG 598: A 207 tam dolu   [Düzelt]
7  Kısıtlar       4 kural · ön kontrol: 0 engel                           ✓
Nasıl devam edilsin?
(●) Oluştur ve mevcut plana ekle — 2026-GÜZ yayındaki planı en az değişiklikle yeniden çözer;
    önizlemeyi onaylamadan hiçbir şey yayınlanmaz.
( ) Yalnızca oluştur — program, dersler ve talepler yazılır; çözüm sonra.
                                                [Taslak olarak bırak]  (Oluştur ve çöz)
```

- Confirm: "2026-GÜZ dönemine 1 program, 7 ders, 7 şube, 1 kohort, 7 talep, 1 yeni öğretim elemanı ve 4 kural eklenecek. 30 gün içinde geri alınabilir."
- With a published plan: write → `POST /runs {parent_run_id, params:{stability:true}}` → run island → moderation preview `/moderation/recreate/[runId]` (moderation §5.4). Without a published plan: write → Generator Studio scoped to the term, with this program preselected.
- **Errors** (✕) disable "Oluştur…". **Warnings** (⚠) need no acknowledgement but are listed.

## 5. Desktop layout (1440)

```
┌ shell ┬─ RAIL (plain, 260) ───────┬─ STEP (content) ──────────────────────────────────┬─ PREVIEW (regular, 320) ─┐
│       │ Yeni program               │ Odalar ve haftalık düzen                          │ MBG Tezli YL · 2026-GÜZ  │
│       │ ✓ 1 Program                │ Ders            Düzen          Haftalar  Oda      │ Fen Bilimleri Enstitüsü  │
│       │ ✓ 2 Dersler      7 ders    │ MBG 598 Seminer [1 saat]       1–14      ≥120 ⚠  │ 7 ders · 7 şube          │
│       │ ✓ 3 Şubeler      7 ortak   │ MBG 532 Epigen. [3 tek blok ▾] 1–14      ≥80     │ 7 ortak ders bağlantısı  │
│       │ ✓ 4 Öğretim el.  5 kişi    │ MBG 502 İleri…  [3 tek blok ▾] 1–14      B 501 ✕ │ haftada 19 saat          │
│       │ ✓ 5 Kohortlar    1         │ ── MBG 598 ─────────────────────────────────────  │ ── Sığan odalar ──       │
│       │ ⚠ 6 Odalar…      2 uyarı   │ 120 öğrenci (MBG 598 + 408 + 416 + 698)            │ A 207 · C 201 · A 203 ·  │
│       │ – 7 Kısıtlar               │ Sığan odalar: A 207 (120), C 201 (126), A 203, A 204│ A 204                    │
│       │ – 8 Oluştur ve çöz         │ ⚠ A 207 tam 120 kişilik; kayıt artarsa sığmaz     │ Pzt–Cum 08:30–17:30      │
│       │ ────────────────────────   │ Etiket [Derslik ×] [+]   Bina [fark etmez ▾]      │                          │
│       │ ✓ Tüm değişiklikler        │ Zaman penceresi (program)                          │                          │
│       │   kaydedildi · 1 dk önce   │ Pzt ●  08:30 – 17:30  + ⧉                          │                          │
│       │ Taslak · 2026-GÜZ'e henüz  │ Sal ●  08:30 – 17:30  + ⧉   …                      │                          │
│       │ hiçbir şey yazılmadı       │                                  [‹ Geri] (Devam ›)│                          │
└───────┴────────────────────────────┴────────────────────────────────────────────────────┴──────────────────────────┘
```

- The rail is plain (not glass: it sits on content in the page body). The page header is `type-large-title` "Yeni program", with the program name once known.
- The draft line at the rail foot mirrors the intake rule: "Taslak · 2026-GÜZ'e henüz hiçbir şey yazılmadı".
- The preview column is a `Card variant="glass"` (regular, over the scene, G1). It collapses below 1280 px into a "Önizleme" disclosure above the step.
- Footer per step: "‹ Geri" (ghost) and "Devam ›" (tint). `Enter` advances when focus is not in a grid or textarea.

## 6. Mobile layout (≤ 390 px)

```
┌ 390 ──────────────────────────────┐
│ ‹ Yeni program          Taslak  ⋯ │
│ 6/8 · Odalar ve düzen  ▬▬▬▬▬▬▭▭   │  ← compact stepper (R9); tap opens the step list sheet
│ ✓ Kaydedildi · 1 dk önce          │
│ ┌───────────────────────────────┐ │
│ │ MBG 598 Seminer        ⚠      │ │
│ │ 1 saat · 1–14 · ≥ 120         │ │
│ │ Sığan: A 207, C 201, A 203, … │ │
│ │ [Düzenle]                     │ │
│ └───────────────────────────────┘ │
│ ┌───────────────────────────────┐ │
│ │ MBG 502 İleri Mol. Gen.  ✕    │ │
│ │ B 501 planlanabilir değil     │ │
│ └───────────────────────────────┘ │
│╭─────────────────────────────────╮│
││  ‹ Geri              (Devam ›)  ││  ← floating capsule, 44 px
│╰─────────────────────────────────╯│
└───────────────────────────────────┘
```

- Grids (Dersler, Şubeler) become one card per row with an "Ekle" button. A tap opens a bottom sheet form. Paste is available from the ⋯ menu ("Excel'den yapıştır"), which opens a text area and then the same preview.
- The weekly-hours editor stacks one day per row, with a switch and a time range. "Diğer günlere kopyala" opens a day-chip sheet.
- The step list opens as a bottom sheet with each step's status, so jumping around stays one tap.
- Autosave is the same. A lost connection shows "Çevrimdışı · değişiklikler bu cihazda tutuluyor" and syncs on reconnect.

## 7. Component list

| Need | Component | Source · licence | Status |
|---|---|---|---|
| Step rail + mobile stepper | new `ui/stepper.tsx` (`orientation="vertical"\|"horizontal"`, status per step), shared with intake | ours | **new** |
| Autosave line | new `common/save-status.tsx` ("Kaydediliyor… / Kaydedildi · 1 dk önce / Kaydedilemedi · Yeniden dene") | ours | **new** |
| Choice cards (Düzey) | `ui/card.tsx` + radio semantics | shadcn · MIT | reuse |
| Courses / sections grid | beUI `@beui/table-editable` (deps: `@tanstack/react-virtual`, motion, lucide), restyled to the 36 px table | beUI · MIT (`LICENSES/beui-MIT.txt`) | **import** (add `SOURCES.md` row) |
| Paste preview | `ui/dialog.tsx` + `ui/table.tsx` | MIT | reuse |
| Numeric steppers (şube, saat) | beUI `@beui/adaptive-stepper` | beUI · MIT | **import** |
| Course / instructor / section comboboxes | `ui/command.tsx` in `ui/popover.tsx` | shadcn + cmdk · MIT | reuse |
| Pattern picker | `ui/segmented-glass.tsx` | ours / beUI tabs · MIT | reuse |
| Week chips | `ui/chip.tsx` | ours | reuse |
| Weekly-hours editor | beUI `@beui/availability-scheduler` (deps include `@floating-ui/dom`, already present) | beUI · MIT | **import** |
| Rules | `studio/rule-card.tsx`, `studio/policy-switches.tsx`, `studio/hardness-control.tsx`, `studio/template-gallery.tsx` | ours | reuse (scoped to program) |
| Pre-check | Studio pre-check (`studio/check-step.tsx` model) | ours | reuse |
| Summary | `ui/card.tsx` + `ui/table.tsx`; checklist pattern (R2, R3) | MIT | reuse |
| Run status | run island + `ui/beautifului/task-rows.tsx` | ours; beautifului · MIT | reuse |
| Validation messages | `ui/input.tsx` (`useShake` on submit with errors), `ui/badge.tsx` tones | MIT | reuse |

## 8. Tokens

| Use | Token |
|---|---|
| Rail status | ✓ `--status-feasible-fg` + `check-circle-2`; ⚠ `--status-warning-fg` + `alert-triangle` + count; ✕ `--status-infeasible-fg` + `x-octagon` + count; – `--label-3` |
| Current step | `bg-tint-soft` pill, `text-label-1` (G3: accent on selection only) |
| Field error | `--status-infeasible-fg` text under the field + `aria-invalid` ring in `--status-infeasible-border` |
| Info fix ("MBG532 → MBG 532") | `--label-2` + `info` glyph, auto-dismissed after the next edit |
| Preview card | `glass-regular` over the scene, `rounded-2xl`, padding 16 |
| Grid | opaque, 36 px rows, header on `--mat-thick` when sticky |
| Footer capsule (mobile) | `glass-chrome`, 44 px |
| Spacing | rail 260 px; step content max 880 px; field gap 12; section gap 24 |
| Type | step title `type-title-2`; field labels `type-callout` w600; hints `type-footnote` label-2 |
| Motion | `motion.md` tokens only |

## 9. States

| State | What the user sees |
|---|---|
| **Empty** (`/programs`, no programs or drafts) | `EmptyState`: "Henüz program yok. Bir program oluşturun ya da listenizi içe alın.", actions "Program oluştur" (tint) and "İçe al" (outline) |
| **First step, blank draft** | Program step with focus in "Program adı". The preview card reads "Program adı girin" |
| **Loading** | Step skeleton for the first load. Comboboxes show "Aranıyor…". Autosave reads "Kaydediliyor…" |
| **Error** (autosave failed) | Save status "Kaydedilemedi · Yeniden dene" (warning tone). Fields stay editable and the draft is kept locally until the save succeeds |
| **Error** (write failed at step 8) | The dialog stays open with the server message. Nothing is written (single transaction). The draft is intact |
| **Partial** | Steps left empty show "–" in the rail. The summary lists them with "Düzelt". "Yalnızca oluştur" is allowed with warnings, never with errors |
| **Conflict** | Another user edits the same draft: the rail shows "Fatih Bey bu taslağı düzenliyor (2 dk önce)". Edits are allowed and merged per field, last write wins, and the overwritten value is shown as an info line |
| **Stale data** | A joint-linked section changed after linking: an inline warning "MBG 014'ün saati değişti (Cum 10:10 → …) · Güncelle" |
| **Permission denied** | Creating programs needs `planning.edit`. Persistent preferences and new people need `planning.edit`. A user with `planning.view` sees `/programs` read-only with no "Program oluştur". The wizard URL shows 403 |
| **Done** | After "Yalnızca oluştur": "Program oluşturuldu · 2026-GÜZ · Geri al (30 gün)" with links Programı aç · Çözüm oluştur. After "Oluştur ve çöz": the run island, then the moderation preview |

## 10. Accessibility

- The rail is a `<nav aria-label="Program sihirbazı adımları">` with an `<ol>`. The current step has `aria-current="step"`. Each item's accessible name includes its status ("Odalar ve haftalık düzen, 2 uyarı").
- Keyboard: `Alt+1–8` (or `g 1–8`) jump to a step, `Enter` advances when valid, and `⌘S` forces a save (also announced). Grids follow the APG grid pattern: arrows move, `Enter`/`F2` edit, `Esc` cancel, `⌘V` paste, `Delete` clears, `⌘Enter` adds a row.
- Validation: every field error is tied with `aria-describedby`. On "Devam" with errors, focus moves to an **error summary** at the top of the step with links to each field (GOV.UK pattern). The rail updates without moving focus.
- Live regions: autosave state (polite, only on state changes, not every keystroke), the paste result ("7 ders eklendi"), and the pre-check result ("Ön kontrol: 0 engel, 2 uyarı").
- The weekly-hours editor: each day is a switch + two time selects with labels ("Pazartesi başlangıç"). There is no drag-only interaction.
- Contrast: rail and grid are opaque. The preview card is regular glass over the scene, holding label-1/label-2 only (G1, ≥ 6.4:1).
- Touch: 44 px targets. Sheet forms keep the focused field above the keyboard.

## 11. Motion moments (hand to the motion agent; names only)

| Moment | Suggested pattern |
|---|---|
| `wizard.step-change` | §2 rail pill morph + §13 enter-only content |
| `wizard.rail-status-change` | text swap; §10 check draw when a step first becomes ✓ |
| `wizard.autosave` | none, besides the text swap ("Kaydedildi") |
| `wizard.row-added` / `paste-inserted` | §6 list insert (≤ 40 rows; none above) |
| `wizard.preview-card-update` | §11 ticker on the numbers only |
| `wizard.day-toggle` (weekly-hours) | §2/§10-style switch (beUI availability-scheduler's spring, retimed to tokens) |
| `wizard.error-summary` | §9 shake on submit with errors |
| `wizard.create-and-solve` | §1 dialog, then §19 island morph |

## 12. i18n (TR + EN)

- Namespace `programWizard.*`. Step names: Program / Program · Dersler / Courses · Şubeler / Sections · Öğretim elemanları / Instructors · Kohortlar / Cohorts · Odalar ve haftalık düzen / Rooms and weekly patterns · Kısıtlar / Constraints · Oluştur ve çöz / Create and solve.
- **Long Turkish strings**: "Odalar ve haftalık düzen" (24) in the rail at 260 px, wrapping to 2 lines and never truncating. "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans" (49) wraps in the header and the preview card. "Taslak · 2026-GÜZ'e henüz hiçbir şey yazılmadı" (45). "A 207 tam 120 kişilik; kayıt artarsa sığmaz" (44).
- Level names: Önlisans / Associate · Lisans / Bachelor's · Tezli YL / Master's (thesis) · Tezsiz YL / Master's (non-thesis) · Doktora / PhD. Öğretim: Normal / Day · İkinci öğretim (İÖ) / Evening (İÖ).
- T/U/L are kept as Turkish abbreviations in both locales, with EN tooltips (Theory / Practice / Lab), because they are what appears on the official course forms.
- Course codes are uppercase ASCII with a space ("MBG 532"). Names keep Turkish letters. Search is Turkish-aware.
- Times are 24 h; weekday abbreviations are as in moderation §13.

## 13. API endpoints (backend tickets)

Existing and reused: `GET /faculties`, `GET /programs`, `GET /courses`, `GET /sections`, `GET /instructors`, `GET /rooms`, `GET /terms`, Studio rule and pre-check endpoints (generator-studio.md §7), `POST /runs`, `POST /runs/{id}/activate`.

New:

| Ticket | Endpoint | Purpose |
|---|---|---|
| P19-W-01 | `POST /program-drafts {term_id}` → `{id}`; `GET /program-drafts?mine=&term_id=`; `GET /program-drafts/{id}`; `PATCH /program-drafts/{id} {path, value, base_version}` → `{version, validation}`; `DELETE /program-drafts/{id}` | Autosave, resume, field-level merge |
| P19-W-02 | `POST /program-drafts/{id}/validate?step=` → `{steps:[{step, status, errors:[{path, code, text}], warnings[...]}]}` (also returned by every PATCH) | Rail status, error summary |
| P19-W-03 | `POST /program-drafts/{id}/paste {step:"courses"\|"sections", tsv}` → `{columns, rows, ignored}` (preview only) | TSV paste preview |
| P19-W-04 | `GET /rooms/fit?capacity=&tags=&building=&term_id=` → `[{room, capacity, tags, bookable}]` | Live "sığan odalar" lines |
| P19-W-05 | `GET /terms/{term_id}/sections/search?q=` (with current placement in the published run) | Ortak ders linking |
| P19-W-06 | `POST /program-drafts/{id}/precheck` → Studio pre-check result for the draft's events in the term context | Step 7 live check |
| P19-W-07 | `POST /program-drafts/{id}/commit {solve:"minimal"\|"none"}` → `{program_id, created:{courses, sections, cohorts, requests, people, rules}, audit_id, run_id?}`, as one transaction | Step 8 write (+ optional child run with `stability`) |
| P19-W-08 | `POST /audit/{audit_id}/undo` covers `program.create` within 30 days (archives everything created) | Undo |

Permissions: drafts and commit need `planning.edit`. Unit-scoped coordinators (if roles are scoped later) only see their unit's drafts.

## 14. Open questions for the product owner

1. Should programs created here be editable later through the same wizard ("Programı düzenle", same steps on live data with a diff before saving), or through Moderasyon and the Studio only?
2. Joint teaching: when the linked section belongs to another unit's program (MBG 534 ↔ lisans MBG 014), does the other program's coordinator need to approve the link?
3. Instructor load limit: is there an institutional maximum (saat/hafta) to warn at, and does it differ by title (Arş. Gör. vs Prof. Dr.)?
4. Rooms like B 501 (named in definitive rooms but outside the bookable pool, no capacity): should the wizard allow adding a room to the pool on the spot (admin only), or send the user to Admin › Odalar?
5. Should a draft expire (for example after 90 days without edits) to keep the list clean?
