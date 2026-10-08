"""Helpers for the CRBS-parity tests (``tests/test_crbs_*.py``)."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.api_fixtures import login


async def make_user(
    client: AsyncClient,
    admin: dict[str, str],
    email: str,
    role: str = "TEACHER",
    password: str = "parola-1234",
    **extra: Any,
) -> tuple[int, dict[str, str]]:
    """Create a user through the API and return (id, auth headers)."""
    r = await client.post(
        "/api/v1/users", json={"email": email, "role": role, "password": password, **extra}, headers=admin
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], await login(client, email, password)


async def role_id(client: AsyncClient, admin: dict[str, str], code: str) -> int:
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    return next(r["id"] for r in roles if r["code"] == code)
