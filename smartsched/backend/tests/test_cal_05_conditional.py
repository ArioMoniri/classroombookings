"""CAL-05 cheap conditional GET on the real Bahar 2026 import: a version key (the link, its scope, the newest audit
event, the day) is checked before anything is built, so a second poll answers 304 with at most three queries;
any audited change (a move, a booking, a setting) flips the ETag; ``Last-Modified`` + ``If-Modified-Since`` work; a
feed above 1 MB is trimmed (tombstones first, then the farthest events); ``last_used_at`` is shown as "en son
çekti"."""

from __future__ import annotations

from datetime import date

import icalendar
import pytest
from app.core import db as dbmod
from app.services import calendar_feeds
from sqlalchemy import event

from tests.cal_support import link_instructor, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)


class Queries:
    def __init__(self) -> None:
        self.n = 0
        self.sql: list[str] = []

    def __call__(self, _conn, _cursor, statement, *_a, **_k) -> None:  # type: ignore[no-untyped-def]
        self.n += 1
        self.sql.append(" ".join(str(statement).split())[:120])


async def _ayse(env):  # type: ignore[no-untyped-def]  # noqa: F811
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    sub = (
        await env.client.post("/api/v1/calendar/subscriptions", json={"scope_kind": "my_classes"}, headers=ayse)
    ).json()
    return p, ayse, f"/api/v1/calendar/feeds/{sub['token']}/classes.ics"


async def test_cal_05_second_poll_is_304_with_three_queries_and_a_change_flips_the_etag(env):  # noqa: F811
    p, ayse, url = await _ayse(env)
    first = await env.client.get(url)
    assert first.status_code == 200 and first.headers["etag"] and first.headers["last-modified"]
    etag = first.headers["etag"]
    counter = Queries()
    engine = dbmod.get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", counter)
    try:
        again = await env.client.get(url, headers={"If-None-Match": etag})
    finally:
        event.remove(engine, "before_cursor_execute", counter)
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag
    assert counter.n <= 3, counter.sql
    # If-Modified-Since alone (clients without ETags)
    ims = await env.client.get(url, headers={"If-Modified-Since": first.headers["last-modified"]})
    assert ims.status_code == 304
    # an audited change (here a forced move of PSY 262 week 5, which the owner rule of 2026-10-17 turns into a draft
    # copy: audited, the published plan unchanged) moves the version key, so the feed is rebuilt; CAL10-F03
    # (fix-h-2026-10-18): the ETag is the body's hash, so it flips exactly when the body does
    r = await env.client.post(
        f"/api/v1/runs/{env.run_id}/assignments/{p.week5_assignment_id}/move",
        json={"day": 1, "start_period": 10, "end_period": 12, "force": True, "reason": "CAL-05 test"},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    changed = await env.client.get(url, headers={"If-None-Match": etag})
    body = (await env.client.get(url)).text
    if body == first.text:
        assert changed.status_code == 304 and changed.headers["etag"] == etag
    else:
        assert changed.status_code == 200 and changed.headers["etag"] != etag
    # "Takviminiz en son çekti" from last_used_at
    links = (await env.client.get("/api/v1/calendar/subscriptions", headers=ayse)).json()["links"]
    assert links[0]["last_fetched_tr"].startswith("Takviminiz en son çekti: ")
    assert links[0]["last_fetched_en"].startswith("Your calendar last fetched: ")


async def test_cal_05_a_feed_above_one_megabyte_is_trimmed(env, monkeypatch):  # noqa: F811
    p = await psy262(env)
    _, teacher = await env.user("bolum.baskani@uni.edu.tr", department_id=p.program_id)
    await calendar_consent(env.client, teacher)
    tok = (await env.client.post("/api/v1/calendar/feeds/tokens", json={}, headers=teacher)).json()["token"]
    url = f"/api/v1/calendar/feeds/{tok}/department/{p.program_id}.ics"
    full = await env.client.get(url)
    assert full.status_code == 200
    size = len(full.content)
    assert "STATUS:CANCELLED" in full.text  # the once-cancelled pre-0039 UIDs
    cap = size // 3
    monkeypatch.setattr(calendar_feeds, "FEED_MAX_BYTES", cap)
    await env.book(env.planner, "A101", date(2026, 2, 18), "P1", department_id=p.program_id)  # a new version
    trimmed = await env.client.get(url)
    assert trimmed.status_code == 200 and len(trimmed.content) <= cap
    cal = icalendar.Calendar.from_ical(trimmed.text)
    evs = list(cal.walk("VEVENT"))
    assert evs and not [e for e in evs if str(e["STATUS"]) == "CANCELLED"]
    # the nearest events stay, the farthest go
    first_full = min(e.decoded("DTSTART") for e in icalendar.Calendar.from_ical(full.text).walk("VEVENT"))
    assert min(e.decoded("DTSTART") for e in evs) == first_full
