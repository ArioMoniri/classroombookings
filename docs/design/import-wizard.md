# Import wizard — Excel planning list / exam list / weekly grid / legacy CRBS DB

Owner: design-pro (B). Route `/import` (+ `/import/[jobId]`). Backend contract:
`POST /imports/planning-list | exam-list | weekly-grid | crbs` (multipart or DSN) → `202 {job_id}`,
`GET /imports/{job_id}` → `{status, summary:{rows, created, updated, warnings[]}}`.
Licences: see `navigation-shell.md §9`. Tokens: `docs/design/tokens.md` if present, else shadcn semantics.

---

## 1. References (what to borrow)

| # | Reference | Borrow |
|---|---|---|
| 1 | [HubSpot – import flow (14 screens)](https://mobbin.com/flows/76a881cf-e903-4eaf-bb60-f7a779cd06c2) | 4-step stepper in the header (`Type · Upload · Map · Details`, "Step 3 of 4"); mapping table with **"Preview information"** column showing 2 sample values per column; "0 errors found, of 3 rows scanned" summary bar; sticky footer `Back · Cancel · Next` with "Tip: press Enter to continue"; completion page with 4 stat tiles (Import rows / New / Updated / –) |
| 2 | [Attio – CSV import (13 screens)](https://mobbin.com/flows/2c5ec636-6d46-416e-b798-ae09d51881c3) | Compact 4-step tabs `1 Upload file · 2 Map columns · 3 Review values · 4 Preview import`; file column → attribute `Select` with warning icon on ambiguous mapping; right-hand "Data preview" of first 3 values; **Review values** screen listing only "Needs review 3" rows with inline fix input; "3 will be created · 0 will be updated" diff line; confirm dialog before start |
| 3 | [Fibery – import into database](https://mobbin.com/flows/9d7f8560-a1ab-4821-b123-7ff4db328f9d) | "New Database ⇄ Existing Database" toggle (→ our **New term / Existing term** choice); checkbox per field to skip; coloured bar data preview; "Import 5 items" primary |
| 4 | [Notion – import source picker](https://mobbin.com/screens/244b511b-a7ea-4a87-ab0e-024b867294cd) | Big dashed dropzone + "File-based imports" card grid beneath (our 4 source cards) |
| 5 | [Remote – review time-off data](https://mobbin.com/screens/ab52924c-333f-42fb-bc19-659aa03720e0) | Per-row status icon (✓ / ⚠1), toggles "Show only rows with errors" and "Show only required columns", error popover on the offending cell with a **Select** to fix it inline; "Save as draft" + "Continue with 1 record" |
| 6 | [Twenty – validate data](https://mobbin.com/screens/8429b076-1864-4c32-b237-7933be9769ae) | Editable cell with yellow outline; floating "Show only rows with errors / Remove" bar |
| 7 | [7shifts – import preview](https://mobbin.com/screens/6b45f042-7f89-46f1-b46f-8270604842b8) | Amber banner "We're unable to import one or more…", red cell chip with ⓧ, "Import employees (1/2)" count in CTA |
| 8 | [QuickBooks – review & confirm](https://mobbin.com/screens/cf8ed259-e9cc-4a61-8fbc-fab397a4ee85) | Row checkboxes to include/exclude from the import |
| 9 | [HubSpot – completion](https://mobbin.com/screens/b68eafc6-ec63-462e-ba3f-79847c8add11) | Success tile + "Clean up your import" secondary card; "Back to Import History" |

## 2. Information architecture

```
/import
  ├─ Source picker (4 cards)                       step 0
  ├─ Upload  (file dropzone | DSN form for CRBS)    step 1
  ├─ Map     (sheet + header row + column mapping)  step 2
  ├─ Review  (parse warnings table, per-row fixes)  step 3
  ├─ Confirm (idempotent diff: create/update/skip)  step 4
  └─ Done    (summary tiles, links to Requests/Rooms) 
/import/history   (table of import_jobs; re-open any job's review)
```

Source cards (Notion #4 layout, 2×2 on desktop):

| Card | Accepts | Target tables | Shape (DATA_ANALYSIS) |
|---|---|---|---|
| **Ders planlama listesi** (planning list) | `.xlsx/.xlsm` | sections, meeting_requests, courses, programs, instructors | A |
| **Sınav planlama listesi** (exam list) | `.xlsx` | exam_requests | B |
| **Haftalık derslik takvimi** (weekly grid) | `.xlsx` (multi-sheet) | rooms (capacity/tags), blocks, assignments(origin IMPORT) | C |
| **CRBS veritabanı** (legacy DB) | MySQL DSN or `.sql` dump | rooms, periods, bookings→blocks, users, departments | — |

Step 2 and 3 differ per shape (§3.3, §3.4). Wizard state lives in URL (`?source=planning&step=2&job=…`) so refresh/back works; file blob is kept in memory + uploaded at step 1 (server stores it against the job).

## 3. Interaction spec

### 3.1 Stepper
- Horizontal stepper in page header (HubSpot #1): 5 dots connected by a 2 px line; completed = check icon, current = filled, future = outline. Label under each. Right side "Adım 3 / 5".
- Line fill animates 200 ms ease-out when advancing. Reduced motion: no fill animation.
- Steps are clickable backwards only; forward requires validation.
- Sticky footer: `← Geri` (ghost) · `İptal` (link) · spacer · hint "Enter = devam" · `Devam →` (primary, disabled until valid). `Enter` advances when the current step is valid and focus is not in a textarea.

### 3.2 Step 1 — Upload
- Dropzone (`react-dropzone`): 100 % width, min-height 220 px, dashed 2 px `border-border`, idle copy "Dosyayı buraya bırakın veya seçin · .xlsx, en fazla 50 MB". On `dragenter` border → `border-primary`, background `bg-primary/5`, icon lifts 4 px (120 ms). Accept exactly one file per import; reject other extensions with inline error "Yalnızca .xlsx".
- After drop: file chip (name, size, ×) above the zone (Fibery/Attio pattern); zone shrinks to a 56 px "Reupload" strip.
- The client reads the workbook with `SheetJS` **only to list sheet names and the first 30 rows** for the mapping preview; the authoritative parse is server-side.
- CRBS source instead shows a form: Host, Port (3306), Database, User, Password (masked, eye toggle), "Bağlantıyı test et" button (→ `POST /imports/crbs?dry_run=1`), result chip ✓ "Connected · 61 rooms · 14 802 bookings" or ✗ with server message. Alternatively a `.sql` dump dropzone (tab switch).
- States: `idle · dragging · rejected(reason) · uploading(progress %) · uploaded · failed(retry)`. Upload progress is a 4 px bar under the chip; cancel aborts the XHR.

### 3.3 Step 2 — Map
- Left 60 %: mapping table (TanStack Table, non-virtualised, ≤ 30 rows). Columns: **File column** (header text, trimmed, with raw `\n` shown as `↵`), **Preview** (2 sample non-empty values, mono, truncated with title), **Maps to** (`Select` of target fields, grouped: Section / Request / Course / Instructor / Skip), **Status** (✓ auto-mapped, ⚠ guessed, – skipped).
- Auto-mapping uses the DATA_ANALYSIS header dictionary (e.g. `Derslik Talebi → requested_room_text`, `Dersin Günü → day`, `Dersliğin Kullanılacağı Haftalar → weeks`). Guessed when fuzzy score < 0.9 → amber icon + tooltip "Guessed from 'Derse Kayıtlanacak Öğrenci Sayısı'".
- Top of step: `Sheet` select (default `Sayfa1`), `Header row` number input (default 1; weekly grid default 2), "Existing term ⇄ New term" toggle (Fibery #3) with term `Select`.
- Right 40 %: **Data preview** card showing first 5 rows under the chosen mapping as they will be interpreted (e.g. `Perşembe/Cuma` → chips `Thu` `Fri` + `flexible_day`).
- Required targets missing (course_code, day, start_time for shape A) → summary bar turns red: "2 zorunlu alan eşlenmedi: Ders Kodu, Gün". Continue disabled.
- **Weekly grid (shape C)** mapping is fixed; step 2 instead shows: detected sheets list with week label parsed from the sheet name (`9 - 15 Şubat → W2 2026-02-09`), checkbox per sheet, room-header regex result count ("29 + 29 + 12 rooms detected"), colour legend mapping (`FFFF00 → HAZIRLIK`, `7030A0 → ?` editable) and a note that cell comments will be imported as assignment notes.
- Save mapping as the user's default for this source (`PUT /settings/import_mapping.planning`), restore next time with a "Son eşleme yüklendi" toast.

### 3.4 Step 3 — Review (parse warnings)
- Server parses the whole file (`POST …?dry_run=1`), returns `warnings[]` with `{row, column, code, raw, suggestion, severity: error|warning|info}`. Show summary bar: "1 529 satır · 1 487 ✓ · 31 ⚠ · 11 ✗".
- Table (TanStack, virtualised with `@tanstack/react-virtual`, row height 44 px): columns `Row# · Status · Course · Program · Day · Time · Room request · Problem · Fix`. Status cell = ✓ / ⚠ count / ✗ (Remote #5).
- Toggles above table: **"Sadece sorunlu satırlar"** (default ON when errors > 0), **"Sadece zorunlu sütunlar"**, search box (course code / instructor), severity filter chips.
- Problem cell: short code text, e.g. `TIME_OFF_GRID 09:00 → 08:30?`, `DAY_UNKNOWN "Hafta içi hergün"`, `ENROL_NOT_INT "12:30:00"`, `COURSE_CODE_PREFIX "YENİ DERS↵ACU 311"`. Hover/focus shows popover with raw cell value and the rule.
- **Fix cell** (per-row inline fix): depends on `code`:
  - time snap → `Select` of grid periods (`08:30 (P1)`, `09:20 (P2)`) preselected with suggestion;
  - day unknown → `Select` {Mon…Sun, Flexible, Not-a-room-request};
  - enrolment / credits parse → number input prefilled with the regex guess;
  - course code → text input with live canonical preview chip (`MAT112 → MAT 112`);
  - room request unparsed → opens the **chip editor** from `requests-inbox.md §3.4` in a popover;
  - any → "Skip row" checkbox.
  Fix is applied client-side to `fixes[row]` and re-validated server-side on Continue (`POST …?dry_run=1&fixes=`). Row status animates ✗→✓ with a 150 ms colour fade; reduced motion: instant.
- Bulk fix bar (appears when ≥1 row selected): "Apply suggestion to 31 selected", "Skip selected". Keyboard: `j/k` move rows, `Enter` open fix, `s` skip, `a` accept suggestion, `Esc` close popover.
- Errors (✗) block the row only, not the import: CTA reads "Devam · 1 518 / 1 529 satır" (7shifts #7). A warning banner lists codes with counts and a "Download problem rows as .xlsx" link.
- Empty: no warnings → green card "Tüm satırlar ayrıştırıldı" and auto-advance button.
- Error: parse crashed → red card with server error id, "Retry", "Download raw log".

### 3.5 Step 4 — Confirm (idempotent re-import diff)
- Server computes diff against the target term using natural keys (`section = term+course_code+program+label`, `meeting_request = section+day+start+weeks`, `room = building+code`, `block = room+day+periods+weeks`).
- Show three stat tiles with count-up animation (beUI Number Animation, ≤ 300 ms): **Yeni** (create), **Güncellenecek** (update), **Değişmedi** (skip), plus **Silinecek?** (rows present in DB from a previous import of the same file kind but absent now — default *not* deleted; checkbox "Remove missing rows (archive)" with confirm).
- Expandable tables per tile (Attio #2 "3 will be created"): for *update* rows show a **field diff**: old value struck, new value green, per field (e.g. `requested_room_text: "A 105" → "A 105 (Bilg. Lab)"`). Use shadcn `Table` + tokens `--success` / `--destructive`, not a library diff component (kobra File Diff is paid).
- Checkbox per row to exclude (QuickBooks #8). Footer CTA "İçe aktar · 1 518 satır" opens confirm `AlertDialog` ("Bu işlem 2026 Bahar dönemine 412 yeni, 1 106 güncelleme yazacak. Geri alınabilir: hayır, ancak import geçmişinden önceki değerler görülebilir.").

### 3.6 Running & Done
- After confirm → `202 {job_id}`; page shows job card: status pill (`QUEUED → RUNNING → DONE/FAILED`), progress bar (server reports `processed/total` via `GET /imports/{id}` polled every 1 s or SSE), elapsed time, "Run in background" (navigates away; toast with progress keeps updating; see navigation-shell §3.7).
- Done: 4 tiles (rows / created / updated / warnings) + CTAs: "Talepleri incele →" (`/requests?import=job`), "Odaları gör" (grid import), "Yeni içe aktarma". Secondary card "Clean up": link to inbox filtered `status=NEEDS_REVIEW&import=job`.
- Failed: red card, error id, "Retry same file", "Download server log".

### 3.7 History (`/import/history`)
TanStack table: date, kind, filename, user, rows, created/updated, warnings, status; row click → read-only review of that job; "Re-run with same mapping" action.

## 4. Component list

| Component | Source | Licence | Note |
|---|---|---|---|
| Dropzone behaviour | `react-dropzone` https://github.com/react-dropzone/react-dropzone | MIT | `pnpm add react-dropzone`; style with tokens |
| Magnetic Dropzone (visual ref: zone "leans" toward the dragged file; `accept/maxSize/onFilesChange` API) | kobra https://kobra.systems/components/magnetic-dropzone | Paid (not in Free set; free tier personal-use only) | Reference only; reimplement lean as `motion` `rotateX/Y` ≤ 3° following pointer, disabled on reduced motion |
| Drag & drop with physics | transitions.dev `/detail.html?t=drag-drop-physics` (free) | custom, commercial OK, keep comment | optional spring on drop |
| Stepper | shadcn has none → build `components/ui/stepper.tsx` (ol/li, `aria-current="step"`) | MIT (ours) | Step Progress on kinetics is reference only |
| Table, Select, Checkbox, Switch, Popover, Tooltip, AlertDialog, Badge, Progress, Card, Tabs, Input | shadcn/ui | MIT | `npx shadcn@latest add table select checkbox switch popover tooltip alert-dialog badge progress card tabs input` |
| Virtualised rows | `@tanstack/react-virtual` | MIT | review table > 200 rows |
| Filter Table (status chips filtering live data) | beautifului.dev https://beautifului.dev/#filter-table | MIT | copy-paste the chip bar pattern for severity filters |
| Diff Table (AI-proposed edits across tabular data) | beautifului.dev https://beautifului.dev/#diff-table | MIT | copy the old→new cell rendering for step 4 field diff |
| Grouped Table | kobra https://kobra.systems (Content › Grouped Table) | Paid | reference only (group by sheet/week) |
| Number count-up | beUI https://beui.dev/components/motion/number | MIT | `bunx --bun shadcn add @beui/number` |
| Skeleton to Content / Spinner to check morph | transitions.dev free set | custom, commercial OK | job card status transition |
| Success Check | kinetics (SVG draw) | no licence | reimplement: `pathLength` 0→1, 250 ms |
| xlsx client preview | SheetJS community `xlsx` https://git.sheetjs.com | Apache-2.0 | read first 30 rows only; never trust for final parse |

## 5. Responsive behaviour

| Width | Layout |
|---|---|
| 360 | Stepper becomes a compact "3/5 · Gözden geçir" line with a 4 px progress bar. Source cards stack 1-col. Upload full-width. Map: table collapses to **cards per file column** (header, preview, Select, status) ; preview pane moves below as a collapsible. Review: table → list rows (course + problem + fix button opening a bottom Sheet). Footer buttons full-width stacked (primary on top). |
| 768 | Source cards 2×2. Map table 100 % with preview as a collapsible drawer on the right (`Sheet`). Review table shows 5 columns (Row, Status, Course, Problem, Fix); others under an expander. |
| 1280 | Map 60/40 split. Review full table 9 columns, sticky header, virtualised. Confirm tiles 4-up. |
| 1920 | Content max 1600 px; review table gains Raw-value column; preview pane 480 px. |

Touch: fix popovers become bottom Sheets; row selection via long-press (400 ms) or leading checkbox column (always visible < 1024 px).

## 6. Accessibility
- Stepper `<ol>` with `aria-current="step"`; each step announces "Step 3 of 5, Review".
- Dropzone is a `<button>` (react-dropzone `getRootProps` with `role="button"`, `tabIndex 0`); `Space/Enter` opens file picker; drag feedback also expressed in text ("Bırakın").
- Table: `<caption>` with counts; status icons have `aria-label` ("3 warnings"); problem codes also exist as visible text, never colour-only; severity colour + icon + text.
- Inline fixes are real form controls with `<label>` (visually hidden) "Fix for row 213".
- Live region announces "31 rows need review" after parse and "Row 213 fixed".
- Keyboard map in §3.4; all popovers trap focus and restore.
- Error summary links jump to first affected row (`aria-describedby`).

## 7. Open questions
1. Keep the parsed-but-unfixable rows in DB as `NEEDS_REVIEW` requests (so the inbox handles them) or keep them out until fixed? Spec assumes **kept** with status NEEDS_REVIEW, because the inbox has richer tools.
2. Delete semantics for re-import: archive vs hard delete of rows absent in the new file (spec default: never delete, offer archive).
3. Weekly grid import: do we create `assignments(origin=IMPORT)` tied to a synthetic run "Imported 2026 Bahar grid", or only `blocks`? Needed for the "reproduce the human planner" regression.
4. Max upload size — DATA_ANALYSIS files are ≤ 2.3 MB, but the university panel export may be larger; spec says 50 MB.
5. Buy kobra Pro for Magnetic Dropzone / Grouped Table / File Diff (same question as navigation-shell §8.3)?
