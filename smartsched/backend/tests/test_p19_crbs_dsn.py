"""Review 2026-10-15 D16: the CRBS import form takes a live MySQL DSN, so a Planner could make the server open a
TCP connection to any host (SSRF). Live DSNs are now planning.admin only and limited to the hosts an admin lists in
the ``crbs_dsn_allowed_hosts`` setting (empty by default: no live DSN until an admin names the CRBS server).
SQL dump uploads are unaffected."""

from __future__ import annotations

import pytest
from app.services import crbs_dsn
from fastapi import HTTPException

from tests.crbs_env import env  # noqa: F401

ALLOWED = crbs_dsn.parse_allowlist("crbs-db.uni.edu.tr, 10.0.4.12:3307 ,\xa0CRBS-DB.UNI.EDU.TR")


def test_allowlist_parsing_folds_case_spaces_and_ports():
    assert ALLOWED == [("crbs-db.uni.edu.tr", None), ("10.0.4.12", 3307)]
    with pytest.raises(ValueError):
        crbs_dsn.parse_allowlist("*.uni.edu.tr")  # no wildcards
    with pytest.raises(ValueError):
        crbs_dsn.parse_allowlist("crbs-db.uni.edu.tr:99999")


@pytest.mark.parametrize(
    ("dsn", "ok"),
    [
        ("mysql://crbs:gizli%40parola@crbs-db.uni.edu.tr/classroombookings", True),
        ("mysql+pymysql://crbs:x@CRBS-DB.uni.edu.tr:3306/crbs", True),
        ("mysql://crbs:x@10.0.4.12:3307/crbs", True),
        ("mysql://crbs:x@10.0.4.12/crbs", False),  # 3306 is not the listed port
        ("mysql://crbs:x@169.254.169.254/latest", False),  # cloud metadata
        ("mysql://crbs:x@localhost/crbs", False),
        ("mysql://crbs:x@crbs-db.uni.edu.tr.evil.example/crbs", False),
        ("mysql://crbs:x@crbs-db.uni.edu.tr/crbs?unix_socket=/var/run/mysqld.sock", False),
        ("postgresql://crbs:x@crbs-db.uni.edu.tr/crbs", False),
        ("mysql:///crbs", False),
    ],
)
def test_only_listed_mysql_hosts_pass(dsn, ok):
    assert (crbs_dsn.dsn_issues(dsn, ALLOWED) == []) is ok


async def test_planner_is_refused_and_admin_needs_the_allowlist(env):  # noqa: F811
    from app.core import db as dbmod
    from app.models import User
    from sqlalchemy import select

    dsn = "mysql://crbs:x@crbs-db.uni.edu.tr/classroombookings"
    async with dbmod.get_session_factory()() as s:
        planner = (await s.execute(select(User).where(User.email == "planner@example.com"))).scalar_one()
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        with pytest.raises(HTTPException) as info:
            await crbs_dsn.check_dsn(s, dsn, planner)
        assert info.value.status_code == 403
        with pytest.raises(HTTPException) as info:  # nothing listed yet
            await crbs_dsn.check_dsn(s, dsn, admin)
        assert info.value.status_code == 422 and "crbs_dsn_allowed_hosts" in str(info.value.detail)
    r = await env.client.put(
        "/api/v1/settings", json={"crbs_dsn_allowed_hosts": "crbs-db.uni.edu.tr"}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["crbs_dsn_allowed_hosts"] == "crbs-db.uni.edu.tr"
    r = await env.client.put("/api/v1/settings", json={"crbs_dsn_allowed_hosts": "*"}, headers=env.admin)
    assert r.status_code == 422
    async with dbmod.get_session_factory()() as s:
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        await crbs_dsn.check_dsn(s, dsn, admin)  # allowed now
        with pytest.raises(HTTPException):
            await crbs_dsn.check_dsn(s, "mysql://crbs:x@10.0.0.5/crbs", admin)
