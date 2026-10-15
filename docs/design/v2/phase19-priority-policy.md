# Phase 19 · Conflict policy and priorities

Owner: design-pro (Phase 19 surfaces) · Status: spec v1.0 (2026-10-15) · Routes: **`/moderation/policy`** (per-term policy + priority overview), with the priority editor also inline in every Moderasyon table, the `ClassInspector`, the person profile, and the Studio scope summary
User decision (ROADMAP Phase 19, 2026-10-15): **locks first (never moved), then coordinator-set priority, then most classes placed; configurable per term.** This resolves the PHAR 114 §2 question (lock-first vs most-classes-first) raised in `docs/testing/2026-10-08-real-data-feasibility.md`.
Related: [`phase19-moderation.md`](phase19-moderation.md) (Eşleşmeler reasons, recreate preview), [`../run-report.md`](../run-report.md) (result card), [`../generator-studio.md`](../generator-studio.md) §3.1 (scope), [`liquid-glass.md`](liquid-glass.md), [`motion.md`](motion.md) (motion is owned there).

---

## 0. BLUF

- **The policy is an ordered list of three criteria**, shown as numbered cards: **1 Kilitler** (locked classes never move), **2 Öncelik** (Yüksek before Normal before Düşük), **3 En çok ders** (place as many classes as possible). Each term stores its own order. The default is the user's decision (1 → 2 → 3).
- **Changing the order is allowed but explained.** Moving "En çok ders" above "Kilitler" shows what that meant in real data: in the 2026-BAHAR term run under that order, four planner locks gave way (ING 102, ING 202, PHAR 114 §2, SYS 18) so that more classes could be placed. The change is admin-only, audited, and takes effect at the next solve.
- **Priority has three tiers**, Yüksek / Normal / Düşük, set on a request, a person or a program. The effective priority is the most specific one set (request › person › program › Normal), and the UI always says where it came from ("Yüksek · kişiden").
- **A distribution bar** keeps priorities meaningful ("Yüksek 38 · Normal 1.471 · Düşük 15"). It warns when Yüksek exceeds 10 % of requests, because when everything is high, nothing is.
- **After every solve the policy explains itself**: a **Politika etkisi** card on the run result (locks kept/lost, priority tiers placed, total placed), a **policy step** on every Matchings row ("adım 1 · kilit"), and a short list of the decisive conflicts ("PHAR 114 §2 kilidi korundu → ING 402 ve SOS 404 §1 başka odaya taşındı"). **"Bu politikayla önizle"** runs a counterfactual child run and opens the moderation preview diff.

## 1. User stories

| # | As a… | I want to… | So that… | Acceptance |
|---|---|---|---|---|
| P1 | coordinator | know which rule wins when two classes want the same room | I can explain outcomes to academicians | the policy page shows the three criteria in order, each with one plain sentence |
| P2 | admin | choose the order for this term | an exam term can use a different policy than a lecture term | the order is saved per term, with an audit entry and "Sonraki çözümde etkili" |
| P3 | admin | understand the consequence before changing it | I don't break locks unknowingly | moving Kilitler down shows the real 2026-BAHAR consequence and asks for confirmation |
| P4 | coordinator | mark a request as high priority | it wins ties against normal requests | `p` / the Öncelik cell → Yüksek. The row shows "Yüksek · talep" |
| P5 | coordinator | give a person a default priority | I don't set it on 9 rows one by one | profile header select → Yüksek. Their requests show "Yüksek · kişiden" unless overridden |
| P6 | coordinator | see how many high-priority items exist | priority stays meaningful | the distribution bar with a warning above 10 % |
| P7 | coordinator | after a solve, see where the policy decided the outcome | I can defend it | the Politika etkisi card + "Politika nedeniyle" filter in Eşleşmeler |
| P8 | coordinator | see what would change under another order | I can decide with evidence | "Bu politikayla önizle" → child run → moderation preview diff |

## 2. References

