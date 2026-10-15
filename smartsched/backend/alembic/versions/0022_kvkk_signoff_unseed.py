"""KVKK sign-off is never seeded (admin persona 2026-10-15 M-18).

Until this release every installation reported the user's 2026-10-08 decision ("KVKK officer (institution user
decision)") as its own calendar-sync sign-off, and calendar sync defaulted to on. A sign-off is now an explicit,
dated action by a named administrator (``PUT /calendar/admin/settings``). This migration:

* replaces a stored copy of the former seeded record with a "not signed" marker (``signed: false``; the old
  record is kept under ``seeded`` for the audit trail);
* switches ``integrations.calendar_sync_enabled`` off wherever no real sign-off (enabled, ``by``, integer
  ``by_user_id``, ISO ``at``) is stored, so token feeds and push connectors stay off until an administrator
  signs off. Installations that never stored either row need nothing: the new defaults are off / ``null``.

Downgrade leaves the rows as they are: a sign-off cannot be invented back.

Revision ID: 0022_kvkk_signoff_unseed
Revises: 0021_outbox_queue
Create Date: 2026-10-15 21:00:00

"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0022_kvkk_signoff_unseed"
down_revision = "0021_outbox_queue"
branch_labels = None
depends_on = None

ENABLED = "integrations.calendar_sync_enabled"
SIGNOFF = "integrations.calendar_sync_signoff"
SEEDED_BY = "KVKK officer (institution user decision)"
SEEDED_AT = "2026-10-08"

settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.Text))


def _signed(record: Any) -> bool:
    """Same rule as ``app.services.bookings_settings.kvkk_signed`` (copied: migrations do not import app code)."""
    if not isinstance(record, dict) or record.get("enabled") is not True or record.get("signed") is False:
        return False
    uid, by = record.get("by_user_id"), record.get("by")
    if not isinstance(uid, int) or isinstance(uid, bool) or not isinstance(by, str) or not by.strip():
        return False
    try:
        date.fromisoformat(str(record.get("at"))[:10])
    except ValueError:
        return False
    return True


def upgrade() -> None:
    conn = op.get_bind()
    rows = dict(
        conn.execute(sa.select(settings.c.key, settings.c.value).where(settings.c.key.in_([ENABLED, SIGNOFF]))).all()
    )
    record: Any = None
    if rows.get(SIGNOFF):
        try:
            record = json.loads(rows[SIGNOFF])
        except ValueError:
            record = None
    if isinstance(record, dict) and record.get("by") == SEEDED_BY and str(record.get("at")) == SEEDED_AT:
        if "by_user_id" not in record:
            record = {
                "signed": False,
                "enabled": False,
                "by": None,
                "at": None,
                "note": "pre-seeded default removed (release 2026-10-15); an administrator must sign off",
                "seeded": record,
            }
            conn.execute(
                settings.update().where(settings.c.key == SIGNOFF).values(value=json.dumps(record, ensure_ascii=False))
            )
    stored_on = str(rows.get(ENABLED) or "").lower() in {"1", "true", "yes", "on"}
    if stored_on and not _signed(record):
        conn.execute(settings.update().where(settings.c.key == ENABLED).values(value="false"))


def downgrade() -> None:
    pass
