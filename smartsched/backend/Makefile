.PHONY: check lint format type test test-slow test-all dev migrate

PY ?= python3
# app/solver + tests/solver are owned by the solver-engineer and gated separately (CI "Solver gate").
# app/ai + tests/ai are part of this gate since the 2026-10-08 review (MINOR 13).
EXCL = --exclude app/solver --exclude tests/solver

check: lint type test

lint:
	ruff check app tests tools $(EXCL)
	ruff format --check app tests tools $(EXCL)

format:
	ruff check --fix app tests tools $(EXCL)
	ruff format app tests tools $(EXCL)

type:
	$(PY) -m mypy app/api app/ai app/importers app/services app/workers app/core app/solver/model.py app/solver/stub.py tools

# fast gate; the heaviest real-workbook tests (tests/conftest.py SLOW_TESTS) run in test-slow (CI runs both)
test:
	$(PY) -m pytest -q --ignore=tests/solver -m "not slow"

test-slow:
	$(PY) -m pytest -q --ignore=tests/solver -m slow

test-all:
	$(PY) -m pytest -q --ignore=tests/solver

dev:
	$(PY) -m uvicorn app.main:app --reload --port 8000

migrate:
	alembic upgrade head
