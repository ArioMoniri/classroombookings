# F-05 · Academician "Taleplerim" (own planning requests) → coordinator moderation of that person: history, matchings, priority edit, re-solve preview diff, publish with confirm

Personas: **academician** (self-view), **admin** as coordinator (moderation, re-solve, publish), viewer and planner helpers (read-only and permission checks). Viewports: desktop, tablet, phone.
Owner decisions:
- **Q11 visibility.** An academician sees only their own requests. Coordinators and admins see all.
- **Conflict policy.** Locks first, then the priority the coordinator set, then the most classes placed.
- **Recreate.** "Pin-and-re-run only. No partial publish, so every published schedule is a full checked solver result." A re-solve is a preview until someone confirms the publish.
- **Publish notifications.** In-app bell plus one e-mail digest per affected academician, with only their changed classes and a per-user e-mail opt-out.
- **Q9 (orchestrator, owner may override).** Raising a priority may leave a lower-priority neighbour unplaced, and the preview lists every such loss with its reason.

Testable on `b75047b` + the P19 UI follow-up (2026-10-16): **mostly**. `smartsched/frontend/e2e/followup.phase19.spec.ts` (tests 3, 4 and 6) proves S01, S02, S04, S08 (person priority), S09, S10 (baseline + chain), S12 (with "Akademisyenlere bildir") and the phone checks.
- The login ↔ instructor link has an API (`PUT /auth/sso/admin/users/{id}/instructor`, audited `user.instructor_link`) and a picker in Yönetim › Kullanıcılar (the user's edit sheet, section "Öğretim elemanı kaydı", `user-instructor`; `components/admin/users-admin-identity.tsx` `InstructorLink`). The README §4.4 seed links the academician through that API.
- Publish-change notices (P19-T3) are built: the publish dialog has **"Akademisyenlere bildir"** (`notify-people`) and names who gets the digest. S13 is runnable.
- The academician's "Tercih ekle" (P19-T2, Q12) is built (backend + UI, 2026-10-16): S03 part 2 is runnable; `e2e/followups-ui.spec.ts` proves it.

## Preconditions

1. Full stack with all four solver runs from README §4.2 (`REC_RUNS` with Bahar week 3, Bahar term, Güz week 3, Güz term). Both full-term runs are published. Record the Güz published run id `G0` (`GET /runs` → `is_active` for 2026-GUZ).
2. Seed applied: `akademisyen.test` is linked to the instructor of PSY 278 (Bahar) / PSY 277 (Güz). `ACADEMICIAN_INSTRUCTOR_ID` is printed by the seed.
3. Helper accounts: `planner.test` (PLANNER) from the seed. Add a viewer for the read-only check:
   `POST /users {"email":"viewer.test@smartsched.local","full_name":"V. T.","role":"VIEWER","password":"Flow-2026!pw"}`.
4. SMTP sink running (S13).
5. Oracle for the self-view, as admin: `GET /terms/<guz>/moderation/matchings` → keep the rows of `ACADEMICIAN_INSTRUCTOR_ID` (`curl/F05-oracle-matchings.json`). The academician must see exactly these, and no others.

## Steps

**S00 · admin · how the link is made**
- Do: Yönetim › Kullanıcılar, open `akademisyen.test`. In **"Öğretim elemanı kaydı"** (`user-instructor`) the seeded link shows the instructor ("Öğretim elemanı #<id>" or the masked name). Press **"Değiştir"** (`instructor-edit`), search (`instructor-search`), pick the same instructor again (`instructor-pick-<id>`).
- See: the toast **"Öğretim elemanı bağlandı"**; the moderation person profile ("Hesap") reads "bir kullanıcıya bağlı". An instructor linked to another account is refused with **"Bu öğretim elemanı başka bir hesaba bağlı"** (409 `instructor_linked`).
- API: `GET /audit` has one `user.instructor_link` row per real change (none when the same instructor is picked again).

### Academician

**S01 · academician · open Taleplerim**
- Do: log in as academician. Look for a navigation entry to the planning requests (sidebar, "Diğer" sheet on the phone, ⌘K "Taleplerim").
- See: the entry **"Taleplerim"** (sidebar on desktop, "Diğer" sheet on the phone) links to `/moderation/me`. It is shown to accounts that can book and lack `planning.view`. Missing → FAIL (minor, discoverability); open `/moderation/me` directly.
- See (`my-requests`): the page header **"Taleplerim"** with the subtitle `2026-GUZ` (the current term from `GET /moderation/current-term`) and a button **"Geçmişim"** (`mine-history`). **No** coordinator tabs (Sınıflar / Kişiler / Talepler / Tercihler / Eşleşmeler) and no "Planı yeniden oluştur". The list (`mine-table`) caption reads **"{n} talebiniz"**, with n = the oracle's count. API: `GET /moderation/me` → `visibility: "own"` and the linked `instructor_id`.
- Each row: course and section (PSY 277 §1 theory / lab, PSI 213, PSY 213), what was asked (day / time / room), what was assigned, and the verdict chip with glyph + word (**"Karşılandı"**, **"Kısmen"**, **"Karşılanmadı"**, **"Yerleşmedi"** or **"Değerlendirilmedi"**), plus **"Neden"** when it was not met.
- API, as academician:
  - `GET /terms/<guz>/moderation/matchings` → only the oracle's rows;
  - `GET /terms/<guz>/moderation/people` → only themselves (or 403);
  - `GET /moderation/people/<another instructor id>/history` → **403**, with the Turkish message.
  - Save all three.

**S02 · academician · own history across terms**
- Do: **"Geçmişim"** → `/moderation/people/<ACADEMICIAN_INSTRUCTOR_ID>`.
- See: the profile (`person-profile`) with **"{n} dönem geçmişi"** (n ≥ 2). The timeline (`request-timeline`) is grouped by term: `2026-GUZ` and `2026-BAHAR` (`term-group`), each collapsible ("{term} daralt / genişlet"). Each item (`timeline-row`) shows **"Talep metni"** (the original text), **"Okunan"** (what the parser understood), **"Kesin oda"**, **"Atanan oda"** and **"Neden"**. Each term line reads **"{of} talebin {met} tanesi karşılandı"**.
- The free-text wishes of this person (lectern PC with JASP, a computer lab with JAMOVI) are visible on their rows. If the parser did not understand one, it carries an "okunmadı" marker instead of disappearing (A-04).
- Nothing about other people appears (Q11): no other instructor's name or row.

**S03 · academician · what they may and may not do**
- No edit control anywhere: priority, inline edit, recreate and publish are absent (hidden, not disabled).
- Part 2 (P19-T2, Q12): **"Tercih ekle"** creates a lower-ranked soft preference that waits for coordinator review.
  - Do: on `/moderation/me` press **"Tercih ekle"** (`wish-open`) or tap the PSY 277 §1 row. See the sheet (`wish-sheet`; a bottom sheet on the phone) with that class ticked, **"Tercih türü"**: Oda / Bina / Zaman aralığı.
  - Do: **Zaman aralığı**, "En geç bitiş" P6, **"Onaya gönder"**. A class whose day and time the department form fixed shows **"… gün ve saatini bölüm formu sabitliyor …"** before sending, and after it the error **"Bölüm formu bu dersin gün ve saatini sabitliyor; saat tercihi bunu değiştiremez."** (`wish-error`, code `fixed_by_department`).
  - Do: **Oda**, pick or type a room the department did not ask for (e.g. `C 301`, Enter). See **"Koordinatörün göreceği özet"**: "PSY 277 §1: oda tercihi C 301", "Yumuşak tercih · bölüm talebinden sonra gelir". Send. See **"Tercihiniz koordinatöre gönderildi"** with the server's text "Koordinatör onaylarsa bir sonraki çözümde bölüm talebinden sonra gelen bir tercih olarak uygulanır".
  - Do: **Bina** with the department's own block. See **"Bölüm formu bu dersler için bunu zaten istiyor"** (`already_requested`).
  - See: **"Tercihlerim"** (`my-wishes`) lists the wish as **"Bekliyor"**, with **"Geri çek"** (asks first). API: `GET /moderation/me/preferences` → `pending`, `enabled: false`, `hardness: soft`, `weight: 1`.
  - Coordinator (S05+): Moderasyon header **"1 akademisyen tercihi bekliyor"** → Tercihler › **Akademisyen tercihleri**; Kişiler shows **"1 tercih bekliyor"**. **"Reddet"** refuses an empty reason (**"Gerekçe en az 3 karakter olmalı."**); **"Kabul et"** turns it into "Yumuşak kural · bölüm odasından sonra". The academician then reads **"Kabul edildi"** or **"Kabul edilmedi"** with **"Gerekçe: …"**, and gets the in-app notice (`preference.accepted` / `.rejected`).

**S04 · staff (unlinked) · the unlinked state**
- Do: log in as staff and open `/moderation/me`.
- See: **"Hesabınız bir öğretim elemanına bağlı değil"** with **"Planlama taleplerinizi ve sonuçlarını görmek için planlama biriminden hesabınızı öğretim elemanı kaydınıza bağlamasını isteyin."** (`mine-unlinked`). No error, no 403 toast.

### Coordinator (admin)

**S05 · admin · console overview**
- Do: log in as admin. Sidebar **"Moderasyon"**. The term switcher shows 2026-GUZ.
- See: `moderation-console` with the tabs **"Sınıflar · Kişiler · Talepler · Tercihler · Eşleşmeler"** (keys `1`–`5` switch them). The header reads **"Yayında: #G0 · taleplerin %{rate}'i karşılandı"**. The staged link (`staged-link`) reads **"Bekleyen değişiklik yok"**. It comes from the server (`GET /terms/{id}/changes-since-publish`), so a second browser shows the same count.

**S06 · admin · find the person**
- Do: **"Kişiler"**. Search (`moderation-search`, `/` focuses it) for `PSY 277`. Names are masked, so search by course.
- See: the person's row: **"{met} karşılandı · {unmet} karşılanmadı"**, Öncelik, Tercih, Öğrenilen and Erişilebilirlik columns, and a streak badge (`streak-badge`) if a request went unmet across terms. Caption **"{total} kişiden {shown} gösteriliyor"**.
- If a course code finds nobody: FAIL (minor; the search placeholder promises "Ders, kişi, oda…"). Open the profile by id and go on.
- Do: Enter on the row (or `⇧Enter`) → the profile.
- See: the same timeline as S02, plus **"Hesap: bir kullanıcıya bağlı"**, **"Alışkanlıklar"** (`habits`, e.g. A-block, with "{k} dönemde görüldü · {total} kaydın {rows} tanesi") and the **"Öneriler"** tab (F-06). `[` / `]` move to the previous / next person.

**S07 · admin · matchings for this person**
- Do: **"Eşleşmeler"**. Chips **"Karşılanmayan"**, **"Kısmen"**, **"Karşılandı"**, **"Tümü"** (`chip-*`). Search `PSY 277`. Enter on a row → the matching inspector (`matching-inspector`).
- See: **"İstenen"** vs **"Atanan"**. **"Karşılanan istekler"** lists Oda / Bina / Özellik / Gün / Saat, each with "karşılandı", "karşılanmadı" or "istenmedi". **"Neden"**. **"Tutan"** names which class holds the requested room (course code). Esc closes it, and focus returns to the row.
- Bahar cross-check (needs scenario M2): switch the term to 2026-BAHAR and search `PHY 102`. Rows 49/210 (requested D 204, definitive D 202) read **"Karşılanmadı"** with the reason "planlama birimi kararı (gerekçe girilmemiş)" or its equivalent. Record the exact text. Switch back to Güz.

**S08 · admin · edit a priority**
- Do: on the PSY 277 §1 theory row press `p` (or the Öncelik cell, `priority-trigger`).
- See: a popover (a bottom sheet on phone) titled **"PSY 277 §1 önceliği"**, **"Şu an:"** Normal, tiers **"Yüksek"** / **"Normal"** / **"Düşük"**, **"Uygulandığı yer"**: "Bu talep" / "Tüm şube", note **"Not (isteğe bağlı): neden?"** (placeholder "örn. akreditasyon laboratuvarı").
- Do: Yüksek, "Tüm şube", note `akreditasyon`, save (`priority-save`).
- See: toast **"PSY 277 §1: öncelik kaydedildi. Bir sonraki çözümde etkili."** and the line **"Bir sonraki çözümde etkili olur. Yayındaki plan değişmez."** The staged link now reads **"1 değişiklik yayında değil"**. Opening it lists the change ("PSY 277 §1: öncelik Yüksek"). Focus returns to the edited row.
- API: `PUT /moderation/sections/<id>/priority` → 200. One audit row. `G0` is still the active run, and its assignments are unchanged.
- Person and programme priority (P19-P-04): on the profile, **"Kişi önceliği · {term}"** (`person-priority`) with Yüksek / Normal / Düşük and the note; in the matching inspector also the programme's (`program-priority`). Save → **"{label}: öncelik kaydedildi ({n} talep). Bir sonraki çözümde etkili."** API: `PUT /moderation/people/<id>/priority {term_id, priority:"high", note}` → 200; `GET /terms/<id>/moderation/priorities?subject=person` → `priority: 1`. The staged list reads **"… kişi önceliği Yüksek"**, and the person's matchings show the source badge **"· kişi"** (`priority-source`, `data-source="person"`): talep > şube > kişi > program.
- Permissions:
  - viewer.test sees the console with **"Yalnızca görüntüleme: düzenlemek için planlama düzenleme izni gerekir."** and no priority trigger. The API PUT as viewer → 403.
  - planner.test can edit a section or request priority (planning.edit).
  - Person-level priority is coordinator/admin only (adopted default): a planner trying it gets 403.

**S09 · admin · re-solve preview**
- Do: **"Planı yeniden oluştur"** (`recreate-open`, or `⇧R`).
- See (`recreate-sheet`):
  - **"Yayındaki plan #G0 temel alınır"**;
  - **"Yayında olmayan değişiklikler (1)"** listing S08;
  - **"Yöntem"** with **"En az değişiklik"** selected by default ("Yayındaki planı temel alır; yalnızca gerekenler taşınır.") and **"Baştan çöz"** ("Tüm dersler yeniden yerleştirilir (önerilmez).");
  - **"Süre sınırı"**;
  - **"Politika: Kilitler → Öncelik → En çok ders (dönem ayarı)."**;
  - **"Önizleme oluşturulur; siz onaylayana kadar kimse için hiçbir şey değişmez."**
- Do: **"Önizleme oluştur"** (`recreate-start`).
- See: toast **"Yeniden çözüm #N başladı. Çalışmaya devam edebilirsiniz."** The run island shows progress, and you can keep using the console. On completion a toast links to the preview `/moderation/recreate/N`.
- API: `POST /terms/<guz>/moderation/resolve` started run N with `parent_run_id = G0`, mode repair, `workers=1`. N is **not active**.

**S10 · admin · read the diff**
- See on `/moderation/recreate/N` (`recreate-preview`):
  - **"Önizleme hazır: {moved} taşınan, {newly} yeni yerleşen, {unplaceable} yerleşemeyen"**;
  - the line **"Yeni çözüm ← yayındaki plan #G0"** and the state **"Yayında değil"** (`preview-state`);
  - the baseline switcher **"Karşılaştır:"** (`baseline-select`: "Varsayılan: #G0 (zinciri başlatan plan)", "#… (bir önceki önizleme)", "#… (zincirdeki adım)") and the chain **"Zincir: #N ← … ← #G0"** (`chain`); switching re-reads `GET /moderation/runs/N/diff?compare_to=<id>`;
  - the summary (`diff-summary`): **"Taşınan"** (`count-moved`), **"Değişmeyen"** (`count-unchanged`), **"Yeni yerleşen"**, **"Yerleşemeyen"** (with "{n} yeni" when it grew), **"Etkilenen kişi"**, **"Zorunlu puan"** 100 → **100**, **"Yumuşak puan"**;
  - the unchanged note **"{n} ders gününü, saatini ve odasını koruyor."** (`unchanged-note`);
  - the scope note **"Düzenlenen kapsam dışındaki {n} ders taşındı ({unexplained} tanesi nedensiz)."**, where unexplained must be **0** (Q9).
- The group tabs (keys `1`–`4`) open on **Taşınan**. Each moved row shows Önce / Sonra / Neden. Unplaceable rows give a Turkish sentence and the culprits ("Kilitli iki ders aynı odada aynı saatte: …").
- **"Onayla ve yayınla"** (`preview-publish`) is disabled until the preview has loaded.
- API: `GET /moderation/runs/N/diff`:
  - the counts equal the UI;
  - **every lock placed in G0 is placed in the same room in N** (M7). Compare the locked assignments of both runs and list any difference: each one is a blocker;
  - every class that lost its place carries a reason code.
- Determinism (owner): repeat S09 with nothing changed. The second preview's diff equals the first one (same moved set).
- **"Takvimde göster"** (`compare-calendar`) shows Önce / Sonra on the calendar ("Takvimde yalnızca ilk {n} taşınan ders hareket eder; diğerleri yerinde değişir.").

**S11 · admin · pin and re-run** (only if something moved; otherwise `SKIP: nothing moved`)
- Do: on a moved row ⋯ (`diff-row-actions`) → **"Bu taşımayı engelle (eski yerinde tut)"**.
- See: **"eski yerine sabitlendi"**. **"Bu önizlemedeki düzenlemeler (1)"** (`draft-edits`). **"Önizlemeyi yeniden çalıştır (1)"** (`preview-rerun`).
- Do: re-run.
- See: a new preview **"Yeni çözüm ← önceki önizleme #N"**, in which that class kept its old cell.
- No checkbox or action publishes a subset of the rows: partial publish does not exist (owner decision). Row checkboxes, if any, serve export and pin only.

**S12 · admin · publish with confirm**
- Do: **"Onayla ve yayınla"**.
- See: the confirm (`publish-confirm`) **"Bu plan yayınlansın mı?"**, body **"Yeni plan herkes için yayındakinin yerini alır. Önceki plan Çözümler'de kalır ve yeniden yayınlanabilir."**, a summary of the counts and the affected people, and the toggle **"Akademisyenlere bildir"** (`notify-people`, on): **"Değişen dersleri olan {n} akademisyene, yalnızca kendi değişiklikleriyle bir bildirim ve e-posta özeti gider:"** followed by their names (`notify-list`), or **"Değişen dersi olan ve hesabı bağlı akademisyen yok; bildirim gitmez."**; unlinked people are only counted. Confirm **"Yayınla"**.
- See: toast **"Yayınlandı: #N artık geçerli plan. Önceki plan Çözümler'de duruyor."** and, with the toggle on, **"{n} akademisyene bildirim gönderildi."** (`POST /runs/N/activate {notify_people: true}` → `notified`).
- API: `GET /runs/N` → `is_active: true`; `G0` → `is_active: false` and still present; one audit row for the activation. The booking grid now follows N (pick one moved class and check its room in `/bookings`).
- Refusal path: if N had a hard score below 100, the confirm must not offer "Yayınla" (`publish-refused`, "Sunucu yayınlamadı: …").
- **"Vazgeç"** (`moderation.preview.discard`) on another preview keeps `G0`/N as it is. That preview stays in Çözümler as not published.

**S13 · academician · told about own changes only** (P19-T3; runnable since the follow-up)
- Target: when a moved class belongs to the academician, their bell has one notice and the sink has **one** digest e-mail listing only their changed classes (course, old → new day/time/room). An academician with no changed class gets nothing. A per-user e-mail opt-out exists (Profile › Bildirimler).
- Check anyway: the sink and the bell after S12. Report what arrived.

**S14 · academician · after publish**
- See: `/moderation` "Taleplerim" now reflects N (assigned rooms of any moved class). The published label shows #N.

## Keyboard path (desktop; spec phase19-moderation.md §7)

Run S05–S12 once without the mouse: `g m` → Moderasyon, `1`–`5` tabs (focus lands on the first row, not on the page top), `/` search, `j`/`k` rows, `Enter` inspector, `⇧Enter` profile, `p` priority, `⇧R` recreate (nothing runs without `⌘↵` / `Ctrl+Enter`), `1`–`4` diff groups and `⌘↵` publish confirm in the preview, `?` shortcuts sheet. After every close, focus is back on the row that opened it.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Taleplerim on phone:** a card list (M-07). Verdict glyph + word on line 1, requested → assigned on line 2, the reason on line 3. "Geçmişim" is reachable without scrolling.
- **Console tabs:** a horizontally scrolling segmented control that never wraps to two rows. The state chips sit on a second row. The search is ≥ 44 px.
- **Rows:** cards. A tap opens the inspector as a bottom sheet (45 % / 92 % detents or a full sheet); a drag down or the close button (≥ 44 px) closes it.
- **Profile:** a full-screen route. The timeline is grouped by term. The facts fold into a "Bilgiler" disclosure under the header.
- **Priority editor:** a bottom sheet with the fields stacked and "Kaydet" pinned to the sheet footer (M-05), clear of the on-screen keyboard while typing the note (M-12).
- **Recreate:** a full-height bottom sheet.
- **Preview:** a grouped list (Taşınan / Yeni / Yerleşemeyen / Değişmeyen collapsed). **"Onayla ve yayınla"** is a floating capsule above the tab bar, with the safe-area inset applied (M-06).
- **Tablet 768:** list + inspector side by side is allowed if the inspector is ≥ 360 px. The preview table may scroll horizontally only with the first column (Ders) pinned (M-07).

## Flow acceptance

1. An academician sees all their own planning requests with verdicts and reasons, across terms, and nothing about anyone else (UI and API).
2. A coordinator can find a person, read their history and matchings, and change a priority. The change is audited, staged and does not touch the published plan.
3. A re-solve is a preview (inactive run). Its diff matches the API, keeps every published lock in place, explains every move and loss, and is deterministic.
4. Publishing needs an explicit confirm that names the consequences. The previous plan stays and can be re-published. Partial publish does not exist.
5. Viewers cannot edit, and permission refusals are clear.
6. MOBILE.md passes on `/moderation` (academician and coordinator), `/moderation/people/<id>` and `/moderation/recreate/<id>` at 390 and 768.

## Earlier issues and scenarios checked here

needs-doc M1, M2, M6, M7; A-02 / P19-T1 (no link and no "my classes"), A-04 (notes visible), P19-T2, P19-T3; persona-academician §5 rows 1–7 and 22–23.
