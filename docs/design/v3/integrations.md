# Integrations gallery, guided setup, identity providers, sign-in buttons, SMTP wizard

Owner: product designer (wave3b-des2-2026-10-17) · Status: v3.0 spec (2026-10-17) · Builders: lane **W3-HUB**
(`frontend/src/components/admin/integrations/**`, `frontend/src/app/(app)/admin/integrations/**`,
`frontend/src/lib/api/integrations.ts`, `api/v1/integrations.py` read-only status) and lane **W3-IDP**
(`services/identity/**`, `api/v1/sso.py`, `frontend/src/components/identity/**`, `components/auth/sign-in-page.tsx`
provider buttons); the SMTP wizard is built by **W3-MAIL** (`components/admin/email/**`) inside the same sheet shell.
Copy namespaces: `integrations.*` (hub, sheet shell), `identity.*` (IdP steps, sign-in buttons), `email.*` (SMTP wizard).
Depends on: [`../tokens.md`](../tokens.md) §A (sizes, `DataTable`, `StatusDot`), [`../v2/liquid-glass.md`](../v2/liquid-glass.md),
[`../v2/sign-in.md`](../v2/sign-in.md) (§7 Microsoft button, §12 invites; **§0 "one door" is amended by §6 here**),
[`../v2/motion.md`](../v2/motion.md), [`emails.md`](emails.md) (§6 headers, `smtp_test`), [`messages.md`](messages.md) (toasts,
banners), `app/services/identity/kinds.py` (W3-IDP kinds, fields, presets, steps; read 2026-10-17 20:20),
`app/api/v1/integrations.py` (W3-HUB areas, statuses, `CardIn`).
Wireframes (wireframe palette; purple = annotation; rendered and checked in Chromium):
`wireframes/integrations-gallery-{1440,390}.svg`, `wireframes/integrations-setup-{1440,390}.svg`,
`wireframes/signin-providers-{1440,390}.svg`, `wireframes/smtp-wizard-{1440,390}.svg`; generator `wireframes/src/ig.py`.

Owner's words (2026-10-17): "Microsoft and other auth providers must be settable in the admin panels, shared between all
admins (when one sets it, everyone gets it from there). Use Pipedream-like things for easier setup. Identity-provider
settings for logins and invitations, e-mail SMTP and the related settings live in the admin settings tab."

---

## 0. BLUF

- **One route, Yönetim › Entegrasyonlar (`/admin/integrations`)**: a gallery of connector cards in six areas (Kimlik ·
  E-posta · Takvim · Kanallar · Webhook ve otomasyon · Yapay zekâ), filter chips with counts, search, a summary line
  ("6 bağlı · 1 hata · 9 yapılandırılmadı") and a pinned **"Dikkat isteyen"** row for cards in error. Settings ›
  "E-posta" and "Kimlik" tabs keep a pointer card to this route (the owner's "admin settings tab" finds it either way).
- **Card** = monogram (no third-party logos in the admin), name, one-line summary, **status dot + word** (Bağlı /
  Yapılandırılmadı / Hata / Kapalı / Bilinmiyor), last check, **"Son değişiklik: <ad>, <zaman>"**, a primary action
  (**Kur** when not configured, **Yönet** otherwise) and an on/off switch once configured. Cards owned by other screens
  (AI providers, channels, webhooks) open those screens (↗); the hub never rewrites them.
- **Guided setup sheet** (Pipedream/n8n pattern): 5 steps **Ön ayar → Sağlayıcıda kaydet → Değerleri yapıştır →
  Bağlantıyı dene → Etkinleştir**. Step 2 shows the exact values to copy into the provider's console (redirect URI, entity
  ID, ACS URL, scopes, logout URL) with **Kopyala** buttons; step 3 has paste-in fields (secrets write-only); step 4 runs a
  live, line-by-line test and translates provider error codes into a cause + a fix + the step to go back to; step 5
  enables, with the sign-up policy and default role. Drafts are server-side and shared, so another admin can finish.
- **Sign-in page with several providers**: when two or more IdPs are on, every IdP button has the **same size and
  weight** (Google requires at least equal prominence), in the admin's order, max 3 visible + "Diğer giriş yolları";
  Microsoft and Google buttons follow their own branding; others are neutral with the admin's label. The password form
  stays the quiet disclosure. An invite link shows only the invited method.
- **SMTP preset wizard**: 6 steps **Sağlayıcı → Bağlantı → Gönderen → Alan adı → Deneme → Etkinleştir**; presets for
  Microsoft 365 (OAuth recommended: Exchange Online disables SMTP Basic auth by default from December 2026), Google
  Workspace (SMTP relay or app password), Yandex 360, the university's own relay, and transactional services (Amazon SES,
  Postmark, Resend, Brevo; abroad → KVKK md. 9 acknowledgement); SPF/DKIM/DMARC check; a real test message with "did it
  arrive?"; and on enabling, a choice for queued notifications ("Yalnız yenileri" by default).
- **Shared and audited**: every value lives in the organisation's database, secrets encrypted and write-only, every
  change audited with the actor; optimistic locking ("Bu ayar siz düzenlerken Ayşe Yılmaz tarafından değiştirildi").
- **Acceptance**: IN-01…IN-24 (§13).

## 1. Users and goals

| Persona | Goal | Where |
|---|---|---|
| System admin (`setup.settings`) | "Turn on Microsoft (or Google, Okta, Shibboleth) sign-in without reading docs for an hour" | Kimlik cards → setup sheet |
| IT department (often a different person from the SmartSched admin) | "Give me the exact values to paste into Entra / Google / Okta; tell me exactly what is wrong" | step 2 copy values, step 4 test |
| Second admin, next day | "See what my colleague set, who and when; finish their draft" | card "Son değişiklik", shared draft |
| Planning admin (`planning.admin`) | "Is mail working? Why did people not get notifications?" | gallery read-only, E-posta card |
| KVKK officer | "Which services send data abroad, and who acknowledged it?" | card summary "yurt dışı", KVKK acknowledgement records |
| Every user | "Sign in with my institution account; the button I expect is there" | `/login` |

Permissions: view `/admin/integrations` with `setup.settings` or `planning.admin` (W3-HUB `HUB_PERMS`); configure, test,
enable/disable needs `setup.settings`. Planning admins see the same cards with actions replaced by "Yalnız görüntüleme"
and no switches.