| # | App · screen (Mobbin, web) | Pattern we take | Avoid |
|---|---|---|---|
| R1 | [WorkOS · Edit priority (roles)](https://mobbin.com/screens/d9f96ee3-37ca-4fa3-9cce-f0117e4f1935) | **"When a member has different roles …, the role with a higher priority will be used. Drag roles to change the priority, from highest to lowest."** A one-sentence rule, then a drag list, then Save. This is the core of our policy editor | — |
| R2 | [Xero · Bank rules](https://mobbin.com/screens/34d9915e-dc0e-45f8-8b61-2f8d40a541c1) | **Numbered** rules with drag handles: "Drag and drop to set their order so they run in the right sequence". Numbers make the order explicit | checkbox + drag on one row (too busy) |
| R3 | [Gorgias · Rules "trigger in the order below"](https://mobbin.com/screens/d303f946-d63b-4719-97ff-ad3c206cbd76) | An order sentence above the list with a "Learn how to prioritise rules" link, and a "Successfully updated rule" toast | — |
| R4 | [Monarch · Prioritise your goals](https://mobbin.com/screens/56cf5630-edd3-49da-a3d0-3cbf4fadcde1) | **#1, #2, #3 rank labels** inside each card, with edit per card | — |
| R5 | [Fresha · Time off types order](https://mobbin.com/screens/c303fa1c-01df-4330-b5bd-f6db02b9371b) | "Close / Save order" as an explicit commit of a reorder (no silent autosave for a policy) | — |
| R6 | [7shifts · Publish with "2 Conflicts · 1 Overtime · Fix warnings"](https://mobbin.com/screens/3fb5adfb-9996-4d21-80de-70094d795699) | Conflicts summarised next to the decision. Used for the policy-impact line on the result card | — |
| R7 | [Square · Publish schedule summary](https://mobbin.com/screens/720e923e-98e8-4736-b1f1-29148ca46c51) | A plain summary table of totals. Used for the Politika etkisi card | — |
| R8 | [Klaviyo · Reject with reason](https://mobbin.com/screens/2a918c1c-fe71-458f-b455-d426c9344288) | A warning banner inside the confirm ("Only reject … for valid reasons") plus a reason select. Used for the "move Kilitler down" confirm | — |

Other: Linear's issue priority (No priority / Urgent / High / Medium / Low with a one-key shortcut and a glyph per level) as the model for a priority that is a property with a glyph, not a coloured badge (liquid-glass.md A4).

Component sites: beUI **sortable-stack** (`@beui/sortable-stack`, "Composable sortable list with group, item, drag handle, content and undo parts", MIT) for the criteria list, with keyboard reordering added if missing (§9).

## 3. Interaction patterns chosen, and why

| Pattern | Why |
|---|---|
| **Numbered, reorderable criteria with one sentence each** (R1, R2, R4) | A lexicographic policy is literally an ordered list. Showing it as one makes "what wins" visible, and numbers survive screenshots and printouts |
| **Explicit Save for policy changes** (R5) | A policy changes many outcomes. It is not autosaved like a field |
| **Consequence-aware confirm** (R8) with real past data | "Locks may move" is abstract. "4 planner locks gave way in 2026-BAHAR" is not |
| **Priority as a property with glyph + word**, three tiers, plus a source suffix | It fits a table column and a keyboard shortcut. The source suffix stops "why is this High?" questions |
| **Inheritance: request › person › program › Normal** | Priorities are usually about people (a dean, a part-time lecturer) or programs (a new program in its first term), and only sometimes about one class |
| **Distribution bar with a soft limit** | Prevents priority inflation without forbidding it |
| **Explain after the fact, on every surface that shows an outcome** (R6, R7) | People ask "why" where they see the result: the result card, Matchings, the inspector and the profile |
| **Counterfactual preview** | The most honest answer to "what if we used the other order?" is a real child run, shown in the same diff the coordinator already knows |

## 4. Semantics (what the UI promises)

| Step | Sentence shown (TR) | Sentence shown (EN) | Solver meaning (backend P19-P-01) |
|---|---|---|---|
| **Kilitler** | "Kilitli dersler hiç taşınmaz. İki kilit aynı oda ve saati isterse biri yerleşemez; hangisi olacağını öncelik, sonra ders-hafta sayısı belirler ve size sorulur." | "Locked classes never move. If two locks want the same room and time, one cannot be placed; priority, then event-weeks, decide which, and you are told." | maximise locked event-weeks kept (lexicographic level 1) |
| **Öncelik** | "Yüksek öncelikli talepler Normal'lerden, Normal'ler Düşük'lerden önce yerleşir." | "High-priority requests are placed before Normal, Normal before Low." | maximise placed event-weeks per tier, High then Normal then Low |
| **En çok ders** | "Kalan her şeyde olabildiğince çok ders yerleşir." | "Everything else: place as many classes as possible." | maximise total placed event-weeks |
| (always last) | "Eşitlikte: yumuşak tercihler ve en az değişiklik." | "Ties: soft preferences and minimal change." | soft objective (unchanged) |

Hard rules (capacity, no room/instructor/cohort overlap, fixed times, tags) are **never** part of the policy. The policy only decides **who gives way** when not everything fits. The 100/100 hard-rule integrity is unchanged.

**Lock conflicts in the data** (two locks that cannot both hold, e.g. MAT 112 §1 13:30–16:00 and HEM 236 15:10–16:40, both locked to A 204 on Thursday) are not hidden by the policy. They appear as **"Kilit çakışması · kararınız gerekiyor"** before solving (Studio pre-check) and after (result card), with actions "MAT 112 §1'i tut" / "HEM 236'yı tut" / "Önceliğe bırak".

## 5. Desktop layout (1440)

### 5.1 Policy page (`/moderation/policy`)

```
┌ shell ┬───────────────────────────────────────────────────────────────────────────────────────────┐
│       │ Öncelik politikası · 2026-BAHAR                                     Yönetici ayarı         │
│       │ Her şey sığmadığında kimin yer vereceğini bu sıra belirler. Zorunlu kurallar hiç esnemez.  │
│       │ ╭ regular card ──────────────────────────────────────────────────────────────────────────╮ │
│       │ │ ⠿ 1  Kilitler        Kilitli dersler hiç taşınmaz.                       532 kilit      │ │
│       │ │ ⠿ 2  Öncelik         Yüksek › Normal › Düşük.                             38 · 1.471 · 15│ │
│       │ │ ⠿ 3  En çok ders     Kalan her şeyde olabildiğince çok ders yerleşir.                   │ │
│       │ │      Eşitlikte: yumuşak tercihler ve en az değişiklik (sabit)                           │ │
│       │ ╰────────────────────────────────────────────────────────────────────────────────────────╯ │
│       │ Hazır sıralar  [Kilitler önce (önerilen)] [En çok ders önce]                               │
│       │ ⓘ Bu dönemin yayındaki planı (tüm dönem, 648 / 684) eski sırayla üretildi:                  │
│       │   En çok ders → Kilitler. Yeni sıra bir sonraki çözümde etkili.   [Bu politikayla önizle]   │
│       │                                                              [Vazgeç]  (Sırayı kaydet)     │
│       │ ── Öncelikler ─────────────────────────────────────────────────────────────────────────── │
│       │ Yüksek 38 ▮▯▯▯▯▯▯▯▯▯ Normal 1.471 ▮▮▮▮▮▮▮▮▮▮ Düşük 15        Yüksek oranı %2,5 · sınır %10 │
│       │ [Talepler] [Kişiler] [Programlar]   Yalnızca Normal dışı ☑   ⌕                              │
│       │ ┌──────────────┬──────────────────────────────┬──────────────┬──────────────┬────────────┐ │
│       │ │Talep          │Kim                           │Öncelik       │Kaynak        │Not         │ │
│       │ │PHAR 114 §2    │Öğr. Gör. S. K. · Yab. Diller │⌃ Yüksek      │talep         │"kilit…"    │ │
│       │ │ENG 106        │Öğr. Gör. S. K.               │⌃ Yüksek      │kişiden       │            │ │
│       │ └──────────────┴──────────────────────────────┴──────────────┴──────────────┴────────────┘ │
└───────┴────────────────────────────────────────────────────────────────────────────────────────────┘
```

The priority counts (38 / 1.471 / 15) show the shape of the live `GET /terms/{id}/priorities/summary`. They are not measured values.

- The criteria card is a `Card variant="glass"` (regular, on the scene). Rows are opaque inner rows (G2). Each row has a drag handle, a rank number, a name, one sentence and a live count.
- **Presets** are two chips that set the order. "En çok ders önce" is labelled with the date it was the default ("2026-10-08 davranışı") so people recognise old outcomes.
- **Sırayı kaydet** is the only tint button. "Vazgeç" restores the saved order. Leaving with unsaved changes asks for confirmation.
- The **priority overview** under it reuses the moderation table core with three entity tabs and the filter "Yalnızca Normal dışı" on by default.

### 5.2 Consequence confirm (moving Kilitler below En çok ders)

```
╭ alertdialog, thick, rounded-3xl ──────────────────────────────────────────────────╮
│ Kilitli dersler yer verebilir                                                     │
│ ⚠ Bu sırayla, daha çok ders yerleşsin diye kilitli dersler taşınabilir veya        │
│   yerleşmeyebilir.                                                                │
│ 2026-BAHAR tüm dönem çözümünde bu sırayla 4 planlayıcı kilidi yer verdi:           │
│   ING 102 · ING 202 · PHAR 114 §2 · SYS 18                                         │
│ Neden (zorunlu) [ Sınav dönemi: en çok sınavın yerleşmesi öncelikli      ]         │
│                                                  [Vazgeç]  (Yine de kaydet)        │
╰───────────────────────────────────────────────────────────────────────────────────╯
```

The example list comes from the last run of this term that used the other order (`GET /terms/{id}/policy/impact?order=`). With no such run, the dialog says "Bu dönemde bu sırayla çözüm yok; etkisini görmek için önce önizleyin" and offers **Bu politikayla önizle**.

### 5.3 Priority editor (inline, everywhere)

```
Öncelik   ( ⌃ Yüksek | [– Normal] | ⌄ Düşük )      Kaynak: kişiden (Öğr. Gör. S. K.)  [Talep için değiştir]
Not       [ isteğe bağlı: neden? ]
```

- In tables, the Öncelik column shows a glyph + word + source in `--label-3` ("⌃ Yüksek · kişiden"). `p` on a row opens this popover. `p 1/2/3` sets High/Normal/Low directly.
- On a person, the profile header select sets the person default. On a program, it is set in Moderasyon › Dersler grouped by program (group header ⋯ › "Program önceliği").
- Overriding an inherited value creates a request-level priority. "Kaynağa dön" removes the override.
- Every change is audited (`priority.set {subject, from, to, note}`) and counts as a staged change (moderation header).

### 5.4 Explaining effects after a solve

**Politika etkisi** card on the run result (Studio result card, run report, moderation preview), as a summary table (R7):

```
Politika etkisi · Kilitler → Öncelik → En çok ders
Kilitler      529 / 532 korundu · 3 kilit çakışması (veride)                         [Gör]
Öncelik       Yüksek 38 / 38 · Normal 1.448 / 1.471 · Düşük 12 / 15 yerleşti           [Gör]
En çok ders   648 / 684 olay
Politikanın belirlediği 4 durum
  PHAR 114 §2 kilidi korundu (adım 1) → ING 402 ve SOS 404 §1 başka odaya taşındı
  … ve 3 benzer durum                                                             [Tümü ›]
[Bu politikayla önizle ▾ En çok ders önce]
```

The numbers above illustrate the shape. A real card shows `GET /runs/{id}/policy-impact` for that run, and 648 / 684 is the measured Bahar term placement under the old order.

- **Matchings rows** (moderation §5.1) carry **Politika adımı**: "adım 1 · kilit", "adım 2 · öncelik (Yüksek > Normal)", "adım 3 · en çok ders", or "—" when the policy did not decide the outcome (for example a pure capacity problem). The filter "Politika nedeniyle" lists only rows where a step decided.
- **Inspector / profile reason line** names the winner and the step: "ING 402 A 306'dan taşındı: PHAR 114 §2 kilitli (adım 1)". On the other side: "PHAR 114 §2 yerleşti: kilit korundu (adım 1); A 306'yı ING 402 istiyordu".
- **"Bu politikayla önizle"** opens a menu of the other orders (and "Öncelikler olmadan"). It runs a child of this run with that policy and stability on, then opens `/moderation/recreate/[runId]`. The diff header says which policy produced it ("Önizleme · En çok ders önce").

## 6. Mobile layout (≤ 390 px)

```
┌ 390 ──────────────────────────────┐
│ ‹ Moderasyon     Öncelik politikası│
│ Her şey sığmadığında kim yer verir │
│ ┌───────────────────────────────┐ │
│ │ 1  Kilitler            ⌃  ⌄   │ │  ← move up/down buttons, 44 px (no drag needed)
│ │ Kilitli dersler hiç taşınmaz. │ │
│ ├───────────────────────────────┤ │
│ │ 2  Öncelik             ⌃  ⌄   │ │
│ ├───────────────────────────────┤ │
│ │ 3  En çok ders         ⌃  ⌄   │ │
│ └───────────────────────────────┘ │
│ [Kilitler önce] [En çok ders önce]│
│ Yüksek 38 · Normal 1.471 · Düşük 15│
│╭─────────────────────────────────╮│
││          (Sırayı kaydet)        ││
│╰─────────────────────────────────╯│
└───────────────────────────────────┘
```

- Reordering on touch uses **up/down buttons**. Long-press drag is also available (beUI sortable-stack), but buttons are the primary path.
- The priority editor is a bottom sheet with a full-width `SegmentedGlass` (fill) and the source line under it.
- The Politika etkisi card stacks its rows. "Tümü ›" opens Matchings filtered to "Politika nedeniyle".

## 7. Component list

| Need | Component | Source · licence | Status |
|---|---|---|---|
| Criteria list | beUI `@beui/sortable-stack` (drag handle, undo), restyled to opaque rows inside a regular card | beUI · MIT (`LICENSES/beui-MIT.txt`) | **import** (add a `SOURCES.md` row; add keyboard move if absent) |
| Fallback reorder | `@dnd-kit/sortable` + `KeyboardSensor` (already a dependency) | MIT | reuse if sortable-stack lacks keyboard support |
| Presets | `ui/chip.tsx` (toggle) | ours | reuse |
| Tier picker | `ui/segmented-glass.tsx` | ours / beUI tabs · MIT | reuse |
| Priority cell | new `moderation/priority-cell.tsx` (glyph + word + source) | ours | **new** |
| Distribution bar | new `moderation/priority-distribution.tsx` (one stacked bar + numbers; no chart library needed) | ours | **new** (follows the dataviz rule: numbers printed, no colour-only meaning) |
| Confirm | `ui/dialog.tsx` (alertdialog) + `ui/textarea.tsx` | MIT | reuse |
| Impact card | new `runs/policy-impact-card.tsx` on `ui/card.tsx` + `ui/table.tsx` | ours / MIT | **new** |
| Matchings step column | `classes/class-table.tsx` column `policyStep` | ours | **extend** |
| Counterfactual menu | `ui/dropdown-menu.tsx` | MIT | reuse |
| Toast | `ui/sonner.tsx` | MIT | reuse |

## 8. Tokens

| Use | Token |
|---|---|
| Rank number | `type-headline`, `tabular-nums`, `--label-2` |
| Criteria rows | opaque `bg-fill-2` inside `glass-regular` (G2), `rounded-lg`, 52 px rows, drag handle `--label-3` |
| Priority glyphs | Yüksek `chevrons-up` (or `⌃`) in `--label-1`; Normal `minus` in `--label-3`; Düşük `chevron-down` in `--label-2`. **No colour coding** for tiers. Priority is not state (A4, A7) |
| Distribution bar | segments in `--label-1` (Yüksek), `--fill-1` (Normal), `--label-3` (Düşük), each labelled with its number. Over-limit warning `--status-warning-*` + `alert-triangle` |
| Lock references | `--status-locked-*` + `lock` |
| Confirm warning | `--status-warning-*` banner inside the dialog |
| Impact card | `Card variant="glass"` on the scene (result screens), rows as plain table |
| Spacing | card padding 20; row gap 4; section gap 32 |
| Motion | `motion.md` tokens only |

## 9. States

| State | What the user sees |
|---|---|
| **Default** (never configured) | The page shows the default order with "Varsayılan (önerilen)" and no "kaydedildi" date. Solving uses the default |
| **Empty** (no requests in the term) | Criteria card works. Priority overview: "Bu dönemde talep yok." |
| **No priorities set** | The distribution bar reads "Tüm talepler Normal". The overview filter "Yalnızca Normal dışı" shows "Normal dışı öncelik yok · Talepler'de `p` ile ayarlayın" |
| **Loading** | Static rows for criteria counts ("…"). The impact card waits for the run (island) |
| **Error** | Save failed: the dialog or page keeps the unsaved order with "Kaydedilemedi · Yeniden dene". Impact load failed: "Politika etkisi yüklenemedi" on the card only |
| **Partial** | The run hit its time limit: the impact card says "Süre sınırında durdu; en iyi bulunan sonuç" and keeps the numbers |
| **Stale published plan** | The policy changed after publishing: banner "Yayındaki plan eski sırayla üretildi" with **Bu politikayla önizle** (§5.1) |
| **Over-limit** | Yüksek > 10 % of requests: warning "Yüksek öncelik çok yaygın (%14); fark yaratmayabilir". Saving is allowed |
| **Permission denied** | Changing the order needs `planning.admin`: others see the list read-only with "Sırayı yalnızca yönetici değiştirebilir". Setting priorities needs `planning.edit`: viewers see the priority cells without the editor |

## 10. Accessibility

- The criteria list is an `<ol>`. Each item is focusable with an accessible name "2. Öncelik: Yüksek, Normal'den önce". Reorder by keyboard: focus an item, `Space` picks up, `↑/↓` move, `Space` drops, `Esc` cancels (dnd-kit pattern). The **⌃ / ⌄ buttons** are always present as the non-drag path (labelled "Yukarı taşı" / "Aşağı taşı").
- Live region on reorder: "Kilitler 1. sıradan 3. sıraya taşındı. Kaydedilmedi." On save: "Politika kaydedildi; bir sonraki çözümde etkili."
- The priority popover is a radio group (`role="radiogroup"` in SegmentedGlass) with arrow keys. The source line is announced after the value ("Yüksek, kişiden").
- The distribution bar has `role="img"` with an `aria-label` carrying the full numbers. The numbers are also visible text.
- The confirm is an `alertdialog`. Focus starts on the reason field. "Vazgeç" is reachable first in tab order after the field.
- Contrast: the criteria card is regular glass over the scene, and its rows are opaque fill-2, so label-1/label-2 hold ≥ 6.4:1. Tier glyphs are never colour-only (word always present).

## 11. Motion moments (hand to the motion agent; names only)

| Moment | Suggested pattern |
|---|---|
| `policy.reorder` (drag and keyboard move) | §7 drag lift / settle on the moved card; siblings §6 reflow (3 items) |
| `policy.preset-applied` | §6 reflow to the preset order |
| `policy.saved` | §10 check + §5 toast |
| `priority.tier-change` | §2 segmented thumb |
| `priority.distribution-update` | §11 ticker on the numbers; bar segments `scaleX` (no stagger) |
| `policy.impact-card-arrival` | §19 island → result card morph (shared with Studio) |
| `policy.counterfactual-start` | §19 island |

## 12. i18n (TR + EN)

- Namespace `policy.*` and `priority.*`.
- Criteria names: Kilitler / Locks · Öncelik / Priority · En çok ders / Most classes placed. Tiers: Yüksek / High · Normal / Normal · Düşük / Low. Sources: talep / request · kişiden / from person · programdan / from program · varsayılan / default.
- **Long Turkish strings**: "Her şey sığmadığında kimin yer vereceğini bu sıra belirler." (58). "Kilitli dersler, daha çok ders yerleşsin diye taşınabilir veya yerleşmeyebilir." (79, wraps in the dialog). "Politikanın belirlediği 4 durum" (31). "Yüksek öncelik çok yaygın (%14); fark yaratmayabilir" (51).
- Step references: TR "adım 1 · kilit", EN "step 1 · lock". Rank numerals are the same in both.
- Percentages: TR "%2,5", EN "2.5%" via `Intl.NumberFormat`.
- Course codes and room codes are not translated. Sentences that name them use the `tr-suffix` helper ("A 306'dan", "ING 402'nin").

## 13. API endpoints (backend tickets)

| Ticket | Endpoint | Purpose |
|---|---|---|
| P19-P-01 | Solver: `params.policy = {order:["locks","priority","most_placed"], tiers:["high","normal","low"]}`, lexicographic (locks kept → placed per tier → total placed → soft). Per-event effective priority passed by the bridge. Tie-break: event-weeks | Policy semantics (§4). Replaces the fixed D3 relaxation order |
| P19-P-02 | `GET /terms/{term_id}/policy` → `{order, updated_at, updated_by, is_default}`; `PUT /terms/{term_id}/policy {order, reason}` (planning.admin, audited `policy.update`) | Policy page |
| P19-P-03 | `GET /terms/{term_id}/policy/impact?order=` → the last run of this term with that order: `{run_id, locks_lost:[{request_id, course, section}], placed}` or `null` | Consequence confirm |
| P19-P-04 | `PUT /requests/meetings/{id}/priority`, `PUT /people/{id}/priority`, `PUT /programs/{id}/priority` with `{tier\|null, note?}`; `POST /priorities/bulk {subject_type, ids[], tier}` | Priority editor and bulk |
| P19-P-05 | `GET /terms/{term_id}/priorities?subject=requests\|people\|programs&non_default=true&q=&offset=&limit=` → rows with `{tier, source, note, updated_by, updated_at}` + `GET /terms/{term_id}/priorities/summary` → `{high, normal, low, high_share}` | Overview + distribution bar |
| P19-P-06 | `GET /runs/{run_id}/policy-impact` → `{order, locks:{kept, total, conflicts:[…]}, tiers:{high:{placed,total}, …}, placed:{events, total}, decisive:[{winner:{request_id, course}, loser:{request_id, course, outcome}, step, text:{tr,en}}]}` | Politika etkisi card |
| P19-P-07 | `MatchingRow.policy_step` and `reasons[].winner` in `GET /runs/{run_id}/matchings` (moderation P19-M-06) | Matchings step column |
| P19-P-08 | `POST /runs` accepts `params.policy` overrides for counterfactual child runs (with `parent_run_id`, `stability`) | Bu politikayla önizle |

## 14. Open questions for the product owner

1. Three tiers, or four (add "Kritik" above Yüksek for legally required classes, e.g. accreditation labs)? Three keeps the meaning sharp.
2. Who may set **person**-level priority: any coordinator, or only admins? A person-level High affects every request of that person.
3. Should a lock-conflict decision ("MAT 112 §1'i tut") be remembered for future terms as a suggestion (suggestions spec), or stay term-only?
4. Exam terms (2026-FINAL): should the default order be different (most exams placed first), given that exam locks are often the planner's tentative choices?
5. Is the 10 % soft limit on High right, and should it be per unit (each faculty gets its own 10 %) rather than per term?
