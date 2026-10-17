"""VO-02 metering and limits: one ``ai_usage`` row per transcription (``feature=voice_stt``, ``modality=audio_in``,
``audio_ms``, cost, ``detail=target=…``), per-minute prices (table + admin override), audio-second limits per user
(10 min/day, 100 min/month by default), per role and per person, the org monthly audio budget, audio minutes in the
reports and in ``GET /ai/me/usage``, and the migration on SQLite (and PostgreSQL when a server is available)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.ai import pipeline
from app.ai.client import STT_PRICE_TABLE_VERSION, estimate_stt_cost
from app.ai.voice.speech import Transcript
from app.core.db import get_session_factory
from app.main import BACKEND_DIR
from app.models import User
from app.models.ai_usage import AIUsage
from app.services import ai_usage as meter
from sqlalchemy import create_engine, inspect, select, text

from tests.ai.voice_support import add_user, configure, install_fake, openai_stub, transcribe, wav
from tests.api_fixtures import login
from tests.pg_support import pg_server  # noqa: F401
from tests.test_crbs_migration import _run

REV = "0042_ai_usage_audio"


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


async def _used(user_email: str, seconds: float) -> None:
    async with get_session_factory()() as s:
        uid = (await s.execute(select(User.id).where(User.email == user_email))).scalar_one()
        s.add(
            AIUsage(
                user_id=uid,
                feature="voice_stt",
                provider="openai",
                model="gpt-4o-mini-transcribe",
                outcome="ok",
                modality="audio_in",
                audio_ms=int(seconds * 1000),
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await s.commit()


def test_per_minute_prices():
    assert estimate_stt_cost("openai", "gpt-4o-mini-transcribe", 60) == (0.003, STT_PRICE_TABLE_VERSION)
    assert estimate_stt_cost("openai", "gpt-transcribe", 120) == (0.009, STT_PRICE_TABLE_VERSION)
    assert estimate_stt_cost("azure_openai", "gpt-4o-mini-transcribe-2025-12-15", 30)[0] == 0.0015
    assert estimate_stt_cost("openai", "whisper-1", 60)[0] == 0.006
    assert estimate_stt_cost("deepgram", "nova-3", 60) == (0.0, "unpriced")
    assert estimate_stt_cost("deepgram", "nova-3", 90, prices={"deepgram:nova-3": 0.0048}) == (0.0072, "admin")


async def test_one_row_per_transcription(client, monkeypatch):
    openai_stub()
    h = await configure(client)
    install_fake(monkeypatch, Transcript(text="B 204", duration_s=12.5))
    r = await transcribe(client, h, wav(12.5))
    assert r.status_code == 200, r.text
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(AIUsage).where(AIUsage.feature == "voice_stt"))).scalars())
    assert len(rows) == 1
    row = rows[0]
    assert (row.modality, row.audio_ms, row.outcome, row.detail) == ("audio_in", 12500, "ok", "target=chat")
    assert row.cost_usd == pytest.approx(0.000625) and row.price_version == STT_PRICE_TABLE_VERSION
    assert row.prompt_sha256 and len(row.prompt_sha256) == 64
    # a text row stays a text row
    async with get_session_factory()() as s:
        s.add(AIUsage(feature="chat", provider="anthropic", model="claude-opus-5-5", outcome="ok"))
        await s.commit()
        text_row = (await s.execute(select(AIUsage).where(AIUsage.feature == "chat"))).scalar_one()
    assert (text_row.modality, text_row.audio_ms) == ("text", 0)


async def test_daily_limit_refuses_at_601_seconds(client, monkeypatch):
    openai_stub()
    h = await configure(client)
    fake = install_fake(monkeypatch)
    await _used("admin@example.com", 595)
    r = await transcribe(client, h, wav(6))
    assert r.status_code == 429
    d = r.json()["detail"]
    assert d["code"] == "ai_voice_limit_reached" and d["message_tr"] and d["message_en"]
    assert d["used_s"] == 595 and d["limit_s"] == 600 and d["scope"] == "user_daily"
    assert fake.calls == []
    assert (await transcribe(client, h, wav(5))).status_code == 200  # 600 s exactly is allowed
    st = (await client.get("/api/v1/ai/voice/status", headers=h)).json()
    assert st["available"] is False and st["reason"] == "limit_reached"


async def test_role_and_person_overrides_win(client, monkeypatch):
    openai_stub()
    h = await configure(client)
    install_fake(monkeypatch, *[Transcript(text="x", duration_s=6.0)] * 3)
    await add_user("planner@example.com", "PLANNER")
    hp = await login(client, "planner@example.com", "parola-1234")
    assert (await client.post("/api/v1/me/consents/voice", headers=hp)).status_code == 200
    await _used("planner@example.com", 598)
    assert (await transcribe(client, hp, wav(6))).status_code == 429
    r = await client.put("/api/v1/ai/admin/limits", json={"roles": {"PLANNER": {"audio_daily": 1200}}}, headers=h)
    assert r.status_code == 200, r.text
    assert (await transcribe(client, hp, wav(6))).status_code == 200
    async with get_session_factory()() as s:
        uid = (await s.execute(select(User.id).where(User.email == "planner@example.com"))).scalar_one()
    r = await client.put("/api/v1/ai/admin/limits", json={"users": {str(uid): {"audio_daily": 300}}}, headers=h)
    assert r.status_code == 200
    assert (await transcribe(client, hp, wav(6))).status_code == 429
    r = await client.put("/api/v1/ai/admin/limits", json={"roles": {"PLANNER": {"audio_weekly": 5}}}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_limit"


async def test_monthly_and_org_audio_limits(client, monkeypatch):
    openai_stub()
    h = await configure(client)
    install_fake(monkeypatch)
    r = await client.put(
        "/api/v1/ai/admin/limits",
        json={"user_daily_audio_s": 0, "user_monthly_audio_s": 0, "org_monthly_audio_s": 100},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["org_monthly_audio_s"] == 100
    await _used("admin@example.com", 98)
    r = await transcribe(client, h, wav(5))
    assert r.status_code == 429 and r.json()["detail"]["scope"] == "org_audio"


async def test_org_cost_budget_includes_voice(client, monkeypatch):
    openai_stub()
    h = await configure(client)
    install_fake(monkeypatch)
    r = await client.put("/api/v1/ai/admin/limits", json={"org_monthly_cost_usd": 0.0001}, headers=h)
    assert r.status_code == 200
    r = await transcribe(client, h, wav(60))
    assert r.status_code == 429 and r.json()["detail"]["code"] == "ai_budget_exceeded"


async def test_reports_and_my_usage_have_audio_minutes(client, monkeypatch):
    openai_stub()
    h = await configure(client)
    install_fake(monkeypatch, Transcript(text="a", duration_s=30.0), Transcript(text="b", duration_s=60.0))
    assert (await transcribe(client, h, wav(30))).status_code == 200
    assert (await transcribe(client, h, wav(60), feature="rules")).status_code == 200
    days = (await client.get("/api/v1/ai/admin/usage?group=day", headers=h)).json()["rows"]
    assert sum(d["audio_minutes"] for d in days) == pytest.approx(1.5)
    by_user = (await client.get("/api/v1/ai/admin/usage?group=user", headers=h)).json()["rows"]
    assert by_user[0]["audio_minutes"] == pytest.approx(1.5)
    by_feature = {r["key"]: r for r in (await client.get("/api/v1/ai/admin/usage?group=feature", headers=h)).json()["rows"]}
    assert by_feature["voice_stt"]["audio_minutes"] == pytest.approx(1.5)
    me = (await client.get("/api/v1/ai/me/usage", headers=h)).json()
    assert me["day_audio_s"] == 90 and me["month_audio_s"] == 90
    assert me["audio_daily_limit_s"] == 600 and me["audio_monthly_limit_s"] == 6000


def test_single_head_is_the_audio_migration() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    assert script.get_revision(REV) is not None


def test_sqlite_round_trip(tmp_path) -> None:
    path = tmp_path / "a.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, REV)
    con = sqlite3.connect(path)
    cols = {r[1]: r for r in con.execute("pragma table_info(ai_usage)")}
    assert {"audio_ms", "modality"} <= set(cols)
    con.execute(
        "insert into ai_usage (created_at, feature, provider, model, input_tokens, output_tokens, cache_read_tokens,"
        " cache_write_tokens, cost_usd, latency_ms, outcome, prompt_chars)"
        " values ('2026-10-17 09:00:00', 'chat', 'anthropic', 'claude-opus-5-5', 1, 1, 0, 0, 0, 0, 'ok', 0)"
    )
    con.commit()
    assert con.execute("select audio_ms, modality from ai_usage").fetchall() == [(0, "text")]
    con.close()
    prev = ScriptDirectory.from_config(_cfg()).get_revision(REV).down_revision
    _run(url, command.downgrade, str(prev))
    con = sqlite3.connect(path)
    assert "audio_ms" not in {r[1] for r in con.execute("pragma table_info(ai_usage)")}
    assert con.execute("select count(*) from ai_usage").fetchone()[0] == 1
    con.close()


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def test_postgres_round_trip(pg_server) -> None:  # noqa: F811
    import uuid

    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    prev = str(ScriptDirectory.from_config(_cfg()).get_revision(REV).down_revision)
    try:
        _run(url, command.upgrade, REV)
        eng = create_engine(url)
        cols = {c["name"]: c for c in inspect(eng).get_columns("ai_usage")}
        assert {"audio_ms", "modality"} <= set(cols)
        with eng.begin() as c:
            c.execute(
                text(
                    "insert into ai_usage (created_at, feature, provider, model, input_tokens, output_tokens,"
                    " cache_read_tokens, cache_write_tokens, cost_usd, latency_ms, outcome, prompt_chars)"
                    " values (now(), 'chat', 'anthropic', 'claude-opus-5-5', 1, 1, 0, 0, 0, 0, 'ok', 0)"
                )
            )
            assert c.execute(text("select audio_ms, modality from ai_usage")).one() == (0, "text")
        eng.dispose()
        _run(url, command.downgrade, prev)
        eng = create_engine(url)
        assert "audio_ms" not in {c["name"] for c in inspect(eng).get_columns("ai_usage")}
        eng.dispose()
        _run(url, command.upgrade, "head")
    finally:
        admin.dispose()
        drop = create_engine(pg_server, isolation_level="AUTOCOMMIT")
        with drop.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        drop.dispose()
