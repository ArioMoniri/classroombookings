"""Owner decision 2026-10-15, section identity: planning-list rows identical except for the class year (same
course, section, programme, instructors, days, times, weeks, definitive rooms and mode) are ONE section taught
once to several class years: ``Section.class_years`` is the union, there is one set of meeting requests, the
cohorts of every listed year are blocked at that time, and the provenance of every source row is kept. Rows that
differ in anything else stay separate.

Real Bahar rows (probe: 9 such groups / 32 rows in Bahar, 4 / 10 in Güz):

* 52, 55, 56  MBG 023 §1, Friday P9-P11, A 102, years 2 / 3 / 4 (enrolment 80 on each row: the class total)
* 421, 422    BME 419 §1, Wednesday P6-P8, C 601, years 3 / 4
* 257, 275    MBG 034 §1, Wednesday P7-P9, B 407, years 3 / 4 (enrolment 80 / 75)
* 34          MBG 408, Friday P8-P9, year 4: overlaps MBG 023, so the merged year 4 cohort clashes with it
"""

from __future__ import annotations

import openpyxl
from sqlalchemy import select

from tests.conftest import BAHAR_LIST
from tests.test_importer_followups import subset

ROWS = [34, 52, 55, 56, 257, 275, 421, 422]
PROG = "Moleküler Biyoloji ve Genetik (İngilizce)"


async def _import(session, path, term="T-YEARS"):  # type: ignore[no-untyped-def]
    from app.importers.planning_list import import_planning_list

    return await import_planning_list(session, path, term)


async def _sections(session, term="T-YEARS"):  # type: ignore[no-untyped-def]
    from app.models import Course, MeetingRequest, Section, Term

    t = (await session.execute(select(Term).where(Term.code == term))).scalar_one()
    out: dict[str, tuple[list[int], int, list[MeetingRequest]]] = {}
    for sec, code in (
        await session.execute(
            select(Section, Course.code).join(Course, Course.id == Section.course_id).where(Section.term_id == t.id)
        )
    ).all():
        meetings = list(
            (
                await session.execute(
                    select(MeetingRequest).where(
                        MeetingRequest.section_id == sec.id, MeetingRequest.archived.is_(False)
                    )
                )
            ).scalars()
        )
        out[code] = (sorted(sec.class_years or []), int(sec.enrolment or 0), meetings)
    return t, out


async def test_rows_that_differ_only_in_class_year_are_one_section(session, tmp_path) -> None:
    report = await _import(session, subset(BAHAR_LIST, ROWS, tmp_path / "years.xlsx"))
    _t, secs = await _sections(session)
    assert secs["MBG023"][0] == [2, 3, 4] and len(secs["MBG023"][2]) == 1
    assert secs["BME419"][0] == [3, 4] and len(secs["BME419"][2]) == 1
    assert secs["MBG034"][0] == [3, 4] and len(secs["MBG034"][2]) == 1
    assert secs["MBG034"][1] == 80  # the class total: the largest of the rows (80 / 75), never their sum
    assert secs["MBG408"][0] == [4] and len(secs["MBG408"][2]) == 1
    merged = report.extra["merged_class_years"]
    assert merged["groups"] == 3 and merged["rows"] == 7  # 8 rows -> 5 meetings
    assert report.rows_imported == 8  # every row is imported (merged rows too)
    # provenance of every source row: on the meeting and in the report (subset rows: 52 -> 3, 55 -> 4, 56 -> 5)
    (mbg,) = secs["MBG023"][2]
    assert mbg.source_row_index == 3
    assert "satır 3 (2. sınıf), 4 (3. sınıf), 5 (4. sınıf)" in (mbg.notes or "")
    item = next(i for i in merged["items"] if i["course"] == "MBG023")
    assert item["rows"] == [3, 4, 5] and item["class_years"] == [2, 3, 4]
    assert any("enrolment 80 / 75" in w for w in report.warnings), report.warnings[:5]


async def test_every_listed_year_is_blocked(session, tmp_path) -> None:
    """The merged section carries the cohort of every year: MBG 023 (now years 2-4) and MBG 408 (year 4) overlap
    on Friday, which the solver's no-cohort-overlap rule now sees for year 4 (before: MBG 023 was year 2 only)."""
    from app.models import ScheduleRun
    from app.services.solver_bridge import build_solver_input

    await _import(session, subset(BAHAR_LIST, ROWS, tmp_path / "years.xlsx"))
    t, _ = await _sections(session)
    run = ScheduleRun(term_id=t.id, kind="COURSE", horizon="WEEK", status="QUEUED", params={"week": 3}, stats={})
    session.add(run)
    await session.commit()
    inp, _members = await build_solver_input(session, run)
    by_label = {e.label.split(" §")[0].replace(" ", ""): e for e in inp.events}
    mbg023, mbg408, bme, mbg034 = by_label["MBG023"], by_label["MBG408"], by_label["BME419"], by_label["MBG034"]
    years = lambda e: sorted(k.rsplit(":Y", 1)[1] for k in e.cohort_keys)  # noqa: E731
    assert years(mbg023) == ["2", "3", "4"] and years(bme) == ["3", "4"] and years(mbg034) == ["3", "4"]
    assert mbg023.cohort_keys & mbg408.cohort_keys  # year 4 shared ...
    assert mbg023.fixed_day == mbg408.fixed_day  # ... on Friday, overlapping periods: a cohort clash
    assert {k.rsplit(":Y", 1)[1] for k in bme.cohort_keys & mbg034.cohort_keys} == {"3", "4"}  # both years


async def test_a_re_import_is_idempotent(session, tmp_path) -> None:
    path = subset(BAHAR_LIST, ROWS, tmp_path / "years.xlsx")
    await _import(session, path)
    _t, first = await _sections(session)
    again = await _import(session, path)
    _t, second = await _sections(session)
    assert again.created.get("meeting_requests", 0) == 0 and again.created.get("sections", 0) == 0
    assert again.updated.get("meeting_requests", 0) == 0 and again.updated.get("sections", 0) == 0
    assert {k: (v[0], v[1], [m.id for m in v[2]]) for k, v in first.items()} == {
        k: (v[0], v[1], [m.id for m in v[2]]) for k, v in second.items()
    }


async def test_rows_that_differ_in_anything_else_stay_separate(session, tmp_path) -> None:
    """Row 56 (MBG 023 year 4) moved to another start time: it is a different meeting, not merged."""
    path = subset(BAHAR_LIST, [52, 55, 56], tmp_path / "moved.xlsx")
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    assert ws is not None
    headers = [str(c.value or "") for c in ws[1]]
    col = next(i for i, h in enumerate(headers, 1) if "Başlangıç" in h)
    ws.cell(row=4, column=col).value = "13:30"  # row 4 of the subset is Bahar row 56
    wb.save(path)
    report = await _import(session, path)
    _t, secs = await _sections(session)
    assert len(secs["MBG023"][2]) == 2  # rows 52 + 55 merged; 56 at another time stays its own meeting
    assert report.extra["merged_class_years"]["groups"] == 1
