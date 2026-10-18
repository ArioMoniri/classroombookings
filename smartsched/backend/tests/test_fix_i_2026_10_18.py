"""FIX-I (round-4 e2e triage, 2026-10-18): the sessions list (AU-B 1, AUX12-F03 rest).

* A token used only by a script (curl, an HTTP library, Playwright's request context) is still a session that can act
  for the account, so it stays in the list (it can be ended there), labelled as a script client, not as an unknown
  browser.
* The stored device label is language-neutral ("Safari, iPhone", "API", or empty), and ``GET /auth/sessions`` returns
  ``browser`` / ``os`` / ``client`` beside it, so the UI words the unknown parts in the viewer's language; rows written
  before FIX-I in Turkish ("bilinmeyen tarayıcı, bilinmeyen cihaz") read as unknown, never as Turkish text.
"""

from __future__ import annotations

import pytest
from app.core import db as dbmod
from app.models.mfa import UserSession
from app.services import sessions
from sqlalchemy import select

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import API, bearer, make_user, password_step
from tests.crbs_env import env  # noqa: F401

EMAIL = "betik.istemci@uni.edu.tr"
CHROME = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    sessions.forget()
    admin = await login(client)
    await make_user(client, admin, EMAIL)
    return client


async def _token(c, ua: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    step = await password_step(c, EMAIL, **{"User-Agent": ua})
    return bearer(step["access_token"])


async def _rows(c, headers: dict[str, str], ua: str = CHROME) -> list[dict]:  # type: ignore[no-untyped-def,type-arg]
    r = await c.get(f"{API}/auth/sessions", headers={**headers, "User-Agent": ua})
    assert r.status_code == 200, r.text
    return list(r.json())


@pytest.mark.parametrize(
    "ua", ["curl/8.5.0", "python-requests/2.32.3", "Playwright/1.48.0 (x64; ubuntu 22.04) node/20.18"]
)
def test_script_clients_are_named(ua: str) -> None:
    assert sessions.session_device(ua) == "API"
    assert sessions.device_parts("API") == {"browser": None, "os": None, "client": "api"}


def test_device_label_is_language_neutral() -> None:
    assert sessions.session_device(CHROME) == "Chrome, Linux"
    assert sessions.session_device("") == ""
    assert sessions.session_device(None) == ""
    assert sessions.device_parts("Chrome, Linux") == {"browser": "Chrome", "os": "Linux", "client": "browser"}
    assert sessions.device_parts("Safari, iPhone") == {"browser": "Safari", "os": "iPhone", "client": "browser"}
    # rows written before FIX-I, in Turkish or English
    for legacy in ("bilinmeyen tarayıcı, bilinmeyen cihaz", "unknown browser, unknown device", "", None):
        assert sessions.device_parts(legacy) == {"browser": None, "os": None, "client": "unknown"}
    assert sessions.device_parts("bilinmeyen tarayıcı, Linux") == {"browser": None, "os": "Linux", "client": "browser"}


async def test_a_script_token_is_listed_as_a_script_client(setup) -> None:  # type: ignore[no-untyped-def]
    c = setup
    script = await _token(c, "curl/8.5.0")
    assert (await c.get(f"{API}/auth/me", headers={**script, "User-Agent": "curl/8.5.0"})).status_code == 200
    browser = await _token(c, CHROME)
    rows = await _rows(c, browser)
    assert len(rows) == 2
    cur = next(x for x in rows if x["current"])
    other = next(x for x in rows if not x["current"])
    assert cur["device"] == "Chrome, Linux" and cur["client"] == "browser" and cur["os"] == "Linux"
    assert other["device"] == "API" and other["client"] == "api" and other["browser"] is None
    assert "bilinmeyen" not in str(rows)


async def test_a_token_first_seen_from_a_script_takes_the_browser_label_later(setup) -> None:  # type: ignore[no-untyped-def]
    c = setup
    tok = await _token(c, "node")
    assert (await c.get(f"{API}/auth/me", headers={**tok, "User-Agent": "node"})).status_code == 200
    sessions.forget()
    assert (await c.get(f"{API}/auth/me", headers={**tok, "User-Agent": CHROME})).status_code == 200
    sessions.forget()
    # a later server-side request never makes it worse
    assert (await c.get(f"{API}/auth/me", headers={**tok, "User-Agent": "node"})).status_code == 200
    row = next(x for x in await _rows(c, tok) if x["current"])
    assert row["device"] == "Chrome, Linux" and row["client"] == "browser"


async def test_a_legacy_turkish_label_reads_as_unknown_and_is_upgraded(setup) -> None:  # type: ignore[no-untyped-def]
    c = setup
    tok = await _token(c, "")
    assert (await c.get(f"{API}/auth/me", headers={**tok, "User-Agent": ""})).status_code == 200
    async with dbmod.get_session_factory()() as s:
        for row in (await s.execute(select(UserSession))).scalars():
            row.device = "bilinmeyen tarayıcı, bilinmeyen cihaz"
        await s.commit()
    sessions.forget()
    rows = await _rows(c, tok, ua="")
    assert rows[0]["client"] == "unknown" and rows[0]["browser"] is None and rows[0]["os"] is None
    sessions.forget()
    row = next(x for x in await _rows(c, tok) if x["current"])
    assert row["device"] == "Chrome, Linux"


# ------------------------------------------------------------------------------------- E2EB-F07: calendar refusals


async def test_a_date_no_term_covers_is_refused_in_turkish(env) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """The grid on a date outside every term said "Bu tarih ya da saat rezerve edilemez (no term covers 18.10.2026)."
    (English inside the Turkish line): the refusal carries message_tr / message_en of its own."""
    _, teacher = await env.user("donem.disi@uni.edu.tr")
    r = await env.client.get("/api/v1/bookings/grid", params={"display": "day", "date": "2031-10-18"}, headers=teacher)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "calendar"
    assert d["message_tr"] == "18.10.2031 hiçbir dönemin içinde değil."
    assert d["message_en"] == "No term covers 18.10.2031."


async def test_a_single_booking_outside_its_term_names_the_term_in_turkish(env) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    _, teacher = await env.user("donem.disi2@uni.edu.tr")
    body = {"room_id": env.rooms["A101"], "date": "2031-10-20", "period_id": env.periods["P1"], "term_id": env.term_id}
    r = await env.client.post("/api/v1/bookings", json=body, headers=teacher)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "calendar"
    assert "20.10.2031" in d["message_tr"] and "döneminin dışında" in d["message_tr"]
    assert "outside" in d["message_en"]
