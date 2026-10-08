"""Commit: write the reviewed records and accepted rule proposals into a term.

Fast-path files are written by the university importers themselves (``import_room_master``,
``import_weekly_grid``, ``import_planning_list``, ``import_exam_list``, in that order), so they get every
rule the university path has. General-path files are written here:

* rooms (canonical code ``A101``; an existing room keeps its capacity, and a room-master value is never
  overwritten);
* courses, programmes, faculties and instructors (the importers' :class:`~app.importers.catalog.Catalog`,
  which normalises names);
* sections and meeting requests: times mapped onto the term's period grid (``terms.periods_json``, set
  from the planner when empty), assigned rooms as definitive rooms (status ``LOCKED``);
* exam requests;
* timetable entries that are not course codes ("HAZIRLIK", "Staff meeting") as blocks. Course entries
  of a timetable are reported as *observed* and are not imported as bookings, because the requests
  come from the request lists;
* weeks from the planner; staff as instructors.

Every written row carries ``source_key = CC:<job>:<file>:<record>`` so a re-commit updates instead of
duplicating. Rule proposals the reviewer accepted are resolved against the new term
(:func:`app.ai.resolve.resolve_proposal`) and saved with :func:`app.ai.elicit.accept_proposals`
(source ``UPLOAD``, file reference in ``source_ref``).
"""

from __future__ import annotations

from collections import Counter
from datetime import date, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.council import critic, fastpath, storage
from app.council import text as tx
from app.council.reconcile import rid, room_key
from app.council.review import build_items, decisions, effective_plan
from app.importers.catalog import Catalog
from app.importers.report import ImportReport
from app.models import (
    Block,
    Building,
    CouncilJob,
    ExamRequest,
    MeetingRequest,
    Room,
    Section,
    SectionInstructor,
    Term,
    Week,
)
from app.models.base import utcnow

SECTION_MODES = {"F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"}


class CommitError(ValueError):
    """Commit refused (HTTP 409 at the API): pending blocking review items, unknown group/term."""


def _t(s: str | None) -> time | None:
    return tx.from_hhmm(s)


async def _term(session: AsyncSession, spec: dict[str, Any]) -> tuple[Term, bool]:
    code = str(spec.get("code") or "").strip()[:32]
    if not code:
        raise CommitError("a term code is needed (term.code or a planner group)")
    term = (await session.execute(select(Term).where(Term.code == code))).scalar_one_or_none()
    created = False
    if term is None:
        start = spec.get("start_date")
        term = Term(
            code=code,
            name=str(spec.get("name") or code)[:128],
            kind=str(spec.get("kind") or "REGULAR")[:16],
            week_count=int(spec.get("week_count") or 14),
            start_date=date.fromisoformat(start) if start else None,
        )
        session.add(term)
        await session.flush()
        created = True
    return term, created


