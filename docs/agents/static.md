## How to resume after an interruption

1. `git pull` on `claude/gracious-cerf-w1598m`; read this file, the last 30 lines of `docs/PROGRESS.md`, and `git log --oneline -20`.
2. Run `python3 scripts/watchdog.py` (stale agents) and `cd smartsched/backend && make check`, `cd smartsched/frontend && npm run check`.
3. For each agent under "Running agents" above whose work is not finished, relaunch an agent of the listed type with
   "You are RESUMING <workstream>. Read docs/AGENT_STATE.md (your row in the Running agents table), the last ledger lines for your name, and
   `git log -p --since=<last milestone time> -- <your scope>`; continue from the 'Next' column; keep the same scope fence."
4. Every launch and finish is recorded automatically by the hooks in `.claude/settings.json`; use `python3 scripts/agent_state.py set <id> status=stopped left_off="..."` for agents killed by a limit.
5. Agents never commit; the orchestrator checkpoints with `git add -A && git commit -m "wip: agent progress checkpoint"`
   and pushes. No GitHub Actions on push (billing); CI runs on the AWS pod.
6. Report to the user in BLUF: what was done, what is needed — briefly.

## Queued waves (start when the listed blockers finish)

| Wave | Starts after | Content |
|---|---|---|
| A | review fixes, CRBS parity fixes and solver follow-up finish | no-placeholder audit (remove MSW mock mode, stub solver fallback, placeholder photos; e2e on real backend), schedule comparison vs the planner's grids, strict solver review |
| B | CRBS parity fixes and CRBS booking screens finish | CRBS superset gate (phase 18): acceptance test per behaviour + `scripts/parity_check.py`, 13 CRBS languages + Turkish, legacy upgrade verified against a real CRBS on the pod (`--profile legacy`), side-by-side diff |
| C | wave B | booking enhancements wave 1 (phase 17): room features, find-a-room, notification hub + native Outlook/Google/Teams connectors + webhooks, audit log, approvals by designated admin approvers, conflict resolver, policies, public view, KVKK record; optional Activepieces profile |
| D | calendar redesign and CRBS booking screens finish (shell glass done) | screenshots v2, recordings (`scripts/record/record-all.sh`, English captions), README rewrite (plain editorial style, real screenshots) |
| E | each wave | merge `claude/gracious-cerf-w1598m` into `claude/smartsched-universal`; restyle onboarding |

## AWS pod (live)

- Instance `i-0c04b735e03446110` (t4g.large, us-east-1), EIP `98.86.98.164`, panel `https://98-86-98-164.sslip.io`.
- Admin `umutk@getvivax.com`; password in SSM `/smartsched/admin_password` (read with AWS CloudShell).
- Budget `smartsched-monthly-100usd` with stop action at 100 %; idle-stop alarm (CPU < 5 % for 60 min).
- Control by pushing `infra/aws/POD_ACTION` with `up|status|stop|start|cost|down destroy` (OIDC role, no keys).
- Pod CI polls both branches every 2 min, runs the gates in Docker, posts commit statuses, serves `/ci/`, redeploys the deploy branch.

## User decisions to respect (see docs/ROADMAP.md "User decisions" and docs/product/booking-enhancements.md)

BLUF reports; no GitHub Actions on push; no paid UI components; English README/captions; CRBS behaviour by default with
settings; departments = programmes; ungrouped rooms hidden by default with toggle; approvers = designated administrators;
KVKK signed off by the user (AI booking + calendar sync on, switchable); check-in reminders-first; default model
claude-opus-5-5; trust planner-locked rooms with visible data issues.
