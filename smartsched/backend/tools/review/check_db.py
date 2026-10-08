"""Level B independent checker: persisted Assignment rows of a run vs raw DB rows (no app code).
usage: check_db.py <tag>   (reads runs/<tag>.db and runs/<tag>.pkl for run_id only)"""
import json, pickle, sqlite3, sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
SP = Path(__file__).parent
tag = sys.argv[1]
blob = pickle.loads((SP / "runs" / f"{tag}.pkl").read_bytes())
rid = blob["run_id"]
c = sqlite3.connect(SP / "runs" / f"{tag}.db"); c.row_factory = sqlite3.Row
q = lambda s, *a: c.execute(s, a).fetchall()
run = q("select * from schedule_runs where id=?", rid)[0]
stats = json.loads(run["stats"]); exam = run["kind"] == "EXAM"
rooms = {r["id"]: r for r in q("select * from rooms")}
code = {i: r["code"] for i, r in rooms.items()}
members = {int(k): v for k, v in (stats.get("event_members") or {}).items()}
group_of = {}
for h, ms in members.items():
    for m in ms: group_of[m] = h
A = q("select * from assignments where run_id=? and archived=0", rid)
F = defaultdict(list)
def add(cls, rule, msg): F[cls].append((rule, msg))
if exam:
    reqs = {r["id"]: r for r in q("select * from exam_requests")}
    key = "exam_request_id"
else:
    reqs = {r["id"]: r for r in q("select m.*, s.enrolment, s.program_id, s.class_year, s.class_years, s.course_id, s.label slabel from meeting_requests m join sections s on s.id=m.section_id")}
    key = "meeting_request_id"
    instr = defaultdict(set)
    for r in q("select m.id mid, si.instructor_id iid from meeting_requests m join section_instructors si on si.section_id=m.section_id"):
        instr[r["mid"]].add(r["iid"])
courses = {r["id"]: r["display_code"] for r in q("select id, display_code from courses")}
def label(rq):
    if exam: return rq["course_code"]
    return f"{courses.get(rq['course_id'])} §{rq['slabel']}"
rows_by_req = defaultdict(list)
for a in A: rows_by_req[a[key]].append(a)
# --- per row: time / lock / weeks
for a in A:
    rq = reqs[a[key]]
    rms = json.loads(a["room_ids"]); wks = json.loads(a["weeks"] or "[]")
    if not wks: add("VIOLATION", "no_weeks", f"{label(rq)} row without weeks")
    if exam:
        if str(a["date"]) != str(rq["date"]):
            add("VIOLATION(member_time)" if a[key] in group_of else "VIOLATION", "exam_date", f"{label(rq)} req {rq['date']} P{rq['start_period']}-{rq['end_period']} -> {a['date']} P{a['start_period']}-{a['end_period']}")
        elif (a["start_period"], a["end_period"]) != (rq["start_period"], rq["end_period"]):
            add("VIOLATION(member_time)" if a[key] in group_of else "VIOLATION", "exam_time", f"{label(rq)} req P{rq['start_period']}-{rq['end_period']} -> P{a['start_period']}-{a['end_period']} (date {a['date']})")
    else:
        if rq["day"] and (a["day"], a["start_period"], a["end_period"]) != (rq["day"], rq["start_period"], rq["end_period"]):
            add("SPAN(merged)" if a[key] in group_of else "VIOLATION", "time", f"{label(rq)} req d{rq['day']} P{rq['start_period']}-{rq['end_period']} -> d{a['day']} P{a['start_period']}-{a['end_period']}")
        rw = set(json.loads(rq["weeks"] or "[]"))
        if rw and not set(wks) <= rw:
            add("VIOLATION", "weeks", f"{label(rq)} weeks {wks} not in requested {sorted(rw)}")
    defin = [int(x) for x in json.loads(rq["definitive_room_ids"] or "[]")]
    if rq["status"] == "LOCKED" and defin and set(rms) != set(defin):
        add("LOCK_MOVED", "locked_room", f"{label(rq)} definitive {[code.get(x) for x in defin]} -> {[code.get(x) for x in rms]} weeks {wks}")
# --- occupancy over ALL rooms (incl. outside pool) per (room, week, day, period)
occ = defaultdict(set)
for a in A:
    wks = json.loads(a["weeks"] or "[]")
    for r in json.loads(a["room_ids"]):
        for w in wks:
            for p in range(a["start_period"], a["end_period"] + 1):
                occ[(r, w, a["day"], p)].add(a[key])
seen = set()
for (r, w, d, p), ids in occ.items():
    heads = {group_of.get(i, i) for i in ids}
    if len(heads) > 1:
        k = (r, tuple(sorted(heads)))
        if k in seen: continue
        seen.add(k)
        pooled = bool(rooms[r]["is_bookable"]) if r in rooms else False
        if exam:
            tot = sum((reqs[i]["enrolment"] or 0) for i in ids)
            cap = rooms[r]["exam_capacity"] or 0
            # exam sharing: single-room exams only checkable here; split ones approximated (whole size)
            cls = "SHARED_EXAM_OK" if tot <= cap else "SHARED_EXAM_OVER"
            add(cls if pooled else "OUTSIDE_POOL_DOUBLE", "room", f"{code[r]} (pool={pooled}) w{w} d{d} P{p}: {sorted({label(reqs[i]) for i in ids})} total {tot} cap {cap}")
        else:
            add("VIOLATION" if pooled else "OUTSIDE_POOL_DOUBLE", "room_double_booking", f"{code[r]} (pool={pooled}) w{w} d{d} P{p}: {sorted({label(reqs[i]) for i in ids})}")
