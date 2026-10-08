"""LDAP authentication with ``ldap3`` (port of CRBS ``libraries/Auth_ldap.php``).

1. Bind as ``bind_dn_format`` with ``:user`` replaced by the username, using the user's password.
2. If ``search_filter`` is set, search ``base_dn`` for exactly one entry and read the mapped attributes.
   Mapping templates are an attribute name (``cn``) or a template with ``:attr`` placeholders
   (``:givenName :sn``), exactly like CRBS.
3. Create the local user when ``create_users`` (default role/department) or update the existing one;
   disabled users are refused before binding.
4. Keep a local password hash so users can sign in while the directory is unreachable (CRBS does the
   same); the caller falls back to local auth only on connection errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import ldap3
from ldap3.core import exceptions as ldap_exc
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import clean_email, fold_username
from app.core.security import hash_password
from app.models import Program, Role, User
from app.services.bookings_perms import set_user_role
from app.services.bookings_settings import get_group

_PLACEHOLDER_RX = re.compile(r":([A-Za-z0-9+]+)")
MAPPING = {
    "firstname": "attr_firstname",
    "lastname": "attr_lastname",
    "displayname": "attr_displayname",
    "email": "attr_email",
}


@dataclass
class LdapResult:
    ok: bool
    user: User | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    connection_error: bool = False


def mapping_attributes(cfg: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for prop in MAPPING.values():
        template = str(cfg.get(prop) or "").strip()
        if not template:
            continue
        if template.isalpha():
            out.append(template)
        else:
            out.extend(_PLACEHOLDER_RX.findall(template))
    return sorted(set(out))


def map_attributes(cfg: dict[str, Any], attrs: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop, key in MAPPING.items():
        template = str(cfg.get(key) or "").strip()
        if not template:
            continue
        if template.isalpha():
            template = f":{template}"
        value = _PLACEHOLDER_RX.sub(lambda m: attrs.get(m.group(1), ""), template).strip()
        if value:
            out[prop] = value
    return out


def _server(cfg: dict[str, Any]) -> ldap3.Server:
    tls = None
    if cfg.get("use_tls"):
        import ssl

        tls = ldap3.Tls(validate=ssl.CERT_NONE if cfg.get("ignore_cert") else ssl.CERT_REQUIRED)
    return ldap3.Server(
        str(cfg["server"]),
        port=int(cfg.get("port") or 389),
        use_ssl=bool(cfg.get("use_tls")),
        tls=tls,
        get_info=ldap3.NONE,
        connect_timeout=10,
    )


def verify(cfg: dict[str, Any], username: str, password: str) -> LdapResult:
    """Bind (and search) against the directory. Network errors set ``connection_error``."""
    if not cfg.get("server") or not cfg.get("port"):
        return LdapResult(False, errors=["no_server_or_port"], connection_error=True)
    if not username or not password:
        return LdapResult(False, errors=["no_username_or_password"])
    bind_dn = str(cfg.get("bind_dn_format") or "").replace(":user", username)
    try:
        conn = ldap3.Connection(
            _server(cfg), user=bind_dn, password=password, version=int(cfg.get("version") or 3), receive_timeout=10
        )
        if not conn.bind():
            return LdapResult(False, errors=["bind_error", str(conn.result.get("description", ""))])
    except (
        ldap_exc.LDAPSocketOpenError,
        ldap_exc.LDAPSocketReceiveError,
        ldap_exc.LDAPSessionTerminatedByServerError,
    ) as exc:
        return LdapResult(False, errors=["no_socket_connection", str(exc)], connection_error=True)
    except ldap_exc.LDAPException as exc:
        return LdapResult(False, errors=["bind_error", str(exc)])
    try:
        search = str(cfg.get("search_filter") or "").strip()
        if not search:
            return LdapResult(True)
        query = search.replace(":user", escape_filter_chars(username))
        fields = mapping_attributes(cfg)
        if not conn.search(str(cfg.get("base_dn") or ""), query, attributes=fields or ldap3.NO_ATTRIBUTES):
            return LdapResult(False, errors=["search_error"])
        if len(conn.entries) != 1:
            return LdapResult(False, errors=["search_num_results_error"])
        entry = conn.entries[0]
        attrs: dict[str, str] = {"dn": str(entry.entry_dn)}
        for f in fields:
            if f in entry.entry_attributes:
                vals = entry[f].values
                attrs[f] = str(vals[0]) if vals else ""
        return LdapResult(True, attributes=attrs)
    except ldap_exc.LDAPException as exc:
        return LdapResult(False, errors=["search_error", str(exc)])
    finally:
        try:
            conn.unbind()
        except ldap_exc.LDAPException:
            pass


async def authenticate(session: AsyncSession, username: str, password: str) -> LdapResult:
    cfg = await get_group(session, "ldap")
    if not cfg["enabled"]:
        return LdapResult(False, errors=["ldap_not_enabled"])
    try:
        key = fold_username(username)
    except ValueError:
        return LdapResult(False, errors=["invalid_username"])
    user = (await session.execute(select(User).where(User.username == key))).scalar_one_or_none()
    if user is not None and not user.is_active:
        return LdapResult(False, errors=["user_not_enabled"])
    if user is None and not cfg["create_users"]:
        return LdapResult(False, errors=["user_not_found_no_create"])
    res = verify(cfg, username.strip(), password)
    if not res.ok:
        return res
    props = map_attributes(cfg, res.attributes) if res.attributes else {}
    email = None
    if props.get("email"):
        try:
            email = clean_email(props["email"])
        except ValueError:
            email = None
    if email:
        clash = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if clash is not None and (user is None or clash.id != user.id):
            email = None  # e-mail already taken by another account: keep the user without it
    if user is None:
        user = User(username=key, is_active=True, auth_source="ldap")
        # CRBS: ldap_default_role_id; without it the account has no role (and no permissions) until an
        # admin assigns one
        role = await session.get(Role, cfg["default_role_id"]) if cfg.get("default_role_id") else None
        set_user_role(user, role)
        if cfg.get("default_department_id") and await session.get(Program, cfg["default_department_id"]):
            user.department_id = int(cfg["default_department_id"])
        session.add(user)
    user.auth_source = "ldap"
    if props.get("firstname"):
        user.firstname = props["firstname"]
    if props.get("lastname"):
        user.lastname = props["lastname"]
    if props.get("displayname"):
        user.full_name = props["displayname"]
    if email:
        user.email = email
    user.password_hash = hash_password(password)
    await session.flush()
    res.user = user
    return res
