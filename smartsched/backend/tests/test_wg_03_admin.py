"""WG-03 welcome guide administration (docs/design/v3/welcome-guide.md §4.6, §6.4, §6.5, §7).

* ``GET/PUT /welcome/settings``, ``GET/PUT /welcome/content/{audience}`` (text only, TR/EN, 80/200 characters,
  placeholders ``{ad}``/``{name}``/``{bölüm}``/``{department}``; ``version`` -> 409 ``stale`` naming the other editor),
  ``POST /welcome/content/{audience}/reshow``, ``GET /welcome/stats?days=`` (aggregate, groups under 5 hidden, no
  per-person output); permission ``setup.settings`` or ``planning.admin``; every change audited;
* KVKK: the person's DSR export lists their ``welcome_progress`` rows, the erasure deletes them.

Real Bahar 2026 data (``tests/crbs_env``).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from app.core import db as dbmod
from app.models import AuditEvent, User
from app.models.welcome import WelcomeProgress
from app.services import kvkk
from app.services import welcome as wsvc
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.test_wg_01_welcome import academician, ev, get

W = "/api/v1/welcome"
T0 = datetime(2026, 10, 19, 9, 0)


@pytest.fixture
def clock(monkeypatch):  # type: ignore[no-untyped-def]
    now = {"t": T0}
    monkeypatch.setattr(wsvc, "_now", lambda: now["t"])
    return now


async def _actions() -> list[str]:
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(AuditEvent.action).order_by(AuditEvent.id))).scalars())


async def _admin_named(env, first: str, last: str, email: str):  # type: ignore[no-untyped-def]  # noqa: F811
    return await env.user(email, role="ADMIN", firstname=first, lastname=last)


async def test_wg_03_a_teacher_gets_403_everywhere(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    for method, path, body in (
        ("GET", f"{W}/settings", None),
        ("PUT", f"{W}/settings", {"sheet": False}),
        ("GET", f"{W}/content/academician", None),
        ("PUT", f"{W}/content/academician", {"version": 0, "fields": {"tr": {"title": "Merhaba"}}}),
        ("POST", f"{W}/content/academician/reshow", None),
        ("GET", f"{W}/stats", None),
        ("GET", W + "?preview=admin", None),
    ):
        r = await env.client.request(method, path, json=body, headers=h)
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["detail"]["message_tr"]


async def test_wg_03_switching_the_sheet_off_hides_it_and_is_audited(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    r = await env.client.get(f"{W}/settings", headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["settings"] == {
        "enabled": True,
        "sheet": True,
        "tour": True,
        "checklist": True,
        "hints": True,
        "hints_for_all": False,
        "min_cohort": 5,
    }
    r = await env.client.put(f"{W}/settings", json={"sheet": False}, headers=env.admin)
    assert r.status_code == 200 and r.json()["settings"]["sheet"] is False
    body = await get(env, h)
    assert body["show"] is None and body["enabled"]["sheet"] is False and body["suppressed"] == "disabled"
    r = await env.client.put(f"{W}/settings", json={"min_cohort": 3}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["message_tr"]
    assert "welcome.settings_update" in await _actions()


async def test_wg_03_texts_with_version_conflict_and_reshow(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    await ev(env, h, "sheet", "shown")
    await ev(env, h, "sheet", "completed")
    _gid, gozde = await _admin_named(env, "Gözde", "Ayrancıgil", "gozde.ayrancigil@uni.edu.tr")
    r = await env.client.get(f"{W}/content/academician", headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 0 and r.json()["fields"] == {"tr": {}, "en": {}}
    assert {"title", "lead", "cards.quick_reserve.title", "cards.quick_reserve.body"} <= {
        f["field"] for f in r.json()["editable"]
    }
    # Gözde saves first (an NBSP from a pasted Word text, a capital placeholder)
    r = await env.client.put(
        f"{W}/content/academician",
        json={"version": 0, "fields": {"tr": {"title": "Hoş geldiniz,  {AD}"}, "en": {"title": "Welcome, {name}"}}},
        headers=gozde,
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1 and r.json()["fields"]["tr"]["title"] == "Hoş geldiniz, {ad}"
    assert r.json()["updated_by"] == "Gözde Ayrancıgil"
    # the seeded admin still edits version 0: 409 stale, naming Gözde
    r = await env.client.put(
        f"{W}/content/academician", json={"version": 0, "fields": {"tr": {"lead": "Eski metin"}}}, headers=env.admin
    )
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "stale" and d["current_version"] == 1
    assert d["message_tr"] == "Bu metni siz düzenlerken Gözde Ayrancıgil değiştirdi. Sayfayı yenileyip yeniden deneyin."
    assert "Gözde Ayrancıgil" in d["message_en"]
    # limits and placeholders (TR/EN messages)
    for fields, code in (
        ({"tr": {"title": "x" * 81}}, "too_long"),
        ({"tr": {"lead": "y" * 201}}, "too_long"),
        ({"tr": {"lead": "Merhaba {soyad}"}}, "placeholder"),
        ({"tr": {"cards.quick_reserve.href": "/admin"}}, "invalid_field"),
        ({"de": {"title": "Willkommen"}}, "invalid_locale"),
    ):
        r = await env.client.put(f"{W}/content/academician", json={"version": 1, "fields": fields}, headers=env.admin)
        assert r.status_code == 422, (fields, r.text)
        assert r.json()["detail"]["code"] == code and r.json()["detail"]["message_tr"]
    # the academician reads the override in their locale; the sheet is not due (no "show again" asked)
    body = await get(env, h)
    assert body["sheet"]["overrides"]["title"] == "Hoş geldiniz, {ad}" and body["show"] is None
    # "Varsayılana dön": an empty text removes the override
    r = await env.client.put(
        f"{W}/content/academician", json={"version": 1, "fields": {"en": {"title": None}}}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["fields"]["en"] == {}
    # show again: the academician gets the sheet with "Güncellendi"
    r = await env.client.post(f"{W}/content/academician/reshow", headers=env.admin)
    assert r.status_code == 200 and r.json()["content_version"] == 1
    body = await get(env, h)
    assert body["show"] == {"kind": "sheet", "key": "sheet", "audiences": ["academician"], "updated": True}
    assert body["sheet"]["updated"] is True
    await ev(env, h, "sheet", "completed")
    assert (await get(env, h))["show"] is None
    # PUT with reshow=true bumps as well
    r = await env.client.put(
        f"{W}/content/academician",
        json={"version": 2, "fields": {"tr": {"lead": "Derslerinizi görün."}}, "reshow": True},
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json()["content_version"] == 2
    assert (await get(env, h))["show"]["updated"] is True
    acts = await _actions()
    assert acts.count("welcome.content_update") == 3 and acts.count("welcome.reshow") == 2
    r = await env.client.get(f"{W}/content/nobody", headers=env.admin)
    assert r.status_code == 404 and r.json()["detail"]["message_tr"]


async def test_wg_03_admin_preview_writes_nothing(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(W, params={"preview": "academician"}, headers=env.admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"] is True and body["primary"] == "academician"
    assert body["show"]["kind"] == "sheet" and [c["key"] for c in body["sheet"]["cards"]][0] == "quick_reserve"
    r = await env.client.post(f"{W}/events", json={"guide_key": "sheet", "event": "shown"}, headers=env.admin)
    assert r.status_code == 204
    async with dbmod.get_session_factory()() as s:
        n = (await s.execute(select(func.count()).select_from(WelcomeProgress))).scalar_one()
    assert n == 1  # only the admin's own event, nothing from the preview


async def _cohort(n: int, audience: str, *, dismissed: int = 0, toured: int = 0) -> list[int]:
    """``n`` people of ``audience`` who saw the sheet 10 days ago."""
    ids = []
    async with dbmod.get_session_factory()() as s:
        for i in range(n):
            u = User(email=f"kisi{i}.{audience}@uni.edu.tr", full_name=f"Kişi {i}", role="TEACHER")
            s.add(u)
            await s.flush()
            ids.append(u.id)
            shown = T0 - timedelta(days=10)
            s.add(
                WelcomeProgress(
                    user_id=u.id,
                    guide_key="sheet",
                    audience=audience,
                    audience_hash=wsvc.audience_hash([audience]),
                    content_version=0,
                    state="dismissed" if i < dismissed else "completed",
                    items={},
                    snooze_count=0,
                    first_shown_at=shown,
                    updated_at=shown,
                )
            )
            if i < toured:
                s.add(
                    WelcomeProgress(
                        user_id=u.id,
                        guide_key="tour",
                        audience=audience,
                        audience_hash="",
                        content_version=0,
                        state="completed",
                        items={},
                        snooze_count=0,
                        first_shown_at=shown,
                        updated_at=shown,
                        completed_at=shown,
                    )
                )
        await s.commit()
    return ids


async def test_wg_03_stats_hide_groups_under_five(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    await _cohort(4, "staff")
    await _cohort(5, "academician", dismissed=1, toured=2)
    r = await env.client.get(f"{W}/stats", params={"days": 30}, headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["days"] == 30 and out["min_cohort"] == 5
    by = {a["audience"]: a for a in out["audiences"]}
    assert by["staff"] == {
        "audience": "staff",
        "small_group": True,
        "shown": None,
        "tour_completed_pct": None,
        "checklist_80_pct": None,
        "dismissed_pct": None,
        "median_days_to_first_booking": None,
    }
    aca = by["academician"]
    assert aca["small_group"] is False and aca["shown"] == 5
    assert aca["tour_completed_pct"] == 40 and aca["dismissed_pct"] == 20 and aca["checklist_80_pct"] == 0
    # no per-person output anywhere
    flat = str(out)
    assert "user_id" not in flat and "@uni.edu.tr" not in flat and "Kişi" not in flat
    # outside the window: nobody
    r = await env.client.get(f"{W}/stats", params={"days": 7}, headers=env.admin)
    assert {a["audience"]: a for a in r.json()["audiences"]}["academician"]["small_group"] is True
    r = await env.client.get(f"{W}/stats", params={"days": 400}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["message_tr"]


async def test_wg_03_kvkk_export_lists_and_erasure_deletes_the_rows(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h = await academician(env)
    await ev(env, h, "sheet", "shown")
    await ev(env, h, "sheet", "snoozed")
    await ev(env, h, "tour", "step", step=3)
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, uid)
        assert user is not None
        data = await kvkk.export_data(s, user)
        rows = data["welcome_guide"]
        assert {r["guide"] for r in rows} == {"sheet", "tour"}
        sheet = next(r for r in rows if r["guide"] == "sheet")
        assert sheet["state"] == "snoozed" and sheet["snooze_count"] == 1
        assert "welcome_guide" in kvkk.EXPORT_FILES and "welcome" in kvkk.DATA_CLASSES
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        res = await kvkk.erase_user(s, admin, user)
        await s.commit()
        assert res["counts"]["welcome_progress"] == 2
        left = (
            await s.execute(select(func.count()).select_from(WelcomeProgress).where(WelcomeProgress.user_id == uid))
        ).scalar_one()
        assert left == 0
