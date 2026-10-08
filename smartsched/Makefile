# SmartSched top-level targets (backend + frontend + deploy). Run from smartsched/.
.PHONY: deploy deploy-legacy down logs dev check check-backend check-frontend e2e watchdog validate

PY ?= python3

deploy:            ## build + start the docker compose stack (generates .env on first run)
	./deploy/deploy.sh

deploy-legacy:     ## same, plus the legacy CRBS app (profile legacy)
	./deploy/deploy.sh --legacy

down:
	./deploy/deploy.sh --down

logs:
	./deploy/deploy.sh --logs

dev:               ## backend uvicorn (:8000) + frontend next dev (:3000) concurrently
	../scripts/dev.sh --run

check: check-backend check-frontend   ## all quality gates

check-backend:
	$(MAKE) -C backend check
	cd backend && $(PY) -m pytest tests/solver -q

check-frontend:
	cd frontend && npm run check

e2e:
	cd frontend && npx playwright test

watchdog:          ## agent ledger report (docs/PROGRESS.md) + gates
	$(PY) ../scripts/watchdog.py --check

validate:          ## static validation of deploy files (no daemon needed)
	./deploy/validate.sh
