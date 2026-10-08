"""Studio pre-check (step 4): the solver's static checker plus cheap rule checks on the draft's input,
turned into plain-language TR/EN items with structured fixes that apply **into the draft**.

* ``static_check`` (``app.solver.diagnose``) runs on ``prepare(inp)`` - no CP-SAT search, well under a
  second for the 1 300-event Bahar term. Its diagnoses are classified by their structured ``code`` /
  ``params`` (never the wording) into groups (``capacity``, ``locked_ineligible``, ``locked_small``,
  ``instructor_clash``, ``pigeonhole`` ...). With the run defaults (``trust_locked_rooms``,
  ``fixed_conflicts_as_warnings``) planner-locked rooms that are too small and clashes between two
  fixed requests are *warnings* (the generator keeps them), not blockers.
* Rule checks: targeted rules that match no class, duplicates, room pin vs room ban contradictions.
* Fix actions (``FixOut.action.type``): ``exclude`` (left out of this draft), ``meeting_update``
  (class-list edit with snapshot, e.g. unlock + other rooms, students), ``exam_update`` (room count),
  ``rule_override`` (this draft only: make a rule a Try-to), ``rule_off`` (this draft only),
  ``builtin_off`` (ADMIN only). The unlock suggestion strings are parsed with
  :func:`app.services.diagnosis_fixes.parse_option` like the run-report fixes.

The last result is stored on the draft (``last_precheck``) so ``POST .../precheck/fix`` applies exactly
the option the planner saw.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers.normalize import PERIODS
from app.models import ConstraintRow, ExamRequest, Instructor, Room, StudioDraft, User
from app.services import settings_service as ss
from app.services import studio as st
from app.services.diagnosis_fixes import parse_option
from app.solver import model as sm

DAYS = {
    "tr": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
TITLES: dict[str, dict[str, str]] = {
    "capacity": {"tr": "Yeterince büyük derslik yok", "en": "No room is big enough"},
    "room_tags": {"tr": "Gerekli özellikte derslik yok", "en": "No room has what this class needs"},
    "room_pin": {"tr": "Sabitlendiği derslik yok", "en": "Pinned to a room that does not exist"},
    "no_room": {"tr": "Kullanılabilecek derslik kalmadı", "en": "No room can be used"},
    "blocked": {"tr": "Uygun derslikler o saatte dolu", "en": "Every suitable room is blocked at that time"},
    "no_time": {"tr": "Kurallara uyan bir saat yok", "en": "No time fits the rules"},
    "bad_time": {"tr": "Gün/saat ders çizelgesinin dışında", "en": "Day or time outside the timetable"},
    "out_of_horizon": {"tr": "Seçilen haftalarda değil", "en": "Not in the chosen weeks"},
    "cohort_clash": {"tr": "Aynı sınıfın dersleri çakışıyor", "en": "Two classes of the same group clash"},
    "instructor_clash": {"tr": "Öğretim elemanının iki dersi çakışıyor", "en": "An instructor has two classes at once"},
    "locked_overlap": {"tr": "İki kilitli ders aynı derslikte", "en": "Two locked classes share a room"},
    "locked_ineligible": {"tr": "Kilitli derslik uygun değil", "en": "The locked room does not fit"},
    "locked_small": {
        "tr": "Kilitli derslik beklenen öğrenci sayısından küçük",
        "en": "The locked room is smaller than the expected class",
    },
    "locked_tags": {"tr": "Kilitli dersliğin özellikleri uymuyor", "en": "The locked room lacks a required feature"},
    "locked_blocked": {"tr": "Kilitli ders dolu bir saatte", "en": "A locked class sits on a blocked slot"},
    "pigeonhole": {"tr": "Aynı saatte yeterli derslik yok", "en": "Not enough rooms at one time"},
    "rule_no_match": {"tr": "Kural hiçbir dersle eşleşmiyor", "en": "A rule matches no classes"},
    "rule_duplicate": {"tr": "İki kural aynı şeyi söylüyor", "en": "Two rules say the same thing"},
    "rule_conflict": {"tr": "İki kural birlikte doğru olamaz", "en": "Two rules can't both be true"},
    "utilisation": {"tr": "Derslikler çok dolu", "en": "Rooms are nearly full"},
    "other": {"tr": "Plan engeli", "en": "Something blocks the plan"},
}
CATEGORY = {
    "rule_no_match": "no_match",
    "rule_duplicate": "clash",
    "rule_conflict": "clash",
    "out_of_horizon": "info",
    "utilisation": "info",
}


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def _when(day: int | None, start: int | None, end: int | None, lang: str) -> str:
    parts = []
    if day and 1 <= day <= 7:
        parts.append(DAYS[lang][day - 1])
    if start and end and 1 <= start <= end <= len(PERIODS):
        parts.append(f"{PERIODS[start - 1].start:%H:%M}-{PERIODS[end - 1].end:%H:%M}")
    elif start and 1 <= start <= len(PERIODS):
        parts.append(f"{PERIODS[start - 1].start:%H:%M}")
    return " ".join(parts)


def _ev_when(e: sm.Event, lang: str) -> str:
    if e.locked is not None:
        return _when(e.locked.day, e.locked.start, e.locked.end, lang)
    end = (e.fixed_start + e.duration - 1) if e.fixed_start else None
    return _when(e.fixed_day, e.fixed_start, end, lang)


def _cohort_text(key: str, lang: str) -> str:
    m = re.match(r"PROG:(?P<p>.+):Y(?P<y>\d+)$", key)
    if not m:
        return key
    return f"{m['p']} {m['y']}. sınıf" if lang == "tr" else f"{m['p']} year {m['y']}"


def _item_id(*parts: Any) -> str:
    return "pc-" + hashlib.sha1(repr(parts).encode()).hexdigest()[:12]


class _Ctx:
    def __init__(
        self,
        din: st.DraftInput,
        rooms_by_id: dict[int, sm.Room],
        instructors: dict[int, str],
        display: dict[str, str] | None = None,
        names: dict[int, str] | None = None,
    ) -> None:
        self.din = din
        self.display = display or {}
        self.names = names or {}  # room id -> display name (every room, also ones without capacity)
        self.events = {e.id: e for e in din.inp.events}
        self.rooms = rooms_by_id
        self.instructors = instructors
        self.exam = any(e.kind == "exam" for e in din.inp.events)

    def label(self, eid: int) -> str:
        e = self.events.get(eid)
        return e.label if e else f"#{eid}"

    def requests(self, eid: int) -> list[int]:
        return list(self.din.members.get(eid, [eid]))

    def classes(self, ids: list[int]) -> list[dict[str, Any]]:
        out = []
        for eid in ids:
            e = self.events.get(eid)
            out.append(
                {
                    "event_id": eid,
                    "label": self.label(eid),
                    "request_ids": self.requests(eid),
                    "size": e.size if e else None,
                    "when": {"tr": _ev_when(e, "tr"), "en": _ev_when(e, "en")} if e else None,
                }
            )
        return out

    def fitting_rooms(self, e: sm.Event, limit: int = 3) -> list[sm.Room]:
        def cap(r: sm.Room) -> int:
            return r.exam_capacity if e.kind == "exam" else r.capacity

        fit = [r for r in self.rooms.values() if cap(r) >= e.size and e.required_tags <= r.tags]
        # TIP (medicine) rooms only when nothing else fits: the bridge keeps courses out of them
        plain = [r for r in fit if "TIP" not in r.tags or "TIP" in e.required_tags]
        return sorted(plain or fit, key=lambda r: (cap(r), r.code))[:limit]

    def show(self, code: str) -> str:
        """Display name of a canonical room code (``A204`` -> ``A 204``)."""
        return self.display.get(code, code)


def _fix(
    option: str, tr: str, en: str, type_: str, payload: dict[str, Any], admin_only: bool = False
) -> dict[str, Any]:
    return {
        "option": option,
        "label": _t(tr, en),
        "action": {"type": type_, "payload": payload},
        "admin_only": admin_only,
    }


def _exclude_fixes(ctx: _Ctx, ids: list[int], limit: int = 3) -> list[dict[str, Any]]:
    if len(ids) == 1:
        lab = ctx.label(ids[0])
        return [
            _fix(
                "exclude",
                f"{lab} bu planın dışında kalsın",
                f"Leave {lab} out of this plan",
                "exclude",
                {"request_ids": ctx.requests(ids[0])},
            )
        ]
    return [
        _fix(
            f"exclude:{eid}",
            f"{ctx.label(eid)} bu planın dışında kalsın",
            f"Leave {ctx.label(eid)} out of this plan",
            "exclude",
            {"request_ids": ctx.requests(eid)},
        )
        for eid in ids[:limit]
    ]


def _unlock_fix(ctx: _Ctx, eid: int, option: str = "unlock") -> dict[str, Any]:
    lab = ctx.label(eid)
    return _fix(
        option,
        f"{lab} kilidini aç (SmartSched derslik seçsin)",
        f"Unlock {lab} (let SmartSched pick the room)",
        "meeting_update" if not ctx.exam else "exam_update",
        {"request_ids": ctx.requests(eid), "patch": {"locked": False} if not ctx.exam else {"status": "PARSED"}},
    )


def _rooms_fix(ctx: _Ctx, e: sm.Event, unlock: bool) -> dict[str, Any] | None:
    fit = ctx.fitting_rooms(e)
    if not fit or ctx.exam:
        return None
    codes = ", ".join(ctx.show(r.code) for r in fit)
    patch: dict[str, Any] = {"requested_room_ids": [r.id for r in fit]}
    if unlock:
        patch["locked"] = False
    if all("TIP" in r.tags for r in fit):
        patch["requested_tags"] = sorted({*e.required_tags, "TIP"})
    return _fix(
        "rooms",
        f"{e.label} için {codes} dersliklerini kullan" + (" (kilidi aç)" if unlock else ""),
        f"Use {codes} for {e.label}" + (" (unlock it)" if unlock else ""),
        "meeting_update",
        {"request_ids": ctx.requests(e.id), "patch": patch},
    )


def _rule_relax_fixes(ctx: _Ctx, e: sm.Event, kinds: list[str]) -> list[dict[str, Any]]:
    from app.solver.constraints._common import select_events

    out = []
    for c in ctx.din.inp.constraints:
        if c.id is None or not c.hard or c.kind not in kinds:
            continue
        if e.id not in {x.id for x in select_events(ctx.din.inp, c.params)}:
            continue
        out.append(
            _fix(
                f"soften:{c.id}",
                f"Kural #{c.id} ({c.kind}) bu planda 'mümkünse' olsun",
                f"Make rule #{c.id} ({c.kind}) a Try-to in this plan",
                "rule_override",
                {"constraint_id": c.id, "hardness": "soft"},
            )
        )
    return out[:3]


def _from_diagnosis(ctx: _Ctx, d: sm.Diagnosis) -> dict[str, Any]:
    """Classify by the solver's structured ``code`` / ``params`` (never by the wording)."""
    msg = d.message
    code = d.code
    prm = d.params or {}
    ids = [int(i) for i in d.event_ids]
    e = ctx.events.get(ids[0]) if ids else None
    lab = ctx.label(ids[0]) if ids else ""
    group = "other"
    message = _t(msg, msg)
    fixes: list[dict[str, Any]] = []
    severity = d.severity if d.severity in ("error", "warning", "info") else "error"
    if code == "bad_time":
        group = "bad_time"
        message = _t(
            f"{lab} çizelgenin dışında bir gün/saate yazılmış.", f"{lab} is set to a day or time outside the timetable."
        )
        fixes = _exclude_fixes(ctx, ids)
    elif code == "out_of_horizon":
        group, severity = "out_of_horizon", "info"
        message = _t(f"{lab} seçilen haftalarda hiç yapılmıyor.", f"{lab} does not meet in the chosen weeks.")
    elif code == "no_time":
        group = "no_time"
        why = "; ".join(str(k) for k in (prm.get("reasons") or {})) or "-"
        message = _t(
            f"{lab} için kurallara uyan bir saat kalmadı ({why}).",
            f"{lab} has no time left that the rules allow ({why}).",
        )
        fixes = (_rule_relax_fixes(ctx, e, d.constraint_kinds) if e else []) + _exclude_fixes(ctx, ids)
    elif code == "no_room" and e is not None:
        reason = prm.get("reason")
        if reason == "tags":
            group = "room_tags"
            missing = {str(t) for t in prm.get("missing_tags") or []}
            tags = ", ".join(sorted(missing))
            message = _t(
                f"{lab} {tags} özellikli bir derslik istiyor ama hiçbir derslikte bu özellik yok.",
                f"{lab} needs a room tagged {tags}, but no room has that tag.",
            )
            if not ctx.exam:
                fixes.append(
                    _fix(
                        "drop_tag",
                        f"{lab} için {tags} şartını kaldır",
                        f"Drop the {tags} requirement for {lab}",
                        "meeting_update",
                        {
                            "request_ids": ctx.requests(e.id),
                            "patch": {"requested_tags": sorted(e.required_tags - missing)},
                        },
                    )
                )
        elif reason == "pin":
            group = "room_pin"
            message = _t(f"{lab} olmayan bir dersliğe sabitlenmiş.", f"{lab} is pinned to a room that does not exist.")
        elif reason == "capacity" and prm.get("largest_room"):
            group = "capacity"
            cap, best = int(prm["largest_capacity"]), ctx.show(str(prm["largest_room"]))
            message = _t(
                f"{lab}: {e.size} öğrenci var ama kullanılabilecek en büyük derslik {best} ({cap} kişilik).",
                f"{lab}: {e.size} students, but the largest room it may use is {best} ({cap} seats).",
            )
            rf = _rooms_fix(ctx, e, unlock=False)
            if rf:
                fixes.append(rf)
            if ctx.exam:
                fixes.append(
                    _fix(
                        "split",
                        f"{lab} sınavı en fazla 3 salona bölünebilsin",
                        f"Let the {lab} exam split across up to 3 rooms",
                        "exam_update",
                        {"request_ids": ctx.requests(e.id), "patch": {"requested_room_count": 3}},
                    )
                )
            else:
                biggest = max((r.capacity for r in ctx.rooms.values()), default=0)
                if biggest and biggest < e.size and len(ctx.requests(e.id)) == 1:
                    fixes.append(
                        _fix(
                            "cap_enrolment",
                            f"Öğrenci sayısını {biggest} yap (en büyük derslik)",
                            f"Set students to {biggest} (largest room)",
                            "meeting_update",
                            {"request_ids": ctx.requests(e.id), "patch": {"enrolment": biggest}},
                        )
                    )
        else:
            group = "no_room"
            why = "; ".join(str(k) for k in (prm.get("reasons") or {})) or "-"
            message = _t(
                f"{lab} için kurallardan sonra hiç derslik kalmadı ({why}).",
                f"{lab} has no room left after the rules ({why}).",
            )
            rf = _rooms_fix(ctx, e, unlock=e.locked is not None)
            if rf:
                fixes.append(rf)
            if e.locked is not None:
                fixes.append(_unlock_fix(ctx, e.id))
            fixes += _rule_relax_fixes(ctx, e, [k for k in d.constraint_kinds if k != "capacity"])
        fixes += _exclude_fixes(ctx, ids)
    elif code == "all_blocked":
        group = "blocked"
        message = _t(
            f"{lab} için uygun bütün derslikler o saatte dolu ({_ev_when(e, 'tr') if e else ''}).",
            f"Every suitable room is blocked when {lab} meets ({_ev_when(e, 'en') if e else ''}).",
        )
        fixes = _exclude_fixes(ctx, ids)
    elif code in ("fixed_conflict", "input_conflict") and len(ids) == 2:
        a, b = ctx.label(ids[0]), ctx.label(ids[1])
        when_tr = _ev_when(e, "tr") if e else ""
        when_en = _ev_when(e, "en") if e else ""
        keys = [(str(k), str(v)) for k, v in prm.get("keys") or []]
        ins_key = next((v for k, v in keys if k == "no_instructor_overlap"), None)
        note_tr = " Girdi çakışması: ikisi de saatini korur." if code == "input_conflict" else ""
        note_en = " Input conflict: both keep their times." if code == "input_conflict" else ""
        if ins_key is None:
            group = "cohort_clash"
            key = next((v for k, v in keys if k == "no_cohort_overlap"), str(prm.get("key", "")))
            message = _t(
                f"{a} ve {b} aynı saatte ({when_tr}) ve ikisi de {_cohort_text(key, 'tr')} dersi.{note_tr}",
                f"{a} and {b} are fixed at the same time ({when_en}) for {_cohort_text(key, 'en')}.{note_en}",
            )
            fixes = _exclude_fixes(ctx, ids, 2) + [
                _fix(
                    "builtin_off:no_cohort_overlap",
                    "Bu planda sınıf çakışması kontrolünü kapat",
                    "Turn off the programme-year clash check in this plan",
                    "builtin_off",
                    {"kind": "no_cohort_overlap"},
                    admin_only=True,
                )
            ]
        else:
            group = "instructor_clash"
            name = ins_key
            if ins_key.startswith("INS:") and ins_key[4:].isdigit():
                name = ctx.instructors.get(int(ins_key[4:]), ins_key)
            message = _t(
                f"{a} ve {b} aynı saatte ({when_tr}) ve aynı öğretim elemanının ({name}) dersi.{note_tr}",
                f"{a} and {b} are fixed at the same time ({when_en}) and share an instructor ({name}).{note_en}",
            )
            fixes = _exclude_fixes(ctx, ids, 2) + [
                _fix(
                    "builtin_off:no_instructor_overlap",
                    "Bu planda öğretim elemanı çakışması kontrolünü kapat",
                    "Turn off the instructor clash check in this plan",
                    "builtin_off",
                    {"kind": "no_instructor_overlap"},
                    admin_only=True,
                )
            ]
    elif code == "locked_overlap" and len(ids) >= 2:
        group = "locked_overlap"
        room = " + ".join(ctx.show(str(c)) for c in prm.get("room_codes") or []) or "?"
        day = prm.get("day")
        p = prm.get("period")
        names_tr = " ve ".join(ctx.label(i) for i in ids[:4])
        names_en = " and ".join(ctx.label(i) for i in ids[:4])
        if prm.get("shared"):
            message = _t(
                f"{names_tr} {room} salonlarını {_when(day, p, p, 'tr')} saatinde paylaşıyor ama "
                f"{prm.get('need')} kişi için yalnızca {prm.get('seats')} yer var.",
                f"{names_en} share {room} on {_when(day, p, p, 'en')} but need {prm.get('need')} seats and the "
                f"rooms seat {prm.get('seats')}.",
            )
        else:
            message = _t(
                f"{names_tr} ikisi de {room} dersliğine {_when(day, p, p, 'tr')} saatinde kilitli.",
                f"{names_en} are both locked in {room} on {_when(day, p, p, 'en')}.",
            )
        opts = [parse_option(j, s, asdict(d)) for j, s in enumerate(d.suggestions)]
        if any(o.action == "unlock" for o in opts):
            fixes = [_unlock_fix(ctx, eid, f"unlock:{eid}") for eid in ids]
        fixes += _exclude_fixes(ctx, ids, 2)
    elif code in ("locked_ineligible", "trusted_lock_capacity", "trusted_lock_tags") and e is not None:
        group = {"locked_ineligible": "locked_ineligible", "trusted_lock_capacity": "locked_small"}.get(
            code, "locked_tags"
        )
        rooms = ", ".join(ctx.names.get(int(x), f"#{x}") for x in prm.get("rooms") or []) or "?"
        if code == "locked_ineligible":
            why = "; ".join(str(r) for r in prm.get("reasons") or [])
            message = _t(
                f"{lab} {rooms} dersliğine kilitli ama bu derslik kullanılamıyor ({why}).",
                f"{lab} is locked to {rooms}, which can't be used ({why}).",
            )
        elif code == "trusted_lock_capacity":
            message = _t(
                f"{lab} {prm.get('size')} öğrenci bekliyor ama {rooms} dersliğine ({prm.get('seats')} kişilik) "
                "kilitli; planlamacının dersliği korunur.",
                f"{lab} expects {prm.get('size')} students but is locked to {rooms} ({prm.get('seats')} seats); "
                "the planner's room is kept.",
            )
        else:
            tags = ", ".join(str(t) for t in [*(prm.get("missing_tags") or []), *(prm.get("forbidden_tags") or [])])
            message = _t(
                f"{lab} {rooms} dersliğine kilitli ama derslik özellikleri uymuyor ({tags}); derslik korunur.",
                f"{lab} is locked to {rooms}, whose tags don't match ({tags}); the room is kept.",
            )
        rf = _rooms_fix(ctx, e, unlock=True)
        if rf:
            fixes.append(rf)
        fixes.append(_unlock_fix(ctx, e.id))
        if code == "locked_ineligible":
            fixes += _exclude_fixes(ctx, ids)
    elif code == "locked_blocked":
        group = "locked_blocked"
        message = _t(
            f"{lab} dolu (bloklu) bir saate kilitli ({_ev_when(e, 'tr') if e else ''}).",
            f"{lab} is locked on a blocked slot ({_ev_when(e, 'en') if e else ''}).",
        )
        if ids:
            fixes = [_unlock_fix(ctx, ids[0])] + _exclude_fixes(ctx, ids)
    elif code == "pigeonhole":
        group = "pigeonhole"
        day, p, w = int(prm["day"]), int(prm["period"]), int(prm["week"])
        message = _t(
            f"{prm['n']} ders {_when(day, p, p, 'tr')} saatinde ({w}. hafta) derslik istiyor ama uygun yalnızca "
            f"{prm['rooms']} derslik var.",
            f"{prm['n']} classes need a room on {_when(day, p, p, 'en')} (week {w}) but only {prm['rooms']} suitable "
            "rooms exist.",
        )
        by_size = sorted(ids, key=lambda i: ctx.events[i].size if i in ctx.events else 0)
        fixes = _exclude_fixes(ctx, by_size, 3) if len(ids) > 1 else _exclude_fixes(ctx, ids)
    elif ids:
        fixes = _exclude_fixes(ctx, ids)
    return {
        "id": _item_id(group, tuple(ids), msg),
        "category": CATEGORY.get(group, "impossible" if severity == "error" else "info"),
        "severity": severity,
        "group": group,
        "title": TITLES.get(group, TITLES["other"]),
        "message": message,
        "detail": msg,
        "event_ids": ids,
        "classes": ctx.classes(ids[:12]),
        "constraint_kinds": list(d.constraint_kinds),
        "constraint_ids": [],
        "fixes": fixes,
    }


