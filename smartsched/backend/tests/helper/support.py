"""Personas for the helper tests on the real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00).

* ``teacher``  - Ayşe Yılmaz, built-in TEACHER role (room.view, book_single.create);
* ``approver`` - Gözde Ayrancıgil, a custom "Onaylayıcı" role (room.view, book_single.create, approvals.decide),
  designated approver for every room;
* ``planner``  - the seeded planner account (PLANNER);
* ``admin``    - the seeded administrator.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.api_fixtures import login

H = "/api/v1/helper"


@dataclass
class Persona:
    name: str
    uid: int
    headers: dict[str, str]
    perms: frozenset[str]


async def _me(env, h) -> tuple[int, frozenset[str]]:  # type: ignore[no-untyped-def]
    r = await env.client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200, r.text
    return int(r.json()["id"]), frozenset(r.json().get("permissions") or [])


async def personas(env) -> dict[str, Persona]:  # type: ignore[no-untyped-def]
    out: dict[str, Persona] = {}
    _, teacher = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    r = await env.client.post(
        "/api/v1/roles",
        json={"name": "Onaylayıcı", "permissions": ["room.view", "book_single.create", "approvals.decide"]},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    r = await env.client.post(
        "/api/v1/users",
        json={
            "email": "gozde.ayrancigil@uni.edu.tr",
            "role_id": r.json()["id"],
            "password": "parola-1234",
            "firstname": "Gözde",
            "lastname": "Ayrancıgil",
            "approves_for": [{"type": "all"}],
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    approver = await login(env.client, "gozde.ayrancigil@uni.edu.tr", "parola-1234")
    for name, h in (("teacher", teacher), ("approver", approver), ("planner", env.planner), ("admin", env.admin)):
        uid, perms = await _me(env, h)
        out[name] = Persona(name, uid, h, perms)
    return out


async def card(env, p: Persona, action: str, **args):  # type: ignore[no-untyped-def]
    return await env.client.post(f"{H}/actions/{action}/card", json={"args": args}, headers=p.headers)
