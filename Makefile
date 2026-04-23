SHELL := /bin/bash

PROJECT_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKEND_COMPOSE_FILE := backend/docker-compose.dev.yml
MIGRATE_SEEDER_CLASS ?= DevBootstrapSeeder
REFRESH_SEEDER_CLASS ?= StartUsersSeeder
RESET_DB_SEEDER_CLASS ?= $(REFRESH_SEEDER_CLASS)
RESET_DB_APP_ENV ?= local
RESET_DB_DATABASE ?= hydro_dev

# Laravel PHPUnit: изолированная БД и APP_ENV=testing (иначе guard в tests/RefreshDatabase.php и env контейнера ломают прогон).
LARAVEL_TEST_DB ?= hydro_test
# Пример: make test-laravel LARAVEL_TEST_ARGS="tests/Feature/PythonIngestControllerTest.php"
LARAVEL_TEST_ARGS ?=

DOCKER_COMPOSE ?= $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; else echo "docker compose"; fi)

.PHONY: help
help:
	@echo "hydro2.0 - targets:"
	@echo "  up             - start dev stack (backend/docker-compose.dev.yml)"
	@echo "  down           - stop dev stack"
	@echo "  migrate        - run Laravel migrations and dev bootstrap seeders"
	@echo "  refresh        - full clean dev refresh with only base users in DB"
	@echo "  seed           - run Laravel seeders"
	@echo "  reset-db       - reset dev DB and seed only base users"
	@echo "  test           - run PHP (phpunit) and Python (pytest) tests"
	@echo "  lint           - run PHP lint (Pint)"
	@echo "  smoke          - run bootstrap smoke (telemetry + command)"
	@echo "  audit          - run hotspots audit report"
	@echo "  protocol-check - run protocol contract tests (incl. schemas-validate)"
	@echo "  ae3-config-lint - check inline numeric literals in AE3 handlers"
	@echo "  schemas-validate - validate JSON Schemas under schemas/ against meta-schema"
	@echo "  logs           - stream logs for selected service (SERVICE=<name>, TAIL=200)"
	@echo "  logs-core      - stream logs for core runtime services"
	@echo "  logs-laravel   - stream Laravel logs"
	@echo "  logs-ae        - stream automation-engine logs"
	@echo "  logs-hl        - stream history-logger logs"
	@echo "  logs-mqttb     - stream mqtt-bridge logs"
	@echo "  logs-db        - stream PostgreSQL logs"
	@echo "  logs-redis     - stream Redis logs"
	@echo "  logs-mqtt      - stream MQTT broker logs"
	@echo "  erd            - generate ERD SVG (docker mermaid-cli)"
	@echo "  dev-tools-check   - check host CLI tools (rg, psql, mosquitto_pub, gh, ...)"
	@echo "  dev-tools-install - install missing host CLI tools (apt + uv)"

.PHONY: up
up:
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) up -d --build

.PHONY: down
down:
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) down

.PHONY: refresh
refresh:
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) down -v --remove-orphans --rmi all
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) pull --ignore-pull-failures
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) build --pull --no-cache
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) up -d --force-recreate --renew-anon-volumes
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d hydro_dev -c "CREATE EXTENSION IF NOT EXISTS pg_cron;" >/dev/null
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan migrate --force
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan db:seed --class=$(REFRESH_SEEDER_CLASS) --force

.PHONY: migrate
migrate: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan migrate --force
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan db:seed --class=$(MIGRATE_SEEDER_CLASS) --force

.PHONY: seed
seed: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T laravel php artisan db:seed

.PHONY: reset-db
reset-db: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d $(RESET_DB_DATABASE) -c "CREATE EXTENSION IF NOT EXISTS pg_cron;" >/dev/null
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		-e APP_ENV=$(RESET_DB_APP_ENV) \
		-e DB_DATABASE=$(RESET_DB_DATABASE) \
		laravel php artisan migrate:fresh --seed --seeder=$(RESET_DB_SEEDER_CLASS)

.PHONY: test test-laravel
test-laravel: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$(LARAVEL_TEST_DB)'" | grep -q 1 \
		|| $(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d postgres -c "CREATE DATABASE $(LARAVEL_TEST_DB);"
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		-e APP_ENV=testing \
		-e DB_DATABASE=$(LARAVEL_TEST_DB) \
		-e DB_CONNECTION=pgsql \
		-e DB_HOST=db \
		-e DB_PORT=5432 \
		-e DB_USERNAME=hydro \
		-e DB_PASSWORD=hydro \
		laravel php artisan test $(LARAVEL_TEST_ARGS)

