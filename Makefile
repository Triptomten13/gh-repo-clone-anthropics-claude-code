# Demonkoncernen AB — one command per task. Run `make help`. (Windows without make: see docs/CROSS_PLATFORM.md §commands.)
.PHONY: help install dev dev-lan prod prod-lan health test test-backend test-frontend test-unit test-e2e test-responsive test-a11y \
        test-pwa test-perf lint typecheck build verify pg-smoke independence demo demo-docker test-demo

help:            ## list the commands
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t 18

install:         ## install backend (Python) and frontend (Node) dependencies
	pip install -r backend/requirements-dev.txt "psycopg[binary]>=3.2" ruff
	pip install --only-binary=llama-cpp-python -r backend/requirements-local-ai.txt || echo "local AI runtime not installed (optional)"
	cd frontend && npm ci

dev:             ## start API + web for development on this computer (http://localhost:3000)
	scripts/dev.sh
dev-lan:         ## same, reachable from phones/tablets on your network
	scripts/dev.sh --lan
prod:            ## production build + standalone server (what Docker runs; PWA testable on localhost)
	scripts/dev.sh --prod
prod-lan:        ## production build, reachable on your network
	scripts/dev.sh --lan --prod
demo:            ## the PUBLIC DEMO locally: DEMO_MODE, its own throw-away database (http://localhost:3300)
	rm -rf .demo-data && mkdir -p .demo-data && DEMO_MODE=1 API_PORT=8300 WEB_PORT=3300 DATABASE_URL=sqlite:///$(CURDIR)/.demo-data/demo.db \
	  ARCHIVE_DIR=$(CURDIR)/.demo-data/archive SECRET_KEY=local-demo-only scripts/dev.sh --prod
demo-docker:     ## the public demo as a container (all-in-one image) → http://localhost:3300
	docker compose --profile demo up --build demo
health:          ## check a running instance (WEB=http://… DK_EMAIL=… DK_PASSWORD=… for the full check)
	scripts/health.sh $(or $(WEB),http://localhost:3000)

test: test-backend test-frontend   ## every automated test
test-backend:    ## backend: pytest (unit, API, security, integration)
	cd backend && python -m pytest -q
test-frontend:   ## frontend: unit + device workflows + responsive + accessibility + PWA + performance (starts its own stack)
	cd frontend && npx playwright test
test-unit:       ## frontend unit tests only
	cd frontend && npm run test:unit
test-e2e:        ## workflows on desktop, iPad, iPhone, Android (Chromium emulation)
	cd frontend && npm run test:e2e
test-responsive: ## every page at 320–1920 px, portrait and landscape
	cd frontend && npm run test:responsive
test-a11y:       ## axe accessibility checks (WCAG 2.2 A/AA rules)
	cd frontend && npm run test:a11y
test-pwa:        ## installability and offline behaviour
	cd frontend && npm run test:pwa
test-perf:       ## LCP/CLS/INP/JS size, desktop + throttled phone → frontend/test-results/perf.json
	cd frontend && npm run test:perf
test-demo:       ## public demo suite + PASS/FAIL report (own demo stack; DEMO_BASE_URL=https://… checks a deployed demo)
	cd frontend && npm run test:demo

lint:            ## ruff (backend) + TypeScript strict type check (frontend)
	cd backend && ruff check .
	cd frontend && npx tsc --noEmit
typecheck:       ## frontend type check
	cd frontend && npx tsc --noEmit
build:           ## production build of the web app
	cd frontend && npx next build
verify:          ## lint + backend tests + type check + production build
	scripts/verify.sh
pg-smoke:        ## migrations + main endpoints on PostgreSQL (DATABASE_URL=postgresql+psycopg://…)
	python scripts/pg_smoke.py
independence:    ## real local-model tests (needs installed models)
	python scripts/independence_test.py
