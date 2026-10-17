"""CAL-03 scope-bound links, the department rule and per-scope approval, on the real Bahar 2026 import.

A link made through ``POST /calendar/subscriptions`` serves only its own path (any other feed path is a 404). The
department scope is allowed for the person's own department, a department of a section they teach, or holders of
``calendar.department_feed`` ("Bölüm ders takvimini dışa aktarma"); it is re-checked on every poll. Each create
records the ``calendar_sync`` consent it rests on and an audit row; revoking, rotating and a refused scope are
audited too; withdrawing the consent revokes every link; legacy links keep their mine / room feeds.
"""

from __future__ import annotations

import pytest
from app.core import db as dbmod
from app.models import AuditEvent, CalendarFeedToken, Consent
from app.services import kvkk
from sqlalchemy import select

from tests.cal_support import link_instructor, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off

PANEL = "https://rezervasyon.uni.edu.tr"


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)
    await env.client.put("/api/v1/calendar/admin/settings", json={"public_url": PANEL}, headers=env.admin)


async def _audits(action: str) -> list[AuditEvent]:
    async with dbmod.get_session_factory()() as s:
        q = select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        return list((await s.execute(q)).scalars())


async def _sub(env, headers, **body):  # type: ignore[no-untyped-def]  # noqa: F811
    return await env.client.post("/api/v1/calendar/subscriptions", json=body, headers=headers)


async def test_cal_03_a_link_serves_only_its_own_scope(env):  # noqa: F811
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    mine = (await _sub(env, ayse, scope_kind="my_classes", label="iPhone")).json()
    dep = await _sub(env, ayse, scope_kind="department_classes", scope_id=p.program_id)  # she teaches in Psikoloji
    assert dep.status_code == 201, dep.text
    dep = dep.json()
    assert dep["scope_label"].endswith(" bölümünün dersleri") and dep["scope_label_en"].endswith("classes")
    base = "/api/v1/calendar/feeds"
    c = env.client
    assert (await c.get(f"{base}/{mine['token']}/classes.ics")).status_code == 200
    for path in ("mine.ics", f"room/{p.room.id}.ics", f"department/{p.program_id}.ics",
                 f"department-classes/{p.program_id}.ics"):  # fmt: skip
        assert (await c.get(f"{base}/{mine['token']}/{path}")).status_code == 404, path
    assert (await c.get(f"{base}/{dep['token']}/department-classes/{p.program_id}.ics")).status_code == 200
    assert (await c.get(f"{base}/{dep['token']}/department-classes/{p.program_id + 1}.ics")).status_code == 404
    assert (await c.get(f"{base}/{dep['token']}/classes.ics")).status_code == 404
    # a legacy link keeps mine and room feeds, but not the new scoped paths
    legacy = (await c.post("/api/v1/calendar/feeds/tokens", json={}, headers=ayse)).json()["token"]
    assert (await c.get(f"{base}/{legacy}/mine.ics")).status_code == 200
    assert (await c.get(f"{base}/{legacy}/room/{p.room.id}.ics")).status_code == 200
    assert (await c.get(f"{base}/{legacy}/classes.ics")).status_code == 404
    # the approval: consent id, audit row (never the token), list with "en son çekti"
    async with dbmod.get_session_factory()() as s:
        consent_id = (
            await s.execute(select(Consent.id).where(Consent.user_id == uid, Consent.purpose == "calendar_sync"))
        ).scalar_one()
        row = await s.get(CalendarFeedToken, mine["id"])
        assert row is not None and row.consent_id == consent_id and row.scope_kind == "my_classes"
        assert row.fields and row.fields["co_instructors"] is False
    assert mine["consent_id"] == consent_id
    created = await _audits("calendar.subscription_create")
    assert [a.entity_id for a in created] == [str(mine["id"]), str(dep["id"])]
    assert created[0].after["scope_kind"] == "my_classes" and mine["token"] not in str(created[0].after)
    listing = (await c.get("/api/v1/calendar/subscriptions", headers=ayse)).json()
    one = next(x for x in listing["links"] if x["id"] == mine["id"])
    assert one["last_used_at"] and one["last_fetched_tr"].startswith("Takviminiz en son çekti:")
    assert one["path"] == "classes.ics" and "token" not in one
    # the KVKK data export lists the scope of each link
    async with dbmod.get_session_factory()() as s:
        from app.models import User

        user = await s.get(User, uid)
        assert user is not None
        data = await kvkk.export_data(s, user)
    kinds = {x.get("scope_kind") for x in data["calendar_links"] if x["record"].startswith("feed link")}
    assert kinds == {"my_classes", "department_classes", None}


