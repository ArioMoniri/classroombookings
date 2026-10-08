"""Fixtures and the ``parity`` marker for the CRBS parity acceptance tests.

Each test names the inventory rows it proves with ``@pytest.mark.parity("B-ROOMS-09", ...)`` (rows in
``tests/parity/inventory.py``). ``scripts/parity_check.py`` runs these tests together with the existing
``tests/test_crbs_*`` tests the inventory references and prints one line per row."""

from __future__ import annotations

from tests.crbs_env import env  # noqa: F401  (the real Bahar 2026 booking environment)
from tests.parity.plugin import MARKER


def pytest_configure(config):  # type: ignore[no-untyped-def]
    config.addinivalue_line("markers", MARKER)
