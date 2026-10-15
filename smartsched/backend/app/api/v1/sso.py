"""Sign-in with Microsoft Entra ID (``/api/v1/auth/sso/*``; app/services/sso.py, docs/deploy/sso-entra.md).

Public: ``GET /providers`` (login button + TR/EN messages), ``GET /entra/start`` (302 to Microsoft),
``GET /entra/callback`` (302 back to the panel), ``POST /exchange`` (one-time ticket -> SmartSched JWT).
Signed in: ``GET /me``, ``POST /entra/link`` (password + confirm), ``DELETE /entra/link``.
``planning.admin``: ``GET/PUT /admin/entra``, ``GET/POST /admin/entra/mappings``, ``DELETE /admin/entra/mappings/{id}``.
``setup.users``: ``GET/POST /admin/invites``, ``DELETE /admin/invites/{id}``, ``POST /admin/users/{id}/bind``,
``DELETE /admin/users/{id}/identity``, ``GET /admin/user-status``.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import DB, Admin, CurrentUser, UsersAdmin
from app.core.config import get_settings
from app.core.security import user_token
from app.schemas.auth import TokenOut
from app.schemas.sso import (
    AuthorizeOut,
    BindIn,
    ExchangeIn,
    InviteIn,
    InviteOut,
    LinkIn,
    MappingIn,
    MappingOut,
    ProvidersOut,
    SsoConfigIn,
    SsoConfigOut,
    SsoMeOut,
)
from app.services import sso as svc

router = APIRouter(prefix="/auth/sso", tags=["sso"])


async def _guarded[T](coro: Awaitable[T]) -> T:
    try:
        return await coro
    except svc.SsoAdminError as exc:
        raise HTTPException(exc.status, exc.detail()) from exc


def _redirect(url: str) -> RedirectResponse:
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"  # the code / ticket never leaks to another site
    return resp


# --------------------------------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------------------------------


@router.get("/providers", response_model=ProvidersOut)
async def providers(db: DB) -> dict[str, Any]:
    """The login screen: whether to show "Sign in with Microsoft 365", and the TR/EN texts of ``sso_error`` codes."""
    return svc.providers_out(await svc.active_client(db) is not None)


@router.get(f"/{svc.PROVIDER}/start", status_code=status.HTTP_302_FOUND)
async def start(db: DB, return_path: str | None = Query(default=None, max_length=255)) -> RedirectResponse:
    """Browser navigation from the login button: 302 to Microsoft (PKCE + state + nonce, 10 minutes). Not configured
    or switched off: 302 back to ``/login?sso_error=not_configured``."""
    try:
        url = await svc.start_login(db, return_path)
    except svc.SsoError as err:
        return _redirect(await svc.login_error_url(db, err.code))
    await db.commit()
    return _redirect(url)


@router.get(f"/{svc.PROVIDER}/callback", status_code=status.HTTP_302_FOUND)
async def callback(
    db: DB,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=256),
) -> RedirectResponse:
    """Microsoft's redirect (the registered redirect URI). Always a 302 into the panel: ``/login/sso?ticket=…&next=…``
    after a sign-in, ``/profile?sso=linked`` after a link, or ``?sso_error=<code>``."""
    return _redirect(await svc.finish(db, code=code, state=state, error=error))


@router.post("/exchange", response_model=TokenOut)
async def exchange(body: ExchangeIn, db: DB) -> TokenOut:
    """The panel turns the one-time ticket (2 minutes) into SmartSched's normal bearer token (``tv`` claim: sign-out,
    disabling and role changes revoke it like any other session)."""
    user = await svc.exchange_ticket(db, body.ticket)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired sign-in ticket")
    return TokenOut(access_token=user_token(user), expires_in=get_settings().jwt_expire_minutes * 60)


# --------------------------------------------------------------------------------------------------
# signed-in user
# --------------------------------------------------------------------------------------------------


@router.get("/me", response_model=SsoMeOut)
async def my_identity(user: CurrentUser, db: DB) -> dict[str, Any]:
    return await svc.me(db, user)


@router.post(f"/{svc.PROVIDER}/link", response_model=AuthorizeOut)
async def link(body: LinkIn, user: CurrentUser, db: DB) -> AuthorizeOut:
    """Profile -> "Kurumsal hesabı bağla": the user re-enters the SmartSched password and confirms; the panel then
    navigates to ``authorize_url``. The only way an existing account links without an administrator's invite."""
    url = await _guarded(svc.start_link(db, user, body.password))
    await db.commit()
    return AuthorizeOut(authorize_url=url)


