# Strict review: backend, AI layer, Generator Studio (commit 56e7f36, 2026-10-08)

Reviewer: strict-reviewer agent (isolated worktree, real Bahar 2026 import, SQLite + Postgres 16).
Repro scripts were kept in the session scratchpad (`rv/`); every finding below was reproduced.

`make check`: green (387 passed, 3 skipped) — but the gate skips lint/types for `app/ai` and types for `app/api`
(`mypy app/api` → 1 error, `app/api/deps.py:56`).

## BLOCKER

| ID | Finding | Location | Fix |
|---|---|---|---|
| B1 | 1.8 KB sparse-dimension xlsx or 1.5 MB shared-string bomb exhausts memory/CPU on every upload path (mapping, AI ingest, planning list, weekly grid); parsing runs on the event loop | `services/studio_rules.py:685-701`, `ai/ingest.py:161-178`, `importers/planning_list.py:129`, `importers/weekly_grid.py:300` | zip pre-inspection (total uncompressed ≤ ~50 MB, sharedStrings ≤ ~20 MB, ratio ≤ ~100), clamp `<dimension>`/max_col/max_row, parse in a thread or subprocess with RLIMIT_AS, 413/400 |
| B2 | Chat-apply child runs of a studio run ignore the draft → left-out classes come back (17 of 25 placed) | `ai/chat.py:852`, `:1093` | use `studio.build_solver_input_for_run`; regression test |
| B3 | PLANNER disables ADMIN-only built-in hard rules via `params.studio` on `POST /runs` | `api/v1/runs.py:61-65`, `services/solver_bridge.py:733`, `services/studio.py:524-533` | strip reserved keys, whitelist/bound params, honour `params.studio` only for runs created by `studio.generate` |

## MAJOR

| ID | Finding | Fix |
|---|---|---|
| M1 | Draft optimistic concurrency not atomic → lost updates (`services/studio.py:344-369`) | `version_id_col` or conditional UPDATE + rowcount check; concurrent test |
| M2 | Chat-apply idempotency racy → two child runs (`ai/chat.py:766-771`, `:968-971`) | claim with conditional update before work |
| M3 | Per-field revert corrupts rows (start without end, day vs days) (`services/studio_classes.py:691-697`) | revert coupled groups; validate start ≤ end |
| M4 | Re-import erases studio edits; content-hash identity changes when definitive rooms are filled → draft exclusions, pins and rule event_ids detach | stable identity (section key + day + occurrence), conflict report with keep/take, remap ids, skip unchanged rows |
| M5 | Pre-check "fixes" write term-wide data and can unlock LOCKED rooms; `exam_update` has no snapshot (`services/precheck.py:766-783`) | apply as draft overrides; explicit confirm for write-through; If-Match |
| M6 | Queue restart recovery fails in Docker (hostname changes / PID reuse) (`workers/queue.py:162-176`) | heartbeat + boot id; run wall-clock timeout |
| M7 | SQLite: every write → 500 "database is locked" during a solve (read txn held across the thread solve; no WAL) | commit/close before solve; WAL + busy_timeout |
| M8 | Formula injection in xlsx/csv exports (`services/exports.py:96,197`) | quote-prefix text starting with `= + - @ \t \r` |
| M9 | Default `APP_SECRET` accepted in prod → forged admin JWT; `JWT_SECRET` ignored (`core/config.py:21-24`) | refuse start in prod with default/short secret; wire or remove JWT_SECRET |
| M10 | `/constraints` CRUD unvalidated: spoofed `BUILTIN`, unknown kinds, bad params, planner can undo admin switches (`api/v1/constraints.py:34-62`) | restrict source, validate params via catalogue, bound weight, protect BUILTIN rows |
| M11 | Comma-separated instructor lists not split → instructor clashes invisible (53 list-names, 64 people hidden) (`importers/normalize.py:886-896`) | split on `,` / ` ve ` / ` & ` when parts are names |
| M12 | AI instructor resolution maps invented names to real people with status ok (70/315) (`ai/resolve.py:312-326`, `:606`) | exact canonical or exact surname + fuzzy first name; tie margin |
| M13 | No real cancel (DELETE leaves solver running); unbounded `time_limit_s`/`workers` on `POST /runs` | CANCELLED status + StopSearch; server-side bounds; per-user limit |

## MINOR

1. Import uploads have no app-side size limit; failed-job files stay on disk (`api/v1/imports.py:25-31`).
2. PDFs with 20 000 pages read fully before the unit cap (`ai/ingest.py:217-226`); `/health` stalls during imports.
3. Upstream AI error text (can echo the key) returned to clients (`api/v1/chat.py:58`, `ai/client.py:229`); keys with control chars accepted and logged at DEBUG.
4. Postgres-only 500s from unvalidated string lengths (constraint source/kind, run labels).
5. Anonymous `/metrics`; no login rate limiting; JWT error text echoed (`api/deps.py:36`).
6. AI/upload "exclude" section edits are term-wide with no snapshot (`ai/edits.py:89,98`).
7. `copy_rules` creates needs_review rules immediately instead of landing in the review tray (`services/studio_rules.py:622-623`).
8. `parse_weeks` silently inverts "son 7 hafta" → [7] and "2-14 (7. hafta hariç)" → [7] (`importers/normalize.py:574`).
9. Draft readiness and stored fixes go stale after other edits (`services/studio.py:843-844`).
10. A planner-authored preset can switch built-ins off when an admin applies it.
11. `/studio/classes` builds the full SolverInput per call (0.86 s); precheck persists the fix map on every autosave.
12. SSE listener queues unbounded (160 003 queued events in a stress run).
13. `make check` gate excludes `app/ai` lint/types and `app/api` types.
14. Room photo upload checks extension only.

## Test quality

No concurrency tests; no test for B2/B3; conditional assertions in `tests/test_studio_generate.py:62,83`; suite takes ~8 min
(slowest: grid link 51 s, studio template 48 s) → add a `slow` marker and one session-scoped imported DB.

## Verified OK

Auth on all 96 operations (401 anonymous, 403 VIEWER on mutations); draft isolation per (term, user, kind); preset
permissions; studio built-in switches 403 for planners; key masking/never logged/transient keys not stored; prompt-injection
text treated as data and every write still gated by accept/apply; `apply_diff` rejects hard violations; studio generate
excludes left-out ids; upload filename sanitising and authenticated `/imports/{id}/file`; CORS; JWT exp + role re-read;
Alembic upgrade/downgrade on SQLite and Postgres 16 with `alembic check` clean; no N+1 (34 statements for 200 or 2 000
rows); thread-safe progress; parameterized SQL; DATA_ANALYSIS quirks parsed correctly.

## Roadmap suggestions (planner expectations)

Real job control (cancel, priorities, DB-backed queue with heartbeats); scenario mode with draft-scoped overrides and
promote-to-published; import diff & merge with stable identity; audit log + undo; approval workflows (TIP rooms, department
sign-off, request portal); versioned publishing + notifications + iCal + CRBS push; instructor availability, max hours,
elective conflict groups; exam invigilation and seat plans; dated mid-term overrides; SSO and per-faculty planner scopes;
utilisation analytics and capacity what-ifs; term rollover; backups, retention and job health.
