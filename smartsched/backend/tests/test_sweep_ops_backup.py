"""Sweeper 2026-10-18: ``GET /ops/status`` reports the last successful backup.

deploy/backup.sh writes ``smartsched_backup_last_success_timestamp_seconds`` into the textfile
``/var/lib/smartsched/textfile/backup.prom`` (mounted read-only into the backend; ``OPS_BACKUP_TEXTFILE``). Without
the file the card falls back to Prometheus, and says ``unknown`` when neither has it. Older than 26 h is ``warn``
(the SmartSchedBackupStale alert's threshold).
"""

from __future__ import annotations

import time
from pathlib import Path

from app.api.v1 import ops

from tests.api_fixtures import login

METRIC = "smartsched_backup_last_success_timestamp_seconds"


def _write(path: Path, ts: float) -> None:
    path.write_text(f"# HELP {METRIC} last successful backup (unix time)\n# TYPE {METRIC} gauge\n{METRIC} {ts:.0f}\n")


def test_parse_textfile_metric() -> None:
    assert ops.parse_backup_metric(f"# HELP {METRIC} x\n{METRIC} 1760745600\n") == 1760745600.0
    assert ops.parse_backup_metric(f'{METRIC}{{host="a"}} 1.7607456e+09\n') == 1760745600.0
    assert ops.parse_backup_metric("other_metric 5\n") is None
    assert ops.parse_backup_metric("") is None


async def test_status_backup_card_fresh_and_stale(client, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    admin = await login(client)
    for key in ("OPS_GRAFANA_URL", "OPS_PROMETHEUS_URL", "OPS_LOKI_URL", "OPS_PODCI_URL"):
        monkeypatch.delenv(key, raising=False)
    prom = tmp_path / "backup.prom"
    monkeypatch.setenv("OPS_BACKUP_TEXTFILE", str(prom))

    d = (await client.get("/api/v1/ops/status", headers=admin)).json()
    assert d["backup"]["status"] == "unknown" and d["backup"]["last_success_at"] is None

    _write(prom, time.time() - 3 * 3600)
    b = (await client.get("/api/v1/ops/status", headers=admin)).json()["backup"]
    assert b["status"] == "ok" and b["source"] == "textfile"
    assert 2.9 <= b["age_h"] <= 3.1 and b["last_success_at"].endswith("Z")
    assert b["stale_after_h"] == 26

    _write(prom, time.time() - 30 * 3600)
    b = (await client.get("/api/v1/ops/status", headers=admin)).json()["backup"]
    assert b["status"] == "warn" and b["age_h"] >= 29.9
