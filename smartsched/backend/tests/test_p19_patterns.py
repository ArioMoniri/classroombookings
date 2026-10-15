"""P19-C2: the weekly-pattern expander (``app.services.patterns``) as pure functions.

The cases are real-shaped: Bahar row 188 (MBG 532 Epigenetik, T=3, Salı 11:00-13:20, Fen Bilimleri
Enstitüsü) and BES 439 ("Salı / Çarşamba / Perşembe / Cuma", a flexible day list), with the Turkish text forms
the planning lists use (dotted times, NBSP, capitals without the Turkish dot). The property tests draw a
thousand specs from a seeded generator (no hypothesis dependency) and check the invariants of every expansion.
"""

from __future__ import annotations

import random
from datetime import time

import pytest
from app.importers import normalize as n
from app.services import patterns as p

# --------------------------------------------------------------------------- days


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("TUE|THU", (2, 4)),
        ("Salı / Perşembe", (2, 4)),
        ("SALI|PERŞEMBE", (2, 4)),
        ("SALI|PERSEMBE", (2, 4)),  # typed without Turkish letters (review D9)
        ("Sali, Persembe", (2, 4)),
        ("salı ve perşembe", (2, 4)),
        ("Salı veya Perşembe", (2, 4)),
        ("Salı\xa0/\xa0Çarşamba / Perşembe / Cuma", (2, 3, 4, 5)),  # BES 439, NBSP from a copy-paste
        ("ÇARŞAMBA", (3,)),
        ("CARSAMBA", (3,)),
        ("Pazartesi", (1,)),
        ("Pazar", (7,)),
        ("Cumartesi|Pazar", (6, 7)),
        ("tuesday thursday", (2, 4)),
        ("2|4", (2, 4)),
        ([4, 2, 2], (2, 4)),
        (["Salı", "Perşembe"], (2, 4)),
        (6, (6,)),
    ],
)
def test_parse_days_turkish_and_english(text: object, want: tuple[int, ...]) -> None:
    assert p.parse_days(text) == want


@pytest.mark.parametrize("bad", ["", "Belirli günü yok", "Salıı", "8", 0, [9], "MON|FUNDAY"])
def test_parse_days_refuses_unknown(bad: object) -> None:
    with pytest.raises(p.PatternError):
        p.parse_days(bad)


# --------------------------------------------------------------------------- start times


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("08:30", 1),
        ("09.20", 2),  # dotted time (planning lists)
        ("9.20", 2),
        (" 11:00\xa0", 4),
        ("13.30", 7),
        ("18:00", 13),
        (time(10, 10), 3),
        (4, 4),
        ("P7", 7),
        ("p13", 13),
    ],
)
def test_parse_start(value: object, want: int) -> None:
    assert p.parse_start(value) == want


@pytest.mark.parametrize("bad", ["23:30", "22:40", 0, 19, "yarın", "", True])
def test_parse_start_refuses_values_off_the_day(bad: object) -> None:
    with pytest.raises(p.PatternError):
        p.parse_start(bad)


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("10.20", 3),  # owner decision: covers 30 of P3's 40 minutes -> P3
        ("10:35", 4),  # 15 of 40 minutes: not half -> P4
        ("09:00", 2),  # 10 of P1's 40 minutes -> P2
        ("10:55", 4),  # in the break -> the next period
        ("07:00", 1),  # before the grid: P1, which it covers fully
    ],
)
def test_off_grid_starts_snap_by_the_half_rule(value: object, want: int) -> None:
    """Product-owner decision 2026-10-15: a hand-made class's off-grid start snaps like the planning list's
    (periods covered for at least half), with a warning, and the written time is kept."""
    period, written, warning = p.start_snap(value)
    assert period == want and written is not None and warning and f"P{want}" in warning
    assert p.parse_start(value) == want


