"""Seed data: the CRBS permission catalogue + default roles (``data.sql``: Administrator, Teacher; plus the
SmartSched Planner and Viewer), and the first admin from ADMIN_EMAIL / ADMIN_PASSWORD when the users table
is empty. Nothing else is seeded (no demo data)."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
    user = User(
        email=settings.admin_email.lower(),
        password_hash=hash_password(settings.admin_password),
        full_name="Administrator",
    )
    set_user_role(user, roles["ADMIN"])
    session.add(user)
    await session.commit()
    log.info("seeded admin user %s", user.email)
    return user
