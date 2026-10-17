"""Mint a one-time Microsoft sign-in ticket for an existing user, exactly as the backend's callback does
(``app.services.sso._issue_ticket``), so e2e/sign-in.spec.ts can test /login/sso → /welcome without a real
Entra tenant. Run with the e2e backend's environment (DATABASE_URL, APP_SECRET, PUBLIC_URL) from
smartsched/backend:

    python3 ../frontend/e2e/tools/mint_sso_ticket.py <email> [self|invited|bound] [inviter name] [next]

Prints the panel URL (``/login/sso?ticket=…``). Test-only: it never runs in the app.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from app.core.db import get_session_factory
from app.models import User
from app.services import sso


async def main(email: str, welcome: str | None, inviter: str | None, next_path: str | None) -> str:
    async with get_session_factory()() as db:
        user = (await db.execute(select(User).where(func.lower(User.email) == email.lower()))).scalar_one()
        data = {"welcome": welcome, "inviter": inviter} if welcome else None
        return await sso._issue_ticket(db, user, next_path, data)  # noqa: SLF001 - the callback's own step


if __name__ == "__main__":
    args = sys.argv[1:]
    url = asyncio.run(main(args[0], args[1] if len(args) > 1 and args[1] else None, args[2] if len(args) > 2 and args[2] else None, args[3] if len(args) > 3 and args[3] else None))
    print(url)
