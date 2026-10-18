"""FIX-D / HB18-F01 (docs/testing/round4/2026-10-18-hb18.md): every time the helper API sends is aware UTC with a
"Z". A naive ISO string ("2026-10-18T13:11:22") is read as *local* time by the browser's ``Date.parse``, so in
Europe/Istanbul (UTC+3) every confirm card was born expired and "Geri al" vanished up to 3 h early.

Covers ``ConfirmCard.expires_at``, ``ResultCard.undo_expires_at``, ``GET /helper/actions/recent`` (``at``,
``undo_expires_at``) and the notes list (``created_at``, ``last_used_at``, ``expires_at``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ai.helper import cards, schema
from app.ai.helper.actions import registry as reg

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, card, personas
from tests.helper.test_hb_05_writes import THU
from tests.helper.test_hb_d_asks import _consent


def _aware_utc(text: str) -> datetime:
    assert isinstance(text, str) and text.endswith("Z"), f"not aware UTC: {text!r}"
    dt = datetime.fromisoformat(text)
    assert dt.utcoffset() == timedelta(0), text
    return dt


def test_schema_datetimes_serialize_as_utc_with_z() -> None:
    base = {
        "id": "b" * 16,
        "action": "create_booking",
        "risk": "R1",
        "token": "abc.def",
        "preview": [],
        "button": {"tr": "Rezerve et", "en": "Book"},
        "undoable": True,
    }
    naive = schema.ConfirmCard.model_validate({**base, "expires_at": datetime(2026, 10, 18, 13, 11, 22)})
    assert cards.dump(naive)["expires_at"] == "2026-10-18T13:11:22Z"
    aware = schema.ConfirmCard.model_validate({**base, "expires_at": "2026-10-18T16:11:22+03:00"})
    assert cards.dump(aware)["expires_at"] == "2026-10-18T13:11:22Z"
    res = schema.ResultCard.model_validate(
        {
            "id": "c" * 16,
            "action": "create_booking",
            "ok": True,
            "message": {"tr": "Tamam", "en": "Done"},
            "undo_token": "abc.def",
            "undo_expires_at": datetime(2026, 10, 19, 7, 10),
        }
    )
    assert cards.dump(res)["undo_expires_at"] == "2026-10-19T07:10:00Z"
    # the wire contract (snapshot) still says a date-time string
    sch = schema.card_json_schema()["$defs"]
    assert sch["ConfirmCard"]["properties"]["expires_at"]["format"] == "date-time"


async def test_helper_api_times_are_aware_utc(env) -> None:  # noqa: F811
    reg.RATE.reset()
    t = (await personas(env))["teacher"]
    now = datetime.now(UTC)
    r = await card(env, t, "create_booking", room="A102", date=THU.isoformat(), period_id=env.periods["P1"])
    assert r.status_code == 200 and r.json()["type"] == "confirm", r.text
    exp = _aware_utc(r.json()["expires_at"])
    assert now < exp <= now + timedelta(minutes=11), (now, exp)

    done = await env.client.post(f"{H}/actions/confirm", json={"token": r.json()["token"]}, headers=t.headers)
    assert done.status_code == 200, done.text
    if done.json().get("undo_expires_at"):
        _aware_utc(done.json()["undo_expires_at"])

    rows = (await env.client.get(f"{H}/actions/recent", headers=t.headers)).json()
    assert rows, rows
    for row in rows:
        at = _aware_utc(row["at"])
        assert abs(at - now) < timedelta(minutes=5), (at, now)
        if row.get("undo_expires_at"):
            _aware_utc(row["undo_expires_at"])

    await _consent(t.uid)
    n = await env.client.post(f"{H}/notes", json={"text": "Pazartesi B blok", "source": "user_confirmed"}, headers=t.headers)
    assert n.status_code == 201, n.text
    notes = (await env.client.get(f"{H}/notes", headers=t.headers)).json()
    items = notes["notes"] if isinstance(notes, dict) else notes
    assert items, notes
    for x in items:
        for k in ("created_at", "last_used_at", "expires_at"):
            _aware_utc(x[k])
