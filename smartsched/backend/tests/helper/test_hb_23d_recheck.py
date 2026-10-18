"""HB-23d: the parent's KVKK re-check conditions on the helper file router (N1, N2, N5, N6, N7, N8, N9).

docs/design/v3/helper-file-router.md §6.3 / §6.5a and docs/kvkk/helper-file-stage.md. Fixtures: the repository's
own workbooks and the synthetic files under ``tests/fixtures/helper_files`` (initials only).
"""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

from app.ai.helper import files as hf
from app.core.config import get_settings

from tests.api_fixtures import login
from tests.helper import test_file_router as router_tests
from tests.helper.test_file_router import BAHAR_LIST, FIX, HF, C, card_of, classify, person, stage_files

rc = router_tests.rc  # the router tests' API client fixture (terms, thread parse, clean rate limiter and stage)

REPO = Path(__file__).resolve().parents[4]
NOTE = REPO / "docs" / "kvkk" / "helper-file-stage.md"
DEPLOY = REPO / "smartsched" / "deploy"
CRBS_DUMP = HF / "crbs_schema_only.sql"


def live_stages() -> list[Path]:
    return [p for p in stage_files() if p.suffix in (".bin", ".claimed")]


def flat(text: str) -> str:
    """The note's markdown quote as one line (line breaks and ``>`` markers gone)."""
    return re.sub(r"\s+", " ", re.sub(r"\n>\s?", " ", text))


# ------------------------------------------------------------------------------------- N1 (d): 10 minutes


async def test_an_expired_stage_is_deleted_when_it_is_read(rc, monkeypatch):
    """A stage past its expiry is refused on read and deleted then, without waiting for the sweeper."""
    h = await login(rc)
    token = (await card_of(rc, h, BAHAR_LIST))["stage"]["upload_token"]
    assert len(live_stages()) == 1
    real = hf.now()
    monkeypatch.setattr(hf, "now", lambda: real + hf.STAGE_TTL_S + 1)
    r = await rc.post(f"{C}/route", json={"upload_token": token, "kind": "planning_list"}, headers=h)
    assert r.status_code == 410 and r.json()["detail"]["code"] == "stage_expired"
    assert live_stages() == []


async def test_the_sweeper_deletes_a_stage_before_its_ten_minutes_end(rc, monkeypatch):
    """The sweeper runs at least every 30 s and deletes a stage one interval before its 10 minutes end, so no stage
    file outlives its expiry (docs/kvkk/helper-file-stage.md "at most 10 minutes")."""
    assert hf.SWEEP_INTERVAL_S <= 30
    assert inspect.signature(hf.start_sweeper).parameters["interval"].default == hf.SWEEP_INTERVAL_S
    h = await login(rc)
    await card_of(rc, h, BAHAR_LIST)
    real = hf.now()
    monkeypatch.setattr(hf, "now", lambda: real + 5)
    assert hf.sweep() == 0 and len(live_stages()) == 1  # a young stage stays
    # the last sweep before the 10-minute mark: from here the next tick would be after the expiry
    monkeypatch.setattr(hf, "now", lambda: real + hf.STAGE_TTL_S - hf.SWEEP_INTERVAL_S + 1)
    assert hf.sweep() >= 1 and live_stages() == []


async def test_the_sweep_loop_uses_the_short_interval(monkeypatch):
    seen: list[float] = []

    async def fake_sleep(s: float) -> None:
        seen.append(s)
        raise asyncio.CancelledError

    monkeypatch.setattr(hf, "sweep", lambda: 0)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    try:
        await hf._sweep_loop(hf.SWEEP_INTERVAL_S)  # noqa: SLF001
    except asyncio.CancelledError:
        pass
    assert seen == [hf.SWEEP_INTERVAL_S]


# ------------------------------------------------------------------------------- N1 (a-c), N2: the wording


def test_notice_paragraph_says_what_happens():
    text = flat(NOTE.read_text(encoding="utf-8"))
    # (a) the file only becomes an import record on Preview; data is written only with Apply
    assert "Siz Önizle'ye ve ardından Uygula'ya basana kadar hiçbir veri kaydedilmez" not in text
    assert (
        "Dosya, siz açılan sayfada Önizle'ye basana kadar içe aktarma kaydına dönüşmez; veriler yalnızca Uygula ile "
        "kayıtlara işlenir." in text
    )
    assert "Nothing is saved until you press Preview and then Apply" not in text
    assert (
        "The file becomes an import record only when you press Preview on the page that opens; data is written to "
        "the records only with Apply." in text
    )
    # (b) part of the key, not the key
    assert "şifre anahtarı yalnızca sizin tarayıcınızdadır" not in text
    assert "the key is held only by your browser" not in text
    assert "anahtarın bir parçası yalnızca tarayıcınızda tutulur; sunucu tek başına dosyayı açamaz" in text
    assert "part of the key is kept only in your browser; the server cannot open the file on its own" in text
    # (c) the legal basis of the import it belongs to, in both languages
    assert "Hukuki sebep: KVKK m.5/2(f)" not in text and "Legal basis: KVKK Art. 5(2)(f)" not in text
    assert "Hukuki sebep: KVKK m.5/2(c), (ç) ve (f)" in text
    assert "Legal basis: KVKK Art. 5(2)(c), (ç) and (f)" in text
    # N2: the Import page's own drops are covered too
    assert "Yardımcıya ya da İçe aktar sayfasına seçtiğiniz dosyalar" in text
    assert "Files you pick in the helper or on the Import page" in text


