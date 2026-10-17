"""Flow-loop round 2, lane A (T-R2-06, R2-M-22): a short password-reset code is refused like a wrong one — a coded
400 with ``message_tr`` — never pydantic's 422 'String should have at least 8 characters'."""

from __future__ import annotations

from tests.crbs_env import env  # noqa: F401


async def test_short_reset_code_is_a_coded_400(env):  # noqa: F811
    c = env.client
    for token in ("12", "x" * 200):
        r = await c.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "Flow-2026!pw"})
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "invalid_code"
        assert detail["message_tr"] == "Kod hatalı ya da süresi dolmuş. Yenisini isteyin."
        assert "String should" not in r.text
    # a wrong but well-formed code answers the very same shape
    r = await c.post(
        "/api/v1/auth/password-reset/confirm", json={"token": "nope-nope-nope", "password": "Flow-2026!pw"}
    )
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_code"


async def test_refused_logo_is_a_coded_problem_with_turkish(env):  # noqa: F811
    """Lane F ask (T-R2-33): an SVG / polyglot logo is refused with code + message_tr, not the bare English text."""
    c = env.client
    r = await c.post(
        "/api/v1/org/logo",
        files={"file": ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")},
        headers=env.admin,
    )
    assert r.status_code in (400, 415, 422), r.text
    detail = r.json()["detail"]
    assert detail["code"] and detail["message_tr"] and "image" not in detail["message_tr"].lower()