class Writer:
    def __init__(self, session: AsyncSession, term: Term, job_id: int, periods: list[dict[str, Any]]) -> None:
        self.s = session
        self.term = term
        self.job_id = job_id
        self.periods = periods
        self.report = ImportReport(kind="council", term_code=term.code)
        self.cat = Catalog(session, self.report)
        self.rooms: dict[str, Room] = {}
        self.counts: Counter[str] = Counter()
        self.notes: list[str] = []
        #: accepted reconciler merges: the second spelling is written as the first
        self.room_alias: dict[str, str] = {}
        self.person_alias: dict[str, str] = {}

    def key(self, fi: int, i: int) -> str:
        return f"CC:{self.job_id}:{fi}:{i}"

    async def room(self, rec: dict[str, Any]) -> Room | None:
        k = rec.get("key") or room_key(rec.get("code") or "")
        k = self.room_alias.get(k, k)
        if not k:
            return None
        if k in self.rooms:
            return self.rooms[k]
        room = (await self.s.execute(select(Room).where(Room.code == k))).scalar_one_or_none()
        if room is None:
            building_id = None
            if rec.get("building"):
                bcode = str(rec["building"]).strip().upper()[:16]
                b = (await self.s.execute(select(Building).where(Building.code == bcode))).scalar_one_or_none()
                if b is None:
                    b = Building(code=bcode, name=str(rec["building"])[:128])
                    self.s.add(b)
                    await self.s.flush()
                building_id = b.id
            cap = int(rec.get("capacity") or 0)
            room = Room(
                code=k,
                display_name=str(rec.get("label") or rec.get("code") or k).splitlines()[0][:64],
                building_id=building_id,
                floor=(str(rec["floor"])[:8] if rec.get("floor") else None),
                capacity=cap,
                exam_capacity=int(rec.get("exam_capacity") or 0),
                tags=list(rec.get("tags") or []),
                is_bookable=bool(cap or rec.get("exam_capacity"))
                if rec.get("bookable") is None
                else bool(rec["bookable"]),
                notes=rec.get("notes"),
                custom_fields={"sources": {"council": f"job {self.job_id}"}},
            )
            self.s.add(room)
            await self.s.flush()
            self.counts["rooms_created"] += 1
        else:
            fields = dict(room.custom_fields or {})
            master = set(fields.get("master") or [])
            for attr in ("capacity", "exam_capacity"):
                v = rec.get(attr)
                if v and not getattr(room, attr) and attr not in master:
                    setattr(room, attr, int(v))
                    self.counts["rooms_updated"] += 1
                elif v and getattr(room, attr) and int(v) != getattr(room, attr):
                    self.notes.append(f"room {k}: file says {attr} {v}, kept {getattr(room, attr)}")
            for t in rec.get("tags") or []:
                if t not in room.tags:
                    room.tags = [*room.tags, t]
        self.rooms[k] = room
        return room

    async def room_ids(self, codes: list[str]) -> list[int]:
        ids = []
        for c in codes:
            k = room_key(c)
            k = self.room_alias.get(k, k)
            room = self.rooms.get(k) or (await self.s.execute(select(Room).where(Room.code == k))).scalar_one_or_none()
            if room is not None:
                self.rooms[k] = room
                ids.append(room.id)
        return ids

    def periods_of(self, start: str | None, end: str | None) -> tuple[int | None, int | None]:
        return critic.period_index(self.periods, start, "start"), critic.period_index(self.periods, end, "end")

    async def meeting(self, fi: int, i: int, r: dict[str, Any]) -> None:
        faculty = await self.cat.faculty(r.get("faculty"))
        program = await self.cat.program(r.get("program"), faculty)
        course = await self.cat.course(r["course_code"], name=r.get("course_name"))
        skey = f"{r['course_code']}|{program.canonical_name if program else ''}|{r.get('section') or ''}"
        section = (
            await self.s.execute(select(Section).where(Section.term_id == self.term.id, Section.source_key == skey))
        ).scalar_one_or_none()
        mode = r.get("mode") if r.get("mode") in SECTION_MODES else "F2F"
        years = r.get("class_years") or []
        if section is None:
            section = Section(
                term_id=self.term.id,
                course_id=course.id,
                program_id=program.id if program else None,
                label=r.get("section"),
                class_year=years[0] if years else None,
                class_years=years,
                enrolment=r.get("enrolment"),
                mode=mode,
                notes=r.get("notes"),
                source_row=r["source"],
                source_key=skey,
            )
            self.s.add(section)
            await self.s.flush()
            self.counts["sections"] += 1
        for idx, raw_name in enumerate(r.get("instructors") or []):
            name = self.person_alias.get(tx.person_key(raw_name), raw_name)
            ins = await self.cat.instructor(name)
            if ins is not None and await self.s.get(SectionInstructor, (section.id, ins.id)) is None:
                self.s.add(
                    SectionInstructor(
                        section_id=section.id, instructor_id=ins.id, role="PRIMARY" if idx == 0 else "SECONDARY"
                    )
                )
        sp, ep = self.periods_of(r.get("start"), r.get("end"))
        definitive = await self.room_ids(r.get("rooms") or [])
        warnings = list(r.get("warnings") or [])
        if r.get("start") and sp is None:
            warnings.append(f"start {r['start']} is outside the term's period grid")
        status = (
            "LOCKED"
            if definitive
            else ("NEEDS_REVIEW" if warnings or (r.get("needs_room") and sp is None) else "PARSED")
        )
        days = r.get("days") or []
        fields = dict(
            section_id=section.id,
            day=days[0] if len(days) == 1 else None,
            days=days,
            start_period=sp,
            end_period=ep,
            start_time=_t(r.get("start")),
            end_time=_t(r.get("end")),
            weeks=r.get("weeks") or [],
            requested_room_text=r.get("room_request"),
            requested_room_ids=await self.room_ids(tx.room_tokens(r.get("room_request"))),
            requested_capacity=r.get("enrolment"),
            flexible_day=bool(r.get("flexible_day")),
            needs_room=bool(r.get("needs_room", True)),
            definitive_room_text=r.get("room_text"),
            definitive_room_ids=definitive,
            status=status,
            parse_warnings=warnings,
            notes=r.get("notes"),
            source_key=self.key(fi, i),
            source_row_index=r["source"].get("row"),
            archived=False,
        )
        mr = (
            await self.s.execute(select(MeetingRequest).where(MeetingRequest.source_key == fields["source_key"]))
        ).scalar_one_or_none()
        if mr is None:
            self.s.add(MeetingRequest(**fields))
            self.counts["meeting_requests"] += 1
        else:
            for k, v in fields.items():
                setattr(mr, k, v)
            self.counts["meeting_requests_updated"] += 1

    async def exam(self, fi: int, i: int, r: dict[str, Any]) -> None:
        faculty = await self.cat.faculty(r.get("faculty"))
        program = await self.cat.program(r.get("program"), faculty)
        await self.cat.course(r["course_code"], name=r.get("course_name"))
        sp, ep = self.periods_of(r.get("start"), r.get("end"))
        definitive = await self.room_ids(r.get("rooms") or [])
        years = r.get("class_years") or []
        fields = dict(
            term_id=self.term.id,
            course_code=r["course_code"],
            course_name=r.get("course_name"),
            program_id=program.id if program else None,
            faculty_text=r.get("faculty"),
            class_year=years[0] if years else None,
            class_years=years,
            enrolment=r.get("enrolment"),
            instructor_text=r.get("instructor"),
            date=date.fromisoformat(r["date"]) if r.get("date") else None,
            start_time=_t(r.get("start")),
            end_time=_t(r.get("end")),
            start_period=sp,
            end_period=ep,
            requested_venue_text=r.get("venue_text"),
            definitive_room_text=r.get("room_text"),
            definitive_room_ids=definitive,
            needs_room=bool(r.get("needs_room", True)),
            merge_key=f"{r['course_code']}:{r.get('date')}:{r.get('start')}"
            if r.get("date") and r.get("start")
            else None,
            status="LOCKED" if definitive else ("NEEDS_REVIEW" if r.get("warnings") else "PARSED"),
            parse_warnings=r.get("warnings") or [],
            source_row=r["source"],
            source_key=self.key(fi, i),
            source_row_index=r["source"].get("row"),
            archived=False,
        )
        ex = (
            await self.s.execute(select(ExamRequest).where(ExamRequest.source_key == fields["source_key"]))
        ).scalar_one_or_none()
        if ex is None:
            self.s.add(ExamRequest(**fields))
            self.counts["exam_requests"] += 1
        else:
            for k, v in fields.items():
                setattr(ex, k, v)
            self.counts["exam_requests_updated"] += 1

    async def booking(self, fi: int, i: int, r: dict[str, Any], week_of: dict[str, int]) -> None:
        if r.get("course_codes"):
            self.counts["timetable_course_entries_observed"] += 1
            return
        room = await self.room(
            {
                "code": r["room_code"],
                "label": r.get("room_label"),
                "capacity": r.get("room_capacity"),
                "tags": r.get("room_tags"),
            }
        )
        if room is None or not r.get("day"):
            self.counts["timetable_entries_skipped"] += 1
            return
        sp, ep = self.periods_of(r.get("start"), r.get("end"))
        if sp is None or ep is None:
            self.counts["timetable_entries_skipped"] += 1
            return
        week = week_of.get(r.get("sheet") or "")
        fields = dict(
            term_id=self.term.id,
            room_id=room.id,
            day=r["day"],
            date=date.fromisoformat(r["date"]) if r.get("date") else None,
            start_period=sp,
            end_period=ep,
            weeks=[week] if week else [],
            label=str(r["text"])[:255],
            tags=[],
            notes=f"from {r['source'].get('file')} {r['source'].get('cell', '')}".strip(),
            source="COUNCIL",
            source_key=self.key(fi, i),
            archived=False,
        )
        b = (await self.s.execute(select(Block).where(Block.source_key == fields["source_key"]))).scalar_one_or_none()
        if b is None:
            self.s.add(Block(**fields))
            self.counts["blocks"] += 1
        else:
            for k, v in fields.items():
                setattr(b, k, v)

    async def weeks(self, group: dict[str, Any]) -> dict[str, int]:
        existing = {
            w.index: w for w in (await self.s.execute(select(Week).where(Week.term_id == self.term.id))).scalars()
        }
        out: dict[str, int] = {}
        for w in group.get("weeks", []):
            idx = int(w["index"])
            if w.get("label"):
                out[w["label"]] = idx
            if idx in existing:
                continue
            self.s.add(
                Week(
                    term_id=self.term.id,
                    index=idx,
                    start_date=date.fromisoformat(w["start_date"]) if w.get("start_date") else None,
                    kind=w.get("kind") or "LECTURE",
                    label=(w.get("label") or None),
                )
            )
            self.counts["weeks"] += 1
        return out


