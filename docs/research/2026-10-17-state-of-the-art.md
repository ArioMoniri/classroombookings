# State of the art, October 2026: timetabling, booking, AI governance, observability, KVKK

Ledger `wave3-res-2026-10-17` (lane W3-RES, researcher). Written 2026-10-17 for wave 3 (docs/ROADMAP.md, owner
requests of 2026-10-17 ~19:00 UTC). Every external claim has a numbered source in [Sources](#sources), with its
publication date or "accessed 2026-10-17" when the page has no date. Vendor marketing and third-party summaries are
marked as such. Where a statement is my inference, it says so.

## BLUF

1. **SmartSched's planning core is already at or above the products we checked.** It has a CP-SAT optimiser, it
   explains every class it cannot place, it has a planner-level validator, minimal-change re-solves, invigilation and
   AI-assisted rule entry that a person must approve. UniTime, Syllabus Plus, Celcat, Infosilem and Coursedog sell the
   optimiser. None of the sources we found shows a peer that explains unplaced classes or validates a run this way.
   The remaining planning gaps are **student-level conflicts** (UniTime and Infosilem plan from student registrations
   [3][9]; SmartSched plans per cohort), **exam seating plans** [9] and an **OBS/UBYS hand-off** (no public API was
   found [32]).
2. **The booking side lacks the 2025–2026 workplace patterns.** Missing: check-in with auto-release of no-shows
   (Robin, Microsoft Places, Skedda [11][12][13][14]), check-in and utilisation analytics (Skedda, May 2026 [13]),
   natural-language booking (Robin User Agent, April 2026 [15]; Copilot in Places [16]) and managed rebooking after a
   timetable change [12]. **One-tap quick reserve** is cheap and directly answers the owner's request.
3. **AI governance (W3-AI): one guarded gateway inside the backend, not a third-party proxy.** Real admin-chosen
   providers are Anthropic direct, Bedrock and Vertex (the official SDK has clients for all three), plus an optional
   OpenAI-compatible gateway URL. Do not import LiteLLM into the backend process: its PyPI releases 1.82.7/1.82.8 were
   malicious in March 2026 [20]. Budgets follow the LiteLLM model: a soft budget that alerts and a hard budget that
   blocks [19]. Map the guardrails to the OWASP LLM Top 10 2025 [21]: spotlighting for untrusted text [23],
   allow-listed strict tools and structured output, the action-selector / plan-then-execute patterns [22], CaMeL-style
   separation of data from control flow [24], and per-purpose token caps against LLM10.
4. **Observability (W3-OPS) on an 8 GB arm64 node: budget ≤ 768 MiB for the whole profile.** The current compose
   caps already add up to 7.25 GB (db 2 g, backend 4 g, frontend 1 g, proxy 256 m). Use Prometheus 3 or VictoriaMetrics
   single-node, Grafana OSS and Loki single-binary or VictoriaLogs, with **Grafana Alloy (not Promtail, which reached end
   of life on 2026-03-02 [26])**. Error tracking should be **built in** (an `error_events` table). Self-hosted Sentry
   needs 4 cores and 16 GB RAM plus 16 GB swap [29], more than the whole node, so it is ruled out. GlitchTip (256–512 MB,
   arm64, Postgres only [28]) is the optional Sentry-SDK-compatible extra.
5. **Turkish compliance.** (a) Since the Law 7499 amendments and the 10 July 2024 by-law, sending personal data to a
   foreign AI provider needs an Art. 9 mechanism, usually a Board standard contract that must be notified to the KVKK
   within 5 business days [33]. Consent alone stopped being a valid basis after 1 September 2024 [33]. The Anthropic
   API offers only `inference_geo` `us` or `global`; EU processing means Bedrock or Vertex EU regions. Either way it is
   a cross-border transfer from Turkey. (b) The KVKK's generative-AI guide of 24 November 2025 asks for a DPIA,
   prompt-injection risk assessment, AI transparency in the interface and data minimisation in prompts [34]. (c)
   **Presidential Circular 2025/10** (Official Gazette, 21 June 2025) makes WCAG 2.2 apply to universities, with a
   1-year deadline that has passed [36][37].

**Top 10 enhancements** (score = value × fit × 4 ÷ effort; full table in §6):
W3E-01 AI transparency notice and "my AI usage" on Profil (18.0) · W3E-02 one-tap quick reserve "Şimdi boş" (15.0) ·
W3E-03 WCAG 2.2 / Circular 2025/10 pass with an accessibility statement (15.0) · W3E-04 KVKK cross-border transfer
register that gates AI calls (15.0) · W3E-05 AI dependency supply-chain hardening (14.4) · W3E-06 built-in error
tracking (12.0) · W3E-07 native "Operasyon" admin page (12.0) · W3E-08 admin provider registry with per-purpose model
routing (10.0) · W3E-09 per-user and per-role token/cost budgets with soft and hard limits (10.0) · W3E-10 scope guard,
spotlighting and a TR/EN injection red-team suite in CI (10.0).

---

## 1. University timetabling and room booking: products, research and the feature matrix

### 1.1 What the products offer in 2025–2026

| Product | What the sources show | Source |
|---|---|---|
| **UniTime** (Apereo, open source) | 4.9, released 2025-09-30: Jakarta EE / Tomcat 10.1, more than 20 course and exam data-entry pages rewritten, new help site. 4.8 (2024) added time and distance conflicts to student scheduling and extended room partitions to events. The product covers course timetabling, exams, student scheduling and events. | [1][2] |
| **ITC 2019** (built from UniTime data) | Real university instances that combine **student sectioning** with time and room assignment, 30 instances, solvers compared (J. Scheduling, online 2024-04-12). | [3] |
| **Coursedog** | Section optimiser (tests configurations, best-fit rooms), "relationships" against conflicts, meeting patterns, faculty preference forms, a requests manager with approvals, utilisation reports, real-time SIS sync, course demand projection. "Coursedog Intelligence" is not described in detail (vendor page). | [4][5] |
| **Scientia Syllabus Plus / Enterprise Timetabler** | Universities use Web Room Booking, being replaced by **Resource Booker**: real-time booking of rooms, desks and IT equipment, self-service for staff and students (university pages; TechnologyOne page). | [6][7] |
| **Celcat** | Timetabling plus ad-hoc room booking, **attendance tracking**, claim management, a self-service portal (third-party listings only; no vendor release notes found). | [8] |
| **Infosilem Exam** (Berger-Levrault) | Exam schedules built from **student registrations**, best-fit rooms, "striping" (several exams in one room), **seating plans with student-seat assignment**, travel time, build before drop/add and refine afterwards (vendor page). | [9] |
| **EMS (Accruent)** | Classroom and exam scheduling, scenarios, utilisation trends, Ellucian SIS integration, "Direct Spaces" AI mobile booking (vendor pages, 2022 brochure). | [10] |
| **Robin** | Abandoned-meeting protection: a room is released when nobody checks in (window 10 min–12 h, default 10 min after start). Recurring series are removed after 3 missed check-ins. **Robin User Agent** (2026-04-23, early access): natural-language booking that fills in missing reservations from usage patterns. | [11][15] |
| **Microsoft Places** | Room auto-release and check-in (Teams panel, Teams chat); desk check-in and auto-release; part-day desk bookings; **Copilot managed booking** (GA Nov 2024) rebooks declined room requests, including recurring ones. | [12][16] |
| **Skedda** | Booking windows, buffers, per-team rules, maximum duration; check-in by QR, e-mail or Wi-Fi with auto-release; room and desk analytics; **check-in analytics on the Insights dashboard (2026-05-24)**. | [13] |
| **Google Calendar** | Room suggestions from each guest's building and floor, booking history, AV equipment and capacity; falls back to frequently used rooms. | [17] |

### 1.2 Research worth tracking

- **CP-SAT decomposition plus repair at scale.** Moreira and de Freitas (SEMISH 2026, 2026-07-19) split the problem
  room by room into CP-SAT sub-problems, add instructor blocks incrementally and use selective rollback with a
  validator. They report 100 % coverage on 11 real instances of up to 6,278 lectures, and the largest solved in
  4.45 s [18]. That is close to SmartSched's own design (repair, validator). It is a reference if term-wide models grow.
- **LLMs as modellers, not solvers.** CP-Agent (arXiv 2508.07468, v3 2026-02-03) solves all 101 CP-Bench problems in an
  agentic write–run–refine loop [38]. Voboril and Szeider (arXiv 2608.08127, 2026-08/09) let an agent reformulate CP
  models and check each variant against a known solution. The new models beat the originals on 21 of 27 instances,
  sometimes by more than 100× [39]. **SCHEDBench** (arXiv 2608.00991, EMNLP 2026 Findings) found that 13 LLMs are *not*
  invariant to rewordings of the same scheduling problem, and that reordering constraints changes their behaviour the
  most [40]. Consequence for SmartSched: the existing rule "Claude is translator and narrator, never the planner"
  (app/ai/README.md) is the right call. Add paraphrase and reorder invariance tests for rule extraction (W3E-14).
- **PATAT 2026** took place 25–28 August 2026 in Nottingham [41]. Its proceedings are the next place to look for
  ITC 2019 results.

### 1.3 Feature matrix (Have / Partial / Missing)

SmartSched status comes from docs/features.yml, docs/STATUS.md and the code (grep, 2026-10-17). A peer column lists
only products whose source above shows the feature. A dash means "not shown in the sources", not "absent".

| Capability | SmartSched | Peers that show it |
|---|---|---|
| Optimiser for course timetables | **Have** (CP-SAT, week / month / term / exam period) | UniTime, Coursedog, Syllabus Plus, Infosilem, Celcat [1][4][8] |
| Explanation of every unplaced class; run validator | **Have** (run_truth, validate_planner) | – |
| Minimal-change re-solve with a diff | **Have / partial** (R1-S-04 losses not reproduced) | – |
| Student-level conflicts (sectioning, electives) | **Missing** (cohort keys only, solver/README.md) | UniTime / ITC 2019 [3], Infosilem Exam [9] |
| Exam timetabling | **Have** (cohort-based) | UniTime, Infosilem, EMS [1][9][10] |
| Exam seating plans / student seats | **Missing** | Infosilem Exam [9] |
| Invigilator assignment | **Have** | – |
| Faculty preference forms → coordinator decision | **Have** (Tercih ekle, accept/reject with reason) | Coursedog [4] |
| Course demand projection | **Missing** | Coursedog [4][5] |
| SIS sync | **Partial** (Excel/CSV/CRBS import, ICS out; no OBS/UBYS adapter) | Coursedog, EMS–Ellucian [4][10] |
| Self-service room booking with rules | **Have** (CRBS superset, limits, policies) | Resource Booker, Skedda, Celcat [6][13][8] |
| Approval workflows | **Have** (approval-first, approvers per room / group / type) | Coursedog, EMS [4][10] |
| Check-in, auto-release, no-show handling | **Missing** | Robin, Places, Skedda [11][12][13] |
| Utilisation analytics | **Partial** (heatmap, dashboard) | Skedda, Coursedog, EMS [13][4][10] |
| Check-in / booked-vs-used analytics | **Missing** | Skedda (2026-05) [13] |
| Natural-language / AI booking | **Missing** (AI only for rules and intake) | Robin User Agent [15], Copilot / Places [16], EMS Direct Spaces [10] |
| AI rules from sentences, human-approved | **Have** | – (Coursedog Intelligence unspecified [4]) |
| Managed rebooking after a change | **Partial** (admin conflict resolver after publish) | Copilot managed booking [12] |
| Calendar sync (ICS, Google / M365 push) | **Have** | Places (native) [12] |
| Room displays / kiosk | **Partial** (/public kiosk, 60 s refresh) | Robin room displays, Teams panels [11][12] |
| Attendance tracking | **Missing** (out of scope so far) | Celcat [8] |
| Desk / equipment booking | **Missing** (rooms only) | Resource Booker, Skedda, Places [6][13][12] |
| Usual-room suggestions from history | **Partial** (find-room ranks by fit, not history) | Google Calendar [17] |
| WCAG 2.2 AA with an accessibility statement | **Partial** (44 px targets, focus rules; no statement, drag has alternatives only in places) | (legal duty, §5) |
| Admin AI governance (provider, budgets, guardrails) | **Partial** (policy switches, KVKK sign-off, UsageTracker per call; no per-user ledger or budgets) | LiteLLM / Portkey pattern [19][25] |
| Observability and error tracking | **Missing** (no /metrics, no error store) | – (platform duty, §3) |

### 1.4 Gaps ranked by value

**For the planning office (Fatih Bey):** (1) student-level conflicts for electives and exams, from OBS course
registrations (W3E-21); (2) an OBS/UBYS hand-off so the published plan does not have to be typed again (W3E-18);
(3) exam seating plans (W3E-22); (4) utilisation KPIs per term for the rectorate (W3E-13); (5) an Operasyon page and
alerts, so he knows whether the system is healthy before a publish (W3E-07, W3E-12); (6) budgets and a provider choice,
so AI use stays inside what the university pays and permits (W3E-08, W3E-09).

**For staff and academicians:** (1) one-tap quick reserve with the admin's slot display (W3E-02); (2) recurring
make-up series with per-date approval (FLE-001, W3E-17); (3) a Turkish natural-language booking box with a live preview
(W3E-16); (4) check-in and auto-release so rooms booked "just in case" come back (W3E-19); (5) rebooking suggestions
when a publish displaces a booking (W3E-20); (6) non-drag and keyboard paths everywhere (W3E-03).

---

## 2. AI governance in admin consoles (2026) → requirements for W3-AI

### 2.1 Findings

- **Gateways.** LiteLLM proxy keeps budgets per virtual key, user and team. `max_budget` blocks, `soft_budget` alerts
  (for example at 80 %), budgets reset per duration, and RPM/TPM/parallel limits answer 429. User and team limits need
  Postgres, and Redis for the rate limits [19]. Portkey's gateway core is MIT-licensed. The sources put its budget
  limits in the paid tiers, and Palo Alto Networks has announced it will acquire Portkey [25] (third-party summaries).
  OpenRouter separates **region pinning** (the EU endpoint is enterprise-only) from **zero data retention**
  (`zdr: true`, `data_collection: deny`). Both have to be set [27].
- **Supply chain (OWASP LLM03).** LiteLLM 1.82.7 and 1.82.8 on PyPI were malicious around 2026-03-24. 1.82.8 shipped a
  `.pth` file that runs at every Python start-up, and PyPI advised rotating every credential in the affected
  environment [20].
- **OWASP Top 10 for LLM Applications 2025** (published 2024-11-18): LLM01 Prompt Injection, LLM02 Sensitive
  Information Disclosure, LLM03 Supply Chain, LLM04 Data and Model Poisoning, LLM05 Improper Output Handling, LLM06
  Excessive Agency, LLM07 System Prompt Leakage, LLM08 Vector and Embedding Weaknesses, LLM09 Misinformation, LLM10
  Unbounded Consumption [21].
- **Injection defences.** Spotlighting (Microsoft) has three methods: delimiting, datamarking and encoding. Datamarking
  and encoding cut indirect-injection success from over 50 % to under 2 % at little cost to the task [23]. The six
  design patterns paper (Beurer-Kellner et al., 2025) covers action-selector, plan-then-execute, map-reduce, dual LLM,
  code-then-execute and context minimisation. A 2026 critique notes that the patterns stop injected text from
  *choosing* actions but not from shaping the *arguments* of allowed actions [22]. CaMeL (Google DeepMind / ETH,
  arXiv 2503.18813) takes control and data flow from the trusted query only and adds capability checks on tool calls:
  77 % of AgentDojo tasks with provable security, against 84 % undefended [24].
- **Provider facts (claude-api skill, cached 2026-10-06).** The official Anthropic SDK has first-party, Bedrock
  (Mantle), Vertex and Foundry clients with the same `messages` surface. `inference_geo` is a top-level Messages
  parameter with values `"us"` or `"global"` (no EU value), and `response.usage.inference_geo` reports where the call
  ran. Strict tools (`strict: true`) and `output_config.format` give schema-valid output. Usage and cost reports exist
  as Admin API endpoints over raw HTTP only. Third-party summaries say the same about EU residency: EU processing goes
  through Bedrock or Vertex EU regions [42].

### 2.2 Requirements for W3-AI (relay; IDs for traceability)

- **R-AI-01 Provider registry, chosen by admins only.** Providers: `anthropic` (direct), `bedrock` (region),
  `vertex` (region), `openai_compatible` (base URL, for a gateway the university runs itself). Every purpose
  (`rules`, `intake`, `vision`, `chat`, `explain`, future `booking_nl`) maps to one provider and model, plus a fallback.
  Keys are encrypted and write-only, as in `anthropic_api_key` today, and each provider has a test button. Users never
  choose. Every change is audited. Sync means one table that every call path reads; there are no per-module settings.
- **R-AI-02 No gateway library inside the backend process.** Use the official SDK clients behind a small adapter.
  A gateway (LiteLLM / Portkey / OpenRouter) is allowed only as an external URL or a separate container pinned by digest
  [20]. Dependencies stay hash-pinned (W3E-05).
- **R-AI-03 Residency and transfer record per provider.** Store the processing region, the retention / ZDR terms, the
  KVKK Art. 9 mechanism (standard contract date and notification date) and the notice version. `ai_allowed()` refuses
  calls that carry personal data when the record is missing (409 `ai_transfer_basis_missing`, TR/EN) [33][34]. Record
  `usage.inference_geo` on each call.
- **R-AI-04 Usage ledger (`ai_usage`).** One row per call: user, role, purpose, provider, model, input / output /
  cache tokens, estimated cost from a versioned price table, latency, outcome (`ok`, `refusal`, `blocked_scope`,
  `blocked_budget`, `error`), guardrail verdict and request id. No prompt text by default: store a hash and the length.
  An optional redacted sample is kept at most 30 days (KVKK minimisation [34]).
- **R-AI-05 Budgets.** Monthly token and cost budgets per user, per role and for the organisation. Soft threshold
  defaults to 80 % and alerts (bell, e-mail / Apprise, Operasyon page). The hard limit blocks with 429
  `ai_budget_exceeded` in TR/EN. Enforcement **reserves** the estimated cost (count_tokens or a heuristic) before the
  call and reconciles afterwards, so parallel calls cannot overrun. Admins can grant a one-off top-up, which is audited.
  Per-user RPM and at most 2 concurrent calls [19].
- **R-AI-06 Unbounded consumption (LLM10).** Each purpose has `max_tokens`, an effort level, a timeout, a file / page
  limit (the existing `MAX_VISION_PAGES`) and a maximum number of tool rounds. A runaway loop ends with a recorded
  outcome, not a silent retry.
- **R-AI-07 Scope guard (out-of-scope use).** Only the allow-listed strict tools for the purpose are sent, with
  structured output only and no free-form "general assistant" route. A deterministic pre-check (length, language,
  known injection markers) and an optional cheap classifier call label each request `in_scope`, `out_of_scope` or
  `injection_suspected`. The last two get a canned TR/EN answer and a ledger row, and they never reach the main model
  [21][22].
- **R-AI-08 Spotlighting for every untrusted input.** Workbook cells, uploaded files, booking notes and user chat
  history go into delimited document blocks with datamarking or encoding, on top of `sanitize.clean_for_model()`.
  Operator instructions travel only in system / mid-conversation system messages. Ids come only from the database
  (already the rule) [23][24].
- **R-AI-09 Output handling and agency (LLM05/06/09).** Model text is rendered as text, never as HTML or as links that
  were not in the input. Numbers in prose must appear in the grounded facts (as `explain_run` does now). Nothing is
  applied without a person's approval and the solver's validation. This keeps the action-selector / plan-then-execute
  pattern [22].
- **R-AI-10 Red-team and invariance suite in CI.** Extend `app/ai/redteam.py` with Turkish and English cases for
  LLM01, 02, 05, 06, 07 and 10: injection in a workbook cell, in a booking note and in a PDF, system-prompt extraction,
  a budget-burn loop, and out-of-scope requests ("bana şiir yaz", "write my thesis"). Add paraphrase and reorder
  invariance tests for rule extraction [40]. The tests run against a recorded or mocked provider, never against a live
  key.
- **R-AI-11 Transparency (KVKK guide).** Every AI surface says in TR/EN that AI is used, which provider and where it
  runs. Profil shows the user's own AI use (calls, tokens, budget left) [34].
- **R-AI-12 Metrics for W3-OPS** (aggregated, no user label): `ai_calls_total{purpose,provider,outcome}`,
  `ai_tokens_total{purpose,provider,direction}`, `ai_cost_usd_total{purpose,provider}`, `ai_budget_blocks_total`,
  `ai_guardrail_blocks_total{reason}`.

---

## 3. Observability on one small node → recommendation for an 8 GB arm64 pod

### 3.1 Findings

| Option | Footprint per the sources | Note |
|---|---|---|
| Grafana OSS | Floor 512 MB / 1 core for evaluation. SQLite is fine for small setups but not recommended for production (MySQL or Postgres) [30] | Real usage at a handful of dashboards is lower (my estimate: 150–250 MB). Set a cap. |
| Prometheus | About 3 kB per head series (Robust Perception, from 2.20); Alloy docs say ~11 GiB per million series [31] | At < 10 k series that is tens of MB plus overhead (my estimate: 150–300 MB). |
| VictoriaMetrics single | Claims up to 7× less RAM than Prometheus; reads `prometheus.yml` scrape configs; `-retentionPeriod` (default 31 d); arm64 builds documented [43] | Vendor claim. A drop-in for Prometheus scraping. |
| Loki vs VictoriaLogs | One team, 4 vCPU / 8 GiB, ~500 GB / 7 d: Loki 6–7 GB RAM, VictoriaLogs 0.8–0.9 GB [44] | Our log volume is MBs per day, not that test's ~500 GB per week, so both fit. VictoriaLogs has more headroom. |
| Promtail | **LTS from 2025-02-13, end of life 2026-03-02**; Alloy is the successor and has a config converter [26] | Do not deploy Promtail (the W3 brief's "Loki/Promtail" needs this correction). |
| Grafana Alloy | No published comparison with Promtail; benchmark on your own load [26] | Or Vector / Fluent Bit (not researched further). |
| SigNoz | 1.5–2 GB at idle (ClickHouse) [45] | Too heavy for this node. |
| OpenObserve | 512 MB minimum single-node, 1–2 GB recommended; local mode uses SQLite [45] | One binary; an alternative if Grafana is not required. |
| Sentry self-hosted | **4 cores, 16 GB RAM + 16 GB swap, 20 GB disk** minimum, 32 GB recommended [29] | Ruled out. |
| GlitchTip | 512 MB recommended, 256 MB all-in-one, x86 or arm64, Postgres ≥ 14, Valkey optional [28] | Optional profile. Sentry SDK compatibility is not confirmed on the install page. |
| Grafana embedding | `allow_embedding` removes `X-Frame-Options: deny`. Cross-site needs `cookie_samesite=none` + HTTPS. For a sub-path, use either `serve_from_sub_path` or a proxy rewrite, never both [46] | Interacts with W3-SEC's headers. |

### 3.2 Recommendation

Memory: the current caps (db 2 g + backend 4 g + frontend 1 g + proxy 256 m = 7.25 g) leave ~750 MB. The observability
profile therefore gets **≤ 768 MiB in total**, with a `mem_limit` on each container. **Profile off by default.**

- **Metrics:** Prometheus 3 (`--storage.tsdb.retention.time=15d`, `retention.size=1GB`, `mem_limit 256m`). Use
  VictoriaMetrics single (192m) if measured RSS goes over 200 MB. Targets: backend `/metrics` (internal network only),
  postgres-exporter (64m), node-exporter (32m). Skip cAdvisor (my estimate: 100–200 MB) unless measured.
- **Logs:** Loki 3 single-binary with filesystem storage, 7 d retention, 192m, with **Alloy** (96m) reading Docker JSON
  logs. Or VictoriaLogs (128m) with the same collector. Either way: JSON logs with `request_id`, and e-mails, tokens
  and `Authorization` values redacted before shipping.
- **Dashboards:** Grafana OSS (192m). Datasources and dashboards are provisioned as code, anonymous access is off, and
  Grafana sits behind nginx at `/ops/grafana/` with `auth_request` to a backend admin check (auth.proxy, `Viewer`
  role). The admin panel's **own "Operasyon" page** shows the key numbers from the backend (it queries the Prometheus
  HTTP API), with a "Grafana'da aç" link. That avoids most iframe and header conflicts.
- **Errors:** built in (`error_events`), as the W3-OPS ownership already plans. GlitchTip all-in-one (≤ 512m, its own
  database in the existing Postgres) is an opt-in second profile, never on by default.

### 3.3 Requirements for W3-OPS (relay)

- **R-OPS-01** The `observability` profile is ≤ 768 MiB in total, with `mem_limit` per service and arm64 images pinned
  by digest (pin-digests.sh). The pod gate records RSS after 10 minutes at idle and under a solver run.
- **R-OPS-02** No Promtail (end of life 2026-03-02 [26]). Use Grafana Alloy (or Vector).
- **R-OPS-03** Retention: metrics 15 d / 1 GB, logs 7 d, error events 90 d (KVKK: purpose and retention written into
  the inventory, and the user id stored as an internal id, never e-mail or name).
- **R-OPS-04** Cardinality budget < 10 k series. Label by route *template*, never raw path, user id or e-mail. Per-user
  AI usage lives in `ai_usage` (W3-AI), not in Prometheus.
- **R-OPS-05** Backend metrics: RED per route template; solver runs (duration, status, queue depth, active solves);
  publish / move guard refusals; booking actions; DB pool; the AI aggregates from R-AI-12; backup age; app info
  (`git_sha`).
- **R-OPS-06** Built-in error tracking: fingerprint = exception type + first app frame + route template; count; first
  and last seen; release (git sha); redacted stack sample; status new / acknowledged / resolved (audited); link from
  `request_id` to the logs. Frontend errors go to `POST /api/v1/ops/client-errors` (rate-limited, ≤ 8 KB, no PII).
- **R-OPS-07** Security: Prometheus, Loki and exporters only on the internal Docker network. Grafana only via nginx
  with the admin check and its admin password from a secret. `/metrics` is not routed through the public proxy. Iframe
  embedding is same-origin only (`frame-ancestors 'self'`), agreed with W3-SEC.
- **R-OPS-08** Alerts (Grafana alerting or vmalert) go to the existing channels (e-mail outbox / Apprise / bell): backend
  down, 5xx > 2 % for 5 min, p95 > 2 s, disk > 80 %, DB connections > 80 %, solver failures, new error fingerprint,
  AI budget at 80 / 100 % (from W3-AI), backup older than 26 h, TLS certificate < 14 d.
- **R-OPS-09** Health: `/healthz` (liveness) and `/readyz` (DB reachable, Alembic at head, workers alive) feed the
  Operasyon page and the compose healthchecks.
- **R-OPS-10** Dashboards are provisioned with Turkish titles first (Genel bakış, API, Çözücü, Veritabanı, Yapay zekâ,
  Hatalar) and English descriptions. The Operasyon page meets the phone rules (44 px, no hover-only, focus).

---

## 4. Booking UX patterns in 2026 (for W3-SLOT and W3-DES)

1. **One-tap "next free slot".** Show the room or slot that is free now or next, with a duration preset from the admin
   slot settings (`booking.slot_display.*`) and one confirm. Workplace tools centre on fast booking and part-day
   bookings (Places part-day desks [12]; Skedda rules and windows [13]). → W3E-02.
2. **Natural language with a live, structured preview.** Fantastical fills in the fields as you type, so the user
   knows the result before pressing Return [47]. Robin User Agent (2026) and Copilot do the same for desks and rooms
   [15][16]. For SmartSched: a deterministic Turkish parser for "yarın 14–16 50 kişilik projeksiyonlu" first, with AI
   only as an optional fallback through W3-AI's guarded `booking_nl` purpose. Every parse shows the preview card and
   the "Neden?" reasons before booking. → W3E-16.
3. **Suggestions ranked by context.** Use history, capacity and equipment, falling back to frequently used rooms
   (Google Calendar [17]). SmartSched find-room already ranks by fit. Add "usually yours" from booking history.
   → W3E-15.
4. **Recurring series as a list of dates.** Each date shows its own conflict and can be skipped or replaced. Recurring
   no-shows release the series after repeated misses (Robin: 3 [11]). Ties to FLE-001 and FLE-010. → W3E-17.
5. **Check-in and auto-release.** Check in by QR on the kiosk, e-mail or the app. The room is released after a grace
   period, the organiser is told, and check-in rates are reported (Robin [11], Places [12], Skedda [13]). → W3E-19.
6. **Non-drag, large-target, no re-typing.** WCAG 2.2 2.5.7 needs a single-pointer alternative for drag-to-book or
   resize [48]. 2.5.8 sets 24 px as the minimum (the project already uses 44 px), and 3.3.7 Redundant Entry asks for
   the last room and purpose to be pre-filled [49]. → W3E-03.
7. **Managed rebooking.** When a publish or a change displaces a booking, offer the user ranked alternatives with one
   accept button instead of a bare cancel notice (Copilot managed booking [12]). → W3E-20.
8. **Book where people already are.** Teams chat check-in and room panels (Places [12]) and calendar push (SmartSched
   has ICS and Google / M365 push). A Teams bot is a later, low-fit item (W3E-26).

---

## 5. KVKK / GDPR and Turkish higher-education specifics

- **Cross-border transfer (KVKK Art. 9).** Amended by Law 7499 (Official Gazette 12 March 2024, No. 32487). The by-law
  was published on 10 July 2024 (No. 32598). There are three tiers: adequacy (no decisions yet in the sources),
  appropriate safeguards (Board **standard contract**, BCR, undertaking) and occasional (*arızi*) transfers. Consent
  alone stopped being a valid basis after 1 September 2024. A standard contract must be notified to the Authority
  **within 5 business days** (online module since 2024-10-25). The sources give fines of TRY 90,308–1,806,377 for 2026
  [33] (law-firm summary; check the official text). One compliance site dates the amended Art. 9 to 1 June 2024 [50].
  → Every AI provider and every channel that receives personal data needs its mechanism recorded (W3E-04, R-AI-03).
- **KVKK generative-AI guide** (24 November 2025, 15 questions) [34][35]. The deployer is the controller. Each
  processing step needs its own legal basis. Avoid personal data in prompts, and remember that outputs can contain
  personal data. Users must know they are talking to an AI, and the notice belongs in the interface. Data subject
  rights cover prompts and outputs. Art. 11/1-g (objection to purely automated results) matters for automated room and
  invigilator allocation, which SmartSched already routes through a person. Run a **DPIA** that covers prompt
  injection and jailbreaks, red-team testing, MFA and secure logging. A February 2025 KVKK advisory tells users not to
  put identifying data into AI tools [35].
- **Data localisation for public bodies.** Presidential Circular 2019/12 and the Information and Communication Security
  Guide require public data to be kept on institutional or domestic, institution-controlled systems rather than
  foreign cloud. Sources disagree on how binding the guide is, and whether it covers universities is unconfirmed [51].
  → Default AI **off** (as now). Self-hosted deployment is the default, and the cloud AI provider is an explicit,
  recorded choice per institution. Foundation universities may differ.
- **Accessibility: Presidential Circular 2025/10** (Official Gazette No. 32933, 21 June 2025) covers **universities**
  under WCAG 2.2 plus the ministry's A-level checklist. The deadline was 1 year (about 20–21 June 2026, now passed).
  Each institution sets up an internal review commission, and passing earns the "Erişilebilirlik Logosu" for 2 years
  [36][37]. → W3E-03: an accessibility statement page, a WCAG 2.2 audit export for the commission, and non-drag paths.
- **YÖK.** YÖK's ethics guide on generative AI in research and publication (May 2024) stresses transparency,
  accountability, privacy and scientific integrity, and asks institutions to write local procedures. Broader AI rules
  for theses were announced but are not confirmed in force [52]. Its direct effect on a timetabling tool is small. It
  supports the transparency notice and the "a person stays responsible" design.
- **OBS / UBYS / YÖKSİS.** Universities keep student records in OBS (fed from YÖKSİS) and sign in through UBYS or
  e-Devlet. Some senates want course timetables entered into OBS so registration can check clashes. No public API was
  found [32]. → W3E-18: file-based import / export profiles first (CSV / JSON per vendor), with an API adapter later per
  university.
- **EU AI Act** (only for EU-facing programmes such as Erasmus). The Digital Omnibus (Regulation (EU) 2026/1744, in
  force 2026-07-27) moved the Annex III education high-risk duties (admission, evaluation, exam proctoring) to
  2 December 2027 [53] (secondary source). Timetabling and invigilator rostering are not in those categories as
  summarised. Keep AI off any student-evaluation path.

---

## 6. Ranked enhancements

Score = value (1–5) × fit (0.5–1.5) × 4 ÷ effort (1–5), one decimal. Fit is 1.5 when the item answers an owner request
of 2026-10-17 or a legal duty, 1.2 for a strong persona need, 1.0 for neutral, and 0.8 for scope creep. Lane = a wave-3
lane, or the area for a later builder.

| Id | Enhancement | Value | Effort | Fit | Score | Lane / area | Sources |
|---|---|---|---|---|---|---|---|
| W3E-01 | AI transparency notice on every AI surface (TR/EN: provider, region) + "Yapay zekâ kullanımım" on Profil (calls, tokens, budget left) | 3 | 1 | 1.5 | 18.0 | W3-AI | [34] |
| W3E-02 | One-tap quick reserve "Şimdi boş / sıradaki boş": nearest free slot with the admin slot-display preset, one confirm, 44 px, phone first | 5 | 2 | 1.5 | 15.0 | W3-SLOT | [12][13] |
| W3E-03 | WCAG 2.2 AA pass for Circular 2025/10: accessibility statement page, a single-pointer path for every drag (2.5.7), pre-filled repeat entries (3.3.7), audit export for the review commission | 5 | 2 | 1.5 | 15.0 | W3-DES → W3-SLOT / all UI | [36][37][48][49] |
| W3E-04 | KVKK transfer register per AI provider and channel (region, retention / ZDR, Art. 9 mechanism, contract and notification dates); AI calls with personal data refused without it | 5 | 2 | 1.5 | 15.0 | W3-AI (+ KVKK admin) | [33][34] |
| W3E-05 | Supply-chain hardening for AI dependencies: hash-pinned SDKs, no in-process gateway library, SBOM in pod CI, credential-rotation runbook | 3 | 1 | 1.2 | 14.4 | W3-SEC / W3-AI | [20][21] |
| W3E-06 | Built-in error tracking: `error_events` with fingerprints, release, request-id link, client-error endpoint, status workflow | 4 | 2 | 1.5 | 12.0 | W3-OPS | [28][29] |
| W3E-07 | Native "Operasyon" admin page (health, 5xx, p95, solver queue, backups, AI spend, open errors) + "Grafana'da aç" | 4 | 2 | 1.5 | 12.0 | W3-OPS | [30][46] |
| W3E-08 | Admin provider registry: Anthropic / Bedrock / Vertex / OpenAI-compatible URL, per-purpose model and fallback, test button, audited | 5 | 3 | 1.5 | 10.0 | W3-AI | [19][27][42] |
| W3E-09 | Per-user, per-role and org token / cost budgets: soft 80 % alert, hard block 429 TR/EN, reservation then reconcile, audited top-ups, RPM / concurrency | 5 | 3 | 1.5 | 10.0 | W3-AI | [19][21] |
| W3E-10 | Scope guard + spotlighting + TR/EN injection red-team suite in CI (OWASP LLM01/02/05/06/07/10) | 5 | 3 | 1.5 | 10.0 | W3-AI | [21][22][23][24] |
| W3E-11 | Observability profile ≤ 768 MiB: Prometheus (or VictoriaMetrics) + Grafana + Loki (or VictoriaLogs) + Alloy, internal-only, digest-pinned | 4 | 3 | 1.5 | 10.0 | W3-OPS | [26][30][31][43][44] |
| W3E-12 | Alert rules into the existing channels (backend down, 5xx, p95, disk, DB, solver failures, new error, AI budget, backup age, TLS) | 4 | 2 | 1.2 | 9.6 | W3-OPS | [26] |
| W3E-13 | Utilisation KPIs per term (booked vs used, seat fill %, peak hours, empty-room hours) as a rectorate report | 4 | 2 | 1.2 | 9.6 | analytics | [13][4] |
| W3E-14 | Rule-extraction robustness: paraphrase and constraint-reorder invariance tests for `propose_constraints` | 3 | 2 | 1.2 | 7.2 | W3-AI | [40] |
| W3E-15 | "Genellikle kullandığınız" room suggestions from booking history in find-room and quick reserve | 3 | 2 | 1.2 | 7.2 | bookings | [17] |
| W3E-16 | Turkish natural-language booking box with a deterministic parser and a live preview card; optional AI fallback through the guarded `booking_nl` purpose | 4 | 3 | 1.2 | 6.4 | W3-SLOT (+ W3-AI) | [15][16][47] |
| W3E-17 | Recurring series as a list of dates with per-date conflicts, skip / replace, per-date approval (FLE-001, FLE-010) | 4 | 3 | 1.2 | 6.4 | bookings | [11] |
| W3E-18 | OBS / UBYS hand-off: import course registrations and export the published plan through file profiles; API adapter per university later | 4 | 3 | 1.2 | 6.4 | integrations | [32] |
| W3E-19 | Check-in (kiosk QR, link, app) with auto-release after a grace period, organiser notice, series released after 3 misses, check-in analytics | 4 | 3 | 1.0 | 5.3 | bookings | [11][12][13] |
| W3E-20 | Managed rebooking: a displaced booking gets ranked alternatives with one-tap accept | 3 | 3 | 1.2 | 4.8 | bookings | [12] |
| W3E-21 | Student-level conflicts (sectioning-lite): electives and exams checked against registrations, clash counts in the run truth | 5 | 5 | 1.0 | 4.0 | solver / planning | [3][9] |
| W3E-22 | Exam seating plans: student-to-seat assignment, room striping, printable seat lists | 4 | 4 | 1.0 | 4.0 | exams | [9] |
| W3E-23 | Waitlist for a full slot with automatic offer on cancel or release | 3 | 3 | 1.0 | 4.0 | bookings | [11] |
| W3E-24 | Optional GlitchTip profile (all-in-one ≤ 512 MiB, own DB in the existing Postgres) for teams that want a Sentry-style UI | 2 | 2 | 1.0 | 4.0 | W3-OPS | [28] |
| W3E-25 | Solver research spike: decomposition + incremental repair for term-wide models; offline agentic model reformulation, validated by the planner gate | 3 | 4 | 1.0 | 3.0 | solver | [18][38][39] |
| W3E-26 | Teams / Outlook bot or add-in for booking and check-in | 3 | 4 | 0.8 | 2.4 | integrations | [12][16] |


---

## Sources

Dates are publication dates where the page gives one; "accessed 2026-10-17" otherwise.

1. Apereo, "UniTime 4.9 Released – Modernized Timetabling and Documentation", 2025-09-30. https://www.apereo.org/news/2025/unitime-49-released-modernized-timetabling-and-documentation
2. Apereo, "UniTime 4.8 build 159" (2024-09) and "UniTime 4.8, Build 170" (2024-12). https://www.apereo.org/news/2024/unitime-48-build-159-here · https://www.apereo.org/news/2024/unitime-48-build-170-release
3. Müller, Rudová, Müllerová, "Real-world university course timetabling at the International Timetabling Competition 2019", J. Scheduling 28(2), online 2024-04-12. https://link.springer.com/article/10.1007/s10951-023-00801-w
4. Coursedog, "Academic course scheduling software" (vendor page), accessed 2026-10-17. https://www.coursedog.com/products/academic-course-scheduling-software
5. Old Dominion University, "Coursedog" implementation page, accessed 2026-10-17. https://www.odu.edu/coursedog
6. University of Strathclyde Resource Booker / DCU academic systems pages, accessed 2026-10-17. https://bookings-dev.strath.ac.uk/Home/Course/5843 · https://www.dcu.ie/ovpaa/Systems-supported-Academic-Systems.shtml
7. TechnologyOne, "Syllabus Plus" (vendor page), accessed 2026-10-17. https://technologyonecorp.co.nz/products/syllabus-plus
8. GetApp, "Celcat Timetabler" listing (third party), accessed 2026-10-17. https://www.getapp.co.uk/software/2074278/celcat-timetabler
9. Berger-Levrault, "Infosilem Exam" (vendor page), accessed 2026-10-17. https://www.berger-levrault.com/ca/en/product/exam-scheduling-software-infosilem-exam/
10. Accruent, "EMS + Ellucian" (vendor page), accessed 2026-10-17; brochure (2022). https://www.accruent.com/products/ems/shared-space-resource-scheduling-software · https://accruent.com/hubfs/assets/pdf/brochures/the-scheduling-solution-for-the-modern-campus.pdf
11. Robin support, "Abandoned meeting protection", accessed 2026-10-17. https://support.robinpowered.com/hc/en-us/articles/360032675532
12. Microsoft Learn, "Enable auto release" (Places), accessed 2026-10-17; HANDS ON tek, "Microsoft Places – Managed booking with Copilot" (2024-11); topedia, "New desk reservation capabilities in Microsoft Places" (2025-09). https://learn.microsoft.com/microsoft-365/places/enable-auto-release · https://m365admin.handsontek.net/microsoft-365-app-microsoft-places-managed-booking-with-copilot/ · https://blog-en.topedia.com/2025/09/new-desk-reservation-capabilities-in-microsoft-places/
13. Skedda, "Room booking software" / "Desk booking system" (vendor), accessed 2026-10-17; People Managing People, "Skedda Review 2026" (mentions the 2026-05-24 check-in analytics). https://www.skedda.com/platform/room-scheduling-software · https://peoplemanagingpeople.com/tools/skedda-review/
14. Robin blog, "Reduce no-show meetings", accessed 2026-10-17. https://robinpowered.com/blog/reduce-no-show-meetings
15. Robin release notes via releases.sh, "Robin User Agent" (2026-04-23), accessed 2026-10-17. https://releases.sh/robin.md
16. Windows Report, "Microsoft Places is now available in Teams…", accessed 2026-10-17. https://windowsreport.com/microsoft-places-is-now-available-in-teams-and-you-can-use-it-to-book-meetings-rooms-without-any-anxiety/
17. Google Workspace Admin Help, "Set up Google Calendar room booking suggestions", accessed 2026-10-17; Workspace Updates, 2023-07. https://support.google.com/a/answer/9025584 · https://workspaceupdates.googleblog.com/2023/07/improved-meeting-room-suggestions-in-google-calendar.html
18. Moreira, de Freitas, "Fast University Timetabling via Room-wise CP-SAT Decomposition and Incremental Repair", SEMISH 2026, 2026-07-19. https://sol.sbc.org.br/index.php/semish/article/view/43522
19. LiteLLM docs, "Budgets, Rate Limits", accessed 2026-10-17. https://docs.litellm.ai/docs/proxy/users
20. PureAI, "PyPI Removes Compromised LiteLLM Releases…", 2026-03-25; Penligent analysis. https://pureai.com/Articles/2026/03/25/PyPI-Removes-Compromised-LiteLLM-Releases-After-Warnings-of-Stolen-Credentials.aspx · https://www.penligent.ai/hackinglabs/?p=4086
21. OWASP GenAI Security Project, "OWASP Top 10 for LLM Applications 2025" announcement, 2024-11-17/19. https://genai.owasp.org/2024/11/17/owasp-reveals-updated-2025-top-10-risks-for-llms-announces-new-llm-project-sponsorship-program-and-inaugural-sponsors/
22. Beurer-Kellner et al., "Design Patterns for Securing LLM Agents against Prompt Injections", arXiv 2506.08837 (2025); S. Willison commentary 2025-06-13. https://arxiv.org/pdf/2506.08837 · https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/
23. Hines et al. (Microsoft), "Defending Against Indirect Prompt Injection Attacks With Spotlighting", arXiv 2403.14720 (2024). https://arxiv.org/html/2403.14720v1
24. Debenedetti et al. (Google / DeepMind / ETH), "Defeating Prompt Injections by Design" (CaMeL), arXiv 2503.18813; S. Willison, 2025-04-11. https://simonwillison.net/2025/Apr/11/camel/
25. Braintrust, "Portkey alternatives 2026" (third party), accessed 2026-10-17. https://www.braintrust.dev/articles/portkey-alternatives-2026
26. Grafana Labs, "Grafana Loki 3.4: … Promtail merging into Alloy", 2025-02-13. https://grafana.com/blog/2025/02/13/grafana-loki-3.4-standardized-storage-config-sizing-guidance-and-promtail-merging-into-alloy/
27. OpenRouter, "Zero Data Retention" and "Provider logging" docs, accessed 2026-10-17. https://openrouter.ai/blog/insights/zero-data-retention/ · https://www.openrouter.ai/docs/guides/privacy/provider-logging.md
28. GlitchTip, "Installation" documentation, accessed 2026-10-17. https://glitchtip.com/documentation/install
29. Sentry, "Self-Hosted Sentry" (developer docs), accessed 2026-10-17. https://develop.sentry.dev/self-hosted/
30. Grafana docs, "Install Grafana" (hardware and database requirements), accessed 2026-10-17. https://grafana.com/docs/grafana/latest/setup-grafana/installation/
31. Robust Perception, "Why does Prometheus use so much RAM?"; Grafana Alloy docs, "Estimate resource usage", accessed 2026-10-17. https://www.robustperception.io/why-does-prometheus-use-so-much-ram · https://grafana.com/docs/alloy/next/set-up/estimate-resource-usage/
32. Atatürk Üniversitesi OBS policy; Trabzon Üniversitesi; Necmettin Erbakan Üniversitesi senate decision (2026); SBTÜ student handbook, accessed 2026-10-17. https://atauni.edu.tr/yuklemeler/bd9109386b412e2f5c40c1a486ac881a.pdf · https://erbakan.edu.tr/storage/departments/files/99999991/E%C4%9Fitim%20Komisyon%20Kararlar%C4%B1/2026/E%C4%9E%C4%B0T%C4%B0M%20VE%20AKADEM%C4%B0K%20YAPILANMA%20KOM%C4%B0SYON%20KARARI%20(1).pdf · https://oidb.sivas.edu.tr//media/uploads/images/Ogrenci/On-Lisans-ve-Lisans-Ogrenci-El-Kitabi/Ogrenci-El-Kitabi.pdf
33. CottGroup, "Standard contract notification obligation and penalties", 2024-11-18 (law-firm summary). https://cottgroup.com/en/blog/kvkk-gdpr/item/standard-contract-notification-obligation-and-penalties
34. İmer Hukuk, summary of KVKK "Üretken Yapay Zekâ ve Kişisel Verilerin Korunması Rehberi (15 Soruda)" (Yayın No 113, Nov 2025), accessed 2026-10-17. https://imer.av.tr/kvkk-araclari/uretken-yapay-zeka-kisisel-veri-rehberi
35. Erdem & Erdem, "Kişisel Verilerin Korunması Bülteni – 2025 4. Çeyrek"; Alomaliye, 2025-11-24. https://www.erdem-erdem.av.tr/bilgi-bankasi/kisisel-verilerin-korunmasi-bulteni-2025-4-ceyrek · https://www.alomaliye.com/2025/11/24/sorularla-uretken-yapay-zeka-ve-kisisel-verilerin-korunmasi-rehberi/
36. Erdem & Erdem, "Web Siteleri ve Mobil Uygulamaların Erişilebilirliği Hakkında 2025/10 Sayılı Cumhurbaşkanlığı Genelgesi Yayımlandı", 2025-06-30. https://www.erdem-erdem.av.tr/bilgi-bankasi/web-siteleri-ve-mobil-uygulamalarin-erisilebilirligi-hakkinda-2025-10-sayili-cumhurbaskanligi-genelgesi-yayimlandi
37. KPMG Türkiye, "Web Siteleri ve Mobil Uygulamaların Erişilebilirliği" (2026-05). https://assets.kpmg.com/content/dam/kpmgsites/tr/pdf/2026/05/Web%20Siteleri%20ve%20Mobil%20Uygulamalar%C4%B1n%20Eri%C5%9Filebilirli%C4%9Fi.pdf
38. Szeider, "CP-Agent: Agentic Constraint Programming", arXiv 2508.07468 (v1 2025-08-10, v3 2026-02-03). https://arxiv.org/abs/2508.07468
39. Voboril, Szeider, "Improving Constraint Models with LLM Agents", arXiv 2608.08127 (2026-08-08, v2 2026-09-22). https://arxiv.org/abs/2608.08127
40. Sharma, Sharma, "SCHEDBench: … LLM Constraint Faithfulness in Natural-Language Combinatorial Scheduling", arXiv 2608.00991 (2026-08-02, v2 2026-08-26). https://arxiv.org/abs/2608.00991
41. University of Nottingham, "Join us in Nottingham for PATAT 2026" (25–28 Aug 2026). https://www.nottingham.ac.uk/computerscience/events/join-us-in-nottingham-for-patat-2026.aspx
42. Lingaro, "Claude data residency and compliance explained"; tianpan.co, "The inference region your data residency policy forgot to pin", 2026-06-02 (third party; cross-checked with the claude-api skill reference cached 2026-10-06). https://lingarogroup.com/insights/claude-data-residency-and-compliance-explained · https://tianpan.co/blog/2026-06-02-the-inference-region-your-data-residency-policy-forgot-to-pin
43. VictoriaMetrics docs, "Single-server VictoriaMetrics", accessed 2026-10-17. https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/
44. TrueFoundry, "VictoriaLogs vs Loki" (2025-07, single-team benchmark). https://www.truefoundry.com/blog/victorialogs-vs-loki
45. CubeAPM, "OpenObserve vs SigNoz"; Railway OpenObserve template; virtua.cloud VPS guide, accessed 2026-10-17. https://cubeapm.com/blog/openobserve-vs-signoz/ · https://railway.com/deploy/openobserve · https://www.virtua.cloud/learn/de/tutorials/signoz-openobserve-vps-selbst-hosten
46. Grafana docs, "Run Grafana behind a reverse proxy"; Last9, "How to get Grafana iframe embedding right"; grafana/grafana issue 66724, accessed 2026-10-17. https://grafana.com/tutorials/run-grafana-behind-a-proxy/ · https://last9.io/blog/how-to-get-grafana-iframe-embedding-right · https://github.com/grafana/grafana/issues/66724
47. Macworld, "Fantastical 2 for OS X review" (older review; live preview). https://www.macworld.com/article/225186/review-fantastical-2-ups-the-ante-for-events-in-os-x.html
48. DAISY KB, "Dragging movements (WCAG 2.5.7)", accessed 2026-10-17. https://kb.daisy.org/publishing/docs/wcag/dragging-movements.html
49. Deque University, "WCAG 2.2 updates", accessed 2026-10-17. https://dequeuniversity.com/resources/wcag-2.2
50. The Art of Service, "Turkey KVKK Art. 9 (2024)" (compliance control page), accessed 2026-10-17. https://compliance.theartofservice.com/controls/turkey-kvkk/kvkk-art9-2024
51. Gazete Vatan on the 2019 information security circular; Gün + Partners, "Verilerin Türkiye'de depolanması yönünde gelişmeler", accessed 2026-10-17. https://www.gazetevatan.com/gundem/cumhurbaskani-erdogandan-bilgi-ve-iletisim-guvenligi-tedbirleri-genelgesi-1263570 · https://beta.gun.av.tr/media/nmahshox/verilerin-tu-rkiye-de-depolanmasi-yo-nu-nde-gelis-meler.pdf
52. YÖK, "CoHE has prepared the Ethics Guide of Generative Artificial Intelligence Use" (2024). https://www.yok.gov.tr/en/Sayfalar/news/2024/cohe-has-prepared-the-ethics-guide-of-generative-artificial-intelligence-use.aspx
53. CASRAI, "EU AI Act digital omnibus deadline delay"; National Law Review, "EU Digital Omnibus AI enters force", accessed 2026-10-17 (secondary). https://www.casrai.org/news/eu-ai-act-digital-omnibus-deadline-delay · https://natlawreview.com/article/eu-digital-omnibus-ai-enters-force
