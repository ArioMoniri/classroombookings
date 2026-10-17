"""Feature-hint registry of the welcome guide (WG-02; docs/design/v3/welcome-guide.md §4.5).

One hint per wave-3 feature, shown once per person as state ``seen`` (``welcome_progress`` row ``hint.<key>``):

* only to people who can use the feature (any of ``perms``; ``needs`` adds a data condition);
* only to accounts created **before** the feature's release (new accounts meet it in the sheet and the tour);
* only until ``expires_days`` after the release;
* ``hints_for_all`` (admin switch, its switch-on time) overrides the account-age rule and earlier ``seen`` states once.

The copy lives in the frontend (``welcome.hints.<key>.*``); the server holds who, where and when.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

#: wave 3 (quick reserve, calendar export, AI, ops, integrations) shipped with this release
WAVE3_RELEASE = date(2026, 10, 17)
WAVE3_VERSION = "0.5.0"
ADMIN_PERMS = frozenset({"setup.settings", "planning.admin"})


@dataclass(frozen=True)
class Hint:
    key: str
    #: any of these permissions (empty: everyone signed in, subject to ``needs``)
    perms: frozenset[str]
    release: date
    version: str
    route: str
    anchor: str | None = None
    expires_days: int = 60
    #: an extra data condition: ``booking_or_instructor`` (has a booking or an instructor link)
    needs: str | None = None

    @property
    def released_at(self) -> datetime:
        return datetime.combine(self.release, datetime.min.time())

    @property
    def expires_at(self) -> datetime:
        return self.released_at + timedelta(days=self.expires_days)

    def out(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "route": self.route,
            "anchor": self.anchor,
            "release": self.release.isoformat(),
            "version": self.version,
            "expires": self.expires_at.date().isoformat(),
        }


HINTS: tuple[Hint, ...] = (
    Hint("hint.quick_reserve", frozenset({"book_single.create"}), WAVE3_RELEASE, WAVE3_VERSION, "/reserve", "nav-reserve"),
    Hint(
        "hint.calendar_export",
        frozenset(),
        WAVE3_RELEASE,
        WAVE3_VERSION,
        "/my-bookings",
        "nav-my-bookings",
        needs="booking_or_instructor",
    ),
    Hint("hint.admin_ai", ADMIN_PERMS, WAVE3_RELEASE, WAVE3_VERSION, "/admin/ai", "nav-admin-ai"),
    Hint("hint.admin_ops", ADMIN_PERMS, WAVE3_RELEASE, WAVE3_VERSION, "/admin/ops", "nav-admin-ops"),
    Hint(
        "hint.admin_integrations", ADMIN_PERMS, WAVE3_RELEASE, WAVE3_VERSION, "/admin/integrations", "nav-integrations"
    ),
)
BY_KEY: dict[str, Hint] = {h.key: h for h in HINTS}


def may_use(hint: Hint, perms: Iterable[str], facts: Mapping[str, bool]) -> bool:
    """The person can use the feature (permission and data condition)."""
    held = set(perms)
    if hint.perms and not (hint.perms & held):
        return False
    if hint.needs == "booking_or_instructor":
        return bool(facts.get("first_booking") or facts.get("instructor_linked"))
    return True


def eligible(
    perms: Iterable[str],
    facts: Mapping[str, bool],
    *,
    created_at: datetime | None,
    now: datetime,
    seen: Mapping[str, datetime],
    hints_for_all_at: datetime | None = None,
) -> list[Hint]:
    """Hints due for this person now, in registry order. ``seen``: hint key -> when its row was last written."""
    held = set(perms)
    out: list[Hint] = []
    for h in HINTS:
        if not may_use(h, held, facts):
            continue
        if not (h.released_at <= now < h.expires_at):
            continue
        override = hints_for_all_at is not None and hints_for_all_at <= now
        if not override and (created_at is None or created_at >= h.released_at):
            continue
        last = seen.get(h.key)
        if last is not None and not (override and hints_for_all_at is not None and last < hints_for_all_at):
            continue
        out.append(h)
    return out


__all__ = ["BY_KEY", "HINTS", "WAVE3_RELEASE", "WAVE3_VERSION", "Hint", "eligible", "may_use"]
