"""CRBS-style permissions: catalogue (``data.sql``), seeded roles, role ∪ room-ACL resolution, booking limits.

``has_permission(user, p)`` in CRBS checks only the role; ``has_permission(user, p, room_id)`` adds the ACL
entries of that room and its room group whose context is the user, the user's role or department
(``BookingPermissions::get_allowed_permissions`` / ``Auth_model::user_room_permissions``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Permission, Role, RoomAcl, User, UserConstraint
from app.models.catalog import Room

# (name, description) in CRBS order; ids in data.sql are 1..28
CRBS_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("system.bypass_maintenance_mode", "Use bookings while maintenance mode is on"),
    ("system.export_bookings", "Export bookings to CSV"),
    ("system.view_all_sessions", "View past and future sessions, not only selectable ones"),
    ("setup.authentication", "Configure authentication (LDAP)"),
    ("setup.departments", "Manage departments"),
    ("setup.roles", "Manage roles and permissions"),
    ("setup.rooms", "Manage rooms, room groups and custom fields"),
    ("setup.rooms_acl", "Manage room access control"),
    ("setup.schedules", "Manage schedules and periods"),
    ("setup.sessions", "Manage sessions, holidays and timetable week dates"),
    ("setup.settings", "Manage organisation and general settings"),
    ("setup.timetable_weeks", "Manage timetable weeks"),
    ("setup.users", "Manage users"),
    ("room.view", "View rooms and their bookings"),
    ("book_single.create", "Create single bookings"),
    ("book_single.edit_other_booking", "Edit other users' single bookings"),
    ("book_single.cancel_other_booking", "Cancel other users' single bookings"),
    ("book_single.set_user", "Set the user of a single booking"),
    ("book_single.set_department", "Set the department of a single booking"),
    ("book_single.view_other_notes", "View notes of other users' single bookings"),
    ("book_single.view_other_users", "View the user of other users' single bookings"),
    ("book_recur.create", "Create recurring bookings"),
    ("book_recur.edit_other_booking", "Edit other users' recurring bookings"),
    ("book_recur.cancel_other_booking", "Cancel other users' recurring bookings"),
    ("book_recur.set_user", "Set the user of a recurring booking"),
    ("book_recur.set_department", "Set the department of a recurring booking"),
    ("book_recur.view_other_notes", "View notes of other users' recurring bookings"),
    ("book_recur.view_other_users", "View the user of other users' recurring bookings"),
)
SMARTSCHED_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("planning.view", "View planning data: terms, requests, runs, timetables"),
    ("planning.edit", "Import, edit requests and rules, generate and publish timetables"),
    ("planning.admin", "Planning administration: AI settings, built-in rules"),
)
ALL_PERMISSIONS: tuple[tuple[str, str], ...] = CRBS_PERMISSIONS + SMARTSCHED_PERMISSIONS
PERMISSION_NAMES: frozenset[str] = frozenset(n for n, _ in ALL_PERMISSIONS)

GROUP_ORDER = ("system", "setup", "planning", "room", "book_single", "book_recur")
ACTION_ORDER = (
    "create",
    "edit_other_booking",
    "cancel_other_booking",
    "set_user",
    "set_department",
    "view_other_notes",
    "view_other_users",
)
#: permissions that may be granted on a room / room group (CRBS ``Permissions_model::SCOPE_BOOKINGS``)
BOOKING_SCOPE_GROUPS = ("room", "book_single", "book_recur")


def perm_group(name: str) -> str:
    return name.split(".", 1)[0]


def _book(*actions: str) -> set[str]:
    return {f"book_{kind}.{a}" for kind in ("single", "recur") for a in actions}


ROLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "ADMIN": {"name": "Administrator", "description": "Administrator", "permissions": set(PERMISSION_NAMES)},
    "TEACHER": {
        "name": "Teacher",
        "description": "Teacher",
        # verbatim from crbs-core/application/modules/install/resources/data.sql (role 2)
        "permissions": {
            "room.view",
            "book_single.create",
            "book_single.view_other_notes",
            "book_recur.view_other_notes",
        },
    },
    "PLANNER": {
        "name": "Planner",
        "description": "Planning office: imports, timetables and bookings",
        "permissions": {
            "planning.view",
            "planning.edit",
            "system.view_all_sessions",
            "system.export_bookings",
            "system.bypass_maintenance_mode",
            "room.view",
        }
        | _book(*ACTION_ORDER),
    },
    "VIEWER": {
        "name": "Viewer",
        "description": "Read-only access to plans and bookings",
        "permissions": {"planning.view", "room.view"} | _book("view_other_notes", "view_other_users"),
    },
}
ROLE_CODES = tuple(ROLE_DEFAULTS)

#: legacy guards (``app.api.deps``) -> permission
LEGACY_GUARDS = {"VIEWER": "planning.view", "PLANNER": "planning.edit", "ADMIN": "planning.admin"}


async def ensure_permissions_and_roles(session: AsyncSession) -> dict[str, Role]:
    """Idempotent seed of the permission catalogue and the four default roles (never touches custom roles;
    existing seeded roles keep admin edits, except that Administrator always holds every permission)."""
    perms = {p.name: p for p in (await session.execute(select(Permission))).scalars()}
    for name, desc in ALL_PERMISSIONS:
        if name not in perms:
            perms[name] = Permission(name=name, group=perm_group(name), description=desc)
            session.add(perms[name])
    await session.flush()
    roles = {r.code: r for r in (await session.execute(select(Role).where(Role.code.is_not(None)))).scalars()}
    for code, spec in ROLE_DEFAULTS.items():
        role = roles.get(code)
        if role is None:
            clash = (await session.execute(select(Role).where(Role.name == spec["name"]))).scalar_one_or_none()
            if clash is not None and clash.code is None:
                clash.code = code  # adopt a same-named custom role
                role = clash
            else:
                role = Role(code=code, name=spec["name"], description=spec["description"])
                session.add(role)
                role.permissions = [perms[n] for n in sorted(spec["permissions"])]
            roles[code] = role
    admin = roles["ADMIN"]
    have = {p.name for p in admin.permissions}
    if have != set(PERMISSION_NAMES):
        admin.permissions = [perms[n] for n in sorted(PERMISSION_NAMES)]
    await session.flush()
    return {k: v for k, v in roles.items() if k is not None}


def set_user_role(user: User, role: Role | None) -> None:
    """Keep ``users.role_id`` and the coarse ``users.role`` code in sync."""
    user.role_id = role.id if role is not None else None
    user.role = (role.code or "CUSTOM") if role is not None else "NONE"


async def user_role(session: AsyncSession, user: User) -> Role | None:
    if user.role_id is not None:
        return await session.get(Role, user.role_id)
    if user.role in ROLE_DEFAULTS:
        return (await session.execute(select(Role).where(Role.code == user.role))).scalar_one_or_none()
    return None


#: Deliberate security difference (docs/review/2026-10-08-crbs-parity-audit.md): CRBS ``Users::save`` lets
#: anyone holding ``setup.users`` give any role, Administrator included. SmartSched also asks for
#: ``setup.roles`` before user management grants -- or takes over the account of -- a privileged role.
GRANT_GUARD = "setup.roles"


def is_privileged_role(role: Role | None) -> bool:
    """Administrator, or any role holding ``setup.roles`` (which can give itself every permission)."""
    return role is not None and (role.code == "ADMIN" or any(p.name == GRANT_GUARD for p in role.permissions))


async def may_grant_role(session: AsyncSession, actor: User, role: Role | None) -> bool:
    return not is_privileged_role(role) or GRANT_GUARD in (await load_access(session, actor)).perms


async def may_manage_user(session: AsyncSession, actor: User, target: User) -> bool:
    """Whether ``actor`` may edit, disable, delete or set the password of ``target`` (privileged accounts
    need ``setup.roles``; anyone may manage their own account)."""
    if actor.id == target.id:
        return True
    role = await user_role(session, target)
    if role is None and target.role == "ADMIN":  # roles table not seeded
        return GRANT_GUARD in (await load_access(session, actor)).perms
    return await may_grant_role(session, actor, role)


@dataclass
class Access:
    """A user's permissions for one request: role permissions plus room ACL entries."""

    user: User
    role: Role | None
    perms: frozenset[str]
    acl_rooms: dict[int, set[str]] = field(default_factory=dict)
    acl_groups: dict[int, set[str]] = field(default_factory=dict)

    @property
    def user_id(self) -> int:
        return self.user.id

    def can(self, name: str, room: Room | None = None) -> bool:
        if name in self.perms:
            return True
        if room is None:
            return False
        return name in self.room_acl(room)

    def room_acl(self, room: Room) -> set[str]:
        out = set(self.acl_rooms.get(room.id, set()))
        if room.room_group_id is not None:
            out |= self.acl_groups.get(room.room_group_id, set())
        return out

    def can_view_room(self, room: Room) -> bool:
        return self.can("room.view", room)


