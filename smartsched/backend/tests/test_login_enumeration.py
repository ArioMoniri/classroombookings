"""Admin persona 2026-10-15 M-42: ``POST /auth/login`` must not tell a disabled account from a wrong password.

A disabled user with the right password gets the same status and body as a wrong password (401 "invalid
credentials"); the real reason goes to the audit log (``auth.login_refused``) and the server log only. Every
refusal costs one password-hash check, also for unknown names, so the answer time does not tell them apart.
Runs on the real Bahar 2026 import (``tests/crbs_env``).
"""

from __future__ import annotations

import logging

from app.api.v1 import auth as auth_api
from app.core import db as dbmod
from app.models import AuditEvent
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

LOGIN = "/api/v1/auth/login"


async def test_disabled_account_answers_like_a_wrong_password(env, caplog, monkeypatch):  # noqa: F811
    c = env.client
    uid, _ = await env.user("pasif.öğretmen@uni.edu.tr", username="pasif.ogretmen", displayname="Işıl İnce")
    wrong = await c.post(LOGIN, json={"username": "pasif.ogretmen", "password": "yanlış-parola"})
    assert wrong.status_code == 401
    r = await c.put(f"/api/v1/users/{uid}", json={"is_active": False}, headers=env.admin)
    assert r.status_code == 200, r.text

    calls: list[str] = []
    real = auth_api.verify_password

    def counting(password: str, hashed: str) -> bool:
        calls.append(hashed[:8])
        return real(password, hashed)

    monkeypatch.setattr(auth_api, "verify_password", counting)
    caplog.set_level(logging.INFO, logger="app.api.v1.auth")
    answers = []
    for body in (
        {"username": "PASİF.OGRETMEN", "password": "parola-1234"},  # Turkish dotted capital İ, right password
        {"email": "pasif.öğretmen@uni.edu.tr", "password": "parola-1234"},
        {"username": "pasif.ogretmen", "password": "yanlış-parola"},
        {"username": "hiç.olmayan.kişi", "password": "parola-1234"},  # unknown name
    ):
        res = await c.post(LOGIN, json=body)
        answers.append((res.status_code, res.json(), res.headers.get("www-authenticate")))
    assert answers == [(wrong.status_code, wrong.json(), wrong.headers.get("www-authenticate"))] * 4
    assert "disabled" not in str(answers)
    assert len(calls) == 4  # one hash check per attempt, unknown names included

    async with dbmod.get_session_factory()() as s:
        refused = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_refused"))).scalars().all()
    assert [(e.entity_type, e.entity_id, (e.after or {}).get("reason")) for e in refused] == [
        ("user", str(uid), "account disabled")
    ] * 2  # only the attempts with the right password reveal (to the audit log) that the account is disabled
    assert any("disabled" in rec.getMessage() and str(uid) in rec.getMessage() for rec in caplog.records)

    await c.put(f"/api/v1/users/{uid}", json={"is_active": True}, headers=env.admin)
    assert (await c.post(LOGIN, json={"username": "pasif.ogretmen", "password": "parola-1234"})).status_code == 200
