"""Reconciler: merge the records of all files into one dataset, deduplicate, resolve names.

* **Rooms** merge on a punctuation-free key (``A 101`` = ``A101`` = ``a-101``). Capacities come first
  from room lists, then from timetable headers, then from planning-list summaries. A disagreement
  between two room lists is a *conflict*.
* **Near duplicates** (``B207`` vs ``B2O7``, ``Ayşe Yılmaz`` vs ``Ayse Yilmaz Dr``) are never merged
  silently. They become ``merge`` review items with a similarity score.
* **Meetings and exams** that appear in two files with the same key (course, section, programme,
  days, time / date) are deduplicated. The later copy is marked ``duplicate_of`` and is not committed
  twice.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from typing import Any

from app.council import text as tx
from app.importers import normalize as n

Record = dict[str, Any]
MERGE_SUGGEST = 0.9
MAX_MERGES = 60

#: a capacity from this record type/source outranks the ones after it
_CAP_RANK = {"room_list": 0, "room-master": 0, "booking": 1, "planning": 2}


def room_key(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", n.tr_upper(code or "")).replace("İ", "I")


def rid(file_index: int, i: int) -> str:
    return f"{file_index}:{i}"


def _meeting_key(r: Record) -> tuple[Any, ...]:
    return (
        r["course_code"],
        tx.fold(r.get("section") or ""),
        tx.fold(r.get("program") or ""),
        tuple(r.get("days") or ()),
        r.get("start"),
        r.get("end"),
    )


def _exam_key(r: Record) -> tuple[Any, ...]:
    return (r["course_code"], tx.fold(r.get("program") or ""), r.get("date"), r.get("start"))


def reconcile(files: list[tuple[int, str, list[Record]]]) -> dict[str, Any]:
    """``files`` = [(file_index, filename, records)] -> dataset summary + duplicates + merges + conflicts."""
    rooms: dict[str, dict[str, Any]] = {}
    cap_sources: dict[str, list[tuple[int, int, dict[str, Any]]]] = defaultdict(list)
    conflicts: list[dict[str, Any]] = []
    duplicates: dict[str, str] = {}
    seen_meet: dict[tuple[Any, ...], str] = {}
    seen_exam: dict[tuple[Any, ...], str] = {}
    courses: dict[str, Counter[str]] = defaultdict(Counter)
    course_count: Counter[str] = Counter()
    people: dict[str, Counter[str]] = defaultdict(Counter)
    programs: dict[str, Counter[str]] = defaultdict(Counter)
    counts: Counter[str] = Counter()

    def add_room(code: str, label: str | None, cap: int | None, exam_cap: int | None, rank: int, rec: Record) -> None:
        k = room_key(code)
        if not k:
            return
        room = rooms.setdefault(
            k,
            {
                "code": code,
                "label": label or code,
                "capacity": None,
                "exam_capacity": None,
                "tags": [],
                "building": None,
                "floor": None,
                "bookable": None,
                "notes": None,
                "sources": [],
                "_rank": 99,
                "_exam_rank": 99,
            },
        )
        if len(room["sources"]) < 5:
            room["sources"].append(rec["source"])
        if cap:
            cap_sources[k].append((rank, cap, rec["source"]))
            if rank < room["_rank"]:
                room["capacity"], room["_rank"] = cap, rank
        if exam_cap and rank < room["_exam_rank"]:
            room["exam_capacity"], room["_exam_rank"] = exam_cap, rank
        for t in rec.get("tags") or rec.get("room_tags") or []:
            if t not in room["tags"]:
                room["tags"].append(t)
        for f in ("building", "floor", "bookable", "notes"):
            if rec.get(f) is not None and room[f] is None:
                room[f] = rec[f]

    for fi, _name, records in files:
        for i, r in enumerate(records):
            t = r["type"]
            counts[t] += 1
            if t == "room":
                rank = _CAP_RANK["room_list"] if r["source"].get("sheet") != "Sayfa2" else _CAP_RANK["planning"]
                add_room(r["code"], r.get("label"), r.get("capacity"), r.get("exam_capacity"), rank, r)
            elif t == "booking":
                add_room(r["room_code"], r.get("room_label"), r.get("room_capacity"), None, _CAP_RANK["booking"], r)
            elif t == "meeting":
                k = _meeting_key(r)
                if k in seen_meet and seen_meet[k].split(":")[0] != str(fi):
                    duplicates[rid(fi, i)] = seen_meet[k]
                else:
                    seen_meet.setdefault(k, rid(fi, i))
            elif t == "exam":
                k = _exam_key(r)
                if k in seen_exam and seen_exam[k].split(":")[0] != str(fi):
                    duplicates[rid(fi, i)] = seen_exam[k]
                else:
                    seen_exam.setdefault(k, rid(fi, i))
            if t in ("meeting", "exam"):
                course_count[r["course_code"]] += 1
                if r.get("course_name"):
                    courses[r["course_code"]][r["course_name"]] += 1
                for name in r.get("instructors") or ([r["instructor"]] if r.get("instructor") else []):
                    key = tx.person_key(name)
                    if key:
                        people[key][name] += 1
                prog = n.canon_program(r.get("program"))
                if prog is not None:
                    programs[prog.canonical][prog.name] += 1
            if t == "staff" and r.get("key"):
                people[r["key"]][r["name"]] += 1

    # capacity conflicts: two room lists disagree (headers that differ from a room list are expected)
    for rk, caps in cap_sources.items():
        listed = {c for rank, c, _ in caps if rank == 0}
        if len(listed) > 1:
            conflicts.append(
                {
                    "kind": "room_capacity",
                    "room": rooms[rk]["code"],
                    "values": sorted(listed),
                    "chosen": rooms[rk]["capacity"],
                    "sources": [s for rank, _, s in caps if rank == 0][:4],
                }
            )

    merges: list[dict[str, Any]] = []
    keys = sorted(rooms)
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            if a[:1] != b[:1] or re.sub(r"\D", "", a) != re.sub(r"\D", "", b):
                continue
            ratio = difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= MERGE_SUGGEST:
                merges.append({"kind": "room", "a": rooms[a]["code"], "b": rooms[b]["code"], "score": round(ratio, 3)})
    pkeys = sorted(people)
    by_initial: dict[str, list[str]] = defaultdict(list)
    for pk in pkeys:
        by_initial[pk[:2]].append(pk)
    for group in by_initial.values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                ratio = difflib.SequenceMatcher(None, a, b).ratio()
                if MERGE_SUGGEST <= ratio < 1.0:
                    merges.append(
                        {
                            "kind": "instructor",
                            "a": people[a].most_common(1)[0][0],
                            "b": people[b].most_common(1)[0][0],
                            "score": round(ratio, 3),
                        }
                    )
    merges.sort(key=lambda m: -m["score"])

    room_list = []
    for rkey in keys:
        room = {kk: v for kk, v in rooms[rkey].items() if not kk.startswith("_")}
        room["key"] = rkey
        room_list.append(room)
    return {
        "counts": dict(counts),
        "rooms": room_list,
        "courses": [
            {"code": c, "name": (courses[c].most_common(1)[0][0] if courses[c] else None), "records": course_count[c]}
            for c in sorted(course_count)
        ],
        "instructors": [{"key": k, "name": people[k].most_common(1)[0][0]} for k in pkeys],
        "programs": [{"canonical": k, "name": v.most_common(1)[0][0]} for k, v in sorted(programs.items())],
        "duplicates": duplicates,
        "merges": merges[:MAX_MERGES],
        "conflicts": conflicts,
    }


__all__ = ["reconcile", "rid", "room_key"]