.PHONY: test-db-init
test-db-init: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$(LARAVEL_TEST_DB)'" | grep -q 1 \
		|| $(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d postgres -c "CREATE DATABASE $(LARAVEL_TEST_DB) WITH OWNER hydro;"
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d $(LARAVEL_TEST_DB) -c "CREATE EXTENSION IF NOT EXISTS timescaledb; CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		-e APP_ENV=testing \
		-e DB_DATABASE=$(LARAVEL_TEST_DB) \
		laravel php artisan migrate --force

.PHONY: test-db-reset
test-db-reset: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T db psql -U hydro -d postgres -c "DROP DATABASE IF EXISTS $(LARAVEL_TEST_DB);" >/dev/null
	@$(MAKE) test-db-init

.PHONY: test-ae
test-ae: test-db-init
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		-e AE3_PYTEST_DB=$(LARAVEL_TEST_DB) \
		automation-engine pytest $(PYTEST_ARGS)

.PHONY: test-hl
test-hl: test-db-init
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		-e PG_DB=$(LARAVEL_TEST_DB) \
		-e DB_DATABASE=$(LARAVEL_TEST_DB) \
		history-logger pytest $(PYTEST_ARGS)

.PHONY: test-mqttb
test-mqttb: test-db-init
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		-e PG_DB=$(LARAVEL_TEST_DB) \
		-e DB_DATABASE=$(LARAVEL_TEST_DB) \
		mqtt-bridge pytest $(PYTEST_ARGS)

.PHONY: test-agg
test-agg: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		telemetry-aggregator pytest $(PYTEST_ARGS)

.PHONY: test-fb
test-fb: up
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T \
		feature-builder pytest $(PYTEST_ARGS)

test: test-laravel test-ae test-hl test-mqttb test-agg test-fb

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

.PHONY: schemas-validate
schemas-validate:
	@echo "Validating JSON Schemas under schemas/..."
	@if [ -x venv/bin/python3 ]; then \
		venv/bin/python3 tools/validate_schemas.py schemas; \
	else \
		python3 tools/validate_schemas.py schemas; \
	fi

.PHONY: ae3-config-lint
ae3-config-lint:
	@python3 tools/ae3_config_lint.py

.PHONY: generate-authority
generate-authority:
	@echo "Generating AUTHORITY.md from schemas/*.v1.json..."
	@python3 tools/generate_authority.py

.PHONY: authority-check
authority-check:
	@echo "Checking AUTOMATION_CONFIG_AUTHORITY.md is regenerated (CI guard)..."
	@python3 tools/generate_authority.py --check

.PHONY: generate-config-catalog
generate-config-catalog:
	@echo "Validating zone_correction_defaults.json against zone_correction.v1.json..."
	@if [ -x venv/bin/python3 ]; then \
		venv/bin/python3 tools/generate_zone_correction_catalog.py; \
	else \
		python3 tools/generate_zone_correction_catalog.py; \
	fi

.PHONY: check-config-catalog
check-config-catalog:
	@echo "CI guard: zone_correction_defaults.json vs zone_correction.v1.json..."
	@if [ -x venv/bin/python3 ]; then \
		venv/bin/python3 tools/generate_zone_correction_catalog.py --check; \
	else \
		python3 tools/generate_zone_correction_catalog.py --check; \
	fi

.PHONY: protocol-check
protocol-check: schemas-validate authority-check ae3-config-lint check-config-catalog
	@echo "Running protocol contract tests..."
	@./tools/check_runtime_schema_parity.sh
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T mqtt-bridge pytest common/schemas/test_contracts.py -v --tb=short
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T mqtt-bridge pytest common/schemas/test_protocol_contracts.py -v --tb=short || echo "⚠️  Legacy protocol tests failed"
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T mqtt-bridge pytest common/schemas/test_chaos.py -v --tb=short -m "not slow" || echo "⚠️  Chaos tests failed (non-blocking)"
	@$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) exec -T mqtt-bridge pytest common/schemas/test_websocket_events.py -v --tb=short

.PHONY: logs logs-core logs-laravel logs-ae logs-hl logs-mqttb logs-db logs-redis logs-mqtt
logs:
	@service="$(SERVICE)"; tail="$${TAIL:-200}"; \
	if [ -z "$$service" ]; then \
		echo "Usage: make logs SERVICE=<service> [TAIL=200]"; \
		exit 1; \
	fi; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f "$$service"

