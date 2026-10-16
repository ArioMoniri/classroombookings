# F-11 · Admin setup: users and roles (no escalation), rooms and features, approval rules and mode, KVKK sign-offs (calendar sync, AI policy)

Personas: **admin** (Fatih Bey as system administrator), **limited admin** (made in S03, for the no-escalation checks). Viewports: desktop for the full flow; tablet and phone for the users list, the user form, the room form, the features tab and the AI-policy panel.
Owner rules:
- **No escalation.** No one grants a permission or role they do not hold. This includes `bookings.skip_approval`.
- **KVKK.** A sign-off is an **explicit, dated admin action**, never pre-seeded (M-18 fix, alembic 0022). AI intake and vision stay off until an admin acknowledges the notice. Turning them on needs `kvkk_ack`, and every change is a new sign-off record plus an audit event.
- **Approval mode.** `bookings.approval_mode` is `rules` (the CRBS default, empty and universal installs) or `all` (the institution profile).
- **Webhooks** are off by default.
- **Languages.** TR + EN only (owner decision; F-13 checks the picker).

Testable: **fully** since the approval-first UI (2026-10-16): the approval mode (S07) is in Yönetim › Ayarlar, the calendar-sync KVKK sign-off (S09, M-40) and the webhooks in Ayarlar › Entegrasyonlar (`/settings?tab=integrations`). Both still run their API checks.

## Preconditions

