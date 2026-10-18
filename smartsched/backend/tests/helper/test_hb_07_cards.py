"""HB-07 card contract ``helper.card.v1`` (docs/design/v3/helper.md §4.1, §4.2, §17 asks A1–A8).

* the JSON Schema matches its snapshot (``fixtures/helper_card_v1.schema.json``; the client's zod is generated from
  the same file); refresh with ``UPDATE_HELPER_SNAPSHOT=1`` after a deliberate change and tell HX-01;
* no string field can carry a URL or HTML: every string in the schema is a plain-text pattern, an identifier
  pattern, an enum or a date-time, and database / model text is neutralised, never a 500;
* every person-facing text has its Turkish and English twin;
* ``choice`` (A2) has 2–5 options and its pick round-trips to the action's card;
* the card endpoint answers with no model call (A4), ``result`` has ≤ 2 follow-ups (A7), ``list`` shows ≤ 5 rows (A8);
* ``GET /helper/status`` (A6) is index-only until an admin routes the helper (owner default).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from app.ai import gateway as gw
from app.ai.helper import cards, schema
from app.ai.helper import status as helper_status
from app.ai.helper.actions import registry as reg
from app.core import db as dbmod
from app.main import app
from pydantic import ValidationError

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, card, personas

SNAPSHOT = Path(__file__).parent / "fixtures" / "helper_card_v1.schema.json"
THU = date(2026, 2, 19)
BAD = ["https://evil.example/x", "<b>kalın</b>", "www.evil.example", "javascript:alert(1)", "data:text/html,x"]


def _strings(node: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if node.get("type") == "string":
            out.append((path, node))
        for k, v in node.items():
            out += _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _strings(v, f"{path}[{i}]")
    return out


def _txts(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        here = [node] if set(node) == {"tr", "en"} else []
        return here + [t for v in node.values() for t in _txts(v)]
    if isinstance(node, list):
        return [t for v in node for t in _txts(v)]
    return []


def test_hb_07_schema_snapshot() -> None:
    current = schema.card_json_schema()
    text = json.dumps(current, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_HELPER_SNAPSHOT") == "1" or not SNAPSHOT.exists():
        SNAPSHOT.write_text(text, encoding="utf-8")
    assert SNAPSHOT.read_text(encoding="utf-8") == text, "helper.card.v1 changed: refresh the snapshot, tell HX-01"
    assert current["$id"] == "helper.card.v1"
    kinds = sorted(
        m["properties"]["type"]["const"]
        for m in current["$defs"].values()
        if "type" in m.get("properties", {}) and "const" in m["properties"]["type"]
    )
    assert sorted(schema.CARD_TYPES) == kinds and "choice" in kinds


def test_hb_07_no_string_field_can_carry_a_url_or_html() -> None:
    sch = schema.card_json_schema()
    loose = [
        p for p, n in _strings(sch) if not ({"pattern", "const", "enum"} & set(n) or n.get("format") == "date-time")
    ]
    assert loose == [], f"unconstrained string fields: {loose}"
    plain = re.compile(schema.PLAIN_PATTERN)
    for bad in BAD:
        assert not plain.match(bad), bad
        with pytest.raises(ValidationError):
            schema.Txt(tr=bad, en="x")
        with pytest.raises(ValidationError):
            schema.validate_card({"type": "answer", "id": "a" * 16, "text": bad, "lang": "tr", "source": "ai"})
    assert plain.match("A 204 · 18.02.2026 10:10–10:50") and plain.match("Ş ğ ü İ ı ö ç")
    # database / model text is neutralised (never a 500): a note with a link and markup in a confirm card's args
    c = schema.ConfirmCard.model_validate(
        {
            "id": "b" * 16,
            "action": "create_booking",
            "risk": "R1",
            "token": "abc.def",
            "expires_at": "2026-02-16T08:10:00",
            "preview": [],
            "button": {"tr": "Rezerve et", "en": "Book"},
            "undoable": True,
            "args": {"notes": "bkz https://evil.example <b>x</b>", "period_id": 3},
        }
    )
    assert "://" not in str(c.args["notes"]) and "<" not in str(c.args["notes"])
    assert cards.clean("<script>x</script> www.evil.example") == "‹script›x‹/script› [bağlantı]"


def test_hb_07_every_text_has_both_languages_and_bounds_hold() -> None:
    sch = schema.card_json_schema()
    assert sorted(sch["$defs"]["Txt"]["required"]) == ["en", "tr"]
    opt = {"label": {"tr": "A", "en": "A"}}
    base = {"id": "c" * 16, "arg": "room", "question": {"tr": "Hangi salon?", "en": "Which room?"}}
    with pytest.raises(ValidationError):
        schema.ChoiceCard.model_validate({**base, "options": [{**opt, "value": 1}]})
    with pytest.raises(ValidationError):
        schema.ChoiceCard.model_validate({**base, "options": [{**opt, "value": i} for i in range(6)]})
    schema.ChoiceCard.model_validate({**base, "options": [{**opt, "value": i} for i in range(2)]})
    fu = {"label": {"tr": "Aç", "en": "Open"}, "feature_id": "my_bookings"}
    with pytest.raises(ValidationError):  # A7
        schema.ResultCard.model_validate(
            {
                "id": "d" * 16,
                "action": "create_booking",
                "ok": True,
                "message": {"tr": "Tamam", "en": "Done"},
                "follow_ups": [fu, fu, fu],
            }
        )
    assert cards.LIST_ROWS == 5  # A8


async def test_hb_07_cards_without_a_model_choice_round_trip_and_list_rows(env, monkeypatch) -> None:  # noqa: F811
    reg.RATE.reset()

    def no_model(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("the card endpoint must not call a model (A4)")

    import anthropic.resources.messages as sdk_messages

    monkeypatch.setattr(sdk_messages.AsyncMessages, "create", no_model)
    monkeypatch.setattr(sdk_messages.Messages, "create", no_model)
    monkeypatch.setattr(gw, "resolve_route", no_model)
    people = await personas(env)
    t = people["teacher"]
    seen: list[dict[str, Any]] = []

    # A2: an ambiguous room asks with a choice card; the pick goes back to the same action's card
    r = await card(env, t, "create_booking", room="A 1", date=THU.isoformat(), period_id=env.periods["P1"])
    assert r.status_code == 200, r.text
    ch = r.json()
    seen.append(ch)
    assert ch["type"] == "choice" and ch["arg"] == "room" and 2 <= len(ch["options"]) <= 5
    pick = next((o for o in ch["options"] if o["label"]["tr"] == "A 102"), ch["options"][0])
    r = await card(env, t, "create_booking", **{**ch["args"], ch["arg"]: pick["value"]})
    assert r.status_code in (200, 409), r.text  # never 422: the option value fits the argument
    if r.status_code == 200:
        assert r.json()["type"] == "confirm"  # A1: all resolved → confirm directly
        seen.append(r.json())

    # A8: a helper list shows ≤ 5 rows and points to the page for the rest
    r = await card(env, t, "find_free_rooms", date=THU.isoformat(), start="08:30", end="09:20")
    assert r.status_code == 200, r.text
    lst = r.json()
    seen.append(lst)
    assert lst["type"] == "list" and len(lst["rows"]) <= cards.LIST_ROWS

    # a model-written note with a link / markup is neutralised on the card (RA-08), never a 500
    r = await card(
        env,
        t,
        "create_booking",
        room="A 102",
        date=THU.isoformat(),
        period_id=env.periods["P1"],
        notes="bkz https://evil.example <img src=x>",
    )
    assert r.status_code == 200, r.text
    seen.append(r.json())
    blob = json.dumps(r.json(), ensure_ascii=False)
    assert "://" not in blob.replace("helper.card", "") and "<img" not in blob

    for c in seen:
        schema.validate_card(c)
        for tx in _txts(c):
            assert tx["tr"] and tx["en"], c


async def test_hb_07_status_is_index_only_until_an_admin_routes_the_helper(env, monkeypatch) -> None:  # noqa: F811
    people = await personas(env)
    t = people["teacher"]
    r = await env.client.get(f"{H}/status", headers=t.headers)
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["mode"] == "index" and st["reason"] == "not_routed" and st["provider_kind"] is None
    assert st["message"]["tr"] and st["message"]["en"]

    # an admin routes ``helper`` to a model (HB-B registers the feature; simulated here)
    monkeypatch.setattr(gw, "FEATURES", (*gw.FEATURES, "helper"))
    async with dbmod.get_session_factory()() as s:
        routes = await gw.get_json(s, gw.ROUTES_KEY, {})
        routes.setdefault("features", {})["helper"] = {"provider": "anthropic", "model": "claude-opus-5-5"}
        await gw.put_json(s, gw.ROUTES_KEY, routes)
        await s.commit()

    async def usable(_s: Any, _p: str) -> bool:
        return True

    monkeypatch.setattr(gw, "provider_usable", usable)
    st = (await env.client.get(f"{H}/status", headers=t.headers)).json()
    assert st["mode"] == "index" and st["reason"] == "consent_missing"
    g = await env.client.post("/api/v1/me/consents/ai_personal", headers=t.headers)
    assert g.status_code in (200, 201), g.text
    st = (await env.client.get(f"{H}/status", headers=t.headers)).json()
    monkeypatch.setattr(helper_status, "turn_registered", lambda _app: False)
    st = (await env.client.get(f"{H}/status", headers=t.headers)).json()
    assert st["mode"] == "index" and st["reason"] == "turn_unavailable"  # a server without HB-06
    monkeypatch.undo()  # the real check: HB-06's POST /helper/turn is mounted on this app
    monkeypatch.setattr(gw, "FEATURES", (*gw.FEATURES, "helper"))
    monkeypatch.setattr(gw, "provider_usable", usable)
    assert helper_status.turn_registered(app)
    st = (await env.client.get(f"{H}/status", headers=t.headers)).json()
    assert st["mode"] == "ai" and st["reason"] is None
    assert st["provider_kind"] == "cloud" and st["provider_label"]["tr"].startswith("Anthropic")
    assert st["fallback_active"] is False
