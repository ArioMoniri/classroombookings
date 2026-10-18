"""Two-step sign-in, passkeys, trusted devices and administrator resets (AU-B, owner request 2026-10-18).

Contract for the UX and frontend lanes: the AU-B API.md (scratchpad); design: docs/research/2026-10-18-auth-backend.md.
Logic lives in :mod:`app.services.mfa`; every refusal is ``{code, message, message_en, message_tr}``. A failed second
factor is committed (counted for the lockout) before the refusal is answered.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import DB, CurrentUser, UsersAdmin, require_permission
from app.models import User
from app.schemas.mfa import (
    AdminResetIn,
    ChallengeIn,
    CodeIn,
    CredentialIn,
    DisableIn,
    PasswordIn,
    PolicyIn,
    RegisterIn,
    RenameIn,
    ResetLinkIn,
    SetupConfirmIn,
    VerifyIn,
)
from app.services import mfa

router = APIRouter(prefix="/auth", tags=["auth-mfa"])
admin_router = APIRouter(prefix="/admin", tags=["auth-mfa"])
AuthAdmin = Annotated[User, Depends(require_permission("setup.authentication"))]


async def _run[T](db: DB, work: Awaitable[T]) -> T:
    """Commit the work, or commit what a refusal recorded (failure counts, audit) and answer the refusal."""
    try:
        out = await work
    except mfa.MfaError as exc:
        await db.commit()
        raise exc.http() from exc
    await db.commit()
    return out


def _origin(request: Request) -> str | None:
    return request.headers.get("origin")


def _recent(request: Request) -> bool:
    """The bearer token was issued within :data:`mfa.REAUTH_WINDOW` (10 minutes): the person just signed in, so a
    sensitive change needs no password again (auth UX spec §17). A password that is sent must still be right."""
    import time

    from app.core.security import decode_access_token

    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return False
    try:
        iat = int(decode_access_token(auth[7:].strip()).get("iat") or 0)
    except Exception:
        return False
    return 0 <= time.time() - iat <= mfa.REAUTH_WINDOW.total_seconds()


async def _reauth(db: DB, user: User, password: str, request: Request) -> None:
    if not await mfa.reauth(db, user, password, recent=_recent(request)):
        raise mfa.reauth_failed().http()


# --------------------------------------------------------------------------------------------------
# status, authenticator app, recovery codes
# --------------------------------------------------------------------------------------------------


@router.get("/mfa")
async def mfa_status(db: DB, user: CurrentUser) -> dict[str, Any]:
    return await mfa.status(db, user)


@router.post("/mfa/totp/start")
async def totp_start(body: PasswordIn, db: DB, user: CurrentUser, request: Request) -> dict[str, Any]:
    """Begin authenticator-app enrolment (re-authentication: the password). The secret and the ``otpauth://`` URI are
    shown to the person for the QR code; the frontend draws the QR from ``otpauth_uri``."""
    await _run(db, mfa._refuse_sso(db, user))
    await _reauth(db, user, body.password, request)
    return await _run(db, mfa.totp_start(db, user))


@router.post("/mfa/totp/confirm")
async def totp_confirm(body: CodeIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    codes = await _run(db, mfa.totp_confirm(db, user, body.code))
    return {"enabled": True, "recovery_codes": codes}


@router.post("/mfa/disable")
async def totp_disable(body: DisableIn, db: DB, user: CurrentUser, request: Request) -> dict[str, Any]:
    return await _run(db, mfa.disable(db, user, body.password, body.code, recent=_recent(request)))


@router.post("/mfa/recovery-codes")
async def recovery_regenerate(body: PasswordIn, db: DB, user: CurrentUser, request: Request) -> dict[str, Any]:
    codes = await _run(db, mfa.regenerate_recovery(db, user, body.password, recent=_recent(request)))
    return {"recovery_codes": codes}


@router.get("/sign-ins")
async def sign_ins(db: DB, user: CurrentUser) -> dict[str, Any]:
    """The person's own sign-in and security history (newest first)."""
    return await mfa.sign_in_history(db, user)


# --------------------------------------------------------------------------------------------------
# the sign-in challenge step (unauthenticated: the challenge token is the credential)
# --------------------------------------------------------------------------------------------------


