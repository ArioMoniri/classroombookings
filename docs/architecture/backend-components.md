# Backend components (the facade view)

How a request travels through the FastAPI backend, and which module is the facade for each area. Index:
[README.md](README.md). Paths are relative to `smartsched/backend/app/`.

```mermaid
flowchart TB
  bff["Next.js BFF handler<br/>(bearer JWT)"] --> deps

  subgraph edge["Request edge"]
    deps["api/deps.py<br/>get_current_user: JWT + token_version,<br/>Access (permissions + room ACL), rls.bind_user"]
    router["api/v1/router.py<br/>one api_router at /api/v1,<br/>audit_context on every request"]
  end
  deps --> router

  subgraph routers["API routers (api/v1/*.py, thin: parse, check permission, call one service)"]
    r_imp["imports.py · council.py"]
    r_run["runs.py · studio.py · constraints.py"]
    r_book["bookings.py · approvals.py · find_room.py"]
    r_ai["chat.py · helper.py · helper_turn.py · ai_admin.py"]
    r_auth["auth.py · mfa.py · sso.py"]
    r_int["calendar_sync.py · webhooks.py · channels.py"]
  end
  router --> routers

  subgraph services["Service layer = the facade the routers call (services/*.py)"]
    s_imp["import_jobs.py · import_term_check.py<br/>term_lock.py"]
    s_run["solver_bridge.py (build input, run, persist)<br/>studio.py · precheck.py"]
    s_guard["publish_guard.py · planner_check.py<br/>move_guard.py · pin_guard.py · run_truth.py"]
    s_book["bookings.py · approvals.py<br/>booking_policies.py · bookings_undo.py"]
    s_auth["mfa.py · sso.py · identity/ · sessions.py<br/>bookings_ldap.py"]
    s_out["events.py publish_event → audit.py<br/>notify_dispatch.py · calendar_connectors.py · webhooks.py"]
  end
  r_imp --> s_imp
  r_run --> s_run & s_guard
  r_book --> s_book
  r_auth --> s_auth
  r_int --> s_out
  s_book --> s_out

  subgraph engines["Engines behind the facade"]
    importers["importers/<br/>planning_list · exam_list · weekly_grid<br/>room_master · crbs_legacy · detect.py"]
    council["council/<br/>orchestrator · render · fastpath · structure<br/>extract · reconcile · critic · review · commit"]
    solver["solver/ (pure Python, no DB)<br/>model.py · cpsat.py · diagnose.py · repair.py"]
    aigw["AI gateway: ai/client.py AIClient<br/>→ ai/pipeline.py (route, KVKK basis, limits,<br/>guards, ai_usage) → ai/providers/"]
    helper["ai/helper_turn.py · ai/helper/<br/>(index, tooluse, cards, confirm)"]
  end
  s_imp --> importers
  r_imp --> council
  council --> importers
  s_run --> solver
  r_ai --> helper & aigw
  helper --> aigw
  helper -- "writes only after confirm,<br/>with the person's Access" --> services
  council -. "AI intake, off by default" .-> aigw

  subgraph jobs["workers/ (in-process)"]
    queue["queue.py JobQueue<br/>run:/import:/council: keys"]
    runjobs["run_jobs.py<br/>solve_off_loop, cancel"]
    integ["integrations.py<br/>outbox drain, retries"]
    sweep["approvals_sweeper.py · reminders.py"]
  end
  r_run & r_imp -- "enqueue" --> queue
  queue --> runjobs --> s_run
  s_out -- "outbox rows" --> integ

  subgraph data["Persistence"]
    models["models/*.py (SQLAlchemy 2)"]
    db["core/db.py sessions"]
    rls["core/rls.py<br/>after_begin: app.user_id / app.perms,<br/>role smartsched_rls"]
    pg[("PostgreSQL 16<br/>RLS policies: alembic 0035")]
  end
  services --> models
  importers & council --> models
  models --> db --> pg
  rls -. "per transaction" .-> db
```

Routers are meant to stay thin and call the service of their area; that service is the facade. Business rules (term
write lock, publish guard, approval routing, event bus) live there, so the CLI, workers and the helper reuse them
instead of calling routers. Known exception: `api/v1/runs.py` still holds the publish switch and the move endpoint's
orchestration itself (it calls `publish_guard`, `planner_check` and `move_guard`). The solver is a pure function `solve(SolverInput) -> SolverResult`: only `services/solver_bridge.py`
turns database rows into its input and its result back into `assignments`. Every model call goes through `AIClient`
and the gateway pipeline; no router or service calls a provider SDK directly. PostgreSQL row-level security is a
second fence under the API checks: `api/deps.py` binds the signed-in user to the session and `core/rls.py` writes the
context into each transaction (a no-op on SQLite).

Where in the code: [`api/deps.py`](../../smartsched/backend/app/api/deps.py),
[`api/v1/router.py`](../../smartsched/backend/app/api/v1/router.py),
[`services/`](../../smartsched/backend/app/services/),
[`services/solver_bridge.py`](../../smartsched/backend/app/services/solver_bridge.py),
[`services/events.py`](../../smartsched/backend/app/services/events.py),
[`importers/`](../../smartsched/backend/app/importers/), [`council/`](../../smartsched/backend/app/council/),
[`solver/`](../../smartsched/backend/app/solver/) ([README](../../smartsched/backend/app/solver/README.md)),
[`ai/client.py`](../../smartsched/backend/app/ai/client.py), [`ai/pipeline.py`](../../smartsched/backend/app/ai/pipeline.py),
[`ai/helper_turn.py`](../../smartsched/backend/app/ai/helper_turn.py), [`workers/`](../../smartsched/backend/app/workers/),
[`core/rls.py`](../../smartsched/backend/app/core/rls.py),
[`alembic/versions/0035_rls_policies.py`](../../smartsched/backend/alembic/versions/0035_rls_policies.py).

## Frontend layout (for orientation)

| Folder | What lives there |
|---|---|
| [`src/app/(app)/`](../../smartsched/frontend/src/app/(app)/) | signed-in pages (import, runs, timetable, bookings, admin, ...) |
| [`src/app/api/`](../../smartsched/frontend/src/app/api/) | the BFF route handlers: `v1/[...path]` proxy and `auth/mfa/[step]` sign-in steps |
| [`src/components/`](../../smartsched/frontend/src/components/) | one folder per feature (import, runs, bookings, helper, shell, ...) |
| [`src/lib/api/`](../../smartsched/frontend/src/lib/api/) | typed API clients and React Query hooks, one file per area |
