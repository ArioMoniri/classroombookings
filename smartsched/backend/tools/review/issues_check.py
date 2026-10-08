"""Data-issues report vs an independent computation from raw request rows.  usage: issues_check.py <tag>"""
import asyncio, json, os, pickle, sqlite3, sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
os.environ.setdefault("APP_SECRET", "review-secret-review-secret-review-0000"); os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ADMIN_EMAIL", "a@example.com"); os.environ.setdefault("ADMIN_PASSWORD", "admin1234")
SP = Path(__file__).parent
tag = sys.argv[1]
blob = pickle.loads((SP / "runs" / f"{tag}.pkl").read_bytes())
rid = blob["run_id"]
async def report():
    from app.core import db as dbmod
    from app.services.data_issues import build_data_issues
    from app.models import ScheduleRun
    dbmod.configure_engine(f"sqlite+aiosqlite:///{SP / 'runs' / (tag + '.db')}")
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, rid)
        rep = await build_data_issues(s, run)
    await dbmod.dispose_engine()
    return rep
rep = asyncio.run(report())
print("report totals:", rep["totals"]["by_group"])
G = {g["code"]: g for g in rep["groups"]}
c = sqlite3.connect(SP / "runs" / f"{tag}.db"); c.row_factory = sqlite3.Row
run = c.execute("select * from schedule_runs where id=?", (rid,)).fetchone()
hp = json.loads(run["horizon_params"] or "{}"); weeks = set(hp.get("weeks") or range(1, 15))
pool = {r["id"]: r for r in c.execute("select * from rooms where is_bookable=1")}
allrooms = {r["id"]: r["code"] for r in c.execute("select id, code from rooms")}
reqs = [r for r in c.execute("""select m.*, co.display_code code, s.label sl, s.enrolment from meeting_requests m join sections s on s.id=m.section_id
          join courses co on co.id=s.course_id where m.archived=0 and m.needs_room=1 and m.status='LOCKED' and m.day is not null and m.start_period is not null""")]
def W(r):
    w = set(json.loads(r["weeks"] or "[]")) or set(range(1, 15)); return w & weeks
# (1) locked overlaps in pooled rooms, raw rows (same room, day, overlapping periods, shared weeks), excluding same course+start (one lecture listed twice)
ov_pool, ov_out = set(), set()
by = defaultdict(list)
for r in reqs:
    for x in json.loads(r["definitive_room_ids"] or "[]"):
        by[(int(x), r["day"])].append(r)
for (room, day), lst in by.items():
    for a, b in combinations(lst, 2):
        if a["start_period"] <= b["end_period"] and b["start_period"] <= a["end_period"] and W(a) & W(b):
            same = a["code"] == b["code"] or a["start_period"] == b["start_period"]
            if same: continue
            (ov_pool if room in pool else ov_out).add((allrooms[room], a["code"], b["code"]))
rep_ov = G["locked_room_overlap"]["count"]
print(f"(1) raw LOCKED overlaps pooled rooms (different course & start): {len(ov_pool)}; outside pool: {len(ov_out)}; report locked_room_overlap items: {rep_ov}")
print("    outside-pool overlaps (not reported as overlaps):", sorted(ov_out)[:8])
# (2) capacity: per LOCKED request, own enrolment vs own definitive pooled rooms
small = [(r["code"], r["sl"], r["enrolment"], [allrooms[int(x)] for x in json.loads(r["definitive_room_ids"])]) for r in reqs
         if W(r) and r["enrolment"] and sum((pool[int(x)]["capacity"] or 0) for x in json.loads(r["definitive_room_ids"]) if int(x) in pool) not in (0,) and
         r["enrolment"] > sum((pool[int(x)]["capacity"] or 0) for x in json.loads(r["definitive_room_ids"]) if int(x) in pool)]
cap_items = G["locked_room_too_small"]
listed = {rq for it in cap_items["items"] for rq in it["request_ids"]}
ids_small = [r["id"] for r in reqs if (r["code"], r["sl"], r["enrolment"], [allrooms[int(x)] for x in json.loads(r["definitive_room_ids"])]) in small]
print(f"(2) raw LOCKED requests with enrolment > own definitive seats: {len(small)}; report 'too small' items {cap_items['count']} covering {len(listed)} requests; raw cases not listed: {len(set(ids_small) - listed)}")
# merged groups whose combined enrolment exceeds the room (bridge artefact)
st = json.loads(run["stats"]); mem = st.get("event_members") or {}
enr = {r["id"]: r["enrolment"] or 0 for r in c.execute("select m.id, s.enrolment from meeting_requests m join sections s on s.id=m.section_id")}
asg = defaultdict(list)
for a in c.execute("select * from assignments where run_id=?", (rid,)):
    asg[a["meeting_request_id"]].append(a)
over = []
for h, ms in mem.items():
    a = asg.get(int(h))
    if not a: continue
    seats = sum((pool[r]["capacity"] or 0) for r in json.loads(a[0]["room_ids"]) if r in pool)
    tot = sum(enr.get(m, 0) for m in ms)
    if seats and tot > seats:
        over.append((h, tot, seats, any(int(m) in listed for m in ms)))
print(f"    merged events seated over capacity (sum of enrolments > seats): {len(over)}; of these listed in the report: {sum(1 for o in over if o[3])}")
print("    examples not listed:", [o for o in over if not o[3]][:6])
