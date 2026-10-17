"""Wave-3 integration follow-up: the person whose own AI limit crosses the threshold gets their own notice through
``notify_dispatch.dispatch`` (their per-event switches apply), while the administrators' budget alerts keep the
always-on path (``ai_usage._deliver``: a switched-off preference never silences them)."""

from __future__ import annotations

from app.ai import gateway as gw
from app.models import InAppNotification
from app.services import ai_usage as meter
from app.services import notify_dispatch as nd
from sqlalchemy import select

from tests.ai.test_w3_ai_gateway import _user


async def _bell(session, uid: int) -> list[InAppNotification]:
    q = select(InAppNotification).where(InAppNotification.user_id == uid).execution_options(populate_existing=True)
    return list((await session.execute(q)).scalars())


async def _setup(session, tag: str):
    meter.reset_state()
    admin = await _user(session, f"yonetici-{tag}@uni.edu.tr", role="ADMIN")
    u = await _user(session, f"planlamaci-{tag}@uni.edu.tr")
    await gw.put_json(session, gw.LIMITS_KEY, {"user_daily_tokens": 100, "soft_pct": 80})
    await session.commit()
    await meter.record(user_id=u.id, feature="chat", provider="anthropic", model="m", input_tokens=85, outcome="ok")
    return admin.id, u.id


async def test_the_user_gets_their_own_notice_through_the_dispatcher(session):
    admin_id, uid = await _setup(session, "a")
    assert await meter.check_alerts(uid)
    mine = await _bell(session, uid)
    assert [n.kind for n in mine] == ["ai.usage_alert"]
    assert "sınırınızın" in mine[0].title and mine[0].link == "/profile"
    assert [n.kind for n in await _bell(session, admin_id)] == ["ai.usage_alert"]
    # once per period and threshold, for both
    await meter.check_alerts(uid)
    assert len(await _bell(session, uid)) == 1 and len(await _bell(session, admin_id)) == 1


async def test_a_switched_off_preference_silences_only_the_user_never_the_admins(session):
    admin_id, uid = await _setup(session, "b")
    for who in (uid, admin_id):
        await nd.update_preferences(session, who, events_in={"ai.usage_alert": {"in_app": False, "email": False}})
    await session.commit()
    assert await meter.check_alerts(uid)
    assert await _bell(session, uid) == []
    assert [n.kind for n in await _bell(session, admin_id)] == ["ai.usage_alert"]
