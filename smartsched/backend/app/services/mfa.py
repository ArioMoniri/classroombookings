"""Two-step sign-in (AU-B, owner request 2026-10-18; docs/research/2026-10-18-auth-backend.md).

* **Policy** (settings ``auth.*``, code defaults): ``mfa_policy`` off | optional | required_for_roles, ``mfa_roles``,
  ``mfa_grace_days``, ``passkeys_enabled``, ``passkey_first_factor``.
* **Account types** (:func:`account_type`): ``local``, ``ldap``, ``mixed`` (a linked identity *and* a local password,
  the break-glass administrator) and ``sso`` (an identity provider only). SSO accounts get no local factor: the
  provider enforces MFA; administrator resets and reset links refuse them (``sso_account``).
* **Factors**: the authenticator app (TOTP, :mod:`app.core.totp`, secret Fernet-encrypted), passkeys
  (:mod:`app.services.passkeys`), ten single-use recovery codes (argon2id), trusted devices (30 days, SHA-256).
* **Challenges** (:class:`app.models.mfa.AuthChallenge`): the password step answers ``mfa_required`` with a signed
  token naming a single-use row (5 minutes, 5 tries). The token is signed with its own key, so it can never pass as a
  bearer token.
* **Lockout**: 5 consecutive second-factor failures lock the factor for 15 minutes, doubling each further 5 (cap 24 h).
* **Audit** (``auth.mfa_*``, ``auth.passkey_*``, ``auth.trusted_device_*``, ``auth.reset_link_by_admin``) and the
  security e-mails (``mail.send_kind``: mfa_enabled, mfa_disabled, mfa_app_changed, mfa_reset_by_admin, passkey_added,
  mfa_recovery_code_used, password_reset_link_by_admin). Nothing here ever returns a secret to an administrator.

The routes are in ``app/api/v1/mfa.py``; ``app/api/v1/auth.py`` calls :func:`after_password`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls, totp
from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret, user_token, verify_password
from app.models import Setting, User
from app.models.base import utcnow
from app.models.mfa import AuthChallenge, MfaRecoveryCode, TrustedDevice, UserMfa, UserSession, WebAuthnCredential
from app.schemas import messages
from app.services import audit, passkeys

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------------------------------

POLICIES = ("off", "optional", "required_for_roles")
ROLE_CODES = ("ADMIN", "PLANNER", "TEACHER", "VIEWER", "CUSTOM")
CHALLENGE_TTL = timedelta(minutes=5)
PENDING_TTL = timedelta(minutes=15)
MAX_TRIES = 5
LOCK_AFTER = 5
LOCK_BASE = timedelta(minutes=15)
LOCK_MAX = timedelta(hours=24)
TRUST_DAYS = 30
TRUST_CHOICES = (0, 7, 30)
#: a bearer token issued this recently counts as a fresh sign-in: sensitive changes need no password again
REAUTH_WINDOW = timedelta(minutes=10)
MAX_PASSKEYS = 10
IDENTITY_CHECKS = ("in_person", "video_call", "phone_callback", "other")
#: recovery codes: argon2id at OWASP's minimum (m = 19 MiB, t = 2, p = 1); 80-bit codes, single use, 10 per person
_codes_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
TRUSTED_HEADER = "x-trusted-device"


def clock() -> datetime:
    """Naive UTC now (tests move it)."""
    return utcnow()


# --------------------------------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------------------------------


class MfaError(Exception):
    def __init__(self, status: int, code: str, tr: str, en: str, headers: dict[str, str] | None = None, **extra: Any):
        super().__init__(en)
        self.status, self.code, self.tr, self.en, self.headers, self.extra = status, code, tr, en, headers, extra

    def http(self) -> HTTPException:
        exc = messages.problem(self.status, self.code, self.tr, self.en, **self.extra)
        if self.headers:
            exc.headers = self.headers
        return exc


def _expired() -> MfaError:
    return MfaError(
        401,
        "challenge_expired",
        "Doğrulama adımının süresi doldu. Yeniden giriş yapın.",
        "This verification step has expired. Sign in again.",
    )


def _invalid_code(status: int = 401) -> MfaError:
    return MfaError(status, "invalid_code", "Kod hatalı. Yeniden deneyin.", "The code is wrong. Try again.")


def _sso() -> MfaError:
    return MfaError(
        409,
        "sso_account",
        "Bu hesap kurum kimlik sağlayıcısıyla giriş yapıyor; iki aşamalı doğrulama orada yönetilir.",
        "This account signs in with the institution's identity provider; two-step verification is managed there.",
    )


def reauth_failed() -> MfaError:
    return MfaError(403, "reauth_failed", "Parola hatalı.", "The password is wrong.")


# --------------------------------------------------------------------------------------------------
# policy
# --------------------------------------------------------------------------------------------------


@dataclass
class Policy:
    mfa_policy: str = "optional"
    mfa_roles: list[str] = field(default_factory=lambda: ["ADMIN"])
    mfa_grace_days: int = 14
    passkeys_enabled: bool = True
    passkey_first_factor: bool = False
    #: "Bu cihazı hatırla": 0 (off), 7 or 30 days
    trusted_device_days: int = TRUST_DAYS

    def out(self) -> dict[str, Any]:
        return asdict(self)


_POLICY_KEYS = {
    "mfa_policy": "auth.mfa_policy",
    "mfa_roles": "auth.mfa_roles",
    "mfa_grace_days": "auth.mfa_grace_days",
    "passkeys_enabled": "auth.passkeys_enabled",
    "passkey_first_factor": "auth.passkey_first_factor",
    "trusted_device_days": "auth.trusted_device_days",
}


async def get_policy(db: AsyncSession) -> Policy:
    rows = {
        r.key: r.value
        for r in (await db.execute(select(Setting).where(Setting.key.in_(list(_POLICY_KEYS.values()))))).scalars()
    }
    p = Policy()
    try:
        if rows.get("auth.mfa_policy") in POLICIES:
            p.mfa_policy = str(rows["auth.mfa_policy"])
        if rows.get("auth.mfa_roles"):
            roles = json.loads(str(rows["auth.mfa_roles"]))
            if isinstance(roles, list):
                p.mfa_roles = [str(r) for r in roles if r in ROLE_CODES]
        if rows.get("auth.mfa_grace_days") is not None:
            p.mfa_grace_days = max(0, min(90, int(str(rows["auth.mfa_grace_days"]))))
        if rows.get("auth.trusted_device_days") is not None:
            days = int(str(rows["auth.trusted_device_days"]))
            p.trusted_device_days = days if days in TRUST_CHOICES else TRUST_DAYS
        for k in ("passkeys_enabled", "passkey_first_factor"):
            raw = rows.get(f"auth.{k}")
            if raw is not None:
                setattr(p, k, str(raw) in ("1", "true"))
    except (TypeError, ValueError):
        pass
    return p


async def set_policy(db: AsyncSession, actor: User, body: dict[str, Any]) -> Policy:
    before = await get_policy(db)
    after = Policy(**before.out())
    for k, v in body.items():
        if v is not None:
            setattr(after, k, v)
    for k, key in _POLICY_KEYS.items():
        v = getattr(after, k)
        raw = json.dumps(v) if isinstance(v, list) else ("1" if v is True else "0" if v is False else str(v))
        row = await db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=raw, is_secret=False))
        else:
            row.value = raw
    await db.flush()
    if after.out() != before.out():
        await audit.record(
            db, "auth.mfa_policy", "setting", "auth", before=before.out(), after=after.out(), actor=actor
        )
        newly = after.mfa_policy == "required_for_roles" and (
            before.mfa_policy != "required_for_roles" or set(after.mfa_roles) - set(before.mfa_roles)
        )
        if newly:
            await _announce_required(
                db, after, set() if before.mfa_policy != "required_for_roles" else set(before.mfa_roles)
            )
    return after


async def list_states(db: AsyncSession, policy: Policy | None = None) -> dict[int, dict[str, Any]]:
    """Every account's 2FA state for the Users list (AUX-F ask; a handful of queries, no per-user round trip):

    * ``mfa_state``: ``on`` (an authenticator app, or a passkey while passkeys are allowed), ``pending`` (the policy
      requires it for the role and nothing is set up), ``off``; ``None`` for an account that signs in only through an
      identity provider (its MFA is managed there: no tag);
    * ``mfa_grace_until``: for ``pending``, the end of the grace period once it started (the first sign-in after the
      policy covered the person), else ``None``.

    ``covered`` and ``active`` feed the policy counts. Never a secret, a code or a key."""
    from app.models import Role
    from app.models.sso import UserIdentity

    policy = policy or await get_policy(db)
    async with rls.system_scope(db):
        mfa_rows = {r.user_id: r for r in (await db.execute(select(UserMfa))).scalars()}
        keyed = (
            set((await db.execute(select(WebAuthnCredential.user_id).distinct())).scalars())
            if policy.passkeys_enabled
            else set()
        )
        linked = set((await db.execute(select(UserIdentity.user_id).distinct())).scalars())
        codes = {rid: str(code or "") for rid, code in await db.execute(select(Role.id, Role.code))}
        people = list((await db.execute(select(User).order_by(User.id))).scalars())
    out: dict[int, dict[str, Any]] = {}
    for u in people:
        sso_only = u.auth_source != "ldap" and not u.password_hash and (u.auth_source == "oidc" or u.id in linked)
        row = mfa_rows.get(u.id)
        on = bool(row and row.totp_secret_enc) or u.id in keyed
        role = codes.get(u.role_id, "") if u.role_id is not None else ""
        covered = (
            not sso_only
            and policy.mfa_policy == "required_for_roles"
            and ((role or str(u.role or "")) in policy.mfa_roles or u.role in policy.mfa_roles)
        )
        state: str | None = None if sso_only else ("on" if on else ("pending" if covered else "off"))
        grace = None
        if state == "pending" and row is not None and row.required_since is not None:
            grace = row.required_since + timedelta(days=policy.mfa_grace_days)
        out[u.id] = {
            "mfa_state": state,
            "mfa_grace_until": grace,
            "covered": covered,
            "active": bool(u.is_active),
        }
    return out


async def policy_out(db: AsyncSession, policy: Policy | None = None) -> dict[str, Any]:
    """The policy plus the policy screen's counts (AUX-F ask): ``required_people`` = active accounts the policy
    requires 2FA of now (``required_for_roles`` and the role; identity-provider-only accounts never), and
    ``enrolled_people`` = how many of them have a second factor. Both 0 unless the policy is ``required_for_roles``."""
    policy = policy or await get_policy(db)
    covered = [s for s in (await list_states(db, policy)).values() if s["covered"] and s["active"]]
    return {
        **policy.out(),
        "required_people": len(covered),
        "enrolled_people": sum(1 for s in covered if s["mfa_state"] == "on"),
    }


async def _announce_required(db: AsyncSession, policy: Policy, already: set[str]) -> int:
    """``mfa_required`` to every active local / LDAP person the policy now covers who has no second factor yet."""
    sent = 0
    async with rls.system_scope(db):
        people = list(
            (await db.execute(select(User).where(User.is_active.is_(True), User.email.is_not(None)))).scalars()
        )
        for u in people:
            code = await _role_code(db, u)
            if code not in policy.mfa_roles and u.role not in policy.mfa_roles:
                continue
            if code in already or u.role in already:
                continue
            if await account_type(db, u) == "sso" or await methods(db, u, policy):
                continue
            await _mail(db, u, "mfa_required", grace_days=policy.mfa_grace_days)
            sent += 1
    return sent


# --------------------------------------------------------------------------------------------------
# accounts
# --------------------------------------------------------------------------------------------------


async def account_type(db: AsyncSession, user: User) -> str:
    """``local`` | ``ldap`` | ``mixed`` (identity + local password) | ``sso`` (identity provider only)."""
    from app.models.sso import UserIdentity

    if user.auth_source == "ldap":
        return "ldap"
    async with rls.system_scope(db):
        linked = (
            await db.execute(select(func.count(UserIdentity.id)).where(UserIdentity.user_id == user.id))
        ).scalar_one()
    has_password = bool(user.password_hash)
    if user.auth_source == "oidc" or linked:
        return "mixed" if has_password else "sso"
    return "local"


async def _refuse_sso(db: AsyncSession, user: User) -> None:
    if await account_type(db, user) == "sso":
        raise _sso()


async def reauth(db: AsyncSession, user: User, password: str | None, *, recent: bool = False) -> bool:
    """Re-authentication for a sensitive change: the local password, or the directory for an LDAP account. Without a
    password, a session younger than :data:`REAUTH_WINDOW` (``recent``) counts; a password that is given must be
    right."""
    if not password:
        return recent
    if user.auth_source == "ldap":
        from app.services import bookings_ldap

        res = await bookings_ldap.authenticate(db, user.username or "", password)
        if res.ok:
            return True
    return bool(user.password_hash) and verify_password(password, user.password_hash or "")


async def _role_code(db: AsyncSession, user: User) -> str:
    if user.role_id is not None:
        from app.models import Role

        role = await db.get(Role, user.role_id)
        if role is not None and role.code:
            return str(role.code)
    return str(user.role or "")


async def required_for(db: AsyncSession, user: User, policy: Policy | None = None) -> bool:
    policy = policy or await get_policy(db)
    if policy.mfa_policy != "required_for_roles":
        return False
    if await account_type(db, user) == "sso":
        return False
    return (await _role_code(db, user)) in policy.mfa_roles or user.role in policy.mfa_roles


async def _row(db: AsyncSession, user_id: int, *, create: bool = False) -> UserMfa | None:
    row = await db.get(UserMfa, user_id)
    if row is None and create:
        row = UserMfa(user_id=user_id, failed_count=0)
        db.add(row)
        await db.flush()
    return row


async def _passkeys(db: AsyncSession, user_id: int) -> list[WebAuthnCredential]:
    q = select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id).order_by(WebAuthnCredential.id)
    return list((await db.execute(q)).scalars())


async def _codes_left(db: AsyncSession, user_id: int) -> tuple[int, int]:
    rows = list((await db.execute(select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))).scalars())
    return sum(1 for r in rows if r.used_at is None), len(rows)


async def methods(db: AsyncSession, user: User, policy: Policy | None = None) -> list[str]:
    """The second factors ``user`` can answer a challenge with now."""
    policy = policy or await get_policy(db)
    row = await _row(db, user.id)
    out: list[str] = []
    if row is not None and row.totp_secret_enc:
        out.append("totp")
    keys = await _passkeys(db, user.id) if policy.passkeys_enabled else []
    if out or keys:
        left, _ = await _codes_left(db, user.id)
        if left:
            out.append("recovery")
    if keys:
        out.append("passkey")
    return out


# --------------------------------------------------------------------------------------------------
# challenge tokens
# --------------------------------------------------------------------------------------------------


def _challenge_key() -> bytes:
    return hashlib.sha256(b"smartsched-auth-challenge:" + get_settings().signing_key.encode("utf-8")).digest()


async def issue_challenge(
    db: AsyncSession,
    user_id: int | None,
    purpose: str,
    *,
    challenge: bytes | None = None,
    data: dict[str, Any] | None = None,
) -> tuple[str, AuthChallenge]:
    now = clock()
    jti = secrets.token_urlsafe(24)
    row = AuthChallenge(
        jti=jti,
        user_id=user_id,
        purpose=purpose,
        challenge=passkeys.b64(challenge) if challenge else None,
        data=dict(data or {}),
        attempts=0,
        created_at=now,
        expires_at=now + CHALLENGE_TTL,
    )
    db.add(row)
    await db.flush()
    exp = time.time() + CHALLENGE_TTL.total_seconds()
    token = jwt.encode({"typ": "ss-challenge", "p": purpose, "j": jti, "exp": int(exp)}, _challenge_key(), "HS256")
    return token, row


async def resolve(db: AsyncSession, token: str | None, *purposes: str) -> AuthChallenge:
    """The open challenge row of ``token`` (one of ``purposes``), else ``challenge_expired``."""
    try:
        claims = jwt.decode(token or "", _challenge_key(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise _expired() from exc
    if claims.get("typ") != "ss-challenge" or claims.get("p") not in purposes:
        raise _expired()
    row = (
        await db.execute(select(AuthChallenge).where(AuthChallenge.jti == str(claims.get("j"))))
    ).scalar_one_or_none()
    if row is None or row.purpose not in purposes or row.used_at is not None or row.expires_at <= clock():
        raise _expired()
    if row.attempts >= MAX_TRIES:
        raise _expired()
    return row


async def _challenge_user(db: AsyncSession, ch: AuthChallenge) -> User:
    user = await db.get(User, ch.user_id) if ch.user_id else None
    if user is None or not user.is_active:
        raise _expired()
    return user


def _expires_in(ch: AuthChallenge) -> int:
    return max(1, int((ch.expires_at - clock()).total_seconds()))


# --------------------------------------------------------------------------------------------------
# lockout
# --------------------------------------------------------------------------------------------------


def _locked(row: UserMfa | None) -> MfaError | None:
    if row is None or row.locked_until is None or row.locked_until <= clock():
        return None
    wait = max(1, int((row.locked_until - clock()).total_seconds()))
    mins = max(1, (wait + 59) // 60)
    return MfaError(
        429,
        "mfa_locked",
        f"Çok fazla hatalı kod girildi. {mins} dakika sonra yeniden deneyin.",
        f"Too many wrong codes. Try again in {mins} minute(s).",
        headers={"Retry-After": str(wait)},
        retry_after=wait,
    )


async def _check_lock(db: AsyncSession, user_id: int) -> None:
    err = _locked(await _row(db, user_id))
    if err is not None:
        raise err


async def _fail(db: AsyncSession, user: User, ch: AuthChallenge | None, method: str) -> None:
    """Count one failed second-factor attempt (the caller commits, then raises)."""
    row = await _row(db, user.id, create=True)
    assert row is not None
    row.failed_count = int(row.failed_count or 0) + 1
    if ch is not None:
        ch.attempts = int(ch.attempts or 0) + 1
        if ch.attempts >= MAX_TRIES:
            ch.used_at = clock()
    await audit.record(
        db, "auth.mfa_failed", "user", user.id, after={"method": method, "failed_count": row.failed_count}, actor=user
    )
    if row.failed_count % LOCK_AFTER == 0:
        n = row.failed_count // LOCK_AFTER
        lock = min(LOCK_BASE * (2 ** (n - 1)), LOCK_MAX)
        row.locked_until = clock() + lock
        await audit.record(
            db,
            "auth.mfa_locked",
            "user",
            user.id,
            after={"failed_count": row.failed_count, "minutes": int(lock.total_seconds() // 60)},
            actor=user,
        )
    await db.flush()


async def _succeed(db: AsyncSession, user_id: int) -> None:
    row = await _row(db, user_id)
    if row is not None:
        row.failed_count, row.locked_until = 0, None


# --------------------------------------------------------------------------------------------------
# e-mails
# --------------------------------------------------------------------------------------------------


async def _when(db: AsyncSession, user: User) -> str:
    from datetime import UTC

    from app.services import bookings_i18n, mail, mail_senders

    lang = await mail.resolve_locale(db, None, user)
    fmt = await bookings_i18n.formatter(db, lang)
    local = clock().replace(tzinfo=UTC).astimezone(await mail_senders._tz(db)).replace(tzinfo=None)
    return f"{fmt.long(local.date())} {fmt.time(local.time())}"


async def _mail(db: AsyncSession, user: User, kind: str, *, link: str = "/profile#security", **ctx: Any) -> None:
    if not user.email:
        return
    from app.services import mail

    try:
        ctx.setdefault("when", await _when(db, user))
        await mail.send_kind(db, kind, to_email=user.email, user=user, link=link, **ctx)
    except Exception:  # a broken template or mail setting never blocks a security change; the audit row stays
        log.exception("could not queue the %s e-mail for user %s", kind, user.id)


def _label(user: User | None) -> str:
    return audit.user_label(user) or ""


# --------------------------------------------------------------------------------------------------
# sign-in
# --------------------------------------------------------------------------------------------------


async def finish_sign_in(db: AsyncSession, user: User, auth_method: str) -> dict[str, Any]:
    """Session for ``user`` after every required step (the caller commits)."""
    from app.services import bookings_events as events

    user.last_login_at = utcnow()
    await events.emit(db, "user.logged_in", {"user_id": user.id, "auth_method": auth_method})
    return {
        "access_token": user_token(user),
        "token_type": "bearer",
        "expires_in": get_settings().jwt_expire_minutes * 60,
        "password_change_required": bool(user.force_password_reset and auth_method == "local"),
    }


@dataclass
class Gate:
    """What the password step does next: ``pass`` (a session, ``extra`` may carry the grace notice), ``challenge``
    (second factor) or ``setup`` (the policy requires enrolment first)."""

    kind: str
    extra: dict[str, Any] = field(default_factory=dict)


async def _trusted(db: AsyncSession, user: User, token: str | None, policy: Policy) -> bool:
    if not token or len(token) > 200 or not policy.trusted_device_days:
        return False
    h = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = (await db.execute(select(TrustedDevice).where(TrustedDevice.token_hash == h))).scalar_one_or_none()
    now = clock()
    if row is None or row.user_id != user.id or row.revoked_at is not None or row.expires_at <= now:
        return False
    row.last_used_at = now
    return True


async def _rp_ok(db: AsyncSession) -> bool:
    return await passkeys.relying_party(db) is not None


async def after_password(db: AsyncSession, user: User, auth_method: str, trusted_token: str | None = None) -> Gate:
    """Called by ``POST /auth/login`` once the password (local or LDAP) is right and the account may sign in."""
    policy = await get_policy(db)
    if policy.mfa_policy == "off" or await account_type(db, user) == "sso":
        return Gate("pass")
    have = await methods(db, user, policy)
    if have:
        if await _trusted(db, user, trusted_token, policy):
            await audit.record(db, "auth.trusted_device_used", "user", user.id, actor=user)
            return Gate("pass")
        token, ch = await issue_challenge(db, user.id, "mfa", data={"auth_method": auth_method})
        return Gate(
            "challenge",
            {
                "mfa_required": True,
                "challenge_token": token,
                "challenge_expires_in": _expires_in(ch),
                "mfa_methods": have,
            },
        )
    if not await required_for(db, user, policy):
        return Gate("pass")
    row = await _row(db, user.id, create=True)
    assert row is not None
    now = clock()
    if row.required_since is None:
        row.required_since = now
    until = row.required_since + timedelta(days=policy.mfa_grace_days)
    setup_methods = ["totp"] + (["passkey"] if policy.passkeys_enabled and await _rp_ok(db) else [])
    if now < until:
        return Gate("pass", {"mfa_setup_required": True, "mfa_grace_until": until, "mfa_setup_methods": setup_methods})
    token, ch = await issue_challenge(db, user.id, "setup", data={"auth_method": auth_method})
    return Gate(
        "setup",
        {
            "mfa_setup_required": True,
            "mfa_grace_until": until,
            "mfa_setup_methods": setup_methods,
            "challenge_token": token,
            "challenge_expires_in": _expires_in(ch),
        },
    )


async def _trust_device(db: AsyncSession, user: User) -> dict[str, Any]:
    from app.services import mail_senders

    days = (await get_policy(db)).trusted_device_days
    if not days:
        return {"trusted_device_token": None, "trusted_device_days": 0}
    token = secrets.token_urlsafe(32)
    now = clock()
    label = mail_senders.device_label(db.info.get(mail_senders.UA_KEY), "tr")[:120]
    row = TrustedDevice(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        label=label,
        created_at=now,
        expires_at=now + timedelta(days=days),
    )
    db.add(row)
    await db.flush()
    await audit.record(db, "auth.trusted_device_added", "user", user.id, after={"label": label}, actor=user)
    return {"trusted_device_token": token, "trusted_device_days": days}


async def verify_code(
    db: AsyncSession, token: str, method: str, code: str, *, trust_device: bool = False
) -> dict[str, Any]:
    """Second step with the authenticator app (``totp``) or a recovery code (``recovery``)."""
    ch = await resolve(db, token, "mfa")
    user = await _challenge_user(db, ch)
    await _check_lock(db, user.id)
    row = await _row(db, user.id)
    remaining: int | None = None
    if method == "totp":
        if row is None or not row.totp_secret_enc:
            await _fail(db, user, ch, method)
            raise _invalid_code()
        step = totp.match(decrypt_secret(row.totp_secret_enc), code, last_step=row.totp_last_step)
        if step is None:
            await _fail(db, user, ch, method)
            raise _invalid_code()
        row.totp_last_step = step
    elif method == "recovery":
        remaining = await _use_recovery(db, user, code)
        if remaining is None:
            await _fail(db, user, ch, method)
            raise _invalid_code()
    else:
        raise MfaError(422, "invalid_method", "Bu doğrulama yöntemi desteklenmiyor.", "Unsupported method.")
    return await _complete(db, user, ch, method, trust_device=trust_device, remaining=remaining)


async def _complete(
    db: AsyncSession,
    user: User,
    ch: AuthChallenge,
    method: str,
    *,
    trust_device: bool = False,
    remaining: int | None = None,
) -> dict[str, Any]:
    ch.used_at = clock()
    await _succeed(db, user.id)
    await audit.record(db, "auth.mfa_verified", "user", user.id, after={"method": method}, actor=user)
    out = await finish_sign_in(db, user, str((ch.data or {}).get("auth_method") or "local"))
    if trust_device:
        out.update(await _trust_device(db, user))
    if remaining is not None:
        out["recovery_codes_remaining"] = remaining
        await audit.record(db, "auth.mfa_recovery_used", "user", user.id, after={"remaining": remaining}, actor=user)
        await _mail(db, user, "mfa_recovery_code_used", remaining=remaining)
    return out


# --------------------------------------------------------------------------------------------------
# recovery codes
# --------------------------------------------------------------------------------------------------


async def _issue_recovery(db: AsyncSession, user_id: int) -> list[str]:
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
    codes = totp.new_recovery_codes()
    now = clock()
    for c in codes:
        db.add(MfaRecoveryCode(user_id=user_id, code_hash=_codes_hasher.hash(c.replace("-", "")), created_at=now))
    await db.flush()
    return codes


async def _use_recovery(db: AsyncSession, user: User, typed: str | None) -> int | None:
    """Spend a recovery code; the number left, or ``None`` when it matches no unused code."""
    canon = totp.normalise_recovery(typed)
    rows = list(
        (
            await db.execute(
                select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
            )
        ).scalars()
    )
    hit: MfaRecoveryCode | None = None
    for r in rows:
        try:
            if canon is not None and _codes_hasher.verify(r.code_hash, canon):
                hit = r
        except VerifyMismatchError:
            continue
        except Exception:  # a malformed stored hash never matches
            continue
    if hit is None:
        return None
    hit.used_at = clock()
    return len(rows) - 1


async def regenerate_recovery(db: AsyncSession, user: User, password: str | None, *, recent: bool = False) -> list[str]:
    await _refuse_sso(db, user)
    if not await reauth(db, user, password, recent=recent):
        raise reauth_failed()
    if not await methods(db, user):
        raise _not_enabled()
    codes = await _issue_recovery(db, user.id)
    await audit.record(db, "auth.mfa_recovery_regenerated", "user", user.id, after={"count": len(codes)}, actor=user)
    await _mail(db, user, "recovery_codes_regenerated")
    return codes


def _not_enabled() -> MfaError:
    return MfaError(409, "not_enabled", "İki aşamalı doğrulama açık değil.", "Two-step verification is not turned on.")


# --------------------------------------------------------------------------------------------------
# TOTP enrolment
# --------------------------------------------------------------------------------------------------


async def _enrolment_allowed(db: AsyncSession, user: User, policy: Policy) -> None:
    await _refuse_sso(db, user)
    if policy.mfa_policy == "off":
        raise MfaError(
            409,
            "mfa_off",
            "Kurumunuz iki aşamalı doğrulamayı kapattı.",
            "Your institution has turned two-step verification off.",
        )


async def totp_start(db: AsyncSession, user: User) -> dict[str, Any]:
    """Begin authenticator-app enrolment (the caller re-authenticated): a new secret and its ``otpauth://`` URI.

    With an app already on this starts a change ("Uygulamayı değiştir", ``replacing: true``): the new secret waits as
    the pending one and the old app keeps signing in until :func:`totp_confirm` gets a code from the new app; an
    abandoned change simply expires after :data:`PENDING_TTL`."""
    from app.services.bookings_settings import get_value

    policy = await get_policy(db)
    await _enrolment_allowed(db, user, policy)
    row = await _row(db, user.id, create=True)
    assert row is not None
    replacing = bool(row.totp_secret_enc)
    secret = totp.new_secret()
    row.totp_pending_enc, row.totp_pending_at = encrypt_secret(secret), clock()
    issuer = str(await get_value(db, "org", "name") or "").strip() or "SmartSched"
    account = user.email or user.username or f"user-{user.id}"
    await audit.record(
        db, "auth.mfa_app_change_started" if replacing else "auth.mfa_enrolment_started", "user", user.id, actor=user
    )
    return {
        "replacing": replacing,
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, account, issuer),
        "issuer": issuer,
        "account": account,
        "digits": totp.DIGITS,
        "period": totp.PERIOD,
        "algorithm": "SHA1",
        "expires_in": int(PENDING_TTL.total_seconds()),
    }


async def totp_on(db: AsyncSession, user: User) -> bool:
    row = await _row(db, user.id)
    return bool(row and row.totp_secret_enc)


async def totp_confirm(db: AsyncSession, user: User, code: str) -> list[str]:
    """Finish enrolment with a code from the app: TOTP on, ten new recovery codes (returned once). When an app was
    already on (a change), the new one replaces it, the recovery codes and trusted devices stay (``[]`` is returned),
    and the person gets ``mfa_app_changed`` instead of ``mfa_enabled``."""
    row = await _row(db, user.id)
    if (
        row is None
        or not row.totp_pending_enc
        or not row.totp_pending_at
        or row.totp_pending_at + PENDING_TTL < clock()
    ):
        raise MfaError(
            409,
            "enrolment_expired",
            "Kurulumun süresi doldu. Yeniden başlayın.",
            "The set-up has expired. Start again.",
        )
    secret = decrypt_secret(row.totp_pending_enc)
    step = totp.match(secret, code)
    if step is None:
        raise _invalid_code(422)
    replacing = bool(row.totp_secret_enc)
    row.totp_secret_enc, row.totp_enabled_at, row.totp_last_step = row.totp_pending_enc, clock(), step
    row.totp_pending_enc = row.totp_pending_at = None
    if replacing:
        await audit.record(db, "auth.mfa_app_changed", "user", user.id, after={"method": "totp"}, actor=user)
        await _mail(db, user, "mfa_app_changed")
        return []
    codes = await _issue_recovery(db, user.id)
    await audit.record(db, "auth.mfa_enabled", "user", user.id, after={"method": "totp"}, actor=user)
    await _mail(db, user, "mfa_enabled")
    return codes


async def disable(
    db: AsyncSession, user: User, password: str | None, code: str | None, *, recent: bool = False
) -> dict[str, Any]:
    """Turn the authenticator app off (password + a current code or a recovery code). Recovery codes and trusted
    devices go with it; passkeys stay (removed one by one)."""
    await _refuse_sso(db, user)
    if not await reauth(db, user, password, recent=recent):
        raise reauth_failed()
    if await required_for(db, user):
        raise MfaError(
            409,
            "mfa_required_by_policy",
            "Kurumunuz bu rol için iki aşamalı doğrulamayı zorunlu tutuyor; kapatılamaz.",
            "Your institution requires two-step verification for this role; it cannot be turned off.",
        )
    row = await _row(db, user.id)
    if row is None or not row.totp_secret_enc:
        raise _not_enabled()
    await _check_lock(db, user.id)
    step = totp.match(decrypt_secret(row.totp_secret_enc), code, last_step=row.totp_last_step)
    if step is None and await _use_recovery(db, user, code) is None:
        await _fail(db, user, None, "disable")
        raise _invalid_code(422)
    row.totp_secret_enc = row.totp_enabled_at = row.totp_last_step = None
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    devices = await _revoke_devices(db, user.id)
    await _succeed(db, user.id)
    await audit.record(db, "auth.mfa_disabled", "user", user.id, after={"trusted_devices": devices}, actor=user)
    await _mail(db, user, "mfa_disabled")
    left = len(await _passkeys(db, user.id))
    return {"disabled": True, "passkeys_remaining": left}


# --------------------------------------------------------------------------------------------------
# setup forced by the policy (enrolment token instead of a session)
# --------------------------------------------------------------------------------------------------


async def setup_user(db: AsyncSession, token: str) -> tuple[User, AuthChallenge]:
    ch = await resolve(db, token, "setup")
    return await _challenge_user(db, ch), ch


async def setup_finish(db: AsyncSession, user: User, ch: AuthChallenge, method: str) -> dict[str, Any]:
    ch.used_at = clock()
    await audit.record(db, "auth.mfa_verified", "user", user.id, after={"method": method, "setup": True}, actor=user)
    return await finish_sign_in(db, user, str((ch.data or {}).get("auth_method") or "local"))


# --------------------------------------------------------------------------------------------------
# passkeys
# --------------------------------------------------------------------------------------------------


def _passkeys_off() -> MfaError:
    return MfaError(
        409, "passkeys_off", "Kurumunuz geçiş anahtarlarını kapattı.", "Your institution has turned passkeys off."
    )


def _unavailable() -> MfaError:
    return MfaError(
        409,
        "passkeys_unavailable",
        "Geçiş anahtarları için panelin genel adresi (https) ayarlanmalı.",
        "Passkeys need the panel's public https address to be set.",
    )


def _passkey_invalid(status: int = 422) -> MfaError:
    return MfaError(
        status,
        "passkey_invalid",
        "Geçiş anahtarı doğrulanamadı. Yeniden deneyin.",
        "The passkey could not be verified. Try again.",
    )


async def _rp(db: AsyncSession, origin: str | None) -> passkeys.RelyingParty:
    rp = await passkeys.relying_party(db, origin)
    if rp is None:
        raise _unavailable()
    return rp


async def _handle(db: AsyncSession, user: User) -> bytes:
    row = await _row(db, user.id, create=True)
    assert row is not None
    if not row.webauthn_user_handle:
        row.webauthn_user_handle = passkeys.b64(secrets.token_bytes(32))
    return passkeys.unb64(row.webauthn_user_handle)


def passkey_out(c: WebAuthnCredential) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "transports": list(c.transports or []),
        "backed_up": bool(c.backed_up),
        "created_at": c.created_at,
        "last_used_at": c.last_used_at,
    }


async def list_passkeys(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    return [passkey_out(c) for c in await _passkeys(db, user.id)]


async def register_options(
    db: AsyncSession, user: User, origin: str | None, *, setup: AuthChallenge | None = None
) -> dict[str, Any]:
    policy = await get_policy(db)
    await _enrolment_allowed(db, user, policy)
    if not policy.passkeys_enabled:
        raise _passkeys_off()
    rp = await _rp(db, origin)
    existing = await _passkeys(db, user.id)
    if len(existing) >= MAX_PASSKEYS:
        raise MfaError(409, "passkey_limit", "En fazla 10 geçiş anahtarı eklenebilir.", "At most 10 passkeys.")
    challenge = passkeys.new_challenge()
    options = passkeys.registration_options(
        rp,
        user_handle=await _handle(db, user),
        user_name=user.email or user.username or f"user-{user.id}",
        display_name=user.full_name or " ".join(x for x in (user.firstname, user.lastname) if x) or "",
        challenge=challenge,
        exclude=[(c.credential_id, list(c.transports or [])) for c in existing],
    )
    if setup is not None:
        setup.challenge = passkeys.b64(challenge)
        return {"options": options}
    token, _ch = await issue_challenge(db, user.id, "register", challenge=challenge)
    return {"challenge_token": token, "options": options}


async def register_verify(
    db: AsyncSession, user: User, ch: AuthChallenge, credential: dict[str, Any], name: str | None, origin: str | None
) -> dict[str, Any]:
    if ch.user_id != user.id or not ch.challenge:
        raise _expired()
    rp = await _rp(db, origin)
    ch.used_at = clock()  # single use, also when it fails
    try:
        reg = passkeys.verify_registration(rp, credential, passkeys.unb64(ch.challenge))
    except passkeys.CeremonyError as exc:
        log.info("passkey registration refused for user %s: %s", user.id, exc)
        raise _passkey_invalid() from exc
    clash = (
        await db.execute(select(WebAuthnCredential.id).where(WebAuthnCredential.credential_id == reg.credential_id))
    ).scalar_one_or_none()
    if clash is not None:
        raise MfaError(409, "passkey_exists", "Bu geçiş anahtarı zaten kayıtlı.", "This passkey is already registered.")
    first = not await methods(db, user)
    label = (name or "").strip()[:64] or "Geçiş anahtarı"
    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=reg.credential_id,
        public_key=reg.public_key,
        sign_count=reg.sign_count,
        transports=reg.transports,
        name=label,
        aaguid=reg.aaguid,
        backup_eligible=reg.backup_eligible,
        backed_up=reg.backed_up,
        created_at=clock(),
    )
    db.add(cred)
    await db.flush()
    out: dict[str, Any] = {"passkey": passkey_out(cred)}
    left, _total = await _codes_left(db, user.id)
    if first and not left:
        out["recovery_codes"] = await _issue_recovery(db, user.id)
    await audit.record(
        db, "auth.passkey_added", "user", user.id, after={"name": label, "backed_up": reg.backed_up}, actor=user
    )
    await _mail(db, user, "passkey_added", device=label)
    return out


async def rename_passkey(db: AsyncSession, user: User, pid: int, name: str) -> dict[str, Any]:
    c = await db.get(WebAuthnCredential, pid)
    if c is None or c.user_id != user.id:
        raise MfaError(404, "not_found", "Geçiş anahtarı bulunamadı.", "Passkey not found.")
    before = c.name
    c.name = name.strip()[:64] or c.name
    await audit.record(db, "auth.passkey_renamed", "user", user.id, before={"name": before}, after={"name": c.name})
    return passkey_out(c)


async def remove_passkey(db: AsyncSession, user: User, pid: int, password: str | None, *, recent: bool = False) -> None:
    c = await db.get(WebAuthnCredential, pid)
    if c is None or c.user_id != user.id:
        raise MfaError(404, "not_found", "Geçiş anahtarı bulunamadı.", "Passkey not found.")
    if not await reauth(db, user, password, recent=recent):
        raise reauth_failed()
    row = await _row(db, user.id)
    others = len(await _passkeys(db, user.id)) - 1
    if others == 0 and not (row and row.totp_secret_enc) and await required_for(db, user):
        raise MfaError(
            409,
            "mfa_required_by_policy",
            "Bu son doğrulama yönteminiz; kurumunuz bu rol için zorunlu tutuyor.",
            "This is your last second factor and your institution requires one for this role.",
        )
    await db.delete(c)
    await audit.record(db, "auth.passkey_removed", "user", user.id, after={"name": c.name}, actor=user)
    await _mail(db, user, "passkey_removed", device=c.name)


async def _assert(
    db: AsyncSession,
    user: User,
    ch: AuthChallenge,
    credential: dict[str, Any],
    origin: str | None,
    *,
    require_uv: bool,
) -> WebAuthnCredential:
    rp = await _rp(db, origin)
    cid = passkeys.credential_id_of(credential)
    cred = (
        (
            await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cid))
        ).scalar_one_or_none()
        if cid
        else None
    )
    if cred is None or cred.user_id != user.id or not ch.challenge:
        await _fail(db, user, ch, "passkey")
        raise _passkey_invalid(401)
    try:
        count = passkeys.verify_assertion(
            rp,
            credential,
            passkeys.unb64(ch.challenge),
            public_key=cred.public_key,
            sign_count=cred.sign_count,
            require_uv=require_uv,
        )
    except passkeys.CeremonyError as exc:
        if exc.counter:
            await audit.record(db, "auth.passkey_counter_error", "user", user.id, after={"name": cred.name}, actor=user)
        await _fail(db, user, ch, "passkey")
        raise _passkey_invalid(401) from exc
    cred.sign_count, cred.last_used_at = count, clock()
    return cred


async def mfa_passkey_options(db: AsyncSession, token: str, origin: str | None) -> dict[str, Any]:
    ch = await resolve(db, token, "mfa")
    user = await _challenge_user(db, ch)
    policy = await get_policy(db)
    if not policy.passkeys_enabled:
        raise _passkeys_off()
    rp = await _rp(db, origin)
    creds = await _passkeys(db, user.id)
    if not creds:
        raise MfaError(409, "no_passkeys", "Hesabınızda geçiş anahtarı yok.", "Your account has no passkey.")
    challenge = passkeys.new_challenge()
    ch.challenge = passkeys.b64(challenge)
    allow = [(c.credential_id, list(c.transports or [])) for c in creds]
    return {"options": passkeys.authentication_options(rp, challenge=challenge, allow=allow, require_uv=False)}


async def mfa_passkey_verify(
    db: AsyncSession, token: str, credential: dict[str, Any], origin: str | None, *, trust_device: bool = False
) -> dict[str, Any]:
    ch = await resolve(db, token, "mfa")
    user = await _challenge_user(db, ch)
    await _check_lock(db, user.id)
    await _assert(db, user, ch, credential, origin, require_uv=False)
    return await _complete(db, user, ch, "passkey", trust_device=trust_device)


async def first_factor_options(db: AsyncSession, origin: str | None) -> dict[str, Any]:
    policy = await get_policy(db)
    if not (policy.passkeys_enabled and policy.passkey_first_factor) or policy.mfa_policy == "off":
        raise MfaError(
            409,
            "passkey_sign_in_off",
            "Geçiş anahtarıyla giriş bu kurumda açık değil.",
            "Passkey sign-in is not turned on at this institution.",
        )
    rp = await _rp(db, origin)
    challenge = passkeys.new_challenge()
    token, ch = await issue_challenge(db, None, "passkey", challenge=challenge)
    return {
        "challenge_token": token,
        "challenge_expires_in": _expires_in(ch),
        "options": passkeys.authentication_options(rp, challenge=challenge, allow=[], require_uv=True),
    }


async def first_factor_verify(
    db: AsyncSession, token: str, credential: dict[str, Any], origin: str | None
) -> dict[str, Any]:
    """Passkey-only sign-in: the credential names the account; user verification is required."""
    ch = await resolve(db, token, "passkey")
    cid = passkeys.credential_id_of(credential)
    cred = (
        (
            await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cid))
        ).scalar_one_or_none()
        if cid
        else None
    )
    user = await db.get(User, cred.user_id) if cred is not None else None
    if user is None or not user.is_active or await account_type(db, user) == "sso":
        ch.attempts = int(ch.attempts or 0) + 1
        if user is not None and not user.is_active:
            await audit.record(
                db,
                "auth.login_refused",
                "user",
                user.id,
                after={"reason": "account disabled", "auth_method": "passkey"},
            )
        raise _passkey_invalid(401)
    await _check_lock(db, user.id)
    await _assert(db, user, ch, credential, origin, require_uv=True)
    ch.used_at = clock()
    await _succeed(db, user.id)
    await audit.record(db, "auth.login", "user", user.id, after={"auth_method": "passkey"}, actor=user)
    return await finish_sign_in(db, user, "passkey")


# --------------------------------------------------------------------------------------------------
# trusted devices
# --------------------------------------------------------------------------------------------------


def device_out(d: TrustedDevice) -> dict[str, Any]:
    return {
        "id": d.id,
        "label": d.label,
        "created_at": d.created_at,
        "expires_at": d.expires_at,
        "last_used_at": d.last_used_at,
    }


async def _open_devices(db: AsyncSession, user_id: int) -> list[TrustedDevice]:
    q = (
        select(TrustedDevice)
        .where(TrustedDevice.user_id == user_id, TrustedDevice.revoked_at.is_(None), TrustedDevice.expires_at > clock())
        .order_by(TrustedDevice.id)
    )
    return list((await db.execute(q)).scalars())


async def list_devices(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    return [device_out(d) for d in await _open_devices(db, user.id)]


async def revoke_device(db: AsyncSession, user: User, device_id: int) -> None:
    d = await db.get(TrustedDevice, device_id)
    if d is None or d.user_id != user.id or d.revoked_at is not None:
        raise MfaError(404, "not_found", "Cihaz bulunamadı.", "Device not found.")
    d.revoked_at = clock()
    await audit.record(db, "auth.trusted_device_revoked", "user", user.id, after={"label": d.label}, actor=user)


async def _revoke_devices(db: AsyncSession, user_id: int) -> int:
    rows = await _open_devices(db, user_id)
    now = clock()
    for d in rows:
        d.revoked_at = now
    return len(rows)


async def revoke_all_devices(db: AsyncSession, user: User) -> int:
    n = await _revoke_devices(db, user.id)
    await audit.record(db, "auth.trusted_device_revoked", "user", user.id, after={"all": True, "count": n}, actor=user)
    return n


# --------------------------------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------------------------------


async def status(db: AsyncSession, user: User) -> dict[str, Any]:
    policy = await get_policy(db)
    kind = await account_type(db, user)
    row = await _row(db, user.id)
    left, total = await _codes_left(db, user.id)
    required = await required_for(db, user, policy)
    grace = None
    if required and row is not None and row.required_since is not None:
        grace = row.required_since + timedelta(days=policy.mfa_grace_days)
    available = kind != "sso" and policy.mfa_policy != "off"
    return {
        "available": available,
        "reason": "sso_account" if kind == "sso" else ("mfa_off" if policy.mfa_policy == "off" else None),
        "account_type": kind,
        "policy": policy.out(),
        "passkeys_available": available and policy.passkeys_enabled and await _rp_ok(db),
        "required": required,
        "grace_until": grace,
        "totp": {
            "enabled": bool(row and row.totp_secret_enc),
            "enabled_at": row.totp_enabled_at if row else None,
            # "Uygulamayı değiştir" started and not confirmed yet (the old app still signs in)
            "change_pending": bool(
                row
                and row.totp_secret_enc
                and row.totp_pending_enc
                and row.totp_pending_at
                and row.totp_pending_at + PENDING_TTL >= clock()
            ),
        },
        "recovery_codes": {"remaining": left, "total": total},
        "passkeys": await list_passkeys(db, user),
        "trusted_devices": await list_devices(db, user),
        "locked_until": row.locked_until if row and row.locked_until and row.locked_until > clock() else None,
        "password_min_length": await password_min_length(db, user),
    }


# --------------------------------------------------------------------------------------------------
# administrators
# --------------------------------------------------------------------------------------------------


async def admin_summary(db: AsyncSession, target: User) -> dict[str, Any]:
    """What an administrator may see: on / off, counts, passkey names and dates. Never a secret, a code or a key."""
    async with rls.system_scope(db):
        kind = await account_type(db, target)
        row = await _row(db, target.id)
        left, _total = await _codes_left(db, target.id)
        keys = await _passkeys(db, target.id)
        devices = await _open_devices(db, target.id)
    return {
        "user_id": target.id,
        "account_type": kind,
        "totp_enabled": bool(row and row.totp_secret_enc),
        "totp_enabled_at": row.totp_enabled_at if row else None,
        "recovery_codes_remaining": left,
        "passkeys": [{"name": k.name, "created_at": k.created_at, "last_used_at": k.last_used_at} for k in keys],
        "trusted_devices": len(devices),
        "locked_until": row.locked_until if row and row.locked_until and row.locked_until > clock() else None,
        "can_reset_mfa": kind != "sso",
        "can_send_reset_link": kind in ("local", "mixed") and bool(target.email),
    }


async def admin_reset(
    db: AsyncSession, actor: User, target: User, *, reason: str, identity_check: str, keep_passkeys: bool = False
) -> dict[str, Any]:
    """Remove a person's second factors after the administrator checked who is asking (ASVS 6.4.4)."""
    if target.id == actor.id:
        raise MfaError(
            409,
            "own_account",
            "Kendi hesabınızı Profil › Güvenlik bölümünden yönetin.",
            "Manage your own account under Profile › Security.",
        )
    if await account_type(db, target) == "sso":
        raise MfaError(
            409,
            "sso_account",
            "Bu hesap kimlik sağlayıcısıyla giriş yapıyor; iki aşamalı doğrulamayı kimlik sağlayıcıda sıfırlayın.",
            "This account signs in with an identity provider; reset two-step verification there.",
        )
    async with rls.system_scope(db):
        row = await _row(db, target.id)
        had_totp = bool(row and row.totp_secret_enc)
        if row is not None:
            row.totp_secret_enc = row.totp_enabled_at = row.totp_last_step = None
            row.totp_pending_enc = row.totp_pending_at = None
            row.failed_count, row.locked_until = 0, None
            row.required_since = clock() if row.required_since is not None else None  # a fresh grace period
        codes = (
            await db.execute(select(func.count(MfaRecoveryCode.id)).where(MfaRecoveryCode.user_id == target.id))
        ).scalar_one()
        await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == target.id))
        n_keys = 0
        if not keep_passkeys:
            n_keys = len(await _passkeys(db, target.id))
            await db.execute(delete(WebAuthnCredential).where(WebAuthnCredential.user_id == target.id))
        n_devices = await _revoke_devices(db, target.id)
        await db.execute(
            delete(AuthChallenge).where(AuthChallenge.user_id == target.id, AuthChallenge.used_at.is_(None))
        )
        await db.flush()
    from app.services import (
        sessions as user_sessions,  # AU-15: every session of the person ends (implies revoke_tokens)
    )

    await user_sessions.revoke_all(db, target, actor=actor, reason="mfa_reset")
    removed = {"totp": had_totp, "recovery_code_count": int(codes), "passkeys": n_keys, "trusted_devices": n_devices}
    await audit.record(
        db,
        "auth.mfa_reset_by_admin",
        "user",
        target.id,
        after={"identity_check": identity_check, "keep_passkeys": keep_passkeys, **removed},
        actor=actor,
        reason=reason,
    )
    await _mail(db, target, "mfa_reset_by_admin", actor=_label(actor))
    return {"user_id": target.id, "removed": removed, "signed_out": True}


