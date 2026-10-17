"""CAL-04 one-off ``.ics`` files from the same engine as the links, on the real Bahar 2026 import:
``/calendar/export/classes.ics``, ``/calendar/export/department/{id}.ics``, ``/calendar/export/bookings.ics`` (JWT,
attachment ``derslerim-2026-bahar.ics``) carry the same UIDs and SEQUENCE as the subscription feed; the planner's run
export (``/runs/{id}/export?format=ics``) is written with TZID=Europe/Istanbul + VTIMEZONE (no floating times) and
without the board notes."""

from __future__ import annotations

from datetime import date

import pytest
from app.core import db as dbmod
from app.models import Assignment
from sqlalchemy import update

from tests.cal_support import events, link_instructor, lint_ics, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)


async def test_cal_04_file_and_feed_share_uids_and_sequence(env):  # noqa: F811
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz", department_id=p.program_id)
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    sub = (
        await env.client.post("/api/v1/calendar/subscriptions", json={"scope_kind": "my_classes"}, headers=ayse)
    ).json()
    feed = (await env.client.get(f"/api/v1/calendar/feeds/{sub['token']}/classes.ics")).text
    f = await env.client.get("/api/v1/calendar/export/classes.ics", headers=ayse)
    assert f.status_code == 200, f.text
    assert f.headers["content-disposition"] == 'attachment; filename="derslerim-2026-bahar.ics"'
    assert f.headers["cache-control"] == "private, no-store"
    cal = lint_ics(f.text, forbidden=p.instructor_names)
    assert "SOURCE" not in cal  # a file never refreshes itself
    pairs = lambda text: {(str(e["UID"]), int(e["SEQUENCE"])) for e in events(text)}  # noqa: E731
    assert pairs(f.text) == pairs(feed) and pairs(feed)
    # the department file: the same UIDs as the department-classes link
    dep = await env.client.get(f"/api/v1/calendar/export/department/{p.program_id}.ics", headers=ayse)
    assert dep.status_code == 200
    assert dep.headers["content-disposition"].startswith('attachment; filename="bolum-psikoloji')
    assert dep.headers["content-disposition"].endswith('-2026-bahar.ics"')
    assert pairs(f.text) <= pairs(dep.text)
    # another department: 403 with the Turkish reason
    other = await env.client.get(f"/api/v1/calendar/export/department/{p.program_id + 1}.ics", headers=ayse)
    assert other.status_code == 403 and other.json()["detail"]["code"] == "department_not_allowed"
    # my bookings as a file
    await env.book(ayse, "A101", date(2026, 2, 17), "P1")
    b = await env.client.get("/api/v1/calendar/export/bookings.ics", headers=ayse)
    assert b.status_code == 200 and b.headers["content-disposition"] == 'attachment; filename="rezervasyonlarim.ics"'
    assert any(str(e["UID"]).startswith("booking-") for e in events(b.text))


async def test_cal_04_run_export_uses_tzid_and_no_board_notes(env):  # noqa: F811
    p = await psy262(env)
    async with dbmod.get_session_factory()() as s:
        await s.execute(
            update(Assignment).where(Assignment.id == p.week5_assignment_id).values(notes="Ezgi Hoca izinli")
        )
        await s.commit()
    r = await env.client.get(f"/api/v1/runs/{env.run_id}/export", params={"format": "ics"}, headers=env.planner)
    assert r.status_code == 200
    assert r.headers["content-disposition"] == f'attachment; filename="smartsched-run{env.run_id}.ics"'
    text = r.text
    cal = lint_ics(text)
    assert [str(t["TZID"]) for t in cal.walk("VTIMEZONE")] == ["Europe/Istanbul"]
    assert "DTSTART;TZID=Europe/Istanbul:20260302T133000" in text
    assert "Ezgi Hoca izinli" not in text
    starts = [ln for ln in text.split("\r\n") if ln.startswith("DTSTART")]
    assert starts and all(ln.startswith("DTSTART;TZID=") or ln == "DTSTART:19700101T000000" for ln in starts)
