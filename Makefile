SHELL := /bin/bash

PROJECT_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKEND_COMPOSE_FILE := backend/docker-compose.dev.yml

DOCKER_COMPOSE ?= $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; else echo "docker compose"; fi)

.PHONY: help
help:
	@echo "hydro2.0 - targets:"
	@echo "  up             - start dev stack (backend/docker-compose.dev.yml)"
	@echo "  down           - stop dev stack"
	@echo "  migrate        - run Laravel migrations"
	@echo "  test           - run PHP (phpunit) and Python (pytest) tests"
	@echo "  lint           - run PHP lint (Pint)"
	@echo "  smoke          - run bootstrap smoke (telemetry + command)"
	@echo "  audit          - run hotspots audit report"
	@echo "  protocol-check - run protocol contract tests"
	@echo "  erd            - generate ERD SVG (docker mermaid-cli)"

.PHONY: up
up:
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) up -d --build

.PHONY: down
down:
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) down

.PHONY: migrate
migrate: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan migrate

.PHONY: test
test: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan test
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T mqtt-bridge pytest

.PHONY: lint
lint: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel vendor/bin/pint --dirty

.PHONY: smoke
smoke:
	@./tools/smoke-test.sh

.PHONY: audit
audit:
	@python3 tools/audit_hotspots.py

.PHONY: setup-dev up-dev down-dev
setup-dev: up
up-dev: up
down-dev: down

.PHONY: protocol-check
protocol-check:
	@echo "Running protocol contract tests..."
	@cd backend/services/common/schemas && bash run_contract_tests.sh

.PHONY: erd
erd:
	@bash backend/laravel/generate-erd.sh