def test_off_grid_start_is_kept_and_warned_on_the_meeting() -> None:
    spec = p.build_spec({"theory": 2, "days": "Salı", "start": "10.20"}, course_hours=(2, 0, 0), max_week=14)
    (m,) = p.expand(spec, enrolment=30, needs_room=True)
    assert (m.start_period, m.end_period) == (3, 4) and m.start_time == time(10, 20)
    assert m.warnings and "10:20" in m.warnings[0] and "P3" in m.warnings[0]
    on_grid = p.expand(
        p.build_spec({"theory": 2, "days": "Salı", "start": "10.10"}, course_hours=(2, 0, 0), max_week=14),
        enrolment=30,
        needs_room=True,
    )
    assert on_grid[0].start_time == time(10, 10) and on_grid[0].warnings == ()


# --------------------------------------------------------------------------- weeks


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("1-14", tuple(range(1, 15))),
        ("1 - 7, 9-14", (*range(1, 8), *range(9, 15))),
        ("Tüm haftalar", tuple(range(1, 15))),
        ("TÜM HAFTALAR", tuple(range(1, 15))),
        ("Hepsi", tuple(range(1, 15))),
        ("İlk 7 hafta", tuple(range(1, 8))),
        ("son 7 hafta", tuple(range(8, 15))),
        ([3, 1, 2, 2], (1, 2, 3)),
        (None, tuple(range(1, 15))),
    ],
)
def test_parse_weeks_spec(value: object, want: tuple[int, ...]) -> None:
    assert p.parse_weeks_spec(value, 14) == want


@pytest.mark.parametrize("bad", ["1-20", [0, 1], [15], "0.5", "Online", "x"])
def test_parse_weeks_spec_refuses_ambiguous_or_out_of_term(bad: object) -> None:
    with pytest.raises(p.PatternError):
        p.parse_weeks_spec(bad, 14)


# --------------------------------------------------------------------------- hours -> blocks


@pytest.mark.parametrize(
    ("hours", "blocks", "want"),
    [
        (3, None, (3,)),
        (3, [2, 1], (2, 1)),
        (3, [1, 1, 1], (1, 1, 1)),
        (3, 2, (2, 1)),
        (5, 2, (2, 2, 1)),
        (4, 4, (4,)),
        (0, None, ()),
        (0, 2, ()),
    ],
)
def test_split_hours(hours: int, blocks: object, want: tuple[int, ...]) -> None:
    assert p.split_hours(hours, blocks) == want


def test_split_hours_refuses_a_total_that_differs() -> None:
    """Design §4.6: "MBG 541: 3 saatlik ders için yalnızca 2 saat yerleştirildi" is an error."""
    with pytest.raises(p.PatternError, match="3"):
        p.split_hours(3, [2])
    with pytest.raises(p.PatternError):
        p.split_hours(3, [2, 0, 1])
    with pytest.raises(p.PatternError):
        p.split_hours(3, 0)


# --------------------------------------------------------------------------- room needs


def test_room_needs_normalise_turkish_text() -> None:
    needs = p.parse_room_needs({"tags": ["pc", "Tıp"], "building": "c blok", "preferred_room": "A\xa0105"})
    assert needs.tags == ("PC", "TIP")
    assert needs.building == "C"
    assert needs.preferred_room == "A105"
    assert needs.room_text == "A 105"
    assert p.parse_room_needs({"tags": "BİLGİSAYAR LAB"}).tags == ("PC",)
    assert p.parse_room_needs(None) == p.RoomNeeds()


@pytest.mark.parametrize("bad", [{"building": "E"}, {"preferred_room": "Derslik"}, {"capacity": -3}, {"tags": ["?"]}])
def test_room_needs_refuse_unknown_values(bad: dict[str, object]) -> None:
    with pytest.raises(p.PatternError):
        p.parse_room_needs(bad)


# --------------------------------------------------------------------------- expansion


def test_three_periods_tue_or_thu_weeks_1_to_14() -> None:
    """The P19-C2 acceptance pattern on Bahar row 188 (MBG 532 Epigenetik, T=3, enrolment 80): "3 periods a
    week, Tue or Thu, weeks 1-14" at 11:00 as 2+1 -> two flexible meetings the solver places on different days."""
    spec = p.build_spec(
        {"theory": 3, "block_size": [2, 1], "days": "Salı veya Perşembe", "start": "11.00", "weeks": "1-14"},
        course_hours=(3, 0, 0),
        max_week=14,
    )
    out = p.expand(spec, enrolment=80, needs_room=True)
    assert [(m.kind, m.start_period, m.end_period) for m in out] == [("T", 4, 5), ("T", 4, 4)]
    for m in out:
        assert m.day is None and m.days == (2, 4) and m.flexible_day
        assert m.weeks == tuple(range(1, 15))
        assert m.requested_capacity == 80
        assert m.start_time == time(11, 0)
    assert out[0].end_time == time(12, 30) and out[1].end_time == time(11, 40)