@router.post("/mfa/verify")
async def mfa_verify(body: VerifyIn, db: DB) -> dict[str, Any]:
    return await _run(
        db, mfa.verify_code(db, body.challenge_token, body.method, body.code, trust_device=body.trust_device)
    )


@router.post("/mfa/passkey/options")
async def mfa_passkey_options(body: ChallengeIn, db: DB, request: Request) -> dict[str, Any]:
    return await _run(db, mfa.mfa_passkey_options(db, body.challenge_token, _origin(request)))


@router.post("/mfa/passkey/verify")
async def mfa_passkey_verify(body: CredentialIn, db: DB, request: Request) -> dict[str, Any]:
    return await _run(
        db,
        mfa.mfa_passkey_verify(
            db, body.challenge_token, body.credential, _origin(request), trust_device=body.trust_device
        ),
    )


# --------------------------------------------------------------------------------------------------
# enrolment the policy requires before a session (setup token from POST /auth/login)
# --------------------------------------------------------------------------------------------------


@router.post("/mfa/setup/totp/start")
async def setup_totp_start(body: ChallengeIn, db: DB) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        user, _ch = await mfa.setup_user(db, body.challenge_token)
        return await mfa.totp_start(db, user)

    return await _run(db, work())


@router.post("/mfa/setup/totp/confirm")
async def setup_totp_confirm(body: SetupConfirmIn, db: DB) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        user, ch = await mfa.setup_user(db, body.challenge_token)
        codes = await mfa.totp_confirm(db, user, body.code)
        return {"enabled": True, "recovery_codes": codes, **await mfa.setup_finish(db, user, ch, "totp")}

    return await _run(db, work())


@router.post("/mfa/setup/passkey/options")
async def setup_passkey_options(body: ChallengeIn, db: DB, request: Request) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        user, ch = await mfa.setup_user(db, body.challenge_token)
        return await mfa.register_options(db, user, _origin(request), setup=ch)

    return await _run(db, work())


@router.post("/mfa/setup/passkey/verify")
async def setup_passkey_verify(body: RegisterIn, db: DB, request: Request) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        user, ch = await mfa.setup_user(db, body.challenge_token)
        out = await mfa.register_verify(db, user, ch, body.credential, body.name, _origin(request))
        return {**out, **await mfa.setup_finish(db, user, ch, "passkey")}

    return await _run(db, work())


# --------------------------------------------------------------------------------------------------
# passkeys of the signed-in person
# --------------------------------------------------------------------------------------------------


