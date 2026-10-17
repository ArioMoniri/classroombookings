from collections import Counter
import json
from tests.api_fixtures import login, client  # noqa: F401
from tests.council.conftest import BAHAR_LIST, EN_CSV
from tests.council.test_formats_api import upload
from tests.council.test_reupload import _ui_body


async def test_dbg(client):
    from app.core.db import get_session_factory
    from app.models import Course, MeetingRequest, Section
    from sqlalchemy import select
    h = await login(client)
    r = await client.post("/api/v1/terms", headers=h, json={"code": "2026-BAHAR", "name": "2026 Bahar", "is_active": True, "week_count": 19})
    tid = r.json()["id"]
    j1 = await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), ai="false")
    await client.post(f"/api/v1/council/jobs/{j1['id']}/commit", headers=h, json=_ui_body(j1))
    j2 = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false")
    dry = (await client.post(f"/api/v1/council/jobs/{j2['id']}/commit", headers=h, json={"group": 0, "term_id": tid, "allow_pending": True, "dry_run": True})).json()
    ups = [x for x in dry["rows"] if x["entity"] == "meeting_requests" and x["change"] == "update"]
    print("DBG_FIELDS", Counter(f["field"] for x in ups for f in x["fields"]))
    print("DBG_SAMPLE", json.dumps(ups[:5], ensure_ascii=False, default=str)[:2500])
    arch = [x for x in ups if any(f["field"] == "archived" for f in x["fields"])]
    async with get_session_factory()() as s:
        for x in arch[:8]:
            mr = await s.get(MeetingRequest, x["id"]); sec = await s.get(Section, mr.section_id); co = await s.get(Course, sec.course_id)
            sib = (await s.execute(select(MeetingRequest).where(MeetingRequest.section_id == sec.id))).scalars().all()
            print("DBG_ARCH", co.code, sec.source_key, mr.days, str(mr.start_time), mr.source_key[-8:], mr.source_row_index, "| sibs", [(m.days, str(m.start_time), m.source_key[-4:]) for m in sib])
