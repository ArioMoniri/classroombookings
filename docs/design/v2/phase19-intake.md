# Phase 19 · Intake: drop any file, review every row, then commit

Owner: design-pro (Phase 19 surfaces) · Status: spec v1.0 (2026-10-15) · Route: **`/onboarding`** (drop) and **`/onboarding/[jobId]`** (job workspace)
Extends the universal onboarding flow on `claude/smartsched-universal` (`components/onboarding/{onboarding-flow,file-drop,council-progress,review-panel,commit-panel}.tsx`, `lib/api/council.ts`). It does not replace it. Every existing call (`POST /council/jobs`, `GET/POST /council/jobs/{id}/review`, `POST /council/jobs/{id}/commit`, `POST …/rerun`, `GET …/records`, `GET …/artifacts`, `GET …/events`) stays as is, and this spec adds to them.
Material, colour and type: [`liquid-glass.md`](liquid-glass.md). Motion: [`motion.md`](motion.md) (owned by the motion agent; this file only names moments). Shared table core: [`all-classes.md`](all-classes.md) §5–§8. Older wizard: [`../import-wizard.md`](../import-wizard.md) (superseded for new work; see open question 1).

---

## 0. BLUF

- **One drop zone takes every format.** Excel (.xlsx/.xls), CSV/TSV (UTF-8 or Windows-1254, delimiter sniffed), ODS, JSON, XML and ICS are read **directly** (no AI). PDF, DOCX, TXT/EML and images go through the **AI** route (Claude API, Settings key) only when an admin allows it. Each file gets its own row with the detected format, the detected kind, the route, live progress and counts.
- **Nothing is saved until the coordinator commits.** A job is a draft that lives on the server. The header always shows the pill **"Taslak · veritabanına henüz hiçbir şey yazılmadı"**. A sticky commit bar counts what is still waiting. "Kaydet" is the only action that writes to the term, and it stays disabled while any blocking item is open.
- **Every row carries its provenance**: file, sheet or page, cell (or table and line for PDFs), and a **Doğrudan / YZ** badge with a confidence figure. Selecting a row opens a source preview with the original cell or page region highlighted.
- **AI rows are never pre-accepted.** Direct rows above the council threshold are "Hazır" (ready). Every AI row starts as "Bekliyor" (waiting) and blocks commit until a person accepts, edits or rejects it.
- The job workspace has five steps in one header stepper: **Dosyalar → Eşleme → İnceleme → Fark → Kaydet**. Steps can be visited in any order. Only Kaydet is gated.
- **KVKK**: when any file will take the AI route, a notice says what is sent, to whom, and for how long it is kept. The start button then reads "YZ ile oku ve başlat". If an admin has turned AI off, those files are listed as "YZ kapalı, okunmadı" and nothing is sent.

## 1. User stories

| # | As a… | I want to… | So that… | Acceptance |
|---|---|---|---|---|
| I1 | scheduler (Fatih Bey) | drop `bahar_derslik_planlama_listesi_v5.xlsx`, `room_master.csv` and a faculty's PDF in one go | I don't have to sort files by type first | 3 rows appear immediately. Each shows a format chip (`XLSX`, `CSV`, `PDF`), a predicted route and live progress |
| I2 | scheduler | see what each file was recognised as | I can catch a wrong guess early | the file row reads e.g. "Ders planlama listesi · 1.524 talep · 1.271 şube · 5 satır atlandı" or "Oda listesi · 87 oda" |
| I3 | scheduler | check where a value came from | I trust the import as much as my Excel | the row's Kaynak cell reads `v5.xlsx · Sayfa1 · R545`. Selecting it shows the original cell (A 206) highlighted among its neighbours (R544 A 205, R546 D 106) |
| I4 | scheduler | tell AI-read rows from directly-read rows at a glance | I review the risky ones first | a **YZ** badge (sparkle + word + %) or a **Doğrudan** badge (sheet icon + word). The filter "Yalnızca YZ" sits one click away |
| I5 | scheduler | accept or reject 40 rows at once | review takes minutes, not hours | a selection bar offers "Onayla", "Reddet" and "Alanı ayarla…". The result toast offers Undo |
| I6 | scheduler | fix a wrong column mapping once | every row of that column is corrected | in the Eşleme step, changing "Assigned Room → oda" to "oda talebi" re-maps 1.348 rows. The İnceleme count updates |
| I7 | scheduler | say that a file belongs to 2026-BAHAR and only to Eczacılık | the rows land in the right term and program | the file → term/program table has a term select and a program scope per file |
| I8 | scheduler | see what will change in the current data before writing | I don't overwrite a planner's correction by accident | the Fark step lists **Yeni 412 · Değişecek 1.106 · Aynı 6 · Dosyada yok 31** with a field diff per changed row |
| I9 | coordinator | be sure nothing is written until I press Kaydet | I can leave and come back without side effects | draft pill, sticky bar, and a leave dialog that says "İş taslak olarak saklandı; ders, oda veya talep oluşturulmadı" |
| I10 | KVKK-aware admin | know when instructor names leave our server | we meet KVKK obligations | an AI notice before start, a "YZ kullanıldı" chip on the job, and an admin switch that turns the AI route off |
| I11 | viewer (planning.view) | open a colleague's job read-only | I can check it without changing it | review controls are disabled, and a note explains which permission is needed |

## 2. References

Mobbin (all web unless marked):

