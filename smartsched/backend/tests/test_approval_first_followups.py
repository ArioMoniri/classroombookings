"""Approval-first follow-ups (ROADMAP "Approval-first backend finished", follow-ups 2026-10-15).

* ``python -m app.cli set-setting <key> <value>`` writes through the validation of ``PUT /org/settings`` (whitelisted
  keys only, values validated, secrets never printed); the institution seed profile uses it for
  ``bookings.approval_mode=all``.
* Approvers get ONE ``approval.requested`` message per submission (``group_id`` = the multi-booking), also when a
  group decision advances every period to the next step.
* A withdrawn request is announced to its approvers too (``approval.withdrawn``, their preferences apply).
* The legacy ``booking_created`` / ``booking_cancelled`` / ``room_owner_booking`` e-mails go through
  ``notify_dispatch``: same templates and outbox kinds, an in-app copy, per-user preferences, a ledger key.
* Learning ``refresh`` and on-demand ``purge`` write audit rows naming the actor.

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 102 is free at P1 every Thursday;
A 201 (TIP) is free on Wednesday 18 Feb 2026 at P3-P5 (10:10-12:30).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from app import cli
from app.core import db as dbmod
from app.models import ApprovalRequest, AuditEvent, InAppNotification, NotificationOutbox, Setting
from app.services import notify_dispatch as nd
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

THU = date(2026, 2, 19)
WED = date(2026, 2, 18)
APPR = "/api/v1/approvals"
PREFS = "/api/v1/me/notification-preferences"
BACKEND = Path(__file__).resolve().parents[1]
FAKE_SECRET = "s3" + "cr3t-" + "parola"  # a test fake, built so no secret-shaped literal is committed


async def _outbox(user_id: int, kind: str | None = None) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationOutbox).where(NotificationOutbox.user_id == user_id)
        if kind:
            q = q.where(NotificationOutbox.kind == kind)
        return list((await s.execute(q.order_by(NotificationOutbox.id))).scalars())


async def _inapp(user_id: int, kind: str | None = None) -> list[InAppNotification]:
    async with dbmod.get_session_factory()() as s:
        q = select(InAppNotification).where(InAppNotification.user_id == user_id)
        if kind:
            q = q.where(InAppNotification.kind == kind)
        return list((await s.execute(q.order_by(InAppNotification.id))).scalars())


async def _mode(env, mode: str) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.put("/api/v1/org/settings", json={"approval_mode": mode}, headers=env.admin)
    assert r.status_code == 200 and r.json()["approval_mode"] == mode, r.text


async def _people(env):  # type: ignore[no-untyped-def]  # noqa: F811
    gid, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr", role="ADMIN", firstname="Gözde", lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )  # fmt: skip
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    return gid, gozde, aid, ayse


async def _submit_tip_group(env, ayse) -> int:  # type: ignore[no-untyped-def]  # noqa: F811
    """Ayşe asks for A 201 on Wed 18 Feb at P3, P4 and P5 in one submission (a multi-booking)."""
    c = env.client
    slots = [
        {"date": WED.isoformat(), "period_id": env.periods[p], "room_id": env.rooms["A201"]} for p in ("P3", "P4", "P5")
    ]
    mb = (await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=ayse)).json()
    r = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={"type": "single", "slots": [{"mbs_id": s["mbs_id"]} for s in mb["slots"]]},
        headers=ayse,
    )
    assert r.status_code in (200, 201, 202), r.text
    return int(mb["id"])


# --------------------------------------------------------------------------------------------------
# 1. set-setting CLI (institution seed: bookings.approval_mode=all)
# --------------------------------------------------------------------------------------------------


async def test_set_setting_writes_through_the_org_settings_validation(env):  # noqa: F811
    c = env.client
    async with dbmod.get_session_factory()() as s:
        # NBSP and stray spaces from a copy-pasted runbook are normalised; the key may carry its group
        out = await cli.apply_setting(s, "bookings.approval_mode", " all ")
    assert out == {"key": "bookings.approval_mode", "value": "all", "changed": True}
    assert (await c.get("/api/v1/org/settings", headers=env.admin)).json()["approval_mode"] == "all"
    async with dbmod.get_session_factory()() as s:
        again = await cli.apply_setting(s, "approval_mode", "all")  # the bare field name works too
        assert again == {"key": "bookings.approval_mode", "value": "all", "changed": False}
        row = await s.get(Setting, "bookings.approval_mode")
        assert row is not None and row.value == "all" and row.is_secret is False
    # a Turkish organisation name keeps its letters (İ/ı/ş/ğ) and loses the NBSP
    async with dbmod.get_session_factory()() as s:
        named = await cli.apply_setting(s, "org.name", "İstanbul Sağlık  Üniversitesi")
    assert named["value"] == "İstanbul Sağlık Üniversitesi"
    # booleans and the "same validation" rules of PUT /org/settings
    async with dbmod.get_session_factory()() as s:
        assert (await cli.apply_setting(s, "bookings.show_ungrouped_rooms", "true"))["value"] is True
    for key, value, why in (
        ("bookings.approval_mode", "hepsi", "approval_mode"),  # not rules | all
        ("bookings.approval_mode", "", "approval_mode"),
        ("org.website", "javascript:alert(1)", "website"),
        ("timezone", "Europe/Ankara", "timezone"),  # unknown zone (Turkey is Europe/Istanbul)
        ("smtp.password", FAKE_SECRET, "unknown setting"),  # not whitelisted: secrets are not set here
        ("org.logo_url", "/x.png", "unknown setting"),
        ("bookings.audit_undo_hours", "48", "unknown setting"),  # not in PUT /org/settings either
    ):
        async with dbmod.get_session_factory()() as s:
            try:
                await cli.apply_setting(s, key, value)
            except cli.SettingError as exc:
                assert why in str(exc), (key, str(exc))
                assert FAKE_SECRET not in str(exc) and "cr3t" not in str(exc)
            else:
                raise AssertionError(f"{key}={value!r} was accepted")
    assert (await c.get("/api/v1/org/settings", headers=env.admin)).json()["approval_mode"] == "all"


def test_set_setting_command_line(tmp_path: Path) -> None:
    """The real command: exit 0 and a one-line JSON on success, exit 2 without echoing a refused value."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    run_env = {**os.environ, "PYTHONPATH": str(BACKEND)}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "app.cli", "--database-url", url, "set-setting", *args],
            cwd=BACKEND, env=run_env, capture_output=True, text=True, timeout=120,
        )  # fmt: skip

    ok = run("bookings.approval_mode", "all")
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout) == {"key": "bookings.approval_mode", "value": "all", "changed": True}
    bad = run("smtp.password", FAKE_SECRET)
    assert bad.returncode == 2 and "unknown setting" in bad.stderr
    assert "cr3t" not in bad.stdout + bad.stderr
    wrong = run("bookings.approval_mode", "hepsi")
    assert wrong.returncode == 2 and "rules" in wrong.stderr and "all" in wrong.stderr


