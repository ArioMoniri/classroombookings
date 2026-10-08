# All classes v2: every class of the term in one place

Owner: design-pro (v2 calendar + all-classes) · Status: spec v2.0 (2026-10-08) · Route: **`/classes`** (new), with `?kind=meetings|exams`
Shares with `docs/design/v2/calendar.md`: the inspector (`ClassInspector`), filter model, faculty colours (§8.1 there), glass roles (§8.2 there: `--mat-chrome` for floating capsules, `--mat-thick` for inspector, popovers and sticky headers, rule G1), motion table (§8.4 there; `/motion_designer` springs and patterns), and the anti-AI rules. Glass components and tokens: `docs/design/v2/liquid-glass.md`. Motion: `docs/design/v2/motion.md`.
Data: Bahar has 1,529 meeting rows (about 1,300 with day and time), Güz 1,037, Final 926 exam rows. One row is **one weekly meeting of a section**, merged with its **solver placement** in the selected run and its **provenance** (file, sheet, row).
Wireframes: `docs/design/v2/wireframes/all-classes-desktop.svg`, `all-classes-mobile.svg`.

**How this relates to the existing table surfaces**: the requests inbox (`/requests`, requests-inbox.md) is intake triage (parse status, free-text chips), and the Generator Studio class list (generator-studio.md §3.2) is draft scope (in plan / left out / pins). All classes is the **term-wide truth after solving**: request + placement + issues + changes + provenance. The three surfaces share one table core (`ClassTable`: columns, filters, grouping, inline edit, bulk bar), each with its own default columns and actions. Long-term, `/requests` can become the saved view "İnceleme bekleyen" (Needs review) here (open question 1).

---

## 0. What v1 does today (`docs/images/screens/requests-*`) and what changes

| v1 | Problem | v2 |
|---|---|---|
| Separate request table and timetable; no place shows "requested X, got Y, because Z" | The planner cross-checks Excel by hand | One row joins request, placement and reason; the inspector explains |
| Filters: one search box + "Status: All" + "Program: All" selects | Can't ask "evening Pharmacy classes on Monday after 17:30 that moved" | Token search + faceted filters (13 fields) + time window + saved views |
| Pastel status pills on every row, mono codes | Generic dashboard look | Glyph + word; system font; colour only for faculty dot and severity |
| The drawer is a modal over a blurred page with a big blue Save | Blocks the table; not Apple-like | Non-modal glass inspector; edits save in place with undo |
| Source shown as one muted line "Source row: …" | Provenance is the planner's main trust signal, and here it is an afterthought | A full **Kaynak** section: file · sheet · row, raw Excel row, cell comment |