def _norm_params(p: dict[str, Any]) -> str:
    return repr(sorted((k, repr(v)) for k, v in p.items() if not str(k).startswith("_")))


def _rule_items(ctx: _Ctx, rows: dict[int, ConstraintRow]) -> list[dict[str, Any]]:
    from app.solver.constraints._common import is_targeted, select_events

    inp = ctx.din.inp
    items: list[dict[str, Any]] = []
    selected: dict[int, set[int]] = {}
    in_play = [c for c in inp.constraints if c.id is not None]
    for c in in_play:
        if is_targeted(c):
            selected[c.id] = {e.id for e in select_events(inp, c.params)}  # type: ignore[index]
    for c in in_play:
        cid = int(c.id)  # type: ignore[arg-type]
        if cid in selected and not selected[cid]:
            row = rows.get(cid)
            text = (row.nl_text if row and row.nl_text else c.kind) or c.kind
            items.append(
                {
                    "id": _item_id("rule_no_match", cid),
                    "category": "no_match",
                    "severity": "warning",
                    "group": "rule_no_match",
                    "title": TITLES["rule_no_match"],
                    "message": _t(
                        f"“{text}” hiçbir dersle eşleşmiyor; adı kontrol edin.",
                        f"“{text}” matches no classes; check the name.",
                    ),
                    "detail": f"rule #{cid} ({c.kind}) selects no event",
                    "event_ids": [],
                    "classes": [],
                    "constraint_kinds": [c.kind],
                    "constraint_ids": [cid],
                    "fixes": [
                        _fix(
                            "rule_off",
                            "Bu planda kuralı kapat",
                            "Turn the rule off in this plan",
                            "rule_off",
                            {"constraint_id": cid},
                        )
                    ],
                }
            )
    seen: dict[tuple[str, str, bool], int] = {}
    for c in in_play:
        key = (c.kind, _norm_params(dict(c.params)), c.hard)
        cid = int(c.id)  # type: ignore[arg-type]
        if key in seen:
            first = seen[key]
            items.append(
                {
                    "id": _item_id("rule_duplicate", first, cid),
                    "category": "clash",
                    "severity": "info",
                    "group": "rule_duplicate",
                    "title": TITLES["rule_duplicate"],
                    "message": _t(
                        f"Kural #{first} ve #{cid} aynı şeyi söylüyor.",
                        f"Rules #{first} and #{cid} say the same thing.",
                    ),
                    "detail": f"duplicate {c.kind}",
                    "event_ids": [],
                    "classes": [],
                    "constraint_kinds": [c.kind],
                    "constraint_ids": [first, cid],
                    "fixes": [
                        _fix(
                            f"rule_off:{cid}",
                            f"Kural #{cid} bu planda kapansın (birleştir)",
                            f"Turn rule #{cid} off in this plan (merge)",
                            "rule_off",
                            {"constraint_id": cid},
                        )
                    ],
                }
            )
        else:
            seen[key] = cid
    pins = [c for c in in_play if c.kind == "room_pin" and c.hard]
    bans = [c for c in in_play if c.kind == "room_forbid" and c.hard]
    for p in pins:
        for b in bans:
            pid, bid = int(p.id), int(b.id)  # type: ignore[arg-type]
            both = selected.get(pid, set()) & selected.get(bid, set())
            p_rooms = {int(r) for r in p.params.get("room_ids") or []}
            b_rooms = {int(r) for r in b.params.get("room_ids") or []}
            if both and p_rooms and p_rooms <= b_rooms:
                ids = sorted(both)
                items.append(
                    {
                        "id": _item_id("rule_conflict", pid, bid),
                        "category": "clash",
                        "severity": "error",
                        "group": "rule_conflict",
                        "title": TITLES["rule_conflict"],
                        "message": _t(
                            f"Kural #{pid} bu dersleri belirli dersliklere sabitliyor, kural #{bid} aynı derslikleri "
                            f"yasaklıyor ({len(ids)} ders).",
                            f"Rule #{pid} pins these classes to rooms that rule #{bid} forbids ({len(ids)} classes).",
                        ),
                        "detail": f"room_pin #{pid} vs room_forbid #{bid}",
                        "event_ids": ids[:50],
                        "classes": ctx.classes(ids[:12]),
                        "constraint_kinds": ["room_pin", "room_forbid"],
                        "constraint_ids": [pid, bid],
                        "fixes": [
                            _fix(
                                f"soften:{bid}",
                                f"Kural #{bid} bu planda 'mümkünse' olsun",
                                f"Make rule #{bid} a Try-to in this plan",
                                "rule_override",
                                {"constraint_id": bid, "hardness": "soft"},
                            ),
                            _fix(
                                f"rule_off:{pid}",
                                f"Kural #{pid} bu planda kapansın",
                                f"Turn rule #{pid} off in this plan",
                                "rule_off",
                                {"constraint_id": pid},
                            ),
                            _fix(
                                f"rule_off:{bid}",
                                f"Kural #{bid} bu planda kapansın",
                                f"Turn rule #{bid} off in this plan",
                                "rule_off",
                                {"constraint_id": bid},
                            ),
                        ],
                    }
                )
    return items


