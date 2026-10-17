"""Welcome guide per role: audiences, the ``show`` decision, checklist signals, admin texts, stats, KVKK hooks
(WG-01…WG-03; docs/design/v3/welcome-guide.md §5, §6, §7; API in ``app/api/v1/welcome.py``).

**Audiences** come from permissions and the instructor link, never from role codes (§5.9 precedence
admin > planner > viewer > dept_admin > approver > academician > staff). The first is the primary audience.

**One automatic surface per call** (:func:`payload`; the client also keeps one per session):

* T1 first sign-in: no ``sheet`` row -> the sheet;
* T3 role change: an audience the person was never welcomed for -> a ``delta`` sheet with only the new audiences;
* T4 "show again": an audience's ``content_version`` above the one the person saw -> the sheet, ``updated``;
* T2 "Sonra": ``snoozed_until`` passed -> the sheet again. A snooze lasts 3 days, at most twice; the third
  "Sonra" ends the automatic sheet (checklist only);
* T5 a feature hint (:mod:`app.services.welcome_hints`) when no sheet is due.

"Bir daha gösterme" (``dismissed``) and a running snooze stop T1-T4. Deep links, kiosk / embed / public pages, the
excluded routes and maintenance mode (without ``system.bypass_maintenance_mode``) get nothing.

**Checklist signals** are read from the rows the real action wrote (bookings, series, approval decisions, channels,
calendar links, runs, audit events of a commit / publish / decision, settings), in one statement. Only view-only
items accept the client's ``item_done``. Done items are kept in the ``checklist`` row (sticky; the stats read it).

**Admin**: switches (settings group ``welcome``), text overrides per audience / locale / field with a version check
(409 ``stale``), "show again", completion stats (aggregate in ``rls.system_scope``, groups under ``min_cohort``
hidden, no per-person output). Every admin change is audited (``welcome.settings_update`` / ``content_update`` /
``reshow``). KVKK: :func:`dsr_rows` (DSR export) and :func:`erase` (erasure), called by ``app.services.kvkk``.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls
from app.importers.normalize import tr_lower
from app.models import (
    ApprovalDecision,
    AuditEvent,
    Booking,
    BookingSeries,
    CalendarConnection,
    CalendarFeedToken,
    Instructor,
    Room,
    ScheduleRun,
    Setting,
    User,
    UserChannel,
)
from app.models.base import utcnow
from app.models.sso import SsoInvite
from app.models.welcome import WelcomeContent, WelcomeProgress
from app.services import audit
from app.services import welcome_hints as hints


def _now() -> datetime:
    """The guide's clock (naive UTC, as the tables store it); tests replace it."""
    return utcnow()


# --------------------------------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------------------------------


class WelcomeError(Exception):
    """A refusal with Turkish and English text (``detail`` of the HTTP error)."""

    def __init__(self, status: int, code: str, message_en: str, message_tr: str, **data: Any) -> None:
        super().__init__(message_en)
        self.status, self.code, self.message_en, self.message_tr, self.data = status, code, message_en, message_tr, data

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message_en,
            "message_en": self.message_en,
            "message_tr": self.message_tr,
            **self.data,
        }


# --------------------------------------------------------------------------------------------------
# audiences
# --------------------------------------------------------------------------------------------------

#: precedence order (§5.9): the first one a person matches is their primary audience
AUDIENCES: tuple[str, ...] = ("admin", "planner", "viewer", "dept_admin", "approver", "academician", "staff")
AUDIENCE_LABELS: dict[str, dict[str, str]] = {
    "admin": {"tr": "Yönetici", "en": "Administrator"},
    "planner": {"tr": "Planlamacı", "en": "Planner"},
    "viewer": {"tr": "İzleyici", "en": "Viewer"},
    "dept_admin": {"tr": "Bölüm yöneticisi", "en": "Department admin"},
    "approver": {"tr": "Onaylayıcı", "en": "Approver"},
    "academician": {"tr": "Öğretim elemanı", "en": "Academician"},
    "staff": {"tr": "İdari personel", "en": "Staff"},
}
#: audiences that book rooms (median days to the first booking in the stats)
BOOKING_AUDIENCES = frozenset({"academician", "staff", "dept_admin"})
DEPT_ADMIN_PERMS = frozenset(
    {"book_single.set_user", "book_recur.set_user", "book_single.set_department", "book_recur.set_department",
     "book_recur.create"}
)
BOOKER_PERMS = frozenset({"book_single.create", "book_single.request"})


def audiences_for(perms: Iterable[str], *, instructor_linked: bool) -> list[str]:
    """The person's audiences in precedence order (research §1.3). Never reads role codes."""
    p = set(perms)
    found: set[str] = set()
    if "planning.admin" in p or any(x.startswith("setup.") for x in p):
        found.add("admin")
    if "planning.edit" in p:
        found.add("planner")
    if "planning.view" in p and "planning.edit" not in p:
        found.add("viewer")
    if DEPT_ADMIN_PERMS & p and "planning.edit" not in p:
        found.add("dept_admin")
    if "approvals.decide" in p:
        found.add("approver")
    if BOOKER_PERMS & p and "planning.view" not in p:
        found.add("academician" if instructor_linked else "staff")
    return [a for a in AUDIENCES if a in found]


