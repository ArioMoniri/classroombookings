"""Studio rules (step 3): templates + weight scale, rule list, affected-count preview, copy from another
term / run, accept with ``source_ref``, the no-AI Excel/CSV column-mapping fallback and presets.

Rule targeting always goes through the solver's own selector (``select_events``) on the draft's
``SolverInput``, so "applies to 42 classes" is exactly what the solver will see.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import catalog
from app.core.safe_files import UnsafeFileError, run_isolated
from app.importers.normalize import (
    PERIODS,
    canon_course_code,
    extract_course_codes,
    normalize_selector_params,
    parse_class_year,
    parse_day,
    parse_mode,
    parse_room_codes,
    parse_time,
    parse_time_slot,
    time_range_to_periods,
    time_to_period,
    tr_casefold,
    tr_upper,
)
from app.importers.tables import read_table, table_cell
from app.models import (
    ConstraintRow,
    Course,
    ExamRequest,
    Faculty,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    StudioDraft,
    StudioPreset,
    User,
)
from app.services import solver_bridge
from app.services import studio as st
from app.solver import model as sm

WEIGHT_SCALE = {"low": 2, "normal": 5, "high": 8}
MAX_MAPPING_BYTES = 5 * 1024 * 1024
MAX_MAPPING_ROWS = 5000
MAX_MAPPING_COLS = 256


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


# --------------------------------------------------------------------------- templates / meta


def _field(name: str, type_: str, param: str | None = None, required: bool = False, **extra: Any) -> dict[str, Any]:
    return {"name": name, "type": type_, "param": param or name, "required": required, **extra}


APPLIES_TO = _field("applies_to", "applies_to", "selector")

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "keep_in_building",
        "topic": "buildings",
        "kind": "building_preference",
        "title": _t("Belirli blokta tut", "Keep in a building"),
        "sentence": _t(
            "{applies_to} derslerini {building} blokta tut [{days}]",
            "Keep {applies_to} in building {building} [on {days}]",
        ),
        "fields": [APPLIES_TO, _field("building", "building", required=True), _field("days", "days")],
        "default_hardness": "soft",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "no_classes_after",
        "topic": "times",
        "kind": "day_window",
        "title": _t("Belirli saatten sonra ders olmasın", "No classes after a time"),
        "sentence": _t(
            "{applies_to} için {latest}'den sonra [veya {earliest}'den önce] ders olmasın",
            "No classes after {latest} [or before {earliest}] for {applies_to}",
        ),
        "fields": [APPLIES_TO, _field("latest", "period", min=1, max=18), _field("earliest", "period", min=1, max=18)],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
        "note": _t(
            "Ders saatleri 40 dakikadır; 17:30, 12. dersin başlangıcıdır.",
            "Periods are 40 minutes. 17:30 is the start of P12.",
        ),
    },
    {
        "id": "room_only_for",
        "topic": "rooms",
        "kind": "room_tags",
        "title": _t("Derslik sadece belirli program için", "Room only for a programme"),
        "sentence": _t("{tag} derslikleri sadece {applies_to} için", "{tag} rooms only for {applies_to}"),
        "fields": [
            _field("tag", "tag", "forbidden_tags", required=True),
            _field("applies_to", "applies_to_others", "selector", note="the rule is stored for everyone *else*"),
        ],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
        "note": _t(
            "Dersliği bir etiketle (ör. TIP) işaretleyin; diğer programlar bu etiketi kullanamaz.",
            "Tag the rooms (e.g. TIP); every other programme is kept out of that tag.",
        ),
    },
    {
        "id": "never_use_room",
        "topic": "rooms",
        "kind": "room_forbid",
        "title": _t("Dersliği kullanma", "Never use a room"),
        "sentence": _t("{rooms} dersliğini {applies_to} için kullanma", "Never use room {rooms} for {applies_to}"),
        "fields": [_field("rooms", "rooms", "room_ids", required=True), APPLIES_TO],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "always_in_room",
        "topic": "rooms",
        "kind": "room_pin",
        "title": _t("Her zaman bu derslikte", "Always in a room"),
        "sentence": _t(
            "{course} her zaman {rooms} dersliğinde [{from_date}'den itibaren]",
            "Always put {course} in room {rooms} [from {from_date}]",
        ),
        "fields": [
            _field("course", "courses", "event_ids", required=True),
            _field("rooms", "rooms", "room_ids", required=True),
            _field("from_date", "date", "weeks"),
        ],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "prefer_rooms",
        "topic": "rooms",
        "kind": "room_preference",
        "title": _t("Derslik tercihi", "Prefer rooms"),
        "sentence": _t("{applies_to} için {rooms} tercih et", "Prefer room(s) {rooms} for {applies_to}"),
        "fields": [_field("rooms", "rooms", "room_ids", required=True, ordered=True), APPLIES_TO],
        "default_hardness": "soft",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "same_room_as",
        "topic": "rooms",
        "kind": "same_room_group",
        "title": _t("Başka dersle aynı derslik", "Same room as another course"),
        "sentence": _t("{courses} dersleri aynı derslikte", "Same room as course {courses}"),
        "fields": [_field("courses", "courses", "event_ids", required=True, min_items=2)],
        "default_hardness": "soft",
        "default_weight": WEIGHT_SCALE["high"],
    },
    {
        "id": "same_room_every_week",
        "topic": "rooms",
        "kind": "same_room_across_weeks",
        "title": _t("Her hafta aynı derslik", "Same room every week"),
        "sentence": _t("{applies_to} her hafta aynı derslikte", "Same room every week for {applies_to}"),
        "fields": [APPLIES_TO],
        "default_hardness": "soft",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "needs_lab",
        "topic": "rooms",
        "kind": "room_tags",
        "title": _t("Bilgisayar laboratuvarı gerekli", "Needs a computer lab"),
        "sentence": _t("{applies_to} için {tag} gerekli", "{applies_to} needs a {tag} room"),
        "fields": [APPLIES_TO, _field("tag", "tag", "required_tags", required=True, default=["PC"])],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "room_closed",
        "topic": "rooms",
        "kind": "room_closed",
        "title": _t("Derslik kapalı", "Room closed"),
        "sentence": _t("{room} {days} {periods} [{weeks}] kapalı", "Room {room} closed on {days} {periods} [{weeks}]"),
        "fields": [
            _field("room", "room", "room_id", required=True),
            _field("days", "days", required=True),
            _field("periods", "periods"),
            _field("weeks", "weeks"),
        ],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "evening_in_buildings",
        "topic": "programmes",
        "kind": "evening_programs_in_buildings",
        "title": _t("İkinci öğretim belirli bloklarda", "Evening programmes in buildings"),
        "sentence": _t("İkinci öğretim {buildings} bloklarında", "Evening programmes in buildings {buildings}"),
        "fields": [_field("buildings", "buildings", required=True)],
        "default_hardness": "soft",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "no_small_in_big",
        "topic": "rooms",
        "kind": "min_capacity_waste",
        "title": _t("Küçük sınıfları büyük amfiye koyma", "Don't put small classes in big halls"),
        "sentence": _t("Küçük sınıfları büyük amfiye koyma", "Don't put small classes in big halls"),
        "fields": [_field("unit", "number", min=1, max=100, advanced=True, default=10)],
        "default_hardness": "soft",
        "default_weight": WEIGHT_SCALE["low"],
    },
    {
        "id": "exam_gap",
        "topic": "exams",
        "kind": "exam_gap",
        "title": _t("Sınavlar arasında boşluk", "Gap between exams"),
        "sentence": _t(
            "Aynı sınıfın sınavları arasında en az {n} ders saati",
            "Exams: at least {n} periods between exams of {applies_to}",
        ),
        "fields": [_field("n", "number", "min_periods", required=True, min=0, max=6), APPLIES_TO],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
    },
    {
        "id": "max_exams_per_day",
        "topic": "exams",
        "kind": "max_exams_per_day",
        "title": _t("Günlük sınav sınırı", "Exams per day"),
        "sentence": _t(
            "{applies_to} için günde en fazla {n} sınav", "Exams: at most {n} exams per day for {applies_to}"
        ),
        "fields": [_field("n", "number", "n", required=True, min=1, max=6), APPLIES_TO],
        "default_hardness": "hard",
        "default_weight": WEIGHT_SCALE["normal"],
    },
]

SOURCES = {
    "FILE": _t("Dosya", "File"),
    "ADMIN": _t("Yönetici", "Admin"),
    "AI": _t("YZ", "AI"),
    "UPLOAD": _t("Yükleme", "Upload"),
    "BUILTIN": _t("Sistem", "Built-in"),
}

MAPPING_ROLES = {
    "course": _t("Ders kodu", "Course code"),
    "section": _t("Şube", "Section"),
    "program": _t("Program / bölüm", "Programme / department"),
    "year": _t("Sınıf", "Class year"),
    "enrolment": _t("Öğrenci sayısı", "Students"),
    "day": _t("Gün", "Day"),
    "time": _t("Saat", "Time"),
    "room": _t("Derslik", "Room"),
    "building": _t("Blok", "Building"),
    "mode": _t("Eğitim şekli", "Mode"),
    "note": _t("Not / talep", "Note / request"),
}


def meta() -> dict[str, Any]:
    kinds = {k["kind"]: k for k in catalog.catalog_dict()["kinds"]}
    templates = []
    for tpl in TEMPLATES:
        spec = kinds.get(tpl["kind"], {})
        allowed = spec.get("allowed_hardness", ["hard", "soft"])
        templates.append(
            {
                **tpl,
                "allowed_hardness": allowed,
                "default_hardness": tpl["default_hardness"] if tpl["default_hardness"] in allowed else allowed[0],
                "params_schema": spec.get("params_schema"),
                "catalog_title": spec.get("title"),
            }
        )
    return {
        "weight_scale": {
            **WEIGHT_SCALE,
            "default": WEIGHT_SCALE["normal"],
            "labels": {
                "low": _t("Düşük", "Low"),
                "normal": _t("Normal", "Normal"),
                "high": _t("Yüksek", "High"),
            },
            "custom_range": [1, 10],
        },
        "templates": templates,
        "builtins": [
            {"kind": k, "title": st.BUILTIN_TEXT[k], "disableable": v, "admin_only": True}
            for k, v in st.BUILTINS.items()
        ],
        "sources": SOURCES,
        "hardness": {
            "hard": {
                "label": _t("Kesin", "Must"),
                "help": _t(
                    "SmartSched bunu asla bozmaz. Mümkün değilse durur ve nedenini söyler.",
                    "SmartSched will never break this. If it can't be done, it stops and tells you why.",
                ),
            },
            "soft": {
                "label": _t("Mümkünse", "Try to"),
                "help": _t(
                    "SmartSched mümkün olduğunda uyar ve uyamadığı yerleri gösterir.",
                    "SmartSched follows this whenever it can and shows you where it couldn't.",
                ),
            },
        },
        "periods": [
            {"index": p.index, "start": f"{p.start:%H:%M}", "end": f"{p.end:%H:%M}", "label": p.label} for p in PERIODS
        ],
        "mapping_roles": MAPPING_ROLES,
        "catalog": list(kinds.values()),
    }


# --------------------------------------------------------------------------- rule list / preview


def _selector_affected(
    inp: sm.SolverInput, members: dict[int, list[int]], kind: str, params: dict[str, Any]
) -> tuple[list[sm.Event], bool]:
    """(events the rule touches, targeted?) - via the solver's selector."""
    from app.solver.constraints._common import is_targeted, select_events

    spec = catalog.KINDS.get(kind)
    clean = normalize_selector_params({k: v for k, v in params.items() if not str(k).startswith("_")})
    clean = solver_bridge.events_for_requests(clean, members)  # merged members -> their event (U3)
    c = sm.Constraint(kind, clean, True, 1, None)
    if spec is not None and not spec.selectable:
        if kind == "room_closed":
            rid = clean.get("room_id")
            days = [int(d) for d in ([clean["day"]] if clean.get("day") else clean.get("days") or [])]
            hit = [
                e
                for e in inp.events
                if rid is not None
                and (
                    (e.locked is not None and int(rid) in e.locked.room_ids and (not days or e.locked.day in days))
                    or int(rid) in e.preferred_room_ids
                    or int(rid) in e.required_room_ids
                )
            ]
            return hit, True
        return list(inp.events), False
    return list(select_events(inp, clean)), is_targeted(c)