def _utilisation(ctx: _Ctx) -> list[dict[str, Any]]:
    """Room-periods needed vs available per week (Mon-Fri, 18 periods): an info item above 85 %."""
    inp = ctx.din.inp
    rooms = len(inp.rooms)
    if not rooms:
        return []
    need: dict[int, int] = defaultdict(int)
    for e in inp.events:
        if e.needs_room:
            for w in e.weeks:
                need[w] += max(1, e.duration) * max(1, e.min_rooms)
    supply = rooms * 5 * inp.periods_per_day
    worst = max(need.items(), key=lambda kv: kv[1], default=(None, 0))
    if worst[0] is None or worst[1] < 0.85 * supply:
        return []
    pct = round(100 * worst[1] / supply)
    return [
        {
            "id": _item_id("utilisation", worst[0], pct),
            "category": "info",
            "severity": "warning" if pct >= 100 else "info",
            "group": "utilisation",
            "title": TITLES["utilisation"],
            "message": _t(
                f"{worst[0]}. haftada derslik saatlerinin %{pct}'i gerekiyor (hafta içi).",
                f"Week {worst[0]} needs {pct}% of the room-hours available on weekdays.",
            ),
            "detail": f"week {worst[0]}: {worst[1]} room-periods needed, {supply} available",
            "event_ids": [],
            "classes": [],
            "constraint_kinds": [],
            "constraint_ids": [],
            "fixes": [],
        }
    ]