def audience_hash(auds: Iterable[str]) -> str:
    return hashlib.sha256(",".join(sorted(set(auds))).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------------------------------
# product content per audience (order, links, anchors; the copy is in messages/{tr,en}.json welcome.*)
# --------------------------------------------------------------------------------------------------

#: sheet cards (key, href) in order
CARDS: dict[str, tuple[tuple[str, str], ...]] = {
    "academician": (
        ("quick_reserve", "/reserve"),
        ("my_requests", "/moderation/me"),
        ("my_bookings", "/my-bookings"),
        ("calendar", "/profile#calendar"),
    ),
    "staff": (
        ("quick_reserve", "/reserve"),
        ("find_room", "/find-room"),
        ("approval_rooms", "/find-room"),
        ("my_bookings", "/my-bookings"),
    ),
    "approver": (("approvals_inbox", "/approvals"),),
    "dept_admin": (
        ("book_for_other", "/bookings"),
        ("recurring", "/bookings"),
        ("department_calendar", "/profile#calendar"),
    ),
    "viewer": (
        ("dashboard", "/dashboard"),
        ("timetable", "/timetable"),
        ("runs", "/runs"),
        ("heatmap", "/analytics/heatmap"),
    ),
    "planner": (
        ("from_files", "/onboarding"),
        ("requests", "/requests"),
        ("generate", "/generate"),
        ("timetable", "/timetable"),
        ("publish", "/runs"),
    ),
    "admin": (
        ("users_roles", "/admin/users"),
        ("rooms_access", "/admin/rooms"),
        ("term_times", "/admin/sessions"),
        ("rules_connections", "/admin/integrations"),
        ("welcome_guide", "/admin/welcome"),
    ),
}
MAX_CARDS = 5
MAX_PRIMARY_WITH_ALSO = 4


@dataclass(frozen=True)
class Step:
    anchor: str
    route: str | None = None
    interactive: bool = False


TOURS: dict[str, tuple[Step, ...]] = {
    "academician": (
        Step("nav-reserve"),
        Step("reserve-when", "/reserve", True),
        Step("nav-my-bookings"),
        Step("nav-my-requests"),
        Step("user-menu"),
    ),
    "staff": (Step("nav-reserve"), Step("nav-find-room"), Step("nav-my-bookings"), Step("user-menu")),
    "approver": (Step("nav-approvals"), Step("approvals-row-actions", "/approvals"), Step("user-menu")),
    "dept_admin": (Step("nav-reserve"), Step("nav-bookings"), Step("nav-my-bookings"), Step("user-menu")),
    "viewer": (Step("nav-dashboard"), Step("nav-timetable"), Step("nav-runs"), Step("nav-heatmap")),
    "planner": (
        Step("nav-onboarding"),
        Step("nav-requests"),
        Step("nav-generate"),
        Step("nav-timetable"),
        Step("nav-moderation"),
        Step("nav-runs"),
    ),
    "admin": (
        Step("nav-admin", "/admin"),
        Step("admin-group-users"),
        Step("admin-group-resources"),
        Step("admin-group-timetable"),
        Step("nav-integrations"),
        Step("nav-welcome-admin"),
    ),
}
#: the steps (1-based numbers of its own tour) an audience adds when it is secondary
EXTRA_STEPS: dict[str, tuple[int, ...]] = {"approver": (1, 2), "dept_admin": (2,)}
MAX_STEPS = 7

CHECKLISTS: dict[str, tuple[str, ...]] = {
    "academician": ("profile", "first_booking", "channel", "calendar", "requests_seen"),
    "staff": ("profile", "first_booking", "find_room_filter", "channel", "calendar_bookings"),
    "approver": ("first_decision", "approver_channel"),
    "dept_admin": ("book_for_other", "recurring"),
    "viewer": ("timetable_seen", "compare_seen", "channel"),
    "planner": ("intake_done", "requests_reviewed", "first_run", "published"),
    "admin": ("org_ready", "rooms_added", "users_invited", "mail_ready", "welcome_reviewed"),
}
ITEM_HREF: dict[str, str] = {
    "profile": "/profile",
    "first_booking": "/reserve",
    "channel": "/profile#notifications",
    "calendar": "/profile#calendar",
    "requests_seen": "/moderation/me",
    "find_room_filter": "/find-room",
    "calendar_bookings": "/profile#calendar",
    "first_decision": "/approvals",
    "approver_channel": "/profile#notifications",
    "book_for_other": "/bookings",
    "recurring": "/bookings",
    "timetable_seen": "/timetable",
    "compare_seen": "/runs/compare",
    "intake_done": "/onboarding",
    "requests_reviewed": "/requests",
    "first_run": "/generate",
    "published": "/runs",
    "org_ready": "/admin/settings",
    "rooms_added": "/admin/rooms",
    "users_invited": "/admin/users",
    "mail_ready": "/admin/email",
    "welcome_reviewed": "/admin/welcome",
}
#: view-only items: the app cannot detect them, the client posts ``item_done`` when the page is opened
MANUAL_ITEMS = frozenset({"requests_seen", "timetable_seen", "compare_seen", "welcome_reviewed", "find_room_filter"})
MAX_ITEMS = 6

# --------------------------------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------------------------------

#: never an automatic surface (§6.2)
EXCLUDED_PREFIXES = ("/setup", "/login", "/welcome", "/reset-password", "/public", "/slot-display", "/print")
#: an audience's home: the only first routes that may be interrupted (a deep link never is)
HOME_ROUTES = frozenset(
    {"/", "/dashboard", "/bookings", "/reserve", "/my-bookings", "/approvals", "/admin", "/profile", "/timetable"}
)


def _path(route: str) -> str:
    p = re.split(r"[?#]", route.strip(), maxsplit=1)[0] or "/"
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def route_suppression(first_route: str | None) -> str | None:
    """``excluded_route`` / ``deep_link`` / None for the first route of the page load."""
    if first_route is None or not first_route.strip():
        return None
    p = _path(first_route)
    if any(p == x or p.startswith(x + "/") for x in EXCLUDED_PREFIXES):
        return "excluded_route"
    if p in HOME_ROUTES or re.fullmatch(r"/admin/[a-z0-9-]+", p):
        return None
    return "deep_link"


# --------------------------------------------------------------------------------------------------
# settings group "welcome"
# --------------------------------------------------------------------------------------------------

PREFIX = "welcome."
SWITCHES: dict[str, bool] = {
    "enabled": True,
    "sheet": True,
    "tour": True,
    "checklist": True,
    "hints": True,
    "hints_for_all": False,
}
MIN_COHORT = 5
SNOOZE_DAYS = 3
MAX_SNOOZES = 2  # "Sonra" brings it back twice; the third ends the automatic sheet
STATS_DAYS = (7, 30, 90)
_TRUE = {"1", "true", "yes", "on"}


@dataclass
class Settings:
    raw: dict[str, str | None]

    def switch(self, key: str) -> bool:
        v = self.raw.get(PREFIX + key)
        return SWITCHES[key] if v is None else v.strip().lower() in _TRUE

    def int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.raw.get(PREFIX + key) or default)
        except ValueError:
            return default

    def content_version(self, aud: str) -> int:
        return self.int(f"content_version.{aud}")

    def text_version(self, aud: str) -> int:
        return self.int(f"text_version.{aud}")

    @property
    def min_cohort(self) -> int:
        return max(MIN_COHORT, self.int("min_cohort", MIN_COHORT))

    @property
    def hints_for_all_at(self) -> datetime | None:
        if not self.switch("hints_for_all"):
            return None
        v = self.raw.get(PREFIX + "hints_for_all_at")
        try:
            return datetime.fromisoformat(v) if v else None
        except ValueError:
            return None

    def get(self, key: str) -> str | None:
        return self.raw.get(key)

    def switches(self) -> dict[str, Any]:
        return {**{k: self.switch(k) for k in SWITCHES}, "min_cohort": self.min_cohort}


