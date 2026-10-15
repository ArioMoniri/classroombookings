"""Free-text preferences (docs/testing/2026-10-15-academician-needs.md §2.3 and appendix).

1. negation: "Mümkünse B Blok olmasın" (ING 302, Bahar rows 366/636) is *avoid* building B, never prefer B;
2. building alternatives: "A veya C blokta …" (7 Bahar / 17 Güz notes) is the building set {A, C};
3. room alternatives: "A 206 veya C 403-404 veya A 106-107" (Final row 19, PTL252) is three groups, each
   satisfied as a whole (the planner granted C 403 - C 404: satisfied);
4. furniture / accessibility wishes map to a typed room feature (P10) when one exists, else they are an
   "unparsed preference" in the data-issues report;
5. the planning list's "Derse Özel Açıklama" column becomes SOFT preferences with provenance, pending review.

Every rule made from free text is soft.
"""

from __future__ import annotations

import pytest
from app.importers import normalize as n
from sqlalchemy import select

from tests.conftest import BAHAR_LIST, EXAM_LIST
from tests.test_importer_followups import subset

# --------------------------------------------------------------------------- 1 negation


@pytest.mark.parametrize(
    "text,avoid",
    [
        ("Mümkünse B Blok olmasın", ["B"]),  # Bahar rows 366 / 636 (ING 302 §10)
        ("MÜMKÜNSE B BLOK OLMASIN", ["B"]),
        ("mumkunse b blok olmasin", ["B"]),
        ("B blok istemiyorum", ["B"]),
        ("B blok hariç", ["B"]),
        ("C blok dışında bir derslik", ["C"]),
        ("B ve D blok olmasın", ["B", "D"]),
    ],
)
def test_negated_buildings_are_avoided(text: str, avoid: list[str]) -> None:
    items = n.parse_preference_text(text)
    assert [(i.kind, i.params) for i in items] == [("avoid_building", {"avoid_buildings": avoid})], items
    assert all(i.hardness == "soft" for i in items)
    v = n.parse_venue_request(text)
    assert v.building is None and v.avoid_buildings == avoid and v.buildings == []


def test_olmasini_is_no_negation() -> None:
    """ "olmasını rica etti" asks *for* something (Bahar 1529: "Dersliğin B blokta olmasını talep ediyor")."""
    items = n.parse_preference_text("Dersliğin B blokta olmasını talep ediyor hocamız.")
    assert [(i.kind, i.params) for i in items] == [("building_preference", {"buildings": ["B"]})]


def test_negated_room_and_feature() -> None:
    items = n.parse_preference_text("A 204 olmasın")
    assert [(i.kind, i.params) for i in items] == [("avoid_room", {"room_codes": ["A204"]})]
    items = n.parse_preference_text("projeksiyonsuz bir sınıf")
    assert [(i.kind, i.params.get("feature"), i.negated) for i in items] == [("feature", "projector", True)]


# --------------------------------------------------------------------------- 2 building alternatives


@pytest.mark.parametrize(
    "text",
    [
        "A veya C blokta derslik verilmesi talep edilmektedir.",  # Bahar 296, 588, 637 ...
        "A veya C blokta derslik planlanması talep edilmektedir.",  # Güz 54, 56, 102 ...
        "A ya da C blok",
        "A/C blok",
    ],
)
def test_building_alternatives_are_a_set(text: str) -> None:
    items = n.parse_preference_text(text)
    assert [(i.kind, i.params) for i in items] == [("building_preference", {"buildings": ["A", "C"]})]
    v = n.parse_venue_request(text)
    assert v.buildings == ["A", "C"] and v.building is None


def test_single_building_keeps_the_old_field() -> None:
    v = n.parse_venue_request("A Blok'ta Derslik")
    assert v.building == "A" and v.buildings == []


# --------------------------------------------------------------------------- 3 room alternatives


def test_room_alternatives_are_groups(parsed_exam_list) -> None:
    rows = {r.row: r for r in parsed_exam_list.rows}
    v = rows[19].venue  # PTL252 "A 206 veya C 403-404 veya A 106-107", definitive "C 403 - C 404"
    assert v.room_groups == [["A206"], ["C403", "C404"], ["A106", "A107"]]
    assert v.room_codes == ["A206", "C403", "C404", "A106", "A107"]  # the preferred order: first group first
    assert v.building is None  # three buildings' rooms: no single building wish
    assert v.satisfied_by(rows[19].definitive.room_codes) is True
    assert v.satisfied_by(["A206"]) is True
    assert v.satisfied_by(["A206", "C403"]) is False  # mixing two alternatives satisfies neither
    assert v.satisfied_by(["C403"]) is False  # half a group
    v557 = rows[557].venue  # PTL152 "A 207 veya C 601-C 602", definitive A 207
    assert v557.room_groups == [["A207"], ["C601", "C602"]] and v557.satisfied_by(["A207"])
    v431 = rows[431].venue  # MBG 224: "B202 ve B203 olabilir. Veya B205-B206, veya A veya C blokta iki adet sınıf."
    assert v431.room_groups == [["B202", "B203"], ["B205", "B206"]]
    assert v431.buildings == ["A", "C"]
    assert v431.satisfied_by(["B202", "B203"]) is True


