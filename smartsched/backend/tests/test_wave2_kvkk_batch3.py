"""A4 KVKK follow-ups (backend asks batch 3, ``backend-asks-3-2026-10-16``) on the real Bahar 2026 import
(``tests/crbs_env``; clock Monday 16 Feb 2026 08:00):

* item 3 -- every ``PUT /admin/retention/{data_class}`` 422 names a stable ``code`` and the input ``field`` with
  English and Turkish messages (Turkish input forms: ``1.095`` days, ``365 gün``, ``SİL``, ``evet``);
* item 4 -- ``GET /admin/dsr?status=all`` lists every request; ``open | DONE | REFUSED | ...`` as before;
* item 5 -- what withdrawing the ``photo``, ``calendar_sync`` and ``ai_personal`` consents does (counts + audit).
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import AuditEvent
from app.models.kvkk import RetentionPolicy
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

RET = "/api/v1/admin/retention"


def _bilingual(d: dict) -> None:  # type: ignore[type-arg]
    assert d["message"] and d["message_en"] == d["message"] and d["message_tr"]
    assert d["message_tr"] != d["message_en"], d


async def test_retention_errors_carry_field_codes_in_both_languages(env):  # noqa: F811
    c, admin = env.client, env.admin
    assert (await c.get(RET, headers=admin)).status_code == 200  # the rows exist from the first read

    async def put(cls: str, body: dict) -> dict:  # type: ignore[type-arg]
        r = await c.put(f"{RET}/{cls}", json=body, headers=admin)
        assert r.status_code == 422, (cls, body, r.status_code, r.text)
        d = r.json()["detail"]
        assert isinstance(d, dict), d
        _bilingual(d)
        assert d["errors"] and d["errors"][0]["code"] == d["code"] and d["errors"][0]["field"] == d["field"]
        for e in d["errors"]:
            _bilingual(e)
        return d

    # below the floor the code sets (audit 365 days)
    d = await put("audit", {"retain_days": 100})
    assert (d["code"], d["field"], d["floor_days"]) == ("below_floor", "retain_days", 365)
    assert "365" in d["message_tr"] and "365" in d["message_en"]
    # not a number of days, or absurdly long: the same field, its own code
    for bad in ("abc", "12,5", True, 3.5, 10**9, [], {"g": 1}):
        d = await put("booking", {"retain_days": bad})
        assert (d["code"], d["field"]) == ("retain_days", "retain_days"), bad
    # the action: an unknown word, and delete for bookings (anonymised only)
    d = await put("notification", {"action": "yak"})
    assert (d["code"], d["field"]) == ("action", "action") and d["allowed"] == ["delete", "anonymise"]
    d = await put("booking", {"action": "SİL"})
    assert (d["code"], d["field"], d["allowed"]) == ("action", "action", ["anonymise"])
    assert "anonimleştirilir" in d["message_tr"]
    # switches
    for key in ("enabled", "legal_hold"):
        d = await put("notification", {key: "belki"})
        assert (d["code"], d["field"]) == (key, key)
    # a legal hold without a reason, and a reason that is not text
    d = await put("notification", {"legal_hold": True})
    assert (d["code"], d["field"]) == ("legal_hold_reason", "legal_hold_reason")
    d = await put("notification", {"legal_hold": True, "legal_hold_reason": 42})
    assert (d["code"], d["field"]) == ("legal_hold_reason", "legal_hold_reason")
    # unknown data classes, and classes without a retention policy (kept until the person removes them)
    for cls in ("ufo", "account", "phone"):
        d = await put(cls, {"retain_days": 400})
        assert (d["code"], d["field"]) == ("unknown_class", "data_class")
        assert d["allowed"] == ["booking", "audit", "notification"]
    # several mistakes at once: every one listed, the first on top
    d = await put("booking", {"retain_days": "x", "action": "delete", "enabled": "?"})
    assert [(e["code"], e["field"]) for e in d["errors"]] == [
        ("retain_days", "retain_days"),
        ("action", "action"),
        ("enabled", "enabled"),
    ]
    # nothing was changed by a refused request
    async with dbmod.get_session_factory()() as s:
        rows = {p.data_class: p for p in (await s.execute(select(RetentionPolicy))).scalars()}
        assert rows["booking"].action == "anonymise" and rows["booking"].retain_days == 1095
        assert not rows["notification"].legal_hold and not rows["notification"].enabled
        n_audit = len(
            list((await s.execute(select(AuditEvent).where(AuditEvent.action == "kvkk.retention_policy"))).scalars())
        )
        assert n_audit == 0

    # Turkish input forms are read, not refused: thousands dot, "gün", NBSP, SİL / evet / hayır
    r = await c.put(
        f"{RET}/booking", json={"retain_days": "1.095 gün", "enabled": "Evet", "action": "Anonimleştir"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert (r.json()["retain_days"], r.json()["enabled"], r.json()["action"]) == (1095, True, "anonymise")
    r = await c.put(
        f"{RET}/notification", json={"retain_days": " 45 ", "action": "SİL", "enabled": "hayır"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert (r.json()["retain_days"], r.json()["enabled"], r.json()["action"]) == (45, False, "delete")


async def test_dsr_queue_status_all_and_the_allowed_values(env):  # noqa: F811
    c, admin = env.client, env.admin
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    _, ismail = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    _, ali = await env.user("ali.kaya@uni.edu.tr", full_name="Ali Kaya")
    ids = {}
    for who, kind in ((ayse, "rectify"), (ismail, "info"), (ali, "erase"), (ayse, "export")):
        r = await c.post("/api/v1/me/data-requests", json={"kind": kind, "note": "Talep"}, headers=who)
        assert r.status_code == 201, r.text
        ids[kind] = r.json()["id"]
    r = await c.post(f"/api/v1/admin/dsr/{ids['rectify']}/refuse", json={"reason": "Kayıt doğru"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "REFUSED"
    r = await c.post(f"/api/v1/admin/dsr/{ids['info']}/complete", json={"note": "Yanıtlandı"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "DONE", r.text

    async def queue(status: str | None) -> list[int]:
        params = {"status": status} if status is not None else {}
        r = await c.get("/api/v1/admin/dsr", params=params, headers=admin)
        assert r.status_code == 200, (status, r.text)
        return [x["id"] for x in r.json()]

    queued = {ids["rectify"], ids["info"], ids["erase"]}  # exports are self-service, never queued
    assert set(await queue("all")) == queued and len(await queue("all")) == 3
    assert set(await queue("ALL")) == queued
    assert await queue(None) == [ids["erase"]] == await queue("open")
    assert await queue("DONE") == [ids["info"]] == await queue("done")
    assert await queue("REFUSED") == [ids["rectify"]] == await queue("refused")
    assert await queue("OPEN") == [ids["erase"]] and await queue("IN_PROGRESS") == []
    assert await queue("in_progress") == [] and set(await queue(" All ")) == queued
    # an unknown value is a 422 with the allowed values, not an empty list
    r = await c.get("/api/v1/admin/dsr", params={"status": "bitti"}, headers=admin)
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert (d["code"], d["field"]) == ("status", "status") and d["message_tr"] != d["message_en"]
    assert d["allowed"] == ["open", "all", "OPEN", "IN_PROGRESS", "DONE", "REFUSED"]