def _org_keys(uid: int | None) -> list[str]:
    keys = [
        "org.name",
        "org.maintenance_mode",
        "org.default_language",
        "timezone",
        "smtp.host",
        "smtp.from_address",
    ]
    if uid is not None:
        keys.append(f"user.{uid}.notification_prefs")
    return keys


async def load_settings(session: AsyncSession, uid: int | None = None) -> Settings:
    """The ``welcome.*`` rows plus the organisation / mail / personal rows the signals need (one statement)."""
    q = select(Setting.key, Setting.value).where(or_(Setting.key.like(PREFIX + "%"), Setting.key.in_(_org_keys(uid))))
    return Settings({k: v for k, v in (await session.execute(q)).all()})


async def _set(session: AsyncSession, key: str, value: str | None) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value, is_secret=False))
    else:
        row.value = value
    await session.flush()


# --------------------------------------------------------------------------------------------------
# signals (one statement)
# --------------------------------------------------------------------------------------------------

FACTS = (
    "instructor_linked",
    "booking",
    "channel_linked",
    "feed_token",
    "calendar_connection",
    "first_decision",
    "book_for_other",
    "recurring",
    "intake_done",
    "requests_reviewed",
    "first_run",
    "published",
    "rooms_added",
    "other_users",
    "invites",
)


async def facts_of(session: AsyncSession, uid: int) -> dict[str, bool]:
    """What the person (and, for the admin items, the organisation) has really done, from the rows the action wrote."""

    def acted(*actions: str) -> Any:
        return exists().where(AuditEvent.actor_id == uid, AuditEvent.action.in_(actions))

    cols = [
        exists().where(Instructor.user_id == uid),
        exists().where(or_(Booking.user_id == uid, Booking.created_by == uid)),
        exists().where(UserChannel.user_id == uid, UserChannel.status == "active"),
        exists().where(CalendarFeedToken.user_id == uid),
        exists().where(CalendarConnection.user_id == uid),
        exists().where(ApprovalDecision.approver_user_id == uid),
        exists().where(Booking.created_by == uid, Booking.user_id.is_not(None), Booking.user_id != uid),
        exists().where(BookingSeries.created_by == uid),
        acted("council.commit"),
        acted("preference.accept", "preference.reject"),
        exists().where(ScheduleRun.created_by == uid),
        acted("run.activate"),
        exists().where(Room.id.is_not(None)),
        exists().where(User.id != uid),
        exists().where(SsoInvite.id.is_not(None)),
    ]
    row = (await session.execute(select(*(c.label(n) for c, n in zip(cols, FACTS, strict=True))))).one()
    return {n: bool(v) for n, v in zip(FACTS, row, strict=True)}


def signals(user: User, facts: Mapping[str, bool], st: Settings) -> dict[str, bool]:
    """``done`` of every detectable checklist item (§6.4)."""
    channel = facts["channel_linked"] or st.get(f"user.{user.id}.notification_prefs") is not None
    calendar = facts["feed_token"] or facts["calendar_connection"]
    return {
        "profile": user.department_id is not None and bool(user.language),
        "first_booking": facts["booking"],
        "channel": channel,
        "approver_channel": channel,
        "calendar": calendar,
        "calendar_bookings": calendar,
        "first_decision": facts["first_decision"],
        "book_for_other": facts["book_for_other"],
        "recurring": facts["recurring"],
        "intake_done": facts["intake_done"],
        "requests_reviewed": facts["requests_reviewed"],
        "first_run": facts["first_run"],
        "published": facts["published"],
        "org_ready": bool((st.get("org.name") or "").strip()) and st.get("timezone") is not None,
        "rooms_added": facts["rooms_added"],
        "users_invited": facts["other_users"] or facts["invites"],
        "mail_ready": bool((st.get("smtp.host") or "").strip() and (st.get("smtp.from_address") or "").strip()),
    }


# --------------------------------------------------------------------------------------------------
# composition
# --------------------------------------------------------------------------------------------------


def _cards(auds: list[str], *, delta: bool) -> list[dict[str, Any]]:
    if not auds:
        return []
    if delta:
        out = [{"key": k, "audience": a, "href": h, "also": False} for a in auds for k, h in CARDS[a]]
        return out[:MAX_CARDS]
    primary, secondary = auds[0], auds[1:]
    also = [{"key": CARDS[a][0][0], "audience": a, "href": CARDS[a][0][1], "also": True} for a in secondary]
    n_primary = MAX_CARDS if not also else max(MAX_PRIMARY_WITH_ALSO, MAX_CARDS - len(also))
    own = [{"key": k, "audience": primary, "href": h, "also": False} for k, h in CARDS[primary][:n_primary]]
    return (own + also)[:MAX_CARDS]