# --- blocks (raw rows: weeks list and/or date)
weeks_rows = q("select * from weeks where term_id=?", run["term_id"])
for b in q("select * from blocks where term_id=? and archived=0", run["term_id"]):
    bw = json.loads(b["weeks"] or "[]")
    day = b["day"]
    for w in (bw or [None]):
        for p in range(b["start_period"], b["end_period"] + 1):
            cand = [(k, v) for k, v in occ.items() if k[0] == b["room_id"] and k[2] == day and k[3] == p and (w is None or k[1] == w)] if False else None
            for wk in ([w] if w is not None else sorted({k[1] for k in occ})):
                ids = occ.get((b["room_id"], wk, day, p))
                if ids:
                    add("VIOLATION", "blocked", f"{code[b['room_id']]} w{wk} d{day} P{p} block '{b['label']}' vs {sorted({label(reqs[i]) for i in ids})}")
# --- capacity (strict, vs enrolment, per persisted row; merged groups summed)
seen_g = set()
for a in A:
    h = group_of.get(a[key], a[key])
    kk = (h, a["weeks"], a["room_ids"])
    if kk in seen_g: continue
    seen_g.add(kk)
    ids = members.get(h, [h])
    size = sum((reqs[i]["enrolment"] or 0) for i in ids) if exam else sum((reqs[i]["enrolment"] or reqs[i]["requested_capacity"] or 0) for i in ids)
    rms = [r for r in json.loads(a["room_ids"]) if r in rooms and rooms[r]["is_bookable"]]
    if not rms: continue
    cap = sum((rooms[r]["exam_capacity"] if exam else rooms[r]["capacity"]) or 0 for r in rms)
    locked = all(reqs[i]["status"] == "LOCKED" and set(int(x) for x in json.loads(reqs[i]["definitive_room_ids"] or "[]")) & set(rms) for i in ids)
    if cap < size:
        add("CAP_SHORT_LOCKED" if locked else "CAP_SHORT_UNLOCKED", "capacity", f"{' + '.join(sorted({label(reqs[i]) for i in ids}))} size {size} in {[code[r] for r in rms]} cap {cap} weeks {json.loads(a['weeks'])}")
# --- tags
for a in A:
    rq = reqs[a[key]]
    tags = set(json.loads(rq["requested_tags"] or "[]"))
    for r in json.loads(a["room_ids"]):
        if r not in rooms: continue
        rt = set(json.loads(rooms[r]["tags"] or "[]"))
        if "PC" in tags and "PC" not in rt:
            add("TAG_PC_MISSING", "tags", f"{label(rq)} wants PC, in {code[r]}")
        if "TIP" in rt and "TIP" not in tags:
            add("TIP_ROOM_UNREQUESTED", "tags", f"{label(rq)} in TIP room {code[r]} status {rq['status']} definitive {[code.get(int(x)) for x in json.loads(rq['definitive_room_ids'] or '[]')]}")
# --- cohort / instructor (courses)
if not exam:
    def ck(rq):
        ys = json.loads(rq["class_years"] or "[]") or [rq["class_year"]]
        return {(rq["program_id"], int(y)) for y in ys if y and rq["program_id"]}
    rows = [(a, reqs[a[key]]) for a in A]
    bykey = defaultdict(list)
    for a, rq in rows:
        for k in ck(rq): bykey[("C",) + k].append(a)
        for i in instr.get(rq["id"], ()): bykey[("I", i)].append(a)
    seenp = set()
    for k, lst in bykey.items():
        for a, b in combinations(lst, 2):
            ha, hb = group_of.get(a[key], a[key]), group_of.get(b[key], b[key])
            if ha == hb or a["day"] != b["day"] or a["start_period"] > b["end_period"] or b["start_period"] > a["end_period"]: continue
            if not set(json.loads(a["weeks"])) & set(json.loads(b["weeks"])): continue
            pk = (k[0], min(ha, hb), max(ha, hb))
            if pk in seenp: continue
            seenp.add(pk)
            ra, rb = reqs[a[key]], reqs[b[key]]
            fixed = bool(ra["day"]) and bool(rb["day"]) and (a["day"], a["start_period"]) == (ra["day"], ra["start_period"]) and (b["day"], b["start_period"]) == (rb["day"], rb["start_period"])
            add("CLASH_BOTH_FIXED" if fixed else "VIOLATION", "cohort" if k[0] == "C" else "instructor", f"{k}: {label(ra)} d{a['day']} P{a['start_period']}-{a['end_period']} vs {label(rb)} d{b['day']} P{b['start_period']}-{b['end_period']}")
# --- unplaced requests vs report
placed_req = set(rows_by_req)
diag = json.loads(run["diagnosis"] or "[]")
named = set()
for d in diag:
    if d.get("severity") == "error":
        for i in d.get("event_ids") or []:
            for m in members.get(i, [i]): named.add(m)
print(json.dumps({"tag": tag, "run": rid, "status": run["status"], "hard": run["hard_score"], "rows": len(A),
                  "counts": {k: len(v) for k, v in F.items()}}, ensure_ascii=False))
for cls in F:
    if cls in ("SHARED_EXAM_OK",): continue
    for rule, msg in F[cls][:12]:
        print(cls, rule, msg)
(SP / "runs" / f"{tag}.checkdb.json").write_text(json.dumps(F, ensure_ascii=False, indent=1, default=str))
