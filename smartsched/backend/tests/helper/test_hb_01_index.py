"""HB-01 feature index (``app/ai/helper/features.yaml``) and the no-AI search core (``app/ai/helper/index.py``).

* the YAML validates (pydantic, ``extra="forbid"``), ids are unique, every TR string has an EN twin, ≤ 3 steps;
* every route has a ``page.tsx`` in ``smartsched/frontend/src/app``; every anchor is a WG / helper.md anchor;
* every ``href`` of ``nav-config.ts``, ``admin/nav-items.ts``, ``lib/permissions.ts`` ``ADMIN_SECTIONS`` and
  ``wave1-sections.ts`` has a ``page`` entry with the **same** any-of permission set and ``hide_with``;
* the CRBS words of helper.md §3.2 are indexed on their entries;
* ``where_queries.json`` (≥ 120 persona queries, typos, ASCII-folded) scores top-1 ≥ 85 % and top-3 ≥ 95 %, offline;
* an academician never gets a ``setup.*`` or ``/admin`` entry, whatever they type.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from app.ai.helper import index
from app.services.bookings_perms import ROLE_DEFAULTS

FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "src"
FIXTURES = Path(__file__).parent / "fixtures"

#: data-tour anchors that exist or are asked for: welcome-guide.md §13 and helper.md §3.4
ANCHORS = frozenset(
    """nav-reserve nav-bookings nav-my-bookings nav-find-room nav-my-requests nav-approvals nav-dashboard nav-onboarding
    nav-requests nav-generate nav-timetable nav-moderation nav-runs nav-heatmap nav-admin nav-integrations
    nav-welcome-admin user-menu reserve-when approvals-row-actions admin-group-users admin-group-resources
    admin-group-timetable admin-users-invite admin-holidays-add admin-periods admin-weeks admin-access-rules
    admin-approval-rules admin-mail admin-sso profile-calendar profile-notifications profile-ai-usage
    profile-helper-memory reserve-room-list find-room-filters my-bookings-cancel runs-publish runs-export
    bookings-export helper-attach""".split()
)

#: helper.md §3.2: entry id -> CRBS words that must be indexed (folded)
CRBS_WORDS: dict[str, list[str]] = {
    "bookings": ["booking", "rezervasyon", "ayırma", "salon ayır", "oda ayır"],
    "admin.rooms": ["room", "oda", "derslik", "salon", "amfi", "lab"],
    "admin.schedules": ["period", "ders saati", "saat dilimi", "zaman çizelgesi"],
    "admin.weeks": ["week", "hafta", "a/b haftası"],
    "admin.sessions": ["session", "dönem", "yarıyıl", "term"],
    "admin.holidays": ["holiday", "tatil", "resmi tatil"],
    "admin.departments": ["department", "bölüm", "birim"],
    "admin.users": ["user", "kullanıcı", "hesap", "davet"],
    "admin.settings": ["settings", "ayarlar"],
    "admin.authentication": ["ldap", "sso", "giriş"],
    "admin.access": ["access", "erişim", "kim ayırabilir", "izin"],
}

PERSONAS: dict[str, frozenset[str]] = {
    "teacher": frozenset(ROLE_DEFAULTS["TEACHER"]["permissions"]),
    "approver": frozenset(ROLE_DEFAULTS["TEACHER"]["permissions"] | {"approvals.decide"}),
    "planner": frozenset(ROLE_DEFAULTS["PLANNER"]["permissions"]),
    "admin": frozenset(ROLE_DEFAULTS["ADMIN"]["permissions"]),
}


# ------------------------------------------------------------------------------------------- frontend parsing


def _page_routes() -> list[re.Pattern[str]]:
    out = []
    for page in (FRONTEND / "app").rglob("page.tsx"):
        parts = [p for p in page.relative_to(FRONTEND / "app").parent.parts if not p.startswith("(")]
        if any(p.startswith("[...") for p in parts):
            continue  # the catch-all 404 page matches everything
        rx = "/" + "/".join(r"[^/]+" if p.startswith("[") else re.escape(p) for p in parts)
        out.append(re.compile(rf"^{rx}$" if parts else r"^/$"))
    return out


def _string_list(text: str, name: str) -> list[str]:
    m = re.search(rf"export const {name}\s*=\s*\[(.*?)\]", text, re.S)
    assert m, name
    return re.findall(r'"([^"]+)"', m.group(1))


def _nav_items() -> list[tuple[str, frozenset[str], str | None, str]]:
    """(href, any-of permissions, hideWith, source file) for every nav entry the shell can list."""
    setup = _string_list((FRONTEND / "lib/permissions.ts").read_text(), "SETUP_PERMISSIONS")
    files = [
        FRONTEND / "components/shell/nav-config.ts",
        FRONTEND / "components/admin/nav-items.ts",
        FRONTEND / "lib/permissions.ts",
        FRONTEND / "components/admin/wave1-sections.ts",
    ]
    out = []
    for f in files:
        for line in f.read_text().splitlines():
            m = re.search(r'\bhref:\s*"(/[^"]*)"', line)
            if not m:
                continue
            perm: list[str] = []
            pm = re.search(r"\bpermission:\s*(\"[^\"]+\"|\[[^\]]*\])", line)
            if pm:
                raw = pm.group(1)
                perm = list(setup) if "...SETUP_PERMISSIONS" in raw else re.findall(r'"([^"]+)"', raw)
            hm = re.search(r'\bhideWith:\s*"([^"]+)"', line)
            out.append((m.group(1), frozenset(perm), hm.group(1) if hm else None, f.name))
    assert len(out) >= 35, "the nav parser found too few entries"
    return out


# ------------------------------------------------------------------------------------------------- tests


def test_hb_01_index_loads_with_unique_ids_and_twins() -> None:
    idx = index.get_index()
    ids = [e.id for e in idx.entries]
    assert len(ids) == len(set(ids)) >= 50
    for e in idx.entries:
        assert e.title.tr.strip() and e.title.en.strip(), e.id
        assert len(e.path.tr) == len(e.path.en) >= 1, e.id
        assert len(e.steps.tr) == len(e.steps.en) <= 3, e.id
        assert e.synonyms.tr and e.synonyms.en, e.id


def test_hb_01_duplicate_id_or_unknown_field_is_refused(tmp_path) -> None:
    good = (Path(index.__file__).with_name("features.yaml")).read_text()
    dup = tmp_path / "dup.yaml"
    first = good.split("\n- id: ")[1]
    dup.write_text(good + "\n- id: " + first)
    with pytest.raises(index.IndexInvalid):
        index.load(dup)
    extra = tmp_path / "extra.yaml"
    extra.write_text(good.replace("  kind: page\n", "  kind: page\n  url: https://example.org\n", 1))
    with pytest.raises(index.IndexInvalid):
        index.load(extra)


def test_hb_01_every_route_has_a_page() -> None:
    routes = _page_routes()
    for e in index.get_index().entries:
        path = re.split(r"[?#]", e.route)[0]
        assert any(rx.match(path) for rx in routes), f"{e.id}: no page.tsx for {path}"


def test_hb_01_anchors_are_known() -> None:
    for e in index.get_index().entries:
        assert e.anchor is None or e.anchor in ANCHORS, f"{e.id}: unknown anchor {e.anchor}"


def test_hb_01_every_nav_href_has_an_entry_with_the_same_permission() -> None:
    pages = {}
    for e in index.get_index().entries:
        if e.kind == "page":
            assert e.route not in pages, f"two page entries for {e.route}"
            pages[e.route] = e
    for href, perm, hide, src in _nav_items():
        e = pages.get(href)
        assert e is not None, f"{src}: {href} has no page entry in features.yaml"
        assert frozenset(e.permission) == perm, f"{href}: index {sorted(e.permission)} != {src} {sorted(perm)}"
        if src != "permissions.ts":  # ADMIN_SECTIONS has no hideWith
            assert e.hide_with == hide, f"{href}: hide_with {e.hide_with} != {hide}"


def test_hb_01_crbs_vocabulary_is_indexed() -> None:
    by_id = {e.id: e for e in index.get_index().entries}
    for entry_id, words in CRBS_WORDS.items():
        e = by_id[entry_id]
        have = {index.fold_phrase(s) for s in (*e.synonyms.tr, *e.synonyms.en, e.title.tr, e.title.en)}
        for w in words:
            assert index.fold_phrase(w) in have, f"{entry_id}: CRBS word {w!r} not indexed"


def test_hb_01_where_queries_top1_and_top3() -> None:
    cases = json.loads((FIXTURES / "where_queries.json").read_text())
    assert len(cases) >= 120
    idx = index.get_index()
    top1 = top3 = 0
    misses = []
    for c in cases:
        hits = [h.entry.id for h in idx.search(c["q"], PERSONAS[c["persona"]], limit=3)]
        top1 += bool(hits) and hits[0] == c["expect"]
        top3 += c["expect"] in hits
        if not hits or hits[0] != c["expect"]:
            misses.append((c["persona"], c["q"], c["expect"], hits))
    n = len(cases)
    assert top1 / n >= 0.85, f"top-1 {top1}/{n}; misses: {misses}"
    assert top3 / n >= 0.95, f"top-3 {top3}/{n}; misses: {misses}"


def test_hb_01_expected_entries_are_visible_to_their_persona() -> None:
    idx = index.get_index()
    by_id = {e.id: e for e in idx.entries}
    for c in json.loads((FIXTURES / "where_queries.json").read_text()):
        assert index.visible(by_id[c["expect"]], PERSONAS[c["persona"]]), c


def test_hb_01_academician_never_gets_setup_pages() -> None:
    idx = index.get_index()
    teacher = PERSONAS["teacher"]
    queries = [c["q"] for c in json.loads((FIXTURES / "where_queries.json").read_text())]
    queries += ["kullanıcı davet", "kullanıcı ekle", "roller", "salon ekle", "tatil ekle", "ldap", "denetim kaydı"]
    for q in queries:
        for h in idx.search(q, teacher, limit=10):
            assert not any(p.startswith("setup.") for p in h.entry.permission), (q, h.entry.id)
            assert not h.entry.route.startswith("/admin"), (q, h.entry.id)


def test_hb_01_hide_with_hides_the_entry() -> None:
    idx = index.get_index()
    planner = PERSONAS["planner"] | {"book_single.create"}
    assert all(h.entry.id != "my_requests" for h in idx.search("taleplerim", planner, limit=10))
    assert idx.search("taleplerim", PERSONAS["teacher"], limit=1)[0].entry.id == "my_requests"


def test_hb_01_fold_handles_turkish_letters() -> None:
    assert index.fold_phrase("İPTAL ŞİFRE Değiştir") == index.fold_phrase("iptal sifre degistir")
    assert "rezervasyon" in index.terms("rezervasyonlarımı")
    assert "tatil" in index.terms("tatiller")
    assert "salon" in index.terms("salonları")