async def send_reset_link(db: AsyncSession, actor: User, target: User, reason: str | None = None) -> dict[str, Any]:
    """E-mail the existing one-time reset token as a link (local accounts only). The token never reaches the
    administrator, the answer or the outbox (ASVS 6.4.6)."""
    from app.models.booking import PasswordResetToken
    from app.services import mail
    from app.services.bookings_settings import smtp_configured
    from app.services.bookings_users import RESET_TTL, _hash, _revoke_open_tokens

    kind = await account_type(db, target)
    if kind == "sso":
        raise MfaError(
            409,
            "sso_account",
            "Bu hesap kimlik sağlayıcısıyla giriş yapıyor; SmartSched parolası yok.",
            "This account signs in with an identity provider; it has no SmartSched password.",
        )
    if kind == "ldap":
        raise MfaError(
            409,
            "directory_account",
            "Bu hesabın parolası kurum dizininde (LDAP); orada sıfırlanır.",
            "This account's password lives in the directory (LDAP); reset it there.",
        )
    if not target.is_active:
        raise MfaError(409, "account_disabled", "Hesap devre dışı.", "The account is disabled.")
    if not target.email:
        raise MfaError(409, "no_email", "Bu kişinin e-posta adresi yok.", "This person has no e-mail address.")
    if not await smtp_configured(db):
        raise MfaError(
            409,
            "mail_not_configured",
            "E-posta ayarlanmadığı için bağlantı gönderilemez. Ayarlar › E-posta bölümünü tamamlayın.",
            "The link cannot be sent because e-mail is not set up. Complete Settings › E-mail.",
        )
    now = utcnow()
    await _revoke_open_tokens(db, target.id, now)
    token = secrets.token_urlsafe(24)
    expires = now + RESET_TTL
    row = PasswordResetToken(user_id=target.id, token_hash=_hash(token), expires_at=expires, created_by=actor.id)
    db.add(row)
    await db.flush()
    hours = int(RESET_TTL.total_seconds() // 3600)
    out = await mail.send_kind(
        db,
        "password_reset_link_by_admin",
        to_email=target.email,
        user=target,
        link=f"/reset-password?token={token}",
        deliver_now=True,
        actor=_label(actor),
        valid_hours=hours,
    )
    emailed = out.status == "SENT"
    out.body = "(password reset link sent by an administrator; not stored)"
    out.link = "/reset-password"
    if not emailed:
        row.used_at = now  # nobody can read the token: retire it at once
    await db.flush()
    await audit.record(
        db,
        "auth.reset_link_by_admin",
        "user",
        target.id,
        after={"expires_at": expires, "emailed": emailed},
        actor=actor,
        reason=(reason or "").strip() or None,
    )
    if not emailed:
        raise MfaError(
            502,
            "mail_failed",
            "E-posta gönderilemedi. E-posta ayarlarını denetleyip yeniden deneyin.",
            "The e-mail could not be sent. Check the e-mail settings and try again.",
        )
    return {"user_id": target.id, "emailed": True, "expires_at": expires}


# --------------------------------------------------------------------------------------------------
# hooks for the login page and the password routes
# --------------------------------------------------------------------------------------------------


async def public_flags(db: AsyncSession) -> dict[str, Any]:
    """For ``GET /org/public`` (the login page decides before first paint): no account is named."""
    policy = await get_policy(db)
    on = policy.mfa_policy != "off" and policy.passkeys_enabled and await _rp_ok(db)
    return {
        "enabled": on,
        "sign_in": on and policy.passkey_first_factor,
        "trusted_device_days": policy.trusted_device_days if policy.mfa_policy != "off" else 0,
    }


PASSWORD_MIN = 12
PASSWORD_MIN_WITH_MFA = 8


async def password_min_length(db: AsyncSession, user: User | None) -> int:
    """Owner default 2026-10-18: a new password has at least 12 characters, or 8 when 2FA is on."""
    if user is not None and await methods(db, user):
        return PASSWORD_MIN_WITH_MFA
    return PASSWORD_MIN


async def check_password_length(db: AsyncSession, user: User | None, password: str) -> None:
    need = await password_min_length(db, user)
    if len(password or "") < need:
        raise MfaError(
            422,
            "password_too_short",
            f"Parola en az {need} karakter olmalı.",
            f"The password must have at least {need} characters.",
            min_length=need,
        )


async def user_for_reset_code(db: AsyncSession, code: str) -> User | None:
    """The account an unused, unexpired reset code belongs to (nothing is consumed)."""
    from app.models.booking import PasswordResetToken
    from app.services.bookings_users import _hash

    row = (
        await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(code.strip())))
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        return None
    return await db.get(User, row.user_id)


