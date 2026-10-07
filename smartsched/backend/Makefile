.PHONY: check lint type test dev migrate

PY ?= python3

check: lint type test

lint:
	ruff check app tests
	ruff format --check app tests

type:
	mypy app/solver app/importers

test:
	$(PY) -m pytest -q

dev:
	$(PY) -m uvicorn app.main:app --reload --port 8000

migrate:
	alembic upgrade head
