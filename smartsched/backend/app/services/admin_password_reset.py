"""Operator password reset for an administrator account (owner request 2026-11-02): ``python -m app.cli
reset-admin-password --email X`` inside the backend container (the AWS pod runs it through ``POD_ACTION
admin-reset``, infra/aws/smartsched_aws.py, and stores the result in SSM ``{prefix}/admin_password``).

For when the e-mail reset (``POST /auth/password-reset/request``, needs SMTP) and the admin's reset link
(``POST /admin/users/{id}/password-reset-link``, needs another signed-in administrator) are not available.

What it does, in one transaction:

* a new random password (24 letters and digits, about 143 bits) is hashed onto the account;
* ``force_password_reset`` is set (unless asked not to), so the next sign-in goes to /login/change-password;
* every session and access token ends (:func:`app.services.sessions.revoke_all`), remembered devices end
  (:func:`app.services.mfa.on_password_changed`), unused reset links are spent;
* the second-factor lockout (``user_mfa.failed_count`` / ``locked_until``) is cleared. The second factor itself
  stays: an enrolled TOTP / passkey is still asked after the password;
* one audit event ``auth.password_reset_cli`` (actor ``system``; never the password).

Only active administrator accounts (role ADMIN, a privileged role or ``planning.admin``) are accepted. The password
is returned to the caller only; nothing here logs it. The in-process sign-in limiter of the running backend
(app/core/ratelimit.py, 10 failures in 5 minutes per address) is not reachable from here; it expires by itself.
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

PASSWORD_LENGTH = 24
_ALPHABET = string.ascii_letters + string.digits


class ResetRefused(Exception):
    """No such account, not active, not an administrator (exit code 2 of the CLI). Never names the password."""


@dataclass
class ResetResult:
    user_id: int
    email: str
    password: str
    force_change: bool
    sessions_revoked: int
    devices_revoked: int
    mfa_lock_cleared: bool
    auth_source: str

    def __repr__(self) -> str:  # never shows the password
        return f"ResetResult(user_id={self.user_id}, email={self.email!r}, force_change={self.force_change})"


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    """Letters and digits only (no shell or URL quoting trouble), at least one lower, upper and digit."""
    while True:
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw


async def reset_admin_password(session: AsyncSession, email: str, *, force_change: bool = True) -> ResetResult:
    """Reset the password of the administrator ``email`` and commit. Raises :class:`ResetRefused`."""
    from app.core.security import hash_password
    from app.models.base import utcnow
    from app.models.booking import PasswordResetToken
    from app.models.mfa import UserMfa
    from app.services import audit, mfa, sessions
    from app.services.sso import is_admin_user

    wanted = (email or "").strip().lower()
    if not wanted or "@" not in wanted:
        raise ResetRefused("--email must be an e-mail address")
    user = (await session.execute(select(User).where(func.lower(User.email) == wanted))).scalar_one_or_none()
    if user is None:
        raise ResetRefused(f"no account with the e-mail {wanted}")
    if not user.is_active:
        raise ResetRefused(f"the account {wanted} is disabled; enable it first (another administrator, Users page)")
    if not await is_admin_user(session, user):
        raise ResetRefused(f"the account {wanted} is not an administrator; this command resets administrators only")

    password = generate_password()
    user.password_hash = hash_password(password)
    user.force_password_reset = bool(force_change)
    now = utcnow()
    open_links = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
    )
    for tok in (await session.execute(open_links)).scalars():
        tok.used_at = now
    revoked = await sessions.revoke_all(session, user, actor=None, reason="cli_password_reset")
    devices = await mfa.on_password_changed(session, user)
    row = await session.get(UserMfa, user.id)
    cleared = bool(row is not None and (row.failed_count or row.locked_until))
    if row is not None:
        row.failed_count, row.locked_until = 0, None
    await audit.record(
        session,
        "auth.password_reset_cli",
        "user",
        user.id,
        after={
            "by": "operator command line",
            "force_change": bool(force_change),
            "sessions_revoked": revoked,
            "devices_revoked": devices,
            "mfa_lock_cleared": cleared,
        },
        reason="python -m app.cli reset-admin-password",
    )
    await session.commit()
    return ResetResult(
        user_id=user.id,
        email=wanted,
        password=password,
        force_change=bool(force_change),
        sessions_revoked=revoked,
        devices_revoked=devices,
        mfa_lock_cleared=cleared,
        auth_source=str(user.auth_source or "local"),
    )


__all__ = ["PASSWORD_LENGTH", "ResetRefused", "ResetResult", "generate_password", "reset_admin_password"]
