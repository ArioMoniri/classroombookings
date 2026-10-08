"""Installer requirements step (CRBS ``Install::check_requirements``, MISSING 6 of the 2026-10-08 parity audit).

CRBS checks the PHP version, the GD module, the LDAP module (warning only), writable ``local`` / ``uploads``
folders, the database connection and an empty database before it creates the first administrator. SmartSched
checks the same things for its own runtime: Python, Pillow (logo / photo re-encoding), ldap3, the uploads
folder, the database and the migration state; plus the production secrets and SMTP (warnings), which CRBS
does not check. ``err`` blocks the first-run setup; ``warn`` is shown only."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Literal, TypedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_APP_SECRET, get_settings

Status = Literal["ok", "warn", "err"]
MIN_PYTHON = (3, 12)  # pyproject requires-python
ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"


class Check(TypedDict):
    status: Status
    message: str


def _check(status: Status, message: str = "") -> Check:
    return {"status": status, "message": message}


def _python() -> Check:
    have = ".".join(str(x) for x in sys.version_info[:3])
    ok = sys.version_info[:2] >= MIN_PYTHON
    need = ".".join(str(x) for x in MIN_PYTHON)
    return _check("ok" if ok else "err", f"Python {have}" + ("" if ok else f"; {need} or newer is required."))


def _image_library() -> Check:
    try:
        import io

        from PIL import Image

        Image.new("RGB", (2, 2)).save(io.BytesIO(), "PNG")
    except Exception as exc:  # noqa: BLE001 - any failure means uploads cannot be re-encoded
        return _check("err", f"Pillow cannot encode images ({type(exc).__name__}); logo and room photo uploads fail.")
    return _check("ok")


def _ldap_module() -> Check:
    if importlib.util.find_spec("ldap3") is None:
        return _check("warn", "The 'ldap3' package is only needed for LDAP authentication.")
    return _check("ok")


def _folder(path: Path, label: str) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".write-test-"):
            pass
    except OSError:
        if not path.is_dir():
            return _check("err", f"'{label}' folder does not exist and could not be created.")
        return _check("err", f"'{label}' folder does not have writable permissions.")
    return _check("ok")


async def _database(session: AsyncSession) -> tuple[Check, Check]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return _check("err", f"Database error: {type(exc).__name__}"), _check("err", "Database unreachable.")
    try:
        current = set((await session.execute(text("SELECT version_num FROM alembic_version"))).scalars())
    except Exception:  # noqa: BLE001 - no alembic_version table
        await session.rollback()
        return _check("ok"), _check("warn", "The schema was created without migrations (no alembic_version).")
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    heads = set(ScriptDirectory.from_config(cfg).get_heads())
    if current != heads:
        have, want = ", ".join(sorted(current)) or "none", ", ".join(sorted(heads))
        return _check("ok"), _check("err", f"Database schema is at {have}; run 'alembic upgrade head' ({want}).")
    return _check("ok"), _check("ok")


def _secrets() -> Check:
    settings = get_settings()
    reasons = settings.insecure_reasons()
    if reasons:
        return _check("err", "; ".join(reasons))
    if settings.app_secret == DEFAULT_APP_SECRET:
        return _check("warn", "APP_SECRET is the development default; set your own before going live.")
    return _check("ok")


async def check_requirements(session: AsyncSession, smtp_ready: bool) -> dict[str, Check]:
    """Ordered like the CRBS installer; keys are stable for the frontend checklist."""
    database, schema = await _database(session)
    out: dict[str, Check] = {
        "python_version": _python(),
        "image_library": _image_library(),
        "ldap_module": _ldap_module(),
        "folder_uploads": _folder(Path(get_settings().upload_dir), "uploads"),
        "database": database,
        "database_schema": schema,
        "secrets": _secrets(),
        "smtp": _check("ok")
        if smtp_ready
        else _check("warn", "SMTP is not configured; e-mails are kept in the outbox until it is."),
    }
    return out


def failing(checks: dict[str, Check]) -> list[str]:
    return [k for k, v in checks.items() if v["status"] == "err"]
