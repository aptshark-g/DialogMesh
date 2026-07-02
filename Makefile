# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh — Docker Orchestration Makefile
# ═══════════════════════════════════════════════════════════════════════════════
#  Works on Linux, macOS, and Windows (Git Bash / WSL / Docker Desktop).
# ───────────────────────────────────────────────────────────────────────────────

.PHONY: build up down logs test clean shell prune restart

IMAGE_NAME   ?= dialogmesh
COMPOSE_FILE ?= docker-compose.yml

# Detect docker compose command (legacy vs modern plugin)
DOCKER_COMPOSE := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; else echo "docker-compose"; fi)

# ═══════════════════════════════════════════════════════════════════════════════
#  Build
# ═══════════════════════════════════════════════════════════════════════════════

build:
	@echo "Building DialogMesh Docker image..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build

# ═══════════════════════════════════════════════════════════════════════════════
#  Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

up:
	@echo "Starting DialogMesh services..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo ""
	@echo "DialogMesh is running:"
	@echo "  API Health : http://localhost:8000/health"
	@echo "  API Docs   : http://localhost:8000/docs"
	@echo "  OpenAPI    : http://localhost:8000/redoc"

# Start with forced rebuild
up-build: build up

down:
	@echo "Stopping DialogMesh services..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down

restart: down up

# ═══════════════════════════════════════════════════════════════════════════════
#  Observability
# ═══════════════════════════════════════════════════════════════════════════════

logs:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f app

logs-all:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f

# ═══════════════════════════════════════════════════════════════════════════════
#  Testing
# ═══════════════════════════════════════════════════════════════════════════════

test:
	@echo "Running tests inside the 'app' container..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec app pytest tests/ -v --tb=short

test-cov:
	@echo "Running tests with coverage..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec app pytest tests/ -v --tb=short --cov=core --cov=service --cov-report=term-missing

# ═══════════════════════════════════════════════════════════════════════════════
#  Shell / Debug
# ═══════════════════════════════════════════════════════════════════════════════

shell:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec app /bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
#  Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

clean: down
	@echo "Removing containers, images, and volumes..."
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) rm -f
	-docker rmi $(IMAGE_NAME) 2>/dev/null || true
	-docker volume rm $(IMAGE_NAME)-data 2>/dev/null || true

prune:
	@echo "Pruning unused Docker resources..."
	docker system prune -f

# ═══════════════════════════════════════════════════════════════════════════════
#  Production helpers
# ═══════════════════════════════════════════════════════════════════════════════

prod-up:
	@echo "Starting production stack..."
	$(DOCKER_COMPOSE) -f deploy/docker-compose.prod.yml up -d

prod-down:
	@echo "Stopping production stack..."
	$(DOCKER_COMPOSE) -f deploy/docker-compose.prod.yml down

prod-logs:
	$(DOCKER_COMPOSE) -f deploy/docker-compose.prod.yml logs -f app

prod-deploy: build prod-up