async def run_precheck(session: AsyncSession, draft: StudioDraft) -> dict[str, Any]:
    from app.solver.build import prepare
    from app.solver.diagnose import static_check

    t0 = time.perf_counter()
    din = await st.build_draft_input(session, draft)
    inp = din.inp
    instructors = {i.id: i.full_name for i in (await session.execute(select(Instructor))).scalars()}
    all_rooms = list((await session.execute(select(Room))).scalars())
    display = {r.code: r.display_name for r in all_rooms}
    ctx = _Ctx(din, {r.id: r for r in inp.rooms}, instructors, display, {r.id: r.display_name for r in all_rooms})
    items: list[dict[str, Any]] = []
    if inp.events:
        prep = prepare(inp)
        items = [_from_diagnosis(ctx, d) for d in static_check(prep)]
    rows = {r.id: r for r in await st.term_rules(session, draft.term_id)}
    items += _rule_items(ctx, rows)
    items += _utilisation(ctx)
    order = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda it: (order.get(it["severity"], 3), it["group"], it["event_ids"][:1]))
    dedup: dict[str, dict[str, Any]] = {}
    for it in items:
        dedup.setdefault(it["id"], it)
    items = list(dedup.values())
    errors = sum(1 for it in items if it["severity"] == "error")
    warnings = sum(1 for it in items if it["severity"] == "warning")
    readiness = "blocked" if errors else ("needs_look" if warnings or items else "ready")
    counts = {
        "impossible": sum(1 for it in items if it["category"] == "impossible"),
        "clash": sum(1 for it in items if it["category"] == "clash"),
        "no_match": sum(1 for it in items if it["category"] == "no_match"),
        "info": sum(1 for it in items if it["category"] == "info"),
        "errors": errors,
        "warnings": warnings,
        "events": len(inp.events),
        "rooms": len(inp.rooms),
        "blocked_classes": len({i for it in items if it["severity"] == "error" for i in it["event_ids"]}),
    }
    params = dict(draft.params or {})
    limit = float(params.get("time_limit_s") or await ss.get_value(session, "solver_default_time_limit") or 60)
    est = st.estimate_seconds(len(inp.events), len(inp.rooms), len(inp.weeks), limit)
    n = counts["blocked_classes"]
    if readiness == "ready":
        summary = _t("Hazır: imkânsız bir şey bulunmadı.", "Ready: nothing impossible found.")
    elif readiness == "needs_look":
        summary = _t(
            f"Bakılması gereken {len(items)} madde var; plan yine de oluşturulabilir.",
            f"{len(items)} things to look at; the plan can still be generated.",
        )
    else:
        summary = _t(
            f"{n} ders kesin kurallarınızla yerleştirilemiyor.",
            f"{n} classes can't be placed under your Must-rules.",
        )
    groups: dict[str, dict[str, Any]] = {}
    for it in items:
        g = groups.setdefault(
            it["group"], {"group": it["group"], "title": it["title"], "severity": it["severity"], "count": 0}
        )
        g["count"] += 1
    out = {
        "draft_id": draft.id,
        "version": draft.version,
        "readiness": readiness,
        "counts": counts,
        "groups": sorted(groups.values(), key=lambda g: (order.get(g["severity"], 3), -g["count"])),
        "items": items,
        "estimate_s": est,
        "summary": summary,
        "duration_s": round(time.perf_counter() - t0, 3),
    }
    draft.last_precheck = {
        "version": draft.version,
        "readiness": readiness,
        "computed_at": datetime.now(UTC).isoformat(),
        "items": {it["id"]: {"fixes": it["fixes"], "group": it["group"]} for it in items},
    }
    await session.commit()
    return out


