"""KVKK in the intake review and memory (T-R1-22) on the real Bahar planning list.

* Merge item ids are opaque (a hash of the folded pair): a viewer's review payload (``content=false``) holds no
  spelling of any person the job read, in no id, title or field.
* The intake memory row of a merge keeps the pair's hash and its kind, never an item id or a name; a row written
  before the fix is scrubbed by the listing.
* ``Hatırlanan kararlar`` names the pair for planners only while both spellings are live instructor names: after
  the people are renamed (masking / erasure) it reads "Birleştirme (öğretim elemanı)".
* The decided merge still applies at commit and is recalled by the next upload of the same file.

The tests compare against the names the job itself read; no name is written in this file."""

from __future__ import annotations

import json

from app.core.db import get_session_factory
from app.council import storage
from app.models import CouncilJob, Instructor, LearnedObservation
from sqlalchemy import select, update

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST
from tests.council.test_formats_api import upload
from tests.council.test_intake_memory_api import _viewer


async def _people(job_id: int) -> set[str]:
    """Every person spelling the job read (instructor fields of the records and both sides of each merge)."""
    async with get_session_factory()() as s:
        job = await s.get(CouncilJob, job_id)
        assert job is not None
        out: set[str] = set()
        for recs in (await storage.records_by_file(s, job)).values():
            for r in recs:
                for k in ("instructor", "instructors"):
                    v = r.get(k)
                    for name in v if isinstance(v, list) else [v]:
                        if isinstance(name, str) and len(name.strip()) > 3:
                            out.add(name.strip())
        ds = await storage.latest(s, job_id, "dataset")
        for m in ds.payload.get("merges", []) if ds else []:
            if m["kind"] == "instructor":
                out |= {m["a"], m["b"]}
    return out


def _leaks(payload: object, names: set[str]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False)
    return sorted(n for n in names if n in text)


async def test_merge_ids_are_opaque_and_memory_keeps_no_names(client):
    h = await login(client)
    job = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()))
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    merges = [it for it in review["items"] if it["kind"] == "merge" and it["current"]["kind"] == "instructor"]
    assert merges, "the Bahar list has instructor spellings the reconciler could not settle"
    names = await _people(job["id"])
    assert len(names) > 50
    # ids are opaque for everyone; planners see the pair inside `current`
    assert all(it["id"].startswith("merge:instructor:") and not _leaks(it["id"], names) for it in merges)
    assert all(it["current"]["a"] in names for it in merges)

    hv = await _viewer(client)
    seen = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=hv)).json()
    assert seen["content"] is False
    assert _leaks(seen, names) == []

    # decide the merges: the remembered rows hold hashes and kinds only
    decisions = [{"id": it["id"], "action": "accept"} for it in merges]
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/review", headers=h, json={"decisions": decisions})
    assert r.status_code == 200 and r.json()["errors"] == []
    async with get_session_factory()() as s:
        rows = (
            (await s.execute(select(LearnedObservation).where(LearnedObservation.kind == "intake_merge")))
            .scalars()
            .all()
        )
    assert len(rows) == len(merges)
    assert all("item" not in (r.detail or {}) and r.detail["merge_kind"] == "instructor" for r in rows)
    assert _leaks([[r.subject_key, r.attribute, r.value, r.detail] for r in rows], names) == []

    # commit: the accepted merges apply through the opaque ids
    body = {"group": 0, "term": {"code": "2026-BAHAR-KVKK", "week_count": 14}, "allow_pending": True}
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["general"].get("merges_applied", 0) == len(merges)

    # Hatırlanan kararlar: names for planners while they are live instructor names, never for viewers
    listing = (await client.get("/api/v1/council/memory?kind=intake_merge", headers=h)).json()
    named = [it for it in listing["items"] if it["context"].get("a")]
    assert named and all(it["context"]["a"] in names for it in named)
    assert _leaks((await client.get("/api/v1/council/memory", headers=hv)).json(), names) == []

    # masking renames every person: the memory names nobody any more, for planners too
    async with get_session_factory()() as s:
        ids = (await s.execute(select(Instructor.id))).scalars().all()
        for i in ids:
            await s.execute(update(Instructor).where(Instructor.id == i).values(full_name=f"Dr. X{i}."))
        await s.commit()
    listing = (await client.get("/api/v1/council/memory?kind=intake_merge", headers=h)).json()
    assert _leaks(listing, names) == []
    assert {g["label"]["tr"] for g in listing["groups"]} == {"Birleştirme (öğretim elemanı)"}

    # the next upload of the same file recalls the decisions by the pair's hash
    again = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()))
    rv = (await client.get(f"/api/v1/council/jobs/{again['id']}/review", headers=h)).json()
    recalled = [it for it in rv["items"] if it["kind"] == "merge" and it.get("remembered")]
    assert {it["id"] for it in recalled} == {it["id"] for it in merges}


async def test_legacy_merge_rows_lose_their_names(client):
    """A merge row stored before T-R1-22 (``item`` = ``merge:<kind>:<a>|<b>``) is scrubbed by the listing."""
    h = await login(client)
    job = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()))
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    m = next(it for it in review["items"] if it["kind"] == "merge")
    await client.post(
        f"/api/v1/council/jobs/{job['id']}/review", headers=h, json={"decisions": [{"id": m["id"], "action": "accept"}]}
    )
    legacy = f"merge:{m['current']['kind']}:{m['current']['a']}|{m['current']['b']}"
    async with get_session_factory()() as s:
        row = (
            await s.execute(select(LearnedObservation).where(LearnedObservation.kind == "intake_merge"))
        ).scalar_one()
        row.detail = {"item": legacy, "action": "accept", "at": "2026-10-16T09:00"}
        await s.commit()
    await client.get("/api/v1/council/memory", headers=h)
    async with get_session_factory()() as s:
        row = (
            await s.execute(select(LearnedObservation).where(LearnedObservation.kind == "intake_merge"))
        ).scalar_one()
    assert row.detail == {"merge_kind": m["current"]["kind"], "action": "accept", "at": "2026-10-16T09:00"}