async def on_password_changed(db: AsyncSession, user: User) -> int:
    """A password change or reset ends every remembered device of the person (auth UX spec §17)."""
    async with rls.system_scope(db):
        n = await _revoke_devices(db, user.id)
    if n:
        await audit.record(
            db, "auth.trusted_device_revoked", "user", user.id, after={"password_change": True, "count": n}
        )
    return n


async def session_after_password(db: AsyncSession, user: User) -> dict[str, Any]:
    """After a reset link or a local invite set the password: the same gate as the password step (``mfa_required`` /
    ``mfa_setup_required`` with a challenge token, else a session)."""
    gate = await after_password(db, user, "local")
    if gate.kind != "pass":
        return {"access_token": None, "expires_in": 0, **gate.extra}
    return {**await finish_sign_in(db, user, "local"), **gate.extra}


HISTORY_ACTIONS = (
    "auth.login",
    "auth.login_refused",
    "auth.mfa_verified",
    "auth.mfa_failed",
    "auth.mfa_locked",
    "auth.mfa_enabled",
    "auth.mfa_disabled",
    "auth.mfa_app_changed",
    "auth.mfa_reset_by_admin",
    "auth.mfa_recovery_used",
    "auth.mfa_recovery_regenerated",
    "auth.passkey_added",
    "auth.passkey_removed",
    "auth.trusted_device_used",
    "auth.trusted_device_added",
    "auth.trusted_device_revoked",
    "auth.reset_link_by_admin",
    "user.reset_code",
)


