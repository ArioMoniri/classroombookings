"""HB-15 admin controls ``ai.helper`` (architecture doc §5.9, §8; helper.md §4.1 rule 8, §5.3).

* ``GET / PUT /ai/admin/helper``: one setting per institution, the defaults (index-only until ``helper`` is routed),
  a partial patch, the ``version`` check between two admins (409), unknown names (422), the ``ai.helper`` audit row;
* an action switched off for an audience disappears from ``GET /helper/actions``, from ``tools_for`` and from the
  list rows' buttons, and its card / confirm answer 403 ``action_off``;
* ``mode: index`` makes 0 model calls even with a routed provider; ``enabled: false`` and an audience switched off
  hide the helper (``/helper/status`` ``enabled: false``);
* the off-scope check's strictness comes from ``guard.scope``.
"""

from __future__ import annotations

import pytest
from app.ai import gateway as gw
from app.ai import helper_turn as ht
from app.ai import pipeline
from app.ai.helper import cards, guard
from app.ai.helper import schema as cs
from app.ai.helper import settings as hs
from app.ai.helper import status as st
from app.ai.helper.actions import registry as reg
from app.core import db as dbmod
from app.core.security import hash_password
from app.models import AuditEvent, User
from app.services import ai_usage as meter
from app.services import kvkk
from app.services import settings_service as ss
from app.services.bookings_perms import load_access
from sqlalchemy import func, select

from tests.ai.conftest import fake_sdk, text  # noqa: F401
from tests.api_fixtures import client, login  # noqa: F401
from tests.crbs_support import make_user

A = "/api/v1/ai/admin/helper"
H = "/api/v1/helper"
MODEL = "claude-opus-5-5"


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    reg.RATE.reset()
    yield
    reg.RATE.reset()


async def _audits() -> int:
    async with dbmod.get_session_factory()() as s:
        return int(
            (await s.execute(select(func.count(AuditEvent.id)).where(AuditEvent.action == "ai.helper"))).scalar_one()
        )


