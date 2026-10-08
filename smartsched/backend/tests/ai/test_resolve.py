from __future__ import annotations

from app.ai.resolve import (
    clean_sentinels,
    load_term_context,
    resolve_course,
    resolve_program,
    resolve_proposal,
    resolve_room,
    resolve_section_edit,
    split_program_and_years,
)

from tests.ai.conftest import empty_params, empty_selector, proposal, section_edit


async def test_room_names_resolve(session, seed):
    ctx = await load_term_context(session, seed.term_id)
    for text in ("A 206", "A206", "a206", "a-206"):
        ent = resolve_room(ctx, text)
        assert ent.resolved_id == seed.rooms["A206"], text
    missing = resolve_room(ctx, "Z 999")
    assert missing.resolved_id is None


async def test_programme_with_class_year(session, seed):
    ctx = await load_term_context(session, seed.term_id)
    assert split_program_and_years("Psikoloji 1. sınıf") == ("Psikoloji", [1])
    ent = resolve_program(ctx, "Psikoloji")
    assert ent.resolved_id == seed.programs["psikoloji"]
    assert resolve_program(ctx, "nursing").resolved_id == seed.programs["hemşirelik"]
    p = resolve_proposal(
        ctx,
        proposal(
            "room_forbid",
            selector=empty_selector(program_name="Psikoloji 1. sınıf"),
            params=empty_params(room_codes=["A 204"]),
            nl_text="Psikoloji 1. sınıf A 204'e girmesin",
        ),
    )
    assert p.status == "ok", p.issues
    assert p.params == {"cohorts": ["PROG:psikoloji:Y1"], "room_ids": [seed.rooms["A204"]]}


async def test_course_code_resolves_to_meeting_ids(session, seed):
    ctx = await load_term_context(session, seed.term_id)
    for text in ("PHAR 240", "phar240", "PHAR-240"):
        ent, ids = resolve_course(ctx, text)
        assert ent.resolved_label == "PHAR 240" and ids == [seed.mr["PHAR240"]], text
    p = resolve_proposal(
        ctx,
        proposal(
            "room_pin",
            selector=empty_selector(course_codes=["PHAR 240"]),
            params=empty_params(room_codes=["A 206"], from_date="2026-02-23"),
        ),
    )
    # from 23 Feb = week 3 of a term starting 9 Feb; room_pin honours weeks
    assert p.params["event_ids"] == [seed.mr["PHAR240"]]
    assert p.params["room_ids"] == [seed.rooms["A206"]]
    assert p.params["weeks"] == list(range(3, 15))
    assert any(e.type == "date" and e.resolved_id == 3 for e in p.entities)


async def test_unresolvable_names_need_review_with_candidates(session, seed):
    ctx = await load_term_context(session, seed.term_id)
    p = resolve_proposal(
        ctx,
        proposal(
            "room_pin",
            selector=empty_selector(course_codes=["PHAR 249"]),
            params=empty_params(room_codes=["A 207"]),
        ),
    )
    assert p.status == "needs_review"
    assert "event_ids" not in p.params and "room_ids" not in p.params  # never invented
    room = next(e for e in p.entities if e.type == "room")
    assert room.resolved_id is None and any(c["label"] == "A 206" for c in room.candidates)
    course = next(e for e in p.entities if e.type == "course")
    assert course.resolved_id is None and course.candidates and course.candidates[0]["label"] == "PHAR 240"
    assert p.confidence <= 0.4

    q = resolve_proposal(
        ctx, proposal("building_preference", "soft", selector=empty_selector(program_name="Astrofizik"))
    )
    assert q.status == "needs_review" and any("Astrofizik" in i for i in q.issues)

    bad = resolve_proposal(ctx, proposal("not_a_kind"))
    assert bad.status == "rejected"


async def test_hardness_rules_and_sentinels(session, seed):
    ctx = await load_term_context(session, seed.term_id)
    p = resolve_proposal(ctx, proposal("no_room_overlap", "soft"))
    assert p.hardness == "hard" and p.issues
    assert clean_sentinels({"a": "", "b": [], "c": 0, "d": False, "e": 3, "f": None}) == {"d": False, "e": 3}
    w = resolve_proposal(
        ctx,
        proposal(
            "day_window",
            "hard",
            selector=empty_selector(program_name="Hemşirelik", class_years=[4]),
            params=empty_params(latest=11),
        ),
    )
    assert w.status == "ok" and w.params == {"cohorts": ["PROG:hemşirelik:Y4"], "latest": 11}


async def test_section_edit_resolution(session, seed):
    ctx = await load_term_context(session, seed.term_id)
    e = resolve_section_edit(
        ctx,
        "set_field",
        section_edit("set_field", course_codes=["PSI 101"], enrolment=85, preferred_room_codes=["A 206"]),
    )
    assert e.status == "ok", e.issues
    assert e.section_ids == [seed.sections["PSI101"]]
    assert e.changes.enrolment == 85 and e.changes.preferred_room_ids == [seed.rooms["A206"]]
    bad = resolve_section_edit(ctx, "exclude", section_edit("exclude", section_ids=[99999]))
    assert bad.status == "needs_review" and not bad.section_ids
