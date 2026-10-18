"""FIX-F AS20-F11: "Bu sürüme dön" onto the version that is already current writes no new version."""

from __future__ import annotations

from app.models import LearningVersion
from sqlalchemy import func, select

from tests.test_as_13_learning import API, _refresh
from tests.test_p19_learning import _session, env  # noqa: F401


async def test_as20_f11_identical_revert_adds_no_version(env):  # noqa: F811
    v1 = (await _refresh(env, env.guz))["version"]
    v2 = (await _refresh(env, env.guz))["version"]
    assert v2["checksum"] == v1["checksum"]  # nothing changed between the two refreshes
    r = await env.client.post(f"{API}/learning/versions/{v1['id']}/revert", headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["unchanged"] is True and out["identical"] is True
    assert out["version"]["number"] == 2  # the current version, not a new "Geri dönüş" row
    async with _session() as s:
        n = (
            await s.execute(select(func.count(LearningVersion.id)).where(LearningVersion.term_id == env.guz))
        ).scalar_one()
    assert n == 2