async def sign_in_history(db: AsyncSession, user: User, limit: int = 50) -> dict[str, Any]:
    """The person's own security events (newest first; no address, the method and the device family only) and the
    devices that signed in (RF-11 known devices). Open sessions: ``GET /auth/sessions`` (AU-15)."""
    from app.models import AuditEvent
    from app.services import mail_senders
    from app.services.bookings_settings import get_user_value

    q = (
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "user",
            AuditEvent.entity_id == str(user.id),
            AuditEvent.action.in_(HISTORY_ACTIONS),
        )
        .order_by(AuditEvent.id.desc())
        .limit(max(1, min(200, limit)))
    )
    events = []
    for e in (await db.execute(q)).scalars():
        after = e.after or {}
        events.append(
            {
                "at": e.ts,
                "action": e.action,
                "method": after.get("method") or after.get("auth_method"),
                "by_admin": e.actor_id is not None and e.actor_id != user.id,
            }
        )
    raw = await get_user_value(db, user.id, mail_senders.DEVICES_KEY)
    try:
        devices = [{"seen": d.get("seen")} for d in (json.loads(raw) if raw else []) if isinstance(d, dict)]
    except ValueError:
        devices = []
    return {"events": events, "known_devices": len(devices), "last_login_at": user.last_login_at}


