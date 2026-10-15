"""Contract fixture drift (ROADMAP Phase 6: "re-record src/lib/api/__fixtures__/real/*.json whenever backend schemas
change; a CI job could run the backend, record and diff"). gates/contract-record.py records the GET payloads the
contract test uses from the e2e backend and compares their *shape* with the committed fixtures."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
from podfakes import POD_CI


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("contract_record", POD_CI / "gates/contract-record.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["contract_record"] = mod
    spec.loader.exec_module(mod)
    return mod


cr = load()


def test_shape_merges_list_elements_and_marks_optional_keys() -> None:
    s = cr.shape([{"id": 1, "name": "A", "floor": None}, {"id": 2, "floor": "1"}])
    assert s == {"list": {"object": {"id": "number", "name": "string?", "floor": "null|string"}}}
    assert cr.shape([]) == {"list": "empty"}


def test_diff_reports_removed_added_and_type_changes() -> None:
    old = {"object": {"id": "number", "code": "string", "stats": {"object": {"unplaced": "number"}}}}
    new = {"object": {"id": "string", "stats": {"object": {"unplaced": "number", "phase": "string"}},
                      "source_ref": "null"}}
    d = cr.diff(old, new)
    assert ("removed", "$.code") in {(k, p) for k, p, _ in d}
    assert ("added", "$.source_ref") in {(k, p) for k, p, _ in d}
    assert ("added", "$.stats.phase") in {(k, p) for k, p, _ in d}
    assert ("type", "$.id") in {(k, p) for k, p, _ in d}
    # null vs a value and an empty list vs a filled one are not drift (data, not schema)
    assert cr.diff({"object": {"a": "null"}}, {"object": {"a": "string"}}) == []
    assert cr.diff({"list": "empty"}, {"list": {"object": {"id": "number"}}}) == []


class Api(BaseHTTPRequestHandler):
    payloads: ClassVar[dict[str, Any]] = {}

    def _send(self, code: int, body: Any) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # login
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send(200, {"access_token": "tok", "expires_in": 60})

    def do_GET(self) -> None:
        if self.headers.get("Authorization") != "Bearer tok":
            self._send(401, {"detail": "no"})
            return
        path = self.path.removeprefix("/api/v1")
        self._send(200, self.payloads[path]) if path in self.payloads else self._send(404, {"detail": path})

    def log_message(self, *a: Any) -> None:
        return


@pytest.fixture
def api():  # type: ignore[no-untyped-def]
    Api.payloads = {
        "/auth/me": {"id": 1, "email": "a@b", "role": "ADMIN", "language": "tr"},
        "/terms": [{"id": 7, "code": "2026-BAHAR"}],
        "/runs": [{"id": 3, "status": "FEASIBLE"}],
    }
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_records_and_reports_drift_against_committed_fixtures(api: str, tmp_path: Path) -> None:
    committed = tmp_path / "committed"
    committed.mkdir()
    (committed / "me.json").write_text(json.dumps({"id": 1, "email": "a@b", "role": "ADMIN", "full_name": "x"}))
    (committed / "terms.json").write_text(json.dumps([{"id": 1, "code": "X"}]))
    (committed / "run_infeasible.json").write_text("{}")  # scenario fixture: not recorded, listed
    out = tmp_path / "out"
    rc = cr.main(["--api", api, "--out", str(out), "--compare", str(committed), "--only", "me", "terms", "runs"])
    assert rc == 0  # report only
    report = json.loads((out / "contract-drift.json").read_text())
    assert report["fixtures"]["me"]["drift"] == [["removed", "$.full_name", "string"],
                                                 ["added", "$.language", "string"]]
    assert report["fixtures"]["terms"]["drift"] == []
    assert report["fixtures"]["runs"]["status"] == "no committed fixture"
    assert "run_infeasible" in report["not_recorded"]
    assert json.loads((out / "me.json").read_text())["language"] == "tr"  # the recorded payload, ready to copy
    assert cr.main(["--api", api, "--out", str(out), "--compare", str(committed), "--only", "me",
                    "--fail-on-drift"]) == 1


def test_endpoint_errors_are_reported_not_fatal(api: str, tmp_path: Path) -> None:
    rc = cr.main(["--api", api, "--out", str(tmp_path / "o"), "--compare", str(tmp_path), "--only", "buildings"])
    assert rc == 0
    report = json.loads((tmp_path / "o/contract-drift.json").read_text())
    assert report["fixtures"]["buildings"]["status"].startswith("HTTP 404")


def test_e2e_real_records_the_contract_payloads() -> None:
    text = (POD_CI / "gates/e2e-real.sh").read_text()
    assert "python /ci/contract-record.py" in text and "/w/contract" in text
    assert "src/lib/api/__fixtures__/real" in text
