.PHONY: help

help:
	@echo "hydro2.0 - targets:"
	@echo "  setup-dev        - подготовить локальную среду (docker-compose.dev)"
	@echo "  up-dev           - поднять локальный стенд (MQTT, БД, backend)"
	@echo "  down-dev         - остановить локальный стенд"

.PHONY: setup-dev
setup-dev:
	@echo "Setup dev environment placeholder"

.PHONY: up-dev
up-dev:
	@echo "Starting dev docker-compose (placeholder)"

.PHONY: down-dev
down-dev:
	@echo "Stopping dev docker-compose (placeholder)"

.PHONY: protocol-check
protocol-check:
	@echo "Running protocol contract tests..."
	@cd backend/services/common/schemas && bash run_protocol_check.sh


