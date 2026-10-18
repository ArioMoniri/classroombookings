"""HB-17 local-model bench fixes (docs/testing/hb-17-local-bench-2026-10-18.md), helper side, on the real Bahar 2026
data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00; A 102 is free at P1 on Thursday 19 Feb).

* bug 1: ``search_site`` answered 500 for a page with a dotted feature id (``feature:profile.calendar``);
* bug 5: a turn that fails logs where (file, line, function; never the prompt) and is counted in HB-14 telemetry
  with ``outcome: error``;
* P1: ``create_booking`` takes a clock time (``start``) and the server resolves the booking period the way
  find-room does; ``period_id`` is still accepted and the confirm card names the resolved period;
* P2: an answer that drifts out of Latin + Turkish letters is replaced by the index answer; markdown images are
  stripped from answers.
"""

from __future__ import annotations

import logging
from datetime import date

from app.ai.helper import cards, guard, schema, telemetry
from app.ai.helper.actions import registry as reg
from app.core import db as dbmod
from app.core import rls
from app.models import Booking
from app.models.helper import HelperEvent
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, card, personas

THU = date(2026, 2, 19)


# ------------------------------------------------------------------------------------------------ bug 1


def test_row_id_allows_a_dotted_feature_id() -> None:
    row = schema.Row(id="feature:profile.calendar", cells={"title": "Takvim"})
    assert row.id == "feature:profile.calendar"


async def test_search_site_with_dotted_feature_ids_is_200(env) -> None:  # noqa: F811
    t = (await personas(env))["teacher"]
    # both answered 500 before: every Profil page id is dotted (takvim → profile.calendar, şifre → profile.password)
    for q, feature in (("takvim", "profile.calendar"), ("şifre", "profile.password")):
        r = await card(env, t, "search_site", q=q)
        assert r.status_code == 200, (q, r.text)
        c = schema.validate_card(r.json())
        ids = [row.id for row in c.rows]  # type: ignore[attr-defined]
        assert f"feature:{feature}" in ids, (q, ids)
    r = await env.client.get(f"{H}/schema", headers=t.headers)
    assert r.status_code == 200
    row_def = r.json()["card"]["$defs"]["Row"]["properties"]["id"]
    assert "." in row_def["pattern"]


# ------------------------------------------------------------------------------------------------ P1