async def apply_fix(session: AsyncSession, draft: StudioDraft, item_id: str, option: str, user: User) -> dict[str, Any]:
    pre = draft.last_precheck or {}
    if item_id not in (pre.get("items") or {}):
        await run_precheck(session, draft)
        pre = draft.last_precheck or {}
    item = (pre.get("items") or {}).get(item_id)
    if item is None:
        raise st.StudioError(404, "pre-check item not found (the plan changed); run the pre-check again")
    fix = next((f for f in item["fixes"] if f["option"] == option), None)
    if fix is None:
        raise st.StudioError(404, f"option {option!r} not offered for this item")
    if fix.get("admin_only") and user.role != "ADMIN":
        raise st.StudioError(403, "only an ADMIN can apply this fix")
    action = fix["action"]
    kind, payload = action["type"], action["payload"]
    if kind == "exclude":
        ids = [int(i) for i in payload["request_ids"]]
        draft.excluded_event_ids = list(dict.fromkeys([*(int(i) for i in draft.excluded_event_ids or []), *ids]))
    elif kind == "meeting_update":
        from app.schemas.studio import BulkEditIn, MeetingPatch
        from app.services import studio_classes as sc

        res = await sc.bulk_edit(
            session, BulkEditIn(ids=list(payload["request_ids"]), patch=MeetingPatch(**payload["patch"])), user
        )
        if res["failed"]:
            errs = [e for r in res["results"] for e in r["errors"]]
            raise st.StudioError(422, f"fix could not be applied: {'; '.join(errs[:3])}")
    elif kind == "exam_update":
        for rid in payload["request_ids"]:
            ex = await session.get(ExamRequest, int(rid))
            if ex is None or ex.term_id != draft.term_id:
                raise st.StudioError(404, f"exam request {rid} not found")
            for k, v in payload["patch"].items():
                if k in ("requested_room_count", "status"):
                    setattr(ex, k, v)
    elif kind == "rule_override":
        ov = dict(draft.rule_overrides or {})
        ov[str(payload["constraint_id"])] = {
            **ov.get(str(payload["constraint_id"]), {}),
            "hardness": payload["hardness"],
        }
        draft.rule_overrides = ov
    elif kind == "rule_off":
        draft.disabled_rule_ids = sorted(
            {*(int(i) for i in draft.disabled_rule_ids or []), int(payload["constraint_id"])}
        )
    elif kind == "builtin_off":
        kinds = sorted({*await st.disabled_builtins(session, draft), str(payload["kind"])})
        await st.set_disabled_builtins(session, draft, kinds, user.id)
    else:  # pragma: no cover - only produced by this module
        raise st.StudioError(422, f"unsupported fix type {kind}")
    await st.bump(session, draft)
    await session.commit()
    return {"item_id": item_id, "option": option, "type": kind, "payload": payload, "label": fix["label"]}


__all__ = ["apply_fix", "run_precheck"]
