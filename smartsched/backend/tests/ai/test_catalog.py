from __future__ import annotations

from app.ai import catalog
from app.schemas.ai import CatalogOut
from app.solver.constraints import HANDLERS

EXPECTED_TOOLS = {
    "propose_constraints",
    "find_assignments",
    "room_schedule",
    "find_sections",
    "explain_assignment",
    "move_event",
    "swap_rooms",
    "lock_assignment",
    "unlock_assignment",
    "add_constraint",
    "remove_constraint",
    "set_weight",
    "include_sections",
    "exclude_sections",
    "set_section_field",
    "re_solve",
}


def test_one_entry_per_registered_kind_with_tr_en_text():
    assert set(HANDLERS) <= set(catalog.KINDS)
    for kind, spec in catalog.KINDS.items():
        assert spec.registered, kind
        assert spec.title["tr"] and spec.title["en"], kind
        assert spec.description["tr"] and spec.description["en"], kind
        assert spec.allowed_hardness and spec.default_hardness in ("hard", "soft"), kind
        assert kind in catalog.MODEL_FIELDS_BY_KIND, kind
    assert catalog.KINDS["no_room_overlap"].allowed_hardness == ("hard",)
    assert catalog.KINDS["min_capacity_waste"].allowed_hardness == ("soft",)


def test_examples_validate_against_params_schema():
    for kind, spec in catalog.KINDS.items():
        for ex in spec.examples:
            assert catalog.validate_params(kind, ex["params"], ex["hardness"]) == [], (kind, ex)


def test_validate_params_rejects_bad_input():
    assert catalog.validate_params("room_pin", {"room_ids": ["x"]}, "hard")
    assert catalog.validate_params("room_pin", {"bogus": 1}, "hard")
    assert catalog.validate_params("no_room_overlap", {}, "soft")
    assert catalog.validate_params("nope", {}, "hard")
    # metadata keys (upload source refs) are ignored
    assert catalog.validate_params("room_pin", {"room_ids": [1], "_source_ref": {"file": "x", "row": 2}}, "hard") == []


def test_tool_schemas_are_strict_and_within_api_limits():
    names = {t["name"] for t in [catalog.PROPOSE_CONSTRAINTS_TOOL, *catalog.CHAT_TOOLS]}
    assert names == EXPECTED_TOOLS
    for request_tools in ([catalog.PROPOSE_CONSTRAINTS_TOOL], catalog.CHAT_TOOLS):
        c = catalog.schema_complexity(request_tools)
        assert c["strict_tools"] == len(request_tools) <= catalog.MAX_STRICT_TOOLS
        assert c["optional_params"] <= catalog.MAX_OPTIONAL_PARAMS
        assert c["union_params"] <= catalog.MAX_UNION_PARAMS
        assert c["non_strict_objects"] == 0
    for t in catalog.CHAT_TOOLS:
        assert t["strict"] is True and t["input_schema"]["additionalProperties"] is False


def test_no_numeric_or_string_constraints_in_strict_schemas():
    banned = {"minimum", "maximum", "minLength", "maxLength", "multipleOf", "pattern"}

    def walk(node):
        if isinstance(node, dict):
            assert not banned & set(node), node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for t in [catalog.PROPOSE_CONSTRAINTS_TOOL, *catalog.CHAT_TOOLS]:
        walk(t["input_schema"])


def test_validate_tool_input():
    assert catalog.validate_tool_input("re_solve", {"stability": True, "reason": "x"}) == []
    assert catalog.validate_tool_input("re_solve", {"stability": "yes", "reason": "x"})
    assert catalog.validate_tool_input("re_solve", {"reason": "x"})  # missing required
    assert catalog.validate_tool_input("move_event", {"assignment_id": 1, "extra": 2})
    assert catalog.validate_tool_input("does_not_exist", {})


def test_catalog_dict_matches_schema_and_prompt_mentions_every_kind():
    out = CatalogOut.model_validate(catalog.catalog_dict())
    assert {k.kind for k in out.kinds} == set(catalog.KINDS)
    assert all(k.title["tr"] and k.description["en"] for k in out.kinds)
    prompt = catalog.catalog_prompt("tr")
    assert all(kind in prompt for kind in catalog.KINDS)
