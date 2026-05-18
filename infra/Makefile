.PHONY: build up up-with-data down down-clean logs migrate migrate-create playwright-install \
        shell-api shell-worker shell-db test test-unit test-integration test-coverage \
        lint format flower demo-candidate demo-search demo-stats

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
COMPOSE_FILE := $(ROOT_DIR)/infra/docker-compose.yml
ENV_FILE := $(ROOT_DIR)/infra/.env
COMPOSE := docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE)
PYTHONPATH_ENV := PYTHONPATH=$(ROOT_DIR)/backend
PYTEST := $(PYTHONPATH_ENV) python -m pytest -c $(ROOT_DIR)/backend/pytest.ini

# ------------------------------------------------------------------ #
# Docker                                                             #
# ------------------------------------------------------------------ #
build:
	$(COMPOSE) build

# Scale flags — explicit --scale ensures correct replica count regardless of
# Docker Compose version (v1 ignores deploy.replicas; v2 may cache old scales).
SCALE_FLAGS := \
	--scale worker-scraping-bulk=$${WORKER_SCRAPING_BULK_SCALE:-2} \
	--scale worker-scraping-realtime=$${WORKER_SCRAPING_REALTIME_SCALE:-8} \
	--scale worker-enrichment=$${WORKER_ENRICHMENT_SCALE:-3} \
	--scale worker-maintenance=$${WORKER_MAINTENANCE_SCALE:-1} \
	--scale worker-cover-bulk=$${WORKER_COVER_BULK_SCALE:-2} \
	--scale worker-cover-ranking=$${WORKER_COVER_RANKING_SCALE:-2} \
	--scale worker-cover-generation=$${WORKER_COVER_GENERATION_SCALE:-3} \
	--scale worker-cover-workflow=$${WORKER_COVER_WORKFLOW_SCALE:-2} \
	--scale worker-email=$${WORKER_EMAIL_SCALE:-2} \
	--scale worker-agentic=$${WORKER_AGENTIC_SCALE:-2}

up:
	$(COMPOSE) up -d $(SCALE_FLAGS)
	@echo ""
	@echo "Services running (without migrations - run 'make migrate' manually):"
	@echo "  API:        http://localhost:8001"
	@echo "  API Docs:   http://localhost:8001/docs"
	@echo "  Dashboard:  http://localhost:3001"
	@echo "  RabbitMQ:   http://localhost:15672"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana:    http://localhost:3002"

# Start all services with database migrations and seed data
up-with-data:
	@echo "Starting infrastructure services (postgres, rabbitmq, redis)..."
	$(COMPOSE) up -d postgres rabbitmq redis
	@echo "Waiting for postgres to be healthy..."
	@sleep 5
	$(COMPOSE) run --rm alembic
	@echo "Starting application services..."
	$(COMPOSE) up -d $(SCALE_FLAGS)
	@echo ""
	@echo "Application is ready with all tables and data!"
	@echo "  API:        http://localhost:8000"
	@echo "  API Docs:   http://localhost:8000/docs"
	@echo "  Dashboard:  http://localhost:3000"
	@echo "  Flower:     http://localhost:5555"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana:    http://localhost:3001"
	@echo "  MinIO:      http://localhost:9001"

down:
	$(COMPOSE) down

down-clean:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

# ------------------------------------------------------------------ #
# Database                                                           #
# ------------------------------------------------------------------ #
migrate:
	$(COMPOSE) exec api alembic -c backend/alembic.ini upgrade head

migrate-create:
	$(COMPOSE) exec api alembic -c backend/alembic.ini revision --autogenerate -m "$(MSG)"

# ------------------------------------------------------------------ #
# Playwright                                                         #
# ------------------------------------------------------------------ #
playwright-install:
	$(COMPOSE) exec worker playwright install chromium --with-deps

# ------------------------------------------------------------------ #
# Shell access                                                       #
# ------------------------------------------------------------------ #
shell-api:
	$(COMPOSE) exec api bash

shell-worker:
	$(COMPOSE) exec worker bash

shell-db:
	$(COMPOSE) exec postgres psql -U jobhunter -d jobhunter

# ------------------------------------------------------------------ #
# Testing                                                            #
# ------------------------------------------------------------------ #
test:
	$(PYTEST) $(ROOT_DIR)/backend/tests/ -v --tb=short

test-unit:
	$(PYTEST) $(ROOT_DIR)/backend/tests/unit/ -v --tb=short

test-integration:
	$(PYTEST) $(ROOT_DIR)/backend/tests/integration/ -v --tb=short

test-coverage:
	$(PYTEST) $(ROOT_DIR)/backend/tests/ --cov=services --cov-report=html --cov-report=term-missing

# ------------------------------------------------------------------ #
# Code quality                                                       #
# ------------------------------------------------------------------ #
lint:
	flake8 $(ROOT_DIR)/backend/services/ $(ROOT_DIR)/backend/tests/ --max-line-length=120 --exclude=__pycache__

format:
	black $(ROOT_DIR)/backend/services/ $(ROOT_DIR)/backend/tests/ --line-length=120

# ------------------------------------------------------------------ #
# Celery Flower                                                      #
# ------------------------------------------------------------------ #
flower:
	$(COMPOSE) exec worker celery -A services.scraper.celery_app flower --port=5555

# ------------------------------------------------------------------ #
# Demo commands                                                      #
# ------------------------------------------------------------------ #
demo-candidate:
	@echo "Creating sample candidate..."
	curl -s -X POST http://localhost:8000/candidates \
	  -H "Content-Type: application/json" \
	  -H "X-API-Key: change-me-secret" \
	  -d '{ \
	    "name": "Priya Sharma", \
	    "email": "priya@example.com", \
	    "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"], \
	    "years_experience": 4, \
	    "target_roles": ["Backend Engineer", "Python Developer"], \
	    "target_locations": ["Bangalore", "Remote"], \
	    "bio": "Experienced backend engineer specializing in Python microservices.", \
	    "linkedin_url": "https://linkedin.com/in/priyasharma" \
	  }' | python3 -m json.tool

demo-search:
	@echo "Triggering search (requires a candidate_id — update CANDIDATE_ID below)..."
	@read -p "Enter candidate_id from demo-candidate output: " cid; \
	curl -s -X POST http://localhost:8000/search \
	  -H "Content-Type: application/json" \
	  -H "X-API-Key: change-me-secret" \
	  -d "{\"job_titles\": [\"Python Developer\"], \"locations\": [\"Bangalore\"], \"portals\": [\"naukri\", \"indeed\"], \"max_results_per_portal\": 10, \"candidate_id\": \"$$cid\", \"auto_generate_covers\": false}" \
	  | python3 -m json.tool

demo-stats:
	@echo "Fetching stats..."
	curl -s http://localhost:8000/stats \
	  -H "X-API-Key: change-me-secret" \
	  | python3 -m json.tool
