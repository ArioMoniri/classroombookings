"""HB-03 action registry and the 10 read actions.

* drift: every action's REST twin exists in ``app.api.v1.router`` with the **same** permission guard, the same
  bookings gate, and every mapped argument is a field of that route (body, query or path);
* permission matrix: 4 personas x 10 read actions through ``POST /helper/actions/{name}/card`` (no model call);
* the strict-schema budget of ``app/ai/catalog.py`` holds for every 10-tool subset, and strict tool schemas carry no
  keyword strict tool use rejects;
* read actions write nothing (a session spy counts add / delete / flush / commit);
* model output is never trusted: unknown fields, wrong types and over-long text are refused before anything runs;
* every card validates against ``helper.card.v1``.
"""

from __future__ import annotations

import inspect
import itertools
from typing import Any

import pytest
from app.ai import catalog
from app.ai.helper import schema
from app.ai.helper.actions import registry as reg
from app.api.v1 import bookings as bookings_api
from app.core import db as dbmod
from app.main import app
from app.models import User
from app.services.bookings_perms import load_access
from fastapi.routing import APIRoute

from tests.crbs_env import TODAY, env  # noqa: F401
from tests.helper.support import H, card, personas

READS = [
    "open_feature",
    "search_site",
    "find_free_rooms",
    "room_day_schedule",
    "my_bookings",
    "my_requests_status",
    "approvals_inbox",
    "run_status",
    "requests_needing_review",
    "my_ai_usage",
]
#: persona -> read actions they may run (any-of permission at role level)
MATRIX = {
    "teacher": {"open_feature", "search_site", "find_free_rooms", "room_day_schedule", "my_bookings",
                "my_requests_status", "my_ai_usage"},
    "approver": {"open_feature", "search_site", "find_free_rooms", "room_day_schedule", "my_bookings",
                 "my_requests_status", "approvals_inbox", "my_ai_usage"},
    "planner": {"open_feature", "search_site", "find_free_rooms", "room_day_schedule", "my_bookings",
                "my_requests_status", "run_status", "requests_needing_review", "my_ai_usage"},
    "admin": set(READS),
}
ARGS: dict[str, dict[str, Any]] = {
    "open_feature": {"feature_id": "find_room"},
    "search_site": {"q": "A 102"},
    "find_free_rooms": {"date": "2026-02-19", "start": "08:30", "headcount": 10},
    "room_day_schedule": {"room": "A 102", "date": "2026-02-19"},
    "my_bookings": {},
    "my_requests_status": {},
    "approvals_inbox": {},
    "run_status": {},
    "requests_needing_review": {},
    "my_ai_usage": {},
}


# ------------------------------------------------------------------------------------------------ drift


def _walk(routes: Any, prefix: str = "") -> Any:
    """Every route with its full path (FastAPI ≥ 0.120 keeps included routers lazy; tests/test_audit_coverage.py)."""
    for r in routes:
        ctx = getattr(r, "include_context", None)
        if ctx is not None and hasattr(r, "original_router"):
            yield from _walk(r.original_router.routes, prefix + (ctx.prefix or ""))
        elif isinstance(r, APIRoute):
            yield prefix + r.path, r


def _route(spec: str) -> APIRoute:
    method, path = spec.split(" ", 1)
    for full, r in _walk(app.routes):
        if full == f"/api/v1{path}" and method in r.methods:
            return r
    raise AssertionError(f"no route {spec}")


def _deps(dependant: Any) -> list[Any]:
    out = []
    for d in dependant.dependencies:
        out.append(d.call)
        out.extend(_deps(d))
    return out


def _guard_perms(route: APIRoute) -> frozenset[str]:
    perms: set[str] = set()
    for call in _deps(route.dependant):
        if getattr(call, "__qualname__", "").startswith("require_permission.<locals>"):
            names = inspect.getclosurevars(call).nonlocals.get("names", ())
            perms |= set(names)
    return frozenset(perms)


