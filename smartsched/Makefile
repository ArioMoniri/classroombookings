# SmartSched top-level targets (backend + frontend + deploy). Usage: make -C smartsched <target>
.PHONY: help deploy deploy-legacy update down logs status dev check check-backend check-frontend \
        check-all e2e watchdog watchdog-check validate

PY ?= python3
ROOT := $(abspath $(CURDIR)/..)

help:              ## list targets
	@grep -E '^[a-z-]+:.*##' $(firstword $(MAKEFILE_LIST)) | sed 's/:.*## /\t/' | expand -t 18

deploy:            ## build + start the docker compose stack (generates deploy/.env with secrets on first run)
	./deploy/deploy.sh

deploy-legacy:     ## same, plus the legacy CRBS app (profile legacy)
	./deploy/deploy.sh --legacy

update:            ## git pull, rebuild, restart (migrations run on start)
	./deploy/deploy.sh --update

down:              ## stop the stack (data volumes kept)
	./deploy/deploy.sh --down

logs:              ## follow container logs
	./deploy/deploy.sh --logs

status:            ## container status + health
	./deploy/deploy.sh --status

dev:               ## local dev without Docker: venv, npm ci, SQLite, seeded admin, backend :8000 + frontend :3000
	$(ROOT)/scripts/dev.sh --run

check: check-backend check-frontend   ## quality gates: backend make check + frontend npm run check

check-backend:     ## ruff + mypy + pytest (backend scope)
	$(MAKE) -C backend check PY=$(PY)

check-frontend:    ## tsc + eslint + vitest
	cd frontend && npm run check

check-all: check   ## check + solver/AI gates + deploy validation (what CI runs, minus Docker builds)
	cd backend && ruff check app/solver && $(PY) -m mypy app/solver && $(PY) -m pytest tests/solver -q
	cd backend && if [ -d app/ai ]; then ruff check app/ai; fi
	cd backend && if grep -q -- '--ignore=tests/ai' Makefile && [ -d tests/ai ]; then $(PY) -m pytest tests/ai -q; fi
	./deploy/validate.sh

e2e:               ## Playwright smoke (mock API, builds next on :3100)
	cd frontend && npx playwright test

watchdog:          ## agent ledger report (docs/PROGRESS.md): stale / active / done
	-$(PY) $(ROOT)/scripts/watchdog.py

watchdog-check:    ## ledger report + run backend/frontend gates
	$(PY) $(ROOT)/scripts/watchdog.py --check

validate:          ## static validation of deploy files (no Docker daemon needed)
	./deploy/validate.sh
