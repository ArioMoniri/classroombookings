"""Deploy-time settings: values given on the deploy command line are written into the database once.

    ORG_NAME=... AI_API_KEY=... SMTP_HOST=... ./deploy.sh          (or the matching deploy.sh flags)
    python infra/aws/smartsched_aws.py up --pod universal --org-name ... (values via SSM {prefix}/bootstrap/*)

deploy.sh runs this inside the backend image after the stack is healthy (same Python, same DATABASE_URL, the env
variables below passed by name, never on a command line), only when at least one of them is set:

    python /seed/tool/bootstrap_settings.py run     # write the groups that have values
    python bootstrap_settings.py plan               # list what would be written (no database, no secret values)

Every value goes through the handler the admin panel calls (``PUT /org/settings``, ``PUT /ai/admin/providers/{p}``,
``PUT /mail/settings``, ``PUT /admin/security-contact``, ``PUT /calendar/admin/settings``): the same validation,
encryption of secrets (APP_SECRET) and audit record, with the first administrator as the actor.

Groups and their variables (a group is written when its required variable is set):

    org        ORG_NAME
    ai         AI_API_KEY (required) | AI_BASE_URL, AI_PROVIDER (default anthropic)
    smtp       SMTP_HOST (required), SMTP_PORT, SMTP_SECURITY (starttls|ssl|none), SMTP_USERNAME, SMTP_PASSWORD,
               SMTP_FROM, SMTP_FROM_NAME
    security   SECURITY_CONTACT (the security.txt contact e-mail)
    google     GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET (calendar connector OAuth client)
    microsoft  MICROSOFT_CLIENT_ID + MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT

Idempotent, and the panel wins (the seed marker pattern of seed.py): the settings row ``deploy.bootstrap_settings``
records each group once it was written ("applied") or found already configured in the panel ("kept"). A recorded
group is never written again, whatever a later deploy passes, unless BOOTSTRAP_FORCE=1. The marker holds group
names and times only, never values. KVKK acknowledgements (AI transfer records, council AI, an abroad mail
provider, calendar sync sign-off) are never given here: they stay an administrator's decision in the panel.

Exit codes: 0 done (or nothing to do), 1 cannot run (no administrator yet, bad input), 3 some groups refused
(reported on stderr without values; the others are written; refused groups are retried on the next deploy).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

MARKER_KEY = "deploy.bootstrap_settings"
MARKER_VERSION = 1

# provider ids of app/ai/providers (checked again by the backend); those whose only secret is an api_key
AI_PROVIDERS = ("anthropic", "openai", "azure_openai", "openrouter", "openai_compatible", "gemini", "deepgram",
                "azure_speech", "google_stt")
SMTP_SECURITY = ("starttls", "ssl", "none")


@dataclass(frozen=True)
class Group:
    name: str
    required: tuple[str, ...]  # any of these set = the group is present
    keys: tuple[str, ...]
    secrets: tuple[str, ...] = ()
    label: str = ""


GROUPS: tuple[Group, ...] = (
    Group("org", ("ORG_NAME",), ("ORG_NAME",), label="organisation name (Yönetim > Ayarlar)"),
    Group("ai", ("AI_API_KEY", "AI_BASE_URL"), ("AI_PROVIDER", "AI_API_KEY", "AI_BASE_URL"), ("AI_API_KEY",),
          label="AI provider key (Yönetim > Yapay zekâ)"),
    Group("smtp", ("SMTP_HOST",), ("SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD",
                                   "SMTP_FROM", "SMTP_FROM_NAME"), ("SMTP_PASSWORD",),
          label="outgoing mail (Yönetim > E-posta)"),
    Group("security", ("SECURITY_CONTACT",), ("SECURITY_CONTACT",), label="security.txt contact (Yönetim > Ayarlar)"),
    Group("google", ("GOOGLE_CLIENT_ID",), ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"), ("GOOGLE_CLIENT_SECRET",),
          label="Google calendar OAuth client (Yönetim > Entegrasyonlar)"),
    Group("microsoft", ("MICROSOFT_CLIENT_ID",), ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET",
                                                  "MICROSOFT_TENANT"), ("MICROSOFT_CLIENT_SECRET",),
          label="Microsoft calendar OAuth client (Yönetim > Entegrasyonlar)"),
)
BY_NAME = {g.name: g for g in GROUPS}
#: every variable this tool reads (deploy.sh passes exactly these to the container, by name)
ALL_KEYS = tuple(dict.fromkeys(k for g in GROUPS for k in g.keys))
SECRET_KEYS = frozenset(k for g in GROUPS for k in g.secrets)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BootstrapError(Exception):
    """Bad input or a refused value. The message names the variable, never its value."""


def collect(env: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """The groups that have values, ``{group: {VAR: value}}``, after light checks (the handlers check again)."""
    vals = {k: str(env.get(k) or "").strip() for k in ALL_KEYS}
    out: dict[str, dict[str, str]] = {}
    for g in GROUPS:
        if not any(vals[k] for k in g.required):
            continue
        out[g.name] = {k: vals[k] for k in g.keys if vals[k]}
    if "ai" in out:
        p = out["ai"].setdefault("AI_PROVIDER", "anthropic").lower()
        out["ai"]["AI_PROVIDER"] = p
        if p not in AI_PROVIDERS:
            raise BootstrapError(f"AI_PROVIDER: expected one of {', '.join(AI_PROVIDERS)} (bedrock and vertex: set "
                                 "their keys in Yönetim > Yapay zekâ)")
        url = out["ai"].get("AI_BASE_URL", "")
        if url and not url.startswith(("https://", "http://")):
            raise BootstrapError("AI_BASE_URL: must start with https:// (or http:// for a local server)")
    if "smtp" in out:
        s = out["smtp"]
        if s.get("SMTP_PORT") and not (s["SMTP_PORT"].isdigit() and 1 <= int(s["SMTP_PORT"]) <= 65535):
            raise BootstrapError("SMTP_PORT: a number 1..65535")
        if s.get("SMTP_SECURITY") and s["SMTP_SECURITY"].lower() not in SMTP_SECURITY:
            raise BootstrapError(f"SMTP_SECURITY: one of {', '.join(SMTP_SECURITY)}")
        if s.get("SMTP_SECURITY"):
            s["SMTP_SECURITY"] = s["SMTP_SECURITY"].lower()
        if s.get("SMTP_FROM") and not _EMAIL.match(s["SMTP_FROM"]):
            raise BootstrapError("SMTP_FROM: an e-mail address")
    if "security" in out and not _EMAIL.match(out["security"]["SECURITY_CONTACT"]):
        raise BootstrapError("SECURITY_CONTACT: an e-mail address (e.g. security@university.edu.tr)")
    for p in ("google", "microsoft"):
        up = p.upper()
        if p in out and not out[p].get(f"{up}_CLIENT_SECRET"):
            raise BootstrapError(f"{up}_CLIENT_SECRET: required with {up}_CLIENT_ID")
        if p not in out and vals[f"{up}_CLIENT_SECRET"]:
            raise BootstrapError(f"{up}_CLIENT_ID: required with {up}_CLIENT_SECRET")
    smtp_given = [k for k in BY_NAME["smtp"].keys if vals[k]]
    if smtp_given and "smtp" not in out:
        raise BootstrapError(f"SMTP_HOST: required with {', '.join(smtp_given)}")
    # (AI_PROVIDER alone configures nothing: the default provider stays)
    return out


def describe(values: Mapping[str, Mapping[str, str]]) -> str:
    """One line per group; secret values are shown as <set>."""
    lines = []
    for name, vals in values.items():
        shown = ", ".join(f"{k}={'<set>' if k in SECRET_KEYS else v}" for k, v in vals.items())
        lines.append(f"{name}: {shown}  ({BY_NAME[name].label})")
    return "\n".join(lines) or "nothing to write"


# ---- runner ----------------------------------------------------------------------------------------------------
class Backend(Protocol):
    async def has_admin(self) -> bool: ...
    async def get_marker(self) -> dict[str, Any] | None: ...
    async def put_marker(self, marker: dict[str, Any]) -> None: ...
    async def configured(self, group: str) -> bool: ...
    async def apply(self, group: str, values: dict[str, str]) -> None: ...


@dataclass
class Outcome:
    applied: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)  # already configured in the panel: left alone
    already: list[str] = field(default_factory=list)  # recorded by an earlier deploy
    failed: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def run(values: Mapping[str, dict[str, str]], backend: Backend, *, force: bool = False,
              log: Callable[[str], None] = print, err: Callable[[str], None] | None = None) -> Outcome:
    err = err or log
    out = Outcome()
    if not values:
        log("[settings] no deploy-time settings given")
        return out
    if not await backend.has_admin():
        raise BootstrapError("no administrator exists yet (ADMIN_EMAIL is seeded on the first start); nothing written")
    marker = await backend.get_marker() or {"version": MARKER_VERSION, "groups": {}}
    done: dict[str, Any] = marker.setdefault("groups", {})
    for name, vals in values.items():
        if name in done and not force:
            out.already.append(name)
            continue
        if not force and await backend.configured(name):
            done[name] = {"at": _now(), "result": "kept"}
            out.kept.append(name)
            log(f"[settings] {name}: already set in the admin panel; kept")
            await backend.put_marker(marker)
            continue
        try:
            await backend.apply(name, dict(vals))
        except BootstrapError as exc:
            out.failed.append(name)
            err(f"[settings] {name}: refused: {exc} (set it in the admin panel, or fix the value and redeploy)")
            continue
        done[name] = {"at": _now(), "result": "applied"}
        await backend.put_marker(marker)
        out.applied.append(name)
        log(f"[settings] {name}: written ({BY_NAME[name].label})")
    log(f"[settings] applied {out.applied or '-'}, kept (panel) {out.kept or '-'}, already {out.already or '-'}, "
        f"refused {out.failed or '-'}")
    return out


# ---- the real backend (inside the backend image) ---------------------------------------------------------------
def _detail(exc: Any) -> str:
    """A refusal's message without the submitted value (FastAPI HTTPException detail: str or a dict)."""
    d = getattr(exc, "detail", exc)
    if isinstance(d, dict):
        return str(d.get("message_en") or d.get("message") or d.get("code") or "refused")
    return str(d)


