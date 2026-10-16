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
from app.core.security import hash_password, revoke_tokens
from app.importers import normalize as n
from app.models import PasswordResetToken, Program, Role, User
from app.models.base import utcnow
from app.schemas.messages import Refusal, pick
from app.services import bookings_events as events
from app.services.bookings_notify import notify
from app.services.bookings_perms import (
    is_privileged_role,
    may_grant_role,
    missing_permissions,
    permission_list,
    role_permission_names,
    set_user_role,
)
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
#: header words that name a column (T-R1-33: a header row is recognised by its names, in either language, in any
#: order; a file without one keeps the CRBS positional order above)
HEADER_ALIASES: dict[str, frozenset[str]] = {
    "username": frozenset(
        {"username", "user_name", "user name", "kullanıcı adı", "kullanici adi", "kullanıcı", "login"}
    ),
    "firstname": frozenset({"firstname", "first_name", "first name", "ad", "adı", "isim"}),
    "lastname": frozenset({"lastname", "last_name", "last name", "surname", "soyad", "soyadı"}),
    "email": frozenset({"email", "e-mail", "mail", "e-posta", "eposta", "e posta"}),
    "password": frozenset({"password", "parola", "şifre", "sifre"}),
    "role": frozenset({"role", "rol"}),
    "department": frozenset({"department", "bölüm", "bolum", "birim"}),
    "force_password_reset": frozenset(
        {
            "force_password_reset",
            "force password reset",
            "password change",
            "parola sıfırlama",
            "şifre sıfırlama",
            "parola değişikliği",
            "şifre değişikliği",
            "ilk girişte parola",
        }
    ),
    "full_name": frozenset(
        {"full_name", "fullname", "full name", "displayname", "display_name", "name", "ad soyad", "adı soyadı"}
    ),
}
HEADER_WORDS = frozenset(w for words in HEADER_ALIASES.values() for w in words)

#: status word of a row, both languages (the summary line)
STATUS_TEXT: dict[str, tuple[str, str]] = {
    "success": ("oluşturuldu", "created"),
    "username_exists": ("kullanıcı adı var", "username exists"),
    "username_empty": ("kullanıcı adı yok", "no username"),
    "password_empty": ("parola yok", "without password"),
    "email_exists": ("e-posta var", "e-mail exists"),
    "invalid": ("geçersiz", "invalid"),
    "forbidden": ("izin yok", "not allowed"),
}


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
    #: ``{"rows": n, "created": n, "<status>": n}`` and the one-line sentence of it (T-R1-33)
    summary: dict[str, int] = field(default_factory=dict)
    summary_tr: str = ""
    summary_en: str = ""


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


def _header_word(cell: str | None) -> str | None:
    word = n.tr_casefold(n.clean_text(cell) or "").replace("_", " ").strip()
    for name, words in HEADER_ALIASES.items():
        if word in words or word.replace(" ", "_") in words:
            return name
    return None


def header_columns(row: list[str]) -> dict[str, int] | None:
    """``{column: index}`` when ``row`` is a header row (at least one cell is a column name), else ``None``.
    Raises :class:`Refusal` when the names identify neither a username nor an e-mail column."""
    found = {name: i for i, cell in enumerate(row) if (name := _header_word(cell)) is not None}
    if not found or any("@" in (c or "") for c in row):
        return None
    # a header word this list does not know ("Parola değişikliği") keeps its CRBS position when that column is free
    for i, cell in enumerate(row):
        if i < len(COLUMNS) and (cell or "").strip() and i not in found.values() and COLUMNS[i] not in found:
            found[COLUMNS[i]] = i
    if "username" not in found and "email" not in found:
        shown = ", ".join(c.strip() for c in row if c and c.strip())
        raise Refusal(
            "csv_columns_unknown",
            f"Sütunlar tanınmadı ({shown}). Başlık satırında en az bir “email” ya da “username” sütunu olmalı; "
            "diğerleri: full_name, firstname, lastname, password, role, department.",
            f"unknown columns ({shown}): the header row needs an email or username column; others: full_name, "
            "firstname, lastname, password, role, department",
        )
    return found


