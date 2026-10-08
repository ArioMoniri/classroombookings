"""AI-layer fixtures: a tiny seeded term + run and a scripted stand-in for ``anthropic.AsyncAnthropic``.

The fake records every request (kwargs) and answers with queued responses, so tests can assert both
what we send to the API (strict tools, model, no forced tool_choice) and how we treat what comes back.
"""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pytest
from app.models import (
    Assignment,
    Course,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    Week,
)

_ids = itertools.count(1)


@dataclass
class Block:
    type: str
    text: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def model_dump(self, **_: Any) -> dict[str, Any]:
        if self.type == "text":
            return {"type": "text", "text": self.text}
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


@dataclass
class Usage:
    input_tokens: int = 120
    output_tokens: int = 40
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Message:
    content: list[Block]
    stop_reason: str = "end_turn"
    model: str = "claude-opus-5-5"
    usage: Usage = field(default_factory=Usage)
    stop_details: Any = None
    _request_id: str = "req_test"


def text(t: str) -> Message:
    return Message([Block("text", text=t)])


def tool(name: str, inp: dict[str, Any], *, say: str = "") -> Message:
    blocks = ([Block("text", text=say)] if say else []) + [
        Block("tool_use", name=name, input=inp, id=f"toolu_{next(_ids)}")
    ]
    return Message(blocks, stop_reason="tool_use")


def tools(*calls: tuple[str, dict[str, Any]]) -> Message:
    return Message(
        [Block("tool_use", name=n, input=i, id=f"toolu_{next(_ids)}") for n, i in calls], stop_reason="tool_use"
    )


class _Endpoint:
    def __init__(self, owner: FakeSDK, beta: bool) -> None:
        self.owner, self.beta = owner, beta

    async def create(self, **kwargs: Any) -> Message:
        self.owner.calls.append({"beta": self.beta, **copy.deepcopy(kwargs)})  # snapshot: callers mutate lists
        if not self.owner.script:
            raise AssertionError("fake SDK: no scripted response left")
        nxt = self.owner.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class _NS:
    def __init__(self, messages: _Endpoint) -> None:
        self.messages = messages


class FakeSDK:
    """Replacement for ``anthropic.AsyncAnthropic`` (constructor signature compatible)."""

    instances: list[FakeSDK] = []
    script: list[Any] = []
    calls: list[dict[str, Any]] = []

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        self.api_key = api_key
        self.kwargs = kwargs
        self.messages = _Endpoint(self, beta=False)
        self.beta = _NS(_Endpoint(self, beta=True))
        FakeSDK.instances.append(self)


@pytest.fixture
def fake_sdk(monkeypatch):
    import anthropic

    FakeSDK.instances, FakeSDK.script, FakeSDK.calls = [], [], []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeSDK)
    return FakeSDK


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------


@dataclass
class Seed:
    term_id: int
    run_id: int
    rooms: dict[str, int]
    mr: dict[str, int]  # course code -> meeting request id
    sections: dict[str, int]
    assignments: dict[str, int]  # course code -> assignment id
    programs: dict[str, int]


