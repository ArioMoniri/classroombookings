"""The browser e2e stack of gate e2e-real.sh: SMTP sink, the empty second backend and the entry script modes.

docs/ROADMAP.md "Test-stack follow-ups": an SMTP sink so the SMTP settings / test message / outbox rows (S-23,
X-02) can be driven without e-mailing anyone, and a second, empty backend for the installer requirements step
(B-SETUP-02). Docker and python are replaced by recording fakes on PATH; the sink runs for real.
"""

from __future__ import annotations

import json
import os
import smtplib
import socket
import subprocess
import sys
import time
import urllib.request
from email.message import EmailMessage
from pathlib import Path

import pytest
from podfakes import POD_CI

GATES = POD_CI / "gates"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def sink():  # type: ignore[no-untyped-def]
    smtp_port, api_port = free_port(), free_port()
    proc = subprocess.Popen([sys.executable, str(GATES / "smtp-sink.py"), "--host", "127.0.0.1",
                             "--smtp-port", str(smtp_port), "--api-port", str(api_port)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    api = f"http://127.0.0.1:{api_port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{api}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("smtp sink did not start: " + proc.stdout.read().decode() if proc.stdout else "")
        yield smtp_port, api
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def get_json(url: str, method: str = "GET") -> object:
    with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=5) as r:
        return json.loads(r.read())


def mail(subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "SmartSched <noreply@smartsched.local>"
    msg["To"] = "teacher@smartsched.local"
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def test_smtp_sink_captures_plain_and_authenticated_mail(sink) -> None:  # type: ignore[no-untyped-def]
    port, api = sink
    # security "none" (bookings_settings SMTP_SPECS), like the backend's bookings_notify._send
    with smtplib.SMTP("127.0.0.1", port, timeout=5) as s:
        s.send_message(mail("Reset code", "Your code is 123456\n.\nline after a lone dot"))
    with smtplib.SMTP("127.0.0.1", port, timeout=5) as s:
        s.login("smartsched", "not-stored")  # any credentials are accepted, the password is never kept
        s.send_message(mail("Test message", "SMTP works"))
    got = get_json(f"{api}/messages")
    assert isinstance(got, list) and [m["subject"] for m in got] == ["Reset code", "Test message"]
    first, second = got
    assert first["to"] == ["teacher@smartsched.local"] and first["from"] == "noreply@smartsched.local"
    assert "123456" in first["text"] and "\n.\nline after a lone dot" in first["text"]  # dot-unstuffed
    assert first["auth_user"] is None and second["auth_user"] == "smartsched"
    assert "not-stored" not in json.dumps(got)
    assert get_json(f"{api}/messages", "DELETE") == {"deleted": 2}
    assert get_json(f"{api}/messages") == []


def test_smtp_sink_offers_no_starttls(sink) -> None:  # type: ignore[no-untyped-def]
    """The backend default security is starttls: against the sink that must fail loudly (outbox FAILED with
    the error), never silently send in clear text."""
    port, _ = sink
    with smtplib.SMTP("127.0.0.1", port, timeout=5) as s:
        s.ehlo()
        assert not s.has_extn("starttls")
        with pytest.raises(smtplib.SMTPNotSupportedError):
            s.starttls()


# ---- gate wiring with a recording docker fake ------------------------------------------------------------

FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
case "$1" in
  exec) [[ -f "$FAKE_DIR/unhealthy" ]] && exit 1; exit 0 ;;
  logs|rm|network) exit 0 ;;
