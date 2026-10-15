"""ROADMAP Phase 9: ``app/ai/chat.py`` treated only OPTIMAL/FEASIBLE as a usable result. A best-effort
``FEASIBLE_PARTIAL`` run (a stored partial timetable) is explained as usable, with its placed/total count."""

from __future__ import annotations

from app.ai.chat import render_template, run_facts
from app.models import ScheduleRun


def _run(status: str, **stats) -> ScheduleRun:
    return ScheduleRun(
        id=7, term_id=1, kind="COURSE", status=status, hard_score=100, soft_score=88, stats=stats, diagnosis=[]
    )


def test_partial_run_is_explained_as_usable_with_its_placement():
    facts = run_facts(_run("FEASIBLE_PARTIAL", partial=True, placed=577, unplaced=26, events_total=603))
    assert facts["placed"] == 577 and facts["events_total"] == 603
    text, sections = render_template(facts, "en")
    assert "hard rules 100/100" in text and "577/603" in text and "problem" not in sections[0]["body"]
    tr, _ = render_template(facts, "tr")
    assert "zorunlu kurallar 100/100" in tr and "577/603" in tr


def test_full_and_failed_runs_unchanged():
    ok, _ = render_template(run_facts(_run("OPTIMAL")), "en")
    assert ok.startswith("Run #7: OPTIMAL, hard rules 100/100") and "/603" not in ok
    bad, _ = render_template(run_facts(_run("INFEASIBLE")), "en")
    assert "problem(s) found" in bad
