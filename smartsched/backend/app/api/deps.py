"""FastAPI dependencies: DB session, current user, permission guards (CRBS role -> permission sets).

The historic ``Viewer`` / ``Planner`` / ``Admin`` guards are kept by name and now check the permissions
``planning.view`` / ``planning.edit`` / ``planning.admin`` of the user's role (docs/CRBS_PARITY.md §1).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.security import decode_access_token, token_is_current
from app.models import User
from app.services.bookings_perms import LEGACY_GUARDS, Access, load_access

bearer = HTTPBearer(auto_error=False)

#: routes a user flagged with ``force_password_reset`` may still call (CRBS ``check_password_reset``)
PASSWORD_CHANGE_ALLOWED = ("/auth/me", "/auth/change-password", "/auth/permissions", "/auth/logout")


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DB
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:  # generic message: no library internals to the client (review MINOR 5)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    try:
        user_id = int(payload.get("uid", 0))
    except (TypeError, ValueError):
        user_id = 0
    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    if not token_is_current(payload, user):  # signed out, password changed, disabled or role changed since
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")
    if (
        user.force_password_reset
        and user.auth_source != "ldap"
        and not request.url.path.endswith(PASSWORD_CHANGE_ALLOWED)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "password_change_required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_access(user: CurrentUser, db: DB) -> Access:
    return await load_access(db, user)


CurrentAccess = Annotated[Access, Depends(get_access)]


#: the Turkish name of every permission, as the Roller ve izinler screen shows it (``messages/tr.json`` ``crbs.perm``;
#: ``tests/test_loop_r1_lane_d.py`` keeps the two in step): a refusal names the permission in the reader's words
PERMISSION_TR: dict[str, str] = {
    "system.bypass_maintenance_mode": "Bakım modunda rezervasyon kullanma",
    "system.export_bookings": "Rezervasyonları dışa aktarma (CSV)",
    "system.view_all_sessions": "Geçmiş ve gelecek dönemleri görme",
    "setup.authentication": "Oturum açma ayarları (LDAP)",
    "setup.departments": "Bölümler",
    "setup.roles": "Roller ve izinler",
    "setup.rooms": "Salonlar, gruplar ve özel alanlar",
    "setup.rooms_acl": "Salon erişimi",
    "setup.schedules": "Ders saatleri",
    "setup.sessions": "Dönemler, tatiller ve hafta tarihleri",
    "setup.settings": "Kurum ayarları",
    "setup.timetable_weeks": "Ders haftaları",
    "setup.users": "Kullanıcılar",
    "room.view": "Salonları ve rezervasyonlarını görme",
    "book_single.create": "Tek seferlik: oluşturma",
    "book_single.edit_other_booking": "Tek seferlik: başkasınınkini düzenleme",
    "book_single.cancel_other_booking": "Tek seferlik: başkasınınkini iptal",
    "book_single.set_user": "Tek seferlik: başkası adına",
    "book_single.set_department": "Tek seferlik: bölüm seçme",
    "book_single.view_other_notes": "Tek seferlik: başkalarının notları",
    "book_single.view_other_users": "Tek seferlik: rezerve edeni görme",
    "book_recur.create": "Tekrarlayan: oluşturma",
    "book_recur.edit_other_booking": "Tekrarlayan: başkasınınkini düzenleme",
    "book_recur.cancel_other_booking": "Tekrarlayan: başkasınınkini iptal",
    "book_recur.set_user": "Tekrarlayan: başkası adına",
    "book_recur.set_department": "Tekrarlayan: bölüm seçme",
    "book_recur.view_other_notes": "Tekrarlayan: başkalarının notları",
    "book_recur.view_other_users": "Tekrarlayan: rezerve edeni görme",
    "planning.view": "Planlama verilerini görme",
    "planning.edit": "İçe aktarma, düzenleme ve ders programı yayımlama",
    "planning.admin": "Planlama yönetimi",
    "rooms.features": "Derslik özelliklerini ve değerlerini yönet",
    "audit.view": "Her değişikliğin denetim kaydını gör",
    "approvals.decide": "Rezervasyon taleplerini onayla ya da reddet (atanmış onaycılar)",
    "book_single.request": "Bir onaycının onaylayacağı tek seferlik rezervasyon iste",
    "book_recur.request": "Bir onaycının onaylayacağı yinelenen rezervasyon iste",
    "bookings.skip_approval": "Onaysız doğrudan rezervasyon",
}


def forbidden(*names: str) -> HTTPException:
    """403 for a missing permission (round-1 T-R1-29): ``{code: forbidden, permission, permissions, message,
    message_en, message_tr}``; ``message`` / ``message_en`` keep the historic English text
    (``requires permission planning.view``), ``message_tr`` names the permission as the roles screen does
    (``Bu işlem için "Planlama verilerini görme" izni gerekiyor``)."""
    en = f"requires permission {' or '.join(names)}"
    labels = " ya da ".join(f'"{PERMISSION_TR.get(n, n)}"' for n in names)
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        {
            "code": "forbidden",
            "permission": names[0] if names else None,
            "permissions": list(names),
            "message": en,
            "message_en": en,
            "message_tr": f"Bu işlem için {labels} izni gerekiyor",
        },
    )


def require_permission(*names: str) -> Callable[..., object]:
    """Guard: the user's role must hold at least one of ``names`` (role-level, no room ACL)."""

    async def _guard(access: CurrentAccess) -> User:
        if not any(n in access.perms for n in names):
            raise forbidden(*names)
        return access.user

    return _guard


def require_role(minimum: str) -> Callable[..., object]:
    """Historic guard name: VIEWER / PLANNER / ADMIN -> planning.view / planning.edit / planning.admin."""
    return require_permission(LEGACY_GUARDS[minimum])


Viewer = Annotated[User, Depends(require_role("VIEWER"))]
Planner = Annotated[User, Depends(require_role("PLANNER"))]
Admin = Annotated[User, Depends(require_role("ADMIN"))]


def perm(*names: str) -> object:
    """``Annotated[User, perm("setup.users")]`` shorthand."""
    return Depends(require_permission(*names))


UsersAdmin = Annotated[User, Depends(require_permission("setup.users"))]


def consent_gate(purpose: str) -> Callable[..., object]:
    """Route dependency: the signed-in user must hold an active KVKK consent for ``purpose``, else 409
    ``consent_required`` (``app.services.kvkk.require_consent``; detail with TR/EN text, ``grant_path``). Any upload
    path that stores a person's photo depends on ``consent_gate("photo")``; there is no such route yet::

        @router.post("/me/photo")
        async def upload(user: Annotated[User, Depends(consent_gate("photo"))], ...): ...
    """
    from app.services import kvkk

    if purpose not in kvkk.PURPOSES:
        raise ValueError(f"unknown consent purpose {purpose!r}")

    async def _gate(db: DB, user: CurrentUser) -> User:
        try:
            await kvkk.require_consent(db, user, purpose)
        except kvkk.KvkkError as exc:
            raise HTTPException(exc.status, exc.as_detail()) from exc
        return user

    return _gate
