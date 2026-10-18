# Wave 3: owner requests of 2026-10-17 ~19:00 UTC (session focused-wright)

Owner's words (verbatim intent): "API and model provider should be synced and chosen by admins between all of them.
Token usage should be monitored by admins and checked for each user, with a threshold and usage-limit alerts, and
guardrails so the scheduler's models are not used for prompt injection or out-of-scope usage. The whole platform should
have the needed security measures and RLS (or the needed equivalent). The admin panel should have operational details
like Grafana for the needed services, plus an error log and tracking. How the slot size is shown is controlled by
admins. Users should be able to make slot reservations easily in a simple UI."

Read COMMON.md (same folder) first: its hard rules apply (no commits, test-first, own ports, never `pkill -f`, nice,
Turkish first, 44 px / 16 px on phones, no weakening of publish/pin/move guards). Ledger rows in docs/PROGRESS.md as
`<role> (wave3-<lane>-2026-10-17)`; add your feature rows to docs/features.yml (status `done` only when shipped with
evidence) and a short "### Wave 3 — <lane> (2026-10-17)" section at the end of docs/ROADMAP.md with `- [x]`/`- [ ]`
items. Final message: BLUF (what shipped, files, tests with counts, stack checks desktop + phone, what is left).

## Lanes and file ownership (never edit another lane's files; write an "Asks" list instead)

| Lane | Owner | Owns (write) | Migration |
|---|---|---|---|
| W3-AI | AI gateway, usage, guardrails | `smartsched/backend/app/ai/**`, new `app/api/v1/ai_admin.py`, `app/services/ai_usage.py`, `app/models/ai_usage.py`, settings keys `ai.*`, `frontend/src/components/admin/ai/**`, `frontend/src/app/(app)/admin/ai/**`, `frontend/src/lib/api/ai-admin.ts`, tests named `test_w3_ai_*` | `0034_ai_usage` (down_revision = the current head `0033_invig_progress`) |
| W3-SEC | security + row-level security | `smartsched/backend/app/core/security*.py`, `app/core/db.py` (session GUCs only), `app/api/deps.py` (request context only; keep `require_permission`), new `app/core/rls.py`, `app/main.py` middleware block, `smartsched/deploy/nginx/**` + `deploy/caddy/**` headers, `docs/SECURITY.md`, tests `test_w3_sec_*` | `0035_rls_policies` (down_revision = `0034_ai_usage`; it must also apply cleanly on SQLite, where RLS is a no-op) |
| W3-OPS | observability + error tracking | new `app/core/observability.py`, `app/api/v1/ops.py`, `app/models/error_event.py`, `smartsched/deploy/observability/**` (Prometheus, Grafana provisioning + dashboards, Loki/Promtail), `deploy/docker-compose*.yml` (an `observability` profile only), `frontend/src/components/admin/ops/**`, `frontend/src/app/(app)/admin/ops/**`, `frontend/src/lib/api/ops.ts`, tests `test_w3_ops_*`, `deploy/pod-ci` only if a gate needs it | `0036_error_events` (down_revision = `0035_rls_policies`) |
| W3-SLOT | slot display + quick reservation | `frontend/src/components/bookings/**`, `frontend/src/components/quick-reserve/**` (new), `frontend/src/app/(app)/reserve/**` (new), `frontend/src/components/settings/slot-display.tsx` (new), backend settings keys `booking.slot_display.*` through `app/services/settings_service.py` SPECS (add keys only) and `app/api/v1/bookings.py` (read-only exposure), tests `test_w3_slot_*` | none (settings are key/value) |
| W3-DES | design + UX specs | `docs/design/v3/**` only | — |
| W3-RES | 2026 research, feature analysis, enhancements | `docs/research/2026-10-17-*.md`, a "Wave 3 enhancements (ranked)" list at the end of docs/ROADMAP.md | — |

Shared files every lane may need: `frontend/messages/{tr,en}.json` (add keys under your own namespace only:
`aiAdmin.*`, `ops.*`, `quickReserve.*` / `slotDisplay.*`, `security.*`), the admin navigation in
`frontend/src/components/shell/nav-config.ts` (one entry per lane, append only), `frontend/playwright.config.ts`
testMatch (already admits `loop-r2-lane[A-Z]`; name e2e specs `w3-<lane>.spec.ts` and add `w3-[a-z]+` once).
Alembic: exactly one head at the end. If your migration is ready before the one below yours, still use the fixed
down_revision above; the orchestrator runs `alembic heads` after each hand-off.

Ports: W3-AI 19510/19511, W3-SEC 19520/19521, W3-OPS 19530/19531 (+ Grafana 19532, Prometheus 19533 if you run
them), W3-SLOT 19540/19541. Scratch: `/tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/w3-<lane>/`.
Three round-3 persona testers also run on this 4-core host: `nice -n 10`, start your stack only when you need it,
`stack.sh down` when done.
