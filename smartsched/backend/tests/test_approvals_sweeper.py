"""The periodic approvals sweep (app/workers/approvals_sweeper.py) runs the same idempotent sweep as
POST /approvals/sweep and survives a failing pass."""

from __future__ import annotations

import asyncio

from app.workers import approvals_sweeper


async def test_loop_keeps_running_after_a_failed_pass(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[int] = []

    async def flaky() -> dict[str, int]:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database briefly unavailable")
        return {"expired": 0, "released": 0}

    monkeypatch.setattr(approvals_sweeper, "sweep_once", flaky)
    approvals_sweeper.start(interval=0.01)
    for _ in range(100):
        if len(calls) >= 3:
            break
        await asyncio.sleep(0.01)
    await approvals_sweeper.stop()
    assert len(calls) >= 3
    assert approvals_sweeper._task is None