# --------------------------------------------------------------------------------------------------
# AU-16: MFA asserted by the identity provider (OIDC / Entra ``amr`` / ``acr``)
# --------------------------------------------------------------------------------------------------

#: RFC 8176 ``amr`` values that say "more than one factor" outright (Entra: ``mfa``; Windows Hello: ``ngcmfa``)
AMR_MFA = frozenset({"mfa", "mca", "ngcmfa"})
#: RFC 8176 factor values; two different ones also make a multi-factor sign-in
AMR_FACTORS = frozenset(
    {"pwd", "otp", "hwk", "swk", "sms", "tel", "sc", "pin", "fpt", "face", "iris", "retina", "vbm", "kba", "user"}
)
IDP_NOTICE_KEY = "idp_mfa_notice"


def idp_asserted_mfa(claims: dict[str, Any]) -> bool:
    """True when the ID token says the provider used more than one factor: an ``amr`` of ``mfa`` / ``mca`` (RFC 8176),
    two different factors, or an ``acr`` naming multi-factor or NIST AAL2 / AAL3."""
    amr = claims.get("amr")
    values = {str(v).strip().lower() for v in amr if isinstance(v, str)} if isinstance(amr, list) else set()
    if values & AMR_MFA or len(values & AMR_FACTORS) >= 2:
        return True
    acr = str(claims.get("acr") or "").strip().lower()
    if not acr:
        return False
    return (
        "mfa" in acr
        or "multi-factor" in acr
        or "multifactor" in acr
        or acr.endswith(("aal2", "aal3", "/loa3", "/loa4"))
    )