class AppBackend:  # pragma: no cover - exercised through the subprocess tests with the backend venv
    def __init__(self, session: Any) -> None:
        self.s = session
        self._admin: Any = None

    async def admin(self) -> Any:
        if self._admin is None:
            from app.models import User
            from sqlalchemy import select

            q = select(User).where(User.role == "ADMIN", User.is_active.is_(True)).order_by(User.id).limit(1)
            self._admin = (await self.s.execute(q)).scalar_one_or_none()
        return self._admin

    async def has_admin(self) -> bool:
        return await self.admin() is not None

    async def get_marker(self) -> dict[str, Any] | None:
        from app.models import Setting

        row = await self.s.get(Setting, MARKER_KEY)
        return json.loads(row.value) if row is not None and row.value else None

    async def put_marker(self, marker: dict[str, Any]) -> None:
        from app.models import Setting

        value = json.dumps(marker, sort_keys=True)
        row = await self.s.get(Setting, MARKER_KEY)
        if row is None:
            self.s.add(Setting(key=MARKER_KEY, value=value, is_secret=False))
        else:
            row.value = value
        await self.s.commit()

    async def configured(self, group: str) -> bool:
        from app.services.bookings_settings import get_group

        if group == "org":
            return bool((await get_group(self.s, "org")).get("name"))
        if group == "ai":
            from app.ai import gateway as gw

            for p in AI_PROVIDERS:
                if await gw.provider_secrets(self.s, p):
                    return True
            return False
        if group == "smtp":
            return bool((await get_group(self.s, "smtp")).get("host"))
        if group == "security":
            from app.services import security_txt as st

            return bool((await st.current(self.s))["configured"])
        if group in ("google", "microsoft"):
            return bool((await get_group(self.s, "integrations")).get(f"{group}_client_id"))
        raise BootstrapError(f"unknown group {group}")

    async def apply(self, group: str, v: dict[str, str]) -> None:
        from fastapi import HTTPException
        from pydantic import ValidationError

        admin = await self.admin()
        try:
            if group == "org":
                from app.cli import SettingError, apply_setting

                try:
                    await apply_setting(self.s, "org.name", v["ORG_NAME"])
                except SettingError as exc:
                    raise BootstrapError(f"ORG_NAME: {str(exc).split(': ', 1)[-1]}") from exc
            elif group == "ai":
                from app.api.v1.ai_admin import ProviderIn, put_provider

                body = ProviderIn(api_key=v.get("AI_API_KEY") or None, base_url=v.get("AI_BASE_URL") or None,
                                  enabled=True)
                await put_provider(v["AI_PROVIDER"], body, self.s, admin)
            elif group == "smtp":
                from app.api.v1.mail_admin import MailSettingsIn
                from app.api.v1.mail_admin import put_settings as put_mail

                user = v.get("SMTP_USERNAME", "")
                data: dict[str, Any] = {"host": v["SMTP_HOST"], "auth_mode": "password" if user else "none"}
                if v.get("SMTP_PORT"):
                    data["port"] = int(v["SMTP_PORT"])
                if v.get("SMTP_SECURITY"):
                    data["security"] = v["SMTP_SECURITY"]
                for key, var in (("username", "SMTP_USERNAME"), ("password", "SMTP_PASSWORD"),
                                 ("from_address", "SMTP_FROM"), ("from_name", "SMTP_FROM_NAME")):
                    if v.get(var):
                        data[key] = v[var]
                await put_mail(MailSettingsIn(**data), self.s, admin)
            elif group == "security":
                from app.api.v1.security_contact import ContactIn, put_contact

                await put_contact(ContactIn(contact_email=v["SECURITY_CONTACT"]), self.s, admin)
            elif group in ("google", "microsoft"):
                from app.api.v1.calendar_sync import IntegrationSettingsIn, put_integration_settings

                up = group.upper()
                fields: dict[str, Any] = {f"{group}_client_id": v[f"{up}_CLIENT_ID"],
                                          f"{group}_client_secret": v[f"{up}_CLIENT_SECRET"]}
                if group == "microsoft" and v.get("MICROSOFT_TENANT"):
                    fields["microsoft_tenant"] = v["MICROSOFT_TENANT"]
                await put_integration_settings(IntegrationSettingsIn(**fields), self.s, admin)
            else:
                raise BootstrapError(f"unknown group {group}")
        except HTTPException as exc:
            await self.s.rollback()
            raise BootstrapError(_detail(exc)) from exc
        except ValidationError as exc:
            await self.s.rollback()
            fields_bad = sorted({str(e["loc"][0]) for e in exc.errors(include_input=False) if e.get("loc")})
            raise BootstrapError(f"invalid {', '.join(fields_bad) or 'value'}") from exc


async def _run_db(values: dict[str, dict[str, str]], force: bool) -> Outcome:  # pragma: no cover
    from app.core.config import get_settings
    from app.core.db import configure_engine, create_all, get_session_factory

    configure_engine(get_settings().database_url)
    await create_all()  # as app.cli does (a no-op after the entrypoint's migrations)
    async with get_session_factory()() as session:
        return await run(values, AppBackend(session), force=force,
                         err=lambda m: print(m, file=sys.stderr))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("command", choices=["run", "plan"])
    a = ap.parse_args(argv)
    try:
        values = collect(os.environ)
    except BootstrapError as exc:
        print(f"[settings] {exc}", file=sys.stderr)
        return 1
    if a.command == "plan":
        print(f"[settings] {describe(values)}")
        return 0
    if not values:
        print("[settings] no deploy-time settings given")
        return 0
    # the backend package: the image's working directory (/app) or the current directory
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    try:
        out = asyncio.run(_run_db(values, os.environ.get("BOOTSTRAP_FORCE") == "1"))
    except BootstrapError as exc:
        print(f"[settings] {exc}", file=sys.stderr)
        return 1
    return 3 if out.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
