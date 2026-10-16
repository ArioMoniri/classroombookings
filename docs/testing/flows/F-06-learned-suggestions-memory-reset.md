# F-06 · Learned suggestions: accept / reject / snooze, then the admin's memory reset and undo

Personas: **admin** (coordinator: accepts and rejects; administrator: resets and erases), **planner** (may decide suggestions, may not reset). Viewports: desktop, tablet, phone.
Owner decisions (ROADMAP Phase 19):
- Learned suggestions are **never auto-applied**. Accepting one adds **one soft preference** (learned weight 5 < explicit soft preference 10, Q7). Hard-rule integrity is unchanged.
- A suggestion needs **2 terms of evidence, or 3 repeats in one term**.
- Memory reset works per person, per term or for everything. It is **admin only**, audited, and **undoable for 30 days**.
- A **KVKK erasure** purges at once. The undo window does not apply to it.
- Suggestions are pull, not push: no toasts, no bell, nothing on the dashboard.

Testable on `b75047b`: yes (L1–L4 and the UI landed: `components/learning/*`, `/moderation/learning`). The P19 UI follow-up (2026-10-16) added the server-side undo of any decision (`POST /learning/suggestions/{id}/restore`, "Geri al" on the receipt and in Geçmiş) and the accept scope (this term vs persistent); `smartsched/frontend/e2e/followup.phase19.spec.ts` test 5 proves S03 (accept, Geri al, persistent), S04 (reject, Geçmiş → Geri al) on the Bahar suggestions.

## Preconditions

1. Full stack (Bahar + Güz imported, both full-term runs published), seed applied.
2. Compute the memory and the suggestions for the current term, as admin:
   ```bash
   curl -fsS -X POST "$API/learning/refresh" "${H[@]}" -d "{\"term_id\":$GUZ_ID}" | jq -c .
   curl -fsS "$API/learning/suggestions?term_id=$GUZ_ID&limit=1000" -H "Authorization: Bearer $A" > "$EV/curl/F06-suggestions.json"
   curl -fsS "$API/learning/memory/summary?term_id=$GUZ_ID" -H "Authorization: Bearer $A" > "$EV/curl/F06-summary-before.json"
   ```
3. Pick the test subjects from the suggestions file:
   - `PA` = the academician's instructor (`ACADEMICIAN_INSTRUCTOR_ID`, 157 on a stack.sh stack). L1 is learned but **not offered**: `GET /learning/suggestions?term_id=$GUZ_ID&person_id=$PA&state=all` → a **building preference "A Blok"** with support 8/8 over **2 terms**, `state: "hidden"`, `hidden_reason: "room_already_set"`, no specific room. All four of their Güz classes already hold a definitive A room from the planning list, so there is no class left to target (a class that has its room is never targeted; lane F, T-R1-40). The default `state=open` list has no card for `PA`: that is correct, not a finding.
   - `P1` = a person with an **open** building suggestion with 2-term evidence (on a stack.sh stack: instructor 98 or 125, building A / D). S01 and S03 use `P1`.
   - `SA`, `SR`, `SS` = three open suggestions of other people (accept, reject, snooze), preferably of different kinds. Note their ids, people and claims.
   - If no person has an open building suggestion with 2-term evidence, record that as a finding against L1 (major) and use any person with ≥ 2 open suggestions as `P1`.
