#!/usr/bin/env bash
# Gate: smartsched/deploy/validate.sh on the host (python3-yaml, docker compose config, nginx -t if present),
# plus the docs check: every generated block of the Markdown docs (<!-- AUTO:<name> --> markers) matches its source
# (scripts/docs/sync_docs.py --check, standard library only) and the generator's own tests pass.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$WS/src"
docs_rc=0
section "docs check (scripts/docs/sync_docs.py --check)"
python3 -I scripts/docs/sync_docs.py --check --diff || docs_rc=1
python3 -I -m unittest discover -s scripts/docs/tests || docs_rc=1
section "README media check (scripts/record/check_readme.py)"
python3 -I scripts/record/check_readme.py || docs_rc=1
section "deploy/validate.sh"
bash smartsched/deploy/validate.sh
if [[ $docs_rc -ne 0 ]]; then
  echo "docs check failed: run 'python3 -I scripts/docs/sync_docs.py' and commit the result" >&2
fi
exit "$docs_rc"