async def test_cal_03_department_rule_permission_and_every_poll(env):  # noqa: F811
    p = await psy262(env)
    role = (
        await env.client.post(
            "/api/v1/roles", json={"name": "Bölüm koordinatörü", "permissions": ["room.view"]}, headers=env.admin
        )
    ).json()
    _, mehmet = await env.user("mehmet.kaya@uni.edu.tr", role=None, role_id=role["id"])
    await calendar_consent(env.client, mehmet)
    r = await _sub(env, mehmet, scope_kind="department_classes", scope_id=p.program_id)  # a forged id
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert d["code"] == "department_not_allowed"
    assert d["message_tr"] == "Bu bölümün derslerini dışa aktarma yetkiniz yok. Bölüm başkanınızdan isteyin."
    denied = await _audits("calendar.scope_denied")
    assert denied and denied[-1].after["scope_id"] == p.program_id
    # the options say why before anyone taps
    opts = (await env.client.get("/api/v1/calendar/export/options", headers=mehmet)).json()
    scopes = {s["kind"]: s for s in opts["scopes"]}
    assert scopes["my_classes"]["available"] is False and scopes["my_classes"]["reason"]["code"] == "not_linked"
    assert scopes["department_classes"]["available"] is False
    assert scopes["my_bookings"]["available"] is True
    # the permission grants it; taking it away closes the feed at the next poll
    r = await env.client.put(
        f"/api/v1/roles/{role['id']}",
        json={"name": "Bölüm koordinatörü", "permissions": ["room.view", "calendar.department_feed"]},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    opts = (await env.client.get("/api/v1/calendar/export/options", headers=mehmet)).json()
    dep_scope = next(s for s in opts["scopes"] if s["kind"] == "department_classes")
    assert dep_scope["available"] is True and any(x["id"] == p.program_id for x in dep_scope["departments"])
    sub = (await _sub(env, mehmet, scope_kind="department_classes", scope_id=p.program_id)).json()
    url = f"/api/v1/calendar/feeds/{sub['token']}/department-classes/{p.program_id}.ics"
    assert (await env.client.get(url)).status_code == 200
    await env.client.put(
        f"/api/v1/roles/{role['id']}", json={"name": "Bölüm koordinatörü", "permissions": ["room.view"]},
        headers=env.admin,
    )  # fmt: skip
    assert (await env.client.get(url)).status_code == 404
    # unknown scope / missing id
    assert (await _sub(env, mehmet, scope_kind="department_classes")).status_code == 422
    assert (await _sub(env, mehmet, scope_kind="students")).status_code == 422
    assert (await _sub(env, mehmet, scope_kind="department_classes", scope_id=999999)).status_code == 404


async def test_cal_03_revoke_rotate_and_consent_withdrawal(env):  # noqa: F811
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    # without the consent: 409 consent_required (the sheet shows the consent tick)
    r = await _sub(env, ayse, scope_kind="my_classes")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "consent_required"
    await calendar_consent(env.client, ayse)
    a = (await _sub(env, ayse, scope_kind="my_classes")).json()
    b = (await _sub(env, ayse, scope_kind="my_bookings")).json()
    c = env.client
    feed = "/api/v1/calendar/feeds"
    assert (await c.get(f"{feed}/{b['token']}/mine.ics")).status_code == 200
    rot = await c.post(f"/api/v1/calendar/subscriptions/{a['id']}/rotate", headers=ayse)
    assert rot.status_code == 201, rot.text
    rot = rot.json()
    assert rot["scope_kind"] == "my_classes" and rot["token"] != a["token"]
    assert (await c.get(f"{feed}/{a['token']}/classes.ics")).status_code == 404
    assert (await c.get(f"{feed}/{rot['token']}/classes.ics")).status_code == 200
    assert (await c.delete(f"/api/v1/calendar/subscriptions/{rot['id']}", headers=ayse)).status_code == 204
    assert (await c.get(f"{feed}/{rot['token']}/classes.ics")).status_code == 404
    _, other = await env.user("baskasi@uni.edu.tr")
    assert (await c.delete(f"/api/v1/calendar/subscriptions/{b['id']}", headers=other)).status_code == 404
    assert [x.entity_id for x in await _audits("calendar.subscription_revoke")] == [str(rot["id"])]
    assert len(await _audits("calendar.subscription_rotate")) == 1
    # withdrawing the consent revokes every link
    assert (await c.delete("/api/v1/me/consents/calendar_sync", headers=ayse)).status_code == 200
    assert (await c.get(f"{feed}/{b['token']}/mine.ics")).status_code == 404
    assert (await c.get("/api/v1/calendar/subscriptions", headers=ayse)).json()["links"] == []
    # the KVKK switch off: the API refuses quietly
    await c.put("/api/v1/calendar/admin/settings", json={"calendar_sync_enabled": False}, headers=env.admin)
    await calendar_consent(env.client, ayse)
    r = await _sub(env, ayse, scope_kind="my_classes")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "calendar_sync_off"