1. Restore the snapshot (seeded accounts present).
2. A small users CSV in scratch (`$SCR/flow-in-F11/users.csv`, initials only):
   ```
   email,full_name,role,password
   ds.test@smartsched.local,D. S.,TEACHER,Flow-2026!pw
   nopass.test@smartsched.local,N. P.,TEACHER,
   personel.test@smartsched.local,P. T.,TEACHER,Flow-2026!pw
   ```
   Expected results: row 1 created; row 2 refused with **"Parola yok"** (or created with a reset code, per the importer's rule; record which); row 3 refused because the user exists ("Kullanıcı adı var" / "E-posta var").

## Steps

### Users

**S01 · admin · create, edit, disable a user**
- Do: Yönetim › **Kullanıcılar** (`/admin/users`) → **"Yeni kullanıcı"** (`users-new`). In the dialog (`user-dialog`): empty submit → messages per field. Then e-mail `ds.test2@smartsched.local`, name `D. S.`, role TEACHER, password `Flow-2026!pw` → save (`user-save`).
- See: a Turkish toast. The row appears in `users-table`. The e-mail is shown once per row (UI review), and the counts use ICU plurals ("1 kullanıcı").
- Do: edit the user: department, "Kimin adına" visibility, "Onay verdiği derslikler" (`user-approves-for`, offered only for roles holding `approvals.decide`). Save. Then disable the user (is_active off).
- Expect: logging in as the disabled user → the **generic** **"E-posta, kullanıcı adı veya şifre yanlış."** (M-42: it said "user disabled"). The API answers 401 with the same body as a wrong password.

**S02 · admin · CSV import**
- Do: **"İçe aktar"** (`users-import`) → the CSV → **"Çalıştır"** (`import-run`).
- See: per-row results (`import-results`) with a status word and the reason per row, as in precondition 2.

### Roles and no escalation

**S03 · admin · a limited user-admin role**
- Do: **Roller** (`/admin/roles`) → **"Yeni rol"** (`roles-new`) → name `Kullanıcı yöneticisi`. Permissions: only the user-management ones (users view / create / edit). Keys show in a tooltip, not in mono under each label (UI review). Save (`role-save`).
- Do: create `limited.admin@smartsched.local` / `Flow-2026!pw` with this role.

**S04 · limited admin · cannot grant what they lack**
- Do: log in as limited.admin.
- See: the landing page is a page they may use (`/admin/users`), not the planner dashboard with 403 toasts (M-38).
- Do: **Roller** → edit `Kullanıcı yöneticisi`.
- See: every permission the limited admin lacks (e.g. `planning.admin`, `approvals.decide`, `bookings.skip_approval`) is a checkbox with `aria-disabled="true"` and a reason (`role-disabled-hint`). In the user form, the role picker shows roles they cannot grant with **"(eksik: …)"**.
- API (each → **403**, save every response):
  1. `PUT /roles/<own role> ` adding `planning.admin`;
  2. `POST /users` with `"role":"ADMIN"`;
  3. `PUT /users/<own id>` with `"role":"ADMIN"`;
  4. `PUT /roles/<TEACHER role>` adding `bookings.skip_approval`;
  5. `POST /roles` with a permission they lack.
- Persona-admin result to match: 13/13 escalation attempts refused.

### Rooms and features

**S05 · admin · a room**
- Do: Yönetim › **Derslikler** (`/admin/rooms`) → **"Yeni derslik"** (`room-new`): code `T 101` (`room-new-code`), name `Test dersliği`, capacity **40** (`room-new-capacity`), group = A Blok (`room-new-group`) → **"Oluştur"** (`room-create`).
- Do: edit it (`room-edit-T 101`): capacity 42 (editable here, M-46), owner, notes. Upload a PNG photo: a success toast appears (M-46: there was no feedback). A wrong type is refused in Turkish (M-36). Save (`room-save`).
- Do: "Erişimi denetle" (`room-check-access-T 101`) for the staff user → the result (`access-result`) per permission, labelled in Turkish ("rolden").
- Delete a room that has bookings → refused with a guarded text. Delete T 101 (no bookings) at the end of the flow.

**S06 · admin · typed features**
- Do: **"Özellikler"** tab (`tab-features`, `features-tab`) → **"Başlangıç kataloğu"** (`features-starter`) → typed features appear in `features-table`. **"Etiketleri benimse"** (`features-adopt`) turns room-master tags (PC, LAB, AMPHI…) into features.
- Do: **"Yeni özellik"** (`feature-new`): name `Projeksiyon`, type yes/no (`feature-type`) → save (`feature-save`). Values for T 101 (`feature-values`, `values-row-T 101`) = Evet → save (`feature-values-save`).
- Do: before deleting a feature, open its impact (`GET /room-admin/features/<id>/impact`). The UI shows how many rooms and rules use it.
- Expect: `GET /rooms/facets` lists Projeksiyon. Find a room (F-03) offers it as a filter, and T 101 matches.

### Approval rules and mode

**S07 · admin · approval mode**
- Do: Yönetim › Ayarlar (`/admin/settings`), block **"Rezervasyon onayı"** (`approval-mode`): **"Yalnız kurallı derslikler"** vs **"Her talep önce onaya"**, each with a one-line explanation, and one sentence on who books directly (approvers, planning administrators, roles with **"Onaysız doğrudan rezervasyon"** = `bookings.skip_approval`). Save (`org-save`); saving is audited.
- API check:
  - `PUT /org/settings {"approval_mode":"all"}` → `GET /org/settings` shows it;
  - `{"approval_mode":"sometimes"}` → **422**;
  - limited.admin (no settings permission) → **403**.
- Effect: F-01 S02 (a staff booking becomes a request).

**S08 · admin · approval rules**
- Do: **Onay kuralları** (`/admin/approval-rules`) → **"rule-new"**:
  - **"rule-entity"** = Derslik grubu: C Blok;
  - one step (`rule-step-1`) = designated approvers, min 1;
  - **"rule-hold"** = 0;
  - lead time 1 workday;
  - expires 60 minutes before start;
  - save (`rule-save`).
- See: the rule in `approval-rules` (`rule-<id>`) with a one-line summary in Turkish.
- Do: a rule on a room type: **"rule-type"** = tag, **"rule-tag"** = PC.
- Warning check (M-35): remove every approver's scope for C Blok (edit the admin user's "Onay verdiği derslikler" so it no longer covers C, or create the rule on a group no approver covers).
  - See: **"Bu derslik için atanmış onaycı yok"** (or equivalent) on the rule.
  - The request still falls back (to the all-room approvers, then the room owner, then Administrators): a request is never orphaned. Check it with one staff request.
- Restore the admin's scope to "all".

### KVKK sign-offs

**S09 · admin · calendar sync** (M-40)
- Do: **Ayarlar › Entegrasyonlar** (`/settings?tab=integrations`), card **"Takvim eşitleme (KVKK)"** (`calendar-sync-admin`). See **"Kapalı"** and **"Onay kaydı yok: takvim eşitleme hiç açılmadı."** (`calendar-no-signoff`) on a fresh install.
- Do: turn on `calendar-sync-switch`. The notice (`calendar-notice`) says what is transferred and where; **"Aç ve onayı kaydet"** (`calendar-confirm`) stays disabled until the acknowledgement (`calendar-ack`) is ticked. Confirm.
- See: the record (`calendar-signoff`) **"<name>, <date> tarihinde açtı ve KVKK onayını verdi."** and **"Hukuki dayanak: KVKK md. 9 (7499 sayılı Kanun ile değişik; yurt dışına aktarım)"** (the API stores the English constant "KVKK Art. 9 as amended by Law 7499 (cross-border transfer)"). Turning it off needs no acknowledgement and shows **"… tarihinde kapattı."** The record stays visible (E-8).
- Webhooks: the card **"Giden webhook'lar"** (`webhooks-admin`) is headed by **"Webhook gönderimi"** (`webhooks-switch`, off by default). A loopback or private URL is refused next to the field (M-41); a new webhook shows its `whsec_…` secret once; delete asks first.
- API check:
  - `GET /calendar/admin/settings` → `calendar_sync_enabled: false`, `calendar_sync_signoff: null` on a fresh install (never pre-seeded);
  - `PUT {"calendar_sync_enabled":true}` → the sign-off record carries `by`, `by_user_id`, `at`, `legal_basis`; one audit row `integrations.calendar_sync`;
  - `PUT {"calendar_sync_enabled":false}` → a new record with `enabled:false`, and token feeds answer 404 (F-04 S11);
  - webhooks: `webhooks_enabled` is false by default.