async def preview(session: AsyncSession, draft: StudioDraft, body: Any) -> dict[str, Any]:
    din = await st.build_draft_input(session, draft)
    issues = catalog.validate_params(body.kind, dict(body.params), body.hardness)
    events, targeted = (
        _selector_affected(din.inp, din.members, body.kind, dict(body.params))
        if body.kind in catalog.KINDS
        else ([], True)
    )
    total = sum(len(v) for v in din.members.values())
    affected = sum(len(din.members.get(e.id, [e.id])) for e in events)
    pct = round(100.0 * affected / total, 1) if total else 0.0
    notes = []
    if targeted and affected == 0:
        notes.append("matches_none")
    if body.hardness == "hard" and pct > 50:
        notes.append("affects_most")
    sample = [
        {"event_id": e.id, "label": e.label, "request_ids": din.members.get(e.id, [e.id]), "size": e.size}
        for e in events[: body.sample]
    ]
    return {
        "affected_count": affected,
        "total": total,
        "percent": pct,
        "targeted": targeted,
        "sample": sample,
        "issues": issues,
        "notes": notes,
    }


def _source_ref(row: ConstraintRow) -> dict[str, Any] | None:
    return row.source_ref or (row.params or {}).get("_source_ref")


async def rules_for_draft(session: AsyncSession, draft: StudioDraft) -> dict[str, Any]:
    rows = await st.term_rules(session, draft.term_id, enabled_only=False)
    din = await st.build_draft_input(session, draft)
    off = {int(i) for i in draft.disabled_rule_ids or []}
    overrides = draft.rule_overrides or {}
    rules = []
    for r in rows:
        spec = catalog.KINDS.get(r.kind)
        events, _targeted = (
            _selector_affected(din.inp, din.members, r.kind, dict(r.params or {})) if spec else ([], True)
        )
        ov = overrides.get(str(r.id))
        rules.append(
            {
                "id": r.id,
                "kind": r.kind,
                "params": {k: v for k, v in (r.params or {}).items() if not str(k).startswith("_")},
                "hardness": r.hardness,
                "weight": r.weight,
                "source": r.source,
                "source_ref": _source_ref(r),
                "nl_text": r.nl_text,
                "enabled": r.enabled,
                "in_play": r.enabled and r.id not in off,
                "override": ov,
                "title": spec.title if spec else _t(r.kind, r.kind),
                "affected_count": sum(len(din.members.get(e.id, [e.id])) for e in events) if spec else None,
            }
        )
    builtins_off = set(await st.disabled_builtins(session, draft))
    in_play = [r for r in rules if r["in_play"]]

    def eff_hard(r: dict[str, Any]) -> bool:
        return bool(((r["override"] or {}).get("hardness") or r["hardness"]) == "hard")

    return {
        "rules": rules,
        "builtins": [
            {"kind": k, "title": st.BUILTIN_TEXT[k], "enabled": k not in builtins_off, "disableable": v}
            for k, v in st.BUILTINS.items()
        ],
        "counts": {
            "must": sum(1 for r in in_play if eff_hard(r)),
            "try": sum(1 for r in in_play if not eff_hard(r)),
            "turned_off": len(rules) - len(in_play),
            "builtin": len(st.BUILTINS),
            "builtin_off": len(builtins_off),
            "matches_none": sum(1 for r in in_play if r["affected_count"] == 0),
        },
    }


