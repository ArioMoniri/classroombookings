.PHONY: check lint format type test test-slow test-all dev migrate lock

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
	$(PY) -m mypy app/api app/ai app/importers app/services app/workers app/core app/council app/solver/model.py app/solver/stub.py tools

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

# SECURITY F13: hash-pinned locks (uv), installed with `pip install --require-hashes` by the Dockerfile and pod CI.
# Each lock is its own constraint, so `make lock` keeps every version; upgrade one with
# `make lock UV_ARGS="--upgrade-package <name>"`. requirements-dev.lock = the runtime pins + pytest/ruff/mypy;
# requirements-build.lock = setuptools (the build backend, installed hashed and used with --no-build-isolation).
UV_COMPILE = uv pip compile --universal --python-version 3.12 --no-annotate --generate-hashes --custom-compile-command "make lock" $(UV_ARGS)
self_c = $(if $(wildcard $(1)),-c $(1))

lock:
	$(UV_COMPILE) pyproject.toml $(call self_c,requirements.lock) -o requirements.lock
	$(UV_COMPILE) pyproject.toml --extra dev -c requirements.lock $(call self_c,requirements-dev.lock) -o requirements-dev.lock
	echo "setuptools>=68" | $(UV_COMPILE) - $(call self_c,requirements-build.lock) -o requirements-build.lock