async def commit(
    session: AsyncSession,
    job: CouncilJob,
    *,
    group: int | None = None,
    term_id: int | None = None,
    term_spec: dict[str, Any] | None = None,
    files: list[int] | None = None,
    include_rules: bool = True,
    allow_pending: bool = False,
    user_id: int | None = None,
) -> dict[str, Any]:
    if job.status not in ("REVIEW", "READY", "COMMITTED"):
        raise CommitError(f"job is {job.status}; wait until the council has finished")
    decided = await decisions(session, job.id)
    plan = effective_plan(job.plan or {}, decided)
    groups = plan.get("groups", [])
    g: dict[str, Any] = {}
    if group is not None:
        if not 0 <= group < len(groups):
            raise CommitError(f"no planner group {group}")
        g = groups[group]
    elif not files and len(groups) == 1:
        g = groups[0]
    chosen = sorted(set(files if files else g.get("files", [])) | set(plan.get("global_files", [])))
    known = {f["index"] for f in job.files}
    if not chosen or any(i not in known for i in chosen):
        raise CommitError("choose a planner group or a list of valid file indexes")
    items = await build_items(session, job)
    pending = [
        it for it in items if it["blocking"] and it["decision"] is None and it.get("file_index") in (None, *chosen)
    ]
    if pending and not allow_pending:
        raise CommitError(f"{len(pending)} review item(s) must be decided first (e.g. {pending[0]['title']})")

    if term_id is not None:
        term = await session.get(Term, term_id)
        if term is None:
            raise CommitError(f"term {term_id} not found")
        term_created = False
    else:
        term, term_created = await _term(session, {**g, **(term_spec or {})})
    periods = plan.get("period_grid", {}).get("periods") or []
    if term.periods_json:
        periods = [
            p if isinstance(p, dict) else {"index": i + 1, "start": p[0], "end": p[1]}
            for i, p in enumerate(term.periods_json)
        ]
    elif periods:
        term.periods_json = periods
    await session.commit()
    term_code, tid = term.code, term.id

    year = int(g.get("year") or job.year_hint or utcnow().year)
    reports: list[dict[str, Any]] = []
    records = await storage.records_by_file(session, job)
    routes = {f["index"]: f.get("route") or "" for f in job.files}
    fast = sorted(
        (i for i in chosen if routes[i].startswith("fast:")), key=lambda i: fastpath.COMMIT_ORDER.get(routes[i][5:], 9)
    )
    entries = {f["index"]: f for f in job.files}
    for i in fast:
        shape = routes[i][5:]
        path = storage.file_path(job.id, entries[i])
        name = entries[i]["filename"]
        if shape == "room-master":
            from app.importers.room_master import import_room_master

            rep = await import_room_master(session, path, filename=name)
        elif shape == "weekly-grid":
            from app.importers.weekly_grid import import_weekly_grid

            rep = await import_weekly_grid(session, path, term_code, year=year, filename=name)
        elif shape == "planning-list":
            from app.importers.planning_list import import_planning_list

            rep = await import_planning_list(
                session, path, term_code, filename=name, week_count=int(g.get("week_count") or 14)
            )
        else:
            from app.importers.exam_list import import_exam_list

            rep = await import_exam_list(session, path, term_code, filename=name)
        d = rep.to_dict()
        reports.append(
            {
                "file": i,
                "filename": name,
                "route": routes[i],
                "created": d["created"],
                "updated": d["updated"],
                "rows_imported": d["rows_imported"],
                "warnings_count": d["warnings_count"],
            }
        )

    term = await session.get(Term, tid)
    assert term is not None
    writer = Writer(session, term, job.id, periods)
    dataset_art = await storage.latest(session, job.id, "dataset")
    dataset = dataset_art.payload if dataset_art is not None else {}
    for m in dataset.get("merges", []):
        md = decided.get(f"merge:{m['kind']}:{m['a']}|{m['b']}")
        if not md or md.get("action") != "accept":
            continue
        if m["kind"] == "room":
            writer.room_alias[room_key(m["b"])] = room_key(m["a"])
        else:
            writer.person_alias[tx.person_key(m["b"])] = m["a"]
        writer.counts["merges_applied"] += 1
    duplicates = dataset.get("duplicates", {})
    general = [i for i in chosen if not routes[i].startswith("fast:")]
    week_of = await writer.weeks(g) if g else {}
    if general:
        file_rooms = {
            room_key(r.get("code") or r.get("room_code") or "")
            for i in general
            for r in records.get(i, [])
            if r["type"] in ("room", "booking")
        }
        for room in dataset.get("rooms", []):
            if room["key"] in file_rooms:
                await writer.room(room)
        for i in general:
            for n, r in enumerate(records.get(i, [])):
                if rid(i, n) in duplicates:
                    writer.counts["duplicates_skipped"] += 1
                    continue
                if r["type"] == "meeting":
                    await writer.meeting(i, n, r)
                elif r["type"] == "exam":
                    await writer.exam(i, n, r)
                elif r["type"] == "booking":
                    await writer.booking(i, n, r, week_of)
                elif r["type"] == "staff":
                    ins = await writer.cat.instructor(r["name"])
                    if ins is not None and r.get("email") and not ins.email:
                        ins.email = r["email"]
                    writer.counts["instructors"] += 1 if ins is not None else 0
                elif r["type"] == "calendar":
                    writer.counts["calendar_entries_reported"] += 1
        await writer.cat.finalize_rooms(lecture_side=True)
        await session.commit()

    created_rules: list[int] = []
    rejected_rules: list[dict[str, Any]] = []
    if include_rules:
        from app.ai.elicit import accept_proposals
        from app.ai.resolve import load_term_context, resolve_proposal

        accepted: list[Any] = []
        ctx = None
        for i in chosen:
            art = await storage.latest(session, job.id, "rules", i)
            if art is None:
                continue
            for n, raw in enumerate(art.payload.get("proposals", [])):
                rd = decided.get(f"rule:{i}:{n}")
                if not rd or rd.get("action") == "reject":
                    continue
                if ctx is None:
                    ctx = await load_term_context(session, tid)
                clean = {k: v for k, v in raw.items() if not k.startswith("_")}
                p = resolve_proposal(ctx, clean)
                if rd.get("action") == "edit" and rd.get("value"):
                    if rd["value"].get("hardness") in ("hard", "soft"):
                        p.hardness = rd["value"]["hardness"]
                    if rd["value"].get("weight"):
                        p.weight = int(rd["value"]["weight"])
                src = raw.get("_source") or {}
                p.source, p.source_ref = (
                    "UPLOAD",
                    {**src, "excerpt": (raw.get("_text") or "")[:200], "council_job": job.id},
                )
                accepted.append(p)
        if accepted:
            created_rules, rejected_rules = await accept_proposals(
                session, tid, accepted, user_id=user_id, source="UPLOAD"
            )
    result = {
        "term_id": tid,
        "term_code": term_code,
        "term_created": term_created,
        "files": chosen,
        "fast_path": reports,
        "general": dict(writer.counts),
        "notes": writer.notes[:50] + writer.report.warnings[:50],
        "constraints_created": created_rules,
        "constraints_rejected": rejected_rules,
        "at": utcnow().isoformat(),
        "by": user_id,
    }
    fresh = await session.get(CouncilJob, job.id)
    job = fresh if fresh is not None else job
    job.commits = [*(job.commits or []), result]
    job.status = "COMMITTED"
    await storage.add_artifact(session, job.id, "commit", result)
    await session.commit()
    return result


__all__ = ["CommitError", "commit"]
