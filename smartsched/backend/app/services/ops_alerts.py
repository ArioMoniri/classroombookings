"""Alert relay (W3-OPS): Prometheus alerts -> the administrators, without an Alertmanager.

Every 60 s the backend polls ``{OPS_PROMETHEUS_URL}/api/v1/alerts`` (rules: deploy/observability/prometheus/alerts.yml)
and hands new events to the notification dispatcher as event ``ops.alert`` (bell, e-mail through the themed renderer,
any channel an admin connected), addressed to every active user whose role holds ``setup.settings`` or
``planning.admin`` (or the legacy role ADMIN).

* **Fire once**: an alert is identified by ``alertname`` + its labels (fingerprint) and its ``activeAt``; the
  dispatcher's ledger key ``ops_alert:<fp>:<activeAt>:firing:<n>`` makes the delivery idempotent per admin and
  channel, also across uvicorn workers and replicas polling at the same time.
* **Re-notify after 6 h** while it is still firing: ``n`` = whole 6-hour periods since ``activeAt``.
* **Resolve once**: an alert seen firing before and absent now gets ``...:resolved``. The set of firing alerts is kept
  in the settings row ``ops.alert_relay`` (JSON), so a restart does not forget what was firing. Nothing is resolved
  while Prometheus is unreachable.
* ``pending`` alerts (inside their ``for:``) are not relayed.

The loop is started lazily by the observability middleware on the first request (outside tests); ``poll_once`` is
the unit the tests drive with a fake Prometheus.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.services import notify_dispatch

log = logging.getLogger("smartsched.ops_alerts")

EVENT = "ops.alert"
STATE_KEY = "ops.alert_relay"
INTERVAL_S = 60.0
RENOTIFY_S = 6 * 3600
OPS_PERMS = ("setup.settings", "planning.admin")

# the dispatcher refuses unknown events; ops.alert is listed in the notification preferences next to the others
notify_dispatch.EVENTS.setdefault(EVENT, ("Sistem uyarıları (yöneticiler)", "System alerts (administrators)"))

_task: asyncio.Task[None] | None = None


def fingerprint(labels: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(labels, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def fetch_alerts() -> list[dict[str, Any]]:
    """Firing alerts from Prometheus; raises when it cannot be read."""
    base = (os.environ.get("OPS_PROMETHEUS_URL") or "").rstrip("/")
    if not base:
        raise LookupError("not_configured")
    async with httpx.AsyncClient(timeout=5.0) as c:
        r = await c.get(f"{base}/api/v1/alerts")
    r.raise_for_status()
    alerts = r.json().get("data", {}).get("alerts", [])
    return [a for a in alerts if a.get("state") == "firing"]


async def _admins(session: Any) -> list[Any]:
    from app.models import Permission, RolePermission, User

    roles = select(RolePermission.role_id).join(Permission, Permission.id == RolePermission.permission_id)
    roles = roles.where(Permission.name.in_(OPS_PERMS))
    q = select(User).where(User.is_active.is_(True))
    q = q.where(or_(User.role_id.in_(roles), (User.role_id.is_(None)) & (User.role == "ADMIN")))
    return list((await session.execute(q.order_by(User.id))).scalars())


async def _load_state(session: Any) -> dict[str, dict[str, Any]]:
    from app.models import Setting

    row = await session.get(Setting, STATE_KEY)
    try:
        data = json.loads(row.value) if row is not None and row.value else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


async def _save_state(session: Any, state: dict[str, dict[str, Any]]) -> None:
    from app.models import Setting

    row = await session.get(Setting, STATE_KEY)
    if row is None:
        session.add(Setting(key=STATE_KEY, value=json.dumps(state), is_secret=False))
    else:
        row.value = json.dumps(state)


def _texts(info: dict[str, Any], status: str, english: bool, hours: int) -> tuple[str, str]:
    name = info.get("name") or "alert"
    summary = (info.get("summary_en") if english else info.get("summary_tr")) or info.get("summary_tr") or name
    if english:
        head = {"firing": "Alert", "reminder": "Still firing", "resolved": "Resolved"}[status]
        tail = {
            "firing": f"Severity: {info.get('severity', 'warning')}. Details on Operations (/admin/ops).",
            "reminder": f"Firing for {hours} h. Details on Operations (/admin/ops).",
            "resolved": "The condition has cleared.",
        }[status]
    else:
        head = {"firing": "Uyarı", "reminder": "Uyarı sürüyor", "resolved": "Çözüldü"}[status]
        sev = {"critical": "kritik", "warning": "uyarı", "info": "bilgi"}.get(str(info.get("severity")), "uyarı")
        tail = {
            "firing": f"Önem: {sev}. Ayrıntılar Operasyon sayfasında (/admin/ops).",
            "reminder": f"{hours} saattir sürüyor. Ayrıntılar Operasyon sayfasında (/admin/ops).",
            "resolved": "Durum düzeldi.",
        }[status]
    return f"{head}: {summary}"[:255], f"{summary}\n{tail}"


async def _notify(session: Any, admins: list[Any], key: str, info: dict[str, Any], status: str, hours: int) -> int:
    sent = 0
    for user in admins:
        english = str(user.language or "").lower().startswith("en")
        title, body = _texts(info, "resolved" if status == "resolved" else status, english, hours)
        notice = notify_dispatch.Notice(
            event=EVENT,
            key=key,
            title=title,
            body=body,
            link="/admin/ops",
            data={
                "alert": info.get("name"),
                "severity": info.get("severity"),
                "status": "resolved" if status == "resolved" else "firing",
                "labels": info.get("labels", {}),
                "active_at": info.get("active_at"),
            },
        )
        out = await notify_dispatch.dispatch(session, user, notice)
        if any(d.status == "sent" for d in out):
            sent += 1
    return 1 if sent else 0


async def poll_once(now: datetime | None = None) -> dict[str, Any]:
    """One relay pass. Returns ``{firing, notified, resolved}`` (+ ``error`` when Prometheus could not be read)."""
    from app.core.db import get_session_factory

    now = now or datetime.now(UTC)
    try:
        alerts = await fetch_alerts()
    except LookupError:
        return {"firing": 0, "notified": 0, "resolved": 0, "error": "not_configured"}
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return {"firing": 0, "notified": 0, "resolved": 0, "error": type(exc).__name__}

    current: dict[str, dict[str, Any]] = {}
    for a in alerts:
        labels = {str(k): str(v) for k, v in (a.get("labels") or {}).items()}
        ann = a.get("annotations") or {}
        fp = fingerprint(labels)
        current[fp] = {
            "name": labels.get("alertname"),
            "severity": labels.get("severity", "warning"),
            "labels": labels,
            "summary_tr": ann.get("summary_tr") or ann.get("summary"),
            "summary_en": ann.get("summary_en") or ann.get("summary"),
            "active_at": a.get("activeAt"),
        }

    notified = resolved = 0
    async with get_session_factory()() as session:
        state = await _load_state(session)
        admins = await _admins(session)
        try:
            for fp, info in current.items():
                started = _parse_ts(info["active_at"]) or now
                periods = max(0, int((now - started).total_seconds() // RENOTIFY_S))
                key = f"ops_alert:{fp}:{info['active_at']}:firing:{periods}"
                status = "reminder" if periods else "firing"
                notified += await _notify(session, admins, key, info, status, periods * 6)
            for fp, info in state.items():
                if fp in current:
                    continue
                key = f"ops_alert:{fp}:{info.get('active_at')}:resolved"
                resolved += await _notify(session, admins, key, info, "resolved", 0)
            await _save_state(session, current)
            await session.commit()
        except IntegrityError:
            # another worker / replica delivered the same keys a moment earlier: its ledger rows win
            await session.rollback()
            return {"firing": len(current), "notified": 0, "resolved": 0, "error": "concurrent"}
    return {"firing": len(current), "notified": notified, "resolved": resolved}


async def _loop(interval: float) -> None:
    while True:
        try:
            out = await poll_once()
            if out.get("notified") or out.get("resolved"):
                log.info("alert relay: %s", out)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the relay must never stop or break the app
            log.warning("alert relay pass failed", exc_info=True)
        await asyncio.sleep(interval)


def start(interval: float = INTERVAL_S) -> None:
    """Start the polling loop once per process (no-op when it runs already)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.get_running_loop().create_task(_loop(interval), name="ops-alert-relay")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
