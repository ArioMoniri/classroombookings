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

Every written row carries ``source_key = CC:<term>:<file sha256[:16]>:<record>`` so a re-commit, or the same
file uploaded again in a new job and committed into the same term, updates instead of duplicating (the
deterministic paths list a file's records in a stable order). TODO(P19-I5): key on the record's natural key
(course, section, day, time / date, room) as well, so an edited re-export of a file matches its old rows.

Rule proposals the reviewer accepted are resolved against the new term (:func:`app.ai.resolve.resolve_proposal`)
and saved with :func:`app.ai.elicit.accept_proposals` (source ``UPLOAD``, file reference in ``source_ref``).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import safe_files
from app.council import airows, critic, fastpath, formats, storage
from app.council import text as tx
from app.council.baseline import as_baseline_run
from app.council.dryrun import ChangeRecorder, summarize
from app.council.reconcile import rid, room_key
from app.council.review import build_items, decisions, effective_plan
from app.importers.catalog import Catalog
from app.importers.identity import plain
from app.importers.normalize import PERIODS
from app.importers.planning_list import _META, _merge
from app.importers.report import ImportReport
from app.models import (
    Block,
    Building,
    CouncilJob,
    ExamRequest,
    ImportedSnapshot,
    MeetingRequest,
    Room,
    Section,
    SectionInstructor,
    Term,
    User,
    Week,
)
from app.models.base import utcnow
from app.services.events import publish_event

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
    def __init__(
        self,
        session: AsyncSession,
        term: Term,
        job_id: int,
        periods: list[dict[str, Any]],
        shas: dict[int, str] | None = None,
        on_conflict: str = "keep",
    ) -> None:
        self.s = session
        #: planner edits (studio snapshots) vs the file: keep the planner's value (default) or take the file's
        self.take = on_conflict == "take"
        self.conflicts: list[dict[str, Any]] = []
        self.unchanged: Counter[str] = Counter()
        self.occurrence: Counter[tuple[str, str]] = Counter()
        self.term = term
        self.job_id = job_id
        #: file index -> sha256 of its bytes (job.files), the stable part of the row keys
        self.shas = shas or {}
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
        """The key rows had before natural keys (job / file sha + record index): looked up to re-key them."""
        sha = self.shas.get(fi)
        if not sha:  # a job stored before sha256 was recorded per file
            return f"CC:{self.job_id}:{fi}:{i}"
        return f"CC:{self.term.id}:{sha[:16]}:{i}"

    def natural(self, kind: str, *parts: Any) -> str:
        """``CC:<term>:<kind>:<hash of the natural key>`` (D14): the same row in any job, any format and any
        file version maps to the same key; identical rows in one commit are numbered (occurrence)."""
        raw = "|".join("" if p is None else str(p) for p in parts)
        self.occurrence[(kind, raw)] += 1
        occ = self.occurrence[(kind, raw)]
        digest = hashlib.sha256(f"{raw}|{occ}".encode()).hexdigest()[:32]
        return f"CC:{self.term.id}:{kind}:{digest}"

    async def find(self, model: Any, natural: str, legacy: str) -> Any:
        """The row of ``natural``, else a row still under its ``legacy`` key (re-keyed to ``natural``)."""
        row = (await self.s.execute(select(model).where(model.source_key == natural))).scalar_one_or_none()
        if row is None:
            row = (await self.s.execute(select(model).where(model.source_key == legacy))).scalar_one_or_none()
            if row is not None:
                row.source_key = natural
                self.counts["rekeyed_to_natural_keys"] += 1
        return row

    @staticmethod
    def assign(obj: Any, fields: dict[str, Any]) -> bool:
        """Set only the fields that differ; True when content (not bookkeeping) changed."""
        changed = False
        for k, v in fields.items():
            if plain(getattr(obj, k)) != plain(v):
                setattr(obj, k, v)
                changed = changed or k not in _META
        return changed

    async def snapshot(self, entity: str, entity_id: int) -> ImportedSnapshot | None:
        """The values imported before a planner's first studio edit (``app.services.studio_classes``)."""
        return (
            await self.s.execute(
                select(ImportedSnapshot).where(
                    ImportedSnapshot.entity == entity, ImportedSnapshot.entity_id == entity_id
                )
            )
        ).scalar_one_or_none()

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
            source_key=self.natural("M", skey, ",".join(map(str, days)), r.get("start")),
            source_row_index=r["source"].get("row"),
            archived=False,
        )
        mr = await self.find(MeetingRequest, fields["source_key"], self.key(fi, i))
        if mr is None:
            self.s.add(MeetingRequest(**fields))
            self.counts["meeting_requests"] += 1
        else:
            if mr.status == "LOCKED" and fields["status"] != "LOCKED":
                fields.pop("status")  # never downgrade a planner lock
            snap = await self.snapshot("meeting", mr.id)
            ctx = {"entity": "meeting", "id": mr.id, "row": r["source"].get("row"), "course": r["course_code"]}
            if _merge(mr, fields, snap, self.take, self.conflicts, ctx):
                self.counts["meeting_requests_updated"] += 1
            else:
                self.unchanged["meeting_requests"] += 1

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
            source_key=self.natural(
                "E", r["course_code"], program.canonical_name if program else "", r.get("date"), r.get("start")
            ),
            source_row_index=r["source"].get("row"),
            archived=False,
        )
        ex = await self.find(ExamRequest, fields["source_key"], self.key(fi, i))
        if ex is None:
            self.s.add(ExamRequest(**fields))
            self.counts["exam_requests"] += 1
        elif self.assign(ex, fields):
            self.counts["exam_requests_updated"] += 1
        else:
            self.unchanged["exam_requests"] += 1

    async def booking(self, fi: int, i: int, r: dict[str, Any], week_of: dict[str, int]) -> None:
        if r.get("course_codes"):  # course entries go to the baseline run (app/council/baseline.py)
            self.counts["timetable_course_entries_observed"] += 1
            await self.room({"code": r["room_code"], "label": r.get("room_label"), "tags": r.get("room_tags")})
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
            source_key=self.natural("B", room.id, week, r["day"], sp, str(r["text"])[:255]),
            archived=False,
        )
        b = await self.find(Block, fields["source_key"], self.key(fi, i))
        if b is None:
            self.s.add(Block(**fields))
            self.counts["blocks"] += 1
        elif self.assign(b, fields):
            self.counts["blocks_updated"] += 1
        else:
            self.unchanged["blocks"] += 1

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