def _gate(route: APIRoute) -> str | None:
    calls = _deps(route.dependant)
    if bookings_api.maintenance_gate in calls and bookings_api.list_gate not in calls:
        return "maintenance"
    if bookings_api.list_gate in calls:
        return "list"
    return None


def _fields(route: APIRoute) -> set[str]:
    d = route.dependant
    names = {p.alias for p in (*d.query_params, *d.path_params)}
    for b in d.body_params:
        model = b.field_info.annotation if hasattr(b.field_info, "annotation") else None
        model = model or getattr(b, "type_", None)
        if model is not None and hasattr(model, "model_fields"):
            names |= set(model.model_fields)
        names.add(b.alias)
    return names


def test_hb_03_ten_read_actions_registered() -> None:
    reads = [a.name for a in reg.all_actions() if a.kind == "read"]
    assert sorted(reads) == sorted(READS)


@pytest.mark.parametrize("name", READS)
def test_hb_03_drift_against_the_rest_twin(name: str) -> None:
    a = reg.get(name)
    assert a is not None
    route = _route(a.route)
    guard = _guard_perms(route)
    if guard:
        assert frozenset(a.permission) == guard, f"{name}: {a.permission} != route guard {sorted(guard)}"
    assert a.gate == _gate(route), f"{name}: gate {a.gate} != route {_gate(route)}"
    fields = _fields(route)
    for arg, field in a.route_args.items():
        assert arg in a.args.model_fields, f"{name}: route_args names unknown arg {arg}"
        assert field in fields, f"{name}: {field} is not a field of {a.route} ({sorted(fields)})"
    for arg in a.args.model_fields:
        assert arg in a.route_args or arg in a.resolved, f"{name}: {arg} is neither mapped nor resolved"


def test_hb_03_strict_schema_budget_for_any_ten_tools() -> None:
    tools = [reg.tool(a) for a in reg.all_actions()]
    for t in tools:
        sch = t["input_schema"]
        assert t["strict"] is True and sch["additionalProperties"] is False
        assert set(sch["required"]) == set(sch["properties"])
        flat = repr(sch)
        for kw in ("minimum", "maximum", "maxLength", "minLength", "pattern", "'title'", "'default'"):
            assert kw not in flat, (t["name"], kw)
    for subset in itertools.combinations(tools, min(10, len(tools))):
        c = catalog.schema_complexity(list(subset))
        assert c["strict_tools"] <= catalog.MAX_STRICT_TOOLS
        assert c["optional_params"] <= catalog.MAX_OPTIONAL_PARAMS
        assert c["union_params"] <= catalog.MAX_UNION_PARAMS
        assert c["non_strict_objects"] == 0


def test_hb_03_args_refuse_untrusted_shapes() -> None:
    a = reg.get("find_free_rooms")
    assert a is not None
    for bad in (
        {"date": "2026-02-19", "start": "08:30", "user_id": 1},  # unknown field (on-behalf smuggling)
        {"date": "next week please", "start": "08:30"},
        {"headcount": "lots"},
        {"text": "x" * 500},
        ["not", "an", "object"],
    ):
        with pytest.raises(reg.ArgsInvalid):
            reg.parse_args(a, bad)


# ------------------------------------------------------------------------------------- matrix and cards


async def test_hb_03_permission_matrix_and_cards(env) -> None:  # noqa: F811
    people = await personas(env)
    for pname, p in people.items():
        allowed = {x["name"] for x in (await env.client.get(f"{H}/actions", headers=p.headers)).json()}
        assert {n for n in allowed if n in READS} == MATRIX[pname], pname
        for name in READS:
            r = await card(env, p, name, **ARGS[name])
            if name in MATRIX[pname]:
                assert r.status_code == 200, (pname, name, r.text)
                c = schema.validate_card(r.json())
                assert c.type in ("nav", "list", "facts", "form", "choice"), (pname, name, c.type)
            else:
                assert r.status_code == 403, (pname, name, r.text)
                assert r.json()["detail"]["card"]["type"] == "refusal"
                assert r.json()["detail"]["message_tr"]


