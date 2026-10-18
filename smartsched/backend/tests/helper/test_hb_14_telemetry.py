"""HB-14 helper telemetry and feedback (architecture doc §2.7, §5.7; KVKK: aggregates only).

* ``POST /helper/feedback``: thumbs plus a reason, the person's own note only when the institution allows notes, one
  answer per person and turn, validated ids, a per-person rate limit;
* ``POST /helper/events``: the client's ``nav_click`` / ``form_open`` / ``cancel`` with index ids and action names;
* :func:`telemetry.record_turn` (called by HB-B's ``POST /helper/turn``): one ``query`` row per turn, the three
  Prometheus series move, no prompt text is stored, an index miss keeps only the folded words;
* ``GET /ai/admin/helper/summary``: matches seeded events, k-anonymity (≥ 5 people) on the unanswered queries, no
  ids or notes, four sentence tiles in TR and EN, admins only; on PostgreSQL it reads everyone's rows through
  ``rls.system_scope`` (RLS keeps the rows owner-only otherwise);
* KVKK: the DSR export lists the person's feedback, the erasure and the 90-day purge remove the notes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from app.ai import helper_turn as ht
from app.ai.helper import memory, telemetry
from app.core import db as dbmod
from app.core import rls
from app.core.security import hash_password
from app.models import User
from app.models.base import utcnow
from app.models.helper import HelperEvent
from app.services.bookings_perms import load_access
from prometheus_client import REGISTRY
from sqlalchemy import select, text

from tests.api_fixtures import client, login  # noqa: F401
from tests.crbs_support import make_user
from tests.pg_support import pg_server, pg_url  # noqa: F401

A = "/api/v1/ai/admin/helper"
H = "/api/v1/helper"
TURN = "0123456789abcdef"


@pytest.fixture(autouse=True)
def _reset():
    telemetry.RATE.reset()
    yield
    telemetry.RATE.reset()


async def _events(**where) -> list[HelperEvent]:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        async with rls.system_scope(s):
            q = select(HelperEvent).order_by(HelperEvent.id)
            for k, v in where.items():
                q = q.where(getattr(HelperEvent, k) == v)
            return list((await s.execute(q)).scalars())


def _metric(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


# ------------------------------------------------------------------------------------------------ feedback


async def test_hb_14_feedback_thumbs_reason_note(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    post = client.post
    r = await post(f"{H}/feedback", json={"turn_id": TURN, "thumb": "up"}, headers=teacher)
    assert r.status_code == 200 and r.json() == {"saved": True, "note_saved": False}, r.text
    # a second answer for the same turn replaces the first (one per person and turn)
    r = await post(
        f"{H}/feedback",
        json={"turn_id": TURN, "thumb": "down", "reason": "wrong_page", "note": "Beni takvime götürdü"},
        headers=teacher,
    )
    assert r.status_code == 200 and r.json() == {"saved": True, "note_saved": True}
    rows = await _events(turn_id=TURN)
    assert [(e.kind, e.reason, e.note, e.user_id) for e in rows] == [
        ("thumb_down", "wrong_page", "Beni takvime götürdü", uid)
    ]
    # a reason or note on a thumbs-up is not kept
    r = await post(
        f"{H}/feedback", json={"turn_id": "fedcba9876543210", "thumb": "up", "reason": "too_slow", "note": "x"},
        headers=teacher,
    )  # fmt: skip
    assert r.json()["note_saved"] is False
    up = (await _events(turn_id="fedcba9876543210"))[0]
    assert up.reason is None and up.note is None
    # validation: id shape, reason list, note length
    for body in (
        {"turn_id": "../etc", "thumb": "up"},
        {"turn_id": TURN, "thumb": "meh"},
        {"turn_id": TURN, "thumb": "down", "reason": "angry"},
        {"turn_id": TURN, "thumb": "down", "note": "x" * 301},
    ):
        assert (await post(f"{H}/feedback", json=body, headers=teacher)).status_code == 422, body
    # the institution switched notes off: the thumb counts, the note is dropped
    await client.put(A, json={"feedback_notes": False}, headers=admin)
    r = await post(
        f"{H}/feedback", json={"turn_id": "aaaaaaaaaaaaaaaa", "thumb": "down", "note": "yavaştı"}, headers=teacher
    )
    assert r.json() == {"saved": True, "note_saved": False}
    assert (await _events(turn_id="aaaaaaaaaaaaaaaa"))[0].note is None
    # per-person rate limit
    for i in range(telemetry.RATE_PER_MINUTE):
        await post(f"{H}/feedback", json={"turn_id": f"{i:016x}", "thumb": "up"}, headers=teacher)
    r = await post(f"{H}/feedback", json={"turn_id": "bbbbbbbbbbbbbbbb", "thumb": "up"}, headers=teacher)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


async def test_hb_14_client_events(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    ok = [
        {"kind": "nav_click", "turn_id": TURN, "feature_id": "profile.password"},
        {"kind": "form_open", "action": "create_booking"},
        {"kind": "cancel", "turn_id": TURN, "action": "create_booking"},
    ]
    for body in ok:
        r = await client.post(f"{H}/events", json=body, headers=teacher)
        assert r.status_code == 204, (body, r.text)
    rows = await _events(user_id=uid)
    assert [(e.kind, e.feature_id, e.action) for e in rows] == [
        ("nav_click", "profile.password", None),
        ("form_open", None, "create_booking"),
        ("cancel", None, "create_booking"),
    ]
    for body, code in (
        ({"kind": "nav_click", "feature_id": "no.such.page"}, "unknown_feature"),
        ({"kind": "cancel", "action": "drop_tables"}, "unknown_action"),
    ):
        r = await client.post(f"{H}/events", json=body, headers=teacher)
        assert r.status_code == 422 and r.json()["detail"]["code"] == code
    # the server records query / preview / confirm itself: the client cannot
    assert (await client.post(f"{H}/events", json={"kind": "confirm"}, headers=teacher)).status_code == 422


# ------------------------------------------------------------------------------------------------ turns


async def test_hb_14_record_turn_moves_counters_and_stores_no_prompt(session) -> None:
    u = User(email="ayse.yilmaz@uni.edu.tr", password_hash=hash_password("parola-1234"), role="TEACHER",
             full_name="Ayşe Yılmaz")  # fmt: skip
    session.add(u)
    await session.commit()
    access = await load_access(session, u)
    before = _metric("smartsched_helper_turns_total", mode="index", outcome="index")
    lat_before = _metric("smartsched_helper_latency_seconds_count", mode="index")
    question = "şifremi nasıl değiştiririm?"
    result = await ht.run_turn(session, access, question, "tr")
    assert result.mode == "index"
    await telemetry.record_turn(session, access, question, result, latency_s=0.04)
    await session.commit()
    assert _metric("smartsched_helper_turns_total", mode="index", outcome="index") == before + 1
    assert _metric("smartsched_helper_latency_seconds_count", mode="index") == lat_before + 1
    rows = await _events(kind="query")
    assert len(rows) == 1
    e = rows[0]
    assert (e.turn_id, e.mode, e.outcome, e.latency_ms, e.user_id) == (result.turn_id, "index", "index", 40, u.id)
    assert e.feature_id and e.feature_id.startswith("profile") and e.query is None  # a hit: nothing typed is kept
    # a miss keeps only the folded words, never digits or an address
    miss = "Kantin fiyatları 12 Şubat ali@uni.edu.tr"
    result = await ht.run_turn(session, access, miss, "tr")
    await telemetry.record_turn(session, access, miss, result, latency_s=0.01)
    await session.commit()
    rows = await _events(kind="query")
    assert len(rows) == 2 and rows[1].query == "kantin fiyatlari subat", rows[1].query
    for row in rows:
        for col in HelperEvent.__table__.columns:
            value = getattr(row, col.name)
            assert not (isinstance(value, str) and ("şifremi" in value or "@" in value)), col.name
    # a write preview counts per action
    p0 = _metric("smartsched_helper_actions_total", action="create_booking", stage="preview", outcome="ok")
    telemetry.observe_action("create_booking", "preview", "ok")
    assert _metric("smartsched_helper_actions_total", action="create_booking", stage="preview", outcome="ok") == p0 + 1


async def test_hb_14_search_final_records_one_query(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    assert (await client.get(f"{H}/search", params={"q": "şifre"}, headers=teacher)).status_code == 200
    assert await _events(kind="query") == []  # keystrokes are not counted
    r = await client.get(f"{H}/search", params={"q": "şifre", "final": "true"}, headers=teacher)
    assert r.status_code == 200
    r = await client.get(f"{H}/search", params={"q": "kantin fiyatları", "final": "true"}, headers=teacher)
    rows = await _events(kind="query")
    assert [(e.mode, e.user_id) for e in rows] == [("index", uid), ("index", uid)]
    assert rows[0].query is None and rows[0].feature_id
    assert rows[1].query == "kantin fiyatlari" and rows[1].feature_id is None


# ------------------------------------------------------------------------------------------------ summary


async def _seed(session, users: list[int]) -> None:
    now = utcnow()
    ev = []
    # 10 turns: 6 index (2 misses), 3 ai answered, 1 fallback
    for i in range(6):
        ev.append(HelperEvent(ts=now, user_id=users[i % len(users)], turn_id=f"{i:016x}", kind="query",
                              mode="index", outcome="index", latency_ms=40 + i))  # fmt: skip
    for i in range(3):
        ev.append(HelperEvent(ts=now, user_id=users[0], turn_id=f"a{i:015x}", kind="query", mode="ai",
                              outcome="answered", latency_ms=2000 + 1000 * i, provider="anthropic",
                              model="claude-opus-5-5"))  # fmt: skip
    ev.append(HelperEvent(ts=now, user_id=users[1], turn_id="f" * 16, kind="query", mode="index",
                          outcome="fallback", reason="rate_limited", latency_ms=300))  # fmt: skip
    # unanswered queries: one typed by 5 people (shown), one by 4 (hidden)
    for uid in users[:5]:
        ev.append(HelperEvent(ts=now, user_id=uid, kind="query", mode="index", outcome="index", latency_ms=30,
                              query="yemekhane menusu"))  # fmt: skip
    for uid in users[:4]:
        ev.append(HelperEvent(ts=now, user_id=uid, kind="query", mode="index", outcome="index", latency_ms=30,
                              query="ayse hocanin odasi"))  # fmt: skip
    ev += [HelperEvent(ts=now, user_id=users[0], kind="nav_click", feature_id="profile.password") for _ in range(7)]
    ev += [
        HelperEvent(ts=now, user_id=users[0], kind="preview", action="create_booking", outcome="ok"),
        HelperEvent(ts=now, user_id=users[0], kind="preview", action="create_booking", outcome="ok"),
        HelperEvent(ts=now, user_id=users[0], kind="confirm", action="create_booking", outcome="ok"),
        HelperEvent(ts=now, user_id=users[0], kind="confirm", action="create_booking", outcome="conflict"),
        HelperEvent(ts=now, user_id=users[0], kind="undo", action="create_booking", outcome="ok"),
        HelperEvent(ts=now, user_id=users[1], kind="thumb_up", turn_id="a" + "0" * 15),
        HelperEvent(ts=now, user_id=users[2], kind="thumb_up", turn_id="b" + "0" * 15),
        HelperEvent(ts=now, user_id=users[3], kind="thumb_down", turn_id="c" + "0" * 15, reason="wrong_page",
                    note="Ayşe Hoca'nın odası yanlış"),  # fmt: skip
        # outside the window: not counted
        HelperEvent(ts=now - timedelta(days=20), user_id=users[0], kind="query", mode="ai", outcome="answered"),
    ]
    async with rls.system_scope(session):
        session.add_all(ev)
        await session.commit()


def _check_summary(body: dict) -> None:  # type: ignore[type-arg]
    assert body["days"] == 7 and body["k_min"] == 5
    t = body["turns"]
    assert t["total"] == 19 and t["ai"] == 3 and t["index"] == 16
    assert t["by_outcome"]["index"] == 15 and t["by_outcome"]["answered"] == 3 and t["by_outcome"]["fallback"] == 1
    assert body["fallback"] == {"count": 1, "share": 0.25, "by_reason": [{"reason": "rate_limited", "count": 1}]}
    assert body["deflection"] == {"queries": 19, "nav_clicks": 7, "share": round(7 / 19, 2)}
    assert body["actions"] == [
        {"action": "create_booking", "preview": 2, "confirm": 1, "undo": 1, "form_open": 0, "cancel": 0, "failed": 1}
    ]
    th = body["thumbs"]
    assert (th["up"], th["down"], th["share_up"], th["reasons"], th["notes"]) == (
        2, 1, 0.67, {"wrong_page": 1}, 1)  # fmt: skip
    assert body["latency_ms"]["ai"] == {"p50": 3000, "p95": 4000, "n": 3}
    assert body["latency_ms"]["index"]["n"] == 16
    assert body["misses"] == [{"query": "yemekhane menusu", "users": 5, "count": 5}]
    tiles = body["tiles"]
    assert [x["id"] for x in tiles] == ["questions", "modes", "actions", "thumbs"]
    assert all(x["tr"] and x["en"] for x in tiles)
    assert tiles[0]["tr"].startswith("Son 7 günde 19 soru")
    flat = repr(body)
    # aggregates only: no note text, no ids, no person
    assert "odası yanlış" not in flat and "ayse hocanin" not in flat and "user_id" not in flat and "turn_id" not in flat


async def test_hb_14_summary_matches_seeded_events(client) -> None:  # noqa: F811
    admin = await login(client)
    ids, heads = [], []
    for i in range(5):
        uid, h = await make_user(client, admin, f"kisi{i}@uni.edu.tr")
        ids.append(uid)
        heads.append(h)
    assert (await client.get(f"{A}/summary", headers=heads[0])).status_code == 403
    async with dbmod.get_session_factory()() as s:
        await _seed(s, ids)
    r = await client.get(f"{A}/summary", params={"days": 7}, headers=admin)
    assert r.status_code == 200, r.text
    _check_summary(r.json())
    assert r.json()["cost"] == [] or all("feature" in c and "label" in c for c in r.json()["cost"])
    assert (await client.get(f"{A}/summary", params={"days": 91}, headers=admin)).status_code == 422
    # an empty window: shares are null, the tiles still read as sentences
    async with dbmod.get_session_factory()() as s:
        empty = await telemetry.summary(s, days=1, now=utcnow() + timedelta(days=30))
    assert empty["deflection"]["share"] is None and empty["thumbs"]["share_up"] is None
    assert all(x["tr"] and x["en"] for x in empty["tiles"])


@pytest.fixture
async def pg(pg_url) -> AsyncIterator[str]:  # noqa: F811
    dbmod.configure_engine(pg_url)
    yield pg_url
    await dbmod.dispose_engine()


async def test_hb_14_summary_on_postgres_reads_through_system_scope(pg) -> None:  # type: ignore[no-untyped-def]
    from tests.test_w3_sec_rls_postgres import _as, _seed_people

    people = await _seed_people()
    async with dbmod.get_session_factory()() as s:
        for i in range(3):
            u = User(email=f"kisi{i}@uni.edu.tr", password_hash="x", role="TEACHER")
            s.add(u)
        await s.commit()
        extra = [x.id for x in (await s.execute(select(User).where(User.email.like("kisi%")))).scalars()]
    users = [people["a"], people["b"], *extra]
    async with dbmod.get_session_factory()() as s:
        await _seed(s, users)
    s = await _as(people["admin"])
    try:
        # RLS: the admin's own context sees none of the others' rows ...
        assert (await s.execute(text("select count(*) from helper_events"))).scalar_one() == 0
        # ... the summary reads them as an aggregate in the system scope
        _check_summary(await telemetry.summary(s, days=7))
        assert (await s.execute(text("select count(*) from helper_events"))).scalar_one() == 0
    finally:
        await s.close()


# ------------------------------------------------------------------------------------------------ KVKK


async def test_hb_14_feedback_in_dsr_export_erasure_and_purge(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    await client.post(
        f"{H}/feedback", json={"turn_id": TURN, "thumb": "down", "reason": "other", "note": "Kısa yanıt"},
        headers=teacher,
    )  # fmt: skip
    async with dbmod.get_session_factory()() as s:
        rows = [r for r in await memory.dsr_rows(s, uid) if r["kind"] == "feedback"]
        assert len(rows) == 1 and rows[0]["thumb"] == "down" and rows[0]["note"] == "Kısa yanıt"
        assert rows[0]["reason"] == "other"
        # the 90-day purge drops the person and the note
        await memory.purge(s, now=utcnow() + timedelta(days=91))
        await s.commit()
    e = (await _events(turn_id=TURN))[0]
    assert e.user_id is None and e.note is None and e.reason == "other"
    await client.post(f"{H}/feedback", json={"turn_id": "1" * 16, "thumb": "down", "note": "ikinci"}, headers=teacher)
    async with dbmod.get_session_factory()() as s:
        await memory.erase(s, uid)
        await s.commit()
    e = (await _events(turn_id="1" * 16))[0]
    assert e.user_id is None and e.note is None


async def test_hb_14_turn_route_records_one_query(client) -> None:  # noqa: F811
    admin = await login(client)
    uid, teacher = await make_user(client, admin, "ayse.yilmaz@uni.edu.tr")
    r = await client.post(f"{H}/turn", json={"text": "şifremi nasıl değiştiririm?"}, headers=teacher)
    assert r.status_code == 200 and "run_finished" in r.text
    rows = await _events(kind="query")
    assert [(e.user_id, e.mode, e.outcome) for e in rows] == [(uid, "index", "index")]
    assert rows[0].turn_id and rows[0].turn_id in r.text and rows[0].latency_ms is not None
