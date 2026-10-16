# F-08 · File intake: Bahar xlsx + a CSV export + a scanned PDF (AI off) → review → dry-run diff → commit → re-upload shows remembered mappings

Persona: **admin** as coordinator; viewer for the read-only check. Viewports: desktop for the full flow; tablet and phone for the screens they visit (the drop zone, the files list, one review card, the commit sheet).
Owner decisions and spec (ROADMAP Phase 19; `docs/design/v2/phase19-intake.md`):
- **Formats.** Structured formats are read directly, with no AI (xlsx, xls, csv/tsv, ods, json, xml, ics). PDF, DOCX, TXT/EML and images take the AI route only when an admin allows it, after a KVKK sign-off. With AI off they are listed as "YZ kapalı, okunmadı" and nothing is sent.
- **Draft until commit.** Nothing is written until the coordinator commits. Every AI row needs a person's decision.
- **Fark before Kaydet.** A dry-run diff shows what will change before the write.
- **Intake memory.** Confirmed mappings are remembered per file signature and offered again as review-gated suggestions, never applied by themselves.
- **Undo.** Intake commit can be undone for 30 days (adopted default).

Testable on `b75047b`: **partly**.
- The council **API** is complete: rows, decisions, dry-run, term lock and memory.
- The Phase 19 **intake UI** is not built yet: the `/onboarding/[jobId]` workspace, the stepper Dosyalar → Eşleme → İnceleme → Fark → Kaydet, the draft pill, the source preview and the remembered chips. It sits with the design-system agent ("Onboarding frontend for rows/decisions, dry-run diff, rerun_queued, remembered items").
- So every step below has a **UI target** and an **API check**. Run both. Report the UI as `FAIL` when an older screen does something different, and as `BLOCKED: intake UI not built` when there is no screen at all. Report the API result separately on the same step.

## Preconditions