def test_inventory_key_text_matches_the_crypto():
    """The stage key is HKDF(token part, info from APP_SECRET): the server holds one part, the token the other."""
    from app.services import kvkk

    stage = kvkk.DATA_CLASSES["helper_file_stage"]
    assert "sunucu anahtarı tutmaz" not in stage["kept"]
    assert "anahtarın bir parçası" in stage["kept"] and "sunucu tek başına" in stage["kept"]
    assert "m.5/2(c), (ç), (f)" in stage["legal_basis"]
    assert "İçe aktar" in stage["tr"] and "Import page" in stage["en"]


# --------------------------------------------------------------------------------- N9: a new drop clears


async def _staged(rc, h) -> None:  # type: ignore[no-untyped-def]
    await card_of(rc, h, BAHAR_LIST)
    assert len(live_stages()) == 1


async def test_rate_limited_drop_clears_the_previous_stage(rc, monkeypatch):
    h = await login(rc)
    await _staged(rc, h)
    monkeypatch.setattr(hf, "rate_ok", lambda user_id: False)
    out = await card_of(rc, h, BAHAR_LIST)
    assert out["card"]["code"] == "rate_limited" and live_stages() == []


async def test_refused_drop_clears_the_previous_stage(rc):
    h = await login(rc)
    await _staged(rc, h)
    out = await card_of(rc, h, name="bos.xlsx", data=b"")
    assert out["card"]["type"] == "refusal" and live_stages() == []


async def test_resend_drop_clears_the_previous_stage(rc, monkeypatch):
    h = await login(rc)
    await _staged(rc, h)
    monkeypatch.setattr(get_settings(), "helper_file_stage", False)
    out = await card_of(rc, h, BAHAR_LIST)
    assert out["resend"] is True and "stage" not in out and live_stages() == []


async def test_too_large_drop_clears_the_previous_stage(rc, monkeypatch):
    h = await login(rc)
    await _staged(rc, h)
    monkeypatch.setattr(get_settings(), "council_max_file_mb", 1)
    r = await classify(rc, h, name="buyuk.csv", data=b"a;b\n" * (300 * 1024))
    assert r.status_code == 413 and live_stages() == []


# ------------------------------------------------------------------------- N8: several files, non-planner


