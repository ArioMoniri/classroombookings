"""Deploy safety: the backend's Alembic revisions form ONE chain. Two heads make `alembic upgrade head` fail in
the container entrypoint (migrations on start), so the deploy would fail; this names the problem in the infra
gate before the backend gate or the deploy trips over it (e.g. a merged branch whose migration has the same
down_revision as one on this branch)."""

from __future__ import annotations

import re
from pathlib import Path

from podfakes import REPO

VERSIONS = REPO / "smartsched/backend/alembic/versions"
RX = re.compile(r'^(revision|down_revision)\s*(?::[^=]*)?=\s*(.+)$', re.M)


def chain(directory: Path) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    parents: dict[str, tuple[str, ...]] = {}
    for f in sorted(directory.glob("*.py")):
        vals = dict(RX.findall(f.read_text(encoding="utf-8")))
        if "revision" not in vals:
            continue
        rev = vals["revision"].strip().strip("'\"")
        down = vals.get("down_revision", "None").strip()
        parents[rev] = tuple(re.findall(r"['\"]([^'\"]+)['\"]", down))
    referenced = {p for ps in parents.values() for p in ps}
    heads = sorted(r for r in parents if r not in referenced)
    return parents, heads


def test_chain_parser(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text('revision = "a"\ndown_revision = None\n')
    (tmp_path / "b.py").write_text('revision: str = "b"\ndown_revision: str | None = "a"\n')
    (tmp_path / "c.py").write_text('revision = "c"\ndown_revision = "a"\n')
    assert chain(tmp_path)[1] == ["b", "c"]
    (tmp_path / "m.py").write_text('revision = "m"\ndown_revision = ("b", "c")\n')  # a merge revision
    assert chain(tmp_path)[1] == ["m"]


def test_single_alembic_head() -> None:
    parents, heads = chain(VERSIONS)
    assert parents, "no migrations found"
    assert len(heads) == 1, (f"multiple Alembic heads {heads}: `alembic upgrade head` fails on start; give the newer "
                             "migration down_revision = the current head (or add a merge revision)")
    missing = sorted({p for ps in parents.values() for p in ps} - set(parents))
    assert not missing, f"down_revision points to unknown revisions {missing}"
