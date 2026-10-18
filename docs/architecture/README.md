# Architecture diagrams

How SmartSched fits together, drawn as Mermaid so GitHub renders it and there are no images to keep up to date. Each
diagram has a short caption and "where in the code" links. The overview diagram stays in the
[README](../../README.md#architecture); the prose design (domain model, solver contract, event bus) is
[docs/ARCHITECTURE.md](../ARCHITECTURE.md), and the import-to-publish pipeline in plain words is
[docs/HOW_IT_WORKS.md](../HOW_IT_WORKS.md).

Last checked against the code: 2026-10-18 (ledger `arch-d-2026-10-18`).

| Page | Diagrams | Kind |
|---|---|---|
| [c4.md](c4.md) | Level 1 system context (roles, identity providers, mail, calendars, AI providers, channels, CRBS); level 2 containers (compose services and profiles) | C4 flowcharts |
| [backend-components.md](backend-components.md) | API routers → service layer (the facade) → importers, council, solver bridge, AI gateway, helper → models and RLS; frontend folders | component flowchart |
| [flows.md](flows.md) | 1 workbook import (preview → term check → Uygula) · 2 solve and publish · 3 booking with approval · 4 helper turn with a confirm card, plus the HB-23 file hand-over · 5 sign-in with a second step or SSO | sequence diagrams |
| [data-model.md](data-model.md) | terms, weeks, rooms, sections, requests, runs, assignments, bookings, approvals, users, roles, audit, import jobs | ER diagram |
| [deployment.md](deployment.md) | AWS pod control path (POD_ACTION → OIDC → bootstrap CLI → EC2, SSM, alarm, budget); pod CI gates → deploy → health; local one-click `deploy.sh` | flowcharts, sequence |
| [states.md](states.md) | a schedule run (queued → solved → published) and an import job (preview → applied) | state diagrams |

Corrections found while checking the diagrams against the code (the diagrams follow the code):

- There is **no separate worker container**. Solver runs, imports, council jobs, outboxes and sweeps are asyncio jobs
  inside the backend process, and CP-SAT runs in a thread (`workers/queue.py`, `workers/run_jobs.py`).
- nginx does not send `/api/*` to FastAPI. It goes through the Next.js route handler, which turns the httpOnly cookie
  into a bearer token. Only the token `.ics` feeds, `security.txt` and room photos go straight to the backend.
- A run has no `DRAFT` status. "Published" is the `is_active` flag on a solved run, not a status.
- HB-23 (the helper file router) landed in the tree while these pages were written: `/helper/files/*`,
  `ai/helper/files.py` and the hand-over into the import wizard exist, so flow 4b is drawn from the code, not from the
  design doc. Its ROADMAP tickets (HB-23b–d: tests, UX run) are still open.

## Is this worth having?

The verdict is from the architecture lane, after drawing every diagram from the code.

**Necessary: keep these and keep them correct.**

1. **C4 level 1 + level 2** ([c4.md](c4.md)). A KVKK or security auditor asks first what leaves the server and which
   process talks to which. Level 1 is that list of external processors, each off by default. Level 2 shows the one
   path from the browser to the API (through the BFF) and that jobs run in the backend process. The README overview
   is too coarse to answer either question.
2. **Backend facade view** ([backend-components.md](backend-components.md)). This is the onboarding map: routers stay
   thin, the service of each area is the facade, the solver never sees the database, and every model call goes
   through the AI gateway. Reviewers use it to spot a router that calls a provider or bypasses a guard.
3. **Three of the five sequences** ([flows.md](flows.md)):
   - **sign-in** (§5): tokens never reach the page, `token_version` revocation, and identity by `oid`+`tid`;
   - **helper confirm** (§4): a write never runs from model output, and the token is signed, owner-bound and single-use;
   - **booking with approval** (§3): `publish_event` inside the transaction, the audit row, outbox-only side effects
     and the `booking_slots` key.

   These carry the security and audit arguments, and they are where a regression would be a finding.

**Nice: useful, but the code or another doc already says it.**

- **Import** (flow 1) and **solve + publish** (flow 2). They are good for onboarding a planner-side contributor, and
  the 409 guards on publish are easy to miss in `runs.py`. But each repeats the docstrings of `_start_job` and
  `activate_run`.
- **ER diagram** ([data-model.md](data-model.md)). The relationships are easier to read here than in the
  domain-model table of ARCHITECTURE.md, and an RLS review benefits from it. But the table already lists the columns.
- **Run state diagram** ([states.md](states.md)). It answers the owner's "draft → solved → published" exactly once,
  in one place.
- **AWS control path** ([deployment.md](deployment.md)). It helps when the pod is moved or the repository is renamed,
  because the workflow and the OIDC role are what the rename touches. [docs/deploy/AWS.md](../deploy/AWS.md) is the
  runbook.

**I would drop (or never extend) these if they start to drift:**

- **Import-job state diagram.** It is four enum values plus the preview link, and flow 1 already shows them.
- **Pod CI sequence.** [`pod-ci/README.md`](../../smartsched/deploy/pod-ci/README.md) has the same flow, and the gate
  table is generated from `podci/gates.py`. Two copies will disagree first.
- **Local one-click flowchart.** The header of `deploy.sh` is the source of truth and changes often.

**Recommended minimal set:** c4.md, backend-components.md, and flows §3, §4 and §5. Keep the rest while the test
below passes. Delete a "drop" diagram rather than let it go stale.

**The rename.** No diagram contains a repository address, an owner handle, a branch name, a host name or an IP. Every
link is relative, so the rename changes nothing here. The diagrams also do not make the rename any easier. What helps
is the test below, which refuses such strings.

### How they stay correct

- [`scripts/docs/tests/test_architecture_docs.py`](../../scripts/docs/tests/test_architecture_docs.py) is standard
  library only, and pod CI's `validate` gate runs it (`python3 -I -m unittest discover -s scripts/docs/tests`). It
  fails when any of these drifts:
  - a relative link here points at nothing;
  - a module named inside a Mermaid block (`services/solver_bridge.py`, `import-wizard.tsx` …) is renamed or removed;
  - a `METHOD /path` in a diagram is no longer declared by a router in `api/v1`;
  - an ER entity is not a `__tablename__`;
  - a page is missing from this index;
  - an address, a branch name or an IP appears.

  A Mermaid line that contains the word "planned" is exempt from the module and route checks, for work that is
  designed but not merged. Remove the word when it lands, and the test checks those steps too.
- The test cannot see an arrow that has become wrong, such as a new call path. Reviewers own that. A change to a
  facade module (`services/*.py` named in a diagram, `api/deps.py`, `core/rls.py`, `ai/pipeline.py`,
  `helper/confirm.py`) updates its diagram in the same change, and the "Last checked" date above moves.
- Mermaid syntax is not checked in CI, because the repository has no Mermaid package. On 2026-10-18 every block here
  and in the README parsed with `mermaid.parse` from mermaid 11.4.1, installed outside the repository. Use GitHub's
  preview when you edit one.