| # | App · flow / screen | Pattern we take | What we avoid |
|---|---|---|---|
| R1 | [Attio · Importing a CSV (13 screens)](https://mobbin.com/flows/2c5ec636-6d46-416e-b798-ae09d51881c3) | Compact header stepper `1 Upload file › 2 Map columns › 3 Review values › 4 Preview import`. Mapping as file column → attribute with a **Data preview** column on the right. Preview shows "3 will be created · 0 will be updated" per entity tab. "Start import" confirm | the generic illustration on "Generating import preview" |
| R2 | [Attio · Review values, "Needs review 3"](https://mobbin.com/screens/60a1cfe5-3788-49e3-b3ae-3da62a33f7ee) | Column list on the left with an orange dot on columns that need attention. Raw value → mapped value pairs, with an inline fix popover ("Invalid domain") | — |
| R3 | [Customer.io · Mapping fields (4 screens)](https://mobbin.com/flows/246ac8d9-3fc6-42e1-a04c-aede744f7879) | One **card per file column**, with 2 sample values, "Map to attribute" select, `Required` / `Reserved` tags and "This column will be skipped". Review shows numeric tiles (NEW / EXISTING / WARNINGS / ERRORS). Used as the **mobile** mapping layout | red error tile colour as the only cue |
| R4 | [Remote · Review time-off data](https://mobbin.com/screens/ab52924c-333f-42fb-bc19-659aa03720e0) | "Show only rows with errors" switch, a per-row ✓ / ⚠ status, an error popover on the cell with a select to fix it, and "Save as draft · Continue with 1 record" | — |
| R5 | [Copy.ai · Review & finalize](https://mobbin.com/screens/c4a1c609-c8af-475f-9cd2-3eb313530ea8) | Tabs **All rows 2 · Clean rows 1 · Rows with issues 1**, which become our row-state tabs | "Fix using AI" as a one-click bulk fix (we never auto-fix with AI) |
| R6 | [Twenty · Validate data](https://mobbin.com/screens/8429b076-1864-4c32-b237-7933be9769ae) | A floating "Show only rows with errors · Remove" capsule at the bottom of the table, which becomes our selection bar position | — |
| R7 | [AWS · Upload status](https://mobbin.com/screens/d0b2a1fa-99a9-4c29-ba83-f77a3f850d40) and [PandaDoc · Imported 0 of 4 files](https://mobbin.com/screens/6e7783c1-2ce2-4ba2-832d-bab89ec45f67) | A **files table** (Name · Type · Size · Status · Error) with a per-row status word and %, plus a summary line "Succeeded 2 files · Failed 0". This replaces the current per-file card grid | the full-width blue banner |
| R8 | [Mistral AI · Document Intelligence review](https://mobbin.com/screens/9d1334ff-fc93-4b2a-99b3-f16e2deedd10) and [Revolut Business · receipt match](https://mobbin.com/screens/1180d5ee-a7bc-45f2-bb0f-03a09b51859a) | **Source beside extraction**: the PDF page on one side and the extracted text on the other, with page paging. This becomes the source preview pane | — |
| R9 | [Supabase · Assistant opt-in level](https://mobbin.com/screens/d150d11b-ea33-414c-9d3c-a00b0d92f186) | Data-sharing levels written in plain words ("schema only" vs "schema and data"), with an org-wide note. Used for the KVKK notice and the admin switch | — |
| R10 | [Fresha · Preview client list, "To be imported (1) · Errors (2)"](https://mobbin.com/screens/2d5e41af-fe36-493e-a2e3-0e1b0306d8a0) | "Errors in a row will result in that row not being imported", which we state as one sentence above the table | — |

Others: Apple HIG [Drag and drop](https://developer.apple.com/design/human-interface-guidelines/drag-and-drop) (a destination shows whether it accepts the dragged content, and dropped content stays editable), and the existing SmartSched studio `SourceChip` (provenance chip, dashed while still a proposal).

## 3. Interaction patterns chosen, and why

| Pattern | Where | Why |
|---|---|---|
| **Draft-until-commit** (persistent draft pill, sticky commit bar, the only write is Kaydet) | whole job | The user asked to make "nothing is saved until reviewed" obvious. One pill in the header plus one bar at the bottom cover both ends of a long page, and the bar's numbers say what is still in the way |
| **Non-linear header stepper** with counts (R1) | job header | The council has already produced everything, so the coordinator jumps to whatever needs work. Counts on each step ("İnceleme 41") say where |
| **Files table with per-file pipeline** (R7) | Dosyalar | A table scales to 20 files. The four council agents (intake → structure → extract → rules) become one compact phase line per file instead of a card each |
| **Provenance cell + source preview** (R8) | İnceleme | Provenance is the planner's main trust signal (all-classes.md §0). Seeing the original cell or page region answers "is this right?" without opening Excel |
| **Method badge Doğrudan / YZ** (studio `SourceChip`: `FILE`, `AI`) | every row | Reuses an existing glyph-and-word chip, so the same meaning reads the same everywhere (rule G4) |
| **Row-state tabs** Tümü / Bekleyen / Hazır / Reddedilen (R5) plus a "Yalnızca YZ" chip | İnceleme | Faster than a filter builder for the 4 questions people actually ask |
| **Selection bar replaces toolbar** (all-classes.md, Notion) | İnceleme, Fark | Same bulk grammar as /classes |
| **Column → field mapping with samples** (R1, R3) | Eşleme | A wrong mapping is one decision that affects 1.348 rows, so it deserves its own step |
| **File → term/program table** | Eşleme | The council planner already groups files into terms (`plan.groups`). Making the grouping editable is cheaper than asking per row |
| **Field-level diff** (beautifului Diff Table, already ported) | Fark | Shows `old → new` per field for the 1.106 changed rows |
| **Explicit AI consent per job** (R9) | drop + header chip | KVKK requires an informed decision. The notice has to sit next to the action |

## 4. Flow and information architecture

```
/onboarding                          drop zone + "Son işler" (recent jobs, GET /council/jobs)
  └─ Başlat → POST /council/jobs → /onboarding/[jobId]
/onboarding/[jobId]?step=files|map|review|diff|commit
  header:  title (first file name + "+2"), job status, DRAFT PILL, AI chip (if used), stepper
  body:    the step
  footer:  sticky commit bar (all steps)
```

Job status → what the user can do:

| Council status | Header pill | Steps enabled | Commit bar |
|---|---|---|---|
| QUEUED / RUNNING | "Okunuyor · %38" (progress from SSE) | Dosyalar; other steps show what is ready per file | "Dosyalar okunuyor…" (Kaydet disabled) |
| REVIEW | "Taslak · veritabanına henüz hiçbir şey yazılmadı" | all | "41 madde inceleme bekliyor · Kaydet" (disabled) |
| READY | same draft pill | all | "Hazır · 1.588 talep, 87 oda · 2026-BAHAR dönemine kaydet" (enabled) |
| COMMITTED | "Kaydedildi · 2026-BAHAR · 15 Eki 14:52" (feasible tone) | all read-only + "Yeni iş" | "Kaydedildi. Talepleri gör →" |
| FAILED | "Okunamadı" (infeasible tone) + error | Dosyalar | "Yeniden dene" |

## 5. Desktop layout (1440)

### 5.1 Drop (`/onboarding`, no job)

```
┌ shell ┬──────────────────────────────────────────────────────────────────────────────────────────┐
│       │ İçe al                                                                                     │
│       │ Dosyaları bırakın; okuyup size gösteririz. Siz onaylamadan hiçbir şey kaydedilmez.          │
│       │ ╭ regular glass card ───────────────────────────────────────────────────────────────────╮ │
│       │ │   ⤓  Dosyaları buraya bırakın veya seçin                                                │ │
│       │ │   Excel, CSV/TSV, ODS, JSON, XML, ICS · PDF, Word, metin, e-posta, görsel · en fazla 50 MB│ │
│       │ ├────────────────────────────────────────────────────────────────────────────────────────┤ │
│       │ │ bahar_derslik_planlama_listesi_v5.xlsx  2,3 MB   XLSX  Doğrudan okunur          ✕       │ │
│       │ │ room_master.csv                          4 KB     CSV   Doğrudan okunur          ✕       │ │
│       │ │ eczacilik_bahar_ders_programi.pdf        1,1 MB   PDF   YZ ile okunur            ✕       │ │
│       │ ├────────────────────────────────────────────────────────────────────────────────────────┤ │
│       │ │ ⓘ 1 dosya yapay zekâ ile okunacak. KVKK bilgilendirmesi ›                              │ │
│       │ │   [✓] Yapay zekâ kullan   (yönetici açtı · Ayarlar › YZ)                                │ │
│       │ │                                              Dönem ipucu [2026 ▾]   (YZ ile oku ve başlat)│ │
│       │ ╰────────────────────────────────────────────────────────────────────────────────────────╯ │
│       │ Son işler                                                                                  │
│       │ 15 Eki 14:31  bahar_requests_en.csv +1   İnceleme · 5 bekliyor   Fatih Bey        Aç ›     │
│       │ 8 Eki 10:17   room_master.csv +1         Kaydedildi · 2026-BAHAR  Fatih Bey        Aç ›     │
└───────┴────────────────────────────────────────────────────────────────────────────────────────────┘
```

- The predicted route per file comes from the extension and magic bytes on the client. The server's intake agent confirms it, and the row updates if it differs ("PDF · metin katmanı var → Doğrudan").
- "Zorla genel okuma" (`forceGeneral`) moves into a ⋯ menu as "Bilinen biçim tanımayı atla". It is an expert option.
- The primary label changes with the content: "Başlat · 3 dosya" when no AI file is present, and "YZ ile oku ve başlat" when one is.

### 5.2 Job workspace (`/onboarding/[jobId]`)

```
┌ shell ┬──────────────────────────────────────────────────────────────────────────────┬─ SOURCE (thick, 420) ─┐
│       │ bahar_derslik_planlama_listesi_v5.xlsx +2         ◌ Taslak · veritabanına      │ v5.xlsx · Sayfa1      │
│       │                                                     henüz hiçbir şey yazılmadı │ satır 545 · sütun R    │
│       │ ✦ YZ kullanıldı (1 dosya · 14.210 token) ›                                     │ ┌──┬────────┬───────┐ │
│       │ ① Dosyalar 3 ✓ › ② Eşleme 5 › ③ İnceleme 41 › ④ Fark › ⑤ Kaydet                │ │   │E       │R      │ │
│       │ ───────────────────────────────────────────────────────────────────────────── │ │544│PHAR 108│A 205  │ │
│       │ [Tümü 1.588] [Bekleyen 41] [Hazır 1.541] [Reddedilen 6]   ✦ Yalnızca YZ  ⌕ …  │ │545│PHAR 240│▌A 206▐│ │
│       │ ┌──┬─────────┬───────────┬────────────┬──────────┬──────┬──────┬────────────┐ │ │546│PHAR 342│D 106  │ │
│       │ │☐ │Durum    │Yöntem     │Ders        │Gün·Saat  │Hafta │Oda   │Kaynak      │ │ └──┴────────┴───────┘ │
│       │ ├──┼─────────┼───────────┼────────────┼──────────┼──────┼──────┼────────────┤ │ Okunan → Alan          │
│       │ │☐ │◌ Bekliyor│✦ YZ 71 %  │PHAR 240 §1 │Per P2–P5 │1–14  │Lab.  │ecz…pdf s.3 │ │ "A 206" → kesin oda    │
│       │ │☐ │✓ Hazır  │▦ Doğrudan │PHAR 240 §1 │Pzt P1–P3 │1–14  │A 206 │v5 · R545   │ │ ── Satır ─────────    │
│       │ │☐ │⚠ Bekliyor│▦ Doğr. 62 %│ING 302 §10 │Çar P2–P3 │1–14  │4 oda │v5 · R366   │ │ Ders kodu  PHAR 240   │
│       │ │   …virtualised, 36 px rows                                                │ │ Öğrenci    80          │
│       │ └───────────────────────────────────────────────────────────────────────────┘ │ [Onayla] [Düzenle]     │
│       │                                                                               │ [Reddet]               │
│       ├───────────────────────────────────────────────────────────────────────────────┴────────────────────────┤
│       │ ◌ 0 / 1.588 kaydedildi · 41 bekliyor (38 YZ) · 5 eşleme kararı   Hedef: 2026-BAHAR ▾    (Kaydet) ⓘ    │
└───────┴────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Header** (not glass): title in `type-title-2`, the draft pill (`Badge tone="warning"` with an `unlock` glyph, sentence case), the AI chip (only if any step used `model != null`), and the stepper as a breadcrumb-like `ol`. Each step shows a count of open items, or ✓ when nothing is open.
- **Commit bar**: `Toolbar placement="floating-bottom"` on `glass-chrome`, full content width. It is always visible. Left: the draft glyph plus the counts. Middle: the target term select. Right: **Kaydet** (the only tint button on the page, rule A6). The ⓘ explains why it is disabled ("5 eşleme kararı ve 41 satır bekliyor").
- **Source pane**: a 420 px non-modal `GlassPanel material="thick"`, docked at ≥ 1600 and overlay at 1280–1599 (same rule as the all-classes inspector).

### 5.3 Step details

**① Dosyalar**: a files table (R7) instead of the current card grid.

| Column | Content |
|---|---|
| Dosya | name (truncated in the middle: `eczacilik_bahar…programi.pdf`), size |
| Biçim | `XLSX` `CSV · Windows-1254 · ;` `PDF · 6 sayfa · taranmış` (encoding and delimiter shown for CSV/TSV) |
| Tür | detected kind: Ders planlama listesi · Haftalık derslik takvimi · Sınav listesi · Oda listesi · Talep listesi · Tercih metni · Bilinmiyor |
| Yol | **Doğrudan** (fast path name on hover, e.g. `fast:room-master`) or **YZ** (model on hover) |
| İlerleme | a phase line `okuma ✓ · yapı ✓ · çıkarım %62 · kurallar –` plus a 4 px bar driven by real SSE events |
| Sonuç | counts from `file.counts`: "1.348 toplantı · 193 kural metni" or "87 oda" |
| ⋯ | Yeniden oku (rerun this file), Bu dosyayı dışarıda bırak, Ham çıktıyı indir |

Below the table, a **"Dosyalar arası"** line shows the cross-file agents (reconcile, planner, critic) as the same phase line. Token use and cost (`step.input_tokens`, `cost_usd`) move into the AI chip popover, so the table stays readable.

**② Eşleme** has two sections on one page.

1. *Sütunlar → alanlar* (column → field). For each grid (file × sheet) there is a sub-table (R1 layout): **Dosya sütunu** (header text, `↵` for newlines) · **Örnek** (3 samples, mono, from `item.samples`) · **Alan** (`Select` of `item.options`, grouped Talep / Ders / Hoca / Oda / Kullanılmaz) · **Güven** (82 %, with a ⚠ when below the threshold) · **Alternatif** (`instructor 0,80` as a one-click chip) · state (Bekliyor / Onaylandı / Değiştirildi). Example: `bahar_requests_en.csv` · "Assigned Room" → oda (82 %, samples `A 204`, `online`, `ANATOMİ LABORATUVARI`). Selecting a mapping row previews the first 5 rows of that column as they will be interpreted, on the right (R1 "Data preview").
2. *Dosyalar → dönem / program* (file → term/program). One row per file: detected term (`2026-BAHAR`, with evidence such as "sayfa adı '9 - 15 Şubat'", confidence 0,93) · term select (existing terms + "Yeni dönem…") · program scope ("Tüm programlar" or a multi-select, for example Eczacılık + Eczacılık (İÖ)) · week count (14). Global files (`plan.global_files`, e.g. `room_master.csv`) show "Tüm dönemler için" and cannot be scoped. Unassigned files (`plan.unassigned_files`) are pinned to the top in warning tone and block commit.

The existing `classification`, `mapping` and `plan` review kinds render here. `merge`, `issue`, `rule`, `rule_text` and record-level items render in ③.

**③ İnceleme** is the row table (see §5.2).

- Columns (column chooser as in all-classes.md §5): ☐ · Durum · Yöntem · Ders · Program · Gün · Saat · Hafta · Öğrenci · Oda talebi · Hoca · Mod · Kaynak · Sorun. Default sort: Bekliyor first, then YZ before Doğrudan, then confidence ascending.
- **Durum** values: `◌ Bekliyor` (waiting), `✓ Hazır` (direct and above the threshold, no issue), `✓ Onaylandı` (a person accepted it), `✎ Düzenlendi`, `✕ Reddedildi`. Glyph plus word every time (G4).
- **Yöntem** is `SourceChip source="FILE"` labelled "Doğrudan", or `source="AI"` labelled "YZ", plus a percentage. AI rows are dashed until accepted (the `proposal` prop).
- **Kaynak** is a compact provenance string with a full tooltip. Spreadsheet: `v5.xlsx · Sayfa1 · R545` (PHAR 240 §1; column R is "Derslik Planlama - Kesinleşen Derslik", value A 206). CSV: `bahar_requests_en.csv · satır 545 · "Assigned Room"`. PDF: `ecz…programi.pdf · s. 3 · tablo 1 · satır 7`. DOCX: `… · tablo 2 · satır 4` or `· paragraf 12`. EML: `… · gövde · satır 18–22`. Image: `… · bölge 3`. JSON: `/requests/544/room`. XML: `/plan/ders[545]/oda`. ICS: `UID 2026-…@… · DTSTART 2026-02-16T08:30`.
- Other review kinds appear as **grouped rows above the table**, collapsible: "Birleştirme önerileri 3" (merge: "BES 128 ve HEM 106 aynı dersin iki satırı olabilir"), "Sorunlar 7" (issue), "Kural metinleri 193" (rule_text, which become Studio rule proposals, linked to generator-studio.md §3.3.3).
- **Inline fix**: double-click or `Enter` on an editable cell opens the field editor (same editors as all-classes.md §8.3: period range, room combobox, weeks chips). Saving an edit sets Durum to Düzenlendi. The edit is stored as a decision `{action:"edit", value}` and not as data.
- Rows with an unresolved issue cannot be accepted. The accept action shows the reason ("Saat 09:00 ızgarada yok; P1 08:30 veya P2 09:20 seçin").

**④ Fark** compares against the target term (computed on demand, §14).

- Summary line, not tiles (rule A2): **Yeni 412 · Değişecek 1.106 · Aynı 6 · Dosyada yok 31**, each a filter.
- Entity segmented control: Talepler · Şubeler · Dersler · Hocalar · Odalar · Kurallar.
- Changed rows render with the ported `beautifului/diff-table`: `requested_room_text: "A 105" → "A 105 (Bilg. Lab)"`, `enrolment: 80 → 130`. One checkbox per row lets the coordinator exclude it from the commit (QuickBooks pattern in import-wizard.md).
- **Dosyada yok** (in the database but not in the file) is never deleted by default. The coordinator can only opt in to "Arşivle", with a confirm.
- **Protected edits**: when a changed field was last edited by a person in SmartSched (audit source `manual`), the row shows "Elle düzeltilmiş · 3 Eki, Fatih Bey" and defaults to **keep the current value**.

**⑤ Kaydet** keeps today's `CommitPanel` content (term group, term code/name/weeks, "Kuralları da ekle") and adds the final count sentence and a confirm dialog:

> "2026-BAHAR dönemine 412 yeni talep, 1.106 değişiklik ve 87 oda yazılacak. 6 satır reddedildi, 31 satır arşivlenmeyecek. Bu işlem tek bir kayıt olarak geçmişe yazılır ve 30 gün içinde geri alınabilir."

The undo promise depends on backend ticket P19-I-09. If that ticket does not ship, the sentence becomes "Geri alınamaz; önceki değerler geçmişte görünür" (open question 3).

## 6. Mobile layout (≤ 390 px)

```
┌ 390 ───────────────────────────────┐
│ ‹ İçe al            ◌ Taslak  ⋯    │  ← chrome top bar; the draft pill stays visible
│ 3/5 · İnceleme · 41 bekliyor  ▬▬▬▭▭│  ← compact stepper (import-wizard.md §5)
│ [Bekleyen 41][Hazır][Red] ✦YZ ⌕    │  ← chips scroll horizontally
│ ┌────────────────────────────────┐ │
│ │ ◌ PHAR 240 §1      ✦ YZ 71 %   │ │
│ │ Pzt P1–P3 · 1–14 · A 206 · 80  │ │
│ │ ecz…programi.pdf · s.3 · t1 s7 │ │
│ │ [Onayla]  [Düzenle]  [Reddet]  │ │  ← 44 px targets
│ └────────────────────────────────┘ │
│ ┌────────────────────────────────┐ │
│ │ ✓ MAT 112 §1       ▦ Doğrudan  │ │
│ │ …                              │ │
│ └────────────────────────────────┘ │
│╭──────────────────────────────────╮│
││ ◌ 41 bekliyor          (Kaydet)  ││  ← floating commit capsule above the tab bar
│╰──────────────────────────────────╯│
└────────────────────────────────────┘
```

- **Drop**: the system file picker (`<input type=file multiple>`, `accept` list). The camera is offered for images ("Fotoğraf çek"), which is the AI route.
- **Dosyalar**: one card per file (name, format chip, route, progress bar, counts).
- **Eşleme**: one card per column (R3): header, 2 samples, a full-width `Select`, confidence and state. File → term is a list of rows, each opening a bottom sheet.
- **İnceleme**: cards as drawn. Tapping a card opens a bottom sheet with detents 45 % / 92 % (motion.md §3.2 pattern). The 45 % detent shows the source preview, and the 92 % detent the full row editor. Long-press enters select mode. The bulk bar replaces the tab bar.
- **Fark**: grouped list (Yeni / Değişecek / Dosyada yok). Each changed row expands to its field diff.
- **Commit**: the capsule is always present. Kaydet opens the confirm as a bottom sheet.

## 7. Component list

| Need | Component | Source · licence | Status |
|---|---|---|---|
| Drop zone + file list | `onboarding/file-drop.tsx` (extend), visual from `import/magnetic-drop.tsx` around `ui/beui/file-upload.tsx` | ours; beUI `@beui/file-upload` · MIT (`LICENSES/beui-MIT.txt`) | extend: per-file predicted route chip, KVKK line, accept list |
| Job pipeline | `onboarding/council-progress.tsx` → `IntakeFilesTable` | ours | rework: table rows plus phase line. Status words come from the existing `ICON` map |
| Phase line per file | `ui/beautifului/task-rows.tsx` (compact mode) | beautifului.dev Task Rows · MIT | reuse |
| Stepper | new `ui/stepper.tsx` (`ol`, `aria-current="step"`, counts) | ours (MIT-compatible, AGPL repo) | **new**, shared with the program wizard |
| Draft pill | `ui/badge.tsx` `tone="warning"` + lucide `lock-open` | shadcn · MIT | reuse |
| Commit bar | `ui/toolbar.tsx` `placement="floating-bottom"` | ours | reuse |
| Row table | `classes/class-table.tsx` core (TanStack Table + `@tanstack/react-virtual`) | MIT | reuse core, new column set `intakeColumns` |
| Method badge | `studio/source-chip.tsx` (`FILE`, `AI`, `proposal`) | ours | reuse, add the `%` suffix prop |
| Provenance cell | new `onboarding/provenance-cell.tsx` | ours | **new** |
| Source preview | new `onboarding/source-preview.tsx`: mini-grid for sheets, page image + highlight box for PDF/images, text excerpt for DOCX/EML | ours. Pattern from Mistral Document AI / Revolut (reference only) | **new** |
| Mapping table | `onboarding/review-panel.tsx` `ItemRow` → `MappingTable` | ours | split out of the review panel. `NativeSelect` → `ui/select.tsx` |
| Row-state tabs | `ui/segmented-glass.tsx` | ours on beUI tabs · MIT | reuse |
| Bulk bar | `ui/beui/expandable-action-bar.tsx` inside `Toolbar` | beUI · MIT | reuse |
| Field diff | `ui/beautifului/diff-table.tsx` | beautifului · MIT | reuse |
| Confirm | `ui/dialog.tsx` (bottom sheet on mobile via `ui/sheet.tsx`) | shadcn · MIT | reuse |
| Toasts + undo | `ui/sonner.tsx` | sonner · MIT | reuse |
| Mobile detail sheet | `ui/sheet.tsx` `side="bottom"` (or beUI `@beui/bottom-sheet` · MIT, if detents are needed) | MIT | reuse / optional import |
| Empty state | `ui/empty-state.tsx` `animation="file-to-rules"` | ours (Lottie, AGPL) | reuse |

Nothing paid is used. kobra "Magnetic Dropzone" is still reference-only (SOURCES.md, decision 2026-10-08).

## 8. Tokens

| Use | Token |
|---|---|
| Draft pill | `--status-warning-*` (fg / bg / border) + `lock-open` glyph |
| Committed pill | `--status-feasible-*` + `check-circle-2` |
| YZ badge | `bg-tint-soft`, `text-tint-text`, dashed border while pending (`SourceChip` today) |
| Doğrudan badge | `bg-background`, `text-foreground`, 1 px `--hairline` |
| Source highlight (cell/bbox) | 2 px `--focus` outline + `--accent-soft` fill. Never colour alone: the cell address is also printed above |
| Commit bar | `glass-chrome`, 44 px high (`lg` controls on coarse pointers), `rounded-full` |
| Source pane | `glass-thick`, `rounded-2xl`, 16 px padding |
| Table | opaque content surface, 36 px rows (`table.tsx`), header sticky on `--mat-thick` |
| Spacing | 4 px base, 8 px rhythm. Card padding 16. Gap between header blocks 12 |
| Type | title `type-title-2`, step labels `type-callout`, counts `tabular-nums`, provenance `type-footnote` mono for cell addresses |
| Motion durations | from `motion.md` only (`--dur-fast` 120, `--dur-base` 180, springs). Nothing over 300 ms |

## 9. States

| State | What the user sees |
|---|---|
| **Empty** (no job) | Drop card + "Son işler". With no previous jobs: `EmptyState animation="file-to-rules"`, title "Henüz içe aktarma yok", description "Ders planlama listenizi, oda listesini veya bir fakültenin PDF programını bırakın.", left-aligned |
| **Empty** (job with 0 records) | İnceleme: "Bu dosyalardan satır çıkmadı." Each file shows why ("Tür: Bilinmiyor · tablo bulunamadı") with "Yeniden oku" and "Genel okumayı zorla" |
| **Loading** | Dosyalar: per-file phase line driven by real SSE. Other steps render what is ready per file and show 8 static placeholder rows for the rest (no shimmer on working surfaces, motion.md §3.3). The draft pill reads "Okunuyor · %38" |
| **Error** (file) | The file row turns infeasible tone with the message (e.g. "Şifreli PDF açılamadı") and actions "Yeniden oku" / "Dışarıda bırak". The job continues |
| **Error** (job) | `FAILED`: banner with `job.error`, "Yeniden dene" (`POST …/rerun`), "Ham günlüğü indir" |
| **Error** (commit) | Dialog stays open with the server message. The draft is untouched, and nothing is half-written: the commit is one transaction (backend P19-I-08) |
| **Partial** | Some files done, some failed or skipped: the commit bar counts only usable rows ("2 / 3 dosya hazır · 1 dosya okunamadı, kaydedilmeyecek"). AI turned off by an admin: those files show "YZ kapalı · okunmadı" and are excluded |
| **Partial** (unassigned) | Files without a term block commit, and the bar links straight to Eşleme › Dosyalar → dönem |
| **Permission denied** | `planning.view` only: every decision control is disabled, and a top note reads "Bu işi görüntüleyebilirsiniz. Onaylamak ve kaydetmek için **planlama düzenleme** izni gerekir." No permission at all: the route returns 403 to the standard forbidden page. AI switch off for the org: the "Yapay zekâ kullan" switch is disabled with "Yönetici kapattı" |
| **Stale** | Someone else decided rows meanwhile (`review.saved` changed): a toast "Fatih Bey 12 satırı onayladı · Yenile" |

## 10. Accessibility

- **Keyboard path**: `Tab` reaches the drop zone (a real `button`, `Enter`/`Space` opens the picker), then the file list, then "Başlat". In the job: `g 1–5` or `Alt+1–5` switch steps. In İnceleme `j/k` move rows, `x` selects, `a` accepts, `r` rejects, `e` edits, `Enter` opens the source pane, `Esc` closes it, `⌘↵` focuses Kaydet. `?` lists everything. No action is gesture-only.
- **Focus**: after accepting a row, focus moves to the next **Bekliyor** row, not the next row. After a bulk action it stays on the selection bar's result toast action (Undo) for 8 s, then returns to the table.
- **Live regions** (polite): per-file phase changes ("eczacilik….pdf: çıkarım tamamlandı, 64 satır"), the job finishing ("Okuma bitti. 41 satır inceleme bekliyor."), and decisions ("12 satır onaylandı"). Assertive is used only for a commit failure.
- **Table**: `role="grid"` with roving tabindex, `aria-sort` on sortable headers, `<caption>` with the counts. The Yöntem chip's accessible name is "Yapay zekâ ile okundu, güven yüzde 71, onay bekliyor".
- **Source pane**: the highlighted cell is described in text ("Sayfa1, R545, değer A 206") so a screen reader user gets the same information as a sighted one.
- **Contrast on glass**: the commit bar is `chrome` over content, so labels are label-1/label-2 (≥ 6.4:1, liquid-glass.md §5.1). The warning pill uses `--status-warning` fg on its tint (5.02 light / ≥ 7 dark). Text never sits on `ultra-thin`/`thin` here, because everything floats over content (G1).
- **Reduced transparency** makes the bar and pane solid (`--mat-*-solid`). Forced colours turn the highlight box into a `Highlight` outline.
- Touch targets are 44 px. Drag-and-drop always has the picker as its keyboard alternative.

## 11. Motion moments (hand to the motion agent; names only)

| Moment | Suggested pattern (motion_designer §5) |
|---|---|
| `intake.drop-hover` (zone accepts a dragged file) | §7 lift / magnetic (already in `magnetic-drop.tsx`) |
| `intake.file-row-added` | §6 list insert |
| `intake.file-phase-progress` (bar tracks SSE) | upload-stage `scaleX` (motion.md §3.4) |
| `intake.file-done` | §10 check draw |
| `intake.step-change` | §2 pill morph + §13 enter-only content |
| `intake.source-pane-open` / `swap` | §1 / §4 inspector (same as `ClassInspector`) |
| `intake.row-decided` (Bekliyor → Onaylandı) | none on the row (A9). Status text swaps |
| `intake.bulk-bar-in` | §19 selection bar replaces toolbar |
| `intake.mapping-changed-recount` (İnceleme count updates) | §11 ticker on the step count only |
| `intake.commit-confirm` | §1 dialog |
| `intake.committed` (pill becomes Kaydedildi) | §10 check + §5 toast |

## 12. i18n (TR + EN)

- Keys live under `onboarding.*` (existing) plus new `intake.*`. Turkish is the source of truth for tone. English is written, not machine-translated.
- **Long Turkish strings** the layout must survive without truncating meaning: "Taslak · veritabanına henüz hiçbir şey yazılmadı" (48 chars; EN "Draft · nothing has been saved yet", 34). The pill wraps to two lines below 1280 px and never truncates. "Yapay zekâ ile okunacak dosyalar için KVKK bilgilendirmesi" (57). "Elle düzeltilmiş değer korunacak" (32). Buttons stay short: "Onayla / Accept", "Reddet / Reject", "Kaydet / Save".
- **Plurals and suffixes**: use the existing `tr-suffix` helper for case endings after codes and numbers ("2026-BAHAR dönemine", "A 206'ya", "PHAR 240'ın").
- **Numbers**: `tr-TR` grouping (1.348), percentages as "%71" in TR and "71 %"/"71%" in EN via `Intl.NumberFormat`. File sizes "2,3 MB".
- **Casefold**: search is Turkish-aware (İ/ı, `sube` finds `şube`), as in all-classes.md §7.
- **Field names** from the council (`room_request`, `instructor2`…) are never shown raw. Each maps to a label key (`intake.field.room_request` → "Oda talebi / Room request").
- Every file name, cell value and quoted source text is rendered with `dir="auto"` and `translate="no"`.

KVKK notice (TR source, EN parallel):

> **Yapay zekâ ile okuma ve KVKK.** Bu işteki 1 dosya (eczacilik_bahar_ders_programi.pdf) okunmak üzere Anthropic'in Claude API'sine gönderilecek. Gönderilen: sayfa görüntüleri ve metin; içinde öğretim elemanı adları ve e-posta adresleri olabilir. Anahtar: kurumunuzun Ayarlar › YZ bölümündeki anahtarı. Sonuçlar bu iş taslağında saklanır ve siz onaylamadan hiçbir veri kaydedilmez. Yöneticiniz bu özelliği kapatabilir. Ayrıntılı aydınlatma metni ›
>
> EN: **AI reading and KVKK.** 1 file in this job will be sent to Anthropic's Claude API to be read. What is sent: page images and text, which may include instructor names and e-mail addresses. Key: your institution's key in Settings › AI. Results stay in this draft job, and nothing is saved until you approve it. Your administrator can turn this off. Full notice ›

The retention period and the link target are set by the institution (open question 4).

## 13. API endpoints (backend tickets)

Existing, unchanged: `POST /council/jobs`, `GET /council/jobs`, `GET /council/jobs/{id}`, `GET /council/jobs/{id}/events` (SSE), `GET/POST /council/jobs/{id}/review`, `POST /council/jobs/{id}/commit`, `POST /council/jobs/{id}/rerun`, `GET /council/jobs/{id}/records?file=&type=&offset=&limit=`, `GET /council/jobs/{id}/artifacts`.

New or changed (ticket ids are suggestions):

| Ticket | Endpoint | Purpose |
|---|---|---|
| P19-I-01 | `GET /council/jobs/{id}/rows?state=pending\|ready\|accepted\|edited\|rejected&method=direct\|ai&file=&q=&sort=&offset=&limit=` | Cross-file row list for İnceleme. Each row is `{id, file_index, entity, values, state, method, confidence, issues[], provenance:{file, sheet\|page, cell\|table,row\|paragraph\|bbox\|json_pointer\|xpath\|ics_uid, raw}}`, plus `counts` by state and method |
| P19-I-02 | `POST /council/jobs/{id}/rows/decisions` body `{decisions:[{row_id, action:"accept"\|"reject"\|"edit", value?}]}` → updated counts | Bulk decide (≤ 500 per call). AI rows require an explicit decision. Server rule: `ready` is only ever set for `method=direct` rows |
| P19-I-03 | `GET /council/jobs/{id}/rows/{row_id}/source` → `{kind:"grid", sheet, window:{rows, cols, cells}, highlight}` or `{kind:"page", page, image_url, bbox}` or `{kind:"text", excerpt, range}` | Source preview. The `rendered` artifacts provide the page images |
| P19-I-04 | `PATCH /council/jobs/{id}/plan` body `{files:[{index, term_code\|term_id, program_ids[], week_count}]}` | File → term/program editor. Returns the new plan and blocking count |
| P19-I-05 | `GET /council/jobs/{id}/diff?term_id=&entity=requests\|sections\|courses\|instructors\|rooms\|rules&change=new\|changed\|same\|missing&offset=&limit=` | Diff against the current term by natural keys (import-wizard.md §3.5). Changed rows carry `{field, from, to, last_edit:{source, by, at}}` |
| P19-I-06 | `POST /council/jobs/{id}/commit` adds `{exclude_rows[], keep_current_fields[], archive_missing:boolean}` | Diff exclusions and protected edits honoured at commit |
| P19-I-07 | `GET /settings/ai` → `{intake_ai_enabled, retention_days, notice_url}`, `PUT` (planning.admin) | Admin switch + KVKK parameters. `POST /council/jobs` with `ai=true` answers 403 when disabled |
| P19-I-08 | Commit runs in one DB transaction (all or nothing) | No half-written term on failure |
| P19-I-09 | Commit writes one `AuditEvent` (kind `intake.commit`, children per entity) and `POST /audit/{id}/undo` reverts it within 30 days | Undo promise in the confirm text |
| P19-I-10 | `GET /council/jobs/{id}/usage` → tokens, cost, model, files sent | The AI chip popover and KVKK record |

Permissions: GET = `planning.view`; decisions, plan, commit = `planning.edit`; AI settings = `planning.admin`.

## 14. Open questions for the product owner

1. Retire `/import` (the v1 four-source wizard) in favour of `/onboarding`, and redirect it? The council already covers its four shapes through the fast path.
2. Should bulk accept be allowed for **AI** rows? This spec allows it on a visible selection of at most 50, behind a confirm that names the count. A stricter reading of "every extracted row needs coordinator review" would require one decision per row.
3. Is undo of a whole commit within 30 days required (P19-I-09)? It is cheap for created rows and harder for updated ones.
4. KVKK: what retention period applies to council artifacts that hold AI input (page images), and which institution page should the "Ayrıntılı aydınlatma metni" link open?
5. Should the "Dosyada yok" (missing) rows ever be archived automatically when the same file kind is re-imported? Default: never.
