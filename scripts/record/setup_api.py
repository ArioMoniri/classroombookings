#!/usr/bin/env python3
"""Configure the recording stack through the public API only (no database writes), like an administrator would.

    python3 scripts/record/setup_api.py API_URL EMAIL PASSWORD bookings [--language en]
    python3 scripts/record/setup_api.py API_URL EMAIL PASSWORD runs SPEC [SPEC ...]

bookings  the one-time CRBS setup that bookings.spec.ts also makes (18-period schedule from the grid, the
          current term open for bookings, one room group per building, the term's published board, a public
          holiday), term names from the workbooks, and the admin's profile language (the booking pages
          follow the profile language, not the browser).
          The current term is Güz 2026-27: its weekly grid holds only two calendar weeks, so the term's end
          date is derived from its imported week count (14 weeks from 21 Sep 2026).
runs      real solver runs through POST /runs (what the Generate button sends), one after another; a finished
          full-term run is then published (POST /runs/{id}/activate), as a planner would.
          SPEC = TERM_CODE:HORIZON:WEEK:TIME_LIMIT, e.g. 2026-GUZ:WEEK:3:120 or 2026-GUZ:TERM:-:240.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

NAMES = {"2026-BAHAR": "Bahar 2026", "2026-GUZ": "Güz 2026-27", "2026-FINAL": "Final 2026"}
LABEL = {"BAHAR": "Bahar", "GUZ": "Güz", "FINAL": "Final"}
# Republic Day (29 October) falls inside Güz 2026-27
HOLIDAY = {"term": "2026-GUZ", "name": "Cumhuriyet Bayramı", "date": "2026-10-29"}


class Api:
    def __init__(self, base: str, email: str, password: str) -> None:
        self.base = base.rstrip("/")
        self.token = ""
        self.token = self.call("POST", "/auth/login", {"email": email, "password": password})["access_token"]

    def call(self, method: str, path: str, body: object | None = None) -> object:
        headers = {"content-type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> {e.code} {e.read().decode()[:400]}") from e


def bookings(api: Api, language: str) -> None:
    terms = {t["code"]: t for t in api.call("GET", "/terms")}
    for code, name in NAMES.items():
        if code in terms and terms[code]["name"] != name:
            api.call("PUT", f"/terms/{terms[code]['id']}", {"name": name})
    guz = terms["2026-GUZ"]
    start = date.fromisoformat(guz["start_date"])
    end = start + timedelta(weeks=guz.get("week_count") or 14, days=-1)
    api.call("PUT", f"/terms/{guz['id']}", {"end_date": end.isoformat()})
    print(f"term {guz['code']}: {start} .. {end}")

    # the imported weekly board of the current term is the published timetable (bookings respect it)
    runs = api.call("GET", "/runs")
    board = next((r for r in runs if r["term_id"] == guz["id"] and r["kind"] == "COURSE"
                  and (r.get("params") or {}).get("source") == "GRID_IMPORT"), None)
    if board and not board.get("is_active"):
        api.call("POST", f"/runs/{board['id']}/activate")
        print(f"published board run #{board['id']}")

    schedules = api.call("GET", "/booking-admin/schedules")
    schedule = next((s for s in schedules if len(s["periods"]) >= 18), None)
    if schedule is None:
        s = api.call("POST", "/booking-admin/schedules", {"name": "Ders saatleri"})
        api.call("POST", f"/booking-admin/schedules/{s['id']}/periods/from-grid?days=1,2,3,4,5")
        schedule = s
    if not api.call("GET", "/room-admin/groups"):
        api.call("POST", "/room-admin/groups/from-buildings")
    api.call("PUT", f"/booking-admin/sessions/{guz['id']}", {"is_selectable": True, "default_schedule_id": schedule["id"]})
    hols = api.call("GET", f"/holidays?term_id={guz['id']}")
    if not any(h["date_start"] == HOLIDAY["date"] for h in hols):
        api.call("POST", "/holidays", {"term_id": guz["id"], "name": HOLIDAY["name"],
                                       "date_start": HOLIDAY["date"], "date_end": HOLIDAY["date"]})
    api.call("PUT", "/auth/profile", {"language": language})
    print(f"bookings ready: schedule #{schedule['id']}, session {guz['code']} open, admin language {language}")


def runs(api: Api, specs: list[str]) -> None:
    terms = {t["code"]: t for t in api.call("GET", "/terms")}
    for spec in specs:
        code, horizon, week, limit = spec.split(":")
        term = terms[code]
        label = f"{LABEL.get(code.split('-')[1], code)} {'week ' + week if horizon == 'WEEK' else 'full term'}"
        body = {"term_id": term["id"], "kind": "COURSE", "horizon": horizon, "label": label,
                "horizon_params": {"weeks": [int(week)]} if horizon == "WEEK" else {},  # what the Studio sends
                "params": {"time_limit_s": float(limit)}}
        rid = api.call("POST", "/runs", body)["run_id"]
        t0 = time.time()
        while True:
            r = api.call("GET", f"/runs/{rid}")
            if r["status"] not in ("QUEUED", "RUNNING", "PENDING"):
                break
            time.sleep(5)
        st = r.get("stats") or {}
        if horizon == "TERM" and r["status"] in ("FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"):
            api.call("POST", f"/runs/{rid}/activate")  # publish it: dashboard, bookings and calendar use it
        print(f"run #{rid} {label}: {r['status']} placed {st.get('placed', '?')}/{st.get('events_total', '?')} "
              f"hard {r.get('hard_score')} in {time.time() - t0:.0f} s")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 1
    base, email, password, cmd, *rest = argv
    api = Api(base, email, password)
    if cmd == "bookings":
        lang = rest[rest.index("--language") + 1] if "--language" in rest else "en"
        bookings(api, lang)
    elif cmd == "runs":
        runs(api, rest or ["2026-GUZ:WEEK:3:120", "2026-GUZ:TERM:-:240"])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
