#!/usr/bin/env bash
# Ruflo (formerly Claude Flow) as a *developer* harness for this repository. See docs/universal/RUFLO.md.
#
#   scripts/ruflo.sh doctor                 # version + the safe flags this wrapper always sets
#   scripts/ruflo.sh swarm                  # hierarchical swarm sized for .claude/agents (8)
#   scripts/ruflo.sh objective "text" [--run]
#                                           # dry run by default: writes the queen prompt to .hive-mind/;
#                                           # --run launches Claude Code with permission prompts ON
#   scripts/ruflo.sh mcp                    # register the Ruflo MCP server for *your* Claude Code only
#   scripts/ruflo.sh status                 # swarm + hive status
#   scripts/ruflo.sh stop                   # stop a background daemon an earlier, unwrapped run started
#
# Never runs `ruflo init` here: init writes CLAUDE.md, .claude/settings.json hooks and helper scripts
# (some auto-commit and push) that this repository does not want. Pinned version, no @latest.
set -euo pipefail

VERSION="${RUFLO_VERSION:-3.55.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Measured in a scratch copy (docs/universal/RUFLO.md "What the CLI does on every run"):
# * every command except `daemon` auto-starts a background worker daemon -> RUFLO_DAEMON_AUTOSTART=0
# * every command checks npm for updates (once a day, ~/.claude-flow/update-state.json) -> --no-update
# * an existing .claude/helpers is auto-refreshed (also ~/.claude/helpers) -> RUFLO_HELPERS_LOCKED=1
# * hooks are not installed here at all (no `init`); CLAUDE_FLOW_HOOKS_ENABLED=false for the MCP server
export DO_NOT_TRACK=1
export npm_config_update_notifier=false
export CLAUDE_FLOW_HOOKS_ENABLED=false
export RUFLO_NO_SKILLS_SH=1
export RUFLO_DAEMON_AUTOSTART=0
export RUFLO_HELPERS_LOCKED=1

ruflo() { npx -y "ruflo@${VERSION}" "$@" --no-update; }

protocol() {
  cat <<EOF
You are the SmartSched orchestrator (queen). Follow docs/AGENTS.md exactly: builders work only in the
directories listed for them in .claude-flow/smartsched-swarm.yaml, every agent appends ledger lines to
docs/PROGRESS.md, reviewers are read-only, and every report ends with the hand-off format
(DONE / NOT DONE / FILES / TESTS / RISKS / ROADMAP). Delegate to the Claude Code subagents defined in
.claude/agents/*.md by name (backend-engineer, solver-engineer, ai-engineer, frontend-engineer,
design-pro, devops-engineer, strict-reviewer, user-tester). Run each agent's gate before reporting done.
Never push to a branch other than the current one, never force-push, never commit secrets.

Objective: $1
EOF
}

cmd="${1:-doctor}"
shift || true
case "$cmd" in
  doctor)
    echo "ruflo@${VERSION} (pinned), repo ${ROOT}"
    echo "env: DO_NOT_TRACK=1 npm_config_update_notifier=false CLAUDE_FLOW_HOOKS_ENABLED=false RUFLO_NO_SKILLS_SH=1"
    ruflo --version
    ;;
  swarm)
    ruflo swarm init --topology hierarchical --max-agents 8
    ;;
  objective)
    [[ $# -ge 1 ]] || { echo "usage: scripts/ruflo.sh objective \"<objective>\" [--run]" >&2; exit 2; }
    text="$1"
    shift
    ruflo hive-mind init -t hierarchical
    if [[ "${1:-}" == "--run" ]]; then
      ruflo hive-mind spawn --claude --no-auto-permissions -o "$(protocol "$text")"
    else
      ruflo hive-mind spawn --claude --dry-run --no-auto-permissions -o "$(protocol "$text")"
    fi
    ;;
  mcp)
    command -v claude >/dev/null || { echo "Claude Code CLI not found" >&2; exit 1; }
    claude mcp add ruflo -s local -e DO_NOT_TRACK=1 -e npm_config_update_notifier=false \
      -e CLAUDE_FLOW_HOOKS_ENABLED=false -e RUFLO_DAEMON_AUTOSTART=0 -e RUFLO_HELPERS_LOCKED=1 \
      -- npx -y "ruflo@${VERSION}" mcp start
    ;;
  status)
    ruflo swarm status || true
    ruflo hive-mind status || true
    ;;
  stop)
    npx -y "ruflo@${VERSION}" daemon stop || true
    ;;
  *)
    sed -n "2,14p" "$0"
    exit 2
    ;;
esac
