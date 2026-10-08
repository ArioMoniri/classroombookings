from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DB, CurrentAccess, CurrentUser
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.models import User
from app.models.base import utcnow
from app.schemas.auth import LoginIn, TokenOut, UserOut
from app.services import bookings_events as events
from app.services import bookings_ldap
from app.services.bookings_settings import get_value
from app.services.bookings_users import find_login_user

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


async def _local(db: DB, identifier: str, password: str) -> User | None:
    user = await find_login_user(db, identifier)
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        return None
    return user


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: DB, request: Request) -> TokenOut:
    """Local or LDAP sign-in (CRBS ``Userauth::log_in``): LDAP first when enabled, local auth when LDAP is
    off or the directory cannot be reached; disabled accounts are refused. Repeated failures from one
    address answer 429 for a while (review MINOR 5)."""
    from app.core import ratelimit

    address = request.client.host if request.client else "?"
    wait = ratelimit.retry_after(address, body.identifier)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many failed logins; try again later",
            headers={"Retry-After": str(wait)},
        )
    try:
        out = await _login(body, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            ratelimit.failure(address, body.identifier)
        raise
    ratelimit.success(address, body.identifier)
    return out


async def _login(body: LoginIn, db: DB) -> TokenOut:
    ident, method = body.identifier, "local"
    user: User | None = None
    if await get_value(db, "ldap", "enabled") and "@" not in ident:
        res = await bookings_ldap.authenticate(db, ident, body.password)
        if res.ok and res.user is not None:
            user, method = res.user, "ldap"
        elif "user_not_enabled" in res.errors:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "user disabled")
        elif not res.connection_error:
            log.info("LDAP login failed for %s: %s", ident, res.errors)
    if user is None:
        user = await _local(db, ident, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user disabled")
    user.last_login_at = utcnow()
    await events.emit(db, "user.logged_in", {"user_id": user.id, "auth_method": method})
    await db.commit()
    token = create_access_token(user.email or user.username or str(user.id), {"uid": user.id, "role": user.role})
    return TokenOut(
        access_token=token,
        expires_in=get_settings().jwt_expire_minutes * 60,
        password_change_required=bool(user.force_password_reset and method == "local"),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser, access: CurrentAccess) -> UserOut:
    out = UserOut.model_validate(user)
    out.permissions = sorted(access.perms)
    if out.role_id is None and access.role is not None:
        out.role_id = access.role.id
    return out