async def test_create_booking_by_clock_time_resolves_the_period(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t = people["teacher"]
    by_time = (await card(env, t, "create_booking", room="A 102", date=THU.isoformat(), start="08:30")).json()
    assert by_time["type"] == "confirm", by_time
    assert by_time["args"]["period_id"] == env.periods["P1"]
    assert by_time["args"]["start"] == ""  # the resolved period is what the button books
    by_id = (
        await card(env, t, "create_booking", room="A 102", date=THU.isoformat(), period_id=env.periods["P1"])
    ).json()
    assert by_id["type"] == "confirm" and by_id["args"]["period_id"] == env.periods["P1"]
    when = lambda c: next(x["value"]["tr"] for x in c["preview"] if x["label"]["en"] == "When")  # noqa: E731
    assert when(by_time) == when(by_id) and "19.02.2026" in when(by_time)
    assert by_time["button"] == by_id["button"]
    # the button books exactly that period
    r = await env.client.post(f"{H}/actions/confirm", json={"token": by_time["token"]}, headers=t.headers)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        b = (await s.execute(select(Booking).where(Booking.user_id == t.uid))).scalars().one()
    assert b.period_id == env.periods["P1"] and b.date == THU


async def test_create_booking_clock_time_outside_the_day_is_refused_and_missing_time_asks(env) -> None:  # noqa: F811
    reg.RATE.reset()
    t = (await personas(env))["teacher"]
    r = await card(env, t, "create_booking", room="A 102", date=THU.isoformat(), start="23:30")
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["code"] == "time_outside_grid" and "23:30" in d["message_tr"] and d["card"]["type"] == "error"
    form = (await card(env, t, "create_booking", room="A 102", date=THU.isoformat())).json()
    assert form["type"] == "form" and "start" in form["missing"]
    assert [f["name"] for f in form["fields"]][:3] == ["room", "date", "start"]


def test_create_booking_strict_schema_takes_start_and_refuses_ranges() -> None:
    a = reg.get("create_booking")
    assert a is not None
    props = reg.tool(a)["input_schema"]["properties"]
    assert set(props) == {"room", "date", "start", "period_id", "notes"}
    assert "HH:MM" in props["start"]["description"]
    ok = reg.parse_args(a, {"room": "B 406", "date": "2026-02-19", "start": "13:30", "period_id": 0, "notes": ""})
    assert ok.start == "13:30"  # type: ignore[attr-defined]
    for bad in ("08:00-22:00", ["08:30", "09:30"], "her saat"):
        try:
            reg.parse_args(a, {"room": "B 406", "date": "2026-02-19", "start": bad, "period_id": 0, "notes": ""})
        except reg.ArgsInvalid:
            continue
        raise AssertionError(f"start={bad!r} was accepted")


# ------------------------------------------------------------------------------------------------ P2

CJK_DRIFT = (
    "Boş derslikler için Oda bul sayfasını kullanabilirsiniz. 然后您可以在列表中选择一个房间并点击预订按钮完成预订。"
)


def test_answer_drifting_out_of_latin_and_turkish_is_not_grounded() -> None:
    assert guard.script_share(CJK_DRIFT) > 0.05
    assert guard.ground_answer(CJK_DRIFT, ["find_room"]) is False
    turkish = "Kâğıt, şifre, ılık, İzmir, çiçek, öğüt, ünlü, şaşkın, îmâ, ûlâ: hepsi Türkçe harfler."
    assert guard.script_share(turkish) == 0.0
    plain = "Bunu kendi hesabınızdan kolayca yapabilir, sonra da sonucu kontrol edebilirsiniz."
    assert guard.ground_answer(plain, []) is True
    # one stray letter in a long Turkish answer is not a drift
    assert guard.ground_answer(plain + " 好", []) is True
    # Vietnamese-style drift (Latin letters with marks Turkish does not use) counts too
    assert guard.script_share("Bạn có thể đặt phòng ở trang này được không ạ") > 0.05


def test_markdown_images_are_stripped_from_answers() -> None:
    a = cards.answer("Bakın: ![harita](https://evil.example/x.png) ve ![](data:image/png;base64,AAAA) burada.", "tr")
    assert "![" not in a.text and "harita](" not in a.text and "evil" not in a.text and "data:image" not in a.text
    assert a.text.startswith("Bakın:") and a.text.rstrip().endswith("burada.")


# ------------------------------------------------------------------------------------------------ bug 5


async def test_a_failed_turn_logs_where_and_is_recorded_as_error(env, monkeypatch, caplog) -> None:  # noqa: F811
    t = (await personas(env))["teacher"]
    secret = "gizli soru metni 4815162342"

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"echo of {secret}")

    monkeypatch.setattr(guard, "check", boom)
    telemetry.RATE.reset()
    with caplog.at_level(logging.WARNING, logger="app.api.v1.helper_turn"):
        r = await env.client.post(f"{H}/turn", json={"text": secret, "lang": "tr"}, headers=t.headers)
    assert r.status_code == 200 and "event: error" in r.text
    [rec] = [x for x in caplog.records if x.name == "app.api.v1.helper_turn"]
    line = rec.getMessage()
    assert "RuntimeError" in line and "test_hb_17_bench_fixes.py:" in line and "boom" in line, line
    assert secret not in line and "4815162342" not in line and "echo of" not in line
    async with dbmod.get_session_factory()() as s:
        async with rls.system_scope(s):
            rows = list((await s.execute(select(HelperEvent).where(HelperEvent.kind == "query"))).scalars())
    [row] = rows
    assert row.outcome == "error" and row.user_id == t.uid and row.reason == "runtimeerror"
    assert secret not in str(row.query or "")
    assert "error" in telemetry.OUTCOMES
