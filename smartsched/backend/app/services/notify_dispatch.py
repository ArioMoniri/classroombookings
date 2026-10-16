"""One notification dispatcher for the approval workflow (owner requirement 2026-10-15: decisions and their reasons
"get notified to users by the email or other connections they added").

A caller builds one :class:`Notice` per recipient (title and body already in the recipient's language, plus the
structured ``data``) and calls :func:`dispatch`. The dispatcher

1. reads the recipient's channel preferences (:class:`Preferences`, the user setting ``notification_prefs``;
   default: every built-in channel on for every event);
2. for every registered channel that is on, claims the ledger row ``notification_deliveries`` keyed by
   (``notice.key``, recipient, channel) -- a key that exists already means the occurrence reached this recipient on
   this channel before (a retried job, a second sweep), so nothing is sent again;
3. hands the notice to the channel adapter and records the outcome on the ledger row.

Everything runs inside the caller's transaction: the ledger row, the in-app row and the outbox row commit (or roll
back) together with the change that caused them. The unique key is the referee if two transactions race.

Built-in channels
-----------------
* ``in_app``: a row in ``inapp_notifications`` (``GET /me/notifications``; ``data`` carries the payload);
* ``email``: a row in the e-mail outbox (``notification_outbox``, alembic 0021), sent after the commit by the
  integrations worker with retries; ``UNSENT`` without SMTP or without an address, as before.

Events
------
:data:`EVENTS` lists every event a user can switch per channel: the approval workflow (``approval.*``, sent by
:mod:`app.services.approvals`; approvers get one ``approval.requested`` per submission and an
``approval.withdrawn`` when the requester withdraws) and the CRBS booking e-mails (``booking.created``,
``booking.cancelled``, ``room_owner.booking``, sent by :mod:`app.services.bookings_notify` with their translatable
templates) and the publish digest (``timetable.published``: one notice per academician whose classes changed when a
timetable is published, sent by :func:`app.services.moderation.publish_digest`). The e-mail channel stores the event
as the outbox ``kind`` with ``_`` for ``.`` (``booking_created``, ``approval_requested``, ``timetable_published``), so
the outbox screen and its filters keep their names.

Extension point: a third channel
--------------------------------
An external integration provider (chosen after the research in docs/product/2026-10-15-integrations-options.md) is
one :class:`ChannelAdapter` subclass registered at start-up with :func:`register_channel`::

    class ProviderChannel(ChannelAdapter):
        name = "<provider>"            # stored in the ledger and in the preferences; 32 characters at most
        label_tr = "..."; label_en = "..."
        default_enabled = False        # opt-in: the user switches it on after connecting an account

        async def available_for(self, session, user) -> bool:
            ...                        # True when the user has connected an account ("connections they added")

        async def send(self, session, user, notice) -> Delivery:
            ...                        # enqueue an outbox row of the provider (never call out from here) and
            return Delivery(self.name, "sent", ref_id=row.id)   # or "skipped" with a detail (not connected)

Nothing else changes: the preferences API lists the new channel, the matrix gets a column, every event fans out to
it. ``send`` runs inside the business transaction, so it must only write rows (an outbox with its own worker and
retries, like ``calendar_sync_jobs`` / ``webhook_deliveries``); a raised exception is logged and recorded as
``failed`` and never breaks the decision that triggered it. No such adapter ships with the product.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InAppNotification, NotificationDelivery, User
from app.services import bookings_notify as mail
from app.services.bookings_settings import get_user_value, set_user_value

log = logging.getLogger(__name__)

PREFS_KEY = "notification_prefs"  # settings row user.<id>.notification_prefs (JSON)

#: event -> (Turkish label, English label) as shown in the preferences screen
EVENTS: dict[str, tuple[str, str]] = {
    "approval.requested": ("Onayımı bekleyen yeni oda talepleri", "New room requests awaiting my approval"),
    "approval.approved": ("Talebim onaylandı", "My request was approved"),
    "approval.rejected": ("Talebim reddedildi (gerekçesiyle)", "My request was declined (with the reason)"),
    "approval.withdrawn": (
        "Bir talep geri çekildi (benim ya da onayımı bekleyen)",
        "A request was withdrawn (mine, or one awaiting my approval)",
    ),
    "approval.expired": ("Talebimin süresi doldu", "My request expired"),
    # the CRBS booking e-mails (app.services.bookings_notify), same templates and outbox kinds as before
    "booking.created": ("Biri benim adıma rezervasyon yaptı", "Someone booked a room for me"),
    "booking.cancelled": ("Rezervasyonum iptal edildi", "My booking was cancelled"),
    "room_owner.booking": ("Sorumlu olduğum odaya rezervasyon yapıldı", "A room I look after was booked"),
    # Phase 19 publish digest (owner decision: in-app + one e-mail digest per affected academician;
    # app.services.moderation.publish_digest, POST /runs/{id}/activate {"notify_people": true})
    "timetable.published": ("Yayınlanan planda derslerim değişti", "My classes changed in a published timetable"),
}


class DispatchError(Exception):
    """Invalid preferences (422, Turkish and English)."""

    def __init__(self, code: str, message: str, message_tr: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr = 422, code, message, message_tr

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "message_tr": self.message_tr}


@dataclass(frozen=True)
class Notice:
    """One notification for one recipient. ``key`` names the occurrence (``approval_request:12:rejected``); the
    dispatcher delivers it at most once per recipient and channel."""

    event: str
    key: str
    title: str
    body: str
    link: str | None = None
    booking_id: int | None = None
    request_id: int | None = None
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Delivery:
    """The outcome on one channel: ``sent`` (handed over), ``skipped`` (channel cannot reach the user), ``failed``,
    ``off`` (the user switched it off) or ``duplicate`` (delivered before)."""

    channel: str
    status: str
    ref_id: int | None = None
    detail: str | None = None


class ChannelAdapter(ABC):
    """A notification channel. Subclass, set the class attributes, implement :meth:`send`, then
    :func:`register_channel` an instance (see the module docstring)."""

    name: ClassVar[str]
    label_tr: ClassVar[str]
    label_en: ClassVar[str]
    #: whether the channel is on for an event the user has not chosen for
    default_enabled: ClassVar[bool] = True

    async def available_for(self, session: AsyncSession, user: User) -> bool:
        """Whether the channel can reach ``user`` (an address / a connected account); shown in the preferences."""
        return True

    @abstractmethod
    async def send(self, session: AsyncSession, user: User, notice: Notice) -> Delivery:
        """Hand ``notice`` to the channel inside the caller's transaction (write rows only, no network calls)."""