@router.get("/passkeys")
async def passkeys_list(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    return await mfa.list_passkeys(db, user)


@router.post("/passkeys/register/options")
async def passkeys_register_options(body: PasswordIn, db: DB, user: CurrentUser, request: Request) -> dict[str, Any]:
    await _run(db, mfa._refuse_sso(db, user))
    await _reauth(db, user, body.password, request)
    return await _run(db, mfa.register_options(db, user, _origin(request)))


@router.post("/passkeys/register/verify", status_code=status.HTTP_201_CREATED)
async def passkeys_register_verify(body: RegisterIn, db: DB, user: CurrentUser, request: Request) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        ch = await mfa.resolve(db, body.challenge_token, "register")
        return await mfa.register_verify(db, user, ch, body.credential, body.name, _origin(request))

    return await _run(db, work())


@router.patch("/passkeys/{passkey_id}")
async def passkeys_rename(passkey_id: int, body: RenameIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    return await _run(db, mfa.rename_passkey(db, user, passkey_id, body.name))


@router.post("/passkeys/{passkey_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
async def passkeys_remove(passkey_id: int, body: PasswordIn, db: DB, user: CurrentUser, request: Request) -> Response:
    await _run(db, mfa.remove_passkey(db, user, passkey_id, body.password, recent=_recent(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------------------------------
# passkey-only sign-in (first factor; the institution switches it on)
# --------------------------------------------------------------------------------------------------


@router.post("/passkey/options")
async def passkey_sign_in_options(db: DB, request: Request) -> dict[str, Any]:
    return await _run(db, mfa.first_factor_options(db, _origin(request)))


@router.post("/passkey/verify")
async def passkey_sign_in_verify(body: CredentialIn, db: DB, request: Request) -> dict[str, Any]:
    return await _run(db, mfa.first_factor_verify(db, body.challenge_token, body.credential, _origin(request)))


# --------------------------------------------------------------------------------------------------
# trusted devices
# --------------------------------------------------------------------------------------------------


@router.get("/trusted-devices")
async def devices_list(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    return await mfa.list_devices(db, user)


@router.delete("/trusted-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def devices_revoke(device_id: int, db: DB, user: CurrentUser) -> Response:
    await _run(db, mfa.revoke_device(db, user, device_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/trusted-devices")
async def devices_revoke_all(db: DB, user: CurrentUser) -> dict[str, Any]:
    return {"revoked": await _run(db, mfa.revoke_all_devices(db, user))}


# --------------------------------------------------------------------------------------------------
# sessions (AU-15)
# --------------------------------------------------------------------------------------------------


@router.get("/sessions")
async def sessions_list(db: DB, user: CurrentUser, request: Request) -> list[dict[str, Any]]:
    """The caller's open sessions, newest first; ``current`` marks this one."""
    from app.services import sessions as user_sessions

    return await user_sessions.list_own(db, user, user_sessions.current_id(request))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def sessions_revoke(session_id: int, db: DB, user: CurrentUser) -> Response:
    from app.services import sessions as user_sessions

    await user_sessions.revoke_one(db, user, session_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-others")
async def sessions_revoke_others(db: DB, user: CurrentUser, request: Request) -> dict[str, Any]:
    """"Diğer cihazlardan çıkış yap": every session but this one."""
    from app.services import sessions as user_sessions

    n = await user_sessions.revoke_others(db, user, user_sessions.current_id(request))
    await db.commit()
    return {"revoked": n}


# --------------------------------------------------------------------------------------------------
# administrators
# --------------------------------------------------------------------------------------------------


@admin_router.get("/auth/mfa-policy")
async def policy_get(db: DB, _me: AuthAdmin) -> dict[str, Any]:
    return (await mfa.get_policy(db)).out()


@admin_router.put("/auth/mfa-policy")
async def policy_put(body: PolicyIn, db: DB, me: AuthAdmin) -> dict[str, Any]:
    policy = await _run(db, mfa.set_policy(db, me, body.model_dump(exclude_none=True)))
    return policy.out()


async def _target(db: DB, me: User, user_id: int) -> User:
    from app.api.v1.users import guard_privileged

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    await guard_privileged(db, me, target=target)
    return target


@admin_router.get("/users/{user_id}/mfa")
async def admin_user_mfa(user_id: int, db: DB, me: UsersAdmin) -> dict[str, Any]:
    return await mfa.admin_summary(db, await _target(db, me, user_id))


@admin_router.post("/users/{user_id}/mfa/reset")
async def admin_mfa_reset(user_id: int, body: AdminResetIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Remove the person's authenticator app, recovery codes, trusted devices and (unless ``keep_passkeys``) passkeys
    after checking who is asking (``identity_check``); a reason is required; audited; the person is e-mailed and
    signed out everywhere. Refused for SSO-only accounts and for one's own account."""
    target = await _target(db, me, user_id)
    return await _run(
        db,
        mfa.admin_reset(
            db,
            me,
            target,
            reason=body.reason.strip(),
            identity_check=body.identity_check,
            keep_passkeys=body.keep_passkeys,
        ),
    )


@admin_router.post("/users/{user_id}/sessions/revoke")
async def admin_sessions_revoke(user_id: int, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Sign the person out everywhere (every session row and the token version); audited."""
    from app.services import sessions as user_sessions

    target = await _target(db, me, user_id)
    n = await user_sessions.revoke_all(db, target, actor=me, reason="admin")
    await db.commit()
    return {"user_id": target.id, "revoked": n, "signed_out": True}


@admin_router.post("/users/{user_id}/password-reset-link")
async def admin_reset_link(user_id: int, body: ResetLinkIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """E-mail a one-time password reset link (local accounts only; ``sso_account`` / ``directory_account``
    otherwise). The answer never carries the token."""
    target = await _target(db, me, user_id)
    return await _run(db, mfa.send_reset_link(db, me, target, body.reason))