async def role_requires(db: AsyncSession, user: User, policy: Policy | None = None) -> bool:
    """The policy's role rule alone (any account type): ``required_for_roles`` and the person's role is listed."""
    policy = policy or await get_policy(db)
    if policy.mfa_policy != "required_for_roles":
        return False
    return (await _role_code(db, user)) in policy.mfa_roles or user.role in policy.mfa_roles


def require_idp_mfa(provider: Any) -> bool:
    return bool((getattr(provider, "options", None) or {}).get("require_idp_mfa"))


async def idp_mfa_gate(db: AsyncSession, provider: Any, user: User, claims: dict[str, Any]) -> None:
    """Called by the SSO sign-in (OIDC / Entra). When the policy requires 2FA for the person's role and the ID token
    does not assert MFA: with "IdP MFA'yı zorunlu tut" on, the sign-in is refused (``idp_mfa`` → public code
    ``idp_mfa_required``); off (default), the person signs in and the panel shows a step-up notice once
    (``idp_mfa_missing`` on ``POST /auth/sso/exchange``). SAML sign-ins are not checked (no ``amr``)."""
    from app.services.identity import kinds as idp_kinds

    if getattr(provider, "kind", None) == idp_kinds.SAML:
        return
    if not await role_requires(db, user) or idp_asserted_mfa(claims):
        return
    enforced = require_idp_mfa(provider)
    await audit.record(
        db,
        "auth.idp_mfa_missing",
        "user",
        user.id,
        after={"provider": getattr(provider, "name", None), "enforced": enforced},
        actor=user,
    )
    if enforced:
        from app.services.sso import SsoError

        raise SsoError("idp_mfa", f"provider {getattr(provider, 'name', '?')} asserted no MFA", user_id=user.id)
    from app.services.bookings_settings import set_user_value

    label = str(getattr(provider, "display_name", None) or getattr(provider, "name", "") or "")[:80]
    await set_user_value(db, user.id, IDP_NOTICE_KEY, label or "1")


