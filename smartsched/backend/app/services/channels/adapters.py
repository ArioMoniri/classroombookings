"""``notify_dispatch.ChannelAdapter`` implementations: one per channel a user sees in the preferences.

``send`` runs inside the business transaction and only writes ``channel_deliveries`` rows (the worker sends them
after the commit). It returns ``skipped`` (never ``failed``) when the channel is not switched on by an administrator
with a KVKK sign-off, or when the user linked no address. ``default_enabled`` is False: linking an address is the
opt-in (``links._switch_on``), so a channel the user never linked writes nothing.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import notify_dispatch as nd
from app.services.channels import config, links, outbox, targets, text

OFF = "channel not switched on by an administrator (configuration + KVKK sign-off)"


async def _base(session: AsyncSession) -> str:
    from app.services.calendar_feeds import public_base

    base, _source = await public_base(session)
    return base


class AddressChannel(nd.ChannelAdapter):
    """Delivers to the addresses the user linked (``user_channels`` of ``name``)."""

    default_enabled: ClassVar[bool] = False

    async def available_for(self, session: AsyncSession, user: User) -> bool:
        if await config.sender_for(session, self.name) is None:
            return False
        return bool(await links.active_channels(session, user.id, self.name))

    async def send(self, session: AsyncSession, user: User, notice: nd.Notice) -> nd.Delivery:
        from app.services.bookings_notify import _language

        sender = await config.sender_for(session, self.name)
        if sender is None:
            return nd.Delivery(self.name, "skipped", detail=OFF)
        chans = await links.active_channels(session, user.id, self.name)
        if not chans:
            return nd.Delivery(self.name, "skipped", detail="no linked address")
        payload = text.notice_payload(notice, await _language(session, user), sender.content_mode, await _base(session))
        first: int | None = None
        created = 0
        for ch in chans:
            row, new = await outbox.queue(
                session,
                kind=self.name,
                event=notice.event,
                dedupe_key=f"{notice.key}|u{user.id}|c{ch.id}",
                payload=payload,
                user_id=user.id,
                user_channel_id=ch.id,
            )
            first = first or row.id
            created += int(new)
        return nd.Delivery(self.name, "sent", ref_id=first, detail=f"queued {created} via {sender.kind}")


class DepartmentChannel(nd.ChannelAdapter):
    """A post in the recipient's department channel (Teams / Slack). Shared channels carry the approvers' events
    only (``approval.requested``): a decision about one person never goes to a shared channel. One post per
    occurrence and department, however many approvers the department has."""

    default_enabled: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("approval.requested",)

    async def available_for(self, session: AsyncSession, user: User) -> bool:
        if await config.effective(session, self.name) is None:
            return False
        return await targets.for_department(session, self.name, user.department_id) is not None

    async def send(self, session: AsyncSession, user: User, notice: nd.Notice) -> nd.Delivery:
        if notice.event not in self.EVENTS:
            return nd.Delivery(self.name, "skipped", detail="department channels carry approval.requested only")
        cfg = await config.effective(session, self.name)
        if cfg is None:
            return nd.Delivery(self.name, "skipped", detail=OFF)
        target = await targets.for_department(session, self.name, user.department_id)
        if target is None:
            return nd.Delivery(self.name, "skipped", detail="no channel mapped for the user's department")
        org_lang = await _org_language(session)
        payload = text.notice_payload(notice, org_lang, cfg.content_mode, await _base(session))
        row, new = await outbox.queue(
            session,
            kind=self.name,
            event=notice.event,
            dedupe_key=f"{notice.key}|{self.name}|t{target.id}",
            payload=payload,
            target_id=target.id,
        )
        return nd.Delivery(self.name, "sent", ref_id=row.id, detail="queued" if new else "already queued for the department")


async def _org_language(session: AsyncSession) -> str:
    from app.services.bookings_settings import get_value

    return str(await get_value(session, "org", "default_language") or "tr")


def _make(base: type[nd.ChannelAdapter], name: str, tr: str, en: str) -> nd.ChannelAdapter:
    cls = type(f"{name.title()}Channel", (base,), {"name": name, "label_tr": tr, "label_en": en})
    return cls()


ADAPTERS: tuple[nd.ChannelAdapter, ...] = (
    _make(AddressChannel, "webpush", "Tarayıcı / telefon bildirimi", "Browser / phone push"),
    _make(AddressChannel, "telegram", "Telegram", "Telegram"),
    _make(AddressChannel, "whatsapp", "WhatsApp", "WhatsApp"),
    _make(AddressChannel, "sms", "SMS", "SMS"),
    _make(DepartmentChannel, "teams", "Microsoft Teams (bölüm kanalı)", "Microsoft Teams (department channel)"),
    _make(DepartmentChannel, "slack", "Slack (bölüm kanalı)", "Slack (department channel)"),
)