def test_fixed_slots_reproduce_the_planning_list_row() -> None:
    """Bahar row 188 as written: Salı 11:00-13:20 (3 periods) -> one fixed meeting, start/end times equal to
    the importer's period mapping."""
    spec = p.build_spec(
        {"slots": [{"day": "SALI", "start": "11:00"}], "weeks": "Tüm haftalar"}, course_hours=(3, 0, 0), max_week=14
    )
    (m,) = p.expand(spec, enrolment=80, needs_room=True)
    assert (m.day, m.days, m.flexible_day) == (2, (2,), False)
    imported = n.time_range_to_periods(time(11, 0), time(13, 20))
    assert (m.start_period, m.end_period) == (imported.start_period, imported.end_period)


def test_theory_practice_and_lab_are_separate_meetings_with_their_own_room_needs() -> None:
    """Design §4.6: U and L blocks are separate meetings with their own room needs (Bahar MBG 110 General
    Biology II: T=3, L=4)."""
    spec = p.build_spec(
        {
            "block_size": [2, 1],
            "days": "Çarşamba",
            "start": ["13:30", "16:00", "08:30"],
            "room_needs": {"building": "A"},
            "room_needs_by_kind": {"lab": {"tags": ["PC"], "preferred_room": "A 105"}},
            "lab_blocks": [4],
        },
        course_hours=(3, 0, 4),
        max_week=14,
    )
    out = p.expand(spec, enrolment=80, needs_room=True)
    assert [(m.kind, m.start_period, m.end_period) for m in out] == [("T", 7, 8), ("T", 10, 10), ("L", 1, 4)]
    assert out[0].requested_building == "A" and out[0].requested_tags == ()
    assert out[2].requested_tags == ("PC",) and out[2].requested_room_code == "A105"
    assert out[2].requested_building == "A"


def test_hours_default_from_the_course_and_zero_hour_courses_need_explicit_hours() -> None:
    spec = p.build_spec({"days": "TUE", "start": "14:20"}, course_hours=(3, 0, 0), max_week=14)
    assert [m.end_period - m.start_period + 1 for m in p.expand(spec, enrolment=20, needs_room=True)] == [3]
    # MBG 598 Seminer is listed 0+0+0 but meets one period on Friday 14:20 (design §4.2)
    with pytest.raises(p.PatternError, match="no weekly hours"):
        p.build_spec({"days": "Cuma", "start": "14:20"}, course_hours=(0, 0, 0), max_week=14)
    spec = p.build_spec({"theory": 1, "days": "Cuma", "start": "14:20"}, course_hours=(0, 0, 0), max_week=14)
    (m,) = p.expand(spec, enrolment=120, needs_room=True)
    assert (m.day, m.start_period, m.end_period) == (5, 8, 8)


def test_online_sections_get_meetings_that_need_no_room() -> None:
    spec = p.build_spec({"days": "Salı", "start": "10:10"}, course_hours=(3, 0, 0), max_week=14)
    (m,) = p.expand(spec, enrolment=80, needs_room=False)
    assert m.needs_room is False


def test_self_overlapping_patterns_are_refused() -> None:
    # two fixed blocks of one section on one day at overlapping times
    with pytest.raises(p.PatternError, match="overlap"):
        p.build_spec({"block_size": [2, 1], "days": "Salı", "start": "11:00"}, course_hours=(3, 0, 0), max_week=14)
    # three blocks at the same time but only two candidate days
    with pytest.raises(p.PatternError, match="days"):
        p.build_spec({"block_size": 1, "days": "TUE|THU", "start": "11:00"}, course_hours=(3, 0, 0), max_week=14)
    # a block running past the last period (22:10-22:50)
    with pytest.raises(p.PatternError, match="P18"):
        p.build_spec({"days": "Cumartesi", "start": "21:20"}, course_hours=(3, 0, 0), max_week=14)