async def _import_fast(
    session: AsyncSession,
    shape: str,
    stored: Any,
    name: str,
    term_code: str,
    *,
    year: int,
    week_count: int,
    on_conflict: str,
) -> ImportReport:
    """One fast-path file through its university importer. A csv / tsv / ods / xls / json / xml export of a
    known shape is read from its workbook transcoding (:func:`app.council.formats.workbook_for`)."""
    if shape == "room-master":
        from app.importers.room_master import import_room_master

        text = await safe_files.run_isolated(formats.utf8_for, stored)  # a cp1254 / UTF-16 room master too
        return await import_room_master(session, text, filename=name)
    path = await safe_files.run_isolated(formats.workbook_for, stored, name)
    if shape == "weekly-grid":
        from app.importers.weekly_grid import import_weekly_grid

        return await import_weekly_grid(session, path, term_code, year=year, filename=name)
    if shape == "planning-list":
        from app.importers.planning_list import import_planning_list

        return await import_planning_list(
            session, path, term_code, filename=name, week_count=week_count, on_conflict=on_conflict
        )
    from app.importers.exam_list import import_exam_list

    return await import_exam_list(session, path, term_code, filename=name)


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
    actor: User | None = None,
    on_conflict: str = "keep",
    recorder: ChangeRecorder | None = None,
) -> dict[str, Any]:
    """Write the chosen files into a term (see the module notes). ``on_conflict``: ``keep`` a planner's studio
    edit when the file changed the same field (default) or ``take`` the file's value; both are reported.
    ``recorder`` (the dry-run's) collects the row changes; otherwise the commit records its own counts."""
    if on_conflict not in ("keep", "take"):
        raise CommitError("on_conflict must be keep or take")
    own_recorder = recorder is None
    rec = recorder if recorder is not None else ChangeRecorder().attach(session)
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
    ai_pending = await airows.pending_ai(session, job, chosen)
    if ai_pending:  # P19-A2: allow_pending never covers rows the AI model read
        raise CommitError(
            f"{len(ai_pending)} row(s) read by the AI model must be accepted, edited or rejected first "
            f"(e.g. {ai_pending[0]}); allow_pending does not apply to them"
        )
    pending = [it for it in pending if it["kind"] != "ai_rows"]
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
        (i for i in chosen if routes[i].startswith("fast:") and routes[i][5:] in fastpath.IMPORTER_SHAPES),
        key=lambda i: fastpath.COMMIT_ORDER.get(routes[i][5:], 9),
    )
    entries = {f["index"]: f for f in job.files}
    for i in fast:
        shape = routes[i][5:]
        name = entries[i]["filename"]
        rep = await _import_fast(
            session,
            shape,
            storage.file_path(job.id, entries[i]),
            name,
            term_code,
            year=year,
            week_count=int(g.get("week_count") or 14),
            on_conflict=on_conflict,
        )
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
                "unchanged": dict(d["extra"].get("unchanged") or {}),
                "conflicts": list(d["extra"].get("conflicts") or [])[:500],
            }
        )

    term = await session.get(Term, tid)
    assert term is not None
    shas = {int(f["index"]): str(f.get("sha256") or "") for f in job.files}
    writer = Writer(session, term, job.id, periods, shas, on_conflict=on_conflict)
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
    # general-path files and the record shapes without an importer (intake.v1 JSON, ICS schedule maps)
    general = [i for i in chosen if not routes[i].startswith("fast:") or routes[i][5:] not in fastpath.IMPORTER_SHAPES]
    week_of = await writer.weeks(g) if g else {}
    if general:
        file_rooms: set[str] = set()
        room_edits: dict[str, dict[str, Any]] = {}
        for i in general:
            for n, r in enumerate(records.get(i, [])):
                if r["type"] not in ("room", "booking"):
                    continue
                d = decided.get(airows.row_id(i, n)) or {}
                if d.get("action") == "reject":  # a rejected row names no room
                    continue
                k = room_key(r.get("code") or r.get("room_code") or "")
                file_rooms.add(k)
                if d.get("action") == "edit" and r["type"] == "room":
                    room_edits[k] = {kk: v for kk, v in (d.get("value") or {}).items() if kk not in airows.FROZEN}
        for room in dataset.get("rooms", []):
            if room["key"] in file_rooms:
                await writer.room({**room, **room_edits.get(room["key"], {})})
        for i in general:
            for n, r in enumerate(records.get(i, [])):
                if rid(i, n) in duplicates:
                    writer.counts["duplicates_skipped"] += 1
                    continue
                row_decision = decided.get(airows.row_id(i, n))
                if row_decision and row_decision.get("action") == "reject":
                    writer.counts["rows_rejected"] += 1
                    continue
                if row_decision and row_decision.get("action") == "edit":
                    r = {**r, **{k: v for k, v in (row_decision.get("value") or {}).items() if k not in airows.FROZEN}}
                    writer.counts["rows_edited"] += 1
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

    # schedule maps (board, ICS, intake.v1 timetable, general timetables) -> the term's baseline IMPORT run
    schedule: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for i in chosen:
        src = {"sha256": shas.get(i) or None, "file": entries[i]["filename"], "job": job.id}
        schedule.extend(
            (r, src)
            for n, r in enumerate(records.get(i, []))
            if r["type"] == "booking" and (decided.get(airows.row_id(i, n)) or {}).get("action") != "reject"
        )
    baseline = None
    if schedule:
        grid = periods or [
            {"index": k + 1, "start": p.start.strftime("%H:%M"), "end": p.end.strftime("%H:%M")}
            for k, p in enumerate(PERIODS)
        ]
        term = await session.get(Term, tid)
        assert term is not None
        baseline = await as_baseline_run(session, term, schedule, grid)
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
        "unchanged": dict(writer.unchanged),
        "baseline_run": baseline,
        "conflicts": writer.conflicts[:500],
        "on_conflict": on_conflict,
        "at": utcnow().isoformat(),
        "by": user_id,
    }
    # the same per-entity counts a dry-run reports (app/council/dryrun.py), so both can be compared
    result["changes"] = summarize(rec, result, on_conflict)["counts"]
    if own_recorder:
        rec.detach(session)
    fresh = await session.get(CouncilJob, job.id)
    job = fresh if fresh is not None else job
    job.commits = [*(job.commits or []), result]
    job.status = "COMMITTED"
    from app.council import memory

    await memory.attach_term(session, job.id, tid)  # the job's intake memory now belongs to the term
    await storage.add_artifact(session, job.id, "commit", result)
    # one audit event (and the event-bus subscribers) per commit, inside the commit's transaction
    await publish_event(
        session,
        "council.commit",
        "council_job",
        job.id,
        after={k: result[k] for k in ("term_code", "term_created", "files", "general", "constraints_created")},
        actor=actor,
        term_id=tid,
    )
    await session.commit()
    return result


__all__ = ["CommitError", "commit"]
