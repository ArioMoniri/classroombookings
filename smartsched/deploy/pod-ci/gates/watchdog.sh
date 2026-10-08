#!/usr/bin/env bash
# Gate (non-blocking): agent ledger report from scripts/watchdog.py, like the Actions watchdog job.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_python -- 'python scripts/watchdog.py; python scripts/watchdog.py --json'