async def pop_idp_notice(db: AsyncSession, user: User) -> dict[str, Any]:
    """The step-up notice for ``POST /auth/sso/exchange`` (shown once)."""
    from app.services.bookings_settings import get_user_value, set_user_value

    label = await get_user_value(db, user.id, IDP_NOTICE_KEY)
    if not label:
        return {}
    await set_user_value(db, user.id, IDP_NOTICE_KEY, None)
    name = label if label != "1" else "kimlik sağlayıcınız"
    name_en = label if label != "1" else "your identity provider"
    return {
        "idp_mfa_missing": True,
        "idp_mfa_message_tr": (
            f"Kurumunuz bu rol için iki aşamalı doğrulama istiyor, ancak {name} bu girişte çok adımlı doğrulama "
            "bildirmedi. Hesabınızda çok adımlı doğrulamayı açın; bir sonraki girişte istenebilir."
        ),
        "idp_mfa_message_en": (
            f"Your institution requires two-step verification for this role, but {name_en} reported no multi-factor "
            "sign-in this time. Turn on multi-factor authentication for your account; the next sign-in may require it."
        ),
    }


async def set_idp_mfa(db: AsyncSession, actor: User, provider_id: int, require: bool) -> dict[str, Any]:
    from app.models.sso import SsoProvider

    row = await db.get(SsoProvider, provider_id)
    if row is None:
        raise MfaError(404, "not_found", "Kimlik sağlayıcı bulunamadı.", "Identity provider not found.")
    before = require_idp_mfa(row)
    opts = dict(row.options or {})
    opts["require_idp_mfa"] = bool(require)
    row.options = opts
    await db.flush()
    if before != bool(require):
        await audit.record(
            db,
            "auth.idp_mfa_setting",
            "sso_provider",
            row.id,
            before={"require_idp_mfa": before},
            after={"require_idp_mfa": bool(require)},
            actor=actor,
        )
    return idp_provider_out(row)