1. A **fresh** stack (`stack.sh up --fresh` on the admin's fresh ports, README §4.2): only the admin and an empty term `2026-BAHAR` (`TERM_ID`). Then run the seed's accounts block (viewer.test needs creating: role VIEWER) and the SMTP block. Do **not** mask yet: there is nothing to mask before the import.
2. AI is **off** and there is no key:
   - `GET /ai/policy` → `intake_enabled: false, vision_enabled: false`;
   - `GET /settings` shows no API key.
3. Input files, built from the snapshot's fixtures into a fresh folder:
   ```bash
   FX="$SNAP/smartsched/backend/tests/fixtures"; IN="$SCR/flow-in-F08"; mkdir -p "$IN"
   cp "$FX/bahar_derslik_planlama_listesi_v5.xlsx" "$FX/universal/bahar_requests_en.csv" "$IN/"
   python3 -I - "$FX" "$IN" "$SNAP/smartsched/backend/tests/council" <<'PY'
   import pathlib, sys
   fx, out, council = map(pathlib.Path, sys.argv[1:])
   sys.path.insert(0, str(council))
   from exports import csv_bytes            # Turkish Excel "CSV (noktalı virgülle ayrılmış)": cp1254, ';', comma decimals, dotted times
   (out / "bahar_listesi_noktali_virgul.csv").write_bytes(csv_bytes(fx / "bahar_derslik_planlama_listesi_v5.xlsx", delimiter=";", encoding="cp1254", decimal=",", dotted_times=True))
   from PIL import Image                    # a scanned page: an image-only PDF, no text layer
   Image.open(fx / "universal" / "final_exams_page1.png").convert("RGB").save(out / "taranmis_sinav_programi.pdf", "PDF", resolution=150)
   PY
   python3 -I -c "import pdfplumber,sys;print(repr(pdfplumber.open(sys.argv[1]).pages[0].extract_text()))" "$IN/taranmis_sinav_programi.pdf"   # expect '' or None
   ```
   - Job A = `bahar_derslik_planlama_listesi_v5.xlsx` + `bahar_requests_en.csv` (the CSV export: English headers, another column order, the general path) + `taranmis_sinav_programi.pdf`.
   - Job B = `bahar_requests_en.csv` again (memory).
   - Job C = `bahar_listesi_noktali_virgul.csv` (cp1254 export).
4. **KVKK (README §7):** the review tables show real instructor names until the masking step S09, which runs **after S11** (S10/S11 compare re-uploads against the committed names). Every screenshot before S09 passes `mask: [page.locator("table tbody, [role=grid] [role=row]:not(:first-child), [data-testid=review-row], [data-testid=upload-row]")]`, and also masks the source preview pane. Report counts, never cell values.

## Steps

**S01 · admin · open the intake screen**
- Do: sidebar **"Dosyalardan kur"** (folder icon) → `/onboarding`.
- UI target: the title "İçe al" and the lead "Dosyaları bırakın; okuyup size gösteririz. Siz onaylamadan hiçbir şey kaydedilmez." A drop zone that is a real button (`Enter` / `Space` opens the picker) reading "Dosyaları buraya bırakın veya seçin", with the format list and "en fazla 50 MB". "Son işler" is empty: "Henüz içe aktarma yok".
- Today the HEAD texts are "Kurulum" and "Dosyaları buraya bırakın veya seçmek için tıklayın". That counts as a PASS with a note if the function is the same; the spec wording is the suggester's call.
- Accessibility: the file input has a label (UI review: an unlabelled `input[multiple]`). The zone is not a nested interactive.

**S02 · admin · drop the three files (Job A)**
- Do: `page.setInputFiles('input[type=file]', [xlsx, csv, pdf])` (on touch viewports use the system picker path: the same call).
- UI target: three rows appear at once. Each has a format chip (**XLSX**, **CSV** with "UTF-8 · ," shown, **PDF**) and a predicted route: "Doğrudan okunur" for xlsx and csv, "YZ ile okunur" for the PDF.
  - Because an admin has switched AI off, the PDF row reads **"YZ kapalı, okunmadı"**, and the "Yapay zekâ kullan" switch is disabled with **"Yönetici kapattı"**. No KVKK notice is needed (nothing will be sent).
  - The primary button reads "Başlat · 3 dosya" (not "YZ ile oku ve başlat").
- HEAD today: "3 dosya seçildi" with "Kaldır" per file, a checkbox "Anahtar tanımlıysa yapay zekâ modelini kullan", and "3 dosyayı analiz et". With AI policy off, that checkbox must be disabled or have no effect: check in S04 that no model call happened.

**S03 · admin · start and watch the progress**
- Do: start.
- API: `POST /council/jobs` (multipart, `mode=auto`, `lang=tr`, `year_hint=2026`) → 201 with the job id `JA`. `GET /council/jobs/JA/events` is an SSE stream.
- UI target: one row per file with a phase line ("okuma ✓ · yapı ✓ · çıkarım %62 · kurallar –") and a 4 px bar driven by the SSE events. A polite live region announces "Okuma bitti. {n} satır inceleme bekliyor." when done. The header pill reads "Okunuyor · %{n}", then "Taslak · veritabanına henüz hiçbir şey yazılmadı".
- The xlsx row's result reads like "Ders planlama listesi · 1.524 talep · … şube". The CSV row reads "Talep listesi · {n} toplantı".

**S04 · admin · the scanned PDF goes to "needs AI"** (needs scenarios I9, I10)
- API: `GET /council/jobs/JA`:
  - the PDF file entry has 0 records and a warning that it has no text layer and can only be read by the AI model;
  - the job's AI note says the deterministic path was used because AI is off ("an administrator has not allowed sending file content …");
  - token use is 0 (`GET /council/jobs/JA/artifacts` holds no model output).
- UI target: the PDF row turns warning tone: **"Bu PDF'de okunabilir metin yok (taranmış belge olabilir)"** plus "YZ kapalı · okunmadı", with actions "Yeniden oku" / "Dışarıda bırak". The commit bar counts it out ("2 / 3 dosya hazır · 1 dosya okunamadı, kaydedilmeyecek"). It is never an empty success (I9).
- Also: no row from the PDF appears in the review.

**S05 · admin · mapping (Eşleme)**
- API: `GET /council/jobs/JA/review`. The xlsx took the fast path (`fast:planning-list`) and needs no column mapping. The CSV has `mapping` items, one per column, with the proposed field, confidence, samples and alternatives (e.g. "Assigned Room" → the definitive room, "Requested Room" → the room request, "Lecturer" → instructor). There is a `plan` item for file → term with `2026-BAHAR` proposed.
- UI target (Eşleme): per CSV column a row with **Dosya sütunu**, 3 **Örnek** values (masked in screenshots), an **Alan** select grouped Talep / Ders / Hoca / Oda / Kullanılmaz, **Güven** (with ⚠ under the threshold), an **Alternatif** chip, and a state (Bekliyor / Onaylandı / Değiştirildi). Field names are never shown raw (`room_request` → "Oda talebi").
- Do: accept every proposed mapping except one. Change "Requested Room" to "Kullanılmaz" (not used). Confirm the file → term row = 2026-BAHAR.
  - API: `POST /council/jobs/JA/review` with those decisions → 200.
  - The İnceleme count updates.
  - If the job reruns (`rerun_queued`), commit is refused meanwhile with a clear message.

**S06 · admin · review rows (İnceleme)**
- API: `GET /council/jobs/JA/rows?limit=50` → counts by state and method. Every row is **direct** (no `ai` method, because AI is off). Rows above the threshold are `ready`. Blocking items (unassigned files, low-confidence mappings) are counted.
- Provenance check (I3): the row for **PHAR 240 §1** carries `v5.xlsx · Sayfa1 · R545` with the definitive room **A 206**. Rows from the CSV carry `bahar_requests_en.csv · satır N · "Assigned Room"`.
- UI target: tabs **Tümü / Bekleyen / Hazır / Reddedilen** with counts and a "Yalnızca YZ" chip (0 here). The Yöntem chip reads **"Doğrudan"** (sheet icon + word). Selecting a row opens the source preview with the cell highlighted and described in text ("Sayfa1, R545, değer A 206").
  - Keyboard: `j`/`k` move, `a` accept, `r` reject, `e` edit, Enter opens the source, Esc closes it.
  - After accepting a row, focus moves to the next **Bekliyor** row.
- Do: reject 2 rows (any). Accept the remaining blocking items.

**S07 · admin · dry-run diff (Fark)**
- API: `POST /council/jobs/JA/commit {"term_id": TERM_ID, "dry_run": true}` → per-entity create / update / unchanged / conflict counts and row diffs. On the empty term almost everything is "create".
  - **Nothing is written:** `GET /terms/TERM_ID` and `GET /terms/TERM_ID/classes` (or the classes count) are unchanged before and after.
  - **No double import.** The xlsx and the CSV describe the same meetings, so the planned creates for meeting requests stay at **≈ 1,524** (± 1 %, natural keys, D14). About 3,000 is a **blocker**.
- UI target (Fark): one summary line **"Yeni {n} · Değişecek {n} · Aynı {n} · Dosyada yok {n}"**, each part a filter. An entity switch Talepler · Şubeler · Dersler · Hocalar · Odalar · Kurallar. A checkbox per changed row to exclude it. "Dosyada yok" is never archived by default.

**S08 · admin · commit (Kaydet)**
- UI target: the sticky commit bar reads "Hazır · {n} talep … · 2026-BAHAR dönemine kaydet". Kaydet opens the confirm: "2026-BAHAR dönemine {n} yeni talep, {n} değişiklik ve {n} oda yazılacak. {n} satır reddedildi, … Bu işlem tek bir kayıt olarak geçmişe yazılır ve 30 gün içinde geri alınabilir." After the confirm, the pill reads "Kaydedildi · 2026-BAHAR · {date time}" and the bar says "Kaydedildi. Talepleri gör →".
- HEAD today: "Döneme yaz" → "Dönem grubu", term code / name / weeks, "Onaylanan kural önerilerini kısıt olarak yaz", "Yaz" → **"2026-BAHAR dönemine yazıldı"**.
- API: `POST /council/jobs/JA/commit {"term_id": TERM_ID}` (what the UI sends) → 200. The counts equal the dry-run's (I4: "counts == the real commit's"). The 2 rejected rows were not written. There is one `council.commit` audit event. While the commit holds the term write lock, a parallel `POST /imports/planning-list` for the same term → **409** with a Turkish message (P19-03).

**S10 · admin · re-upload: remembered mappings (Job B)**
- Do: a new job with `bahar_requests_en.csv` only.
- API: `GET /council/jobs/JB/review` → the CSV's mapping items carry `remembered` (value, job, date, the label "remembered from <date> / job JA") and a `suggestion` equal to S05's decisions, including "Requested Room" → not used. The job is still **review-gated**: nothing was decided automatically, and commit without decisions answers 409.
- UI target: each remembered mapping shows a chip such as "Önceki işten hatırlandı · {date}" (label as built), preselected as a suggestion. One click accepts all remembered items, and each stays visible as a decision.
- Do: accept the remembered items. Dry-run against 2026-BAHAR.
- API: the dry-run reports **0 creates and 0 updates for meeting requests**: "re-upload in a new job changes 0 rows" (I5 / D14). Commit it. Again 0 changes.

**S11 · admin · the Turkish Excel CSV (Job C)** (I1, I8)
- Do: a new job with `bahar_listesi_noktali_virgul.csv`.
- API: the file entry reports encoding **cp1254** (Windows-1254) and delimiter **`;`**. Course and programme names keep Turkish letters (ş, ğ, İ, ı): spot-check 5 rows against the xlsx import. The dry-run against 2026-BAHAR is ≥ 99 % "unchanged" for meeting requests.
- UI target: the Biçim column reads "CSV · Windows-1254 · ;".

**S09 · admin · mask names now** (KVKK; runs **after S11**)
- Why here: S10 and S11 compare re-uploads of the same names against Job A's committed rows. Masking first rewrites those names to initials, so every re-upload then plans 400+ new instructors and 1,300+ request changes: a test artefact, not the product's answer (round 1, R1-S-39). Until this step, keep the precondition-4 masks on every screenshot.
- Do: `bash "$SNAP/scripts/record/stack.sh" mask` (with this stack's env). It masks with `kvkk_mask.py`, then runs the README §7 check and prints **`left 0`**. If it stops with names left, run the README §4.4 masking block and report the count and shapes it printed (T-R1-44).
- From here on, screenshots need no masks.

**S12 · viewer · read-only job**
- Do: log in as viewer.test (VIEWER: `planning.view` only). Open Job A.
- UI target: every decision control is disabled, and a note at the top reads "Bu işi görüntüleyebilirsiniz. Onaylamak ve kaydetmek için **planlama düzenleme** izni gerekir."
- API: `GET /council/jobs/JA/review` → no sample values, texts or names (`content=false`); `POST …/review` → 403; `POST …/commit` → 403.

**S13 · admin · wrong files**
- Do: drop a PNG renamed to `.xlsx`, and the Bahar **weekly grid** workbook as a 4th file in a new job.
- Expect: the PNG is refused at upload with a specific message (not "server error"). The grid workbook is recognised as a weekly room grid ("Haftalık derslik takvimi") and routed to its importer (M-20: a specific reason, not "Doğru Excel şablonu mu?").

**S14 · admin · undo the commit** (adopted default: 30 days, P19-I-09)
- Do: `/admin/audit` → the `council.commit` event → Geri al.
- Target: one step reverts Job A's writes. Without P19-I-09 the confirm text in S08 must say "Geri alınamaz; önceki değerler geçmişte görünür" instead. Report which one the product says and does. A confirm that promises an undo that does not work: FAIL (major).

**S15 · admin · AI route with the switch on** — `SKIP (NEEDS-AI: no key)`
- Kept for the round that has a key: the KVKK notice text (phase19-intake.md §12) before start, "YZ ile oku ve başlat", every AI row "Bekliyor" and blocking, bulk accept ≤ 50 with a confirm naming the count, low-confidence rows one by one.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Drop:** the drop zone is a full-width ≥ 44 px button that opens the system picker (`<input type=file multiple>` with an `accept` list). There is no drag-only path (M-11). "Fotoğraf çek" is offered only when the AI route is allowed.
- **Files:** one card per file with the name truncated in the middle, the format chip, the route, a progress bar and the counts. No table on phone (M-07).
- **Mapping:** one card per CSV column (header, 2 samples, a full-width select, confidence, state). File → term opens a bottom sheet per file.
- **Review:** cards ("◌ PHAR 240 §1 · Doğrudan" / "Pzt P1–P3 · 1–14 · A 206 · 80" / provenance), with Onayla / Düzenle / Reddet as ≥ 44 px buttons. A tap opens a bottom sheet: the 45 % detent shows the source preview, the 92 % detent the row editor. Long-press enters select mode, and the bulk bar replaces the tab bar.
- **Diff:** a grouped list (Yeni / Değişecek / Dosyada yok). Each changed row expands to its field diff, and nothing scrolls sideways.
- **Commit:** a floating capsule "◌ {n} bekliyor (Kaydet)" above the tab bar and the safe-area inset (M-05, M-06). The confirm opens as a bottom sheet.
- The draft pill stays visible in the top bar on every step.

## Flow acceptance

1. With AI off, a scanned PDF produces 0 rows and a clear Turkish "needs AI / no text layer" message. Nothing leaves the server.
2. Structured files are read directly with provenance down to the sheet row and column.
3. A dry-run shows the exact counts of the later commit and writes nothing. The real commit equals it, is one audited event, and holds the term lock.
4. The same meetings in two formats in one job are not imported twice.
5. A re-upload offers the earlier mapping decisions as visible suggestions. Nothing is auto-applied, and the re-commit changes 0 rows.
6. Viewers can look but not decide, and they get no raw cell content.
7. MOBILE.md passes on `/onboarding` and on every job step that exists, at 390 and 768.

## Scenarios covered

needs-doc I1 (CSV parity), I3 (provenance), I8 (cp1254), I9 (scanned PDF), I10 (AI off), I13 partly (round trip through the CSV); phase19-intake.md I1–I11; ROADMAP intake I4 (dry-run), I5 (re-upload 0 rows), intake memory; M-13, M-20, M-22, M-25 from the admin persona.