def test_one_room_set_is_one_group() -> None:
    v = n.parse_venue_request("A 101 / A 106 / A 107")
    assert v.room_groups == [["A101", "A106", "A107"]]
    assert v.satisfied_by(["A101", "A106", "A107"]) and not v.satisfied_by(["A101"])


# --------------------------------------------------------------------------- 4 features


@pytest.mark.parametrize(
    "text,feature,negated",
    [
        ("Giriş Kata Yakın Olmasını rica etti hocamız", "step_free", False),  # Bahar 609 (ACU 303)
        ("giriş kata yakın olmasını rica etti hocamız.", "step_free", False),  # Güz 543
        ("Engelli öğrencimiz var, asansörlü bina", "step_free", False),
        ("kolçaklı sandalye olmasın", "armchair", True),  # Final 262 (RTT 294)
        ("Sıralar olan sınıf", "fixed_desks", False),
        ("barkovizyon aktif olsun", "projector", False),  # OPT 124
    ],
)
def test_feature_wishes(text: str, feature: str, negated: bool) -> None:
    items = [i for i in n.parse_preference_text(text) if i.kind == "feature"]
    assert [(i.params["feature"], i.negated) for i in items] == [(feature, negated)], items


def test_unparsed_wishes_are_kept() -> None:
    items = n.parse_preference_text("Arkasındaki 2 saate ders konmaması rica olunur")  # RAD 202
    assert [i.kind for i in items] == ["unparsed"]
    assert items[0].text.startswith("Arkasındaki")
    assert n.parse_preference_text("1. ve 2. öğretim birlikte") == []  # no wish wording: nothing to review


# --------------------------------------------------------------------------- 5 the notes column on import


async def test_notes_become_soft_preferences_pending_review(session, tmp_path) -> None:
    """Bahar rows 296 (NUT254, "A veya C blokta"), 366 (ING302 §10, "Mümkünse B Blok olmasın"), 609 (ACU303,
    "Giriş Kata Yakın") and 430 (ACU243, "min. 40 kişilik"): soft FILE rules with their cell, pending review;
    nothing hard is created from free text."""
    from app.importers.planning_list import import_planning_list
    from app.models import ConstraintRow, MeetingRequest

    path = subset(BAHAR_LIST, [296, 366, 430, 609], tmp_path / "notes.xlsx")
    report = await import_planning_list(session, path, "T-NOTES")
    mrs = {m.source_row_index: m for m in (await session.execute(select(MeetingRequest))).scalars()}
    cons = list((await session.execute(select(ConstraintRow))).scalars())
    assert cons and all(c.hardness == "soft" and c.source == "FILE" for c in cons)
    assert all(c.enabled is False and (c.source_ref or {}).get("review") == "pending" for c in cons)
    by_row = {(c.source_ref or {}).get("row"): c for c in cons}
    nut = by_row[2]  # subset rows are renumbered: 296 -> 2
    assert nut.kind == "building_preference" and nut.params["buildings"] == ["A", "C"]
    assert nut.params["event_ids"] == [mrs[2].id] and nut.params["kinds"] == ["course"]
    assert nut.source_ref == {
        "file": "notes.xlsx",
        "sheet": "Sayfa1",
        "row": 2,
        "column": "Derse Özel Açıklama",
        "excerpt": "A veya C blokta derslik verilmesi talep edilmektedir.",
        "review": "pending",
        "key": nut.source_ref["key"],
    }
    assert nut.nl_text == "A veya C blokta derslik verilmesi talep edilmektedir."
    ing = by_row[3]
    assert ing.kind == "building_preference" and ing.params["avoid_buildings"] == ["B"]
    assert "buildings" not in ing.params  # resolved against the run's rooms by the bridge
    prefs = report.extra["preferences"]
    assert prefs["pending_review"] == len(cons) and prefs["notes_rows"] == 4
    assert prefs["unparsed"] >= 1  # 609: no step-free feature in the catalogue yet; 430: a capacity note
    # a re-import keeps the planner's review decision and creates no duplicates
    nut.enabled = True
    nut.source_ref = {**nut.source_ref, "review": "accepted"}
    await session.commit()
    await import_planning_list(session, path, "T-NOTES")
    cons2 = list((await session.execute(select(ConstraintRow))).scalars())
    assert len(cons2) == len(cons)
    nut2 = next(c for c in cons2 if c.id == nut.id)
    assert nut2.enabled is True and nut2.source_ref["review"] == "accepted"