# --------------------------------------------------------------------------------------------------
# 2. one approver message per submission
# --------------------------------------------------------------------------------------------------


async def test_approvers_get_one_message_per_submission(env):  # noqa: F811
    c = env.client
    gid, gozde, aid, ayse = await _people(env)
    await c.post("/api/v1/approval-rules", json={"entity_type": "tag", "tag": "TIP"}, headers=env.admin)
    mb_id = await _submit_tip_group(env, ayse)
    inbox = (await c.get(f"{APPR}/inbox", headers=gozde)).json()
    assert len(inbox) == 3 and {x["group_id"] for x in inbox} == {mb_id}
    (note,) = await _inapp(gid, "approval.requested")
    assert note.data is not None
    assert note.data["group_id"] == mb_id and sorted(note.data["request_ids"]) == sorted(x["id"] for x in inbox)
    assert [p["name"] for p in note.data["periods"]] == ["P3", "P4", "P5"]
    assert note.data["requester"]["name"] == "Ayşe Yılmaz" and note.data["room"] == "A 201"
    assert "A 201" in note.title and "10:10-12:30" in note.title and "18.02.2026" in note.body
    assert "Ayşe Yılmaz" in note.body
    (mail,) = await _outbox(gid, "approval_requested")
    assert "10:10-12:30" in mail.subject and "Ayşe Yılmaz" in mail.body
    assert await _inapp(aid) == []  # the requester gets nothing for her own submission
    # a single request still gets its own message
    r = await env.book(ayse, "A202", WED, "P3")
    assert r.status_code == 202, r.text
    assert len(await _inapp(gid, "approval.requested")) == 2


