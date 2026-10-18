"""FIX-G (2026-10-18): round-4 AS-20 / CH-12 open items, owner rule "apply the recommended option".

AS20-F09: planners (``planning.edit``) create and edit DRAFT season profiles; only admins (``planning.admin``)
activate, revert or retire. Every planner write is audited under the planner's id.
"""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import AuditEvent
from sqlalchemy import select

from tests.api_fixtures import login
from tests.crbs_support import make_user

LECTURE = [{"season": "BAHAR", "period_kind": "LECTURE"}]


def _body(key: str = "planlamaci-taslak") -> dict:
    return {"key": key, "name_tr": "Planlamacı taslağı", "name_en": "Planner draft", "applies_to": LECTURE}


async def _actors(client) -> tuple[dict[str, str], dict[str, str], int]:
    admin = await login(client)
    pid, planner = await make_user(client, admin, "planner-g@example.com", role="PLANNER")
    return admin, planner, pid


async def _audit(action: str, entity_id: int) -> list[AuditEvent]:
    async with get_session_factory()() as s:
        return list(
            (
                await s.execute(
                    select(AuditEvent).where(AuditEvent.action == action, AuditEvent.entity_id == str(entity_id))
                )
            ).scalars()
        )


async def test_as20_f09_planner_drafts_admin_activates(client):
    admin, planner, pid = await _actors(client)
    # the planner reads the list and creates a draft
    r = await client.get("/api/v1/seasons/profiles", headers=planner)
    assert r.status_code == 200, r.text
    assert r.json()["can_activate"] is False
    assert (await client.get("/api/v1/seasons/profiles", headers=admin)).json()["can_activate"] is True
    r = await client.post("/api/v1/seasons/profiles", json=_body(), headers=planner)
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["status"] == "draft"
    [row] = await _audit("season_profile.create", draft["id"])
    assert row.actor_id == pid
    # ...edits the draft in place
    r = await client.put(f"/api/v1/seasons/profiles/{draft['id']}", json={"name_tr": "Yeni ad"}, headers=planner)
    assert r.status_code == 200 and r.json()["status"] == "draft", r.text
    [row] = await _audit("season_profile.update", draft["id"])
    assert row.actor_id == pid
    # ...cannot approve it
    r = await client.post(f"/api/v1/seasons/profiles/{draft['id']}/activate", headers=planner)
    assert r.status_code == 403
    assert r.json()["detail"]["permission"] == "planning.admin"
    assert r.json()["detail"]["message_tr"]
    assert await _audit("season_profile.activate", draft["id"]) == []
    # the admin approves it
    r = await client.post(f"/api/v1/seasons/profiles/{draft['id']}/activate", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "active"
    # editing the active profile gives the planner a new draft version, still inert
    r = await client.put(
        f"/api/v1/seasons/profiles/{draft['id']}", json={"solver_weights": {"room_preference": 6}}, headers=planner
    )
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert (v2["version"], v2["status"], v2["parent_id"]) == (2, "draft", draft["id"])
    # the planner may throw away a draft, but not retire or revert the active version
    r = await client.delete(f"/api/v1/seasons/profiles/{draft['id']}", headers=planner)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/seasons/profiles/{v2['id']}/activate", headers=admin)
    assert r.status_code == 200
    r = await client.post(f"/api/v1/seasons/profiles/{v2['id']}/revert", headers=planner)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/seasons/profiles/{v2['id']}/revert", headers=admin)
    assert r.status_code == 200
    r = await client.put(f"/api/v1/seasons/profiles/{draft['id']}", json={"name_tr": "Üçüncü"}, headers=planner)
    v3 = r.json()
    assert v3["status"] == "draft"
    r = await client.delete(f"/api/v1/seasons/profiles/{v3['id']}", headers=planner)
    assert r.status_code == 204
    [row] = await _audit("season_profile.delete", v3["id"])
    assert row.actor_id == pid
    # the admin retires the active one
    r = await client.delete(f"/api/v1/seasons/profiles/{draft['id']}", headers=admin)
    assert r.status_code == 204


async def test_as20_f09_viewer_and_segments_stay_closed(client):
    admin, planner, _pid = await _actors(client)
    _vid, viewer = await make_user(client, admin, "viewer-g@example.com", role="VIEWER")
    assert (await client.get("/api/v1/seasons/profiles", headers=viewer)).status_code == 403
    assert (await client.post("/api/v1/seasons/profiles", json=_body("v"), headers=viewer)).status_code == 403
    # the season calendar (segments) stays an admin tool
    assert (await client.post("/api/v1/seasons/terms/1/segments", json={}, headers=planner)).status_code == 403


# ------------------------------------------------------------------------------------------------ AS20-F13


def test_as20_f13_advisor_counts_a_merge_group_once() -> None:
    from datetime import date

    from app.services import exam_advisor as ea

    d1, d2 = date(2026, 6, 1), date(2026, 6, 2)
    items = [
        # one shared exam listed by three programmes: one sitting
        ea.ExamItem(id=1, request_ids=(1, 2, 3), label="ORT101", date=d1, start=1, end=2, seats=90, rows=3),
        ea.ExamItem(id=4, request_ids=(4,), label="A", date=d1, start=3, end=4, seats=30),
        ea.ExamItem(id=5, request_ids=(5,), label="B", date=d2, start=1, end=2, seats=30),
    ]
    s = ea.summary(items)
    assert s["peak_day"] == d1.isoformat() and s["peak_exams"] == 2
    out = ea.advise(items)
    assert "bir kez" in out["basis"]["tr"] and "counts once" in out["basis"]["en"]


def test_as20_f13_one_unit_for_the_advisor_the_forecast_and_b6a(parsed_exam_list) -> None:  # type: ignore[no-untyped-def]
    from app.services import backtest as bt
    from app.services import exam_advisor as ea

    b6a = bt.exam_day_load(parsed_exam_list).metrics
    adv = ea.summary(ea.items_from_exam_list(parsed_exam_list))
    assert (adv["peak_day"], adv["peak_exams"]) == (b6a["peak_day"], b6a["peak_exams"]) == ("2026-06-03", 98)
    assert adv["weekday_mean"] == b6a["weekday_mean"]


# ------------------------------------------------------------------------------------------------ CH12-F10


async def test_ch12_f10_public_not_found_logs_its_reason_but_answers_the_same(client, caplog):  # type: ignore[no-untyped-def]
    import logging

    from app.core import throttle

    throttle.PUBLIC_PER_ADDRESS.reset()
    pub = "/api/v1/public/schedule"
    caplog.set_level(logging.INFO, logger="app.api.v1.public_schedule")
    r = await client.get(f"{pub}/rooms/A204")
    assert r.status_code == 404 and r.json() == {"detail": "not found"}
    assert "reason=off" in caplog.text
    admin = await login(client)
    assert (
        await client.put("/api/v1/public-schedule/admin/settings", json={"enabled": True}, headers=admin)
    ).status_code == 200
    caplog.clear()
    r = await client.get(f"{pub}/rooms/A204", params={"date": "2001-01-01"})
    assert r.status_code == 404 and r.json() == {"detail": "not found"}
    assert "reason=date" in caplog.text
    caplog.clear()
    r = await client.get(f"{pub}/rooms/ZZ999")
    assert r.status_code == 404 and r.json() == {"detail": "not found"}
    assert "reason=unknown" in caplog.text