# --------------------------------------------------------------------------- accept (source_ref column)


async def accept(session: AsyncSession, term_id: int, body: Any, user: User) -> dict[str, Any]:
    from app.ai.edits import apply_section_edits
    from app.ai.elicit import accept_proposals
    from app.schemas.ai import ProposedConstraint, ProposedSectionEdit

    await st.get_term(session, term_id)
    try:
        props = [ProposedConstraint.model_validate(p) for p in body.proposals]
        edits = [ProposedSectionEdit.model_validate(e) for e in body.section_edits]
    except ValueError as exc:
        raise st.StudioError(422, str(exc).splitlines()[0]) from exc
    for p in props:
        if p.source_ref and p.source == "AI":
            p.source = "UPLOAD"
    created, rejected = await accept_proposals(session, term_id, props, user_id=user.id, commit=False)
    for cid in created:
        row = await session.get(ConstraintRow, cid)
        if row is not None and (row.params or {}).get("_source_ref") is not None:
            params = dict(row.params)
            row.source_ref = params.pop("_source_ref")
            row.params = params
    applied, rejected_edits = await apply_section_edits(session, term_id, edits, commit=False, draft_user_id=user.id)
    await session.commit()
    return {
        "created": created,
        "rejected": rejected + [{**r, "section_edit": True} for r in rejected_edits],
        "section_edits_applied": applied,
    }


# --------------------------------------------------------------------------- copy


async def _meeting_keys(
    session: AsyncSession, ids: Iterable[int]
) -> dict[int, tuple[int, int | None, str | None, int | None, int | None]]:
    wanted = list({int(i) for i in ids})
    if not wanted:
        return {}
    q = (
        select(
            MeetingRequest.id,
            Section.course_id,
            Section.program_id,
            Section.label,
            MeetingRequest.day,
            MeetingRequest.start_period,
        )
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(MeetingRequest.id.in_(wanted))
    )
    return {r[0]: (r[1], r[2], r[3], r[4], r[5]) for r in (await session.execute(q)).all()}