async def test_group_decision_advancing_a_step_sends_one_message_to_the_next_step(env):  # noqa: F811
    c = env.client
    gid, gozde = await env.user(
        "gozde@uni.edu.tr", role="ADMIN", firstname="Gözde", lastname="Ayrancıgil",
        approves_for=[{"type": "tag", "tag": "TIP"}],
    )  # fmt: skip
    mid, murat = await env.user(
        "murat.isik@uni.edu.tr", role="ADMIN", firstname="Murat", lastname="Işık",
        approves_for=[{"type": "room", "id": env.rooms["A101"]}],
    )  # fmt: skip
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    rule = await c.post(
        "/api/v1/approval-rules",
        json={
            "entity_type": "tag",
            "tag": "TIP",
            "steps": [
                {"approvers": {"type": "designated"}, "min_approvals": 1},
                {"approvers": {"type": "users", "ids": [mid]}, "min_approvals": 1},
            ],
        },
        headers=env.admin,
    )
    assert rule.status_code == 201, rule.text
    mb_id = await _submit_tip_group(env, ayse)
    assert len(await _inapp(gid, "approval.requested")) == 1 and await _inapp(mid) == []
    r = await c.post(f"{APPR}/groups/{mb_id}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 200 and [x["ok"] for x in r.json()["results"]] == [True, True, True], r.text
    (step2,) = await _inapp(mid, "approval.requested")
    assert step2.data is not None and step2.data["step"] == 2 and step2.data["group_id"] == mb_id
    assert len(step2.data["request_ids"]) == 3 and "Işık" not in step2.body and "Ayşe Yılmaz" in step2.body
    assert len(await _outbox(mid, "approval_requested")) == 1
    assert await _inapp(aid) == []  # not decided yet: nothing for the requester
    r = await c.post(f"{APPR}/groups/{mb_id}/decide", json={"decision": "approve"}, headers=murat)
    assert [x["status"] for x in r.json()["results"]] == ["APPROVED"] * 3, r.text
    assert len(await _inapp(aid, "approval.approved")) == 1


# --------------------------------------------------------------------------------------------------
# 3. withdraw notifies the approvers
# --------------------------------------------------------------------------------------------------


async def test_withdraw_notifies_the_approvers_with_their_preferences(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    gid, gozde, aid, ayse = await _people(env)
    r = await env.book(ayse, "A102", THU, "P1", notes="FZT 132 telafi")
    assert r.status_code == 202, r.text
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    # Gözde keeps in-app for withdrawals but switches their e-mail off
    p = await c.put(PREFS, json={"events": {"approval.withdrawn": {"email": False}}}, headers=gozde)
    assert p.status_code == 200, p.text
    assert (await c.post(f"{APPR}/{req['id']}/withdraw", headers=ayse)).status_code == 200
    (note,) = await _inapp(gid, "approval.withdrawn")
    assert note.data is not None and note.data["decision"] == "withdrawn" and note.data["request_id"] == req["id"]
    assert note.data["requester"]["name"] == "Ayşe Yılmaz" and note.data["status"] == "WITHDRAWN"
    assert "Ayşe Yılmaz" in note.body and "A 102" in note.title and "19.02.2026" in note.body
    assert "geri çekti" in note.body  # the approver's text, not the requester's "Talebiniz geri çekildi"
    assert await _outbox(gid, "approval_withdrawn") == []
    # the requester's own confirmation is unchanged (both channels)
    assert len(await _inapp(aid, "approval.withdrawn")) == 1 and len(await _outbox(aid, "approval_withdrawn")) == 1
    # the label in the preferences screen covers both sides
    ev = next(e for e in (await c.get(PREFS, headers=gozde)).json()["events"] if e["event"] == "approval.withdrawn")
    assert ev["channels"] == {"in_app": True, "email": False} and "geri çek" in ev["label_tr"]


# --------------------------------------------------------------------------------------------------
# 4. legacy booking e-mails through the dispatcher
# --------------------------------------------------------------------------------------------------


async def test_booking_created_and_cancelled_go_through_the_dispatcher(env):  # noqa: F811
    c = env.client
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    oid, _owner = await env.user("oda.sorumlusu@uni.edu.tr", firstname="İlker", lastname="Şahin")
    await c.put(f"/api/v1/room-admin/rooms/{env.rooms['A102']}", json={"owner_user_id": oid}, headers=env.admin)
    prefs = (await c.get(PREFS, headers=teacher)).json()
    assert {"booking.created", "booking.cancelled", "room_owner.booking"} <= {e["event"] for e in prefs["events"]}
    r = await env.book(env.planner, "A102", THU, "P1", user_id=tid, notes="Fatih Bey ayırdı")
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    # the same template and outbox kind as before, plus the in-app copy with the same text
    (mail,) = await _outbox(tid, "booking_created")
    assert mail.subject == "Sizin adınıza rezervasyon yapıldı" and "A 102" in mail.body and mail.status == "UNSENT"
    (note,) = await _inapp(tid, "booking.created")
    assert note.title == mail.subject and note.body == mail.body and note.booking_id == bid
    assert note.data is not None and note.data["booking_ids"] == [bid]
    (own,) = await _outbox(oid, "room_owner_booking")
    assert "A 102" in own.subject and len(await _inapp(oid, "room_owner.booking")) == 1
    # Hatice switches cancellation e-mails off: the cancellation reaches her in-app only
    p = await c.put(PREFS, json={"events": {"booking.cancelled": {"email": False}}}, headers=teacher)
    assert p.status_code == 200, p.text
    r = await c.post(
        f"/api/v1/bookings/{bid}/cancel", json={"scope": "one", "reason": "Sınav haftası"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    assert await _outbox(tid, "booking_cancelled") == []
    (cn,) = await _inapp(tid, "booking.cancelled")
    assert cn.title == "Rezervasyonunuz iptal edildi" and "A 102" in cn.body and "Gerekçe:" in cn.body
    # idempotent: the same occurrence dispatched again reaches nobody twice
    async with dbmod.get_session_factory()() as s:
        from app.models import User

        user = await s.get(User, tid)
        assert user is not None
        dup = nd.Notice(event="booking.created", key=f"booking:{bid}:created", title="t", body="b")
        assert {d.channel: d.status for d in await nd.dispatch(s, user, dup)} == {
            "in_app": "duplicate",
            "email": "duplicate",
        }
        await s.commit()
    assert len(await _inapp(tid, "booking.created")) == 1


async def test_own_booking_sends_nothing_and_series_mail_keeps_its_template(env):  # noqa: F811
    c = env.client
    tid, teacher = await env.user("hoca@uni.edu.tr")
    assert (await env.book(teacher, "A102", THU, "P1")).status_code == 201
    assert await _inapp(tid) == [] and await _outbox(tid) == []
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": "2026-02-26",
        "start": "2026-02-26",
        "end": "2026-03-12",
        "user_id": tid,
    }
    r = await c.post("/api/v1/bookings/recurring", json=body, headers=env.planner)
    assert r.status_code == 201, r.text
    (mail,) = await _outbox(tid, "booking_created")
    assert mail.subject == "Sizin adınıza rezervasyon yapıldı" and mail.body.count("A 102") == 3
    assert len(await _inapp(tid, "booking.created")) == 1


# --------------------------------------------------------------------------------------------------
# 5. audit rows for the learning writes that had none
# --------------------------------------------------------------------------------------------------


async def test_learning_refresh_and_purge_are_audited(env):  # noqa: F811
    c = env.client
    r = await c.post("/api/v1/learning/refresh", json={"term_id": env.term_id}, headers=env.planner)
    assert r.status_code == 200, r.text
    r = await c.post("/api/v1/learning/purge", headers=env.admin)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        rows = {
            e.action: e
            for e in (
                await s.execute(select(AuditEvent).where(AuditEvent.action.in_(["learning.refresh", "learning.purge_run"])))
            ).scalars()
        }
    assert set(rows) == {"learning.refresh", "learning.purge_run"}
    assert rows["learning.refresh"].actor_id is not None and rows["learning.refresh"].term_id == env.term_id
    assert rows["learning.refresh"].after and "extract" in rows["learning.refresh"].after
    assert rows["learning.purge_run"].after == {"resets": 0, "observations": 0, "feedback": 0}


async def test_withdrawn_request_row_keeps_its_audit(env):  # noqa: F811
    """Withdraw is still audited once (approval.withdraw) after the approver notice was added."""
    c = env.client
    await _mode(env, "all")
    _gid, _gozde, _aid, ayse = await _people(env)
    r = await env.book(ayse, "A102", THU, "P1")
    async with dbmod.get_session_factory()() as s:
        rid = (await s.execute(select(ApprovalRequest.id).where(ApprovalRequest.booking_id == r.json()["id"]))).scalar_one()
    assert (await c.post(f"{APPR}/{rid}/withdraw", headers=ayse)).status_code == 200
    async with dbmod.get_session_factory()() as s:
        acts = list((await s.execute(select(AuditEvent.action).where(AuditEvent.entity_id == str(rid)))).scalars())
    assert acts.count("approval.withdraw") == 1
