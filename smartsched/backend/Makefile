.PHONY: check lint format type test dev migrate

PY ?= python3
# Directories owned by other agents (solver-engineer, ai-engineer) run their own gates.
EXCL = --exclude app/solver --exclude app/ai --exclude tests/solver --exclude tests/ai

check: lint type test

lint:
	ruff check app tests $(EXCL)
	ruff format --check app tests $(EXCL)

format:
	ruff check --fix app tests $(EXCL)
	ruff format app tests $(EXCL)

type:
	$(PY) -m mypy app/importers app/services app/workers app/core app/solver/model.py app/solver/stub.py

test:
	$(PY) -m pytest -q --ignore=tests/solver

dev:
	$(PY) -m uvicorn app.main:app --reload --port 8000

migrate:
	alembic upgrade head