async def _map_event_ids(session: AsyncSession, ids: list[int], target_term: int) -> tuple[list[int], list[int]]:
    """Meeting ids of another term -> the same course + programme + section (same day/time first) in the
    target term. Returns (mapped ids, unmapped source ids)."""
    keys = await _meeting_keys(session, ids)
    if not keys:
        return [], list(ids)
    course_ids = {k[0] for k in keys.values()}
    q = (
        select(
            MeetingRequest.id,
            Section.course_id,
            Section.program_id,
            Section.label,
            MeetingRequest.day,
            MeetingRequest.start_period,
        )
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == target_term, Section.course_id.in_(course_ids), MeetingRequest.archived.is_(False))
    )
    target = (await session.execute(q)).all()
    mapped: list[int] = []
    unmapped: list[int] = []
    for sid in ids:
        k = keys.get(sid)
        if k is None:
            unmapped.append(sid)
            continue
        same_sec = [t for t in target if (t[1], t[2], t[3]) == k[:3]]
        exact = [t for t in same_sec if (t[4], t[5]) == k[3:]]
        hit = exact or same_sec
        if hit:
            mapped.extend(t[0] for t in hit)
        else:
            unmapped.append(sid)
    return sorted(set(mapped)), unmapped


async def copy_rules(session: AsyncSession, body: Any, user: User) -> dict[str, Any]:
    target = await st.get_term(session, body.to_term_id)
    if (body.from_run_id is None) == (body.from_term_id is None):
        raise st.StudioError(422, "give exactly one of from_run_id / from_term_id")
    src_run: ScheduleRun | None = None
    if body.from_run_id is not None:
        src_run = await session.get(ScheduleRun, body.from_run_id)
        if src_run is None:
            raise st.StudioError(404, "run not found")
        src_term = src_run.term_id
        q = select(ConstraintRow).where(
            ((ConstraintRow.run_id == src_run.id) | (ConstraintRow.term_id == src_term)),
            ConstraintRow.source != "BUILTIN",
        )
    else:
        src_term = int(body.from_term_id)
        await st.get_term(session, src_term)
        q = select(ConstraintRow).where(ConstraintRow.term_id == src_term, ConstraintRow.source != "BUILTIN")
    rows = list((await session.execute(q.order_by(ConstraintRow.id))).scalars())
    if body.constraint_ids is not None:
        wanted = set(body.constraint_ids)
        rows = [r for r in rows if r.id in wanted]
    else:
        rows = [r for r in rows if r.enabled]
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    existing = {
        (r.kind, _norm(r.params), r.hardness) for r in await st.term_rules(session, target.id, enabled_only=False)
    }
    drafts: dict[str, st.DraftInput] = {}

    async def target_input(kind: str) -> st.DraftInput:
        if kind not in drafts:
            d = await st.get_draft(session, target.id, user.id, kind)
            drafts[kind] = await st.build_draft_input(session, d)
        return drafts[kind]

    out: dict[str, list[dict[str, Any]]] = {"will_match": [], "needs_review": [], "cannot_match": []}
    created: list[int] = []
    for r in rows:
        params = {k: v for k, v in (r.params or {}).items() if not str(k).startswith("_")}
        reasons: list[str] = []
        fatal = False
        room_ids = [int(x) for x in params.get("room_ids") or []] + (
            [int(params["room_id"])] if params.get("room_id") is not None else []
        )
        gone = [x for x in room_ids if x not in rooms or not rooms[x].is_bookable]
        if gone:
            reasons.append(f"room(s) {gone} do not exist or are not bookable")
            fatal = True
        if params.get("event_ids") and src_term != target.id:
            mapped, unmapped = await _map_event_ids(session, [int(x) for x in params["event_ids"]], target.id)
            if not mapped:
                reasons.append("none of its classes exist in this term")
                fatal = True
            elif unmapped:
                reasons.append(f"{len(unmapped)} of its classes do not exist in this term")
            params["event_ids"] = mapped
        kind_for_input = (
            "EXAM" if "exam" in (params.get("kinds") or []) or r.kind in ("exam_gap", "max_exams_per_day") else "COURSE"
        )
        affected = 0
        if not fatal and r.kind in catalog.KINDS:
            din = await target_input(kind_for_input)
            events, targeted = _selector_affected(din.inp, din.members, r.kind, params)
            affected = sum(len(din.members.get(e.id, [e.id])) for e in events)
            if targeted and affected == 0:
                reasons.append("matches no classes in this term")
        if (r.kind, _norm(params), r.hardness) in existing:
            reasons.append("an identical rule already exists in this term")
            fatal = True
        item = {
            "source_id": r.id,
            "kind": r.kind,
            "hardness": r.hardness,
            "weight": r.weight,
            "nl_text": r.nl_text,
            "params": params,
            "affected_count": affected,
            "reasons": reasons,
            "created_id": None,
        }
        bucket = "cannot_match" if fatal else ("needs_review" if reasons else "will_match")
        # review MINOR 7: only rules that match as they are are created; "needs_review" ones go to the
        # review tray (returned, accepted later through /studio/proposals/accept)
        if bucket == "will_match" and not body.dry_run:
            row = ConstraintRow(
                term_id=target.id,
                kind=r.kind,
                params=params,
                hardness=r.hardness,
                weight=r.weight,
                source=r.source,
                source_ref={
                    "copied_from": {
                        "term_id": src_term,
                        "run_id": src_run.id if src_run else None,
                        "constraint_id": r.id,
                    },
                    **({"original": _source_ref(r)} if _source_ref(r) else {}),
                },
                nl_text=r.nl_text,
                enabled=True,
                created_by=user.id,
            )
            session.add(row)
            await session.flush()
            item["created_id"] = row.id
            created.append(row.id)
            existing.add((r.kind, _norm(params), r.hardness))
        out[bucket].append(item)
    if created:
        await session.commit()
    return {**out, "created": created, "dry_run": bool(body.dry_run)}


def _norm(params: dict[str, Any] | None) -> str:
    return repr(sorted((k, repr(v)) for k, v in (params or {}).items() if not str(k).startswith("_")))


# --------------------------------------------------------------------------- no-AI column mapping


_BUILDING_RX = re.compile(r"\b([A-Da-d])\s*[-]?\s*(?:blok|BLOK|Blok|bloğu|BLOĞU|Bloğu)")


_ASCII = str.maketrans("İIıÇçĞğÖöŞşÜü", "IIICCGGOOSSUU")


def _ascii_code(code: str) -> str:
    return re.sub(r"\s+", "", str(code)).translate(_ASCII).upper()


