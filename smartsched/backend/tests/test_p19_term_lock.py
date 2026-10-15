"""P19-03 / review 2026-10-15 D8: a per-term write lock for imports and commits. Two imports of one term never run
at once: the second waits (``wait_s``) or is refused with the holder's name (HTTP 409). The lock is a row in
``term_locks`` (works across worker processes), expires when its holder dies and is kept alive while it works.

Real Bahar 2026 import (``tests/crbs_env``): term ``2026-BAHAR``.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from app.core import db as dbmod
from app.models import TermLock
from app.models.base import utcnow
from app.services import term_lock as tl

from tests.crbs_env import env  # noqa: F401


def test_keys_fold_case_spaces_and_turkish_letters():
    assert tl.term_key("2026-BAHAR") == tl.term_key(" 2026-bahar\xa0") == "term:2026-BAHAR"
    assert tl.term_key("2026-2027 güz") == tl.term_key("2026-2027 GÜZ") == "term:2026-2027 GÜZ"
    # dotted / dotless i: a code typed "final", "FİNAL" (Turkish upper case) or "FINAL" is one term
    assert tl.term_key("2026-final") == tl.term_key("2026-FİNAL") == tl.term_key("2026-FINAL") == "term:2026-FINAL"
    with pytest.raises(ValueError):
        tl.term_key("  ")


async def test_second_import_of_the_same_term_is_refused_with_the_holder(env):  # noqa: F811
    key = await tl.term_key_for(env.term_id)
    assert key == "term:2026-BAHAR"
    async with tl.term_write_lock(key, "import:12 planning-list (Bahar Derslik Planlama Listesi v5.xlsx)"):
        with pytest.raises(tl.TermLocked) as info:
            async with tl.term_write_lock(tl.term_key("2026-bahar"), "import:13 weekly-grid"):
                pass
        assert "import:12 planning-list" in str(info.value)
        http = tl.http_error(info.value)
        assert http.status_code == 409 and http.detail["holder"].startswith("import:12")
        with pytest.raises(tl.TermLocked):
            await tl.assert_unlocked(key)
        # another term is not blocked
        async with tl.term_write_lock(tl.term_key("2026-2027 GÜZ"), "import:14 planning-list"):
            pass
    await tl.assert_unlocked(key)  # released


async def test_waiting_import_runs_after_the_first_one(env):  # noqa: F811
    key = await tl.term_key_for(env.term_id)
    order: list[str] = []

    async def job(name: str, hold: float) -> None:
        async with tl.term_write_lock(key, name, wait_s=10, poll_s=0.05):
            order.append(f"{name} start")
            await asyncio.sleep(hold)
            order.append(f"{name} end")

    first = asyncio.create_task(job("import:1", 0.3))
    await asyncio.sleep(0.05)
    await asyncio.gather(first, job("import:2", 0))
    assert order == ["import:1 start", "import:1 end", "import:2 start", "import:2 end"]


async def test_concurrent_acquire_has_exactly_one_winner(env):  # noqa: F811
    key = await tl.term_key_for(env.term_id)
    results = await asyncio.gather(*(tl.acquire(key, f"commit:{i}") for i in range(5)), return_exceptions=True)
    won = [r for r in results if isinstance(r, tl.LockHandle)]
    assert len(won) == 1 and all(isinstance(r, tl.TermLocked) for r in results if r not in won)
    await tl.release(won[0])


async def test_dead_holder_expires_and_a_live_one_is_kept_alive(env):  # noqa: F811
    key = await tl.term_key_for(env.term_id)
    async with dbmod.get_session_factory()() as s:  # a worker died while importing: its row stays behind
        s.add(
            TermLock(key=key, holder="import:9 (worker gone)", token="dead", expires_at=utcnow() - timedelta(seconds=1))
        )
        await s.commit()
    async with tl.term_write_lock(key, "import:10", ttl_s=1.0) as h:
        await asyncio.sleep(1.5)  # longer than the ttl: the heartbeat extends it
        with pytest.raises(tl.TermLocked):
            await tl.acquire(key, "import:11")
        assert h.holder == "import:10"
    await tl.assert_unlocked(key)
