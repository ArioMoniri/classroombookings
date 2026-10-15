"""Record the frontend contract-test payloads from a running e2e backend and report schema drift.

ROADMAP Phase 6: ``smartsched/frontend/src/lib/api/__fixtures__/real/*.json`` (parsed by contract.test.ts) must be
re-recorded whenever backend schemas change. The pod CI gate e2e-real.sh runs this inside the seeded backend
container once it is healthy (stdlib only, image python), writes every payload to ``--out`` (ready to copy over
the fixtures) and ``contract-drift.json``, and prints one line per fixture. It compares *shapes* (keys and value
types, list elements merged), not values: a field removed, added or retyped is drift; null vs a value and an
empty vs a filled list are data. Report only: exit 0 unless ``--fail-on-drift``.

    python contract-record.py --api http://127.0.0.1:8000 --out /w/contract \
        --compare /w/src/smartsched/frontend/src/lib/api/__fixtures__/real
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# fixture name -> GET path ({term} = first term, {run} = first feasible run), as the UI calls them (endpoints.ts)
FIXTURES: dict[str, str] = {
    "me": "/auth/me",
    "terms": "/terms",
    "weeks": "/terms/{term}/weeks",
    "rooms": "/rooms",
    "buildings": "/buildings",
    "programs": "/programs?limit=500",
    "users": "/users",
    "settings": "/settings",
    "runs": "/runs",
    "dashboard": "/dashboard?term_id={term}",
    "grid": "/runs/{run}/grid?week=3",
    "assignments": "/runs/{run}/assignments?week=3",
    "meetings": "/requests/meetings?limit=50",
    "meetings_needs_review": "/requests/meetings?status=NEEDS_REVIEW&limit=50",
    "imports": "/imports",
    "constraints": "/constraints?term_id={term}",
    "chat_empty": "/runs/{run}/chat",
    "ai_catalog": "/ai/catalog",
}
FEASIBLE = ("FEASIBLE", "OPTIMAL", "DONE", "SUCCEEDED")

Shape = Any


def _scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int | float):
        return "number"
    return "string" if isinstance(v, str) else type(v).__name__


def _union(a: str, b: str) -> str:
    return "|".join(sorted(set(a.split("|")) | set(b.split("|"))))


def _merge(a: Shape, b: Shape) -> Shape:
    if a == b:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        if "object" in a and "object" in b:
            ka, kb = a["object"], b["object"]
            out = {}
            for k in sorted(set(ka) | set(kb)):
                if k in ka and k in kb:
                    out[k] = _merge(ka[k], kb[k])
                else:
                    v = ka.get(k, kb.get(k))
                    out[k] = v + "?" if isinstance(v, str) and not v.endswith("?") else v
            return {"object": out}
        if "list" in a and "list" in b:
            if a["list"] == "empty":
                return b
            if b["list"] == "empty":
                return a
            return {"list": _merge(a["list"], b["list"])}
    if isinstance(a, str) and isinstance(b, str):
        opt = a.endswith("?") or b.endswith("?")
        return _union(a.rstrip("?"), b.rstrip("?")) + ("?" if opt else "")
    return "mixed"


def shape(v: Any) -> Shape:
    if isinstance(v, dict):
        return {"object": {k: shape(x) for k, x in sorted(v.items())}}
    if isinstance(v, list):
        if not v:
            return {"list": "empty"}
        s = shape(v[0])
        for x in v[1:]:
            s = _merge(s, shape(x))
        return {"list": s}
    return _scalar(v)


def _label(s: Shape) -> str:
    if isinstance(s, dict):
        return "object" if "object" in s else "list"
    return str(s).rstrip("?")


def _types(s: str) -> set[str]:
    return set(s.rstrip("?").split("|")) - {"null"}


def diff(old: Shape, new: Shape, path: str = "$") -> list[tuple[str, str, str]]:
    """(kind, path, detail) with kind removed / added / type; old = committed fixture, new = live payload."""
    if isinstance(old, dict) and isinstance(new, dict):
        if "object" in old and "object" in new:
            out: list[tuple[str, str, str]] = []
            ko, kn = old["object"], new["object"]
            for k in sorted(set(ko) | set(kn)):
                p = f"{path}.{k}"
                if k not in kn:
                    out.append(("removed", p, _label(ko[k])))
                elif k not in ko:
                    out.append(("added", p, _label(kn[k])))
                else:
                    out += diff(ko[k], kn[k], p)
            return out
        if "list" in old and "list" in new:
            if "empty" in (old["list"], new["list"]):
                return []
            return diff(old["list"], new["list"], path + "[]")
    if isinstance(old, str) and isinstance(new, str):
        a, b = _types(old), _types(new)
        return [] if not a or not b or a & b else [("type", path, f"{_label(old)} -> {_label(new)}")]
    if (isinstance(old, str) and old.rstrip("?") == "null") or (isinstance(new, str) and new.rstrip("?") == "null"):
        return []
    return [("type", path, f"{_label(old)} -> {_label(new)}")]


class Client:
    def __init__(self, api: str, email: str, password: str):
        if not api.startswith(("http://", "https://")):
            raise ValueError(f"--api must be an http(s) URL, got {api!r}")
        self.base = api.rstrip("/") + "/api/v1"
        req = urllib.request.Request(  # noqa: S310 - http(s) only, checked above
            self.base + "/auth/login", method="POST",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            self.token = json.loads(r.read())["access_token"]

    def get(self, path: str) -> Any:
        req = urllib.request.Request(self.base + path, headers={"Authorization": f"Bearer {self.token}"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
            return json.loads(r.read())


def _ids(client: Client, cache: dict[str, Any]) -> dict[str, Any]:
    if not cache:
        terms = client.get("/terms")
        runs = client.get("/runs")
        cache["term"] = terms[0]["id"] if terms else 0
        ok = [r for r in runs if str(r.get("status", "")).upper() in FEASIBLE]
        cache["run"] = (ok or runs or [{"id": 0}])[0]["id"]
    return cache


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--compare", type=Path, required=True, help="directory of the committed fixtures")
    ap.add_argument("--only", nargs="*", help="fixture names (default: all)")
    ap.add_argument("--fail-on-drift", action="store_true")
    ap.add_argument("--email", default=os.environ.get("E2E_ADMIN_EMAIL", "admin@smartsched.local"))
    ap.add_argument("--password", default=os.environ.get("E2E_ADMIN_PASSWORD", "Admin-2026!"))
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    client = Client(a.api, a.email, a.password)
    names = a.only or list(FIXTURES)
    ids: dict[str, Any] = {}
    fixtures: dict[str, dict[str, Any]] = {}
    for name in names:
        tmpl = FIXTURES[name]
        entry: dict[str, Any] = {"path": tmpl}
        try:
            path = tmpl.format(**_ids(client, ids)) if "{" in tmpl else tmpl
            entry["path"] = path
            live = client.get(path)
        except urllib.error.HTTPError as exc:
            entry["status"] = f"HTTP {exc.code} for {entry['path']}"
            fixtures[name] = entry
            continue
        except (OSError, ValueError, KeyError, IndexError) as exc:
            entry["status"] = f"error: {exc}"
            fixtures[name] = entry
            continue
        (a.out / f"{name}.json").write_text(json.dumps(live, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        committed = a.compare / f"{name}.json"
        if not committed.is_file():
            entry["status"] = "no committed fixture"
        else:
            entry["drift"] = [list(d) for d in diff(shape(json.loads(committed.read_text(encoding="utf-8"))),
                                                    shape(live))]
            entry["status"] = "drift" if entry["drift"] else "same shape"
        fixtures[name] = entry
    committed_names = sorted(p.stem for p in a.compare.glob("*.json")) if a.compare.is_dir() else []
    report = {"fixtures": fixtures, "not_recorded": [n for n in committed_names if n not in FIXTURES]}
    (a.out / "contract-drift.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    drifted = 0
    for name, e in fixtures.items():
        d = e.get("drift") or []
        drifted += bool(d)
        print(f"{name:<22} {e['status']}" + (f" ({len(d)}: " + "; ".join(f"{k} {p}" for k, p, _ in d[:4])
                                               + (" ..." if len(d) > 4 else "") + ")" if d else ""))
    if report["not_recorded"]:
        print("not recorded (scenario fixtures, re-record by hand): " + ", ".join(report["not_recorded"]))
    print(f"{drifted} fixture(s) drifted; payloads in {a.out}")
    return 1 if a.fail_on_drift and drifted else 0


if __name__ == "__main__":
    sys.exit(main())