async def seed_small(session) -> Seed:
    """3 courses, 5 rooms, one feasible run (Mon/Tue/Wed), 14 weeks starting 2026-02-09."""
    term = Term(code="2026-BAHAR", name="2025-2026 Bahar", start_date=date(2026, 2, 9), week_count=14, is_active=True)
    session.add(term)
    await session.flush()
    for i in range(1, 15):
        session.add(Week(term_id=term.id, index=i, start_date=date(2026, 2, 9) + timedelta(weeks=i - 1)))
    rooms = {
        "A206": Room(code="A206", display_name="A 206", capacity=60, exam_capacity=30),
        "A204": Room(code="A204", display_name="A 204", capacity=156, exam_capacity=80),
        "A101": Room(code="A101", display_name="A 101", capacity=20, exam_capacity=10),
        "C301": Room(code="C301", display_name="C 301", capacity=80, exam_capacity=40),
        "A201": Room(code="A201", display_name="A 201", capacity=90, exam_capacity=45, tags=["TIP"]),
    }
    programs = {
        "eczacılık": Program(name="Eczacılık", canonical_name="eczacılık"),
        "psikoloji": Program(name="Psikoloji", canonical_name="psikoloji"),
        "hemşirelik": Program(name="Hemşirelik", canonical_name="hemşirelik"),
    }
    courses = {
        "PHAR240": Course(code="PHAR240", display_code="PHAR 240", name="Pharmacology"),
        "PSI101": Course(code="PSI101", display_code="PSI 101", name="Intro Psychology"),
        "NRS450": Course(code="NRS450", display_code="NRS 450", name="Nursing Practice"),
    }
    inst = Instructor(full_name="Ayşe Yılmaz", canonical_name="ayşe yılmaz")
    session.add_all([*rooms.values(), *programs.values(), *courses.values(), inst])
    await session.flush()
    spec = {  # code -> (program, year, enrolment, day, start, end, room)
        "PHAR240": ("eczacılık", 2, 50, 1, 2, 4, "A206"),
        "PSI101": ("psikoloji", 1, 70, 2, 1, 3, "A204"),
        "NRS450": ("hemşirelik", 4, 30, 3, 5, 6, "C301"),
    }
    sections: dict[str, int] = {}
    mrs: dict[str, int] = {}
    secs: dict[str, Section] = {}
    for code, (prog, year, enrol, *_rest) in spec.items():
        sec = Section(
            term_id=term.id,
            course_id=courses[code].id,
            program_id=programs[prog].id,
            label="1",
            class_year=year,
            class_years=[year],
            enrolment=enrol,
            source_key=f"test:{code}",
        )
        session.add(sec)
        secs[code] = sec
    await session.flush()
    session.add(SectionInstructor(section_id=secs["PSI101"].id, instructor_id=inst.id))
    for code, (_p, _y, _e, day, sp, ep, _room) in spec.items():
        mr = MeetingRequest(section_id=secs[code].id, day=day, days=[day], start_period=sp, end_period=ep, weeks=[])
        session.add(mr)
        await session.flush()
        mrs[code] = mr.id
        sections[code] = secs[code].id
    run = ScheduleRun(
        term_id=term.id,
        kind="COURSE",
        horizon="TERM",
        status="OPTIMAL",
        hard_score=100,
        soft_score=97,
        params={"time_limit_s": 10, "workers": 2},
        stats={"objective_breakdown": {"min_capacity_waste": 3}, "events": 3, "rooms": 5, "assignments": 3},
        diagnosis=[],
    )
    session.add(run)
    await session.flush()
    assigns: dict[str, int] = {}
    for code, (_p, _y, _e, day, sp, ep, room) in spec.items():
        a = Assignment(
            run_id=run.id,
            meeting_request_id=mrs[code],
            weeks=list(range(1, 15)),
            day=day,
            start_period=sp,
            end_period=ep,
            room_ids=[rooms[room].id],
            origin="SOLVER",
        )
        session.add(a)
        await session.flush()
        assigns[code] = a.id
    await session.commit()
    return Seed(
        term.id,
        run.id,
        {k: r.id for k, r in rooms.items()},
        mrs,
        sections,
        assigns,
        {k: p.id for k, p in programs.items()},
    )


@pytest.fixture
async def seed(session) -> Seed:
    return await seed_small(session)


async def store_key(session, key: str = "sk-ant-test-key-0000") -> None:
    from app.services import settings_service as ss

    await ss.set_value(session, "anthropic_api_key", key)


def empty_selector(**kw: Any) -> dict[str, Any]:
    return {
        "course_codes": [],
        "program_name": "",
        "class_years": [],
        "instructor_name": "",
        "match": "",
        "kinds": [],
        **kw,
    }


def empty_params(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "room_codes": [],
        "buildings": [],
        "required_tags": [],
        "forbidden_tags": [],
        "days": [],
        "periods": [],
        "earliest": 0,
        "latest": 0,
        "weeks": [],
        "from_date": "",
        "to_date": "",
        "last_n_weeks": 0,
        "amount": 0,
        "label": "",
    }
    return {**base, **kw}


def proposal(kind: str, hardness: str = "hard", *, selector=None, params=None, **kw: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "hardness": hardness,
        "weight": kw.pop("weight", 0 if hardness == "hard" else 5),
        "title": kw.pop("title", kind),
        "nl_text": kw.pop("nl_text", ""),
        "rationale": kw.pop("rationale", "test"),
        "confidence": kw.pop("confidence", 0.9),
        "source_ref": kw.pop("source_ref", 0),
        "selector": selector or empty_selector(),
        "params": params or empty_params(),
    }


def section_edit(op: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "op": op,
        "section_ids": [],
        "course_codes": [],
        "program_name": "",
        "section_label": "",
        "enrolment": 0,
        "day": 0,
        "start_period": 0,
        "end_period": 0,
        "mode": "",
        "preferred_room_codes": [],
        "nl_text": "",
        "rationale": "",
        "confidence": 0.9,
        "source_ref": 0,
    }
    return {**base, **kw}
