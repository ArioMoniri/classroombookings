"""pod-ci/README.md stays in sync with podci/gates.py (gate table and the flow line)."""

from __future__ import annotations

from podfakes import POD_CI

from podci.gates import GATES


def test_readme_lists_every_gate_in_order() -> None:
    text = (POD_CI / "README.md").read_text(encoding="utf-8")
    for g in GATES:
        assert f"| `{g.name}` |" in text, f"README gate table misses {g.name}"
    flow = next(line for line in text.splitlines() if "prepare -> validate" in line)
    assert [s.strip() for s in flow.split("->")] == [g.name for g in GATES]