logs-core:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f laravel automation-engine history-logger mqtt-bridge

logs-laravel:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f laravel

logs-ae:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f automation-engine

logs-hl:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f history-logger

logs-mqttb:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f mqtt-bridge

logs-db:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f db

logs-redis:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f redis

logs-mqtt:
	@tail="$${TAIL:-200}"; \
	$(DOCKER_COMPOSE) -f $(BACKEND_COMPOSE_FILE) logs --tail="$$tail" -f mqtt

.PHONY: erd
erd:
	@bash backend/laravel/generate-erd.sh

# ---------------------------------------------------------------------------
# Host CLI tools (полезны для работы agent-а и ручной отладки).
# Не требуются для dev-стека (он в Docker), но ускоряют work-flow.
# Описание — в CLAUDE.md → "Локально доступные CLI-инструменты".
# ---------------------------------------------------------------------------

# Формат: "binary:apt-package" (binary совпадает с apt-package — указать один раз)
DEV_TOOLS_APT := \
	rg:ripgrep \
	jq:jq \
	yq:yq \
	fzf:fzf \
	tree:tree \
	htop:htop \
	btop:btop \
	tig:tig \
	gh:gh \
	http:httpie \
	delta:git-delta \
	psql:postgresql-client \
	mosquitto_pub:mosquitto-clients \
	fdfind:fd-find \
	batcat:bat

.PHONY: dev-tools-check
dev-tools-check:
	@missing_apt=""; missing_uv=""; ok=""; \
	for pair in $(DEV_TOOLS_APT); do \
		bin="$${pair%%:*}"; pkg="$${pair##*:}"; \
		if command -v "$$bin" >/dev/null 2>&1; then \
			ok="$$ok $$bin"; \
		else \
			missing_apt="$$missing_apt $$pkg"; \
		fi; \
	done; \
	if ! command -v uv >/dev/null 2>&1; then missing_uv="uv $$missing_uv"; fi; \
	if ! command -v pgcli >/dev/null 2>&1; then missing_uv="pgcli $$missing_uv"; fi; \
	echo "OK:$$ok"; \
	if [ -n "$$missing_apt" ]; then echo "MISS (apt):$$missing_apt"; fi; \
	if [ -n "$$missing_uv" ]; then echo "MISS (uv):$$missing_uv"; fi; \
	if [ -z "$$missing_apt$$missing_uv" ]; then \
		echo "Все инструменты установлены."; \
	else \
		echo ""; echo "Запусти: make dev-tools-install"; exit 1; \
	fi

.PHONY: dev-tools-install
dev-tools-install:
	@missing_apt=""; need_uv=0; need_pgcli=0; \
	for pair in $(DEV_TOOLS_APT); do \
		bin="$${pair%%:*}"; pkg="$${pair##*:}"; \
		if ! command -v "$$bin" >/dev/null 2>&1; then missing_apt="$$missing_apt $$pkg"; fi; \
	done; \
	if ! command -v uv >/dev/null 2>&1; then need_uv=1; fi; \
	if ! command -v pgcli >/dev/null 2>&1; then need_pgcli=1; fi; \
	if [ -n "$$missing_apt" ]; then \
		echo "==> apt install:$$missing_apt"; \
		sudo apt update && sudo apt install -y $$missing_apt; \
	fi; \
	mkdir -p "$$HOME/.local/bin"; \
	if command -v fdfind >/dev/null 2>&1 && ! command -v fd >/dev/null 2>&1; then \
		ln -sf "$$(command -v fdfind)" "$$HOME/.local/bin/fd"; \
		echo "==> symlink: ~/.local/bin/fd -> fdfind"; \
	fi; \
	if command -v batcat >/dev/null 2>&1 && ! command -v bat >/dev/null 2>&1; then \
		ln -sf "$$(command -v batcat)" "$$HOME/.local/bin/bat"; \
		echo "==> symlink: ~/.local/bin/bat -> batcat"; \
	fi; \
	if [ "$$need_uv" = "1" ]; then \
		echo "==> install uv (Astral installer)"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi; \
	if [ "$$need_pgcli" = "1" ]; then \
		echo "==> install pgcli via uv"; \
		PATH="$$HOME/.local/bin:$$PATH" uv tool install pgcli; \
	fi; \
	echo ""; $(MAKE) --no-print-directory dev-tools-check
