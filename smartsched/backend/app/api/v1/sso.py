"""Sign-in with Microsoft Entra ID (``/api/v1/auth/sso/*``; app/services/sso.py; UI contract
docs/design/v2/sign-in.md §14-§15; IT checklist docs/deploy/sso-entra.md).

Public: ``GET /providers`` (the login page's ``auth`` block + TR/EN texts), ``GET /entra/start`` (302 to Microsoft),
``GET /entra/callback`` (302 back to the panel), ``POST /exchange`` (one-time ticket -> SmartSched JWT),
``GET /invites/{token}`` (invite banner).
Signed in: ``GET /me``, ``POST /entra/link`` (password + confirm), ``DELETE /entra/link``.
``planning.admin``: ``GET/PUT /admin/entra``, ``GET/POST /admin/entra/mappings``, ``DELETE /admin/entra/mappings/{id}``.
``setup.users``: ``GET/POST /admin/invites``, ``POST /admin/invites/{id}/renew``, ``DELETE /admin/invites/{id}``,
``POST /admin/users/{id}/bind``, ``DELETE /admin/users/{id}/identity``, ``PUT /admin/users/{id}/instructor``,
``GET /admin/user-status``.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import DB, Admin, CurrentUser, UsersAdmin
from app.core.config import get_settings
from app.core.security import user_token
from app.schemas.sso import (
    AuthorizeOut,
    BindIn,
    ExchangeIn,
    InstructorIn,
    InstructorOut,
    InviteIn,
    InviteOut,
    LinkIn,
    MappingIn,
    MappingOut,
    ProvidersOut,
    PublicInviteOut,
    SsoConfigIn,
    SsoConfigOut,
    SsoMeOut,
    SsoTokenOut,
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
    """The login page: ``auth`` (Microsoft button on/off, domain hint, self sign-up, password door, LDAP, the
    sign-up role's name) and the TR/EN texts of the ``error`` codes. Nothing about any account."""
    return await svc.providers_out(db)


@router.get(f"/{svc.PROVIDER}/start", status_code=status.HTTP_302_FOUND)
async def start(
    db: DB,
    next: str | None = Query(default=None, max_length=255),  # noqa: A002 - the panel's parameter name
    invite: str | None = Query(default=None, max_length=256),
    prompt: str | None = Query(default=None, max_length=32),
    login_hint: str | None = Query(default=None, max_length=255),
) -> RedirectResponse:
    """A real navigation from the Microsoft button: 302 to Microsoft (PKCE + state + nonce, 10 minutes). ``next`` is
    kept only when it is a same-origin path. Refusals: 302 to ``/login?error=failed&ref=…`` (not configured),
    ``invite_invalid`` or ``invite_expired``."""
    try:
        url = await svc.start_login(db, next, invite=invite, prompt=prompt, login_hint=login_hint)
    except svc.SsoError as err:
        return _redirect(await svc.refuse(db, err, "login"))
    await db.commit()
    return _redirect(url)


@router.get(f"/{svc.PROVIDER}/callback", status_code=status.HTTP_302_FOUND)
async def callback(
    db: DB,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=256),
) -> RedirectResponse:
    """Microsoft's redirect (the registered redirect URI). Always a 302 into the panel:
    ``/login/sso?ticket=…[&next=…][&welcome=self|invited|bound]`` after a sign-in, ``/profile?sso=linked`` after a
    link, or ``/login?error=<code>[&ref=…][&invite=…&invited_masked=…&signed_in=…]``."""
    return _redirect(await svc.finish(db, code=code, state=state, error=error))


@router.post("/exchange", response_model=SsoTokenOut)
async def exchange(body: ExchangeIn, db: DB) -> SsoTokenOut:
    """The panel turns the one-time ticket (2 minutes) into SmartSched's normal bearer token (``tv`` claim: sign-out,
    disabling and role changes revoke it like any other session), plus ``next`` and the ``welcome`` kind."""
    got = await svc.exchange_ticket(db, body.ticket)
    if got is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired sign-in ticket")
    return SsoTokenOut(
        access_token=user_token(got.user),
        expires_in=get_settings().jwt_expire_minutes * 60,
        next=got.next,
        welcome=got.welcome,
        inviter_name=got.inviter_name,
    )