async def test_hb_15_defaults_patch_version_and_audit(client) -> None:  # noqa: F811
    admin = await login(client)
    _, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    assert (await client.get(A, headers=teacher)).status_code == 403
    r = await client.get(A, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    s = body["settings"]
    assert s["enabled"] is True and s["mode"] == "ai" and s["guard"] == {"scope": "normal"}
    assert set(s["audiences"]) == set(hs.AUDIENCES) and all(s["audiences"].values())
    assert set(s["actions"]) == {a.name for a in reg.all_actions()}
    assert all(v == {"enabled": True, "audiences": None} for v in s["actions"].values())
    assert s["memory"] == {"enabled": True, "retention_days": 180} and s["history_days"] == 30
    assert s["feedback_notes"] is True
    # index-only until an admin routes the helper feature (owner default)
    assert body["effective"]["mode"] == "index" and body["effective"]["reason"] == "not_routed"
    assert body["effective"]["message"]["tr"] and body["effective"]["message"]["en"]
    # the catalogue the tab draws from: plain risk words in TR and EN
    risk = {a["name"]: a["risk_label"] for a in body["catalog"]["actions"]}
    assert risk["create_booking"] == {"tr": "Kendi rezervasyonu", "en": "Own booking"}
    assert risk["decide_approval"]["tr"] == "Başkalarını etkiler"
    assert {a["id"] for a in body["catalog"]["audiences"]} == set(hs.AUDIENCES)
    assert [x["id"] for x in body["catalog"]["scopes"]] == ["strict", "normal", "loose"]
    # quotas come from the HB-10 chain: shown, not edited here
    assert body["limits"]["caps"] == gw.DEFAULT_CAPS["helper"] and body["limits"]["faculties"] == 0
    v1 = body["version"]

    r = await client.put(
        A,
        json={"version": v1, "mode": "index", "actions": {"create_booking": {"audiences": ["academician"]}}},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["settings"]["mode"] == "index" and after["version"] != v1
    assert after["settings"]["actions"]["create_booking"] == {"enabled": True, "audiences": ["academician"]}
    assert after["settings"]["actions"]["cancel_my_booking"] == {"enabled": True, "audiences": None}
    assert after["effective"]["reason"] == "index_mode"
    assert await _audits() == 1
    # a second admin with the old version does not overwrite the change
    r = await client.put(A, json={"version": v1, "mode": "ai"}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "stale_settings"
    assert r.json()["detail"]["version"] == after["version"] and r.json()["detail"]["message_tr"]
    r = await client.put(A, json={"actions": {"drop_tables": {"enabled": False}}}, headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_action"
    r = await client.put(A, json={"audiences": {"rector": False}}, headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_audience"
    r = await client.put(A, json={"guard": {"scope": "paranoid"}}, headers=admin)
    assert r.status_code == 422
    assert await _audits() == 1
    # HB-09's memory route writes the same setting and keeps the HB-15 fields
    r = await client.put(f"{H}/admin/settings", json={"retention_days": 90}, headers=admin)
    assert r.status_code == 200
    s = (await client.get(A, headers=admin)).json()["settings"]
    assert s["memory"]["retention_days"] == 90 and s["mode"] == "index"


async def test_hb_15_action_off_disappears_everywhere(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    names = {a["name"] for a in (await client.get(f"{H}/actions", headers=teacher)).json()}
    assert "create_booking" in names and "cancel_my_booking" in names
    # Ayşe has no instructor record: the welcome guide's audience is "staff"
    r = await client.put(
        A,
        json={
            "actions": {
                "create_booking": {"audiences": ["academician", "admin"]},
                "cancel_my_booking": {"enabled": False},
            }
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    names = {a["name"] for a in (await client.get(f"{H}/actions", headers=teacher)).json()}
    assert "create_booking" not in names and "cancel_my_booking" not in names and "my_bookings" in names
    r = await client.post(f"{H}/actions/create_booking/card", json={"args": {}}, headers=teacher)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "action_off", r.text
    assert r.json()["detail"]["card"]["type"] == "refusal"
    # the admin keeps create_booking (audience "admin" is listed); cancel_my_booking is off for everyone
    names = {a["name"] for a in (await client.get(f"{H}/actions", headers=admin)).json()}
    assert "create_booking" in names and "cancel_my_booking" not in names

    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, uid)
        access = await load_access(s, user)
        assert await hs.audiences_of(s, access) == ["staff"]
        pol = await hs.policy(s, access)
        assert "create_booking" not in pol.actions and "open_feature" in pol.actions
        offered = {t["name"] for t in reg.tools_for(access, ["create_booking"], enabled=pol.actions)}
        assert "create_booking" not in offered and "cancel_my_booking" not in offered
        assert "create_booking" not in reg.permitted_names(access, pol.actions)
    # list rows and nav cards lose the buttons of switched-off actions
    lst = cs.ListCard(
        id=cards.new_id(),
        title=cards.txt("Boş salonlar", "Free rooms"),
        columns=[cs.Column(key="room", label=cards.txt("Salon", "Room"), kind="room")],
        rows=[
            cs.Row(
                id="room:1",
                cells={"room": "A 204"},
                actions=[
                    cs.RowAction(action="create_booking", label=cards.txt("Ayır", "Book"), args={"room": 1}),
                    cs.RowAction(action="room_day_schedule", label=cards.txt("Gün", "Day"), args={"room": "A 204"}),
                ],
            )
        ],
        total=1,
    )
    out = hs.strip_card(lst, {"room_day_schedule"})
    assert [a.action for a in out.rows[0].actions] == ["room_day_schedule"]  # type: ignore[attr-defined]


async def test_hb_15_disabled_and_audience_off_hide_the_helper(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    r = await client.get(f"{H}/status", headers=teacher)
    assert r.json()["enabled"] is True and r.json()["reason"] == "not_routed"
    await client.put(A, json={"audiences": {"staff": False}}, headers=admin)
    body = (await client.get(f"{H}/status", headers=teacher)).json()
    assert body["enabled"] is False and body["reason"] == "audience_off" and body["mode"] == "index"
    assert body["message"]["tr"] and body["message"]["en"]
    assert (await client.get(f"{H}/status", headers=admin)).json()["enabled"] is True
    await client.put(A, json={"audiences": {"staff": True}, "enabled": False}, headers=admin)
    body = (await client.get(f"{H}/status", headers=teacher)).json()
    assert body["enabled"] is False and body["reason"] == "disabled"


async def _person(session) -> User:
    u = User(email="ayse.yilmaz@uni.edu.tr", password_hash=hash_password("parola-1234"), role="TEACHER",
             full_name="Ayşe Yılmaz")  # fmt: skip
    session.add(u)
    await session.commit()
    await kvkk.grant(session, u, "ai_personal")
    await ss.set_value(session, "anthropic_api_key", "sk-ant-test-0000")
    await gw.put_json(session, gw.ROUTES_KEY, {"features": {"helper": {"provider": "anthropic", "model": MODEL}}})
    await session.commit()
    return u


async def test_hb_15_index_mode_makes_no_model_call(session, fake_sdk) -> None:  # noqa: F811
    user = await _person(session)
    access = await load_access(session, user)
    assert (await st.helper_status(session, user.id, turn_available=True))["mode"] == "ai"
    await hs.save(session, {"mode": "index"})
    await session.commit()
    state = await st.helper_status(session, user.id, turn_available=True)
    assert state["mode"] == "index" and state["reason"] == "index_mode" and state["enabled"] is True
    fake_sdk.script = [text("bu yanıt hiç istenmemeli")]
    result = await ht.run_turn(session, access, "şifremi nasıl değiştiririm?", "tr")
    assert result.mode == "index" and result.model_calls == 0 and fake_sdk.calls == []
    assert any(c["type"] == "nav" for c in result.cards)


def test_hb_15_guard_scope_sets_the_off_scope_threshold() -> None:
    assert hs.SCOPES["normal"] == guard.MIN_COVERAGE
    assert hs.SCOPES["strict"] > hs.SCOPES["normal"] > hs.SCOPES["loose"]
    perms = frozenset({"room.view"})
    assert guard.check("şifre değiştir", perms).allowed
    v = guard.check("şifre değiştir", perms, min_coverage=1.01)
    assert not v.allowed and v.code == guard.OUT_OF_SCOPE
    assert hs.min_coverage({**hs.defaults(), "guard": {"scope": "strict"}}) == hs.SCOPES["strict"]


async def test_hb_15_switched_off_action_is_not_a_model_tool(session, fake_sdk) -> None:  # noqa: F811
    user = await _person(session)
    access = await load_access(session, user)
    fake_sdk.script = [text("Boş salonları sayfada görebilirsiniz.")]
    await ht.run_turn(session, access, "yarın boş salon ayırmak istiyorum", "tr")
    first = {t["name"] for t in fake_sdk.calls[0]["tools"]}
    assert "create_booking" in first
    await hs.save(session, {"actions": {"create_booking": {"enabled": False}}})
    await session.commit()
    fake_sdk.calls.clear()
    fake_sdk.script = [text("Boş salonları sayfada görebilirsiniz.")]
    await ht.run_turn(session, access, "yarın boş salon ayırmak istiyorum", "tr")
    offered = {t["name"] for t in fake_sdk.calls[0]["tools"]}
    assert "create_booking" not in offered and "open_feature" in offered


async def test_hb_15_notes_used_under_the_answer(session, fake_sdk) -> None:  # noqa: F811
    from app.ai.helper import memory

    user = await _person(session)
    access = await load_access(session, user)
    await memory.add_note(session, user, "Derslerim B blokta.", "user_button")
    await memory.add_note(session, user, "Sabah saatlerini severim.", "user_button")
    await session.commit()
    fake_sdk.script = [text("B blokta yarın 10:10 için boş bir salon var.")]
    result = await ht.run_turn(session, access, "yarın boş salon var mı?", "tr")
    answer = next(c for c in result.cards if c["type"] == "answer")
    assert answer["source"] == "ai" and answer["notes_used"] == ["Derslerim B blokta."]
    cs.validate_card(answer)
    # an answer that draws on no note carries no field (older clients see the same card as before)
    fake_sdk.script = [text("Yarın 10:10 için boş bir salon var.")]
    result = await ht.run_turn(session, access, "yarın boş salon var mı?", "tr")
    assert "notes_used" not in next(c for c in result.cards if c["type"] == "answer")
    assert memory.notes_in_answer(["Derslerim B blokta."], "Bir şey yok.") == []
