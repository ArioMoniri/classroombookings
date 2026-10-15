# Ruflo in the development harness

[Ruflo](https://github.com/ruvnet/ruflo) (formerly Claude Flow; npm `ruflo` and `claude-flow`, both
**3.55.0**, MIT) coordinates several Claude Code agents: swarms and hive-minds, shared memory, and an
MCP server. In this repository it orchestrates the existing subagents in `.claude/agents/*.md` under
the protocol in `docs/AGENTS.md`. **It is not part of the product.** The backend's Ingestion Council is
an in-process Python orchestrator; ARCHITECTURE.md §5 explains why.

## What is in the repository

| Path | What |
|---|---|
| `.claude-flow/config.yaml` | The runtime config written by `ruflo init`, reduced to safe values: hierarchical topology, 8 agents, sqlite memory, **hooks off, auto-execute off, daemon off, neural/learning off, MCP not auto-started**. |
| `.claude-flow/smartsched-swarm.yaml` | Agent mapping: each `.claude/agents/*.md` role → its Ruflo role (worker / specialist / scout), the directories it may write (the scope fences from `docs/AGENTS.md`) and its gate command. Pinned Ruflo version. |
| `.claude-flow/.gitignore` | Ignores every runtime file under `.claude-flow/` except the two configs above. |
| `scripts/ruflo.sh` | The only supported entry point. It pins the version, sets the safe environment and never runs `init`. |
| `.gitignore` | Adds `.swarm/`, `.hive-mind/`, `ruvector.db`, `.mcp.json`, `.claude/proven-config.json` and `.claude/.proven-config-version`. |

What we did **not** take from `ruflo init` (measured in a scratch copy; RESEARCH-2026.md §1.2):

* its 224-line `CLAUDE.md` (it contradicts this repository's commit attribution rules and agent protocol);
* `.claude/settings.json`, whose hooks run `node .claude/helpers/hook-handler.cjs` on PreToolUse,
  PostToolUse, UserPromptSubmit, SessionStart/End, Stop, PreCompact, SubagentStart/Stop and
  Notification, and which also sets a statusline, `"model": "claude-sonnet-5"` and agent teams;
* `.claude/helpers/*` (44 files): `auto-commit.sh` commits **and pushes**, checkpoint hooks commit,
  and `hook-handler.cjs` spawns detached `npx` processes;
* 17 agent templates, about 150 slash commands and 30 skills;
* `.mcp.json` with an unpinned `npx -y ruflo@latest mcp start`.

Our own `.claude/settings` and `CLAUDE.md` are untouched. This repository does not ship them.

## What the CLI does on every run (measured) and how the wrapper neutralises it

| Behaviour of `ruflo@3.55.0` | Wrapper setting |
|---|---|
| Every command except `daemon` starts a **background worker daemon** for the working directory. | `RUFLO_DAEMON_AUTOSTART=0`; `scripts/ruflo.sh stop` stops one started by an unwrapped run. |
| Checks npm for a newer version (at most daily; `~/.claude-flow/update-state.json`). | `--no-update` on every call, `npm_config_update_notifier=false`. |
| Auto-refreshes `.claude/helpers` and **`~/.claude/helpers`** when they exist. | `RUFLO_HELPERS_LOCKED=1` (and we never create helpers). |
| Adopts a signed "proven config" into `.claude/proven-config.json` and `.claude/.proven-config-version`, and writes `.claude-flow/policy/*`. | No opt-out exists. The files are git-ignored. |
| `hive-mind spawn` launches Claude Code with **`--dangerously-skip-permissions` by default**. | The wrapper always passes `--no-auto-permissions`, and `objective` is a dry run unless you add `--run`. |
| `init` offers a Cognitum signup and `npx skills add ruvnet/ruflo`. | The wrapper never runs `init`; `RUFLO_NO_SKILLS_SH=1` is set anyway. |
| Telemetry. | The README and user guide document no telemetry switch. `DO_NOT_TRACK=1` is set as a courtesy. Network use observed: `npx` downloads and the update check. |

`claude-flow@3.55.0 init` fails with a packaging bug ("could not locate .claude/helpers/statusline.cjs")
after writing part of its files, so use the `ruflo` package. The wrapper does.

## Usage (exact commands)

From the repository root. Node 20+ and `npx` are required; the first call downloads the pinned package.

```bash
scripts/ruflo.sh doctor
# ruflo@3.55.0 (pinned), the safe environment, "ruflo v3.55.0"

scripts/ruflo.sh swarm
# hierarchical swarm, max 8 agents (one per .claude/agents role)

scripts/ruflo.sh objective "Review app/council against docs/AGENTS.md and report with the hand-off format"
# dry run: initialises the hive (queen) and writes the coordination prompt to
# .hive-mind/sessions/hive-mind-prompt-<id>.txt; read it before running for real

scripts/ruflo.sh objective "Add an ODS reader to the council intake with tests" --run
# launches Claude Code as the queen WITH permission prompts on; the prompt tells it to delegate to the
# named subagents (backend-engineer, strict-reviewer, ...), respect their write scopes, append to
# docs/PROGRESS.md and run each agent's gate

scripts/ruflo.sh mcp
# registers the Ruflo MCP server for your own Claude Code only (local scope, nothing committed):
# claude mcp add ruflo -s local -e DO_NOT_TRACK=1 ... -- npx -y ruflo@3.55.0 mcp start

scripts/ruflo.sh status     # swarm and hive status
scripts/ruflo.sh stop       # stop a background daemon
```

Use a different version only on purpose, for example `RUFLO_VERSION=3.55.1 scripts/ruflo.sh doctor`.
Read the release notes first, because some releases have been deprecated for broken dependency graphs.

## Rules when Ruflo runs the agents

* The orchestrator (queen) owns the plan and the branch. Builders write only inside their `writes`
  list in `smartsched-swarm.yaml`. Reviewers (`strict-reviewer`, and `user-tester` except for its test
  reports) are scouts.
* The ledger stays `docs/PROGRESS.md`, and the hand-off format stays the one in `docs/AGENTS.md`. Ruflo
  memory (`.swarm/`, `.claude-flow/data/`) is a local cache, never the record.
* Never `--dangerously-skip-permissions`, never `@latest`, never `ruflo init` in this checkout (use a
  scratch copy to try new versions).
* After a session, `git status` must show only the files the agents meant to change; Ruflo state is
  git-ignored.
