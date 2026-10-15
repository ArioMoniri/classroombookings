# Phase 19 · Learned suggestions and resettable memory

Owner: design-pro (Phase 19 surfaces) · Status: spec v1.0 (2026-10-15)
Surfaces: a **suggestion card** component that appears in three places (moderation profile, Generator Studio rules step, intake review), a **Öneriler** saved view in Moderasyon › Tercihler, and **Ayarlar › Öğrenme ve öneriler** (admin) for memory and reset.
User decisions (ROADMAP Phase 19, 2026-10-15): suggestions are **never auto-applied**. Accepting one adds a **soft** preference. Hard-rule integrity (100/100 or explained infeasibility) is unchanged. Memory reset works per person, per term or for everything, is admin-only, audited, and undoable for 30 days.
Related: [`phase19-moderation.md`](phase19-moderation.md) (profile, patterns), [`phase19-intake.md`](phase19-intake.md) (review), [`../generator-studio.md`](../generator-studio.md) §3.3 (rule cards, review tray), [`liquid-glass.md`](liquid-glass.md), [`motion.md`](motion.md) (motion is owned there).

---

## 0. BLUF

- **A suggestion is a proposed soft preference plus its evidence.** Example (real rows, person shortened to initials): "Dr. Öğr. Üyesi E. Y. teorik derslerini Pazartesi sabahı istiyor. Görüldü: 2 dönemin 2'sinde (2026-BAHAR PHAR 240 §1 Pzt 08:30–10:50 · 2026-GÜZ PHAR 205/241 Pzt 09:20–11:40)." The card shows a confidence level in words and as a meter.
- **Three actions, nothing automatic.** Accept adds a soft preference (weight Normal, this term) and can be undone. Dismiss takes an optional reason, and the suggestion only returns with new evidence. Snooze lasts until the next solve, for 7 days, or until next term. There is no "accept all automatically" switch anywhere (we deliberately do not copy Canny's Autopilot banner).
- **Where cards appear**: the person profile (patterns → suggestions), the Studio rules step (a "Öğrenilen öneriler" group in the existing review tray), and intake review (suggestions related to the rows being imported, staged until commit like everything else there).
- **Dashed means "not applied yet"**, the same visual language as the Studio `SourceChip` proposal state. A card becomes a solid rule with source chip **Öneri** once accepted.
- **Memory reset** lives in Ayarlar › Öğrenme ve öneriler (`planning.admin` only), with three scopes (Kişi / Dönem / Tümü). Every reset needs a reason and a confirm ("Tümü" also needs the typed word **SIFIRLA**), writes an audit event, and appears under "Son sıfırlamalar" with **Geri al · 27 gün kaldı** until it is purged after 30 days.
- **First use is honest.** Until two terms of evidence exist, the card area explains what is needed instead of showing weak guesses.

## 1. User stories

| # | As a… | I want to… | So that… | Acceptance |
|---|---|---|---|---|
| S1 | coordinator | be told when an academician has a stable habit that this term's requests don't state | the new plan respects what people need without them re-asking | a card on the profile and in the Studio with evidence and confidence |
| S2 | coordinator | see why the system thinks so | I trust or reject it quickly | "Kanıtı göster" lists every occurrence with term, course, day/time, room and source cell |
| S3 | coordinator | accept with one click | it becomes a normal soft preference I can edit later | Accept → the rule appears in Tercihler with source chip "Öneri" and an Undo toast (8 s) |
| S4 | coordinator | dismiss a wrong suggestion and say why | it stops coming back | Dismiss → optional reason chips. The same suggestion does not reappear unless a new term adds evidence |
| S5 | coordinator | postpone a suggestion | I can decide after the next solve | Ertele → until the next solve / 7 days / next term |
| S6 | coordinator | see suggestions while importing a new term | the habits carry over at the moment the data arrives | an "Öneriler 3" group in İnceleme. Accepting stages a soft preference that is created only at commit |
| S7 | admin | wipe what the system learned about one person | their circumstances changed (new role, health) | Kişi reset with reason and confirm, an audit event, and Undo for 30 days |
| S8 | admin | exclude an atypical term from learning | the 2026-FINAL exam period doesn't teach lecture habits | Dönem reset: the term's evidence is dropped and suggestions are recomputed |
| S9 | admin | reset everything | we start clean after a reorganisation | Tümü reset with typed confirmation, audit, and Undo for 30 days |
| S10 | academician (later, read-only) | not be surprised | the plan never changes because of a guess | accepted suggestions are visible as preferences with source "Öneri" in the profile |

## 2. References

| # | App · screen (Mobbin, web) | Pattern we take | Avoid |
|---|---|---|---|
| R1 | [AirOps · Recommended prompts](https://mobbin.com/screens/ae0f151a-f195-43ba-9f2f-9c3ff74bfa10) | One row per suggestion with a one-line rationale, small evidence chips, and **✕ / ✓ per item** plus "Decline all · Accept all" in the header | "Accept all" as the main button; ours is secondary and asks to confirm |
| R2 | [Peec AI · Actions › Impact (Todo / History)](https://mobbin.com/screens/a33f472c-a45f-4a1d-bcab-6aa85d66c70e) | **Todo / History** tabs for open vs decided suggestions, and compact ✕ ✓ at the row end | coloured type tags |
| R3 | [Canny · Autopilot](https://mobbin.com/screens/7b436878-cfec-48e7-b198-365e5c17e947) | Suggestion with **source** ("Imports") and actions **Looks good / Merge / Move / Delete** | the "Automate actions" banner (auto-accept), which we explicitly reject |
| R4 | [Contra · Indy dismiss reasons](https://mobbin.com/screens/2d2dcef8-11e2-4f07-b309-513aed0309cd) | "Let me know why … I'll use your input to refine future recommendations": **checkbox reasons + Skip (no specific reason)** after Dismiss | — |
| R5 | [Rox · Recommended action with "1 source"](https://mobbin.com/screens/3f692f59-31ca-4254-8d47-1112661613a1) | A recommendation card with **source count** and "AI can make mistakes. Please double-check sources." | — |
| R6 | [ChatGPT · Saved memories, delete one](https://mobbin.com/screens/dd9efafc-19e8-4f22-a3da-f2b3b0ec7a71) | A memory list with search, and a delete confirm that **quotes the item and states the consequence** ("may not remember this information going forward") | — |
| R7 | [Mistral Le Chat · Memories](https://mobbin.com/screens/b2c011be-a7e2-4b9d-a63b-86908762ef26) and [Base44 · Saved facts](https://mobbin.com/screens/b9e26ebf-676c-4984-af5b-d25c31ec2f08) | "Enabled" state next to the title, dated entries, edit/delete per entry, and an "updated" toast | — |
| R8 | [Supabase · Assistant opt-in level](https://mobbin.com/screens/d150d11b-ea33-414c-9d3c-a00b0d92f186) | Org-wide levels with plain consequences, used for the "Önerileri göster / Öğrenmeyi sürdür" switches | — |
| R9 | [WorkOS · Edit priority](https://mobbin.com/screens/d9f96ee3-37ca-4fa3-9cce-f0117e4f1935) | A confirm that explains the rule before saving. Used in the reset dialog's "what is kept" paragraph | — |

Component sites: beautifului.dev **Recommendation Card** ("Agent suggestion with a confidence meter and actions", registry `/r/recommendation-card.json`, MIT © 2026 Shane Levine) as the base of `SuggestionCard`. beUI **Citations** (`@beui/citations`, MIT) as a pattern for the collapsible evidence list.

## 3. Interaction patterns chosen, and why

| Pattern | Why |
|---|---|
| **Evidence-first card** (claim · proposed preference · evidence · confidence · actions) | The user asked for evidence ("seen in 3 terms"). Leading with evidence makes accept/dismiss a judgement about facts, not about a black box |
| **Confidence as word + meter + reason** ("Orta · 2/2 dönem, son dönem dahil, çelişen yok") | A bare percentage invites false precision. Three levels plus the reason are enough to act on (G4: never colour alone) |
| **Accept = soft preference only**, weight picked on a split button | Matches the user decision. Hard rules stay with the Studio and the coordinator |
| **Dismiss with optional reason** (R4) | Reasons improve the engine and explain to colleagues why a habit was ignored |
| **Snooze with concrete horizons** | "Later" is vague. "Bir sonraki çözüme kadar" ties the delay to the planner's real cadence |
| **Todo / History tabs** (R2) | Decided suggestions stay inspectable (who accepted what), which supports the audit and undo story |
| **Staged accept in intake** | Intake promises that nothing is saved before commit. A suggestion accepted there becomes part of the commit, not an immediate write |
| **Reset as a settings action with scope, reason, confirm, audit and a visible undo window** (R6, R7) | Destructive, admin-only, and legally relevant (KVKK right to erasure), so it has to be deliberate and reversible for 30 days, then really gone |

## 4. What the engine learns (so the UI can explain it)

| Kind (`kind`) | Learned from | Proposed soft preference (Studio rule kind) | Example (real data) |
|---|---|---|---|
| `day_part` | a person's requests across terms | `day_window` (soft, scoped to the person's events; existing kind) | E. Y.: Monday morning theory lectures (Bahar R545 Pzt 08:30–10:50; Güz R38 Pzt 09:20–11:40) |
| `lab_pattern` | consecutive lab sections on one day | **new** soft kind `same_day_blocks` for the course family (solver ticket P19-S-10) | E. Y.: lab sections morning + afternoon on one day (Bahar R855–R856 Per 09:20–12:30 / 13:30–16:40; Güz R447–R449 Çar, same times) |
| `course_room` | a course's definitive room in repeated terms, or repeated manual moves into a room | `room_preference` (existing) | PHAR 240 §1 in A 206 (Bahar R545). This needs a second term with the same room before it is suggested |
| `building` | free-text notes repeated across rows | `building_preference` (existing; soft avoid/prefer) | ING 302 §10 "Mümkünse B Blok olmasın" (Bahar R366 and R636): seen twice in one term, so it qualifies through the within-term rule |
| `manual_fix` | the coordinator's own edits after solving (timetable moves, diagnosis fixes, chat applies), repeated ≥ 2 times | the matching soft rule | "MBT 698 + MBT 598 için A 104, A 103, A 105 dersliklerini kullan" applied as a fix in run #5 (usability report 3.9). It qualifies only if the same fix is applied again in a later run or term |

**Thresholds (defaults, admin-tunable):** a suggestion is shown when support is ≥ 2 terms, or ≥ 2 independent rows or edits within one term, **and** confidence ≥ 0,50. Confidence combines support (seen / taught), recency (the last term counts double), consistency (same room/time vs only a similar one), and contradicting evidence (a term where the person asked for the opposite lowers it). Levels: **Yüksek** ≥ 0,80 · **Orta** 0,60–0,79 · **Düşük** 0,50–0,59.

The engine never proposes anything that would conflict with a hard rule already in the term. Suggestions that duplicate an existing preference are suppressed. A suggestion that partly overlaps one becomes an "update" card ("Mevcut tercihi genişlet: Pzt → Pzt + Sal sabahı").

## 5. The card

### 5.1 Desktop anatomy (360–560 px wide, depending on the surface)

```
╭╌ inset card, dashed hairline (not applied yet) ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╮
┊ ✦ Öneri · Kişi alışkanlığı                                   Orta ▮▮▯  ⓘ                ┊
┊ Dr. Öğr. Üyesi E. Y. teorik derslerini Pazartesi sabahı istiyor.                        ┊
┊ Eklenecek yumuşak tercih: "E. Y.'nin teorik dersleri mümkünse Pazartesi 08:30–12:30     ┊
┊ arasında olsun" · Ağırlık Normal · Bu dönem                                             ┊
┊ Kanıt · 2 dönemin 2'sinde                                         [Kanıtı göster ▾]     ┊
┊   2026-BAHAR  PHAR 240 §1  Pzt 08:30–10:50  A 206   v5.xlsx · R545                      ┊
┊   2026-GÜZ    PHAR 205/241 Pzt 09:20–11:40  B 202   güz_v2.xlsx · R38                   ┊
┊ Bu dönem etkilenen: 1 ders (PHAR 341 §1 · Sal 08:30 istendi) ⚠ çelişki olabilir          ┊
┊ (Kabul et · Normal ▾)   [Yoksay]   [Ertele ▾]                                           ┊
╰╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╯
```

- **Header**: the `sparkles` glyph (lucide, label-2, A3) + "Öneri · {kind label}" + confidence (word, a 3-step meter, and an ⓘ popover with the reason: "2/2 dönem · son dönem dahil · çelişen talep yok").
- **Claim**: one sentence in `type-headline`, naming a person, course or program, and a habit.
- **Proposed preference**: the exact Studio rule sentence (`rule-sentence.ts`), so what is accepted is what the Studio will show. Weight and scope are shown.
- **Evidence**: collapsed to "Kanıt · 2 dönemin 2'sinde" and expandable to a list with provenance (file · cell), each row linking to the timeline item.
- **Impact line**: what it touches this term, plus a warning when it may fight this term's explicit requests. A request always wins over a learned habit, and the card says so in the ⓘ.
- **Actions**: one tint **Kabul et** split button (weight menu: Düşük / Normal / Yüksek; scope menu: Bu dönem / Kalıcı, where Kalıcı needs `planning.admin`), **Yoksay** (ghost), **Ertele ▾** (ghost; Bir sonraki çözüme kadar · 7 gün · Gelecek döneme kadar).

### 5.2 After an action

| Action | Card becomes | Elsewhere |
|---|---|---|
| Kabul et | solid card that collapses to a one-line receipt: "✓ Yumuşak tercih eklendi · Tercihler'de gör · Geri al". Leaves the Todo list after 8 s | rule appears in the term draft (Studio rules list, Moderasyon › Tercihler) with source chip **Öneri**. Audit `suggestion.accept`. Staged changes +1 |
| Yoksay | inline reason chips (R4): "Artık geçerli değil" · "Yanlış kişi eşleşmesi" · "Bu dönem farklı" · "Diğer…" · **Nedensiz atla**. Then a receipt with Geri al | audit `suggestion.dismiss {reason}`. Returns only when a new term adds evidence |
| Ertele | receipt "Bir sonraki çözüme kadar ertelendi · Geri al" | resurfaces at the chosen horizon |

### 5.3 Where cards surface

| Surface | Placement | Filter | Behaviour specific to the surface |
|---|---|---|---|
| **Moderation profile** (`/moderation/people/[id]`) | under "Alışkanlıklar" (max 2 inline) + **Öneriler** tab with Todo / History | this person | Accept writes to the current term draft |
| **Generator Studio, step 3 "Tercihler ve kurallar"** | a group **"Öğrenilen öneriler 4"** at the top of the existing review tray (`studio/review-tray.tsx`), next to AI and upload proposals | people and courses in this run's scope | Accept moves the card into the rule list (same `layoutId` travel as other tray proposals). The rail shows the count. They are never preselected |
| **Intake review** (`/onboarding/[jobId]?step=review`) | collapsible group **"Bu içe aktarmayla ilgili öneriler 3"** above the rows, plus a ✦ marker on the related rows | people and courses present in this job | Accept **stages** the preference (state "Kaydedilince eklenecek"). It is created in the same transaction as the commit, and discarded if the job is abandoned |
| **Moderasyon › Tercihler** | saved view **"Öneriler"**: one row per open suggestion (table form, R1) | term | Bulk "Kabul et" needs a confirm naming the count. There is no "accept all" without a selection |

Not on the dashboard and not as toasts or notifications: suggestions are pull, not push (rule A9 spirit, and no nagging).

## 6. Memory and reset (Ayarlar › Öğrenme ve öneriler)

```
┌ settings content (plain) ────────────────────────────────────────────────────────────────────┐
│ Öğrenme ve öneriler                                                         Yalnızca yönetici │
│ Önerileri göster                         Planlayıcılar öneri kartlarını görür.        [● açık]│
│ Öğrenmeyi sürdür                         Yeni dönemler ve düzenlemeler belleğe eklenir.[● açık]│
│ En az kanıt                              [2 dönem ▾]     En az güven  [Orta ve üstü ▾]        │
│ ── Bellek ──────────────────────────────────────────────────────────────────────────────── │
│ Kapsanan dönemler   2026-BAHAR · 2026-GÜZ            Hariç tutulan: 2026-FINAL (sınav)       │
│ Öğrenilmiş alışkanlık  {n} · Açık öneri {n} · Kabul edilen {n}                                │
│ ── Sıfırla ─────────────────────────────────────────────────────────────────────────────── │
│ Bir kişinin belleği     [Kişi seçin ▾]                                    [Sıfırla…]          │
│ Bir dönemin katkısı     [Dönem seçin ▾]                                   [Sıfırla…]          │
│ Tüm bellek                                                                 [Tümünü sıfırla…]  │
│ ── Son sıfırlamalar ────────────────────────────────────────────────────────────────────── │
│ 15 Eki 15:02 · Kişi · Öğr. Gör. S. K. · "görev değişikliği" · Fatih Bey   Geri al · 30 gün    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

The `{n}` fields are live counts from `GET /learning/memory/summary`.

**Confirm dialog** (alertdialog, `rounded-3xl`, thick):

> **Öğr. Gör. S. K. için öğrenilenler sıfırlansın mı?**
> Silinecek: bu kişiye ait öğrenilmiş alışkanlıklar ve açık, ertelenmiş veya yoksayılmış öneriler.
> Kalacak: daha önce kabul edilmiş tercihler (artık normal tercihlerdir), talepler ve planlar.
> 30 gün içinde "Son sıfırlamalar"dan geri alabilirsiniz; sonra kalıcı olarak silinir.
> Neden (zorunlu): [__________________]
> [Vazgeç]  (Sıfırla)

- **Tümü** adds: "Onaylamak için **SIFIRLA** yazın" (EN: type **RESET**). The button stays disabled until the word matches (Turkish-aware casefold, so "sıfırla" also matches).
- **Dönem** explains the effect: "2026-FINAL bundan sonra öğrenmede kullanılmaz; öneriler yeniden hesaplanır (yaklaşık 1 dk)."
- Each reset → audit `learning.reset {scope, subject, reason, counts}` → toast "Sıfırlandı · Geri al" → row in Son sıfırlamalar with a countdown ("27 gün kaldı"). Undo restores exactly what was removed and writes `learning.reset.undo`.
- After 30 days the data is purged by a job, and the row reads "Kalıcı olarak silindi · 14 Kas". The audit entry stays (no personal content beyond the subject id).
- A per-person reset is also in the profile ⋯ menu ("Öğrenilenleri sıfırla…", admin only), using the same dialog.

## 7. Mobile layout (≤ 390 px)

```
┌ 390 ──────────────────────────────┐
│ ‹ E. Y.              Öneriler 1   │
│ [Bekleyen 1] [Geçmiş 3]           │
│ ╭╌ dashed inset card ╌╌╌╌╌╌╌╌╌╌╌╮ │
│ ┊ ✦ Kişi alışkanlığı   Orta ▮▮▯ ┊ │
│ ┊ Teorik dersler Pazartesi      ┊ │
│ ┊ sabahı.                       ┊ │
│ ┊ Kanıt · 2 dönemin 2'sinde  ▾  ┊ │
│ ┊ ┌───────────────────────────┐ ┊ │
│ ┊ │     Kabul et · Normal ▾   │ ┊ │  ← 44 px, full width
│ ┊ └───────────────────────────┘ ┊ │
│ ┊ [Yoksay]          [Ertele ▾]  ┊ │
│ ╰╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╯ │
└───────────────────────────────────┘
```

- Cards stack full width with a 12 px gap. Evidence opens in place. Ertele and the reason chips open as bottom sheets.
- Swipe on the card: right = Kabul et, left = Yoksay. This is optional and also in the buttons, never gesture-only (beUI Swipeable List pattern, MIT).
- The Studio tray on phones is already a bottom sheet (generator-studio.md §8). The suggestions group sits at its top.
- Settings › Öğrenme: one column. Each reset row opens the confirm as a full-height sheet with the reason field focused.

## 8. Component list

| Need | Component | Source · licence | Status |
|---|---|---|---|
| Suggestion card | new `suggestions/suggestion-card.tsx` | ours, based on beautifului **Recommendation Card** (`/r/recommendation-card.json`) · MIT © 2026 Shane Levine. Port with a licence header and a `SOURCES.md` row | **new (port)** |
| Evidence list | new `suggestions/evidence-list.tsx` | ours; pattern from beUI **Citations** (`@beui/citations`) · MIT | **new** |
| Confidence meter | inside the card: 3-step `meter` | ours | **new** |
| Split accept | `ui/button.tsx` + `ui/dropdown-menu.tsx` | shadcn · MIT | reuse |
| Snooze / reason | `ui/dropdown-menu.tsx`, `ui/chip.tsx` (reason chips) | MIT / ours | reuse |
| Source chip "Öneri" | `studio/source-chip.tsx`, add `SourceKind = "LEARNED"` (icon `sparkles` variant `history`) | ours | **extend** |
| Studio tray group | `studio/review-tray.tsx` | ours | **extend** (group header + kind) |
| Intake group | in `onboarding` review (intake spec) | ours | **extend** |
| Tercihler saved view | `classes/class-table.tsx` core with `preferenceCols` | MIT | reuse |
| Settings rows | settings-row grammar (references.md H21, liquid-glass.md §16 item 5), `ui/switch.tsx`, `ui/select.tsx` | MIT | reuse |
| Reset dialog | `ui/dialog.tsx` (alertdialog), `ui/input.tsx` with `useShake` for a wrong typed word | MIT | reuse |
| Undo toasts | `ui/sonner.tsx` | MIT | reuse |
| Mobile swipe | `@beui/swipeable-list` (optional) | beUI · MIT | optional import |

## 9. Tokens

| Use | Token |
|---|---|
| Card (pending) | `Card variant="inset"` (fill-2, no blur: it sits inside panels, G2) + 1 px **dashed** `--hairline-strong` |
| Card (accepted receipt) | solid `--hairline`, `check-circle-2` in `--status-feasible-fg` |
| Sparkle glyph | `--label-2` (not the accent, A3/G3). Accent only on the primary action |
| Confidence meter | filled steps `--label-1` at 60 %, empty steps `--fill-2`. The word is always shown |
| Conflict warning line | `--status-warning-*` + `alert-triangle` |
| Settings | plain content surface, `rounded-2xl` group cards, rows 44 px |
| Destructive button | `variant="destructive"`, only inside the dialog (A6) |
| Spacing | card padding 16, inner gap 8, evidence row 28 px |
| Type | claim `type-headline`; sentence `type-body`; evidence `type-footnote` (mono for cell refs) |
| Motion | `motion.md` tokens only |

## 10. States

| State | What the user sees |
|---|---|
| **First use** (fewer than 2 terms of evidence, or learning just turned on) | An explainer instead of cards (`EmptyState`, left-aligned, no animation): "Öneriler, en az iki dönemin verisinden sonra başlar. Şu an: 2026-BAHAR (yayında) ve 2026-GÜZ (planlama listesi) var; 2026-GÜZ çözülüp yayınlanınca öneriler oluşur." With the within-term rule, cards that qualify within one term (repeated notes, repeated manual fixes) may still appear and are labelled "tek dönem" |
| **Empty** (nothing to suggest) | Profile: "E. Y. için öneri yok · 2 dönemde tutarlı bir alışkanlık bulunamadı." Studio tray: the group is hidden (no empty group). Intake: hidden |
| **All handled** | "Tüm öneriler gözden geçirildi · 4 kabul, 1 yoksayıldı · Geçmiş ›" |
| **Loading** | Card-shaped static placeholders (max 2). Suggestions load after the main content and never block it |
| **Recomputing** (after a term reset or new term) | A one-line notice "Öneriler yeniden hesaplanıyor…" with the thinking shimmer on the text only (motion.md pattern §17). Existing cards stay visible but disabled |
| **Error** | "Öneriler yüklenemedi · Yeniden dene" in place of the group. The rest of the surface works |
| **Partial** | Some evidence rows point to archived terms: they show "arşiv" and open read-only |
| **Turned off** (admin) | Cards hidden everywhere. Profile Öneriler tab: "Öneriler yönetici tarafından kapatıldı." The settings page shows the switches |
| **Memory reset** (person) | Profile: "Bu kişinin öğrenilenleri 15 Eki'de sıfırlandı · Geri al (30 gün)" (the undo link is admin-only) |
| **Permission denied** | `planning.view`: cards are visible without actions, with "Önerileri kabul etmek için planlama düzenleme izni gerekir". Settings › Öğrenme for non-admins: the route is hidden from nav, and direct access shows the standard 403 |

## 11. Accessibility

- The card is an `<article aria-labelledby="claim-id" aria-describedby="evidence-id">`. The confidence meter is `role="meter"` with `aria-valuenow`, `aria-valuemin=0`, `aria-valuemax=1` and `aria-valuetext="Orta güven, 2 dönemin 2'sinde"`.
- Keyboard: in a card list, `j/k` (or `[ ]`) move between cards, `a` accepts, `d` dismisses (opens the reasons), `s` snoozes, `Enter` toggles the evidence, and `⇧A` opens the weight menu. In the reset dialog, focus starts on the reason field, and `Esc` cancels.
- Focus after an action goes to the next pending card, or to the "Tüm öneriler gözden geçirildi" heading if none are left.
- Live region (polite): "Öneri kabul edildi: yumuşak tercih eklendi. Geri almak için Ctrl+Z." The undo toast action is a real button.
- The dashed border is not the only "pending" cue: the header reads "Öneri" and the receipt reads "eklendi" (G4).
- Contrast: cards are opaque inset fills inside panels, so text contrast is label-1/label-2 on fill-2 (≥ 6.4:1). The warning line uses status-warning fg on tint (≥ 5.02).
- Swipe actions have button equivalents. Targets are 44 px on touch.

## 12. Motion moments (hand to the motion agent; names only)

| Moment | Suggested pattern |
|---|---|
| `suggestion.group-first-reveal` | §6 stagger (first 6 only, first reveal only) |
| `suggestion.accept-to-rules` (Studio tray → rule list) | §6 shared `layoutId` travel (same as "Accept proposal", motion.md §3.4) |
| `suggestion.accept-receipt` | §10 check draw + collapse via `layout` |
| `suggestion.dismiss` / `snooze` | §6 pop out of layout + §5 undo toast |
| `suggestion.evidence-expand` | §6 `layout` height (≤ 40 rows) |
| `suggestion.recomputing` | §17 thinking shimmer (text only) |
| `memory.reset-confirm` | §1 dialog; §9 shake on a wrong typed word |
| `memory.reset-done` / `undo` | §5 toast |

## 13. i18n (TR + EN)

- Namespace `suggestions.*` and `learning.*`.
- Kind labels: Kişi alışkanlığı / Personal habit · Laboratuvar düzeni / Lab pattern · Ders–oda / Course–room · Bina tercihi / Building preference · Tekrarlanan düzeltme / Repeated fix.
- Evidence plural: TR "{k} dönemin {n}'sinde" with `tr-suffix` ("2 dönemin 2'sinde", "4 dönemin 3'ünde"); EN "in {n} of {k} terms". Single term: "tek dönemde {n} kez" / "{n} times in one term".
- Confidence words: Yüksek / High, Orta / Medium, Düşük / Low.
- **Long Turkish strings**: "Bu içe aktarmayla ilgili öneriler" (33), "Kaydedilince eklenecek" (22), "Öneriler, en az iki dönemin verisinden sonra başlar" (51), "Bu kişinin öğrenilenleri 15 Eki'de sıfırlandı" (45). The card claim wraps to at most 3 lines and is never truncated, because truncating a claim changes its meaning.
- Typed confirmation word per locale: **SIFIRLA** (tr), **RESET** (en). Either is accepted in either locale, so a bilingual admin is not blocked.
- Rule sentences come from `rule-sentence.ts` in both languages, so an accepted preference reads the same in the Studio.

## 14. API endpoints (backend tickets)

| Ticket | Endpoint | Purpose |
|---|---|---|
| P19-S-01 | `GET /suggestions?term_id=&person_id=&course_id=&program_id=&surface=studio\|moderation\|intake&job_id=&state=open\|snoozed\|dismissed\|accepted&offset=&limit=` → `SuggestionOut {id, kind, subject:{person_id?, course_id?, program_id?}, claim:{tr,en}, proposal:{rule_kind, params, sentence:{tr,en}, weight, scope}, evidence:[{term_code, request_id?, assignment_id?, audit_id?, provenance?, text:{tr,en}}], support:{seen_terms, of_terms, within_term}, confidence, level, impact:{term_id, request_ids[], conflicts:[{request_id, text}]}, state, snoozed_until, decided_by?, decided_at?}` | cards on every surface |
| P19-S-02 | `POST /suggestions/{id}/accept {weight?, scope?, term_id, job_id?}` → `{preference_id}` or `{staged:true}` when `job_id` is given | Accept. Creates a soft rule only (server rejects `hardness=hard`) |
| P19-S-03 | `POST /suggestions/{id}/dismiss {reason_code?, note?}` · `POST /suggestions/{id}/snooze {until:"next_solve"\|"P7D"\|"next_term"}` · `POST /suggestions/{id}/restore` | Dismiss / Snooze / Undo |
| P19-S-04 | `POST /suggestions/bulk {ids[], action:"accept"\|"dismiss"\|"snooze", ...}` | Tercihler › Öneriler bulk |
| P19-S-05 | `GET /learning/settings` · `PUT /learning/settings {suggestions_enabled, learning_enabled, min_terms, min_confidence, excluded_term_ids[]}` (planning.admin) | Settings switches |
| P19-S-06 | `GET /learning/memory/summary` → `{terms:[{term_code, included}], patterns, open, accepted, dismissed}` | Bellek section |
| P19-S-07 | `POST /learning/reset {scope:"person"\|"term"\|"all", person_id?, term_id?, reason}` → `{reset_id, counts, undo_until}` (planning.admin) | Reset |
| P19-S-08 | `GET /learning/resets` · `POST /learning/resets/{id}/undo` (≤ 30 days, planning.admin) · a purge job at day 30 | Son sıfırlamalar + undo |
| P19-S-09 | Commit of an intake job creates staged suggestion preferences in the same transaction (extends P19-I-06/08) | Intake staging |
| P19-S-10 | Solver: soft constraint kind `same_day_blocks` (sections of one course family on the same day, morning + afternoon) added to `CONSTRAINT_KINDS` with a rule sentence in TR/EN | `lab_pattern` suggestions |

Audit kinds: `suggestion.accept`, `suggestion.dismiss`, `suggestion.snooze`, `suggestion.restore`, `learning.settings.update`, `learning.reset`, `learning.reset.undo`, `learning.purge`.

## 15. Open questions for the product owner

1. Minimum evidence: is **2 terms** the right default, or should one term with repeated rows (e.g. ING 302 §10 "B Blok olmasın" twice) also produce suggestions? This spec allows both, labelled "tek dönem".
2. Should "Kalıcı" (persistent, cross-term) acceptance exist at all, or should every accepted suggestion be term-scoped and re-suggested next term?
3. Do academicians ever see suggestions about themselves (for example in a future self-service portal), or are suggestions strictly coordinator-facing?
4. KVKK: is 30 days the right undo window for a person reset, given an erasure request from the academician? A legal erasure request may need immediate purge (an "Hemen kalıcı sil" option for admins).
5. Should dismiss reasons be visible to other coordinators (shared memory) or private to the person who dismissed?