@router.get("/invites/{token}", response_model=PublicInviteOut)
async def invite_banner(token: str, db: DB) -> dict[str, Any]:
    """The banner of ``/login?invite=<token>``: inviter, role, masked address, days left. 404 unknown / used /
    revoked, 410 expired."""
    out = await svc.public_invite(db, token[:256])
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite_invalid")
    if out.get("expired"):
        raise HTTPException(status.HTTP_410_GONE, "invite_expired")
    return out


# --------------------------------------------------------------------------------------------------
# signed-in user
# --------------------------------------------------------------------------------------------------


@router.get("/me", response_model=SsoMeOut)
async def my_identity(user: CurrentUser, db: DB) -> dict[str, Any]:
    return await svc.me(db, user)


@router.post(f"/{svc.PROVIDER}/link", response_model=AuthorizeOut)
async def link(body: LinkIn, user: CurrentUser, db: DB) -> AuthorizeOut:
    """Profile -> "Microsoft hesabını bağla": the user re-enters the SmartSched password and confirms; the panel then
    navigates to ``authorize_url``. The only way an existing account links without an administrator's mark."""
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
# setup.users: invites, "bind on next SSO login", instructor link, status
# --------------------------------------------------------------------------------------------------


@router.get("/admin/invites", response_model=list[InviteOut])
async def get_invites(db: DB, _: UsersAdmin) -> list[dict[str, Any]]:
    return await svc.list_invites(db)


@router.post("/admin/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def post_invite(body: InviteIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Create an account (no password) for an institution e-mail / UPN: status ``invited`` until the first Entra
    login of the pinned tenant whose verified UPN equals it binds ``oid + tid`` (once). 409 ``invite_pending`` (renew
    it), ``account_bound``, ``account_exists`` (use ``POST /admin/users/{id}/bind``)."""
    out = await _guarded(svc.create_invite(db, me, body.model_dump()))
    await db.commit()
    return out


@router.post("/admin/invites/{invite_id}/renew", response_model=InviteOut)
async def renew_invite(invite_id: int, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """A new link and the full validity again; the old link stops working."""
    out = await _guarded(svc.renew_invite(db, me, invite_id))
    await db.commit()
    return out


@router.delete("/admin/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(invite_id: int, db: DB, me: UsersAdmin) -> Response:
    """Revoke an invite or cancel a scheduled binding (the account itself stays)."""
    await _guarded(svc.delete_invite(db, me, invite_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/users/{user_id}/bind", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def bind_user(user_id: int, body: BindIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Mark an existing account (also another administrator's, under the no-escalation rule; never your own)
    "bind on next SSO login" for ``email`` (default: the account's e-mail)."""
    out = await _guarded(svc.mark_bind(db, me, user_id, body.email, body.days))
    await db.commit()
    return out


@router.delete("/admin/users/{user_id}/identity", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user(user_id: int, db: DB, me: UsersAdmin) -> Response:
    await _guarded(svc.admin_unlink(db, me, user_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/admin/users/{user_id}/instructor", response_model=InstructorOut)
async def set_instructor(user_id: int, body: InstructorIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Link the login to an instructor record (``instructors.user_id``; ``null`` clears). Audited."""
    out = await _guarded(svc.set_instructor(db, me, user_id, body.instructor_id))
    await db.commit()
    return out


@router.get("/admin/user-status")
async def user_status(db: DB, _: UsersAdmin) -> dict[str, dict[str, Any]]:
    """``{user_id: {status, auth_methods, invite, binding_pending, self_signup_at, break_glass, instructor_id}}`` for
    every account (the Users screen's columns, sign-in.md §13)."""
    return await svc.user_status(db)