4. Constraint baseline: `GET /constraints?term_id=$GUZ_ID` → save it. Count the rows with `source = LEARNED` (expected 0).
5. Expectations from L5/L6, checked in S09: no suggestion proposes A 204 for HEM 236 or MAT 112 §1 (a planner's locked double booking), and none proposes B 407 for MBG 034 (80 students locked in 30 seats).

## Steps

**S01 · admin · suggestions on the person profile**
- Do: `/moderation/people/<P1>` → tab **"Öneriler"**.
- See: the list **"Öneriler ({n})"** with views **"Bekleyen {n}"** and **"Geçmiş {n}"**. Each card (`suggestion-card`, dashed while not applied):
  - **"Öneri · {kind}"**, where kind is "Bina tercihi", "Ders–oda", "Kişi alışkanlığı" or "Oda özelliği";
  - confidence as a word plus a meter (**"{level} güven, {evidence}"**, level Yüksek / Orta / Düşük);
  - one claim sentence and the exact preference sentence that would be added;
  - **"Kanıt"** collapsed, with **"Kanıtı göster"** (`suggestion-evidence-toggle`) listing the term, course, slot and room per evidence row, plus provenance;
  - an impact line **"Bu dönem {n} talebi etkiler"**, or **"{n} talep zaten başka bir şey istiyor; talep her zaman öğrenilmiş alışkanlıktan önce gelir"**;
  - the cross-season marker **"farklı dönem verisi içerir"** when Bahar evidence feeds a Güz suggestion (L2: then no room or slot suggestion, at most a building one);
  - actions **"Kabul et · {weight}"** (`suggestion-accept`, with a weight menu "Ağırlık seç": Düşük / Normal), **"Reddet"** (`suggestion-reject`), **"Ertele"** (`suggestion-snooze`).
- For P1 (L1): the claim is a building preference, with evidence counts over **2 terms**. No card names a single room, and no card that carries "farklı dönem verisi içerir" is a room preference (cross-season evidence gives a building at most; lane F fixed the room-feature case in T-R1-40).
- For PA: `/moderation/people/<PA>` › Öneriler shows no open card; the API's hidden item says why (`room_already_set`).

**S02 · admin · nothing is applied before a decision** (L3)
- Do: start a Güz week-3 run through the Studio (or `POST /runs` as in `setup_api.py runs`) **without** accepting anything.
- API: the run's constraint set and `params` equal a run with suggestions off. There are 0 `LEARNED` constraints in `GET /constraints?term_id=$GUZ_ID`.

**S03 · admin · accept**
- Do: on P1's card, open the weight menu, keep **"Normal"** and press **"Kabul et · …"**.
- See: the card collapses into the receipt **"Yumuşak tercih eklendi"** (`suggestion-receipt`), with "Tercihler'de gör" and **"Geri al"** (`suggestion-undo`). The live region says **"Öneri kabul edildi: yumuşak tercih eklendi."** Focus moves to the receipt or to the next card, not `<body>`. The card leaves the Bekleyen view and appears under Geçmiş as **"Kabul edildi"**.
- API (L4): exactly **one** new constraint with `hardness: "soft"`, `source: "LEARNED"`, weight **5** (Normal), a `source_ref` to the suggestion and its evidence rows. The constraint is targeted (it names the person or their sections). `POST /learning/suggestions/<id>/accept` with a structural kind → 422.
- Elsewhere: Moderasyon › **"Tercihler"** lists the rule with the source chip **"Öneri"**. The staged link counts one more change.
- Do: **"Geri al"**.
- See: **"Kabul geri alındı: tercih kaldırıldı."** The constraint is gone. The card is back in Bekleyen.
- API: `POST /learning/suggestions/<id>/restore` → the suggestion is `open` again and its rule is off.
- Persistent (planning.admin only): the weight menu (**"Ağırlık seç"**) also offers **"Kalıcı tercih olarak kabul et…"** (`suggestion-accept-persistent`). It asks first (`persistent-confirm`): **"Kalıcı tercih olarak kabul edilsin mi?"** with **"Hiçbir zaman kendiliğinden uygulanmaz: sonraki dönemlerde aynı öneri yalnızca işaretlenir ve bir kişinin kabulünü bekler."**, **"Yalnızca yumuşak bir tercihtir; talepler ve zorunlu kurallar her zaman önce gelir."** and **"Geçmiş'ten istediğiniz zaman geri alabilirsiniz."** → **"Kalıcı olarak kabul et"** (`persistent-go`). The receipt reads **"Kalıcı tercih olarak eklendi"**; API `state: "accepted", scope: "persistent"`. In a later term the same suggestion shows **"Başka bir dönemde kalıcı tercih olarak kabul edildi; burada da sizin kabulünüzü bekliyor."** and is still not applied. planner.test does not see the persistent option; the API refuses it with 403.
- Undo the persistent accept, then accept again for this term (leave it accepted for the rest of the flow).

**S04 · admin · reject with a reason** (L8)
- Do: on `SR`, **"Reddet"**.
- See: the inline question **"Neden? Yanıtınız sonraki önerileri iyileştirir."** with chips **"Artık geçerli değil"**, **"Yanlış kişi eşleşmesi"**, **"Bu dönem farklı"**, **"Diğer neden"** (with a field "Diğer…") and **"Nedensiz atla"** (`dismiss-skip`). Choose "Bu dönem farklı".
- See: the receipt **"Reddedildi"** with Geri al, and the live text **"Öneri reddedildi."**
- API: `SR` is `dismissed` with the reason. No constraint is created.
- Dismissal sticks: `POST /learning/refresh` again → `SR` is not open again (it returns only when a new term adds evidence).
- Undo from history: **"Geçmiş {n}"** → the `SR` row (`history-row`, `data-state="dismissed"`) → **"Geri al"** (`history-undo`) → `SR` is back under **"Bekleyen"**. Reject it again with the reason.

**S05 · admin · snooze**
- Do: on `SS`, **"Ertele"** → **"Bir sonraki çözüme kadar"** (other options "7 gün", "Gelecek döneme kadar").
- See: the receipt **"Ertelendi: {until}"** and the live text **"Öneri ertelendi."**
- API: `SS` is `snoozed` with `until = next_solve`. After the next finished run in this term (S02's run, or a new one), `SS` is open again.

**S06 · admin · the same suggestions in the Generator Studio**
- Do: `/generate`, 2026-GUZ, go to the rules step.
- See: a group **"Öğrenilen öneriler ({n})"** at the top of the review tray, next to the AI and upload proposals. None is preselected. Accepting there behaves as S03, and the accepted rule appears in the rule list.

**S07 · planner · may decide, may not reset** (L9)
- Do: log in as planner.test. Accept `SA` on its person's profile (planner holds planning.edit) → as S03.
- Do: open `/moderation/learning`.
- See: **"Öğrenme belleğini yalnızca planlama yöneticileri yönetebilir"** with **"Öğrenilenleri sıfırlamak ya da silmek için bir yöneticiye başvurun."** No reset buttons.
- API: `POST /learning/reset {"scope":"person","value":<P1>,"reason":"deneme"}` as planner → **403**.
- viewer.test sees the cards with **"Önerileri kabul etmek için planlama düzenleme izni gerekir."** and no action buttons.

**S08 · admin · the memory screen**
- Do: `/moderation/learning` (`learning-memory`).
- See: **"Öğrenme belleği"** with the intro **"SmartSched'in önceki dönemlerden ve düzenlemelerden öğrendikleri. Bunlara dayanan öneriler hiçbir zaman kendiliğinden uygulanmaz."** The summary (`memory-summary`) shows:
  - **"Kapsanan dönemler"** (2026-BAHAR, 2026-GUZ; the Final exam term excluded);
  - **"Öğrenilmiş gözlem"** (`memory-observations`), equal to the API summary;
  - **"Bu dönem öneriler"** **"{open} açık · {accepted} kabul · {dismissed} red"**, equal to S03–S07;
  - the reset scopes **"Bir kişinin belleği"** (`memory-person`), **"Bir dönemin katkısı"** (`memory-term`), **"Tüm bellek"**, and **"Son sıfırlamalar"** (`reset-list`).

**S09 · admin · L5 / L6 safety**
- In the suggestions file (precondition 2) and on the HEM 236, MAT 112 and MBG 034 profiles: no suggestion proposes A 204 for HEM 236 or MAT 112 §1, and none proposes B 407 for MBG 034. A violation is a **major** finding (learning from planner errors).

**S10 · admin · reset one person, then undo** (L9, L10)
- Do: on P1's profile, the ⋯ menu (`moderation.profile.more`) → **"Öğrenilenleri sıfırla…"** (`reset-person-open`).
  - Masked names make the memory screen's person search ("Adın en az 2 harfini yazın") ambiguous, so use the profile route.
- See: the alert dialog **"{label} için öğrenilenler sıfırlansın mı?"** with:
  - **"Silinecek: bu kapsamdaki öğrenilmiş alışkanlıklar ve açık, ertelenmiş veya reddedilmiş öneriler."**
  - **"Kalacak: daha önce kabul edilmiş tercihler (artık normal tercihlerdir), talepler ve planlar."**
  - **"30 gün içinde Son sıfırlamalar'dan geri alabilirsiniz; sonra kalıcı olarak silinir."**
  - **"Neden (zorunlu)"** (`reset-reason`).
  - **"Sıfırla"** (`reset-confirm`) is disabled while the reason is empty or under 3 characters.
- Do: reason `görev değişikliği` → Sıfırla.
- See: toast **"Sıfırlandı"** (with Geri al). P1 has **0** open suggestions and 0 dismissals. Other people's counts are unchanged (compare with the summary). P1's accepted constraint from S03 **still exists**. A row in "Son sıfırlamalar" (`reset-row`): date · "Bir kişinin belleği" · P1's initials · the reason · "Administrator" · **"Geri alma için 30 gün kaldı"**. One audit event `learning.reset`.
- Do: **"Geri al"** (`reset-undo`).
- See: **"Sıfırlama geri alındı"**. The row reads **"Geri alındı"**. P1's suggestions and dismissals come back exactly as before (same ids and states).

**S11 · admin · reset one term's contribution** (L11)
- Do: "Bir dönemin katkısı" → **"Dönem seçin"** = 2026-GUZ → **"Sıfırla…"** (`reset-term-open`).
- See: **"2026-GUZ öğrenmeden çıkarılsın mı?"** with **"Bu dönem bundan sonra öğrenmede kullanılmaz; öneriler yeniden hesaplanır (yaklaşık 1 dk)."** Give a reason and confirm.
- After the recompute, P1's building suggestion has evidence from **2026-BAHAR only** ("1 dönem"), or it disappears if one term is not enough evidence. Report which. 2026-GUZ runs and requests still exist (`GET /runs`, request counts unchanged).
- Undo it (Son sıfırlamalar → Geri al).

**S12 · admin · reset everything (typed confirmation)**
- Do: **"Tümünü sıfırla…"** (`reset-all-open`).
- See: **"Tüm öğrenme belleği sıfırlansın mı?"** with **"Onaylamak için SIFIRLA (ya da RESET) yazın"** (`reset-word`).
  - `sifirla` (no dotless ı) → **"Yazılan kelime eşleşmiyor."**
  - `sıfırla` (lower case) → accepted (Turkish-aware casefold).
  - Confirm with a reason.
- See: every open suggestion is gone and the summary is 0. Undo it, and everything returns.
- Expiry: an undo older than 30 days is refused with the date it expired (L10). This cannot be reached in a test run; report `SKIP: needs 30 days`, or a backend unit test name if one exists.

**S13 · admin · KVKK erasure** (no undo)
- Do: on another person's profile (not P1) → ⋯ → **"Öğrenilenleri sil (KVKK)…"**.
- See: **"{label} hakkında öğrenilen her şey silinsin mi?"**, **"Bu kişinin öğrenilmiş gözlemleri, retleri ve alışkanlıkları şimdi silinir."**, **"Kalacak: talepler, çözümler, rezervasyonlar ve kabul edilmiş tercihler (kaynak veri; ayrı bir akışla silinir)."**, **"Bu işlem geri alınamaz."** A reason is required. Confirm **"Şimdi sil"**.
- See: toast **"{label} için öğrenilenler silindi"**. In Son sıfırlamalar the row reads **"Hemen silindi"** with **no** Geri al.
- API: `POST /learning/erase` → 201. The person's learned observations count is 0 (`/learning/priors?subject_id=`).

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Cards** stack full width with a 12 px gap. **"Kabul et"** is a full-width ≥ 44 px button. "Reddet" and "Ertele" are ≥ 44 px and sit side by side below it.
- The weight menu, the snooze options and the reject reason chips open as **bottom sheets** (M-04), each option ≥ 44 px.
- An optional swipe (right = accept, left = reject) is allowed, but every action is also a button (M-11: never gesture-only).
- The evidence list expands in place, and its rows wrap. The page never scrolls sideways.
- **Memory screen:** one column. Each reset opens as a full-height sheet with the reason field focused and visible above the keyboard (M-12). The typed-word field for "Tümünü sıfırla" uses `autocapitalize="characters"` or accepts lower case (S12).
- **Tablet 768:** the profile with the Öneriler tab may use two columns, if each card is ≥ 360 px wide.

## Flow acceptance

1. Nothing learned reaches a run until a person accepts it (L3).
2. Accept → exactly one targeted soft LEARNED constraint at weight ≤ 5. Undo removes it.
3. Reject records the reason and does not come back on refresh. Snooze comes back at its horizon.
4. Planners can decide but not reset. Viewers can only read. The API agrees.
5. A person / term / all reset removes exactly that scope, keeps accepted preferences, is audited, and is undone exactly. Erasure has no undo.
6. No suggestion is built on planner errors (L5, L6). Cross-season evidence is labelled and never yields a room or slot suggestion (L2).
7. MOBILE.md passes on the profile Öneriler tab and `/moderation/learning` at 390 and 768.

## Scenarios covered

needs-doc L1–L11 (L10's 30-day expiry is SKIP), phase19-suggestions.md §5–§7, motion T4 (focus after accept or reject).
