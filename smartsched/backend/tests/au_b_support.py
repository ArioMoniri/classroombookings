"""Shared helpers for the AU-B tests (2FA, passkeys, admin resets; docs/research/2026-10-18-auth-backend.md)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.core import db as dbmod
from app.core import totp
from app.models import AuditEvent, NotificationOutbox, User
from httpx import AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login

PASSWORD = "parola-1234"
API = "/api/v1"


async def make_user(
    c: AsyncClient, admin: dict[str, str], email: str, role: str = "TEACHER", **extra: Any
) -> tuple[int, dict[str, str]]:
    r = await c.post(f"{API}/users", json={"email": email, "role": role, "password": PASSWORD, **extra}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"], await login(c, email, PASSWORD)


async def password_step(c: AsyncClient, email: str, password: str = PASSWORD, **headers: str) -> dict[str, Any]:
    r = await c.post(f"{API}/auth/login", json={"email": email, "password": password}, headers=headers or None)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def enrol_totp(c: AsyncClient, headers: dict[str, str]) -> tuple[str, list[str]]:
    """Turn the authenticator app on for the bearer's account: (secret, recovery codes)."""
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = await c.post(f"{API}/auth/mfa/totp/confirm", json={"code": code_now(secret)}, headers=headers)
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def code_now(secret: str, delta_steps: int = 0) -> str:
    return totp.code_at(secret, int(totp.now()) + delta_steps * totp.PERIOD)


class FakeTotpClock:
    """The TOTP clock of a test: real time at the start, moved on one 30 s step by :func:`next_code` (a code works
    once, so each sign-in of a test needs a later step than the one before)."""

    def __init__(self) -> None:
        self.t = float(int(time.time()))

    def __call__(self) -> float:
        return self.t

    def tick(self, steps: int = 1) -> None:
        self.t += totp.PERIOD * steps


@pytest.fixture(autouse=True)
def totp_clock(monkeypatch) -> FakeTotpClock:  # type: ignore[no-untyped-def]
    clk = FakeTotpClock()
    monkeypatch.setattr(totp, "now", clk)
    return clk


def next_code(secret: str) -> str:
    """The code of the next 30 s step (the clock moves on)."""
    if isinstance(totp.now, FakeTotpClock):
        totp.now.tick()
    return code_now(secret)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def outbox(kind: str, user_id: int | None = None) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationOutbox).where(NotificationOutbox.kind == kind)
        if user_id is not None:
            q = q.where(NotificationOutbox.user_id == user_id)
        return list((await s.execute(q.order_by(NotificationOutbox.id))).scalars())


async def audit_rows(action: str) -> list[AuditEvent]:
    async with dbmod.get_session_factory()() as s:
        q = select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        return list((await s.execute(q)).scalars())


async def set_user(user_id: int, **values: Any) -> None:
    async with dbmod.get_session_factory()() as s:
        u = await s.get(User, user_id)
        assert u is not None
        for k, v in values.items():
            setattr(u, k, v)
        await s.commit()


async def set_policy(c: AsyncClient, admin: dict[str, str], **body: Any) -> dict[str, Any]:
    r = await c.put(f"{API}/admin/auth/mfa-policy", json=body, headers=admin)
    assert r.status_code == 200, r.text
    return dict(r.json())