def idp_provider_out(row: Any) -> dict[str, Any]:
    from app.services.identity import kinds as idp_kinds

    return {
        "id": row.id,
        "name": row.name,
        "display_name": row.display_name,
        "kind": row.kind,
        "supported": row.kind != idp_kinds.SAML,
        "require_idp_mfa": require_idp_mfa(row),
    }


async def idp_providers(db: AsyncSession) -> list[dict[str, Any]]:
    from app.models.sso import SsoProvider

    rows = (await db.execute(select(SsoProvider).order_by(SsoProvider.sort_order, SsoProvider.id))).scalars()
    return [idp_provider_out(r) for r in rows]


# --------------------------------------------------------------------------------------------------
# KVKK
# --------------------------------------------------------------------------------------------------


async def dsr_rows(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """The person's own sign-in security data for the DSR export (one row per item, CSV-friendly): what is on and
    when, never a secret, a code or a key."""
    async with rls.system_scope(db):
        row = await _row(db, user_id)
        left, total = await _codes_left(db, user_id)
        keys = await _passkeys(db, user_id)
        devices = list((await db.execute(select(TrustedDevice).where(TrustedDevice.user_id == user_id))).scalars())
    out: list[dict[str, Any]] = [
        {
            "item": "authenticator_app",
            "name": None,
            "enabled": bool(row and row.totp_secret_enc),
            "created_at": row.totp_enabled_at if row else None,
            "last_used_at": None,
            "detail": None,
        },
        {
            "item": "recovery_codes",
            "name": None,
            "enabled": total > 0,
            "created_at": None,
            "last_used_at": None,
            "detail": f"{left}/{total}",
        },
    ]
    for k in keys:
        out.append(
            {
                "item": "passkey",
                "name": k.name,
                "enabled": True,
                "created_at": k.created_at,
                "last_used_at": k.last_used_at,
                "detail": None,
            }
        )
    from app.services import sessions as user_sessions

    for sess in await user_sessions.dsr_rows(db, user_id):
        out.append(
            {
                "item": "session",
                "name": sess["device"],
                "enabled": sess["revoked_at"] is None,
                "created_at": sess["created_at"],
                "last_used_at": sess["last_seen_at"],
                "detail": sess["network"],
            }
        )
    for d in devices:
        out.append(
            {
                "item": "trusted_device",
                "name": d.label,
                "enabled": d.revoked_at is None,
                "created_at": d.created_at,
                "last_used_at": d.last_used_at,
                "detail": f"expires {d.expires_at:%Y-%m-%d}",
            }
        )
    return out


async def erase(db: AsyncSession, user_id: int) -> int:
    """Delete every sign-in security row of the person (KVKK erasure); the number of rows deleted."""
    total = 0
    async with rls.system_scope(db):
        for model in (MfaRecoveryCode, WebAuthnCredential, TrustedDevice, AuthChallenge, UserSession, UserMfa):
            res = await db.execute(
                delete(model).where(model.user_id == user_id).execution_options(synchronize_session=False)
            )
            total += int(getattr(res, "rowcount", 0) or 0)
    return total


__all__ = [
    "Gate",
    "MfaError",
    "Policy",
    "account_type",
    "admin_reset",
    "admin_summary",
    "after_password",
    "dsr_rows",
    "erase",
    "finish_sign_in",
    "get_policy",
    "send_reset_link",
    "set_policy",
    "status",
]