def test_build_spec_requires_a_start_or_slots() -> None:
    """The solver picks the room and (among ``days``) the day; the time is the department's (every planning-list
    row carries one), and a MeetingRequest has no duration column for a time-flexible request."""
    with pytest.raises(p.PatternError, match="start"):
        p.build_spec({"days": "TUE|THU"}, course_hours=(3, 0, 0), max_week=14)
    with pytest.raises(p.PatternError, match="start"):
        p.build_spec({"block_size": [2, 1], "days": "TUE|THU", "start": ["11:00"]}, course_hours=(3, 0, 0), max_week=14)
    with pytest.raises(p.PatternError, match="slots"):
        p.build_spec(
            {"block_size": [2, 1], "slots": [{"day": 2, "start": "11:00"}]}, course_hours=(3, 0, 0), max_week=14
        )


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(p.PatternError, match="unknown"):
        p.build_spec({"days": "TUE", "start": 1, "teory": 3}, course_hours=(3, 0, 0), max_week=14)


# --------------------------------------------------------------------------- properties


def _random_spec(rng: random.Random) -> tuple[dict[str, object], tuple[int, int, int], int]:
    hours = (rng.randint(0, 4), rng.randint(0, 3), rng.randint(0, 4))
    if sum(hours) == 0:
        hours = (rng.randint(1, 4), hours[1], hours[2])
    max_week = rng.choice([14, 15, 16])
    days = tuple(sorted(rng.sample(range(1, 8), rng.randint(1, 4))))
    raw: dict[str, object] = {"block_size": rng.choice([None, 1, 2, 3, 4])}
    if rng.random() < 0.5:
        raw["days"] = "|".join(rng.choice([n.DAY_LABELS_TR[d], n.DAY_LABELS_TR[d].upper(), str(d)]) for d in days)
    else:
        raw["days"] = list(days)
    lo = rng.randint(1, 6)
    raw["weeks"] = rng.choice([None, f"{lo}-{max_week}", list(range(lo, max_week + 1, 2)), "Tüm haftalar"])
    return raw, hours, max_week


def test_expansion_invariants_over_a_thousand_seeded_specs() -> None:
    rng = random.Random(20261015)
    expanded = refused = 0
    for _ in range(1000):
        raw, hours, max_week = _random_spec(rng)
        blocks = p.blocks_for(raw, hours)
        if blocks is None:
            refused += 1
            continue
        # one start per block, spread over the day so the blocks of one section can fit
        raw["start"] = [p.PERIOD_STARTS[(i * 4) % 12] for i in range(len(blocks))]
        try:
            spec = p.build_spec(raw, course_hours=hours, max_week=max_week)
        except p.PatternError:
            refused += 1
            continue
        enrol = rng.randint(1, 150)
        out = p.expand(spec, enrolment=enrol, needs_room=True)
        again = p.expand(
            p.build_spec(dict(raw), course_hours=hours, max_week=max_week), enrolment=enrol, needs_room=True
        )
        assert out == again  # deterministic
        assert len(out) == len(blocks)
        for kind, total in zip("TUL", hours, strict=True):
            assert sum(m.end_period - m.start_period + 1 for m in out if m.kind == kind) == total
        for m in out:
            assert 1 <= m.start_period <= m.end_period <= n.PERIODS_PER_DAY
            assert m.start_time == n.PERIODS[m.start_period - 1].start
            assert m.end_time == n.PERIODS[m.end_period - 1].end
            assert m.weeks and set(m.weeks) <= set(range(1, max_week + 1)) and list(m.weeks) == sorted(m.weeks)
            assert m.days and set(m.days) <= set(range(1, 8))
            assert m.flexible_day == (len(m.days) > 1)
            assert m.day == (m.days[0] if len(m.days) == 1 else None)
            assert m.requested_capacity == enrol
        # never two blocks of one section that must overlap: on a fixed common day they are disjoint
        for a in out:
            for b in out:
                if a is not b and a.day is not None and a.day == b.day:
                    assert a.end_period < b.start_period or b.end_period < a.start_period
        expanded += 1
    assert expanded > 600 and refused > 0  # both branches are exercised
