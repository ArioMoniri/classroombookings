"""FastAPI dependencies: DB session, current user, role guard."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.security import decode_access_token
from app.models import User

bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {"VIEWER": 1, "PLANNER": 2, "ADMIN": 3}


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DB) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc
    try:
        user_id = int(payload.get("uid", 0))
    except (TypeError, ValueError):
        user_id = 0
    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum: str) -> Callable[..., User]:
    async def _guard(user: CurrentUser) -> User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {minimum}")
        return user

    return _guard


Viewer = Annotated[User, Depends(require_role("VIEWER"))]
Planner = Annotated[User, Depends(require_role("PLANNER"))]
Admin = Annotated[User, Depends(require_role("ADMIN"))]