def _val(row: list[str], i: int | None) -> str | None:
    return n.clean_text(row[i]) if i is not None and i < len(row) else None


def _texts(result: dict[str, Any], key: str, tr: str, en: str, language: str | None) -> None:
    """``error`` / ``warning`` in the actor's language, plus ``_tr`` and ``_en`` for a client that picks itself."""
    result[key] = pick(language, tr, en)
    result[f"{key}_tr"] = tr
    result[f"{key}_en"] = en


def summarize(out: ImportResult) -> None:
    counts: dict[str, int] = {"rows": len(out.results), "created": out.created}
    for r in out.results:
        if r["status"] != "success":
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    out.summary = counts
    parts_tr = [f"{out.created} oluşturuldu"]
    parts_en = [f"{out.created} created"]
    for status, (tr, en) in STATUS_TEXT.items():
        if status != "success" and counts.get(status):
            parts_tr.append(f"{counts[status]} {tr}")
            parts_en.append(f"{counts[status]} {en}")
    out.summary_tr = f"{counts['rows']} satır: {', '.join(parts_tr)}"
    out.summary_en = f"{counts['rows']} rows: {', '.join(parts_en)}"


async def import_users_csv(
    session: AsyncSession, data: bytes, defaults: ImportDefaults, actor: User | None = None
) -> ImportResult:
    """Columns ``username, firstname, lastname, email, password, role, department[, force_password_reset]``
    (CRBS order) when the file has no header row; a header row names the columns in any order (``email,
    full_name, role, password`` works, the username is then the e-mail's local part). Existing usernames and
    e-mails are left untouched (CRBS semantics). Role and department are matched by exact name,
    Turkish-case-insensitively. Row texts come in the actor's language (``error``, ``warning``) and in both
    (``_tr`` / ``_en``); ``summary`` counts the statuses."""
    language = actor.language if actor is not None else None
    roles = {n.tr_casefold(r.name): r for r in (await session.execute(select(Role))).scalars()}
    deps = {n.tr_casefold(p.name): p for p in (await session.execute(select(Program))).scalars()}
    default_role = await session.get(Role, defaults.role_id) if defaults.role_id else None
    out = ImportResult()
    seen: set[str] = set()
    columns: dict[str, int] = {name: i for i, name in enumerate(COLUMNS)}
    header_seen = False
    for line, row in enumerate(_rows(_decode(data))):
        if not any((c or "").strip() for c in row):
            continue
        if not header_seen and not out.results:
            header_seen = True
            named = header_columns(row)
            if named is not None:
                columns = named
                continue
        username_cell = _val(row, columns.get("username"))
        email = _val(row, columns.get("email"))
        # a header that names no username column: the e-mail's local part is the username
        raw_username = username_cell or (email.split("@", 1)[0] if email and "username" not in columns else None)
        result: dict[str, Any] = {"line": line + 1, "username": raw_username, "status": "success"}
        out.results.append(result)
        if not raw_username:
            result["status"] = "username_empty"
            continue
        try:
            username = fold_username(raw_username)
        except ValueError as exc:
            _texts(
                result,
                "error",
                "Kullanıcı adı yalnızca harf, rakam ve . _ - @ + içerebilir (boşluksuz).",
                str(exc),
                language,
            )
            result["status"] = "invalid"
            continue
        result["username"] = username
        password = _val(row, columns.get("password")) or defaults.password
        if not password:
            result["status"] = "password_empty"
            continue
        if email:
            try:
                email = clean_email(email)
            except ValueError:
                _texts(result, "error", f"Geçersiz e-posta: {email}", f"invalid e-mail {email!r}", language)
                result["status"] = "invalid"
                continue
        if (
            username in seen
            or (await session.execute(select(User.id).where(User.username == username))).scalar_one_or_none()
            is not None
        ):
            result["status"] = "username_exists"
            continue
        if email and (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
            _texts(
                result,
                "error",
                "Bu e-posta başka bir kullanıcıya ait.",
                f"e-mail {email} belongs to another user",
                language,
            )
            result["status"] = "email_exists"
            continue
        role = default_role
        role_name = _val(row, columns.get("role"))
        if role_name:
            key = n.tr_casefold(role_name)
            role = roles.get(key) or next((r for r in roles.values() if (r.code or "").lower() == key), role)
            if role is None or (key not in roles and (role.code or "").lower() != key):
                _texts(
                    result,
                    "warning",
                    f"Bilinmeyen rol “{role_name}”; varsayılan kullanıldı.",
                    f"unknown role {role_name!r}; default used",
                    language,
                )
        if actor is not None and role is not None and not await may_grant_role(session, actor, role):
            missing = await missing_permissions(
                session,
                actor,
                role_permission_names(role) | {"setup.roles"}
                if is_privileged_role(role)
                else role_permission_names(role),
            )
            names = permission_list(missing)
            _texts(
                result,
                "error",
                f"“{role.name}” rolünü vermek için sizde olmayan izinler gerekir: {names['tr']}",
                f"granting the role {role.name!r} needs permissions you do not hold: {', '.join(missing)}",
                language,
            )
            result["status"] = "forbidden"
            continue
        dep_id = defaults.department_id
        dep_name = _val(row, columns.get("department"))
        if dep_name:
            prog = deps.get(n.tr_casefold(dep_name))
            if prog is not None:
                dep_id = prog.id
            else:
                _texts(
                    result,
                    "warning",
                    f"Bilinmeyen bölüm “{dep_name}”; varsayılan kullanıldı.",
                    f"unknown department {dep_name!r}; default used",
                    language,
                )
        frc = n.parse_bool_loose(_val(row, columns.get("force_password_reset")))
        firstname, lastname = _val(row, columns.get("firstname")), _val(row, columns.get("lastname"))
        display = _val(row, columns.get("full_name")) or " ".join(x for x in (firstname, lastname) if x) or None
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
    summarize(out)
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


async def issue_reset_token(
    session: AsyncSession, user: User, actor: User | None, *, revoke_others: bool = True
) -> IssuedToken:
    """New one-time token. E-mailed when SMTP is configured and the user has an address; the plain token is
    never stored (only its SHA-256). An administrator's new token revokes the older unused ones; a public
    request (``revoke_others=False``, audit B10) does not, so a stranger asking for resets cannot invalidate
    the code the user just received. Using any code revokes the others (:func:`consume_reset_token`)."""
    now = utcnow()
    if revoke_others:
        await _revoke_open_tokens(session, user.id, now)
    token = secrets.token_urlsafe(24)
    expires = now + RESET_TTL
    session.add(
        PasswordResetToken(
            user_id=user.id, token_hash=_hash(token), expires_at=expires, created_by=actor.id if actor else None
        )
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
            deliver_now=True,  # the caller shows the code when the e-mail could not be sent
        )
        emailed = row.status == "SENT"
        # the outbox keeps a record of the e-mail, never the live token
        row.body = "(one-time password reset code; not stored)"
    await session.flush()
    from app.services import audit as audit_log

    # audit coverage: who issued a reset code for whom (never the code itself)
    await audit_log.record(
        session,
        "user.reset_code",
        "user",
        user.id,
        after={"expires_at": expires, "emailed": emailed, "self_service": actor is None},
        actor=actor,
    )
    await events.emit(session, "password.reset_requested", {"user_id": user.id, "expires_at": expires.isoformat()})
    return IssuedToken(token, expires, emailed)


async def _revoke_open_tokens(session: AsyncSession, user_id: int, now: datetime) -> None:
    for old in (
        await session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None)
            )
        )
    ).scalars():
        old.used_at = now


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
    await _revoke_open_tokens(session, user.id, now)
    user.password_hash = hash_password(new_password)
    user.force_password_reset = False
    revoke_tokens(user)  # B-AUTH-11: whoever held the old password is signed out too
    await session.flush()
    return user
