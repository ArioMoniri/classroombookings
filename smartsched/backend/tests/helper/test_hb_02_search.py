"""HB-02 ``GET /helper/search``: index hits as ``nav`` cards (pages / "Nerede?") plus data hits through the person's
own rights, with no AI and no metering. 4 personas x 10 queries on the real Bahar 2026 data; a source the person may
not read is skipped and named, never a 403; p95 < 50 ms per request (process CPU time); Turkish-first strings."""

from __future__ import annotations

import statistics
import time

from app.ai.helper import schema
from app.ai.helper.index import get_index, visible
from app.core import db as dbmod
from app.models import AIUsage
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, personas

QUERIES = {
    "teacher": ["salon ayır", "rezervasyonlarım", "iptal", "şifre", "takvim", "boş derslik", "A 102", "PHAR",
                "bildirim", "kullanıcı davet"],
    "approver": ["bekleyen talepler", "reddet", "onay", "A 102", "rezervasyon", "takvim", "bildirim", "şifre",
                 "salon bul", "tatil"],
    "planner": ["planı yayınla", "çalıştırma", "talepler", "PHAR", "PHAR 240", "A 102", "çizelge", "içe aktar",
                "gözetmen", "rapor"],
    "admin": ["tatil", "ders saatleri", "periods", "kullanıcı davet", "ldap", "salon ekle", "A 102", "PHAR",
              "kvkk", "yapay zeka"],
}


async def test_hb_02_four_personas_ten_queries(env) -> None:  # noqa: F811
    people = await personas(env)
    idx = get_index()
    timings: list[tuple[float, str, str]] = []
    for name, qs in QUERIES.items():
        p = people[name]
        for q in qs:
            t0 = time.process_time()
            r = await env.client.get(f"{H}/search", params={"q": q}, headers=p.headers)
            # CPU time of the whole request in this process (the ASGI stack + the SQLite thread): the host runs
            # several builders at once, so wall time measures the load average, not the search
            timings.append(((time.process_time() - t0) * 1000, name, q))
            assert r.status_code == 200, (name, q, r.text)
            out = r.json()
            for group in ("pages", "where"):
                assert len(out[group]) <= 6
                for c in out[group]:
                    schema.validate_card(c)
                    assert c["type"] == "nav"
                    entry = idx.by_id[c["feature_id"]]
                    assert visible(entry, p.perms), (name, q, c["feature_id"])
                    assert c["title"]["tr"] and c["title"]["en"]
                    # "Burada yap" only names actions the person may run
                    assert set(c.get("actions", [])) <= set(entry.actions)
            assert sum(len(v) for v in out["data"].values()) + len(out["pages"]) + len(out["where"]) <= 24
    p95 = statistics.quantiles([t for t, *_ in timings], n=20)[-1]
    assert p95 < 50, sorted(timings, reverse=True)[:8]
    async with dbmod.get_session_factory()() as s:  # no AI, no metering
        assert (await s.execute(select(func.count(AIUsage.id)))).scalar_one() == 0


async def test_hb_02_forbidden_sources_are_skipped_not_fatal(env) -> None:  # noqa: F811
    people = await personas(env)
    t = (await env.client.get(f"{H}/search", params={"q": "PHAR"}, headers=people["teacher"].headers)).json()
    assert {s["source"] for s in t["skipped"]} == {"courses", "instructors", "programs"}
    assert "courses" not in t["data"]
    p = (await env.client.get(f"{H}/search", params={"q": "PHAR", "term_id": env.term_id},
                              headers=people["planner"].headers)).json()
    assert p["skipped"] == []
    assert p["data"]["courses"] and all(c["label"].startswith("PHAR") for c in p["data"]["courses"])
    assert p["data"]["sections"]


async def test_hb_02_rooms_match_with_or_without_the_space(env) -> None:  # noqa: F811
    people = await personas(env)
    for q in ("A 102", "a102", "A102"):
        out = (await env.client.get(f"{H}/search", params={"q": q}, headers=people["teacher"].headers)).json()
        labels = [r["label"] for r in out["data"].get("rooms", [])]
        assert "A 102" in labels, (q, labels)


async def test_hb_02_academician_gets_no_admin_page(env) -> None:  # noqa: F811
    people = await personas(env)
    for q in ("kullanıcı davet", "salon ekle", "ldap", "tatil ekle", "roller ve izinler"):
        out = (await env.client.get(f"{H}/search", params={"q": q}, headers=people["teacher"].headers)).json()
        ids = [c["feature_id"] for c in out["pages"] + out["where"]]
        assert not [i for i in ids if i.startswith("admin")], (q, ids)


async def test_hb_02_question_flag_and_auth(env) -> None:  # noqa: F811
    people = await personas(env)
    h = people["teacher"].headers
    assert (await env.client.get(f"{H}/search", params={"q": "nasıl iptal ederim"}, headers=h)).json()["question"]
    assert (await env.client.get(f"{H}/search", params={"q": "iptal?"}, headers=h)).json()["question"]
    assert not (await env.client.get(f"{H}/search", params={"q": "iptal"}, headers=h)).json()["question"]
    assert (await env.client.get(f"{H}/search", params={"q": "iptal"})).status_code == 401
