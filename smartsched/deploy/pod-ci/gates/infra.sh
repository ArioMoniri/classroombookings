#!/usr/bin/env bash
# Gate: pod CI + AWS bootstrap tests and lint (this CI tests itself before it redeploys itself).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
in_python -- '
python -m venv /w/venv-infra && . /w/venv-infra/bin/activate
pip install -q -r smartsched/deploy/pod-ci/requirements-test.txt
echo "==== ruff"; ruff check infra/aws smartsched/deploy/pod-ci
echo "==== pytest"; python -m pytest infra/aws/tests smartsched/deploy/pod-ci/tests -q -p no:cacheprovider
'
