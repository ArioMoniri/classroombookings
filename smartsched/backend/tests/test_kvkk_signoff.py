"""Admin persona 2026-10-15 M-18: a KVKK sign-off is an explicit, dated action by a named administrator.

No installation ships one: ``integrations.calendar_sync_signoff`` is ``null`` and calendar sync (token feeds and
the Google / Microsoft push) is off until an administrator switches it on through
``PUT /calendar/admin/settings``, which records who and when. A stored "on" without such a record counts as off.
AI intake keeps its own sign-off (``app/ai/policy.py``) and is off on a fresh stack too. alembic
``0022_kvkk_signoff_unseed`` marks rows copied from the old pre-seeded default (2026-10-08 "KVKK officer
(institution user decision)") as not signed and switches the sync off. Runs on the real Bahar 2026 import.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from alembic import command
from app.core import db as dbmod
from app.models import Setting
from app.services import bookings_settings as bs

from tests.crbs_env import env  # noqa: F401
from tests.test_calendar_migration import _run

SETTINGS = "/api/v1/calendar/admin/settings"
#: the record every installation used to report as its own sign-off (bookings_settings before 2026-10-15)
SEEDED = {
    "by": "KVKK officer (institution user decision)",
    "at": "2026-10-08",
    "features": ["ai_nl_booking", "calendar_sync"],
    "legal_basis": "KVKK Art. 9 as amended by Law 7499 (cross-border transfer)",
    "enabled": True,
}


async def test_fresh_stack_has_no_signoff_and_everything_stays_off(env):  # noqa: F811
    c = env.client
    s = (await c.get(SETTINGS, headers=env.admin)).json()
    assert s["calendar_sync_enabled"] is False and s["calendar_sync_signoff"] is None
    _, teacher = await env.user("kvkk.öğretmen@uni.edu.tr", displayname="İpek Işıklı")
    assert (await c.get("/api/v1/calendar/sync", headers=teacher)).json()["enabled"] is False
    tok = await c.post("/api/v1/calendar/feeds/tokens", json={"label": "Google Takvim"}, headers=teacher)
    if tok.status_code == 201:  # a link may be prepared, it serves nothing before the sign-off
        assert (await c.get(f"/api/v1/calendar/feeds/{tok.json()['token']}/mine.ics")).status_code == 404
    policy = (await c.get("/api/v1/ai/policy", headers=env.admin)).json()
    assert policy["intake_enabled"] is False and policy["vision_enabled"] is False and policy["signoff"] is None

    # the explicit action: a named administrator, dated
    r = await c.put(SETTINGS, json={"calendar_sync_enabled": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    me = (await c.get("/api/v1/auth/me", headers=env.admin)).json()
    sign = r.json()["calendar_sync_signoff"]
    assert r.json()["calendar_sync_enabled"] is True
    assert sign["enabled"] is True and sign["by_user_id"] == me["id"] and sign["by"]
    assert sign["at"].startswith(date.today().isoformat()[:4]) and "T" in sign["at"]
    assert (await c.get("/api/v1/calendar/sync", headers=teacher)).json()["enabled"] is True
    tok = await c.post("/api/v1/calendar/feeds/tokens", json={"label": "Google Takvim"}, headers=teacher)
    assert tok.status_code == 201, tok.text
    assert (await c.get(f"/api/v1/calendar/feeds/{tok.json()['token']}/mine.ics")).status_code == 200


async def test_a_stored_switch_without_a_real_signoff_counts_as_off(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        await bs.set_group(s, "integrations", {"calendar_sync_enabled": True, "calendar_sync_signoff": SEEDED})
        await s.commit()
        assert await bs.get_value(s, "integrations", "calendar_sync_enabled") is False
        assert (await bs.get_group(s, "integrations"))["calendar_sync_enabled"] is False
    out = (await env.client.get(SETTINGS, headers=env.admin)).json()
    assert out["calendar_sync_enabled"] is False
    # switching it on is the sign-off that was missing
    r = await env.client.put(SETTINGS, json={"calendar_sync_enabled": True}, headers=env.admin)
    assert r.json()["calendar_sync_enabled"] is True and r.json()["calendar_sync_signoff"]["by_user_id"]


def test_signed_predicate():
    assert not bs.kvkk_signed(None) and not bs.kvkk_signed(SEEDED) and not bs.kvkk_signed({})
    real = {"enabled": True, "by": "Yönetici", "by_user_id": 1, "at": "2026-10-15T12:00:00Z", "features": []}
    assert bs.kvkk_signed(real)
    assert not bs.kvkk_signed({**real, "enabled": False})
    assert not bs.kvkk_signed({**real, "signed": False})
    assert not bs.kvkk_signed({**real, "by": "   "})
    assert not bs.kvkk_signed({**real, "by_user_id": "1"})
    assert not bs.kvkk_signed({**real, "at": "sonra"})
    assert "calendar_sync_signoff" in bs.INTEGRATIONS_SPECS
    assert bs.INTEGRATIONS_SPECS["calendar_sync_signoff"].default is None
    assert bs.INTEGRATIONS_SPECS["calendar_sync_enabled"].default is False


def test_migration_marks_seeded_signoffs_as_not_signed(tmp_path):
    for case in ("seeded", "real", "absent"):
        path = tmp_path / f"{case}.db"
        url = f"sqlite+aiosqlite:///{path}"
        _run(url, command.upgrade, "0021_outbox_queue")
        con = sqlite3.connect(path)
        real = {"enabled": True, "by": "Ayşe Yıldız", "by_user_id": 1, "at": "2026-10-12T09:30:00Z"}
        rows = [("integrations.calendar_sync_enabled", "true")]
        if case == "seeded":
            rows.append(("integrations.calendar_sync_signoff", json.dumps(SEEDED, ensure_ascii=False)))
        if case == "real":
            rows.append(("integrations.calendar_sync_signoff", json.dumps(real, ensure_ascii=False)))
        con.executemany("INSERT INTO settings (key, value, is_secret) VALUES (?, ?, 0)", rows)
        con.commit()
        con.close()
        _run(url, command.upgrade, "head")
        con = sqlite3.connect(path)
        got = dict(con.execute("SELECT key, value FROM settings WHERE key LIKE 'integrations.calendar_sync_%'"))
        con.close()
        if case == "real":
            assert got["integrations.calendar_sync_enabled"] == "true"
            assert json.loads(got["integrations.calendar_sync_signoff"]) == real
            continue
        assert got["integrations.calendar_sync_enabled"] == "false", case
        if case == "seeded":
            mark = json.loads(got["integrations.calendar_sync_signoff"])
            assert mark["signed"] is False and mark["enabled"] is False and mark["seeded"] == SEEDED
            assert not bs.kvkk_signed(mark)
        else:
            assert "integrations.calendar_sync_signoff" not in got
    assert Setting.__tablename__ == "settings"
