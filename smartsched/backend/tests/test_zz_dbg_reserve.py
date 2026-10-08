from datetime import date
from sqlalchemy import select
from app.core import db as dbmod
from app.models import Assignment, MeetingRequest, Section, Program, ScheduleRun
from tests.crbs_env import env  # noqa: F401

async def test_dbg(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        runs = list((await s.execute(select(ScheduleRun.id, ScheduleRun.is_active, ScheduleRun.term_id))).all())
        print("runs", runs)
        q = select(Assignment.room_ids, Assignment.label, Assignment.meeting_request_id, Assignment.run_id).where(Assignment.label.like("PSI%"))
        rows = list((await s.execute(q)).all())[:8]
        print("psi", rows)
        n = (await s.execute(select(Assignment.id).where(Assignment.meeting_request_id.is_not(None)))).all()
        print("with mr", len(n))
        progs = (await s.execute(select(Section.program_id, Program.name).join(Program, Program.id==Section.program_id).limit(5))).all()
        print("progs", progs)
