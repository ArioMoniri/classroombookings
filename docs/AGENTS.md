# Agent Protocol (subagents, watchdog, worktrees, hand-offs)

The orchestrator (main session) owns the plan and the git branch `claude/gracious-cerf-w1598m`.
Builders work in disjoint directories so they can run in parallel without merge conflicts; reviewers
and testers are read-mostly and may run in `isolation: worktree`.

## Roles & characteristics (`.claude/agents/*.md`)

| Agent | Writes to | Traits |
|---|---|---|
| `backend-engineer` | `smartsched/backend/{app/api,app/models,app/schemas,app/importers,app/services,alembic,tests}` | pragmatic, TDD-first, Turkish-text aware, never touches `app/solver` internals |
| `solver-engineer` | `smartsched/backend/app/solver`, `tests/solver` | OR/CP specialist, obsessive about proofs of infeasibility and determinism (fixed seeds) |
| `ai-engineer` | `smartsched/backend/app/ai`, `tests/ai` | loads `claude-api` skill first, schema-strict tool use, never trusts model output without validation |
| `frontend-engineer` | `smartsched/frontend` | TypeScript strict, accessibility, motion with restraint, responsive first |
| `design-pro` (parallel ×N) | `docs/design/*.md`, `smartsched/frontend/src/components/ui` | researches Mobbin + the reference component sites, extracts patterns, imports MIT components, documents sources/licences |
| `devops-engineer` | `smartsched/deploy`, `.github/workflows`, `scripts/` | one-click, reproducible, secrets never committed |
| `strict-reviewer` | nothing (reports) | adversarial; blocks on correctness, security, data-loss, unverified claims; proposes roadmap items |
| `user-tester` | `docs/testing/*.md` | plays the planner (Fatih Bey persona) end-to-end; reports friction & bugs with repro steps |
| `researcher` | `docs/RESEARCH.md` | citations or it didn't happen |

## Watchdog (continuity of subagents)

1. **Ledger**: every agent appends a line to `docs/PROGRESS.md` when it starts, every meaningful
   milestone, and when it stops (`[ts] [agent] [phase] status: … next: …`). The orchestrator reads it on
   every wake.
2. **Heartbeat**: long builders are launched in the background; the orchestrator schedules a check-in
   (`send_later` / `ScheduleWakeup`, 20–30 min) and, on wake, (a) reads the ledger, (b) runs
   `make check` for the agent's directory, (c) re-launches a fresh agent with the ledger's `next:` line
   if the previous one died or stalled.
3. **Scope fences**: each launch prompt names the only directories the agent may write; `git status`
   is checked after completion and out-of-scope changes are reverted.
4. **Definition of Done per launch**: tests green in scope, ledger updated, no TODOs left silently —
   unfinished items go to `docs/ROADMAP.md` backlog.
5. **Script**: `scripts/watchdog.py` prints stale ledger entries (> 45 min without update) and failing
   checks; CI runs it in "report" mode.

## Worktree protocol

- Builders that must touch overlapping files (rare) are launched with `isolation: worktree`; the
  orchestrator merges with `git merge --no-ff` after `make check`.
- Reviewers always get a worktree so experiments never leak into the branch.

## Hand-off format (end of every agent report)

```
DONE: …            (verified how)
NOT DONE: …        (why; moved to backlog?)
FILES: …
TESTS: command + result summary
RISKS / QUESTIONS FOR USER: …
ROADMAP SUGGESTIONS: …
```
