"""install.sh must not race with smartsched-ci-update.service (owner refresh 2026-10-18 failed with
`cp: cannot stat '/opt/smartsched-ci.new/./gates/...'`: touching update-request started a second install
that deleted the shared staging directory mid-copy)."""

from __future__ import annotations

import re
from pathlib import Path

INSTALL = (Path(__file__).resolve().parents[1] / "install.sh").read_text()


def test_installs_are_serialized_by_a_lock() -> None:
    lock = INSTALL.index("flock 9")
    assert lock < INSTALL.index('cp -r "$HERE/podci"')


def test_update_request_is_never_touched_when_it_exists() -> None:
    assert not re.search(r"^\s*(touch|chown)\b.*update-request", INSTALL, re.M)
    assert '[[ -e "$STATE/$f" ]] ||' in INSTALL


def test_each_run_stages_in_its_own_directory() -> None:
    assert 'mktemp -d "$DEST.new.XXXXXX"' in INSTALL
    assert '"$DEST.new"' not in INSTALL