async def load_access(session: AsyncSession, user: User) -> Access:
    cached = user.__dict__.get("_crbs_access")
    if isinstance(cached, Access):
        return cached
    role = await user_role(session, user)
    if role is not None:
        perms = frozenset(p.name for p in role.permissions)
    elif user.role_id is None and user.role in ROLE_DEFAULTS:
        # roles table not seeded (bare DB): fall back to the built-in sets
        perms = frozenset(ROLE_DEFAULTS[user.role]["permissions"])
    else:
        perms = frozenset()
    contexts = [(RoomAcl.context_type == "user") & (RoomAcl.context_id == user.id)]
    if role is not None:
        contexts.append((RoomAcl.context_type == "role") & (RoomAcl.context_id == role.id))
    if user.department_id is not None:
        contexts.append((RoomAcl.context_type == "department") & (RoomAcl.context_id == user.department_id))
    acc = Access(user=user, role=role, perms=perms)
    for acl in (await session.execute(select(RoomAcl).where(or_(*contexts)))).scalars():
        names = {p.name for p in acl.permissions}
        target = acc.acl_rooms if acl.entity_type == "room" else acc.acl_groups
        target.setdefault(acl.entity_id, set()).update(names)
    user.__dict__["_crbs_access"] = acc
    return acc


def forget_access(user: User) -> None:
    user.__dict__.pop("_crbs_access", None)


