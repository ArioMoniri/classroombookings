# Operations panel (`/admin/ops`): status, errors, logs, Grafana

Owner: product designer (wave3-des-2026-10-17) · Status: v3.0 spec (2026-10-17) · Builder: lane **W3-OPS**
(`frontend/src/components/admin/ops/**`, `frontend/src/app/(app)/admin/ops/**`, `frontend/src/lib/api/ops.ts`, copy
`ops.*`; backend `app/api/v1/ops.py`, `app/core/observability.py`, `app/models/error_event.py`,
`deploy/observability/**`).
Grounded in the endpoints W3-OPS has already written (`GET /ops/status|requests|errors|errors/{id}|logs|dashboards|alerts`,
`POST /ops/errors/{id}/status`, error statuses `open | acknowledged | resolved | ignored`, Loki services
`backend, frontend, proxy, db, caddy, grafana, prometheus, loki, alloy`, six provisioned dashboards).
Depends on: `docs/design/tokens.md` §A (DataTable, StatusDot, BarList, Card), §2.2 status colours, dataviz conventions
(dashboard.md), `docs/design/v2/motion.md`, MOBILE.md.
Wireframes: `wireframes/ops-status-1440.svg`, `wireframes/ops-errors-logs-1440.svg`, `wireframes/ops-390.svg`.

Owner's words: "The admin panel should have operational details like Grafana for the needed services, plus an error log
and tracking."

---

## 0. BLUF

- **Yönetim › Operasyon** (`/admin/ops`), four tabs: **Durum · Hatalar · Günlükler · Panolar**.
- **Durum** leads with one sentence ("Tüm servisler çalışıyor" / "2 servis dikkat istiyor"), then firing alerts, then
  one status card per service from `GET /ops/status` (status dot + word + the one number that matters), then three
  small request charts (istek/dk, 5xx/dk, p95) as small multiples, never a dual axis.
- **Hatalar** is a grouped error list (Sentry-like: one row per fingerprint with count, first/last seen, release) with a
  lifecycle **Yeni → İnceleniyor → Çözüldü / Yok sayıldı**, a detail sheet with the scrubbed stack and a "Günlüklerde aç"
  jump by request id.
- **Günlükler** is a Loki tail per service with time window, text and level filters, and a **Canlı** mode that never
  yanks the scroll position.
- **Panolar** lists the six Grafana dashboards with "Grafana'da aç" (same-origin `/grafana/`, forward-auth) and lazy
  embedded key panels on desktop; phones get links only.
- Auto-refresh every 30 s on Durum (pausable), results replace in place, nothing animates on refresh.

## 1. Users and goals

| Persona | Goal | Where |
|---|---|---|
| System admin on call (setup.settings / planning.admin) | "Is SmartSched OK right now? If not, what is broken?" in 5 seconds | Durum headline + cards |
| Same, during an incident | "Since when, how many users, which release?" | Hatalar → detail |
| Same | "Show me what the backend logged around that request" | Günlükler (prefilled by request id) |
| IT department | "Long-term graphs, alert rules" | Panolar → Grafana |
| Admin on a phone (evening) | glance at status and acknowledge an error | phone layout |

## 2. References (public, checked 2026-10-17)