## 1. References (Mobbin), with what we borrow

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| 1 | [Linear: saved view "High Priority Tasks" with Save to / Cancel / Save](https://mobbin.com/screens/610d34b6-6ad8-45ab-80fb-2107b31ed01e) | A view header with name, description, a **Save to Personal ▾ · Cancel · Save** bar that appears only when the view is modified; collapsible status groups with count and a per-group `+` | |
| 2 | [Linear: filter menu with property list + side panel](https://mobbin.com/screens/d1d26f7d-e1e5-490f-ab4f-c96dd12854c1) and [filter field list](https://mobbin.com/screens/ed670cda-0527-4716-a1a6-0159f12c4f42) | A type-ahead filter menu: "Add Filter…" field, then property list (Status, Assignee, Labels, Dates…) with submenus; "AI Filter" and "Advanced filter" entries at the top. Ours: a natural-language filter (TR/EN) plus an advanced builder. | |
| 3 | [Linear: display options](https://mobbin.com/screens/815793b1-5c75-43ac-94c7-93380781e337) | One **Görünüm** (Display) popover holding List/Board, Grouping, Sub-grouping, Ordering, toggles, and "Display properties" as toggle chips; "Reset · Set default for everyone" | |
| 4 | [Airtable: Group by picker](https://mobbin.com/screens/78b76ba8-be7a-4286-a991-abf82f444044) and [grouped grid with aggregates](https://mobbin.com/screens/7612f4c4-4104-4dbc-8e5f-579dde687f2b) | Group header showing the field name small above the value, count right, a per-group aggregate row ("Avg 53"); "Collapse all · Expand all"; "Add subgroup" | Heavy coloured group pills |
| 5 | [Airtable: row height menu](https://mobbin.com/screens/3c262023-056c-4329-af3c-3505a85f2d80) | Density as named heights (Short/Medium/Tall), which become Sıkı/Standart/Rahat; "Wrap headers" | |
| 6 | [Attio: sort and advanced-filter chips + count footer](https://mobbin.com/screens/f85654c3-a89c-444e-bdf4-7ba40c3118f4) | "Sorted by Last interaction" and "Advanced filter 3" as compact chips under the view name; a "3 count" footer; "+ Add calculation" per column footer, which becomes column aggregates | |
| 7 | [Attio: table + keyboard shortcuts panel](https://mobbin.com/screens/fa567c5a-616d-4991-88fc-e2a047b5fcfd) | A searchable shortcuts side panel grouped General / Record page / Table view (our `?` sheet); multi-value tag chips in cells | |
| 8 | [Attio: record page with Details side](https://mobbin.com/screens/ee14880a-1c0e-46e9-8ccc-5cb1ed1a58e5) | A right **Details** column of label/value pairs with "Show all values", and activity tabs. Becomes the inspector sections Talep / Yerleşim / Kaynak / Geçmiş. | |
| 9 | [Notion: selection bar replaces the header](https://mobbin.com/screens/f49ef73e-f5ea-4da3-b785-f9c768aaca1b) | On selection, a compact bar "2 selected · Role · Status · Person · Date · 🗑 · ⋯" takes the toolbar's place, so property actions are one click. This is our bulk bar. | |
| 10 | [Notion: sort popover](https://mobbin.com/screens/e57c782d-f578-4d24-ac76-4c5ef616f256) | Multi-sort rows (drag handle, field, direction, ✕) and "+ Add sort"; active sort as a chip "↑ Name ▾" | |
| 11 | [Shopify iOS: search with scope chips + counts, iOS 26 chrome](https://mobbin.com/screens/83a79099-6b71-454f-817e-a701eb23811e) | Mobile: a detached glass search circle next to the floating tab bar; scope chips with counts ("All 19 · Navigation 7"); result rows with status chips | |
| 12 | [Public iOS: filter sheet](https://mobbin.com/screens/ba40857a-9822-45af-9cc6-2f267f174cc4) | Mobile filter sheet: search on top, "Sort by" chips, grouped checkbox sections, floating capsules **Clear all** / **Apply filter** | |
| 13 | [Tripadvisor iOS: filter capsules + result count](https://mobbin.com/screens/79149ae3-242e-43b9-98d9-46acdc4b9ff1) | A horizontal row of filter capsules with chevrons ("Duration ▾ Language ▾ More Filters"), "973 Results · Featured ▾" | Promo banners |
| 14 | [Public iOS: agenda grouped by date](https://mobbin.com/screens/e44ca9c4-52c9-4504-9b6d-90513b4aa9b2) | Section headers by day, rows with a right-aligned time capsule, "‹ June · August ›" capsules at the bottom. Becomes the mobile "group by day" layout. | |
| 15 | [Deputy: banded groups with state badges](https://mobbin.com/screens/9915dbfc-159b-425c-a1be-e1fc81df62a8) | Small LOCKED/OPEN state badges inside items; a footer legend with counts | |
| 16 | Apple Numbers macOS 26 / iOS 26 (not on Mobbin; [HIG: Tables](https://developer.apple.com/design/human-interface-guidelines/tables), [HIG: Materials](https://developer.apple.com/design/human-interface-guidelines/materials)) | A plain opaque table with hairline rules; header and toolbar on glass; a right **Format/Organize** inspector; categories (group by) with collapsible summary rows; `⌘C` copies cells as tab-separated text | Spreadsheet-style cell borders on every cell |

## 2. Interaction patterns named

| Pattern | Where |
|---|---|
| **Saved views as tabs** with a modified-state Save bar (Linear #1, Notion) | top of the table |
| **Token search** (`fak:ecz gün:pzt saat:13:30-17:30`) with autocomplete, plus natural-language filter (TR/EN) | toolbar |
| **Faceted filter popovers** with live counts per value | filter chips |
| **Display popover** (group, sub-group, sort, columns, density in one place; Linear #3) | toolbar |
| **Sticky glass group headers** with aggregates (Airtable #4) | grouped body |
| **Inline cell edit** (`Enter`/`F2`, Excel habit) | editable columns |
| **Selection bar replaces toolbar** (Notion #9) | bulk |
| **Non-modal inspector** with request ↔ placement ↔ provenance | right |
| **Explain placement** (streamed) | inspector |
| **Copy/paste as TSV** (Numbers #16) | `⌘C`/`⌘V` with preview |

## 3. Information architecture and layout (desktop 1440)

```
┌ shell rail ┬──────────────────────────── TABLE CANVAS (opaque) ───────────────────────────────┬─ INSPECTOR (glass, 400) ─┐
│            │ Tüm dersler                       2026 Bahar · Run #42 ▾       [Dersler | Sınavlar]   │ BME 419 §1          ‹ › ✕│
│            │ ╭ views ────────────────────────────────────────────────────────────────────────╮  │ Biyomedikal · 3. sınıf   │
│            │ │ Tümü 1.529 · Yerleşmeyen 21 · Sorunlu 7 · Değişen 17 · Akşam 96 · + Görünüm ▾ │  │ ● Yerleşti · Kilitli     │
│            │ ╰───────────────────────────────────────────────────────────────────────────────╯  │ [Takvimde aç] [Açıkla]   │
│            │ ╭ glass toolbar capsule ──────────────────────────────────────────────────────────╮  │ ── Talep ─────────────── │
│            │ │ ⌕ fak:ecz gün:pzt …        Filtre +   Görünüm ▾   Dışa aktar ▾   ⋯              │  │ İstenen: "C 301 veya …" │
│            │ ╰───────────────────────────────────────────────────────────────────────────────╯  │  → [C 301] [C 302]       │
│            │ Fakülte: Eczacılık ✕  Gün: Pzt, Sal ✕  Saat: 13:30–17:30 (örtüşen) ✕  Temizle     │  Çar 13:30–15:50 · 1–14  │
│            │ Görünüm değişti · Kaydet · Farklı kaydet · Sıfırla                                 │ ── Yerleşim (Run #42) ── │
│            │ ┌──┬────────┬──────────────┬──────────┬───┬──────────────┬────────┬─────┬─────┐  │  A 204 · 102/156 (%65)   │
│            │ │☐ │Ders    │Program       │Hoca      │Sın│Yerleşim      │İstenen │Öğr. │Sorun│  │  ✓ bina ✓ kapasite …    │
│            │ ├──┴────────┴──────────────┴──────────┴───┴──────────────┴────────┴─────┴─────┤  │ ── Kaynak ────────────── │
│            │ │▾ ● Eczacılık Fakültesi         184 ders · Σ 6.204 öğr · %97 yerleşti · 2 ⚠  │  │  Bahar … v5.xlsx         │
│            │ │  ▾ Eczacılık (İÖ)              42                                             │  │  Sayfa1 · satır 412      │
│            │ │   ECZ 112 §1  Eczacılık 1   Doç. Dr. …  1  Pzt 18:00–19:30 · B 204  B blok  64 │  │  [Satırı göster]         │
│            │ │   …                                                                          │  │ ── Geçmiş ────────────── │
│            │ │▸ ● Mühendislik Fakültesi       212 ders · …                                   │  │  #40 A 102 → #42 A 204   │
│            │ └──────────────────────────────────────────────────────────────────────────────┘  │                          │
│            │ 212 / 1.529 ders · 6 seçili · Σ öğrenci 6.204                         Yoğunluk ▾  │                          │
└────────────┴──────────────────────────────────────────────────────────────────────────────────┴──────────────────────────┘
```
- The **title row** is not glass: "Tüm dersler" at 22/28 semibold, then term + run picker and the kind segmented control **Dersler | Sınavlar**. Changing the run re-joins placements without refetching requests.
- **View tabs** (§6): a horizontal list of saved views with counts; overflow goes into "+ Görünüm ▾".
- **Toolbar** is one glass capsule (`--mat-chrome`, 44 px) with search, Filtre +, Görünüm (Display), Dışa aktar, ⋯ (Sütunlar, Yoğunluk, Kopyala, Yazdır).
- The **filter chips row** (opaque) appears only when filters are active.
- The **modified bar** "Görünüm değişti · Kaydet · Farklı kaydet · Sıfırla" appears only when the current view differs from its saved state (Linear #1).
- **Table**: opaque content surface. The header row and group headers are sticky on `--mat-thick` with the hard edge from motion pattern §15 (rule G1: only thick/chrome over content; calendar.md §8.2).
- **Footer** (opaque, 32 px): "212 / 1.529 ders · 6 seçili · Σ öğrenci 6.204" plus column aggregates when "Hesap" (calculation) is set on a column (Attio #6).
- **Inspector**: 400 px non-modal `GlassPanel`; docked at ≥ 1600, overlay at 1280–1599.

## 4. Row model (`ClassRowV2`)

```ts
type ClassRowV2 = {
  id: number; kind: "meeting" | "exam";
  // request (from meeting_requests / sections)
  courseCode: string; courseName: string; section: string | null;     // "BME 419", "Biyomedikal Sinyal…", "1"
  facultyId: number; facultyName: string; facultySlot: 1|2|3|4|5|6|7|8;
  programId: number | null; programName: string | null; isEvening: boolean; classYears: number[];
  instructors: { id?: number; name: string }[];
  enrolment: number | null; mode: "F2F"|"HYBRID"|"ONLINE"|"UZEM"|"ASYNC"|"HOSPITAL"|"SIMULATION"|"OTHER"; needsRoom: boolean;
  req: { day: number | null; days: number[]; startPeriod: number | null; endPeriod: number | null; weeks: number[];
         roomText: string | null; roomIds: number[]; building: string | null; tags: string[]; capacity: number | null;
         flexibleDay: boolean; status: "NEW"|"PARSED"|"NEEDS_REVIEW"|"LOCKED"; warnings: string[]; notes: string | null };
  // placement in the selected run (null = unplaced, or no run)
  placement: null | { assignmentIds: number[]; day: number; startPeriod: number; endPeriod: number; roomIds: number[];
         roomCodes: string[]; capacity: number; weeksPlaced: number[]; locked: boolean; origin: "SOLVER"|"MANUAL"|"IMPORT" };
  placementStatus: "placed" | "partial" | "unplaced" | "conflict" | "no_room_needed" | "no_run";
  issues: { severity: "hard"|"soft"; code: string; text: { tr: string; en: string } }[];
  changed: { field: string; from: unknown; to: unknown; source: "import"|"manual"|"run" }[];   // vs imported snapshot / vs compare run
  provenance: { importJobId?: number; fileName?: string; sheet?: string; row?: number; rawRow?: Record<string, unknown>; cellComment?: string };
  updatedAt: string; updatedBy?: string;
};
```
Built by the proposed `GET /terms/{term_id}/classes?run_id=` (§16), or, until it exists, by joining `GET /terms/{term_id}/studio/classes` (planner) or `GET /requests/meetings?limit=2000` (viewer) with `GET /runs/{run_id}/assignments` on `meeting_request_id` in the worker.

## 5. Columns (column chooser)

`Görünüm › Sütunlar` (also right-click a header). Columns can be toggled, dragged to reorder, and resized (double-click a divider auto-fits). The first two (☐, Ders) are pinned at ≥ 1280. Header labels are sentence case, 12/16 w600 `--fg-muted`; numbers are right-aligned.

| Column (TR / EN) | Cell rendering | Default | Editable (§8) |
|---|---|---|---|
| ☐ | checkbox; visible on row hover/focus, on selected rows, or in select mode | ✓ | — |
| Durum / Status | placement glyph + word: ● Yerleşti · ◐ Kısmi 12/14 · ○ Yerleşmedi · ▲ Çakışma · — Oda gerekmez | ✓ | — |
| Ders / Course | **BME 419** (w600) + "§1" (`--fg-muted`) on line 1; name truncated on line 2 at Standard density and above | ✓ pinned | — |
| Fakülte / Faculty | faculty colour dot (8 px) + short name | | — |
| Program | "Biyomedikal Müh." + an "İÖ" text capsule for evening | ✓ | — |
| Sınıf / Year | "3" or "1–2" | ✓ | — |
| Öğretim elemanı / Instructor | first name + "+1" | ✓ | — |
| Öğrenci / Students | right-aligned "102" | ✓ | number |
| Mod / Mode | "Yüz yüze", "Hibrit", "Online"… | | select |
| İstenen zaman / Requested time | "Çar 13:30–15:50" | | day + period range |
| Haftalar / Weeks | "1–14", "1–7", "1,3,5…" + a 14-tick micro-pattern on hover | | week picker |
| İstenen oda / Requested room | chips (max 2 + "+n"): `C 301` `C 302` or `≥ 72` `C blok`; raw text in tooltip | ✓ | chip editor (requests-inbox §3.4) |
| Yerleşim / Placement | "Çar 13:30–15:50 · A 204" (room code w600); "—" when unplaced; a `↔` glyph if it differs from the request | ✓ | room combobox / time (through Move) |
| Uyum / Fit | "102/156 · %65"; amber when > 100 % or < 30 % | ✓ | — |
| Sorunlar / Issues | severity glyph + count + first reason ("▲ 1 · Hoca çakışması") | ✓ | — |
| Kilit / Lock | lock glyph button (pinned = pin glyph) | ✓ | toggle |
| Değişti / Changed | 6 px amber dot + field names in tooltip ("Öğrenci, Oda") | ✓ | revert in the inspector |
| Talep durumu / Request status | NEW · PARSED · NEEDS_REVIEW · LOCKED (glyph + word) | | select |
| Kaynak / Source | "v5.xlsx · 412" (file short name · row) | | — |
| Not / Notes | first line, muted | | text |
| Güncellendi / Updated | "2 sa önce" (relative; absolute in tooltip) | | — |
| Plana dahil / In plan (studio draft) | switch (planner only; deep-links into the Studio) | | toggle |

Exam kind columns: ☐ · Durum · Ders · Programlar (merged chip "3 program · 70 öğrenci") · Tarih · Saat · Öğrenci · Oda sayısı · İstenen yer · Yerleşim (multi-room "A 101 + A 102") · Uyum (exam capacity) · Sorunlar · Kilit · Kaynak.

## 6. Saved views

- **System views** (always present, non-deletable, reorderable): Tümü (All) · Yerleşmeyenler (Unplaced) · Sorunlular (Has issues) · Değişenler (Changed) · Akşam / İÖ (Evening) · TIP odaları · Odasız / online (No room needed) · İnceleme bekleyen (Needs review). Each tab shows a live count.
- **Personal** and **shared** views ("Herkesle paylaş", ADMIN/PLANNER). A view stores: kind, filters (as a filter AST, not row ids, so it survives re-imports), sort (multi), group + sub-group, collapsed groups, visible columns + order + widths, density, and the compare run (optional).
- **Modified state**: changing anything shows the modified bar. "Kaydet" (save) overwrites (owner only), "Farklı kaydet" (save as) prompts for a name, "Sıfırla" (reset) reverts. Switching views with unsaved changes keeps them in memory per view until reload (no nag dialog).
- URL mirrors the active view id plus a compact diff (`/classes?view=unplaced&f=…`), so any state is shareable.
- Storage: server-side per user (backend needed, §16), with a `localStorage` fallback that syncs once the endpoint exists.

## 7. Filtering

### 7.1 Fields
| Field (TR / EN) | Control | Notes |
|---|---|---|
| Fakülte / Faculty | multi-select with colour dots + counts | |
| Program / Programme | multi-select grouped by faculty, searchable, "İÖ" marker | |
| Sınıf / Year | 0–6 toggle chips | `class_years` may hold several |
| Öğretim elemanı / Instructor | searchable multi-select (normalised names, title-stripped) | |
| Bina / Building | A B C D | applies to **placement** by default; a switch "İstenen / Yerleşen" (requested/placed) |
| Oda / Room | room combobox (code, capacity, tags) | same requested/placed switch |
| Gün / Day | Pzt…Paz toggle chips | requested or placed (same switch) |
| Saat aralığı / Time window | dual-handle range over 08:30–22:50 snapping to period starts, with mode **Örtüşen / Tamamen içinde** (overlapping / fully within) | "after 17:30" preset = İÖ |
| Mod / Mode | multi-select | |
| Durum / Status | request status (NEW/PARSED/NEEDS_REVIEW/LOCKED) and placement status (§5) as two groups | |
| Yerleşti mi / Placed | Yerleşti · Kısmi · Yerleşmedi · Oda gerekmez | |
| Sorun var / Has issue | any / hard / soft, plus issue-type checkboxes (Kapasite, Hoca çakışması, Program çakışması, TIP, PC, Bina tercihi, Hafta) | |
| Değişti / Changed | any · vs imported file · manual edits · vs compare run (moved) | |
| Kilitli / Locked, Sabitlenmiş / Pinned | booleans | |
| Kaynak / Source | import job (file) | |

### 7.2 Ways to filter (all produce the same filter AST)
1. **Token search** in the toolbar: plain text matches code, name, instructor and room, Turkish-aware (casefold İ/ı, diacritic-insensitive: `sube` finds `şube`). Typed tokens become chips on space: `fak:` `prog:` `sınıf:` `hoca:` `bina:` `oda:` `gün:` `saat:13:30-17:30` `mod:` `durum:` `yerleşmedi` `sorunlu` `değişti` `kilitli` (English aliases `fac: prog: year: instr: bldg: room: day: time: mode: status: unplaced issues changed locked`). Autocomplete lists matching values with counts.
2. **Filtre +** popover (Linear #2): a type-ahead field list, then a value list with **facet counts** computed against the other active filters ("Pazartesi 212 · Salı 198 …"), with "Temizle · 212 dersi göster".
3. **Natural language** (first row in the Filtre + list, "Cümleyle filtrele" / "Filter with a sentence"): "eczacılık pazartesi 17:30 sonrası taşınanlar" becomes chips shown for confirmation before they apply. Uses the AI catalogue; it never mutates data. Needs a small endpoint (§16); hidden when AI is off.
4. **Quick facets from cells**: `⌥`-click any cell value adds "= value"; `⌥⇧`-click adds "≠ value".
- Active filters render as removable chips ("Gün: Pzt, Sal ✕"); clicking a chip reopens its popover. `Esc` in the search clears text, not chips.
- The result count is announced politely ("212 ders gösteriliyor"), debounced 500 ms.

## 8. Grouping, sorting, inline edit

### 8.1 Grouping (Görünüm › Grupla)
- Group by: Fakülte · Program · Gün · Oda · Öğretim elemanı · Bina · Durum · Sorun türü · Sınıf; **sub-group** one level (e.g. Fakülte › Program, Gün › Oda).
- **Glass group header** (sticky, 36 px; sub-group 32 px, stacked under its parent): chevron, faculty dot (when grouped by faculty/programme), name (w600), count, and right-aligned aggregates `Σ 6.204 öğrenci · %97 yerleşti · 2 ▲`. On hover: "Grubu seç" (select group) and "Takvimde göster" (show in calendar). The group's field name appears small above the value the first time, as in Airtable #4.
- Collapse: click the chevron or press `←` on a header; `⌥`-click collapses or expands all at that level; `[` / `]` collapse/expand all. Collapsed state is saved in the view.
- Empty groups are hidden (Linear option "Show empty groups" off).
- Sorting within groups follows the sort; group order is natural (faculty by name; day Pzt→Paz; room by building then code; status by severity).

### 8.2 Sorting
Click a header to cycle asc/desc/none. `⇧`-click adds a secondary sort. The Sırala popover (Notion #10) lists multi-sorts with drag handles. Default: Durum (issues first), then Gün, then start period, then Ders. Turkish collation (`Intl.Collator('tr')`).

### 8.3 Inline edit
- Enter edit: double-click, `Enter`, or `F2` (Excel habit). `Esc` cancels; `Enter` saves and moves down; `Tab` saves and moves right.
- Request fields (Öğrenci, Mod, İstenen zaman, Haftalar, İstenen oda, Not, Talep durumu) save to the request (`PUT /requests/meetings/{id}`, or `PUT /studio/meetings/bulk` for draft-aware edits). The cell gets the Değişti dot and a "Sonraki çalıştırmada etkili" tooltip.
- **Placement** fields (Yerleşim room/time) go through the calendar's Move flow: the editor shows live validity against the index ("✓ A 101 boş · 58 koltuk", "✕ ENG 102 ile çakışıyor"), then the scope radio (Tüm haftalar / Sadece bu hafta / Bu haftadan itibaren), then `POST /runs/{run_id}/assignments/{aid}/move`.
- Capacity check inline (requests-inbox pattern): "A 103: 47 koltuk, bu ders 60 öğrenci", with the fix link "≥ 60 koltuklu oda seç" (pick a room with 60+ seats). Backed by `POST /requests/meetings/{mr_id}/check-room`.
- Optimistic save; the cell shows a 10 px spinner in the corner; failure rolls back, the cell gets a red underline, and a toast offers "Tekrar dene". Draft 409 (`If-Match`): "Bu ders başka biri tarafından değiştirildi · Yenile" (someone else changed this class; refresh).
- **Paste** (`⌘V`) a vertical range from Excel into a column of selected rows. A preview popover ("24 dersin öğrenci sayısı değişecek", 24 classes' student counts will change) leads to Uygula (apply), as one undoable bulk edit (studio method h).

## 9. Inspector (shared `ClassInspector`)

Non-modal glass panel (400 px; calendar.md §5.3 at 360 px). `‹ ›` and `J`/`K` step through rows in the current sort. It follows keyboard focus when "Odakla senkronize" (sync with focus) is on, which is the default.

1. **Header**: faculty bar · **BME 419 §1** (17/22) · course name · programme · year. Status line: "● Yerleşti · Kilitli" or "○ Yerleşmedi: kapasiteye uygun boş oda yok" (unplaced: no free room with enough capacity). Actions: **Takvimde aç** (opens `/timetable?lens=week&subject=room:…&sel=…`) · **Yerleşimi açıkla** · Kilitle · ⋯ (Sabitle…, Kurala dönüştür, Sohbette aç, Bağlantıyı kopyala).
2. **Talep / Request (as submitted, then as understood)**: the raw requested-room text in a muted quote ("C 301 veya C 302"), with parsed chips below it (AI-suggested chips dashed until accepted). Day/time, weeks, enrolment, mode, flexible day, notes. Parse warnings in amber. All editable (§8.3).
3. **Yerleşim / Placement (Run #42)**: room(s) with capacity and fit bar ("102 / 156 · %65"), day/time, weeks placed as a 14-square pattern (filled = placed), lock state, origin (Çözücü / Elle / İçe aktarım). The **check list** shows requested building, capacity fit, tags, instructor free, cohort free, same room all weeks, each as ✓/✕/– with one line of text. Issues with the diagnosis "Düzelt" (fix) action (`POST /runs/{run_id}/diagnoses/{idx}/apply`). **Across runs**: "Run #40: A 102 · Run #41: A 204 · Run #42: A 204 (kilitli)".
4. **Açıklama / Explanation** (after pressing **Yerleşimi açıkla**): streamed text (beautifului Streaming Text) with sections *Neden bu oda* (why this room), *Değerlendirilen alternatifler* (alternatives considered: "A 207 120 koltuk: Çarşamba P8 dolu"), *Taşırsanız* (if you move it: what breaks). A footer shows the source ("Model" or "Şablon", from `ExplainOut.source`), "Yeniden oluştur" (regenerate), and copy. Loading: "Yerleşim inceleniyor…" with the Thinking indicator (≤ 10 s typical); cancellable. Error: "Açıklama alınamadı · Tekrar dene"; the deterministic check list stays above, so the user is never left with nothing. Until the per-assignment endpoint exists, the button opens chat with the prefilled question "BME 419 §1 neden A 204'te?" (`POST /runs/{run_id}/chat`).
5. **Kaynak / Provenance**: "Bahar Derslik Planlama Listesi v5.xlsx · Sayfa1 · satır 412 · içe aktarım 2 Ekim, Fatih Demir". **Satırı göster** expands the raw Excel row as label/value pairs with the original Turkish headers (Derslik Talebi, Dersin Günü, Kesinleşen Derslik…), monospace-free, with empty values shown as "—". **Dosyayı indir** uses `GET /imports/{job_id}/file`. If the row came from the weekly grid, the cell comment shows here ("23 şubat dahil a 206 a geçecek").
6. **Geçmiş / History**: import → parse → edits (field, from → to, who, when, "Geri al") → placements per run.

Multi-selection shows a summary ("6 ders · 412 öğrenci · 3 bina · 2 sorunlu") with bulk actions instead of a single record.

## 10. Bulk actions

- Any selection replaces the toolbar capsule with the **selection bar** (Notion #9; glass, same position, 180 ms cross-fade; reduced motion: instant): "**31 seçili** · Kilitle · Sabitle… · Taşı… · Durum ▾ · Öğrenci… · Bina tercihi… · Kurala dönüştür · Takvimde göster · Dışa aktar · ⋯ (Yerleşimi kaldır, Plandan çıkar) · ✕".
- Selection: checkbox, `X`, `⇧`-click or `⇧↑↓` for range, `⌘A` (all filtered rows, not just the visible part; the bar says "1.529 dersin tümü seçili"), group header "Grubu seç".
- **Taşı…** (move) opens a dialog: target room / day / shift by ±n periods, scope; dry-run preview listing "28 uygun · 3 çakışma" (28 fit, 3 clash) with per-row reasons; then "28'ini taşı" (move the 28). Uses bulk-move (backend needed; sequential fallback).
- **Kurala dönüştür** (make a rule) opens the Studio rule builder with "applies to" = the selection (generator-studio §3.3.2).
- **Takvimde göster** (show in calendar) opens `/timetable` with these ids selected (session hand-off) and Board · Gün on the first one's day.
- Confirmation only for destructive or large actions: "Yerleşimi kaldır", and any action on more than 100 rows. Partial failures are summarised in a toast: "28 kilitlendi, 3 atlandı (çakışma) · Ayrıntı · Geri al" (28 locked, 3 skipped for clashes). Every bulk action is one undo entry.

## 11. Export

`Dışa aktar ▾` (Export):
- **Bu görünüm (.xlsx)**: visible columns in their order, current filters/sort; grouping becomes Excel outline levels with subtotal rows. Sheet name = view name.
- **Planlama listesi biçiminde (.xlsx)**: the original 26-column planning-list shape with **Derslik Planlama - Kesinleşen Derslik** filled from the placement. This is a round-trip to the planner's own file format, which is what he sends to faculties.
- **CSV** (UTF-8 BOM so Excel opens Turkish characters correctly).
- **Takvim (.ics)** for one instructor, room or cohort (enabled when the view filters to one of them).
- Server-side preferred (§16); the dialog shows "1.529 satır · ~210 KB" and a progress toast for large exports.

## 12. States

| State | Treatment (TR copy) |
|---|---|
| Loading (first) | Title, tabs and toolbar render immediately. The table shows its header and 10 static placeholder rows (hairlines with 30 %-wide muted bars, no shimmer). The footer reads "Yükleniyor…". |
| Loaded | footer "1.529 ders" |
| Empty: no data for term | "Bu dönem için ders yok. Planlama listesini içe aktararak başlayın." [İçe aktar] |
| Empty: no run yet | The table works (request columns). Placement columns show "—", and a top banner reads "Henüz yerleşim yok · Program oluştur" (no placements yet · generate a timetable). |
| Empty: filters match nothing | "Bu filtrelere uyan ders yok." [Filtreleri temizle] + the active chips |
| Empty: system view is empty | Positive and factual, no exclamation: "Yerleşmeyen ders yok." (no unplaced classes) |
| Error: load | Inline banner "Dersler yüklenemedi. [Tekrar dene]". The cached data stays visible if present. |
| Error: cell save | the cell reverts + red underline + toast "Kaydedilemedi: {neden} · Tekrar dene" |
| Conflict (draft version) | "Bu ders başka biri tarafından değiştirildi · Yenile" |
| Stale run | "Yeni çalıştırma hazır: Run #43 · Yerleşimleri güncelle" (re-joins placements) |
| Read-only (viewer) | editing affordances hidden; the selection bar offers only Dışa aktar / Takvimde göster |
| Offline | toolbar shows "Çevrimdışı"; edits are queued with "3 değişiklik bekliyor" |
| Explain running / failed | §9.4 |

## 13. Mobile (360–430): cards

Wireframe: `wireframes/all-classes-mobile.svg`.
- **Nav**: large title "Tüm dersler" with the subtitle "1.529 ders · Run #42", collapsing on scroll. Glass circle buttons top-right: Filtre (with a badge for the active filter count) and ⋯ (Grupla, Sırala, Görünümler, Dışa aktar).
- **Scope chips** (horizontally scrollable, with counts; Shopify #11) = saved views: "Tümü 1.529 · Yerleşmeyen 21 · Sorunlu 7 · Değişen 17 · Akşam 96".
- **Search**: the detached glass search circle at the bottom next to the shell's tab bar expands into a field on tap (iOS 26 idiom, Shopify #11). Same token grammar, with token suggestions as chips above the keyboard.
- **Group headers**: inset-grouped section headers on `--mat-thick` (motion pattern §15), sticky: "Eczacılık Fakültesi · 184".
- **Card** (opaque, inset grouped list cell, 12 px radius, 16 px padding):
  ```
  ▌ BME 419 §1                                ▲ 1
  ▌ Biyomedikal Müh. · 3. sınıf
  ▌ Çar 13:30–15:50 · A 204 · 102/156
  ▌ Kilitli · Değişti
  ```
  Line 1: faculty bar, code (w600), issue glyph + count right. Line 2: programme · year (`--fg-muted`). Line 3: placement, or "Yerleşmedi · İstenen: C 301" in amber. Line 4 (only when relevant): state words. Minimum height 72; whole-card tap target.
- **Swipe** (beUI Swipeable List): right reveals **Kilitle**; left reveals **Açıkla** and **Takvimde**. Every swipe action also lives in the card's long-press menu.
- **Select mode**: "Seç" in the ⋯ menu or a long-press on a card. Checkboxes slide in (180 ms; reduced: instant). The **bulk toolbar** replaces the tab bar as a glass bottom bar: "6 seçili · Kilitle · Taşı · Dışa aktar · ⋯".
- **Filter sheet** (Public #12): a glass bottom sheet (large detent) with search, "Sırala" chips, sections per field (counts on each value), time-window slider, and the floating capsules **Temizle** · **212 dersi göster**.
- **Inspector**: bottom sheet (medium/large detents) with the same sections, collapsed as an accordion; editing happens only in the sheet (no inline cell edit on phones).
- Group by day uses the Public #14 layout: day headers and a right-aligned time capsule per card.

## 14. Responsive and density

| Width | Layout |
|---|---|
| 360–767 | cards (§13) |
| 768–1179 | table with ☐ · Durum · Ders · Program · Yerleşim · Sorunlar (others hidden by default, still selectable in Sütunlar); horizontal scroll for more; inspector = right overlay sheet (420 px) in landscape, bottom sheet in portrait; filters as a popover from a single "Filtre" capsule |
| 1280–1599 | full default columns (§5); inspector overlays; sticky ☐ + Ders |
| 1600–2559 | inspector docked; + Fakülte, Mod, Haftalar, Kaynak columns by default |
| ≥ 2560 (4K) | inspector docked + an optional **Önizleme** (preview) pane (`⋯ › Takvim önizlemesi`): a compact calendar Week lens for the selected row's room, so a placement can be judged without leaving the table. All columns fit with no horizontal scroll at standard density. Type does not scale. |

Density (Görünüm › Yoğunluk, Airtable #5): **Sıkı** 32 px rows (one line; pointer only) · **Standart** 44 px (two-line Ders cell) · **Rahat** 56 px. Persisted in the view.

## 15. Copy (TR / EN), key labels

| Key | TR | EN |
|---|---|---|
| page.title | Tüm dersler | All classes |
| kind | Dersler · Sınavlar | Classes · Exams |
| views.system | Tümü · Yerleşmeyenler · Sorunlular · Değişenler · Akşam (İÖ) · TIP odaları · Odasız / online · İnceleme bekleyen | All · Unplaced · Has issues · Changed · Evening · TIP rooms · No room / online · Needs review |
| views.modified | Görünüm değişti · Kaydet · Farklı kaydet · Sıfırla | View changed · Save · Save as · Reset |
| views.share | Herkesle paylaş | Share with everyone |
| toolbar | Ara · Filtre · Görünüm · Dışa aktar | Search · Filter · Display · Export |
| display | Grupla · Alt grup · Sırala · Sütunlar · Yoğunluk | Group · Sub-group · Sort · Columns · Density |
| filter.nl | Cümleyle filtrele | Filter with a sentence |
| filter.window | Saat aralığı · Örtüşen · Tamamen içinde | Time window · Overlapping · Fully within |
| filter.where | İstenen · Yerleşen | Requested · Placed |
| filter.apply | Temizle · {n} dersi göster | Clear · Show {n} classes |
| status.placement | Yerleşti · Kısmi · Yerleşmedi · Çakışma · Oda gerekmez | Placed · Partial · Unplaced · Conflict · No room needed |
| status.request | Yeni · Ayrıştırıldı · İnceleme bekliyor · Kilitli | New · Parsed · Needs review · Locked |
| cols | Ders · Program · Sınıf · Öğretim elemanı · Öğrenci · Mod · İstenen zaman · Haftalar · İstenen oda · Yerleşim · Uyum · Sorunlar · Kilit · Değişti · Kaynak · Not · Güncellendi | Course · Programme · Year · Instructor · Students · Mode · Requested time · Weeks · Requested room · Placement · Fit · Issues · Lock · Changed · Source · Notes · Updated |
| group.aggregate | {n} ders · Σ {s} öğrenci · %{p} yerleşti · {i} sorun | {n} classes · Σ {s} students · {p}% placed · {i} issues |
| bulk.bar | {n} seçili | {n} selected |
| bulk.actions | Kilitle · Sabitle… · Taşı… · Durum · Öğrenci… · Bina tercihi… · Kurala dönüştür · Takvimde göster · Dışa aktar · Yerleşimi kaldır | Lock · Pin… · Move… · Status · Students… · Preferred building… · Make a rule · Show in calendar · Export · Remove placement |
| bulk.result | {a} kilitlendi, {b} atlandı ({neden}) · Geri al | {a} locked, {b} skipped ({reason}) · Undo |
| inspector.sections | Talep · Yerleşim · Açıklama · Kaynak · Geçmiş | Request · Placement · Explanation · Source · History |
| inspector.openCal | Takvimde aç | Open in calendar |
| explain.button | Yerleşimi açıkla | Explain placement |
| explain.loading | Yerleşim inceleniyor… | Looking at this placement… |
| explain.sections | Neden bu oda · Değerlendirilen alternatifler · Taşırsanız | Why this room · Alternatives considered · If you move it |
| explain.error | Açıklama alınamadı · Tekrar dene | Couldn't get an explanation · Try again |
| source.line | {dosya} · {sayfa} · satır {n} | {file} · {sheet} · row {n} |
| source.showRow | Satırı göster · Dosyayı indir | Show row · Download file |
| edit.nextRun | Sonraki çalıştırmada etkili | Takes effect on the next run |
| edit.capacity | {oda}: {k} koltuk, bu ders {s} öğrenci | {room}: {k} seats, this class has {s} students |
| export | Bu görünüm (.xlsx) · Planlama listesi biçiminde (.xlsx) · CSV · Takvim (.ics) | This view (.xlsx) · As planning list (.xlsx) · CSV · Calendar (.ics) |
| empty.term | Bu dönem için ders yok. Planlama listesini içe aktararak başlayın. | No classes for this term yet. Import a planning list to start. |
| empty.filtered | Bu filtrelere uyan ders yok. | No classes match these filters. |
| empty.unplaced | Yerleşmeyen ders yok. | No unplaced classes. |
| error.load | Dersler yüklenemedi. | Couldn't load classes. |
| count.footer | {shown} / {total} ders · {sel} seçili | {shown} of {total} classes · {sel} selected |

## 16. API endpoints (prefix `/api/v1`)

**Existing**
| Endpoint | Use |
|---|---|
| `GET /terms`, `GET /terms/{term_id}/weeks` | term picker, week labels |
| `GET /runs?…`, `GET /runs/{run_id}`, `GET /runs/{run_id}/assignments` | run picker; placements joined by `meeting_request_id` / `exam_request_id` |
| `GET /terms/{term_id}/studio/classes?kind=&faculty_id=&program_id=&class_year=&day=&building=&mode=&status=&changed=&included=&needs_room=&pinned=&rule_id=&ids=&q=&limit≤2000` | request rows with changed fields, pins and the include flag (PLANNER; draft-bound) |
| `GET /requests/meetings?term_id=&status=&needs_room=&day=&program_id=&search=&limit≤2000`, `GET /requests/exams` | request rows for VIEWER, and exams |
| `GET /requests/stats` | system-view counts before the worker finishes |
| `PUT /requests/meetings/{mr_id}`, `PUT /requests/exams/{ex_id}` | inline edit of request fields |
| `POST /requests/meetings/{mr_id}/check-room` | inline capacity/tag check |
| `PUT /studio/meetings/bulk`, `POST /studio/meetings/{mr_id}/revert`, `POST /studio/meetings/revert` | bulk edits; revert to imported |
| `POST /runs/{run_id}/assignments/{aid}/move`, `POST /runs/{run_id}/assignments/{aid}/lock` | placement edits, lock |
| `POST /runs/{run_id}/diagnoses/{idx}/apply` | "Düzelt" (fix) on issues |
| `POST /constraints` (`room_pin`, `fixed_time`, …) | Sabitle (pin), Kurala dönüştür (make a rule) |
| `POST /runs/{run_id}/chat` | interim "Yerleşimi açıkla" (explain placement) and "Sohbette aç" (open in chat) |
| `POST /runs/{run_id}/explain` | run-level explanation (link from the footer) |
| `GET /faculties`, `GET /programs`, `GET /instructors`, `GET /rooms`, `GET /buildings` | filter values, room combobox |
| `GET /imports`, `GET /imports/{job_id}`, `GET /imports/{job_id}/file` | Kaynak filter values; provenance download |
| `GET /runs/{run_id}/export?format=xlsx\|csv\|ics\|crbs` | whole-run export (interim for "Bu görünüm") |
| `GET /runs/{run_id}/events` (SSE) | stale-run banner |

**Backend needed**
| Endpoint | Why |
|---|---|
| `GET /terms/{term_id}/classes?kind=&run_id=&compare_run_id=&…filters…&sort=&limit=&offset=` returning `ClassRowV2` (§4) | one read model for VIEWER and PLANNER, independent of the studio draft; adds `instructor_id`, `room_id` (requested/placed), `start_gte`/`end_lte` (time window with overlap mode), `placed`, `has_issue`, `issue_code`, `changed_since` |
| `GET /terms/{term_id}/classes/facets?…filters…` | facet counts when not computed client-side (phones) |
| `GET /terms/{term_id}/classes/{id}?run_id=` | full inspector payload: raw row, provenance, history across runs |
| `import_job_id` + `sheet_name` on `meeting_requests` / `exam_requests` | "file · sheet · row" provenance (today only `source_row_index` + `sections.source_row`) |
| `POST /runs/{run_id}/assignments/{aid}/explain` `{lang}` → `ExplainOut` (sections: why, alternatives, impact) [ai-engineer] | **Yerleşimi açıkla** (explain placement) |
| `POST /terms/{term_id}/classes/nl-filter` `{text, lang}` → filter AST [ai-engineer] | "Cümleyle filtrele" (filter with a sentence) |
| `POST /runs/{run_id}/assignments/bulk-move` `{moves, atomic, dry_run}` and `POST /runs/{run_id}/assignments` (place unplaced) | bulk Taşı… (move), placement from the table |
| `GET/POST/PUT/DELETE /views?surface=classes\|calendar` (per user; `shared` flag; ADMIN/PLANNER may share) | saved views (also wanted by requests-inbox §3.5, which referenced a non-existent `PUT /settings/views`) |
| `GET /terms/{term_id}/classes/export?format=xlsx\|csv\|planning-list&columns=&group=&…filters…` | view-shaped and planning-list-shaped exports |
| `GET /audit?entity=meeting_request&id=` | Geçmiş (history) with who/when |

## 17. Keyboard map

| Keys | Action |
|---|---|
| `↑` `↓` or `J` `K` | Next / previous row (group headers included) |
| `←` `→` | Previous / next cell; on a group header, `←` collapses and `→` expands |
| `Home` / `End`, `⌘↑` / `⌘↓` | First/last cell in row; first/last row |
| `Enter` | Open the inspector (row); edit (cell, when the column is editable) |
| `F2` / `E` | Edit the focused cell |
| `Esc` | Cancel edit, then close popover, then clear selection, then close inspector |
| `Tab` / `⇧Tab` (editing) | Save and move right / left |
| `X` / `Space` | Toggle row selection |
| `⇧↑` `⇧↓` | Extend selection |
| `⌘A` | Select all filtered rows |
| `L` / `P` | Lock / Pin… |
| `O` | Open in calendar |
| `.` | Explain placement |
| `/` | Focus search · `F` open Filtre + · `V` view switcher (then type to find a view) · `G` Grupla · `⇧S` Sırala |
| `[` / `]` | Collapse / expand all groups |
| `⌥`-click value | Add "= value" filter; `⌥⇧`-click: "≠ value" |
| `⌘C` / `⌘V` | Copy selected cells as TSV / paste a column (with preview) |
| `⌘Z` / `⌘⇧Z` | Undo / redo |
| `⌘S` | Save the view (when modified) |
| `⌘⇧E` | Export this view |
| `?` | Shortcut panel (Attio #7) |

## 18. Accessibility

- **Grid semantics**: ungrouped = `role="grid"`; grouped = `role="treegrid"` (APG). Group rows have `aria-level="1"` (sub-groups 2, data rows 2 or 3), `aria-expanded`, `aria-setsize`/`aria-posinset`. `aria-rowcount` is the total row count including group rows; virtualised rows carry `aria-rowindex`. Headers are buttons with `aria-sort`. One tab stop with roving focus; cell focus is visible (2 px `--focus`, 2 px offset, inset on edge cells).
- **Editing**: entering edit mode announces "düzenleniyor: Öğrenci, 102"; commit announces "kaydedildi"; failure goes to the assertive region.
- **Checkboxes**: `aria-label="BME 419 §1 seç"`. The hidden-until-hover checkbox is always present in the DOM and visible on focus.
- **Live regions**: polite for result counts (debounced 500 ms), selection count, bulk results and saved-view changes; assertive only for failed saves.
- **Status**: glyph + word everywhere (Durum, Sorunlar, Değişti tooltips mirrored in the inspector); faculty identity always includes the name; the colour dot is decorative (`aria-hidden`).
- **Contrast on glass**: the toolbar or selection bar is `--mat-chrome`; the sticky header, group headers, inspector and popovers are `--mat-thick`. Over the worst content scrolling underneath (saturated faculty hues, black/white), `--fg-muted` stays ≥ 5.49:1 / 5.06:1 on thick and ≥ 5.22:1 / 5.34:1 on chrome (light/dark; calendar.md §15). `--mat-regular` and thinner materials never sit over the table (rule G1). `node docs/design/v2/verify-contrast.mjs` gates the tokens. Reduced transparency, forced colours and the in-app setting switch to solid surfaces.
- **Touch**: rows ≥ 44 px on touch (cards ≥ 72). Swipe actions have menu equivalents. The filter sheet controls are ≥ 44 px.
- **Reflow**: below 768 px the table becomes cards (no two-dimensional scroll). On larger screens the table may scroll horizontally (data table exemption), with the sticky first column.
- **Language**: TR default, `Intl.Collator('tr')` sorting, `Intl.NumberFormat` (1.529 vs 1,529), Turkish casefold in search. Shortcuts are Latin letters present on Turkish Q/F layouts; matching uses `KeyboardEvent.code` for `[ ] . /`.

## 19. Performance

- **Volume**: ≤ 2,000 rows (Bahar 1,529 meetings; Final 926 exams) × ~24 columns.
- **One fetch, worker-side query**: rows plus placements are fetched once per (term, kind, run). A Web Worker holds the rows and runs filter, facet counts, multi-sort (`Intl.Collator('tr')`) and grouping. Each query takes < 10 ms for 2,000 rows and returns a flattened list of `{type:"group"|"row", id, depth}`. The main thread renders only visible rows.
- **Virtualisation**: `@tanstack/react-virtual` over the flattened list (group headers are items; sticky headers via `rangeExtractor` keeping the active group header mounted). Overscan 10; fixed row heights per density (32/44/56), so measurement is not needed except in mobile cards (`measureElement`).
- **Columns are not virtualised** (≤ 24; at 4K all fit). Sticky columns use CSS `position: sticky`.
- **Rendering**: rows are `React.memo` keyed on `id + version`; cell editors mount in a portal only when editing; tooltips use a single shared floating element.
- **Mutations**: optimistic updates patch the worker's row and re-run the current query (incremental: only affected groups' aggregates change).
- **Glass**: at most 4 `backdrop-filter` surfaces (toolbar or selection bar, sticky header, active sticky group header, inspector); the sticky group header blur is skipped while scrolling fast (velocity > 2,000 px/s), then restored.
- **Budgets**: first rows ≤ 600 ms after data; filter keystroke to repaint ≤ 50 ms; scroll at 60 fps on a 2020 integrated-GPU laptop.

## 20. Components (mapped to the glass-system imports)

| Need | Component | Source · licence (checked 2026-10-08) |
|---|---|---|
| Table engine | TanStack Table v8 (installed) | MIT |
| Virtualiser | `@tanstack/react-virtual` (installed) | MIT |
| Table primitives, Checkbox, Popover, Command (filter menu, ⌘K), Select, DropdownMenu, ContextMenu, Tabs (view tabs), Sheet, Dialog, Tooltip, Badge, Slider (time window) | shadcn/ui (most installed; add `context-menu`) | MIT |
| Glass toolbar capsule, glass panel (inspector), glass group header, glass selection bar, solid fallback | `GlassCapsule`, `GlassPanel`, `GlassStickyHeader` from **liquid-glass.md** | glass-system agent (shadcn-based, MIT) |
| Chip-in-cell rendering (requested rooms, programmes) | beautifului **Records Table** | https://beautifului.dev · MIT (© 2026 Shane Levine; licence page checked) |
| Quick status-chip filtering for system views | beautifului **Filter Table** | MIT |
| Changes vs imported (inspector Geçmiş, "Review changes") | beautifului **Diff Table** | MIT |
| Selection bar | beautifului **Selection Actions** (re-skinned on `GlassCapsule`) | MIT |
| Explain placement (stream + thinking) | beautifului **Streaming Text** + **Thinking** | MIT |
| Fix suggestions | beautifului **Recommendation Card** | MIT |
| Token search with empty state | beautifului **Search** (command search) as a reference, on shadcn Command | MIT |
| Mobile bottom sheets (inspector, filters) | beUI **Bottom Sheet** | https://beui.dev · MIT (public library; Pro separate) |
| Mobile swipe actions | beUI **Swipeable List** (`npx shadcn add @beui/swipeable-list`) | MIT |
| Segmented controls (kind, density) | beUI **Tabs** (segment style) via `GlassSegmented` | MIT |
| Group aggregates as tiny bars (optional, ≥ 1600 only) | evilcharts **Bar chart** (Recharts) | https://evilcharts.com · MIT (© 2026 Gurbinder) |
| Toasts with undo | sonner (installed) | MIT |
| URL state | `nuqs` | MIT |
| Undo stack, view state | `zustand` (installed) | MIT |
| In-house | `ClassTable`, `ClassCard`, `FilterTokenInput`, `FacetPopover`, `TimeWindowSlider`, `ViewTabs`, `DisplayPopover`, `ColumnChooser`, `ClassInspector` (shared with calendar), `ExportDialog` | ours |

No code from kobra, reverseui, Kinetics or transitions.dev (licences; tokens.md §9).

## 21. Anti-AI-look checklist (all classes)

1. ☐ No KPI-card row above the table; counts live in the view tabs and the footer.
2. ☐ No pastel pill for every status. Use glyph + word; colour only for the faculty dot and issue severity.
3. ☐ No initials-in-circle avatars for instructors; plain names.
4. ☐ No monospace codes; `tabular-nums` for numbers; numbers right-aligned.
5. ☐ No zebra stripes and no full cell borders; hairline row separators at 8 % alpha; row hover is a 4 % tint (no lift, no shadow).
6. ☐ Header labels in sentence case at w600 `--fg-muted`, not tracked ALL CAPS grey.
7. ☐ The toolbar is one glass capsule, not a row of identical outlined buttons; secondary actions live in Görünüm/⋯.
8. ☐ No pagination footer ("Showing 1–25 of 1,529"); a virtualised list plus a count.
9. ☐ Empty values render as "—" in `--fg-subtle`, never "N/A", "null" or "0" placeholders.
10. ☐ Checkboxes appear on hover/focus/selection only (Linear), so there is no permanent checkbox column noise.
11. ☐ Group headers are glass strips with text aggregates, not coloured banners.
12. ☐ No sparkles or gradient "AI" buttons; Explain is a plain text button with a speech-bubble glyph.
13. ☐ Default density is Standard 44 px, not airy 64 px rows; at 1440 × 900, ≥ 14 rows are visible (≈ 640 px of body ÷ 44).
14. ☐ Dates and times have one format everywhere ("Çar 13:30–15:50"); relative time only in "Güncellendi".
15. ☐ Copy is concrete ("3 atlandı: ENG 102 ile çakışma"), sentence case, no exclamation marks, no "seamless"/"powerful".
16. ☐ Truncation shows a tooltip and the full value in the inspector; no wrapping chaos in cells.
17. ☐ Mobile cards are opaque inset-grouped cells (iOS Settings/Mail style), not floating glass cards with shadows.
18. ☐ No decorative illustrations or emoji in empty/error states.
19. ☐ Radii are concentric (toolbar capsule full, inspector 20, cards 12, chips 6).
20. ☐ Dark mode is designed: faculty dots use the dark palette and glass stays ≥ 72 % tint.

## 22. Open questions

1. Should `/requests` (the inbox) become a saved view of `/classes` ("İnceleme bekleyen" plus the chip editor) to remove a near-duplicate table, or stay a separate intake surface?
2. Exams: one row per `merge_key` (merged exam) with expandable members, as requests-inbox suggests? This spec assumes yes in the Sınavlar kind.
3. Should inline placement edits be allowed on the **active/published** run, or only on drafts (child runs)? This affects read-only rules.
4. Shared views: may PLANNER share, or ADMIN only?
5. "Planlama listesi biçiminde" export: should it overwrite **Kesinleşen Derslik** with the placement, or add a new column next to it so faculties see both?