async def test_several_files_from_a_non_planner_are_refused(rc):
    admin = await login(rc)
    teacher = await person(rc, admin, "akad.hd@uni.edu.tr", role="TEACHER")
    await card_of(rc, teacher, BAHAR_LIST)  # a TEACHER gets my_classes (no stage); nothing to clear but harmless
    r = await rc.post(
        f"{C}/classify",
        files=[
            ("file", (BAHAR_LIST.name, BAHAR_LIST.read_bytes(), "application/octet-stream")),
            ("file", ("room_master.csv", (FIX / "room_master.csv").read_bytes(), "text/csv")),
        ],
        headers=teacher,
    )
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["code"] == "one_file_only" and "bir dosya" in d["message_tr"] and "one file" in d["message_en"]
    # a planner still gets the setup-wizard card
    r = await rc.post(
        f"{C}/classify",
        files=[
            ("file", (BAHAR_LIST.name, BAHAR_LIST.read_bytes(), "application/octet-stream")),
            ("file", ("room_master.csv", (FIX / "room_master.csv").read_bytes(), "text/csv")),
        ],
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["card"]["primary"]["feature_id"] == "onboarding"


# --------------------------------------------------------------------------- N5: exactly one upload_token


async def test_crbs_import_refuses_a_token_with_a_dsn_and_keeps_the_stage(rc):
    h = await login(rc)
    token = (await card_of(rc, h, CRBS_DUMP))["stage"]["upload_token"]
    r = await rc.post(
        "/api/v1/imports/crbs", data={"dsn": "mysql://crbs:x@crbs-db.uni.edu.tr/crbs", "upload_token": token}, headers=h
    )
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["code"] == "dsn_or_token" and d["message_tr"] and d["message_en"]
    assert len(live_stages()) == 1  # not consumed


async def test_crbs_import_takes_one_token_and_refuses_several(rc):
    h = await login(rc)
    token = (await card_of(rc, h, CRBS_DUMP))["stage"]["upload_token"]
    r = await rc.post("/api/v1/imports/crbs", data={"upload_tokens": [token, token]}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "one_upload_token", r.text
    assert len(live_stages()) == 1
    r = await rc.post("/api/v1/imports/crbs", data={"upload_token": token}, headers=h)
    assert r.status_code == 202, r.text
    assert r.json()["filename"].endswith(".sql") and live_stages() == []
    # a used token is refused before any job exists
    r = await rc.post("/api/v1/imports/crbs", data={"upload_token": token}, headers=h)
    assert r.status_code == 410 and r.json()["detail"]["code"] == "stage_used"


async def test_council_takes_one_token_and_refuses_several(rc):
    h = await login(rc)
    token = (await card_of(rc, h, FIX / "room_master.csv"))["stage"]["upload_token"]
    r = await rc.post("/api/v1/council/jobs", data={"upload_tokens": [token, token], "ai": "false"}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "one_upload_token", r.text
    assert len(live_stages()) == 1
    r = await rc.post("/api/v1/council/jobs", data={"upload_token": token, "ai": "false"}, headers=h)
    assert r.status_code == 202, r.text
    assert len(r.json()["files"]) == 1 and live_stages() == []


async def test_handoff_takes_exactly_one_token(rc):
    h = await login(rc)
    token = (await card_of(rc, h, BAHAR_LIST))["stage"]["upload_token"]
    body = {"upload_tokens": [token, token], "feature_id": "onboarding"}
    r = await rc.post(f"{C}/handoff", json=body, headers=h)
    assert r.status_code == 422, r.text
    r = await rc.post(f"{C}/handoff", json={"feature_id": "onboarding"}, headers=h)
    assert r.status_code == 422
    r = await rc.post(f"{C}/handoff", json={"upload_token": token, "feature_id": "onboarding"}, headers=h)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------------- N6: one CRBS upgrade at a time


async def test_one_crbs_upgrade_at_a_time(rc, monkeypatch):
    from app.services import crbs_upgrade as up

    h = await login(rc)
    started, release = asyncio.Event(), asyncio.Event()

    class Rep:
        def to_dict(self) -> dict[str, bool]:
            return {"dry_run": True}

    async def slow_dry_run(source, *, filename=None):  # type: ignore[no-untyped-def]
        started.set()
        await release.wait()
        return Rep()

    monkeypatch.setattr(up, "dry_run", slow_dry_run)
    files = [("files", (CRBS_DUMP.name, CRBS_DUMP.read_bytes(), "application/sql"))]
    first = asyncio.create_task(rc.post("/api/v1/crbs-upgrade", files=files, headers=h))
    await asyncio.wait_for(started.wait(), 10)
    try:
        r = await asyncio.wait_for(rc.post("/api/v1/crbs-upgrade", files=files, headers=h), 10)
    finally:
        release.set()  # never leave the first request hanging
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "crbs_upgrade_busy" and d["message_tr"] and d["message_en"]
    assert (await asyncio.wait_for(first, 10)).status_code == 200
    # the lock is released: the next one runs
    r = await rc.post("/api/v1/crbs-upgrade", files=files, headers=h)
    assert r.status_code == 200, r.text


def test_tmpfs_budget_is_documented_and_wired():
    env = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^BACKEND_TMPFS=\d+m$", env, re.M)
    i, j = env.index("BACKEND_MEMORY="), env.index("BACKEND_TMPFS=")
    assert abs(env.count("\n", 0, i) - env.count("\n", 0, j)) <= 12  # next to BACKEND_MEMORY
    compose = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/tmp:size=${BACKEND_TMPFS:-256m},mode=1777" in compose


# ------------------------------------------------------------------------------------- N7: nginx comment


def test_nginx_classify_comment_does_not_claim_streaming():
    conf = (DEPLOY / "nginx" / "default.conf").read_text(encoding="utf-8")
    block = conf[conf.index("# Helper file router") : conf.index("location = /api/v1/helper/files/classify")]
    assert "bodies streamed" not in block and "arrayBuffer" in block


# ------------------------------------------------------------------- UX-27: a newer file replaced the stage
async def test_a_stage_replaced_by_a_newer_file_says_so(rc):
    """HB-23d UX-27: one live stage per person (N9), so a classify in another window replaces the older stage. Its
    token then answers 410 ``stage_replaced`` with its own words, not "the file expired (10 minutes)"."""
    h = await login(rc)
    first = (await card_of(rc, h, BAHAR_LIST))["stage"]["upload_token"]
    await card_of(rc, h, FIX / "room_master.csv")  # the same person, another window
    for path, body in (
        (f"{C}/route", {"upload_token": first, "kind": "planning_list"}),
        (
            f"{C}/handoff",
            {
                "upload_token": first,
                "kind": "planning_list",
                "feature_id": "import",
                "params": {"kind": "planning-list"},
            },
        ),
    ):
        r = await rc.post(path, json=body, headers=h)
        assert r.status_code == 410, r.text
        d = r.json()["detail"]
        assert d["code"] == "stage_replaced" and "pencere" in d["message_tr"] and "10 dakika" not in d["message_tr"]
    assert len(live_stages()) == 1  # the newer file is untouched
