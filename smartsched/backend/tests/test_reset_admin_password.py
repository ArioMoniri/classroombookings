"""``python -m app.cli reset-admin-password --email X`` (owner request 2026-11-02; app/services/admin_password_reset.py):
a random password on stdout only, change required at the next sign-in, sessions and tokens ended, the second-factor
lockout cleared, one audit event without the password; administrators only."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from app import cli
from app.core import db as dbmod
from app.core.security import hash_password, verify_password
from app.models import AuditEvent, Base, User
from app.models.base import utcnow
from app.models.mfa import UserMfa, UserSession
from app.services import admin_password_reset as apr
from sqlalchemy import select

OLD = "eski-parola-1234567"


async def _user(session, email: str, role: str = "ADMIN", active: bool = True) -> User:
    u = User(email=email, password_hash=hash_password(OLD), role=role, is_active=active, full_name="Umut K")
    session.add(u)
    await session.commit()
    return u


async def test_reset_sets_a_strong_password_and_ends_everything(session):
    u = await _user(session, "umutk@getvivax.com")
    session.add(UserMfa(user_id=u.id, failed_count=7, locked_until=utcnow() + timedelta(minutes=30)))
    session.add(UserSession(user_id=u.id, jti_hash="a" * 64, expires_at=utcnow() + timedelta(hours=8)))
    await session.commit()
    tv = u.token_version or 0

    res = await apr.reset_admin_password(session, "  UmutK@GetVivax.com ")
    assert len(res.password) == apr.PASSWORD_LENGTH and res.password.isalnum()
    assert "password" not in repr(res) and res.password not in repr(res)
    await session.refresh(u)
    assert verify_password(res.password, u.password_hash or "") and not verify_password(OLD, u.password_hash or "")
    assert u.force_password_reset is True and u.token_version == tv + 1
    assert res.sessions_revoked == 1 and res.mfa_lock_cleared
    mfa = await session.get(UserMfa, u.id)
    assert mfa is not None and mfa.failed_count == 0 and mfa.locked_until is None
    sess = (await session.execute(select(UserSession).where(UserSession.user_id == u.id))).scalar_one()
    assert sess.revoked_at is not None
    [ev] = (await session.execute(select(AuditEvent).where(AuditEvent.action == "auth.password_reset_cli"))).scalars()
    assert ev.actor_type == "system" and res.password not in json.dumps(ev.after) + (ev.reason or "")


async def test_no_force_change_keeps_the_flag_off(session):
    await _user(session, "admin@uni.edu.tr")
    res = await apr.reset_admin_password(session, "admin@uni.edu.tr", force_change=False)
    assert res.force_change is False


@pytest.mark.parametrize(
    ("email", "role", "active", "needle"),
    [
        ("nobody@uni.edu.tr", None, True, "no account"),
        ("teacher@uni.edu.tr", "TEACHER", True, "not an administrator"),
        ("off@uni.edu.tr", "ADMIN", False, "disabled"),
        ("not-an-email", None, True, "e-mail"),
    ],
)
async def test_refused_accounts_are_left_alone(session, email, role, active, needle):
    if role:
        u = await _user(session, email, role=role, active=active)
        before = u.password_hash
    with pytest.raises(apr.ResetRefused, match=needle):
        await apr.reset_admin_password(session, email)
    if role:
        await session.refresh(u)
        assert u.password_hash == before


def test_generated_passwords_mix_classes_and_differ():
    pws = {apr.generate_password() for _ in range(50)}
    assert len(pws) == 50
    assert all(any(c.isupper() for c in p) and any(c.islower() for c in p) and any(c.isdigit() for c in p) for p in pws)


def test_cli_prints_the_password_alone_on_stdout(tmp_path, capsys):
    url = f"sqlite+aiosqlite:///{tmp_path}/cli.db"

    async def prepare() -> None:
        eng = dbmod.configure_engine(url)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with dbmod.get_session_factory()() as s:
            await _user(s, "umutk@getvivax.com")
        await dbmod.dispose_engine()

    async def check(pw: str) -> bool:
        dbmod.configure_engine(url)
        async with dbmod.get_session_factory()() as s:
            u = (await s.execute(select(User))).scalar_one()
            ok = verify_password(pw, u.password_hash or "") and u.force_password_reset
        await dbmod.dispose_engine()
        return ok

    asyncio.run(prepare())
    code = cli.main(["--database-url", url, "reset-admin-password", "--email", "umutk@getvivax.com"])
    out, err = capsys.readouterr()
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 1 and lines[0].isalnum() and len(lines[0]) == apr.PASSWORD_LENGTH
    assert lines[0] not in err and "umutk@getvivax.com" in err and "auth.password_reset_cli" in err
    assert asyncio.run(check(lines[0]))

    code = cli.main(["--database-url", url, "reset-admin-password", "--email", "nobody@getvivax.com"])
    out, err = capsys.readouterr()
    assert code == 2 and out == "" and "no account" in err
    asyncio.run(dbmod.dispose_engine())
