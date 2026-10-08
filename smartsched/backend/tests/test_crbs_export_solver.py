"""CSV export (CRBS columns, Turkish text), iCalendar feeds (bearer and token), and confirmed bookings as
solver blocks in ``build_solver_input`` (real Bahar term, week 3)."""

from __future__ import annotations

import csv
import io
from datetime import date

from app.core import db as dbmod
from app.models import ScheduleRun, Term
from app.services.solver_bridge import build_solver_input
from app.solver import model as sm

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)
NOTE = "Şube toplantısı – İç Hastalıkları; ölçme, değerlendirme"


async def test_csv_export_has_crbs_columns_and_turkish_text(env):  # noqa: F811
    _, teacher = await env.user("disa.aktar@uni.edu.tr", displayname="Gülşen Ağaoğlu", username="gulsen.agaoglu")
    b = (await env.book(teacher, "A101", MON, "P1", notes=NOTE)).json()
    cancelled = (await env.book(teacher, "A101", MON, "P2")).json()
    await env.client.post(f"/api/v1/bookings/{cancelled['id']}/cancel", json={}, headers=teacher)
    assert (await env.client.get("/api/v1/bookings/export.csv", headers=teacher)).status_code == 403
    # the imported rooms have no room group; CRBS's export leaves ungrouped rooms out (export_ungrouped_rooms)
    await env.client.put("/api/v1/org/settings", json={"export_ungrouped_rooms": True}, headers=env.admin)
    r = await env.client.get("/api/v1/bookings/export.csv", params={"term_id": env.term_id}, headers=env.planner)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="bookings-2026-BAHAR.csv"' in r.headers["content-disposition"]
    raw = r.content
    assert raw.startswith("﻿".encode())  # Excel opens UTF-8 with a BOM correctly
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert len(rows) == 1
    row = rows[0]
    assert row["Booking ID"] == str(b["id"]) and row["Type"] == "Single" and row["Status"] == "Booked"
    assert row["Date"] == "2026-02-16" and row["Weekday"] == "Monday" and row["Period"] == "P1"
    assert row["Start Time"] == "08:30" and row["End Time"] == "09:10" and row["Room"] == "A 101"
    assert row["Notes"] == NOTE and row["User"] == "Gülşen Ağaoğlu" and row["Username"] == "gulsen.agaoglu"
    assert row["Schedule"] == "Ders saatleri" and row["Session"]
    everything = await env.client.get(
        "/api/v1/bookings/export.csv", params={"include_cancelled": "true"}, headers=env.planner
    )
    statuses = [x["Status"] for x in csv.DictReader(io.StringIO(everything.content.decode("utf-8-sig")))]
    assert sorted(statuses) == ["Booked", "Cancelled"]


async def test_ics_feeds(env):  # noqa: F811
    tid, teacher = await env.user("takvim@uni.edu.tr", displayname="Çağrı Öztürk")
    await env.book(teacher, "A101", MON, "P1", notes=NOTE)
    r = await env.client.get("/api/v1/bookings/feed/user.ics", headers=teacher)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    text = r.text
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    unfolded = text.replace("\r\n ", "")
    assert "DTSTART;TZID=Europe/Istanbul:20260216T083000" in unfolded
    assert "DTEND;TZID=Europe/Istanbul:20260216T091000" in unfolded
    assert "SUMMARY:A 101 – P1" in unfolded and "LOCATION:A 101" in unfolded
    assert "Şube toplantısı – İç Hastalıkları\\; ölçme\\, değerlendirme" in unfolded  # RFC 5545 escaping
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))  # folded
    # calendar apps cannot send a bearer header: token links
    tok = (await env.client.post("/api/v1/bookings/feed/token", headers=teacher)).json()
    feed = await env.client.get(tok["user_feed"])
    assert feed.status_code == 200 and "BEGIN:VEVENT" in feed.text
    room = await env.client.get(f"/api/v1/ics/{tok['token']}/room/{env.rooms['A101']}.ics")
    assert room.status_code == 200 and "UID:booking-" in room.text
    assert (await env.client.get("/api/v1/ics/not-a-valid-token-at-all-xx/user.ics")).status_code == 404
    rotated = (await env.client.post("/api/v1/bookings/feed/token", headers=teacher)).json()
    assert (await env.client.get(tok["user_feed"])).status_code == 404 and rotated["token"] != tok["token"]


async def test_confirmed_bookings_are_solver_blocks(env):  # noqa: F811
    _, teacher = await env.user("cozucu@uni.edu.tr")
    kept = (await env.book(teacher, "A101", MON, "P1")).json()
    gone = (await env.book(teacher, "A101", MON, "P2")).json()
    await env.client.post(f"/api/v1/bookings/{gone['id']}/cancel", json={}, headers=teacher)
    later = (await env.book(teacher, "A101", date(2026, 3, 2), "P1")).json()  # week 5: outside the horizon
    assert kept["id"] and later["id"]
    async with dbmod.get_session_factory()() as s:
        term = await s.get(Term, env.term_id)
        run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="WEEK", horizon_params={"week": 3})
        s.add(run)
        await s.flush()
        inp, _ = await build_solver_input(s, run)
        await s.rollback()
    a101 = env.rooms["A101"]
    mine = [b for b in inp.blocks if b.room_id == a101 and b.day == 1 and b.week == 3]
    assert sm.Block(a101, 3, 1, 1, 1) in mine
    assert sm.Block(a101, 3, 1, 2, 2) not in inp.blocks  # cancelled bookings free the slot
    assert all(b.week in (3, None) for b in inp.blocks)