class InAppChannel(ChannelAdapter):
    name = "in_app"
    label_tr = "Uygulama içi"
    label_en = "In-app"

    async def send(self, session: AsyncSession, user: User, notice: Notice) -> Delivery:
        row = InAppNotification(
            user_id=user.id,
            kind=notice.event[:32],
            title=notice.title[:255],
            body=notice.body,
            link=notice.link,
            booking_id=notice.booking_id,
            request_id=notice.request_id,
            data=dict(notice.data) or None,
        )
        session.add(row)
        await session.flush()
        return Delivery(self.name, "sent", ref_id=row.id)


class EmailChannel(ChannelAdapter):
    name = "email"
    label_tr = "E-posta"
    label_en = "E-mail"

    async def available_for(self, session: AsyncSession, user: User) -> bool:
        return bool(user.email)

    async def send(self, session: AsyncSession, user: User, notice: Notice) -> Delivery:
        row = await mail.notify(
            session,
            kind=notice.event.replace(".", "_")[:32],
            to_email=user.email,
            subject=notice.title,
            body=notice.body,
            user_id=user.id,
            booking_id=notice.booking_id,
        )
        # the outbox row is the e-mail's own record (PENDING -> SENT / FAILED, or UNSENT without SMTP / address)
        return Delivery(self.name, "sent", ref_id=row.id, detail=row.status)


_CHANNELS: list[ChannelAdapter] = [InAppChannel(), EmailChannel()]


def channels() -> list[ChannelAdapter]:
    return list(_CHANNELS)


def channel(name: str) -> ChannelAdapter:
    for a in _CHANNELS:
        if a.name == name:
            return a
    raise KeyError(name)


def register_channel(adapter: ChannelAdapter) -> None:
    """Add a channel (once per name; the name is stored in the ledger and in the users' preferences)."""
    if not getattr(adapter, "name", None) or len(adapter.name) > 32:
        raise ValueError("a channel needs a name of at most 32 characters")
    if any(a.name == adapter.name for a in _CHANNELS):
        raise ValueError(f"channel {adapter.name!r} is registered already")
    _CHANNELS.append(adapter)


def unregister_channel(name: str) -> None:
    _CHANNELS[:] = [a for a in _CHANNELS if a.name != name]


# --------------------------------------------------------------------------------------------------
# Preferences
# --------------------------------------------------------------------------------------------------