@router.delete(f"/{svc.PROVIDER}/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(user: CurrentUser, db: DB) -> Response:
    await _guarded(svc.unlink_own(db, user))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------------------
# planning.admin: configuration and role mapping
# --------------------------------------------------------------------------------------------------


@router.get(f"/admin/{svc.PROVIDER}", response_model=SsoConfigOut)
async def get_config(db: DB, _: Admin) -> dict[str, Any]:
    return await svc.config_out(db)


@router.put(f"/admin/{svc.PROVIDER}", response_model=SsoConfigOut)
async def put_config(body: SsoConfigIn, db: DB, me: Admin) -> dict[str, Any]:
    """Partial update. 422: incomplete client or no public URL when enabling, a privileged sign-up role; 409: the
    break-glass rule (``oidc_only_non_admins`` needs an active administrator with a local password)."""
    try:
        await svc.update_config(db, me, body.model_dump(exclude_unset=True))
    except svc.SsoAdminError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.detail()) from exc
    await db.commit()
    return await svc.config_out(db)


@router.get(f"/admin/{svc.PROVIDER}/mappings", response_model=list[MappingOut])
async def get_mappings(db: DB, _: Admin) -> list[dict[str, Any]]:
    return await svc.list_mappings(db)


@router.post(f"/admin/{svc.PROVIDER}/mappings", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
async def post_mapping(body: MappingIn, db: DB, me: Admin) -> dict[str, Any]:
    """Entra app role value or group object id -> SmartSched role. Applied at every login only while
    ``role_mapping_enabled`` is on. 403: the editor lacks a permission of the role (no escalation); 422: an
    administrative role while ``allow_admin_mapping`` is off."""
    m = await _guarded(svc.add_mapping(db, me, body.claim, body.value, body.role_id))
    await db.commit()
    return next(x for x in await svc.list_mappings(db) if x["id"] == m.id)


@router.delete(f"/admin/{svc.PROVIDER}/mappings/{{mapping_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(mapping_id: int, db: DB, me: Admin) -> Response:
    await _guarded(svc.delete_mapping(db, me, mapping_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------------------
# setup.users: invites, "bind on next SSO login", status
# --------------------------------------------------------------------------------------------------


@router.get("/admin/invites", response_model=list[InviteOut])
async def get_invites(db: DB, _: UsersAdmin) -> list[dict[str, Any]]:
    return await svc.list_invites(db)


@router.post("/admin/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def post_invite(body: InviteIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Create an account (no password) for an institution e-mail / UPN: status ``invited`` until the first Entra
    login of the pinned tenant whose verified UPN equals it binds ``oid + tid`` (once). 409: the e-mail has an
    account already (use ``POST /admin/users/{id}/bind``)."""
    out = await _guarded(svc.create_invite(db, me, body.model_dump()))
    await db.commit()
    return out


@router.delete("/admin/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(invite_id: int, db: DB, me: UsersAdmin) -> Response:
    await _guarded(svc.delete_invite(db, me, invite_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/users/{user_id}/bind", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def bind_user(user_id: int, body: BindIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Mark an existing account (also another administrator's, under the no-escalation rule) "bind on next SSO
    login" for ``email`` (default: the account's e-mail)."""
    out = await _guarded(svc.mark_bind(db, me, user_id, body.email, body.days))
    await db.commit()
    return out


@router.delete("/admin/users/{user_id}/identity", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user(user_id: int, db: DB, me: UsersAdmin) -> Response:
    await _guarded(svc.admin_unlink(db, me, user_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/user-status")
async def user_status(db: DB, _: UsersAdmin) -> dict[str, str]:
    """``{user_id: "linked" | "invited" | "invite_expired"}`` (accounts without Entra state are absent)."""
    return await svc.user_status(db)