def _cell(v: Any) -> str:
    return table_cell(v)


def _read_table(
    data: bytes, filename: str, sheet: str | None
) -> tuple[list[str], str | None, list[tuple[int, list[str]]]]:
    return read_table(data, filename, sheet, max_rows=MAX_MAPPING_ROWS, max_cols=MAX_MAPPING_COLS)


def _detect(header: list[str]) -> dict[str, int]:
    from app.ai.ingest import detect_columns

    roles = {role: col for col, role in detect_columns(header).items()}
    for col, h in enumerate(header):
        key = tr_casefold(h or "")
        if "building" not in roles and key in ("blok", "bina", "building"):
            roles["building"] = col
    return roles


def _header_row(rows: list[tuple[int, list[str]]]) -> int | None:
    best: tuple[int, int] | None = None
    for i, (_n, cells) in enumerate(rows[:15]):
        n = len(_detect(cells))
        if n >= 2 and (best is None or n > best[0]):
            best = (n, i)
    return best[1] if best else None


async def mapping_fallback(
    session: AsyncSession, term_id: int, data: bytes, filename: str, mapping: dict[str, Any] | None, lang: str
) -> dict[str, Any]:
    await st.get_term(session, term_id)
    if not data:
        raise st.StudioError(400, "empty file")
    sheet_req = (mapping or {}).get("sheet")
    try:  # bounded parse off the event loop, in a memory-capped child process (review B1)
        sheets, sheet, rows = await run_isolated(
            read_table, data, filename, sheet_req, max_rows=MAX_MAPPING_ROWS, max_cols=MAX_MAPPING_COLS
        )
    except UnsafeFileError as exc:
        raise st.StudioError(exc.status, exc.message) from exc
    if not rows:
        raise st.StudioError(400, "the sheet is empty")
    if mapping and mapping.get("header_row"):
        hidx = next((i for i, (n, _c) in enumerate(rows) if n == int(mapping["header_row"])), None)
    else:
        hidx = _header_row(rows)
    header = rows[hidx][1] if hidx is not None else []
    body_rows = [r for i, r in enumerate(rows) if hidx is None or i > hidx]
    if not mapping or not mapping.get("columns"):
        width = max((len(c) for _n, c in rows[:50]), default=0)
        columns = []
        for col in range(width):
            samples = [c[col] for _n, c in body_rows[:30] if col < len(c) and c[col]][:3]
            columns.append({"index": col, "header": header[col] if col < len(header) else "", "samples": samples})
        return {
            "mode": "columns",
            "filename": filename,
            "sheets": sheets,
            "sheet": sheet,
            "header_row": rows[hidx][0] if hidx is not None else None,
            "row_count": len([r for r in body_rows if any(r[1])]),
            "columns": columns,
            "suggested_mapping": {
                "columns": _detect(header) if header else {},
                "room_rule": "prefer",
                "hardness": "soft",
                "weight": WEIGHT_SCALE["normal"],
            },
            "roles": MAPPING_ROLES,
        }
    return await _map_rows(session, term_id, filename, sheet if len(sheets) > 1 else None, header, body_rows, mapping)


