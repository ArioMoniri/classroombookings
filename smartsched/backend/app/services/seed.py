"""Seed data: the CRBS permission catalogue + default roles (``data.sql``: Administrator, Teacher; plus the
SmartSched Planner and Viewer), and the first admin from ADMIN_EMAIL / ADMIN_PASSWORD when the users table
is empty. Nothing else is seeded (no demo data).

Production (no-placeholder audit M3): a placeholder or short ADMIN_PASSWORD is refused (``RuntimeError``),
and the admin is created with ``force_password_reset`` so the first login goes to /login/change-password.
The flag is set on creation only: once any user exists this function never touches an account again."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import admin_password_problem, get_settings
from app.core.security import hash_password
from app.models import User
from app.services.bookings_perms import ensure_permissions_and_roles, set_user_role

log = logging.getLogger(__name__)


async def seed_admin(session: AsyncSession) -> User | None:
    settings = get_settings()
    roles = await ensure_permissions_and_roles(session)
    await session.commit()
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    if count:
        return None
    if not settings.admin_email or not settings.admin_password:
        log.warning("no users and ADMIN_EMAIL/ADMIN_PASSWORD not set; login will be impossible")
        return None
    problem = None if settings.is_relaxed else admin_password_problem(settings.admin_password)
    if problem:
        raise RuntimeError(
            f"refusing to seed the admin with ENVIRONMENT={settings.environment}: ADMIN_PASSWORD {problem}"
        )
    user = User(
        email=settings.admin_email.strip().lower(),
        password_hash=hash_password(settings.admin_password),
        full_name="Administrator",
        force_password_reset=not settings.is_relaxed,
    )
    set_user_role(user, roles["ADMIN"])
    session.add(user)
    await session.commit()
    log.info("seeded admin user %s", user.email)
    return user