@dataclass
class Preferences:
    """``channels``: a master switch per channel (off = off for every event); ``events``: event -> channel -> on.
    Anything not chosen: the channel's ``default_enabled``."""

    channels: dict[str, bool] = field(default_factory=dict)
    events: dict[str, dict[str, bool]] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: str | None) -> Preferences:
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        chans = {str(k): bool(v) for k, v in (data.get("channels") or {}).items() if isinstance(v, bool)}
        events: dict[str, dict[str, bool]] = {}
        for ev, per in (data.get("events") or {}).items():
            if isinstance(per, dict):
                events[str(ev)] = {str(k): bool(v) for k, v in per.items() if isinstance(v, bool)}
        return cls(chans, events)

    def dump(self) -> str:
        return json.dumps({"channels": self.channels, "events": self.events}, ensure_ascii=False, sort_keys=True)

    def channel_on(self, adapter: ChannelAdapter) -> bool:
        return self.channels.get(adapter.name, True)

    def event_on(self, event: str, adapter: ChannelAdapter) -> bool:
        return self.events.get(event, {}).get(adapter.name, adapter.default_enabled)

    def enabled(self, event: str, adapter: ChannelAdapter) -> bool:
        return self.channel_on(adapter) and self.event_on(event, adapter)


async def load_preferences(session: AsyncSession, user_id: int) -> Preferences:
    return Preferences.parse(await get_user_value(session, user_id, PREFS_KEY))


async def update_preferences(
    session: AsyncSession,
    user_id: int,
    channels_in: Mapping[str, bool] | None = None,
    events_in: Mapping[str, Mapping[str, bool]] | None = None,
) -> Preferences:
    """Merge the given switches into the stored preferences (what is not named keeps its value)."""
    names = {a.name for a in _CHANNELS}

    def check_channel(name: str) -> None:
        if name not in names:
            raise DispatchError(
                "unknown_channel",
                f"unknown channel {name!r}; channels: {', '.join(sorted(names))}",
                f"bilinmeyen kanal {name!r}; kanallar: {', '.join(sorted(names))}",
            )

    prefs = await load_preferences(session, user_id)
    for name, on in (channels_in or {}).items():
        check_channel(name)
        prefs.channels[name] = bool(on)
    for event, per in (events_in or {}).items():
        if event not in EVENTS:
            raise DispatchError(
                "unknown_event",
                f"unknown event {event!r}; events: {', '.join(EVENTS)}",
                f"bilinmeyen bildirim türü {event!r}; türler: {', '.join(EVENTS)}",
            )
        for name, on in per.items():
            check_channel(name)
            prefs.events.setdefault(event, {})[name] = bool(on)
    await set_user_value(session, user_id, PREFS_KEY, prefs.dump())
    return prefs


async def preferences_out(session: AsyncSession, user: User) -> dict[str, Any]:
    prefs = await load_preferences(session, user.id)
    return {
        "channels": [
            {
                "name": a.name,
                "label_tr": a.label_tr,
                "label_en": a.label_en,
                "enabled": prefs.channel_on(a),
                "available": await a.available_for(session, user),
                "default_enabled": a.default_enabled,
            }
            for a in _CHANNELS
        ],
        "events": [
            {
                "event": ev,
                "label_tr": tr,
                "label_en": en,
                "channels": {a.name: prefs.enabled(ev, a) for a in _CHANNELS},
            }
            for ev, (tr, en) in EVENTS.items()
        ],
    }


# --------------------------------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------------------------------


async def _delivered(session: AsyncSession, key: str, user_id: int, name: str) -> bool:
    q = select(NotificationDelivery.id).where(
        NotificationDelivery.event_key == key,
        NotificationDelivery.user_id == user_id,
        NotificationDelivery.channel == name,
    )
    return (await session.execute(q)).first() is not None


async def dispatch(session: AsyncSession, user: User, notice: Notice) -> list[Delivery]:
    """Fan ``notice`` out to ``user``'s channels, at most once per (``notice.key``, user, channel)."""
    if notice.event not in EVENTS:
        raise ValueError(f"unknown notification event {notice.event!r}")
    prefs = await load_preferences(session, user.id)
    out: list[Delivery] = []
    for adapter in list(_CHANNELS):
        if not prefs.enabled(notice.event, adapter):
            out.append(Delivery(adapter.name, "off"))
            continue
        if await _delivered(session, notice.key, user.id, adapter.name):
            out.append(Delivery(adapter.name, "duplicate"))
            continue
        ledger = NotificationDelivery(
            event=notice.event, event_key=notice.key[:160], user_id=user.id, channel=adapter.name, status="sent"
        )
        session.add(ledger)
        await session.flush()
        try:
            result = await adapter.send(session, user, notice)
        except Exception as exc:  # noqa: BLE001 - a broken channel never undoes the decision that triggered it
            log.exception("notification channel %s failed for %s", adapter.name, notice.key)
            result = Delivery(adapter.name, "failed", detail=f"{type(exc).__name__}: {exc}"[:255])
        ledger.status, ledger.ref_id, ledger.detail = result.status, result.ref_id, result.detail
        out.append(result)
    await session.flush()
    return out