async def _map_rows(
    session: AsyncSession,
    term_id: int,
    filename: str,
    sheet: str | None,
    header: list[str],
    rows: list[tuple[int, list[str]]],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    from app.ai.resolve import load_term_context, resolve_proposal, resolve_section_edit

    cols = {
        str(k): int(v) for k, v in (mapping.get("columns") or {}).items() if v is not None and str(k) in MAPPING_ROLES
    }
    if "course" not in cols and "program" not in cols:
        raise st.StudioError(422, "map at least the course (or programme) column")
    room_rule = str(mapping.get("room_rule") or "prefer")
    if room_rule not in ("prefer", "pin", "forbid"):
        raise st.StudioError(422, "room_rule must be prefer, pin or forbid")
    kind_for_room = {"prefer": "room_preference", "pin": "room_pin", "forbid": "room_forbid"}[room_rule]
    default_hard = "soft" if room_rule == "prefer" else "hard"
    hardness = str(mapping.get("hardness") or default_hard)
    weight = int(mapping.get("weight") or WEIGHT_SCALE["normal"])
    ctx = await load_term_context(session, term_id)
    proposals: list[dict[str, Any]] = []
    edits: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []

    by_ascii = {_ascii_code(c.code): c.code for c in ctx.courses}

    def _term_code(raw: str) -> str:
        """Course code as stored in the term: ``PSİ 116`` (Turkish keyboard) -> ``PSI116``."""
        canon = canon_course_code(raw) or raw
        return by_ascii.get(_ascii_code(canon), canon)

    def val(cells: list[str], role: str) -> str:
        i = cols.get(role)
        return cells[i].strip() if i is not None and i < len(cells) and cells[i] else ""

    for rownum, cells in rows:
        if not any(cells):
            continue
        excerpt = " | ".join(
            f"{header[i] if i < len(header) and header[i] else f'#{i + 1}'}={c}" for i, c in enumerate(cells) if c
        )[:300]
        ref: dict[str, Any] = {"file": filename, "row": rownum, "excerpt": excerpt}
        if sheet:
            ref["sheet"] = sheet
        codes = [_term_code(c) for c in extract_course_codes(val(cells, "course"))]
        program = val(cells, "program")
        years = [int(y) for y in (parse_class_year(val(cells, "year")) or []) if y] if val(cells, "year") else []
        label = val(cells, "section").lstrip("§").strip()
        selector = {
            "course_codes": codes,
            "program_name": program,
            "class_years": years,
        }
        if not codes and not program:
            unparsed.append({"source_ref": ref, "text": excerpt, "reason": "no course code or programme in this row"})
            continue
        note = val(cells, "note")
        made = 0
        room_text = val(cells, "room")
        room_codes = parse_room_codes(room_text) if room_text else []
        building_text = val(cells, "building") or room_text
        bm = _BUILDING_RX.search(building_text or "")
        buildings = [tr_upper(bm.group(1))] if bm and not room_codes else []
        if not buildings and val(cells, "building") and len(val(cells, "building").strip()) == 1:
            buildings = [tr_upper(val(cells, "building").strip())]
        raw_kind = kind_for_room if room_codes else ("building_preference" if buildings else None)
        if raw_kind:
            raw = {
                "kind": raw_kind,
                "hardness": hardness if raw_kind != "building_preference" else str(mapping.get("hardness") or "soft"),
                "weight": weight,
                "nl_text": excerpt,
                "rationale": "column mapping (no AI)",
                "confidence": 0.9,
                "selector": selector,
                "params": {"room_codes": room_codes, "buildings": buildings},
            }
            p = resolve_proposal(ctx, raw)
            if label and p.params.get("event_ids"):
                keep = {
                    mid
                    for sid, s in ctx.sections.items()
                    if (s.label or "").strip() == label
                    for mid in [m.id for m in s.meeting_requests if not m.archived]
                }
                narrowed = [e for e in p.params["event_ids"] if e in keep]
                if narrowed:
                    p.params["event_ids"] = narrowed
                else:
                    p.issues.append(f"no section '{label}' of these courses")
                    p.status = "needs_review"
            p.source = "UPLOAD"
            p.source_ref = ref
            proposals.append(p.model_dump())
            made += 1
        changes: dict[str, Any] = {}
        enr = val(cells, "enrolment")
        if enr and re.fullmatch(r"\d{1,4}", enr.replace(".", "").replace(",", "")):
            changes["enrolment"] = int(enr.replace(".", "").replace(",", ""))
        if val(cells, "mode"):
            mode = parse_mode(val(cells, "mode")).mode
            if mode != "OTHER":
                changes["mode"] = mode
        day_text, time_text = val(cells, "day"), val(cells, "time")
        if day_text:
            d = parse_day(day_text)
            if len(d.days) == 1:
                changes["day"] = d.days[0]
        if time_text:
            slot = parse_time_slot(time_text)  # "13.30-15.50", "13:30 - 15:50"
            if slot:
                pr = time_range_to_periods(*slot)
                if pr.start_period and pr.end_period:
                    changes["start_period"], changes["end_period"] = pr.start_period, pr.end_period
            elif (one := parse_time(time_text)) is not None:
                pm = time_to_period(one, "start")
                if pm.period:
                    changes["start_period"] = pm.period
        if changes and codes:
            e = resolve_section_edit(
                ctx,
                "set_field",
                {
                    "course_codes": codes,
                    "program_name": program,
                    "section_label": label,
                    **changes,
                    "nl_text": excerpt,
                    "reason": "column mapping (no AI)",
                    "confidence": 0.9,
                },
            )
            e.source = "UPLOAD"
            e.source_ref = ref
            edits.append(e.model_dump())
            made += 1
        if not made:
            unparsed.append(
                {
                    "source_ref": ref,
                    "text": note or excerpt,
                    "reason": "nothing mappable (room, building, students, mode, day/time) in this row"
                    + ("; the note needs AI or a rule written by hand" if note else ""),
                }
            )
    ready = sum(1 for p in proposals if p["status"] == "ok") + sum(1 for e in edits if e["status"] == "ok")
    look = len(proposals) + len(edits) - ready
    return {
        "mode": "proposals",
        "filename": filename,
        "proposals": proposals,
        "section_edits": edits,
        "unparsed": unparsed,
        "counts": {"ready": ready, "needs_look": look, "couldnt_read": len(unparsed)},
    }


# --------------------------------------------------------------------------- presets


async def _event_index(session: AsyncSession, ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    wanted = list({int(i) for i in ids})
    if not wanted:
        return {}
    q = (
        select(MeetingRequest.id, Course.code, Section.label, Program.canonical_name)
        .join(Section, Section.id == MeetingRequest.section_id)
        .join(Course, Course.id == Section.course_id)
        .outerjoin(Program, Program.id == Section.program_id)
        .where(MeetingRequest.id.in_(wanted))
    )
    out: dict[int, dict[str, Any]] = {
        i: {"code": c, "label": lbl, "program": p} for i, c, lbl, p in (await session.execute(q)).all()
    }
    qe = select(ExamRequest.id, ExamRequest.course_code).where(ExamRequest.id.in_([i for i in wanted if i not in out]))
    for i, c in (await session.execute(qe)).all():
        out[i] = {"code": canon_course_code(c) or c, "label": None, "program": None, "exam": True}
    return out


async def to_portable(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    """Ids -> names so a preset transfers across terms."""
    p = {k: v for k, v in (params or {}).items() if not str(k).startswith("_")}
    rooms = {r.id: r.code for r in (await session.execute(select(Room))).scalars()}
    if "room_ids" in p:
        p["room_codes"] = [rooms.get(int(r), f"#{r}") for r in p.pop("room_ids") or []]
    if "room_id" in p and p["room_id"] is not None:
        p["room_code"] = rooms.get(int(p.pop("room_id")), None)
    if "event_ids" in p:
        idx = await _event_index(session, p.pop("event_ids") or [])
        seen: list[dict[str, Any]] = []
        for ref in idx.values():
            if ref not in seen:
                seen.append(ref)
        p["courses"] = seen
    for key in ("instructor", "instructors"):
        if key in p:
            vals = p.pop(key)
            vals = [vals] if isinstance(vals, str) else list(vals or [])
            ids = [int(v[4:]) for v in vals if str(v).startswith("INS:") and str(v)[4:].isdigit()]
            names = {
                i.id: i.canonical_name
                for i in (await session.execute(select(Instructor).where(Instructor.id.in_(ids)))).scalars()
            }
            p["instructor_names"] = [names[i] for i in ids if i in names]
    return p


async def from_portable(
    session: AsyncSession, term_id: int, params: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Names -> ids in ``term_id``; returns (params, problems)."""
    p = dict(params or {})
    problems: list[str] = []
    if "room_codes" in p:
        codes = [str(c).replace(" ", "").upper() for c in p.pop("room_codes") or []]
        found = {r.code: r.id for r in (await session.execute(select(Room).where(Room.code.in_(codes)))).scalars()}
        problems += [f"room {c} not found" for c in codes if c not in found]
        p["room_ids"] = [found[c] for c in codes if c in found]
    if "room_code" in p:
        code = str(p.pop("room_code") or "").replace(" ", "").upper()
        rid = (await session.execute(select(Room.id).where(Room.code == code))).scalar_one_or_none()
        if rid is None:
            problems.append(f"room {code} not found")
        else:
            p["room_id"] = rid
    if "courses" in p:
        refs = p.pop("courses") or []
        ids: list[int] = []
        for ref in refs:
            code = canon_course_code(ref.get("code")) or ref.get("code")
            if ref.get("exam"):
                q = select(ExamRequest.id).where(ExamRequest.term_id == term_id, ExamRequest.course_code == code)
            else:
                q = (
                    select(MeetingRequest.id)
                    .join(Section, Section.id == MeetingRequest.section_id)
                    .join(Course, Course.id == Section.course_id)
                    .outerjoin(Program, Program.id == Section.program_id)
                    .where(Section.term_id == term_id, Course.code == code, MeetingRequest.archived.is_(False))
                )
                if ref.get("label") is not None:
                    q = q.where(Section.label == ref["label"])
                if ref.get("program") is not None:
                    q = q.where(Program.canonical_name == ref["program"])
            hit = list((await session.execute(q)).scalars())
            if not hit:
                sec_label = f" §{ref['label']}" if ref.get("label") else ""
                problems.append(f"course {ref.get('code')}{sec_label} not in this term")
            ids += hit
        p["event_ids"] = sorted(set(ids))
    if "instructor_names" in p:
        names = list(p.pop("instructor_names") or [])
        found2 = {
            i.canonical_name: i.id
            for i in (await session.execute(select(Instructor).where(Instructor.canonical_name.in_(names)))).scalars()
        }
        problems += [f"instructor {n} not found" for n in names if n not in found2]
        p["instructors"] = [f"INS:{found2[n]}" for n in names if n in found2]
    return p, problems


async def _author(session: AsyncSession, uid: int | None) -> str | None:
    if uid is None:
        return None
    u = await session.get(User, uid)
    return (u.full_name or u.email) if u else None


async def preset_out(session: AsyncSession, p: StudioPreset) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "kind": p.kind,
        "rules": list(p.rules or []),
        "scope": dict(p.scope or {}),
        "filters": dict(p.filters or {}),
        "disabled_builtin_kinds": list(p.disabled_builtin_kinds or []),
        "created_by": p.created_by,
        "author": await _author(session, p.created_by),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _check_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, r in enumerate(rules):
        kind = str(r.get("kind") or "")
        if kind not in catalog.KINDS:
            raise st.StudioError(422, f"rule {i}: unknown kind {kind!r}")
        hardness = str(r.get("hardness") or catalog.KINDS[kind].default_hardness)
        if hardness not in catalog.KINDS[kind].allowed_hardness:
            raise st.StudioError(422, f"rule {i}: {kind} cannot be {hardness}")
        out.append(
            {
                "kind": kind,
                "params": dict(r.get("params") or {}),
                "hardness": hardness,
                "weight": max(1, min(10, int(r.get("weight") or WEIGHT_SCALE["normal"]))),
                "enabled": bool(r.get("enabled", True)),
                "nl_text": r.get("nl_text"),
            }
        )
    return out


def _check_filters(filters: dict[str, Any]) -> dict[str, Any]:
    allowed = {"program", "faculty", "class_year", "day", "building", "mode", "status", "q", "needs_room"}
    out: dict[str, Any] = {}
    for key in ("exclude", "include_only"):
        f = filters.get(key)
        if f is None:
            continue
        bad = [k for k in f if k not in allowed]
        if bad:
            raise st.StudioError(422, f"unknown filter key(s) {bad}; allowed: {sorted(allowed)}")
        out[key] = dict(f)
    return out


async def create_preset(session: AsyncSession, body: Any, user: User) -> StudioPreset:
    rules = _check_rules(body.rules or [])
    scope = dict(body.scope or {})
    builtins = list(body.disabled_builtin_kinds or [])
    if body.from_term_id is not None:
        draft = await st.get_draft(session, body.from_term_id, user.id, body.kind)
        for r in await st.term_rules(session, body.from_term_id, enabled_only=False):
            off = r.id in {int(i) for i in draft.disabled_rule_ids or []}
            ov = (draft.rule_overrides or {}).get(str(r.id)) or {}
            rules.append(
                {
                    "kind": r.kind,
                    "params": await to_portable(session, dict(r.params or {})),
                    "hardness": ov.get("hardness") or r.hardness,
                    "weight": int(ov.get("weight") or r.weight),
                    "enabled": bool(r.enabled and not off),
                    "nl_text": r.nl_text,
                }
            )
        scope = scope or {"horizon": draft.horizon, "horizon_params": dict(draft.horizon_params or {})}
        builtins = builtins or await st.disabled_builtins(session, draft)
    bad = [k for k in builtins if not st.BUILTINS.get(k)]
    if bad:
        raise st.StudioError(422, f"built-in rule(s) {bad} cannot be switched off")
    if scope.get("horizon") and scope["horizon"] not in st.HORIZONS:
        raise st.StudioError(422, f"horizon must be one of {st.HORIZONS}")
    p = StudioPreset(
        name=body.name,
        description=body.description,
        kind=body.kind,
        rules=rules,
        scope=scope,
        filters=_check_filters(body.filters or {}),
        disabled_builtin_kinds=sorted(set(builtins)),
        created_by=user.id,
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


async def update_preset(session: AsyncSession, p: StudioPreset, body: Any) -> StudioPreset:
    data = body.model_dump(exclude_unset=True)
    if data.get("rules") is not None:
        p.rules = _check_rules(data["rules"])
    if data.get("filters") is not None:
        p.filters = _check_filters(data["filters"])
    if data.get("disabled_builtin_kinds") is not None:
        bad = [k for k in data["disabled_builtin_kinds"] if not st.BUILTINS.get(k)]
        if bad:
            raise st.StudioError(422, f"built-in rule(s) {bad} cannot be switched off")
        p.disabled_builtin_kinds = sorted(set(data["disabled_builtin_kinds"]))
    for key in ("name", "description", "scope"):
        if key in data and data[key] is not None:
            setattr(p, key, data[key])
    await session.commit()
    await session.refresh(p)
    return p


async def _filter_ids(session: AsyncSession, draft: StudioDraft, f: dict[str, Any]) -> set[int]:
    from app.services import studio_classes as sc

    filt = sc.ClassFilters(
        class_year=f.get("class_year"),
        day=f.get("day"),
        building=f.get("building"),
        mode=f.get("mode"),
        status=f.get("status"),
        needs_room=f.get("needs_room"),
        q=f.get("q"),
    )
    if f.get("program"):
        pid = (
            await session.execute(select(Program.id).where(Program.canonical_name == f["program"]))
        ).scalar_one_or_none()
        filt.program_id = pid if pid is not None else -1
    if f.get("faculty"):
        fid = (
            await session.execute(select(Faculty.id).where(Faculty.canonical_name == f["faculty"]))
        ).scalar_one_or_none()
        filt.faculty_id = fid if fid is not None else -1
    page = await sc.class_page(session, draft, filt, limit=100000, offset=0)
    return {int(r["id"]) for r in page["items"]}


async def apply_preset(
    session: AsyncSession, p: StudioPreset, term_id: int, dry_run: bool, user: User
) -> dict[str, Any]:
    term = await st.get_term(session, term_id)
    draft = await st.get_draft(session, term.id, user.id, p.kind)
    existing = await st.term_rules(session, term.id, enabled_only=False)
    by_key = {(r.kind, _norm(r.params)): r for r in existing}
    add: list[dict[str, Any]] = []
    change: list[dict[str, Any]] = []
    turn_off: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for i, rule in enumerate(p.rules or []):
        params, problems = await from_portable(session, term.id, dict(rule.get("params") or {}))
        if (
            problems
            and not any(params.get(k) for k in ("event_ids", "room_ids", "room_id", "instructors"))
            and any(k in (rule.get("params") or {}) for k in ("courses", "room_codes", "room_code", "instructor_names"))
        ):
            unresolved.append({"index": i, "kind": rule["kind"], "problems": problems, "nl_text": rule.get("nl_text")})
            continue
        match = by_key.get((rule["kind"], _norm(params)))
        entry = {
            "index": i,
            "kind": rule["kind"],
            "params": params,
            "hardness": rule["hardness"],
            "weight": rule["weight"],
            "nl_text": rule.get("nl_text"),
            "problems": problems,
        }
        if match is None:
            if rule.get("enabled", True):
                add.append(entry)
            continue
        entry["constraint_id"] = match.id
        if not rule.get("enabled", True):
            if match.enabled and match.id not in {int(x) for x in draft.disabled_rule_ids or []}:
                turn_off.append(entry)
        elif (match.hardness, match.weight) != (rule["hardness"], rule["weight"]):
            entry["from"] = {"hardness": match.hardness, "weight": match.weight}
            change.append(entry)
    excluded: set[int] | None = None
    filters = p.filters or {}
    if filters.get("include_only") or filters.get("exclude"):
        everything = await _filter_ids(session, draft, {})
        excluded = set()
        if filters.get("include_only"):
            excluded |= everything - await _filter_ids(session, draft, filters["include_only"])
        if filters.get("exclude"):
            excluded |= await _filter_ids(session, draft, filters["exclude"])
    builtins = list(p.disabled_builtin_kinds or [])
    if builtins and user.role != "ADMIN":
        unresolved.append({"index": None, "kind": "builtin", "problems": [f"only an ADMIN can switch off {builtins}"]})
        builtins_apply: list[str] | None = None
    else:
        builtins_apply = builtins
    created: list[int] = []
    if not dry_run:
        for e in add:
            row = ConstraintRow(
                term_id=term.id,
                kind=e["kind"],
                params=e["params"],
                hardness=e["hardness"],
                weight=e["weight"],
                source="ADMIN",
                source_ref={"preset_id": p.id, "preset": p.name},
                nl_text=e.get("nl_text"),
                enabled=True,
                created_by=user.id,
            )
            session.add(row)
            await session.flush()
            created.append(row.id)
        ov = dict(draft.rule_overrides or {})
        for e in change:
            ov[str(e["constraint_id"])] = {"hardness": e["hardness"], "weight": e["weight"]}
        draft.rule_overrides = ov
        draft.disabled_rule_ids = sorted(
            {*(int(x) for x in draft.disabled_rule_ids or []), *(e["constraint_id"] for e in turn_off)}
        )
        if p.scope.get("horizon"):
            draft.horizon = p.scope["horizon"]
            draft.horizon_params = dict(p.scope.get("horizon_params") or {})
        if excluded is not None:
            draft.excluded_event_ids = sorted(excluded)
        if builtins_apply is not None:
            await st.set_disabled_builtins(session, draft, sorted(set(builtins_apply)), user.id)
        draft.preset_id = p.id
        await st.bump(session, draft)
        await st.commit_draft(session, draft)
        await session.refresh(draft)
    return {
        "add": add,
        "change": change,
        "turn_off": turn_off,
        "unresolved": unresolved,
        "scope": dict(p.scope or {}) or None,
        "excluded_count": len(excluded) if excluded is not None else len(draft.excluded_event_ids or []),
        "dry_run": dry_run,
        "created": created,
        "draft": None if dry_run else await st.draft_out(session, draft),
    }


async def list_presets(session: AsyncSession, kind: str | None) -> list[StudioPreset]:
    q = select(StudioPreset).order_by(StudioPreset.name, StudioPreset.id)
    if kind:
        q = q.where(StudioPreset.kind == kind)
    return list((await session.execute(q)).scalars())


__all__ = [
    "MAX_MAPPING_BYTES",
    "TEMPLATES",
    "WEIGHT_SCALE",
    "accept",
    "apply_preset",
    "copy_rules",
    "create_preset",
    "from_portable",
    "list_presets",
    "mapping_fallback",
    "meta",
    "preset_out",
    "preview",
    "rules_for_draft",
    "to_portable",
    "update_preset",
]
