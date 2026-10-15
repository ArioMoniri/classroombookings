# Phase 19 · Moderation: classes, people, requests, preferences, matchings, and re-solve

Owner: design-pro (Phase 19 surfaces) · Status: spec v1.0 (2026-10-15) · Routes: **`/moderation?tab=classes|people|requests|preferences|matchings`**, **`/moderation/people/[personId]`**, **`/moderation/recreate/[runId]`**
Builds on: the shared table core and inspector of [`all-classes.md`](all-classes.md) (`ClassTable`, `ClassInspector`, token search, saved views, selection bar), the rule sentence and rule card of [`../generator-studio.md`](../generator-studio.md) §3.3, the run island of [`motion.md`](motion.md) §3.1, the priority model of [`phase19-priority-policy.md`](phase19-priority-policy.md), and the suggestion cards of [`phase19-suggestions.md`](phase19-suggestions.md).
Material and colour: [`liquid-glass.md`](liquid-glass.md). Motion is owned by [`motion.md`](motion.md); this file only names moments.

People in examples are shortened to title + initials (KVKK). Courses, rooms, times, rows and outcomes are real 2026-BAHAR / 2026-GÜZ data from `bahar_derslik_planlama_listesi_v5.xlsx`, `guz_derslik_planlama_2026_2027_v2.xlsx` and `docs/testing/2026-10-08-real-data-feasibility.md`.

---

## 0. BLUF

- **One console, five entity tabs**: Dersler · Kişiler · Talepler · Tercihler · Eşleşmeler (Classes · People · Requests · Preferences · Matchings). They share one table core with the term-wide `/classes` view, so filters, saved views, density, keyboard and bulk actions behave the same everywhere.
- **The person profile answers "what does this academician usually ask for, and did they get it?"** It shows a request-history timeline across terms, grouped by term. Each request shows its outcome (Karşılandı / Kısmen / Karşılanmadı / Yerleşmedi) with a one-line reason. Learned patterns are summarised with evidence ("Pazartesi sabah teorik ders · 2 dönemin 2'sinde"). Preferences and requests can be edited inline.
- **The Matchings tab is "requested → assigned, and why"** for every request in the published plan. Real example: PHAR 114 §2 asked for A 306 + C 602 on Tuesday 11:00–12:30 and was **not placed**. Both rooms are held every week by ING 402 and SOS 404 §1, and under the old policy one lock gave way so that two classes could be placed.
- **"Planı yeniden oluştur" is a minimal-change re-solve with a preview, never a blind overwrite.** It runs a child of the published run with the stability objective (`parent_run_id`, `params.stability=true`). The preview diff has four groups: **Taşınan · Değişmeyen · Yeni yerleşen · Yerleşemeyen (nedeniyle)**. Nothing changes for anyone until "Onayla ve yayınla".
- **Built for 1,300 classes**: virtualised 36 px rows, sticky headers, token search, faceted filters, and a full keyboard path (`1–5` tabs, `/` search, `j/k`, `Enter`, `e`, `p`, `⇧R`).

## 1. User stories

| # | As a… | I want to… | So that… | Acceptance |
|---|---|---|---|---|
| M1 | coordinator | see all classes of 2026-BAHAR with who asked, what they got and their priority | I moderate the term from one place | the Dersler tab lists 1.524 request rows from the planning list, with Öncelik and Durum columns |
| M2 | coordinator | open an academician and see their requests over several terms | I can tell a habit from a one-off | the profile timeline shows 2026-GÜZ and 2026-BAHAR groups, and a pattern line "Pazartesi sabah teorik ders · 2 dönemin 2'sinde" |
| M3 | coordinator | see why a request was not satisfied | I can answer the academician's e-mail in one sentence | the request row reads "Yerleşmedi · A 306 ve C 602 her hafta ING 402 ve SOS 404 §1 tarafından tutuluyor" with "Ayrıntı" opening the diagnosis |
| M4 | coordinator | edit a preference or a request in place | I don't have to go back to Excel or the Studio | the inline editor saves to the term draft, shows "Bir sonraki çözümde etkili olur", and lands in the audit log |
| M5 | coordinator | list every request whose assignment differs from what was asked | I can prioritise follow-up | Eşleşmeler with the filter "Durum: Kısmen, Karşılanmadı, Yerleşmedi" |
| M6 | coordinator | rebuild the plan after edits without shuffling everyone | academicians keep the rooms they already planned around | "Planı yeniden oluştur" defaults to **En az değişiklik**, and the preview shows "Değişmeyen 646" first |
| M7 | coordinator | approve the new plan only after seeing who moves and who cannot be placed | publishing is a conscious decision | "Onayla ve yayınla" is disabled until the preview has loaded. The confirm names the counts and the affected people |
| M8 | coordinator | set a priority for a request or a person from the console | important requests win ties | `p` or the Öncelik cell opens the priority editor (priority-policy spec) |
| M9 | power user | do all of this from the keyboard | I process 50 requests in a session | every action has a key, and focus never jumps to the page top |
| M10 | viewer (planning.view) | look up an academician's history | I can answer questions | read-only profile. Edit controls are hidden, not disabled, with a single note at the top |

## 2. References

