"""RF-14: the learning time bands (sabah P1-P6, öğleden sonra P7-P12, akşam P13-P18) show the clock times of the
admin-editable period grid (RF-09, ``app.services.period_grid``), not fixed times.

* a habit sentence computed after a grid change names the new times;
* a habit stored before the change (the sentence keeps the old times) is shown with the current times when read
  (GET /learning/priors on the real Bahar + Güz 2026 planning lists of ``tests/test_p19_learning.py``);
* nothing is cached at import time: ``normalize.PERIODS`` is changed in place.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.importers import normalize as n
from app.models import LearnedPrior
from app.services import learning, period_grid
from sqlalchemy import select

from tests.test_p19_learning import _session, env  # noqa: F401

API = "/api/v1"
DEFAULT = [(f"{p.start:%H:%M}", f"{p.end:%H:%M}") for p in n.DEFAULT_PERIODS]


@pytest.fixture(autouse=True)
def _default_grid() -> Iterator[None]:
    n.set_period_grid(None)
    yield
    n.set_period_grid(None)


def _faculty_grid() -> None:
    """The faculty starts at 08.00 and the afternoon ends at 17.50 (dotted times and an NBSP, as pasted from the
    senate's circular); every other period keeps its default time."""
    times: list[tuple[str, str]] = list(DEFAULT)
    times[0] = ("08.00", "08:40 ")
    times[11] = ("17.30", "17.50")
    n.set_period_grid(period_grid.parse([{"start": s, "end": e} for s, e in times]))


def test_band_hours_follow_the_period_grid() -> None:
    assert learning.band_hours("morning") == "08:30–13:20"
    assert learning.band_hours("afternoon") == "13:30–18:00"
    assert learning.band_hours("evening") == "18:00–22:50"
    _faculty_grid()
    assert learning.band_hours("morning") == "08:00–13:20"
    assert learning.band_hours("afternoon") == "13:30–17:50"
    vt = learning._value_text("period", "morning", {})
    assert vt["tr"] == "sabah saatleri (08:00–13:20)"
    assert vt["tr_loc"] == "sabah saatlerinde (08:00–13:20)"
    assert vt["en"] == "the morning (08:00–13:20)"
    assert learning.band_hours("night") == ""  # not a band: no hours


def test_a_stored_sentence_is_read_with_the_current_grid() -> None:
    stored = "{subject} derslerinin 4/5'i sabah saatlerinde (08:30–13:20) yapıldı."
    assert learning._fill(stored, "BME 419", "morning") == "BME 419 derslerinin 4/5'i sabah saatlerinde (08:30–13:20) yapıldı."
    _faculty_grid()
    assert learning._fill(stored, "BME 419", "morning") == "BME 419 derslerinin 4/5'i sabah saatlerinde (08:00–13:20) yapıldı."
    # a room or building sentence has no band: nothing else is touched
    assert learning._fill("{subject} A 204'te (08:30–13:20)", "BME 419", None) == "BME 419 A 204'te (08:30–13:20)"


async def test_learned_period_habit_shows_the_admins_grid(env) -> None:  # noqa: F811
    r = await env.client.post(f"{API}/learning/refresh", json={"term_id": env.guz}, headers=env.planner)
    assert r.status_code == 200, r.text
    async with _session() as s:
        p = (
            await s.execute(
                select(LearnedPrior)
                .where(LearnedPrior.term_id == env.guz, LearnedPrior.attribute == "period")
                .order_by(LearnedPrior.id)
                .limit(1)
            )
        ).scalar_one()
        band, key = p.value, p.subject_key
    old = learning.band_hours(band)
    assert old in str((p.explanation or {}).get("tr"))

    # the admins move the grid; the stored habit still has the old times, the API shows the new ones
    times: list[tuple[str, str]] = list(DEFAULT)
    lo, hi = next((lo, hi) for name, lo, hi in learning.BANDS if name == band)
    times[lo - 1] = (f"{n.PERIODS[lo - 1].start:%H}.05", f"{n.PERIODS[lo - 1].end:%H:%M}")
    n.set_period_grid(period_grid.parse([{"start": s, "end": e} for s, e in times]))
    new = learning.band_hours(band)
    assert new != old and new.endswith(f"{n.PERIODS[hi - 1].end:%H:%M}")

    r = await env.client.get(
        f"{API}/learning/priors",
        params={"term_id": env.guz, "subject_type": p.subject_type, "subject_id": key},
        headers=env.planner,
    )
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x["id"] == p.id)
    assert new in row["explanation"]["tr"] and old not in row["explanation"]["tr"]
    assert new in row["explanation"]["en"]
    assert new in row["value_label"]["tr"] and new in row["value_label"]["en"]
