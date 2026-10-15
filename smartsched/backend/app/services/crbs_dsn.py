"""Live CRBS MySQL DSNs (review 2026-10-15 D16): SSRF guard for ``POST /imports/crbs`` with a ``dsn``.

The importer connects to whatever host the DSN names, so a live DSN is accepted only

* from a ``planning.admin`` (403 otherwise), and
* for a host (and port) an administrator listed in the ``crbs_dsn_allowed_hosts`` setting: comma separated host
  names or IP addresses, optionally ``:port`` (default 3306), exact matches only, no wildcards. The setting is
  empty by default, so no live DSN is accepted until an admin names the CRBS database server (422).

Only ``mysql://`` / ``mysql+pymysql://`` with a host and no query string (``unix_socket`` and friends) pass. SQL
dump uploads never open a connection and are not affected.

Call site (``app/api/v1/imports.py``, ``import_crbs_endpoint``)::

    if dsn:
        await crbs_dsn.check_dsn(db, dsn, user)
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import settings_service as ss
from app.services.bookings_perms import load_access

SETTING = "crbs_dsn_allowed_hosts"
DEFAULT_PORT = 3306
SCHEMES = frozenset({"mysql", "mysql+pymysql"})
_HOST_RX = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$|^\[[0-9a-f:]+\]$")

Allowed = list[tuple[str, int | None]]


def parse_allowlist(value: str | list[str] | None) -> Allowed:
    """``"crbs-db.uni.edu.tr, 10.0.4.12:3307"`` -> ``[("crbs-db.uni.edu.tr", None), ("10.0.4.12", 3307)]``
    (lower case, NBSP and spaces stripped, duplicates dropped). ValueError on a malformed entry."""
    items = value if isinstance(value, list) else str(value or "").split(",")
    out: Allowed = []
    for raw in items:
        entry = str(raw).replace("\xa0", " ").strip().lower()
        if not entry:
            continue
        m = re.match(r"^(\[[0-9a-f:]+\])(?::(\d+))?$", entry) or re.match(r"^([^:\[\]]+)(?::(\d+))?$", entry)
        if m is None:
            raise ValueError(f"'{raw}' is not a host name or IP address (no wildcards)")
        host, port = m.group(1), int(m.group(2)) if m.group(2) else None
        if port is not None and not 1 <= port <= 65535:
            raise ValueError(f"invalid port in '{raw}'")
        if not _HOST_RX.match(host):
            raise ValueError(f"'{raw}' is not a host name or IP address (no wildcards)")
        if (host, port) not in out:
            out.append((host, port))
    return out


def format_allowlist(allowed: Allowed) -> str:
    return ", ".join(h if p is None else f"{h}:{p}" for h, p in allowed)


def dsn_issues(dsn: str, allowed: Allowed) -> list[str]:
    """Why ``dsn`` may not be opened; empty = it names a listed MySQL host."""
    try:
        u = urlsplit(str(dsn).strip())
        port = u.port or DEFAULT_PORT
    except ValueError:
        return ["the DSN is not a valid URL"]
    if u.scheme.lower() not in SCHEMES:
        return ["only mysql:// DSNs are accepted"]
    host = (u.hostname or "").lower()
    if not host:
        return ["the DSN names no host"]
    if u.query or u.fragment:
        return ["DSN options (?unix_socket=... etc.) are not accepted"]
    if not allowed:
        return [f"no CRBS database host is allowed yet; an administrator lists it in the '{SETTING}' setting"]
    if not any(host == h and port == (p or DEFAULT_PORT) for h, p in allowed):
        return [f"host {host}:{port} is not in '{SETTING}' ({format_allowlist(allowed)})"]
    return []


async def check_dsn(session: AsyncSession, dsn: str, user: User) -> None:
    """403 unless ``user`` is a planning admin; 422 unless the DSN names an allowed host."""
    if "planning.admin" not in (await load_access(session, user)).perms:
        raise HTTPException(403, "importing from a live CRBS database is admin-only; upload an SQL dump instead")
    try:
        allowed = parse_allowlist(await ss.get_value(session, SETTING))
    except ValueError:
        allowed = []
    issues = dsn_issues(dsn, allowed)
    if issues:
        raise HTTPException(422, {"message": "CRBS DSN refused", "issues": issues, "setting": SETTING})


__all__ = ["SETTING", "check_dsn", "dsn_issues", "format_allowlist", "parse_allowlist"]