**S10 · admin · AI policy (intake and vision)**
- Do: **Ayarlar** (`/settings`) → the AI policy panel (`ai-policy`). The status pill (`ai-status-pill`) reads off.
- See: two switches, **intake** (`ai-policy-intake`) and **vision** (`ai-policy-vision`), each with its hint. The KVKK notice (`ai-policy-notice`, `ai-policy-notice-text`) is in Turkish: what is sent (file text; page images for vision), to whom (Anthropic's Claude API) and how long it is kept.
- Do: turn intake on **without** ticking the acknowledgement (`ai-policy-ack`).
  - See: the confirm (`ai-policy-confirm`) stays disabled, or the save is refused with a Turkish message.
  - API: `PUT /ai/policy {"intake_enabled":true}` → **422** (needs `kvkk_ack`). `{"vision_enabled":true,"intake_enabled":false}` → **422** ("vision needs intake").
- Do: tick the acknowledgement, add the reason `KVKK sorumlusu onayı (test)` and confirm.
  - See: the sign-off (`ai-signoff`) shows the name, the date and time, the notice version and the legal basis. The status pill reads on.
  - API: `GET /ai/policy` → `intake_enabled: true`, a `signoff` record. One audit row `ai.policy` with before/after.
- Do: turn intake off again (every other flow runs with AI off).
  - See: vision goes off with it. A new sign-off record shows `enabled:false`.
- No key is needed to toggle. The model card says **"Önce bir API anahtarı ekleyin"** with a link, and has no dead "Kaydet".

### Audit

**S11 · admin · everything above is in the audit log**
- Do: `/admin/audit`, newest first.
- See: one row per action of S01–S10 as a **domain sentence** ("Derslik özelliği eklendi · #2", "Kullanıcı oluşturuldu · D. S."), with the raw key only in the details, before/after values, the actor and the time. Filter by actor = Administrator. The CSV export works.

## Mobile-specific expectations (phone 390×844; tablet 768×1024)

- **Setup sub-navigation** (13 tabs) scrolls horizontally with edge fades, or moves into a "Diğer ▾" overflow. Tab labels are never clipped ("Sign-", "Acce", UI review). Each tab is ≥ 44 px.
- **Users list:** a card list (name, e-mail once, role chip, status word) or a table that scrolls with the name column pinned (M-07). The row menu ("…") is a ≥ 44 px button, not a hover reveal.
- **User / room / feature forms** open as full-height bottom sheets in one column (M-10). The role picker and "Onay verdiği derslikler" open as searchable sheets. Save is sticky in the sheet footer.
- **Roles editor:** permission groups are collapsible sections. Each checkbox row is ≥ 44 px, with the disabled reason visible as text, not only in a tooltip (M-11).
- **`/admin/rooms` at 390:** no horizontal page overflow (UI review: it overflowed).
- **AI policy panel:** the notice text is readable without a modal inside a modal. The acknowledgement checkbox has a ≥ 44 px hit area.
- **Tablet 768:** forms may be a centred dialog at most 640 px wide. Lists may be tables if no column is clipped.

## Flow acceptance

1. Users can be created, imported, edited and disabled. A disabled login is indistinguishable from a wrong password.
2. Nobody can grant what they lack, in the UI (disabled with a reason) and in the API (403), including `bookings.skip_approval`.
3. Rooms, capacities and typed features can be managed and show up in Find a room.
4. Approval rules work on rooms, groups and types. A rule nobody can approve is flagged and still never orphans a request. The approval mode can be set in the UI and validated.
5. Calendar sync and AI intake are off until an admin records a dated sign-off. Every change is audited and visible.
6. MOBILE.md passes on `/admin/users`, `/admin/roles`, `/admin/rooms` (+ features tab), `/admin/approval-rules` and `/settings` at 390 and 768.

## Earlier issues to re-verify here

M-18, M-35, M-36, M-38, M-40, M-41 (webhook SSRF: optional `POST /webhooks` to `http://127.0.0.1` → refused), M-42, M-43, M-46, M-48 (unsaved-changes guard on Kurum ayarları: edit, navigate away → a guard dialog, or the change is saved).
