from __future__ import annotations

import logging
from functools import cache

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import DB, CurrentAccess, CurrentUser
from app.core.config import get_settings
from app.core.security import hash_password, password_needs_rehash, revoke_tokens, user_token, verify_password
from app.models import User
from app.models.base import utcnow
from app.schemas.auth import LoginIn, TokenOut, UserOut
from app.services import audit, bookings_ldap, sso
from app.services import bookings_events as events
from app.services.bookings_settings import get_value
from app.services.bookings_users import find_login_user

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)
#: the one answer for every refused sign-in (admin persona M-42: a disabled account is not told apart)
INVALID = "invalid credentials"


@cache
def _dummy_hash() -> str:
    return hash_password("smartsched-timing-equaliser")


def _spend_hash_time(password: str) -> None:
    """A hash check against a throw-away hash, so refusals without a stored hash take as long as a wrong one."""
    verify_password(password, _dummy_hash())


async def _refuse_disabled(db: DB, user: User | None, method: str) -> HTTPException:
    """Disabled account: the reason goes to the audit log and the server log, the caller sees ``INVALID``."""
    log.warning("login refused for user %s (%s): account disabled", user.id if user else "?", method)
    await audit.record(
        db,
        "auth.login_refused",
        "user",
        user.id if user else None,
        after={"reason": "account disabled", "auth_method": method},
    )
    await db.commit()
    return HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)


async def _local(db: DB, identifier: str, password: str, *, ldap_rejected: bool = False) -> User | None:
    """Local password check. A legacy CRBS hash (``$2y$`` / ``sha1:``) is replaced by argon2 once it has been
    verified, as CRBS upgrades ``sha1:`` hashes (``Auth_local::verify``). After the directory *rejected* the
    password, the local copy is not tried for directory accounts (``auth_source = ldap``): only when the
    directory cannot be reached (deliberate security difference; CRBS always falls back)."""
    user = await find_login_user(db, identifier)
    if user is None or not user.password_hash or (ldap_rejected and user.auth_source == "ldap"):
        _spend_hash_time(password)  # unknown names cost a hash check too (M-42 timing)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: DB, request: Request) -> TokenOut:
    """Local or LDAP sign-in (CRBS ``Userauth::log_in``): LDAP first when enabled, local auth when LDAP is
    off or the directory cannot be reached; disabled accounts are refused with the same 401 as a wrong password
    (the reason is audited as ``auth.login_refused``, persona M-42). Repeated failures from one
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
    ldap_rejected = False
    if await get_value(db, "ldap", "enabled") and "@" not in ident:
        res = await bookings_ldap.authenticate(db, ident, body.password)
        if res.ok and res.user is not None:
            user, method = res.user, "ldap"
        elif "user_not_enabled" in res.errors:
            _spend_hash_time(body.password)  # the directory answers before any bind for a disabled account
            raise await _refuse_disabled(db, await find_login_user(db, ident), "ldap")
        elif not res.connection_error:
            ldap_rejected = True
            log.info("LDAP login failed for %s: %s", ident, res.errors)
    if user is None:
        user = await _local(db, ident, body.password, ldap_rejected=ldap_rejected)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    if not user.is_active:
        raise await _refuse_disabled(db, user, method)
    if not await sso.password_login_allowed(db, user):  # "Microsoft only for non-admins": same 401 as a bad password
        await sso.record_password_refusal(db, user, method)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    user.last_login_at = utcnow()
    await events.emit(db, "user.logged_in", {"user_id": user.id, "auth_method": method})
    await db.commit()
    token = user_token(user)  # carries the token version (B-AUTH-11)
    return TokenOut(
        access_token=token,
        expires_in=get_settings().jwt_expire_minutes * 60,
        password_change_required=bool(user.force_password_reset and method == "local"),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, db: DB) -> Response:
    """Sign out (CRBS ``Logout``, parity B-AUTH-11): the user's token version moves on, so this bearer token and
    every other token of the user (other browsers, devices) answer 401 from now on. Allowed while a forced
    password change is pending."""
    revoke_tokens(user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser, access: CurrentAccess) -> UserOut:
    out = UserOut.model_validate(user)
    out.permissions = sorted(access.perms)
    if out.role_id is None and access.role is not None:
        out.role_id = access.role.id
    return out