async def test_step_free_feature_maps_to_its_solver_tag(session, tmp_path) -> None:
    """With the P10 feature "Engelli erişimi" (solver tag STEP_FREE) in the catalogue, Bahar 609's "Giriş Kata
    Yakın Olmasını rica etti" becomes a soft room_tags wish for STEP_FREE."""
    from app.importers.planning_list import import_planning_list
    from app.models import ConstraintRow, RoomCustomField

    session.add(RoomCustomField(name="Engelli erişimi", type="BOOLEAN", solver_tag="STEP_FREE"))
    await session.commit()
    path = subset(BAHAR_LIST, [609], tmp_path / "acu.xlsx")
    report = await import_planning_list(session, path, "T-ACU")
    cons = list((await session.execute(select(ConstraintRow))).scalars())
    assert [(c.kind, c.params.get("required_tags"), c.hardness) for c in cons] == [("room_tags", ["STEP_FREE"], "soft")]
    assert report.extra["preferences"]["unparsed"] == 0


async def test_request_column_negation_and_alternatives_on_exams(session, tmp_path) -> None:
    """Final rows 19 (PTL252, room alternatives) and 262 (RTT294, "kolçaklı sandalye olmasın"): the exam
    venue column keeps its room groups; the furniture wish with no feature in the catalogue is reported."""
    from app.importers.exam_list import import_exam_list
    from app.models import ConstraintRow, ExamRequest

    path = subset(EXAM_LIST, [19, 262], tmp_path / "final.xlsx")
    report = await import_exam_list(session, path, "T-FINAL")
    exams = list((await session.execute(select(ExamRequest))).scalars())
    assert len(exams) == 2
    assert not list((await session.execute(select(ConstraintRow).where(ConstraintRow.hardness == "hard"))).scalars())
    assert report.extra["preferences"]["unparsed"] == 2  # fixed desks + no armrest chairs: no such feature


async def test_bridge_resolves_avoided_buildings(session, tmp_path) -> None:
    from app.services.solver_bridge import resolve_building_sets

    params = {"event_ids": [1], "avoid_buildings": ["B"], "kinds": ["course"]}
    out = resolve_building_sets(params, {"A", "B", "C", "D"})
    assert out["buildings"] == ["A", "C", "D"] and out["avoid_buildings"] == ["B"]
    assert resolve_building_sets({"buildings": ["A", "C"]}, {"A", "B", "C"}) == {"buildings": ["A", "C"]}
    # avoiding every building is no wish at all
    assert "buildings" not in resolve_building_sets({"avoid_buildings": ["A", "B"]}, {"A", "B"})


async def test_unparsed_preferences_in_the_data_issues(session, tmp_path) -> None:
    from app.importers.planning_list import import_planning_list
    from app.models import ScheduleRun, Term
    from app.services.data_issues import preference_checks

    path = subset(BAHAR_LIST, [296, 609], tmp_path / "di.xlsx")
    await import_planning_list(session, path, "T-DI")
    term = (await session.execute(select(Term).where(Term.code == "T-DI"))).scalar_one()
    run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="WEEK", status="FEASIBLE", params={}, stats={})
    session.add(run)
    await session.commit()
    out = await preference_checks(session, run)
    unparsed = out["unparsed_preference"]
    assert [it["params"]["text"] for it in unparsed] == ["Giriş Kata Yakın Olmasını rica etti hocamız"]
    assert unparsed[0]["params"]["feature"] == "step_free"
    review = out["preference_review"]
    assert len(review) == 1 and review[0]["params"]["kind"] == "building_preference"


@pytest.mark.parametrize(
    "text",
    [
        "Bilgisayar Mühendisliği öğrencileri için 15 kontenjan isteniyor.",  # a department, not a PC lab
        "Seminer öncesi bilgisayar hazırlığı için gerekli.",  # Bahar rows 34/35 (MBG 408/416): no PC lab
        "Derslik gerekiyor.",  # Bahar row 50: a classroom is needed - nothing to review
    ],
)
def test_real_notes_that_ask_for_nothing_structured(text: str) -> None:
    assert n.parse_preference_text(text) == []


@pytest.mark.parametrize(
    "text", ["C 202 BİLG. LAB BU DERSTE ZORUNLU", "Bilgisayar laboratuvarında yapılacaktır", "bilgisayarlı derslik"]
)
def test_pc_lab_wishes(text: str) -> None:
    feats = [i.params["feature"] for i in n.parse_preference_text(text) if i.kind == "feature"]
    assert feats == ["pc"]