| # | Reference | Borrow | Avoid |
|---|---|---|---|
| O1 | Atlassian Statuspage component states: Operational, Degraded performance, Partial outage, Major outage, Under maintenance; most severe wins ([Statuspage: what is a component](https://support.atlassian.com/statuspage/docs/what-is-a-component), [show service status with components](https://support.atlassian.com/statuspage/docs/show-service-status-with-components/)) | a fixed vocabulary of states mapped to our `ok / warn / down / unknown`; headline = worst card | colour-only states (we add the word) |
| O2 | Sentry issues: events grouped by fingerprint; issue shows count in 24 h / 30 d, first and last seen; states resolved / ignored / archived, resurfacing on new events ([Sentry issues](https://docs.sentry.io/product/issues), [grouping and fingerprints](https://docs.sentry.io/product/issues/grouping-and-fingerprints/), [error issues](https://docs.sentry.io/product/issues/issue-details/error-issues/)) | the error-group row, the lifecycle, "yeniden açıldı" when a resolved group fires again | Sentry's density of tabs and tags |
| O3 | Vercel runtime logs: Timeline filter (last hour, 3 days, custom), **Live mode**, Level filter (Warning / Error / Fatal) ([Vercel runtime logs](https://vercel.com/docs/logs/runtime)) | live toggle + level + time window in one filter row; level read from the record | infinite retention promises (Loki retention is the limit, shown) |
| O4 | Grafana embedding: `/d-solo/{uid}/{slug}?panelId=` single-panel iframes, `allow_embedding`, auth proxy with `X-WEBAUTH-USER` ([last9: Grafana iframe embedding](https://last9.io/blog/how-to-get-grafana-iframe-embedding-right), [SigNoz: embed with auth](https://signoz.io/guides/how-to-authenticate-and-embedded-grafana-charts-into-iframe/)) | same-origin `/grafana/` behind the app's forward-auth (`GET /ops/grafana-auth`), lazy single-panel embeds | anonymous Grafana access |
| O5 | Vercel / Datadog service overview: status = 8 px dot + word (Vercel H6 in tokens §A.8), one number per card | card grammar | sparkline in every card |
| O6 | SmartSched `GET /ops/status` card set: api, db, queues, mail, deliveries, disk, errors, services (grafana / prometheus / loki), version, podci, alerts | exactly these cards, no invented ones | — |

Licences: pattern references only; Grafana is AGPL-3.0 and runs as a separate service (linked and iframed, not
bundled). Charts use EvilCharts (MIT) on recharts (MIT). No new UI dependency.

## 3. Information hierarchy

```
Yönetim › Operasyon                                 Son yenileme 19:42:10 · [Otomatik yenile ●]  [Grafana'yı aç ↗]
├─ Durum     headline sentence · firing alerts · service cards (grid) · requests small multiples · release + pod CI
├─ Hatalar   filters (durum, kaynak, dönem, ara) · error groups table → detail sheet
├─ Günlükler filter row (servis, süre, seviye, metin, Canlı) · log lines
└─ Panolar   6 dashboard cards (link + up to 2 embedded panels on desktop)
```

## 4. Tabs in detail

### 4.1 Durum

1. **Headline** (`type-title-2`, with `StatusDot` size 12): worst card wins (O1).
   - all ok: "Tüm servisler çalışıyor"
   - any warn: "{n} servis dikkat istiyor"
   - any down: "{n} servis çalışmıyor" (danger)
   - plus "Sürüm 3.4.1 · a1b2c3d · 17 Eki 16:05'te yayına alındı · üretim".
2. **Firing alerts** (only when any): `Alert` rows (`tone` by severity: critical → danger, warning → warning) with the
   TR summary, since when, and "Grafana'da gör ↗". Never more than 5; "+3 uyarı" link to Panolar.
3. **Service cards** (`Card` plain, 3 columns at 1440, 2 at 768, 1 list at 390). Each: name, `StatusDot` + word
   (Çalışıyor / Dikkat / Çalışmıyor / Bilinmiyor), **one key line**, an optional second line, and a link where the fix lives.

| Card (`status` key) | Key line | Second line | Link |
|---|---|---|---|
| API (`api`) | "Çalışma süresi 3 g 4 sa" | "{n} işçi süreç" | Panolar › API |
| Veritabanı (`db`) | "Gecikme 4 ms" | "Şema güncel" / "Şema eski: {current} → {head}" (warn) | — |
| İş kuyrukları (`queues`) | "{queued} sırada · {running} çalışıyor" | "Son 24 sa {failed} başarısız" / "Takılı çalıştırma: #{id}" | /runs |
| E-posta (`mail`) | "{pending} bekliyor" | "En eski {min} dk" (warn > 30) · "{failed} başarısız" | Ayarlar › Kanallar |
| Teslimatlar (`deliveries`) | "{failed} başarısız" | per queue: Bildirim / Webhook / Takvim | Ayarlar › Entegrasyonlar |
| Disk (`disk`) | "%{pct} dolu · {free} boş" | meter (same-ramp, warning ≥ 80 %, danger ≥ 90 %) | — |
| Hatalar (`errors`) | "{open} açık hata grubu" | "Son 24 sa {seen} olay" | Hatalar tab |
| İzleme (`services`) | "Grafana ✓ · Prometheus ✓ · Loki ✕" (icon + name per service; the accessible name says "çalışıyor" / "çalışmıyor") | "Loki çalışmıyor: günlükler gösterilemez" | Panolar |
| Pod CI (`podci`) | "Son çalıştırma: Geçti · main · a1b2c3d" | started time | external CI page |

   Card status words map: `ok` → "Çalışıyor" (feasible green dot), `warn` → "Dikkat" (warning), `down` →
   "Çalışmıyor" (infeasible), `unknown` → "Bilinmiyor" (neutral gray, dashed dot). Order: down first, then warn, then the
   fixed order above (so problems rise to the top, but healthy cards never shuffle among themselves).
4. **İstekler** (`GET /ops/requests`): three small multiples side by side, same time window (son 1 sa, son 6 sa, son 24 sa
   `SegmentedControl`), each a single-series line (2 px, `--primary`), one axis each, own unit: "İstek/dk", "5xx/dk"
   (line in `--infeasible-fg`, the status colour justified because 5xx is the failure signal; with an icon in the title),
   "p95 gecikme (ms)". Crosshair tooltip shared across the three (hover one, all three show the same minute). Source
   note: "Kaynak: Prometheus" or "Kaynak: bu süreç (Prometheus kapalı)". "Tablo" view toggles one `DataTable` with the
   three columns per minute.

### 4.2 Hatalar

- **Filter row**: status `SegmentedControl` "Açık (Yeni + İnceleniyor) · Çözüldü · Yok sayıldı · Tümü" (default Açık),
  source `NativeSelect` (Sunucu, Arka plan işi, Tarayıcı), period (24 sa · 7 g · 30 g), search (kind, message, route).
- **Table** (`DataTable`, sorted by last seen desc; column system §A.10):

| Column | Content |
|---|---|
| Durum | chip with icon + word: Yeni (`circle-dot`), İnceleniyor (`eye`), Çözüldü (`check-circle-2`), Yok sayıldı (`bell-off`); "Yeniden açıldı ×2" footnote when `reopened` > 0 |
| Hata | `kind` (`type-headline`, e.g. `IntegrityError`) + first line of `message` (truncate, full in title) |
| Kaynak | Sunucu / Arka plan işi / Tarayıcı |
| Rota | `POST /api/v1/bookings` (method + route template, mono numerals only) |
| Olay | `count` (tabular) |
| İlk görülme / Son görülme | relative ("3 dk önce") with absolute in `<time title>` |
| Sürüm | `release` |

  Bulk: row checkboxes → floating action bar (existing multi-select tray pattern, motion §3.7) "İncelemeye al ·
  Çözüldü · Yok say".
- **Detail sheet** (`Sheet` right, bottom on phone; `GET /ops/errors/{id}`):
  - header: kind, status chip, "{count} olay · ilk {first} · son {last} · sürüm {release}"
  - message (full), route + method + status code, user role (never the user's identity; the payload is PII-scrubbed)
  - **Yığın izi**: `<pre>` in the mono stack, scrollable inside the sheet, "Kopyala" button, line wrap toggle
  - "Günlüklerde aç" (switches to Günlükler with service = backend, query = `last_request_id`, window ± 5 min),
    "Grafana'da aç ↗" (Hatalar ve günlükler dashboard)
  - status actions: "İncelemeye al", "Çözüldü olarak işaretle", "Yok say", "Yeniden aç"; each writes the status and an
    audit event; a resolved group that fires again returns as Yeni with "Yeniden açıldı".
  - toast on change with "Geri al" (sets the previous status).

### 4.3 Günlükler

- **Filter row**: Servis `NativeSelect` (Sunucu `backend`, Arayüz `frontend`, Vekil `proxy`/`caddy`, Veritabanı `db`,
  Grafana, Prometheus, Loki, Alloy), Süre `SegmentedControl` "15 dk · 1 sa · 24 sa · 7 g", Seviye chips "Bilgi · Uyarı ·
  Hata" (multi-select), Metin `Input` (debounced 400 ms, max 200 chars), **Canlı** `Switch`, Satır kaydır `Switch`,
  "Kopyala" (visible lines).
- **Lines**: virtualised list, mono 12/16 (`type-footnote` + `font-mono`), each line: time (`HH:mm:ss.SSS`, tabular),
  level word in a fixed-width column with icon (Bilgi plain, Uyarı warning, Hata infeasible), message. A request id in a
  line is a button that filters by it. Secrets are already scrubbed server-side (`_LOG_SCRUB`); the UI says so in the
  footer: "Parolalar, belirteçler ve çerezler gizlenir. Saklama: {days} gün."
- **Live mode**: polls every 5 s (`GET /ops/logs?minutes=…`), appends at the bottom. If the reader has scrolled up, new
  lines do **not** move the view; a pill "{n} yeni satır ↓" appears at the bottom (motion pattern 1, the jump-to-latest
  pill) and jumps on click. Live pauses automatically when the tab is hidden and says "Duraklatıldı".
- Limit: 500 lines; above it, "Daha eski satırlar için süreyi daraltın ya da Grafana › Keşfet'te açın ↗".

### 4.4 Panolar

Six cards from `GET /ops/dashboards` (Servis sağlığı, API, Çözücü ve işler, Rezervasyonlar ve onaylar, Yapay zekâ
kullanımı, Hatalar ve günlükler). Each: title, one-line purpose, "Grafana'da aç ↗" (opens `/grafana/d/{uid}/{slug}` in a
new tab; the edge's forward-auth lets admins in without a second login), and on desktop up to two embedded key panels
(`iframe` of the `embed` URL, `loading="lazy"`, `title` = panel title, 16:9, 6 h window, `sandbox="allow-scripts
allow-same-origin"`, `referrerpolicy="same-origin"`). When Grafana is down (`grafana.ok` false): the card shows
"Grafana şu an ulaşılamıyor" + the Durum link, no broken iframes. The Yapay zekâ kullanımı card also links to
`/admin/ai` ("Kullanıcı bazında kullanım: Yapay zekâ yönetimi").

## 5. Phone layout (390, `wireframes/ops-390.svg`)

- Headline + release line at the top; the auto-refresh switch moves into a "⋯" menu.
- Firing alerts as full-width `Alert`s.
- Service cards become one **list** (each row ≥ 56 px: dot + name + key line, chevron to a detail sheet with the
  second line and link).
- Request charts: one chart at a time with a `SegmentedControl` "İstek · 5xx · p95" (`fill`).
- Hatalar: card list (status chip, kind, message 2 lines, "{count} olay · {last}"); filters behind "Filtreler · n"
  (M-04); detail opens as a bottom sheet with actions in its footer (M-05).
- Günlükler: filters in a sheet; lines wrap by default; the Canlı switch stays visible in a sticky bottom bar together
  with "{n} yeni satır ↓".
- Panolar: links only (no iframes on phones: heavy, and Grafana panels are not touch-sized).

## 6. States

| Surface | Loading | Empty | Error / degraded |
|---|---|---|---|
| Durum | static placeholders per card (`LoadingValue`) | — | `GET /ops/status` fails: danger `Alert` "Durum alınamadı. API'ye ulaşılamıyor olabilir." + "Tekrar dene"; keep the last good data greyed with "Son başarılı: 19:40" |
| Card | — | — | `unknown`: "Bilinmiyor" + why ("Prometheus kapalı") |
| Requests | skeleton frame | "Bu aralıkta istek yok." | "Prometheus kapalı; yalnızca bu sürecin verisi gösteriliyor." (info) |
| Hatalar | placeholder rows | Açık filter: "Açık hata yok." (plain); other filters: "Bu filtreyle hata yok." + "Filtreleri temizle" | danger alert |
| Detail | sheet skeleton | no stack: "Yığın izi yok (tarayıcı raporu)." | 404: "Hata kaydı bulunamadı." |
| Günlükler | "Yükleniyor…" line | "Bu aralıkta satır yok." | Loki down: warning "Loki çalışmıyor; günlükler gösterilemez." + link to Durum; 422 unknown service: "Bilinmeyen servis." |
| Panolar | card placeholders | — | Grafana down (above) |
| No permission | route-level `NoAccess` (existing) | | |

## 7. Copy (keys `ops.*`; TR first)

| Key | TR | EN |
|---|---|---|
| `ops.nav` | Operasyon | Operations |
| `ops.title` | Operasyon | Operations |
| `ops.tab.status` | Durum | Status |
| `ops.tab.errors` | Hatalar | Errors |
| `ops.tab.logs` | Günlükler | Logs |
| `ops.tab.dashboards` | Panolar | Dashboards |
| `ops.refreshed` | Son yenileme {time} | Last refreshed {time} |
| `ops.autoRefresh` | Otomatik yenile | Auto-refresh |
| `ops.openGrafana` | Grafana'yı aç | Open Grafana |
| `ops.headline.ok` | Tüm servisler çalışıyor | All services are running |
| `ops.headline.warn` | {n, plural, other {# servis dikkat istiyor}} | {n, plural, one {# service needs attention} other {# services need attention}} |
| `ops.headline.down` | {n, plural, other {# servis çalışmıyor}} | {n, plural, one {# service is down} other {# services are down}} |
| `ops.release` | Sürüm {version} · {sha} · {date} tarihinde yayına alındı · {env} | Version {version} · {sha} · deployed {date} · {env} |
| `ops.state.ok` | Çalışıyor | Running |
| `ops.state.warn` | Dikkat | Attention |
| `ops.state.down` | Çalışmıyor | Down |
| `ops.state.unknown` | Bilinmiyor | Unknown |
| `ops.card.api` | API | API |
| `ops.card.api.uptime` | Çalışma süresi {duration} | Uptime {duration} |
| `ops.card.api.workers` | {n} işçi süreç | {n} worker processes |
| `ops.card.db` | Veritabanı | Database |
| `ops.card.db.latency` | Gecikme {ms} ms | Latency {ms} ms |
| `ops.card.db.migrationsOk` | Şema güncel | Schema up to date |
| `ops.card.db.migrationsOld` | Şema eski: {current} → {head} | Schema behind: {current} → {head} |
| `ops.card.queues` | İş kuyrukları | Job queues |
| `ops.card.queues.line` | {queued} sırada · {running} çalışıyor | {queued} queued · {running} running |
| `ops.card.queues.failed` | Son 24 sa {n} başarısız | {n} failed in 24 h |
| `ops.card.queues.stalled` | Takılı çalıştırma: #{id} | Stalled run: #{id} |
| `ops.card.mail` | E-posta | Email |
| `ops.card.mail.pending` | {n} bekliyor | {n} pending |
| `ops.card.mail.oldest` | En eski {min} dk | Oldest {min} min |
| `ops.card.mail.failed` | {n} başarısız | {n} failed |
| `ops.card.deliveries` | Teslimatlar | Deliveries |
| `ops.card.deliveries.channel` | Bildirim | Notifications |
| `ops.card.deliveries.webhook` | Webhook | Webhooks |
| `ops.card.deliveries.calendar` | Takvim | Calendar |
| `ops.card.disk` | Disk | Disk |
| `ops.card.disk.line` | %{pct} dolu · {free} boş | {pct}% used · {free} free |
| `ops.card.errors` | Hatalar | Errors |
| `ops.card.errors.open` | {n} açık hata grubu | {n} open error groups |
| `ops.card.errors.seen` | Son 24 sa {n} olay | {n} events in 24 h |
| `ops.card.monitoring` | İzleme | Monitoring |
| `ops.card.monitoring.lokiDown` | Loki çalışmıyor: günlükler gösterilemez | Loki is down: logs are unavailable |
| `ops.card.podci` | Pod CI | Pod CI |
| `ops.card.podci.line` | Son çalıştırma: {state} · {branch} · {sha} | Last run: {state} · {branch} · {sha} |
| `ops.alerts.more` | +{n} uyarı | +{n} alerts |
| `ops.alerts.since` | {time} itibarıyla | since {time} |
| `ops.requests.title` | İstekler | Requests |
| `ops.requests.rate` | İstek/dk | Requests/min |
| `ops.requests.errors` | 5xx/dk | 5xx/min |
| `ops.requests.p95` | p95 gecikme (ms) | p95 latency (ms) |
| `ops.requests.sourceProm` | Kaynak: Prometheus | Source: Prometheus |
| `ops.requests.sourceLocal` | Kaynak: bu süreç (Prometheus kapalı) | Source: this process (Prometheus is off) |
| `ops.window.1h` | Son 1 sa | Last 1 h |
| `ops.window.6h` | Son 6 sa | Last 6 h |
| `ops.window.24h` | Son 24 sa | Last 24 h |
| `ops.errors.filter.open` | Açık | Open |
| `ops.errors.status.open` | Yeni | New |
| `ops.errors.status.acknowledged` | İnceleniyor | Acknowledged |
| `ops.errors.status.resolved` | Çözüldü | Resolved |
| `ops.errors.status.ignored` | Yok sayıldı | Ignored |
| `ops.errors.reopened` | Yeniden açıldı ×{n} | Reopened ×{n} |
| `ops.errors.source.server` | Sunucu | Server |
| `ops.errors.source.job` | Arka plan işi | Background job |
| `ops.errors.source.browser` | Tarayıcı | Browser |
| `ops.errors.col.error` | Hata | Error |
| `ops.errors.col.source` | Kaynak | Source |
| `ops.errors.col.route` | Rota | Route |
| `ops.errors.col.count` | Olay | Events |
| `ops.errors.col.first` | İlk görülme | First seen |
| `ops.errors.col.last` | Son görülme | Last seen |
| `ops.errors.col.release` | Sürüm | Release |
| `ops.errors.summary` | {count} olay · ilk {first} · son {last} · sürüm {release} | {count} events · first {first} · last {last} · release {release} |
| `ops.errors.stack` | Yığın izi | Stack trace |
| `ops.errors.noStack` | Yığın izi yok (tarayıcı raporu). | No stack trace (browser report). |
| `ops.errors.copy` | Kopyala | Copy |
| `ops.errors.openLogs` | Günlüklerde aç | Open in logs |
| `ops.errors.openGrafana` | Grafana'da aç | Open in Grafana |
| `ops.errors.ack` | İncelemeye al | Acknowledge |
| `ops.errors.resolve` | Çözüldü olarak işaretle | Mark resolved |
| `ops.errors.ignore` | Yok say | Ignore |
| `ops.errors.reopen` | Yeniden aç | Reopen |
| `ops.errors.changed` | Durum: {status} | Status: {status} |
| `ops.errors.emptyOpen` | Açık hata yok. | No open errors. |
| `ops.errors.emptyFiltered` | Bu filtreyle hata yok. | No errors match these filters. |
| `ops.errors.clearFilters` | Filtreleri temizle | Clear filters |
| `ops.errors.notFound` | Hata kaydı bulunamadı. | Error group not found. |
| `ops.logs.service` | Servis | Service |
| `ops.logs.service.backend` | Sunucu | Backend |
| `ops.logs.service.frontend` | Arayüz | Frontend |
| `ops.logs.service.proxy` | Vekil sunucu | Proxy |
| `ops.logs.service.db` | Veritabanı | Database |
| `ops.logs.window` | Süre | Window |
| `ops.logs.level` | Seviye | Level |
| `ops.logs.level.info` | Bilgi | Info |
| `ops.logs.level.warn` | Uyarı | Warning |
| `ops.logs.level.error` | Hata | Error |
| `ops.logs.search` | Metinde ara | Search text |
| `ops.logs.live` | Canlı | Live |
| `ops.logs.paused` | Duraklatıldı | Paused |
| `ops.logs.wrap` | Satır kaydır | Wrap lines |
| `ops.logs.newLines` | {n} yeni satır ↓ | {n} new lines ↓ |
| `ops.logs.scrubbed` | Parolalar, belirteçler ve çerezler gizlenir. Saklama: {days} gün. | Passwords, tokens and cookies are hidden. Retention: {days} days. |
| `ops.logs.limit` | Daha eski satırlar için süreyi daraltın ya da Grafana › Keşfet'te açın | For older lines narrow the window or open Grafana › Explore |
| `ops.logs.empty` | Bu aralıkta satır yok. | No lines in this window. |
| `ops.logs.lokiDown` | Loki çalışmıyor; günlükler gösterilemez. | Loki is down; logs cannot be shown. |
| `ops.dash.open` | Grafana'da aç | Open in Grafana |
| `ops.dash.down` | Grafana şu an ulaşılamıyor. | Grafana is unreachable right now. |
| `ops.dash.aiLink` | Kullanıcı bazında kullanım: Yapay zekâ yönetimi | Per-user usage: AI administration |
| `ops.error.status` | Durum alınamadı. API'ye ulaşılamıyor olabilir. | Could not load status. The API may be unreachable. |
| `ops.error.lastGood` | Son başarılı: {time} | Last successful: {time} |
| `ops.retry` | Tekrar dene | Try again |

## 8. Motion

| Moment | Animation | Token | Reduced motion | Reduced transparency |
|---|---|---|---|---|
| Auto-refresh replaces data | **none** (values swap; no ticker on a monitoring screen, it would read as change everywhere) | — | — | — |
| A card changes state (ok → warn) | the card's dot swaps; the card moves to its sorted place with a `layout` reflow (one-time, data-driven, only when the order changes) | `smooth` | instant | — |
| Tab switch | primitive tab indicator | `--spring-glass-morph` | jumps | solid |
| Error detail sheet | pattern 4 | `sheet`, exit 120 ms | end state | solid |
| Status change → row | row chip swaps; rows leaving the current filter pop out (≤ 40 rows, pattern 6) | `smooth`, exit `tween.fadeOut` | instant | — |
| Live log lines | **no per-line animation**; "yeni satır" pill materialises (pattern 1) | `glassMorph` | fade 100 ms | solid pill |
| Bulk action bar | multi-select tray (motion §3.7) | `smooth` | fade | solid |
| Chart crosshair | follows pointer 1:1, no easing | — | — | — |

## 9. Accessibility and keyboard

- The headline is a `role="status"` live region (polite) that announces only **changes** of the overall state ("1 servis
  dikkat istiyor"), never every 30 s refresh.
- Status is never colour-only: dot + word everywhere; `unknown` uses a dashed outline dot.
- Cards are `article`s with an `h3`; the link inside is the only tab stop per card.
- Charts: summary sentence ("Son 1 saatte dakikada ortalama 42 istek, 5xx yok, p95 180 ms"), table view, keyboard
  crosshair (Tab to the chart, ←/→ minute).
- Log list: `role="log"` with `aria-live="off"` while Live (announcing every line is noise); a polite message reports "12
  yeni satır" when the pill appears. Lines are selectable text; request-id buttons have names ("İstek {id} ile filtrele").
- Stack trace `<pre tabindex="0">` so keyboard users can scroll it; "Kopyala" announces "Kopyalandı".
- iframes carry `title`; Panolar links say they open in a new tab ("Grafana'da aç, yeni sekmede").
- Touch: all controls 44 px; text ≥ 12 px in logs on phones (mono 12/16 is the floor, M-03), inputs 16 px.

## 10. Components

| Component | File | Use | Source / licence |
|---|---|---|---|
| `Tabs` | `ui/tabs.tsx` | the four tabs | shadcn/ui MIT |
| `Card` (plain) | `ui/card.tsx` | service and dashboard cards | shadcn/ui MIT |
| `StatusDot` | `ui/data-table` | state dots + words | in-house |
| `Alert` | `ui/alert.tsx` | firing alerts, degraded notes | in-house |
| `DataTable` | `ui/data-table/` | error groups, chart table views | in-house (TanStack MIT) |
| EvilCharts area/line | `ui/evilcharts/charts/recharts-area-chart.tsx` | small multiples | MIT © 2026 Gurbinder |
| `SegmentedControl`, `NativeSelect`, `Input`, `Switch`, `Chip` | `ui/*` | filters | in-house / MIT |
| `Sheet` | `ui/sheet.tsx` | error detail, phone filters | shadcn/ui MIT |
| multi-select tray | bookings bulk bar pattern | bulk status | in-house |
| `Progress`-style meter | `ui/progress.tsx` | disk | shadcn/ui MIT |
| `EmptyState`, `LoadingValue` | `ui/empty-state.tsx`, `ui/skeleton.tsx` | states | in-house / MIT |
| **new** `LogView` | `components/admin/ops/log-view.tsx` (W3-OPS) | virtualised mono lines + jump-to-latest pill + level column | in-house; reason: no existing log component |

## 11. Acceptance checks

| # | Check | Pass |
|---|---|---|
| OP-01 | `/admin/ops` as setup.settings at 1440 | headline sentence, release line, service cards for api, db, queues, mail, deliveries, disk, errors, monitoring, pod CI; each with dot + word + key line |
| OP-02 | Stop Loki (or point the config at a dead host) | İzleme card says "Dikkat" with "Loki çalışmıyor…", headline "1 servis dikkat istiyor"; Günlükler shows the Loki-down warning, no spinner forever |
| OP-03 | Cause a 500 (test route or a failing request) | within one refresh, Hatalar shows a Yeni group with count, route, release; the Hatalar card count increments |
| OP-04 | Open the group | stack shown, no e-mail / token / cookie strings in it; "Günlüklerde aç" switches to Günlükler filtered by the request id with the matching line visible |
| OP-05 | Mark resolved, cause the same error again | the group returns as Yeni with "Yeniden açıldı ×1"; the status changes wrote audit events |
| OP-06 | Live logs | enable Canlı, scroll up: the view does not move when lines arrive; the "{n} yeni satır ↓" pill appears and jumps to the end on click; switching browser tabs shows "Duraklatıldı" |
| OP-07 | Panolar at 1440 | six cards; "Grafana'da aç" opens `/grafana/d/...` in a new tab without a second login for an admin, and with 403 for a teacher (forward-auth) |
| OP-08 | Grafana down | dashboard cards show "Grafana şu an ulaşılamıyor." and no broken iframes |
| OP-09 | Requests charts | three separate charts, one y-axis each, shared crosshair; "Tablo" shows per-minute rows |
| OP-10 | 390 touch | M-01/M-02/M-04/M-05 pass on all four tabs; service cards are a list; no iframes; error detail actions in the sheet footer |
| OP-11 | Screen reader | headline announced only when the overall state changes; log list does not announce every line |
| OP-12 | Teacher (no ops permission) | nav entry hidden; `/admin/ops` shows the no-access state; `GET /ops/status` 403 |
| OP-13 | Reduced motion | card reorder without animation; pill appears with ≤ 100 ms fade |
| OP-14 | English | every `ops.*` string translated; status words never raw (`acknowledged` never visible) |
