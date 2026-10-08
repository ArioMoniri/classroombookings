"""Organisation (CRBS ``settings/{Organisation,General,Authentication}``, ``setup/Language``, ``install``,
``Changelog``, ``Events``) and the self-service auth routes (profile, password change and reset)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, func, select

from app.api.deps import DB, CurrentAccess, CurrentUser, bearer, get_current_user, require_permission
from app.core.config import get_settings
from app.core.identity import clean_email, fold_username
from app.core.images import ImageError, sanitize_image
from app.core.security import hash_password, revoke_tokens, verify_password
from app.importers import normalize as n
from app.models import (
    BookingSchedule,
    Holiday,
    Program,
    Role,
    RoomGroup,
    Term,
    TermDate,
    TimetableWeek,
    Translation,
    User,
)
from app.models.catalog import Room
from app.schemas.auth import ChangePasswordIn, ProfileIn, ProfileOut, ResetConfirmIn, ResetRequestIn
from app.schemas.crbs import (
    LdapSettingsIn,
    LdapTestIn,
    OrgSettingsIn,
    SetupIn,
    SmtpSettingsIn,
    SmtpTestIn,
    TranslationIn,
    TranslationOut,
)
from app.services import bookings_events as events
from app.services import bookings_i18n, bookings_ldap, bookings_setup, settings_service
from app.services.bookings_notify import notify
from app.services.bookings_perms import (
    ensure_permissions_and_roles,
    grouped_permissions,
    load_access,
    set_user_role,
)
from app.services.bookings_settings import (
    BOOKINGS_SPECS,
    get_group,
    get_user_value,
    set_group,
    set_user_value,
    smtp_configured,
)
from app.services.bookings_users import consume_reset_token, find_login_user, issue_reset_token

router = APIRouter(prefix="/org", tags=["org"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]
AuthAdmin = Annotated[User, Depends(require_permission("setup.authentication"))]

CHANGELOG = Path(__file__).resolve().parents[3] / "CHANGELOG.md"
SHOW_NAME_PERMS = ("book_single.view_other_users", "book_recur.view_other_users")


# --- public --------------------------------------------------------------------------------------------


@router.get("/public")
async def public_info(db: DB) -> dict[str, Any]:
    """Everything the login page needs; no authentication."""
    org = await get_group(db, "org")
    users = (await db.execute(select(func.count(User.id)))).scalar_one()
    return {
        "name": org["name"],
        "website": org["website"],
        "logo_url": org["logo_url"],
        "login_message": org["login_message_text"] if org["login_message_enabled"] else None,
        "maintenance_mode": org["maintenance_mode"],
        "maintenance_message": org["maintenance_mode_message"] if org["maintenance_mode"] else None,
        "ldap_enabled": bool((await get_group(db, "ldap"))["enabled"]),
        "setup_required": users == 0,
        "default_language": org["default_language"],
        "languages": org["languages"],
    }


@router.get("/setup-status")
async def setup_status(db: DB) -> dict[str, Any]:
    """CRBS install + setup dashboard as a checklist (counts only; public so the first-run screen works)."""

    async def count(model: Any) -> int:
        return int((await db.execute(select(func.count()).select_from(model))).scalar_one())

    org = await get_group(db, "org")
    users = await count(User)
    return {
        "setup_required": users == 0,
        "checks": {
            "organisation_name": bool(org["name"]),
            "admin": users > 0,
            "terms": await count(Term),
            "rooms": await count(Room),
            "bookable_rooms": int(
                (await db.execute(select(func.count(Room.id)).where(Room.is_bookable.is_(True)))).scalar_one()
            ),
            "room_groups": await count(RoomGroup),
            "schedules": await count(BookingSchedule),
            "timetable_weeks": await count(TimetableWeek),
            "mapped_dates": await count(TermDate),
            "holidays": await count(Holiday),
            "departments": await count(Program),
            "roles": await count(Role),
            "smtp_configured": await smtp_configured(db),
        },
    }


@router.get("/setup/requirements")
async def setup_requirements(
    request: Request, db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> dict[str, Any]:
    """CRBS installer "Check requirements" step (audit MISSING 6). Public while no user exists, like the
    CRBS installer; afterwards it lists versions and paths, so it needs ``setup.settings``."""
    setup_required = not (await db.execute(select(func.count(User.id)))).scalar_one()
    if not setup_required:
        access = await load_access(db, await get_current_user(request, creds, db))
        if "setup.settings" not in access.perms:
            raise HTTPException(403, "requires permission setup.settings")
    checks = await bookings_setup.check_requirements(db, await smtp_configured(db))
    return {"setup_required": setup_required, "ok": not bookings_setup.failing(checks), "requirements": checks}


@router.post("/setup", status_code=201)
async def first_run_setup(body: SetupIn, db: DB) -> dict[str, Any]:
    """First-run wizard (CRBS ``install/info``): organisation name, timezone and the first administrator.
    Only while no user exists; afterwards 409. Refused while a requirement is an error (CRBS installer)."""
    if (await db.execute(select(func.count(User.id)))).scalar_one():
        raise HTTPException(409, "setup is already complete")
    failed = bookings_setup.failing(await bookings_setup.check_requirements(db, await smtp_configured(db)))
    if failed:
        raise HTTPException(409, f"requirements not met: {', '.join(failed)} (GET /org/setup/requirements)")
    try:
        email = clean_email(body.admin_email)
        username = fold_username(body.admin_username) if body.admin_username else None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    roles = await ensure_permissions_and_roles(db)
    await set_group(db, "org", {"name": body.org_name})
    await settings_service.set_value(db, "timezone", body.timezone)
    user = User(
        email=email,
        username=username,
        full_name=n.clean_text(body.admin_displayname) or "Administrator",
        password_hash=hash_password(body.admin_password),
    )
    set_user_role(user, roles["ADMIN"])
    db.add(user)
    await db.commit()
    return {"user_id": user.id, "email": user.email, "username": user.username}


# --- organisation / general settings ------------------------------------------------------------------


async def _teacher_role(db: DB) -> Role | None:
    return (await db.execute(select(Role).where(Role.code == "TEACHER"))).scalar_one_or_none()


async def _settings_out(db: DB) -> dict[str, Any]:
    org = await get_group(db, "org")
    teacher = await _teacher_role(db)
    org["timezone"] = await settings_service.get_value(db, "timezone")
    org["bookings_show_name"] = bool(
        teacher and all(p in {x.name for x in teacher.permissions} for p in SHOW_NAME_PERMS)
    )
    org["max_active_bookings"] = teacher.max_active_bookings if teacher else None
    # the bookings group (show_ungrouped_rooms and the deliberate-difference switches) is flat here
    org.update(await get_group(db, "bookings"))
    return org


@router.get("/settings")
async def get_org_settings(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    return await _settings_out(db)


@router.put("/settings")
async def put_org_settings(body: OrgSettingsIn, db: DB, _: SettingsAdmin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    show = data.pop("bookings_show_name", None)
    max_b = data.pop("max_active_bookings", None)
    unlimited = data.pop("max_active_bookings_unlimited", None)
    tz = data.pop("timezone", None)
    booking_values = {k: data.pop(k) for k in list(data) if k in BOOKINGS_SPECS}
    booking_values = {k: v for k, v in booking_values.items() if v is not None}
    if booking_values:
        await set_group(db, "bookings", booking_values)
    if tz is not None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(422, f"unknown timezone {tz!r}") from exc
        await settings_service.set_value(db, "timezone", tz)
    current = await get_group(db, "org")
    dtype = data.get("displaytype", current["displaytype"])
    cols = data.get("d_columns", current["d_columns"])
    if cols not in {"day": {"periods", "rooms"}, "room": {"periods", "days"}}[dtype]:
        raise HTTPException(422, f"columns {cols!r} do not fit display type {dtype!r}")
    langs = data.get("languages") or current["languages"] or []
    default_lang = data.get("default_language") or current["default_language"]
    if default_lang not in langs:  # B8
        raise HTTPException(422, f"default language {default_lang!r} is not among the enabled languages {langs}")
    for k in ("name", "website", "login_message_text", "maintenance_mode_message"):
        if k in data and data[k] is not None:
            data[k] = n.clean_text(data[k]) or ""
    if data:
        await set_group(db, "org", {k: v for k, v in data.items() if v is not None or k in ("website",)})
    teacher = await _teacher_role(db)
    if teacher is not None and show is not None:
        # CRBS migration 20250321152500: "show names" = Teacher's view_other_users permissions
        from app.models import Permission

        perms = {p.name: p for p in teacher.permissions}
        if show:
            for name in SHOW_NAME_PERMS:
                if name not in perms:
                    perms[name] = (await db.execute(select(Permission).where(Permission.name == name))).scalar_one()
        else:
            for name in SHOW_NAME_PERMS:
                perms.pop(name, None)
        teacher.permissions = list(perms.values())
    if teacher is not None and (max_b is not None or unlimited):
        teacher.max_active_bookings = None if unlimited else max_b
    await db.commit()
    return await _settings_out(db)


LOGO_MAX_BYTES = 2 * 1024 * 1024


@router.post("/logo")
async def upload_logo(db: DB, _: SettingsAdmin, file: UploadFile = File(...)) -> dict[str, Any]:
    """CRBS ``settings/Organisation``: jpg, png or gif only. The image is decoded and re-encoded (at most
    1600 px), so an SVG or an HTML polyglot can never be served from our origin (audit B2)."""
    raw = await file.read(LOGO_MAX_BYTES + 1)
    if len(raw) > LOGO_MAX_BYTES:
        raise HTTPException(413, "logo larger than 2 MB")
    try:
        data, ext = sanitize_image(raw, max_bytes=LOGO_MAX_BYTES)
    except ImageError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    target = Path(get_settings().upload_dir) / "rooms"  # the only public upload directory
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob("org-logo.*"):
        old.unlink(missing_ok=True)
    (target / f"org-logo{ext}").write_bytes(data)
    url = f"/uploads/rooms/org-logo{ext}"
    await set_group(db, "org", {"logo_url": url})
    await db.commit()
    return {"logo_url": url}


@router.delete("/logo")
async def delete_logo(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    for old in (Path(get_settings().upload_dir) / "rooms").glob("org-logo.*"):
        old.unlink(missing_ok=True)
    await set_group(db, "org", {"logo_url": None})
    await db.commit()
    return {"logo_url": None}


# --- LDAP ---------------------------------------------------------------------------------------------


@router.get("/auth/ldap")
async def get_ldap(db: DB, _: AuthAdmin) -> dict[str, Any]:
    return await get_group(db, "ldap")


@router.put("/auth/ldap")
async def put_ldap(body: LdapSettingsIn, db: DB, _: AuthAdmin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    merged = {**(await get_group(db, "ldap")), **data}
    if merged["enabled"] and not (merged["server"] and merged["port"] and merged["bind_dn_format"]):
        raise HTTPException(422, "server, port and bind DN format are required to enable LDAP")
    if data.get("default_role_id") is not None and await db.get(Role, data["default_role_id"]) is None:
        raise HTTPException(422, f"role {data['default_role_id']} not found")
    if data.get("default_department_id") is not None and await db.get(Program, data["default_department_id"]) is None:
        raise HTTPException(422, f"department {data['default_department_id']} not found")
    await set_group(db, "ldap", data)
    await db.commit()
    return await get_group(db, "ldap")


@router.post("/auth/ldap/test")
async def test_ldap(body: LdapTestIn, db: DB, _: AuthAdmin) -> dict[str, Any]:
    """Bind (and search) with the given or saved settings; nothing is stored and no user is created."""
    cfg = {**(await get_group(db, "ldap")), **(body.settings.model_dump(exclude_unset=True) if body.settings else {})}
    res = bookings_ldap.verify(cfg, body.username.strip(), body.password)
    return {
        "ok": res.ok,
        "errors": res.errors,
        "connection_error": res.connection_error,
        "attributes": res.attributes,
        "mapped": bookings_ldap.map_attributes(cfg, res.attributes) if res.attributes else {},
    }


# --- SMTP ---------------------------------------------------------------------------------------------


@router.get("/smtp")
async def get_smtp(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    out = await get_group(db, "smtp")
    out["configured"] = await smtp_configured(db)
    return out


@router.put("/smtp")
async def put_smtp(body: SmtpSettingsIn, db: DB, _: SettingsAdmin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if data.get("from_address"):
        try:
            data["from_address"] = clean_email(data["from_address"])
        except ValueError as exc:
            raise HTTPException(422, "from_address must be an e-mail address") from exc
    if "password" in data and data["password"] is None:
        data.pop("password")  # null = keep; "" clears
    await set_group(db, "smtp", data)
    await db.commit()
    return await get_smtp(db, _)


@router.post("/smtp/test")
async def test_smtp(body: SmtpTestIn, db: DB, me: SettingsAdmin) -> dict[str, Any]:
    try:
        to = clean_email(body.to)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = await notify(
        db,
        kind="smtp_test",
        to_email=to,
        subject="SmartSched SMTP test",
        body="Bu bir deneme iletisidir. / This is a test message.\n",
        user_id=me.id,
    )
    await db.commit()
    return {"status": row.status, "error": row.error, "outbox_id": row.id}


# --- translations -------------------------------------------------------------------------------------


@router.get("/translations", response_model=list[TranslationOut])
async def list_translations(db: DB, _: CurrentUser, language: str | None = None) -> list[Translation]:
    q = select(Translation).order_by(Translation.language, Translation.set, Translation.key)
    if language:
        q = q.where(Translation.language == language)
    return list((await db.execute(q)).scalars())


@router.put("/translations", response_model=list[TranslationOut])
async def upsert_translations(body: list[TranslationIn], db: DB, _: SettingsAdmin) -> list[Translation]:
    out = []
    for item in body:
        text = item.text.replace("\xa0", " ")
        row = (
            await db.execute(
                select(Translation).where(
                    Translation.language == item.language, Translation.set == item.set, Translation.key == item.key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = Translation(language=item.language, set=item.set, key=item.key, text=text)
            db.add(row)
        else:
            row.text = text
        out.append(row)
    await db.commit()
    return out


@router.delete("/translations/{tid}", status_code=204)
async def delete_translation(tid: int, db: DB, _: SettingsAdmin) -> None:
    await db.execute(delete(Translation).where(Translation.id == tid))
    await db.commit()


async def _language_or_default(db: DB, language: str | None) -> tuple[str, dict[str, Any]]:
    org = await get_group(db, "org")
    lang = (language or org["default_language"] or "tr").strip().lower()
    if lang not in bookings_i18n.SHIPPED_LANGUAGES or lang not in (org["languages"] or []):
        raise HTTPException(422, f"language {lang!r} is not enabled ({', '.join(org['languages'] or [])})")
    return lang, org


@router.get("/i18n")
async def i18n_bundle(db: DB, language: str | None = None) -> dict[str, Any]:
    """Public (the login page is translated too): the strings the backend ships for ``language`` merged with
    the admin overrides of that language (CRBS ``MY_Lang::load_from_db``), plus the date patterns. The
    frontend lays ``messages`` over its own message files."""
    lang, org = await _language_or_default(db, language)
    return {
        "language": lang,
        "default_language": org["default_language"],
        "languages": org["languages"],
        "language_names": {k: bookings_i18n.LANGUAGE_NAMES[k] for k in org["languages"] or []},
        "messages": await bookings_i18n.bundle(db, lang),
        "date_patterns": {k: org[k] for k in ("pattern_long", "pattern_weekday", "pattern_time")},
        "date_defaults": bookings_i18n.DEFAULT_PATTERNS[lang],
    }


@router.get("/date-patterns")
async def date_patterns(db: DB, _: CurrentUser, language: str | None = None) -> dict[str, Any]:
    """The pattern options of CRBS ``Dates::date_pattern_options`` / ``time_pattern_options`` with an example
    each (16 April, 09:30) in ``language``; ``PUT /org/settings`` accepts only these (or "" = default)."""
    lang, org = await _language_or_default(db, language)
    out = bookings_i18n.pattern_options(lang)
    out["current"] = {k: org[k] for k in ("pattern_long", "pattern_weekday", "pattern_time")}
    return out


# --- changelog, events --------------------------------------------------------------------------------

_VERSION_RX = re.compile(r"^##\s+\[?([^\]\s]+)\]?\s*(\d{4}-\d{2}-\d{2})?")


def parse_changelog(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    section = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = _VERSION_RX.match(line)
        if m:
            entries.append({"version": m.group(1), "date": m.group(2), "sections": {}})
            section = None
            continue
        if not entries:
            continue
        if line.startswith("### "):
            section = line[4:].strip().rstrip(":")
            entries[-1]["sections"].setdefault(section, [])
        elif line.lstrip().startswith(("- ", "* ")) and section:
            entries[-1]["sections"][section].append(line.lstrip()[2:].strip())
    return entries


def _entries() -> list[dict[str, Any]]:
    return parse_changelog(CHANGELOG.read_text(encoding="utf-8")) if CHANGELOG.exists() else []


@router.get("/changelog")
async def changelog(db: DB, user: CurrentUser) -> dict[str, Any]:
    """Unread = the newest entry is not the version the user marked as seen (audit B12: a date alone missed a
    second release on the same day). Users who marked an older build (date only) fall back to the date."""
    entries = _entries()
    seen_at = await get_user_value(db, user.id, "changelog_viewed_at")
    seen_version = await get_user_value(db, user.id, "changelog_viewed_version")
    latest = next((e["date"] for e in entries if e.get("date")), None)
    latest_version = entries[0]["version"] if entries else None
    if seen_version is not None:
        unread = latest_version is not None and seen_version != latest_version
    else:
        unread = bool(latest) and (seen_at is None or seen_at[:10] < str(latest))
    return {
        "entries": entries,
        "latest": latest,
        "latest_version": latest_version,
        "viewed_at": seen_at,
        "viewed_version": seen_version,
        "unread": unread,
    }


@router.post("/changelog/seen")
async def changelog_seen(db: DB, user: CurrentUser) -> dict[str, Any]:
    from app.models.base import utcnow

    stamp = utcnow().replace(microsecond=0).isoformat()
    entries = _entries()
    version = entries[0]["version"] if entries else None
    await set_user_value(db, user.id, "changelog_viewed_at", stamp)
    await set_user_value(db, user.id, "changelog_viewed_version", version)
    await db.commit()
    return {"viewed_at": stamp, "version": version}


@router.get("/events")
async def list_events(_: SettingsAdmin) -> dict[str, Any]:
    return {"events": events.EVENT_TYPES, "listeners": events.listeners()}


# --- self-service auth: profile, password ----------------------------------------------------------------


async def _profile(db: DB, u: User) -> ProfileOut:
    role = await db.get(Role, u.role_id) if u.role_id else None
    return ProfileOut(
        id=u.id,
        email=u.email,
        username=u.username,
        firstname=u.firstname,
        lastname=u.lastname,
        displayname=u.full_name,
        ext=u.ext,
        language=u.language,
        department_id=u.department_id,
        role=u.role,
        role_name=role.name if role else None,
    )


@auth_router.get("/permissions")
async def my_permissions(access: CurrentAccess, db: DB) -> dict[str, Any]:
    from app.models import Permission

    mine = [p for p in (await db.execute(select(Permission))).scalars() if p.name in access.perms]
    return {
        "role": access.role.name if access.role else None,
        "role_code": access.role.code if access.role else None,
        "permissions": sorted(access.perms),
        "groups": grouped_permissions(mine),
    }


@auth_router.get("/profile", response_model=ProfileOut)
async def get_profile(db: DB, user: CurrentUser) -> ProfileOut:
    return await _profile(db, user)


@auth_router.put("/profile", response_model=ProfileOut)
async def put_profile(body: ProfileIn, db: DB, user: CurrentUser) -> ProfileOut:
    data = body.model_dump(exclude_unset=True)
    if "email" in data:
        if data["email"]:
            try:
                data["email"] = clean_email(data["email"])
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            clash = (await db.execute(select(User.id).where(User.email == data["email"], User.id != user.id))).scalar()
            if clash is not None:
                raise HTTPException(409, "e-mail already in use")
        else:
            data["email"] = None
    org = await get_group(db, "org")
    if data.get("language") and data["language"] not in (org["languages"] or []):
        raise HTTPException(422, f"language {data['language']!r} is not enabled")
    if "displayname" in data:
        data["full_name"] = data.pop("displayname")
    for k, v in data.items():
        setattr(user, k, n.clean_text(v) if isinstance(v, str) and k != "email" else v)
    await db.commit()
    return await _profile(db, user)


@auth_router.post("/change-password")
async def change_password(body: ChangePasswordIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    """Own password (CRBS ``Profile::save`` / ``new_password``): the current password is required unless
    a forced change is pending; the new password must differ from the current one. Every session of the user
    ends (``signed_out``: the caller signs in again with the new password; parity B-AUTH-11)."""
    if not user.force_password_reset or user.password_hash is None:
        if user.password_hash and not verify_password(body.current_password or "", user.password_hash):
            raise HTTPException(403, "current password is wrong")
    if user.password_hash and verify_password(body.new_password, user.password_hash):
        raise HTTPException(422, "the new password must differ from the current one")
    user.password_hash = hash_password(body.new_password)
    user.force_password_reset = False
    revoke_tokens(user)  # B-AUTH-11: every session, this one included, signs in again with the new password
    await db.commit()
    return {"ok": True, "signed_out": True}


@auth_router.post("/password-reset/request", status_code=202)
async def reset_request(body: ResetRequestIn, db: DB, request: Request) -> dict[str, Any]:
    """Public. With SMTP a one-time code is e-mailed; without SMTP the request is recorded in the outbox
    for the administrators (no code is created). The answer never reveals whether the account exists.
    Audit B10: at most 20 requests per client address per 15 minutes (then 429) and 3 per account (further
    ones answer 202 but send nothing); a new code never revokes the earlier unexpired ones."""
    from app.core import throttle

    address = request.client.host if request.client else "?"
    if throttle.RESET_PER_ADDRESS.hit(f"ip:{address}"):
        raise HTTPException(
            429,
            "too many password reset requests; try again later",
            headers={"Retry-After": str(throttle.RESET_PER_ADDRESS.retry_after(f"ip:{address}"))},
        )
    user = await find_login_user(db, body.email)
    if user is not None and user.is_active and throttle.RESET_PER_ACCOUNT.hit(f"user:{user.id}"):
        user = None  # over the per-account limit: same answer, nothing sent
    if user is not None and user.is_active:
        if user.email and await smtp_configured(db):
            await issue_reset_token(db, user, None, revoke_others=False)
        else:
            await notify(
                db,
                kind="password_reset_request",
                to_email=None,
                subject=f"Password reset requested by {user.username or user.email}",
                body="Issue a one-time code under Users → reset password; SMTP is not configured.",
                user_id=user.id,
            )
        await db.commit()
    return {"detail": "if the account exists, instructions were sent or an administrator was notified"}


@auth_router.post("/password-reset/confirm")
async def reset_confirm(body: ResetConfirmIn, db: DB) -> dict[str, Any]:
    user = await consume_reset_token(db, body.token, body.password)
    if user is None:
        raise HTTPException(400, "invalid or expired code")
    await db.commit()
    return {"ok": True, "user_id": user.id}
