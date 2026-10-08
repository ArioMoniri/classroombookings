"""Users: CSV import (CRBS ``Users::import``), one-time password reset tokens, login identifier lookup."""

from __future__ import annotations

import csv
import hashlib
import io
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import clean_email, fold_username
from app.core.security import hash_password
from app.importers import normalize as n
from app.models import PasswordResetToken, Program, Role, User
from app.models.base import utcnow
from app.services import bookings_events as events
from app.services.bookings_notify import notify
from app.services.bookings_perms import set_user_role
from app.services.bookings_settings import smtp_configured

RESET_TTL = timedelta(hours=24)

# --------------------------------------------------------------------------------------------------
# Login lookup
# --------------------------------------------------------------------------------------------------


async def find_login_user(session: AsyncSession, identifier: str) -> User | None:
    ident = identifier.strip()
    if "@" in ident:
        try:
            email = clean_email(ident)
        except ValueError:
            email = None
        if email:
            u = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                return u
    try:
        key = fold_username(ident)
    except ValueError:
        return None
    return (await session.execute(select(User).where(User.username == key))).scalar_one_or_none()


# --------------------------------------------------------------------------------------------------
# CSV import
# --------------------------------------------------------------------------------------------------

COLUMNS = ("username", "firstname", "lastname", "email", "password", "role", "department", "force_password_reset")
HEADER_WORDS = {"username", "kullanıcı adı", "kullanici adi", "kullanıcı"}


@dataclass
class ImportDefaults:
    password: str | None = None
    role_id: int | None = None
    department_id: int | None = None
    enabled: bool = True
    force_password_reset: bool = False


@dataclass
class ImportResult:
    created: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):  # cp1254 = Turkish Windows (Excel "CSV")
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim)]


def _val(row: list[str], i: int) -> str | None:
    return n.clean_text(row[i]) if i < len(row) else None


async def import_users_csv(
    session: AsyncSession, data: bytes, defaults: ImportDefaults, actor: User | None = None
) -> ImportResult:
    """Columns ``username, firstname, lastname, email, password, role, department[, force_password_reset]``;
    an optional header row is skipped; existing usernames are left untouched (CRBS semantics). Role and
    department are matched by exact name, Turkish-case-insensitively."""
    roles = {n.tr_casefold(r.name): r for r in (await session.execute(select(Role))).scalars()}
    deps = {n.tr_casefold(p.name): p for p in (await session.execute(select(Program))).scalars()}
    default_role = await session.get(Role, defaults.role_id) if defaults.role_id else None
    out = ImportResult()
    seen: set[str] = set()
    for line, row in enumerate(_rows(_decode(data))):
        if not any((c or "").strip() for c in row):
            continue
        first = n.tr_casefold(row[0] or "") if row else ""
        if line == 0 and first in HEADER_WORDS:
            continue
        raw_username = _val(row, 0)
        result: dict[str, Any] = {"line": line + 1, "username": raw_username, "status": "success"}
        out.results.append(result)
        if not raw_username:
            result["status"] = "username_empty"
            continue
        try:
            username = fold_username(raw_username)
        except ValueError as exc:
            result.update(status="invalid", error=str(exc))
            continue
        result["username"] = username
        password = _val(row, 4) or defaults.password
        if not password:
            result["status"] = "password_empty"
            continue
        email = _val(row, 3)
        if email:
            try:
                email = clean_email(email)
            except ValueError:
                result.update(status="invalid", error=f"invalid e-mail {email!r}")
                continue
        if username in seen or (
            await session.execute(select(User.id).where(User.username == username))
        ).scalar_one_or_none() is not None:
            result["status"] = "username_exists"
            continue
        if email and (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
            result.update(status="invalid", error=f"e-mail {email} belongs to another user")
            continue
        role = default_role
        role_name = _val(row, 5)
        if role_name:
            role = roles.get(n.tr_casefold(role_name), role)
            if n.tr_casefold(role_name) not in roles:
                result["warning"] = f"unknown role {role_name!r}; default used"
        dep_id = defaults.department_id
        dep_name = _val(row, 6)
        if dep_name:
            prog = deps.get(n.tr_casefold(dep_name))
            if prog is not None:
                dep_id = prog.id
            else:
                result["warning"] = f"unknown department {dep_name!r}; default used"
        frc = n.parse_bool_loose(_val(row, 7))
        firstname, lastname = _val(row, 1), _val(row, 2)
        display = " ".join(x for x in (firstname, lastname) if x) or None
        u = User(
            username=username,
            email=email,
            firstname=firstname,
            lastname=lastname,
            full_name=display,
            password_hash=hash_password(password),
            is_active=defaults.enabled,
            department_id=dep_id,
            force_password_reset=defaults.force_password_reset if frc is None else frc,
        )
        set_user_role(u, role)
        session.add(u)
        await session.flush()
        seen.add(username)
        result["user_id"] = u.id
        out.created += 1
    return out


# --------------------------------------------------------------------------------------------------
# Password reset tokens
# --------------------------------------------------------------------------------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class IssuedToken:
    token: str
    expires_at: datetime
    emailed: bool


async def issue_reset_token(session: AsyncSession, user: User, actor: User | None) -> IssuedToken:
    """New one-time token (older unused ones are revoked). E-mailed when SMTP is configured and the user
    has an address; the plain token is never stored (only its SHA-256)."""
    now = utcnow()
    for old in (
        await session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        )
    ).scalars():
        old.used_at = now
    token = secrets.token_urlsafe(24)
    expires = now + RESET_TTL
    session.add(
        PasswordResetToken(user_id=user.id, token_hash=_hash(token), expires_at=expires, created_by=actor.id if actor else None)
    )
    emailed = False
    if user.email and await smtp_configured(session):
        row = await notify(
            session,
            kind="password_reset",
            to_email=user.email,
            subject="SmartSched parola sıfırlama / password reset",
            body=(
                "Parolanızı sıfırlamak için bu tek kullanımlık kodu kullanın (24 saat geçerli):\n"
                f"{token}\n\nUse this one-time code to reset your password (valid for 24 hours):\n{token}\n"
            ),
            user_id=user.id,
        )
        emailed = row.status == "SENT"
        # the outbox keeps a record of the e-mail, never the live token
        row.body = "(one-time password reset code; not stored)"
    await session.flush()
    await events.emit(session, "password.reset_requested", {"user_id": user.id, "expires_at": expires.isoformat()})
    return IssuedToken(token, expires, emailed)


async def consume_reset_token(session: AsyncSession, token: str, new_password: str) -> User | None:
    row = (
        await session.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(token.strip())))
    ).scalar_one_or_none()
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at < now:
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    row.used_at = now
    user.password_hash = hash_password(new_password)
    user.force_password_reset = False
    await session.flush()
    return user