def _steps(auds: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(aud: str, n: int) -> None:
        s = TOURS[aud][n - 1]
        if s.anchor in seen:
            return
        seen.add(s.anchor)
        out.append(
            {"key": f"{aud}.{n}", "audience": aud, "anchor": s.anchor, "route": s.route, "interactive": s.interactive}
        )

    if auds:
        for n in range(1, len(TOURS[auds[0]]) + 1):
            add(auds[0], n)
        for a in auds[1:]:
            for n in EXTRA_STEPS.get(a, ()):
                add(a, n)
    return out[:MAX_STEPS]


def _item_keys(auds: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in auds:
        for k in CHECKLISTS[a]:
            if k not in seen:
                seen.add(k)
                out.append((k, a))
    return out[:MAX_ITEMS]


def _first_name(user: User) -> str:
    if user.firstname and user.firstname.strip():
        return user.firstname.strip()
    if user.full_name and user.full_name.strip():
        return user.full_name.strip().split()[0]
    return ""


def display_name(user: User | None) -> str:
    if user is None:
        return "başka bir yönetici"
    if user.full_name and user.full_name.strip():
        return user.full_name.strip()
    name = " ".join(x for x in (user.firstname, user.lastname) if x and x.strip())
    return name or user.username or user.email or f"#{user.id}"


def locale_of(user: User, st: Settings) -> str:
    lang = tr_lower((user.language or st.get("org.default_language") or "tr").strip())
    return "en" if lang.startswith("en") or lang == "english" else "tr"


def _iso(v: datetime | None) -> str | None:
    return v.isoformat(timespec="seconds") if v is not None else None


async def _rows(session: AsyncSession, uid: int) -> dict[str, WelcomeProgress]:
    q = select(WelcomeProgress).where(WelcomeProgress.user_id == uid)
    return {r.guide_key: r for r in (await session.execute(q)).scalars()}


def _sheet_trigger(
    row: WelcomeProgress | None, auds: list[str], st: Settings, now: datetime
) -> dict[str, Any] | None:
    """T1 / T3 / T4 / T2 for the sheet, or None."""
    if not auds:
        return None
    if row is None:
        return {"kind": "sheet", "key": "sheet", "audiences": list(auds), "updated": False}
    if row.state == "dismissed":
        return None
    if row.state == "snoozed" and (row.snoozed_until is None or row.snoozed_until > now):
        return None
    items = row.items or {}
    welcomed = set(items.get("audiences") or [])
    new = [a for a in auds if a not in welcomed]
    if new:
        return {"kind": "delta", "key": "sheet", "audiences": new, "updated": False}
    seen_versions = items.get("versions") or {}
    if any(st.content_version(a) > int(seen_versions.get(a, 0) or 0) for a in auds):
        return {"kind": "sheet", "key": "sheet", "audiences": list(auds), "updated": True}
    if row.state == "snoozed":  # lapsed
        return {"kind": "sheet", "key": "sheet", "audiences": list(auds), "updated": False}
    return None


async def _overrides(
    session: AsyncSession, auds: list[str], locale: str, st: Settings
) -> dict[str, dict[str, str]]:
    wanted = [a for a in auds if st.text_version(a) > 0]
    if not wanted:
        return {}
    q = select(WelcomeContent).where(WelcomeContent.audience.in_(wanted), WelcomeContent.locale == locale)
    out: dict[str, dict[str, str]] = {}
    for r in (await session.execute(q)).scalars():
        out.setdefault(r.audience, {})[r.field] = r.text
    return out


async def payload(
    session: AsyncSession,
    user: User,
    access: Any,
    *,
    first_route: str | None = None,
    kiosk: bool = False,
    embed: bool = False,
    preview: str | None = None,
) -> dict[str, Any]:
    """``GET /welcome``: the person's audiences, the one automatic surface due now and the parts' content. Writes
    only the checklist snapshot when a new item got done (never in ``preview``). ≤ 6 statements."""
    now = _now()
    perms = set(access.perms)
    st = await load_settings(session, user.id)
    facts = await facts_of(session, user.id)
    if preview is not None:
        auds, rows = [preview], {}
    else:
        auds = audiences_for(perms, instructor_linked=facts["instructor_linked"])
        rows = await _rows(session, user.id)
    locale = locale_of(user, st)
    enabled = {k: st.switch("enabled") and st.switch(k) for k in ("sheet", "tour", "checklist", "hints")}

    # what is due, before the switches and the page say no
    suppressed: str | None = None
    if kiosk:
        suppressed = "kiosk"
    elif embed:
        suppressed = "embed"
    else:
        suppressed = route_suppression(first_route)
    if suppressed is None and st.get("org.maintenance_mode") in ("1", "true") and (
        "system.bypass_maintenance_mode" not in perms
    ):
        suppressed = "maintenance"
    trigger = _sheet_trigger(rows.get("sheet"), auds, st, now)
    if preview is not None:
        trigger = {"kind": "sheet", "key": "sheet", "audiences": list(auds), "updated": False}

    show: dict[str, Any] | None = None
    if trigger is not None and enabled["sheet"]:
        show = trigger
    due_hints: list[hints.Hint] = []
    if enabled["hints"] and preview is None:
        seen = {k: r.updated_at for k, r in rows.items() if k.startswith("hint.")}
        hint_facts = {"first_booking": facts["booking"], "instructor_linked": facts["instructor_linked"]}
        due_hints = hints.eligible(
            perms, hint_facts, created_at=user.created_at, now=now, seen=seen, hints_for_all_at=st.hints_for_all_at
        )
    if show is None and due_hints:
        show = {"kind": "hint", "key": due_hints[0].key, "audiences": [], "updated": False}
    if show is None and suppressed is None and (not st.switch("enabled") or (trigger is not None and not enabled["sheet"])):
        suppressed = "disabled"
    if suppressed is not None:
        show = None

    # sheet
    sheet_row = rows.get("sheet")
    delta = trigger is not None and trigger["kind"] == "delta"
    card_auds = trigger["audiences"] if delta and trigger is not None else auds
    texts = await _overrides(session, list(dict.fromkeys([*auds, *card_auds])), locale, st)
    cards = _cards(card_auds, delta=delta)
    for c in cards:
        own = texts.get(c["audience"], {})
        ov = {f: own[f"cards.{c['key']}.{f}"] for f in ("title", "body") if f"cards.{c['key']}.{f}" in own}
        if ov:
            c["overrides"] = ov
    primary = auds[0] if auds else None
    sheet = {
        "audience": primary,
        "state": sheet_row.state if sheet_row else None,
        "snooze_count": sheet_row.snooze_count if sheet_row else 0,
        "snoozed_until": _iso(sheet_row.snoozed_until) if sheet_row else None,
        "delta": delta,
        "updated": bool(trigger and trigger.get("updated")),
        "cards": cards,
        "overrides": {k: v for k, v in texts.get(primary or "", {}).items() if not k.startswith("cards.")},
    }

    # tour
    tour_row = rows.get("tour")
    tour = {
        "state": tour_row.state if tour_row else None,
        "step": tour_row.step if tour_row else None,
        "steps": _steps(auds),
    }

    # checklist: server signals win; view-only items from the stored ticks; done items are sticky
    check_row = rows.get("checklist")
    stored_done: dict[str, str] = dict(((check_row.items or {}).get("done") or {}) if check_row else {})
    live = signals(user, facts, st) if preview is None else {}
    keys = _item_keys(auds)
    items = []
    newly: dict[str, str] = {}
    for key, aud in keys:
        manual = key in MANUAL_ITEMS
        done = key in stored_done or (not manual and live.get(key, False))
        if done and key not in stored_done and not manual:
            newly[key] = _iso(now) or ""
        items.append({"key": key, "audience": aud, "href": ITEM_HREF[key], "done": done, "manual": manual})
    n_done = sum(1 for i in items if i["done"])
    if preview is None and (newly or (check_row is not None and (check_row.items or {}).get("total") != len(items))):
        await _write_checklist(session, user.id, check_row, {**stored_done, **newly}, len(items), primary or "", now)
    checklist = {
        "state": check_row.state if check_row else None,
        "hidden": bool(check_row and check_row.state == "hidden"),
        "items": items,
        "done": n_done,
        "total": len(items),
    }
    return {
        "preview": preview is not None,
        "audiences": auds,
        "primary": primary,
        "secondary": auds[1:],
        "audience_labels": {a: AUDIENCE_LABELS[a] for a in auds},
        "name": _first_name(user),
        "locale": locale,
        "enabled": enabled,
        "show": show,
        "suppressed": suppressed,
        "sheet": sheet,
        "tour": tour,
        "checklist": checklist,
        "hints": [h.out() for h in due_hints],
        "content_version": {a: st.content_version(a) for a in auds},
    }


async def _write_checklist(
    session: AsyncSession,
    uid: int,
    row: WelcomeProgress | None,
    done: dict[str, str],
    total: int,
    audience: str,
    now: datetime,
) -> None:
    items = {"done": done, "total": total}
    if row is not None:
        row.items, row.updated_at = items, now
        await session.flush()
        return
    try:
        async with session.begin_nested():
            session.add(
                WelcomeProgress(
                    user_id=uid,
                    guide_key="checklist",
                    audience=audience,
                    state="shown",
                    items=items,
                    first_shown_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError:  # another device wrote it first: its snapshot is as good
        pass


# --------------------------------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------------------------------

EVENTS: dict[str, frozenset[str]] = {
    "sheet": frozenset({"shown", "snoozed", "dismissed", "started", "completed"}),
    "tour": frozenset({"shown", "started", "step", "dismissed", "completed"}),
    "checklist": frozenset({"shown", "hidden", "item_done"}),
}
HINT_EVENTS = frozenset({"shown", "seen", "dismissed", "started", "completed"})
ALL_ITEMS = frozenset(k for items in CHECKLISTS.values() for k in items)


def _refuse(code: str, en: str, tr: str, **data: Any) -> WelcomeError:
    return WelcomeError(422, code, en, tr, **data)


async def _row(session: AsyncSession, uid: int, key: str, now: datetime) -> WelcomeProgress:
    q = select(WelcomeProgress).where(WelcomeProgress.user_id == uid, WelcomeProgress.guide_key == key)
    row = (await session.execute(q)).scalar_one_or_none()
    if row is not None:
        return row
    row = WelcomeProgress(user_id=uid, guide_key=key, state="shown", items={}, first_shown_at=now, updated_at=now)
    try:
        async with session.begin_nested():
            session.add(row)
    except IntegrityError:  # the other device's event created it a moment ago
        row = (await session.execute(q)).scalar_one()
    return row


def _remember_audiences(row: WelcomeProgress, auds: list[str], st: Settings) -> None:
    items = dict(row.items or {})
    welcomed = list(dict.fromkeys([*(items.get("audiences") or []), *auds]))
    versions = dict(items.get("versions") or {})
    versions.update({a: st.content_version(a) for a in auds})
    row.items = {**items, "audiences": welcomed, "versions": versions}
    row.audience = auds[0] if auds else row.audience
    row.audience_hash = audience_hash(auds)
    row.content_version = st.content_version(auds[0]) if auds else 0


async def record_event(
    session: AsyncSession,
    user: User,
    access: Any,
    guide_key: str,
    event: str,
    *,
    step: int | None = None,
    item: str | None = None,
) -> None:
    """``POST /welcome/events``: idempotent; a repeated event leaves the state as the first one left it."""
    now = _now()
    key = unicodedata.normalize("NFC", (guide_key or "").strip())
    ev = (event or "").strip()
    perms = set(access.perms)
    if key.startswith("hint."):
        hint = hints.BY_KEY.get(key)
        if hint is None:
            raise _refuse(
                "unknown_guide_key", f"unknown guide part {key!r}", f"bilinmeyen rehber bölümü: {key}", guide_key=key
            )
        allowed = HINT_EVENTS
    else:
        if key not in EVENTS:
            raise _refuse(
                "unknown_guide_key",
                f"unknown guide part {key!r}: sheet, tour, checklist or hint.<key>",
                f"bilinmeyen rehber bölümü: {key} (sheet, tour, checklist ya da hint.<anahtar>)",
                guide_key=key,
            )
        allowed = EVENTS[key]
    if ev not in allowed:
        raise _refuse(
            "unknown_event",
            f"unknown event {ev!r} for {key}: {', '.join(sorted(allowed))}",
            f"{key} için bilinmeyen olay: {ev} ({', '.join(sorted(allowed))})",
            guide_key=key,
            allowed=sorted(allowed),
        )
    if step is not None and not (0 <= step <= 50):
        raise _refuse("invalid_step", "step must be between 0 and 50", "adım 0 ile 50 arasında olmalı")
    facts: dict[str, bool] | None = None
    if key == "sheet" or key.startswith("hint."):
        facts = await facts_of(session, user.id)
    if key.startswith("hint."):
        assert facts is not None
        hint_facts = {"first_booking": facts["booking"], "instructor_linked": facts["instructor_linked"]}
        if not hints.may_use(hints.BY_KEY[key], perms, hint_facts):
            raise _refuse(
                "not_eligible",
                f"{key} is not for this account",
                f"{key} bu hesap için değil",
                guide_key=key,
            )
    if ev == "item_done":
        it = (item or "").strip()
        if it not in ALL_ITEMS:
            raise _refuse("unknown_item", f"unknown checklist item {it!r}", f"bilinmeyen liste maddesi: {it}", item=it)
        if it not in MANUAL_ITEMS:
            raise _refuse(
                "not_manual",
                f"{it} is ticked by the server when the action is done",
                f"{it} maddesi, işlem yapıldığında sunucu tarafından işaretlenir",
                item=it,
            )
    row = await _row(session, user.id, key, now)
    changed = True
    if key == "sheet":
        assert facts is not None
        st = await load_settings(session)
        auds = audiences_for(perms, instructor_linked=facts["instructor_linked"])
        lapsed = row.snoozed_until is not None and row.snoozed_until <= now
        if ev == "shown":
            if row.state == "snoozed" and not lapsed:
                changed = False  # a re-render while the snooze runs
            else:
                row.state = "shown"
        elif ev == "snoozed":
            if row.state == "snoozed" and not lapsed:
                changed = False  # double tap / retried request
            else:
                row.snooze_count = (row.snooze_count or 0) + 1
                row.state = "snoozed"
                row.snoozed_until = now + timedelta(days=SNOOZE_DAYS) if row.snooze_count <= MAX_SNOOZES else None
        elif ev == "dismissed":
            row.state, row.snoozed_until = "dismissed", None
        else:  # started (the tour began from the sheet) / completed
            row.state, row.snoozed_until = "completed", None
            row.completed_at = row.completed_at or now
        if changed:
            _remember_audiences(row, auds, st)
    elif key == "tour":
        if ev == "step":
            row.state, row.step = "started", step if step is not None else row.step
        elif ev == "started":
            row.state, row.step = "started", step if step is not None else (row.step or 1)
        elif ev == "dismissed":
            row.state = "dismissed"
            row.step = step if step is not None else row.step
        elif ev == "completed":
            row.state, row.completed_at = "completed", row.completed_at or now
        else:
            row.state = "shown"
    elif key == "checklist":
        if ev == "item_done":
            items = dict(row.items or {})
            done = dict(items.get("done") or {})
            if item in done:
                changed = False
            else:
                done[str(item)] = _iso(now) or ""
                row.items = {**items, "done": done}
        else:
            row.state = ev
    else:  # hint.*
        new_state = {"shown": "shown", "started": "started", "completed": "completed"}.get(ev, "seen")
        row.state = new_state
        if new_state == "completed":
            row.completed_at = row.completed_at or now
    if changed:
        row.updated_at = now
    await session.flush()


async def restart(session: AsyncSession, user: User, access: Any) -> dict[str, Any]:
    """``POST /welcome/restart`` (Help › Turu yeniden başlat): sheet and tour back to ``shown``; the payload with the
    sheet as ``show`` (the user's own ask, not counted as an automatic interruption)."""
    now = _now()
    facts = await facts_of(session, user.id)
    st = await load_settings(session)
    auds = audiences_for(access.perms, instructor_linked=facts["instructor_linked"])
    sheet = await _row(session, user.id, "sheet", now)
    sheet.state, sheet.snoozed_until, sheet.updated_at = "shown", None, now
    _remember_audiences(sheet, auds, st)
    tour = await _row(session, user.id, "tour", now)
    tour.state, tour.step, tour.updated_at = "shown", None, now
    await session.flush()
    out = await payload(session, user, access)
    out["show"] = {"kind": "sheet", "key": "sheet", "audiences": auds, "updated": False, "reason": "restart"}
    out["suppressed"] = None
    return out


# --------------------------------------------------------------------------------------------------
# admin: switches
# --------------------------------------------------------------------------------------------------


async def settings_out(session: AsyncSession) -> dict[str, Any]:
    st = await load_settings(session)
    stamp = (
        await session.execute(select(func.max(Setting.updated_at)).where(Setting.key.like(PREFIX + "%")))
    ).scalar_one_or_none()
    return {
        "settings": st.switches(),
        "content_version": {a: st.content_version(a) for a in AUDIENCES},
        "text_version": {a: st.text_version(a) for a in AUDIENCES},
        "hints_for_all_at": _iso(st.hints_for_all_at),
        "updated_at": _iso(stamp),
    }


async def put_settings(session: AsyncSession, actor: User, values: Mapping[str, Any]) -> dict[str, Any]:
    st = await load_settings(session)
    before = st.switches()
    changes: dict[str, Any] = {}
    for k, v in values.items():
        if v is None:
            continue
        if k in SWITCHES:
            if not isinstance(v, bool):
                raise _refuse("invalid_value", f"{k} must be true or false", f"{k} açık ya da kapalı olmalı", field=k)
            changes[k] = v
        elif k == "min_cohort":
            if not isinstance(v, int) or isinstance(v, bool) or not (MIN_COHORT <= v <= 100):
                raise _refuse(
                    "invalid_min_cohort",
                    f"the smallest group shown is at least {MIN_COHORT} people (KVKK)",
                    f"gösterilen en küçük grup en az {MIN_COHORT} kişi olmalı (KVKK)",
                    field=k,
                )
            changes[k] = v
        else:
            raise _refuse("invalid_field", f"unknown setting {k!r}", f"bilinmeyen ayar: {k}", field=k)
    for k, v in changes.items():
        await _set(session, PREFIX + k, ("1" if v else "0") if isinstance(v, bool) else str(v))
    if changes.get("hints_for_all") is True and not before["hints_for_all"]:
        await _set(session, PREFIX + "hints_for_all_at", _now().isoformat(timespec="seconds"))
    after = (await load_settings(session)).switches()
    if after != before:
        await audit.record(
            session, "welcome.settings_update", "setting", "welcome", before=before, after=after, actor=actor
        )
    return await settings_out(session)


# --------------------------------------------------------------------------------------------------
# admin: texts
# --------------------------------------------------------------------------------------------------

LOCALES = ("tr", "en")
TITLE_MAX, BODY_MAX = 80, 200
PLACEHOLDERS = {"ad": "ad", "name": "name", "bölüm": "bölüm", "department": "department"}
_PLACEHOLDER = re.compile(r"\{([^{}]{0,40})\}")
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_SPACES = re.compile(r"[\s   ]+")


def editable_fields(aud: str) -> list[dict[str, Any]]:
    out = [{"field": "title", "max": TITLE_MAX}, {"field": "lead", "max": BODY_MAX}]
    for k, _href in CARDS[aud]:
        out += [{"field": f"cards.{k}.title", "max": TITLE_MAX}, {"field": f"cards.{k}.body", "max": BODY_MAX}]
    return out


def check_audience(aud: str) -> str:
    a = tr_lower(unicodedata.normalize("NFC", (aud or "").strip()))
    if a not in AUDIENCES:
        raise WelcomeError(
            404,
            "unknown_audience",
            f"unknown audience {aud!r}: {', '.join(AUDIENCES)}",
            f"bilinmeyen kitle: {aud} ({', '.join(AUDIENCES)})",
        )
    return a


def clean_text(value: str | None, *, field: str, locale: str, limit: int) -> str | None:
    """NFC, no invisible characters, NBSP / newlines as one space; placeholders canonical (``{AD}`` -> ``{ad}``).
    Empty -> None ("Varsayılana dön")."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value)).translate(_INVISIBLE)
    text = _SPACES.sub(" ", text).strip()
    if not text:
        return None

    def canon(m: re.Match[str]) -> str:
        inner = tr_lower(m.group(1).strip())
        if inner not in PLACEHOLDERS:
            raise _refuse(
                "placeholder",
                f"{field} ({locale}): only {{ad}}, {{name}}, {{bölüm}} and {{department}} may be used, not {{{m.group(1)}}}",
                f"{field} ({locale}): yalnızca {{ad}}, {{name}}, {{bölüm}} ve {{department}} kullanılabilir; "
                f"{{{m.group(1)}}} kullanılamaz",
                field=field,
                locale=locale,
            )
        return "{" + PLACEHOLDERS[inner] + "}"

    text = _PLACEHOLDER.sub(canon, text)
    if len(text) > limit:
        raise _refuse(
            "too_long",
            f"{field} ({locale}) is {len(text)} characters; at most {limit}",
            f"{field} ({locale}) {len(text)} karakter; en fazla {limit} olabilir",
            field=field,
            locale=locale,
            max=limit,
        )
    return text


async def content_out(session: AsyncSession, aud: str) -> dict[str, Any]:
    a = check_audience(aud)
    st = await load_settings(session)
    rows = (await session.execute(select(WelcomeContent).where(WelcomeContent.audience == a))).scalars()
    fields: dict[str, dict[str, str]] = {loc: {} for loc in LOCALES}
    for r in rows:
        fields.setdefault(r.locale, {})[r.field] = r.text
    by = _last_editor(st, a)
    return {
        "audience": a,
        "label": AUDIENCE_LABELS[a],
        "version": st.text_version(a),
        "content_version": st.content_version(a),
        "locales": list(LOCALES),
        "editable": editable_fields(a),
        "placeholders": sorted(PLACEHOLDERS),
        "fields": fields,
        "updated_by": by.get("name"),
        "updated_at": by.get("at"),
    }


def _last_editor(st: Settings, aud: str) -> dict[str, Any]:
    raw = st.get(f"{PREFIX}text_by.{aud}")
    try:
        v = json.loads(raw) if raw else {}
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}


async def _claim_version(session: AsyncSession, aud: str, expected: int) -> bool:
    """Compare-and-set of the audience's text revision: True when ``expected`` was current and is now +1."""
    key = f"{PREFIX}text_version.{aud}"
    if expected == 0:
        row = await session.get(Setting, key)
        if row is None:
            try:
                async with session.begin_nested():
                    session.add(Setting(key=key, value="1", is_secret=False))
                return True
            except IntegrityError:
                return False
    res = await session.execute(
        update(Setting)
        .where(Setting.key == key, Setting.value == str(expected))
        .values(value=str(expected + 1), updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    return bool(getattr(res, "rowcount", 0) == 1)


async def put_content(
    session: AsyncSession,
    actor: User,
    aud: str,
    version: int,
    fields: Mapping[str, Mapping[str, str | None]],
    *,
    reshow_after: bool = False,
) -> dict[str, Any]:
    """Save text overrides (``None`` / empty = back to the product copy). 409 ``stale`` when someone saved since
    ``version`` was read."""
    a = check_audience(aud)
    limits = {f["field"]: int(f["max"]) for f in editable_fields(a)}
    clean: dict[tuple[str, str], str | None] = {}
    for loc, values in fields.items():
        if loc not in LOCALES:
            raise _refuse("invalid_locale", f"unknown locale {loc!r}: tr or en", f"bilinmeyen dil: {loc} (tr ya da en)")
        for field, text in (values or {}).items():
            if field not in limits:
                raise _refuse(
                    "invalid_field",
                    f"{field} cannot be edited; texts only (order, links and icons are fixed)",
                    f"{field} düzenlenemez; yalnızca metinler değişir (sıra, bağlantı ve simgeler sabittir)",
                    field=field,
                )
            clean[(loc, field)] = clean_text(text, field=field, locale=loc, limit=limits[field])
    st = await load_settings(session)
    current = st.text_version(a)
    if version != current or not await _claim_version(session, a, current):
        st = await load_settings(session)
        who = _last_editor(st, a).get("name") or "başka bir yönetici"
        raise WelcomeError(
            409,
            "stale",
            f"{who} changed this text while you were editing it. Reload the page and try again.",
            f"Bu metni siz düzenlerken {who} değiştirdi. Sayfayı yenileyip yeniden deneyin.",
            current_version=st.text_version(a),
            updated_by=who,
        )
    new_version = current + 1
    now = utcnow()
    existing = {
        (r.locale, r.field): r
        for r in (await session.execute(select(WelcomeContent).where(WelcomeContent.audience == a))).scalars()
    }
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for (loc, field), text in clean.items():
        row = existing.get((loc, field))
        old = row.text if row is not None else None
        if old == text:
            continue
        before[f"{loc}.{field}"], after[f"{loc}.{field}"] = old, text
        if text is None:
            if row is not None:
                await session.delete(row)
        elif row is None:
            session.add(
                WelcomeContent(
                    audience=a, locale=loc, field=field, text=text, version=new_version, updated_by_id=actor.id,
                    updated_at=now,
                )
            )
        else:
            row.text, row.version, row.updated_by_id, row.updated_at = text, new_version, actor.id, now
    await _set(
        session,
        f"{PREFIX}text_by.{a}",
        json.dumps({"name": display_name(actor), "at": _iso(now)}, ensure_ascii=False),
    )
    await session.flush()
    await audit.record(
        session,
        "welcome.content_update",
        "welcome_content",
        a,
        before={"version": current, "fields": before},
        after={"version": new_version, "fields": after},
        actor=actor,
    )
    if reshow_after:
        await reshow(session, actor, a)
    return await content_out(session, a)


async def reshow(session: AsyncSession, actor: User, aud: str) -> dict[str, Any]:
    """"Show again" to the audience: its ``content_version`` +1, so everyone of it gets the sheet with "Güncellendi"."""
    a = check_audience(aud)
    st = await load_settings(session)
    old = st.content_version(a)
    await _set(session, f"{PREFIX}content_version.{a}", str(old + 1))
    await audit.record(
        session,
        "welcome.reshow",
        "welcome_content",
        a,
        before={"content_version": old},
        after={"content_version": old + 1},
        actor=actor,
    )
    return {"audience": a, "content_version": old + 1}


# --------------------------------------------------------------------------------------------------
# admin: completion stats (aggregate, k >= min_cohort, no per-person output)
# --------------------------------------------------------------------------------------------------


def _pct(n: int, d: int) -> int:
    return round(100 * n / d) if d else 0


async def stats(session: AsyncSession, days: int) -> dict[str, Any]:
    if days not in STATS_DAYS:
        raise _refuse(
            "invalid_days",
            f"days: one of {', '.join(map(str, STATS_DAYS))}",
            f"gün: {', '.join(map(str, STATS_DAYS))} değerlerinden biri",
            allowed=list(STATS_DAYS),
        )
    now = _now()
    since = now - timedelta(days=days)
    st = await load_settings(session)
    k = st.min_cohort
    cohort = (
        select(WelcomeProgress.user_id)
        .where(WelcomeProgress.guide_key == "sheet", WelcomeProgress.first_shown_at >= since)
    )
    async with rls.system_scope(session):
        sheets = (
            await session.execute(
                select(
                    WelcomeProgress.user_id, WelcomeProgress.audience, WelcomeProgress.state,
                    WelcomeProgress.first_shown_at,
                ).where(WelcomeProgress.guide_key == "sheet", WelcomeProgress.first_shown_at >= since)
            )
        ).all()
        others = (
            await session.execute(
                select(WelcomeProgress.user_id, WelcomeProgress.guide_key, WelcomeProgress.state, WelcomeProgress.items)
                .where(WelcomeProgress.guide_key.in_(("tour", "checklist")), WelcomeProgress.user_id.in_(cohort))
            )
        ).all()
        first_booking = dict(
            (
                await session.execute(
                    select(Booking.user_id, func.min(Booking.created_at))
                    .where(Booking.user_id.in_(cohort))
                    .group_by(Booking.user_id)
                )
            ).all()
        )
    toured = {u for u, g, s, _i in others if g == "tour" and s == "completed"}
    eighty: set[int] = set()
    for u, g, _s, items in others:
        if g != "checklist" or not isinstance(items, dict):
            continue
        total = int(items.get("total") or 0)
        if total and len(items.get("done") or {}) / total >= 0.8:
            eighty.add(u)
    out = []
    for a in AUDIENCES:
        group = [(u, s, shown) for u, aud, s, shown in sheets if aud == a]
        n = len(group)
        if n < k:
            out.append(
                {
                    "audience": a,
                    "small_group": True,
                    "shown": None,
                    "tour_completed_pct": None,
                    "checklist_80_pct": None,
                    "dismissed_pct": None,
                    "median_days_to_first_booking": None,
                }
            )
            continue
        ids = [u for u, _s, _t in group]
        median = None
        if a in BOOKING_AUDIENCES:
            gaps = [
                max(0.0, (first_booking[u] - shown).total_seconds() / 86400)
                for u, _s, shown in group
                if u in first_booking and first_booking[u] is not None
            ]
            median = round(statistics.median(gaps), 1) if gaps else None
        out.append(
            {
                "audience": a,
                "small_group": False,
                "shown": n,
                "tour_completed_pct": _pct(sum(1 for u in ids if u in toured), n),
                "checklist_80_pct": _pct(sum(1 for u in ids if u in eighty), n),
                "dismissed_pct": _pct(sum(1 for _u, s, _t in group if s == "dismissed"), n),
                "median_days_to_first_booking": median,
            }
        )
    return {"days": days, "since": _iso(since), "min_cohort": k, "audiences": out}


# --------------------------------------------------------------------------------------------------
# KVKK (called by app.services.kvkk: DSR export and erasure)
# --------------------------------------------------------------------------------------------------


async def dsr_rows(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """The person's own guide state, for the DSR export (``welcome_guide``)."""
    async with rls.system_scope(session):
        rows = (
            await session.execute(
                select(WelcomeProgress).where(WelcomeProgress.user_id == user_id).order_by(WelcomeProgress.id)
            )
        ).scalars()
        return [
            {
                "guide": r.guide_key,
                "audience": r.audience,
                "state": r.state,
                "step": r.step,
                "snooze_count": r.snooze_count,
                "snoozed_until": r.snoozed_until,
                "content_version": r.content_version,
                "items": r.items,
                "first_shown_at": r.first_shown_at,
                "updated_at": r.updated_at,
                "completed_at": r.completed_at,
            }
            for r in rows
        ]


async def erase(session: AsyncSession, user_id: int) -> int:
    """Delete the person's guide state (KVKK erasure); the number of rows deleted."""
    async with rls.system_scope(session):
        res = await session.execute(
            delete(WelcomeProgress).where(WelcomeProgress.user_id == user_id).execution_options(synchronize_session=False)
        )
    return int(getattr(res, "rowcount", 0) or 0)


__all__ = [
    "AUDIENCES",
    "CARDS",
    "CHECKLISTS",
    "MANUAL_ITEMS",
    "WelcomeError",
    "audience_hash",
    "audiences_for",
    "check_audience",
    "content_out",
    "dsr_rows",
    "erase",
    "facts_of",
    "load_settings",
    "payload",
    "put_content",
    "put_settings",
    "record_event",
    "reshow",
    "restart",
    "settings_out",
    "stats",
]