# --------------------------------------------------------------------------------------------------
# Booking limits (role values with per-user R/U/X overrides)
# --------------------------------------------------------------------------------------------------

LIMIT_KEYS = ("max_active_bookings", "range_min", "range_max", "recur_max_instances")


async def user_constraint_row(session: AsyncSession, user_id: int) -> UserConstraint | None:
    return await session.get(UserConstraint, user_id)


async def effective_limits(session: AsyncSession, user: User) -> dict[str, int | None]:
    """``Users_model::get_constraints``: R = role value, U = user value, X = unlimited."""
    role = await user_role(session, user)
    row = await user_constraint_row(session, user.id)
    out: dict[str, int | None] = {}
    for key in LIMIT_KEYS:
        kind = getattr(row, f"{key}_type", "R") if row is not None else "R"
        if kind == "U":
            out[key] = getattr(row, f"{key}_value")
        elif kind == "X":
            out[key] = None
        else:
            out[key] = getattr(role, key) if role is not None else None
    return out


def grouped_permissions(perms: list[Permission]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """``Permissions_model::get_scoped``: {"system": {group: [...]}, "bookings": {group: [...]}}."""
    by_group: dict[str, list[Permission]] = {}
    for p in perms:
        by_group.setdefault(p.group, []).append(p)

    def order(p: Permission) -> tuple[int, str]:
        action = p.name.split(".", 1)[1]
        return (ACTION_ORDER.index(action) if action in ACTION_ORDER else 99, p.name)

    out: dict[str, dict[str, list[dict[str, Any]]]] = {"system": {}, "bookings": {}}
    for g in GROUP_ORDER + tuple(sorted(set(by_group) - set(GROUP_ORDER))):
        items = sorted(by_group.get(g, []), key=order)
        if not items:
            continue
        scope = "bookings" if g in BOOKING_SCOPE_GROUPS else "system"
        out[scope][g] = [{"id": p.id, "name": p.name, "description": p.description} for p in items]
    return out