async def test_hb_03_read_results_are_real(env) -> None:  # noqa: F811
    people = await personas(env)
    t = people["teacher"]
    r = await card(env, t, "find_free_rooms", date="2026-02-19", start="08:30", headcount=10)
    c = r.json()
    assert c["type"] == "list" and c["rows"], c
    assert all(row["actions"][0]["action"] == "create_booking" for row in c["rows"])
    assert len(c["rows"]) <= 5 and c["more"] == "find_room"
    # A 102 is free at P1 on Thursday 19 Feb (the approval-first suite books it); the day view says so
    r = await card(env, t, "room_day_schedule", room="a102", date="2026-02-19")
    day = r.json()
    assert day["type"] == "list" and day["title"]["tr"].startswith("A 102"), day
    assert any(row["actions"] for row in day["rows"])
    # a missing start time asks for it (form), it does not guess
    assert (await card(env, t, "find_free_rooms", date="2026-02-19")).json()["type"] == "form"
    # a page the teacher cannot open is a refusal with nearby entries, never the page
    refusal = (await card(env, t, "open_feature", feature_id="admin.users")).json()
    assert refusal["type"] == "refusal" and refusal["code"] == "not_allowed"
    assert all(not f["feature_id"].startswith("admin") for f in refusal.get("fallback", []))
    # the teacher's own booking shows in my_bookings with a cancel button
    b = await env.book(t.headers, "A102", TODAY.replace(day=19), "P1")
    assert b.status_code in (201, 202), b.text
    mine = (await card(env, t, "my_bookings")).json()
    assert any(row["id"] == f"booking:{b.json()['id']}" for row in mine["rows"]) or b.status_code == 202
    # planners: facts with sentences, never bare numbers
    facts = (await card(env, people["planner"], "run_status")).json()
    assert facts["type"] == "facts" and all(" " in i["value"]["tr"] for i in facts["items"])
    review = (await card(env, people["planner"], "requests_needing_review")).json()
    assert review["type"] == "facts" and "talep" in review["items"][0]["value"]["tr"]


async def test_hb_03_read_actions_write_nothing(env, monkeypatch) -> None:  # noqa: F811
    people = await personas(env)
    calls: list[str] = []
    factory = dbmod.get_session_factory()
    async with factory() as session:
        for meth in ("add", "add_all", "delete", "flush", "commit", "merge"):
            orig = getattr(session, meth)

            def spy(*a: Any, _m: str = meth, _o: Any = orig, **k: Any) -> Any:
                calls.append(_m)
                return _o(*a, **k)

            monkeypatch.setattr(session, meth, spy)
        admin = await session.get(User, people["admin"].uid)
        assert admin is not None
        access = await load_access(session, admin)
        for name in READS:
            a = reg.get(name)
            assert a is not None
            out = await a.run(reg.Ctx(session, access), reg.parse_args(a, ARGS[name]))
            schema.validate_card(out.model_dump(mode="json"))
            assert calls == [], f"{name} wrote: {calls}"


def test_hb_03_tools_for_is_small_and_drops_writes_when_tainted() -> None:
    class _Access:
        perms = frozenset({"room.view", "book_single.create", "approvals.decide"})

    tools = reg.tools_for(_Access(), hits=["find_free_rooms"])  # type: ignore[arg-type]
    names = [t["name"] for t in tools]
    assert names[0] == "open_feature" and names[1] == "find_free_rooms"
    assert len(tools) <= reg.MAX_TOOLS
    reads = {a.name for a in reg.all_actions() if a.kind == "read"}
    assert {t["name"] for t in reg.tools_for(_Access(), allow_writes=False)} <= reads  # type: ignore[arg-type]