| # | App · screen / flow (Mobbin) | Pattern we take | Avoid |
|---|---|---|---|
| R1 | [Reddit · Mod tools Queue](https://mobbin.com/screens/c20fd251-fbfe-471b-b3a4-c0175cf1ada4) | A queue with **state tabs** (Needs Review · Reported · Removed · Edited · Unmoderated), per-item actions in one row (Approve · Remove · Lock), and sort "Newest first" | coloured spam badges |
| R2 | [Google Workspace · Admin › Moderation](https://mobbin.com/screens/a3f540cf-f18d-457f-86c4-05c256f43c27) | Admin moderation page: one-line purpose, **entity tabs** (Gmail · Chat), filter chips "STATUS: Pending triage", and a dense table with paging | the decorative empty illustration |
| R3 | [Circle · Content › Moderation](https://mobbin.com/screens/d695963e-5465-44f1-8a86-171fd1f7c121) | Tabs with counts **Inbox 0 · Approved 1 · Rejected 0**, and a "Content approved" toast after an action | — |
| R4 | [ElevenLabs · User conversation timeline](https://mobbin.com/screens/e5619492-dfcd-4ad4-9fc9-d4c0cdd58c6d) | A person side panel: **timeline of items** with a status tag (Successful / Failed), a short summary per item, and a right column of facts (first/last contact, totals). This becomes our profile timeline + facts column | — |
| R5 | [WorkOS · User profile › Events](https://mobbin.com/screens/ad2ad9ad-c825-4248-94c5-4c7750a5d396) | Profile header + tabs (Details · Sessions · Events), and an event list with a detail pane on the right | raw JSON |
| R6 | [Attio iOS · Person activity](https://mobbin.com/screens/83ca81e1-1d87-432a-b862-8ee43f7ed0e1) | Activity grouped by period ("This week", "August"), "changed Phone numbers and 1 other attribute" with **Show all changes**. This becomes the mobile profile and the "edited by" entries | — |
| R7 | [Fiverr iOS · Order timeline](https://mobbin.com/screens/02b264b5-7d66-4e44-a478-2165ae7c9acb) | Outcome-first timeline rows: "Resolution declined" / "Resolution accepted" in status colour **with an icon**, expandable for details. This becomes satisfied / unsatisfied rows | colour-only headings |
| R8 | [AirOps · Review Changes before publish](https://mobbin.com/screens/9dc41840-28c1-4033-b623-1666f65d2616) | "Compare [published] → Draft" header, a change list where each item shows **Created** and **Revert / Edit**, and one "Publish" primary. This becomes the recreate preview | — |
| R9 | [7shifts · Publish schedule](https://mobbin.com/screens/3fb5adfb-9996-4d21-80de-70094d795699) and [Deputy · Publishing shifts](https://mobbin.com/screens/6512c0b6-fe6c-4a7c-a9c1-1ebc3f4306eb) | Schedule tools put **"2 Conflicts · 1 Overtime · Fix warnings"** next to Publish, a publish popover that asks who to notify, and a checklist "Checking shifts for issues ✓ · Preparing ✓ · Publishing". This becomes approve and publish | — |
| R10 | [Square · Publish schedule summary](https://mobbin.com/screens/720e923e-98e8-4736-b1f1-29148ca46c51) | A plain summary table (Total team members 3 · Total shifts 19 · Total hours 228h) above the Publish button | — |
| R11 | [Vercel · Review Change (staged, not live)](https://mobbin.com/screens/56371ade-be8a-45d7-89a2-b1a3a7ca7db0) | "The following changes have been staged and are not yet live", with **Discard all changes** and **Publish**. Used for the copy of the "changes since publish" list | — |
| R12 | Linear Inbox and Attio records (already in all-classes.md R1–R8, requests-inbox.md R1) | Saved views, grouped list, properties side panel, Details column | — |

## 3. Interaction patterns chosen, and why

| Pattern | Where | Why |
|---|---|---|
| **Entity tabs with counts** (R2, R3) as a `SegmentedGlass` | top of the console | Five entities, one mental model. Counts show where the work is |
| **Shared table core** (`ClassTable`, all-classes.md §5–§10) | every tab | 1,300 rows need the same virtualisation, filters and keyboard map the planner already learned in /classes |
| **Person profile = header facts + pattern summary + term-grouped timeline** (R4, R5, R6) | `/moderation/people/[id]` | The question is longitudinal ("3 of 4 terms"), so time is the spine and facts sit beside it |
| **Outcome-first timeline rows** with glyph + word (R7) | profile | The outcome is what the coordinator answers the academician about. The request detail is secondary |
| **Inline edit in a popover**, reusing `RuleCard` (Studio) for preferences and the all-classes cell editors for requests | profile, Tercihler, Talepler | One way to express a preference across the product. Edits go to the term draft, never straight to the published plan |
| **Requested → assigned pair** with status and reason | Eşleşmeler | Mirrors the planner's Excel column 18 habit (requests-inbox.md). Reasons reuse the run diagnoses (`GET /runs/{id}/data-issues`, `diagnose.py`) |
| **Staged changes list** (R11) + **minimal-change re-solve** + **preview diff** (R8) + **publish with checks** (R9, R10) | recreate flow | Re-solving 1,300 classes is high stakes. Preview-then-publish is the industry norm for schedules, and minimal change protects people's plans |
| **Run island** (motion.md §3.1) | while the re-solve runs | The coordinator can keep moderating during the 20–120 s solve |

## 4. Information architecture

```
/moderation                                    (term from the term switcher; run = published run)
  header: "Moderasyon" · 2026-BAHAR · Yayında: tüm dönem (648 / 684 yerleşti) ▾
          "12 değişiklik yayında değil" ›            (Planı yeniden oluştur)
  tabs:   Dersler 1.524 · Kişiler · Talepler 1.524 · Tercihler · Eşleşmeler 684
  body:   tab table (+ inspector on the right)
/moderation/people/[personId]                  profile (also opens as a 560 px sheet from any table)
/moderation/recreate/[runId]                   preview diff of a re-solve against the published run
```

| Tab | Row = | Default columns | Default view |
|---|---|---|---|
| **Dersler** | one weekly meeting of a section (`ClassRowV2`) | ☐ · Ders · Program · Hoca · Gün/Saat · Atanan oda · Öncelik · Durum · Değişti | all, grouped by faculty |
| **Kişiler** | one academician | Ad · Unvan · Birim · Bu dönem ders · Talep · Karşılanan (5/6) · Öncelik · Öneri · Son düzenleme | sorted by "Karşılanmayan" desc |
| **Talepler** | one meeting or exam request (`meeting_requests`) | ☐ · Durum (NEW/PARSED/NEEDS_REVIEW/LOCKED) · Ders · Talep eden · İstenen gün/saat · İstenen oda (chips) · Öğr. · Öncelik · Kaynak | NEEDS_REVIEW first |
| **Tercihler** | one soft preference (Studio soft rule, accepted suggestion, preference upload) | Kim / Ne için · Tercih (sentence) · Ağırlık · Kaynak (Dosya / Yönetici / YZ / Öneri) · Kapsam (bu dönem / kalıcı) · Bu çözümde (✓ / ✕) | grouped by person |
| **Eşleşmeler** | one request in the published run | Ders · İstenen → Atanan · Durum · Neden · Politika adımı · Kişi | Durum ≠ Karşılandı first |

## 5. Desktop layout (1440)

### 5.1 Console (Eşleşmeler tab shown)

```
┌ shell ┬────────────────────────────────────────────────────────────────────────────────┬─ INSPECTOR (thick, 400) ──┐
│       │ Moderasyon   2026-BAHAR · Yayında: tüm dönem · 648 / 684 ▾                       │ PHAR 114 §2         ‹ › ✕ │
│       │ ◌ 12 değişiklik yayında değil ›                         (Planı yeniden oluştur)  │ English for Academic …    │
│       │ ╭ segmented ───────────────────────────────────────────────────────────────╮    │ Eczacılık · 1. sınıf · 30 │
│       │ │ Dersler 1.524 │ Kişiler │ Talepler 1.524 │ Tercihler │ [Eşleşmeler 684] │    │ ✕ Yerleşmedi · Normal     │
│       │ ╰──────────────────────────────────────────────────────────────────────────╯    │ ── İstenen ────────────── │
│       │ ╭ toolbar capsule ───────────────────────────────────────────────────────────╮  │ Sal 11:00–12:30 (P4–P5)   │
│       │ │ ⌕ durum:yerleşmedi fak:ecz     Filtre +   Görünüm ▾   Dışa aktar ▾   ⋯       │  │ A 306 + C 602 (kesin)     │
│       │ ╰────────────────────────────────────────────────────────────────────────────╯  │ v5.xlsx · Sayfa1 · R1156  │
│       │ [Karşılanmayan 36] [Kısmen 9] [Karşılandı 639] [Tümü 684]                       │ ── Atanan ─────────────── │
│       │ ┌──┬────────────┬───────────────────────────┬───────────────┬────────────────┐ │ —                         │
│       │ │☐ │Ders        │İstenen → Atanan            │Durum          │Neden           │ │ ── Neden ──────────────── │
│       │ ├──┼────────────┼───────────────────────────┼───────────────┼────────────────┤ │ A 306 ve C 602 her hafta  │
│       │ │☐ │PHAR 114 §2 │Sal P4–P5 A 306+C 602 → —   │✕ Yerleşmedi   │Kilit geri çekildi│ │ ING 402 ve SOS 404 §1     │
│       │ │☐ │MAT 112 §1  │Per P7–P9 A 204 → —         │✕ Yerleşmedi   │Kilit çakışması │ │ tarafından tutuluyor.     │
│       │ │☐ │ENG 106     │Çar P2–P3 derslik·70 → —    │✕ Yerleşmedi   │Uygun oda yok   │ │ Politika (eski): en çok   │
│       │ │☐ │HEM 106     │Cum P1–P2 C 201 → A 204     │◐ Kısmen       │Ortak ders      │ │ ders önce → 2 ders > 1    │
│       │ │☐ │PHAR 240 §1 │Pzt P1–P3 A 206 → A 206     │✓ Karşılandı   │—               │ │ kilit.                    │
│       │ │   … virtualised                                                              │ │ [Önceliği Yüksek yap]     │
│       │ └──────────────────────────────────────────────────────────────────────────────┘ │ [Kişiyi aç] [Takvimde aç] │
│       │ 45 / 684 talep · 2 seçili                                         Yoğunluk ▾   │                           │
└───────┴──────────────────────────────────────────────────────────────────────────────────┴───────────────────────────┘
```

- The title row is not glass. Header: `type-large-title` "Moderasyon", then term, then the published-run picker (the published run is the default, and any run can be inspected read-only).
- The **staged-changes link** ("12 değişiklik yayında değil", R11) opens a popover listing draft edits since the published run (from the audit log). Each entry has "Geri al".
- The **one tint button** in the header is "Planı yeniden oluştur" (rule A6). It is outline when there are 0 staged changes and tint when there are more than 0.
- The segmented tabs use `SegmentedGlass` (layoutId thumb). Counts are plain numerals (A4, A7).
- The quick state chips under the toolbar are per-tab presets (R1, R3). Everything else goes through the all-classes token search and filter popovers.
- Reason cells are short codes in words ("Kilit geri çekildi", "Kilit çakışması", "Uygun oda yok", "Ortak ders", "Kapasite", "Etiket", "Hoca çakışması", "Kohort çakışması"). The inspector holds the full sentence.

Reasons used above, all from the real Bahar runs (feasibility report): MAT 112 §1 and HEM 236 are both locked to A 204 on Thursday (13:30–16:00 and 15:10–16:40), so one gives way. ENG 106 (70 students, Wednesday 09:20–10:50) has no fitting room free at that time, because the planner's locks hold them. HEM 106 was asked for C 201 in the preference upload, but it is merged into the joint lecture "BES 128 + HEM 106", which sits in A 204 (usability report, step 3.8).

### 5.2 Person profile (`/moderation/people/[id]`, or a 560 px sheet from any table)

```
┌ shell ┬──────────────────────────────────────────────────────────────┬─ FACTS (plain, 320) ──────────────┐
│       │ ‹ Kişiler                                                    │ Birim       Eczacılık Fakültesi    │
│       │ Dr. Öğr. Üyesi E. Y.                     Öncelik: Normal ▾    │ Bu dönem    4 ders satırı          │
│       │ Eczacılık · 2 dönem geçmişi                                   │ Karşılanan  4 / 4 (2026-BAHAR)     │
│       │ [Zaman çizelgesi] [Tercihler 2] [Öneriler 1]                  │ Son talep   Pzt 08:30 · A 206      │
│       │ ── Alışkanlıklar ─────────────────────────────────────────── │ Son düzenleme 3 Eki · Fatih Bey     │
│       │ ⟲ Pazartesi sabah teorik ders · 2 dönemin 2'sinde             │ ── Hızlı işlemler ──              │
│       │   Bahar: PHAR 240 §1 Pzt 08:30–10:50 · Güz: PHAR 205/241      │ [Tercih ekle] [Takvimde göster]   │
│       │   Pzt 09:20–11:40                                             │ [Geçmişi indir (.xlsx)]           │
│       │ ⟲ Laboratuvar günü: aynı gün sabah + öğleden sonra iki şube   │                                   │
│       │   · 2 dönemin 2'sinde (Bahar Per, Güz Çar)                    │                                   │
│       │ ╭ öneri kartı (phase19-suggestions) ───────────────────────╮ │                                   │
│       │ │ ✦ Pazartesi sabahı tercihi ekle · görüldü: 2 dönem · Orta │ │                                   │
│       │ │   [Kabul et] [Yoksay] [Ertele ▾]                          │ │                                   │
│       │ ╰─────────────────────────────────────────────────────────╯ │                                   │
│       │ ── 2026-GÜZ (planlama listesi · çözüm yok) ───────────────── │                                   │
│       │ ○ PHAR 205 / PHAR 241 §1 · Pzt 09:20–11:40 · 64 öğr.          │                                   │
│       │   İstenen: Fakülte · Kesin oda: B 202  (planlayıcı)           │                                   │
│       │ ○ PHAR 341 §1 · Sal 08:30–10:50 · B 206 (planlayıcı)          │                                   │
│       │ ○ PHAR 341 §1 lab · Çar 09:20–12:30 · Laboratuvar             │                                   │
│       │ ── 2026-BAHAR (yayında: tüm dönem) ───────────────────────── │                                   │
│       │ ✓ PHAR 240 §1 · Pzt 08:30–10:50 · A 206 → A 206 · Karşılandı  │                                   │
│       │   v5.xlsx · R545                                  [Düzenle]   │                                   │
│       │ ✓ PHAR 480 §1 · Sal 13:30–15:00 · A 102 → A 102 · Karşılandı  │                                   │
│       │ ✓ PHAR 240 §1–2 lab · Per 09:20–12:30 / 13:30–16:40 · Lab.    │                                   │
└───────┴──────────────────────────────────────────────────────────────┴───────────────────────────────────┘
```

The requests and rooms above are real rows (Bahar R545, R855, R856, R1039; Güz R38, R273, R447, R449). The Güz rows were linked to the same person **by name match only**, which is exactly the identity problem described below. The ✓ outcomes assume their planner-locked rooms held in the term run, as they did for 512 of 532 planner-roomed events. In the product the outcome always comes from `GET /people/{id}/history` and is never inferred in the UI.

A second, real example of the **unsatisfied** case (another profile):

```
── 2026-BAHAR (yayında: tüm dönem) ──────────────────────────────────────────────
✕ PHAR 114 §2 · Sal 11:00–12:30 · A 306 + C 602 (kesin) → yerleşmedi
  A 306 ve C 602 her hafta ING 402 ve SOS 404 §1 tarafından tutuluyor; eski politika
  (önce en çok ders) bu kilidi geri çekti.  [Önceliği Yüksek yap] [Ayrıntı]
✕ ENG 106 · Çar 09:20–10:50 · derslik, 70 öğr. → yerleşmedi
  Bu saatte 70 kişilik boş oda yok; sığan odaları planlayıcı kilitleri tutuyor.  [Saat öner]
✓ ENG 106 §2 · Çar 08:30–10:00 · B 203 + B 205 → B 203 + B 205 · Karşılandı
```

- **Header**: name (title + name as stored; initials in this spec only), unit, the person-level priority select (priority-policy spec), and tabs Zaman çizelgesi · Tercihler · Öneriler (with counts).
- **Alışkanlıklar** (patterns): at most 3 lines, each with an evidence string ("2 dönemin 2'sinde") and an expand that lists the occurrences. Patterns come from the suggestion engine's evidence (`GET /people/{id}/patterns`). A pattern is a fact. A suggestion card is the actionable proposal built on it (suggestions spec).
- **Timeline**: grouped by term, newest first. Each group header names its source: "yayında: tüm dönem" (a solved, published run), "planlama listesi · çözüm yok" (imported data, not solved yet, so outcomes come from the planner's definitive rooms and are labelled "(planlayıcı)"), or "arşiv".
- **Row**: outcome glyph + word, course + section, requested day/time/room → assigned, provenance (file · cell), and a reason line when the outcome is not ✓. Hover or focus reveals **Düzenle**, which opens the inline editor.
- **Identity across terms.** The Bahar list alone has 574 distinct instructor strings in its two instructor columns (452 in the first), written in mixed forms (real forms, shortened to initials here: "ARŞ.GÖR.C. S." vs "Arş. Gör. C. S."; two names in one cell). Names are normalised and matched into one person record on import. Uncertain matches are **never** merged silently. They show as a banner on the profile, "Bu kişi 2026-GÜZ'deki 'Dr. Öğr. Üyesi E. Y.' ile aynı mı? · Birleştir · Ayrı tut", and merges are audited and undoable. History and pattern counts only include confirmed or exact matches.
- **"3 of 4 terms" counting rule**: a term counts when the person had at least one request matching the pattern's key (same course or course family, same day part, same room or room group). The denominator is the number of terms the person taught. A term with no teaching is not counted against them.

### 5.3 Inline edit (popover from a timeline row, a Tercihler row or a Talepler cell)

```
╭ thick popover, 380 ───────────────────────────────────────╮
│ PHAR 240 §1 · 2026-BAHAR                                   │
│ Talep   Gün [Pzt ▾]  Saat [P1 08:30 ▾]–[P3 10:50 ▾]         │
│         Oda [A 206 ×] [+ oda / bina / etiket]               │
│         Haftalar [1–14]                                     │
│ Tercih  "PHAR 240 §1 mümkünse A 206 dersliğinde olsun"      │
│         Ağırlık (Düşük | [Normal] | Yüksek)  Kapsam [Bu dönem ▾]│
│ ⓘ Bir sonraki çözümde etkili olur. Yayındaki plan değişmez. │
│                                   [Vazgeç]  (Kaydet)        │
╰────────────────────────────────────────────────────────────╯
```

- Request fields reuse the all-classes cell editors (period range, room chip editor, weeks). Preferences reuse the Studio `RuleCard` sentence in compact mode with `HardnessControl` locked to *soft* (Must-rules are edited in the Studio, not here).
- **Kapsam** (scope): "Bu dönem" (this term's draft) or "Kalıcı" (carried into future terms as a person preference). Kalıcı needs `planning.admin`.
- Save writes to the term draft (`PATCH`) and creates an audit event. The staged-changes count in the header increments, and a toast offers Undo.

### 5.4 Recreate schedule

**Step A, sheet** (right, 560 px, `glass-chrome`):

```
Planı yeniden oluştur · 2026-BAHAR
Yayında olmayan değişiklikler (12)                     [Listeyi aç]
  PHAR 114 §2 önceliği Normal → Yüksek · 15 Eki, Fatih Bey
  ING 302 §10 oda talebi "A 306 / A 307 / C 501 / C 502" → + "B blok olmasın" · …
Yöntem   (●) En az değişiklik — yayındaki planı temel alır; yalnızca gerekenler taşınır
         ( ) Baştan çöz — tüm dersler yeniden yerleştirilir (önerilmez)
Kapsam   [Tüm dönem ▾]          Süre sınırı [120 sn ▾]
Politika Kilitler → Öncelik → En çok ders   (dönem ayarı) ›
ⓘ Önizleme oluşturulur; siz onaylayana kadar kimse için hiçbir şey değişmez.
                                         [Vazgeç]  (Önizleme oluştur)
```

This calls `POST /runs {term_id, kind:"COURSE", horizon:"TERM", parent_run_id:<published>, params:{stability:true}}`. The run island appears ("Yeniden çözüm · %38"). The coordinator can keep working, and on completion the island and a toast link to the preview.

**Step B, preview** (`/moderation/recreate/[runId]`). Worked example: PHAR 114 §2 raised to Yüksek, under the new locks-first policy.

```
‹ Moderasyon   Önizleme · yeni çözüm ← yayındaki plan                    Yayında değil
Taşınan 2 · Değişmeyen 646 · Yeni yerleşen 1 · Yerleşemeyen 35 (önce 36)
Etkilenen kişi 3 · Kural ihlali (zorunlu) 0 · Yumuşak puan 84 → 84
[Taşınan 2] [Yeni yerleşen 1] [Yerleşemeyen 35] [Değişmeyen 646]
┌──┬────────────┬──────────────────────────┬──────────────────────────┬──────────────────────────────┐
│☐ │Ders        │Önce                      │Sonra                     │Neden                         │
│☐ │ING 402     │Sal P4–P5 · A 306         │Sal P4–P5 · başka oda      │PHAR 114 §2 kilidi korundu     │
│☐ │SOS 404 §1  │Sal P4–P5 · C 602         │Sal P4–P5 · başka oda      │PHAR 114 §2 kilidi korundu     │
│  │PHAR 114 §2 │—                         │Sal P4–P5 · A 306 + C 602 │Öncelik Yüksek · kilit (adım 1)│
└──┴────────────┴──────────────────────────┴──────────────────────────┴──────────────────────────────┘
                     [Vazgeç]  [Excel'e aktar]                  (Onayla ve yayınla)
```

The rooms ING 402 and SOS 404 §1 move to are whatever the solver returns. This spec does not invent them.

- **Groups** (R8): Taşınan (moved), Yeni yerleşen (newly placed), Yerleşemeyen (unplaceable, with the diagnosis sentence and culprits), and Değişmeyen (unchanged; collapsed, searchable). The **Taşınan** tab opens first, because those are the people who need to be told.
- **Unplaceable reasons** reuse the diagnosis groups (`locked_overlap`, `no_room`, `locked_ineligible`, `pigeonhole`, `unplaced`), rendered as Turkish sentences ("Kilitli iki ders aynı odada aynı saatte: MAT 112 §1 ve HEM 236, A 204, Perşembe").
- **Approve and publish** opens a confirm (R9, R10): a summary table (Taşınan 2 · Yeni yerleşen 1 · Yerleşemeyen 35 · Etkilenen kişi 3), "[✓] Etkilenen öğretim elemanlarına e-posta gönder (3)" (only if mail is set up), and the button "Yayınla". That calls `POST /runs/{id}/activate`. The previous published run stays in history, and "Önceki plana dön" is available from the runs list.
- **Vazgeç** keeps the published plan. The preview run stays in Runs as "önizleme, yayınlanmadı".
- Rows have checkboxes only for **export** and for "Bu taşımayı engelle" (pins the class to its old cell and re-runs the preview). Partial publish is out of scope (open question 2).

## 6. Mobile layout (≤ 390 px)

```
┌ 390 ─────────────────────────────┐   ┌ 390 ─────────────────────────────┐
│ Moderasyon        2026-BAHAR ▾   │   │ ‹ Kişiler                     ⋯  │
│ ◌ 12 değişiklik yayında değil ›  │   │ Dr. Öğr. Üyesi E. Y.             │
│ [Dersler][Kişiler][Talepler][Te… │   │ Eczacılık · Öncelik Normal ▾     │
│ [Karşılanmayan 36][Kısmen 9] ⌕   │   │ [Çizelge][Tercihler 2][Öneri 1]  │
│ ┌──────────────────────────────┐ │   │ ⟲ Pazartesi sabah · 2/2 dönem    │
│ │ ✕ PHAR 114 §2   Yerleşmedi   │ │   │ ╭ ✦ öneri kartı ───────────────╮ │
│ │ Sal 11:00 · A 306 + C 602 → —│ │   │ │ [Kabul et] [Yoksay] [Ertele] │ │
│ │ Kilit geri çekildi           │ │   │ ╰──────────────────────────────╯ │
│ └──────────────────────────────┘ │   │ 2026-GÜZ                         │
│ ┌──────────────────────────────┐ │   │ ○ PHAR 341 §1 · Sal 08:30 · B 206│
│ │ ✕ MAT 112 §1   Yerleşmedi    │ │   │ 2026-BAHAR                       │
│ │ Per 13:30 · A 204 → —        │ │   │ ✓ PHAR 240 §1 · Pzt 08:30 · A 206│
│ └──────────────────────────────┘ │   │ ✓ PHAR 480 §1 · Sal 13:30 · A 102│
│╭────────────────────────────────╮│   │╭────────────────────────────────╮│
││  ⌂   ☰   ⚑ Moderasyon   ⋯   ⌕  ││   ││     (Planı yeniden oluştur)    ││
│╰────────────────────────────────╯│   │╰────────────────────────────────╯│
└──────────────────────────────────┘   └──────────────────────────────────┘
```

- Entity tabs become a horizontally scrolling `SegmentedGlass` with `fill` off. State chips sit on a second row.
- Rows become cards (all-classes.md §13): outcome glyph + word on the first line, requested → assigned on the second, reason on the third. A tap opens the inspector as a bottom sheet (45 % / 92 %).
- The profile is a full-screen route with the timeline grouped by term and the facts column folded into a "Bilgiler" disclosure under the header.
- Inline edit becomes a bottom sheet with the same fields stacked. Kaydet is pinned to the sheet footer.
- Recreate: the sheet becomes a full-height bottom sheet. The preview is a grouped list (Taşınan / Yeni / Yerleşemeyen / Değişmeyen collapsed). "Onayla ve yayınla" is a floating capsule above the tab bar.
- Bulk select uses long-press (250 ms), and the selection bar replaces the tab bar (motion.md §3.3).

## 7. Keyboard path

| Key | Action |
|---|---|
| `g m` | go to Moderasyon |
| `1`–`5` | switch tab (Dersler … Eşleşmeler) |
| `/` | focus token search · `f` open filter menu · `Esc` clear focus (not filters) |
| `j` / `k`, `↑` / `↓` | next / previous row · `Home` / `End` first / last |
| `Enter` | open the inspector · `⇧Enter` open the person profile for the row's person |
| `e` | inline edit (request or preference) · `p` priority editor · `x` select · `⇧x` range |
| `[` / `]` | previous / next person in the profile |
| `⇧R` | Planı yeniden oluştur (opens the sheet; nothing runs without `⌘↵`) |
| In preview: `1`–`4` | Taşınan / Yeni / Yerleşemeyen / Değişmeyen · `⌘↵` opens the publish confirm |
| `?` | shortcuts sheet |

Focus rules: closing the inspector returns focus to the row that opened it. After an inline save, focus returns to the edited row. After a tab switch, focus lands on the first row, not on the page top.

## 8. Component list

| Need | Component | Source · licence | Status |
|---|---|---|---|
| Tabs | `ui/segmented-glass.tsx` | ours on `beui/tabs` · MIT | reuse |
| Table core | `classes/class-table.tsx`, `classes/filter-bar.tsx`, `classes/classes-model.ts` | ours; TanStack Table + `@tanstack/react-virtual` · MIT | reuse; add column sets `moderationClassCols`, `peopleCols`, `requestCols`, `preferenceCols`, `matchingCols` |
| Inspector | `classes/class-inspector.tsx` (`ClassInspector`) | ours | reuse; add "Eşleşme" section (requested → assigned, reason, policy step) |
| Person profile | new `moderation/person-profile.tsx` | ours | **new** |
| Timeline | new `moderation/request-timeline.tsx` (`ol` grouped by term, outcome rows) | ours; pattern from ElevenLabs / Fiverr / Attio (reference only) | **new** |
| Pattern line | new `moderation/pattern-line.tsx` | ours | **new** (shares evidence format with suggestion cards) |
| Outcome badge | `ui/badge.tsx` `tone="feasible|warning|infeasible|preoccupied"` + glyph | shadcn · MIT | reuse |
| Inline editor | `ui/popover.tsx` + all-classes cell editors + `studio/rule-card.tsx` (compact) + `studio/hardness-control.tsx` | shadcn · MIT; ours | reuse |
| Priority select | `ui/select.tsx` / editor from priority-policy spec | MIT / ours | reuse |
| Staged changes popover | `ui/popover.tsx` + list from audit | MIT | reuse |
| Recreate sheet | `ui/sheet.tsx` (right; bottom on mobile) | shadcn · MIT | reuse |
| Run status | run island (shell) + `ui/beautifului/task-rows.tsx` | ours; beautifului · MIT | reuse |
| Preview diff | `ui/beautifului/diff-table.tsx` | beautifului · MIT | reuse; "Önce → Sonra" columns |
| Publish confirm | `ui/dialog.tsx` + `ui/table.tsx` summary | MIT | reuse |
| Bulk bar | `ui/beui/expandable-action-bar.tsx` in `Toolbar floating-bottom` | beUI · MIT | reuse |
| Suggestion card | `suggestions/suggestion-card.tsx` (suggestions spec) | ours, built on beautifului Recommendation Card pattern · MIT | from the suggestions spec |
| Mobile rows | `classes/class-cards.tsx`; optional `@beui/swipeable-list` · MIT for swipe actions | MIT | reuse / optional import |
| Empty states | `ui/empty-state.tsx` | ours | reuse |

Nothing paid. kobra "CRM Table" and "Grouped Table" are reference only.

## 9. Tokens

| Use | Token |
|---|---|
| Outcome Karşılandı | `--status-feasible-*` + `check-circle-2` |
| Outcome Kısmen | `--status-warning-*` + `circle-dot-dashed` (half) |
| Outcome Karşılanmadı | `--status-warning-*` + `alert-triangle` (assigned, but differently from what was asked) |
| Outcome Yerleşmedi | `--status-infeasible-*` + `x-octagon` |
| Planner-only outcome (no solve) | `--label-2` text + `circle` glyph, "(planlayıcı)" suffix |
| Lock | `--status-locked-*` + `lock` |
| Staged-changes link | `--label-2` with a `circle-dashed` glyph; a count in `tabular-nums` |
| Table | opaque surface, 36 px rows (Sıkı 32 / Standart 36 / Rahat 44), hairline rows, sticky header on `--mat-thick` |
| Inspector, popovers | `glass-thick`, `rounded-2xl` (inspector), `rounded-xl` (popover) |
| Recreate sheet | `glass-chrome`, `rounded-2xl`, 24 px padding |
| Spacing | 4 px base; toolbar capsule 44 px; timeline row gap 8, group gap 24 |
| Type | page `type-large-title`, group headers `type-headline`, rows `type-callout`, reasons `type-footnote` in `--label-2` |
| Motion | `motion.md` tokens only; ≤ 300 ms |

## 10. States

| State | Console | Profile | Recreate |
|---|---|---|---|
| **Empty** | No term data: `EmptyState` "Bu dönemde henüz ders yok", with actions "İçe al" (/onboarding) and "Program oluştur" (program wizard). No published run: Eşleşmeler says "Henüz yayında plan yok. Önce bir plan oluşturun." with a link to /generate | A person with no requests: "Bu dönem talebi yok." The history still lists past terms | No staged changes: the sheet says "Yayındaki planla taslak aynı. Yine de yeniden çözebilirsiniz." and the button is outline |
| **Loading** | 12 static placeholder rows (no shimmer). Tab counts show "…" | Facts column first, timeline groups stream in per term | Run island with real phases. Preview: placeholder rows per group |
| **Error** | Inline banner with retry. Filters stay applied | "Geçmiş yüklenemedi" per term group, with retry for that group only | Run FAILED: the island shows the error and a link to run details. Activate failure: dialog stays open with the message and nothing is published |
| **Partial** | Run is INFEASIBLE / partial (648/684): Eşleşmeler shows the 36 unplaced with reasons. Header says "Kısmi plan" | Terms without a solved run show planner outcomes, labelled "(planlayıcı)" | Preview finished on the time limit: banner "Süre sınırında durdu; sonuç en iyi bulunan" with "Süreyi artırıp tekrar dene" |
| **Permission denied** | `planning.view`: tables read-only, no selection column, no recreate button, and a one-line note. No `planning.view`: 403 page | Same; edit affordances hidden | Recreate and publish need `planning.edit`. Publish follows the existing `POST /runs/{id}/activate` permission. The button is hidden for others, with "Yayınlamak için planlama düzenleme izni gerekir" in the staged-changes popover |
| **Conflict** | Another user published while a preview was open: the preview shows "Yayındaki plan değişti (Run #…)", and publish is disabled until "Önizlemeyi yenile" | — | same |

## 11. Accessibility

- Tables: `role="grid"`, roving tabindex, `aria-sort`, `<caption>` with counts ("45 / 684 talep, filtrelenmiş"). Outcome cells carry text, never only colour. Requested → assigned reads as "İstenen Salı 11:00, A 306 ve C 602; atanan yok".
- Timeline: an ordered list per term (`<section aria-labelledby>` per term, `<ol>` of requests). Each row is a `<li>` with an accessible name of course + outcome. The pattern line is a `<p>` with its evidence in text.
- Inline editor: a labelled form in a popover, with focus trapped and restored. Save is announced politely ("PHAR 240 §1 tercihi kaydedildi; bir sonraki çözümde etkili").
- Live regions: tab result counts (polite, 500 ms debounce), staged-change count, re-solve phases ("Yeniden çözüm: kısıtlar kuruluyor"), and preview ready ("Önizleme hazır: 2 taşınan, 1 yeni yerleşen, 35 yerleşemeyen").
- Publish confirm: `role="alertdialog"`. The summary table has headers. The destructive alternative "Vazgeç" is the default focus.
- Contrast on glass: the inspector and popovers are `thick` over content and the sheet is `chrome` (G1). Reason text uses label-2 (≥ 6.4:1). Status foregrounds on tints pass ≥ 4.69:1 (liquid-glass.md §5.3).
- Reduced transparency makes every glass surface solid. Forced colours: outcome glyphs stay, and badges become `CanvasText` borders.
- Touch: 44 px rows on coarse pointers, and every swipe action is also in the row ⋯ menu.

## 12. Motion moments (hand to the motion agent; names only)

| Moment | Suggested pattern |
|---|---|
| `moderation.tab-switch` | §2 segmented thumb + enter-only content (no stagger, A9) |
| `moderation.inspector-open` / `swap` | §4 inspector (shared with `ClassInspector`) |
| `moderation.profile-open-as-sheet` | §4 sheet |
| `moderation.timeline-group-expand` | §6 (height via `layout`, ≤ 40 items) |
| `moderation.inline-edit-saved` | §10 Saved ✓ |
| `moderation.staged-count-bump` | badge bump, only on the user's own edit (motion.md §3.2 rule) |
| `moderation.recreate-start` (sheet → island) | §19 island morph |
| `moderation.recreate-ready` | §10 + §5 toast |
| `moderation.preview-group-switch` | §2 |
| `moderation.publish-confirm` / `published` | §1 dialog, then §10 check + §5 toast |
| `moderation.selection-bar` | §19 selection bar replaces toolbar |

## 13. i18n (TR + EN)

- Namespace `moderation.*`. Tab names: Dersler / Classes, Kişiler / People, Talepler / Requests, Tercihler / Preferences, Eşleşmeler / Matchings.
- Outcome words: Karşılandı / Satisfied, Kısmen / Partly, Karşılanmadı / Not as requested, Yerleşmedi / Not placed. EN "Not as requested" is longer than TR, so the column is sized for the longest of both.
- **Long Turkish strings**: "A 306 ve C 602 her hafta ING 402 ve SOS 404 §1 tarafından tutuluyor" (66 chars) wraps in the inspector and truncates with a tooltip in the table cell. "Yayında olmayan değişiklikler" (29). "Planı yeniden oluştur" (21; EN "Recreate schedule", 17). "Etkilenen öğretim elemanlarına e-posta gönder" (45; EN "E-mail affected instructors", 27).
- Evidence counts use ICU plurals: TR "{n} dönemin {k}'sinde" with the `tr-suffix` helper for the case ending ("2'sinde", "3'ünde", "4'ünde"); EN "in {k} of {n} terms".
- Days and periods: TR "Pzt/Sal/Çar/Per/Cum/Cmt/Paz", EN "Mon…Sun". Period labels "P4–P5 11:00–12:30" are the same in both. Times use 24 h in both locales.
- Person titles (Prof. Dr., Doç. Dr., Dr. Öğr. Üyesi, Öğr. Gör., Arş. Gör.) are data and are never translated.
- Turkish-aware search and sort (`localeCompare('tr')`, İ/ı casefold).

## 14. API endpoints (backend tickets)

Existing and reused: `GET /terms/{term_id}/classes` (proposed in all-classes.md §16), `GET/PUT /requests/meetings`, `GET /runs/{run_id}/assignments`, `GET /runs/{run_id}/data-issues`, `POST /runs` (with `parent_run_id` and `params.stability`), `GET /runs/{id}/events`, `POST /runs/{id}/activate`, `POST /runs/{run_id}/assignments/{aid}/explain`, `GET /audit`, `POST /audit/{id}/undo`, `GET /instructors`.

New:

| Ticket | Endpoint | Purpose |
|---|---|---|
| P19-M-01 | `GET /terms/{term_id}/moderation/summary` → `{counts:{classes, people, requests, preferences, matchings}, published_run_id, staged_changes}` | header and tab counts |
| P19-M-02 | `GET /terms/{term_id}/people?q=&unit=&priority=&satisfaction=&has_suggestions=&sort=&offset=&limit=` → `PersonRow {id, display_name, title, unit, classes, requests, satisfied, unsatisfied, unplaced, priority, suggestions, updated_at, updated_by}` | Kişiler tab |
| P19-M-03 | `GET /people/{person_id}/history?terms=&limit=` → `[{term_code, run:{id, label, published}\|null, items:[{request_id, course, section, requested:{day, periods, rooms[], weeks}, assigned\|null, outcome:"satisfied"\|"partial"\|"not_as_requested"\|"unplaced"\|"planner_only", reasons:[{code, text:{tr,en}, culprits:[{course, section, room}]}], provenance:{file, sheet, row, cell}}]}]` | profile timeline |
| P19-M-04 | `GET /people/{person_id}/patterns` → `[{key, label:{tr,en}, seen_terms:[term_code], of_terms, occurrences:[{term_code, request_id}]}]` | Alışkanlıklar (shared with the suggestion engine) |
| P19-M-05 | `GET /terms/{term_id}/preferences?person_id=&program_id=&source=&scope=&offset=&limit=`, `POST /terms/{term_id}/preferences`, `PATCH /preferences/{id}`, `DELETE /preferences/{id}` | Tercihler tab + inline edit. Stored as soft rules in the term draft (Studio) with `owner_person_id`, `scope: term\|persistent`, `source` |
| P19-M-06 | `GET /runs/{run_id}/matchings?status=&reason=&person_id=&program_id=&q=&sort=&offset=&limit=` → `MatchingRow {request_id, course, section, person_ids[], requested, assigned\|null, status, reasons[], policy_step, priority}` + `counts` by status | Eşleşmeler tab |
| P19-M-07 | `GET /terms/{term_id}/changes-since-publish` → audit events since the published run's `finished_at` that affect solving (requests, preferences, priorities, locks) | staged-changes popover and the recreate sheet |
| P19-M-08 | `GET /runs/{run_id}/diff?against={run_id}&group=moved\|unchanged\|new\|unplaceable&q=&offset=&limit=` → `{counts, items:[{request_id, course, section, before\|null, after\|null, reason:{code, text}, people[]}]}` | recreate preview |
| P19-M-09 | `POST /runs/{run_id}/activate` accepts `{notify_people: boolean}` and returns `{notified: n}` | publish + optional e-mail (uses the CRBS e-mail settings) |
| P19-M-10 | `POST /runs/{run_id}/pins` body `{request_ids[]}` → a new preview run with those classes pinned to their parent cells | "Bu taşımayı engelle" |
| P19-M-11 | `GET /people/{person_id}/merge-candidates` → `[{person_id, display_name, terms[], score, evidence[]}]`; `POST /people/{person_id}/merge {other_id}` (audited, undoable); `POST /people/{person_id}/keep-separate {other_id}` | cross-term identity banner |

Permissions: GETs need `planning.view`. Edits, priorities and recreate need `planning.edit`. Persistent (cross-term) preferences need `planning.admin`. Publish follows the existing activate rule.

## 15. Open questions for the product owner

1. Should `/requests` (the v1 inbox) become the **Talepler** tab here, with a redirect? Two places for the same rows is confusing.
2. Partial publish: should the coordinator be able to accept some moves and reject others in the preview? This spec only allows pinning a class and re-running the preview, which keeps every published plan a real solver result.
3. Notify academicians on publish: by e-mail only, or also an in-app notification for those with accounts? Who signs the message?
4. Should the people directory include staff who only appear as second instructor ("Dersin 2. Öğretim Elemanı"), or only primary instructors?
5. Is cross-term history allowed to show terms older than the retention period the institution sets under KVKK? Proposed default: keep 4 terms, configurable by an admin.