esac
exit 0
"""


def gate_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    return {
        "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "docker.log"),
        "FAKE_DIR": str(tmp_path), "WS": str(tmp_path / "ws"), "CACHE_DIR": str(tmp_path / "cache"),
        "RUN_TAG": "7-abc1234", "CI_UID": "1000", "CI_GID": "1000", "GATES_DIR": str(GATES),
        "PY_IMAGE": "smartsched-podci-python:x", "PW_IMAGE": "mcr.microsoft.com/playwright:v1-noble",
        "E2E_HEALTH_TRIES": "2", "E2E_HEALTH_SLEEP": "0",
    }


def built(env: dict[str, str]) -> dict[str, str]:
    """The e2e-build gate's output in the run's source tree (.next with BUILD_ID, cache/ and standalone/)."""
    nxt = Path(env["WS"]) / "src/smartsched/frontend/.next"
    for sub in ("cache", "standalone", "server/app"):
        (nxt / sub).mkdir(parents=True, exist_ok=True)
    (nxt / "BUILD_ID").write_text("b1")
    (nxt / "server/app/page.js").write_text("x")
    return env


def e2e_real(env: dict[str, str], shard: str = "2/3") -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(GATES / "e2e-real.sh"), shard], env=env, capture_output=True, text=True,
                          timeout=60)


def test_e2e_real_starts_smtp_sink_and_empty_backend_for_playwright(tmp_path: Path) -> None:
    env = built(gate_env(tmp_path))
    r = e2e_real(env, "2/3")
    assert r.returncode == 0, r.stdout + r.stderr
    calls = (tmp_path / "docker.log").read_text().splitlines()
    runs = [c for c in calls if c.startswith("run ")]
    detached = [c for c in runs if c.startswith("run -d ")]
    seeded = next(c for c in detached if "--network-alias backend " in c and "e2e-backend-entry.sh" in c)
    # the shard's own DB / uploads directory; the venv of the backend-deps gate
    assert "-e E2E_WORKDIR=/w/e2e-shard-2 " in seeded and "-e E2E_VENV=/w/venv " in seeded
    smtp = next(c for c in detached if "--network-alias smtp " in c)
    assert "/ci/smtp-sink.py" in smtp and "--smtp-port 1025" in smtp and "--api-port 8025" in smtp
    empty = next(c for c in detached if "--network-alias backend-empty " in c)
    assert "-e E2E_EMPTY=1" in empty and "-e E2E_VENV=/w/venv" in empty
    assert "-e E2E_WORKDIR=/w/e2e-shard-2/empty" in empty
    # the empty backend shares the seeded backend's venv: it starts only once that one is healthy
    first_exec = next(i for i, c in enumerate(calls) if c.startswith("exec "))
    assert calls.index(empty) > first_exec
    idp = next(c for c in detached if "w3-idp-mock-issuer.py" in c)
    assert "--network container:podci-7-abc1234-e2e2-backend " in idp
    playwright = runs[-1]
    log = (tmp_path / "docker.log").read_text()  # the playwright script spans several lines of the log
    # the e2e-build gate built .next once: the shard never builds, it only starts its private copy
    assert "npx next build" not in log and "--no-mock-build" not in log
    assert 'npx playwright test --shard="${E2E_SHARD}" --workers=1 --reporter=list,json' in log
    for flag in ("-e E2E_REAL=1", "-e W3_IDP_EXTERNAL=1", "--network container:podci-7-abc1234-e2e2-backend",
                 "-e E2E_SHARD=2/3", "-e E2E_SMTP_HOST=smtp", "-e E2E_SMTP_PORT=1025",
                 "-e E2E_SMTP_API=http://smtp:8025", "-e E2E_EMPTY_API_URL=http://backend-empty:8000",
                 "-e E2E_DB=/w/e2e-shard-2/e2e.db", "-e PLAYWRIGHT_JSON_OUTPUT_NAME=/w/playwright-report-2.json",
                 f"-v {env['WS']}/e2e-shard-2/next:/w/src/smartsched/frontend/.next",
                 f"-v {env['WS']}/e2e-shard-2/test-results:/w/src/smartsched/frontend/test-results"):
        assert flag in playwright, flag
    assert not any("contract-record.py" in c for c in calls)  # shard 1 records the contract payloads
    assert any(c.startswith("network create ") and c.endswith(" podci-7-abc1234-e2e2") for c in calls)
    assert any(c == "network rm podci-7-abc1234-e2e2" for c in calls)
    for name in ("backend", "smtp", "backend-empty", "idp"):
        assert any(c.startswith("rm -f ") and f"podci-7-abc1234-e2e2-{name}" in c for c in calls)
    # the private build copy is gone afterwards (no cache/ or standalone/ was copied); test-results stay
    ws = Path(env["WS"])
    assert not (ws / "e2e-shard-2/next").exists() and (ws / "e2e-shard-2/test-results").is_dir()


def test_e2e_real_copies_the_build_without_cache_and_standalone(tmp_path: Path) -> None:
    env = built(gate_env(tmp_path))
    fake = tmp_path / "bin/docker"
    # snapshot the shard's copy while "playwright" runs (cleanup removes it afterwards)
    fake.write_text(FAKE_DOCKER.replace('printf \'%s\\n\' "$*" >> "$FAKE_LOG"',
                                        'printf \'%s\\n\' "$*" >> "$FAKE_LOG"\n'
                                        '[[ "$*" == *E2E_SHARD=* ]] && (cd "$WS/e2e-shard-1/next" && find . | sort '
                                        '> "$FAKE_DIR/copy.txt")'))
    r = e2e_real(env, "1/3")
    assert r.returncode == 0, r.stdout + r.stderr
    copy = (tmp_path / "copy.txt").read_text().split()
    assert "./BUILD_ID" in copy and "./server/app/page.js" in copy
    assert not any(c.startswith(("./cache", "./standalone")) for c in copy)
    calls = (tmp_path / "docker.log").read_text().splitlines()
    record = [c for c in calls if "contract-record.py" in c]
    assert len(record) == 1 and "--out /w/contract " in record[0]  # one recording per run, from shard 1


def test_e2e_real_needs_the_e2e_build_output_and_a_valid_shard(tmp_path: Path) -> None:
    env = gate_env(tmp_path)
    r = e2e_real(env, "1/3")
    assert r.returncode == 1 and "e2e-build gate builds it" in r.stdout
    assert not (tmp_path / "docker.log").exists()  # nothing started
    for i, bad in enumerate(("x; rm -rf /", "4/3", "0/3", "")):
        (tmp_path / str(i)).mkdir()
        b = e2e_real(built(gate_env(tmp_path / str(i))), bad)
        assert b.returncode != 0 and ("bad shard" in b.stdout or "usage" in b.stderr), bad


def test_e2e_real_fails_when_the_seeded_backend_never_gets_healthy(tmp_path: Path) -> None:
    env = built(gate_env(tmp_path))
    (tmp_path / "unhealthy").write_text("")
    r = e2e_real(env, "1/3")
    assert r.returncode != 0
    assert "not healthy" in r.stdout
    calls = (tmp_path / "docker.log").read_text().splitlines()
    assert not any("--network-alias backend-empty " in c for c in calls)  # nothing started after a dead backend
    assert any(c.startswith("logs ") for c in calls)


def test_e2e_build_builds_once_for_every_shard_and_checks_for_mock_code(tmp_path: Path) -> None:
    r = subprocess.run(["bash", str(GATES / "e2e-build.sh")], env=gate_env(tmp_path), capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    log = (tmp_path / "docker.log").read_text()
    run = next(c for c in log.splitlines() if c.startswith("run "))
    # the alias every shard's seeded backend has on its own network: one build serves all shards
    assert "-e NEXT_PUBLIC_API_URL=http://backend:8000" in run and "--max-old-space-size=3072" in run
    assert log.index("npx next build") < log.index("validate.sh --no-mock-build .next/standalone")


# ---- e2e-backend-entry.sh modes with fake python / alembic -----------------------------------------------

def entry_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    rec = tmp_path / "calls.log"
    for tool in ("python", "alembic"):
        (bin_dir / tool).write_text(
            f"#!/usr/bin/env bash\nprintf '{tool} %s | ADMIN_EMAIL=%s ADMIN_PASSWORD=%s DB=%s\\n' \"$*\" "
            f"\"${{ADMIN_EMAIL-unset}}\" \"${{ADMIN_PASSWORD:+set}}\" \"$DATABASE_URL\" >> {rec}\n")
        (bin_dir / tool).chmod(0o755)
    return {"PATH": f"{bin_dir}:/usr/bin:/bin", "E2E_WORKDIR": str(tmp_path / "w"), "E2E_VENV": "none", **extra}


def test_entry_seeded_mode_imports_seeds_and_solves(tmp_path: Path) -> None:
    r = subprocess.run(["bash", str(GATES / "e2e-backend-entry.sh")], env=entry_env(tmp_path), cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    calls = (tmp_path / "calls.log").read_text()
    assert "alembic upgrade head" in calls and "import weekly-grid" in calls and "seed-admin" in calls
    assert "solve --term 2026-BAHAR" in calls and "e2e-backend-serve.py" in calls
    assert "ADMIN_EMAIL=admin@smartsched.local ADMIN_PASSWORD=set" in calls
    # the room master before every solve
    order = [ln.split(" |")[0] for ln in calls.splitlines()]
    at = lambda needle: next(i for i, ln in enumerate(order) if needle in ln)  # noqa: E731
    assert at("import room-master") < at("solve --term 2026-BAHAR")
    # the analytics runs before the full-term run: the screens open the term's latest usable run
    final_grid = at("import weekly-grid --source seed tests/fixtures/final_")
    assert final_grid < at("e2e-seed-analytics.py") < at("solve --term 2026-BAHAR")
    # the Güz 2026-27 workbooks (grid + planning list) after Bahar and before Final (Final keeps the newest term id),
    # before the analytics seed that publishes the Güz board; Güz gets no solver run (e2e-gate-seed 2026-10-17)
    assert (
        at("import weekly-grid --source seed tests/fixtures/bahar_")
        < at("import weekly-grid --source seed tests/fixtures/guz_")
        < at("import planning-list --source seed tests/fixtures/guz_")
        < at("import weekly-grid --source seed tests/fixtures/final_")
    )
    assert at("import planning-list --source seed tests/fixtures/guz_") < at("e2e-seed-analytics.py")
    assert "solve --term 2026-GUZ" not in calls
    assert at("solve --term 2026-BAHAR") < at("e2e-backend-serve.py")


def test_entry_empty_mode_migrates_only_and_seeds_no_admin(tmp_path: Path) -> None:
    env = entry_env(tmp_path, E2E_EMPTY="1", E2E_ADMIN_EMAIL="admin@smartsched.local")
    r = subprocess.run(["bash", str(GATES / "e2e-backend-entry.sh")], env=env, cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "calls.log").read_text().splitlines()
    assert [ln.split(" |")[0].split()[:2] for ln in lines] == [["alembic", "upgrade"],
                                                             ["python", str(GATES / "e2e-backend-serve.py")]]
    # no users and no ADMIN_* -> the first-run installer (requirements step) is reachable
    assert all("ADMIN_EMAIL= ADMIN_PASSWORD= " in ln for ln in lines)
    assert all(f"DB=sqlite+aiosqlite:///{tmp_path / 'w'}/e2e.db" in ln for ln in lines)
