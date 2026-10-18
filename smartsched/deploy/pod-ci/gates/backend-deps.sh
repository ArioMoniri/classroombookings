#!/usr/bin/env bash
# Gate: the backend venv of this run (/w/venv) from the hash-pinned locks (gates/backend-lib.sh PY_VENV_INSTALL).
# Built once: backend.sh and the backend-unit-* shards (which may run at the same time) only activate it.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/backend-lib.sh"
in_python -- "$PY_VENV_INSTALL$PY_VENV"
