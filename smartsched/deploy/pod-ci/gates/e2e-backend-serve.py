"""Serve the REAL backend for the browser e2e stack, with the booking clock pinned inside Bahar 2026.

E2E stack only (pod CI gate e2e-real.sh via e2e-backend-entry.sh, or a local run of that script); the
product code is not changed. The Bahar fixtures are a past term and staff cannot book the past, so
``E2E_BOOKING_CLOCK`` (ISO date-time, default Monday 16 Feb 2026 08:00 = Bahar week 3) replaces
``app.services.bookings.today/now_local``: the same two-function patch ``tests/crbs_env.py`` applies
in the backend test suite. ``E2E_BOOKING_CLOCK=`` (empty) keeps the wall clock.

    python e2e-backend-serve.py [--host 0.0.0.0] [--port 8000]      (cwd: smartsched/backend)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from typing import Any

DEFAULT_CLOCK = "2026-02-16T08:00"


def pin_booking_clock(value: str) -> datetime | None:
    if not value:
        return None
    fixed = datetime.fromisoformat(value).replace(tzinfo=None)
    from app.services import bookings

    async def now_local(_session: Any) -> datetime:
        return fixed

    async def today(_session: Any) -> date:
        return fixed.date()

    bookings.now_local = now_local  # type: ignore[assignment]
    bookings.today = today  # type: ignore[assignment]
    return fixed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # inside the per-run docker network the Playwright container reaches the backend by its alias
    p.add_argument("--host", default=os.environ.get("E2E_HOST", "0.0.0.0"))  # noqa: S104
    p.add_argument("--port", type=int, default=int(os.environ.get("E2E_PORT", "8000")))
    args = p.parse_args()
    sys.path.insert(0, os.getcwd())  # app/ lives in the backend directory
    fixed = pin_booking_clock(os.environ.get("E2E_BOOKING_CLOCK", DEFAULT_CLOCK))
    print(f"e2e backend: booking clock {'pinned to ' + fixed.isoformat() if fixed else '= wall clock'}", flush=True)
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
