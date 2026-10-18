"""FIX-A HX/HB copy (e2e results 2026-10-18, HB-02 note): a slot taken between the helper card and its confirm is
refused with the helper cards' own words, "Bu saat az önce doldu." / "This slot was just taken."
(``components/helper/__fixtures__/cards.json``, docs/design/v3/helper.md "Card confirm"), not "Bu saat dolu.".
The booking service now sends the Turkish with its ``conflict`` refusals, so the helper (``writes.refusal``, which
prefers the service's ``message_tr``) and the booking API say the same thing.

Real data: the Bahar 2026 environment (``tests/crbs_env``): A 102, Thursday 19 Feb 2026, P1."""

from __future__ import annotations

from app.ai.helper.actions import registry as reg

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import personas
from tests.helper.test_hb_05_writes import THU, _book_card, _confirm

TAKEN_TR = "Bu saat az önce doldu."
TAKEN_EN = "This slot was just taken."


async def test_a_slot_taken_before_confirm_reads_like_the_helper_card(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t, a = people["teacher"], people["approver"]
    c = await _book_card(env, t)
    assert (await env.book(a.headers, "A102", THU, "P1")).status_code == 201
    r = await _confirm(env, t, c["token"])
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "conflict" and d["message_tr"] == TAKEN_TR, d
    assert d.get("message_en") == TAKEN_EN and "alternatives" in d


async def test_the_booking_api_sends_the_same_words_for_a_taken_slot(env) -> None:  # noqa: F811
    people = await personas(env)
    t, a = people["teacher"], people["approver"]
    assert (await env.book(a.headers, "A102", THU, "P1")).status_code == 201
    r = await env.book(t.headers, "A102", THU, "P1")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "conflict" and d["conflict"]["kind"] == "booking"
    assert d["message_tr"] == TAKEN_TR and d["message_en"] == TAKEN_EN
