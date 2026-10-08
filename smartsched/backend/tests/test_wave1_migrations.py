"""Alembic 0012-0015 (booking enhancements wave 1): upgrade with existing CRBS CHECKBOX values and imported room
tags (the room master's A 103 = PC, A 201 = TIP), adopt the tags as typed features, keep the CHECKBOX values,
grant the new permissions to Administrator only; the audit table refuses UPDATE/DELETE; downgrade to
0011_integrations and upgrade again work; one head."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from tests.test_crbs_migration import _cfg, _run


def test_wave1_upgrade_keeps_checkbox_values_adopts_tags_and_round_trips(tmp_path):
    path = tmp_path / "w1.db"
    url = f"sqlite+aiosqlite:///{path}"
    assert ScriptDirectory.from_config(_cfg(url)).get_heads() == ["0015_approvals"]
    _run(url, command.upgrade, "0011_integrations")
    con = sqlite3.connect(path)
    con.execute(
        "insert into rooms (id, code, display_name, capacity, exam_capacity, tags, is_bookable, custom_fields, pos, "
        "created_at, updated_at) values (3, 'A103', 'A 103', 47, 33, '[\"PC\"]', 1, '{}', 0, '2026-10-01', '2026-10-01'), "
        "(10, 'A201', 'A 201', 96, 48, '[\"TIP\"]', 1, '{}', 0, '2026-10-01', '2026-10-01')"
    )
    con.execute("insert into room_custom_fields (id, name, type, pos) values (1, 'Projeksiyon', 'CHECKBOX', 1)")
    con.execute("insert into room_custom_field_values (room_id, field_id, value) values (3, 1, '1')")
    con.commit()
    con.close()

    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    fields = {
        r[0]: r[1:] for r in con.execute("select name, type, solver_tag, filterable, public from room_custom_fields")
    }
    assert fields["Projeksiyon"] == ("CHECKBOX", None, 1, 1)
    assert fields["Bilgisayar laboratuvarı"] == ("BOOLEAN", "PC", 1, 1)
    assert fields["Tıp Fakültesi dersliği"] == ("BOOLEAN", "TIP", 1, 1)
    assert con.execute("select value from room_custom_field_values where field_id = 1").fetchone() == ("1",)
    admin = con.execute("select id from roles where code = 'ADMIN'").fetchone()[0]
    teacher = con.execute("select id from roles where code = 'TEACHER'").fetchone()[0]
    wave1 = {"rooms.features", "audit.view", "approvals.decide", "book_single.request", "book_recur.request"}

    def held(role: int) -> set[str]:
        q = "select p.name from permissions p join role_permissions rp on rp.permission_id = p.id where rp.role_id = ?"
        return {r[0] for r in con.execute(q, (role,))}

    assert wave1 <= held(admin) and not (wave1 & held(teacher))
    con.execute(
        "insert into audit_events (ts, actor_type, action, entity_type, reversible) "
        "values ('2026-10-08', 'system', 'test.event', 'test', 0)"
    )
    con.commit()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("update audit_events set action = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("delete from audit_events")
    con.close()

    _run(url, command.downgrade, "0011_integrations")
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert not {"audit_events", "approval_rules", "approval_requests", "inapp_notifications"} & tables
    cols = {r[1] for r in con.execute("pragma table_info(room_custom_fields)")}
    assert "solver_tag" not in cols
    assert con.execute("select value from room_custom_field_values where field_id = 1").fetchone() == ("1",)
    assert con.execute("select count(*) from permissions").fetchone()[0] == 31
    con.close()
    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    again = sorted(r for r in con.execute("select name, type, solver_tag from room_custom_fields"))
    assert again == [
        ("Bilgisayar laboratuvarı", "BOOLEAN", "PC"),
        ("Projeksiyon", "CHECKBOX", None),
        ("Tıp Fakültesi dersliği", "BOOLEAN", "TIP"),
    ]
    con.close()
