"""Department -> Teams / Slack channel webhooks (phase 1: department channel posts; personal DMs are phase 2).

The administrator enters the URL; a user never pastes one (the URL is a bearer secret and would reopen SSRF).
Every URL passes, at save time and again right before each send:

1. the M-41 webhook rules (``app.services.webhooks.validate_url``: no user info, no private / loopback /
   link-local / metadata literal, no localhost names), https only, port 443;
2. the vendor allowlist: Teams Workflows on ``*.logic.azure.com`` or ``*.api.powerplatform.com`` (Office 365
   connectors were retired in 2026), Slack incoming webhooks on ``hooks.slack.com``;
3. Apprise must parse it as that vendor's notifier (``NotifyWorkflows`` / ``NotifySlack``);
4. DNS: every address the host resolves to must be public (``webhooks.check_resolved``).

The URL is stored Fernet-encrypted; responses show the host only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_secret
from app.importers import normalize as n
from app.models import ChannelDepartmentTarget, Program, User
from app.services import audit
from app.services.channels.config import ConfigError

ALLOW: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    # kind -> (exact hosts, host suffixes, Apprise notifier)
    "teams": ((), (".logic.azure.com", ".api.powerplatform.com"), "NotifyWorkflows"),
    "slack": (("hooks.slack.com",), (), "NotifySlack"),
}


def _refused(kind: str, en: str, tr: str) -> ConfigError:
    return ConfigError("url_refused", f"{kind} webhook URL refused: {en}", f"{kind} webhook adresi reddedildi: {tr}")


async def check_url(kind: str, value: Any, *, resolve: bool = True) -> str:
    from app.services import webhooks
    from app.services.channels import transport

    if kind not in ALLOW:
        raise ConfigError("unknown_channel", f"{kind} has no department targets", f"{kind} bölüm hedefi almaz", 404)
    url = (n.clean_text(value) or "").replace(" ", "")
    try:
        url = webhooks.validate_url(url)
    except ValueError as exc:
        raise _refused(kind, str(exc), str(exc)) from exc
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    exact, suffixes, plugin = ALLOW[kind]
    if parts.scheme != "https" or parts.port not in (None, 443):
        raise _refused(kind, "https on port 443 only", "yalnızca 443 portunda https")
    if not (host in exact or (suffixes and host.endswith(suffixes))):
        raise _refused(
            kind,
            f"the host is not on the {kind} allowlist ({', '.join(exact + tuple('*' + s for s in suffixes))})",
            f"adres {kind} izin listesinde değil ({', '.join(exact + tuple('*' + s for s in suffixes))})",
        )
    if not transport.apprise_url_ok(url, plugin):
        raise _refused(kind, "not a webhook URL of this service", "bu servisin webhook adresi değil")
    if resolve:
        try:
            await webhooks.check_resolved(url)
        except ValueError as exc:
            raise _refused(kind, str(exc), "engellenen adres (blocked): " + str(exc)) from exc
    return url


def target_out(t: ChannelDepartmentTarget, department: str | None) -> dict[str, Any]:
    return {
        "id": t.id,
        "kind": t.kind,
        "department_id": t.department_id,
        "department": department,
        "host": t.host,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


async def for_department(session: AsyncSession, kind: str, department_id: int | None) -> ChannelDepartmentTarget | None:
    if department_id is None:
        return None
    q = select(ChannelDepartmentTarget).where(
        ChannelDepartmentTarget.kind == kind, ChannelDepartmentTarget.department_id == department_id
    )
    return (await session.execute(q)).scalar_one_or_none()


async def put(session: AsyncSession, kind: str, department_id: int, url: Any, admin: User) -> dict[str, Any]:
    dept = await session.get(Program, department_id)
    if dept is None:
        raise ConfigError("department_not_found", "department not found", "bölüm bulunamadı", 404)
    clean = await check_url(kind, url)
    host = (urlsplit(clean).hostname or "").lower()
    row = await for_department(session, kind, department_id)
    created = row is None
    if row is None:
        row = ChannelDepartmentTarget(kind=kind, department_id=department_id, created_by=admin.id)
        session.add(row)
    row.url_enc, row.host = encrypt_secret(clean), host[:255]
    await session.flush()
    await audit.record(
        session,
        "channels.department_target",
        "channel_department_target",
        row.id,
        after={"kind": kind, "department_id": department_id, "host": host, "created": created},
        actor=admin,
    )
    return target_out(row, dept.name)


async def remove(session: AsyncSession, kind: str, department_id: int, admin: User) -> bool:
    row = await for_department(session, kind, department_id)
    if row is None:
        return False
    rid, host = row.id, row.host
    await session.delete(row)
    await session.flush()
    await audit.record(
        session,
        "channels.department_target_delete",
        "channel_department_target",
        rid,
        before={"kind": kind, "department_id": department_id, "host": host},
        actor=admin,
    )
    return True


async def listing(session: AsyncSession, kind: str | None = None) -> list[dict[str, Any]]:
    q = select(ChannelDepartmentTarget, Program.name).join(Program, Program.id == ChannelDepartmentTarget.department_id)
    if kind:
        q = q.where(ChannelDepartmentTarget.kind == kind)
    rows = (await session.execute(q.order_by(ChannelDepartmentTarget.kind, Program.name))).all()
    return [target_out(t, name) for t, name in rows]
