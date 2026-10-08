"""FastAPI dependencies: DB session, current user, permission guards (CRBS role -> permission sets).

The historic ``Viewer`` / ``Planner`` / ``Admin`` guards are kept by name and now check the permissions
``planning.view`` / ``planning.edit`` / ``planning.admin`` of the user's role (docs/CRBS_PARITY.md §1).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.security import decode_access_token
from app.models import User
from app.services.bookings_perms import LEGACY_GUARDS, Access, load_access

bearer = HTTPBearer(auto_error=False)

#: routes a user flagged with ``force_password_reset`` may still call (CRBS ``check_password_reset``)
PASSWORD_CHANGE_ALLOWED = ("/auth/me", "/auth/change-password", "/auth/permissions")


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DB
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:  # generic message: no library internals to the client (review MINOR 5)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    try:
        user_id = int(payload.get("uid", 0))
    except (TypeError, ValueError):
        user_id = 0
    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    if (
        user.force_password_reset
        and user.auth_source != "ldap"
        and not request.url.path.endswith(PASSWORD_CHANGE_ALLOWED)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "password_change_required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_access(user: CurrentUser, db: DB) -> Access:
    return await load_access(db, user)


CurrentAccess = Annotated[Access, Depends(get_access)]


def require_permission(*names: str) -> Callable[..., object]:
    """Guard: the user's role must hold at least one of ``names`` (role-level, no room ACL)."""

    async def _guard(access: CurrentAccess) -> User:
        if not any(n in access.perms for n in names):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires permission {' or '.join(names)}")
        return access.user

    return _guard


def require_role(minimum: str) -> Callable[..., object]:
    """Historic guard name: VIEWER / PLANNER / ADMIN -> planning.view / planning.edit / planning.admin."""
    return require_permission(LEGACY_GUARDS[minimum])


Viewer = Annotated[User, Depends(require_role("VIEWER"))]
Planner = Annotated[User, Depends(require_role("PLANNER"))]
Admin = Annotated[User, Depends(require_role("ADMIN"))]


def perm(*names: str) -> object:
    """``Annotated[User, perm("setup.users")]`` shorthand."""
    return Depends(require_permission(*names))


UsersAdmin = Annotated[User, Depends(require_permission("setup.users"))]
