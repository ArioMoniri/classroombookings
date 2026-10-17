"""Owner decision 2026-10-17 (R2-M-08, ledger ``decisions-2026-10-17``): only coordinators and administrators
(``planning.admin``) set a person's priority. A planner gets a coded 403 ``person_priority_admin`` with a Turkish
sentence and nothing changes; section and request priorities stay planner-editable. Real Bahar 2026 data
(``tests/test_p19_moderation.real``): PTL 102 §1 (row 601) and its primary instructor.
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import AuditEvent
from sqlalchemy import select

from tests.crbs_support import make_user
from tests.test_loop_r1_lane_d import ROW, _row
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)

API = "/api/v1"


async def test_a_planner_cannot_set_a_persons_priority_but_an_admin_can(real: dict[str, Any]) -> None:  # noqa: F811
    c, admin, tid = real["client"], real["admin"], real["term_id"]
    rid, sid, iid = await _row(tid, ROW)
    _pid, planner = await make_user(c, admin, "pelin.planlamaci@uni.edu.tr", role="PLANNER", full_name="Pelin Işık")
    body = {"term_id": tid, "priority": "high", "note": "Engelli öğrencisi var"}

    r = await c.put(f"{API}/moderation/people/{iid}/priority", json=body, headers=planner)
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert d["code"] == "person_priority_admin" and d["permission"] == "planning.admin"
    assert d["message_tr"] == "Kişi önceliğini yalnızca koordinatörler ve yöneticiler değiştirebilir."
    assert d["message_en"] and d["message_en"] != d["message_tr"]
    async with dbmod.get_session_factory()() as s:
        rows = (await s.execute(select(AuditEvent).where(AuditEvent.action == "person.priority"))).scalars()
        assert not list(rows)  # nothing was written

    # section and request priorities stay planner-editable
    r = await c.put(f"{API}/moderation/sections/{sid}/priority", json={"priority": 3}, headers=planner)
    assert r.status_code == 200, r.text
    r = await c.put(f"{API}/moderation/requests/{rid}/priority", json={"priority": 4}, headers=planner)
    assert r.status_code == 200, r.text

    r = await c.put(f"{API}/moderation/people/{iid}/priority", json=body, headers=admin)
    assert r.status_code == 200, r.text