## 2. References (public, checked 2026-10-17)

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| P1 | Pipedream Connect: OAuth clients page (enter client ID/secret, copy the generated redirect URI into the app's console, edit scopes) and Connect Link hosted flow ([OAuth clients](https://pipedream.com/docs/apps/oauth-clients), [Connect Link](https://pipedream.com/docs/connect/managed-auth/connect-link), [create OAuth client API](https://pipedream.com/docs/connect/api-reference/create-oauth-client.md)) | gallery of app cards; "copy this into the provider" as a first-class step; scopes shown and editable; success/error redirect pages | a third-party broker holding our secrets (everything stays in our DB) |
| P2 | n8n credentials: "copy the OAuth Redirect URL from n8n and paste it into the provider", per-provider credential docs ([Raindrop](https://docs.n8n.io/integrations/builtin/credentials/raindrop), [GetResponse](https://n8n-docs.teamlab.info/integrations/builtin/credentials/getresponse/), [Twist](https://docs.n8n.io/integrations/builtin/credentials/twist)) | the redirect URL at the top of the form; per-provider short steps; the "localhost is rejected" warning → our public-URL check | a generic form with no provider steps |
| P3 | Zapier, *Test authentication* (green check, HTTP and console tabs, "a 200 with an error body still fails") ([docs.zapier.com](https://docs.zapier.com/platform/build/test-auth)); Make, OAuth 2.0 connection with a validation request ([docs.make.com](https://docs.make.com/apps/app-structure/connections/oauth2)) | test = a real call to an identity endpoint; show the raw detail behind "Ayrıntı" for IT | silent "Saved" without a test |
| P4 | WorkOS Admin Portal / SSO connection setup: provider-specific instructions after picking the IdP, ACS URL and SP entity ID to copy, metadata URL *or* manual fields, "test the connection, then save", then optional vs enforced ([test SSO](https://workos.com/docs/sso/test-sso.md), [Okta SAML guide](https://workos.com/docs/integrations/okta-saml/introduction), [ManageEngine steps](https://www.manageengine.com/identity-360/integrations/workos-sso.html), [Ventrata admin portal](https://support.ventrata.com/en/articles/12301124-how-to-access-and-use-the-workos-admin-portal)) | the step order and the "test with your own account" round trip; metadata URL first, manual as a fallback | enforcing SSO in the wizard (enforcement is a separate, guarded setting) |
| P5 | Microsoft Learn: register a web app (Authentication › Add a platform › Web › redirect URI; Certificates & secrets › New client secret, copy once; certificates preferred) ([learn.microsoft.com](https://learn.microsoft.com/en-gb/graph/auth-register-app-v2), [Python web app tutorial](https://learn.microsoft.com/en-sg/entra/identity-platform/tutorial-web-app-python-register-app), [entra-docs](https://github.com/MicrosoftDocs/entra-docs/blob/main/docs/identity-platform/scenario-web-app-sign-user-app-registration.md)) | step texts in the console's own Turkish/English labels (W3-IDP `STEPS`); secret expiry reminder | screenshots of the portal (they change; text names instead) |
| P6 | Google, *Sign in with Google branding guidelines*: button "at least as prominent as other third-party sign-in options", light/dark/neutral themes, official G logo unmodified ([developers.google.com](https://developers.google.com/identity/branding-guidelines)) | equal-weight provider stack; Google's colours and label | recolouring the G or shrinking the Google button |
| P7 | Resend domains: SPF + DKIM required, DMARC recommended, statuses not started / pending / verified / failure / temporary failure, "Restart verification" ([resend.com/docs](https://resend.com/docs/dashboard/domains/introduction), [not verifying](https://resend.com/docs/knowledge-base/what-if-my-domain-is-not-verifying)) | DNS check rows with a status word each and the exact record to add | auto-creating DNS (we only check) |
| P8 | Microsoft Message Center MC786329 (updated 27 Jan 2026): Exchange Online SMTP AUTH Basic auth disabled by default from December 2026, final removal date in H2 2027; error `550 5.7.30` ([itelio mirror](https://www.itelio.com/en/microsoft-message-center/MC786329), [ChangePilot](https://portal.changepilot.cloud/MC786329), [CaptainDNS guide](https://www.captaindns.com/en/blog/microsoft-exchange-basic-auth-smtp-end)) | OAuth as the Microsoft 365 default; a warning on the password option; the 5.7.30 message mapped | stale "April 2026" dates |
| P9 | Google Workspace: less secure apps off (password SMTP stopped working in 2025), app passwords need 2-Step Verification, SMTP relay recommended for devices and apps ([support.google.com/a/answer/176600](https://support.google.com/a/answer/176600), [transition to OAuth](https://knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth?hl=en)) | Google preset = relay (IP or auth) first, app password second | asking for the account password |
| P10 | SmartSched: `components/settings/calendar-push-admin.tsx` KVKK sign-off pattern, `channels.admin.*` (missing list, "Genel adres yok"), `sso.users.*` (break-glass warning), `signin.*` copy, `aiAdmin.*` provider cards | the KVKK acknowledgement, the "missing: …" sentence, the break-glass rule, existing wording | a second, different KVKK pattern |

Licences: all of the above are pattern references; no code or assets copied. Brand marks: the **sign-in page** uses the
Microsoft logo (four squares, per Microsoft identity platform branding, already in sign-in.md §7) and the official Google
"G" (Google branding guidelines permit it for Sign in with Google buttons; ship Google's SVG unmodified with its source
noted in `components/ui/SOURCES.md`). The **admin gallery** uses text monograms (W3-IDP `BADGES`: MS, G, OIDC, SAML, LDAP;
plus SMTP, ICS, AI…), so no third-party logo is needed there.

## 3. Information hierarchy

```
Yönetim › Entegrasyonlar                                                    [Entegrasyon ara]
├─ chips: Tümü · Kimlik n · E-posta n · Takvim n · Kanallar n · Webhook ve otomasyon n · Yapay zekâ n
├─ summary line: "6 bağlı · 1 hata · 9 yapılandırılmadı"  (status words, counts)
├─ "Dikkat isteyen" row (only if any card is in error): one line per card + "Sorunu gider" (opens its sheet at the failing step)
├─ Kimlik            Microsoft 365 · Google Workspace · Kurum girişi (OIDC, presets) · Kurum girişi (SAML) · LDAP · [+ Sağlayıcı ekle]
│                    + "Giriş sayfası" card (button order, preview)
├─ E-posta           E-posta (SMTP)  (+ "Şablonlar" link to W3-MAIL's template screen)
├─ Takvim            Takvim akışları (ICS) · Google Takvim aktarımı · Microsoft 365 takvim aktarımı   (existing owners)
├─ Kanallar          Web push · Telegram · WhatsApp · SMS · Teams · Slack                              (channels admin)
├─ Webhook ve otomasyon  Webhook uç noktaları · (Zapier/Make/n8n via webhook recipes)                   (webhooks admin)
└─ Yapay zekâ        Anthropic · OpenAI-uyumlu · Google Gemini                                          (/admin/ai)
```

Order inside an area is fixed (does not reorder when a status changes, so muscle memory holds). Deep links:
`/admin/integrations?area=identity`, `/admin/integrations/<key>` opens the sheet (`?step=3` for a step).

## 4. Gallery

### 4.1 Card anatomy (1440: 4 columns of 272 px, gap 18; 1024: 3; 768: 2; < 600: list rows)

| Part | Content | Notes |
|---|---|---|
| Monogram | 40 × 40, `fill-2` bg, hairline, 13/700 text | W3-IDP `BADGES`; decorative (`aria-hidden`) |
| Name | 15/600 `label-1` | admin label for IdPs ("Okta", "Kampüs girişi") |
| Summary | 12/400 `label-2`, one line, ellipsis with full text in `title` and accessible description | e.g. "Entra ID · tek kiracı", "Shibboleth · YETKİM", "e-posta hizmeti · yurt dışı" |
| Status | `StatusDot` + word: **Bağlı** (feasible), **Yapılandırılmadı** (hollow dot, label-2), **Hata** (infeasible), **Kapalı** (configured but off; filled grey), **Bilinmiyor** (`unknown`: dashed dot, "Durum alınamadı") | W3-HUB `STATUSES`; word always visible |
| Last check | "Son kontrol: 4 dk önce · başarılı" / "· 535 5.7.3" / "Henüz kurulmadı" | relative time (Intl), absolute in tooltip |
| Changed | "Son değişiklik: Mehmet Kaya, 17 Eki 19:40" | from the audit trail (`changed_by`, `changed_at`) |
| Footer | **Kur** (primary) when `not_configured`; **Yönet** (secondary) otherwise; `Switch` "Kullanımda" when configured | external owner: "Yönet ↗" opens its screen |
| Error | 2 px infeasible edge + the first error line under the status | also listed in "Dikkat isteyen" |

Switch behaviour: off → on is allowed directly only when the last test passed and nothing is missing; otherwise the
switch opens the sheet at the missing step (W3-HUB `toggle.enable_in_setup`). On → off asks for confirmation when it has
consequences (§5.6).

### 4.2 "+ Sağlayıcı ekle" (Kimlik)
A dashed card opens a picker sheet: Microsoft 365 (Entra ID) · Google Workspace · OpenID Connect (presets: Okta,
Keycloak, Auth0, Authentik, ADFS, Genel) · SAML 2.0 (presets: Shibboleth IdP, YETKİM federasyonu (eduGAIN), ADFS (SAML),
Genel) · LDAP / Active Directory (opens the existing LDAP settings). Each row: monogram, name, one-line description
(W3-IDP `DESCRIPTIONS`). Several OIDC/SAML providers may coexist (each gets a slug, `RESERVED_SLUGS` blocked); Microsoft
and Google are one each.

### 4.3 "Giriş sayfası" card (Kimlik)
Button order (drag handle + up/down buttons for keyboard), "Ana yöntem" (first), "Kullanıcı adı ve parola formu"
(`Gizli: yalnız ?method=local` / `Açılır bağlantı` / `Kapalı` with the break-glass guard), a live preview at 390 and
desktop width (§6), and "Son girişi hatırla" (on).

## 5. Guided setup sheet

Desktop: right sheet 608 px (720 px for SMTP), full height, scrim 28 %; phone: full-screen page with a back button,
step "Adım 2 / 5" + progress bar, sticky footer (Geri · İleri) above the home indicator. Header: monogram, "{name} ile
giriş" (or "E-posta (SMTP)"), "Son değişiklik: <ad>, <zaman> · Taslak paylaşılır", close (✕). Steps on desktop as a
vertical stepper (done ✓ / current / upcoming) that is also a navigation list (a done step can be reopened).

### 5.1 Step 1 · Ön ayar
Preset chips or tiles (OIDC: Okta / Keycloak / Auth0 / Authentik / ADFS / Genel; SAML: Shibboleth / YETKİM / ADFS /
Genel), the button label field ("Girişte görünen ad", default from `DEFAULT_LABELS`, e.g. "Okta" → button "Okta ile
giriş yap"), the slug (shown, editable, validated `^[a-z][a-z0-9-]{1,39}$`), and for Entra/Google the domain
("uni.edu.tr"). Microsoft and Google have no presets: step 1 is the domain + label only.

### 5.2 Step 2 · Sağlayıcıda kaydet (copy values)
Numbered short steps (W3-IDP `STEPS` / preset `steps`, TR/EN), a link "{Console} aç ↗" (Entra yönetim merkezi, Google
Cloud Console, Okta Admin, Keycloak admin), then **copy fields**, generated from `public_url` (W3-IDP `console_values`):

| Kind | Values to copy (label TR / EN) |
|---|---|
| Entra | Yeniden yönlendirme URI'si (Web) / Redirect URI (Web) · Ön kanal oturum kapatma URL'si / Front-channel logout URL · API izinleri (Microsoft Graph, temsilci): `openid profile email User.Read` |
| Google | Yetkili JavaScript kaynağı / Authorised JavaScript origin · Yetkili yönlendirme URI'si / Authorised redirect URI · Kapsamlar / Scopes `openid email profile` |
| OIDC | Yönlendirme adresi / Sign-in redirect URI · Oturum kapatma sonrası adres / Post-logout redirect URI · Kapsamlar / Scopes (`openid profile email` + preset extras, e.g. `groups`) |
| SAML | SP meta veri adresi / SP metadata URL (primary) · Varlık kimliği (Entity ID) · ACS adresi (Assertion Consumer Service URL, HTTP-POST) · SLO adresi · NameID biçimi: persistent · Öznitelikler: `mail`, `displayName`, `eduPersonPrincipalName` (+ `eduPersonEntitlement`) · "SP meta verisini indir (.xml)" |

**Copy field** (component `CopyField`, in-house): label (13/600), read-only value in monospace 13 px on `fill-3` with the
whole value visible (wraps, never truncated, `user-select: all`), button **Kopyala** (44 px; 36 px fine pointer) →
label swaps to **✓ Kopyalandı** for 1.5 s in place (no toast), `aria-live="polite"` "{label} kopyalandı". If the
Clipboard API fails: the value gets selected and the message reads "Kopyalanamadı; değer seçildi, Ctrl+C ile kopyalayın."
"Tümünü kopyala" (secondary) copies all values as `Label: value` lines for an e-mail to IT. Plus "Bu adımları BT'ye
gönder" (mailto with the same text; no secrets ever).

Missing `public_url`: step 2 shows a danger `Alert` "Önce panelin genel adresini ayarlayın; sağlayıcıya verilecek adresler
ondan üretilir." + "Genel adresi ayarla" (Ayarlar › Genel), and **İleri** is disabled (n8n's localhost lesson, P2). A
`http://` or `localhost` public URL shows warning "Sağlayıcılar yalnızca https adresleri kabul eder."

### 5.3 Step 3 · Değerleri yapıştır
Fields from W3-IDP `FIELDS` with TR/EN labels and hints:

| Key | Label TR / EN | Hint TR | Validation |
|---|---|---|---|
| `tenant_id` | Dizin (kiracı) kimliği / Directory (tenant) ID | Entra › Genel bakış'ta; GUID biçiminde. | GUID; "common/organizations" rejected: "Tek kiracı gerekli: kurumunuzun kiracı kimliğini girin." |
| `client_id` | Uygulama (istemci) kimliği / Application (client) ID | | non-empty; GUID for Entra |
| `client_secret` | İstemci gizli anahtarı / Client secret | "Değer" sütunu; "Gizli anahtar kimliği" değil. | write-only |
| `secret_expires` | Gizli anahtarın bitiş tarihi (isteğe bağlı) / Secret expiry (optional) | 30 gün kala yöneticilere hatırlatılır. | date ≥ today |
| `domain_hint` | Alan adı ipucu / Domain hint | | domain |
| `hosted_domains` | Kurum alan adları / Workspace domains | Virgülle ayırın: uni.edu.tr, ogr.uni.edu.tr | domains |
| `issuer` | Yayıncı (issuer) adresi / Issuer URL | Örnek: https://uni.okta.com/oauth2/default | https, no trailing `/.well-known` (stripped with a note) |
| `groups_claim`, `roles_claim` | Grup / rol talebi adı / Groups / roles claim | rol eşlemesi için (5.5) | |
| `trust_email` | E-posta doğrulanmış sayılsın / Treat e-mail as verified | Yalnız sağlayıcı e-postaları doğruluyorsa açın. | switch, warning tone |
| `metadata_url` / `metadata_xml` | IdP meta veri adresi / IdP metadata URL · ya da XML yapıştırın / or paste XML | Federasyon meta verisiyse IdP varlık kimliğini de girin. | one of the two |
| `idp_entity_id`, `email_attribute`, `name_attribute`, `groups_attribute` | (SAML advanced, collapsed) | | |

**Secret field** (write-only): empty → password input with show/hide; saved → "•••••••• kayıtlı · 17 Eki" + "Değiştir"
(opens an empty input; the secret never returns to the browser; W3-HUB never returns masked fragments). Pasting a
value with spaces/quotes trims them and says so ("Baştaki ve sondaki boşluklar silindi."). Paste-detect: pasting a GUID
into "Gizli anahtar" shows warning "Bu bir kimliğe benziyor; gizli anahtarın 'Değer' sütununu yapıştırın."
Draft autosave on blur (server-side, shared): "Taslak kaydedildi · 19:42".

### 5.4 Step 4 · Bağlantıyı dene
"Bağlantıyı dene" runs server-side checks and streams one row per check (word + icon; "Kontrol ediliyor…" while
running). Then **"Kendi hesabımla dene"** opens the provider's sign-in in a popup (or same tab on phones) and returns to
the sheet with the real claims ("Giriş başarılı: ayse.yilmaz@uni.edu.tr · gruplar: 3"). Step 5 unlocks when the server
checks pass **and** the round trip succeeded (SAML/OIDC/Entra/Google) — LDAP and SMTP have their own tests.

Checks per kind (TR / EN):

| Kind | Checks |
|---|---|
| Entra | Keşif belgesi alındı / Discovery document fetched · Kiracı doğru: {tenant_name} / Tenant is {tenant_name} · İstemci kimliği ve gizli anahtar kabul edildi / Client ID and secret accepted · Deneme girişi / Test sign-in |
| Google | İstemci kabul edildi · Alan adı {domain} için `hd` doğrulandı · Deneme girişi |
| OIDC | Keşif belgesi ({issuer}/.well-known/openid-configuration) · Yayıncı eşleşiyor · JWKS alındı ({n} anahtar) · İstemci kabul edildi · Deneme girişi · Grup talebi geldi (if configured) |
| SAML | Meta veri okundu · İmza sertifikası geçerli ({date} tarihine kadar) · Deneme girişi: imza, hedef kitle, zaman, NameID |

**Error translation** (cause · fix · step to return to; the raw code under "Ayrıntı" for IT):

| Provider says | TR (cause + fix) | EN | Back to |
|---|---|---|---|
| `AADSTS50011` redirect mismatch | Yönlendirme adresi Entra'daki kayıtla eşleşmiyor. 2. adımdaki adresi Yeniden yönlendirme URI'si (Web) olarak ekleyin. | The redirect URI does not match the Entra registration. Add the address from step 2 as Redirect URI (Web). | 2 |
| `AADSTS7000215` / `7000222` | İstemci gizli anahtarı yanlış ya da süresi dolmuş. Entra'da yeni bir gizli anahtar oluşturup "Değer"i yapıştırın. | The client secret is wrong or expired. Create a new one in Entra and paste its Value. | 3 |
| `AADSTS700016` / `90002` | Bu uygulama bu kiracıda bulunamadı. Kiracı kimliğini ve uygulama kimliğini kontrol edin. | The application was not found in this tenant. Check the tenant and application IDs. | 3 |
| `AADSTS65001` consent | Kurum yöneticisinin uygulamaya izin vermesi gerekiyor. Entra › API izinleri › "{org} için yönetici onayı ver". | An administrator must grant consent: Entra › API permissions › Grant admin consent. | 2 |
| Google `redirect_uri_mismatch` | Yönlendirme adresi Google'daki istemciyle eşleşmiyor. 2. adımdaki adresi Yetkili yönlendirme URI'si olarak ekleyin. | … Authorised redirect URI … | 2 |
| Google `org_internal` / `hd` mismatch | Bu hesap {domain} alanında değil. Kurum hesabınızla deneyin ya da alan adını düzeltin. | This account is not in {domain}. … | 1 |
| Google `invalid_client` | İstemci kimliği veya gizli anahtar yanlış. | Client ID or secret is wrong. | 3 |
| OIDC discovery 404 / not JSON | Yayıncı adresinde keşif belgesi yok. Adresi yetkilendirme sunucusunun kökü olarak girin (…/oauth2/default). | No discovery document at the issuer. … | 3 |
| OIDC issuer mismatch | Belgedeki yayıncı ({found}) girilen adresle aynı değil. | The issuer in the document ({found}) differs from the one entered. | 3 |
| TLS / certificate error | Sağlayıcının sertifikası doğrulanamadı ({detail}). Kurum içi bir sertifika yetkilisi kullanılıyorsa BT'ye iletin. | The provider's certificate could not be verified. … | — |
| Timeout / DNS | Sağlayıcıya ulaşılamadı ({host}). Sunucunun dışarıya çıkışı kapalı olabilir. | Could not reach {host}. Outbound access may be blocked. | — |
| SAML signature invalid | Onaylamanın imzası doğrulanamadı. IdP meta verisini yeniden alın (sertifika değişmiş olabilir). | The assertion signature failed. Re-fetch the IdP metadata. | 3 |
| SAML audience mismatch | Hedef kitle (Audience) SmartSched'in varlık kimliği değil. IdP'de 2. adımdaki varlık kimliğini kullanın. | Audience is not SmartSched's entity ID. | 2 |
| SAML clock skew | Saatler arasında {n} dakika fark var. Sunucuların saatini (NTP) kontrol edin. | Clocks differ by {n} minutes. | — |
| SAML NameID / e-mail missing | Onaylamada e-posta özniteliği yok. IdP'de `mail` özniteliğini yayımlayın. | No e-mail attribute in the assertion. | 2 |
| Popup blocked / closed | Giriş penceresi açılmadı ya da kapatıldı. Yeniden deneyin. | The sign-in window was blocked or closed. | 4 |

### 5.5 Step 5 · Etkinleştir
- **Kimler girebilir** (`SegmentedControl`): "Yalnız davet edilenler" / "Kurum hesabı olan herkes (en düşük rol)" (sign-in.md
  §1 owner decision; default: invite-only for OIDC/SAML, everyone for Entra/Google where the tenant/domain is pinned).
- **Varsayılan rol** (`NativeSelect`, roles without admin permissions only; admin roles never come from an IdP).
- **Rol eşlemesi** (collapsed, optional): rows "Grup `{value}` → rol {role}", tested against the claims of the step-4
  round trip ("Sizin gruplarınızla: Planlama yöneticisi").
- **Giriş sayfasında göster** (on) + position in the button order.
- Summary sentence: "Etkinleştirince giriş sayfasında 'Okta ile giriş yap' görünür. Yeni kişiler davetle girer; rolleri
  'Standart kullanıcı'." → **Etkinleştir** (primary) · "Kapalı kaydet" (secondary: save configured but off).
- After enabling: success check (motion §10) + toast "Okta ile giriş açıldı" + the card shows Bağlı.

### 5.6 Disable, edit, delete
- Disable (switch off or "Kapat"): confirm dialog "Okta ile giriş kapatılsın mı?" body "{n} kişi yalnız bu yöntemle giriş
  yapıyor; kapatırsanız giriş yapamazlar. Açık oturumları kapanmaz." + "Kapat". **Blocked** when it would leave no way in
  for any admin: "Bu, yöneticilerin kullandığı son giriş yöntemi. Önce bir yerel yönetici hesabı (acil durum) oluşturun."
  (sso.users.breakGlass*).
- Editing a live provider: changes are a draft until tested; the live configuration keeps working ("Canlı ayar
  değişmedi; yeni değerler denendikten sonra geçerli olur.").
- Delete (Yönet › ⋯ › "Sağlayıcıyı sil", only when off): "Bağlı {n} kimlik silinir; kişilerin hesapları kalır."
- Concurrency: save sends the version; on conflict: warning `Alert` "Bu ayar siz düzenlerken Ayşe Yılmaz tarafından
  değiştirildi (19:44). Değişikliklerini görmek için yenileyin; sizin girdikleriniz bu sekmede kalır." + "Yenile".

## 6. Sign-in page with several providers (amends sign-in.md §0 and §7 "no second provider with equal weight")

Why the amendment: sign-in.md was written for Microsoft-only. With Google enabled, Google's branding terms require its
button to be at least as prominent as other third-party options (P6); with Okta/SAML the institution may have several
doors. So: **all IdP buttons are equal**; the local form stays the quiet second door.

| Rule | Detail |
|---|---|
| One IdP on | sign-in.md unchanged (Microsoft or the one provider as the single primary button) |
| ≥ 2 IdPs on | a vertical stack, full column width, 44 px fine / 48 px coarse, 12 px gap, same radius; order = the admin's order (§4.3) |
| Visible | max 3; more → "Diğer giriş yolları ({n}) ▾" disclosure (same pattern as the password disclosure, opens in place) |
| Microsoft | sign-in.md §7 spec unchanged ("Microsoft ile giriş yap", four-square logo, `#FFFFFF`/`#5E5E5E`/`#8C8C8C`) |
| Google | official G logo 18 px; label "Google ile oturum açın" / "Sign in with Google"; light `#FFFFFF` fill, 1 px `#747775` edge, text `#1F1F1F`; dark `#131314` fill, `#8E918F` edge, `#E3E3E3` text; Roboto Medium 14/20 where available (falls back to the system font); radius 12 to match the stack (the guidelines allow rectangular or pill shapes) |
| OIDC / SAML | neutral: `--mat` card fill, `--border-control` edge, `label-1` text 15/600; leading 20 px monogram or an admin-uploaded square icon (PNG/SVG ≤ 32 KB, sanitised); label "{provider_name} ile giriş yap" / "Sign in with {provider_name}" |
| Last used | chip "Son girişiniz bu yöntemle" above the matching button (from a first-party cookie; extends `signin.local.lastMethod`) |
| Invite link (`?invite=`) | only the invited method's button + the invite banner (sign-in.md §12); "Başka bir yöntemle giriş yap" link under it |
| Footnote | one line under the stack: "Kurum hesabınızla ilk girişte hesabınız standart kullanıcı olarak açılır. Rolünüzü yalnızca bir yönetici değiştirebilir." (shown only if any on-provider allows sign-up) |
| Errors | provider-specific errors reuse `signin.error.*` with `{provider_name}` ("{provider_name}'a ulaşılamıyor" is **not** allowed: no suffix on placeholders → "{provider_name} şu anda yanıt vermiyor.") |
| Busy | the pressed button shows "{provider_name} sayfasına yönlendiriliyor…"; the other buttons stay enabled but a second click is ignored |

P2 idea (not in this wave): "E-postanızla devam edin" field that routes by domain (home-realm discovery) when more than 3
providers exist.

## 7. SMTP preset wizard (E-posta (SMTP) card; built by W3-MAIL in the sheet shell)

Steps: **1 Sağlayıcı · 2 Bağlantı · 3 Gönderen · 4 Alan adı · 5 Deneme · 6 Etkinleştir** (horizontal step bar on desktop,
"Adım n / 6" + bar on phones).

### 7.1 Presets (step 1, 3 × 3 tiles)

| Preset | Host · port · security | Auth options (default first) | Notes shown |
|---|---|---|---|
| Microsoft 365 | smtp.office365.com · 587 · STARTTLS | **OAuth 2.0** ("Microsoft ile bağlan": app registration with `SMTP.Send`; copy fields like §5.2) · kullanıcı adı + parola (warning) | warning callout: Basic auth off by default from December 2026 (P8); "Gönderen adresine 'Farklı gönder' izni gerekir" |
| Google Workspace | **smtp-relay.gmail.com · 587 · STARTTLS** (relay: IP allow-list or SMTP auth) · or smtp.gmail.com · 587 with an app password | relay · uygulama parolası | "Uygulama parolası, 2 adımlı doğrulaması açık hesapta üretilir." (P9); never the account password |
| Yandex 360 | smtp.yandex.com · 465 · SSL | uygulama parolası | common in Türkiye |
| Kurum SMTP sunucusu | host · 25/587 · STARTTLS or none | none (IP-based) · kullanıcı adı + parola | "Güvenlik: yok" shows warning "Bağlantı şifresiz; yalnız kurum ağı içinde kullanın." |
| Amazon SES | email-smtp.{region}.amazonaws.com · 587 · STARTTLS | SMTP kimlik bilgileri | **yurt dışı** |
| Postmark | smtp.postmarkapp.com · 587 · STARTTLS | sunucu belirteci (kullanıcı adı = parola) | **yurt dışı** |
| Resend | smtp.resend.com · 465 SSL / 587 | API anahtarı (kullanıcı adı `resend`) | **yurt dışı** |
| Brevo | smtp-relay.brevo.com · 587 · STARTTLS | SMTP anahtarı | **yurt dışı** |
| Özel | blank | any | |

Presets fill and **lock** host/port/security ("Değiştir" unlocks with a note "Ön ayar dışına çıkıyorsunuz").
"Yurt dışı" presets add, at step 3, the KVKK acknowledgement (same component as calendar sync): "Bildirim e-postaları
(alıcı adı, adresi, rezervasyon bilgileri) {provider} sunucularına (yurt dışı) aktarılır. KVKK md. 9." + checkbox
"Bildirimi okudum; kurum adına onaylıyorum." — recorded with name and date.

### 7.2 Steps 2–6
- **2 Bağlantı**: locked preset fields, username, secret field (write-only, §5.3), timeout (advanced).
- **3 Gönderen**: Gönderen adresi (must be a mailbox the server may send as), Gönderen adı (default "{org kısa adı}
  SmartSched", emails.md §6), Yanıt adresi (optional, recommended), panel's public URL check (links in mails).
- **4 Alan adı** (P7): DNS lookups for the from-domain, one row each with a status word: **SPF** (Bulundu · {preset}'i
  kapsıyor / Bulundu · kapsamıyor / Yok), **DKIM** (selector per preset: `selector1/2._domainkey` for Microsoft 365,
  `google._domainkey`, `resend._domainkey`; Bulundu / Bulunamadı / "Kurum sunucusu: kontrol edilemez"), **DMARC**
  (Bulundu `p=quarantine` / Yok · önerilir). Missing records show the record to add with a Kopyala field. This step
  warns but never blocks ("Kayıtlar eksikse iletiler istenmeyene düşebilir.") and has "Yeniden kontrol et".
- **5 Deneme**: "Deneme iletisi gönder" (to the admin's own address, editable) → streamed rows: Bağlantı · TLS · Kimlik
  doğrulama · Gönderen izni · Gönderildi (server accepted) ; then "Deneme iletisi gelen kutunuza ulaştı mı?" **Evet,
  geldi** / **Hayır / istenmeyende** (the "no" opens tips: check spam, DKIM/DMARC rows, the From permission).
- **6 Etkinleştir**: summary; if the outbox has `UNSENT` rows: "Gönderilmeyi bekleyen {n} bildirim var." choice
  **Yalnız yenileri** (default; the old ones are marked "Gönderilmedi: SMTP sonradan açıldı") / **Bekleyenleri de gönder**
  (only rows younger than 7 days); then **Etkinleştir**.

SMTP error translation (step 5):

| Server says | TR | EN |
|---|---|---|
| `535 5.7.3` / `535 5.7.8` | Kullanıcı adı veya parola kabul edilmedi. Uygulama parolası gerekiyorsa onu girin. | Username or password rejected. Use an app password if required. |
| `550 5.7.30` / "basic auth disabled" | Microsoft 365 bu kiracıda parola ile SMTP'yi kapatmış. OAuth 2.0 ile bağlanın. | Microsoft 365 has password SMTP turned off for this tenant. Connect with OAuth 2.0. |
| `534 5.7.9` (Gmail app password) | Google bu hesap için uygulama parolası istiyor. | Google requires an app password for this account. |
| `530 5.7.0 Must issue STARTTLS` | Sunucu şifreli bağlantı istiyor. Güvenliği STARTTLS yapın. | The server requires encryption. Set security to STARTTLS. |
| `550 5.7.60` / SendAs denied | Bu hesap {from} adresiyle gönderemiyor. Gönderen adresini değiştirin ya da izin verin. | This account cannot send as {from}. |
| `554` relay denied | Sunucu bu adresten aktarım kabul etmiyor (IP izin listesi?). | The server refuses to relay from here (IP allow-list?). |
| connection refused / timeout | {host}:{port} ulaşılamıyor. Bağlantı noktası kapalı olabilir (465/587). | Can't reach {host}:{port}. The port may be blocked. |
| TLS hostname mismatch | Sertifika {host} adı için değil. | The certificate is not for {host}. |

## 8. States and copy (keys; TR / EN)

| Key | TR | EN |
|---|---|---|
| `integrations.title` | Entegrasyonlar | Integrations |
| `integrations.lead` | Kurum genelindeki bağlantılar. Her yönetici aynı ayarları görür; değişiklikler denetim kaydına yazılır. | Organisation-wide connections. Every administrator sees the same settings; changes are audited. |
| `integrations.search` | Entegrasyon ara | Search integrations |
| `integrations.area.{identity,email,calendar,channels,automation,ai}` | Kimlik · E-posta · Takvim · Kanallar · Webhook ve otomasyon · Yapay zekâ | Identity · E-mail · Calendar · Channels · Webhooks and automation · AI |
| `integrations.summary` | {connected} bağlı · {error} hata · {notConfigured} yapılandırılmadı | {connected} connected · {error} with errors · {notConfigured} not set up |
| `integrations.attention` | Dikkat isteyen | Needs attention |
| `integrations.fix` | Sorunu gider | Fix it |
| `integrations.status.{connected,not_configured,error,disabled,unknown}` | Bağlı · Yapılandırılmadı · Hata · Kapalı · Bilinmiyor | Connected · Not set up · Error · Off · Unknown |
| `integrations.lastCheck` | Son kontrol: {time} · {result} | Last check: {time} · {result} |
| `integrations.never` | Henüz kurulmadı | Not set up yet |
| `integrations.changed` | Son değişiklik: {name}, {time} | Last changed: {name}, {time} |
| `integrations.setup` / `.manage` | Kur / Yönet | Set up / Manage |
| `integrations.enabled` | Kullanımda | In use |
| `integrations.readOnly` | Yalnız görüntüleme | View only |
| `integrations.external` | {screen} ekranında yönetilir | Managed on the {screen} screen |
| `integrations.empty.search` | "{q}" ile eşleşen entegrasyon yok. | No integration matches "{q}". |
| `integrations.loadError` | Durum alınamadı. Kartlar son bilinen hâliyle gösteriliyor. | Couldn't load status. Showing the last known state. |
| `integrations.sheet.step` | Adım {n} / {total} | Step {n} of {total} |
| `integrations.sheet.steps.{preset,console,values,test,enable}` | Ön ayar · Sağlayıcıda kaydet · Değerleri yapıştır · Bağlantıyı dene · Etkinleştir | Preset · Register at the provider · Paste values · Test connection · Enable |
| `integrations.sheet.draftSaved` | Taslak kaydedildi · {time} | Draft saved · {time} |
| `integrations.sheet.draftBy` | Taslak: {name} başladı, {time} | Draft started by {name}, {time} |
| `integrations.sheet.conflict` | Bu ayar siz düzenlerken {name} tarafından değiştirildi ({time}). Değişikliklerini görmek için yenileyin; sizin girdikleriniz bu sekmede kalır. | {name} changed this setting while you were editing ({time}). Refresh to see their changes; what you typed stays in this tab. |
| `integrations.copy` / `.copied` / `.copyFailed` | Kopyala / Kopyalandı / Kopyalanamadı; değer seçildi, Ctrl+C ile kopyalayın. | Copy / Copied / Couldn't copy; the value is selected, press Ctrl+C. |
| `integrations.copyAll` / `.mailIt` | Tümünü kopyala / Bu adımları BT'ye gönder | Copy all / Send these steps to IT |
| `integrations.noPublicUrl` | Önce panelin genel adresini ayarlayın; sağlayıcıya verilecek adresler ondan üretilir. | Set the panel's public address first; the values for the provider are built from it. |
| `integrations.httpsOnly` | Sağlayıcılar yalnızca https adresleri kabul eder. | Providers accept https addresses only. |
| `integrations.secret.saved` / `.change` | •••••••• kayıtlı · {date} / Değiştir | •••••••• saved · {date} / Change |
| `integrations.secret.trimmed` | Baştaki ve sondaki boşluklar silindi. | Leading and trailing spaces were removed. |
| `integrations.test.run` / `.running` / `.again` / `.self` | Bağlantıyı dene / Kontrol ediliyor… / Yeniden dene / Kendi hesabımla dene | Test connection / Checking… / Try again / Try with my account |
| `integrations.test.ok` | Tüm kontroller geçti. | All checks passed. |
| `integrations.test.backTo` | {n}. adıma dön | Back to step {n} |
| `integrations.test.detail` | Ayrıntı: {code} | Detail: {code} |
| `integrations.enable` / `.saveOff` | Etkinleştir / Kapalı kaydet | Enable / Save as off |
| `integrations.enabledToast` | {name} açıldı | {name} is on |
| `integrations.disable.title` | {name} kapatılsın mı? | Turn off {name}? |
| `integrations.disable.body` | {n} kişi yalnız bu yöntemle giriş yapıyor; kapatırsanız giriş yapamazlar. Açık oturumları kapanmaz. | {n} people sign in only this way; they won't be able to sign in. Open sessions stay. |
| `integrations.disable.lastAdmin` | Bu, yöneticilerin kullandığı son giriş yöntemi. Önce bir yerel yönetici hesabı (acil durum) oluşturun. | This is the last sign-in method administrators use. Create a local (break-glass) admin account first. |
| `identity.who.{invited,everyone}` | Yalnız davet edilenler / Kurum hesabı olan herkes (en düşük rol) | Invited people only / Anyone with an organisation account (lowest role) |
| `identity.button.generic` | {provider} ile giriş yap | Sign in with {provider} |
| `identity.button.google` | Google ile oturum açın | Sign in with Google |
| `identity.more` | Diğer giriş yolları ({n}) | Other ways to sign in ({n}) |
| `identity.lastUsed` | Son girişiniz bu yöntemle | You used this last time |
| `identity.busy` | {provider} sayfasına yönlendiriliyor… | Redirecting to {provider}… |
| `identity.unavailable` | {provider} şu anda yanıt vermiyor. Birkaç dakika sonra tekrar deneyin. | {provider} isn't responding. Try again in a few minutes. |
| `email.wizard.steps.{provider,connection,sender,domain,test,enable}` | Sağlayıcı · Bağlantı · Gönderen · Alan adı · Deneme · Etkinleştir | Provider · Connection · Sender · Domain · Test · Enable |
| `email.wizard.abroad` | Bildirim e-postaları (alıcı adı, adresi, rezervasyon bilgileri) {provider} sunucularına (yurt dışı) aktarılır. KVKK md. 9. | Notification e-mails (recipient name, address, booking details) are transferred to {provider} servers abroad. KVKK Art. 9. |
| `email.wizard.arrived` / `.yes` / `.no` | Deneme iletisi gelen kutunuza ulaştı mı? / Evet, geldi / Hayır / istenmeyende | Did the test message arrive? / Yes, it arrived / No / in spam |
| `email.wizard.queued` | Gönderilmeyi bekleyen {n} bildirim var. | {n} notifications are waiting to be sent. |
| `email.wizard.onlyNew` / `.sendQueued` | Yalnız yenileri / Bekleyenleri de gönder (son 7 gün) | New ones only / Also send the waiting ones (last 7 days) |
| `email.wizard.m365Basic` | Exchange Online, parola ile SMTP'yi Aralık 2026'dan itibaren varsayılan olarak kapatır. OAuth 2.0 ile bağlanın. | Exchange Online turns password SMTP off by default from December 2026. Connect with OAuth 2.0. |

## 9. Components (existing first)

| Component | Source | Licence | Use |
|---|---|---|---|
| `Card`, `Badge`, `Switch`, `Button`, `Input`, `InputGroup`, `NativeSelect`, `SegmentedControl`, `Alert`, `Sheet`, `Dialog`, `Chip`, `EmptyState`, `Skeleton`, `BusyLabel` | `smartsched/frontend/src/components/ui` | in-house (beUI/shadcn-derived pieces per `ui/SOURCES.md`, MIT) | everything above |
| `StatusDot` + word | tokens.md §A.9 | in-house | card status |
| **new** `ConnectorCard`, `ConnectorGallery`, `AttentionRow` | `components/admin/integrations/` (W3-HUB) | in-house | §4 |
| **new** `SetupSheet` (stepper, sticky footer, draft line) | `components/admin/integrations/setup-sheet.tsx` (W3-HUB; IdP and SMTP steps plug in) | in-house | §5, §7 |
| **new** `CopyField`, `SecretField`, `CheckList` (streamed test rows) | `components/admin/integrations/` | in-house | §5.2–5.4 |
| `MicrosoftSignIn` | `components/auth/microsoft-sign-in.tsx` | in-house; Microsoft logo per Microsoft branding | §6 |
| **new** `GoogleSignIn`, `ProviderButton` | `components/identity/` (W3-IDP) | Google "G" SVG from Google's branding kit (Google brand terms, unmodified) | §6 |
| KVKK acknowledgement | the calendar-push admin pattern | in-house | §7.1 |
| transitions.dev "text-states-swap", "success-check", "panel-reveal" (free) | `scratchpad/transitions/free/*.md`; CSS copied into `components/ui/transitions/transitions-dev.css` with the required header | Transitions.dev License (use and modify, no redistribution of the library) | §10 |

## 10. Motion (per `/motion_designer`; rows for `v2/motion.md` new §3.18 Integrations)

| Moment | Purpose | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|---|
| Sheet open/close | where the setup lives (grows from the right edge, returns there) | x 100 % → 0, scrim 0 → 28 % | `sheet`; exit 180 ms `--ease-in` | 100 ms fade | opaque sheet |
| Step change | forward/back direction | content x ±16 px + opacity; stepper current dot moves | `smooth` (≤ 280 ms); dot `glassMorph` | instant swap | same |
| Copy → Copied | did it work, in place | label crossfade with the check icon (transitions.dev *text-states-swap*/*icon-swap* retuned: 120 ms out, 180 ms in, no blur) | `--dur-fast`/`--dur-base` | instant swap; aria-live still announces | same |
| Test rows arrive | results arrive one by one as the server reports them (not staged) | each row fades in + y 4 px when its event arrives; no stagger timer | `smooth` | ≤ 100 ms fade | same |
| Running check | ongoing work | "Kontrol ediliyor…" text + small spinner (loop, stops with the check) | loop | static "…" + text | same |
| Test passed / enabled | it worked | success check draw (transitions.dev *success-check* retuned: no 80° rotate, no 40 px bob, no blur; path draw 220 ms + scale 0.9 → 1) | `bouncySubtle` | final frame | same |
| Error row | what failed | the error callout appears in place (no shake: the user did not just type it) | `--dur-base` opacity | instant | same |
| Card status change (gallery) | a state changed while you watch | dot colour swaps instantly, the word crossfades 180 ms; the card does not move | `--dur-base` | instant | same |
| "Dikkat isteyen" row appears/leaves | layout change | height via `layout` FLIP, content fade | `smooth` | instant | same |
| Provider stack "Diğer giriş yolları" | making room | disclosure layout FLIP (same as sign-in.md §10 password disclosure) | `smooth` | instant | same |

No motion on: filter chips/search results (swap in place), the switch (its own `snappy` thumb only), page load.
Hosted Motion Agent: not used here.

## 10a. Accessibility

- Gallery: `<section aria-labelledby>` per area; cards are `<article>` with the name as heading (h3); the switch has the
  accessible name "{name}: Kullanımda"; the status word is text (not only colour); the attention row is `role="status"`
  on change (polite), not on load.
- Filter chips are a `radiogroup` with counts in the name ("Kimlik, 4 entegrasyon").
- Sheet: `role="dialog"` `aria-modal`, focus to the heading on open, back to the triggering card button on close;
  `Esc` closes (asks if a draft has unsaved typing — drafts autosave, so normally no ask). Stepper = `nav` with
  `aria-current="step"`; upcoming steps are not links until reachable.
- Copy fields: the value is a read-only `<input>` (selectable, focusable) or `<code>` with `tabindex=0`; "Kopyala"'s name
  includes the label ("Yönlendirme adresini kopyala").
- Test results: a list; each row "✓ Kiracı doğru" has the word in text; the result summary is announced once
  (`role="status"`), an error moves focus to the error callout heading.
- Secret fields: `autocomplete="off"`, `spellcheck=false`, show/hide with `aria-pressed`.
- Sign-in stack: buttons are links styled as buttons (sign-in.md §7), order in DOM = visual order, "Son girişiniz" chip is
  associated with its button via `aria-describedby`.
- Touch targets 44 px (48 on coarse pointers); 16 px inputs on phones (no iOS zoom); contrast as tokens.md §A.

## 11. Mobile layout (390)

- Gallery: chips scroll horizontally; cards become 64 px rows (monogram, name, status word, chevron); the attention row
  is a full-width danger card at the top; switches move into the setup page ("Kullanımda" row at the top of step 5 /
  the manage view) so a row tap never toggles by accident.
- Setup: full-screen page, "Adım n / 5" + progress bar, one step per screen, copy fields full width with the value wrapped
  above a full-width "Kopyala" (44 px), sticky footer Geri (110) + İleri (fill) 48 px above the safe area; the keyboard
  never covers the focused field (`interactive-widget=resizes-content`, sign-in.md §5.4).
- "Kendi hesabımla dene" uses a same-tab redirect on phones and returns to `?step=4&test=done`.
- SMTP presets: 2-column tiles, then lists; DNS rows stack (record, status word, Kopyala).
- Sign-in: the stack fills the column at 16 px margins; "Diğer giriş yolları" below the 3rd button.

## 12. Wireframes

| File | Shows |
|---|---|
| `integrations-gallery-1440.svg` | chips with counts, summary line, attention row, Kimlik and mixed cards (Bağlı/Yapılandırılmadı/Kapalı/Hata) |
| `integrations-gallery-390.svg` | search, chips, attention card, 64 px rows |
| `integrations-setup-1440.svg` | Entra sheet at step 2 (copy fields, one in the "Kopyalandı" state, public-URL note) + inset of step 4 with an `AADSTS50011` translation |
| `integrations-setup-390.svg` | step 2 on a phone, full-width Kopyala, sticky footer |
| `signin-providers-1440.svg`, `signin-providers-390.svg` | equal-weight Microsoft, Google, Okta buttons, "Son girişiniz" chip, more-ways disclosure, password disclosure |
| `smtp-wizard-1440.svg` | preset tiles, Microsoft 365 OAuth warning, auth choice; inset: test rows, "did it arrive?", queued-notifications choice |
| `smtp-wizard-390.svg` | step 2 with locked preset fields and an app-password field |

## 13. Acceptance checks

| Id | Check | Pass when |
|---|---|---|
| IN-01 | Admin A configures Microsoft 365; admin B opens the gallery in another browser | B sees Bağlı and "Son değişiklik: A, <time>" |
| IN-02 | Planning admin opens the gallery | same cards, no switches, "Yalnız görüntüleme" |
| IN-03 | Card in error | appears in "Dikkat isteyen"; "Sorunu gider" opens the sheet at the failing step |
| IN-04 | Status words | each card shows one of the five words; colours never alone (axe + snapshot) |
| IN-05 | No secret in any response | `GET /integrations/status` and the provider GET never contain the secret or a fragment |
| IN-06 | Copy | "Kopyala" writes the exact value; label shows "Kopyalandı" 1.5 s; live region announces; clipboard failure selects the value |
| IN-07 | Values from public URL | changing the public URL changes every step-2 value; missing/http public URL blocks İleri with the message |
| IN-08 | Draft sharing | A fills step 3 and closes; B opens: "Taslak: A başladı" and the non-secret values are there |
| IN-09 | Conflict | A and B save the same provider; the second gets the conflict alert and keeps their typing |
| IN-10 | Test streaming | rows appear as checks finish; a wrong secret shows the 7000215 translation and "3. adıma dön" |
| IN-11 | Round trip | "Kendi hesabımla dene" with the mock IdP (:19712) returns claims and unlocks step 5 |
| IN-12 | Enable | the provider button appears on `/login` in the admin's order; toast and success check shown |
| IN-13 | Disable guard | disabling the last admin-usable method is blocked with the break-glass message |
| IN-14 | Sign-in, 2+ IdPs | all IdP buttons same height and width (±1 px), Google button colours per §6, max 3 visible |
| IN-15 | Sign-in, invite link | only the invited method is shown + "Başka bir yöntemle giriş yap" |
| IN-16 | Sign-in, last used | the chip sits above the last-used method's button |
| IN-17 | SMTP presets | choosing Microsoft 365 fills host/port/security, defaults to OAuth, shows the December 2026 warning |
| IN-18 | SMTP abroad | a "yurt dışı" preset cannot be enabled without the KVKK acknowledgement; the record has name and date |
| IN-19 | DNS step | SPF/DKIM/DMARC rows show status words and the record to add; never block |
| IN-20 | SMTP test | the sink (:2721) receives `smtp_test`; "Hayır" shows the tips; 535 shows the translated message |
| IN-21 | Queued notifications | with UNSENT rows, enabling defaults to "Yalnız yenileri"; choosing the other sends only ≤ 7-day rows |
| IN-22 | Audit | every save, test, enable, disable writes an audit row with the actor |
| IN-23 | Phone 390 | no horizontal scroll; targets ≥ 44 px; sticky footer above the keyboard and safe area |
| IN-24 | Reduced motion | sheet, step change, copy and success check end on the next frame or ≤ 100 ms fade |

## 14. Hand-off and asks

- **W3-HUB**: gallery + sheet shell (§4, §5 framework, §10); keep card order fixed; implement `CopyField`, `SecretField`,
  `CheckList`; deep links `?area=`, `/<key>?step=`.
- **W3-IDP**: steps content from `kinds.py` (already matches §5.2); add `secret_expires`, the error translation table (§5.4),
  the round-trip test, sign-up policy and role mapping (§5.5), the provider stack on `/login` (§6), and an
  `integration_status(session)` contract per provider for the hub.
- **W3-MAIL**: the SMTP wizard steps (§7) inside the shell, presets and error table, DNS check, queued-notifications choice,
  the `email.wizard.*` copy.
- **Owner of `v2/sign-in.md`**: note the §6 amendment (equal-weight buttons when ≥ 2 IdPs are on).
- **Owner of `v2/motion.md`**: copy §10 rows as §3.18.
